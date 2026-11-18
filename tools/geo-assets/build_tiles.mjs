#!/usr/bin/env node
/**
 * Build calibrated XYZ satellite tiles (`assets/geo/tiles/{z}/{x}/{y}.jpg`)
 * and lightweight thematic GeoJSON vectors (`assets/geo/vector/*.geojson`)
 * from raw downloaded assets in `assets/geo/raw/`.
 *
 * Uses `sharp` (libvips) to apply a deterministic documentary color grade at
 * build time (deepening ocean water toward Geoverum `#03161F` while preserving
 * natural terrain relief and coastal reef turquoise), avoiding runtime CSS filters.
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const GEO_ROOT = join(REPO_ROOT, "assets/geo");
const RAW_DIR = join(GEO_ROOT, "raw");
const TILES_OUT = join(GEO_ROOT, "tiles");
const VECTOR_OUT = join(GEO_ROOT, "vector");

/**
 * Apply Geoverum documentary dark-ocean / crisp-relief grading to a 256x256 RGB tile buffer.
 * Water pixels (where blue > red * 1.08 and blue > green * 0.92 and luma < 140) are darkened
 * toward deep abyssal navy `#03161F`, while coastal shallows keep their cyan/turquoise glow
 * and landmass relief receives a subtle contrast & vegetation boost.
 */
async function gradeTile(inputPath, outPath, blendPath = null, blendWeight = 0.0) {
  const inputSize = statSync(inputPath).size;
  const effectivePrimary =
    inputSize <= 250 && blendPath && existsSync(blendPath) ? blendPath : inputPath;

  if (statSync(effectivePrimary).size <= 250) {
    // Pure open-ocean / polar nodata tile: render solid Geoverum abyssal ocean (#03161F)
    mkdirSync(dirname(outPath), { recursive: true });
    await sharp({
      create: { width: 256, height: 256, channels: 3, background: { r: 3, g: 22, b: 31 } },
    })
      .jpeg({ quality: 86, mozjpeg: true })
      .toFile(outPath);
    return;
  }

  const { data, info } = await sharp(effectivePrimary)
    .flatten({ background: { r: 3, g: 22, b: 31 } })
    .removeAlpha()
    .resize(256, 256)
    .raw()
    .toBuffer({ resolveWithObject: true });

  let blendData = null;
  if (
    effectivePrimary !== blendPath &&
    blendPath &&
    existsSync(blendPath) &&
    statSync(blendPath).size > 250 &&
    blendWeight > 0
  ) {
    const b = await sharp(blendPath)
      .flatten({ background: { r: 3, g: 22, b: 31 } })
      .removeAlpha()
      .resize(256, 256)
      .raw()
      .toBuffer();
    blendData = b;
  }

  const out = Buffer.allocUnsafe(data.length);
  for (let i = 0; i < data.length; i += 3) {
    let r = data[i];
    let g = data[i + 1];
    let b = data[i + 2];

    if (blendData) {
      r = r * (1 - blendWeight) + blendData[i] * blendWeight;
      g = g * (1 - blendWeight) + blendData[i + 1] * blendWeight;
      b = b * (1 - blendWeight) + blendData[i + 2] * blendWeight;
    }

    const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    const blueDominance = b - Math.max(r * 1.05, g * 0.88);
    const maxCh = Math.max(r, g, b);

    if (maxCh < 22 || (blueDominance > 3 && luma < 155)) {
      // Open-ocean nodata (near-black in Sentinel-2 coastal mask) or blue water:
      // pull smoothly toward Geoverum abyssal navy (#03161F = 3, 22, 31)
      const nodataStrength = maxCh < 22 ? Math.min(1, (22 - maxCh) / 14) : 0;
      const waterStrength = Math.max(
        nodataStrength,
        Math.min(1, Math.max(0, blueDominance) / 26) * Math.min(1, (160 - luma) / 95)
      );
      const targetR = 3 + r * 0.22;
      const targetG = 22 + g * 0.36;
      const targetB = 31 + b * 0.44;
      r = r * (1 - waterStrength) + targetR * waterStrength;
      g = g * (1 - waterStrength) + targetG * waterStrength;
      b = b * (1 - waterStrength) + targetB * waterStrength;
    } else {
      // Land / clouds / shallow reef: subtle S-curve contrast and warm-natural clarity
      const c = 1.08;
      r = (r - 110) * c + 106;
      g = (g - 110) * (c * 1.02) + 108;
      b = (b - 110) * (c * 0.96) + 102;
    }

    out[i] = Math.max(0, Math.min(255, Math.round(r)));
    out[i + 1] = Math.max(0, Math.min(255, Math.round(g)));
    out[i + 2] = Math.max(0, Math.min(255, Math.round(b)));
  }

  mkdirSync(dirname(outPath), { recursive: true });
  await sharp(out, { raw: { width: info.width, height: info.height, channels: 3 } })
    .jpeg({ quality: 86, mozjpeg: true })
    .toFile(outPath);
}

function listTilesRecursive(rootDir) {
  const results = [];
  if (!existsSync(rootDir)) return results;
  for (const zStr of readdirSync(rootDir)) {
    const zDir = join(rootDir, zStr);
    const z = Number(zStr);
    if (!Number.isInteger(z)) continue;
    for (const xStr of readdirSync(zDir)) {
      const xDir = join(zDir, xStr);
      const x = Number(xStr);
      if (!Number.isInteger(x)) continue;
      for (const yFile of readdirSync(xDir)) {
        if (!yFile.endsWith(".jpg")) continue;
        const y = Number(yFile.replace(/\.jpg$/, ""));
        results.push({ z, x, y, path: join(xDir, yFile) });
      }
    }
  }
  return results;
}

/**
 * Round coordinates to 4 decimal places (~11m precision) to keep GeoJSON files compact.
 */
function roundCoords(coords) {
  if (typeof coords[0] === "number") {
    return [+coords[0].toFixed(4), +coords[1].toFixed(4)];
  }
  return coords.map(roundCoords);
}

function bboxIntersects(geom, [minLon, minLat, maxLon, maxLat]) {
  let hit = false;
  function walk(c) {
    if (hit) return;
    if (typeof c[0] === "number") {
      if (c[0] >= minLon && c[0] <= maxLon && c[1] >= minLat && c[1] <= maxLat) hit = true;
      return;
    }
    for (const sub of c) walk(sub);
  }
  walk(geom.coordinates);
  return hit;
}

/**
 * Build curated, lightweight GeoJSON datasets in `assets/geo/vector/` for Geoverum scenes.
 */
function buildVectorDatasets() {
  mkdirSync(VECTOR_OUT, { recursive: true });
  const rawVec = join(RAW_DIR, "vector");

  // 1. Countries (Turkey, India, Pakistan, Armenia, Azerbaijan, Greece, Cyprus, Indonesia, Malaysia, Philippines, Australia)
  const admin0 = JSON.parse(readFileSync(join(rawVec, "ne_10m_admin_0_countries.geojson"), "utf8"));
  const targetCountries = new Set([
    "Indonesia",
    "Malaysia",
    "Philippines",
    "Australia",
    "Papua New Guinea",
    "Timor-Leste",
    "Brunei",
    "Singapore",
    "Turkey",
    "India",
    "Pakistan",
    "Armenia",
    "Azerbaijan",
    "Greece",
    "Cyprus",
    "Iran",
    "Iraq",
    "Syria",
    "Georgia",
  ]);
  const countriesFeatures = admin0.features
    .filter((f) => targetCountries.has(f.properties.ADMIN) || targetCountries.has(f.properties.NAME))
    .map((f) => ({
      type: "Feature",
      properties: {
        name: f.properties.NAME || f.properties.ADMIN,
        iso_a2: f.properties.ISO_A2,
        iso_a3: f.properties.ISO_A3,
        subregion: f.properties.SUBREGION,
      },
      geometry: {
        type: f.geometry.type,
        coordinates: roundCoords(f.geometry.coordinates),
      },
    }));
  writeFileSync(
    join(VECTOR_OUT, "countries_curated.geojson"),
    JSON.stringify({ type: "FeatureCollection", features: countriesFeatures })
  );

  // 2. Sulawesi Unified Exterior Coastline (from admin_0 so zero internal administrative seams exist)
  //    plus 4 peninsula zones clipped to the exterior coastline for progressive sweep animations.
  const idnFeature = admin0.features.find((f) => f.properties.ISO_A3 === "IDN");
  const sulawesiArchipelagoPolys = idnFeature.geometry.coordinates.filter((poly) => {
    const ring = poly[0];
    let cx = 0;
    let cy = 0;
    for (const [x, y] of ring) {
      cx += x;
      cy += y;
    }
    cx /= ring.length;
    cy /= ring.length;
    if (cx < 118.5 || cx > 125.6 || cy < -6.0 || cy > 2.0) return false;
    if (cx < 119.15 && cy > -2.5) return false; // Exclude East Kalimantan shoreline
    if (cx > 124.2 && cy < -1.2) return false; // Exclude Maluku (Taliabu/Buru)
    return true;
  });

  // Sort by vertex count descending so index 0 is the 1792-vertex Sulawesi mainland polygon
  sulawesiArchipelagoPolys.sort((a, b) => b[0].length - a[0].length);
  const sulawesiMainlandPoly = sulawesiArchipelagoPolys[0];

  const sulawesiOutline = [
    {
      type: "Feature",
      properties: {
        name: "Sulawesi Mainland",
        feature_type: "mainland_exterior",
      },
      geometry: {
        type: "Polygon",
        coordinates: roundCoords(sulawesiMainlandPoly),
      },
    },
    {
      type: "Feature",
      properties: {
        name: "Sulawesi Archipelago",
        feature_type: "island_outline",
      },
      geometry: {
        type: "MultiPolygon",
        coordinates: roundCoords(sulawesiArchipelagoPolys),
      },
    },
  ];

  const admin1 = JSON.parse(readFileSync(join(rawVec, "ne_10m_admin_1_states_provinces.geojson"), "utf8"));
  const sulawesiProvinces = new Set([
    "Sulawesi Utara",
    "Gorontalo",
    "Sulawesi Tengah",
    "Sulawesi Barat",
    "Sulawesi Selatan",
    "Sulawesi Tenggara",
  ]);
  const peninsulaRole = {
    "Sulawesi Utara": "northern_peninsula",
    Gorontalo: "northern_peninsula",
    "Sulawesi Tengah": "eastern_peninsula",
    "Sulawesi Tenggara": "southeastern_peninsula",
    "Sulawesi Selatan": "southern_peninsula",
    "Sulawesi Barat": "southern_peninsula",
  };
  const sulawesiFeatures = admin1.features
    .filter((f) => f.properties.admin === "Indonesia" && sulawesiProvinces.has(f.properties.name))
    .map((f) => ({
      type: "Feature",
      properties: {
        name: f.properties.name,
        peninsula: peninsulaRole[f.properties.name] || "sulawesi",
        feature_type: "peninsula_mask",
        iso_3166_2: f.properties.iso_3166_2,
      },
      geometry: {
        type: f.geometry.type,
        coordinates: roundCoords(f.geometry.coordinates),
      },
    }));

  writeFileSync(
    join(VECTOR_OUT, "sulawesi_regions.geojson"),
    JSON.stringify({
      type: "FeatureCollection",
      features: [...sulawesiOutline, ...sulawesiFeatures],
    })
  );

  // 3. Marine polygons & Gulfs around Sulawesi (Gulf of Tomini, Gulf of Boni/Bone, Gulf of Tolo, Makassar Strait, Banda Sea)
  const marinePolys = JSON.parse(
    readFileSync(join(rawVec, "ne_10m_geography_marine_polys.geojson"), "utf8")
  );
  const sulawesiMarine = marinePolys.features
    .filter((f) => f.geometry && bboxIntersects(f.geometry, [115.0, -9.0, 128.0, 5.0]))
    .map((f) => ({
      type: "Feature",
      properties: {
        name: f.properties.name || f.properties.NAME,
        label_id:
          /tomini/i.test(f.properties.name || "")
            ? "TELUK TOMINI"
            : /boni|bone/i.test(f.properties.name || "")
              ? "TELUK BONE"
              : /tolo/i.test(f.properties.name || "")
                ? "TELUK TOLO"
                : (f.properties.name || "").toUpperCase(),
        featurecla: f.properties.featurecla,
      },
      geometry: {
        type: f.geometry.type,
        coordinates: roundCoords(f.geometry.coordinates),
      },
    }));
  writeFileSync(
    join(VECTOR_OUT, "sulawesi_marine.geojson"),
    JSON.stringify({ type: "FeatureCollection", features: sulawesiMarine })
  );

  // 4. Tectonic Plate Boundaries (PB2002) & Active Faults (GEM) in Southeast Asia / Sulawesi
  const pb2002 = JSON.parse(readFileSync(join(rawVec, "PB2002_boundaries.json"), "utf8"));
  const regionalPlates = pb2002.features
    .filter((f) => f.geometry && bboxIntersects(f.geometry, [90.0, -18.0, 145.0, 22.0]))
    .map((f) => ({
      type: "Feature",
      properties: {
        layer: "plate_boundary",
        name: f.properties.Name || `${f.properties.PlateA || ""}-${f.properties.PlateB || ""}`,
        type: f.properties.Type || "boundary",
      },
      geometry: {
        type: f.geometry.type,
        coordinates: roundCoords(f.geometry.coordinates),
      },
    }));

  const gemFaults = JSON.parse(
    readFileSync(join(rawVec, "gem_active_faults_harmonized.geojson"), "utf8")
  );
  const sulawesiFaults = gemFaults.features
    .filter((f) => f.geometry && bboxIntersects(f.geometry, [117.5, -7.0, 126.5, 3.0]))
    .map((f) => ({
      type: "Feature",
      properties: {
        layer: "active_fault",
        name: f.properties.name || "Active Fault",
        slip_type: f.properties.slip_type || "unknown",
        is_palu_koro: /palu|koro/i.test(f.properties.name || ""),
      },
      geometry: {
        type: f.geometry.type,
        coordinates: roundCoords(f.geometry.coordinates),
      },
    }));

  // Also add an explicit, smooth schematic curve for the Palu-Koro Fault trace and the "K" strokes
  // for clean draw-on callout animations at regional scale.
  const curatedTraces = [
    {
      type: "Feature",
      properties: {
        layer: "callout_trace",
        id: "sesar_palu_koro_trace",
        label: "SESAR PALU KORO",
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [119.45, 0.35],
          [119.72, -0.32],
          [119.86, -0.89],
          [120.04, -1.45],
          [120.38, -2.08],
          [120.85, -2.55],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        layer: "callout_trace",
        id: "sulawesi_k_spine",
        label: "K_SPINE",
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [124.95, 1.55],
          [123.05, 0.72],
          [120.45, 0.55],
          [119.85, -0.85],
          [119.35, -3.25],
          [119.85, -5.45],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        layer: "callout_trace",
        id: "sulawesi_k_upper_arm",
        label: "K_UPPER_ARM",
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [120.15, -1.35],
          [121.45, -1.25],
          [123.15, -0.82],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        layer: "callout_trace",
        id: "sulawesi_k_lower_arm",
        label: "K_LOWER_ARM",
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [120.25, -1.75],
          [121.55, -3.15],
          [122.45, -4.35],
        ],
      },
    },
  ];

  writeFileSync(
    join(VECTOR_OUT, "sulawesi_tectonics.geojson"),
    JSON.stringify({
      type: "FeatureCollection",
      features: [...curatedTraces, ...sulawesiFaults, ...regionalPlates],
    })
  );

  console.log(
    `[vectors] Built 4 curated GeoJSON files in assets/geo/vector/: ` +
      `countries(${countriesFeatures.length}), sulawesi_regions(${sulawesiOutline.length + sulawesiFeatures.length}), ` +
      `sulawesi_marine(${sulawesiMarine.length}), sulawesi_tectonics(${curatedTraces.length + sulawesiFaults.length + regionalPlates.length})`
  );
}

async function main() {
  mkdirSync(TILES_OUT, { recursive: true });
  const s2Tiles = listTilesRecursive(join(RAW_DIR, "tiles_s2_2016"));
  console.log(`[tiles] Grading ${s2Tiles.length} tiles into assets/geo/tiles/ ...`);

  const concurrency = 16;
  let idx = 0;
  let done = 0;
  const t0 = Date.now();

  async function worker() {
    while (idx < s2Tiles.length) {
      const item = s2Tiles[idx++];
      const outPath = join(TILES_OUT, String(item.z), String(item.x), `${item.y}.jpg`);
      // At low zoom levels (z0-z4), blend 35% NASA Blue Marble bathymetry/shaded relief with Sentinel-2 cloudless
      const bmngPath =
        item.z <= 4
          ? join(RAW_DIR, "tiles_bmng", String(item.z), String(item.x), `${item.y}.jpg`)
          : null;
      const blendWeight = item.z <= 2 ? 0.45 : item.z <= 4 ? 0.25 : 0.0;
      await gradeTile(item.path, outPath, bmngPath, blendWeight);
      done++;
      if (done % 400 === 0 || done === s2Tiles.length) {
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        console.log(`  [tiles] ${done}/${s2Tiles.length} graded (${elapsed}s)`);
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  buildVectorDatasets();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
