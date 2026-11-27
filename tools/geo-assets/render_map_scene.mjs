#!/usr/bin/env node
/**
 * Declarative Camera-Synced World-Space Map Scene Engine (`vedit geo bake-scene`).
 *
 * Adheres to the `tools/geo-assets` capture contract:
 *  - Offline MapLibre GL JS serving graded tiles from `serve_tiles.mjs`
 *  - CDP JPEG q=92 piped directly into FFmpeg `image2pipe` MJPEG (all-intra bt709)
 *  - Executable Chrome check (`X_OK`), Darwin Metal ANGLE on macOS
 *  - Scale-coupled Mercator camera physics + optional optical sub-frame shutter motion blur
 *  - Offscreen-mask exterior polygon dissolve (zero internal administrative seams)
 *  - Multi-ring luminous text glow and 3-layer glowing routes
 */

import {
  accessSync,
  constants,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import {
  createCdpScreenshotter,
  getChromeArgs,
  spawnFramePipeEncoder,
} from "./fast_capture.mjs";
import { coverageReport, startTileServer } from "./serve_tiles.mjs";
import { cutBlurAmount, shutterSubframeSchedule } from "./map_draw_math.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
// Pure geometry helpers shared with Node tests; inlined into the page with `export` removed.
const DRAW_MATH_SRC = readFileSync(join(__dirname, "map_draw_math.mjs"), "utf8").replace(/^export\s+/gm, "");
const FLAG_RASTER_WIDTH = 1600;
const puppeteer = require("puppeteer-core");
const sharp = require("sharp");

function isExecutable(p) {
  try {
    accessSync(p, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function resolveChrome() {
  if (process.env.CHROME && isExecutable(process.env.CHROME)) return process.env.CHROME;
  const exe = process.platform === "win32" ? "chrome-headless-shell.exe" : "chrome-headless-shell";
  const base = join(homedir(), ".cache", "puppeteer", "chrome-headless-shell");
  if (existsSync(base)) {
    for (const v of readdirSync(base).sort().reverse()) {
      try {
        for (const inner of readdirSync(join(base, v))) {
          const bin = join(base, v, inner, exe);
          if (isExecutable(bin)) return bin;
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
    if (isExecutable(c)) return c;
  }
  throw new Error("Executable Chrome / chrome-headless-shell not found.");
}

function parseArgs(argv) {
  const args = {};
  const onlyActs = [];
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith("--")) continue;
    const name = k.slice(2);
    const val = i + 1 < argv.length && !argv[i + 1].startsWith("--") ? argv[++i] : true;
    if (name === "only-act") {
      if (typeof val === "string") {
        for (const part of val.split(",")) {
          const trimmed = part.trim();
          if (trimmed) onlyActs.push(trimmed);
        }
      }
      continue;
    }
    args[name] = val;
  }
  if (onlyActs.length > 0) args["only-act"] = onlyActs;
  return args;
}

const __FONT_KNOWN_FAMILIES = Object.freeze({
  archivoblack: "Archivo Black",
  unbounded: "Unbounded",
  bebasneue: "Bebas Neue",
  oswald: "Oswald",
  anton: "Anton",
  leaguegothic: "League Gothic",
  syne: "Syne",
  barlowcondensed: "Barlow Condensed",
  cinzel: "Cinzel",
  rubik: "Rubik",
  spacegrotesk: "Space Grotesk",
  inter: "Inter",
  montserrat: "Montserrat",
  plusjakartasans: "Plus Jakarta Sans",
  roboto: "Roboto",
  poppins: "Poppins",
  outfit: "Outfit",
  dmsans: "DM Sans",
  manrope: "Manrope",
  opensans: "Open Sans",
  lato: "Lato",
  nunito: "Nunito",
  sora: "Sora",
  worksans: "Work Sans",
  ebgaramond: "EB Garamond",
  playfairdisplay: "Playfair Display",
  lora: "Lora",
  merriweather: "Merriweather",
  librebaskerville: "Libre Baskerville",
  instrumentserif: "Instrument Serif",
  spacemono: "Space Mono",
  ibmplexmono: "IBM Plex Mono",
  jetbrainsmono: "JetBrains Mono",
  sourcecodepro: "Source Code Pro",
  courierprime: "Courier Prime",
  caveat: "Caveat",
  permanentmarker: "Permanent Marker",
  patrickhand: "Patrick Hand",
});

function readTtfWeightAxis(filePath) {
  try {
    const buf = readFileSync(filePath);
    if (buf.length < 12) return null;
    const numTables = buf.readUInt16BE(4);
    let fvarOff = 0;
    let os2Off = 0;
    for (let i = 0; i < numTables; i++) {
      const rec = 12 + i * 16;
      if (rec + 16 > buf.length) break;
      const tag = buf.toString("ascii", rec, rec + 4);
      if (tag === "fvar") fvarOff = buf.readUInt32BE(rec + 8);
      else if (tag === "OS/2") os2Off = buf.readUInt32BE(rec + 8);
    }
    if (fvarOff && fvarOff + 12 <= buf.length) {
      const axesOff = buf.readUInt16BE(fvarOff + 4);
      const axisCount = buf.readUInt16BE(fvarOff + 8);
      const axisSize = buf.readUInt16BE(fvarOff + 10);
      for (let i = 0; i < axisCount; i++) {
        const off = fvarOff + axesOff + i * axisSize;
        if (off + 16 > buf.length) break;
        if (buf.toString("ascii", off, off + 4) === "wght") {
          const minW = Math.max(1, Math.min(1000, Math.round(buf.readInt32BE(off + 4) / 65536)));
          const maxW = Math.max(minW, Math.min(1000, Math.round(buf.readInt32BE(off + 12) / 65536)));
          return { isVariable: true, minWeight: minW, maxWeight: maxW };
        }
      }
    }
    if (os2Off && os2Off + 6 <= buf.length) {
      const w = Math.max(100, Math.min(900, buf.readUInt16BE(os2Off + 4)));
      return { isVariable: false, minWeight: w, maxWeight: w };
    }
    return null;
  } catch {
    return null;
  }
}

function buildDynamicFontFaceCss(baseUrl) {
  const fontsDir = join(REPO_ROOT, "assets", "geo", "fonts");
  const faces = [];
  if (existsSync(fontsDir)) {
    const files = readdirSync(fontsDir)
      .filter((fn) => /\.(?:ttf|otf)$/i.test(fn))
      .sort();
    for (const fn of files) {
      const fullPath = join(fontsDir, fn);
      const base = fn.replace(/\.(?:ttf|otf)$/i, "");
      const style = /italic/i.test(base) ? "italic" : "normal";
      const stem = base
        .replace(
          /[-_](Italic[-_])?(Variable|Regular|ExtraLight|Light|Medium|SemiBold|Bold|ExtraBold|Black|Italic)+$/i,
          ""
        )
        .replace(/[-_](BoldItalic|BlackItalic|Italic)$/i, "");
      const compact = stem.toLowerCase().replace(/[^a-z0-9]/g, "");
      const family =
        __FONT_KNOWN_FAMILIES[compact] ||
        stem.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim();
      if (!family) continue;
      const axis = readTtfWeightAxis(fullPath);
      const isVariable = Boolean(axis?.isVariable || /variable/i.test(base));
      let weight = "400";
      if (axis?.isVariable) {
        weight = `${axis.minWeight} ${axis.maxWeight}`;
      } else if (/variable/i.test(base)) {
        weight = "100 900";
      } else if (/(?:^|[-_])(extra[-_]?bold|ultrabold)(?:italic)?$/i.test(base)) {
        weight = "800";
      } else if (/(?:^|[-_])(semi[-_]?bold|demibold)(?:italic)?$/i.test(base)) {
        weight = "600";
      } else if (/(?:^|[-_])black(?:italic)?$/i.test(base)) {
        weight = "900";
      } else if (compact === "archivoblack") {
        weight = "400 900";
      } else if (/(?:^|[-_])bold(?:italic)?$/i.test(base)) {
        weight = "700";
      } else if (/(?:^|[-_])medium(?:italic)?$/i.test(base)) {
        weight = "500";
      } else if (/(?:^|[-_])(extra[-_]?light|ultralight)(?:italic)?$/i.test(base)) {
        weight = "200";
      } else if (/(?:^|[-_])light(?:italic)?$/i.test(base)) {
        weight = "300";
      } else if (axis && !axis.isVariable) {
        weight = String(axis.minWeight);
      }
      const fmt = fn.toLowerCase().endsWith(".otf") ? "opentype" : "truetype";
      faces.push({ fn, family, weight, style, fmt, isVariable });
    }
  }
  // Deduplicate static vs variable collisions per (family, style) so Chromium resolves exact fvar axes cleanly.
  const varKeys = new Set(faces.filter((f) => f.isVariable).map((f) => `${f.family.toLowerCase()}::${f.style}`));
  const deduped = faces.filter((f) => f.isVariable || !varKeys.has(`${f.family.toLowerCase()}::${f.style}`));
  if (deduped.length > 0) {
    const rules = deduped.map(
      (f) =>
        `    @font-face { font-family: "${f.family}"; src: url("${baseUrl}/fonts/${encodeURIComponent(f.fn)}") format("${f.fmt}"); font-weight: ${f.weight}; font-style: ${f.style}; font-display: block; }`
    );
    rules.push("    :root, body { font-synthesis: none; font-optical-sizing: auto; }");
    return rules.join("\n");
  }
  return `    @font-face { font-family: "Barlow Condensed"; src: url("${baseUrl}/fonts/BarlowCondensed-Bold.ttf") format("truetype"); font-weight: 700; font-display: block; }
    @font-face { font-family: "Barlow Condensed"; src: url("${baseUrl}/fonts/BarlowCondensed-ExtraBold.ttf") format("truetype"); font-weight: 800; font-display: block; }
    @font-face { font-family: "Inter"; src: url("${baseUrl}/fonts/Inter-Variable.ttf") format("truetype"); font-weight: 100 900; font-display: block; }
    @font-face { font-family: "Rubik"; src: url("${baseUrl}/fonts/Rubik-Variable.ttf") format("truetype"); font-weight: 300 900; font-display: block; }
    @font-face { font-family: "Lora"; src: url("${baseUrl}/fonts/Lora-Italic-Variable.ttf") format("truetype"); font-weight: 400 700; font-style: italic; font-display: block; }
    @font-face { font-family: "IBM Plex Mono"; src: url("${baseUrl}/fonts/IBMPlexMono-Bold.ttf") format("truetype"); font-weight: 700; font-display: block; }
    :root, body { font-synthesis: none; font-optical-sizing: auto; }`;
}

function buildMapSceneHtml(baseUrl, width, height, vectorsJson, mapOpts = {}) {
  const sourceMode = mapOpts.tile_source || "hybrid";
  const tileRoute =
    sourceMode === "project"
      ? "/tiles_project/{z}/{x}/{y}.jpg"
      : sourceMode === "project_graded"
        ? "/tiles_project_graded/{z}/{x}/{y}.jpg"
        : sourceMode === "realistic"
          ? "/tiles_hq/{z}/{x}/{y}.jpg"
          : sourceMode === "graded"
            ? "/tiles/{z}/{x}/{y}.jpg"
            : "/tiles_hybrid/{z}/{x}/{y}.jpg";
  const satMaxZoom = 18;
  const terrain3d = Boolean(mapOpts.terrain_3d);
  const terrainExag = Number(mapOpts.terrain_exaggeration ?? 2.4);
  const demMaxZoom = Number(mapOpts.dem_maxzoom ?? 10);
  const has3d = Boolean(mapOpts.has_3d);
  const originCoord = mapOpts.origin_coord || mapOpts.initial_camera?.center || [0, 0];
  const ovScale = Math.max(1.0, Math.min(2.0, Number(mapOpts.ov_scale ?? 1.5) || 1.5));
  const ovW = Math.round(width * ovScale);
  const ovH = Math.round(height * ovScale);
  const sunAzimuth = Number.isFinite(Number(mapOpts.sun_azimuth_deg)) ? Number(mapOpts.sun_azimuth_deg) : 335;
  const sunElevation = Number.isFinite(Number(mapOpts.sun_elevation_deg)) ? Number(mapOpts.sun_elevation_deg) : 42;
  const maxPitch = Math.max(Number(mapOpts.max_pitch || 0), Number(mapOpts.initial_camera?.pitch || 0));
  const enableSky = mapOpts.atmosphere === false ? false : Boolean(terrain3d || maxPitch >= 25 || mapOpts.atmosphere);
  const hdrBloomEnabled = mapOpts.hdr_bloom !== false;
  const skySpec = mapOpts.atmosphere && typeof mapOpts.atmosphere === "object"
    ? {
        "sky-color": mapOpts.atmosphere.sky_color || "#071E2E",
        "sky-horizon-blend": mapOpts.atmosphere.sky_horizon_blend ?? 0.55,
        "horizon-color": mapOpts.atmosphere.horizon_color || "#1E5B70",
        "horizon-fog-blend": mapOpts.atmosphere.horizon_fog_blend ?? 0.45,
        "fog-color": mapOpts.atmosphere.fog_color || "#0C2C3B",
        "fog-ground-blend": mapOpts.atmosphere.fog_ground_blend ?? 0.35,
      }
    : {
        "sky-color": "#071E2E",
        "sky-horizon-blend": 0.55,
        "horizon-color": "#1E5B70",
        "horizon-fog-blend": 0.45,
        "fog-color": "#0C2C3B",
        "fog-ground-blend": 0.35,
      };
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${baseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${baseUrl}/vendor/maplibre-gl.js"></script>${has3d ? `
  <script type="importmap">{"imports":{"three":"${baseUrl}/vendor/three/three.module.js","three/addons/":"${baseUrl}/vendor/three/jsm/"}}</script>
  <script type="module">
    import * as THREE from "three";
    import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
    import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
    import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
    window.THREE = THREE;
    window.THREE_ADDONS = { GLTFLoader, DRACOLoader, RoomEnvironment };
    if (window.__resolveThreeReady) window.__resolveThreeReady();
  </script>` : ""}
  <style>
${typeof buildDynamicFontFaceCss === "function" ? buildDynamicFontFaceCss(baseUrl) : ""}
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #083847; }
    #stage, #map, #ov, #comp { position: absolute; inset: 0; width: ${width}px; height: ${height}px; }
    #stage { transform-origin: 50% 50%; will-change: transform; }
    #ov, #comp { pointer-events: none; }
    #comp { display: none; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <div id="stage">
    <div id="map"></div>
    <canvas id="ov" width="${ovW}" height="${ovH}"></canvas>
  </div>
  <canvas id="comp" width="${width}" height="${height}"></canvas>
  <script>
    const BASE_URL = ${JSON.stringify(baseUrl)};
    const VEC = ${vectorsJson};
    const W = ${width}, H = ${height};
    const OV_SCALE = ${ovScale};
    const OV_W = ${ovW}, OV_H = ${ovH};
    const SUN_AZIMUTH_DEG = ${sunAzimuth};
    const SUN_ELEVATION_DEG = ${sunElevation};
    const HDR_BLOOM_ENABLED = ${hdrBloomEnabled};
    const FLAG_RASTER_WIDTH = ${FLAG_RASTER_WIDTH};
${DRAW_MATH_SRC}
    const SUN_VEC = sunDirectionFromAzimuthElevation(SUN_AZIMUTH_DEG, SUN_ELEVATION_DEG);

    const map = new maplibregl.Map({
      container: "map",
      maxPitch: 75,
      style: {
        version: 8,
        projection: { type: ${JSON.stringify(mapOpts.projection || "mercator")} },
        sources: {
          sat: {
            type: "raster",
            tiles: [BASE_URL + ${JSON.stringify(tileRoute)}],
            tileSize: 256,
            maxzoom: ${satMaxZoom}
          }${terrain3d ? `,
          dem: {
            type: "raster-dem",
            tiles: [BASE_URL + "/dem/{z}/{x}/{y}.png"],
            tileSize: 256,
            encoding: "terrarium",
            maxzoom: ${demMaxZoom}
          }` : ""}
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0A3A4A" } },
          { id: "sat", type: "raster", source: "sat", paint: { "raster-contrast": ${mapOpts.tile_source === "realistic" ? 0.08 : mapOpts.tile_source === "project" ? 0.06 : 0}, "raster-saturation": ${mapOpts.tile_source === "realistic" ? 0.06 : mapOpts.tile_source === "project" ? 0.04 : 0} } }${terrain3d ? `,
          { id: "hillshade", type: "hillshade", source: "dem", paint: { "hillshade-exaggeration": 0.28, "hillshade-illumination-direction": ${sunAzimuth}, "hillshade-illumination-anchor": "map", "hillshade-shadow-color": "#041620", "hillshade-highlight-color": "#FFF5D6" } }` : ""}
        ]${terrain3d ? `,
        terrain: { source: "dem", exaggeration: ${terrainExag} }` : ""}${enableSky ? `,
        sky: ${JSON.stringify(skySpec)}` : ""}
      },
      center: ${JSON.stringify(mapOpts.initial_camera?.center || [0, 0])},
      zoom: ${Number(mapOpts.initial_camera?.zoom ?? 2)},
      bearing: ${Number(mapOpts.initial_camera?.bearing ?? 0)},
      pitch: ${Number(mapOpts.initial_camera?.pitch ?? 0)},
      minZoom: 0.5,
      maxZoom: 18,
      maxPitch: 75,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true,
      maxTileCacheSize: 8000,
      transformConstrain: (lngLat, zoom) => ({ center: lngLat, zoom }),
      canvasContextAttributes: { alpha: false, preserveDrawingBuffer: true, antialias: true }
    });

    const ovCanvas = document.getElementById("ov");
    const ctx = ovCanvas.getContext("2d");
    ctx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
    const compCanvas = document.getElementById("comp");
    const compCtx = compCanvas.getContext("2d");

    // Half-resolution offscreen canvas for smooth continuous-feathered organic masks & spotlights
    const ORG_SCALE = 0.5;
    const orgW = Math.max(128, Math.round(W * ORG_SCALE));
    const orgH = Math.max(128, Math.round(H * ORG_SCALE));
    const organicCanvas = document.createElement("canvas");
    organicCanvas.width = orgW; organicCanvas.height = orgH;
    const organicCtx = organicCanvas.getContext("2d");

    // Supersampled offscreen canvases for seamless dissolved polygon exterior glow, rim & FX passes
    const maskCanvas = document.createElement("canvas");
    maskCanvas.width = OV_W; maskCanvas.height = OV_H;
    const maskCtx = maskCanvas.getContext("2d");

    const rimCanvas = document.createElement("canvas");
    rimCanvas.width = OV_W; rimCanvas.height = OV_H;
    const rimCtx = rimCanvas.getContext("2d");

    const fxCanvas = document.createElement("canvas");
    fxCanvas.width = OV_W; fxCanvas.height = OV_H;
    const fxCtx = fxCanvas.getContext("2d");

    // Two-step pyramid bloom buffers (0.5x -> 0.25x) to eliminate thin-rim temporal shimmer
    const GLOW_HALF_SCALE = 0.5;
    const glowHalfW = Math.max(128, Math.round(W * GLOW_HALF_SCALE));
    const glowHalfH = Math.max(128, Math.round(H * GLOW_HALF_SCALE));
    const glowHalfCanvas = document.createElement("canvas");
    glowHalfCanvas.width = glowHalfW; glowHalfCanvas.height = glowHalfH;
    const glowHalfCtx = glowHalfCanvas.getContext("2d");

    const GLOW_SCALE = 0.25;
    const glowW = Math.max(64, Math.round(W * GLOW_SCALE));
    const glowH = Math.max(64, Math.round(H * GLOW_SCALE));
    const glowCanvas = document.createElement("canvas");
    glowCanvas.width = glowW; glowCanvas.height = glowH;
    const glowCtx = glowCanvas.getContext("2d");

    // Deterministic triangular-PDF micro-dither tile (128x128) to suppress 8-bit gradient banding
    const ditherCanvas = document.createElement("canvas");
    ditherCanvas.width = 128; ditherCanvas.height = 128;
    const ditherCtx = ditherCanvas.getContext("2d");
    const ditherImg = ditherCtx.createImageData(128, 128);
    {
      let seed = 133791;
      const nextRand = () => {
        seed = (seed * 1664525 + 1013904223) >>> 0;
        return seed / 4294967296;
      };
      for (let i = 0; i < ditherImg.data.length; i += 4) {
        const tri = nextRand() - nextRand();
        const v = tri >= 0 ? 255 : 0;
        ditherImg.data[i] = v;
        ditherImg.data[i + 1] = v;
        ditherImg.data[i + 2] = v;
        ditherImg.data[i + 3] = Math.round(Math.abs(tri) * 255);
      }
      ditherCtx.putImageData(ditherImg, 0, 0);
    }
    const ditherPattern = ctx.createPattern(ditherCanvas, "repeat");
    function applyMicroDither(targetCtx, alpha = 0.025) {
      if (!ditherPattern || alpha <= 0.001) return;
      targetCtx.save();
      targetCtx.globalCompositeOperation = "overlay";
      targetCtx.globalAlpha = clamp(alpha, 0, 0.08);
      targetCtx.fillStyle = ditherPattern;
      targetCtx.fillRect(0, 0, W, H);
      targetCtx.restore();
    }

    const __worldHatchCache = new Map();

    const HAS_3D = ${has3d};
    const ORIGIN_COORD = ${JSON.stringify(originCoord)};
    let __update3DScene = null;
    const __threeReadyPromise = HAS_3D
      ? new Promise((resolve) => {
          if (typeof window.THREE !== "undefined") resolve();
          else window.__resolveThreeReady = resolve;
        })
      : Promise.resolve();

    window.__ready = Promise.all([
      new Promise((res) => map.on("load", res)),
      __threeReadyPromise,
    ]).then(() => {
      if (HAS_3D && typeof THREE !== "undefined") {
        __update3DScene = initThreeMapLayer();
      }
    });
    window.__gltfCache = Object.create(null);
    window.__preloadModels = async function(urls) {
      const unique = [...new Set((urls || []).filter(Boolean))];
      if (!unique.length || !window.THREE_ADDONS || !window.THREE_ADDONS.GLTFLoader) return;
      const loader = new window.THREE_ADDONS.GLTFLoader();
      if (window.THREE_ADDONS.DRACOLoader) {
        const draco = new window.THREE_ADDONS.DRACOLoader();
        draco.setDecoderPath(BASE_URL + "/vendor/three/jsm/libs/draco/gltf/");
        loader.setDRACOLoader(draco);
      }
      await Promise.all(unique.map((u) => new Promise((resolve) => {
        if (window.__gltfCache[u]) { resolve(); return; }
        loader.load(u, (gltf) => {
          window.__gltfCache[u] = gltf.scene || gltf.scenes?.[0] || null;
          resolve();
        }, undefined, () => resolve());
      })));
    };
    window.__imgCache = Object.create(null);
    window.__preloadAssets = async function(urls) {
      const unique = [...new Set((urls || []).filter(Boolean))];
      await Promise.all(unique.map((u) => new Promise((resolve) => {
        if (window.__imgCache[u]) { resolve(); return; }
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          // Rasterize SVG into a crisp offscreen canvas so drawImage slicing works reliably.
          // Flags keep their natural aspect at a width large enough to cover a whole territory.
          const c = document.createElement("canvas");
          if (u.includes("/flags/")) {
            const nw = img.naturalWidth || 4;
            const nh = img.naturalHeight || 3;
            c.width = FLAG_RASTER_WIDTH;
            c.height = Math.max(1, Math.round(FLAG_RASTER_WIDTH * (nh / nw)));
          } else {
            c.width = 360;
            c.height = 240;
          }
          const cx = c.getContext("2d");
          cx.drawImage(img, 0, 0, c.width, c.height);
          window.__imgCache[u] = c;
          resolve();
        };
        img.onerror = () => resolve();
        img.src = u;
      })));
    };
    window.__waitIdle = function(ms) {
      return new Promise((res) => {
        if (map.loaded() && map.areTilesLoaded()) {
          map.triggerRepaint();
          requestAnimationFrame(() => res(false));
          return;
        }
        const t0 = performance.now();
        (function poll() {
          if (map.loaded() && map.areTilesLoaded()) {
            map.triggerRepaint();
            requestAnimationFrame(() => res(false));
            return;
          }
          if (performance.now() - t0 > (ms || 1500)) {
            res(!map.areTilesLoaded());
            return;
          }
          setTimeout(poll, 20);
        })();
      });
    };

    const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
    const lerp = (a, b, t) => a + (b - a) * t;
    const seg = (t, a, b) => (b <= a ? 1 : clamp((t - a) / (b - a), 0, 1));
    const easeInOutCubic = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
    const easeOutCubic = (x) => 1 - Math.pow(1 - x, 3);
    const easeOutExpo = (x) => x >= 1 ? 1 : 1 - Math.pow(2, -10 * x);
    const easeInExpo = (x) => x <= 0 ? 0 : Math.pow(2, 10 * x - 10);
    const easeInCubic = (x) => x * x * x;
    const easeOutBack = (x) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };

    function resolveGeom(ref) {
      if (!ref) return null;
      if (typeof ref === "object" && ref.type) return ref;
      if (typeof ref !== "string") return null;
      const parts = ref.split(".");
      let cur = VEC;
      for (const p of parts) {
        if (cur && typeof cur === "object" && p in cur) cur = cur[p];
        else return null;
      }
      return cur;
    }

    function projectRingClipped(ring) {
      if (!ring || ring.length < 3) return [];
      const tr = map.transform;
      const M = tr && (tr.mercatorMatrix || tr._mercatorMatrix);
      if (M && (map.getPitch() || 0) > 1.0) {
        const hasTerr = ${terrain3d} && typeof map.queryTerrainElevation === "function";
        const hom = [];
        for (let i = 0; i < ring.length; i++) {
          const c = ring[i];
          const elev = hasTerr ? Math.max(0, map.queryTerrainElevation(c, { exaggerated: true }) || 0) : 0;
          const mc = maplibregl.MercatorCoordinate.fromLngLat(c, elev);
          hom.push({
            x: M[0] * mc.x + M[4] * mc.y + M[8] * mc.z + M[12],
            y: M[1] * mc.x + M[5] * mc.y + M[9] * mc.z + M[13],
            z: M[2] * mc.x + M[6] * mc.y + M[10] * mc.z + M[14],
            w: M[3] * mc.x + M[7] * mc.y + M[11] * mc.z + M[15],
          });
        }
        const clipped = clipHomogeneousRing(hom, 1e-4);
        if (clipped.length < 3) return [];
        const pts = [];
        for (let i = 0; i < clipped.length; i++) {
          const v = clipped[i];
          const iw = 1 / Math.max(1e-4, v.w);
          pts.push({
            x: (v.x * iw * 0.5 + 0.5) * W,
            y: (0.5 - v.y * iw * 0.5) * H,
          });
        }
        return pts;
      }
      return ring.map((c) => map.project(c));
    }

    function projectPointSafe(lngLat, eps = 1e-4) {
      if (!lngLat || lngLat.length < 2) return null;
      const tr = map.transform;
      const M = tr && (tr.mercatorMatrix || tr._mercatorMatrix);
      if (M && (map.getPitch() || 0) > 1.0) {
        const hasTerr = ${terrain3d} && typeof map.queryTerrainElevation === "function";
        const elev = hasTerr ? Math.max(0, map.queryTerrainElevation(lngLat, { exaggerated: true }) || 0) : 0;
        const mc = maplibregl.MercatorCoordinate.fromLngLat(lngLat, elev);
        const w = M[3] * mc.x + M[7] * mc.y + M[11] * mc.z + M[15];
        const z = M[2] * mc.x + M[6] * mc.y + M[10] * mc.z + M[14];
        if (!Number.isFinite(w) || w <= eps || z + w < 0) return null;
        const x = M[0] * mc.x + M[4] * mc.y + M[8] * mc.z + M[12];
        const y = M[1] * mc.x + M[5] * mc.y + M[9] * mc.z + M[13];
        const iw = 1 / w;
        return { x: (x * iw * 0.5 + 0.5) * W, y: (0.5 - y * iw * 0.5) * H };
      }
      const p = map.project(lngLat);
      return p && Number.isFinite(p.x) && Number.isFinite(p.y) ? p : null;
    }

    function projectPolylineClipped(coords, eps = 1e-4) {
      if (!coords || coords.length < 2) return [];
      const tr = map.transform;
      const M = tr && (tr.mercatorMatrix || tr._mercatorMatrix);
      if (M && (map.getPitch() || 0) > 1.0) {
        const hasTerr = ${terrain3d} && typeof map.queryTerrainElevation === "function";
        const hom = [];
        for (let i = 0; i < coords.length; i++) {
          const c = coords[i];
          const elev = hasTerr ? Math.max(0, map.queryTerrainElevation(c, { exaggerated: true }) || 0) : 0;
          const mc = maplibregl.MercatorCoordinate.fromLngLat(c, elev);
          hom.push({
            x: M[0] * mc.x + M[4] * mc.y + M[8] * mc.z + M[12],
            y: M[1] * mc.x + M[5] * mc.y + M[9] * mc.z + M[13],
            z: M[2] * mc.x + M[6] * mc.y + M[10] * mc.z + M[14],
            w: M[3] * mc.x + M[7] * mc.y + M[11] * mc.z + M[15],
          });
        }
        const segs = clipHomogeneousPolyline(hom, eps);
        return segs.map((segVerts) =>
          segVerts.map((v) => {
            const iw = 1 / Math.max(eps, v.w);
            return { x: (v.x * iw * 0.5 + 0.5) * W, y: (0.5 - v.y * iw * 0.5) * H };
          })
        );
      }
      return [coords.map((c) => map.project(c))];
    }

    function traceRing(targetCtx, ring) {
      const pts = projectRingClipped(ring);
      if (pts.length < 3) return;
      for (let i = 0; i < pts.length; i++) {
        if (i === 0) targetCtx.moveTo(pts[i].x, pts[i].y);
        else targetCtx.lineTo(pts[i].x, pts[i].y);
      }
      targetCtx.closePath();
    }

    function traceGeom(targetCtx, geom) {
      if (!geom) return;
      if (Array.isArray(geom)) {
        for (const item of geom) traceGeom(targetCtx, item?.geometry || item);
        return;
      }
      if (geom.type === "Feature" || (!geom.type && geom.geometry)) {
        traceGeom(targetCtx, geom.geometry);
      } else if (geom.type === "FeatureCollection") {
        traceGeom(targetCtx, geom.features);
      } else if (geom.type === "GeometryCollection") {
        traceGeom(targetCtx, geom.geometries);
      } else if (geom.type === "Polygon") {
        for (const r of geom.coordinates || []) traceRing(targetCtx, r);
      } else if (geom.type === "MultiPolygon") {
        for (const poly of geom.coordinates || []) {
          for (const r of poly) traceRing(targetCtx, r);
        }
      }
    }

    function parseHexRgb(hex) {
      const raw = String(hex || "#FFFFFF").trim();
      const rgbMatch = raw.match(/^rgba?\\(\\s*([\\d.]+)\\s*,\\s*([\\d.]+)\\s*,\\s*([\\d.]+)/i);
      if (rgbMatch) {
        return [
          clamp(Math.round(Number(rgbMatch[1])), 0, 255),
          clamp(Math.round(Number(rgbMatch[2])), 0, 255),
          clamp(Math.round(Number(rgbMatch[3])), 0, 255),
        ];
      }
      const h = raw.replace("#", "");
      return [
        parseInt(h.slice(0, 2), 16) || 0,
        parseInt(h.slice(2, 4), 16) || 0,
        parseInt(h.slice(4, 6), 16) || 0,
      ];
    }

    function mixHex(c1, c2, u) {
      const a = parseHexRgb(c1), b = parseHexRgb(c2);
      const r = Math.round(lerp(a[0], b[0], u));
      const g = Math.round(lerp(a[1], b[1], u));
      const bl = Math.round(lerp(a[2], b[2], u));
      return "rgb(" + r + "," + g + "," + bl + ")";
    }

    function rgbaStr(hex, alpha) {
      const [r, g, b] = parseHexRgb(hex);
      return "rgba(" + r + "," + g + "," + b + "," + clamp(alpha, 0, 1).toFixed(3) + ")";
    }

    function computeGeomBounds(geom) {
      let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
      const visitRing = (ring) => {
        for (const pt of ring) {
          if (pt[0] < minLng) minLng = pt[0];
          if (pt[0] > maxLng) maxLng = pt[0];
          if (pt[1] < minLat) minLat = pt[1];
          if (pt[1] > maxLat) maxLat = pt[1];
        }
      };
      const visit = (g) => {
        if (!g) return;
        if (Array.isArray(g)) { for (const it of g) visit(it?.geometry || it); return; }
        if (g.type === "Feature" || (!g.type && g.geometry)) { visit(g.geometry); }
        else if (g.type === "FeatureCollection") { visit(g.features); }
        else if (g.type === "GeometryCollection") { visit(g.geometries); }
        else if (g.type === "Polygon") { for (const r of g.coordinates || []) visitRing(r); }
        else if (g.type === "MultiPolygon") { for (const p of g.coordinates || []) for (const r of p) visitRing(r); }
      };
      visit(geom);
      if (!Number.isFinite(minLng)) return null;
      return [minLng, minLat, maxLng, maxLat];
    }

    function applyWorldDirectionalClip(targetCtx, geom, axis, progress, explicitBounds = null) {
      const p = clamp(progress, 0, 1);
      if (p >= 0.999) return true;
      if (p <= 0.001) return false;
      const b = explicitBounds || computeGeomBounds(geom);
      if (!b) return true;
      const [minLng, minLat, maxLng, maxLat] = b;
      const padLng = Math.max(12, (maxLng - minLng) * 0.45);
      const padLat = Math.max(12, (maxLat - minLat) * 0.45);
      let w = minLng - padLng, e = maxLng + padLng, s = minLat - padLat, n = maxLat + padLat;
      if (axis === "north_south") {
        s = lerp(maxLat + 0.5, minLat - padLat, p);
      } else if (axis === "south_north") {
        n = lerp(minLat - 0.5, maxLat + padLat, p);
      } else if (axis === "west_east") {
        e = lerp(minLng - 0.5, maxLng + padLng, p);
      } else if (axis === "east_west") {
        w = lerp(maxLng + 0.5, minLng - padLng, p);
      }
      const corners = [[w, n], [e, n], [e, s], [w, s]];
      const projCorners = projectRingClipped(corners);
      if (projCorners.length < 3) return false;
      targetCtx.beginPath();
      for (let i = 0; i < projCorners.length; i++) {
        if (i === 0) targetCtx.moveTo(projCorners[i].x, projCorners[i].y);
        else targetCtx.lineTo(projCorners[i].x, projCorners[i].y);
      }
      targetCtx.closePath();
      targetCtx.clip();
      return true;
    }

    function drawProgressiveGeomPerimeter(geom, progress, { rimHex = "#F4F1EA", rimWidth = 3.2, bloomHex = "#60A5FA", bloomScale = 1.0, alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || progress <= 0.001 || !geom) return;
      const rings = [];
      const collect = (g) => {
        if (!g) return;
        if (Array.isArray(g)) { for (const it of g) collect(it?.geometry || it); return; }
        if (g.type === "Feature" || (!g.type && g.geometry)) { collect(g.geometry); }
        else if (g.type === "FeatureCollection") { collect(g.features); }
        else if (g.type === "GeometryCollection") { collect(g.geometries); }
        else if (g.type === "Polygon" && g.coordinates?.[0]) rings.push(g.coordinates[0]);
        else if (g.type === "MultiPolygon") { for (const p of g.coordinates || []) if (p[0]) rings.push(p[0]); }
      };
      collect(geom);
      for (const ring of rings) {
        if (ring.length < 3) continue;
        // Trace ring symmetrically from two opposite anchors so perimeter closes swiftly across the continent
        const mid = Math.floor(ring.length / 2);
        const segA = ring.slice(0, mid + 1);
        const segB = ring.slice(mid);
        const drawHalf = (coords) => {
          drawPartialRoute(coords, progress, {
            color: rimHex,
            bloom: bloomHex || rimHex,
            core: "#FFFFFF",
            width: rimWidth,
            alpha,
          });
        };
        drawHalf(segA);
        drawHalf(segB);
      }
    }

    // Exterior rings of a (Multi)Polygon or feature list, in lng/lat.
    function outerRingsLngLat(geom) {
      return polygonRings(geom).outer;
    }

    // Per-ring start vertex and walk direction for a border trace, decided in lng/lat so the
    // heads never jump between frames while the camera moves. Default start: northernmost vertex.
    function borderTraceOptions(ringsLL, heads, startLngLat, dir) {
      const startIndex = ringsLL.map((r) => {
        if (startLngLat) {
          return nearestVertexIndex(r.map((c) => ({ x: c[0], y: c[1] })), { x: startLngLat[0], y: startLngLat[1] });
        }
        let best = 0;
        for (let i = 1; i < r.length; i++) if (r[i][1] > r[best][1]) best = i;
        return best;
      });
      // Lat grows northward (y up), so a ring that is clockwise on a north-up screen has negative area here.
      const wantCw = dir !== "ccw";
      const direction = ringsLL.map((r) => {
        const cwOnScreen = signedArea(r.map((c) => ({ x: c[0], y: c[1] }))) < 0;
        return cwOnScreen === wantCw ? 1 : -1;
      });
      return { heads: heads === 1 ? 1 : 2, startIndex, direction };
    }

    // Draw a flag raster over a territory's screen bounds (upright, optional quarter turns).
    // "stretch" maps the whole flag design onto the bounding box; "cover" keeps the flag's
    // proportions and covers the box, cropping the overflow. Optional travelling wind-gust
    // vertical slice displacement warps the fabric silhouette when flagWave.warp > 0.
    function drawFlagCover(tctx, img, bounds, rotateDeg = 0, fit = "stretch", flagWave = null, time = 0) {
      const quarter = ((Math.round((rotateDeg || 0) / 90) % 4) + 4) % 4;
      const aspect = quarter % 2 ? img.height / img.width : img.width / img.height;
      const r = fit === "cover"
        ? coverRect(bounds, aspect)
        : { x: bounds.minX, y: bounds.minY, w: Math.max(1, bounds.maxX - bounds.minX), h: Math.max(1, bounds.maxY - bounds.minY) };
      const dw = quarter % 2 ? r.h : r.w;
      const dh = quarter % 2 ? r.w : r.h;
      tctx.save();
      tctx.translate(r.x + r.w / 2, r.y + r.h / 2);
      tctx.rotate((quarter * Math.PI) / 2);
      tctx.imageSmoothingQuality = "high";
      const warpFrac = flagWave && flagWave.warp > 0 ? Number(flagWave.warp) : 0;
      if (warpFrac > 0.001 && dw >= 12) {
        const slices = 80;
        const sw = img.width / slices;
        const dwS = dw / slices;
        const warpPx = clamp(dh * warpFrac, 2, 42);
        const cycles = flagWave.cycles ?? 2.5;
        const speed = flagWave.speed ?? 0.5;
        for (let i = 0; i < slices; i++) {
          const u = (i + 0.5) / slices;
          const ph = 2 * Math.PI * (cycles * u - speed * time);
          const gust = 0.72 * Math.sin(ph) + 0.28 * Math.sin(2 * ph + 1.15);
          const dy = gust * warpPx;
          tctx.drawImage(
            img,
            i * sw,
            0,
            Math.max(1, sw + 0.9),
            img.height,
            -dw / 2 + i * dwS - 0.9,
            -dh / 2 + dy - warpPx * 0.35,
            dwS + 2.2,
            dh + warpPx * 0.70
          );
        }
      } else {
        tctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
      }
      tctx.restore();
    }

    // Cloth shading for a waving flag: highlight and shadow bands along "angleDeg" across the
    // territory bounds, composited onto the flag pixels only, plus optional satin gloss sheen.
    function applyClothShade(tctx, b, wave, t) {
      const stops = clothWaveStops(t, { ...wave, stops: 40 });
      const amp = Math.max(0.001, Number(wave.amplitude) || 0.22);
      const ang = ((wave.angleDeg ?? 20) * Math.PI) / 180;
      const cx = (b.minX + b.maxX) / 2;
      const cy = (b.minY + b.maxY) / 2;
      const half = Math.max(1, Math.hypot(b.maxX - b.minX, b.maxY - b.minY) / 2);
      const dx = Math.cos(ang) * half;
      const dy = Math.sin(ang) * half;
      const grad = tctx.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
      for (const st of stops) {
        grad.addColorStop(st.offset, st.light >= 0
          ? "rgba(255,255,255," + clamp(st.light * 1.15, 0, 0.72).toFixed(3) + ")"
          : "rgba(0,0,0," + clamp(-st.light * 1.18, 0, 0.72).toFixed(3) + ")");
      }
      tctx.save();
      tctx.globalCompositeOperation = "source-atop";
      tctx.fillStyle = grad;
      tctx.fillRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);
      const gloss = wave.gloss > 0 ? clamp(Number(wave.gloss), 0, 1) : 0;
      if (gloss > 0.01) {
        const specGrad = tctx.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
        for (const st of stops) {
          const ridge = Math.max(0, (st.light / amp - 0.30) / 0.70);
          const crestA = clamp(Math.pow(ridge, 1.8) * gloss * 0.56, 0, 0.68);
          specGrad.addColorStop(st.offset, "rgba(255,255,255," + crestA.toFixed(3) + ")");
        }
        tctx.fillStyle = specGrad;
        tctx.fillRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);

        const sheenGrad = tctx.createLinearGradient(b.minX, b.minY, b.maxX, b.maxY);
        sheenGrad.addColorStop(0.0, "rgba(255,255,255," + (0.24 * gloss).toFixed(3) + ")");
        sheenGrad.addColorStop(0.38, "rgba(255,255,255," + (0.04 * gloss).toFixed(3) + ")");
        sheenGrad.addColorStop(0.68, "rgba(255,255,255," + (0.14 * gloss).toFixed(3) + ")");
        sheenGrad.addColorStop(1.0, "rgba(255,255,255,0)");
        tctx.fillStyle = sheenGrad;
        tctx.fillRect(b.minX, b.minY, b.maxX - b.minX, b.maxY - b.minY);
      }
      tctx.restore();
    }

    // Soft-edged reveal mask applied with destination-in: "radial" grows from "origin" (default
    // bounds centre); "organic" grows a world-space noise-edged seed with continuous Gaussian
    // feathering (zero step banding); "wipe_right" / "wipe_left" / "wipe_down" / "wipe_up" travel
    // in the named direction (see wipeFrontEdge).
    function applyRevealMask(tctx, mode, progress, b, origin = null, organic = null, geomBounds = null, originLngLat = null) {
      const p = clamp(progress, 0, 1);
      if (!b || mode === "fade" || p >= 0.999) return;
      if (mode === "organic") {
        organicCtx.save();
        organicCtx.setTransform(ORG_SCALE, 0, 0, ORG_SCALE, 0, 0);
        organicCtx.clearRect(0, 0, W, H);
        organicCtx.filter = "blur(6px)";
        organicCtx.fillStyle = "#000";
        const rough = organic && organic.roughness != null ? organic.roughness : 0.22;
        const seed = organic && organic.seed != null ? organic.seed : 1;
        let drewWorld = false;
        if (geomBounds && geomBounds.length === 4) {
          const [minLng, minLat, maxLng, maxLat] = geomBounds;
          const origLL = originLngLat || [(minLng + maxLng) * 0.5, (minLat + maxLat) * 0.5];
          const om = lngLatToMercNorm(origLL);
          const cornersM = [
            lngLatToMercNorm([minLng, minLat]),
            lngLatToMercNorm([maxLng, minLat]),
            lngLatToMercNorm([maxLng, maxLat]),
            lngLatToMercNorm([minLng, maxLat]),
          ];
          const maxRMerc = Math.max(
            1e-6,
            ...cornersM.map((cm) => Math.hypot(cm.x - om.x, cm.y - om.y))
          );
          const radii = organicRevealRadii(p, maxRMerc / 0.88, { points: 120, roughness: rough, seed });
          const ringLL = radii.map((r, i) => {
            const th = (2 * Math.PI * i) / radii.length;
            return mercNormToLngLat(om.x + Math.cos(th) * r, om.y + Math.sin(th) * r);
          });
          const pts = projectRingClipped(ringLL);
          if (pts.length >= 3) {
            organicCtx.beginPath();
            for (let i = 0; i < pts.length; i++) {
              if (i === 0) organicCtx.moveTo(pts[i].x, pts[i].y);
              else organicCtx.lineTo(pts[i].x, pts[i].y);
            }
            organicCtx.closePath();
            organicCtx.fill();
            drewWorld = true;
          }
        }
        if (!drewWorld) {
          const cx = origin ? origin.x : (b.minX + b.maxX) / 2;
          const cy = origin ? origin.y : (b.minY + b.maxY) / 2;
          const R = Math.max(
            Math.hypot(b.minX - cx, b.minY - cy), Math.hypot(b.maxX - cx, b.minY - cy),
            Math.hypot(b.minX - cx, b.maxY - cy), Math.hypot(b.maxX - cx, b.maxY - cy), 1
          );
          const radii = organicRevealRadii(p, R / 0.88, { points: 120, roughness: rough, seed });
          organicCtx.beginPath();
          radii.forEach((r, i) => {
            const th = (2 * Math.PI * i) / radii.length;
            const x = cx + Math.cos(th) * r;
            const y = cy + Math.sin(th) * r;
            if (i === 0) organicCtx.moveTo(x, y); else organicCtx.lineTo(x, y);
          });
          organicCtx.closePath();
          organicCtx.fill();
        }
        organicCtx.filter = "none";
        organicCtx.restore();
        tctx.save();
        tctx.globalCompositeOperation = "destination-in";
        tctx.drawImage(organicCanvas, 0, 0, W, H);
        tctx.restore();
        return;
      }
      tctx.save();
      tctx.globalCompositeOperation = "destination-in";
      let grad = null;
      if (mode === "radial") {
        const cx = origin ? origin.x : (b.minX + b.maxX) / 2;
        const cy = origin ? origin.y : (b.minY + b.maxY) / 2;
        const R = Math.max(
          Math.hypot(b.minX - cx, b.minY - cy), Math.hypot(b.maxX - cx, b.minY - cy),
          Math.hypot(b.minX - cx, b.maxY - cy), Math.hypot(b.maxX - cx, b.maxY - cy), 1
        );
        const feather = 0.12 * R;
        const r1 = Math.max(0.01, p * (R + feather));
        grad = tctx.createRadialGradient(cx, cy, Math.max(0, r1 - feather), cx, cy, r1);
      } else {
        const { horiz, back, front } = wipeFrontEdge(mode, p, b);
        grad = horiz ? tctx.createLinearGradient(back, 0, front, 0) : tctx.createLinearGradient(0, back, 0, front);
      }
      grad.addColorStop(0, "rgba(0,0,0,1)");
      grad.addColorStop(1, "rgba(0,0,0,0)");
      tctx.fillStyle = grad;
      tctx.fillRect(0, 0, W, H);
      tctx.restore();
    }

    // World-space surface-locked or concentric-contour progressive interior hatching clipped cleanly to maskCanvas.
    function drawProgressiveInteriorHatch(geom, geomBounds, {
      hatchColor = "rgba(255,255,255,0.24)",
      hatchSpacing = 18,
      hatchWidth = 3.2,
      hatchSpace = "world",
      hatchRevealMode = "fade",
      hatchProgress = 1.0,
      hatchStagger = 0.62,
      hatchDirection = "ltr",
      hatchAngleDeg = 45,
      hatchEase = "editorial_out",
      hatchRefZoom = null,
      hatchCross = false,
      hatchTipGlow = false,
      hatchGlowHex = null,
      fillRevealMode = "fade",
      fillReveal = 1.0,
      revealTargetBounds = null,
      fillRevealOriginPx = null,
      fillRevealOriginLL = null,
      fillRevealOrganic = null,
      revealAxis = null,
      revealProgress = 1.0,
      revealBounds = null,
      geomKey = "",
      alpha = 1.0,
    } = {}) {
      if (alpha <= 0.005 || hatchProgress <= 0.001) return;
      rimCtx.save();
      rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      rimCtx.clearRect(0, 0, W, H);
      rimCtx.globalCompositeOperation = "source-over";

      const tipPoints = [];
      if (hatchRevealMode === "contour_ripple") {
        // Exact Euclidean interior iso-contours via (S(d) \ S(d - w)) intersected with maskCanvas.
        const count = 5;
        const stepPx = Math.max(8, hatchSpacing * 0.85);
        const bandW = Math.max(1.5, hatchWidth);
        for (let k = 0; k < count; k++) {
          const st = hatchLineRevealState(k, count, hatchProgress, {
            mode: "contour_ripple",
            staggerFrac: hatchStagger,
            direction: hatchDirection,
            ease: hatchEase,
          });
          if (!st.active || st.alpha <= 0.005) continue;
          const dist = (k + 1) * stepPx;
          const lw = Math.max(1.0, bandW * st.widthScale);
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.lineJoin = "round";
          fxCtx.lineCap = "round";
          fxCtx.strokeStyle = "#FFFFFF";
          fxCtx.lineWidth = 2 * dist;
          fxCtx.beginPath();
          traceGeom(fxCtx, geom);
          fxCtx.stroke();
          const innerD = Math.max(0, dist - lw);
          if (innerD > 0.25) {
            fxCtx.globalCompositeOperation = "destination-out";
            fxCtx.lineWidth = 2 * innerD;
            fxCtx.beginPath();
            traceGeom(fxCtx, geom);
            fxCtx.stroke();
          }
          fxCtx.globalCompositeOperation = "source-in";
          fxCtx.fillStyle = hatchColor;
          fxCtx.fillRect(0, 0, W, H);
          fxCtx.restore();

          rimCtx.save();
          rimCtx.globalAlpha = st.alpha * (1 - k * 0.12);
          rimCtx.drawImage(fxCanvas, 0, 0, W, H);
          rimCtx.restore();
        }
      } else if (hatchSpace === "screen" || !geomBounds) {
        const angRad = ((hatchAngleDeg ?? 45) * Math.PI) / 180;
        const sp = Math.max(4, hatchSpacing);
        const diag = Math.hypot(W, H);
        const cx = W * 0.5, cy = H * 0.5;
        const ux = Math.cos(angRad), uy = -Math.sin(angRad);
        const nx = Math.sin(angRad), ny = Math.cos(angRad);
        const halfN = diag * 0.65;
        const count = Math.max(2, Math.min(260, Math.ceil((2 * halfN) / sp)));
        rimCtx.strokeStyle = hatchColor;
        rimCtx.lineCap = "round";
        for (let i = 0; i < count; i++) {
          const st = hatchLineRevealState(i, count, hatchProgress, {
            mode: hatchRevealMode,
            staggerFrac: hatchStagger,
            direction: hatchDirection,
            ease: hatchEase,
          });
          if (!st.active || st.alpha <= 0.005) continue;
          const nOff = -halfN + i * sp;
          const u0 = lerp(-halfN, halfN, st.drawFrom);
          const u1 = lerp(-halfN, halfN, st.drawTo);
          rimCtx.save();
          rimCtx.globalAlpha = st.alpha;
          rimCtx.lineWidth = Math.max(0.8, hatchWidth * st.widthScale);
          rimCtx.beginPath();
          rimCtx.moveTo(cx + nOff * nx + u0 * ux, cy + nOff * ny + u0 * uy);
          rimCtx.lineTo(cx + nOff * nx + u1 * ux, cy + nOff * ny + u1 * uy);
          rimCtx.stroke();
          rimCtx.restore();
        }
      } else {
        // World-space surface-locked Mercator hatch with octave blending & progressive per-line reveal.
        const curZoom = map.getZoom();
        const oct = computeOctaveHatchSpacing(hatchSpacing, curZoom, hatchRefZoom);
        const angles = hatchCross ? [hatchAngleDeg, hatchAngleDeg + 90] : [hatchAngleDeg];
        const bObj = {
          minLng: geomBounds[0],
          minLat: geomBounds[1],
          maxLng: geomBounds[2],
          maxLat: geomBounds[3],
        };
        const spacingStep = oct.subAlpha > 0.02 ? oct.subSpacingMerc : oct.primarySpacingMerc;
        const useSubFlag = oct.subAlpha > 0.02;
        for (let ai = 0; ai < angles.length; ai++) {
          const ang = angles[ai];
          const cacheKey = [
            geomKey || geomBounds.map((v) => v.toFixed(3)).join(","),
            ang.toFixed(1),
            oct.octave,
            useSubFlag ? "s" : "p",
            hatchSpacing,
          ].join("|");
          let lines = __worldHatchCache.get(cacheKey);
          if (!lines) {
            lines = buildWorldHatchLines(bObj, {
              angleDeg: ang,
              spacingMerc: spacingStep,
              maxLines: 180,
              padFrac: 0.14,
              segmentsPerLine: 10,
            });
            if (__worldHatchCache.size > 128) __worldHatchCache.clear();
            __worldHatchCache.set(cacheKey, lines);
          }
          const total = lines.length;
          const passProg = ai === 0 ? hatchProgress : clamp((hatchProgress - 0.18) / 0.82, 0, 1);
          if (passProg <= 0.001 || total === 0) continue;
          rimCtx.strokeStyle = hatchColor;
          rimCtx.lineCap = "round";
          rimCtx.lineJoin = "round";
          for (let i = 0; i < total; i++) {
            const line = lines[i];
            const octaveAlpha = useSubFlag && line.isSub ? oct.subAlpha : 1.0;
            if (octaveAlpha <= 0.01) continue;
            const st = hatchLineRevealState(i, total, passProg, {
              mode: hatchRevealMode,
              staggerFrac: hatchStagger,
              direction: hatchDirection,
              ease: hatchEase,
            });
            if (!st.active || st.alpha <= 0.005) continue;
            const subCoords = slicePolylineFraction(line.coords, st.drawFrom, st.drawTo);
            if (subCoords.length < 2) continue;
            const projSegs = projectPolylineClipped(subCoords);
            if (!projSegs.length) continue;
            rimCtx.save();
            rimCtx.globalAlpha = st.alpha * octaveAlpha * (ai === 1 ? 0.72 : 1.0);
            rimCtx.lineWidth = Math.max(0.8, hatchWidth * st.widthScale);
            rimCtx.beginPath();
            for (const segPts of projSegs) {
              if (segPts.length < 2) continue;
              rimCtx.moveTo(segPts[0].x, segPts[0].y);
              for (let k = 1; k < segPts.length; k++) rimCtx.lineTo(segPts[k].x, segPts[k].y);
            }
            rimCtx.stroke();
            rimCtx.restore();
            if (hatchTipGlow && st.drawTo > 0.02 && st.drawTo < 0.985) {
              const tipSeg = (hatchDirection === "alternate" && i % 2 === 1)
                ? projSegs[0]?.[0]
                : projSegs[projSegs.length - 1]?.[projSegs[projSegs.length - 1].length - 1];
              if (tipSeg && Number.isFinite(tipSeg.x) && Number.isFinite(tipSeg.y)) {
                tipPoints.push({ x: tipSeg.x, y: tipSeg.y, a: st.alpha * octaveAlpha });
              }
            }
          }
        }
      }

      // Optional luminous tip spark riding each actively drawing hatch line (clipped inside silhouette)
      if (tipPoints.length > 0) {
        const gHex = hatchGlowHex || "#FFFFFF";
        rimCtx.save();
        rimCtx.globalCompositeOperation = "lighter";
        for (const tp of tipPoints) {
          const rad = Math.max(6, hatchWidth * 3.2);
          const g = rimCtx.createRadialGradient(tp.x, tp.y, 0, tp.x, tp.y, rad);
          g.addColorStop(0, "rgba(255,255,255," + (0.85 * tp.a).toFixed(3) + ")");
          g.addColorStop(0.45, rgbaStr(gHex, 0.45 * tp.a));
          g.addColorStop(1, rgbaStr(gHex, 0));
          rimCtx.fillStyle = g;
          rimCtx.beginPath();
          rimCtx.arc(tp.x, tp.y, rad, 0, Math.PI * 2);
          rimCtx.fill();
        }
        rimCtx.restore();
      }

      // Mask to active reveal front (if non-fade) and strictly clip inside polygon silhouette
      if (fillRevealMode !== "fade" && fillReveal < 0.999) {
        applyRevealMask(rimCtx, fillRevealMode, fillReveal, revealTargetBounds, fillRevealOriginPx, fillRevealOrganic, geomBounds, fillRevealOriginLL);
      }
      rimCtx.globalCompositeOperation = "destination-in";
      rimCtx.drawImage(maskCanvas, 0, 0, W, H);
      rimCtx.restore();

      ctx.save();
      if (revealAxis && revealProgress < 0.999) {
        applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds);
      }
      ctx.globalAlpha = alpha * (fillRevealMode === "fade" ? clamp(fillReveal, 0, 1) : 1);
      ctx.drawImage(rimCanvas, 0, 0, W, H);
      ctx.restore();
    }

    // Shape-aware studio spotlight: dims map outside target polygons with soft feathered cutout.
    function drawFocusSpotlight(geoms, { dimAlpha = 0.58, dimHex = "#04101A", featherPx = 36, rimGlowHex = null, rimGlowAlpha = 0.25, alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || dimAlpha <= 0.005) return;
      const list = (geoms || []).filter(Boolean);
      if (!list.length) return;
      maskCtx.save();
      maskCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      maskCtx.clearRect(0, 0, W, H);
      maskCtx.fillStyle = "#FFFFFF";
      maskCtx.beginPath();
      for (const g of list) traceGeom(maskCtx, g);
      maskCtx.fill();
      maskCtx.restore();

      const blurR = clamp(Math.round((Number(featherPx) || 36) * ORG_SCALE), 2, 60);
      organicCtx.save();
      organicCtx.setTransform(ORG_SCALE, 0, 0, ORG_SCALE, 0, 0);
      organicCtx.clearRect(0, 0, W, H);
      organicCtx.filter = "blur(" + blurR + "px)";
      organicCtx.drawImage(maskCanvas, 0, 0, W, H);
      organicCtx.filter = "none";
      organicCtx.restore();

      fxCtx.save();
      fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      fxCtx.clearRect(0, 0, W, H);
      fxCtx.fillStyle = rgbaStr(dimHex, clamp(dimAlpha * alpha, 0, 0.95));
      fxCtx.fillRect(0, 0, W, H);
      fxCtx.globalCompositeOperation = "destination-out";
      fxCtx.drawImage(organicCanvas, 0, 0, W, H);
      fxCtx.restore();

      ctx.save();
      ctx.globalCompositeOperation = "source-over";
      ctx.drawImage(fxCanvas, 0, 0, W, H);
      if (rimGlowHex && rimGlowAlpha > 0.005) {
        fxCtx.save();
        fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        fxCtx.clearRect(0, 0, W, H);
        fxCtx.drawImage(organicCanvas, 0, 0, W, H);
        fxCtx.globalCompositeOperation = "destination-out";
        fxCtx.drawImage(maskCanvas, 0, 0, W, H);
        fxCtx.globalCompositeOperation = "source-in";
        fxCtx.fillStyle = rimGlowHex;
        fxCtx.fillRect(0, 0, W, H);
        fxCtx.restore();
        ctx.globalCompositeOperation = "screen";
        ctx.globalAlpha = clamp(rimGlowAlpha * alpha, 0, 0.85);
        ctx.drawImage(fxCanvas, 0, 0, W, H);
      }
      ctx.restore();
      applyMicroDither(ctx, 0.025 * alpha);
    }

    // Seamless exterior polygon dissolve + 2.5D lift/bevel/cast-shadow + 2-step pyramid screen bloom +
    // world-space border trace with comet head + world-space progressive hatch & optical lighting sweeps.
    function drawDissolvedPolygon(geom, {
      fillHex,
      fillAlpha = 0.56,
      rimHex = "#F4F1EA",
      rimWidth = 3.0,
      bloomHex = "#22C55E",
      bloomScale = 1.0,
      alpha = 1.0,
      preserveTerrain = true,
      borderReveal = 1.0,
      fillReveal = 1.0,
      revealAxis = null,
      revealProgress = 1.0,
      revealBounds = null,
      outlineOnly = false,
      perimeterProgress = 1.0,
      featherPx = 0,
      hatch = false,
      hatchColor = "rgba(255,255,255,0.22)",
      hatchSpacing = 18,
      hatchWidth = 3.5,
      hatchSpace = "world",
      hatchRevealMode = "fade",
      hatchProgress = 1.0,
      hatchStagger = 0.62,
      hatchDirection = "ltr",
      hatchAngleDeg = 45,
      hatchEase = "editorial_out",
      hatchRefZoom = null,
      hatchCross = false,
      hatchTipGlow = false,
      hatchGlowHex = null,
      flashHex = null,
      flashIntensity = 0,
      traced = false,
      traceProgress = 1.0,
      traceEndS = 0,
      traceHeads = 2,
      traceStart = null,
      traceDir = "cw",
      traceHeadGlow = false,
      flagImg = null,
      flagAlpha = 1.0,
      flagBlend = "source-over",
      flagRotateDeg = 0,
      flagFit = "stretch",
      fillRevealMode = "fade",
      fillRevealOrigin = null,
      fillRevealOrganic = null,
      fillBloomOvershoot = 1.0,
      flagWave = null,
      dissolveSeams = false,
      liftPx = 0,
      liftProgress = 1.0,
      castShadow = null,
      bevelLight = 0,
      lightSweep = null,
      rimGlint = null,
      geomKey = "",
      time = 0,
    } = {}) {
      if (alpha <= 0.005 || !geom) return;
      if (outlineOnly && perimeterProgress < 0.999 && !traced) {
        drawProgressiveGeomPerimeter(geom, perimeterProgress, { rimHex, rimWidth, bloomHex, bloomScale, alpha });
        return;
      }
      if (traced && traceProgress <= 0.001 && fillReveal <= 0.005) return;

      const geomBounds = computeGeomBounds(geom);
      const isMultiPart = Boolean(dissolveSeams) || Array.isArray(geom) || (geom && (geom.type === "FeatureCollection" || geom.type === "GeometryCollection"));
      const needOuter = traced || Boolean(flagImg) || fillRevealMode !== "fade" || Boolean(rimGlint) || Boolean(lightSweep);
      const ringsLL = needOuter ? outerRingsLngLat(geom) : [];
      const ringsPx = needOuter ? ringsLL.map((r) => projectRingClipped(r)) : [];

      // 1. Build clean solid silhouette mask (seam-bridge stroke only on multi-part dissolved regions)
      maskCtx.save();
      maskCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      maskCtx.clearRect(0, 0, W, H);
      maskCtx.fillStyle = "#FFFFFF";
      maskCtx.beginPath();
      traceGeom(maskCtx, geom);
      maskCtx.fill();
      if (isMultiPart) {
        maskCtx.strokeStyle = "#FFFFFF";
        maskCtx.lineWidth = 3.5;
        maskCtx.lineJoin = "round";
        maskCtx.stroke();
      }
      maskCtx.restore();

      // 2. Optional 2.5D tactile lift & directional cast shadow synced to global SUN_VEC
      const effLiftPx = Math.max(0, Number(liftPx) || 0) * clamp(liftProgress, 0, 1.15);
      const shadowCfg = castShadow === true
        ? { opacity: 0.44, blurPx: Math.max(10, effLiftPx * 0.95 + 8), offsetScale: 1.0 }
        : (castShadow && typeof castShadow === "object"
          ? {
              opacity: clamp(Number(castShadow.opacity ?? 0.44), 0, 0.9),
              blurPx: Math.max(4, Number(castShadow.blur_px ?? (effLiftPx * 0.95 + 10))),
              offsetScale: Math.max(0.2, Number(castShadow.offset_scale ?? 1.0)),
            }
          : (effLiftPx > 0.5 ? { opacity: 0.42, blurPx: Math.max(10, effLiftPx * 0.9 + 6), offsetScale: 1.0 } : null));

      if (shadowCfg && !outlineOnly && fillReveal > 0.01) {
        const shDist = Math.max(6, effLiftPx * 1.15 + 4) * shadowCfg.offsetScale;
        const shDx = SUN_VEC.shadowDx * shDist;
        const shDy = SUN_VEC.shadowDy * shDist;
        const blurOrg = clamp(Math.round(shadowCfg.blurPx * ORG_SCALE), 2, 40);
        organicCtx.save();
        organicCtx.setTransform(ORG_SCALE, 0, 0, ORG_SCALE, 0, 0);
        organicCtx.clearRect(0, 0, W, H);
        organicCtx.filter = "blur(" + blurOrg + "px)";
        organicCtx.drawImage(maskCanvas, shDx, shDy, W, H);
        organicCtx.filter = "none";
        organicCtx.globalCompositeOperation = "source-in";
        organicCtx.fillStyle = "#020A12";
        organicCtx.fillRect(0, 0, W, H);
        organicCtx.restore();

        ctx.save();
        ctx.globalAlpha = alpha * shadowCfg.opacity * clamp(fillReveal, 0, 1);
        ctx.drawImage(organicCanvas, 0, 0, W, H);
        ctx.restore();
      }

      // Faux 2.5D extruded skirt wall beneath lifted country block
      if (effLiftPx > 0.8 && !outlineOnly && fillReveal > 0.01) {
        const skirtColor = mixHex(fillHex || "#16A82A", "#030B12", 0.64);
        fxCtx.save();
        fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        fxCtx.clearRect(0, 0, W, H);
        const steps = Math.max(2, Math.min(18, Math.ceil(effLiftPx / 1.4)));
        for (let s = 0; s < steps; s++) {
          const yOff = -((s / steps) * effLiftPx);
          fxCtx.drawImage(maskCanvas, 0, yOff, W, H);
        }
        fxCtx.globalCompositeOperation = "destination-out";
        fxCtx.drawImage(maskCanvas, 0, -effLiftPx, W, H);
        fxCtx.globalCompositeOperation = "source-in";
        fxCtx.fillStyle = skirtColor;
        fxCtx.fillRect(0, 0, W, H);
        fxCtx.restore();

        ctx.save();
        ctx.globalAlpha = alpha * Math.min(0.94, fillAlpha + 0.25) * clamp(fillReveal, 0, 1);
        ctx.drawImage(fxCanvas, 0, 0, W, H);
        ctx.restore();
      }

      // 3. Build exterior-only rim ring into supersampled rimCanvas.
      rimCtx.save();
      rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      rimCtx.clearRect(0, 0, W, H);
      rimCtx.globalCompositeOperation = "source-over";
      const rw = Math.max(1.8, rimWidth);
      let traceHeadsPx = [];
      let cometSegsPx = [];
      const cometCloseFade = traced
        ? (traceProgress < 0.999 ? 1.0 : 1.0 - easeOutCubic(seg(time, traceEndS, traceEndS + 0.28)))
        : 0;
      if (traced) {
        if (traceProgress > 0.001) {
          const holesLL = polygonRings(geom).inner;
          const outerRes = perimeterPartialPathsLngLat(ringsLL, traceProgress, {
            ...borderTraceOptions(ringsLL, traceHeads, traceStart, traceDir),
            cometFraction: 0.055,
          });
          const holeRes = holesLL.length
            ? perimeterPartialPathsLngLat(holesLL, traceProgress, {
                ...borderTraceOptions(holesLL, traceHeads, traceStart, traceDir),
                cometFraction: 0.055,
              })
            : { paths: [], comets: [] };
          const allPathsLL = [...outerRes.paths, ...holeRes.paths];
          const allCometsLL = [...outerRes.comets, ...holeRes.comets];

          rimCtx.strokeStyle = "#FFFFFF";
          rimCtx.lineWidth = 2 * (rw + (isMultiPart ? 1.75 : 0.25));
          rimCtx.lineCap = "round";
          rimCtx.lineJoin = "round";
          rimCtx.beginPath();
          for (const pathLL of allPathsLL) {
            const segs = projectPolylineClipped(pathLL);
            for (const pts of segs) {
              if (pts.length < 2) continue;
              rimCtx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) rimCtx.lineTo(pts[i].x, pts[i].y);
              if (traceProgress >= 1) rimCtx.closePath();
              if (traceProgress < 1) traceHeadsPx.push(pts[pts.length - 1]);
            }
          }
          rimCtx.stroke();
          if (cometCloseFade > 0.01) {
            for (const cLL of allCometsLL) {
              for (const pts of projectPolylineClipped(cLL)) {
                if (pts.length >= 2) cometSegsPx.push(pts);
              }
            }
          }
        }
      } else if (!isMultiPart) {
        rimCtx.strokeStyle = "#FFFFFF";
        rimCtx.lineWidth = 2 * rw;
        rimCtx.lineCap = "round";
        rimCtx.lineJoin = "round";
        rimCtx.beginPath();
        traceGeom(rimCtx, geom);
        rimCtx.stroke();
      } else {
        const dirs = 16;
        for (let k = 0; k < dirs; k++) {
          const ang = (k / dirs) * Math.PI * 2;
          rimCtx.drawImage(maskCanvas, Math.cos(ang) * rw, Math.sin(ang) * rw, W, H);
        }
      }
      rimCtx.globalCompositeOperation = "destination-out";
      rimCtx.drawImage(maskCanvas, 0, 0, W, H);
      rimCtx.restore();

      // Begin lifted country body coordinate space
      ctx.save();
      if (effLiftPx > 0.05) ctx.translate(0, -effLiftPx);

      // 4. Exterior-only 2-step pyramid screen bloom (0.5x -> 0.25x prevents thin-rim shimmer)
      ctx.save();
      if (revealAxis && revealProgress < 0.999) {
        if (!applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds)) {
          ctx.restore();
          ctx.restore();
          return;
        }
      } else if (borderReveal < 0.999) {
        ctx.beginPath();
        ctx.rect(0, 0, W, H * clamp(borderReveal, 0, 1));
        ctx.clip();
      }
      const overshootWave = (fillBloomOvershoot > 1.001 && fillReveal > 0.005 && fillReveal < 0.999)
        ? 1.0 + (fillBloomOvershoot - 1.0) * Math.sin(fillReveal * Math.PI) * (1 - 0.35 * fillReveal)
        : 1.0;
      const effBloomHex = (flashHex && flashIntensity > 0.01) ? flashHex : bloomHex;
      const effBloomScale = bloomScale * overshootWave + flashIntensity * 1.15;
      if (effBloomHex && effBloomScale > 0) {
        rimCtx.save();
        rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = effBloomHex;
        rimCtx.fillRect(0, 0, W, H);
        rimCtx.restore();

        // Step 1: smooth 0.5x half-pyramid downsample
        glowHalfCtx.save();
        glowHalfCtx.clearRect(0, 0, glowHalfW, glowHalfH);
        glowHalfCtx.imageSmoothingEnabled = true;
        glowHalfCtx.imageSmoothingQuality = "high";
        glowHalfCtx.drawImage(rimCanvas, 0, 0, glowHalfW, glowHalfH);
        glowHalfCtx.restore();

        // Step 2: multi-radius glow on 0.25x buffer
        glowCtx.save();
        glowCtx.clearRect(0, 0, glowW, glowH);
        glowCtx.imageSmoothingEnabled = true;
        glowCtx.imageSmoothingQuality = "high";
        const passes = [
          [42 * effBloomScale * GLOW_SCALE, Math.min(0.95, 0.42 + flashIntensity * 0.40)],
          [20 * effBloomScale * GLOW_SCALE, Math.min(0.98, 0.62 + flashIntensity * 0.28)],
          [8 * effBloomScale * GLOW_SCALE, Math.min(1.0, 0.78 + flashIntensity * 0.20)],
        ];
        for (const [blurPx, a] of passes) {
          glowCtx.save();
          glowCtx.globalAlpha = a;
          glowCtx.shadowColor = effBloomHex;
          glowCtx.shadowBlur = Math.max(1, blurPx);
          glowCtx.drawImage(glowHalfCanvas, 0, 0, glowW, glowH);
          glowCtx.restore();
        }
        glowCtx.restore();

        ctx.save();
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.globalCompositeOperation = "screen";
        ctx.globalAlpha = clamp(alpha * 0.92, 0, 1);
        ctx.drawImage(glowCanvas, 0, 0, W, H);
        ctx.globalCompositeOperation = "lighter";
        ctx.globalAlpha = clamp(alpha * 0.22, 0, 0.45);
        ctx.drawImage(glowCanvas, 0, 0, W, H);
        ctx.restore();
      }

      // 5. Crisp exterior rim (animated by borderReveal)
      if (rimHex && rimWidth > 0) {
        rimCtx.save();
        rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = (flashHex && flashIntensity > 0.25) ? "#FFFFFF" : rimHex;
        rimCtx.fillRect(0, 0, W, H);
        rimCtx.restore();
        ctx.globalCompositeOperation = "source-over";
        ctx.globalAlpha = alpha * 0.94;
        ctx.drawImage(rimCanvas, 0, 0, W, H);
      }

      // 5b. Travelling specular rim glint riding the exterior rim while polygon holds
      if (rimGlint && (!traced || traceProgress >= 0.99) && ringsLL.length > 0) {
        const gSpeed = Number(rimGlint.speed ?? 0.22);
        const gSpan = clamp(Number(rimGlint.span_frac ?? 0.14), 0.03, 0.45);
        const gCol = rimGlint.color || "#FFFFFF";
        const gInt = clamp(Number(rimGlint.intensity ?? 0.85), 0.05, 1.5);
        const phase = ((time * gSpeed) % 1 + 1) % 1;
        const glintPaths = perimeterWindowPathsLngLat(ringsLL, phase, gSpan);
        if (glintPaths.length > 0) {
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.lineCap = "round";
          fxCtx.lineJoin = "round";
          for (const gpLL of glintPaths) {
            for (const pts of projectPolylineClipped(gpLL)) {
              if (pts.length < 2) continue;
              const p0 = pts[0], p1 = pts[pts.length - 1];
              const grad = fxCtx.createLinearGradient(p0.x, p0.y, p1.x, p1.y);
              grad.addColorStop(0, rgbaStr(gCol, 0));
              grad.addColorStop(0.5, rgbaStr(gCol, 0.95));
              grad.addColorStop(1, rgbaStr(gCol, 0));
              fxCtx.strokeStyle = grad;
              fxCtx.lineWidth = rw * 2.6;
              fxCtx.beginPath();
              fxCtx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) fxCtx.lineTo(pts[i].x, pts[i].y);
              fxCtx.stroke();
            }
          }
          fxCtx.globalCompositeOperation = "destination-in";
          fxCtx.drawImage(rimCanvas, 0, 0, W, H);
          fxCtx.restore();

          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          ctx.globalAlpha = clamp(alpha * gInt, 0, 1);
          ctx.drawImage(fxCanvas, 0, 0, W, H);
          ctx.restore();
        }
      }

      // 5c. Tapered electric comet draw-head & flare during border_trace
      if (cometSegsPx.length > 0 && cometCloseFade > 0.01) {
        const glowHex = bloomHex || rimHex || "#FFFFFF";
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        for (const pts of cometSegsPx) {
          const p0 = pts[0], p1 = pts[pts.length - 1];
          const cg = ctx.createLinearGradient(p0.x, p0.y, p1.x, p1.y);
          cg.addColorStop(0, rgbaStr(glowHex, 0));
          cg.addColorStop(0.55, rgbaStr(glowHex, 0.72 * alpha * cometCloseFade));
          cg.addColorStop(1, "rgba(255,255,255," + (0.96 * alpha * cometCloseFade).toFixed(3) + ")");
          ctx.strokeStyle = cg;
          ctx.lineWidth = rw * 1.9;
          ctx.beginPath();
          ctx.moveTo(pts[0].x, pts[0].y);
          for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
          ctx.stroke();
        }
        ctx.restore();
      }
      if ((traceHeadGlow || cometSegsPx.length > 0) && traceHeadsPx.length) {
        const glowHex = bloomHex || rimHex;
        const flareScale = traceHeadGlow ? 6.0 : 3.6;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        for (const hp of traceHeadsPx) {
          const rad = rw * flareScale;
          const g = ctx.createRadialGradient(hp.x, hp.y, 0, hp.x, hp.y, rad);
          g.addColorStop(0, "rgba(255,255,255," + (0.92 * alpha * cometCloseFade).toFixed(3) + ")");
          g.addColorStop(0.32, rgbaStr(glowHex, 0.56 * alpha * cometCloseFade));
          g.addColorStop(1, rgbaStr(glowHex, 0));
          ctx.globalAlpha = 1;
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(hp.x, hp.y, rad, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();
      }
      ctx.restore();

      // 6. Interior fill (terrain-preserving tint or flag raster), inner bevel, progressive hatch & light sweep
      if (!outlineOnly && fillReveal > 0.005) {
        const clusters = needOuter ? ringClusters(ringsPx, { viewport: { w: W, h: H } }) : [];
        const fillBounds = clusters.length ? clusters[0].bounds : null;
        const visibleClusters = clusters.filter(
          (c) => c.bounds.maxX > 0 && c.bounds.minX < W && c.bounds.maxY > 0 && c.bounds.minY < H
        );
        const revealTargetBounds = visibleClusters.length
          ? visibleClusters.reduce(
              (acc, c) => ({
                minX: Math.min(acc.minX, c.bounds.minX),
                minY: Math.min(acc.minY, c.bounds.minY),
                maxX: Math.max(acc.maxX, c.bounds.maxX),
                maxY: Math.max(acc.maxY, c.bounds.maxY),
              }),
              visibleClusters[0].bounds
            )
          : fillBounds;
        const fillRevealOriginPx = fillRevealOrigin ? projectPointSafe(fillRevealOrigin) : null;

        rimCtx.save();
        rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
        rimCtx.clearRect(0, 0, W, H);
        rimCtx.globalCompositeOperation = "source-over";
        if (flagImg && fillBounds) {
          for (const cluster of visibleClusters) {
            const cb = cluster.bounds;
            rimCtx.save();
            rimCtx.beginPath();
            rimCtx.rect(cb.minX, cb.minY, cb.maxX - cb.minX, cb.maxY - cb.minY);
            rimCtx.clip();
            drawFlagCover(rimCtx, flagImg, cb, flagRotateDeg, flagFit, flagWave, time);
            if (flagWave) applyClothShade(rimCtx, cb, flagWave, time);
            rimCtx.restore();
          }
          rimCtx.globalCompositeOperation = "destination-in";
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
        } else {
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-in";
          rimCtx.fillStyle = fillHex;
          rimCtx.fillRect(0, 0, W, H);
        }
        if (fillRevealMode !== "fade") {
          applyRevealMask(rimCtx, fillRevealMode, fillReveal, revealTargetBounds, fillRevealOriginPx, fillRevealOrganic, geomBounds, fillRevealOrigin);
        }
        rimCtx.restore();
        const revealAlpha = fillRevealMode === "fade" ? clamp(fillReveal, 0, 1) : 1;

        ctx.save();
        if (revealAxis && revealProgress < 0.999) {
          if (!applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds)) {
            ctx.restore();
            ctx.restore();
            return;
          }
        }
        const useFlag = Boolean(flagImg && fillBounds);
        ctx.globalCompositeOperation = useFlag ? flagBlend : "source-over";
        const baseFillA = (useFlag ? flagAlpha : fillAlpha) * overshootWave;
        ctx.globalAlpha = clamp(alpha * baseFillA * revealAlpha, 0, 1);
        if (featherPx > 0) {
          ctx.shadowColor = fillHex;
          ctx.shadowBlur = featherPx;
        }
        ctx.drawImage(rimCanvas, 0, 0, W, H);
        ctx.restore();

        // 6b. Subtle directional inner bevel (sun-facing inner highlight + opposite inner shadow)
        const bAmt = clamp(Number(bevelLight) || 0, 0, 1);
        if (bAmt > 0.01) {
          const bOff = 2.2;
          // Sun-facing highlight edge
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.drawImage(maskCanvas, 0, 0, W, H);
          fxCtx.globalCompositeOperation = "destination-out";
          fxCtx.drawImage(maskCanvas, SUN_VEC.shadowDx * bOff, SUN_VEC.shadowDy * bOff, W, H);
          fxCtx.globalCompositeOperation = "source-in";
          fxCtx.fillStyle = "#FFFFFF";
          fxCtx.fillRect(0, 0, W, H);
          fxCtx.restore();
          ctx.save();
          ctx.globalCompositeOperation = "screen";
          ctx.globalAlpha = alpha * bAmt * 0.42 * revealAlpha;
          ctx.drawImage(fxCanvas, 0, 0, W, H);
          ctx.restore();

          // Shadow-facing inner depth edge
          fxCtx.save();
          fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          fxCtx.clearRect(0, 0, W, H);
          fxCtx.drawImage(maskCanvas, 0, 0, W, H);
          fxCtx.globalCompositeOperation = "destination-out";
          fxCtx.drawImage(maskCanvas, SUN_VEC.lightDx * bOff, SUN_VEC.lightDy * bOff, W, H);
          fxCtx.globalCompositeOperation = "source-in";
          fxCtx.fillStyle = "#03101A";
          fxCtx.fillRect(0, 0, W, H);
          fxCtx.restore();
          ctx.save();
          ctx.globalCompositeOperation = "multiply";
          ctx.globalAlpha = alpha * bAmt * 0.34 * revealAlpha;
          ctx.drawImage(fxCanvas, 0, 0, W, H);
          ctx.restore();
        }

        // 6c. Progressive world-space / contour interior hatch
        if (hatch) {
          drawProgressiveInteriorHatch(geom, geomBounds, {
            hatchColor,
            hatchSpacing,
            hatchWidth,
            hatchSpace,
            hatchRevealMode,
            hatchProgress,
            hatchStagger,
            hatchDirection,
            hatchAngleDeg,
            hatchEase,
            hatchRefZoom,
            hatchCross,
            hatchTipGlow,
            hatchGlowHex: hatchGlowHex || bloomHex || rimHex,
            fillRevealMode,
            fillReveal,
            revealTargetBounds,
            fillRevealOriginPx,
            fillRevealOriginLL: fillRevealOrigin,
            fillRevealOrganic,
            revealAxis,
            revealProgress,
            revealBounds,
            geomKey,
            alpha,
          });
        }

        // 6d. Optional diagonal specular light sweep across country silhouette
        if (lightSweep && lightSweep.progress > 0.001 && lightSweep.progress < 0.999) {
          const sb = revealTargetBounds || { minX: 0, minY: 0, maxX: W, maxY: H };
          const bw = Math.max(40, sb.maxX - sb.minX);
          const bh = Math.max(40, sb.maxY - sb.minY);
          const diag = Math.hypot(bw, bh);
          const cx = (sb.minX + sb.maxX) * 0.5;
          const cy = (sb.minY + sb.maxY) * 0.5;
          const ang = ((lightSweep.angleDeg ?? 32) * Math.PI) / 180;
          const dx = Math.cos(ang), dy = Math.sin(ang);
          const bandW = diag * clamp(lightSweep.widthFrac ?? 0.24, 0.08, 0.65);
          const travel = lerp(-diag * 0.72 - bandW, diag * 0.72 + bandW, lightSweep.progress);
          const sx0 = cx + dx * (travel - bandW * 0.5);
          const sy0 = cy + dy * (travel - bandW * 0.5);
          const sx1 = cx + dx * (travel + bandW * 0.5);
          const sy1 = cy + dy * (travel + bandW * 0.5);
          const col = lightSweep.color || "#FFFFFF";
          const env = Math.sin(lightSweep.progress * Math.PI);
          const inten = clamp((lightSweep.intensity ?? 0.55) * env, 0, 1);
          if (inten > 0.005) {
            fxCtx.save();
            fxCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
            fxCtx.clearRect(0, 0, W, H);
            const lg = fxCtx.createLinearGradient(sx0, sy0, sx1, sy1);
            lg.addColorStop(0.0, rgbaStr(col, 0));
            lg.addColorStop(0.28, rgbaStr(col, 0.22 * inten));
            lg.addColorStop(0.50, rgbaStr(col, 0.95 * inten));
            lg.addColorStop(0.76, rgbaStr(col, 0.28 * inten));
            lg.addColorStop(1.0, rgbaStr(col, 0));
            fxCtx.fillStyle = lg;
            fxCtx.fillRect(0, 0, W, H);
            fxCtx.globalCompositeOperation = "destination-in";
            fxCtx.drawImage(maskCanvas, 0, 0, W, H);
            fxCtx.restore();

            ctx.save();
            ctx.globalCompositeOperation = "screen";
            ctx.globalAlpha = alpha * revealAlpha;
            ctx.drawImage(fxCanvas, 0, 0, W, H);
            ctx.restore();
          }
        }

        // 6e. Optional ownership tint-flash surge over interior silhouette
        if (flashHex && flashIntensity > 0.01) {
          rimCtx.save();
          rimCtx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
          rimCtx.clearRect(0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-over";
          rimCtx.drawImage(maskCanvas, 0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-in";
          rimCtx.fillStyle = flashHex;
          rimCtx.fillRect(0, 0, W, H);
          rimCtx.restore();
          ctx.save();
          ctx.globalCompositeOperation = "screen";
          ctx.globalAlpha = alpha * Math.min(0.85, flashIntensity * 0.72);
          ctx.drawImage(rimCanvas, 0, 0, W, H);
          ctx.restore();
        }
      }

      // End lifted country body coordinate space
      ctx.restore();
    }

    function drawStandardPolygon(geom, { fillHex, fillAlpha = 0.45, rimHex = "#F4F1EA", rimWidth = 2.2, bloomHex = null, bloomScale = 0.4, alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || !geom) return;
      ctx.save();
      if (bloomHex && bloomScale > 0) {
        for (const [w, a] of [[rimWidth + 18 * bloomScale, 0.22], [rimWidth + 8 * bloomScale, 0.42]]) {
          ctx.beginPath();
          traceGeom(ctx, geom);
          ctx.strokeStyle = bloomHex;
          ctx.lineWidth = w;
          ctx.lineJoin = "round";
          ctx.globalAlpha = alpha * a;
          ctx.stroke();
        }
      }
      ctx.beginPath();
      traceGeom(ctx, geom);
      ctx.fillStyle = rgbaStr(fillHex, fillAlpha);
      ctx.globalAlpha = alpha;
      ctx.fill();
      if (rimHex && rimWidth > 0) {
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = rimWidth;
        ctx.lineJoin = "round";
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawPartialRoute(coords, progress, { color = "#FDE047", bloom = "#F5C542", core = "#FFFFFF", width = 8, dash = null, alpha = 1, cableCasing = false, pulseSpeed = 0, pulseCount = 3, pulseColor = "#FFFFFF", pulseGlow = "#FDE047", pulseTailFrac = 0.12, time = 0 } = {}) {
      if (progress <= 0.001 || alpha <= 0.005 || !coords || coords.length < 2) return;
      const clippedSegs = projectPolylineClipped(coords);
      if (!clippedSegs.length) return;
      const pts = clippedSegs.reduce((best, s) => (s.length >= best.length ? s : best), clippedSegs[0]);
      if (!pts || pts.length < 2) return;
      const lens = [0];
      let tot = 0;
      for (let i = 1; i < pts.length; i++) {
        tot += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
        lens.push(tot);
      }
      const target = tot * clamp(progress, 0, 1);
      const out = [pts[0]];
      for (let i = 1; i < pts.length; i++) {
        if (lens[i] <= target) out.push(pts[i]);
        else {
          const frac = (target - lens[i - 1]) / Math.max(1e-5, lens[i] - lens[i - 1]);
          out.push({ x: lerp(pts[i - 1].x, pts[i].x, frac), y: lerp(pts[i - 1].y, pts[i].y, frac) });
          break;
        }
      }
      if (out.length < 2) return;
      const trace = () => {
        ctx.beginPath();
        ctx.moveTo(out[0].x, out[0].y);
        for (let i = 1; i < out.length; i++) ctx.lineTo(out[i].x, out[i].y);
      };
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (dash) ctx.setLineDash(dash);
      if (cableCasing && !dash) {
        trace(); ctx.strokeStyle = "#03161F"; ctx.globalAlpha = alpha * 0.82; ctx.lineWidth = width * 1.48; ctx.stroke();
      }
      if (bloom) {
        trace(); ctx.strokeStyle = bloom; ctx.globalAlpha = alpha * 0.28; ctx.lineWidth = width * 2.8; ctx.stroke();
        trace(); ctx.strokeStyle = bloom; ctx.globalAlpha = alpha * 0.56; ctx.lineWidth = width * 1.65; ctx.stroke();
      }
      trace(); ctx.strokeStyle = color; ctx.globalAlpha = alpha; ctx.lineWidth = width; ctx.stroke();
      if (core && !dash) {
        trace(); ctx.strokeStyle = core; ctx.globalAlpha = alpha * 0.88; ctx.lineWidth = Math.max(1.8, width * 0.36); ctx.stroke();
      }
      if (pulseSpeed > 0 && !dash && target > 24) {
        const outLens = [0];
        let outTot = 0;
        for (let i = 1; i < out.length; i++) {
          outTot += Math.hypot(out[i].x - out[i - 1].x, out[i].y - out[i - 1].y);
          outLens.push(outTot);
        }
        const sampleOut = (dist) => {
          const d = clamp(dist, 0, outTot);
          for (let i = 1; i < outLens.length; i++) {
            if (outLens[i] >= d || i === outLens.length - 1) {
              const span = Math.max(1e-5, outLens[i] - outLens[i - 1]);
              const f = clamp((d - outLens[i - 1]) / span, 0, 1);
              return { x: lerp(out[i - 1].x, out[i].x, f), y: lerp(out[i - 1].y, out[i].y, f) };
            }
          }
          return out[0];
        };
        ctx.setLineDash([]);
        const count = Math.max(1, Math.round(pulseCount));
        const tailDist = Math.max(18, outTot * pulseTailFrac);
        for (let k = 0; k < count; k++) {
          const phase = ((time * pulseSpeed + k / count) % 1 + 1) % 1;
          const headD = phase * (outTot + tailDist);
          const steps = 10;
          for (let s = 1; s <= steps; s++) {
            const d0 = headD - tailDist * (1 - (s - 1) / steps);
            const d1 = headD - tailDist * (1 - s / steps);
            if (d1 < 0 || d0 > outTot) continue;
            const p0 = sampleOut(d0);
            const p1 = sampleOut(d1);
            const frac = s / steps;
            ctx.strokeStyle = frac > 0.72 ? pulseColor : pulseGlow;
            ctx.globalAlpha = alpha * Math.pow(frac, 1.5) * 0.95;
            ctx.lineWidth = width * (0.45 + 0.85 * frac);
            ctx.beginPath();
            ctx.moveTo(p0.x, p0.y);
            ctx.lineTo(p1.x, p1.y);
            ctx.stroke();
          }
          if (headD >= 0 && headD <= outTot) {
            const hp = sampleOut(headD);
            const hg = ctx.createRadialGradient(hp.x, hp.y, 1, hp.x, hp.y, width * 1.9);
            hg.addColorStop(0, "rgba(255,255,255," + (0.95 * alpha).toFixed(2) + ")");
            hg.addColorStop(0.45, rgbaStr(pulseGlow, 0.72 * alpha));
            hg.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = hg;
            ctx.globalAlpha = 1;
            ctx.beginPath();
            ctx.arc(hp.x, hp.y, width * 1.9, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      ctx.restore();
    }

    // Local 2x2 MapLibre projection Jacobian (dScreen/dEast, dScreen/dSouth) for 3D surface-locked overlays.
    // Samples a micro-step at the active camera zoom so the probe point never crosses behind the WebGL near plane
    // during high-pitch dive-zooms (preventing inverted/mirrored text), then scales back to refZoom units.
    function getMapPlaneMatrix(coord, refZoom = 5.0) {
      const [lng, lat] = coord;
      const p0 = map.project([lng, lat]);
      const curZoom = map.getZoom();
      const cosLat = Math.max(0.15, Math.cos((lat * Math.PI) / 180));
      const stepZoom = Math.max(refZoom, curZoom);
      const stepPx = 4;
      const dLng = (360 / (512 * Math.pow(2, stepZoom))) * stepPx;
      const dLat = dLng * cosLat;
      const relScale = Math.pow(2, stepZoom - refZoom);
      const pEast = map.project([lng + dLng, lat]);
      const pSouth = map.project([lng, lat - dLat]);
      let a = ((pEast.x - p0.x) / stepPx) * relScale;
      let b = ((pEast.y - p0.y) / stepPx) * relScale;
      let c = ((pSouth.x - p0.x) / stepPx) * relScale;
      let d = ((pSouth.y - p0.y) / stepPx) * relScale;
      const det = a * d - b * c;
      if (!Number.isFinite(det) || det <= 1e-6) {
        const mag = Math.hypot(a, b);
        const s = Number.isFinite(mag) && mag > 1e-4 ? mag : Math.pow(2, curZoom - refZoom);
        const rot = (-map.getBearing() * Math.PI) / 180;
        const pitchCos = Math.max(0.25, Math.cos(((map.getPitch() || 0) * Math.PI) / 180));
        a = Math.cos(rot) * s;
        b = Math.sin(rot) * s;
        c = -Math.sin(rot) * s * pitchCos;
        d = Math.cos(rot) * s * pitchCos;
      }
      return { a, b, c, d, e: p0.x, f: p0.y };
    }

    const CARTO_TYPO_PRESETS = Object.freeze({
      country: { family: "Barlow Condensed", weight: 800, fontStyle: "normal", letterSpacingEm: 0.14, fill: "#F4F1EA", strokeHex: "rgba(3,22,31,0.80)", strokeMult: 0.048, glowStrength: "none", uppercase: true },
      region:  { family: "Inter", weight: 600, fontStyle: "normal", letterSpacingEm: 0.18, fill: "#C8D4DC", strokeHex: "rgba(3,22,31,0.72)", strokeMult: 0.042, glowStrength: "none", uppercase: true },
      city:    { family: "Inter", weight: 700, fontStyle: "normal", letterSpacingEm: 0.01, fill: "#F4F1EA", strokeHex: "rgba(3,22,31,0.82)", strokeMult: 0.045, glowStrength: "none", uppercase: false },
      water:   { family: "Lora", weight: 600, fontStyle: "italic", letterSpacingEm: 0.08, fill: "#A8D8FF", strokeHex: "rgba(3,22,31,0.78)", strokeMult: 0.042, glowStrength: "none", uppercase: false },
      coord:   { family: "IBM Plex Mono", weight: 700, fontStyle: "normal", letterSpacingEm: 0.06, fill: "#DCE8F5", strokeHex: "rgba(3,22,31,0.82)", strokeMult: 0.042, glowStrength: "none", uppercase: true, tabularDigits: true },
      hero:    { family: "Barlow Condensed", weight: 800, fontStyle: "normal", letterSpacingEm: -0.01, fill: "#F4F1EA", strokeHex: "rgba(3,22,31,0.86)", strokeMult: 0.052, glowStrength: "none", uppercase: true },
    });

    function inferFontFallback(family) {
      const f = String(family || "").toLowerCase();
      if (/garamond|lora|playfair|merriweather|baskerville|serif|cinzel/.test(f)) return "Georgia, serif";
      if (/mono|courier|code/.test(f)) return "monospace";
      return "sans-serif";
    }

    function resolveCanvasLetterSpacingPx(letterSpacing, fontPx) {
      if (!letterSpacing) return 0;
      if (typeof letterSpacing === "number") return Number.isFinite(letterSpacing) ? letterSpacing : 0;
      const s = String(letterSpacing).trim();
      if (s.endsWith("em")) {
        const val = parseFloat(s);
        return Number.isFinite(val) ? val * fontPx : 0;
      }
      const px = parseFloat(s);
      return Number.isFinite(px) ? px : 0;
    }

    function applyCanvasLetterSpacing(letterSpacing, fontPx) {
      if (typeof ctx.letterSpacing !== "string") return;
      const px = resolveCanvasLetterSpacingPx(letterSpacing, fontPx);
      ctx.letterSpacing = px ? px.toFixed(2) + "px" : "0px";
    }

    // Draw a single centered line with optional fixed-width tabular digit slots (eliminates
    // horizontal jitter on proportional fonts in Canvas 2D) and anchored left-to-right typewriter.
    function renderLinePass(fullLine, ly, mode, { tabularDigits = false, typewriterChars = null, typewriterLeadHex = null, fill = "#FFFFFF", strokeHex = null, extraSpacingPx = 0 } = {}) {
      const isTw = typewriterChars != null;
      const visibleChars = isTw ? Math.max(0, Math.min(fullLine.length, typewriterChars)) : fullLine.length;
      if (visibleChars <= 0) return;
      if (!tabularDigits && !isTw) {
        ctx.textAlign = "center";
        if (mode === "stroke") ctx.strokeText(fullLine, 0, ly);
        else ctx.fillText(fullLine, 0, ly);
        return;
      }
      if (!tabularDigits && isTw) {
        // Measure full text width once so centered typewriter stays anchored with zero creep.
        const fullW = ctx.measureText(fullLine).width;
        const x0 = -fullW * 0.5;
        ctx.textAlign = "left";
        const shown = fullLine.slice(0, visibleChars);
        if (mode === "stroke") {
          ctx.strokeText(shown, x0, ly);
        } else if (typewriterLeadHex && visibleChars < fullLine.length && shown.length > 0) {
          const head = shown.slice(0, -1);
          const lead = shown.slice(-1);
          if (head) {
            ctx.fillStyle = fill;
            ctx.fillText(head, x0, ly);
          }
          ctx.fillStyle = typewriterLeadHex;
          ctx.fillText(lead, x0 + ctx.measureText(head).width, ly);
        } else {
          ctx.fillText(shown, x0, ly);
        }
        return;
      }
      // Fixed-slot tabular digit rendering for smooth zero-jitter Canvas 2D counters/odometers.
      const prevLs = typeof ctx.letterSpacing === "string" ? ctx.letterSpacing : null;
      if (prevLs !== null) ctx.letterSpacing = "0px";
      let maxDigitW = 0;
      for (let d = 0; d <= 9; d++) {
        maxDigitW = Math.max(maxDigitW, ctx.measureText(String(d)).width);
      }
      const chars = Array.from(fullLine);
      const widths = chars.map((ch) => (ch >= "0" && ch <= "9" ? maxDigitW : ctx.measureText(ch).width));
      const totalW = widths.reduce((a, b) => a + b, 0) + Math.max(0, chars.length - 1) * extraSpacingPx;
      let cx = -totalW * 0.5;
      ctx.textAlign = "center";
      for (let i = 0; i < Math.min(chars.length, visibleChars); i++) {
        const ch = chars[i];
        const cw = widths[i];
        const px = cx + cw * 0.5;
        if (mode === "stroke") {
          ctx.strokeText(ch, px, ly);
        } else {
          if (typewriterLeadHex && isTw && visibleChars < chars.length && i === visibleChars - 1) {
            ctx.fillStyle = typewriterLeadHex;
          } else {
            ctx.fillStyle = fill;
          }
          ctx.fillText(ch, px, ly);
        }
        cx += cw + extraSpacingPx;
      }
      if (prevLs !== null) ctx.letterSpacing = prevLs;
    }

    // Multi-ring luminous text glow + cartographic dark contrast halo with continuous sub-pixel
    // scaling, italic/letter-spacing support, Canvas 2D tabular digit slots, and anchored typewriter.
    function drawGlowingText(text, x, y, fontPx, { fill = "#F4F1EA", glowHex = null, glowStrength = "none", angle = 0, scale = 1.0, alpha = 1, family = "Barlow Condensed", weight = 800, fontStyle = "normal", letterSpacing = 0, strokeHex = null, strokeWidth = 0, lineHeightMult = 1.08, tabularDigits = false, typewriterChars = null, typewriterLeadHex = null, subPill = null } = {}) {
      if (alpha <= 0.005 || scale <= 0.01) return;
      const lines = String(text ?? "").split("\\n");
      const lineStep = fontPx * lineHeightMult;
      const totalH = (lines.length - 1) * lineStep;
      const fallback = inferFontFallback(family);
      const stylePrefix = fontStyle && fontStyle !== "normal" ? fontStyle + " " : "";
      ctx.save();
      ctx.translate(x, y);
      if (angle) ctx.rotate(angle);
      if (Math.abs(scale - 1.0) > 1e-4) ctx.scale(scale, scale);
      ctx.font = stylePrefix + weight + " " + Math.round(fontPx) + "px '" + family + "', " + fallback;
      const extraSpacingPx = resolveCanvasLetterSpacingPx(letterSpacing, fontPx);
      applyCanvasLetterSpacing(letterSpacing, fontPx);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      // Distribute typewriter character budget cleanly across multi-line strings.
      const lineBudgets = [];
      let remChars = typewriterChars;
      for (let li = 0; li < lines.length; li++) {
        if (remChars == null) {
          lineBudgets.push(null);
        } else {
          const take = Math.max(0, Math.min(lines[li].length, remChars));
          lineBudgets.push(take);
          remChars = Math.max(0, remChars - lines[li].length - 1);
        }
      }

      if (glowHex && glowStrength && glowStrength !== "none") {
        const rings = glowStrength === "intense"
          ? [[fontPx * 0.85, 0.55], [fontPx * 0.45, 0.82], [fontPx * 0.18, 0.96]]
          : glowStrength === "subtle"
            ? [[fontPx * 0.32, 0.48], [fontPx * 0.14, 0.68]]
            : [[fontPx * 0.58, 0.46], [fontPx * 0.26, 0.74], [fontPx * 0.12, 0.90]];
        for (const [blurR, a] of rings) {
          ctx.save();
          ctx.globalAlpha = alpha * a;
          ctx.shadowColor = glowHex;
          ctx.shadowBlur = blurR;
          ctx.fillStyle = fill;
          for (let li = 0; li < lines.length; li++) {
            renderLinePass(lines[li], -totalH * 0.5 + li * lineStep, "fill", {
              tabularDigits,
              typewriterChars: lineBudgets[li],
              fill,
              extraSpacingPx,
            });
          }
          ctx.restore();
        }
      }
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(0,0,0,0.82)";
      ctx.shadowBlur = Math.max(4, fontPx * 0.12);
      ctx.shadowOffsetY = 2;
      if (strokeHex && strokeWidth > 0) {
        ctx.strokeStyle = strokeHex;
        ctx.lineWidth = Math.min(strokeWidth, fontPx * 0.24);
        ctx.lineJoin = "round";
        ctx.miterLimit = 2;
        for (let li = 0; li < lines.length; li++) {
          renderLinePass(lines[li], -totalH * 0.5 + li * lineStep, "stroke", {
            tabularDigits,
            typewriterChars: lineBudgets[li],
            strokeHex,
            extraSpacingPx,
          });
        }
      }
      ctx.fillStyle = fill;
      for (let li = 0; li < lines.length; li++) {
        renderLinePass(lines[li], -totalH * 0.5 + li * lineStep, "fill", {
          tabularDigits,
          typewriterChars: lineBudgets[li],
          typewriterLeadHex,
          fill,
          extraSpacingPx,
        });
      }

      if (subPill && subPill.alpha > 0.01 && subPill.text) {
        const pScale = subPill.scale ?? 1.0;
        const pFont = subPill.font_px ?? Math.max(18, Math.round(fontPx * 0.26));
        const pY = (totalH * 0.5) + fontPx * 0.52 + (subPill.dy ?? 6);
        ctx.save();
        ctx.translate(0, pY);
        ctx.scale(pScale, pScale);
        ctx.globalAlpha = alpha * subPill.alpha;
        ctx.font = "800 " + pFont + "px '" + family + "', " + fallback;
        applyCanvasLetterSpacing(0, pFont);
        const tw = ctx.measureText(subPill.text).width;
        const iconW = subPill.icon === "person" ? pFont * 0.95 : 0;
        const padX = pFont * 0.55;
        const pillW = tw + iconW + padX * 2;
        const pillH = pFont * 1.48;
        const r = pillH * 0.5;
        ctx.shadowColor = "rgba(0,0,0,0.65)";
        ctx.shadowBlur = 10;
        ctx.shadowOffsetY = 3;
        ctx.fillStyle = subPill.bg_hex || fill;
        ctx.beginPath();
        ctx.roundRect(-pillW * 0.5, -pillH * 0.5, pillW, pillH, r);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.shadowOffsetY = 0;
        if (subPill.border_hex) {
          ctx.strokeStyle = subPill.border_hex;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        const fg = subPill.text_hex || "#FFFFFF";
        if (subPill.icon === "person") {
          const ix = -pillW * 0.5 + padX + iconW * 0.36;
          ctx.fillStyle = fg;
          ctx.beginPath();
          ctx.arc(ix, -pFont * 0.20, pFont * 0.19, 0, Math.PI * 2);
          ctx.fill();
          ctx.beginPath();
          ctx.arc(ix, pFont * 0.36, pFont * 0.33, Math.PI, 0, false);
          ctx.closePath();
          ctx.fill();
        }
        ctx.fillStyle = fg;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(subPill.text, -pillW * 0.5 + padX + iconW, 1);
        ctx.restore();
      }
      ctx.restore();
    }

    // Arc-length-parametrized curved cartographic label for rivers, straits, coastlines, and ranges.
    function drawCurvedMapLabel(screenPts, text, fontPx, { fill = "#A8D8FF", family = "Lora", weight = 600, fontStyle = "italic", letterSpacingPx = 0, strokeHex = "rgba(3,22,31,0.78)", strokeWidth = 2.0, alpha = 1.0, offsetPx = 0, revealProgress = 1.0, maxCharAngleDeg = 22 } = {}) {
      if (alpha <= 0.005 || !screenPts || screenPts.length < 2 || !text) return;
      // Auto-orient left-to-right so curved map labels are never rendered upside-down.
      let pts = screenPts;
      const first = pts[0];
      const last = pts[pts.length - 1];
      if (last.x < first.x) {
        pts = [...pts].reverse();
      }
      const cum = [0];
      for (let i = 1; i < pts.length; i++) {
        cum.push(cum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
      }
      const totalLen = cum[cum.length - 1];
      if (totalLen < fontPx * 0.8) return;

      const sampleAt = (s) => {
        const clamped = Math.max(0, Math.min(totalLen, s));
        let lo = 0;
        let hi = cum.length - 1;
        while (lo + 1 < hi) {
          const mid = (lo + hi) >> 1;
          if (cum[mid] <= clamped) lo = mid;
          else hi = mid;
        }
        const segLen = Math.max(1e-6, cum[hi] - cum[lo]);
        const u = (clamped - cum[lo]) / segLen;
        const p0 = pts[lo];
        const p1 = pts[hi];
        const dx = p1.x - p0.x;
        const dy = p1.y - p0.y;
        const ang = Math.atan2(dy, dx);
        const nx = -Math.sin(ang);
        const ny = Math.cos(ang);
        return {
          x: p0.x + dx * u + nx * offsetPx,
          y: p0.y + dy * u + ny * offsetPx,
          angle: ang,
        };
      };

      const fallback = inferFontFallback(family);
      const stylePrefix = fontStyle && fontStyle !== "normal" ? fontStyle + " " : "";
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.font = stylePrefix + weight + " " + Math.round(fontPx) + "px '" + family + "', " + fallback;
      applyCanvasLetterSpacing(0, fontPx);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      const chars = Array.from(String(text));
      const charWidths = chars.map((ch) => ctx.measureText(ch).width);
      // Pairwise optical kerning adjustment preserves natural glyph spacing (e.g. AV, WA, To)
      // when laying out curved river, strait, and coastline labels character-by-character.
      const advances = chars.map((ch, i) => {
        const chW = charWidths[i];
        let kern = 0;
        if (i + 1 < chars.length) {
          const next = chars[i + 1];
          const pairW = ctx.measureText(ch + next).width;
          kern = pairW - (chW + charWidths[i + 1]);
        }
        return Math.max(chW * 0.35, chW + kern) + letterSpacingPx;
      });
      const textLen = advances.reduce((a, b) => a + b, 0) - letterSpacingPx;
      const startS = Math.max(0, (totalLen - textLen) * 0.5);
      const visibleCount = Math.max(0, Math.round(chars.length * clamp(revealProgress, 0, 1)));
      const maxDeltaRad = (maxCharAngleDeg * Math.PI) / 180;

      // Pass 1: crisp dark halo; Pass 2: clean high-luma fill.
      const passes = strokeHex && strokeWidth > 0 ? ["stroke", "fill"] : ["fill"];
      for (const pass of passes) {
        let sCur = startS;
        let prevAng = null;
        for (let i = 0; i < visibleCount; i++) {
          const ch = chars[i];
          const adv = advances[i];
          const midS = sCur + charWidths[i] * 0.5;
          const pose = sampleAt(midS);
          let ang = pose.angle;
          if (prevAng != null) {
            let delta = ang - prevAng;
            while (delta > Math.PI) delta -= Math.PI * 2;
            while (delta < -Math.PI) delta += Math.PI * 2;
            if (Math.abs(delta) > maxDeltaRad) {
              ang = prevAng + Math.sign(delta) * maxDeltaRad;
            }
          }
          prevAng = ang;
          if (ch.trim()) {
            ctx.save();
            ctx.translate(pose.x, pose.y);
            ctx.rotate(ang);
            if (pass === "stroke") {
              ctx.strokeStyle = strokeHex;
              ctx.lineWidth = Math.min(strokeWidth, fontPx * 0.24);
              ctx.lineJoin = "round";
              ctx.miterLimit = 2;
              ctx.shadowColor = "rgba(0,0,0,0.75)";
              ctx.shadowBlur = Math.max(3, fontPx * 0.1);
              ctx.strokeText(ch, 0, 0);
            } else {
              ctx.fillStyle = fill;
              ctx.fillText(ch, 0, 0);
            }
            ctx.restore();
          }
          sCur += adv;
        }
      }
      ctx.restore();
    }

    function drawHumanFigure(x, y, h, color = "#FFFFFF", alpha = 1.0) {
      if (alpha <= 0.005 || h <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(0,0,0,0.65)";
      ctx.shadowBlur = Math.max(4, h * 0.14);
      ctx.shadowOffsetY = 2;
      ctx.fillStyle = color;
      // Head
      const headR = h * 0.135;
      ctx.beginPath();
      ctx.arc(0, -h * 0.37, headR, 0, Math.PI * 2);
      ctx.fill();
      // Torso + arms (clean pill silhouette)
      const w = h * 0.38;
      ctx.beginPath();
      ctx.roundRect(-w * 0.5, -h * 0.20, w, h * 0.38, w * 0.36);
      ctx.fill();
      // Legs
      const legW = w * 0.34;
      const legGap = w * 0.12;
      ctx.beginPath();
      ctx.roundRect(-legGap * 0.5 - legW, h * 0.10, legW, h * 0.38, legW * 0.45);
      ctx.roundRect(legGap * 0.5, h * 0.10, legW, h * 0.38, legW * 0.45);
      ctx.fill();
      ctx.restore();
    }

    function drawLandmarkSilhouette(x, y, heightPx, landmark = "statue_of_liberty", { fillHex = "#94A3B8", accentHex = "#CBD5E1", rimHex = "#E2E8F0", alpha = 1.0, riseProgress = 1.0, time = 0, angleDeg = 0 } = {}) {
      if (alpha <= 0.005 || heightPx <= 2 || riseProgress <= 0.01) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      // Ground shadow anchor beneath structure so it sits physically on terrain
      const shS = heightPx / 200;
      ctx.save();
      ctx.fillStyle = "rgba(2, 10, 14, 0.44)";
      ctx.beginPath();
      ctx.ellipse(0, 4 * shS, 42 * shS * clamp(riseProgress, 0.3, 1), 12 * shS * clamp(riseProgress, 0.3, 1), 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      // Clip from baseline upward so the monument rises out of the map anchor cleanly
      ctx.beginPath();
      ctx.rect(-heightPx * 1.05, -heightPx * 1.35, heightPx * 2.1, heightPx * 1.45);
      ctx.clip();
      const slideY = (1 - riseProgress) * heightPx * 1.15;
      ctx.translate(0, slideY);
      const s = heightPx / 200;
      ctx.scale(s, s);
      ctx.shadowColor = "rgba(0,0,0,0.65)";
      ctx.shadowBlur = 14;
      ctx.shadowOffsetY = 5;

      if (landmark === "statue_of_liberty") {
        // Pedestal base
        ctx.fillStyle = "#64748B";
        ctx.beginPath();
        ctx.roundRect(-24, -18, 48, 18, 3);
        ctx.fill();
        // Draped robe & body silhouette
        const grad = ctx.createLinearGradient(-22, -160, 26, -18);
        grad.addColorStop(0, accentHex);
        grad.addColorStop(0.55, fillHex);
        grad.addColorStop(1, "#475569");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(-20, -18);
        ctx.lineTo(-16, -95);
        ctx.lineTo(-22, -124);
        ctx.lineTo(-10, -138);
        // Raised torch arm (right side)
        ctx.lineTo(14, -142);
        ctx.lineTo(22, -182);
        ctx.lineTo(29, -182);
        ctx.lineTo(24, -132);
        ctx.lineTo(18, -95);
        ctx.lineTo(21, -18);
        ctx.closePath();
        ctx.fill();
        // Tablet in left arm
        ctx.fillStyle = "#475569";
        ctx.beginPath();
        ctx.roundRect(-24, -118, 13, 22, 2);
        ctx.fill();
        // Head & 7-ray crown
        ctx.fillStyle = accentHex;
        ctx.beginPath();
        ctx.arc(-1, -149, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 2.4;
        ctx.lineCap = "round";
        for (let i = -3; i <= 3; i++) {
          const ang = -Math.PI * 0.5 + i * 0.34;
          ctx.beginPath();
          ctx.moveTo(-1 + Math.cos(ang) * 9, -151 + Math.sin(ang) * 9);
          ctx.lineTo(-1 + Math.cos(ang) * 19, -151 + Math.sin(ang) * 19);
          ctx.stroke();
        }
        // Torch cup & flame
        ctx.fillStyle = "#CBD5E1";
        ctx.beginPath();
        ctx.roundRect(19, -187, 13, 7, 2);
        ctx.fill();
        ctx.fillStyle = "#FACC15";
        ctx.shadowColor = "#F59E0B";
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.moveTo(25.5, -203);
        ctx.quadraticCurveTo(32, -193, 25.5, -186);
        ctx.quadraticCurveTo(19, -193, 25.5, -203);
        ctx.fill();
      } else if (landmark === "transmission_tower") {
        // Steel HVDC lattice transmission pylon with cross-arms and energized insulator terminals
        ctx.strokeStyle = rimHex;
        ctx.fillStyle = fillHex;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        // Concrete foundation pads
        ctx.fillRect(-38, -8, 16, 8);
        ctx.fillRect(22, -8, 16, 8);
        // Main tapered lattice legs
        ctx.lineWidth = 5.5;
        ctx.beginPath();
        ctx.moveTo(-30, -8); ctx.lineTo(-10, -158); ctx.lineTo(0, -188);
        ctx.moveTo(30, -8); ctx.lineTo(10, -158); ctx.lineTo(0, -188);
        ctx.stroke();
        // Horizontal cross-arms (lower and upper)
        ctx.lineWidth = 5.0;
        ctx.beginPath();
        ctx.moveTo(-54, -108); ctx.lineTo(54, -108);
        ctx.moveTo(-40, -148); ctx.lineTo(40, -148);
        ctx.stroke();
        // Cross-arm diagonal braces
        ctx.lineWidth = 3.0;
        ctx.beginPath();
        ctx.moveTo(-54, -108); ctx.lineTo(-16, -94);
        ctx.moveTo(54, -108); ctx.lineTo(16, -94);
        ctx.moveTo(-40, -148); ctx.lineTo(-12, -134);
        ctx.moveTo(40, -148); ctx.lineTo(12, -134);
        // Body X-bracing bays
        const bays = [[-8, -42, 30, 24], [-42, -76, 24, 19], [-76, -108, 19, 15], [-108, -148, 15, 11]];
        for (const [y0, y1, w0, w1] of bays) {
          ctx.moveTo(-w0, y0); ctx.lineTo(w1, y1);
          ctx.moveTo(w0, y0); ctx.lineTo(-w1, y1);
          ctx.moveTo(-w1, y1); ctx.lineTo(w1, y1);
        }
        ctx.stroke();
        // Suspended insulator strings & glowing energized terminals
        ctx.shadowBlur = 12;
        ctx.shadowColor = accentHex;
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 3.0;
        for (const [ix, iy] of [[-52, -108], [52, -108], [-38, -148], [38, -148]]) {
          ctx.beginPath(); ctx.moveTo(ix, iy); ctx.lineTo(ix, iy + 14); ctx.stroke();
          ctx.fillStyle = accentHex;
          ctx.beginPath(); ctx.arc(ix, iy + 16, 5.5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath(); ctx.arc(ix, iy + 16, 2.3, 0, Math.PI * 2); ctx.fill();
        }
        // Earth-wire apex beacon
        ctx.fillStyle = accentHex;
        ctx.beginPath(); ctx.arc(0, -190, 4.5, 0, Math.PI * 2); ctx.fill();
      } else if (landmark === "solar_array") {
        // Isometric perspective solar panel bank with tilted PV cell grid and animated sun glint
        const panels = [[-46, -18], [4, -18], [-34, -58], [16, -58]];
        for (let pi = 0; pi < panels.length; pi++) {
          const [px, py] = panels[pi];
          // Support stanchion
          ctx.fillStyle = "#64748B";
          ctx.fillRect(px + 14, py + 12, 5, 16);
          ctx.save();
          ctx.translate(px, py);
          // Tilted panel quad
          ctx.beginPath();
          ctx.moveTo(-22, 12);
          ctx.lineTo(24, 12);
          ctx.lineTo(34, -16);
          ctx.lineTo(-12, -16);
          ctx.closePath();
          const pg = ctx.createLinearGradient(-18, -16, 30, 12);
          pg.addColorStop(0, fillHex === "#94A3B8" ? "#1E3A8A" : fillHex);
          pg.addColorStop(1, "#0F172A");
          ctx.fillStyle = pg;
          ctx.fill();
          ctx.strokeStyle = rimHex;
          ctx.lineWidth = 2.4;
          ctx.stroke();
          // PV cell grid lines
          ctx.strokeStyle = "rgba(147, 197, 253, 0.45)";
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          for (const f of [0.33, 0.66]) {
            ctx.moveTo(lerp(-22, 24, f), 12); ctx.lineTo(lerp(-12, 34, f), -16);
            ctx.moveTo(lerp(-22, -12, f), lerp(12, -16, f)); ctx.lineTo(lerp(24, 34, f), lerp(12, -16, f));
          }
          ctx.stroke();
          // Subtle sunlit glint sweep
          const glint = 0.5 + 0.5 * Math.sin(time * 3.4 + pi * 1.3);
          ctx.fillStyle = rgbaStr(accentHex === "#CBD5E1" ? "#FDE047" : accentHex, 0.16 + glint * 0.24);
          ctx.beginPath();
          ctx.moveTo(-12, 8); ctx.lineTo(2, 8); ctx.lineTo(10, -12); ctx.lineTo(-4, -12);
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      } else if (landmark === "substation_hub") {
        // HVDC converter terminal station with glowing energy bolt crest
        ctx.fillStyle = "#1E293B";
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 3.2;
        ctx.beginPath();
        ctx.roundRect(-48, -56, 96, 56, 6);
        ctx.fill();
        ctx.stroke();
        // Roof deck & transformer bushings
        ctx.fillStyle = "#334155";
        ctx.fillRect(-42, -68, 84, 12);
        for (const bx of [-28, 0, 28]) {
          ctx.strokeStyle = rimHex;
          ctx.lineWidth = 3.5;
          ctx.beginPath(); ctx.moveTo(bx, -68); ctx.lineTo(bx, -88); ctx.stroke();
          ctx.fillStyle = accentHex;
          ctx.shadowColor = accentHex;
          ctx.shadowBlur = 12;
          ctx.beginPath(); ctx.arc(bx, -91, 5, 0, Math.PI * 2); ctx.fill();
        }
        // Central energized lightning bolt
        ctx.fillStyle = accentHex;
        ctx.beginPath();
        ctx.moveTo(4, -46); ctx.lineTo(-12, -26); ctx.lineTo(-1, -26);
        ctx.lineTo(-7, -8); ctx.lineTo(13, -30); ctx.lineTo(2, -30);
        ctx.closePath();
        ctx.fill();
      } else if (landmark === "survey_vessel") {
        // Ocean cable-laying / survey ship with bow wake and rotating radar mast
        ctx.save();
        ctx.translate(0, -18);
        if (angleDeg) ctx.rotate((angleDeg * Math.PI) / 180);
        // Subtle ocean wake V behind stern
        ctx.strokeStyle = "rgba(124, 224, 249, 0.55)";
        ctx.lineWidth = 2.6;
        ctx.beginPath();
        ctx.moveTo(-44, 4); ctx.lineTo(-74, -12);
        ctx.moveTo(-44, 10); ctx.lineTo(-74, 26);
        ctx.stroke();
        // Hull
        ctx.fillStyle = fillHex === "#94A3B8" ? "#0F172A" : fillHex;
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 2.8;
        ctx.beginPath();
        ctx.moveTo(-48, 12);
        ctx.lineTo(36, 12);
        ctx.lineTo(58, -4);
        ctx.lineTo(44, -10);
        ctx.lineTo(-44, -10);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        // Superstructure & bridge
        ctx.fillStyle = "#F8FAFC";
        ctx.fillRect(-16, -26, 36, 16);
        ctx.fillStyle = "#38BDF8";
        ctx.fillRect(6, -22, 11, 6);
        // Cable reel drum on stern deck
        ctx.fillStyle = accentHex;
        ctx.beginPath();
        ctx.arc(-30, -16, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#0F172A";
        ctx.lineWidth = 2;
        ctx.stroke();
        // Mast + radar ping dot
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(-2, -26); ctx.lineTo(-2, -44); ctx.stroke();
        ctx.fillStyle = accentHex;
        ctx.beginPath(); ctx.arc(-2, -46, 4, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      } else if (landmark === "gavel") {
        // Editorial permit/leverage gavel with strike base and subtle impact ring
        const strike = Math.sin(clamp(riseProgress, 0, 1) * Math.PI * 0.5);
        const swingAng = lerp(-0.58, 0.06, strike);
        // Sound block base
        ctx.fillStyle = "#451A03";
        ctx.strokeStyle = rimHex;
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.roundRect(-34, -16, 68, 14, 4);
        ctx.fill();
        ctx.stroke();
        // Swinging hammer
        ctx.save();
        ctx.translate(22, -22);
        ctx.rotate(swingAng);
        // Handle
        ctx.fillStyle = "#B45309";
        ctx.strokeStyle = "#FEF3C7";
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.roundRect(-42, -5, 76, 10, 4);
        ctx.fill();
        ctx.stroke();
        // Head
        ctx.fillStyle = fillHex === "#94A3B8" ? "#F59E0B" : fillHex;
        ctx.beginPath();
        ctx.roundRect(-52, -24, 24, 48, 5);
        ctx.fill();
        ctx.strokeStyle = accentHex;
        ctx.lineWidth = 2.8;
        ctx.stroke();
        ctx.restore();
      } else {
        // Generic monument spire
        ctx.fillStyle = fillHex;
        ctx.beginPath();
        ctx.moveTo(-16, 0);
        ctx.lineTo(-9, -155);
        ctx.lineTo(0, -195);
        ctx.lineTo(9, -155);
        ctx.lineTo(16, 0);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
    }

    function drawShadedCloud(x, y, radiusPx, alpha, tLocal, seed = 1, shadowDx = 14, shadowDy = 36) {
      if (alpha <= 0.005 || radiusPx <= 2) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      const s = radiusPx / 90;
      ctx.scale(s, s);
      // Soft elongated ground shadow cast clearly beneath cloud onto terrain
      ctx.save();
      ctx.translate(shadowDx, shadowDy);
      ctx.scale(1.55, 0.42);
      const sh = ctx.createRadialGradient(0, 0, 10, 0, 0, 105);
      sh.addColorStop(0, "rgba(2, 10, 14, 0.62)");
      sh.addColorStop(0.55, "rgba(2, 10, 14, 0.28)");
      sh.addColorStop(1, "rgba(2, 10, 14, 0)");
      ctx.fillStyle = sh;
      ctx.beginPath();
      ctx.arc(0, 0, 105, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Elongated realistic cumulus/stratocumulus silhouette (wider than tall, crisp sunlit tops)
      ctx.save();
      ctx.scale(1.22, 0.56);
      const puffs = [
        [-84, 14, 38, 0.86], [-48, -14, 52, 0.95], [-6, -24, 62, 0.99],
        [40, -14, 54, 0.96], [78, 8, 42, 0.88], [-24, 16, 48, 0.94],
        [24, 16, 46, 0.92], [102, 18, 28, 0.78],
      ];
      for (let i = 0; i < puffs.length; i++) {
        const [px, py, pr, pa] = puffs[i];
        const jx = Math.sin(seed * 7.1 + i * 2.3 + tLocal * 1.1) * 3.5;
        const jy = Math.cos(seed * 5.3 + i * 1.9 + tLocal * 0.8) * 2.2;
        const cx = px + jx, cy = py + jy;
        const g = ctx.createRadialGradient(cx - pr * 0.22, cy - pr * 0.36, pr * 0.12, cx, cy, pr);
        g.addColorStop(0, "rgba(255, 255, 255, " + pa + ")");
        g.addColorStop(0.56, "rgba(238, 244, 249, " + (pa * 0.95) + ")");
        g.addColorStop(0.84, "rgba(176, 192, 204, " + (pa * 0.58) + ")");
        g.addColorStop(1, "rgba(142, 162, 178, 0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(cx, cy, pr, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
      ctx.restore();
    }

    function samplePolylineCoord(coords, u) {
      if (!coords || coords.length === 0) return [0, 0];
      if (coords.length === 1) return coords[0];
      const p = clamp(u, 0, 1);
      const segLens = [];
      let total = 0;
      for (let i = 1; i < coords.length; i++) {
        const d = Math.hypot(coords[i][0] - coords[i - 1][0], coords[i][1] - coords[i - 1][1]);
        segLens.push(d);
        total += d;
      }
      if (total <= 1e-6) return coords[0];
      const target = total * p;
      let acc = 0;
      for (let i = 0; i < segLens.length; i++) {
        if (acc + segLens[i] >= target || i === segLens.length - 1) {
          const f = segLens[i] > 1e-6 ? clamp((target - acc) / segLens[i], 0, 1) : 0;
          return [
            lerp(coords[i][0], coords[i + 1][0], f),
            lerp(coords[i][1], coords[i + 1][1], f),
          ];
        }
        acc += segLens[i];
      }
      return coords[coords.length - 1];
    }

    function drawWindStreamline(coords, headU, tailFrac, { widthPx = 4.5, color = "#FFFFFF", glowHex = "#7CE0F9", alpha = 1.0 } = {}) {
      if (alpha <= 0.005 || !coords || coords.length < 2) return;
      const u1 = clamp(headU, 0, 1 + tailFrac);
      const u0 = u1 - tailFrac;
      const segStart = clamp(u0, 0, 1);
      const segEnd = clamp(u1, 0, 1);
      if (segEnd - segStart <= 0.005) return;
      const steps = 28;
      const pts = [];
      for (let i = 0; i <= steps; i++) {
        const u = lerp(segStart, segEnd, i / steps);
        const c = samplePolylineCoord(coords, u);
        const pt = projectPointSafe(c);
        if (pt) pts.push(pt);
      }
      if (pts.length < 2) return;
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (let i = 1; i < pts.length; i++) {
        const frac = i / (pts.length - 1);
        const taper = Math.sin(frac * Math.PI);
        const segAlpha = alpha * Math.pow(frac, 0.8) * (0.25 + 0.75 * taper);
        if (segAlpha <= 0.01) continue;
        ctx.strokeStyle = rgbaStr(color, segAlpha);
        ctx.lineWidth = Math.max(1.2, widthPx * (0.28 + 0.72 * taper));
        ctx.shadowColor = glowHex || color;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.moveTo(pts[i - 1].x, pts[i - 1].y);
        ctx.lineTo(pts[i].x, pts[i].y);
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawProhibitionPin(x, y, radiusPx, iconKind, popScale, slashProgress, alpha) {
      if (alpha <= 0.005 || popScale <= 0.01) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(popScale, popScale);
      ctx.globalAlpha = alpha;
      const r = radiusPx;
      // Anchor is at the bottom tip of the teardrop pin (0, 0)
      const cy = -r * 1.24;

      // Ground drop shadow
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,0.38)";
      ctx.beginPath();
      ctx.ellipse(0, 3, r * 0.44, r * 0.16, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // White teardrop pin body
      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,0.45)";
      ctx.shadowBlur = 14;
      ctx.shadowOffsetY = 4;
      ctx.fillStyle = "#FFFFFF";
      ctx.beginPath();
      ctx.arc(0, cy, r, Math.PI * 0.22, Math.PI * 0.78, true);
      ctx.lineTo(0, 0);
      ctx.closePath();
      ctx.fill();
      ctx.restore();

      // Inner domain icon
      ctx.save();
      ctx.translate(0, cy);
      if (iconKind === "water_drop") {
        // Glossy hydro-blue raindrop
        const dg = ctx.createLinearGradient(-r * 0.3, -r * 0.55, r * 0.35, r * 0.55);
        dg.addColorStop(0, "#38BDF8");
        dg.addColorStop(1, "#0284C7");
        ctx.fillStyle = dg;
        ctx.beginPath();
        ctx.moveTo(0, -r * 0.56);
        ctx.bezierCurveTo(r * 0.46, -r * 0.04, r * 0.48, r * 0.50, 0, r * 0.54);
        ctx.bezierCurveTo(-r * 0.48, r * 0.50, -r * 0.46, -r * 0.04, 0, -r * 0.56);
        ctx.closePath();
        ctx.fill();
        // Specular highlight
        ctx.fillStyle = "rgba(255,255,255,0.68)";
        ctx.beginPath();
        ctx.ellipse(-r * 0.14, r * 0.06, r * 0.08, r * 0.17, -0.35, 0, Math.PI * 2);
        ctx.fill();
      } else if (iconKind === "wheat_crop") {
        // Golden wheat stalks sprouting from dark soil mound
        ctx.fillStyle = "#F59E0B";
        ctx.strokeStyle = "#D97706";
        ctx.lineWidth = Math.max(1.5, r * 0.06);
        const stalks = [-0.28, -0.10, 0.10, 0.28];
        for (const sx of stalks) {
          const topY = -r * (0.48 - Math.abs(sx) * 0.35);
          ctx.beginPath();
          ctx.moveTo(sx * r, r * 0.24);
          ctx.quadraticCurveTo(sx * r * 1.15, topY * 0.5, sx * r * 1.25, topY);
          ctx.stroke();
          // Wheat grains
          for (let g = 0; g < 3; g++) {
            const gy = lerp(topY + r * 0.06, r * 0.06, g / 2.4);
            const gx = sx * r * (1.22 - g * 0.06);
            ctx.beginPath();
            ctx.ellipse(gx, gy, r * 0.085, r * 0.13, sx * 0.8, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        // Rich soil mound at bottom
        ctx.fillStyle = "#5C3A21";
        ctx.beginPath();
        ctx.arc(0, r * 0.42, r * 0.56, Math.PI * 1.12, Math.PI * 1.88, false);
        ctx.quadraticCurveTo(0, r * 0.60, -r * 0.50, r * 0.22);
        ctx.closePath();
        ctx.fill();
      } else {
        // Fallback geometric circle emblem
        ctx.fillStyle = "#3B82F6";
        ctx.beginPath();
        ctx.arc(0, 0, r * 0.45, 0, Math.PI * 2);
        ctx.fill();
      }

      // Stage 2: Animated crimson prohibition ring + diagonal slash
      if (slashProgress > 0.01) {
        const sp = clamp(slashProgress, 0, 1);
        const ringP = clamp(sp / 0.65, 0, 1);
        const barP = clamp((sp - 0.30) / 0.70, 0, 1);
        ctx.strokeStyle = "#DC2626";
        ctx.lineWidth = Math.max(4, r * 0.19);
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(0, 0, r * 0.86, -Math.PI * 0.75, -Math.PI * 0.75 + Math.PI * 2 * ringP);
        ctx.stroke();
        if (barP > 0.01) {
          const d = r * 0.62;
          ctx.beginPath();
          ctx.moveTo(-d, -d);
          ctx.lineTo(lerp(-d, d, barP), lerp(-d, d, barP));
          ctx.stroke();
        }
      }
      ctx.restore();
      ctx.restore();
    }

    function drawCrimsonX(x, y, size, alpha) {
      if (alpha <= 0.005 || size <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      const g = ctx.createRadialGradient(0, 0, size * 0.1, 0, 0, size * 2.0);
      g.addColorStop(0, "rgba(239, 44, 44, 0.9)");
      g.addColorStop(0.45, "rgba(220, 38, 38, 0.45)");
      g.addColorStop(1, "rgba(220, 38, 38, 0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(0, 0, size * 2.0, 0, Math.PI * 2); ctx.fill();
      ctx.lineCap = "round";
      for (const [col, w, a] of [["#DC2626", size * 0.36, 0.9], ["#FFFFFF", size * 0.2, 1.0]]) {
        ctx.strokeStyle = col; ctx.lineWidth = w; ctx.globalAlpha = alpha * a;
        ctx.beginPath();
        ctx.moveTo(-size * 0.48, -size * 0.48); ctx.lineTo(size * 0.48, size * 0.48);
        ctx.moveTo(size * 0.48, -size * 0.48); ctx.lineTo(-size * 0.48, size * 0.48);
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawSkull(x, y, r, alpha, { rotRad = 0, pitchScale = 1.0 } = {}) {
      if (alpha <= 0.005 || r <= 2) return;
      ctx.save();
      ctx.translate(x, y);
      if (pitchScale < 0.999) ctx.scale(1, Math.max(0.45, pitchScale));
      if (rotRad) ctx.rotate(rotRad);
      ctx.globalAlpha = alpha;
      // Warm neon crimson outer bloom fused with crimson territory polygon
      ctx.shadowColor = "#FF2E4C";
      ctx.shadowBlur = Math.max(8, r * 0.42);
      ctx.strokeStyle = "#FFD6DC";
      ctx.lineWidth = r * 0.22;
      ctx.lineCap = "round";
      const bx = r * 0.95, by = r * 0.72, yOff = r * 0.26;
      for (const [x1, y1, x2, y2] of [[-bx, yOff - by * 0.4, bx, yOff + by * 0.65], [bx, yOff - by * 0.4, -bx, yOff + by * 0.65]]) {
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        ctx.fillStyle = "#FFD6DC";
        for (const [kx, ky] of [[x1, y1], [x2, y2]]) {
          ctx.beginPath(); ctx.arc(kx, ky - r * 0.08, r * 0.12, 0, Math.PI * 2); ctx.arc(kx, ky + r * 0.08, r * 0.12, 0, Math.PI * 2); ctx.fill();
        }
      }
      ctx.fillStyle = "#FFE4E6";
      ctx.beginPath();
      ctx.arc(0, -r * 0.22, r * 0.66, Math.PI * 0.85, Math.PI * 2.15);
      ctx.lineTo(r * 0.45, r * 0.22);
      ctx.quadraticCurveTo(r * 0.42, r * 0.50, r * 0.28, r * 0.52);
      ctx.lineTo(-r * 0.28, r * 0.52);
      ctx.quadraticCurveTo(-r * 0.42, r * 0.50, -r * 0.45, r * 0.22);
      ctx.closePath();
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#7F1D1D";
      ctx.beginPath();
      ctx.ellipse(-r * 0.24, -r * 0.12, r * 0.18, r * 0.16, -0.15, 0, Math.PI * 2);
      ctx.ellipse(r * 0.24, -r * 0.12, r * 0.18, r * 0.16, 0.15, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath(); ctx.moveTo(0, r * 0.02); ctx.lineTo(-r * 0.09, r * 0.20); ctx.lineTo(r * 0.09, r * 0.20); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = "#7F1D1D"; ctx.lineWidth = Math.max(1.5, r * 0.055);
      for (const tx of [-0.14, 0, 0.14]) { ctx.beginPath(); ctx.moveTo(r * tx, r * 0.34); ctx.lineTo(r * tx, r * 0.52); ctx.stroke(); }
      ctx.restore();
    }

    function drawTeardropPin(x, y, r, kind, alpha, badgeColor = "#DC2626") {
      if (alpha <= 0.005 || r <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      // Anchor at bottom tip (0,0), center of circular head at (0, -r * 1.35)
      const cy = -r * 1.25;
      ctx.shadowColor = "rgba(0,0,0,0.45)";
      ctx.shadowBlur = 18;
      ctx.fillStyle = "#FFFFFF";
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.bezierCurveTo(-r * 0.52, -r * 0.62, -r, -r * 0.88, -r, cy);
      ctx.arc(0, cy, r, Math.PI, 0, false);
      ctx.bezierCurveTo(r, -r * 0.88, r * 0.52, -r * 0.62, 0, 0);
      ctx.closePath();
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = badgeColor;
      ctx.lineWidth = Math.max(5, r * 0.12);
      ctx.stroke();

      ctx.translate(0, cy);
      ctx.fillStyle = badgeColor;
      ctx.strokeStyle = badgeColor;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (kind === "snake") {
        ctx.lineWidth = r * 0.18;
        ctx.beginPath();
        ctx.moveTo(-r * 0.42, r * 0.40);
        ctx.bezierCurveTo(-r * 0.55, 0, r * 0.55, r * 0.36, r * 0.36, -r * 0.05);
        ctx.bezierCurveTo(r * 0.24, -r * 0.44, -r * 0.40, -r * 0.26, -r * 0.10, -r * 0.46);
        ctx.stroke();
        ctx.beginPath(); ctx.arc(r * 0.06, -r * 0.48, r * 0.16, 0, Math.PI * 2); ctx.fill();
      } else if (kind === "jaguar") {
        ctx.beginPath(); ctx.arc(0, r * 0.06, r * 0.44, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(-r * 0.34, -r * 0.32, r * 0.16, 0, Math.PI * 2); ctx.arc(r * 0.34, -r * 0.32, r * 0.16, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#FFFFFF";
        ctx.beginPath(); ctx.ellipse(-r * 0.16, -r * 0.02, r * 0.08, r * 0.05, 0.2, 0, Math.PI * 2); ctx.ellipse(r * 0.16, -r * 0.02, r * 0.08, r * 0.05, -0.2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.moveTo(0, r * 0.08); ctx.lineTo(-r * 0.09, r * 0.22); ctx.lineTo(r * 0.09, r * 0.22); ctx.closePath(); ctx.fill();
      } else if (kind === "mosquito") {
        ctx.lineWidth = r * 0.08;
        ctx.beginPath(); ctx.ellipse(0, 0, r * 0.12, r * 0.42, 0.35, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(-r * 0.30, -r * 0.12, r * 0.30, r * 0.11, -0.35, 0, Math.PI * 2); ctx.ellipse(r * 0.30, -r * 0.12, r * 0.30, r * 0.11, 0.35, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath();
        ctx.moveTo(r * 0.18, -r * 0.34); ctx.lineTo(r * 0.48, -r * 0.56);
        ctx.moveTo(-r * 0.10, r * 0.18); ctx.lineTo(-r * 0.48, r * 0.44);
        ctx.moveTo(r * 0.10, r * 0.18); ctx.lineTo(r * 0.48, r * 0.46);
        ctx.stroke();
      } else {
        ctx.beginPath(); ctx.arc(0, r * 0.14, r * 0.26, 0, Math.PI * 2); ctx.arc(0, -r * 0.22, r * 0.17, 0, Math.PI * 2); ctx.fill();
        ctx.lineWidth = r * 0.07;
        for (const s of [-1, 1]) {
          for (const dy of [-0.28, -0.06, 0.16, 0.38]) {
            ctx.beginPath(); ctx.moveTo(s * r * 0.18, r * dy * 0.6); ctx.lineTo(s * r * 0.44, r * (dy - 0.14)); ctx.lineTo(s * r * 0.58, r * (dy + 0.12)); ctx.stroke();
          }
        }
      }
      ctx.restore();
    }

    function drawNoPoliceBadge(x, y, r, alpha) {
      if (alpha <= 0.005 || r <= 1) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      const g = ctx.createRadialGradient(0, 0, r * 0.72, 0, 0, r * 1.5);
      g.addColorStop(0, "rgba(220, 38, 38, 0.72)");
      g.addColorStop(1, "rgba(220, 38, 38, 0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(0, 0, r * 1.5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#FFFFFF";
      ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#B91C1C";
      ctx.lineWidth = Math.max(4, r * 0.065);
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(-r * 0.42, -r * 0.44); ctx.lineTo(-r * 0.26, -r * 0.68); ctx.lineTo(0, -r * 0.76);
      ctx.lineTo(r * 0.26, -r * 0.68); ctx.lineTo(r * 0.42, -r * 0.44); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-r * 0.36, -r * 0.38); ctx.quadraticCurveTo(0, -r * 0.30, r * 0.36, -r * 0.38); ctx.stroke();
      ctx.beginPath(); ctx.arc(0, -r * 0.16, r * 0.24, 0, Math.PI); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-r * 0.56, r * 0.62); ctx.quadraticCurveTo(-r * 0.52, r * 0.16, -r * 0.18, r * 0.10);
      ctx.lineTo(0, r * 0.28); ctx.lineTo(r * 0.18, r * 0.10); ctx.quadraticCurveTo(r * 0.52, r * 0.16, r * 0.56, r * 0.62); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, r * 0.28); ctx.lineTo(0, r * 0.62); ctx.stroke();
      ctx.beginPath(); ctx.arc(r * 0.28, r * 0.40, r * 0.09, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = "#DC2626";
      ctx.lineWidth = Math.max(8, r * 0.15);
      ctx.beginPath(); ctx.arc(0, 0, r * 0.94, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(-r * 0.66, -r * 0.66); ctx.lineTo(r * 0.66, r * 0.66); ctx.stroke();
      ctx.restore();
    }

    function drawDoubleArrow(p1, p2, labelText, progress, alpha) {
      if (alpha <= 0.005 || progress <= 0.01) return;
      const mx = (p1.x + p2.x) * 0.5, my = (p1.y + p2.y) * 0.5;
      const dx = p2.x - p1.x, dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy);
      const ang = Math.atan2(dy, dx);
      const half = (len * 0.5) * clamp(progress, 0, 1);
      ctx.save();
      ctx.translate(mx, my);
      ctx.rotate(ang);
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = "#FFFFFF";
      ctx.fillStyle = "#FFFFFF";
      ctx.shadowColor = "rgba(0,0,0,0.88)";
      ctx.shadowBlur = 14;
      ctx.lineWidth = Math.max(5, len * 0.015);
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(-half + 14, 0); ctx.lineTo(half - 14, 0); ctx.stroke();
      const ah = Math.max(18, len * 0.048);
      for (const s of [-1, 1]) {
        ctx.beginPath();
        ctx.moveTo(s * half, 0);
        ctx.lineTo(s * (half - ah), -ah * 0.62);
        ctx.lineTo(s * (half - ah * 0.72), 0);
        ctx.lineTo(s * (half - ah), ah * 0.62);
        ctx.closePath();
        ctx.fill();
      }
      const fSize = Math.max(38, Math.min(130, len * 0.145));
      ctx.font = "800 " + Math.round(fSize) + "px 'Barlow Condensed', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      const ly = -Math.max(16, len * 0.045);
      ctx.save();
      ctx.shadowBlur = 0;
      ctx.strokeStyle = "rgba(3,22,31,0.84)";
      ctx.lineWidth = Math.max(3, fSize * 0.06);
      ctx.lineJoin = "round";
      ctx.strokeText(labelText, 0, ly);
      ctx.restore();
      ctx.fillText(labelText, 0, ly);
      ctx.restore();
    }

    function drawWeatherCloudsRain(cx, cy, scale, alpha, tLocal) {
      if (alpha <= 0.005) return;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(scale, scale);
      ctx.globalAlpha = alpha;

      // Ground shadow cast beneath cloud cluster onto map relief
      const sh = ctx.createRadialGradient(18, 42, 20, 18, 42, 230);
      sh.addColorStop(0, "rgba(2, 12, 16, 0.52)");
      sh.addColorStop(0.65, "rgba(2, 12, 16, 0.24)");
      sh.addColorStop(1, "rgba(2, 12, 16, 0)");
      ctx.fillStyle = sh;
      ctx.beginPath(); ctx.arc(18, 42, 230, 0, Math.PI * 2); ctx.fill();

      // Parallax diagonal rain streaks
      ctx.strokeStyle = "rgba(215, 244, 255, 0.58)";
      ctx.lineWidth = 2.6;
      ctx.lineCap = "round";
      for (let i = 0; i < 48; i++) {
        const rx = ((i * 73) % 360) - 180;
        const speed = 340 + (i % 5) * 48;
        const ry = ((tLocal * speed + i * 53) % 360) - 45;
        ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(rx - 15, ry + 38); ctx.stroke();
      }

      // Multi-puff shaded volumetric clouds
      const puffs = [
        [-102, -96, 72, 0.92], [-26, -128, 92, 0.97], [60, -108, 78, 0.93], [116, -68, 58, 0.88],
        [-118, 22, 76, 0.95], [-36, 2, 98, 0.99], [48, 16, 86, 0.96], [114, 42, 60, 0.89],
        [-58, 96, 66, 0.87], [26, 104, 62, 0.85],
      ];
      for (let idx = 0; idx < puffs.length; idx++) {
        const [px, py, pr, pa] = puffs[idx];
        const dx = Math.sin(tLocal * 1.3 + idx) * 9;
        const dy = Math.cos(tLocal * 1.0 + idx * 0.7) * 4.5;
        const g = ctx.createRadialGradient(px + dx - pr * 0.28, py + dy - pr * 0.32, pr * 0.1, px + dx, py + dy, pr);
        g.addColorStop(0, "rgba(255, 255, 255, " + pa + ")");
        g.addColorStop(0.62, "rgba(232, 240, 245, " + (pa * 0.92) + ")");
        g.addColorStop(1, "rgba(168, 188, 200, 0)");
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(px + dx, py + dy, pr, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }

    function drawJungleEmojiEnding(tLocal, gagAt = 1.12) {
      const canopyP = easeOutExpo(seg(tLocal, 0.0, 0.45));
      const emojiP = easeOutBack(seg(tLocal, 0.18, 0.55));
      const gagP = easeOutExpo(seg(tLocal, gagAt, gagAt + 0.32));

      ctx.save();
      const drawCanopyCluster = (baseY, dirSign, colors) => {
        ctx.save();
        ctx.translate(0, baseY);
        for (let layer = 0; layer < colors.length; layer++) {
          for (let i = -2; i <= 20; i++) {
            const cx = i * 58 + (layer % 2) * 29;
            const cy = dirSign * (32 + layer * 72 + Math.sin(i * 2.5 + layer * 1.7) * 34);
            const rx = 56 + ((i * 19 + layer * 13) % 34);
            const ry = 38 + ((i * 11 + layer * 7) % 24);
            const g = ctx.createRadialGradient(cx - rx * 0.2, cy - ry * 0.3, 6, cx, cy, rx);
            g.addColorStop(0, colors[layer][0]);
            g.addColorStop(1, colors[layer][1]);
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.ellipse(cx, cy, rx, ry, ((i + layer) % 5 - 2) * 0.28, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        ctx.restore();
      };

      const topPal = [["#143A18", "#0A200D"], ["#1F5621", "#103213"], ["#2F7428", "#17421A"], ["#439432", "#20591F"], ["#5CB33F", "#2D7127"]];
      drawCanopyCluster(lerp(-440, 0, canopyP), 1, topPal);

      // Bottom trunks + canopy
      const botOff = lerp(540, 0, canopyP);
      ctx.save();
      ctx.translate(0, botOff);
      ctx.fillStyle = "#3E2616";
      for (const [tx, tw] of [[85, 42], [290, 34], [540, 48], [810, 36], [985, 44]]) {
        ctx.fillRect(tx - tw / 2, H - 360, tw, 380);
      }
      ctx.restore();
      drawCanopyCluster(H + botOff - 10, -1, topPal);

      if (emojiP > 0.01) {
        const ex = W * 0.5, ey = H * 0.43;
        const r = 138 * clamp(emojiP, 0, 1.15);
        ctx.save();
        ctx.translate(ex, ey);
        ctx.shadowColor = "rgba(0,0,0,0.58)";
        ctx.shadowBlur = 32;
        const eg = ctx.createRadialGradient(-r * 0.28, -r * 0.28, r * 0.08, 0, 0, r);
        eg.addColorStop(0, "#FFF078");
        eg.addColorStop(0.7, "#FACC15");
        eg.addColorStop(1, "#D97706");
        ctx.fillStyle = eg;
        ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = "#92400E"; ctx.lineWidth = 4; ctx.stroke();

        for (const sx of [-1, 1]) {
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath(); ctx.arc(sx * r * 0.34, -r * 0.16, r * 0.24, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = "#78350F"; ctx.lineWidth = 3; ctx.stroke();
          ctx.fillStyle = "#111827";
          ctx.beginPath(); ctx.arc(sx * r * 0.30, -r * 0.14, r * 0.095, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = "#78350F"; ctx.lineWidth = 7; ctx.lineCap = "round";
          ctx.beginPath(); ctx.moveTo(sx * r * 0.14, -r * 0.48); ctx.lineTo(sx * r * 0.52, -r * 0.38); ctx.stroke();
        }
        ctx.strokeStyle = "#78350F"; ctx.lineWidth = 8; ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(-r * 0.38, r * 0.32);
        ctx.quadraticCurveTo(-r * 0.20, r * 0.18, 0, r * 0.32);
        ctx.quadraticCurveTo(r * 0.20, r * 0.44, r * 0.38, r * 0.30);
        ctx.stroke();

        if (gagP > 0.01) {
          const gx = lerp(380, 18, gagP);
          ctx.save();
          ctx.translate(gx, r * 0.28);
          ctx.fillStyle = "#0F1115";
          ctx.shadowColor = "rgba(0,0,0,0.68)";
          ctx.shadowBlur = 18;
          ctx.beginPath(); ctx.roundRect(-r * 0.64, -r * 0.26, r * 1.52, r * 0.54, r * 0.24); ctx.fill();
          ctx.strokeStyle = "#374151"; ctx.lineWidth = 3;
          for (const fy of [-0.11, 0.04, 0.18]) { ctx.beginPath(); ctx.moveTo(-r * 0.58, r * fy); ctx.lineTo(r * 0.18, r * fy); ctx.stroke(); }
          ctx.restore();
        }
        ctx.restore();
      }
      ctx.restore();
    }

    function drawLayers(layers, t) {
      ctx.setTransform(OV_SCALE, 0, 0, OV_SCALE, 0, 0);
      ctx.clearRect(0, 0, W, H);
      for (const layer of layers || []) {
        const tStart = layer.start_s ?? 0;
        const tEnd = layer.end_s ?? 1e9;
        if (t < tStart - 0.001 || t > tEnd + 0.001) continue;
        const tLoc = t - tStart;
        const fadeIn = layer.fade_in_s ? easeOutCubic(seg(t, tStart, tStart + layer.fade_in_s)) : 1;
        const fadeOut = layer.fade_out_s ? 1 - easeInCubic(seg(t, tEnd - layer.fade_out_s, tEnd)) : 1;
        const baseAlpha = clamp(fadeIn * fadeOut * (layer.opacity ?? 1), 0, 1);

        if (layer.type === "polygon") {
          const geom = resolveGeom(layer.geom_ref);
          let fillHex = layer.fill_hex || "#16A82A";
          let rimHex = layer.rim_hex || "#F4F1EA";
          let bloomHex = layer.bloom_hex || "#22C55E";
          let rimWidth = layer.rim_width ?? 3.0;
          let bloomScale = layer.bloom_scale ?? 1.0;
          let fillAlpha = layer.fill_alpha ?? 0.72;
          if (layer.morph) {
            const m = easeInOutCubic(seg(t, layer.morph.start_s, layer.morph.end_s));
            fillHex = mixHex(fillHex, layer.morph.fill_hex, m);
            if (layer.morph.rim_hex) rimHex = mixHex(rimHex, layer.morph.rim_hex, m);
            if (layer.morph.bloom_hex) bloomHex = mixHex(bloomHex, layer.morph.bloom_hex, m);
            if (layer.morph.rim_width != null) rimWidth = lerp(rimWidth, layer.morph.rim_width, m);
            if (layer.morph.bloom_scale != null) bloomScale = lerp(bloomScale, layer.morph.bloom_scale, m);
            if (layer.morph.fill_alpha != null) fillAlpha = lerp(fillAlpha, layer.morph.fill_alpha, m);
          }
          const borderReveal = layer.border_draw_s
            ? easeOutCubic(seg(t, tStart + (layer.border_delay_s ?? 0), tStart + (layer.border_delay_s ?? 0) + layer.border_draw_s))
            : 1.0;
          // Border trace: exterior rim traces in Web Mercator space, overlapping fill entry at 75%.
          const traceS = Number(layer.border_trace_s || 0);
          const traced = traceS > 0;
          const traceStartS = tStart + (layer.border_trace_delay_s ?? 0);
          const traceEndS = traceStartS + traceS;
          let traceProgress = 1.0;
          if (traced) {
            const u = seg(t, traceStartS, traceEndS);
            const ease = layer.border_trace_ease || "editorial_out";
            traceProgress = evalEase(ease, u);
            const traceHex = layer.border_trace_hex || rimHex;
            const traceWidth = layer.border_trace_width ?? rimWidth;
            const settleS = layer.border_trace_settle_s ?? 0;
            const settle = settleS > 0 ? easeInOutCubic(seg(t, traceEndS, traceEndS + settleS)) : (t >= traceEndS ? 1 : 0);
            if (traceHex !== rimHex) rimHex = mixHex(traceHex, rimHex, settle);
            rimWidth = lerp(traceWidth, rimWidth, settle);
          }
          const fillStartS = layer.fill_delay_s != null
            ? tStart + layer.fill_delay_s
            : (traced ? traceStartS + traceS * 0.75 : tStart);
          const fillDrawS = layer.fill_draw_s ?? (traced ? 0.45 : 0);
          const fillReveal = fillDrawS > 0
            ? editorialOut(seg(t, fillStartS, fillStartS + fillDrawS))
            : (!traced && layer.fill_delay_s == null ? 1.0 : (t >= fillStartS - 0.001 ? 1.0 : 0.0));
          const fillBloomOvershoot = layer.fill_bloom_overshoot != null
            ? clamp(Number(layer.fill_bloom_overshoot), 1.0, 1.6)
            : (traced || fillDrawS > 0 ? 1.18 : 1.0);
          const flagCode = layer.flag_fill ? String(layer.flag_fill).toLowerCase() : null;
          const flagImg = flagCode ? (window.__imgCache[BASE_URL + "/flags/" + flagCode + ".svg"] || null) : null;
          const fillRevealMode = (flagCode ? layer.flag_reveal : null) || layer.fill_reveal_mode || "fade";
          const blendMap = { normal: "source-over", multiply: "multiply", overlay: "overlay", "soft-light": "soft-light", screen: "screen" };
          const flagBlend = blendMap[layer.flag_blend || "normal"] || "source-over";
          const waveAmp = layer.flag_wave === true ? 0.22 : Number(layer.flag_wave) || 0;
          const waveWarp = layer.flag_wave_warp === false
            ? 0
            : (layer.flag_wave_warp === true
              ? 0.036
              : (layer.flag_wave_warp != null ? Number(layer.flag_wave_warp) : (waveAmp > 0 ? 0.036 : 0)));
          const waveGloss = layer.flag_gloss === false
            ? 0
            : (layer.flag_gloss === true
              ? 0.48
              : (layer.flag_gloss != null ? Number(layer.flag_gloss) : (waveAmp > 0 ? 0.48 : 0)));
          const flagWave = waveAmp > 0
            ? {
                amplitude: waveAmp,
                cycles: layer.flag_wave_cycles ?? 2.5,
                speed: layer.flag_wave_speed ?? 0.5,
                angleDeg: layer.flag_wave_angle_deg ?? 20,
                warp: waveWarp,
                gloss: waveGloss,
              }
            : null;
          const revealProgress = layer.reveal_duration_s
            ? easeInOutCubic(seg(t, tStart + (layer.reveal_delay_s ?? 0), tStart + (layer.reveal_delay_s ?? 0) + layer.reveal_duration_s))
            : 1.0;
          const perimeterProgress = layer.perimeter_draw_s
            ? easeOutCubic(seg(t, tStart + (layer.perimeter_delay_s ?? 0), tStart + (layer.perimeter_delay_s ?? 0) + layer.perimeter_draw_s))
            : 1.0;

          // Progressive world-space / contour hatch timing
          const hatchRevealMode = layer.hatch_reveal_mode || (Number(layer.hatch_draw_s || 0) > 0 ? "staggered_draw" : "fade");
          const hatchDrawS = layer.hatch_draw_s != null
            ? Math.max(0, Number(layer.hatch_draw_s) || 0)
            : (hatchRevealMode !== "fade" ? 0.75 : 0);
          const hatchStartS = fillStartS + (layer.hatch_delay_s != null ? Number(layer.hatch_delay_s) : (hatchDrawS > 0 ? 0.08 : 0));
          const hatchProgress = hatchDrawS > 0
            ? seg(t, hatchStartS, hatchStartS + hatchDrawS)
            : (t >= hatchStartS - 0.001 ? 1.0 : 0.0);

          // Optional 2.5D tactile lift & inner bevel
          const liftPx = Math.max(0, Number(layer.lift_px || 0));
          const liftStartS = fillStartS + (layer.lift_delay_s ?? 0);
          const liftDurS = layer.lift_duration_s ?? (liftPx > 0 ? 0.55 : 0);
          const liftProgress = liftDurS > 0
            ? evalEase(layer.lift_ease || "spring_tactile", seg(t, liftStartS, liftStartS + liftDurS))
            : 1.0;
          const bevelLight = layer.bevel_light === true ? 0.65 : clamp(Number(layer.bevel_light || 0), 0, 1);

          // Optional diagonal specular light sweep (opt-in)
          let lightSweep = null;
          if (layer.light_sweep) {
            const lsObj = typeof layer.light_sweep === "object" ? layer.light_sweep : {};
            const lsAt = lsObj.at_s != null
              ? Number(lsObj.at_s)
              : (fillStartS + fillDrawS + Number(lsObj.delay_s ?? 0.08));
            const lsDur = Math.max(0.08, Number(lsObj.duration_s ?? 0.65));
            if (t >= lsAt && t <= lsAt + lsDur) {
              lightSweep = {
                progress: easeInOutCubic(seg(t, lsAt, lsAt + lsDur)),
                angleDeg: lsObj.angle_deg ?? 32,
                color: lsObj.color || "#FFFFFF",
                intensity: lsObj.intensity ?? 0.55,
                widthFrac: lsObj.width_frac ?? 0.24,
              };
            }
          }

          // Optional travelling perimeter rim glint (opt-in)
          const rimGlint = layer.rim_glint === true
            ? { speed: 0.22, span_frac: 0.14, color: "#FFFFFF", intensity: 0.85 }
            : (layer.rim_glint && typeof layer.rim_glint === "object" ? layer.rim_glint : null);

          let flashHex = null;
          let flashIntensity = 0;
          for (const fl of layer.flashes || []) {
            const fd = fl.duration_s ?? 0.65;
            if (t >= fl.at_s && t <= fl.at_s + fd) {
              const u = clamp((t - fl.at_s) / fd, 0, 1);
              const val = Math.sin(u * Math.PI) * (fl.intensity ?? 1.0);
              if (val > flashIntensity) {
                flashIntensity = val;
                flashHex = fl.hex || fillHex;
              }
            }
          }
          if (
            layer.dissolve ||
            layer.dissolve_seams ||
            traced ||
            flagCode ||
            fillRevealMode !== "fade" ||
            fillDrawS > 0 ||
            layer.fill_delay_s != null ||
            Boolean(layer.border_draw_s) ||
            Boolean(layer.reveal_axis) ||
            Boolean(layer.outline_only) ||
            Boolean(layer.hatch) ||
            liftPx > 0 ||
            Boolean(layer.cast_shadow) ||
            bevelLight > 0 ||
            Boolean(layer.light_sweep) ||
            Boolean(rimGlint) ||
            (Array.isArray(layer.flashes) && layer.flashes.length > 0)
          ) {
            drawDissolvedPolygon(geom, {
              traced,
              traceProgress,
              traceEndS,
              traceHeads: layer.border_trace_heads ?? 2,
              traceStart: layer.border_trace_start || null,
              traceDir: layer.border_trace_dir || "cw",
              traceHeadGlow: Boolean(layer.border_trace_head_glow),
              flagImg,
              flagAlpha: layer.flag_alpha ?? 1.0,
              flagBlend,
              flagRotateDeg: layer.flag_rotate_deg ?? 0,
              flagFit: layer.flag_fit === "cover" ? "cover" : "stretch",
              fillRevealMode,
              fillRevealOrigin: layer.fill_reveal_origin || null,
              fillRevealOrganic: { roughness: layer.fill_reveal_roughness ?? 0.22, seed: layer.fill_reveal_seed ?? 1 },
              fillBloomOvershoot,
              flagWave,
              dissolveSeams: Boolean(layer.dissolve_seams),
              liftPx,
              liftProgress,
              castShadow: layer.cast_shadow ?? null,
              bevelLight,
              lightSweep,
              rimGlint,
              geomKey: typeof layer.geom_ref === "string" ? layer.geom_ref : (layer.id || ""),
              time: t,
              fillHex,
              fillAlpha,
              rimHex,
              rimWidth,
              bloomHex,
              bloomScale,
              alpha: baseAlpha,
              borderReveal,
              fillReveal,
              revealAxis: layer.reveal_axis || null,
              revealProgress,
              revealBounds: layer.reveal_bounds || null,
              outlineOnly: Boolean(layer.outline_only),
              perimeterProgress,
              featherPx: layer.feather_px ?? 0,
              hatch: Boolean(layer.hatch),
              hatchColor: layer.hatch_color || "rgba(255,255,255,0.24)",
              hatchSpacing: layer.hatch_spacing ?? 18,
              hatchWidth: layer.hatch_width ?? 3.5,
              hatchSpace: layer.hatch_space || "world",
              hatchRevealMode,
              hatchProgress,
              hatchStagger: layer.hatch_stagger ?? 0.62,
              hatchDirection: layer.hatch_direction || "ltr",
              hatchAngleDeg: layer.hatch_angle_deg ?? 45,
              hatchEase: layer.hatch_ease || "editorial_out",
              hatchRefZoom: layer.hatch_ref_zoom ?? null,
              hatchCross: Boolean(layer.hatch_cross),
              hatchTipGlow: Boolean(layer.hatch_tip_glow),
              hatchGlowHex: layer.hatch_glow_hex || null,
              flashHex,
              flashIntensity,
            });
          } else {
            drawStandardPolygon(geom, { fillHex, fillAlpha, rimHex, rimWidth, bloomHex, bloomScale, alpha: baseAlpha });
          }
        } else if (layer.type === "route") {
          let coords = resolveGeom(layer.coords_ref) || layer.coords || [];
          if (layer.reverse) coords = [...coords].reverse();
          // Routes draw on by default (0.9 s); "instant: true" shows the whole line at once.
          const drawS = layer.instant === true ? 0 : (layer.draw_duration_s ?? 0.9);
          const drawFrom = tStart + (layer.draw_delay_s ?? 0);
          const drawEase = layer.draw_ease === "linear" ? (x) => x : layer.draw_ease === "in_out" ? easeInOutCubic : easeOutCubic;
          const prog = drawS > 0 ? drawEase(seg(t, drawFrom, drawFrom + drawS)) : (t >= drawFrom - 0.001 ? 1 : 0);
          // Optional world-space width: doubles per zoom level above "width_ref_zoom" (coupling 1).
          const baseWidth = layer.width || 8;
          const widthPx = scaledWidth(
            baseWidth, map.getZoom(), layer.width_ref_zoom ?? null, layer.width_coupling ?? 1.0,
            layer.width_min_scale ?? 0.4, layer.width_max_scale ?? 6
          );
          const dash = layer.dash ? layer.dash.map((d) => d * (widthPx / baseWidth)) : null;
          drawPartialRoute(coords, prog, {
            color: layer.color || layer.hex || "#FDE047",
            bloom: layer.bloom || "#F5C542",
            core: layer.core ?? "#FFFFFF",
            width: widthPx,
            dash,
            alpha: baseAlpha,
            cableCasing: Boolean(layer.cable_casing),
            pulseSpeed: Number(layer.pulse_speed || 0),
            pulseCount: Number(layer.pulse_count || 3),
            pulseColor: layer.pulse_color || "#FFFFFF",
            pulseGlow: layer.pulse_glow || layer.bloom || "#FDE047",
            pulseTailFrac: Number(layer.pulse_tail_frac || 0.12),
            time: tLoc,
          });
          if (layer.beacon_coord) {
            const bA = baseAlpha * easeOutCubic(seg(t, layer.beacon_start_s ?? tStart, (layer.beacon_start_s ?? tStart) + 0.7));
            const bp = bA > 0.01 ? projectPointSafe(layer.beacon_coord) : null;
            if (bp) {
              const bg = ctx.createRadialGradient(bp.x, bp.y, 10, bp.x, bp.y, 130);
              bg.addColorStop(0, "rgba(255,255,255," + (0.95 * bA).toFixed(2) + ")");
              bg.addColorStop(0.35, rgbaStr(layer.beacon_color || "#4ADE80", 0.78 * bA));
              bg.addColorStop(1, "rgba(34,197,94,0)");
              ctx.fillStyle = bg;
              ctx.beginPath(); ctx.arc(bp.x, bp.y, 130, 0, Math.PI * 2); ctx.fill();
            }
          }
        } else if (layer.type === "glow_label") {
          const preset = layer.carto_role ? (CARTO_TYPO_PRESETS[layer.carto_role] || {}) : {};
          const space = layer.space || (layer.ref_zoom != null ? "map_plane" : "world_billboard");
          const useComicBounce = layer.register === "comic" || layer.pop_bounce === true;
          let sc = layer.pop_scale
            ? lerp(
                useComicBounce ? 0.86 : 0.94,
                1.0,
                (useComicBounce ? easeOutBack : easeOutExpo)(seg(t, tStart, tStart + (layer.pop_duration_s ?? 0.30)))
              )
            : 1.0;
          if (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s) {
            sc *= 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd));
          }
          let yFly = 0;
          if (layer.fly_through) {
            const enterP = easeOutExpo(seg(t, tStart, tStart + 0.52));
            const exitP = easeInExpo(seg(t, tEnd - 0.42, tEnd));
            sc = lerp(5.2, 1.0, enterP) * lerp(1.0, 4.8, exitP);
            yFly = lerp(320, 0, enterP) - lerp(0, 220, exitP);
          }
          let displayText = String(layer.text ?? "");
          if (preset.uppercase && !layer.preserve_case) {
            displayText = displayText.toUpperCase();
          }
          let tabularDigits = Boolean(layer.tabular_digits ?? preset.tabularDigits ?? false);
          let typewriterChars = null;
          if (layer.count_to != null) {
            const cStart = tStart + (layer.count_delay_s ?? 0);
            const cDur = layer.count_duration_s ?? 0.85;
            // Critically damped expo-out avoids overshooting numeric metrics past ground truth.
            const cu = easeOutExpo(seg(t, cStart, cStart + cDur));
            const val = Math.round(lerp(layer.count_from ?? 0, layer.count_to, cu));
            displayText = (layer.count_prefix || "") + val.toLocaleString(layer.count_locale || "en-US") + (layer.count_suffix || "");
            tabularDigits = true;
          } else if (layer.typewriter_s) {
            const twStart = tStart + (layer.typewriter_delay_s ?? 0);
            const twU = clamp(seg(t, twStart, twStart + layer.typewriter_s), 0, 1);
            typewriterChars = Math.max(0, Math.round(displayText.length * twU));
          }
          let curCoord = layer.coord;
          if (curCoord && layer.move_to_coord && layer.move_start_s != null) {
            const mu = easeInOutCubic(seg(t, layer.move_start_s, layer.move_start_s + (layer.move_duration_s ?? 0.6)));
            curCoord = [
              lerp(curCoord[0], layer.move_to_coord[0], mu),
              lerp(curCoord[1], layer.move_to_coord[1], mu),
            ];
          }
          let subPill = null;
          if (layer.sub_pill) {
            const spStart = layer.sub_pill.start_s ?? (tStart + (layer.sub_pill.delay_s ?? 0));
            const spEnd = layer.sub_pill.end_s ?? tEnd;
            if (t >= spStart && t <= spEnd) {
              const spEase = useComicBounce ? easeOutBack : easeOutExpo;
              const spIn = lerp(useComicBounce ? 0.82 : 0.94, 1.0, spEase(seg(t, spStart, spStart + (layer.sub_pill.pop_s ?? 0.26))));
              const spOut = layer.sub_pill.fade_out_s ? 1 - seg(t, spEnd - layer.sub_pill.fade_out_s, spEnd) : 1;
              subPill = {
                ...layer.sub_pill,
                alpha: clamp(spOut, 0, 1),
                scale: clamp(spIn, 0, useComicBounce ? 1.12 : 1.0),
              };
            }
          }
          const angDeg = layer.angle_end != null
            ? lerp(layer.angle_start || 0, layer.angle_end, seg(t, tStart, tEnd))
            : (layer.angle || 0);
          const angRad = angDeg * Math.PI / 180;
          const baseFont = layer.font_px || 64;
          let letterSpacing = layer.letter_spacing ?? (preset.letterSpacingEm != null ? (preset.letterSpacingEm + "em") : 0);
          if (layer.tracking_from_em != null && layer.tracking_to_em != null) {
            const trU = easeOutExpo(seg(t, tStart, tStart + (layer.tracking_duration_s ?? 0.9)));
            letterSpacing = lerp(layer.tracking_from_em, layer.tracking_to_em, trU).toFixed(4) + "em";
          }
          const hasExplicitGlow = layer.glow_hex != null || (layer.glow_strength != null && layer.glow_strength !== "none");
          const defaultHaloW = Math.max(1.8, Math.min(4.2, baseFont * (preset.strokeMult ?? 0.045)));
          const textOpts = {
            fill: layer.fill || preset.fill || "#F4F1EA",
            glowHex: hasExplicitGlow ? (layer.glow_hex ?? "#F5C542") : null,
            glowStrength: layer.glow_strength ?? (layer.glow_hex ? "luminous" : (preset.glowStrength ?? "none")),
            angle: angRad,
            scale: sc,
            alpha: baseAlpha,
            family: layer.family || preset.family || "Barlow Condensed",
            weight: layer.weight || preset.weight || 800,
            fontStyle: layer.font_style || preset.fontStyle || "normal",
            letterSpacing,
            strokeHex: layer.stroke_hex ?? preset.strokeHex ?? "rgba(3,22,31,0.80)",
            strokeWidth: layer.stroke_width !== undefined ? layer.stroke_width : defaultHaloW,
            lineHeightMult: layer.line_height_mult ?? 1.08,
            tabularDigits,
            typewriterChars,
            typewriterLeadHex: layer.typewriter_lead_hex || null,
            subPill,
          };
          if (space === "map_plane" && curCoord && !layer.fly_through) {
            const m = getMapPlaneMatrix(curCoord, layer.ref_zoom ?? map.getZoom());
            const mag = Math.hypot(m.a, m.b);
            const minSc = layer.min_scale ?? 0.35;
            const maxSc = layer.max_scale ?? 3.2;
            const clampFactor = mag > 1e-4 ? clamp(mag, minSc, maxSc) / mag : 1.0;
            ctx.save();
            ctx.transform(m.a * clampFactor, m.b * clampFactor, m.c * clampFactor, m.d * clampFactor, m.e, m.f);
            drawGlowingText(displayText, layer.dx || 0, layer.dy || 0, baseFont, textOpts);
            ctx.restore();
          } else if (curCoord) {
            const pt = projectPointSafe(curCoord);
            if (pt) {
              if (layer.ref_zoom != null) {
                const coupling = layer.scale_coupling ?? 0.45;
                const zScale = Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling);
                sc *= clamp(zScale, layer.min_scale ?? 0.45, layer.max_scale ?? 2.4);
                textOpts.scale = sc;
              }
              drawGlowingText(displayText, pt.x + (layer.dx || 0), pt.y + (layer.dy || 0) + yFly, baseFont, textOpts);
            }
          } else if (layer.x_pct != null || layer.y_pct != null) {
            drawGlowingText(
              displayText,
              W * (layer.x_pct ?? 0.5) + (layer.dx || 0),
              H * (layer.y_pct ?? 0.25) + (layer.dy || 0) + yFly,
              baseFont,
              textOpts
            );
          }
        } else if (layer.type === "curved_label") {
          const preset = CARTO_TYPO_PRESETS[layer.carto_role || "water"] || CARTO_TYPO_PRESETS.water;
          const rawCoords = resolveGeom(layer.coords_ref) || layer.coords || [];
          const segs = projectPolylineClipped(rawCoords);
          if (segs.length && segs[0].length >= 2) {
            const fPx = layer.font_px || 42;
            const revealP = layer.reveal_s ? easeOutExpo(seg(t, tStart, tStart + layer.reveal_s)) : 1.0;
            let txt = String(layer.text ?? "");
            if (preset.uppercase && !layer.preserve_case) txt = txt.toUpperCase();
            const lsEm = layer.letter_spacing_em ?? preset.letterSpacingEm ?? 0.08;
            drawCurvedMapLabel(segs[0], txt, fPx, {
              fill: layer.fill || preset.fill || "#A8D8FF",
              family: layer.family || preset.family || "Lora",
              weight: layer.weight || preset.weight || 600,
              fontStyle: layer.font_style || preset.fontStyle || "italic",
              letterSpacingPx: lsEm * fPx,
              strokeHex: layer.stroke_hex ?? preset.strokeHex ?? "rgba(3,22,31,0.78)",
              strokeWidth: layer.stroke_width ?? Math.max(1.6, Math.min(3.5, fPx * (preset.strokeMult ?? 0.042))),
              alpha: baseAlpha,
              offsetPx: layer.offset_px ?? 0,
              revealProgress: revealP,
              maxCharAngleDeg: layer.max_char_angle_deg ?? 22,
            });
          }
        } else if (layer.type === "crimson_x") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const pop = easeOutBack(seg(t, tStart, tStart + 0.32));
            const sz = lerp(layer.size_start || 56, layer.size_end || 90, seg(t, tStart, tEnd)) * clamp(pop, 0, 1.25);
            drawCrimsonX(pt.x, pt.y, sz, baseAlpha);
          }
        } else if (layer.type === "skull") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const pop = easeOutBack(seg(t, tStart, tStart + 0.32));
            const refZoom = layer.ref_zoom ?? 7.3;
            const zoomScale = Math.pow(2, map.getZoom() - refZoom);
            const sz = (layer.size_start || 155) * zoomScale * clamp(pop, 0, 1.15);
            const rotRad = -map.getBearing() * Math.PI / 180;
            const pitchScale = Math.cos((map.getPitch() || 0) * Math.PI / 180);
            drawSkull(pt.x, pt.y + (layer.dy || 0), sz, baseAlpha, { rotRad, pitchScale });
          }
        } else if (layer.type === "endpoint_dots") {
          const pulse = 1 + 0.16 * Math.sin(t * 14);
          const dr = lerp(layer.r_start || 12, layer.r_end || 28, seg(t, tStart, tEnd)) * pulse;
          for (const c of layer.coords || []) {
            const pt = projectPointSafe(c);
            if (!pt) continue;
            const g = ctx.createRadialGradient(pt.x, pt.y, dr * 0.2, pt.x, pt.y, dr * 2.2);
            g.addColorStop(0, "rgba(255,65,65,0.96)");
            g.addColorStop(0.5, "rgba(220,38,38,0.56)");
            g.addColorStop(1, "rgba(220,38,38,0)");
            ctx.save();
            ctx.globalAlpha = baseAlpha;
            ctx.fillStyle = g; ctx.beginPath(); ctx.arc(pt.x, pt.y, dr * 2.2, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#EF4444"; ctx.beginPath(); ctx.arc(pt.x, pt.y, dr * 0.72, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#FFFFFF"; ctx.beginPath(); ctx.arc(pt.x, pt.y, dr * 0.28, 0, Math.PI * 2); ctx.fill();
            ctx.restore();
          }
        } else if (layer.type === "measurement_arrow") {
          const p1 = projectPointSafe(layer.from);
          const p2 = projectPointSafe(layer.to);
          if (p1 && p2) {
            const arrP = easeOutExpo(seg(t, tStart, tStart + (layer.draw_s || 0.75)));
            const val = Math.round(lerp(layer.count_from ?? 0, layer.count_to ?? 160, easeOutCubic(seg(t, tStart, tStart + (layer.count_s || 1.1)))));
            drawDoubleArrow(p1, p2, val + " " + (layer.unit || "km"), arrP, baseAlpha);
          }
        } else if (layer.type === "weather_clouds_rain") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const sc = lerp(layer.scale_start || 0.85, layer.scale_end || 1.22, easeOutCubic(seg(t, tStart, tStart + 0.8)));
            drawWeatherCloudsRain(pt.x, pt.y + (layer.dy || -30), sc, baseAlpha, tLoc);
          }
        } else if (layer.type === "migrant_swarm") {
          const count = layer.count || 28;
          const [sLng0, sLat0, sLng1, sLat1] = layer.from_box;
          const [eLng0, eLat0, eLng1, eLat1] = layer.to_box;
          const lossStart = layer.loss_start_s ?? (tStart + 2.4);
          for (let i = 0; i < count; i++) {
            const sd1 = ((i * 197 + 31) % 100) / 100;
            const sd2 = ((i * 313 + 17) % 100) / 100;
            const delay = (i % 7) * 0.2;
            const mt = tLoc - delay;
            if (mt < 0) continue;
            const prog = clamp(mt * (0.14 + (i % 4) * 0.024), 0, 1.15);
            const pt = projectPointSafe([
              lerp(lerp(sLng0, sLng1, sd1), lerp(eLng0, eLng1, sd1), prog),
              lerp(lerp(sLat0, sLat1, sd2), lerp(eLat0, eLat1, sd2), prog),
            ]);
            if (!pt) continue;
            let dotA = baseAlpha * Math.min(1, mt * 3);
            let isRed = false;
            const isLost = i % 4 === 1;
            const lostAt = lossStart + (i % 6) * 0.22;
            if (isLost && t >= lostAt) {
              isRed = true;
              dotA *= 1 - seg(t, lostAt + 0.15, lostAt + 0.85);
            }
            if (dotA <= 0.01) continue;
            ctx.save();
            ctx.globalAlpha = dotA;
            const g = ctx.createRadialGradient(pt.x, pt.y, 2, pt.x, pt.y, 26);
            g.addColorStop(0, "#FFFFFF");
            g.addColorStop(0.36, isRed ? "rgba(239,68,68,0.88)" : "rgba(92,225,255,0.88)");
            g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g; ctx.beginPath(); ctx.arc(pt.x, pt.y, 26, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = isRed ? "#EF4444" : "#38BDF8"; ctx.beginPath(); ctx.arc(pt.x, pt.y, 9.5, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#FFFFFF"; ctx.beginPath(); ctx.arc(pt.x, pt.y, 4.2, 0, Math.PI * 2); ctx.fill();
            ctx.restore();
          }
        } else if (layer.type === "wildlife_pins") {
          for (const item of layer.items || []) {
            if (t < item.start_s) continue;
            const pop = easeOutBack(seg(t, item.start_s, item.start_s + 0.3));
            const pt = projectPointSafe(item.coord);
            if (pt) drawTeardropPin(pt.x, pt.y, (layer.radius || 76) * clamp(pop, 0, 1.15), item.kind, baseAlpha);
          }
        } else if (layer.type === "prohibition_badge") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const inP = easeOutExpo(seg(t, tStart, tStart + 0.65));
            const outP = easeInCubic(seg(t, tEnd - 0.95, tEnd));
            const rad = lerp(layer.r_enter || 340, layer.r_hold || 150, inP) * lerp(1.0, 2.8, outP);
            const cy = lerp(220, pt.y - 20, inP) - outP * 380;
            drawNoPoliceBadge(pt.x, cy, rad, baseAlpha);
          }
        } else if (layer.type === "radar_rings") {
          for (const hub of layer.hubs || []) {
            if (t < hub.start_s) continue;
            const age = t - hub.start_s;
            const pt = projectPointSafe(hub.coord);
            if (!pt) continue;
            ctx.save();
            ctx.globalAlpha = baseAlpha;
            ctx.fillStyle = hub.color || "#DC2626";
            ctx.beginPath(); ctx.arc(pt.x, pt.y, 16, 0, Math.PI * 2); ctx.fill();
            for (let k = 0; k < 3; k++) {
              const ph = (age * 0.85 + k / 3) % 1;
              const rr = lerp(18, hub.max_r || 175, ph);
              ctx.strokeStyle = rgbaStr(hub.color || "#EF4444", (1 - ph) * 0.88);
              ctx.lineWidth = lerp(8.5, 2.5, ph);
              ctx.beginPath(); ctx.arc(pt.x, pt.y, rr, 0, Math.PI * 2); ctx.stroke();
            }
            ctx.restore();
          }
        } else if (layer.type === "vignette_grade") {
          const pt = (layer.coord ? projectPointSafe(layer.coord) : null) || { x: W * 0.5, y: H * 0.48 };
          ctx.save();
          const vg = ctx.createRadialGradient(pt.x, pt.y, layer.inner_r || 130, pt.x, pt.y, layer.outer_r || 1050);
          vg.addColorStop(0, "rgba(4,10,14," + (0.22 * baseAlpha).toFixed(3) + ")");
          vg.addColorStop(0.5, "rgba(4,9,12," + (0.76 * baseAlpha).toFixed(3) + ")");
          vg.addColorStop(1, "rgba(2,5,8," + (0.95 * baseAlpha).toFixed(3) + ")");
          ctx.fillStyle = vg;
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
          applyMicroDither(ctx, 0.025 * baseAlpha);
        } else if (layer.type === "focus_spotlight") {
          const refs = Array.isArray(layer.geom_refs)
            ? layer.geom_refs
            : (layer.geom_ref ? [layer.geom_ref] : []);
          const geoms = refs.map((r) => resolveGeom(r)).filter(Boolean);
          drawFocusSpotlight(geoms, {
            dimAlpha: layer.dim_alpha ?? 0.58,
            dimHex: layer.dim_hex || "#04101A",
            featherPx: layer.feather_px ?? 36,
            rimGlowHex: layer.rim_glow_hex || null,
            rimGlowAlpha: layer.rim_glow_alpha ?? 0.25,
            alpha: baseAlpha,
          });
        } else if (layer.type === "color_flash") {
          ctx.save();
          ctx.fillStyle = rgbaStr(layer.hex || "#D8A8F5", (layer.max_alpha ?? 0.82) * baseAlpha);
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
        } else if (layer.type === "jungle_emoji_ending") {
          drawJungleEmojiEnding(tLoc, layer.gag_at_s ?? 1.12);
        } else if (layer.type === "equator_laser") {
          const lat = layer.lat ?? 0.0;
          const lngMin = layer.lng_min ?? 90.0;
          const lngMax = layer.lng_max ?? 130.0;
          const steps = 40;
          const coords = [];
          for (let i = 0; i <= steps; i++) coords.push([lerp(lngMin, lngMax, i / steps), lat]);
          const prog = layer.draw_duration_s ? easeOutExpo(seg(t, tStart, tStart + layer.draw_duration_s)) : 1;
          drawPartialRoute(coords, prog, {
            color: layer.color || "#F5C542",
            bloom: layer.bloom || "#F5C542",
            core: layer.core ?? "#FFFFFF",
            width: layer.width || 6,
            dash: layer.dash || null,
            alpha: baseAlpha,
          });
          if (layer.label && prog > 0.35) {
            const lp = projectPointSafe([layer.label_lng ?? ((lngMin + lngMax) * 0.5), lat]);
            if (lp) drawGlowingText(layer.label, lp.x + (layer.dx || 0), lp.y + (layer.dy || -34), layer.font_px || 36, {
              fill: "#FFFBEB",
              glowHex: layer.bloom || "#F5C542",
              glowStrength: "luminous",
              alpha: baseAlpha * easeOutCubic(seg(prog, 0.35, 0.7)),
            });
          }
        } else if (layer.type === "year_badge") {
          const x = W * (layer.x_pct ?? 0.5);
          const y = H * (layer.y_pct ?? 0.21);
          const sc = lerp(0.94, 1.0, easeOutExpo(seg(t, tStart, tStart + 0.30)));
          const fPx = layer.font_px || 96;
          drawGlowingText(String(layer.text || "1928"), x, y, fPx, {
            fill: layer.fill || "#F4F1EA",
            glowHex: layer.glow_hex || "#F5C542",
            glowStrength: layer.glow_strength || "subtle",
            strokeHex: "rgba(3,22,31,0.84)",
            strokeWidth: Math.max(2.2, fPx * 0.04),
            family: layer.family || "IBM Plex Mono",
            weight: layer.weight || 700,
            tabularDigits: true,
            scale: sc,
            alpha: baseAlpha,
          });
          if (layer.subtitle) {
            drawGlowingText(String(layer.subtitle), x, y + 66, 30, {
              fill: "#DCE8F5",
              strokeHex: "rgba(3,22,31,0.84)",
              strokeWidth: 1.8,
              family: layer.subtitle_family || "Inter",
              weight: 600,
              letterSpacing: "0.06em",
              alpha: baseAlpha * 0.95,
            });
          }
        } else if (layer.type === "void_wipe") {
          const dir = layer.direction || "rtl";
          const wipeS = layer.wipe_s ?? tStart;
          const wipeDur = layer.wipe_duration_s ?? 0.28;
          const unwipeS = layer.unwipe_s ?? (tEnd - 0.35);
          const unwipeDur = layer.unwipe_duration_s ?? 0.32;
          const pIn = easeInOutCubic(seg(t, wipeS, wipeS + wipeDur));
          const pOut = layer.unwipe_s != null ? easeInOutCubic(seg(t, unwipeS, unwipeS + unwipeDur)) : 0;
          const voidAlpha = (layer.void_alpha ?? 0.88) * baseAlpha * (1 - pOut);
          if (voidAlpha > 0.005 && pIn > 0.001) {
            ctx.save();
            ctx.fillStyle = rgbaStr(layer.void_hex || "#0C0E11", voidAlpha);
            let barX = -100;
            if (dir === "rtl") {
              const x0 = lerp(W, 0, pIn);
              ctx.fillRect(x0, 0, W - x0, H);
              barX = x0;
            } else {
              const w0 = lerp(0, W, pIn);
              ctx.fillRect(0, 0, w0, H);
              barX = w0;
            }
            if (pIn > 0.01 && pIn < 0.995) {
              ctx.save();
              ctx.shadowColor = layer.bar_glow || "#FFFFFF";
              ctx.shadowBlur = 28;
              ctx.fillStyle = "#FFFFFF";
              ctx.globalAlpha = baseAlpha * Math.sin(pIn * Math.PI);
              ctx.fillRect(barX - 4, 0, 8, H);
              ctx.restore();
            }
            ctx.restore();
          }
        } else if (layer.type === "flag_pin") {
          const code = String(layer.code || "es").toLowerCase();
          const img = window.__imgCache[BASE_URL + "/flags/" + code + ".svg"];
          if (img) {
            const pop = easeOutBack(seg(t, tStart, tStart + 0.30));
            const popSc = clamp(pop, 0, 1.15);
            const space = layer.space || "world_billboard";
            const fwBase = layer.width_px || 136;
            const fhBase = fwBase * (layer.aspect ?? 0.667);
            ctx.save();
            ctx.globalAlpha = baseAlpha;
            if (space === "map_plane" && layer.coord) {
              const m = getMapPlaneMatrix(layer.coord, layer.ref_zoom ?? map.getZoom());
              const mag = Math.hypot(m.a, m.b);
              const cf = mag > 1e-4 ? clamp(mag, layer.min_scale ?? 0.35, layer.max_scale ?? 2.8) / mag : 1.0;
              ctx.transform(m.a * cf, m.b * cf, m.c * cf, m.d * cf, m.e, m.f);
              ctx.translate(layer.dx || 0, layer.dy || 0);
              if (layer.angle) ctx.rotate((layer.angle * Math.PI) / 180);
              ctx.scale(popSc, popSc);
            } else {
              const pt = projectPointSafe(layer.coord);
              if (!pt) { ctx.restore(); continue; }
              const coupling = layer.scale_coupling ?? 0.45;
              const zoomScale = layer.ref_zoom != null
                ? clamp(Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling), layer.min_scale ?? 0.45, layer.max_scale ?? 2.4)
                : 1.0;
              ctx.translate(pt.x + (layer.dx || 0), pt.y + (layer.dy || 0));
              if (layer.angle) ctx.rotate((layer.angle * Math.PI) / 180);
              ctx.scale(zoomScale * popSc, zoomScale * popSc);
            }
            const fx = -fwBase * 0.5;
            const fy = -fhBase * 0.5;
            ctx.shadowColor = "rgba(0,0,0,0.62)";
            ctx.shadowBlur = 18;
            ctx.shadowOffsetY = 6;
            if (layer.wave === true) {
              const slices = 18;
              const sw = img.width / slices;
              const dw = fwBase / slices;
              for (let i = 0; i < slices; i++) {
                const ph = (i / slices) * Math.PI * 2.2 - tLoc * 5.2;
                const dyW = Math.sin(ph) * (fhBase * 0.055) * (0.2 + 0.8 * (i / slices));
                ctx.drawImage(img, i * sw, 0, sw + 0.5, img.height, fx + i * dw, fy + dyW, dw + 0.8, fhBase);
              }
            } else {
              const bw = layer.border_px ?? 4;
              ctx.fillStyle = layer.border_color || "#FFFFFF";
              ctx.fillRect(fx - bw, fy - bw, fwBase + bw * 2, fhBase + bw * 2);
              ctx.shadowBlur = 0;
              ctx.drawImage(img, fx, fy, fwBase, fhBase);
            }
            ctx.restore();
          }
        } else if (layer.type === "dashed_distance") {
          const dSegs = projectPolylineClipped([layer.from, layer.to]);
          if (dSegs.length && dSegs[0].length >= 2) {
            const p1 = dSegs[0][0];
            const p2 = dSegs[0][dSegs[0].length - 1];
          const prog = layer.draw_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_s)) : 1.0;
          const qx = lerp(p1.x, p2.x, prog);
          const qy = lerp(p1.y, p2.y, prog);
          const col = layer.color || "#FDE047";
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          ctx.lineCap = "butt";
          ctx.setLineDash(layer.dash || [16, 12]);
          ctx.strokeStyle = col;
          ctx.shadowColor = "rgba(0,0,0,0.75)";
          ctx.shadowBlur = 10;
          ctx.lineWidth = layer.width || 7;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(qx, qy);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.restore();
          const labelAlpha = baseAlpha * easeOutCubic(seg(prog, 0.25, 0.7));
          const primaryTxt = layer.primary || layer.metric_label;
          const secondaryTxt = layer.secondary || layer.imperial_label;
          if (labelAlpha > 0.01 && primaryTxt) {
            const mx = (p1.x + p2.x) * 0.5 + (layer.dx || 0);
            const my = (p1.y + p2.y) * 0.5 + (layer.dy || 0);
            const fPx = layer.font_px || 54;
            let angRad = ((layer.angle_deg ?? 0) * Math.PI) / 180;
            if (layer.align_to_line) {
              angRad = Math.atan2(p2.y - p1.y, p2.x - p1.x);
              if (angRad > Math.PI / 2) angRad -= Math.PI;
              if (angRad < -Math.PI / 2) angRad += Math.PI;
            }
            const lblCol = layer.label_color || col;
            ctx.save();
            ctx.translate(mx, my);
            if (angRad) ctx.rotate(angRad);
            drawGlowingText(String(primaryTxt), 0, -fPx * 0.25, fPx, {
              fill: lblCol,
              strokeHex: "rgba(3,22,31,0.85)",
              strokeWidth: Math.max(2.0, fPx * 0.045),
              glowStrength: "none",
              alpha: labelAlpha,
              family: layer.family || "Barlow Condensed",
              weight: layer.weight || 800,
              tabularDigits: true,
            });
            if (secondaryTxt) {
              const secPx = Math.round(fPx * 0.56);
              drawGlowingText(String(secondaryTxt), 0, fPx * 0.55, secPx, {
                fill: lblCol,
                strokeHex: "rgba(3,22,31,0.85)",
                strokeWidth: Math.max(1.6, secPx * 0.05),
                glowStrength: "none",
                alpha: labelAlpha * 0.96,
                family: layer.secondary_family || "IBM Plex Mono",
                weight: 700,
                tabularDigits: true,
              });
            }
            ctx.restore();
          }
          }
        } else if (layer.type === "curved_arc_arrow") {
          const aSegs = projectPolylineClipped([layer.from, layer.to]);
          const prog = layer.draw_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_s)) : 1.0;
          if (prog > 0.01 && aSegs.length && aSegs[0].length >= 2) {
            const p1 = aSegs[0][0];
            const p2 = aSegs[0][aSegs[0].length - 1];
            const dx = p2.x - p1.x, dy = p2.y - p1.y;
            const len = Math.max(1, Math.hypot(dx, dy));
            const nx = -dy / len, ny = dx / len;
            const bend = layer.arc_offset_px != null ? layer.arc_offset_px : len * (layer.arc_ratio ?? 0.26);
            const cx = (p1.x + p2.x) * 0.5 + nx * bend;
            const cy = (p1.y + p2.y) * 0.5 + ny * bend;
            const bez = sampleQuadraticBezierTo(p1, { x: cx, y: cy }, p2, prog, 40);
            const pts = bez.points;
            const col = layer.color || "#EF4444";
            const bloom = layer.bloom || col;
            const w = layer.width || 9;
            ctx.save();
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            const traceArc = () => {
              ctx.beginPath();
              ctx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
            };
            ctx.strokeStyle = bloom; ctx.globalAlpha = baseAlpha * 0.38; ctx.lineWidth = w * 2.4; traceArc(); ctx.stroke();
            ctx.strokeStyle = col; ctx.globalAlpha = baseAlpha; ctx.lineWidth = w; traceArc(); ctx.stroke();
            // Arrowhead at exact Bezier tip using analytic tangent
            const tip = bez.tip;
            const ang = bez.angleRad;
            const ah = Math.max(20, w * 2.6);
            ctx.translate(tip.x, tip.y);
            ctx.rotate(ang);
            ctx.fillStyle = col;
            ctx.beginPath();
            ctx.moveTo(ah * 0.35, 0);
            ctx.lineTo(-ah, -ah * 0.58);
            ctx.lineTo(-ah * 0.65, 0);
            ctx.lineTo(-ah, ah * 0.58);
            ctx.closePath();
            ctx.fill();
            ctx.restore();
          }
        } else if (layer.type === "ghost_overlay") {
          const geom = resolveGeom(layer.geom_ref);
          if (geom) {
            const slideP = layer.slide_s ? easeOutCubic(seg(t, tStart, tStart + layer.slide_s)) : 1.0;
            const dxSlide = lerp(layer.slide_from_dx ?? -420, layer.dx ?? 0, slideP);
            const dySlide = lerp(layer.slide_from_dy ?? 0, layer.dy ?? 0, slideP);
            ctx.save();
            ctx.translate(dxSlide, dySlide);
            drawDissolvedPolygon(geom, {
              fillHex: layer.fill_hex || "#38BDF8",
              fillAlpha: layer.fill_alpha ?? 0.42,
              rimHex: layer.rim_hex || "#BAE6FD",
              rimWidth: layer.rim_width ?? 2.8,
              bloomHex: layer.bloom_hex || "#38BDF8",
              bloomScale: layer.bloom_scale ?? 0.85,
              alpha: baseAlpha,
            });
            if (layer.label && layer.label_coord) {
              const lp = projectPointSafe(layer.label_coord);
              if (lp) drawGlowingText(String(layer.label), lp.x + (layer.label_dx || 0), lp.y + (layer.label_dy || -90), layer.font_px || 54, {
                fill: "#E0F2FE",
                glowHex: layer.bloom_hex || "#38BDF8",
                glowStrength: "luminous",
                alpha: baseAlpha * slideP,
                family: layer.family || "Barlow Condensed",
                weight: layer.weight || 800,
              });
            }
            ctx.restore();
          }
        } else if (layer.type === "counter_odometer") {
          const steps = layer.steps || [{ at_s: tStart, value: "0" }];
          const useComicBounce = layer.register === "comic" || layer.pop_bounce === true;
          const flyP = (useComicBounce ? easeOutBack : easeOutExpo)(seg(t, tStart, tStart + (layer.fly_up_s ?? 0.28)));
          const cx = W * (layer.x_pct ?? 0.5);
          const cy = H * (layer.y_pct ?? 0.22) + lerp(240, 0, clamp(flyP, 0, useComicBounce ? 1.06 : 1.0));
          const fPx = layer.font_px || 152;
          let curIdx = 0;
          for (let i = 0; i < steps.length; i++) {
            if (t >= steps[i].at_s) curIdx = i;
          }
          const curStep = steps[curIdx];
          const prevStep = curIdx > 0 ? steps[curIdx - 1] : null;
          const rollDur = layer.roll_s ?? 0.14;
          const rollP = prevStep ? easeOutExpo(seg(t, curStep.at_s, curStep.at_s + rollDur)) : 1.0;
          const odoFamily = layer.family || "Barlow Condensed";
          const odoWeight = layer.weight || 800;
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(((layer.angle_deg ?? 0) * Math.PI) / 180);
          ctx.beginPath();
          ctx.rect(-W * 0.46, -fPx * 1.05, W * 0.92, fPx * 2.10);
          ctx.clip();
          if (prevStep && rollP < 0.995) {
            drawGlowingText(String(prevStep.value), 0, lerp(0, -fPx * 0.72, rollP), fPx, {
              fill: layer.fill || "#F5C542",
              glowHex: layer.glow_hex || "#F59E0B",
              glowStrength: layer.glow_strength || "subtle",
              strokeHex: "rgba(3,22,31,0.88)",
              strokeWidth: Math.max(2.8, fPx * 0.032),
              alpha: baseAlpha * Math.pow(1 - rollP, 2.0),
              family: odoFamily,
              weight: odoWeight,
              tabularDigits: true,
            });
          }
          drawGlowingText(String(curStep.value), 0, lerp(fPx * 0.72, 0, rollP), fPx, {
            fill: layer.fill || "#F5C542",
            glowHex: layer.glow_hex || "#F59E0B",
            glowStrength: layer.glow_strength || "subtle",
            strokeHex: "rgba(3,22,31,0.88)",
            strokeWidth: Math.max(2.8, fPx * 0.032),
            alpha: prevStep ? baseAlpha * Math.pow(rollP, 1.15) : baseAlpha,
            family: odoFamily,
            weight: odoWeight,
            tabularDigits: true,
          });
          ctx.restore();
        } else if (layer.type === "question_arc") {
          const pt = projectPointSafe(layer.coord);
          if (pt) {
            const count = layer.count || 5;
            const spread = layer.spread_px || 260;
            const lift = layer.arc_lift_px || 52;
            const stagger = layer.stagger_s || 0.08;
            for (let i = 0; i < count; i++) {
              const it = tStart + i * stagger;
              if (t < it) continue;
              const pop = easeOutBack(seg(t, it, it + 0.24));
              const frac = count > 1 ? i / (count - 1) - 0.5 : 0;
              const qx = pt.x + (layer.dx || 0) + frac * spread;
              const qy = pt.y + (layer.dy || -80) - Math.cos(frac * Math.PI) * lift;
              drawGlowingText("?", qx, qy, layer.font_px || 66, {
                fill: layer.fill || "#FDE047",
                glowHex: layer.glow_hex || "#F59E0B",
                glowStrength: "intense",
                angle: frac * 0.35,
                scale: clamp(pop, 0, 1.15),
                alpha: baseAlpha,
                family: "Rubik",
                weight: 900,
              });
            }
          }
        } else if (layer.type === "shifting_route") {
          const coordsA = resolveGeom(layer.coords_a_ref) || layer.coords_a || [];
          const coordsB = resolveGeom(layer.coords_b_ref) || layer.coords_b || [];
          if (coordsA.length >= 2 && coordsA.length === coordsB.length) {
            const shiftU = layer.shift_start_s != null
              ? easeInOutCubic(seg(t, layer.shift_start_s, layer.shift_end_s ?? (layer.shift_start_s + 0.55)))
              : 0;
            const blended = coordsA.map((c, idx) => [
              lerp(c[0], coordsB[idx][0], shiftU),
              lerp(c[1], coordsB[idx][1], shiftU),
            ]);
            const prog = layer.draw_duration_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_duration_s)) : 1.0;
            drawPartialRoute(blended, prog, {
              color: layer.color || "#FDE047",
              bloom: layer.bloom || "#F5C542",
              core: layer.core ?? "#FFFFFF",
              width: layer.width || 9,
              dash: layer.dash || null,
              alpha: baseAlpha,
            });
          }
        } else if (layer.type === "curved_pointer_label") {
          const anchor = layer.coord ? projectPointSafe(layer.coord) : { x: W * (layer.x_pct ?? 0.5), y: H * (layer.y_pct ?? 0.25) };
          if (!anchor) continue;
          const bx = anchor.x + (layer.dx || 0);
          const by = anchor.y + (layer.dy || 0);
          const pop = easeOutCubic(seg(t, tStart, tStart + 0.28));
          const fPx = layer.font_px || 64;
          const lines = layer.lines || [String(layer.text || "")];
          const lineH = Math.round(fPx * 1.12);
          ctx.save();
          ctx.translate(bx, by);
          ctx.rotate(((layer.angle_deg ?? 0) * Math.PI) / 180);
          ctx.globalAlpha = baseAlpha * pop;
          const ptrFamily = layer.family || "Barlow Condensed";
          const ptrWeight = layer.weight || 800;
          ctx.font = ptrWeight + " " + fPx + "px '" + ptrFamily + "', " + inferFontFallback(ptrFamily);
          ctx.textBaseline = "middle";
          for (let li = 0; li < lines.length; li++) {
            const ly = (li - (lines.length - 1) * 0.5) * lineH;
            const ln = String(lines[li]);
            if (li === 0 && layer.highlight_prefix && ln.startsWith(layer.highlight_prefix)) {
              const pre = layer.highlight_prefix;
              const rest = ln.slice(pre.length);
              const wPre = ctx.measureText(pre).width;
              const wTot = ctx.measureText(ln).width;
              const x0 = -wTot * 0.5;
              // Red/neon radial glow behind highlighted prefix word (e.g. "NOT")
              const glowCol = layer.highlight_glow || "#EF4444";
              for (const [blurR, a] of [[fPx * 0.9, 0.72], [fPx * 0.45, 0.92], [fPx * 0.18, 1.0]]) {
                ctx.save();
                ctx.globalAlpha = baseAlpha * pop * a;
                ctx.shadowColor = glowCol;
                ctx.shadowBlur = blurR;
                ctx.fillStyle = "#FFFFFF";
                ctx.textAlign = "left";
                ctx.fillText(pre, x0, ly);
                ctx.restore();
              }
              ctx.save();
              ctx.globalAlpha = baseAlpha * pop;
              ctx.shadowColor = "rgba(0,0,0,0.85)";
              ctx.shadowBlur = 12;
              ctx.shadowOffsetY = 3;
              ctx.fillStyle = "#FFFFFF";
              ctx.textAlign = "left";
              ctx.fillText(pre, x0, ly);
              ctx.fillText(rest, x0 + wPre, ly);
              ctx.restore();
            } else {
              drawGlowingText(ln, 0, ly, fPx, {
                fill: layer.fill || "#F4F1EA",
                strokeHex: layer.stroke_hex ?? "rgba(3,22,31,0.84)",
                strokeWidth: layer.stroke_width ?? Math.max(2.0, fPx * 0.045),
                glowStrength: layer.glow_strength || "none",
                alpha: baseAlpha * pop,
                family: ptrFamily,
                weight: ptrWeight,
              });
            }
          }
          ctx.restore();
          // Graceful hand-drawn curved white Bezier arrow with open chevron tip
          if (layer.pointer_coord) {
            const tp = projectPointSafe(layer.pointer_coord);
            const sx = bx + (layer.arrow_start_dx || 0);
            const sy = by + (layer.arrow_start_dy ?? Math.round(lines.length * lineH * 0.5 + 14));
            const arrowProg = tp ? easeOutCubic(seg(t, tStart + 0.08, tStart + 0.44)) : 0;
            if (arrowProg > 0.01) {
              const dx = tp.x - sx, dy = tp.y - sy;
              const len = Math.max(1, Math.hypot(dx, dy));
              const nx = -dy / len, ny = dx / len;
              const bend = layer.arrow_bend_px ?? (len * 0.24);
              const cx = (sx + tp.x) * 0.5 + nx * bend;
              const cy = (sy + tp.y) * 0.5 + ny * bend;
              const bez = sampleQuadraticBezierTo({ x: sx, y: sy }, { x: cx, y: cy }, tp, arrowProg, 36);
              const pts = bez.points;
              ctx.save();
              ctx.globalAlpha = baseAlpha;
              ctx.strokeStyle = "#FFFFFF";
              ctx.lineWidth = layer.arrow_width || 5;
              ctx.lineCap = "round";
              ctx.lineJoin = "round";
              ctx.shadowColor = "rgba(0,0,0,0.75)";
              ctx.shadowBlur = 10;
              ctx.beginPath();
              ctx.moveTo(pts[0].x, pts[0].y);
              for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
              ctx.stroke();
              // Open chevron V-head at exact Bezier tip
              const tip = bez.tip;
              const ang = bez.angleRad;
              const ah = layer.arrow_head_px || 22;
              ctx.translate(tip.x, tip.y);
              ctx.rotate(ang);
              ctx.beginPath();
              ctx.moveTo(-ah, -ah * 0.52);
              ctx.lineTo(0, 0);
              ctx.lineTo(-ah, ah * 0.52);
              ctx.stroke();
              ctx.restore();
            }
          }
        } else if (layer.type === "pin_label") {
          const pt = projectPointSafe(layer.coord);
          if (!pt) continue;
          const pop = easeOutCubic(seg(t, tStart, tStart + 0.28));
          const coupling = layer.scale_coupling ?? 0.42;
          const zSc = layer.ref_zoom != null
            ? clamp(Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling), layer.min_scale ?? 0.55, layer.max_scale ?? 2.2)
            : 1.0;
          const stemH = (layer.stem_px ?? 58) * pop * zSc;
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          ctx.shadowColor = "rgba(0,0,0,0.75)";
          ctx.shadowBlur = 8;
          ctx.strokeStyle = "#FFFFFF";
          ctx.lineWidth = Math.max(2, 3 * zSc);
          ctx.beginPath();
          ctx.moveTo(pt.x, pt.y);
          ctx.lineTo(pt.x, pt.y - stemH);
          ctx.stroke();
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, Math.max(4, 6 * zSc), 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
          const pinFontPx = layer.font_px || 40;
          const pinPreset = layer.carto_role ? (CARTO_TYPO_PRESETS[layer.carto_role] || {}) : CARTO_TYPO_PRESETS.city;
          drawGlowingText(String(layer.text || ""), pt.x + (layer.dx || 0), pt.y - stemH - pinFontPx * 0.65 * zSc + (layer.dy || 0), pinFontPx, {
            fill: layer.fill || pinPreset.fill || "#F4F1EA",
            strokeHex: layer.stroke_hex ?? pinPreset.strokeHex ?? "rgba(3,22,31,0.82)",
            strokeWidth: layer.stroke_width ?? Math.max(1.8, pinFontPx * 0.045),
            glowStrength: layer.glow_strength || "none",
            scale: zSc,
            alpha: baseAlpha * pop,
            family: layer.family || pinPreset.family || "Inter",
            weight: layer.weight || pinPreset.weight || 700,
            fontStyle: layer.font_style || pinPreset.fontStyle || "normal",
            letterSpacing: layer.letter_spacing ?? (pinPreset.letterSpacingEm != null ? (pinPreset.letterSpacingEm + "em") : 0),
          });
        } else if (layer.type === "human_silhouette_row") {
          const count = layer.count || 10;
          const figH = layer.figure_h_px || 66;
          const spacing = layer.spacing_px || (figH * 0.50);
          const stagger = layer.pop_stagger_s ?? 0.055;
          const popDur = layer.pop_duration_s ?? 0.22;
          const splitAt = layer.split_at_s;
          const splitDur = layer.split_duration_s ?? 0.55;
          const splitLeftCount = layer.split_left_count ?? 2;
          const splitU = splitAt != null ? easeInOutCubic(seg(t, splitAt, splitAt + splitDur)) : 0;
          const exitScale = (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s)
            ? 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd))
            : 1.0;

          const basePt = projectPointSafe(layer.coord);
          if (!basePt) continue;
          const leftPt = (layer.left_coord ? projectPointSafe(layer.left_coord) : null) || basePt;
          const rightPt = (layer.right_coord ? projectPointSafe(layer.right_coord) : null) || basePt;
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.85;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.35, layer.max_scale ?? 2.6) * exitScale;

          for (let i = 0; i < count; i++) {
            const p = easeOutBack(seg(t, tStart + i * stagger, tStart + i * stagger + popDur));
            if (p <= 0.01) continue;
            const unifiedX = basePt.x + (layer.dx || 0) + (i - (count - 1) * 0.5) * spacing * zSc;
            const unifiedY = basePt.y + (layer.dy || 0);
            let tx = unifiedX;
            let ty = unifiedY;
            if (splitAt != null && splitU > 0.001) {
              if (i < splitLeftCount) {
                const lx = leftPt.x + (layer.left_dx || 0) + (i - (splitLeftCount - 1) * 0.5) * spacing * zSc;
                const ly = leftPt.y + (layer.left_dy || 0);
                tx = lerp(unifiedX, lx, splitU);
                ty = lerp(unifiedY, ly, splitU);
              } else {
                const rIdx = i - splitLeftCount;
                const rCount = count - splitLeftCount;
                const rx = rightPt.x + (layer.right_dx || 0) + (rIdx - (rCount - 1) * 0.5) * spacing * zSc;
                const ry = rightPt.y + (layer.right_dy || 0);
                tx = lerp(unifiedX, rx, splitU);
                ty = lerp(unifiedY, ry, splitU);
              }
            }
            let figAlpha = baseAlpha;
            if (i < splitLeftCount && layer.left_end_s != null) {
              if (t > layer.left_end_s) continue;
              if (layer.left_fade_out_s) figAlpha *= 1 - seg(t, layer.left_end_s - layer.left_fade_out_s, layer.left_end_s);
            }
            if (i >= splitLeftCount && layer.right_end_s != null) {
              if (t > layer.right_end_s) continue;
              if (layer.right_fade_out_s) figAlpha *= 1 - seg(t, layer.right_end_s - layer.right_fade_out_s, layer.right_end_s);
            }
            drawHumanFigure(tx, ty, figH * zSc * clamp(p, 0, 1.18), layer.color || "#FFFFFF", figAlpha);
          }
        } else if (layer.type === "landmark_silhouette") {
          let curCoord = layer.coord;
          let headingDeg = layer.angle_deg || 0;
          if (Array.isArray(layer.path) && layer.path.length >= 2) {
            const moveDur = layer.move_duration_s ?? (tEnd - tStart);
            const u = clamp(seg(t, tStart, tStart + moveDur), 0, 1);
            curCoord = samplePolylineCoord(layer.path, u);
            if (layer.auto_heading) {
              const pA = projectPointSafe(samplePolylineCoord(layer.path, Math.max(0, u - 0.02)));
              const pB = projectPointSafe(samplePolylineCoord(layer.path, Math.min(1, u + 0.02)));
              if (pA && pB && Math.hypot(pB.x - pA.x, pB.y - pA.y) > 0.5) {
                headingDeg = (Math.atan2(pB.y - pA.y, pB.x - pA.x) * 180) / Math.PI;
              }
            }
          }
          const pt = projectPointSafe(curCoord);
          if (!pt) continue;
          const coupling = layer.scale_coupling ?? 0.55;
          const zSc = layer.ref_zoom != null
            ? clamp(Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling), layer.min_scale ?? 0.45, layer.max_scale ?? 2.4)
            : 1.0;
          const riseP = layer.rise_duration_s
            ? easeOutBack(seg(t, tStart, tStart + layer.rise_duration_s))
            : 1.0;
          const exitScale = (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s)
            ? 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd))
            : 1.0;
          drawLandmarkSilhouette(
            pt.x + (layer.dx || 0),
            pt.y + (layer.dy || 0),
            (layer.height_px || 190) * zSc * exitScale,
            layer.landmark || "statue_of_liberty",
            {
              fillHex: layer.fill_hex || "#94A3B8",
              accentHex: layer.accent_hex || "#CBD5E1",
              rimHex: layer.rim_hex || "#E2E8F0",
              alpha: baseAlpha,
              riseProgress: clamp(riseP, 0, 1.08),
              time: tLoc,
              angleDeg: headingDeg,
            },
          );
        } else if (layer.type === "cloud_system") {
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.85;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.35, layer.max_scale ?? 3.0);
          for (let ci = 0; ci < (layer.clouds || []).length; ci++) {
            const cl = layer.clouds[ci];
            const cStart = cl.start_s ?? tStart;
            const cEnd = cl.end_s ?? tEnd;
            if (t < cStart - 0.001 || t > cEnd + 0.001) continue;
            const cIn = easeOutCubic(seg(t, cStart, cStart + (cl.fade_in_s ?? 0.45)));
            const cOut = 1 - seg(t, cEnd - (cl.fade_out_s ?? 0.45), cEnd);
            const cAlpha = baseAlpha * clamp(cIn * cOut * (cl.opacity ?? 0.96), 0, 1);
            const moveDur = cl.move_duration_s ?? (cEnd - cStart);
            const rawU = seg(t, cStart, cStart + moveDur);
            const u = cl.easing === "linear" ? rawU : cl.easing === "ease_in_out" ? easeInOutCubic(rawU) : easeOutCubic(rawU);
            const coord = samplePolylineCoord(cl.path, u);
            const pt = projectPointSafe(coord);
            if (!pt) continue;
            drawShadedCloud(
              pt.x + (cl.dx || 0),
              pt.y + (cl.dy || 0),
              (cl.radius_px || 78) * zSc,
              cAlpha,
              t - cStart,
              cl.seed ?? (ci + 1),
              (cl.shadow_dx ?? 18) * zSc,
              (cl.shadow_dy ?? 34) * zSc,
            );
          }
        } else if (layer.type === "wind_streamlines") {
          for (const st of layer.streams || []) {
            const sStart = st.start_s ?? tStart;
            const sEnd = st.end_s ?? tEnd;
            if (t < sStart || t > sEnd) continue;
            const dur = st.duration_s ?? 1.4;
            const rep = st.repeat_s ?? 0;
            const localT = t - sStart;
            const tailFrac = st.tail_frac ?? 0.42;
            const cycles = rep > 0 ? Math.floor(localT / rep) + 1 : 1;
            for (let c = 0; c < cycles; c++) {
              const ct = localT - c * rep;
              if (ct < 0 || ct > dur * (1 + tailFrac)) continue;
              const headU = (ct / dur) * (1 + tailFrac);
              drawWindStreamline(st.coords, headU, tailFrac, {
                widthPx: st.width_px ?? 4.8,
                color: st.color || "#FFFFFF",
                glowHex: st.glow_hex || "#7CE0F9",
                alpha: baseAlpha * (st.opacity ?? 0.88),
              });
            }
          }
        } else if (layer.type === "prohibition_pins") {
          const refZoom = layer.ref_zoom ?? map.getZoom();
          const coupling = layer.scale_coupling ?? 0.72;
          const zSc = clamp(Math.pow(2, (map.getZoom() - refZoom) * coupling), layer.min_scale ?? 0.40, layer.max_scale ?? 2.2);
          for (const pin of layer.pins || []) {
            const pStart = pin.pop_s ?? tStart;
            if (t < pStart) continue;
            const popP = easeOutBack(seg(t, pStart, pStart + (pin.pop_duration_s ?? 0.26)));
            const slashStart = pStart + (pin.slash_delay_s ?? 0.36);
            const slashP = easeOutCubic(seg(t, slashStart, slashStart + (pin.slash_duration_s ?? 0.24)));
            const pt = projectPointSafe(pin.coord);
            if (!pt) continue;
            drawProhibitionPin(
              pt.x + (pin.dx || 0),
              pt.y + (pin.dy || 0),
              (pin.radius_px || 44) * zSc,
              pin.icon || "water_drop",
              clamp(popP, 0, 1.15),
              slashP,
              baseAlpha,
            );
          }
        }
      }
    }

    const ALLOW_WORLD_VOID = ${Boolean(mapOpts.allow_world_void || mapOpts.projection === "globe")};
    const stageEl = document.getElementById("stage");
    window.__currentRoll = 0;

    function clampMercatorCamera(cam) {
      if (ALLOW_WORLD_VOID) return cam;
      const bearing = cam.bearing || 0;
      const pitch = Math.max(0, Math.min(72, cam.pitch || 0));
      const roll = Math.max(-12, Math.min(12, cam.roll || 0));
      const minZoom = Math.log2(H / 512) + 0.08;
      const z = Math.max(cam.zoom, minZoom);
      const worldPx = 512 * Math.pow(2, z);
      const halfY = (H * 0.5) / worldPx + 0.012;
      const lat = Math.max(-85.0, Math.min(85.0, cam.center[1]));
      const sinLat = Math.sin(lat * Math.PI / 180);
      let yNorm = 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI);
      if (halfY < 0.49) {
        yNorm = Math.max(halfY, Math.min(1 - halfY, yNorm));
      } else {
        yNorm = 0.5;
      }
      const n = Math.PI - 2 * Math.PI * yNorm;
      const clampedLat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
      return {
        center: [cam.center[0], clampedLat],
        zoom: z,
        bearing,
        pitch,
        roll,
      };
    }

    function computeRollOverscan(rollDeg) {
      const r = Math.abs(rollDeg || 0) * Math.PI / 180;
      return Math.cos(r) + Math.sin(r) * Math.max(W / H, H / W);
    }

    // Smooth camera sampling (pre-expanded camera_samples or scale-coupled inline keyframes)
    window.__setSceneCamera = function(cam) {
      const safe = clampMercatorCamera(cam);
      window.__currentRoll = safe.roll || 0;
      if (Math.abs(window.__currentRoll) > 0.01) {
        const sc = computeRollOverscan(window.__currentRoll);
        stageEl.style.transform = "rotate(" + window.__currentRoll.toFixed(3) + "deg) scale(" + sc.toFixed(5) + ")";
      } else {
        stageEl.style.transform = "";
      }
      map.jumpTo({
        center: safe.center,
        zoom: safe.zoom,
        bearing: safe.bearing,
        pitch: safe.pitch,
      });
    };

    function initThreeMapLayer() {
      const originLng = ORIGIN_COORD[0] || 0;
      const originLat = ORIGIN_COORD[1] || 0;
      const originMerc = maplibregl.MercatorCoordinate.fromLngLat([originLng, originLat], 0);
      const meterScale = originMerc.meterInMercatorCoordinateUnits();
      const sceneOriginMat = new THREE.Matrix4()
        .makeTranslation(originMerc.x, originMerc.y, originMerc.z)
        .scale(new THREE.Vector3(meterScale, -meterScale, meterScale));

      function lngLatAltToLocal(lng, lat, altM = 0) {
        const mc = maplibregl.MercatorCoordinate.fromLngLat([lng, lat], altM);
        return new THREE.Vector3(
          (mc.x - originMerc.x) / meterScale,
          -(mc.y - originMerc.y) / meterScale,
          (mc.z - originMerc.z) / meterScale
        );
      }

      function groundElevM(lng, lat) {
        if (${terrain3d} && typeof map.queryTerrainElevation === "function") {
          const e = map.queryTerrainElevation([lng, lat], { exaggerated: true });
          if (Number.isFinite(e) && e > 0) return e;
        }
        return 0;
      }

      function metersForScreenPx(px, lat, curZoom, refZoom, coupling = 0.45, minScale = 0.4, maxScale = 3.2) {
        const baseZ = refZoom != null ? refZoom : curZoom;
        const mpp = (156543.03392 * Math.max(0.2, Math.cos((lat * Math.PI) / 180))) / Math.pow(2, curZoom);
        const ratio = Math.pow(2, (curZoom - baseZ) * coupling);
        return px * mpp * clamp(ratio, minScale, maxScale);
      }

      // Procedural PBR textures built once per WebGL scene
      function makeShadowDiscTex() {
        const c = document.createElement("canvas");
        c.width = 128; c.height = 128;
        const cx = c.getContext("2d");
        const g = cx.createRadialGradient(64, 64, 4, 64, 64, 62);
        g.addColorStop(0, "rgba(2,8,14,0.68)");
        g.addColorStop(0.55, "rgba(2,8,14,0.30)");
        g.addColorStop(1, "rgba(2,8,14,0)");
        cx.fillStyle = g;
        cx.fillRect(0, 0, 128, 128);
        const tex = new THREE.CanvasTexture(c);
        tex.needsUpdate = true;
        return tex;
      }

      function makeSolarCellTex() {
        const c = document.createElement("canvas");
        c.width = 256; c.height = 256;
        const cx = c.getContext("2d");
        const bg = cx.createLinearGradient(0, 0, 256, 256);
        bg.addColorStop(0, "#102B63");
        bg.addColorStop(0.5, "#1D4D9F");
        bg.addColorStop(1, "#0B1D42");
        cx.fillStyle = bg;
        cx.fillRect(0, 0, 256, 256);
        cx.strokeStyle = "rgba(186, 230, 253, 0.55)";
        cx.lineWidth = 2;
        for (let i = 1; i < 8; i++) {
          const p = (i * 256) / 8;
          cx.beginPath(); cx.moveTo(p, 0); cx.lineTo(p, 256); cx.stroke();
          cx.beginPath(); cx.moveTo(0, p); cx.lineTo(256, p); cx.stroke();
        }
        cx.strokeStyle = "#CBD5E1";
        cx.lineWidth = 8;
        cx.strokeRect(4, 4, 248, 248);
        const tex = new THREE.CanvasTexture(c);
        tex.anisotropy = 4;
        return tex;
      }

      function makeVolumeTopTex(edgeHex) {
        const c = document.createElement("canvas");
        c.width = 256; c.height = 256;
        const cx = c.getContext("2d");
        cx.fillStyle = "rgba(245, 158, 11, 0.24)";
        cx.fillRect(0, 0, 256, 256);
        cx.strokeStyle = edgeHex || "#FEF08A";
        cx.lineWidth = 2;
        for (let i = 1; i < 8; i++) {
          const p = (i * 256) / 8;
          cx.beginPath(); cx.moveTo(p, 0); cx.lineTo(p, 256); cx.stroke();
          cx.beginPath(); cx.moveTo(0, p); cx.lineTo(256, p); cx.stroke();
        }
        cx.lineWidth = 6;
        cx.strokeRect(3, 3, 250, 250);
        const tex = new THREE.CanvasTexture(c);
        return tex;
      }

      const armorTexCache = new Map();
      function getArmorTexSet(armorHex, jacketHex) {
        const key = (armorHex || "#D4A037") + "|" + (jacketHex || "#1E293B");
        if (armorTexCache.has(key)) return armorTexCache.get(key);
        const W_TEX = 256, H_TEX = 256;
        const cCol = document.createElement("canvas");
        cCol.width = W_TEX; cCol.height = H_TEX;
        const xCol = cCol.getContext("2d");
        xCol.fillStyle = jacketHex || "#1E293B";
        xCol.fillRect(0, 0, W_TEX, H_TEX);

        const cBump = document.createElement("canvas");
        cBump.width = W_TEX; cBump.height = H_TEX;
        const xBump = cBump.getContext("2d");
        xBump.fillStyle = "#303030";
        xBump.fillRect(0, 0, W_TEX, H_TEX);

        // Diagonal helical steel-wire & armored brass/copper strands wrapping continuously across UV tile
        const strands = 12;
        for (let i = -strands; i <= strands * 2; i++) {
          const u0 = (i / strands) * W_TEX;
          const isAccent = (Math.abs(i) % 3 === 0);
          xCol.strokeStyle = isAccent ? (armorHex || "#E5B449") : "#64748B";
          xCol.lineWidth = isAccent ? 12 : 9;
          xCol.beginPath(); xCol.moveTo(u0, 0); xCol.lineTo(u0 + W_TEX, H_TEX); xCol.stroke();

          // Dark crevice between wrapped wires
          xCol.strokeStyle = "#0F172A";
          xCol.lineWidth = 3;
          xCol.beginPath(); xCol.moveTo(u0 + 6, 0); xCol.lineTo(u0 + 6 + W_TEX, H_TEX); xCol.stroke();

          // Cylindrical ridge in bump map
          xBump.strokeStyle = "#FFFFFF";
          xBump.lineWidth = 10;
          xBump.beginPath(); xBump.moveTo(u0, 0); xBump.lineTo(u0 + W_TEX, H_TEX); xBump.stroke();
        }
        // Subtle specular highlight band along longitudinal center
        const shine = xCol.createLinearGradient(0, 0, 0, H_TEX);
        shine.addColorStop(0, "rgba(0,0,0,0.22)");
        shine.addColorStop(0.5, "rgba(255,255,255,0.20)");
        shine.addColorStop(1, "rgba(0,0,0,0.22)");
        xCol.fillStyle = shine;
        xCol.fillRect(0, 0, W_TEX, H_TEX);

        const makeWrapped = (canvas) => {
          const t = new THREE.CanvasTexture(canvas);
          t.wrapS = THREE.RepeatWrapping;
          t.wrapT = THREE.RepeatWrapping;
          t.anisotropy = 8;
          return t;
        };
        const out = { colCanvas: cCol, bumpCanvas: cBump, makeWrapped };
        armorTexCache.set(key, out);
        return out;
      }

      const shadowTex = makeShadowDiscTex();
      const solarTex = makeSolarCellTex();

      function makeBeamBetween(a, b, r, mat) {
        const dir = new THREE.Vector3().subVectors(b, a);
        const len = dir.length();
        const geo = new THREE.CylinderGeometry(r, r, len, 6, 1);
        geo.rotateX(Math.PI / 2);
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.copy(a).add(b).multiplyScalar(0.5);
        mesh.lookAt(b);
        return mesh;
      }

      function addGroundShadow(group, radiusXY) {
        const sGeo = new THREE.PlaneGeometry(radiusXY * 2, radiusXY * 2);
        const sMat = new THREE.MeshBasicMaterial({
          map: shadowTex,
          transparent: true,
          depthWrite: false,
          opacity: 0.72,
        });
        const m = new THREE.Mesh(sGeo, sMat);
        m.position.set(0, 0, 0.004);
        group.add(m);
      }

      function buildTransmissionTowerModel(layer) {
        const root = new THREE.Group();
        const powered = layer.powered !== false;
        const accentHex = layer.accent_hex || "#FDE047";
        const steelMat = new THREE.MeshStandardMaterial({
          color: powered ? 0xe2e8f0 : 0x475569,
          metalness: powered ? 0.82 : 0.45,
          roughness: powered ? 0.28 : 0.65,
        });
        const concreteMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.85, metalness: 0.1 });
        const termMat = powered
          ? new THREE.MeshStandardMaterial({
              color: new THREE.Color(accentHex),
              emissive: new THREE.Color(accentHex),
              emissiveIntensity: 0.9,
              roughness: 0.2,
              metalness: 0.3,
            })
          : new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.7, metalness: 0.2 });

        addGroundShadow(root, 0.42);
        const cornersBase = [[-0.17, -0.17], [0.17, -0.17], [0.17, 0.17], [-0.17, 0.17]];
        for (const [cx, cy] of cornersBase) {
          const pad = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.11, 0.045), concreteMat);
          pad.position.set(cx, cy, 0.022);
          root.add(pad);
        }
        const levelZ = [0.03, 0.24, 0.46, 0.66, 0.85, 1.0];
        const levelW = [0.165, 0.125, 0.092, 0.068, 0.046, 0.008];
        for (let bay = 0; bay < levelZ.length - 1; bay++) {
          const z0 = levelZ[bay], z1 = levelZ[bay + 1];
          const w0 = levelW[bay], w1 = levelW[bay + 1];
          const bPts = [[-w0, -w0, z0], [w0, -w0, z0], [w0, w0, z0], [-w0, w0, z0]];
          const tPts = [[-w1, -w1, z1], [w1, -w1, z1], [w1, w1, z1], [-w1, w1, z1]];
          for (let k = 0; k < 4; k++) {
            const kn = (k + 1) % 4;
            const a = new THREE.Vector3(...bPts[k]);
            const b = new THREE.Vector3(...tPts[k]);
            const an = new THREE.Vector3(...bPts[kn]);
            const bn = new THREE.Vector3(...tPts[kn]);
            root.add(makeBeamBetween(a, b, 0.017, steelMat));
            root.add(makeBeamBetween(b, bn, 0.011, steelMat));
            if (bay < 4) {
              root.add(makeBeamBetween(a, bn, 0.009, steelMat));
              root.add(makeBeamBetween(an, b, 0.009, steelMat));
            }
          }
        }
        // Two 3D cross-arm assemblies with hanging ceramic insulators & energized corona spheres
        const arms = [[0.64, 0.36, 0.068], [0.83, 0.26, 0.048]];
        const insMat = new THREE.MeshStandardMaterial({ color: powered ? 0xf8fafc : 0x475569, roughness: 0.35, metalness: 0.2 });
        for (const [az, span, bodyW] of arms) {
          for (const side of [-1, 1]) {
            const tip = new THREE.Vector3(side * span, 0, az);
            const innerUp = new THREE.Vector3(side * bodyW, 0, az + 0.07);
            const innerF = new THREE.Vector3(side * bodyW, bodyW, az);
            const innerB = new THREE.Vector3(side * bodyW, -bodyW, az);
            root.add(makeBeamBetween(tip, innerUp, 0.013, steelMat));
            root.add(makeBeamBetween(tip, innerF, 0.013, steelMat));
            root.add(makeBeamBetween(tip, innerB, 0.013, steelMat));
            const insTop = new THREE.Vector3(side * (span * 0.94), 0, az);
            const insBot = new THREE.Vector3(side * (span * 0.94), 0, az - 0.11);
            root.add(makeBeamBetween(insTop, insBot, 0.014, insMat));
            const orb = new THREE.Mesh(new THREE.SphereGeometry(0.030, 12, 10), termMat);
            orb.position.copy(insBot);
            root.add(orb);
          }
        }
        const apexOrb = new THREE.Mesh(new THREE.SphereGeometry(0.028, 12, 10), termMat);
        apexOrb.position.set(0, 0, 1.015);
        root.add(apexOrb);
        return root;
      }

      function buildSubstationModel(layer) {
        const root = new THREE.Group();
        const powered = layer.powered !== false;
        const accentHex = layer.accent_hex || "#38BDF8";
        addGroundShadow(root, 0.85);
        const padMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.88, metalness: 0.08 });
        const hallMat = new THREE.MeshStandardMaterial({
          color: powered ? 0x1e293b : 0x334155,
          metalness: 0.65,
          roughness: 0.35,
        });
        const roofMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.72, roughness: 0.3 });
        const glowMat = powered
          ? new THREE.MeshStandardMaterial({
              color: new THREE.Color(accentHex),
              emissive: new THREE.Color(accentHex),
              emissiveIntensity: 0.85,
              roughness: 0.25,
            })
          : new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.75 });

        const pad = new THREE.Mesh(new THREE.BoxGeometry(1.36, 0.96, 0.06), padMat);
        pad.position.set(0, 0, 0.03);
        root.add(pad);

        const hall = new THREE.Mesh(new THREE.BoxGeometry(0.92, 0.56, 0.56), hallMat);
        hall.position.set(-0.12, 0.06, 0.34);
        root.add(hall);

        const roof = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.62, 0.06), roofMat);
        roof.position.set(-0.12, 0.06, 0.65);
        root.add(roof);

        const strip = new THREE.Mesh(new THREE.BoxGeometry(0.94, 0.58, 0.065), glowMat);
        strip.position.set(-0.12, 0.06, 0.52);
        root.add(strip);

        // 3 outdoor cylindrical HVDC converter transformers + high-voltage ceramic bushings
        for (let i = 0; i < 3; i++) {
          const tx = 0.44;
          const ty = -0.26 + i * 0.26;
          const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.095, 0.36, 14), roofMat);
          tank.rotation.x = Math.PI / 2;
          tank.position.set(tx, ty, 0.24);
          root.add(tank);

          const bush = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.024, 0.28, 10), roofMat);
          bush.rotation.x = Math.PI / 2;
          bush.position.set(tx, ty, 0.55);
          root.add(bush);

          const tip = new THREE.Mesh(new THREE.SphereGeometry(0.036, 10, 8), glowMat);
          tip.position.set(tx, ty, 0.71);
          root.add(tip);
        }
        return root;
      }

      function buildSolarFarmModel(layer) {
        const root = new THREE.Group();
        addGroundShadow(root, 1.25);
        const baseMat = new THREE.MeshStandardMaterial({ color: 0x5c3a28, roughness: 0.95, metalness: 0.04 });
        const steelMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.8, roughness: 0.3 });
        const panelMat = new THREE.MeshStandardMaterial({
          map: solarTex,
          metalness: 0.52,
          roughness: 0.18,
          emissive: new THREE.Color("#0F2A6B"),
          emissiveIntensity: 0.18,
        });
        const accentMat = new THREE.MeshStandardMaterial({
          color: 0xfde047,
          emissive: 0xf59e0b,
          emissiveIntensity: 0.75,
        });

        const apron = new THREE.Mesh(new THREE.BoxGeometry(2.0, 1.65, 0.04), baseMat);
        apron.position.set(0, 0, 0.02);
        root.add(apron);

        const rows = 4, cols = 4;
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const px = -0.66 + c * 0.44;
            const py = -0.54 + r * 0.34;
            const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.022, 0.18, 6), steelMat);
            leg.rotation.x = Math.PI / 2;
            leg.position.set(px, py, 0.12);
            root.add(leg);

            const tbl = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.25, 0.024), panelMat);
            tbl.position.set(px, py, 0.21);
            tbl.rotation.x = 0.48;
            root.add(tbl);
          }
        }
        // Inverter / collector cabin + glowing energy bus
        const inv = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.22, 0.22), steelMat);
        inv.position.set(0.82, 0.62, 0.15);
        root.add(inv);
        const beacon = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.24, 0.05), accentMat);
        beacon.position.set(0.82, 0.62, 0.27);
        root.add(beacon);
        return root;
      }

      function buildSurveyVesselModel(layer) {
        const root = new THREE.Group();
        addGroundShadow(root, 0.95);
        const hullMat = new THREE.MeshStandardMaterial({ color: 0x0f2744, metalness: 0.45, roughness: 0.38 });
        const keelMat = new THREE.MeshStandardMaterial({ color: 0xb91c1c, roughness: 0.55, metalness: 0.2 });
        const deckMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.72, metalness: 0.25 });
        const bridgeMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.32, metalness: 0.15 });
        const glassMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0ea5e9, emissiveIntensity: 0.45, metalness: 0.8, roughness: 0.15 });
        const drumMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0xd97706, emissiveIntensity: 0.25, metalness: 0.65, roughness: 0.28 });

        // Hull plan extruded along Z (Bow pointing toward +Y)
        const shape = new THREE.Shape();
        shape.moveTo(-0.22, -0.78);
        shape.lineTo(0.22, -0.78);
        shape.lineTo(0.24, 0.36);
        shape.quadraticCurveTo(0.14, 0.82, 0, 0.98);
        shape.quadraticCurveTo(-0.14, 0.82, -0.24, 0.36);
        shape.closePath();

        const keelGeo = new THREE.ExtrudeGeometry(shape, { depth: 0.08, bevelEnabled: false });
        const keel = new THREE.Mesh(keelGeo, keelMat);
        keel.position.z = 0.01;
        root.add(keel);

        const hullGeo = new THREE.ExtrudeGeometry(shape, { depth: 0.16, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.015, bevelSegments: 2 });
        const hull = new THREE.Mesh(hullGeo, hullMat);
        hull.position.z = 0.09;
        root.add(hull);

        const deck = new THREE.Mesh(new THREE.BoxGeometry(0.40, 1.05, 0.03), deckMat);
        deck.position.set(0, -0.18, 0.27);
        root.add(deck);

        // Bridge superstructure near bow
        const br1 = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.36, 0.24), bridgeMat);
        br1.position.set(0, 0.30, 0.39);
        root.add(br1);
        const br2 = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.24, 0.14), bridgeMat);
        br2.position.set(0, 0.32, 0.56);
        root.add(br2);
        const win = new THREE.Mesh(new THREE.BoxGeometry(0.30, 0.14, 0.07), glassMat);
        win.position.set(0, 0.40, 0.57);
        root.add(win);

        // Radar mast & aft cable carousel drum
        const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.018, 0.28, 8), bridgeMat);
        mast.rotation.x = Math.PI / 2;
        mast.position.set(0, 0.28, 0.76);
        root.add(mast);

        const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.16, 20), drumMat);
        drum.rotation.z = Math.PI / 2;
        drum.position.set(0, -0.34, 0.40);
        root.add(drum);

        // Stern A-frame gantry crane
        const gantryL = makeBeamBetween(new THREE.Vector3(-0.18, -0.72, 0.27), new THREE.Vector3(-0.12, -0.76, 0.58), 0.016, bridgeMat);
        const gantryR = makeBeamBetween(new THREE.Vector3(0.18, -0.72, 0.27), new THREE.Vector3(0.12, -0.76, 0.58), 0.016, bridgeMat);
        const gantryT = makeBeamBetween(new THREE.Vector3(-0.12, -0.76, 0.58), new THREE.Vector3(0.12, -0.76, 0.58), 0.016, bridgeMat);
        root.add(gantryL, gantryR, gantryT);

        // Subtle V-shaped foam wake on sea behind stern
        const wakeMat = new THREE.MeshBasicMaterial({ color: 0xe0f2fe, transparent: true, opacity: 0.48, side: THREE.DoubleSide, depthWrite: false });
        for (const s of [-1, 1]) {
          const wMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.06, 0.85), wakeMat);
          wMesh.position.set(s * 0.26, -1.16, 0.02);
          wMesh.rotation.z = s * 0.28;
          root.add(wMesh);
        }
        return root;
      }

      function computeParallelFrames(pts) {
        const n = pts.length;
        const tangents = [];
        const normals = [];
        const binormals = [];
        const worldUp = new THREE.Vector3(0, 0, 1);
        for (let i = 0; i < n; i++) {
          const a = pts[Math.max(0, i - 1)];
          const b = pts[Math.min(n - 1, i + 1)];
          const tan = new THREE.Vector3().subVectors(b, a).normalize();
          if (tan.lengthSq() < 1e-8) tan.set(1, 0, 0);
          tangents.push(tan);
        }
        let n0 = new THREE.Vector3().crossVectors(tangents[0], worldUp);
        if (n0.lengthSq() < 1e-5) n0.set(1, 0, 0);
        n0.normalize();
        normals.push(n0);
        binormals.push(new THREE.Vector3().crossVectors(tangents[0], n0).normalize());
        for (let i = 1; i < n; i++) {
          const prevN = normals[i - 1].clone();
          const tPrev = tangents[i - 1];
          const tCur = tangents[i];
          const axis = new THREE.Vector3().crossVectors(tPrev, tCur);
          if (axis.lengthSq() > 1e-9) {
            axis.normalize();
            const ang = Math.acos(clamp(tPrev.dot(tCur), -1, 1));
            prevN.applyAxisAngle(axis, ang);
          }
          prevN.normalize();
          normals.push(prevN);
          binormals.push(new THREE.Vector3().crossVectors(tCur, prevN).normalize());
        }
        return { tangents, normals, binormals };
      }

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera();
      camera.matrixAutoUpdate = false;

      scene.add(new THREE.AmbientLight(0xffffff, 0.22));
      scene.add(new THREE.HemisphereLight(0xdbeafe, 0x162432, 0.52));
      const keySun = new THREE.DirectionalLight(0xfff5e0, 1.25);
      keySun.position.set(SUN_VEC.x * 1000, SUN_VEC.y * 1000, SUN_VEC.z * 1000);
      keySun.castShadow = true;
      keySun.shadow.mapSize.set(2048, 2048);
      keySun.shadow.bias = -0.0005;
      keySun.shadow.normalBias = 0.02;
      scene.add(keySun);
      scene.add(keySun.target);

      const rimSun = new THREE.DirectionalLight(0x7dd3fc, 0.36);
      rimSun.position.set(-SUN_VEC.x * 1000, -SUN_VEC.y * 1000, Math.max(0.45, SUN_VEC.z * 0.7) * 1000);
      scene.add(rimSun);

      // Physical ground shadow receiver plane dynamically fitted to active 3D bounds
      const shadowGroundMat = new THREE.ShadowMaterial({ opacity: 0.44, depthWrite: false });
      const shadowGround = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), shadowGroundMat);
      shadowGround.receiveShadow = true;
      shadowGround.frustumCulled = false;
      shadowGround.visible = false;
      scene.add(shadowGround);

      // Shared camera position vector in local scene meters (extracted each frame from projectionMatrix)
      const camLocalPos = new THREE.Vector3(0, 0, 500000);
      const invProjMat = new THREE.Matrix4();
      function updateCameraLocalPos(projMat) {
        invProjMat.copy(projMat).invert();
        const e = invProjMat.elements;
        if (Math.abs(e[11]) > 1e-9) {
          camLocalPos.set(e[8] / e[11], e[9] / e[11], Math.abs(e[10] / e[11]));
        }
      }

      // Native zero-addon Dual-Kawase HDR Bloom + ACESFilmic composite pipeline
      let renderer = null;
      let bloomState = null;

      function disposeBloomTargets(st) {
        if (!st) return;
        if (st.sceneRT) st.sceneRT.dispose();
        for (const rt of st.downRTs || []) rt.dispose();
        for (const rt of st.upRTs || []) rt.dispose();
      }

      function initDualKawaseBloom(gl) {
        const fsCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
        const fsGeo = new THREE.PlaneGeometry(2, 2);
        const fsVert = [
          "varying vec2 vUv;",
          "void main() {",
          "  vUv = uv;",
          "  gl_Position = vec4(position.xy, 0.0, 1.0);",
          "}",
        ].join("\\n");

        const brightMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tInput;",
            "uniform float uThreshold;",
            "uniform float uKnee;",
            "varying vec2 vUv;",
            "void main() {",
            "  vec4 c = texture2D(tInput, vUv);",
            "  vec3 col = c.rgb;",
            "  float br = max(col.r, max(col.g, col.b));",
            "  float soft = clamp(br - uThreshold + uKnee, 0.0, 2.0 * uKnee);",
            "  soft = (soft * soft) / max(4.0 * uKnee, 1e-4);",
            "  float contrib = max(soft, br - uThreshold) / max(br, 1e-4);",
            "  gl_FragColor = vec4(col * max(contrib, 0.0), 1.0);",
            "}",
          ].join("\\n"),
          uniforms: {
            tInput: { value: null },
            uThreshold: { value: 1.15 },
            uKnee: { value: 0.22 },
          },
          depthTest: false,
          depthWrite: false,
        });

        // Dual-Kawase 5-tap downsample kernel (1/2 center + four 1/8 half-pixel corners)
        const downMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tInput;",
            "uniform vec2 uHalfPixel;",
            "uniform float uOffset;",
            "varying vec2 vUv;",
            "void main() {",
            "  vec2 d = uHalfPixel * uOffset;",
            "  vec4 sum = texture2D(tInput, vUv) * 4.0;",
            "  sum += texture2D(tInput, vUv - d);",
            "  sum += texture2D(tInput, vUv + d);",
            "  sum += texture2D(tInput, vUv + vec2(d.x, -d.y));",
            "  sum += texture2D(tInput, vUv - vec2(d.x, -d.y));",
            "  gl_FragColor = sum * 0.125;",
            "}",
          ].join("\\n"),
          uniforms: {
            tInput: { value: null },
            uHalfPixel: { value: new THREE.Vector2(0.001, 0.001) },
            uOffset: { value: 1.5 },
          },
          depthTest: false,
          depthWrite: false,
        });

        // Dual-Kawase 8-tap tent upsample kernel (four 1/6 inner diagonals + four 1/12 outer cardinals)
        const upMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tInput;",
            "uniform sampler2D tBlend;",
            "uniform vec2 uHalfPixel;",
            "uniform float uOffset;",
            "uniform float uBlendWeight;",
            "varying vec2 vUv;",
            "void main() {",
            "  vec2 d = uHalfPixel * uOffset;",
            "  vec4 sum = texture2D(tInput, vUv + vec2(-d.x * 2.0, 0.0));",
            "  sum += texture2D(tInput, vUv + vec2(-d.x, d.y)) * 2.0;",
            "  sum += texture2D(tInput, vUv + vec2(0.0, d.y * 2.0));",
            "  sum += texture2D(tInput, vUv + vec2(d.x, d.y)) * 2.0;",
            "  sum += texture2D(tInput, vUv + vec2(d.x * 2.0, 0.0));",
            "  sum += texture2D(tInput, vUv + vec2(d.x, -d.y)) * 2.0;",
            "  sum += texture2D(tInput, vUv + vec2(0.0, -d.y * 2.0));",
            "  sum += texture2D(tInput, vUv + vec2(-d.x, -d.y)) * 2.0;",
            "  vec4 up = sum / 12.0;",
            "  vec4 base = texture2D(tBlend, vUv);",
            "  gl_FragColor = up + base * uBlendWeight;",
            "}",
          ].join("\\n"),
          uniforms: {
            tInput: { value: null },
            tBlend: { value: null },
            uHalfPixel: { value: new THREE.Vector2(0.001, 0.001) },
            uOffset: { value: 1.5 },
            uBlendWeight: { value: 0.45 },
          },
          depthTest: false,
          depthWrite: false,
        });

        // ACESFilmic HDR tone-mapping + premultiplied alpha composite onto MapLibre framebuffer
        const compMat = new THREE.ShaderMaterial({
          vertexShader: fsVert,
          fragmentShader: [
            "uniform sampler2D tScene;",
            "uniform sampler2D tBloom;",
            "uniform float uBloomStrength;",
            "uniform float uExposure;",
            "varying vec2 vUv;",
            "vec3 acesFilmic(vec3 x) {",
            "  const float a = 2.51;",
            "  const float b = 0.03;",
            "  const float c = 2.43;",
            "  const float d = 0.59;",
            "  const float e = 0.14;",
            "  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);",
            "}",
            "vec3 linearToSRGB(vec3 c) {",
            "  vec3 lo = c * 12.92;",
            "  vec3 hi = 1.055 * pow(max(c, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055;",
            "  return mix(lo, hi, step(vec3(0.0031308), c));",
            "}",
            "void main() {",
            "  vec4 sc = texture2D(tScene, vUv);",
            "  vec3 bl = texture2D(tBloom, vUv).rgb * uBloomStrength;",
            "  float a = clamp(sc.a, 0.0, 1.0);",
            "  vec3 unpremul = a > 1e-4 ? (sc.rgb / a) : vec3(0.0);",
            "  vec3 sceneMapped = linearToSRGB(acesFilmic(unpremul * uExposure)) * a;",
            "  vec3 bloomMapped = linearToSRGB(acesFilmic(bl * uExposure));",
            "  vec3 outRgb = sceneMapped + bloomMapped;",
            "  gl_FragColor = vec4(outRgb, a);",
            "}",
          ].join("\\n"),
          uniforms: {
            tScene: { value: null },
            tBloom: { value: null },
            uBloomStrength: { value: 0.28 },
            uExposure: { value: 0.92 },
          },
          transparent: true,
          blending: THREE.CustomBlending,
          blendEquation: THREE.AddEquation,
          blendSrc: THREE.OneFactor,
          blendDst: THREE.OneMinusSrcAlphaFactor,
          depthTest: false,
          depthWrite: false,
        });

        const quad = new THREE.Mesh(fsGeo, brightMat);
        const fsScene = new THREE.Scene();
        fsScene.add(quad);

        const hasHalfFloat = Boolean(
          gl.getExtension("EXT_color_buffer_float") ||
          gl.getExtension("EXT_color_buffer_half_float")
        );
        return {
          fsCam,
          fsScene,
          quad,
          brightMat,
          downMat,
          upMat,
          compMat,
          texType: hasHalfFloat ? THREE.HalfFloatType : THREE.UnsignedByteType,
          rtW: 0,
          rtH: 0,
          sceneRT: null,
          downRTs: [],
          upRTs: [],
          rendered: false,
        };
      }

      function ensureBloomTargets(st, widthPx, heightPx) {
        const w = Math.max(64, Math.round(widthPx || W));
        const h = Math.max(64, Math.round(heightPx || H));
        if (st.rtW === w && st.rtH === h && st.sceneRT) return;
        disposeBloomTargets(st);
        const mkRT = (rw, rh, withDepth) => {
          const rt = new THREE.WebGLRenderTarget(Math.max(16, rw), Math.max(16, rh), {
            type: st.texType,
            minFilter: THREE.LinearFilter,
            magFilter: THREE.LinearFilter,
            wrapS: THREE.ClampToEdgeWrapping,
            wrapT: THREE.ClampToEdgeWrapping,
            depthBuffer: withDepth,
            stencilBuffer: false,
          });
          return rt;
        };
        st.sceneRT = mkRT(w, h, true);
        st.downRTs = [
          mkRT(w >> 1, h >> 1, false),
          mkRT(w >> 2, h >> 2, false),
          mkRT(w >> 3, h >> 3, false),
        ];
        st.upRTs = [
          mkRT(w >> 1, h >> 1, false),
          mkRT(w >> 2, h >> 2, false),
        ];
        st.rtW = w;
        st.rtH = h;
      }

      let hasActive3D = false;
      const customLayer = {
        id: "vedit-three-3d",
        type: "custom",
        renderingMode: "3d",
        onAdd(m, gl) {
          renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true });
          renderer.autoClear = false;
          renderer.shadowMap.enabled = true;
          renderer.shadowMap.type = THREE.PCFSoftShadowMap;
          if (window.THREE_ADDONS && window.THREE_ADDONS.RoomEnvironment && typeof THREE.PMREMGenerator === "function") {
            const pmrem = new THREE.PMREMGenerator(renderer);
            const envTex = pmrem.fromScene(new window.THREE_ADDONS.RoomEnvironment(), 0.04).texture;
            scene.environment = envTex;
            if ("environmentIntensity" in scene) scene.environmentIntensity = 0.26;
            pmrem.dispose();
          }
          if (HDR_BLOOM_ENABLED) {
            try {
              bloomState = initDualKawaseBloom(gl);
            } catch {
              bloomState = null;
            }
          }
        },
        prerender(gl, options) {
          if (!renderer || !bloomState || !hasActive3D) {
            if (bloomState) bloomState.rendered = false;
            return;
          }
          const rawMat = (options && options.defaultProjectionData && options.defaultProjectionData.mainMatrix) || options;
          if (!rawMat) return;
          camera.projectionMatrix = new THREE.Matrix4().fromArray(rawMat).multiply(sceneOriginMat);
          updateCameraLocalPos(camera.projectionMatrix);

          const prevFbo = gl.getParameter(gl.FRAMEBUFFER_BINDING);
          const prevVp = gl.getParameter(gl.VIEWPORT);
          ensureBloomTargets(bloomState, gl.drawingBufferWidth, gl.drawingBufferHeight);

          renderer.resetState();
          // 1. Render 3D HDR scene + PCF soft shadows into sceneRT
          renderer.setRenderTarget(bloomState.sceneRT);
          renderer.setClearColor(0x000000, 0);
          renderer.clear(true, true, false);
          renderer.render(scene, camera);

          // 2. Bright-pass threshold -> downRTs[0] (1/2 res)
          bloomState.brightMat.uniforms.tInput.value = bloomState.sceneRT.texture;
          bloomState.quad.material = bloomState.brightMat;
          renderer.setRenderTarget(bloomState.downRTs[0]);
          renderer.clear(true, false, false);
          renderer.render(bloomState.fsScene, bloomState.fsCam);

          // 3. Dual-Kawase 5-tap downsample pyramid (1/2 -> 1/4 -> 1/8)
          bloomState.quad.material = bloomState.downMat;
          for (let i = 0; i < 2; i++) {
            const src = bloomState.downRTs[i];
            const dst = bloomState.downRTs[i + 1];
            bloomState.downMat.uniforms.tInput.value = src.texture;
            bloomState.downMat.uniforms.uHalfPixel.value.set(0.5 / src.width, 0.5 / src.height);
            bloomState.downMat.uniforms.uOffset.value = 1.6;
            renderer.setRenderTarget(dst);
            renderer.render(bloomState.fsScene, bloomState.fsCam);
          }

          // 4. Dual-Kawase 8-tap tent upsample pyramid (1/8 -> 1/4 -> 1/2)
          bloomState.quad.material = bloomState.upMat;
          // 1/8 -> upRTs[1] (1/4) blended with downRTs[1]
          bloomState.upMat.uniforms.tInput.value = bloomState.downRTs[2].texture;
          bloomState.upMat.uniforms.tBlend.value = bloomState.downRTs[1].texture;
          bloomState.upMat.uniforms.uHalfPixel.value.set(0.5 / bloomState.downRTs[2].width, 0.5 / bloomState.downRTs[2].height);
          bloomState.upMat.uniforms.uOffset.value = 1.6;
          bloomState.upMat.uniforms.uBlendWeight.value = 0.55;
          renderer.setRenderTarget(bloomState.upRTs[1]);
          renderer.render(bloomState.fsScene, bloomState.fsCam);

          // upRTs[1] (1/4) -> upRTs[0] (1/2) blended with downRTs[0]
          bloomState.upMat.uniforms.tInput.value = bloomState.upRTs[1].texture;
          bloomState.upMat.uniforms.tBlend.value = bloomState.downRTs[0].texture;
          bloomState.upMat.uniforms.uHalfPixel.value.set(0.5 / bloomState.upRTs[1].width, 0.5 / bloomState.upRTs[1].height);
          bloomState.upMat.uniforms.uOffset.value = 1.6;
          bloomState.upMat.uniforms.uBlendWeight.value = 0.42;
          renderer.setRenderTarget(bloomState.upRTs[0]);
          renderer.render(bloomState.fsScene, bloomState.fsCam);

          bloomState.rendered = true;
          renderer.setRenderTarget(null);
          gl.bindFramebuffer(gl.FRAMEBUFFER, prevFbo);
          if (prevVp) gl.viewport(prevVp[0], prevVp[1], prevVp[2], prevVp[3]);
          renderer.resetState();
        },
        render(gl, options) {
          if (!renderer || !hasActive3D) return;
          const rawMat = (options && options.defaultProjectionData && options.defaultProjectionData.mainMatrix) || options;
          camera.projectionMatrix = new THREE.Matrix4().fromArray(rawMat).multiply(sceneOriginMat);
          updateCameraLocalPos(camera.projectionMatrix);
          if (bloomState && bloomState.rendered) {
            renderer.resetState();
            bloomState.compMat.uniforms.tScene.value = bloomState.sceneRT.texture;
            bloomState.compMat.uniforms.tBloom.value = bloomState.upRTs[0].texture;
            bloomState.quad.material = bloomState.compMat;
            renderer.render(bloomState.fsScene, bloomState.fsCam);
            renderer.resetState();
          } else {
            renderer.resetState();
            renderer.clearDepth();
            renderer.render(scene, camera);
            renderer.resetState();
          }
        },
      };
      map.addLayer(customLayer);

      const cableCache = new Map();
      const modelCache = new Map();
      const volumeCache = new Map();
      const countryBlockCache = new Map();

      function pointInLocalRing(px, py, ring) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const xi = ring[i].x, yi = ring[i].y;
          const xj = ring[j].x, yj = ring[j].y;
          const intersect = ((yi > py) !== (yj > py)) && (px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-12) + xi);
          if (intersect) inside = !inside;
        }
        return inside;
      }

      function smoothLocalRingCorners(pts, iters = 1) {
        let cur = pts;
        for (let it = 0; it < iters; it++) {
          if (cur.length < 3 || cur.length > 900) break;
          const next = [];
          const n = cur.length;
          for (let i = 0; i < n; i++) {
            const a = cur[i];
            const b = cur[(i + 1) % n];
            next.push(
              new THREE.Vector2(a.x * 0.78 + b.x * 0.22, a.y * 0.78 + b.y * 0.22),
              new THREE.Vector2(a.x * 0.22 + b.x * 0.78, a.y * 0.22 + b.y * 0.78)
            );
          }
          cur = next;
        }
        return cur;
      }

      function buildCountryBlock3DEntry(layer, idx) {
        const geom = resolveGeom(layer.geom_ref);
        const { outer, inner } = polygonRings(geom);
        const grp = new THREE.Group();
        if (!outer.length) {
          scene.add(grp);
          return { key: layer.id || ("cblock_" + idx), grp, empty: true };
        }

        const toLocal2D = (ringLL) => {
          const pts = [];
          for (const c of ringLL || []) {
            if (!c || c.length < 2) continue;
            const v = lngLatAltToLocal(c[0], c[1], 0);
            if (!pts.length || Math.hypot(v.x - pts[pts.length - 1].x, v.y - pts[pts.length - 1].y) > 1e-3) {
              pts.push(new THREE.Vector2(v.x, v.y));
            }
          }
          if (pts.length > 1 && pts[0].distanceTo(pts[pts.length - 1]) < 1e-3) pts.pop();
          return pts;
        };

        const smoothIters = layer.round_corners === false ? 0 : Math.max(0, Math.min(2, Number(layer.corner_smooth_iters ?? 1)));
        const outerRings2D = [];
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const r of outer) {
          let pts = toLocal2D(r);
          if (pts.length < 3) continue;
          if (smoothIters > 0) pts = smoothLocalRingCorners(pts, smoothIters);
          for (const p of pts) {
            if (p.x < minX) minX = p.x;
            if (p.y < minY) minY = p.y;
            if (p.x > maxX) maxX = p.x;
            if (p.y > maxY) maxY = p.y;
          }
          outerRings2D.push(pts);
        }
        if (!outerRings2D.length) {
          scene.add(grp);
          return { key: layer.id || ("cblock_" + idx), grp, empty: true };
        }

        const holeRings2D = inner.map(toLocal2D).filter((h) => h.length >= 3);
        const shapes = outerRings2D.map((pts) => {
          const sh = new THREE.Shape(pts);
          for (const hole of holeRings2D) {
            if (pointInLocalRing(hole[0].x, hole[0].y, pts)) {
              sh.holes.push(new THREE.Path(hole));
            }
          }
          return sh;
        });

        const spanX = Math.max(100, maxX - minX);
        const spanY = Math.max(100, maxY - minY);
        const spanDiag = Math.hypot(spanX, spanY);
        const extrudeHeightM = Math.max(100, Number(layer.extrude_height_m || Math.max(15000, spanDiag * 0.055)));
        const bevelFrac = layer.bevel_px != null ? clamp(Number(layer.bevel_px) / 48, 0, 0.25) : 0.085;
        const bevelThickness = bevelFrac > 0.001 ? clamp(extrudeHeightM * bevelFrac, 80, extrudeHeightM * 0.18) : 0;
        const bevelSize = bevelFrac > 0.001 ? clamp(spanDiag * 0.0032 * (bevelFrac / 0.085), 50, spanDiag * 0.012) : 0;

        const extrudeGeo = new THREE.ExtrudeGeometry(shapes, {
          depth: extrudeHeightM,
          bevelEnabled: bevelThickness > 0 && bevelSize > 0,
          bevelThickness,
          bevelSize,
          bevelSegments: 3,
          curveSegments: 6,
        });

        // Normalize planar UVs across polygon footprint so flag textures and shaders map cleanly
        const posAttr = extrudeGeo.attributes.position;
        const uvAttr = extrudeGeo.attributes.uv;
        if (posAttr && uvAttr) {
          for (let i = 0; i < posAttr.count; i++) {
            const x = posAttr.getX(i);
            const y = posAttr.getY(i);
            uvAttr.setXY(i, (x - minX) / spanX, (y - minY) / spanY);
          }
          uvAttr.needsUpdate = true;
        }
        extrudeGeo.computeVertexNormals();

        // Optional flag texture mapped onto 3D top face
        let flagTex = null;
        if (layer.flag_fill) {
          const fImg = window.__imgCache[BASE_URL + "/flags/" + String(layer.flag_fill).toLowerCase() + ".svg"];
          if (fImg) {
            flagTex = new THREE.CanvasTexture(fImg);
            flagTex.colorSpace = THREE.SRGBColorSpace;
            flagTex.anisotropy = 4;
          }
        }

        const fillCol = new THREE.Color(layer.fill_hex || "#1F9D55");
        const sideCol = layer.side_hex
          ? new THREE.Color(layer.side_hex)
          : fillCol.clone().multiplyScalar(0.56);
        const fresnelCol = new THREE.Color(layer.fresnel_hex || layer.rim_hex || "#BAE6FD");
        const hatchCol = new THREE.Color(layer.hatch_color || "#FFFFFF");

        const topUniforms = {
          uCamPos: { value: camLocalPos },
          uScaleZ: { value: 1.0 },
          uFresnelColor: { value: fresnelCol },
          uFresnelIntensity: { value: Number(layer.fresnel_intensity ?? 0.28) },
          uHatchEnabled: { value: layer.hatch ? 1.0 : 0.0 },
          uHatchSpacingM: { value: Math.max(500, spanDiag / Math.max(8, Number(layer.hatch_density ?? 36))) },
          uHatchAngleRad: { value: ((Number(layer.hatch_angle_deg ?? 45)) * Math.PI) / 180 },
          uHatchProgress: { value: 1.0 },
          uHatchColor: { value: hatchCol },
          uHatchAlpha: { value: Number(layer.hatch_alpha ?? 0.36) },
          uBoundsMin: { value: new THREE.Vector2(minX, minY) },
          uBoundsSpan: { value: new THREE.Vector2(spanX, spanY) },
          uSweepProgress: { value: -1.0 },
          uSweepIntensity: { value: 0.0 },
          uSweepColor: { value: new THREE.Color("#FFFFFF") },
        };

        const topMat = new THREE.MeshStandardMaterial({
          color: flagTex ? 0xffffff : fillCol,
          map: flagTex,
          roughness: layer.roughness ?? 0.62,
          metalness: layer.metalness ?? 0.06,
          transparent: true,
          opacity: layer.fill_alpha ?? 0.96,
        });
        topMat.onBeforeCompile = (shader) => {
          Object.assign(shader.uniforms, topUniforms);
          shader.vertexShader = shader.vertexShader
            .replace(
              "#include <common>",
              "#include <common>\\nuniform vec3 uCamPos;\\nvarying vec3 vBlockLocalPos;\\nvarying vec3 vBlockLocalNorm;"
            )
            .replace(
              "#include <begin_vertex>",
              "#include <begin_vertex>\\nvBlockLocalPos = position;\\nvBlockLocalNorm = normal;"
            )
            .replace(
              "vViewPosition = - mvPosition.xyz;",
              "vViewPosition = uCamPos - (modelMatrix * vec4(transformed, 1.0)).xyz;"
            );
          shader.fragmentShader = shader.fragmentShader
            .replace(
              "#include <common>",
              [
                "#include <common>",
                "uniform vec3 uCamPos;",
                "uniform float uScaleZ;",
                "uniform vec3 uFresnelColor;",
                "uniform float uFresnelIntensity;",
                "uniform float uHatchEnabled;",
                "uniform float uHatchSpacingM;",
                "uniform float uHatchAngleRad;",
                "uniform float uHatchProgress;",
                "uniform vec3 uHatchColor;",
                "uniform float uHatchAlpha;",
                "uniform vec2 uBoundsMin;",
                "uniform vec2 uBoundsSpan;",
                "uniform float uSweepProgress;",
                "uniform float uSweepIntensity;",
                "uniform vec3 uSweepColor;",
                "varying vec3 vBlockLocalPos;",
                "varying vec3 vBlockLocalNorm;",
              ].join("\\n")
            )
            .replace(
              "#include <emissivemap_fragment>",
              [
                "#include <emissivemap_fragment>",
                "vec3 wPos = vec3(vBlockLocalPos.xy, vBlockLocalPos.z * max(uScaleZ, 0.005));",
                "vec3 wNorm = normalize(vec3(vBlockLocalNorm.xy, vBlockLocalNorm.z / max(uScaleZ, 0.01)));",
                "vec3 viewDirW = normalize(uCamPos - wPos);",
                "float ndv = clamp(dot(wNorm, viewDirW), 0.0, 1.0);",
                "float bevelMask = 1.0 - smoothstep(0.65, 0.96, wNorm.z);",
                "float fresnel = pow(1.0 - ndv, 3.2) * mix(0.28, 1.0, bevelMask);",
                "totalEmissiveRadiance += uFresnelColor * fresnel * uFresnelIntensity;",
                "if (uHatchEnabled > 0.5 && uHatchProgress > 0.001 && wNorm.z > 0.72) {",
                "  float ca = cos(uHatchAngleRad);",
                "  float sa = sin(uHatchAngleRad);",
                "  float nCoord = vBlockLocalPos.x * sa + vBlockLocalPos.y * ca;",
                "  float cell = nCoord / max(uHatchSpacingM, 1.0);",
                "  float fw = max(fwidth(cell), 1e-4);",
                "  float distLine = abs(fract(cell + 0.5) - 0.5);",
                "  float lineMask = 1.0 - smoothstep(0.045 - fw, 0.045 + fw, distLine);",
                "  vec2 uvNorm = (vBlockLocalPos.xy - uBoundsMin) / max(uBoundsSpan, vec2(1.0));",
                "  float rank = clamp(uvNorm.x * 0.65 + (1.0 - uvNorm.y) * 0.35, 0.0, 1.0);",
                "  float localP = clamp((uHatchProgress - rank * 0.55) / 0.45, 0.0, 1.0);",
                "  float uFrac = clamp((uvNorm.x * ca + (1.0 - uvNorm.y) * sa), 0.0, 1.0);",
                "  float sweepReveal = smoothstep(localP + 0.04, localP - 0.04, uFrac * 0.85);",
                "  float hMask = lineMask * sweepReveal * uHatchAlpha * step(0.002, localP);",
                "  diffuseColor.rgb = mix(diffuseColor.rgb, uHatchColor, clamp(hMask, 0.0, 0.75));",
                "  totalEmissiveRadiance += uHatchColor * hMask * 0.08;",
                "}",
                "if (uSweepIntensity > 0.005 && uSweepProgress >= 0.0 && uSweepProgress <= 1.0) {",
                "  vec2 uvNormS = (vBlockLocalPos.xy - uBoundsMin) / max(uBoundsSpan, vec2(1.0));",
                "  float diagS = (uvNormS.x * 0.72 + uvNormS.y * 0.28);",
                "  float band = exp(-pow((diagS - mix(-0.25, 1.25, uSweepProgress)) / 0.11, 2.0));",
                "  totalEmissiveRadiance += uSweepColor * band * uSweepIntensity * 0.65;",
                "}",
              ].join("\\n")
            );
        };

        const sideUniforms = {
          uExtrudeH: { value: Math.max(1, extrudeHeightM) },
          uFresnelColor: { value: fresnelCol },
          uCamPos: { value: camLocalPos },
          uScaleZ: { value: 1.0 },
        };
        const sideMat = new THREE.MeshStandardMaterial({
          color: sideCol,
          roughness: layer.side_roughness ?? 0.68,
          metalness: layer.side_metalness ?? 0.10,
          transparent: true,
          opacity: layer.fill_alpha ?? 0.96,
        });
        sideMat.onBeforeCompile = (shader) => {
          Object.assign(shader.uniforms, sideUniforms);
          shader.vertexShader = shader.vertexShader
            .replace(
              "#include <common>",
              "#include <common>\\nuniform vec3 uCamPos;\\nvarying vec3 vSideLocalPos;"
            )
            .replace(
              "#include <begin_vertex>",
              "#include <begin_vertex>\\nvSideLocalPos = position;"
            )
            .replace(
              "vViewPosition = - mvPosition.xyz;",
              "vViewPosition = uCamPos - (modelMatrix * vec4(transformed, 1.0)).xyz;"
            );
          shader.fragmentShader = shader.fragmentShader
            .replace(
              "#include <common>",
              "#include <common>\\nuniform float uExtrudeH;\\nvarying vec3 vSideLocalPos;"
            )
            .replace(
              "#include <dithering_fragment>",
              [
                "float baseAO = mix(0.38, 1.0, smoothstep(0.0, 0.55, vSideLocalPos.z / max(uExtrudeH, 1.0)));",
                "gl_FragColor.rgb *= baseAO;",
                "#include <dithering_fragment>",
              ].join("\\n")
            );
        };

        const blockMesh = new THREE.Mesh(extrudeGeo, [topMat, sideMat]);
        blockMesh.castShadow = true;
        blockMesh.receiveShadow = true;
        blockMesh.frustumCulled = false;
        grp.add(blockMesh);

        // Crisp HDR emissive top perimeter rim for sharp figure-ground separation
        const rimLines = [];
        const rimCol = new THREE.Color(layer.rim_hex || "#F8FAFC");
        const rimIntensity = Number(layer.rim_emissive ?? 1.35);
        const rimMat = new THREE.LineBasicMaterial({
          color: rimCol.clone().multiplyScalar(rimIntensity),
          transparent: true,
          opacity: 0.95,
        });
        const rimZ = extrudeHeightM + bevelThickness + Math.max(40, extrudeHeightM * 0.008);
        for (const pts of outerRings2D) {
          const verts = pts.map((p) => new THREE.Vector3(p.x, p.y, rimZ));
          const lGeo = new THREE.BufferGeometry().setFromPoints(verts);
          const loop = new THREE.LineLoop(lGeo, rimMat);
          loop.frustumCulled = false;
          grp.add(loop);
          rimLines.push(loop);
        }

        scene.add(grp);
        return {
          key: layer.id || ("cblock_" + idx),
          grp,
          blockMesh,
          topMat,
          sideMat,
          rimMat,
          topUniforms,
          sideUniforms,
          baseFillAlpha: layer.fill_alpha ?? 0.96,
          boundsBox: new THREE.Box3(
            new THREE.Vector3(minX, minY, 0),
            new THREE.Vector3(maxX, maxY, extrudeHeightM + bevelThickness)
          ),
          empty: false,
        };
      }

      function buildCableEntry(layer, idx) {
        const rawCoords = resolveGeom(layer.coords_ref) || layer.coords || [];
        const coords = layer.reverse ? [...rawCoords].reverse() : rawCoords;
        const rawPts = coords.map((c) => {
          const v = lngLatAltToLocal(c[0], c[1], c[2] || 0);
          return v;
        });
        const curve = rawPts.length >= 2 ? new THREE.CatmullRomCurve3(rawPts, false, "catmullrom", 0.35) : null;
        const baseSegs = clamp(Math.round(Math.max(90, coords.length * 14)), 90, 320);
        const radialSegs = 14;
        const catenary = Boolean(layer.catenary);
        const spanAnchors = layer.span_fractions || null; // optional array of sub-spans for catenary sag
        const centerPts = [];
        const unitVert = [];
        let totalLenM = 1;
        if (curve) {
          let prev = null;
          totalLenM = 0;
          for (let i = 0; i <= baseSegs; i++) {
            const u = i / baseSegs;
            const p = curve.getPointAt(u);
            centerPts.push(p);
            if (prev) totalLenM += p.distanceTo(prev);
            prev = p;
          }
        }
        const frames = centerPts.length >= 2 ? computeParallelFrames(centerPts) : null;
        const texSet = getArmorTexSet(layer.armor_hex || "#E5B449", layer.jacket_hex || "#1E293B");
        const colorTex = texSet.makeWrapped(texSet.colCanvas);
        const bumpTex = texSet.makeWrapped(texSet.bumpCanvas);

        const offCount = Array.isArray(layer.parallel_offsets_px) && layer.parallel_offsets_px.length > 0
          ? layer.parallel_offsets_px
          : [0];
        const strands = offCount.map((offPx) => {
          const tubeGeo = new THREE.BufferGeometry();
          const vertCount = (baseSegs + 1) * (radialSegs + 1);
          const posArr = new Float32Array(vertCount * 3);
          const normArr = new Float32Array(vertCount * 3);
          const uvArr = new Float32Array(vertCount * 2);
          const idxArr = [];
          for (let i = 0; i <= baseSegs; i++) {
            const u = i / baseSegs;
            for (let j = 0; j <= radialSegs; j++) {
              const v = j / radialSegs;
              const k = i * (radialSegs + 1) + j;
              uvArr[k * 2] = u;
              uvArr[k * 2 + 1] = v;
              if (i < baseSegs && j < radialSegs) {
                const a = i * (radialSegs + 1) + j;
                const b = (i + 1) * (radialSegs + 1) + j;
                const c = (i + 1) * (radialSegs + 1) + (j + 1);
                const d = i * (radialSegs + 1) + (j + 1);
                idxArr.push(a, b, d, b, c, d);
              }
            }
          }
          tubeGeo.setAttribute("position", new THREE.BufferAttribute(posArr, 3));
          tubeGeo.setAttribute("normal", new THREE.BufferAttribute(normArr, 3));
          tubeGeo.setAttribute("uv", new THREE.BufferAttribute(uvArr, 2));
          tubeGeo.setIndex(idxArr);
          const mat = new THREE.MeshStandardMaterial({
            map: colorTex,
            bumpMap: bumpTex,
            bumpScale: 0.35,
            metalness: layer.metalness ?? 0.78,
            roughness: layer.roughness ?? 0.28,
            emissive: new THREE.Color(layer.emissive_hex || "#F59E0B"),
            emissiveIntensity: layer.emissive_intensity ?? 0.16,
            transparent: true,
            opacity: 1,
          });
          const mesh = new THREE.Mesh(tubeGeo, mat);
          mesh.frustumCulled = false;

          // Seabed / ground shadow ribbon under the cable
          const shGeo = new THREE.BufferGeometry();
          const shPos = new Float32Array((baseSegs + 1) * 2 * 3);
          const shIdx = [];
          for (let i = 0; i < baseSegs; i++) {
            const a = i * 2, b = i * 2 + 1, c = (i + 1) * 2, d = (i + 1) * 2 + 1;
            shIdx.push(a, c, b, c, d, b);
          }
          shGeo.setAttribute("position", new THREE.BufferAttribute(shPos, 3));
          shGeo.setIndex(shIdx);
          const shMat = new THREE.MeshBasicMaterial({
            color: 0x02080d,
            transparent: true,
            opacity: 0.42,
            side: THREE.DoubleSide,
            depthWrite: false,
          });
          const shMesh = new THREE.Mesh(shGeo, shMat);
          shMesh.frustumCulled = false;

          return { offPx, tubeGeo, posArr, normArr, mat, mesh, shGeo, shPos, shMat, shMesh };
        });

        const group = new THREE.Group();
        for (const s of strands) {
          group.add(s.shMesh);
          group.add(s.mesh);
        }

        // Energized induction rings travelling smoothly along sheath
        const pulseCount = Math.max(0, Math.round(layer.pulse_count ?? 3));
        const pulseRings = [];
        const ringMat = new THREE.MeshStandardMaterial({
          color: new THREE.Color(layer.pulse_hex || "#FDE047"),
          emissive: new THREE.Color(layer.pulse_hex || "#F59E0B"),
          emissiveIntensity: 0.95,
          roughness: 0.22,
          metalness: 0.65,
          transparent: true,
        });
        for (let p = 0; p < pulseCount; p++) {
          const rm = new THREE.Mesh(new THREE.TorusGeometry(1, 0.17, 8, 18), ringMat);
          rm.frustumCulled = false;
          group.add(rm);
          pulseRings.push(rm);
        }
        const tipSpark = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), ringMat);
        tipSpark.frustumCulled = false;
        group.add(tipSpark);

        let startCollar = null;
        let endCollar = null;
        if (layer.landing_collar) {
          const collarMat = new THREE.MeshStandardMaterial({
            color: 0x94a3b8,
            metalness: 0.85,
            roughness: 0.25,
          });
          startCollar = new THREE.Mesh(new THREE.CylinderGeometry(1.55, 1.85, 1.4, 14), collarMat);
          startCollar.rotation.x = Math.PI / 2;
          startCollar.frustumCulled = false;
          endCollar = startCollar.clone();
          endCollar.frustumCulled = false;
          group.add(startCollar, endCollar);
        }

        scene.add(group);
        return {
          key: layer.id || ("cable_" + idx),
          coords,
          baseSegs,
          radialSegs,
          centerPts,
          frames,
          totalLenM,
          colorTex,
          bumpTex,
          strands,
          pulseRings,
          ringMat,
          tipSpark,
          startCollar,
          endCollar,
          catenary,
          spanAnchors,
          group,
        };
      }

      function update3DScene(layers, t) {
        const curZoom = map.getZoom();
        const activeCables = new Set();
        const activeModels = new Set();
        const activeVolumes = new Set();
        const activeBlocks = new Set();
        const activeShadowBox = new THREE.Box3();
        let anyVisible3D = false;
        let anyShadowCaster = false;

        for (let idx = 0; idx < (layers || []).length; idx++) {
          const layer = layers[idx];
          const tStart = layer.start_s ?? 0;
          const tEnd = layer.end_s ?? 1e9;
          const visible = t >= tStart - 0.001 && t <= tEnd + 0.001;
          const fadeIn = layer.fade_in_s ? easeOutCubic(seg(t, tStart, tStart + layer.fade_in_s)) : 1;
          const fadeOut = layer.fade_out_s ? 1 - easeInCubic(seg(t, tEnd - layer.fade_out_s, tEnd)) : 1;
          const alpha = clamp(fadeIn * fadeOut * (layer.opacity ?? 1), 0, 1);

          if (layer.type === "cable_3d") {
            const key = layer.id || ("cable_" + idx);
            let entry = cableCache.get(key);
            if (!entry) {
              entry = buildCableEntry(layer, idx);
              cableCache.set(key, entry);
            }
            activeCables.add(key);
            entry.group.visible = visible && alpha > 0.01 && entry.centerPts.length >= 2;
            if (!entry.group.visible) continue;
            anyVisible3D = true;

            const midLat = entry.coords.length ? entry.coords[Math.floor(entry.coords.length / 2)][1] : originLat;
            const rawRMeters = metersForScreenPx(
              layer.radius_px ?? 5.5,
              midLat,
              curZoom,
              layer.radius_ref_zoom ?? curZoom,
              layer.radius_coupling ?? 0.42,
              layer.min_scale ?? 0.45,
              layer.max_scale ?? 2.8
            );
            const minScreenPx = Number(layer.min_screen_radius_px || 0);
            const minRMeters = minScreenPx > 0 ? metersForScreenPx(minScreenPx, midLat, curZoom, curZoom, 0, 1, 1) : 0;
            const rMeters = Math.max(rawRMeters, minRMeters);
            const endTaperM = Math.max(0, Number(layer.end_taper_m || 0));
            const altMeters = layer.altitude_px != null
              ? metersForScreenPx(layer.altitude_px, midLat, curZoom, layer.radius_ref_zoom ?? curZoom, layer.radius_coupling ?? 0.42, layer.min_scale ?? 0.45, layer.max_scale ?? 2.8)
              : rMeters * 1.15;
            const sagMeters = metersForScreenPx(layer.catenary_sag_px ?? 16, midLat, curZoom, layer.radius_ref_zoom ?? curZoom, layer.radius_coupling ?? 0.42, 0.45, 2.8);

            const drawS = layer.instant === true ? 0 : (layer.draw_duration_s ?? 1.2);
            const drawFrom = tStart + (layer.draw_delay_s ?? 0);
            const drawEase = layer.draw_ease || "editorial_out";
            const prog = drawS > 0 ? evalEase(drawEase, seg(t, drawFrom, drawFrom + drawS)) : (t >= drawFrom - 0.001 ? 1 : 0);
            const exactSegPos = clamp(entry.baseSegs * prog, 0, entry.baseSegs);
            const fullSegs = Math.floor(exactSegPos);
            const segFrac = exactSegPos - fullSegs;
            const hasTipFrac = segFrac > 1e-4 && fullSegs < entry.baseSegs;
            const drawSegs = hasTipFrac ? fullSegs + 1 : fullSegs;

            const repU = clamp(entry.totalLenM / Math.max(1, rMeters * 4.5), 6, 420);
            entry.colorTex.repeat.set(repU, 1);
            entry.bumpTex.repeat.set(repU, 1);

            const N = entry.frames.normals;
            const B = entry.frames.binormals;
            const T = entry.frames.tangents;
            const rSeg = entry.radialSegs;
            const sampleCenterAt = (fIdx) => {
              const i0 = clamp(Math.floor(fIdx), 0, entry.baseSegs);
              const i1 = Math.min(entry.baseSegs, i0 + 1);
              const f = clamp(fIdx - i0, 0, 1);
              const cp = entry.centerPts[i0].clone().lerp(entry.centerPts[i1], f);
              const tan = T[i0].clone().lerp(T[i1], f).normalize();
              const nVec = N[i0].clone().lerp(N[i1], f).normalize();
              const bVec = B[i0].clone().lerp(B[i1], f).normalize();
              return { cp, tan, nVec, bVec, u: fIdx / entry.baseSegs };
            };

            for (const st of entry.strands) {
              const latShiftM = st.offPx
                ? metersForScreenPx(st.offPx, midLat, curZoom, layer.radius_ref_zoom ?? curZoom, layer.radius_coupling ?? 0.42, 0.45, 2.8)
                : 0;
              st.mat.opacity = alpha;
              st.shMat.opacity = alpha * (entry.catenary ? 0.30 : 0.48);

              for (let i = 0; i <= drawSegs; i++) {
                const isFracTip = hasTipFrac && i === drawSegs;
                const sData = isFracTip ? sampleCenterAt(exactSegPos) : {
                  cp: entry.centerPts[i],
                  tan: T[i],
                  nVec: N[i],
                  bVec: B[i],
                  u: i / entry.baseSegs,
                };
                const u = sData.u;
                let sagOff = 0;
                if (entry.catenary) {
                  const nSpans = Math.max(1, (entry.coords.length || 2) - 1);
                  const spanPhase = (u * nSpans) % 1;
                  sagOff = -Math.sin(spanPhase * Math.PI) * sagMeters;
                }
                const cp = sData.cp;
                const tan = sData.tan;
                const sideDir = new THREE.Vector3(-tan.y, tan.x, 0).normalize();
                if (sideDir.lengthSq() < 0.01) sideDir.set(1, 0, 0);
                const cx = cp.x + sideDir.x * latShiftM;
                const cy = cp.y + sideDir.y * latShiftM;
                const cz = cp.z + altMeters + sagOff;

                const nVec = sData.nVec;
                const bVec = sData.bVec;
                let localRad = rMeters;
                if (endTaperM > 0) {
                  const distFromStart = u * entry.totalLenM;
                  const distFromEnd = (1 - u) * entry.totalLenM;
                  const taperFactor = Math.min(1, distFromStart / endTaperM, distFromEnd / endTaperM);
                  localRad = rMeters * clamp(taperFactor, 0.15, 1.0);
                }
                for (let j = 0; j <= rSeg; j++) {
                  const theta = (j / rSeg) * Math.PI * 2;
                  const cosT = Math.cos(theta), sinT = Math.sin(theta);
                  const nx = nVec.x * cosT + bVec.x * sinT;
                  const ny = nVec.y * cosT + bVec.y * sinT;
                  const nz = nVec.z * cosT + bVec.z * sinT;
                  const k = (i * (rSeg + 1) + j) * 3;
                  st.posArr[k] = cx + nx * localRad;
                  st.posArr[k + 1] = cy + ny * localRad;
                  st.posArr[k + 2] = cz + nz * localRad;
                  st.normArr[k] = nx;
                  st.normArr[k + 1] = ny;
                  st.normArr[k + 2] = nz;
                }
                const sk = i * 6;
                const sw = rMeters * 1.65;
                st.shPos[sk] = cx - sideDir.x * sw;
                st.shPos[sk + 1] = cy - sideDir.y * sw;
                st.shPos[sk + 2] = cp.z + rMeters * 0.08;
                st.shPos[sk + 3] = cx + sideDir.x * sw;
                st.shPos[sk + 4] = cy + sideDir.y * sw;
                st.shPos[sk + 5] = cp.z + rMeters * 0.08;
              }
              st.tubeGeo.attributes.position.needsUpdate = true;
              st.tubeGeo.attributes.normal.needsUpdate = true;
              st.tubeGeo.setDrawRange(0, drawSegs * rSeg * 6);
              st.shGeo.attributes.position.needsUpdate = true;
              st.shGeo.setDrawRange(0, drawSegs * 6);
            }

            // Animate pulse rings continuously along sheath
            const pSpeed = Number(layer.pulse_speed || 0);
            entry.ringMat.opacity = alpha;
            if (pSpeed > 0 && exactSegPos >= 2) {
              const pLen = entry.pulseRings.length;
              for (let p = 0; p < pLen; p++) {
                const rm = entry.pulseRings[p];
                const ph = (((t - tStart) * pSpeed + p / Math.max(1, pLen)) % 1 + 1) % 1;
                const sData = sampleCenterAt(ph * exactSegPos);
                rm.visible = true;
                rm.position.set(sData.cp.x, sData.cp.y, sData.cp.z + altMeters);
                rm.scale.setScalar(rMeters * 1.18);
                rm.lookAt(sData.cp.x + sData.tan.x, sData.cp.y + sData.tan.y, sData.cp.z + altMeters + sData.tan.z);
              }
            } else {
              for (const rm of entry.pulseRings) rm.visible = false;
            }
            if (entry.startCollar && entry.endCollar) {
              const sp0 = entry.centerPts[0];
              entry.startCollar.visible = exactSegPos >= 0.5;
              entry.startCollar.position.set(sp0.x, sp0.y, sp0.z + altMeters * 0.55);
              entry.startCollar.scale.set(rMeters, rMeters, Math.max(rMeters, altMeters));
              const spEnd = entry.centerPts[entry.baseSegs];
              entry.endCollar.visible = prog >= 0.99;
              entry.endCollar.position.set(spEnd.x, spEnd.y, spEnd.z + altMeters * 0.55);
              entry.endCollar.scale.set(rMeters, rMeters, Math.max(rMeters, altMeters));
            }
            if (prog > 0.01 && prog < 0.995 && exactSegPos > 0.1) {
              const tipData = sampleCenterAt(exactSegPos);
              entry.tipSpark.visible = true;
              entry.tipSpark.position.set(tipData.cp.x, tipData.cp.y, tipData.cp.z + altMeters);
              entry.tipSpark.scale.setScalar(rMeters * 1.8);
            } else {
              entry.tipSpark.visible = false;
            }
          } else if (layer.type === "country_block_3d") {
            const key = layer.id || ("cblock_" + idx);
            let entry = countryBlockCache.get(key);
            if (!entry) {
              entry = buildCountryBlock3DEntry(layer, idx);
              countryBlockCache.set(key, entry);
            }
            activeBlocks.add(key);
            entry.grp.visible = visible && alpha > 0.01 && !entry.empty;
            if (!entry.grp.visible) continue;
            anyVisible3D = true;
            anyShadowCaster = true;

            const riseDelay = Number(layer.rise_delay_s ?? 0);
            const riseDur = layer.rise_duration_s != null ? Math.max(0, Number(layer.rise_duration_s)) : 0.72;
            const riseEase = layer.rise_ease || "spring_tactile";
            const riseRaw = riseDur > 0 ? evalEase(riseEase, seg(t, tStart + riseDelay, tStart + riseDelay + riseDur)) : 1.0;
            const scaleZ = Math.max(0.005, riseRaw);
            entry.grp.scale.set(1, 1, scaleZ);
            entry.topUniforms.uScaleZ.value = scaleZ;
            entry.sideUniforms.uScaleZ.value = scaleZ;
            entry.topMat.opacity = entry.baseFillAlpha * alpha;
            entry.sideMat.opacity = entry.baseFillAlpha * alpha;
            entry.rimMat.opacity = 0.95 * alpha;

            if (layer.hatch) {
              const hDelay = Number(layer.hatch_delay_s ?? (riseDelay + riseDur * 0.45));
              const hDur = layer.hatch_draw_s != null ? Math.max(0, Number(layer.hatch_draw_s)) : 0.85;
              entry.topUniforms.uHatchEnabled.value = 1.0;
              entry.topUniforms.uHatchProgress.value = hDur > 0 ? evalEase("editorial_out", seg(t, tStart + hDelay, tStart + hDelay + hDur)) : 1.0;
            } else {
              entry.topUniforms.uHatchEnabled.value = 0.0;
            }

            if (layer.light_sweep) {
              const lsObj = typeof layer.light_sweep === "object" ? layer.light_sweep : {};
              const lsAt = lsObj.at_s != null ? Number(lsObj.at_s) : (tStart + riseDelay + riseDur + Number(lsObj.delay_s ?? 0.1));
              const lsDur = Math.max(0.08, Number(lsObj.duration_s ?? 0.75));
              if (t >= lsAt && t <= lsAt + lsDur) {
                const u = easeInOutCubic(seg(t, lsAt, lsAt + lsDur));
                entry.topUniforms.uSweepProgress.value = u;
                entry.topUniforms.uSweepIntensity.value = Math.sin(u * Math.PI) * Number(lsObj.intensity ?? 0.65);
                if (lsObj.color) entry.topUniforms.uSweepColor.value.set(lsObj.color);
              } else {
                entry.topUniforms.uSweepIntensity.value = 0.0;
              }
            } else {
              entry.topUniforms.uSweepIntensity.value = 0.0;
            }

            activeShadowBox.union(entry.boundsBox);
          } else if (layer.type === "model_3d") {
            const key = layer.id || ("model_" + idx);
            let entry = modelCache.get(key);
            if (!entry) {
              let grp = null;
              const gltfUrl = layer.gltf_url
                ? (String(layer.gltf_url).startsWith("http")
                  ? String(layer.gltf_url)
                  : BASE_URL + "/" + String(layer.gltf_url).replace(/^\\/+/, ""))
                : null;
              if (gltfUrl && window.__gltfCache[gltfUrl]) {
                grp = new THREE.Group();
                const rawClone = window.__gltfCache[gltfUrl].clone(true);
                if (layer.up_axis !== "z") rawClone.rotation.x = Math.PI / 2;
                rawClone.updateMatrixWorld(true);
                const box = new THREE.Box3().setFromObject(rawClone);
                const size = new THREE.Vector3();
                const center = new THREE.Vector3();
                box.getSize(size);
                box.getCenter(center);
                const normH = Math.max(1e-4, size.z || size.y || 1);
                rawClone.position.set(-center.x, -center.y, -box.min.z);
                const holder = new THREE.Group();
                holder.add(rawClone);
                holder.scale.setScalar(1 / normH);
                if (layer.powered === false) {
                  rawClone.traverse((ch) => {
                    if (ch.isMesh && ch.material) {
                      const m = ch.material.clone();
                      if (m.color) m.color.multiplyScalar(0.45);
                      if ("emissiveIntensity" in m) m.emissiveIntensity = 0.05;
                      ch.material = m;
                    }
                  });
                }
                addGroundShadow(grp, 0.72);
                grp.add(holder);
              } else if (layer.model === "transmission_tower") grp = buildTransmissionTowerModel(layer);
              else if (layer.model === "substation") grp = buildSubstationModel(layer);
              else if (layer.model === "solar_farm") grp = buildSolarFarmModel(layer);
              else if (layer.model === "survey_vessel") grp = buildSurveyVesselModel(layer);
              else grp = buildTransmissionTowerModel(layer);
              grp.traverse((ch) => {
                if (ch.isMesh) {
                  ch.castShadow = true;
                  ch.receiveShadow = true;
                }
              });
              scene.add(grp);
              entry = { key, grp };
              modelCache.set(key, entry);
            }
            activeModels.add(key);
            entry.grp.visible = visible && alpha > 0.01;
            if (!entry.grp.visible) continue;
            anyVisible3D = true;
            anyShadowCaster = true;

            let curCoord = layer.coord || [originLng, originLat];
            let headingDeg = layer.heading_deg || 0;
            if (Array.isArray(layer.path) && layer.path.length >= 2) {
              const moveDur = layer.move_duration_s ?? Math.max(0.1, tEnd - tStart);
              const u = clamp(seg(t, tStart, tStart + moveDur), 0, 1);
              curCoord = samplePolylineCoord(layer.path, u);
              if (layer.auto_heading !== false) {
                const cA = samplePolylineCoord(layer.path, Math.max(0, u - 0.02));
                const cB = samplePolylineCoord(layer.path, Math.min(1, u + 0.02));
                const pA = lngLatAltToLocal(cA[0], cA[1], 0);
                const pB = lngLatAltToLocal(cB[0], cB[1], 0);
                const dx = pB.x - pA.x, dy = pB.y - pA.y;
                if (Math.hypot(dx, dy) > 1e-3) {
                  headingDeg = (Math.atan2(-dx, dy) * 180) / Math.PI;
                }
              }
            }
            const elev = layer.model === "survey_vessel" ? 0 : groundElevM(curCoord[0], curCoord[1]);
            const pos = lngLatAltToLocal(curCoord[0], curCoord[1], elev);
            const hMeters = metersForScreenPx(
              layer.height_px ?? 95,
              curCoord[1],
              curZoom,
              layer.ref_zoom ?? curZoom,
              layer.scale_coupling ?? 0.46,
              layer.min_scale ?? 0.45,
              layer.max_scale ?? 2.8
            );
            const riseP = layer.rise_duration_s
              ? easeOutBack(seg(t, tStart, tStart + layer.rise_duration_s))
              : 1.0;
            const exitSc = (layer.exit_scale_down_s && t > tEnd - layer.exit_scale_down_s)
              ? 1 - easeInCubic(seg(t, tEnd - layer.exit_scale_down_s, tEnd))
              : 1.0;
            const scXY = hMeters * clamp(exitSc, 0.01, 1.5);
            const scZ = hMeters * clamp(riseP, 0.02, 1.15) * clamp(exitSc, 0.01, 1.5);
            entry.grp.position.copy(pos);
            entry.grp.rotation.set(0, 0, (headingDeg * Math.PI) / 180);
            entry.grp.scale.set(scXY, scXY, scZ);
            activeShadowBox.expandByPoint(new THREE.Vector3(pos.x - scXY, pos.y - scXY, pos.z));
            activeShadowBox.expandByPoint(new THREE.Vector3(pos.x + scXY, pos.y + scXY, pos.z + scZ));
          } else if (layer.type === "volume_3d") {
            const key = layer.id || ("vol_" + idx);
            let entry = volumeCache.get(key);
            if (!entry) {
              const grp = new THREE.Group();
              const wM = Number(layer.width_m || 10000);
              const lM = Number(layer.length_m || 10000);
              const hM = Number(layer.height_m || 1200);
              const boxGeo = new THREE.BoxGeometry(wM, lM, hM);
              const wallMat = new THREE.MeshStandardMaterial({
                color: new THREE.Color(layer.fill_hex || "#F59E0B"),
                emissive: new THREE.Color(layer.fill_hex || "#F59E0B"),
                emissiveIntensity: 0.35,
                transparent: true,
                opacity: layer.fill_alpha ?? 0.32,
                depthWrite: false,
                side: THREE.DoubleSide,
              });
              const boxMesh = new THREE.Mesh(boxGeo, wallMat);
              boxMesh.position.set(0, 0, hM * 0.5);
              grp.add(boxMesh);

              const edgeMat = new THREE.LineBasicMaterial({
                color: new THREE.Color(layer.edge_hex || "#FEF08A"),
                transparent: true,
                opacity: 0.95,
              });
              const edges = new THREE.LineSegments(new THREE.EdgesGeometry(boxGeo), edgeMat);
              edges.position.set(0, 0, hM * 0.5);
              grp.add(edges);

              if (layer.grid_top !== false) {
                const topTex = makeVolumeTopTex(layer.edge_hex || "#FEF08A");
                const topMat = new THREE.MeshBasicMaterial({
                  map: topTex,
                  transparent: true,
                  opacity: 0.85,
                  side: THREE.DoubleSide,
                  depthWrite: false,
                });
                const topPlane = new THREE.Mesh(new THREE.PlaneGeometry(wM, lM), topMat);
                topPlane.position.set(0, 0, hM + 2);
                grp.add(topPlane);
              }
              scene.add(grp);
              entry = { key, grp, wallMat, edgeMat, baseFillAlpha: layer.fill_alpha ?? 0.32 };
              volumeCache.set(key, entry);
            }
            activeVolumes.add(key);
            entry.grp.visible = visible && alpha > 0.01;
            if (!entry.grp.visible) continue;
            anyVisible3D = true;
            const c = layer.coord || [originLng, originLat];
            const pos = lngLatAltToLocal(c[0], c[1], groundElevM(c[0], c[1]));
            const riseP = layer.rise_duration_s ? easeOutCubic(seg(t, tStart, tStart + layer.rise_duration_s)) : 1.0;
            entry.grp.position.copy(pos);
            entry.grp.rotation.set(0, 0, ((layer.heading_deg || 0) * Math.PI) / 180);
            entry.grp.scale.set(1, 1, clamp(riseP, 0.02, 1.0));
            entry.wallMat.opacity = entry.baseFillAlpha * alpha;
            entry.edgeMat.opacity = 0.95 * alpha;
          }
        }

        for (const [k, v] of cableCache.entries()) if (!activeCables.has(k)) v.group.visible = false;
        for (const [k, v] of modelCache.entries()) if (!activeModels.has(k)) v.grp.visible = false;
        for (const [k, v] of volumeCache.entries()) if (!activeVolumes.has(k)) v.grp.visible = false;
        for (const [k, v] of countryBlockCache.entries()) if (!activeBlocks.has(k)) v.grp.visible = false;

        hasActive3D = anyVisible3D;
        if (anyShadowCaster && !activeShadowBox.isEmpty()) {
          const boxCenter = new THREE.Vector3();
          const boxSize = new THREE.Vector3();
          activeShadowBox.getCenter(boxCenter);
          activeShadowBox.getSize(boxSize);
          const rad = Math.max(100, boxSize.length() * 0.68);
          keySun.target.position.set(boxCenter.x, boxCenter.y, 0);
          keySun.position.set(
            boxCenter.x + SUN_VEC.x * rad * 2.2,
            boxCenter.y + SUN_VEC.y * rad * 2.2,
            Math.max(rad * 0.6, SUN_VEC.z * rad * 2.2)
          );
          keySun.shadow.camera.left = -rad;
          keySun.shadow.camera.right = rad;
          keySun.shadow.camera.top = rad;
          keySun.shadow.camera.bottom = -rad;
          keySun.shadow.camera.near = rad * 0.1;
          keySun.shadow.camera.far = rad * 6.0;
          keySun.shadow.camera.updateProjectionMatrix();
          keySun.shadow.normalBias = Math.max(0.02, rad * 0.0005);
          shadowGround.position.set(boxCenter.x, boxCenter.y, 0.02);
          shadowGround.scale.set(rad * 4.5, rad * 4.5, 1);
          shadowGround.visible = true;
        } else {
          shadowGround.visible = false;
        }
      }

      return update3DScene;
    }

    window.__drawSceneLayers = function(layers, t) {
      if (__update3DScene) {
        __update3DScene(layers, t);
      }
      drawLayers(layers, t);
      if (__update3DScene) {
        map.triggerRepaint();
        return new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)));
      }
    };

    // Optical sub-frame shutter accumulator with arbitrary per-sample weights (cosine/trapezoid window).
    window.__beginShutterAccum = function() {
      compCanvas.style.display = "block";
      compCtx.clearRect(0, 0, W, H);
    };
    window.__accumSubframe = function(weightOrIdx, cumWeight) {
      compCtx.save();
      const blendAlpha = (cumWeight != null && cumWeight > 0)
        ? clamp(Number(weightOrIdx) / Number(cumWeight), 0, 1)
        : (1 / (Number(weightOrIdx) + 1));
      compCtx.globalAlpha = blendAlpha;
      if (Math.abs(window.__currentRoll) > 0.01) {
        const sc = computeRollOverscan(window.__currentRoll);
        compCtx.translate(W * 0.5, H * 0.5);
        compCtx.rotate((window.__currentRoll * Math.PI) / 180);
        compCtx.scale(sc, sc);
        compCtx.translate(-W * 0.5, -H * 0.5);
      }
      compCtx.drawImage(map.getCanvas(), 0, 0, W, H);
      compCtx.drawImage(ovCanvas, 0, 0, W, H);
      compCtx.restore();
    };
    window.__endShutterAccum = function() {
      compCanvas.style.display = "none";
    };

    // Radial zoom blur around the frame centre for act cuts. Reads the shutter
    // composite when one is showing, otherwise the map and overlay canvases with the
    // current roll, then averages scaled copies from 1 to 1 + amount into the
    // composite canvas. The caller hides the composite after capture.
    const cutBlurSrc = document.createElement("canvas");
    cutBlurSrc.width = W; cutBlurSrc.height = H;
    const cutBlurSrcCtx = cutBlurSrc.getContext("2d");
    window.__cutBlurComposite = function(amount, copies) {
      cutBlurSrcCtx.save();
      cutBlurSrcCtx.clearRect(0, 0, W, H);
      if (compCanvas.style.display === "block") {
        cutBlurSrcCtx.drawImage(compCanvas, 0, 0, W, H);
      } else {
        if (Math.abs(window.__currentRoll || 0) > 0.01) {
          const sc = computeRollOverscan(window.__currentRoll);
          cutBlurSrcCtx.translate(W * 0.5, H * 0.5);
          cutBlurSrcCtx.rotate((window.__currentRoll * Math.PI) / 180);
          cutBlurSrcCtx.scale(sc, sc);
          cutBlurSrcCtx.translate(-W * 0.5, -H * 0.5);
        }
        cutBlurSrcCtx.drawImage(map.getCanvas(), 0, 0, W, H);
        cutBlurSrcCtx.drawImage(ovCanvas, 0, 0, W, H);
      }
      cutBlurSrcCtx.restore();
      const n = Math.max(2, Math.min(24, Math.round(copies) || 12));
      compCanvas.style.display = "block";
      compCtx.save();
      compCtx.clearRect(0, 0, W, H);
      for (let k = 0; k < n; k++) {
        const sc = 1 + amount * (k / (n - 1));
        compCtx.globalAlpha = 1 / (k + 1);
        compCtx.setTransform(sc, 0, 0, sc, W * 0.5 * (1 - sc), H * 0.5 * (1 - sc));
        compCtx.drawImage(cutBlurSrc, 0, 0, W, H);
      }
      compCtx.restore();
    };
  </script>
</body>
</html>`;
}

function buildBlueprintHtml(baseUrl, width, height, vectorsJson, actSpec) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
${typeof buildDynamicFontFaceCss === "function" ? buildDynamicFontFaceCss(baseUrl) : ""}
    * { margin: 0; padding: 0; }
    html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #1E1B18; }
    canvas { display: block; width: ${width}px; height: ${height}px; }
  </style>
</head>
<body>
  <canvas id="c" width="${width}" height="${height}"></canvas>
  <script>
    const VEC = ${vectorsJson};
    const SPEC = ${JSON.stringify(actSpec)};
    const W = ${width}, H = ${height};
    const ctx = document.getElementById("c").getContext("2d");
    const maskC = document.createElement("canvas"); maskC.width = 1200; maskC.height = 1700;
    const maskX = maskC.getContext("2d");

    const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
    const lerp = (a, b, t) => a + (b - a) * t;
    const seg = (t, a, b) => (b <= a ? 1 : clamp((t - a) / (b - a), 0, 1));
    const easeInOutCubic = (x) => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
    const easeOutCubic = (x) => 1 - Math.pow(1 - x, 3);
    const easeInExpo = (x) => x <= 0 ? 0 : Math.pow(2, 10 * (x - 1));

    function resolveGeom(ref) {
      if (!ref) return null;
      if (typeof ref === "object" && ref.type) return ref;
      let cur = VEC;
      for (const p of String(ref).split(".")) cur = cur ? cur[p] : null;
      return cur;
    }

    const cLng = SPEC.center?.[0] ?? -77.55;
    const cLat = SPEC.center?.[1] ?? 8.15;
    function projLocal(lng, lat) {
      return [(lng - cLng) * 235, -(lat - cLat) * 245];
    }
    function traceLocal(targetCtx, geom, ox = 0, oy = 0) {
      if (!geom) return;
      const doRing = (ring) => {
        for (let i = 0; i < ring.length; i++) {
          const [x, y] = projLocal(ring[i][0], ring[i][1]);
          if (i === 0) targetCtx.moveTo(x + ox, y + oy);
          else targetCtx.lineTo(x + ox, y + oy);
        }
        targetCtx.closePath();
      };
      if (geom.type === "Polygon") geom.coordinates.forEach(doRing);
      else if (geom.type === "MultiPolygon") geom.coordinates.forEach((p) => p.forEach(doRing));
    }

    function drawPartial(pts, prog, strokeStyle, width) {
      if (prog <= 0.001 || pts.length < 2) return;
      const lens = [0]; let tot = 0;
      for (let i = 1; i < pts.length; i++) { tot += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); lens.push(tot); }
      const target = tot * clamp(prog, 0, 1);
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) {
        if (lens[i] <= target) ctx.lineTo(pts[i][0], pts[i][1]);
        else {
          const f = (target - lens[i - 1]) / Math.max(1e-5, lens[i] - lens[i - 1]);
          ctx.lineTo(lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f));
          break;
        }
      }
      ctx.strokeStyle = strokeStyle; ctx.lineWidth = width; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke();
    }

    const regionGeom = resolveGeom(SPEC.region_ref);
    const landGeoms = (SPEC.land_refs || []).map(resolveGeom).filter(Boolean);
    const northPts = (SPEC.north_road || []).map((c) => projLocal(c[0], c[1]));
    const southPts = (SPEC.south_road || []).map((c) => projLocal(c[0], c[1]));
    const failPts = (SPEC.failed_road || []).map((c) => projLocal(c[0], c[1]));

    // Pre-bake seamless dissolved mask for paper blueprint region
    maskX.clearRect(0, 0, 1200, 1700);
    maskX.fillStyle = "#FFFFFF"; maskX.strokeStyle = "#FFFFFF"; maskX.lineWidth = 3.5; maskX.lineJoin = "round";
    maskX.beginPath(); traceLocal(maskX, regionGeom, 600, 850); maskX.fill(); maskX.stroke();

    window.__renderBlueprint = function(t) {
      ctx.fillStyle = "#1E1B18";
      ctx.fillRect(0, 0, W, H);
      const pull = easeInOutCubic(seg(t, 0.2, 5.6));
      const scale = lerp(2.35, 1.18, pull);
      const rot = lerp(-0.16, 0.08, pull);
      const ox = lerp(W * 0.54, W * 0.50, pull);
      const oy = lerp(H * 0.52, H * 0.49, pull);
      const stampAt = SPEC.stamp_at_s ?? 5.65;

      let sx = 0, sy = 0;
      if (t >= stampAt && t <= stampAt + 0.36) {
        const d = 1 - seg(t, stampAt, stampAt + 0.36);
        sx = Math.sin(t * 98) * 15 * d;
        sy = Math.cos(t * 82) * 15 * d;
      }

      ctx.save();
      ctx.translate(ox + sx, oy + sy);
      ctx.rotate(rot);
      ctx.scale(scale, scale);

      const pw = 1160, ph = 1660;
      ctx.fillStyle = "#D9D2C3";
      ctx.shadowColor = "rgba(0,0,0,0.65)"; ctx.shadowBlur = 40;
      ctx.fillRect(-pw / 2, -ph / 2, pw, ph);
      ctx.shadowBlur = 0;

      ctx.fillStyle = "#8C939A";
      ctx.fillRect(-pw / 2 + 44, -ph / 2 + 195, pw - 88, ph - 265);

      ctx.save();
      ctx.beginPath(); ctx.rect(-pw / 2 + 44, -ph / 2 + 195, pw - 88, ph - 265); ctx.clip();
      ctx.fillStyle = "#CFC8B8"; ctx.strokeStyle = "#6B675E"; ctx.lineWidth = 2;
      for (const g of landGeoms) { ctx.beginPath(); traceLocal(ctx, g); ctx.fill(); ctx.stroke(); }

      ctx.strokeStyle = "rgba(92, 88, 80, 0.26)"; ctx.lineWidth = 1.2;
      for (let gx = -560; gx <= 560; gx += 85) { ctx.beginPath(); ctx.moveTo(gx, -650); ctx.lineTo(gx, 760); ctx.stroke(); }
      for (let gy = -620; gy <= 760; gy += 85) { ctx.beginPath(); ctx.moveTo(-560, gy); ctx.lineTo(560, gy); ctx.stroke(); }

      // Seamless glowing green dissolved boundary on paper
      ctx.save();
      ctx.shadowColor = "#22C55E"; ctx.shadowBlur = 24;
      ctx.globalAlpha = 0.52;
      ctx.drawImage(maskC, -600, -850);
      ctx.restore();
      ctx.save();
      ctx.globalAlpha = 0.34;
      ctx.beginPath(); traceLocal(ctx, regionGeom); ctx.fillStyle = "#22C55E"; ctx.fill();
      ctx.restore();

      drawPartial(northPts, 1, "#C89B2B", 7.5);
      drawPartial(southPts, 1, "#C89B2B", 7.5);
      drawPartial(failPts, easeInOutCubic(seg(t, 0.4, 5.2)), "#8B0000", 9);
      ctx.restore();

      ctx.fillStyle = "#48433B";
      ctx.font = "600 56px 'EB Garamond', Georgia, serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(SPEC.header || "PAN AMERICAN HIGHWAY", 0, -ph / 2 + 104);
      ctx.font = "400 18px 'EB Garamond', Georgia, serif";
      ctx.fillStyle = "#6B655B";
      ctx.fillText(SPEC.subheader || "ENGINEERING ROUTE SURVEY", 0, -ph / 2 + 150);

      // Subtle paper fold lines
      ctx.strokeStyle = "rgba(40, 35, 28, 0.2)"; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(-pw / 2, -60); ctx.lineTo(pw / 2, -60); ctx.moveTo(0, -ph / 2); ctx.lineTo(0, ph / 2); ctx.stroke();

      if (t >= stampAt - 0.03) {
        const stA = seg(t, stampAt - 0.03, stampAt + 0.07);
        ctx.save();
        ctx.translate(18, 22); ctx.rotate(-0.50); ctx.globalAlpha = stA * 0.94;
        ctx.strokeStyle = "#991B1B"; ctx.lineWidth = 8; ctx.strokeRect(-142, -52, 284, 104);
        ctx.lineWidth = 3; ctx.strokeRect(-130, -40, 260, 80);
        ctx.fillStyle = "#991B1B"; ctx.font = "900 56px 'Archivo Black', sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(SPEC.stamp_text || "FAILED", 0, 3);
        ctx.restore();
      }

      if (t >= stampAt - 0.40 && t <= stampAt + 0.35) {
        const down = easeInExpo(seg(t, stampAt - 0.40, stampAt));
        const up = easeOutCubic(seg(t, stampAt + 0.07, stampAt + 0.35));
        const lift = 1 - down + up;
        const sc = 1.0 + lift * 0.95;
        const al = seg(t, stampAt - 0.40, stampAt - 0.28) * (1 - seg(t, stampAt + 0.23, stampAt + 0.35));
        ctx.save();
        ctx.translate(18 + lift * 210, 22 + lift * 160); ctx.rotate(-0.50); ctx.scale(sc, sc); ctx.globalAlpha = al;
        ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 24 + lift * 35; ctx.shadowOffsetX = 12 + lift * 24; ctx.shadowOffsetY = 18 + lift * 30;
        ctx.fillStyle = "#8C6239"; ctx.beginPath(); ctx.roundRect(-155, -64, 310, 128, 10); ctx.fill();
        ctx.strokeStyle = "#5C3D1E"; ctx.lineWidth = 5; ctx.stroke();
        ctx.shadowBlur = 14; ctx.fillStyle = "#262320"; ctx.beginPath(); ctx.ellipse(24, 18, 62, 48, 0.2, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }
      ctx.restore();

      // Macro-lens subtle top/bottom atmospheric vignette on paper sheet
      const mg = ctx.createRadialGradient(W * 0.5, H * 0.48, 280, W * 0.5, H * 0.48, 1120);
      mg.addColorStop(0, "rgba(0,0,0,0)");
      mg.addColorStop(1, "rgba(18,14,10,0.34)");
      ctx.fillStyle = mg;
      ctx.fillRect(0, 0, W, H);

      if (SPEC.entry_flash_hex && t < 0.55) {
        const fA = 1 - easeOutCubic(seg(t, 0, 0.55));
        const h = SPEC.entry_flash_hex.replace("#", "");
        ctx.fillStyle = "rgba(" + parseInt(h.slice(0,2),16) + "," + parseInt(h.slice(2,4),16) + "," + parseInt(h.slice(4,6),16) + "," + (fA * 0.78).toFixed(3) + ")";
        ctx.fillRect(0, 0, W, H);
      }
    };
  </script>
</body>
</html>`;
}

function sampleCameraAt(samples, frameIndex, subOffset = 0) {
  if (!samples || samples.length === 0) return { center: [0, 0], zoom: 2, bearing: 0, pitch: 0, shutter_samples: 1 };
  const exact = frameIndex + subOffset;
  if (exact <= 0) return samples[0];
  if (exact >= samples.length - 1) return samples[samples.length - 1];
  const i0 = Math.floor(exact);
  const i1 = Math.min(samples.length - 1, i0 + 1);
  const u = exact - i0;
  const a = samples[i0], b = samples[i1];
  return {
    center: [
      a.center[0] + (b.center[0] - a.center[0]) * u,
      a.center[1] + (b.center[1] - a.center[1]) * u,
    ],
    zoom: a.zoom + (b.zoom - a.zoom) * u,
    bearing: (a.bearing || 0) + ((b.bearing || 0) - (a.bearing || 0)) * u,
    pitch: (a.pitch || 0) + ((b.pitch || 0) - (a.pitch || 0)) * u,
    roll: (a.roll || 0) + ((b.roll || 0) - (a.roll || 0)) * u,
    shutter_samples: a.shutter_samples || 1,
  };
}

async function bakeAct(browser, baseUrl, vectorsJson, width, height, fps, act, outDir, opts = {}) {
  const previewCount = Number(opts.previewKeyframes || 0);
  const isPreview = previewCount > 0;
  const outName = act.output_file || act.output_name || `${act.act_id}.mp4`;
  const outMp4 = resolve(outDir, outName);
  const resolvedOutDir = resolve(outDir);
  if (outMp4 !== resolvedOutDir && !outMp4.startsWith(resolvedOutDir + "/")) {
    throw new Error(`Output path escapes output directory (${resolvedOutDir}): ${outName}`);
  }
  const actKind = act.kind || act.mode || act.type || "map";
  const totalFrames = Math.max(1, Math.round(act.duration_s * fps));
  if (actKind !== "blueprint_paper") {
    const REJECTED_LAYERS = new Set([
      "coord_plaque",
      "scale_comparison",
      "survey_pin",
      "orbital_sightlines",
      "culmination_sun",
      "callout_badge",
    ]);
    for (const layer of act.layers || []) {
      if (REJECTED_LAYERS.has(layer.type)) {
        throw new Error(
          `Rejected legacy chrome layer type "${layer.type}" in act "${act.act_id}". ` +
          `Use calibrated boxless primitives instead (glow_label, pin_label, curved_pointer_label, dashed_distance, curved_arc_arrow, void_wipe, counter_odometer, ghost_overlay, prohibition_pins).`
        );
      }
    }
  }
  console.log(`\n=== ${isPreview ? "Previewing" : "Baking"} ${act.act_id} (${actKind}): ${act.duration_s.toFixed(3)}s (${totalFrames} frames) -> ${isPreview ? "keyframes" : outMp4} ===`);

  const page = await browser.newPage();
  page.on("pageerror", (err) => console.error(`  [${act.act_id} pageerror]`, err));
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  const captureFormat = act.capture_format || opts.captureFormat || "jpeg";
  const captureQuality = act.capture_quality ?? opts.captureQuality ?? 95;
  const shotter = await createCdpScreenshotter(page, width, height, {
    format: captureFormat,
    quality: captureQuality,
  });
  const encoder = isPreview
    ? null
    : spawnFramePipeEncoder(outMp4, {
        codec: captureFormat === "png" ? "png" : "mjpeg",
        fps,
        crf: 15,
        gop: 1,
        preset: "fast",
        useVideoToolbox: false,
      });
  const t0 = Date.now();
  const trackLog = [];
  const previewFrames = [];
  let succeeded = false;

  const sampleIndices = (() => {
    if (!isPreview) return null;
    const count = Math.max(1, Math.min(totalFrames, previewCount));
    if (count === 1) return [0];
    const s = new Set([0, totalFrames - 1]);
    for (let i = 1; i < count - 1; i++) {
      s.add(Math.min(totalFrames - 1, Math.round((i / (count - 1)) * (totalFrames - 1))));
    }
    return [...s].sort((a, b) => a - b);
  })();

  try {
    if (actKind === "blueprint_paper") {
      await page.setContent(buildBlueprintHtml(baseUrl, width, height, vectorsJson, act), { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      const framesToRun = sampleIndices || Array.from({ length: totalFrames }, (_, i) => i);
      for (const f of framesToRun) {
        await page.evaluate((sec) => window.__renderBlueprint(sec), f / fps);
        const buf = await shotter.captureJpegBuffer();
        if (isPreview) previewFrames.push({ act_id: act.act_id, frame: f, t_s: f / fps, buf });
        else await encoder.writeFrame(buf);
        if (!isPreview && (f % 60 === 0 || f === totalFrames - 1)) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
    } else {
      const has3d = (act.layers || []).some(
        (l) => l && (l.type === "cable_3d" || l.type === "model_3d" || l.type === "volume_3d" || l.type === "country_block_3d")
      );
      const initialCam = sampleCameraAt(act.camera_samples || [], 0, 0);
      const maxPitch = Math.max(
        Number(initialCam.pitch || 0),
        ...(act.camera_samples || []).map((s) => Number(s?.pitch || 0))
      );
      await page.setContent(
        buildMapSceneHtml(baseUrl, width, height, vectorsJson, {
          tile_source: act.tile_source || "hybrid",
          projection: act.projection || "mercator",
          terrain_3d: Boolean(act.terrain_3d),
          terrain_exaggeration: act.terrain_exaggeration ?? 2.4,
          dem_maxzoom: act.dem_maxzoom ?? 10,
          allow_world_void: Boolean(act.allow_world_void),
          has_3d: has3d,
          origin_coord: act.origin_coord || initialCam.center,
          initial_camera: initialCam,
          max_pitch: maxPitch,
          ov_scale: act.ov_scale ?? opts.ovScale ?? 1.5,
          sun_azimuth_deg: act.sun_azimuth_deg ?? opts.sunAzimuthDeg ?? 335,
          sun_elevation_deg: act.sun_elevation_deg ?? opts.sunElevationDeg ?? 42,
          atmosphere: act.atmosphere ?? null,
          hdr_bloom: act.hdr_bloom ?? opts.hdrBloom ?? true,
        }),
        { waitUntil: "load" }
      );
      await page.evaluate(() => window.__ready);
      const samples = act.camera_samples || [];
      const layers = act.layers || [];
      // Deterministically preload Canvas 2D font faces before frame 0 so measureText/fillText never hit FOUT.
      const fontSpecs = new Set([
        "700 48px 'Barlow Condensed'",
        "800 64px 'Barlow Condensed'",
        "600 40px 'Inter'",
        "700 48px 'Inter'",
        "700 56px 'Rubik'",
        "800 56px 'Rubik'",
        "italic 600 42px 'Lora'",
        "700 42px 'Lora'",
        "700 42px 'IBM Plex Mono'",
        "400 64px 'Archivo Black'",
      ]);
      for (const layer of layers) {
        if (layer.family) {
          const st = layer.font_style === "italic" ? "italic " : "";
          const wt = layer.weight || 700;
          fontSpecs.add(`${st}${wt} 48px '${layer.family}'`);
        }
      }
      await page.evaluate(async (specs) => {
        await Promise.allSettled(specs.map((s) => document.fonts.load(s)));
        await document.fonts.ready;
      }, [...fontSpecs]);
      const preloadUrls = [];
      const preloadModelUrls = [];
      for (const layer of layers) {
        if (layer.type === "flag_pin" && layer.code) {
          preloadUrls.push(`${baseUrl}/flags/${String(layer.code).toLowerCase()}.svg`);
        }
        if ((layer.type === "polygon" || layer.type === "country_block_3d") && layer.flag_fill) {
          preloadUrls.push(`${baseUrl}/flags/${String(layer.flag_fill).toLowerCase()}.svg`);
        }
        if (layer.type === "model_3d" && layer.gltf_url) {
          const u = String(layer.gltf_url);
          preloadModelUrls.push(u.startsWith("http") ? u : `${baseUrl}/${u.replace(/^\/+/, "")}`);
        }
      }
      if (preloadUrls.length > 0) {
        await page.evaluate((urls) => window.__preloadAssets(urls), preloadUrls);
        const missing = await page.evaluate((urls) => urls.filter((u) => !window.__imgCache[u]), [...new Set(preloadUrls)]);
        for (const u of missing) {
          console.warn(`  [${act.act_id}] warning: flag asset not found (${u.split("/").pop()}); layer falls back to its colour fill`);
        }
      }
      if (preloadModelUrls.length > 0) {
        await page.evaluate((urls) => window.__preloadModels(urls), preloadModelUrls);
        const missingM = await page.evaluate((urls) => urls.filter((u) => !window.__gltfCache[u]), [...new Set(preloadModelUrls)]);
        for (const u of missingM) {
          console.warn(`  [${act.act_id}] warning: glTF asset failed to load (${u}); falling back to procedural geometry`);
        }
      }
      // Sub-frame shutter accumulation is opt-in so frames stay crisp by default.
      const enableShutter = act.optical_shutter_blur === true;
      // Radial zoom blur that peaks on the act's first and/or last frame (cut accents).
      const cutBlurIn = Number(act.cut_blur_in_s) || 0;
      const cutBlurOut = Number(act.cut_blur_out_s) || 0;
      const cutBlurStrength = act.cut_blur_strength ?? 0.12;
      const IDLE_WAIT_MS = 6000;
      let pendingFrames = 0;

      // Pre-warm tiles across act timeline (skip for fast keyframe preview)
      if (!isPreview) {
        for (let f = 0; f < totalFrames; f += Math.max(15, Math.floor(totalFrames / 8))) {
          const cam = sampleCameraAt(samples, f, 0);
          await page.evaluate((c) => window.__setSceneCamera(c), cam);
          await page.evaluate((ms) => window.__waitIdle(ms), 1500);
        }
      }

      const framesToRun = sampleIndices || Array.from({ length: totalFrames }, (_, i) => i);
      for (const f of framesToRun) {
        const cam = sampleCameraAt(samples, f, 0);
        const subN = !isPreview && enableShutter ? Math.min(16, Math.max(1, cam.shutter_samples || 1)) : 1;
        const blurAmt = cutBlurAmount(f, totalFrames, fps, cutBlurIn, cutBlurOut, cutBlurStrength);
        const applyCutBlur = async () => {
          if (blurAmt > 0.002) await page.evaluate((a) => window.__cutBlurComposite(a, 12), blurAmt);
        };
        if (subN > 1 && f > 0) {
          let pending = false;
          const schedule = shutterSubframeSchedule(subN, act.shutter_angle_deg ?? 180, act.shutter_profile || "cosine");
          let cumWeight = 0;
          await page.evaluate(() => window.__beginShutterAccum());
          for (const entry of schedule) {
            const subOff = entry.offset;
            cumWeight += entry.weight;
            const subCam = sampleCameraAt(samples, f, subOff);
            const subT = Math.max(0, (f + subOff) / fps);
            await page.evaluate((c) => window.__setSceneCamera(c), subCam);
            pending = (await page.evaluate((ms) => window.__waitIdle(ms), IDLE_WAIT_MS)) || pending;
            await page.evaluate(([ls, sec]) => window.__drawSceneLayers(ls, sec), [layers, subT]);
            await page.evaluate(([w, cw]) => window.__accumSubframe(w, cw), [entry.weight, cumWeight]);
          }
          if (pending) pendingFrames++;
          await applyCutBlur();
          await encoder.writeFrame(await shotter.captureBuffer());
          await page.evaluate(() => window.__endShutterAccum());
        } else {
          await page.evaluate((c) => window.__setSceneCamera(c), cam);
          if (await page.evaluate((ms) => window.__waitIdle(ms), IDLE_WAIT_MS)) pendingFrames++;
          await page.evaluate(([ls, sec]) => window.__drawSceneLayers(ls, sec), [layers, f / fps]);
          await applyCutBlur();
          const buf = await shotter.captureBuffer();
          if (isPreview) previewFrames.push({ act_id: act.act_id, frame: f, t_s: f / fps, buf });
          else await encoder.writeFrame(buf);
          if (blurAmt > 0.002) await page.evaluate(() => window.__endShutterAccum());
        }
        if (!isPreview && act.export_camera_track) {
          trackLog.push({ frame: f, t: Number((f / fps).toFixed(4)), ...cam });
        }
        if (!isPreview && (f % 60 === 0 || f === totalFrames - 1)) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
      console.log(`  [${act.act_id}] frames captured with tiles still pending: ${pendingFrames}`);
      if (!isPreview && act.export_camera_track) {
        writeFileSync(join(outDir, `${act.act_id}_camera_track.json`), JSON.stringify(trackLog));
      }
    }
    succeeded = true;
  } finally {
    await shotter.close();
    await page.close();
    if (!succeeded && encoder) {
      await encoder.abort();
    }
  }
  if (encoder) await encoder.finish();
  return previewFrames;
}

/**
 * Coverage pass for one map act: step the camera over every 2nd frame (plus the last), waiting
 * for tiles, without drawing overlays or capturing frames. The tile server records every raster
 * tile it had to synthesise from an upscaled ancestor.
 */
async function coverageAct(browser, baseUrl, vectorsJson, width, height, fps, act) {
  const actKind = act.kind || act.mode || act.type || "map";
  if (actKind === "blueprint_paper") return;
  const samples = act.camera_samples || [];
  const totalFrames = Math.max(
    1,
    act.duration_s != null ? Math.round(act.duration_s * fps) : samples.length || Math.round(fps)
  );
  const initialCam = sampleCameraAt(samples, 0, 0);
  const page = await browser.newPage();
  try {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.setContent(
      buildMapSceneHtml(baseUrl, width, height, vectorsJson, {
        tile_source: act.tile_source || "hybrid",
        projection: act.projection || "mercator",
        terrain_3d: Boolean(act.terrain_3d),
        terrain_exaggeration: act.terrain_exaggeration ?? 2.4,
        dem_maxzoom: act.dem_maxzoom ?? 10,
        allow_world_void: Boolean(act.allow_world_void),
        initial_camera: initialCam,
      }),
      { waitUntil: "load" }
    );
    await page.evaluate(() => window.__ready);
    const frames = [];
    for (let f = 0; f < totalFrames; f += 2) frames.push(f);
    if (frames[frames.length - 1] !== totalFrames - 1) frames.push(totalFrames - 1);
    for (const f of frames) {
      await page.evaluate((c) => window.__setSceneCamera(c), sampleCameraAt(samples, f, 0));
      await page.evaluate((ms) => window.__waitIdle(ms), 6000);
    }
  } finally {
    await page.close();
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (typeof args["scene-file"] !== "string" || typeof args["out-dir"] !== "string") {
    console.error("Usage: render_map_scene.mjs --scene-file <spec.json> --out-dir <dir> [--base-dir <dir>]");
    process.exit(1);
  }
  if (args["coverage-out"] === true) {
    throw new Error("--coverage-out requires a file path argument");
  }
  const coverageOnly = Boolean(args["coverage-only"]);
  const coverageOut = typeof args["coverage-out"] === "string" ? resolve(args["coverage-out"]) : null;
  if (coverageOnly && !coverageOut) {
    throw new Error("--coverage-only requires --coverage-out <file>");
  }
  if (coverageOut) {
    mkdirSync(dirname(coverageOut), { recursive: true });
  }
  const sceneFile = resolve(args["scene-file"]);
  const baseDir = resolve(typeof args["base-dir"] === "string" ? args["base-dir"] : dirname(sceneFile));
  const outDir = resolve(args["out-dir"]);
  mkdirSync(outDir, { recursive: true });

  const spec = JSON.parse(readFileSync(sceneFile, "utf8"));
  const width = Number(spec.width || 1080);
  const height = Number(spec.height || 1920);
  const fps = Number(spec.fps || 30);

  let vectorsObj = {};
  const vecSpec = spec.vectors_file || spec.vectors_path;
  if (vecSpec) {
    const vPath = isAbsolute(vecSpec) ? vecSpec : resolve(baseDir, vecSpec);
    if (!existsSync(vPath)) {
      throw new Error(`Map scene vectors file not found: ${vPath}`);
    }
    vectorsObj = JSON.parse(readFileSync(vPath, "utf8"));
  }
  if (spec.inline_vectors && typeof spec.inline_vectors === "object") {
    vectorsObj = { ...vectorsObj, ...spec.inline_vectors };
  }
  // Fail loud if any layer geom_ref or geom_refs entry is missing from the loaded vectors bundle.
  const checkGeomRef = (actId, ref) => {
    if (typeof ref !== "string") return;
    let cur = vectorsObj;
    for (const p of ref.split(".")) cur = cur && typeof cur === "object" ? cur[p] : undefined;
    if (!cur) {
      throw new Error(`Act '${actId}' references missing geom_ref '${ref}' (loaded keys: ${Object.keys(vectorsObj).join(", ")})`);
    }
  };
  for (const act of spec.acts || []) {
    for (const layer of act.layers || []) {
      if (typeof layer.geom_ref === "string") checkGeomRef(act.act_id, layer.geom_ref);
      if (Array.isArray(layer.geom_refs)) {
        for (const r of layer.geom_refs) checkGeomRef(act.act_id, r);
      }
    }
  }
  const vectorsJson = JSON.stringify(vectorsObj);

  const projectTilesSpec = spec.project_tiles_dir;
  const projectTilesDir = projectTilesSpec
    ? (isAbsolute(projectTilesSpec) ? projectTilesSpec : resolve(baseDir, projectTilesSpec))
    : null;
  const projectModelsSpec = spec.project_models_dir;
  const projectModelsDir = projectModelsSpec
    ? (isAbsolute(projectModelsSpec) ? projectModelsSpec : resolve(baseDir, projectModelsSpec))
    : (existsSync(resolve(baseDir, "models")) ? resolve(baseDir, "models") : null);

  let selectedActs = spec.acts || [];
  const onlyActs = args["only-act"];
  if (Array.isArray(onlyActs) && onlyActs.length > 0) {
    const known = new Set(selectedActs.map((a) => a.act_id));
    for (const id of onlyActs) {
      if (!known.has(id)) {
        throw new Error(`Unknown act_id '${id}' passed to --only-act (available: ${[...known].join(", ")})`);
      }
    }
    const want = new Set(onlyActs);
    selectedActs = selectedActs.filter((a) => want.has(a.act_id));
  }

  const rawPreview = args["preview-keyframes"];
  const previewTotal = rawPreview === true ? 12 : (typeof rawPreview === "string" ? Math.max(1, Number(rawPreview) || 12) : 0);

  const server = await startTileServer(0, "127.0.0.1", {
    recordGaps: Boolean(coverageOut),
    projectTilesDir,
    projectModelsDir,
  });
  const url = `http://127.0.0.1:${server.address().port}`;
  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: "new",
    args: getChromeArgs(width, height),
  });
  const allPreviewFrames = [];
  try {
    for (const act of selectedActs) {
      if (coverageOnly) {
        await coverageAct(browser, url, vectorsJson, width, height, fps, act);
      } else {
        const perActPreview = previewTotal > 0 ? Math.max(2, Math.ceil(previewTotal / Math.max(1, selectedActs.length))) : 0;
        const pFrames = await bakeAct(browser, url, vectorsJson, width, height, fps, act, outDir, {
          previewKeyframes: perActPreview,
          ovScale: spec.ov_scale,
          captureFormat: spec.capture_format,
          captureQuality: spec.capture_quality,
          sunAzimuthDeg: spec.sun_azimuth_deg,
          sunElevationDeg: spec.sun_elevation_deg,
          hdrBloom: spec.hdr_bloom,
        });
        if (perActPreview > 0 && Array.isArray(pFrames)) allPreviewFrames.push(...pFrames);
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  if (previewTotal > 0 && allPreviewFrames.length > 0) {
    const previewDir = join(outDir, "preview_keyframes");
    mkdirSync(previewDir, { recursive: true });
    for (const pf of allPreviewFrames) {
      const pName = `${pf.act_id}_${pf.t_s.toFixed(2).replace(".", "_")}s.jpg`;
      writeFileSync(join(previewDir, pName), pf.buf);
    }
    const cols = Math.min(4, allPreviewFrames.length);
    const rows = Math.ceil(allPreviewFrames.length / cols);
    const thumbW = 360;
    const thumbH = Math.max(120, Math.round((height / width) * thumbW));
    const composites = await Promise.all(
      allPreviewFrames.map(async (pf, idx) => ({
        input: await sharp(pf.buf).resize(thumbW, thumbH).toBuffer(),
        left: (idx % cols) * thumbW,
        top: Math.floor(idx / cols) * thumbH,
      }))
    );
    const sheetPath = join(outDir, "preview_contact_sheet.jpg");
    await sharp({
      create: { width: cols * thumbW, height: rows * thumbH, channels: 3, background: { r: 6, g: 16, b: 24 } },
    })
      .composite(composites)
      .jpeg({ quality: 88 })
      .toFile(sheetPath);
    console.log(JSON.stringify({ ok: true, preview_frames: allPreviewFrames.length, contact_sheet: sheetPath }));
    return;
  }
  if (coverageOut) {
    const report = coverageReport(server.tileGaps);
    const tmpCov = `${coverageOut}.tmp`;
    try {
      writeFileSync(tmpCov, JSON.stringify(report));
      renameSync(tmpCov, coverageOut);
    } catch (err) {
      try {
        if (existsSync(tmpCov)) unlinkSync(tmpCov);
      } catch {
        // Ignore cleanup errors.
      }
      throw err;
    }
    console.log(`Coverage pass complete: ${report.tiles.length} tiles served from an upscaled ancestor -> ${coverageOut}`);
    if (coverageOnly) return;
  }
  console.log("Declarative map scene bake complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
