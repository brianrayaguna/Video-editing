#!/usr/bin/env node
/**
 * Render the 6 Geoverum cartographic specimen stills (1080x1920 vertical) from the
 * local offline tile server (`serve_tiles.mjs`) using local MapLibre GL (`5.24.0`).
 *
 * Enforces all rules in `DESIGN.md` (`taste-skill`, `stageshow`, `emil-design-eng`):
 * - Unboxed broadcast bug watermark (`GEOVERUM` with geometric meridian mark, no pill, no glowing dot)
 * - Unified exterior island coastline (`island_outline` with zero internal administrative seams)
 * - Terrain-preserving multiply/screen landmass tinting (never opaque pastel mud, never violet)
 * - Single visual signal per specimen still ("Say it once")
 * - Zero label/coastline collision (`[collide]`) and clean leader/pointer callout geometry
 */

import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { startTileServer } from "./serve_tiles.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const puppeteer = require("puppeteer-core");
const sharp = require("sharp");

function resolveChrome() {
  if (process.env.CHROME && existsSync(process.env.CHROME)) return process.env.CHROME;
  const exe = process.platform === "win32" ? "chrome-headless-shell.exe" : "chrome-headless-shell";
  const base = join(homedir(), ".cache", "puppeteer", "chrome-headless-shell");
  if (existsSync(base)) {
    for (const v of readdirSync(base).sort().reverse()) {
      try {
        for (const inner of readdirSync(join(base, v))) {
          const bin = join(base, v, inner, exe);
          if (existsSync(bin)) return bin;
        }
      } catch {
        /* ignore */
      }
    }
  }
  for (const c of [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ]) {
    if (existsSync(c)) return c;
  }
  throw new Error("Chrome / chrome-headless-shell binary not found.");
}

const SPECIMENS = [
  {
    id: "01_globe_horizon",
    title: "Orbital Globe Horizon (z1.85)",
    projection: "globe",
    center: [118.0, 2.0],
    zoom: 1.85,
    pitch: 0,
    bearing: 0,
    mode: "clean_globe",
    caption: "",
  },
  {
    id: "02_archipelago_context",
    title: "Maritime Southeast Asia Context (z4.15)",
    projection: "globe",
    center: [118.5, -2.2],
    zoom: 4.15,
    pitch: 0,
    bearing: 0,
    mode: "clean_archipelago",
    caption: "Kalau lihat peta, Sulawesi",
  },
  {
    id: "03_sulawesi_silhouette_k",
    title: "Sulawesi Unified Silhouette & K-Stroke (z5.95)",
    projection: "mercator",
    center: [121.35, -1.75],
    zoom: 5.95,
    pitch: 0,
    bearing: 0,
    mode: "sulawesi_k_shape",
    caption: "tampak seperti huruf K yang patah",
  },
  {
    id: "04_teluk_tomini_basin",
    title: "Gulf of Tomini 3D Basin Close-Up (z7.65 · pitch 36°)",
    projection: "mercator",
    center: [120.88, -0.25],
    zoom: 7.65,
    pitch: 36,
    bearing: -8,
    mode: "teluk_tomini_closeup",
    caption: "masuk membentuk Teluk Tomini,",
  },
  {
    id: "05_palu_koro_fault_callout",
    title: "Palu-Koro Active Fault Trace & Callout (z6.05)",
    projection: "mercator",
    center: [121.35, -1.68],
    zoom: 6.05,
    pitch: 14,
    bearing: -4,
    mode: "palu_koro_fault",
    caption: "Sesar besar seperti Palu-Koro ikut mengacak bentuknya,",
  },
  {
    id: "06_geopolitical_distance_corridor",
    title: "Geopolitical Corridor & Distance Metric (z3.18)",
    projection: "mercator",
    center: [57.5, 28.5],
    zoom: 3.18,
    pitch: 6,
    bearing: 0,
    mode: "distance_corridor",
    caption: "terpisah lebih dari 4.000 km,",
  },
];

function buildHtml(baseUrl) {
  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stars = Array.from({ length: 220 }, () => {
    const x = (rnd() * 1080).toFixed(0);
    const y = (rnd() * 1920).toFixed(0);
    const r = (rnd() * 1.3 + 0.35).toFixed(2);
    const a = (rnd() * 0.55 + 0.18).toFixed(2);
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="#F4F1EA" opacity="${a}"/>`;
  }).join("");

  return `<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <link href="${baseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${baseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('${baseUrl}/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    @font-face {
      font-family: 'Archivo Black';
      src: url('${baseUrl}/fonts/ArchivoBlack-Regular.ttf') format('truetype');
      font-weight: 900;
    }
    @font-face {
      font-family: 'Unbounded';
      src: url('${baseUrl}/fonts/Unbounded-Variable.ttf') format('truetype');
      font-weight: 400 900;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: radial-gradient(ellipse at 50% 46%, #061D28 0%, #03161F 56%, #01090E 100%);
      font-family: 'Space Grotesk', sans-serif;
      font-variant-numeric: tabular-nums;
      -webkit-font-smoothing: antialiased;
    }
    #stars { position: absolute; inset: 0; z-index: 1; }
    #map { position: absolute; inset: 0; width: 1080px; height: 1920px; z-index: 2; }
    #svg-overlay {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      z-index: 3;
      pointer-events: none;
    }
    /* Clean unboxed broadcast watermark — zero pill, zero border, zero glowing status dot */
    #watermark {
      position: absolute;
      top: 72px;
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 14px;
      z-index: 4;
      opacity: 0.86;
      filter: drop-shadow(0 2px 10px rgba(0, 0, 0, 0.68));
    }
    .wm-wordmark {
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      font-size: 32px;
      letter-spacing: 0.12em;
      color: #F4F1EA;
      line-height: 1;
    }
    /* Narrative caption rail at 76% height (y = 1460px) — no border, calm dark surface */
    #caption-host {
      position: absolute;
      top: 1445px;
      left: 84px;
      right: 84px;
      display: flex;
      justify-content: center;
      z-index: 4;
    }
    #caption-chip {
      background: rgba(3, 18, 26, 0.78);
      color: #F4F1EA;
      padding: 11px 24px;
      border-radius: 7px;
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 500;
      font-size: 31px;
      line-height: 1.3;
      letter-spacing: -0.01em;
      text-align: center;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.38);
      display: none;
    }
    #credit {
      position: absolute;
      bottom: 22px;
      left: 64px;
      right: 64px;
      text-align: center;
      font-size: 13px;
      font-weight: 400;
      color: rgba(244, 241, 234, 0.40);
      z-index: 4;
      letter-spacing: 0.01em;
    }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <svg id="stars" width="1080" height="1920">${stars}</svg>
  <div id="map"></div>
  <svg id="svg-overlay" viewBox="0 0 1080 1920"></svg>

  <div id="watermark">
    <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
      <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.2" />
      <ellipse cx="17" cy="17" rx="6" ry="13" stroke="#F4F1EA" stroke-width="1.6" />
      <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.6" />
    </svg>
    <span class="wm-wordmark">GEOVERUM</span>
  </div>

  <div id="caption-host">
    <div id="caption-chip"></div>
  </div>

  <div id="credit" data-layout-ignore="true">Imagery: NASA Blue Marble, EOX Sentinel-2 cloudless 2016 (Copernicus) · Vectors: Natural Earth, PB2002, GEM</div>

  <script>
    const BASE_URL = ${JSON.stringify(baseUrl)};
    let map = null;
    let sulawesiRegions = null;
    let sulawesiMarine = null;
    let sulawesiTectonics = null;
    let countriesCurated = null;

    window.__init = async function() {
      const [regResp, marResp, tecResp, cntResp] = await Promise.all([
        fetch(BASE_URL + "/vector/sulawesi_regions.geojson"),
        fetch(BASE_URL + "/vector/sulawesi_marine.geojson"),
        fetch(BASE_URL + "/vector/sulawesi_tectonics.geojson"),
        fetch(BASE_URL + "/vector/countries_curated.geojson"),
      ]);
      sulawesiRegions = await regResp.json();
      sulawesiMarine = await marResp.json();
      sulawesiTectonics = await tecResp.json();
      countriesCurated = await cntResp.json();

      map = new maplibregl.Map({
        container: "map",
        style: {
          version: 8,
          projection: { type: "globe" },
          sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 4.5, 0.85, 6.0, 0] },
          sources: {
            sat: {
              type: "raster",
              tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"],
              tileSize: 256,
              maxzoom: 11
            }
          },
          layers: [
            { id: "sat-layer", type: "raster", source: "sat" }
          ]
        },
        center: [118.0, 2.0],
        zoom: 1.85,
        pitch: 0,
        bearing: 0,
        interactive: false,
        attributionControl: false,
        fadeDuration: 0,
        preserveDrawingBuffer: true,
        canvasContextAttributes: { alpha: true, preserveDrawingBuffer: true }
      });

      await new Promise((res) => map.on("load", res));
    };

    function projectRing(ring) {
      return ring.map((c, i) => {
        const p = map.project(c);
        return (i === 0 ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1);
      }).join(" ") + "Z";
    }

    function projectLine(coords) {
      return coords.map((c, i) => {
        const p = map.project(c);
        return (i === 0 ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1);
      }).join(" ");
    }

    function geomToPath(geom) {
      if (geom.type === "Polygon") return geom.coordinates.map(projectRing).join(" ");
      if (geom.type === "MultiPolygon") return geom.coordinates.map((poly) => poly.map(projectRing).join(" ")).join(" ");
      if (geom.type === "LineString") return projectLine(geom.coordinates);
      if (geom.type === "MultiLineString") return geom.coordinates.map(projectLine).join(" ");
      return "";
    }

    function buildSmoothCatmullRom(pts) {
      if (pts.length < 2) return "";
      let d = \`M \${pts[0].x.toFixed(1)} \${pts[0].y.toFixed(1)}\`;
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[Math.max(0, i - 1)];
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const p3 = pts[Math.min(pts.length - 1, i + 2)];
        const cp1x = p1.x + (p2.x - p0.x) / 6;
        const cp1y = p1.y + (p2.y - p0.y) / 6;
        const cp2x = p2.x - (p3.x - p1.x) / 6;
        const cp2y = p2.y - (p3.y - p1.y) / 6;
        d += \` C \${cp1x.toFixed(1)} \${cp1y.toFixed(1)}, \${cp2x.toFixed(1)} \${cp2y.toFixed(1)}, \${p2.x.toFixed(1)} \${p2.y.toFixed(1)}\`;
      }
      return d;
    }

    function filterMainlandCountry(feat, minLon, maxLon, minLat, maxLat) {
      if (feat.geometry.type !== "MultiPolygon") return feat.geometry;
      const kept = feat.geometry.coordinates.filter((poly) => {
        const ring = poly[0];
        let cx = 0, cy = 0;
        for (const [x, y] of ring) { cx += x; cy += y; }
        cx /= ring.length; cy /= ring.length;
        return cx >= minLon && cx <= maxLon && cy >= minLat && cy <= maxLat;
      });
      return { type: "MultiPolygon", coordinates: kept };
    }

    window.__renderSpecimen = async function(shot) {
      map.setProjection({ type: shot.projection });
      map.jumpTo({
        center: shot.center,
        zoom: shot.zoom,
        pitch: shot.pitch || 0,
        bearing: shot.bearing || 0
      });

      await new Promise((res) => {
        const t0 = performance.now();
        function check() {
          if (map.loaded() && map.areTilesLoaded()) {
            map.triggerRepaint();
            requestAnimationFrame(() => requestAnimationFrame(res));
            return;
          }
          if (performance.now() - t0 > 8000) {
            res();
            return;
          }
          setTimeout(check, 40);
        }
        check();
      });

      const capEl = document.getElementById("caption-chip");
      if (shot.caption) {
        capEl.textContent = shot.caption;
        capEl.style.display = "block";
      } else {
        capEl.style.display = "none";
      }

      const svg = document.getElementById("svg-overlay");
      svg.innerHTML = "";

      const islandFeat = sulawesiRegions.features.find((f) => f.properties.feature_type === "island_outline");
      const mainlandFeat = sulawesiRegions.features.find((f) => f.properties.feature_type === "mainland_exterior");
      const islandPathD = islandFeat ? geomToPath(islandFeat.geometry) : "";
      const mainlandPathD = mainlandFeat ? geomToPath(mainlandFeat.geometry) : islandPathD;

      if (shot.mode === "sulawesi_k_shape") {
        // Single signal: unified crimson-terracotta island highlight (preserving terrain) + smooth K strokes
        const kSpine = [
          [124.85, 1.45],
          [122.80, 0.65],
          [120.42, 0.55],
          [119.88, -0.90],
          [119.45, -3.10],
          [119.85, -5.35]
        ].map((c) => map.project(c));
        const kUpper = [
          [120.12, -1.32],
          [121.55, -1.22],
          [123.15, -0.82]
        ].map((c) => map.project(c));
        const kLower = [
          [120.22, -1.65],
          [121.65, -3.20],
          [122.45, -4.40]
        ].map((c) => map.project(c));

        const dSpine = buildSmoothCatmullRom(kSpine);
        const dUpper = buildSmoothCatmullRom(kUpper);
        const dLower = buildSmoothCatmullRom(kLower);

        svg.innerHTML = \`
          <defs>
            <filter id="coast-glow" x="-15%" y="-15%" width="130%" height="130%">
              <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#F4F1EA" flood-opacity="0.55" />
            </filter>
            <filter id="k-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="2" stdDeviation="5" flood-color="#000000" flood-opacity="0.65" />
            </filter>
          </defs>
          <!-- Terrain-preserving deep crimson tint over unified exterior coastline (zero internal seams) -->
          <path d="\${islandPathD}" fill="rgba(128, 14, 22, 0.62)" style="mix-blend-mode: multiply;" />
          <path d="\${islandPathD}" fill="rgba(168, 24, 32, 0.28)" />
          <path d="\${islandPathD}" fill="none" stroke="#F4F1EA" stroke-width="2.0" stroke-linejoin="round" filter="url(#coast-glow)" />

          <!-- Dual-stroke "K" trace matching Reference A f100 -->
          <g filter="url(#k-glow)">
            <path d="\${dSpine}" fill="none" stroke="#F4F1EA" stroke-width="14" stroke-linecap="round" />
            <path d="\${dUpper}" fill="none" stroke="#F4F1EA" stroke-width="14" stroke-linecap="round" />
            <path d="\${dLower}" fill="none" stroke="#F4F1EA" stroke-width="14" stroke-linecap="round" />
            <path d="\${dSpine}" fill="none" stroke="#F5C542" stroke-width="7" stroke-linecap="round" />
            <path d="\${dUpper}" fill="none" stroke="#F5C542" stroke-width="7" stroke-linecap="round" />
            <path d="\${dLower}" fill="none" stroke="#F5C542" stroke-width="7" stroke-linecap="round" />
          </g>
        \`;
      } else if (shot.mode === "teluk_tomini_closeup") {
        // Close-up of Gulf of Tomini: mainland coastal rim + curved hydrographic textPath in open western-central basin
        const arcPts = [
          [120.20, -0.36],
          [120.58, -0.22],
          [120.98, -0.20],
          [121.34, -0.28]
        ].map((c) => map.project(c));
        const arcD = buildSmoothCatmullRom(arcPts);

        svg.innerHTML = \`
          <defs>
            <filter id="bay-rim" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="0" stdDeviation="9" flood-color="#7CE0F9" flood-opacity="0.75" />
            </filter>
            <filter id="text-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="3" stdDeviation="6" flood-color="#010A0F" flood-opacity="0.90" />
            </filter>
            <path id="tomini-arc" d="\${arcD}" />
          </defs>
          <path d="\${mainlandPathD}" fill="none" stroke="#E6F7FF" stroke-width="2.6" stroke-linejoin="round" filter="url(#bay-rim)" />
          <text font-family="Unbounded" font-weight="800" font-size="30" fill="#7CE0F9" letter-spacing="3.5" filter="url(#text-shadow)">
            <textPath href="#tomini-arc" startOffset="50%" text-anchor="middle">TELUK TOMINI</textPath>
          </text>
        \`;
      } else if (shot.mode === "palu_koro_fault") {
        // Single signal: unified crimson Sulawesi + tapered golden fault line + clean pointer callout
        const faultCoords = [
          [119.50, 0.28],
          [119.74, -0.35],
          [119.87, -0.90],
          [120.08, -1.48],
          [120.42, -2.08],
          [120.88, -2.52]
        ].map((c) => map.project(c));

        // Build a tapered crescent polygon for the fault trace (like Reference A f1340)
        const leftSide = [];
        const rightSide = [];
        for (let i = 0; i < faultCoords.length; i++) {
          const t = i / (faultCoords.length - 1);
          const halfWidth = Math.sin(Math.PI * t) * 5.2 + 0.8;
          const pPrev = faultCoords[Math.max(0, i - 1)];
          const pNext = faultCoords[Math.min(faultCoords.length - 1, i + 1)];
          const dx = pNext.x - pPrev.x;
          const dy = pNext.y - pPrev.y;
          const len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len;
          const ny = dx / len;
          leftSide.push({ x: faultCoords[i].x + nx * halfWidth, y: faultCoords[i].y + ny * halfWidth });
          rightSide.unshift({ x: faultCoords[i].x - nx * halfWidth, y: faultCoords[i].y - ny * halfWidth });
        }
        const taperedRing = [...leftSide, ...rightSide];
        const taperedD = taperedRing.map((p, i) => (i === 0 ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1)).join(" ") + "Z";

        // Anchor point on the fault trace in the neck of Palu-Koro
        const anchor = map.project([119.90, -0.98]);
        const boxX = Math.round(anchor.x + 26);
        const boxY = Math.round(anchor.y - 20);
        const boxW = 248;
        const boxH = 40;

        svg.innerHTML = \`
          <defs>
            <filter id="coast-subtle" x="-15%" y="-15%" width="130%" height="130%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#F4F1EA" flood-opacity="0.40" />
            </filter>
            <filter id="callout-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000000" flood-opacity="0.55" />
            </filter>
          </defs>
          <path d="\${islandPathD}" fill="rgba(124, 14, 20, 0.64)" style="mix-blend-mode: multiply;" />
          <path d="\${islandPathD}" fill="rgba(160, 22, 30, 0.25)" />
          <path d="\${islandPathD}" fill="none" stroke="#F4F1EA" stroke-width="1.6" stroke-linejoin="round" filter="url(#coast-subtle)" />

          <!-- Tapered golden fault trace -->
          <path d="\${taperedD}" fill="#F5C542" filter="url(#callout-shadow)" />

          <!-- Clean callout badge with sharp triangular pointer aiming at the fault trace (6px clear gap) -->
          <g filter="url(#callout-shadow)">
            <path d="M \${anchor.x + 7} \${anchor.y} L \${boxX} \${boxY + 12} L \${boxX} \${boxY + 28} Z" fill="#F4F1EA" />
            <rect x="\${boxX}" y="\${boxY}" width="\${boxW}" height="\${boxH}" rx="4" fill="#F4F1EA" />
            <text x="\${boxX + boxW / 2}" y="\${boxY + 27}" text-anchor="middle"
                  font-family="Archivo Black" font-size="19" letter-spacing="0.02em" fill="#03161F">SESAR PALU-KORO</text>
          </g>
        \`;
      } else if (shot.mode === "distance_corridor") {
        // Turkey & India corridor (like Ref B f90, without violet/magenta slop)
        const turkeyFeat = countriesCurated.features.find((f) => f.properties.name === "Turkey");
        const indiaFeat = countriesCurated.features.find((f) => f.properties.name === "India");
        const turkeyD = turkeyFeat ? geomToPath(filterMainlandCountry(turkeyFeat, 25, 46, 35, 43)) : "";
        const indiaD = indiaFeat ? geomToPath(filterMainlandCountry(indiaFeat, 67, 98, 7, 36)) : "";

        const ptTurkey = map.project([35.2, 39.0]);
        const ptIndia = map.project([78.5, 22.8]);
        const dx = ptIndia.x - ptTurkey.x;
        const dy = ptIndia.y - ptTurkey.y;
        const angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
        const midX = (ptTurkey.x + ptIndia.x) / 2 - 24;
        const midY = (ptTurkey.y + ptIndia.y) / 2 + 48;

        svg.innerHTML = \`
          <defs>
            <filter id="card-drop" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.72" />
            </filter>
          </defs>
          <!-- Subtle dark scrim over bright desert terrain so distance metric holds > 10:1 contrast -->
          <rect x="0" y="0" width="1080" height="1920" fill="rgba(3, 18, 26, 0.24)" />

          <!-- Country silhouettes preserving satellite relief underneath -->
          <path d="\${turkeyD}" fill="rgba(46, 107, 230, 0.64)" stroke="#F4F1EA" stroke-width="1.8" stroke-linejoin="round" />
          <path d="\${indiaD}" fill="rgba(194, 65, 45, 0.66)" stroke="#F4F1EA" stroke-width="1.8" stroke-linejoin="round" />

          <!-- Dashed geodesic distance line -->
          <line x1="\${ptTurkey.x.toFixed(1)}" y1="\${ptTurkey.y.toFixed(1)}"
                x2="\${ptIndia.x.toFixed(1)}" y2="\${ptIndia.y.toFixed(1)}"
                stroke="#D9383A" stroke-width="7" stroke-dasharray="18 12" stroke-linecap="round" filter="url(#card-drop)" />

          <!-- Tabular distance metric with dark knock-out halo for high contrast over desert terrain -->
          <g transform="translate(\${midX.toFixed(1)}, \${midY.toFixed(1)}) rotate(\${angleDeg.toFixed(2)})" filter="url(#card-drop)">
            <text x="0" y="0" text-anchor="middle" font-family="Archivo Black" font-size="44"
                  letter-spacing="0.02em" fill="#F5C542"
                  stroke="#03161F" stroke-width="9" stroke-linejoin="round" style="paint-order: stroke fill;">+4.000 KM</text>
          </g>

          <!-- Country callout chips placed above centroids with pointer tips -->
          <g transform="translate(\${(ptTurkey.x - 6).toFixed(1)}, \${(ptTurkey.y - 36).toFixed(1)})" filter="url(#card-drop)">
            <rect x="-56" y="-34" width="112" height="34" rx="4" fill="#F5C542" />
            <path d="M -8 0 L 8 0 L 0 9 Z" fill="#F5C542" />
            <text x="0" y="-10" text-anchor="middle" font-family="Archivo Black" font-size="19" fill="#03161F">TURKI</text>
          </g>

          <g transform="translate(\${(ptIndia.x + 8).toFixed(1)}, \${(ptIndia.y - 24).toFixed(1)})" filter="url(#card-drop)">
            <rect x="-56" y="-34" width="112" height="34" rx="4" fill="#F5C542" />
            <path d="M -8 0 L 8 0 L 0 9 Z" fill="#F5C542" />
            <text x="0" y="-10" text-anchor="middle" font-family="Archivo Black" font-size="19" fill="#03161F">INDIA</text>
          </g>
        \`;
      }
    };
  </script>
</body>
</html>`;
}

async function main() {
  const outDir = process.argv[2] || join(REPO_ROOT, "renders/basemap_specimens");
  mkdirSync(outDir, { recursive: true });

  const port = 8766;
  const server = await startTileServer(port, "127.0.0.1");
  const baseUrl = `http://127.0.0.1:${port}`;
  console.log(`[specimens] Local offline tile server started at ${baseUrl}`);

  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: true,
    args: [
      "--no-sandbox",
      "--hide-scrollbars",
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--enable-webgl",
      "--window-size=1080,1920",
    ],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
    await page.setContent(buildHtml(baseUrl), { waitUntil: "load" });
    await page.evaluate(() => window.__init());

    const renderedPaths = [];
    for (const shot of SPECIMENS) {
      await page.evaluate((s) => window.__renderSpecimen(s), shot);
      const outPath = join(outDir, `${shot.id}.png`);
      await page.screenshot({
        path: outPath,
        clip: { x: 0, y: 0, width: 1080, height: 1920 },
      });
      renderedPaths.push({ shot, outPath });
      console.log(`  [ok] Rendered ${shot.id}.png (${shot.title})`);
    }

    const cellW = 540;
    const cellH = 960;
    const composites = [];
    for (let i = 0; i < renderedPaths.length; i++) {
      const col = i % 3;
      const row = Math.floor(i / 3);
      const resized = await sharp(renderedPaths[i].outPath).resize(cellW, cellH).toBuffer();
      composites.push({ input: resized, left: col * cellW, top: row * cellH });
    }
    const gridPath = join(outDir, "geoverum_specimens_grid.jpg");
    await sharp({
      create: {
        width: cellW * 3,
        height: cellH * 2,
        channels: 3,
        background: { r: 3, g: 22, b: 31 },
      },
    })
      .composite(composites)
      .jpeg({ quality: 92 })
      .toFile(gridPath);
    console.log(`[specimens] Contact sheet written to ${gridPath}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
