#!/usr/bin/env node
/**
 * Bake multi-scale MapLibre base plates and projected cartographic vectors for
 * Geoverum Labels & Lines (`labels-lines`), generate the HyperFrames project,
 * validate via `@hyperframes/lint`, and render the 300-frame (10.0s @ 30fps)
 * 1080x1920 deliverable and 6-beat QA sheet.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { startTileServer } from "../../../tools/geo-assets/serve_tiles.mjs";
import {
  buildBroadcastLayerHtml,
  buildSmoothCatmullRomPath,
  buildTaperedFaultPath,
  encodeDeliverableAndSheet,
  puppeteer,
  renderProjectFrames,
  resolveChrome,
  startStudyAssetServer,
  validateStudyProject,
} from "../../../tools/geo-assets/study_runner.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const COMP_DIR = join(STUDY_DIR, "compositions");
const RENDERS_DIR = join(STUDY_DIR, "renders");

const BEATS = [
  {
    id: "corridor",
    projection: "mercator",
    center: [57.5, 28.5],
    zoom: 3.18,
    pitch: 6,
    bearing: 0,
    plateFile: "plate-corridor.jpg",
  },
  {
    id: "tomini",
    projection: "mercator",
    center: [120.88, -0.25],
    zoom: 7.65,
    pitch: 36,
    bearing: -8,
    plateFile: "plate-tomini.jpg",
  },
  {
    id: "kshape",
    projection: "mercator",
    center: [121.35, -1.75],
    zoom: 5.95,
    pitch: 0,
    bearing: 0,
    plateFile: "plate-kshape.jpg",
  },
  {
    id: "palu",
    projection: "mercator",
    center: [121.35, -1.68],
    zoom: 6.05,
    pitch: 14,
    bearing: -4,
    plateFile: "plate-palu.jpg",
  },
];

function computePolylineLength(pts) {
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
        sources: {
          sat: { type: "raster", tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"], tileSize: 256, maxzoom: 11 }
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#03161F" } },
          { id: "sat", type: "raster", source: "sat" }
        ]
      },
      center: [121.35, -1.75],
      zoom: 5.95,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true
    });

    window.__init = async function() {
      const [cResp, sResp] = await Promise.all([
        fetch(BASE_URL + "/vector/countries_curated.geojson"),
        fetch(BASE_URL + "/vector/sulawesi_regions.geojson")
      ]);
      countries = await cResp.json();
      sulawesi = await sResp.json();
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

    window.__setAndExtract = async function(beat) {
      map.setProjection({ type: beat.projection });
      map.jumpTo({ center: beat.center, zoom: beat.zoom, pitch: beat.pitch, bearing: beat.bearing });
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

      if (beat.id === "corridor") {
        const trFeat = countries.features.find((f) => f.properties.name === "Turkey");
        const inFeat = countries.features.find((f) => f.properties.name === "India");
        return {
          turkeyD: geomToPath(filterMainland(trFeat, 25, 46, 35, 43)),
          indiaD: geomToPath(filterMainland(inFeat, 67, 98, 7, 36)),
          ptTurkey: map.project([35.2, 39.0]),
          ptIndia: map.project([78.5, 22.8]),
          badgeTurkey: map.project([35.0, 41.2]),
          badgeIndia: map.project([78.8, 25.4]),
        };
      }

      if (beat.id === "tomini") {
        const mainlandFeat = sulawesi.features.find((f) => f.properties.feature_type === "mainland_exterior");
        const arcPts = [
          [120.22, -0.36],
          [120.58, -0.22],
          [120.98, -0.20],
          [121.34, -0.28],
        ].map((c) => map.project(c));
        return {
          mainlandD: geomToPath(mainlandFeat.geometry),
          arcPts,
        };
      }

      if (beat.id === "kshape") {
        const islandFeat = sulawesi.features.find((f) => f.properties.feature_type === "island_outline");
        const kSpine = [
          [124.85, 1.45], [122.80, 0.65], [120.42, 0.55],
          [119.88, -0.90], [119.45, -3.10], [119.85, -5.35],
        ].map((c) => map.project(c));
        const kUpper = [
          [120.12, -1.32], [121.55, -1.22], [123.15, -0.82],
        ].map((c) => map.project(c));
        const kLower = [
          [120.22, -1.65], [121.65, -3.20], [122.45, -4.40],
        ].map((c) => map.project(c));
        return {
          islandD: geomToPath(islandFeat.geometry),
          kSpine,
          kUpper,
          kLower,
        };
      }

      if (beat.id === "palu") {
        const islandFeat = sulawesi.features.find((f) => f.properties.feature_type === "island_outline");
        const faultPts = [
          [119.50, 0.28], [119.74, -0.35], [119.87, -0.90],
          [120.08, -1.48], [120.42, -2.08], [120.88, -2.52],
        ].map((c) => map.project(c));
        // Fault anchor along upper Makassar-facing neck for collision-free open-water badge placement
        const anchor = map.project([119.77, -0.60]);
        return {
          islandD: geomToPath(islandFeat.geometry),
          faultPts,
          anchor,
        };
      }
      return {};
    };
  </script>
</body>
</html>`;

  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => window.__init());

  const extracted = {};
  for (const beat of BEATS) {
    extracted[beat.id] = await page.evaluate((b) => window.__setAndExtract(b), beat);
    await page.screenshot({
      path: join(ASSETS_DIR, beat.plateFile),
      type: "jpeg",
      quality: 94,
      clip: { x: 0, y: 0, width: 1080, height: 1920 },
    });
    console.log(`  [labels-lines] Baked ${beat.plateFile} (${beat.id})`);
  }
  await page.close();
  writeFileSync(join(ASSETS_DIR, "labels-lines-coords.json"), JSON.stringify(extracted, null, 2));
  return extracted;
}

function writeHyperframesProject(coords) {
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
  <title>Geoverum Labels & Lines — Map Labels &amp; Line Choreography</title>
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
    @font-face {
      font-family: 'Unbounded';
      src: url('assets/fonts/Unbounded-Variable.ttf') format('truetype');
      font-weight: 400 900;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #03161F;
      font-family: 'Space Grotesk', sans-serif;
      font-variant-numeric: tabular-nums;
      -webkit-font-smoothing: antialiased;
    }
    #root {
      position: relative;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: #03161F;
    }
  </style>
</head>
<body>
  <div
    id="root"
    data-composition-id="main"
    data-start="0"
    data-duration="10"
    data-width="1080"
    data-height="1920"
    data-fps="30"
  >
    <div
      id="labels-lines-scene"
      data-composition-id="labels-lines-scene"
      data-composition-src="compositions/labels-lines-scene.html"
      data-start="0"
      data-duration="10"
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
      data-duration="10"
      data-track-index="2"
      data-track-kind="graphics"
      data-width="1080"
      data-height="1920"
    ></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.to({}, { duration: 10 });
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
`;

  // Beat 1 geometry (Turkey -> India corridor)
  const c = coords.corridor;
  const dx = c.ptIndia.x - c.ptTurkey.x;
  const dy = c.ptIndia.y - c.ptTurkey.y;
  const angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
  const midX = (c.ptTurkey.x + c.ptIndia.x) / 2 - 36;
  const midY = (c.ptTurkey.y + c.ptIndia.y) / 2 + 64;
  const trX = Math.round(c.badgeTurkey.x);
  const trY = Math.round(c.badgeTurkey.y);
  const inX = Math.round(c.badgeIndia.x);
  const inY = Math.round(c.badgeIndia.y);
  const lineStartX = Math.round(Math.min(c.ptTurkey.x, c.ptIndia.x) - 16);
  const lineSpanW = Math.round(Math.abs(dx) + 32);

  // Beat 2 geometry (Gulf of Tomini smooth arc + split tspans)
  const tominiArcD = buildSmoothCatmullRomPath(coords.tomini.arcPts);
  const tominiChars = "TELUK TOMINI".split("");
  const tominiTspans = tominiChars
    .map((ch, idx) =>
      ch === " "
        ? `<tspan xml:space="preserve"> </tspan>`
        : `<tspan class="tomini-char" id="tc-${idx}" style="opacity: 0;">${ch}</tspan>`
    )
    .join("");

  // Beat 3 geometry (Sulawesi K dual-stroke paths with computed arc lengths for stroke-dashoffset)
  const k = coords.kshape;
  const dSpine = buildSmoothCatmullRomPath(k.kSpine);
  const dUpper = buildSmoothCatmullRomPath(k.kUpper);
  const dLower = buildSmoothCatmullRomPath(k.kLower);
  const lenSpine = Math.ceil(computePolylineLength(k.kSpine) * 1.15);
  const lenUpper = Math.ceil(computePolylineLength(k.kUpper) * 1.15);
  const lenLower = Math.ceil(computePolylineLength(k.kLower) * 1.15);

  // Beat 4 geometry (Palu-Koro fault + clean open-water callout badge over Makassar Strait)
  const p = coords.palu;
  const taperedFaultD = buildTaperedFaultPath(p.faultPts, 5.4, 0.8);
  const faultMinY = Math.floor(Math.min(...p.faultPts.map((q) => q.y)) - 8);
  const faultMaxY = Math.ceil(Math.max(...p.faultPts.map((q) => q.y)) + 8);
  const faultH = faultMaxY - faultMinY;
  const tipX = Math.round(p.anchor.x - 8); // 8px clear of the golden fault trace in open Makassar Strait
  const tipY = Math.round(p.anchor.y);
  const badgeW = 246;
  const badgeH = 42;
  const badgeX = tipX - 18 - badgeW; // cleanly in open water west of Sulawesi
  const badgeY = tipY - Math.round(badgeH / 2);

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
    @font-face {
      font-family: 'Unbounded';
      src: url('assets/fonts/Unbounded-Variable.ttf') format('truetype');
      font-weight: 400 900;
    }
    #root {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: #03161F;
      font-family: 'Space Grotesk', sans-serif;
      font-variant-numeric: tabular-nums;
      -webkit-font-smoothing: antialiased;
    }
    .beat-layer {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      opacity: 0;
    }
    .cam-rig {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      transform-origin: 540px 960px;
      will-change: transform;
    }
    .plate-img {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      object-fit: cover;
      display: block;
    }
    .vec-svg {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      pointer-events: none;
    }
    #watermark-clip {
      position: absolute;
      top: 72px;
      left: 108px;
      right: 108px;
      display: flex;
      justify-content: center;
      pointer-events: none;
      z-index: 6;
    }
    #watermark-inner {
      display: flex;
      align-items: center;
      gap: 14px;
      opacity: 0;
    }
    .wm-wordmark {
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      font-size: 32px;
      letter-spacing: 0.12em;
      color: #F4F1EA;
      line-height: 1;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.68);
    }
    #credit-clip {
      position: absolute;
      bottom: 24px;
      left: 84px;
      right: 84px;
      display: flex;
      justify-content: center;
      pointer-events: none;
      z-index: 6;
    }
    #credit-inner {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 13px;
      font-weight: 400;
      color: rgba(244, 241, 234, 0.40);
      letter-spacing: 0.01em;
      text-align: center;
    }
  </style>
  <div id="root" data-composition-id="labels-lines-scene" data-width="1080" data-height="1920">
    <!-- BEAT 1 (0.00s - 2.80s): Turkey-India Geodesic Distance Corridor + Country Chips -->
    <div id="beat-corridor" class="beat-layer clip" data-start="0" data-duration="2.8" data-track-index="1" data-layout-allow-overflow="true">
      <div id="rig-corridor" class="cam-rig">
        <img class="plate-img" src="assets/plate-corridor.jpg" alt="Eurasia corridor basemap" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <defs>
            <clipPath id="corridor-wipe-clip">
              <rect id="corridor-wipe-rect" x="${lineStartX}" y="0" width="0" height="1920" />
            </clipPath>
            <filter id="card-drop-1" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.70" />
            </filter>
          </defs>
          <rect x="0" y="0" width="1080" height="1920" fill="rgba(3, 18, 26, 0.24)" />
          <path id="turkey-fill" d="${c.turkeyD}" fill="rgba(46, 107, 230, 0.64)" stroke="#F4F1EA" stroke-width="1.8" stroke-linejoin="round" style="opacity: 0;" />
          <path id="india-fill" d="${c.indiaD}" fill="rgba(194, 65, 45, 0.66)" stroke="#F4F1EA" stroke-width="1.8" stroke-linejoin="round" style="opacity: 0;" />

          <!-- Dashed geodesic trace revealed by geometry-independent clip mask (dash spacing stays rigid) -->
          <g clip-path="url(#corridor-wipe-clip)">
            <line x1="${c.ptTurkey.x.toFixed(1)}" y1="${c.ptTurkey.y.toFixed(1)}"
                  x2="${c.ptIndia.x.toFixed(1)}" y2="${c.ptIndia.y.toFixed(1)}"
                  stroke="#D9383A" stroke-width="7" stroke-dasharray="18 12" stroke-linecap="round" filter="url(#card-drop-1)" />
            <circle cx="${c.ptTurkey.x.toFixed(1)}" cy="${c.ptTurkey.y.toFixed(1)}" r="7" fill="#F5C542" stroke="#03161F" stroke-width="2.5" />
            <circle cx="${c.ptIndia.x.toFixed(1)}" cy="${c.ptIndia.y.toFixed(1)}" r="7" fill="#F5C542" stroke="#03161F" stroke-width="2.5" />
          </g>

          <!-- Tabular numeric distance readout parallel to corridor axis -->
          <g id="metric-group" transform="translate(${midX.toFixed(1)}, ${midY.toFixed(1)}) rotate(${angleDeg.toFixed(2)})" filter="url(#card-drop-1)" style="opacity: 0;">
            <text id="metric-text" x="0" y="0" text-anchor="middle" font-family="Archivo Black" font-size="40"
                  letter-spacing="0.02em" fill="#F5C542" stroke="#03161F" stroke-width="9"
                  stroke-linejoin="round" style="paint-order: stroke fill; font-variant-numeric: tabular-nums;">+0 KM</text>
          </g>

          <!-- Origin-aware country chips placed cleanly north of centroids -->
          <g id="badge-turkey" filter="url(#card-drop-1)" style="opacity: 0;">
            <rect x="${trX - 58}" y="${trY - 44}" width="116" height="35" rx="4" fill="#F5C542" />
            <path d="M ${trX - 8} ${trY - 9} L ${trX + 8} ${trY - 9} L ${trX} ${trY} Z" fill="#F5C542" />
            <text x="${trX}" y="${trY - 20}" text-anchor="middle" font-family="Archivo Black" font-size="19" fill="#03161F">TURKI</text>
          </g>

          <g id="badge-india" filter="url(#card-drop-1)" style="opacity: 0;">
            <rect x="${inX - 56}" y="${inY - 44}" width="112" height="35" rx="4" fill="#F5C542" />
            <path d="M ${inX - 8} ${inY - 9} L ${inX + 8} ${inY - 9} L ${inX} ${inY} Z" fill="#F5C542" />
            <text x="${inX}" y="${inY - 20}" text-anchor="middle" font-family="Archivo Black" font-size="19" fill="#03161F">INDIA</text>
          </g>
        </svg>
      </div>
    </div>

    <!-- BEAT 2 (2.80s - 5.30s): Close-Up Gulf of Tomini 3D Coast & Curved <textPath> -->
    <div id="beat-tomini" class="beat-layer clip" data-start="2.8" data-duration="2.5" data-track-index="2" data-layout-allow-overflow="true">
      <div id="rig-tomini" class="cam-rig">
        <img class="plate-img" src="assets/plate-tomini.jpg" alt="Gulf of Tomini close-up" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <defs>
            <path id="tomini-arc" d="${tominiArcD}" />
            <filter id="bay-rim-glow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="0" stdDeviation="8" flood-color="#7CE0F9" flood-opacity="0.72" />
            </filter>
            <filter id="bay-text-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="3" stdDeviation="6" flood-color="#010A0F" flood-opacity="0.92" />
            </filter>
          </defs>
          <path id="tomini-coast-rim" d="${coords.tomini.mainlandD}" fill="none" stroke="#E6F7FF" stroke-width="2.6" stroke-linejoin="round" filter="url(#bay-rim-glow)" style="opacity: 0;" />
          <text font-family="Unbounded" font-weight="800" font-size="30" fill="#7CE0F9" letter-spacing="3.5" filter="url(#bay-text-shadow)">
            <textPath href="#tomini-arc" startOffset="50%" text-anchor="middle">${tominiTspans}</textPath>
          </text>
        </svg>
      </div>
    </div>

    <!-- BEAT 3 (5.30s - 7.80s): Sulawesi Unified Crimson Silhouette & Progressive Dual-Stroke "K" -->
    <div id="beat-kshape" class="beat-layer clip" data-start="5.3" data-duration="2.5" data-track-index="3" data-layout-allow-overflow="true">
      <div id="rig-kshape" class="cam-rig">
        <img class="plate-img" src="assets/plate-kshape.jpg" alt="Sulawesi K-shape basemap" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <defs>
            <filter id="k-coast-glow" x="-15%" y="-15%" width="130%" height="130%">
              <feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#F4F1EA" flood-opacity="0.52" />
            </filter>
            <filter id="k-stroke-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="3" stdDeviation="6" flood-color="#000000" flood-opacity="0.68" />
            </filter>
          </defs>
          <g id="k-silhouette" style="opacity: 0;">
            <path d="${k.islandD}" fill="rgba(128, 14, 22, 0.62)" style="mix-blend-mode: multiply;" />
            <path d="${k.islandD}" fill="rgba(168, 24, 32, 0.28)" />
            <path d="${k.islandD}" fill="none" stroke="#F4F1EA" stroke-width="2.0" stroke-linejoin="round" filter="url(#k-coast-glow)" />
          </g>
          <g filter="url(#k-stroke-glow)">
            <path class="k-spine" d="${dSpine}" fill="none" stroke="#F4F1EA" stroke-width="14" stroke-linecap="round" stroke-dasharray="${lenSpine}" stroke-dashoffset="${lenSpine}" />
            <path class="k-upper" d="${dUpper}" fill="none" stroke="#F4F1EA" stroke-width="14" stroke-linecap="round" stroke-dasharray="${lenUpper}" stroke-dashoffset="${lenUpper}" />
            <path class="k-lower" d="${dLower}" fill="none" stroke="#F4F1EA" stroke-width="14" stroke-linecap="round" stroke-dasharray="${lenLower}" stroke-dashoffset="${lenLower}" />
            <path class="k-spine" d="${dSpine}" fill="none" stroke="#F5C542" stroke-width="7" stroke-linecap="round" stroke-dasharray="${lenSpine}" stroke-dashoffset="${lenSpine}" />
            <path class="k-upper" d="${dUpper}" fill="none" stroke="#F5C542" stroke-width="7" stroke-linecap="round" stroke-dasharray="${lenUpper}" stroke-dashoffset="${lenUpper}" />
            <path class="k-lower" d="${dLower}" fill="none" stroke="#F5C542" stroke-width="7" stroke-linecap="round" stroke-dasharray="${lenLower}" stroke-dashoffset="${lenLower}" />
          </g>
        </svg>
      </div>
    </div>

    <!-- BEAT 4 (7.80s - 10.00s): Palu-Koro Tapered Fault & Clean Open-Water Callout over Makassar Strait -->
    <div id="beat-palu" class="beat-layer clip" data-start="7.8" data-duration="2.2" data-track-index="4" data-layout-allow-overflow="true">
      <div id="rig-palu" class="cam-rig">
        <img class="plate-img" src="assets/plate-palu.jpg" alt="Palu-Koro fault basemap" />
        <svg class="vec-svg" viewBox="0 0 1080 1920">
          <defs>
            <clipPath id="fault-reveal-clip">
              <rect id="fault-reveal-rect" x="0" y="${faultMinY}" width="1080" height="0" />
            </clipPath>
            <filter id="palu-coast-soft" x="-15%" y="-15%" width="130%" height="130%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#F4F1EA" flood-opacity="0.38" />
            </filter>
            <filter id="palu-badge-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="5" stdDeviation="8" flood-color="#000000" flood-opacity="0.62" />
            </filter>
          </defs>
          <g id="palu-silhouette" style="opacity: 0;">
            <path d="${p.islandD}" fill="rgba(124, 14, 20, 0.64)" style="mix-blend-mode: multiply;" />
            <path d="${p.islandD}" fill="rgba(160, 22, 30, 0.24)" />
            <path d="${p.islandD}" fill="none" stroke="#F4F1EA" stroke-width="1.6" stroke-linejoin="round" filter="url(#palu-coast-soft)" />
          </g>
          <g clip-path="url(#fault-reveal-clip)">
            <path d="${taperedFaultD}" fill="#F5C542" filter="url(#palu-badge-shadow)" />
          </g>
          <g id="palu-callout" filter="url(#palu-badge-shadow)" style="opacity: 0;">
            <path d="M ${tipX} ${tipY} L ${badgeX + badgeW} ${badgeY + 12} L ${badgeX + badgeW} ${badgeY + badgeH - 12} Z" fill="#F4F1EA" />
            <rect x="${badgeX}" y="${badgeY}" width="${badgeW}" height="${badgeH}" rx="5" fill="#F4F1EA" />
            <text x="${badgeX + badgeW / 2}" y="${badgeY + 28}" text-anchor="middle"
                  font-family="Archivo Black" font-size="18.5" letter-spacing="0.02em" fill="#03161F">SESAR PALU-KORO</text>
          </g>
        </svg>
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    const metricEl = document.getElementById("metric-text");
    const distCounter = { km: 0 };

    function updateKmText() {
      const n = Math.round(distCounter.km);
      const formatted = n.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ".");
      metricEl.textContent = "+" + formatted + " KM";
    }

    // Explicit initial states at t=0
    tl.set("#beat-corridor", { opacity: 1 }, 0);
    tl.set("#beat-tomini, #beat-kshape, #beat-palu", { opacity: 0 }, 0);
    tl.set("#turkey-fill, #india-fill, #badge-turkey, #badge-india, #metric-group", { opacity: 0 }, 0);
    tl.set("#badge-turkey", { scale: 0.92, svgOrigin: "${trX} ${trY}" }, 0);
    tl.set("#badge-india", { scale: 0.92, svgOrigin: "${inX} ${inY}" }, 0);
    tl.set("#palu-callout", { opacity: 0, scale: 0.92, svgOrigin: "${tipX} ${tipY}" }, 0);

    // BEAT 1 (0.00s - 2.80s)
    tl.fromTo("#rig-corridor", { scale: 1.0, x: 0, y: 0 }, { scale: 1.06, x: -8, y: -6, duration: 2.8, ease: "none" }, 0.0);
    tl.to("#turkey-fill", { opacity: 1, duration: 0.24, ease: "expo.out" }, 0.08);
    tl.to("#india-fill", { opacity: 1, duration: 0.24, ease: "expo.out" }, 0.16);
    tl.to("#badge-turkey", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 0.18);
    tl.to("#corridor-wipe-rect", { attr: { width: ${lineSpanW} }, duration: 0.80, ease: "power2.inOut" }, 0.35);
    tl.to("#metric-group", { opacity: 1, duration: 0.18, ease: "expo.out" }, 0.42);
    tl.to(distCounter, { km: 4000, duration: 0.72, ease: "power2.inOut", onUpdate: updateKmText }, 0.42);
    tl.to("#badge-india", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 0.98);

    // Clean beat cut at 2.80s -> BEAT 2
    tl.set("#beat-corridor", { opacity: 0 }, 2.80);
    tl.set("#beat-tomini", { opacity: 1 }, 2.80);
    tl.fromTo("#rig-tomini", { scale: 1.0, x: 0, y: 0 }, { scale: 1.07, x: -6, y: 8, duration: 2.5, ease: "none" }, 2.80);
    tl.to("#tomini-coast-rim", { opacity: 1, duration: 0.24, ease: "expo.out" }, 2.90);

    // Curved Bay TextPath non-uniform per-glyph reveal (48ms stepping down to 26ms)
    const charEls = Array.from(document.querySelectorAll(".tomini-char"));
    let tChar = 3.20;
    charEls.forEach((el, idx) => {
      tl.to(el, { opacity: 1, duration: 0.09, ease: "expo.out" }, tChar);
      const step = Math.max(0.026, 0.048 - idx * 0.0022);
      tChar += step;
    });

    // Clean beat cut at 5.30s -> BEAT 3
    tl.set("#beat-tomini", { opacity: 0 }, 5.30);
    tl.set("#beat-kshape", { opacity: 1 }, 5.30);
    tl.fromTo("#rig-kshape", { scale: 1.0, x: 0, y: 0 }, { scale: 1.06, x: 0, y: -8, duration: 2.5, ease: "none" }, 5.30);
    tl.to("#k-silhouette", { opacity: 1, duration: 0.25, ease: "expo.out" }, 5.36);
    tl.to(".k-spine", { attr: { "stroke-dashoffset": 0 }, duration: 0.48, ease: "power2.inOut" }, 5.55);
    tl.to(".k-upper", { attr: { "stroke-dashoffset": 0 }, duration: 0.42, ease: "power2.inOut" }, 5.85);
    tl.to(".k-lower", { attr: { "stroke-dashoffset": 0 }, duration: 0.42, ease: "power2.inOut" }, 6.08);

    // Clean beat cut at 7.80s -> BEAT 4
    tl.set("#beat-kshape", { opacity: 0 }, 7.80);
    tl.set("#beat-palu", { opacity: 1 }, 7.80);
    tl.fromTo("#rig-palu", { scale: 1.0, x: 0, y: 0 }, { scale: 1.05, x: 6, y: -6, duration: 2.2, ease: "none" }, 7.80);
    tl.to("#palu-silhouette", { opacity: 1, duration: 0.22, ease: "expo.out" }, 7.85);
    tl.to("#fault-reveal-rect", { attr: { height: ${faultH} }, duration: 0.68, ease: "power2.inOut" }, 8.00);
    tl.to("#palu-callout", { opacity: 1, scale: 1.0, duration: 0.20, ease: "expo.out" }, 8.54);

    window.__timelines = window.__timelines || {};
    window.__timelines["labels-lines-scene"] = tl;
  </script>
</template>
`;

  writeFileSync(join(STUDY_DIR, "index.html"), indexHtml, "utf8");
  writeFileSync(join(COMP_DIR, "labels-lines-scene.html"), sceneHtml, "utf8");
  writeFileSync(join(COMP_DIR, "broadcast-layer.html"), buildBroadcastLayerHtml(10), "utf8");
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });
  mkdirSync(COMP_DIR, { recursive: true });
  mkdirSync(RENDERS_DIR, { recursive: true });

  const tileServer = await startTileServer(8769, "127.0.0.1");
  const tileBaseUrl = `http://127.0.0.1:8769`;
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
    console.log("[labels-lines] Baking basemap plates and projecting cartographic vectors...");
    const coords = await bakePlatesAndCoords(browser, tileBaseUrl);
    writeHyperframesProject(coords);
    await validateStudyProject(STUDY_DIR, "labels-lines");

    const { server: assetServer, baseUrl: assetBaseUrl } = await startStudyAssetServer(STUDY_DIR);
    try {
      const framesDir = join(RENDERS_DIR, "frames-labels-lines");
      console.log("[labels-lines] Rendering 300-frame (10.0s @ 30fps) HyperFrames timeline...");
      await renderProjectFrames({
        browser,
        baseUrl: assetBaseUrl,
        studyDir: STUDY_DIR,
        totalFrames: 300,
        fps: 30,
        framesDir,
      });

      const outMp4 = join(RENDERS_DIR, "labels_lines_1080x1920.mp4");
      const sheetJpg = join(RENDERS_DIR, "labels_lines_sheet.jpg");
      encodeDeliverableAndSheet({
        framesDir,
        outMp4,
        sheetJpg,
        fps: 30,
        selectFrames: [18, 56, 128, 190, 220, 276],
      });
      console.log(`[labels-lines] Complete -> ${outMp4}`);
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
