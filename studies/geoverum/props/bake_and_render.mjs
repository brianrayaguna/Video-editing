#!/usr/bin/env node
/**
 * Bake MapLibre satellite plates and projected coordinates for Geoverum Props
 * (`props`), verifying circular SVG flag pins (`lipis/flag-icons`), single-family Google Material
 * Symbols markers, and tectonic convergence flow arrows with `stroke-dashoffset` draw-on.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { startTileServer } from "../../../tools/geo-assets/serve_tiles.mjs";
import {
  buildBroadcastLayerHtml,
  buildSmoothCatmullRomPath,
  encodeDeliverableAndSheet,
  puppeteer,
  renderProjectFrames,
  REPO_ROOT,
  resolveChrome,
  startStudyAssetServer,
  validateStudyProject,
} from "../../../tools/geo-assets/study_runner.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const COMP_DIR = join(STUDY_DIR, "compositions");
const RENDERS_DIR = join(STUDY_DIR, "renders");

function readMaterialIconPath(iconName) {
  const raw = readFileSync(join(REPO_ROOT, `assets/geo/icons/${iconName}.svg`), "utf8");
  const match = raw.match(/d="([^"]+)"/);
  return match ? match[1] : "";
}

function polylineLength(pts) {
  let len = 0;
  for (let i = 1; i < pts.length; i++) {
    len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  }
  return len;
}

async function bakePlatesAndCoords(browser, tileBaseUrl) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${tileBaseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${tileBaseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    * { margin: 0; padding: 0; }
    html, body, #map { width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    const BASE_URL = ${JSON.stringify(tileBaseUrl)};
    let countries = null;
    let sulawesi = null;
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: "mercator" },
        sources: { sat: { type: "raster", tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"], tileSize: 256, maxzoom: 11 } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#03161F" } }, { id: "sat", type: "raster", source: "sat" }]
      },
      center: [57.5, 29.0], zoom: 3.3, interactive: false, attributionControl: false, fadeDuration: 0, preserveDrawingBuffer: true
    });
    window.__init = async function() {
      const [cR, sR] = await Promise.all([
        fetch(BASE_URL + "/vector/countries_curated.geojson"),
        fetch(BASE_URL + "/vector/sulawesi_regions.geojson")
      ]);
      countries = await cR.json();
      sulawesi = await sR.json();
      await new Promise((res) => { if (map.loaded()) res(); else map.on("load", res); });
    };
    function projectRing(ring) {
      return ring.map((c, i) => {
        const p = map.project(c);
        return (i === 0 ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1);
      }).join(" ") + "Z";
    }
    function geomToPath(geom) {
      if (geom.type === "Polygon") return geom.coordinates.map(projectRing).join(" ");
      if (geom.type === "MultiPolygon") return geom.coordinates.map((poly) => poly.map(projectRing).join(" ")).join(" ");
      return "";
    }
    function filterMainland(feat, minLon, maxLon, minLat, maxLat) {
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
    window.__extract = async function(view) {
      map.jumpTo(view);
      await new Promise((res) => {
        const t0 = performance.now();
        (function poll() {
          if (map.loaded() && map.areTilesLoaded()) {
            map.triggerRepaint();
            requestAnimationFrame(() => requestAnimationFrame(res));
            return;
          }
          if (performance.now() - t0 > 9000) { res(); return; }
          setTimeout(poll, 35);
        })();
      });
      if (view.id === "flags") {
        const trF = countries.features.find((f) => f.properties.name === "Turkey");
        const pkF = countries.features.find((f) => f.properties.name === "Pakistan");
        const inF = countries.features.find((f) => f.properties.name === "India");
        return {
          turkeyD: geomToPath(filterMainland(trF, 25, 46, 35, 43)),
          pakistanD: geomToPath(filterMainland(pkF, 60, 78, 23, 37)),
          indiaD: geomToPath(filterMainland(inF, 67, 98, 7, 36)),
          pins: [
            { id: "tr", iso: "tr", label: "TURKI", pt: map.project([35.2, 39.2]) },
            { id: "pk", iso: "pk", label: "PAKISTAN", pt: map.project([69.2, 29.8]) },
            { id: "in", iso: "in", label: "INDIA", pt: map.project([79.2, 21.5]) },
          ]
        };
      }
      if (view.id === "icons") {
        const islandF = sulawesi.features.find((f) => f.properties.feature_type === "island_outline");
        return {
          islandD: geomToPath(islandF.geometry),
          tsunamiPt: map.project([119.72, -0.78]),
          warningPt: map.project([120.10, -1.62]),
          explorePt: map.project([121.35, -0.32]),
        };
      }
      // flow
      const islandF = sulawesi.features.find((f) => f.properties.feature_type === "island_outline");
      return {
        islandD: geomToPath(islandF.geometry),
        hubPt: map.project([120.85, -1.55]),
        vecWest: [[117.0, -1.35], [118.2, -1.45], [119.35, -1.52]].map((c) => map.project(c)),
        vecNorthEast: [[125.9, 2.35], [124.75, 1.55], [123.65, 0.95]].map((c) => map.project(c)),
        vecSouthEast: [[124.4, -6.15], [123.45, -4.95], [122.45, -3.75]].map((c) => map.project(c)),
      };
    };
  </script>
</body>
</html>`;

  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => window.__init());

  const views = [
    { id: "flags", center: [57.5, 29.0], zoom: 3.30, pitch: 6, bearing: 0, file: "plate-props-eurasia.jpg" },
    { id: "icons", center: [121.35, -1.75], zoom: 5.95, pitch: 8, bearing: 0, file: "plate-props-sulawesi.jpg" },
    { id: "flow", center: [121.25, -1.65], zoom: 5.55, pitch: 6, bearing: 0, file: "plate-props-flow.jpg" },
  ];

  const coords = {};
  for (const v of views) {
    coords[v.id] = await page.evaluate((vw) => window.__extract(vw), v);
    await page.screenshot({
      path: join(ASSETS_DIR, v.file),
      type: "jpeg",
      quality: 94,
      clip: { x: 0, y: 0, width: 1080, height: 1920 },
    });
    console.log(`  [props] Baked ${v.file}`);
  }
  await page.close();
  writeFileSync(join(ASSETS_DIR, "props-coords.json"), JSON.stringify(coords, null, 2));
  return coords;
}

function buildArrowHeadTransform(pts) {
  const a = pts[pts.length - 2];
  const b = pts[pts.length - 1];
  const deg = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
  return { x: b.x.toFixed(1), y: b.y.toFixed(1), deg: deg.toFixed(2) };
}

function writeHyperframesProject(coords) {
  const iconTsunami = readMaterialIconPath("tsunami");
  const iconWarning = readMaterialIconPath("warning");
  const iconExplore = readMaterialIconPath("explore");
  const iconLocation = readMaterialIconPath("location_on");

  // Beat 1: Circular flag pins using verified lipis/flag-icons SVGs (with explicit origin at stalk foot)
  const flagMarkersHtml = coords.flags.pins
    .map((pin) => {
      const px = Math.round(pin.pt.x);
      const py = Math.round(pin.pt.y);
      const flagRaw = readFileSync(join(REPO_ROOT, `assets/geo/flags/1x1/${pin.iso}.svg`), "utf8");
      const flagDataUri = `data:image/svg+xml;base64,${Buffer.from(flagRaw).toString("base64")}`;
      // Place tag neatly ABOVE the circular medallion so stalks never overlap text
      return `
        <div id="flag-pin-${pin.id}" class="flag-pin" style="left:${px}px; top:${py}px; transform-origin: center bottom;">
          <div class="pin-tag">${pin.label}</div>
          <div class="flag-disc">
            <img src="${flagDataUri}" alt="${pin.label}" />
          </div>
          <div class="pin-stalk"></div>
          <div class="pin-dot"></div>
        </div>`;
    })
    .join("\n");

  // Beat 2: Single-family Material Symbols Rounded badges inside solid opaque 48x48 circular housing
  const ic = coords.icons;
  const tpX = Math.round(ic.tsunamiPt.x);
  const tpY = Math.round(ic.tsunamiPt.y);
  const wpX = Math.round(ic.warningPt.x);
  const wpY = Math.round(ic.warningPt.y);
  const epX = Math.round(ic.explorePt.x);
  const epY = Math.round(ic.explorePt.y);

  // Place TSUNAMI PALU cleanly to left in Makassar Strait, SESAR AKTIF slightly southeast in open space
  // Wait: check clearance! Let's place TSUNAMI marker stalked directly into Makassar Strait open water left of coast (tpX - 68, tpY) and pointer stem aiming right to Palu Bay,
  // WARNING marker above SE central ridge with clean solid opaque disc, EXPLORE marker centered in wide open Gulf of Tomini!
  const markerSpecs = [
    { id: "mk-tsunami", x: tpX - 72, y: tpY - 8, targetX: tpX, targetY: tpY, bg: "#C2412D", ink: "#F4F1EA", path: iconTsunami, tag: "TSUNAMI PALU" },
    { id: "mk-warning", x: wpX + 108, y: wpY + 42, targetX: wpX, targetY: wpY, bg: "#03161F", ink: "#F5C542", path: iconWarning, tag: "SESAR AKTIF" },
    { id: "mk-explore", x: epX - 6, y: epY + 26, targetX: epX - 6, targetY: epY - 12, bg: "#03161F", ink: "#7CE0F9", path: iconExplore, tag: "CEKUNGAN TOMINI" },
  ];

  // Beat 3: Tectonic convergence paths + computed lengths + arrowheads
  const fl = coords.flow;
  const dWest = buildSmoothCatmullRomPath(fl.vecWest);
  const dNE = buildSmoothCatmullRomPath(fl.vecNorthEast);
  const dSE = buildSmoothCatmullRomPath(fl.vecSouthEast);
  const lWest = Math.ceil(polylineLength(fl.vecWest) * 1.12);
  const lNE = Math.ceil(polylineLength(fl.vecNorthEast) * 1.12);
  const lSE = Math.ceil(polylineLength(fl.vecSouthEast) * 1.12);
  const ahWest = buildArrowHeadTransform(fl.vecWest);
  const ahNE = buildArrowHeadTransform(fl.vecNorthEast);
  const ahSE = buildArrowHeadTransform(fl.vecSouthEast);

  const indexHtml = `<!DOCTYPE html>
<html
  lang="id"
  data-composition-variables='[
    {"id":"color-ground","type":"color","label":"Background","default":"#03161F"},
    {"id":"color-ink","type":"color","label":"Text","default":"#F4F1EA"},
    {"id":"color-accent","type":"color","label":"Accent","default":"#F5C542"}
  ]'
>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Geoverum Props — Props, Flags, Icons &amp; Flow Vectors</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    @font-face {
      font-family: 'Archivo Black';
      src: url('assets/fonts/ArchivoBlack-Regular.ttf') format('truetype');
      font-weight: 900;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: #03161F; }
    #root { position: relative; width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }
  </style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="8" data-width="1080" data-height="1920" data-fps="30">
    <div
      id="props-scene"
      data-composition-id="props-scene"
      data-composition-src="compositions/props-scene.html"
      data-start="0"
      data-duration="8"
      data-track-index="1"
      data-track-kind="graphics"
      data-width="1080"
      data-height="1920"
    ></div>
    <div
      id="broadcast-layer"
      data-composition-id="broadcast-layer"
      data-composition-src="compositions/broadcast-layer.html"
      data-start="0"
      data-duration="8"
      data-track-index="2"
      data-track-kind="graphics"
      data-width="1080"
      data-height="1920"
    ></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.to({}, { duration: 8 });
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
`;

  const sceneHtml = `<template>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    @font-face {
      font-family: 'Archivo Black';
      src: url('assets/fonts/ArchivoBlack-Regular.ttf') format('truetype');
      font-weight: 900;
    }
    #root {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: #03161F;
      font-family: 'Space Grotesk', sans-serif;
    }
    .beat-layer { position: absolute; inset: 0; width: 1080px; height: 1920px; overflow: hidden; opacity: 0; }
    .cam-rig { position: absolute; inset: 0; width: 1080px; height: 1920px; transform-origin: 540px 960px; will-change: transform; }
    .plate-img { position: absolute; inset: 0; width: 1080px; height: 1920px; object-fit: cover; display: block; }
    .vec-svg { position: absolute; inset: 0; width: 1080px; height: 1920px; pointer-events: none; }

    /* Flag pin structure: centered vertically upward from coordinate point */
    .flag-pin {
      position: absolute;
      width: 0;
      height: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-end;
      opacity: 0;
    }
    .pin-tag {
      background: #03161F;
      color: #F4F1EA;
      font-family: 'Archivo Black', sans-serif;
      font-size: 16px;
      letter-spacing: 0.04em;
      padding: 4px 10px 5px 10px;
      border-radius: 4px;
      white-space: nowrap;
      margin-bottom: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.60);
    }
    .flag-disc {
      width: 58px;
      height: 58px;
      border-radius: 50%;
      border: 3px solid #F4F1EA;
      overflow: hidden;
      background: #03161F;
      box-shadow: 0 6px 16px rgba(0,0,0,0.65);
      flex: none;
    }
    .flag-disc img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .pin-stalk { width: 2.5px; height: 22px; background: #F4F1EA; box-shadow: 0 2px 6px rgba(0,0,0,0.55); }
    .pin-dot { width: 10px; height: 10px; border-radius: 50%; background: #F5C542; border: 2px solid #03161F; transform: translateY(5px); }
  </style>
  <div id="root" data-composition-id="props-scene" data-width="1080" data-height="1920">
    <!-- BEAT 1 (0.00s - 2.67s): Circular Country Flag Pins -->
    <div id="beat-flags" class="beat-layer clip" data-start="0" data-duration="2.67" data-track-index="1" data-layout-allow-overflow="true">
      <div id="rig-flags" class="cam-rig">
        <img class="plate-img" src="assets/plate-props-eurasia.jpg" alt="Eurasia flag context" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <rect x="0" y="0" width="1080" height="1920" fill="rgba(3, 18, 26, 0.20)" />
          <path d="${coords.flags.turkeyD}" fill="rgba(46, 107, 230, 0.56)" stroke="#F4F1EA" stroke-width="1.6" stroke-linejoin="round" />
          <path d="${coords.flags.pakistanD}" fill="rgba(46, 134, 96, 0.58)" stroke="#F4F1EA" stroke-width="1.6" stroke-linejoin="round" />
          <path d="${coords.flags.indiaD}" fill="rgba(194, 65, 45, 0.58)" stroke="#F4F1EA" stroke-width="1.6" stroke-linejoin="round" />
        </svg>
        ${flagMarkersHtml}
      </div>
    </div>

    <!-- BEAT 2 (2.67s - 5.33s): Single-Family Material Symbols Rounded Pictograms -->
    <div id="beat-icons" class="beat-layer clip" data-start="2.67" data-duration="2.66" data-track-index="2" data-layout-allow-overflow="true">
      <div id="rig-icons" class="cam-rig">
        <img class="plate-img" src="assets/plate-props-sulawesi.jpg" alt="Sulawesi hazard sites" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <defs>
            <filter id="marker-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#000000" flood-opacity="0.65" />
            </filter>
          </defs>
          <path d="${ic.islandD}" fill="rgba(124, 14, 20, 0.52)" style="mix-blend-mode: multiply;" />
          <path d="${ic.islandD}" fill="none" stroke="#F4F1EA" stroke-width="1.8" stroke-linejoin="round" />

          ${markerSpecs
            .map((m) => {
              const tagW = m.tag.length * 10.6 + 22;
              return `
          <g id="${m.id}" filter="url(#marker-shadow)" style="opacity: 0;">
            <line x1="${m.x}" y1="${m.y}" x2="${m.targetX.toFixed(1)}" y2="${m.targetY.toFixed(1)}" stroke="#F4F1EA" stroke-width="2" />
            <circle cx="${m.targetX.toFixed(1)}" cy="${m.targetY.toFixed(1)}" r="5" fill="#F5C542" stroke="#03161F" stroke-width="2" />
            <circle cx="${m.x}" cy="${m.y}" r="25" fill="${m.bg}" stroke="#F4F1EA" stroke-width="2.4" />
            <g transform="translate(${m.x - 14}, ${m.y - 14}) scale(0.02916)">
              <path d="${m.path}" fill="${m.ink}" transform="translate(0, 960)" />
            </g>
            <rect x="${m.x - tagW / 2}" y="${m.y - 58}" width="${tagW.toFixed(0)}" height="26" rx="4" fill="#03161F" />
            <text x="${m.x}" y="${m.y - 40}" text-anchor="middle" font-family="Archivo Black" font-size="14" letter-spacing="0.03em" fill="#F4F1EA">${m.tag}</text>
          </g>`;
            })
            .join("\n")}
        </svg>
      </div>
    </div>

    <!-- BEAT 3 (5.33s - 8.00s): Tectonic Convergence Flow Arrows + Hub Marker -->
    <div id="beat-flow" class="beat-layer clip" data-start="5.33" data-duration="2.67" data-track-index="3" data-layout-allow-overflow="true">
      <div id="rig-flow" class="cam-rig">
        <img class="plate-img" src="assets/plate-props-flow.jpg" alt="Tectonic convergence basemap" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <defs>
            <filter id="flow-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.72" />
            </filter>
          </defs>
          <path d="${fl.islandD}" fill="rgba(128, 14, 22, 0.58)" style="mix-blend-mode: multiply;" />
          <path d="${fl.islandD}" fill="none" stroke="#F4F1EA" stroke-width="1.8" stroke-linejoin="round" />

          <!-- Dark halo understrokes for crisp sea/land contrast -->
          <g filter="url(#flow-shadow)">
            <path class="arr-west" d="${dWest}" fill="none" stroke="#03161F" stroke-width="11" stroke-linecap="round" stroke-dasharray="${lWest}" stroke-dashoffset="${lWest}" />
            <path class="arr-ne" d="${dNE}" fill="none" stroke="#03161F" stroke-width="11" stroke-linecap="round" stroke-dasharray="${lNE}" stroke-dashoffset="${lNE}" />
            <path class="arr-se" d="${dSE}" fill="none" stroke="#03161F" stroke-width="11" stroke-linecap="round" stroke-dasharray="${lSE}" stroke-dashoffset="${lSE}" />

            <path class="arr-west" d="${dWest}" fill="none" stroke="#F5C542" stroke-width="5.5" stroke-linecap="round" stroke-dasharray="${lWest}" stroke-dashoffset="${lWest}" />
            <path class="arr-ne" d="${dNE}" fill="none" stroke="#F5C542" stroke-width="5.5" stroke-linecap="round" stroke-dasharray="${lNE}" stroke-dashoffset="${lNE}" />
            <path class="arr-se" d="${dSE}" fill="none" stroke="#F5C542" stroke-width="5.5" stroke-linecap="round" stroke-dasharray="${lSE}" stroke-dashoffset="${lSE}" />
          </g>

          <!-- Geometric arrowheads synced to each route terminus -->
          <g id="head-west" transform="translate(${ahWest.x}, ${ahWest.y}) rotate(${ahWest.deg})" style="opacity: 0;">
            <path d="M -8 -10 L 14 0 L -8 10 Z" fill="#F5C542" stroke="#03161F" stroke-width="2.5" stroke-linejoin="round" />
          </g>
          <g id="head-ne" transform="translate(${ahNE.x}, ${ahNE.y}) rotate(${ahNE.deg})" style="opacity: 0;">
            <path d="M -8 -10 L 14 0 L -8 10 Z" fill="#F5C542" stroke="#03161F" stroke-width="2.5" stroke-linejoin="round" />
          </g>
          <g id="head-se" transform="translate(${ahSE.x}, ${ahSE.y}) rotate(${ahSE.deg})" style="opacity: 0;">
            <path d="M -8 -10 L 14 0 L -8 10 Z" fill="#F5C542" stroke="#03161F" stroke-width="2.5" stroke-linejoin="round" />
          </g>

          <!-- Central Convergence Hub Icon (Material Symbols location_on) -->
          <g id="flow-hub" filter="url(#flow-shadow)" style="opacity: 0;">
            <circle cx="${fl.hubPt.x.toFixed(1)}" cy="${fl.hubPt.y.toFixed(1)}" r="26" fill="#C2412D" stroke="#F4F1EA" stroke-width="2.6" />
            <g transform="translate(${(fl.hubPt.x - 15).toFixed(1)}, ${(fl.hubPt.y - 15).toFixed(1)}) scale(0.03125)">
              <path d="${iconLocation}" fill="#F4F1EA" transform="translate(0, 960)" />
            </g>
          </g>
        </svg>
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });

    // Initial states at t=0
    tl.set("#beat-flags", { opacity: 1 }, 0);
    tl.set("#beat-icons, #beat-flow", { opacity: 0 }, 0);
    tl.set(".flag-pin", { opacity: 0, scale: 0.92 }, 0);
    tl.set("#mk-tsunami", { opacity: 0, scale: 0.92, svgOrigin: "${tpX} ${tpY}" }, 0);
    tl.set("#mk-warning", { opacity: 0, scale: 0.92, svgOrigin: "${wpX} ${wpY}" }, 0);
    tl.set("#mk-explore", { opacity: 0, scale: 0.92, svgOrigin: "${(epX - 6).toFixed(0)} ${(epY - 12).toFixed(0)}" }, 0);
    tl.set("#head-west, #head-ne, #head-se", { opacity: 0, scale: 0.90, svgOrigin: "0 0" }, 0);
    tl.set("#flow-hub", { opacity: 0, scale: 0.92, svgOrigin: "${fl.hubPt.x.toFixed(1)} ${fl.hubPt.y.toFixed(1)}" }, 0);

    // BEAT 1 (0.00s - 2.67s): Eurasia circular flag medallions
    tl.fromTo("#rig-flags", { scale: 1.0, x: 0, y: 0 }, { scale: 1.05, x: -6, y: -4, duration: 2.67, ease: "none" }, 0.0);
    tl.to("#flag-pin-tr", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 0.20);
    tl.to("#flag-pin-pk", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 0.35);
    tl.to("#flag-pin-in", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 0.45);

    // BEAT 2 (2.67s - 5.33s): Single-family Material Symbols field icons
    tl.set("#beat-flags", { opacity: 0 }, 2.67);
    tl.set("#beat-icons", { opacity: 1 }, 2.67);
    tl.fromTo("#rig-icons", { scale: 1.0, x: 0, y: 0 }, { scale: 1.06, x: 0, y: -8, duration: 2.66, ease: "none" }, 2.67);
    tl.to("#mk-tsunami", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 2.87);
    tl.to("#mk-warning", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 3.00);
    tl.to("#mk-explore", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 3.09);

    // BEAT 3 (5.33s - 8.00s): Tectonic convergence vectors & hub arrival
    tl.set("#beat-icons", { opacity: 0 }, 5.33);
    tl.set("#beat-flow", { opacity: 1 }, 5.33);
    tl.fromTo("#rig-flow", { scale: 1.0, x: 0, y: 0 }, { scale: 1.05, x: 4, y: -6, duration: 2.67, ease: "none" }, 5.33);

    tl.to(".arr-west", { attr: { "stroke-dashoffset": 0 }, duration: 0.58, ease: "power2.inOut" }, 5.53);
    tl.to(".arr-ne", { attr: { "stroke-dashoffset": 0 }, duration: 0.58, ease: "power2.inOut" }, 5.67);
    tl.to(".arr-se", { attr: { "stroke-dashoffset": 0 }, duration: 0.58, ease: "power2.inOut" }, 5.78);

    tl.to("#head-west", { opacity: 1, scale: 1.0, duration: 0.16, ease: "expo.out" }, 6.02);
    tl.to("#head-ne", { opacity: 1, scale: 1.0, duration: 0.16, ease: "expo.out" }, 6.16);
    tl.to("#head-se", { opacity: 1, scale: 1.0, duration: 0.16, ease: "expo.out" }, 6.27);
    tl.to("#flow-hub", { opacity: 1, scale: 1.0, duration: 0.22, ease: "expo.out" }, 6.30);

    window.__timelines = window.__timelines || {};
    window.__timelines["props-scene"] = tl;
  </script>
</template>
`;

  writeFileSync(join(STUDY_DIR, "index.html"), indexHtml, "utf8");
  writeFileSync(join(COMP_DIR, "props-scene.html"), sceneHtml, "utf8");
  writeFileSync(join(COMP_DIR, "broadcast-layer.html"), buildBroadcastLayerHtml(8), "utf8");
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });
  mkdirSync(COMP_DIR, { recursive: true });
  mkdirSync(RENDERS_DIR, { recursive: true });

  const tileServer = await startTileServer(8771, "127.0.0.1");
  const tileBaseUrl = "http://127.0.0.1:8771";
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
    console.log("[props] Baking plates & projected prop anchor coordinates...");
    const coords = await bakePlatesAndCoords(browser, tileBaseUrl);
    writeHyperframesProject(coords);
    await validateStudyProject(STUDY_DIR, "props");

    const { server: assetServer, baseUrl: assetBaseUrl } = await startStudyAssetServer(STUDY_DIR);
    try {
      const framesDir = join(RENDERS_DIR, "frames-props");
      console.log("[props] Rendering 240-frame (8.0s @ 30fps) HyperFrames timeline...");
      await renderProjectFrames({
        browser,
        baseUrl: assetBaseUrl,
        studyDir: STUDY_DIR,
        totalFrames: 240,
        fps: 30,
        framesDir,
      });

      const outMp4 = join(RENDERS_DIR, "props_1080x1920.mp4");
      const sheetJpg = join(RENDERS_DIR, "props_sheet.jpg");
      encodeDeliverableAndSheet({
        framesDir,
        outMp4,
        sheetJpg,
        fps: 30,
        selectFrames: [22, 62, 115, 150, 192, 225],
      });
      console.log(`[props] Complete -> ${outMp4}`);
    } finally {
      assetServer.close();
    }
  } finally {
    await browser.close();
    tileServer.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
