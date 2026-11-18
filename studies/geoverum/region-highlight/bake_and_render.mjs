#!/usr/bin/env node
/**
 * Bake the projected Sulawesi geometry & satellite plate, generate the HyperFrames
 * composition (`index.html` + `compositions/region-highlight-scene.html`), validate with
 * `@hyperframes/lint`, and render the 300-frame (10.0s @ 30fps, 1080x1920) deliverable
 * for Geoverum Region Highlight (`region-highlight`).
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { startTileServer } from "../../../tools/geo-assets/serve_tiles.mjs";
import { lintHyperframesProjectDir } from "../../../packages/hf-compiler-ts/dist/lint.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const COMP_DIR = join(STUDY_DIR, "compositions");
const RENDERS_DIR = join(STUDY_DIR, "renders");

const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const puppeteer = require("puppeteer-core");

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
  throw new Error("Chrome / chrome-headless-shell not found.");
}

async function captureBasePlateAndCoords(browser, baseUrl) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${baseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${baseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    * { margin: 0; padding: 0; }
    html, body, #map { width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    const BASE_URL = ${JSON.stringify(baseUrl)};
    let sulawesiRegions = null;
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: "mercator" },
        sources: {
          sat: {
            type: "raster",
            tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"],
            tileSize: 256,
            maxzoom: 11
          }
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#03161F" } },
          { id: "sat", type: "raster", source: "sat" }
        ]
      },
      center: [121.35, -1.75],
      zoom: 5.95,
      pitch: 0,
      bearing: 0,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true
    });

    window.__ready = new Promise((res) => {
      map.on("load", async () => {
        sulawesiRegions = await fetch(BASE_URL + "/vector/sulawesi_regions.geojson").then((r) => r.json());
        const t0 = performance.now();
        (function poll() {
          if (map.loaded() && map.areTilesLoaded()) {
            map.triggerRepaint();
            requestAnimationFrame(() => requestAnimationFrame(res));
            return;
          }
          if (performance.now() - t0 > 8000) { res(); return; }
          setTimeout(poll, 35);
        })();
      });
    });

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
    function bboxOfGeom(geom) {
      let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
      function eat(ring) {
        for (const c of ring) {
          const p = map.project(c);
          if (p.x < minX) minX = p.x;
          if (p.y < minY) minY = p.y;
          if (p.x > maxX) maxX = p.x;
          if (p.y > maxY) maxY = p.y;
        }
      }
      if (geom.type === "Polygon") geom.coordinates.forEach(eat);
      else if (geom.type === "MultiPolygon") geom.coordinates.forEach((poly) => poly.forEach(eat));
      return {
        x: Math.floor(minX - 6),
        y: Math.floor(minY - 6),
        w: Math.ceil(maxX - minX + 12),
        h: Math.ceil(maxY - minY + 12),
      };
    }

    window.__extract = function() {
      const islandFeat = sulawesiRegions.features.find((f) => f.properties.feature_type === "island_outline");
      const islandD = geomToPath(islandFeat.geometry);
      const islandBbox = bboxOfGeom(islandFeat.geometry);

      const byPeninsula = {};
      for (const f of sulawesiRegions.features) {
        if (f.properties.feature_type !== "peninsula_mask") continue;
        const pen = f.properties.peninsula;
        if (!byPeninsula[pen]) byPeninsula[pen] = { paths: [], bboxes: [] };
        byPeninsula[pen].paths.push(geomToPath(f.geometry));
        byPeninsula[pen].bboxes.push(bboxOfGeom(f.geometry));
      }

      const peninsulas = {};
      for (const [k, v] of Object.entries(byPeninsula)) {
        const minX = Math.min(...v.bboxes.map((b) => b.x));
        const minY = Math.min(...v.bboxes.map((b) => b.y));
        const maxX = Math.max(...v.bboxes.map((b) => b.x + b.w));
        const maxY = Math.max(...v.bboxes.map((b) => b.y + b.h));
        peninsulas[k] = {
          d: v.paths.join(" "),
          bbox: { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
        };
      }

      return {
        islandD,
        islandBbox,
        peninsulas,
        pulses: {
          north: map.project([124.15, 0.82]),
          east: map.project([122.45, -1.18]),
          se: map.project([122.05, -3.95]),
          south: map.project([119.95, -4.35]),
        }
      };
    };
  </script>
</body>
</html>`;

  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => window.__ready);
  const baseJpg = join(ASSETS_DIR, "sulawesi-base.jpg");
  await page.screenshot({
    path: baseJpg,
    type: "jpeg",
    quality: 94,
    clip: { x: 0, y: 0, width: 1080, height: 1920 },
  });
  const coords = await page.evaluate(() => window.__extract());
  writeFileSync(join(ASSETS_DIR, "sulawesi-coords.json"), JSON.stringify(coords, null, 2));
  await page.close();
  return coords;
}

function writeHyperframesProject(coords) {
  const indexHtml = `<!DOCTYPE html>
<html
  lang="id"
  data-composition-variables='[
    {"id":"color-ground","type":"color","label":"Background","default":"#03161F"},
    {"id":"color-ink","type":"color","label":"Text","default":"#F4F1EA"},
    {"id":"color-accent","type":"color","label":"Accent","default":"#F5C542"},
    {"id":"font-display","type":"string","label":"Display font","default":"Space Grotesk"}
  ]'
>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Geoverum Region Highlight — Region Highlight</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
      font-style: normal;
    }
    :root {
      --color-ground: #03161F;
      --color-ink: #F4F1EA;
      --color-accent: #F5C542;
      --font-display: 'Space Grotesk';
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: var(--color-ground);
      font-family: var(--font-display), sans-serif;
      font-variant-numeric: tabular-nums;
      -webkit-font-smoothing: antialiased;
    }
    #root {
      position: relative;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: var(--color-ground);
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
      id="region-highlight-scene"
      data-composition-id="region-highlight-scene"
      data-composition-src="compositions/region-highlight-scene.html"
      data-start="0"
      data-duration="10"
      data-track-index="1"
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

  const ib = coords.islandBbox;
  // Partition the island bounding box into 4 non-overlapping quadrant bands corresponding to the 4 peninsulas:
  // 1. Northern arm: top 26% of island height (y: ib.y .. ib.y + 0.26*h), wiping left-to-right
  // 2. Eastern arm: middle-upper band (y: ib.y + 0.26*h .. ib.y + 0.54*h, x: center .. right), wiping left-to-right
  // 3. Southeastern arm: lower-right quadrant (y: ib.y + 0.54*h .. ib.y + h, x: splitX .. right), wiping top-to-bottom
  // 4. Southern arm + western spine: remaining left/south region, wiping top-to-bottom
  const yNorthEnd = Math.round(ib.y + ib.h * 0.27);
  const yMidEnd = Math.round(ib.y + ib.h * 0.55);
  const xSpineSplit = Math.round(ib.x + ib.w * 0.36);
  const xSouthSplit = Math.round(ib.x + ib.w * 0.44);

  const zones = {
    north: { x: ib.x, y: ib.y, w: ib.w, h: yNorthEnd - ib.y },
    east: { x: xSpineSplit, y: yNorthEnd, w: ib.x + ib.w - xSpineSplit, h: yMidEnd - yNorthEnd },
    se: { x: xSouthSplit, y: yMidEnd, w: ib.x + ib.w - xSouthSplit, h: ib.y + ib.h - yMidEnd },
    south: { x: ib.x, y: yNorthEnd, w: xSouthSplit - ib.x, h: ib.y + ib.h - yNorthEnd },
  };

  const pulseNodes = [
    { id: "pulse-north", pt: coords.pulses.north, start: 6.50 },
    { id: "pulse-east", pt: coords.pulses.east, start: 6.77 },
    { id: "pulse-se", pt: coords.pulses.se, start: 7.00 },
    { id: "pulse-south", pt: coords.pulses.south, start: 7.20 },
  ];

  const pulseMarkup = pulseNodes
    .map(
      (n) => `
          <g id="${n.id}" transform="translate(${n.pt.x.toFixed(1)}, ${n.pt.y.toFixed(1)})">
            <circle class="pulse-ring-outer" r="18" fill="rgba(245, 197, 66, 0.24)" stroke="#F5C542" stroke-width="2.8" style="opacity: 0;" />
            <circle class="pulse-ring-inner" r="14" fill="rgba(194, 65, 45, 0.38)" stroke="#F4F1EA" stroke-width="2.2" style="opacity: 0;" />
            <circle class="pulse-core" r="9.5" fill="#F5C542" stroke="#F4F1EA" stroke-width="3.0" style="opacity: 0;" />
          </g>`
    )
    .join("\n");

  const sceneHtml = `<template>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
      font-style: normal;
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
    }
    #stage-clip {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
    }
    /* Shared coordinate rig: satellite plate and SVG vectors transform as one locked unit */
    #camera-rig {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      transform-origin: 540px 960px;
      will-change: transform;
    }
    #basemap-plate {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      object-fit: cover;
      display: block;
    }
    #region-svg {
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
      z-index: 4;
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
      z-index: 4;
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
  <div id="root" data-composition-id="region-highlight-scene" data-width="1080" data-height="1920">
    <div id="stage-clip" class="clip" data-start="0" data-duration="10" data-track-index="1" data-layout-allow-overflow="true">
      <div id="camera-rig">
        <img id="basemap-plate" src="assets/sulawesi-base.jpg" alt="Sulawesi satellite basemap" />
        <svg id="region-svg" viewBox="0 0 1080 1920">
          <defs>
            <!-- Master exterior island clipPath: guarantees zero internal provincial seams and crisp coastal edges -->
            <clipPath id="sulawesi-land-clip">
              <path d="${coords.islandD}" />
            </clipPath>

            <!-- Unified progressive wipe clipPath composed of 4 non-overlapping peninsula reveal rects (Beat 2) -->
            <clipPath id="wipe-peninsulas-clip">
              <rect id="wipe-north-rect" x="${zones.north.x}" y="${zones.north.y}" width="0" height="${zones.north.h}" />
              <rect id="wipe-east-rect" x="${zones.east.x}" y="${zones.east.y}" width="0" height="${zones.east.h}" />
              <rect id="wipe-se-rect" x="${zones.se.x}" y="${zones.se.y}" width="${zones.se.w}" height="0" />
              <rect id="wipe-south-rect" x="${zones.south.x}" y="${zones.south.y}" width="${zones.south.w}" height="0" />
            </clipPath>

            <!-- Tectonic collision zone upward wipe clipPath (Beat 4) -->
            <clipPath id="wipe-hatch-clip">
              <rect id="wipe-hatch-rect" x="${ib.x}" y="${ib.y + ib.h}" width="${ib.w}" height="0" />
            </clipPath>

            <!-- 45-degree diagonal tectonic hatching pattern (Beat 4) -->
            <pattern id="tectonic-hatch-pattern" width="18" height="18" patternTransform="rotate(-45 0 0)" patternUnits="userSpaceOnUse">
              <rect width="18" height="18" fill="rgba(194, 65, 45, 0.28)" />
              <line x1="0" y1="0" x2="0" y2="18" stroke="#F5C542" stroke-width="5.5" opacity="0.86" />
            </pattern>

            <filter id="coastal-glow" x="-15%" y="-15%" width="130%" height="130%">
              <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#F4F1EA" flood-opacity="0.55" />
            </filter>
          </defs>

          <!-- BEAT 1: Terrain-Preserving Unified Crimson Silhouette -->
          <g id="crimson-silhouette-group" style="opacity: 0;">
            <path d="${coords.islandD}" fill="rgba(128, 14, 22, 0.64)" style="mix-blend-mode: multiply;" />
            <path d="${coords.islandD}" fill="rgba(168, 24, 32, 0.28)" />
          </g>

          <!-- BEAT 2: Progressive 4-Peninsula Cobalt-Azure Sweep (single unified island path -> ZERO internal seams) -->
          <g id="azure-sweep-group" clip-path="url(#sulawesi-land-clip)">
            <g clip-path="url(#wipe-peninsulas-clip)">
              <path d="${coords.islandD}" fill="rgba(22, 82, 205, 0.68)" style="mix-blend-mode: multiply;" />
              <path d="${coords.islandD}" fill="rgba(56, 132, 255, 0.46)" />
            </g>
          </g>

          <!-- BEAT 4: Tectonic Collision Zone Diagonal 45° Hatching (clipped inside unified exterior coastline) -->
          <g id="tectonic-hatch-group" clip-path="url(#sulawesi-land-clip)">
            <g clip-path="url(#wipe-hatch-clip)">
              <rect x="${ib.x}" y="${ib.y}" width="${ib.w}" height="${ib.h}" fill="url(#tectonic-hatch-pattern)" />
            </g>
          </g>

          <!-- Unified Exterior Coastline Rim (never draws internal provincial borders) -->
          <path
            id="exterior-coast-rim"
            d="${coords.islandD}"
            fill="none"
            stroke="#F4F1EA"
            stroke-width="2.1"
            stroke-linejoin="round"
            filter="url(#coastal-glow)"
            style="opacity: 0;"
          />

          <!-- BEAT 3: Non-Uniform Staggered Tectonic Pulse Markers on the 4 Peninsulas -->
          <g id="pulse-markers-group">
            ${pulseMarkup}
          </g>
        </svg>
      </div>
    </div>

    <div id="watermark-clip" class="clip" data-start="0" data-duration="10" data-track-index="2">
      <div id="watermark-inner">
        <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
          <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.2" />
          <ellipse cx="17" cy="17" rx="6" ry="13" stroke="#F4F1EA" stroke-width="1.6" />
          <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.6" />
        </svg>
        <span class="wm-wordmark" data-var-text="brand-name">GEOVERUM</span>
      </div>
    </div>

    <div id="credit-clip" class="clip" data-start="0" data-duration="10" data-track-index="3" data-layout-ignore="true">
      <div id="credit-inner" data-layout-ignore="true">
        Imagery: NASA Blue Marble, EOX Sentinel-2 cloudless 2016 (Copernicus) · Vectors: Natural Earth, PB2002, GEM
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });

    // Initialize starting states at t=0 so seek(0..6.5) keeps pulse nodes strictly invisible
    tl.set("#crimson-silhouette-group, #exterior-coast-rim", { opacity: 0 }, 0);
    tl.set(".pulse-core, .pulse-ring-inner, .pulse-ring-outer", { opacity: 0, scale: 0.5, svgOrigin: "0 0" }, 0);

    // Global Lead: Continuous slow camera push-in (never static; vectors & basemap locked in #camera-rig)
    tl.fromTo(
      "#camera-rig",
      { scale: 1.0, x: 0, y: 0 },
      { scale: 1.13, x: -12, y: -16, duration: 10.0, ease: "none", immediateRender: true },
      0.0
    );

    // Broadcast watermark entrance (200ms expo.out, then dead still)
    tl.fromTo(
      "#watermark-inner",
      { opacity: 0, scale: 0.96 },
      { opacity: 0.86, scale: 1.0, duration: 0.2, ease: "expo.out", immediateRender: true },
      0.1
    );

    // BEAT 1 (0.33s - 2.40s): Terrain-preserving unified crimson silhouette + exterior coastal rim
    tl.to("#crimson-silhouette-group", { opacity: 1, duration: 0.34, ease: "expo.out" }, 0.33);
    tl.to("#exterior-coast-rim", { opacity: 1, duration: 0.34, ease: "expo.out" }, 0.33);

    // BEAT 2 (2.50s - 6.20s): Progressive 4-Peninsula Sweep Recolor (20f = 0.67s per arm, power2.inOut)
    tl.to("#wipe-north-rect", { attr: { width: ${zones.north.w} }, duration: 0.67, ease: "power2.inOut" }, 2.50);
    tl.to("#wipe-east-rect", { attr: { width: ${zones.east.w} }, duration: 0.67, ease: "power2.inOut" }, 3.33);
    tl.to("#wipe-se-rect", { attr: { height: ${zones.se.h} }, duration: 0.67, ease: "power2.inOut" }, 4.13);
    tl.to("#wipe-south-rect", { attr: { height: ${zones.south.h} }, duration: 0.67, ease: "power2.inOut" }, 4.93);

    // Recede Beat 2 azure sweep cleanly before Beat 3 pulses begin ("Say it once" restraint)
    tl.to("#azure-sweep-group", { opacity: 0, duration: 0.28, ease: "power2.inOut" }, 6.20);

    // BEAT 3 (6.50s - 8.20s): Non-uniform staggered tectonic pulse markers (270ms -> 230ms -> 200ms)
    const pulses = [
      { sel: "#pulse-north", t: 6.50 },
      { sel: "#pulse-east", t: 6.77 },
      { sel: "#pulse-se", t: 7.00 },
      { sel: "#pulse-south", t: 7.20 },
    ];
    pulses.forEach((p) => {
      tl.fromTo(
        p.sel + " .pulse-core",
        { opacity: 0, scale: 0.92, svgOrigin: "0 0" },
        { opacity: 1, scale: 1.0, duration: 0.18, ease: "expo.out", immediateRender: false },
        p.t
      );
      tl.fromTo(
        p.sel + " .pulse-ring-inner",
        { opacity: 0.88, scale: 0.5, svgOrigin: "0 0" },
        { opacity: 0, scale: 2.4, duration: 0.52, ease: "expo.out", immediateRender: false },
        p.t
      );
      tl.fromTo(
        p.sel + " .pulse-ring-outer",
        { opacity: 0.82, scale: 0.55, svgOrigin: "0 0" },
        { opacity: 0, scale: 3.2, duration: 0.64, ease: "expo.out", immediateRender: false },
        p.t + 0.05
      );
    });

    // Simultaneous, snappy exit of all 4 pulse nodes at 8.20s (170ms)
    tl.to("#pulse-markers-group", { opacity: 0, duration: 0.17, ease: "power2.in" }, 8.20);

    // BEAT 4 (8.37s - 10.00s): Tectonic collision zone 45° diagonal hatching upward wipe
    const hatchTargetY = ${Math.round(ib.y + ib.h * 0.26)};
    const hatchTargetH = ${Math.round(ib.h * 0.74)};
    tl.to(
      "#wipe-hatch-rect",
      { attr: { y: hatchTargetY, height: hatchTargetH }, duration: 0.58, ease: "power2.inOut" },
      8.37
    );

    window.__timelines = window.__timelines || {};
    window.__timelines["region-highlight-scene"] = tl;
  </script>
</template>
`;

  writeFileSync(join(STUDY_DIR, "index.html"), indexHtml, "utf8");
  writeFileSync(join(COMP_DIR, "region-highlight-scene.html"), sceneHtml, "utf8");
}

async function renderTimelineFrames(browser, baseUrl) {
  const framesDir = join(RENDERS_DIR, "frames-region-highlight");
  mkdirSync(framesDir, { recursive: true });

  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });

  const gsapBytes = readFileSync(join(REPO_ROOT, "assets/geo/vendor/gsap.min.js"));
  const fontBytes = readFileSync(join(ASSETS_DIR, "fonts/SpaceGrotesk-Variable.ttf"));
  const basePlateB64 = readFileSync(join(ASSETS_DIR, "sulawesi-base.jpg")).toString("base64");

  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const u = req.url();
    if (u.includes("gsap") && u.endsWith(".js")) {
      req.respond({ status: 200, contentType: "application/javascript", body: gsapBytes });
      return;
    }
    if (u.endsWith("SpaceGrotesk-Variable.ttf")) {
      req.respond({ status: 200, contentType: "font/ttf", body: fontBytes });
      return;
    }
    req.continue();
  });

  // Build standalone runtime host that mounts the sub-composition template with embedded base plate
  const tplRaw = readFileSync(join(COMP_DIR, "region-highlight-scene.html"), "utf8");
  const innerMatch = tplRaw.match(/<template>([\s\S]*?)<\/template>/i);
  const tplContent = (innerMatch ? innerMatch[1] : tplRaw).replace(
    'src="assets/sulawesi-base.jpg"',
    `src="data:image/jpeg;base64,${basePlateB64}"`
  );

  const hostHtml = `<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <base href="${baseUrl}/">
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>* { margin: 0; padding: 0; box-sizing: border-box; } html, body { width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }</style>
</head>
<body>
  ${tplContent}
</body>
</html>`;

  await page.setContent(hostHtml, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);

  const N = 300;
  const FPS = 30;
  const t0 = Date.now();
  for (let i = 0; i < N; i++) {
    const tSec = i / FPS;
    await page.evaluate((t) => {
      window.__timelines["region-highlight-scene"].seek(t, false);
    }, tSec);
    await page.screenshot({
      path: join(framesDir, `f${String(i).padStart(4, "0")}.png`),
      clip: { x: 0, y: 0, width: 1080, height: 1920 },
      optimizeForSpeed: true,
    });
    if (i % 60 === 0 || i === N - 1) {
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      console.log(`  [region-highlight] rendered frame ${i + 1}/${N} (${elapsed}s)`);
    }
  }
  await page.close();

  const outMp4 = join(RENDERS_DIR, "region_highlight_1080x1920.mp4");
  const ff = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-framerate",
      "30",
      "-i",
      join(framesDir, "f%04d.png"),
      "-c:v",
      "libx264",
      "-profile:v",
      "high",
      "-pix_fmt",
      "yuv420p",
      "-r",
      "30",
      "-color_primaries",
      "bt709",
      "-color_trc",
      "bt709",
      "-colorspace",
      "bt709",
      "-crf",
      "16",
      "-g",
      "60",
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ff.status !== 0) {
    throw new Error(`FFmpeg encoding failed with status ${ff.status}`);
  }

  // Extract 6 key QA beats contact sheet (f005, f045, f115, f175, f218, f280)
  const sheetJpg = join(RENDERS_DIR, "region_highlight_sheet.jpg");
  const ffSheet = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      outMp4,
      "-vf",
      "drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text='f%{n} %{pts\\:hms}':x=20:y=20:fontsize=38:fontcolor=yellow:box=1:boxcolor=black@0.7,select='eq(n\\,5)+eq(n\\,45)+eq(n\\,115)+eq(n\\,175)+eq(n\\,218)+eq(n\\,280)',scale=540:960,tile=3x2",
      "-fps_mode",
      "passthrough",
      "-frames:v",
      "1",
      "-update",
      "1",
      sheetJpg,
    ],
    { stdio: "inherit" }
  );
  if (ffSheet.status !== 0) {
    throw new Error(`Contact sheet extraction failed with status ${ffSheet.status}`);
  }

  rmSync(framesDir, { recursive: true, force: true });
  return outMp4;
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });
  mkdirSync(COMP_DIR, { recursive: true });
  mkdirSync(RENDERS_DIR, { recursive: true });

  const port = 8768;
  const server = await startTileServer(port, "127.0.0.1");
  const baseUrl = `http://127.0.0.1:${port}`;

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
    console.log("[region-highlight] Capturing Sulawesi base plate and projecting vector coordinates...");
    const coords = await captureBasePlateAndCoords(browser, baseUrl);

    console.log("[region-highlight] Writing HyperFrames project files...");
    writeHyperframesProject(coords);

    console.log("[region-highlight] Running @hyperframes/lint & performance gate...");
    const lintSummary = await lintHyperframesProjectDir(STUDY_DIR);
    console.log(JSON.stringify(lintSummary, null, 2));
    if (!lintSummary.ok) {
      throw new Error(`HyperFrames lint failed with ${lintSummary.totalErrors} error(s).`);
    }

    console.log("[region-highlight] Rendering 300-frame (10.0s @ 30fps) GSAP timeline...");
    const outMp4 = await renderTimelineFrames(browser, baseUrl);
    console.log(`[region-highlight] Complete -> ${outMp4}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
