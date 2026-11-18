#!/usr/bin/env node
/**
 * Bake the Sulawesi pullback plate and render Geoverum Branding (`branding`),
 * verifying the unboxed broadcast meridian watermark and editorial documentary closing end-card
 * across 180 frames (6.0s @ 30fps, 1080x1920).
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { startTileServer } from "../../../tools/geo-assets/serve_tiles.mjs";
import {
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

async function bakeSulawesiPullbackPlate(browser, tileBaseUrl) {
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
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: "mercator" },
        sources: { sat: { type: "raster", tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"], tileSize: 256, maxzoom: 11 } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#03161F" } }, { id: "sat", type: "raster", source: "sat" }]
      },
      center: [121.35, -1.75], zoom: 5.80, pitch: 8, bearing: -3,
      interactive: false, attributionControl: false, fadeDuration: 0, preserveDrawingBuffer: true
    });
    window.__ready = new Promise((res) => {
      map.on("load", () => {
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
    });
  </script>
</body>
</html>`;

  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => window.__ready);
  await page.screenshot({
    path: join(ASSETS_DIR, "sulawesi-outro-plate.jpg"),
    type: "jpeg",
    quality: 94,
    clip: { x: 0, y: 0, width: 1080, height: 1920 },
  });
  await page.close();
  console.log("  [branding] Baked sulawesi-outro-plate.jpg");
}

function writeHyperframesProject() {
  const locPath = readMaterialIconPath("location_on");

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
  <title>Geoverum Branding — Channel Watermark &amp; Documentary End-Card</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: #03161F; }
    #root { position: relative; width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }
  </style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="6" data-width="1080" data-height="1920" data-fps="30">
    <div
      id="branding-scene"
      data-composition-id="branding-scene"
      data-composition-src="compositions/branding-scene.html"
      data-start="0"
      data-duration="6"
      data-track-index="1"
      data-track-kind="graphics"
      data-width="1080"
      data-height="1920"
    ></div>
    <div
      id="top-bug"
      data-composition-id="top-bug"
      data-composition-src="compositions/top-bug.html"
      data-start="0"
      data-duration="2.25"
      data-track-index="2"
      data-track-kind="graphics"
      data-width="1080"
      data-height="1920"
    ></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.to({}, { duration: 6 });
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
    #pullback-rig {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      transform-origin: 540px 960px;
      will-change: transform;
    }
    #pullback-img {
      width: 1080px;
      height: 1920px;
      object-fit: cover;
      display: block;
    }
    #outro-scrim {
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(3, 22, 31, 0.56) 0%, rgba(3, 22, 31, 0.78) 50%, rgba(3, 22, 31, 0.64) 100%);
      opacity: 0.14;
      pointer-events: none;
    }
    /* Upper safe-zone unboxed broadcast watermark (exits before endcard lockup enters -> "Say it once") */
    #top-bug-clip {
      position: absolute;
      top: 72px;
      left: 108px;
      right: 108px;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }
    #top-bug-inner {
      display: flex;
      align-items: center;
      gap: 14px;
      opacity: 0;
    }
    .bug-text {
      font-weight: 700;
      font-size: 32px;
      letter-spacing: 0.12em;
      color: #F4F1EA;
      line-height: 1;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.68);
    }

    /* Editorial closing prompt card in calm central safe band */
    #endcard-clip {
      position: absolute;
      top: 640px;
      left: 120px;
      right: 120px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      pointer-events: none;
    }
    #endcard-head {
      display: flex;
      flex-direction: column;
      align-items: center;
      opacity: 0;
    }
    .ec-brand-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 18px;
    }
    .ec-brand-label {
      font-weight: 700;
      font-size: 20px;
      letter-spacing: 0.16em;
      color: rgba(244, 241, 234, 0.84);
    }
    .ec-accent-rule {
      width: 56px;
      height: 3px;
      background: #F5C542;
      margin-bottom: 28px;
    }
    .ec-headline {
      font-weight: 700;
      font-size: 52px;
      line-height: 1.18;
      letter-spacing: -0.015em;
      color: #F4F1EA;
      max-width: 760px;
    }
    #endcard-cta {
      margin-top: 34px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding-bottom: 12px;
      border-bottom: 2px solid rgba(245, 197, 66, 0.42);
      opacity: 0;
    }
    .cta-label {
      font-weight: 500;
      font-size: 29px;
      color: #F5C542;
      letter-spacing: -0.01em;
    }
    #endcard-colophon {
      margin-top: 56px;
      font-weight: 400;
      font-size: 16px;
      letter-spacing: 0.04em;
      color: rgba(244, 241, 234, 0.56);
      opacity: 0;
    }
    #tail-dip {
      position: absolute;
      inset: 0;
      background: #03161F;
      opacity: 0;
      pointer-events: none;
    }
  </style>
  <div id="root" data-composition-id="branding-scene" data-width="1080" data-height="1920">
    <div id="map-clip" class="clip" data-start="0" data-duration="6" data-track-index="1" data-layout-allow-overflow="true">
      <div id="pullback-rig">
        <img id="pullback-img" src="assets/sulawesi-outro-plate.jpg" alt="Sulawesi pullback relief" />
      </div>
      <div id="outro-scrim"></div>
    </div>

    <div id="endcard-clip" class="clip" data-start="2.20" data-duration="3.80" data-track-index="2">
      <div id="endcard-head">
        <div class="ec-brand-row">
          <svg width="26" height="26" viewBox="0 0 34 34" fill="none">
            <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.3" />
            <ellipse cx="17" cy="17" rx="6" ry="13" stroke="#F4F1EA" stroke-width="1.7" />
            <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.7" />
          </svg>
          <span class="ec-brand-label">GEOVERUM · GEOGRAFI NUSANTARA</span>
        </div>
        <div class="ec-accent-rule"></div>
        <div class="ec-headline">Ada yang berasal dari Sulawesi?</div>
      </div>

      <div id="endcard-cta">
        <svg width="28" height="28" viewBox="0 -960 960 960" fill="none">
          <path d="${locPath}" fill="#F5C542" />
        </svg>
        <span class="cta-label">Tulis asal daerahmu di komentar</span>
      </div>

      <div id="endcard-colophon">
        Citra: NASA Blue Marble &amp; Copernicus Sentinel-2 · Vektor: Natural Earth &amp; GEM Faults
      </div>
    </div>

    <div id="tail-dip" class="clip" data-start="5.50" data-duration="0.50" data-track-index="4"></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });

    // Initial states at t=0
    tl.set("#endcard-head, #endcard-cta, #endcard-colophon, #tail-dip", { opacity: 0 }, 0);
    tl.set("#endcard-head", { y: 12 }, 0);
    tl.set("#endcard-cta", { y: 8, scale: 0.96 }, 0);

    // Global Lead: Continuous smooth satellite pullback across all 6.0 seconds
    tl.fromTo(
      "#pullback-rig",
      { scale: 1.12, x: 10, y: -26 },
      { scale: 1.00, x: 0, y: 0, duration: 6.0, ease: "none" },
      0.0
    );

    // Beat 2 (2.10s - 5.50s): Documentary scrim deepen + headline + comment CTA + colophon
    tl.to("#outro-scrim", { opacity: 0.92, duration: 0.42, ease: "power2.inOut" }, 2.10);
    tl.to("#endcard-head", { opacity: 1, y: 0, duration: 0.26, ease: "expo.out" }, 2.32);
    tl.to("#endcard-cta", { opacity: 1, y: 0, scale: 1.0, duration: 0.22, ease: "expo.out" }, 2.46);
    tl.to("#endcard-colophon", { opacity: 1, duration: 0.20, ease: "expo.out" }, 2.60);

    // Beat 3 (5.50s - 6.00s): Clean 15-frame fade-to-abyss exit
    tl.to("#tail-dip", { opacity: 1, duration: 0.50, ease: "power2.in" }, 5.50);

    window.__timelines = window.__timelines || {};
    window.__timelines["branding-scene"] = tl;
  </script>
</template>
`;

  const bugHtml = `<template>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    #root {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: transparent;
      font-family: 'Space Grotesk', sans-serif;
    }
    #top-bug-clip {
      position: absolute;
      top: 72px;
      left: 108px;
      right: 108px;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }
    #top-bug-inner {
      display: flex;
      align-items: center;
      gap: 14px;
      opacity: 0;
    }
    .bug-text {
      font-weight: 700;
      font-size: 32px;
      letter-spacing: 0.12em;
      color: #F4F1EA;
      line-height: 1;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.68);
    }
  </style>
  <div id="root" data-composition-id="top-bug" data-width="1080" data-height="1920">
    <div id="top-bug-clip" class="clip" data-start="0" data-duration="2.25" data-track-index="1">
      <div id="top-bug-inner">
        <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
          <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.2" />
          <ellipse cx="17" cy="17" rx="6" ry="13" stroke="#F4F1EA" stroke-width="1.6" />
          <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.6" />
        </svg>
        <span class="bug-text" data-var-text="brand-name">GEOVERUM</span>
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#top-bug-inner",
      { opacity: 0, scale: 0.96 },
      { opacity: 0.86, scale: 1.0, duration: 0.20, ease: "expo.out" },
      0.10
    );
    tl.to("#top-bug-inner", { opacity: 0, duration: 0.14, ease: "power2.in" }, 2.08);
    window.__timelines = window.__timelines || {};
    window.__timelines["top-bug"] = tl;
  </script>
</template>
`;

  writeFileSync(join(STUDY_DIR, "index.html"), indexHtml, "utf8");
  writeFileSync(join(COMP_DIR, "branding-scene.html"), sceneHtml, "utf8");
  writeFileSync(join(COMP_DIR, "top-bug.html"), bugHtml, "utf8");
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });
  mkdirSync(COMP_DIR, { recursive: true });
  mkdirSync(RENDERS_DIR, { recursive: true });

  const tileServer = await startTileServer(8772, "127.0.0.1");
  const tileBaseUrl = "http://127.0.0.1:8772";
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
    console.log("[branding] Baking Sulawesi outro pullback plate...");
    await bakeSulawesiPullbackPlate(browser, tileBaseUrl);
    writeHyperframesProject();
    await validateStudyProject(STUDY_DIR, "branding");

    const { server: assetServer, baseUrl: assetBaseUrl } = await startStudyAssetServer(STUDY_DIR);
    try {
      const framesDir = join(RENDERS_DIR, "frames-branding");
      console.log("[branding] Rendering 180-frame (6.0s @ 30fps) HyperFrames timeline...");
      await renderProjectFrames({
        browser,
        baseUrl: assetBaseUrl,
        studyDir: STUDY_DIR,
        totalFrames: 180,
        fps: 30,
        framesDir,
      });

      const outMp4 = join(RENDERS_DIR, "branding_1080x1920.mp4");
      const sheetJpg = join(RENDERS_DIR, "branding_sheet.jpg");
      encodeDeliverableAndSheet({
        framesDir,
        outMp4,
        sheetJpg,
        fps: 30,
        selectFrames: [15, 45, 68, 90, 140, 174],
      });
      console.log(`[branding] Complete -> ${outMp4}`);
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
