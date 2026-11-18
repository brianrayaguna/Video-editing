#!/usr/bin/env node
/**
 * Bake 4 multi-scale 3D MapLibre satellite shots (globe dive, Gulf of Tomini 3D,
 * Palu-Koro rift pass, and Copernicus Sentinel-2 z11 Maros-Pangkep karst aerial relief),
 * pre-render optical transition assets (6-frame radial zoom-blur whip sequence + warm
 * amber-cream optical light-leak plate with zero runtime CSS blur), generate the
 * HyperFrames project, validate via `@hyperframes/lint`, and render the 300-frame
 * (10.0s @ 30fps, 1080x1920) deliverable + QA sheets.
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { startTileServer } from "../../../tools/geo-assets/serve_tiles.mjs";
import {
  buildBroadcastLayerHtml,
  encodeDeliverableAndSheet,
  puppeteer,
  REPO_ROOT,
  resolveChrome,
  sharp,
  startStudyAssetServer,
  validateStudyProject,
} from "../../../tools/geo-assets/study_runner.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const SEQ_DIR = join(ASSETS_DIR, "seq");
const COMP_DIR = join(STUDY_DIR, "compositions");
const RENDERS_DIR = join(STUDY_DIR, "renders");

const TOTAL_FRAMES = 300;
const FPS = 30;

function makeCubicBezier(x1, y1, x2, y2) {
  function sx(t) { return ((1 - 3 * x2 + 3 * x1) * t ** 3) + ((3 * x2 - 6 * x1) * t ** 2) + (3 * x1 * t); }
  function sy(t) { return ((1 - 3 * y2 + 3 * y1) * t ** 3) + ((3 * y2 - 6 * y1) * t ** 2) + (3 * y1 * t); }
  function dx(t) { return (3 * (1 - 3 * x2 + 3 * x1) * t ** 2) + (2 * (3 * x2 - 6 * x1) * t) + (3 * x1); }
  return (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const err = sx(t) - x;
      if (Math.abs(err) < 1e-6) return sy(t);
      const d = dx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= err / d;
    }
    return sy(t);
  };
}

const EASE_IN_OUT = makeCubicBezier(0.77, 0.0, 0.175, 1.0);
const EASE_POWER3_IN = (t) => t * t * t;

/** Compute camera parameters for a frame index inside each continuous shot sequence. */
function shotCameraAt(shotId, localIdx, shotLen) {
  const u = shotLen <= 1 ? 1 : localIdx / (shotLen - 1);
  if (shotId === "shot-a") {
    // Globe dive into Sulawesi accelerating into a rapid inward pull across f58..f63
    const baseT = EASE_IN_OUT(Math.min(1, u / 0.88));
    const whipBoost = u > 0.88 ? EASE_POWER3_IN((u - 0.88) / 0.12) * 0.95 : 0;
    return {
      projection: "globe",
      center: [108.0 + (121.25 - 108.0) * baseT, 8.0 + (-1.55 - 8.0) * baseT],
      zoom: 1.85 + (6.10 - 1.85) * baseT + whipBoost,
      pitch: 8 * baseT,
      bearing: -4 * baseT,
    };
  }
  if (shotId === "shot-b") {
    // 3D Gulf of Tomini coastline tilt glide (f064..f147, 84 frames)
    return {
      projection: "mercator",
      center: [120.88 + 0.24 * u, -0.24 - 0.10 * u],
      zoom: 7.45 + 0.48 * u,
      pitch: 36 + 4 * u,
      bearing: -8 + 4 * u,
    };
  }
  if (shotId === "shot-c") {
    // Palu-Koro tectonic rift 3D fly-over (f148..f209, 62 frames including crossfade tail)
    return {
      projection: "mercator",
      center: [119.95 - 0.10 * u, -1.18 + 0.34 * u],
      zoom: 8.45 + 0.65 * u,
      pitch: 40 + 4 * u,
      bearing: -14 + 5 * u,
    };
  }
  // shot-d: Raw Copernicus Sentinel-2 cloudless z11 aerial pass over Maros-Pangkep karst (f191..f299, 109 frames)
  return {
    projection: "mercator",
    center: [119.63 + 0.10 * u, -4.97 + 0.10 * u],
    zoom: 10.65 + 0.45 * u,
    pitch: 48 + 4 * u,
    bearing: 16 + 8 * u,
  };
}

/** Synthesize an energy-preserving optical radial zoom-blur frame from scaled concentric taps. */
async function preRenderRadialZoomBlur(srcJpg, outJpg, strength) {
  const W = 1080;
  const H = 1920;
  const taps = 9;
  const nBytes = W * H * 3;
  const acc = new Float32Array(nBytes);
  let totalWeight = 0;

  for (let m = 0; m < taps; m++) {
    const f = m / (taps - 1);
    const cropScale = 1 + strength * 0.34 * f;
    const cropW = Math.max(240, Math.round(W / cropScale));
    const cropH = Math.max(420, Math.round(H / cropScale));
    const left = Math.round((W - cropW) / 2);
    const top = Math.round((H - cropH) / 2);
    const w = 1.0 - f * 0.62;
    totalWeight += w;

    const buf =
      m === 0
        ? await sharp(srcJpg).raw().toBuffer()
        : await sharp(srcJpg)
            .extract({ left, top, width: cropW, height: cropH })
            .resize(W, H, { kernel: "cubic" })
            .raw()
            .toBuffer();

    for (let i = 0; i < nBytes; i++) {
      acc[i] += buf[i] * w;
    }
  }

  const outBuf = Buffer.allocUnsafe(nBytes);
  const invW = 1 / totalWeight;
  for (let i = 0; i < nBytes; i++) {
    outBuf[i] = Math.min(255, Math.max(0, Math.round(acc[i] * invW)));
  }

  await sharp(outBuf, { raw: { width: W, height: H, channels: 3 } })
    .jpeg({ quality: 92 })
    .toFile(outJpg);
}

/** Pre-render a 1080x1920 warm solar amber-cream optical light-leak plate (zero purple/magenta). */
async function preRenderWarmLightLeak(outPng) {
  const W = 1080;
  const H = 1920;
  const buf = Buffer.alloc(W * H * 4);
  for (let y = 0; y < H; y++) {
    const ny = y / H;
    for (let x = 0; x < W; x++) {
      const nx = x / W;
      // Primary solar flare bloom from upper-right edge sweeping across diagonal axis
      const d1 = Math.hypot((nx - 0.84) * 1.15, (ny - 0.16) * 0.85);
      const lobe1 = Math.exp(-d1 * d1 * 4.4);
      // Secondary diagonal halation wash from lower-left corner
      const d2 = Math.hypot((nx - 0.14) * 1.05, (ny - 0.78) * 0.90);
      const lobe2 = Math.exp(-d2 * d2 * 3.8) * 0.78;
      // Warm streak band connecting both flares
      const diag = Math.exp(-Math.pow((nx * 0.75 + ny * 0.65 - 0.72), 2) * 16.0) * 0.45;

      const intensity = Math.min(1.0, lobe1 * 0.95 + lobe2 * 0.72 + diag * 0.55);
      // Warm amber (#F5C542) -> burnt solar orange (#E67E22) -> warm cream (#FFFDF8)
      const r = Math.min(255, Math.round(238 + 17 * intensity));
      const g = Math.min(255, Math.round(132 + 114 * Math.pow(intensity, 1.35)));
      const b = Math.min(255, Math.round(38 + 204 * Math.pow(intensity, 2.3)));
      const a = Math.min(255, Math.round(255 * Math.pow(intensity, 0.85)));

      const off = (y * W + x) * 4;
      buf[off] = r;
      buf[off + 1] = g;
      buf[off + 2] = b;
      buf[off + 3] = a;
    }
  }
  await sharp(buf, { raw: { width: W, height: H, channels: 4 } }).png().toFile(outPng);
}

function encodeSeqToMp4(pattern, outMp4, fps = 30) {
  const ff = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-framerate",
      String(fps),
      "-i",
      pattern,
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-r",
      String(fps),
      "-color_primaries",
      "bt709",
      "-color_trc",
      "bt709",
      "-colorspace",
      "bt709",
      "-crf",
      "16",
      "-g",
      "1",
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ff.status !== 0) {
    throw new Error(`FFmpeg sequence encode failed for ${outMp4}`);
  }
}

async function bakeAllShotSequences(browser, tileBaseUrl) {
  mkdirSync(SEQ_DIR, { recursive: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });

  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stars = Array.from({ length: 220 }, () => {
    const x = (rnd() * 1080).toFixed(0);
    const y = (rnd() * 1920).toFixed(0);
    const r = (rnd() * 1.3 + 0.35).toFixed(2);
    const a = (rnd() * 0.55 + 0.18).toFixed(2);
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="#F4F1EA" opacity="${a}"/>`;
  }).join("");

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${tileBaseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${tileBaseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    * { margin: 0; padding: 0; }
    html, body { width: 1080px; height: 1920px; overflow: hidden; background: radial-gradient(ellipse at 50% 46%, #061D28 0%, #03161F 56%, #01090E 100%); }
    #stars { position: absolute; inset: 0; }
    #map { position: absolute; inset: 0; width: 1080px; height: 1920px; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <svg id="stars" width="1080" height="1920">${stars}</svg>
  <div id="map"></div>
  <script>
    const BASE_URL = ${JSON.stringify(tileBaseUrl)};
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: "globe" },
        sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 4.5, 0.85, 6.0, 0] },
        sources: { sat: { type: "raster", tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"], tileSize: 256, maxzoom: 11 } },
        layers: [{ id: "sat", type: "raster", source: "sat" }]
      },
      center: [108, 8], zoom: 1.85, interactive: false, attributionControl: false, fadeDuration: 0,
      preserveDrawingBuffer: true, canvasContextAttributes: { alpha: true, preserveDrawingBuffer: true }
    });
    window.__ready = new Promise((res) => { if (map.loaded()) res(); else map.on("load", res); });
    window.__applyCam = async function(c) {
      document.getElementById("stars").style.display = c.projection === "globe" ? "block" : "none";
      map.setProjection({ type: c.projection });
      map.jumpTo({ center: c.center, zoom: c.zoom, pitch: c.pitch, bearing: c.bearing });
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
    };
  </script>
</body>
</html>`;

  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => window.__ready);

  const specs = [
    { id: "shot-a", count: 64 },
    { id: "shot-b", count: 84 },
    { id: "shot-c", count: 62 },
    { id: "shot-d", count: 109 },
  ];

  for (const s of specs) {
    const dir = join(SEQ_DIR, s.id);
    mkdirSync(dir, { recursive: true });
    const lastExpected = join(dir, `f${String(s.count - 1).padStart(4, "0")}.jpg`);
    if (process.env.REBAKE !== "1" && existsSync(lastExpected)) {
      console.log(`  [transitions] Reusing cached ${s.id} (${s.count} frames)`);
      continue;
    }
    for (let i = 0; i < s.count; i++) {
      const cam = shotCameraAt(s.id, i, s.count);
      await page.evaluate((c) => window.__applyCam(c), cam);
      await page.screenshot({
        path: join(dir, `f${String(i).padStart(4, "0")}.jpg`),
        type: "jpeg",
        quality: 92,
        clip: { x: 0, y: 0, width: 1080, height: 1920 },
      });
    }
    console.log(`  [transitions] Rendered ${s.id} (${s.count} frames)`);
  }
  await page.close();

  // Preserve unblurred whip source frames so re-runs stay strictly idempotent
  const rawBackupDir = join(SEQ_DIR, ".raw-whip");
  mkdirSync(rawBackupDir, { recursive: true });
  console.log("[transitions] Pre-rendering 6-frame radial zoom-blur whip plates (zero runtime CSS blur)...");
  for (let k = 0; k < 6; k++) {
    const fIdx = 58 + k;
    const fn = `f${String(fIdx).padStart(4, "0")}.jpg`;
    const activeP = join(SEQ_DIR, "shot-a", fn);
    const bakP = join(rawBackupDir, `a_${fn}`);
    if (!existsSync(bakP)) copyFileSync(activeP, bakP);
    const strength = (k + 1) / 6;
    await preRenderRadialZoomBlur(bakP, activeP, strength);
  }
  const shotB0 = join(SEQ_DIR, "shot-b", "f0000.jpg");
  const shotB0Bak = join(rawBackupDir, "b_f0000.jpg");
  if (!existsSync(shotB0Bak)) copyFileSync(shotB0, shotB0Bak);
  await preRenderRadialZoomBlur(shotB0Bak, shotB0, 0.24);

  for (const s of specs) {
    encodeSeqToMp4(join(SEQ_DIR, s.id, "f%04d.jpg"), join(ASSETS_DIR, `${s.id}.mp4`), FPS);
    console.log(`  [transitions] Encoded assets/${s.id}.mp4`);
  }

  // Representative poster stills for standalone HyperFrames inspection
  await sharp(join(SEQ_DIR, "shot-a", "f0030.jpg")).toFile(join(ASSETS_DIR, "shot-a-poster.jpg"));
  await sharp(join(SEQ_DIR, "shot-b", "f0030.jpg")).toFile(join(ASSETS_DIR, "shot-b-poster.jpg"));
  await sharp(join(SEQ_DIR, "shot-c", "f0020.jpg")).toFile(join(ASSETS_DIR, "shot-c-poster.jpg"));
  await sharp(join(SEQ_DIR, "shot-d", "f0050.jpg")).toFile(join(ASSETS_DIR, "shot-d-poster.jpg"));

  console.log("[transitions] Pre-rendering warm amber-cream optical light-leak plate...");
  await preRenderWarmLightLeak(join(ASSETS_DIR, "light-leak-amber.png"));
}

function writeHyperframesProject() {
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
  <title>Geoverum Transitions — Transitions &amp; Aerial Relief</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('assets/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #03161F;
      font-family: 'Space Grotesk', sans-serif;
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
    <video id="shot-a-vid" class="clip" src="assets/shot-a.mp4" data-start="0" data-duration="2.133" data-media-start="0" data-track-index="1" muted playsinline style="position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;"></video>
    <video id="shot-b-vid" class="clip" src="assets/shot-b.mp4" data-start="2.133" data-duration="2.800" data-media-start="0" data-track-index="1" muted playsinline style="position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;"></video>
    <video id="shot-c-vid" class="clip" src="assets/shot-c.mp4" data-start="4.933" data-duration="1.767" data-media-start="0" data-track-index="1" muted playsinline style="position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;"></video>
    <video id="shot-d-vid" class="clip" src="assets/shot-d.mp4" data-start="6.367" data-duration="3.633" data-media-start="0" data-track-index="2" muted playsinline style="position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;"></video>

    <div
      id="transitions-overlay"
      data-composition-id="transitions-overlay"
      data-composition-src="compositions/transitions-overlay.html"
      data-start="0"
      data-duration="10"
      data-track-index="3"
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
      data-track-index="4"
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

  const overlayHtml = `<template>
  <style>
    #root {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: transparent;
      pointer-events: none;
    }
    #leak-layer {
      position: absolute;
      inset: -120px;
      width: 1320px;
      height: 2160px;
      transform-origin: 540px 960px;
      mix-blend-mode: screen;
      opacity: 0;
    }
    #leak-layer img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    #flash-plate {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      background: #FFF8EC;
      opacity: 0;
    }
    #dip-out-plate {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      background: #03161F;
      opacity: 0;
    }
  </style>
  <div id="root" data-composition-id="transitions-overlay" data-width="1080" data-height="1920">
    <div id="leak-layer" class="clip" data-start="4.65" data-duration="0.75" data-track-index="1">
      <img src="assets/light-leak-amber.png" alt="Warm optical light leak" />
    </div>
    <div id="flash-plate" class="clip" data-start="4.80" data-duration="0.35" data-track-index="2"></div>
    <div id="dip-out-plate" class="clip" data-start="9.50" data-duration="0.50" data-track-index="3"></div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.set("#leak-layer, #flash-plate, #dip-out-plate", { opacity: 0 }, 0);

    // Pre-rendered optical amber-cream light leak blooming cleanly into peak flash at f148 (4.933s)
    tl.fromTo(
      "#leak-layer",
      { opacity: 0, scale: 1.18, x: -70, y: 50 },
      { opacity: 0.94, scale: 1.0, x: 0, y: 0, duration: 0.22, ease: "power2.in" },
      4.71
    );
    tl.to(
      "#leak-layer",
      { opacity: 0, scale: 0.96, x: 35, y: -30, duration: 0.42, ease: "expo.out" },
      4.95
    );

    // Warm cream exposure flash across f147..f151
    tl.fromTo(
      "#flash-plate",
      { opacity: 0 },
      { opacity: 0.90, duration: 0.08, ease: "power2.in" },
      4.85
    );
    tl.to(
      "#flash-plate",
      { opacity: 0, duration: 0.22, ease: "expo.out" },
      4.94
    );

    // Clean documentary dip-out over final 15 frames (9.50s..10.00s)
    tl.to("#dip-out-plate", { opacity: 1, duration: 0.50, ease: "power2.in" }, 9.50);

    window.__timelines = window.__timelines || {};
    window.__timelines["transitions-overlay"] = tl;
  </script>
</template>
`;

  writeFileSync(join(STUDY_DIR, "index.html"), indexHtml, "utf8");
  writeFileSync(join(COMP_DIR, "transitions-overlay.html"), overlayHtml, "utf8");
  writeFileSync(join(COMP_DIR, "broadcast-layer.html"), buildBroadcastLayerHtml(10, 9.50), "utf8");
}

async function renderCompositeTimeline(browser, baseUrl) {
  const framesDir = join(RENDERS_DIR, "frames-transitions");
  mkdirSync(framesDir, { recursive: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });

  const gsapBytes = readFileSync(join(REPO_ROOT, "assets/geo/vendor/gsap.min.js"));
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const u = req.url();
    if (u.includes("gsap") && u.endsWith(".js")) {
      req.respond({ status: 200, contentType: "application/javascript", body: gsapBytes });
      return;
    }
    req.continue();
  });

  const ovRaw = readFileSync(join(COMP_DIR, "transitions-overlay.html"), "utf8");
  const ovInner = (ovRaw.match(/<template>([\s\S]*?)<\/template>/i) || [])[1];
  const ovStyled = ovInner.replace(/#root\b/g, '[data-composition-id="transitions-overlay"]').replace(/\bid=["']root["']/i, 'id="host-transitions-overlay"');

  const bRaw = readFileSync(join(COMP_DIR, "broadcast-layer.html"), "utf8");
  const bInner = (bRaw.match(/<template>([\s\S]*?)<\/template>/i) || [])[1];
  const bStyled = bInner.replace(/#root\b/g, '[data-composition-id="broadcast-layer"]').replace(/\bid=["']root["']/i, 'id="host-broadcast-layer"');

  const extractScript = (html) => (html.match(/<script\b[^>]*>([\s\S]*?)<\/script>/i) || [])[1] || "";
  const stripScripts = (html) => html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");

  const hostHtml = `<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <base href="${baseUrl}/">
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }
    #stage-wrap { position: relative; width: 1080px; height: 1920px; overflow: hidden; background: #03161F; }
    .shot-layer { position: absolute; inset: 0; width: 1080px; height: 1920px; overflow: hidden; transform-origin: 540px 960px; display: none; }
    .shot-layer img { width: 100%; height: 100%; object-fit: cover; display: block; }
  </style>
</head>
<body>
  <div id="stage-wrap">
    <div id="layer-main" class="shot-layer" style="z-index: 1;"><img id="img-main" src="assets/shot-a-poster.jpg" /></div>
    <div id="layer-cross" class="shot-layer" style="z-index: 2;"><img id="img-cross" src="assets/shot-d-poster.jpg" /></div>
    <div style="position: absolute; inset: 0; z-index: 3;">${stripScripts(ovStyled)}</div>
    <div style="position: absolute; inset: 0; z-index: 4;">${stripScripts(bStyled)}</div>
  </div>
  <script>
    window.__timelines = {};
    (() => { ${extractScript(ovInner)} })();
    (() => { ${extractScript(bInner)} })();

    function easeOutExpo(x) { return x >= 1 ? 1 : 1 - Math.pow(2, -10 * x); }
    function easeInOutQuad(x) { return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; }

    window.__setFrameState = async function(i) {
      const tSec = i / ${FPS};
      const layerMain = document.getElementById("layer-main");
      const imgMain = document.getElementById("img-main");
      const layerCross = document.getElementById("layer-cross");
      const imgCross = document.getElementById("img-cross");

      let mainSrc = "";
      let mainScale = 1.0;
      let crossSrc = "";
      let crossOpacity = 0.0;

      if (i < 64) {
        mainSrc = "assets/seq/shot-a/f" + String(i).padStart(4, "0") + ".jpg";
        if (i >= 58) {
          // Subtle inward acceleration whip scaling alongside radial streak frames
          const w = (i - 57) / 6;
          mainScale = 1.0 + 0.14 * w * w;
        }
      } else if (i < 148) {
        const local = i - 64;
        mainSrc = "assets/seq/shot-b/f" + String(local).padStart(4, "0") + ".jpg";
        if (local < 7) {
          // Incoming whip momentum settle (scale 1.07 -> 1.00 over 0.20s)
          const u = easeOutExpo(local / 6);
          mainScale = 1.07 - 0.07 * u;
        }
      } else {
        const cLocal = Math.min(61, i - 148);
        mainSrc = "assets/seq/shot-c/f" + String(cLocal).padStart(4, "0") + ".jpg";
        if (i >= 191) {
          const dLocal = i - 191;
          crossSrc = "assets/seq/shot-d/f" + String(dLocal).padStart(4, "0") + ".jpg";
          if (i <= 201) {
            crossOpacity = easeInOutQuad((i - 191) / 10);
          } else {
            crossOpacity = 1.0;
          }
        }
      }

      if (i <= 201) {
        layerMain.style.display = "block";
        layerMain.style.transform = "scale(" + mainScale.toFixed(4) + ")";
        if (imgMain.getAttribute("src") !== mainSrc) {
          imgMain.setAttribute("src", mainSrc);
          await imgMain.decode().catch(() => {});
        }
      } else {
        layerMain.style.display = "none";
      }

      if (crossSrc && crossOpacity > 0) {
        layerCross.style.display = "block";
        layerCross.style.opacity = crossOpacity.toFixed(4);
        if (imgCross.getAttribute("src") !== crossSrc) {
          imgCross.setAttribute("src", crossSrc);
          await imgCross.decode().catch(() => {});
        }
      } else {
        layerCross.style.display = "none";
      }

      window.__timelines["transitions-overlay"].seek(tSec, false);
      window.__timelines["broadcast-layer"].seek(tSec, false);
    };
  </script>
</body>
</html>`;

  await page.setContent(hostHtml, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);

  const t0 = Date.now();
  for (let i = 0; i < TOTAL_FRAMES; i++) {
    await page.evaluate((idx) => window.__setFrameState(idx), i);
    await page.screenshot({
      path: join(framesDir, `f${String(i).padStart(4, "0")}.png`),
      clip: { x: 0, y: 0, width: 1080, height: 1920 },
      optimizeForSpeed: true,
    });
    if (i % 60 === 0 || i === TOTAL_FRAMES - 1) {
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      console.log(`  [transitions] rendered frame ${i + 1}/${TOTAL_FRAMES} (${elapsed}s)`);
    }
  }
  await page.close();

  const outMp4 = join(RENDERS_DIR, "transitions_1080x1920.mp4");
  const sheetJpg = join(RENDERS_DIR, "transitions_sheet.jpg");
  encodeDeliverableAndSheet({
    framesDir,
    outMp4,
    sheetJpg,
    fps: FPS,
    selectFrames: [30, 61, 65, 146, 148, 151, 196, 250, 294],
    tileCols: 3,
    tileRows: 3,
    scaleW: 360,
    scaleH: 640,
    cleanupFrames: true,
  });

  // Also extract a tight 10-frame transition strip across the zoom-blur whip (f59..f66) + flash peak (f146..f150)
  const stripJpg = join(RENDERS_DIR, "transitions_seams_strip.jpg");
  const seamFrames = [59, 61, 62, 63, 64, 65, 145, 147, 148, 150];
  const sel = seamFrames.map((n) => `eq(n\\,${n})`).join("+");
  spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      outMp4,
      "-vf",
      `drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text='f%{n}':x=16:y=16:fontsize=42:fontcolor=yellow:box=1:boxcolor=black@0.75,select='${sel}',scale=320:568,tile=5x2`,
      "-fps_mode",
      "passthrough",
      "-frames:v",
      "1",
      "-update",
      "1",
      stripJpg,
    ],
    { stdio: "inherit" }
  );
  console.log(`[transitions] Complete -> ${outMp4}`);
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });
  mkdirSync(COMP_DIR, { recursive: true });
  mkdirSync(RENDERS_DIR, { recursive: true });

  const tileServer = await startTileServer(8770, "127.0.0.1");
  const tileBaseUrl = "http://127.0.0.1:8770";
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
    console.log("[transitions] Baking 4 MapLibre camera sequences and optical transitions...");
    await bakeAllShotSequences(browser, tileBaseUrl);
    writeHyperframesProject();
    await validateStudyProject(STUDY_DIR, "transitions");

    const { server: assetServer, baseUrl: assetBaseUrl } = await startStudyAssetServer(STUDY_DIR);
    try {
      await renderCompositeTimeline(browser, assetBaseUrl);
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
