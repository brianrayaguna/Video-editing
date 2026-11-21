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
  writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import {
  createCdpScreenshotter,
  getChromeArgs,
  spawnMjpegPipeEncoder,
} from "./fast_capture.mjs";
import { startTileServer } from "./serve_tiles.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const puppeteer = require("puppeteer-core");

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
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k.startsWith("--") && i + 1 < argv.length) {
      args[k.slice(2)] = argv[++i];
    }
  }
  return args;
}

function buildMapSceneHtml(baseUrl, width, height, vectorsJson, mapOpts = {}) {
  const tileRoute = mapOpts.tile_source === "realistic" ? "/tiles_hq/{z}/{x}/{y}.jpg" : "/tiles/{z}/{x}/{y}.jpg";
  const satMaxZoom = mapOpts.tile_source === "realistic" ? 15 : 9;
  const terrain3d = Boolean(mapOpts.terrain_3d);
  const terrainExag = Number(mapOpts.terrain_exaggeration ?? 2.4);
  const demMaxZoom = Number(mapOpts.dem_maxzoom ?? 10);
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${baseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${baseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    @font-face {
      font-family: "Space Grotesk";
      src: url("${baseUrl}/fonts/SpaceGrotesk-Variable.ttf") format("truetype");
      font-weight: 100 900;
    }
    @font-face {
      font-family: "Archivo Black";
      src: url("${baseUrl}/fonts/ArchivoBlack-Regular.ttf") format("truetype");
      font-weight: 400 900;
    }
    @font-face {
      font-family: "EB Garamond";
      src: url("${baseUrl}/fonts/EBGaramond-Variable.ttf") format("truetype");
      font-weight: 400 800;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #083847; }
    #map, #ov, #comp { position: absolute; inset: 0; width: ${width}px; height: ${height}px; }
    #ov, #comp { pointer-events: none; }
    #comp { display: none; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <div id="map"></div>
  <canvas id="ov" width="${width}" height="${height}"></canvas>
  <canvas id="comp" width="${width}" height="${height}"></canvas>
  <script>
    const BASE_URL = ${JSON.stringify(baseUrl)};
    const VEC = ${vectorsJson};
    const W = ${width}, H = ${height};

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
          { id: "sat", type: "raster", source: "sat", paint: { "raster-contrast": ${mapOpts.tile_source === "realistic" ? 0.08 : 0}, "raster-saturation": ${mapOpts.tile_source === "realistic" ? 0.06 : 0} } }${terrain3d ? `,
          { id: "hillshade", type: "hillshade", source: "dem", paint: { "hillshade-exaggeration": 0.28, "hillshade-shadow-color": "#041620", "hillshade-highlight-color": "#FFF5D6" } }` : ""}
        ]${terrain3d ? `,
        terrain: { source: "dem", exaggeration: ${terrainExag} },
        sky: {
          "sky-color": "#071E2E",
          "sky-horizon-blend": 0.55,
          "horizon-color": "#1E5B70",
          "horizon-fog-blend": 0.45,
          "fog-color": "#0C2C3B",
          "fog-ground-blend": 0.35
        }` : ""}
      },
      center: [0, 0],
      zoom: 2,
      minZoom: 0.5,
      maxZoom: 18,
      maxPitch: 75,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true,
      maxTileCacheSize: 8000,
      transformConstrain: (lngLat, zoom) => ({ center: lngLat, zoom }),
      canvasContextAttributes: { alpha: false, preserveDrawingBuffer: true }
    });

    const ovCanvas = document.getElementById("ov");
    const ctx = ovCanvas.getContext("2d");
    const compCanvas = document.getElementById("comp");
    const compCtx = compCanvas.getContext("2d");

    // Offscreen canvases for seamless dissolved polygon exterior glow & rim (zero internal borders)
    const maskCanvas = document.createElement("canvas");
    maskCanvas.width = W; maskCanvas.height = H;
    const maskCtx = maskCanvas.getContext("2d");

    const rimCanvas = document.createElement("canvas");
    rimCanvas.width = W; rimCanvas.height = H;
    const rimCtx = rimCanvas.getContext("2d");

    window.__ready = new Promise((res) => map.on("load", () => res()));
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

    function traceRing(targetCtx, ring) {
      for (let i = 0; i < ring.length; i++) {
        const p = map.project(ring[i]);
        if (i === 0) targetCtx.moveTo(p.x, p.y);
        else targetCtx.lineTo(p.x, p.y);
      }
      targetCtx.closePath();
    }

    function traceGeom(targetCtx, geom) {
      if (!geom) return;
      if (Array.isArray(geom)) {
        for (const item of geom) traceGeom(targetCtx, item.geometry || item);
        return;
      }
      if (geom.type === "Polygon") {
        for (const r of geom.coordinates) traceRing(targetCtx, r);
      } else if (geom.type === "MultiPolygon") {
        for (const poly of geom.coordinates) {
          for (const r of poly) traceRing(targetCtx, r);
        }
      }
    }

    function parseHexRgb(hex) {
      const h = (hex || "#FFFFFF").replace("#", "");
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

    // Seamless exterior polygon dissolve + exterior-only feathered bloom + animated perimeter reveal
    function drawDissolvedPolygon(geom, { fillHex, fillAlpha = 0.56, rimHex = "#F4F1EA", rimWidth = 3.0, bloomHex = "#22C55E", bloomScale = 1.0, alpha = 1.0, preserveTerrain = true, borderReveal = 1.0, fillReveal = 1.0 } = {}) {
      if (alpha <= 0.005 || !geom) return;

      // 1. Build unified solid silhouette mask (bridges tiny sub-pixel gaps between adjacent provinces)
      maskCtx.clearRect(0, 0, W, H);
      maskCtx.fillStyle = "#FFFFFF";
      maskCtx.strokeStyle = "#FFFFFF";
      maskCtx.lineWidth = 3.5;
      maskCtx.lineJoin = "round";
      maskCtx.beginPath();
      traceGeom(maskCtx, geom);
      maskCtx.fill();
      maskCtx.stroke();

      // 2. Build exterior-only rim ring into rimCanvas (8-12 direction dilation minus inner mask)
      rimCtx.clearRect(0, 0, W, H);
      rimCtx.globalCompositeOperation = "source-over";
      const dirs = 12;
      const rw = Math.max(2.0, rimWidth);
      for (let k = 0; k < dirs; k++) {
        const ang = (k / dirs) * Math.PI * 2;
        rimCtx.drawImage(maskCanvas, Math.cos(ang) * rw, Math.sin(ang) * rw);
      }
      rimCtx.globalCompositeOperation = "destination-out";
      rimCtx.drawImage(maskCanvas, 0, 0);

      // 3. Exterior-only Gaussian bloom (never stacks opaque color over interior mountain texture)
      ctx.save();
      if (borderReveal < 0.999) {
        ctx.beginPath();
        ctx.rect(0, 0, W, H * clamp(borderReveal, 0, 1));
        ctx.clip();
      }
      if (bloomHex && bloomScale > 0) {
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = bloomHex;
        rimCtx.fillRect(0, 0, W, H);
        const passes = [
          [42 * bloomScale, 0.45],
          [20 * bloomScale, 0.65],
          [8 * bloomScale, 0.80],
        ];
        for (const [blurPx, a] of passes) {
          ctx.save();
          ctx.globalAlpha = alpha * a;
          ctx.shadowColor = bloomHex;
          ctx.shadowBlur = blurPx;
          ctx.drawImage(rimCanvas, 0, 0);
          ctx.restore();
        }
      }

      // 4. Crisp exterior rim (animated by borderReveal)
      if (rimHex && rimWidth > 0) {
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = rimHex;
        rimCtx.fillRect(0, 0, W, H);
        ctx.globalCompositeOperation = "source-over";
        ctx.globalAlpha = alpha * 0.92;
        ctx.drawImage(rimCanvas, 0, 0);
      }
      ctx.restore();

      // 5. Terrain-preserving interior fill (single clean translucent pass so mountain ridges shine through)
      if (fillReveal > 0.005) {
        rimCtx.clearRect(0, 0, W, H);
        rimCtx.globalCompositeOperation = "source-over";
        rimCtx.drawImage(maskCanvas, 0, 0);
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = fillHex;
        rimCtx.fillRect(0, 0, W, H);

        ctx.save();
        ctx.globalCompositeOperation = preserveTerrain ? "source-over" : "source-over";
        ctx.globalAlpha = alpha * fillAlpha * clamp(fillReveal, 0, 1);
        ctx.drawImage(rimCanvas, 0, 0);
        ctx.restore();
      }
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

    function drawPartialRoute(coords, progress, { color = "#FDE047", bloom = "#F5C542", core = "#FFFFFF", width = 8, dash = null, alpha = 1 } = {}) {
      if (progress <= 0.001 || alpha <= 0.005 || !coords || coords.length < 2) return;
      const pts = coords.map((c) => map.project(c));
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
      if (bloom) {
        trace(); ctx.strokeStyle = bloom; ctx.globalAlpha = alpha * 0.28; ctx.lineWidth = width * 2.8; ctx.stroke();
        trace(); ctx.strokeStyle = bloom; ctx.globalAlpha = alpha * 0.56; ctx.lineWidth = width * 1.65; ctx.stroke();
      }
      trace(); ctx.strokeStyle = color; ctx.globalAlpha = alpha; ctx.lineWidth = width; ctx.stroke();
      if (core && !dash) {
        trace(); ctx.strokeStyle = core; ctx.globalAlpha = alpha * 0.88; ctx.lineWidth = Math.max(1.8, width * 0.36); ctx.stroke();
      }
      ctx.restore();
    }

    // Multi-ring luminous text glow (3 outer halo rings + crisp readability drop shadow)
    function drawGlowingText(text, x, y, fontPx, { fill = "#FFFFFF", glowHex = "#22C55E", glowStrength = "luminous", angle = 0, alpha = 1, family = "Space Grotesk", weight = 800 } = {}) {
      if (alpha <= 0.005) return;
      ctx.save();
      ctx.translate(x, y);
      if (angle) ctx.rotate(angle);
      ctx.font = weight + " " + Math.round(fontPx) + "px '" + family + "', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      if (glowHex && glowStrength !== "none") {
        const rings = glowStrength === "intense"
          ? [[fontPx * 0.85, 0.55], [fontPx * 0.45, 0.82], [fontPx * 0.18, 0.96]]
          : glowStrength === "subtle"
            ? [[fontPx * 0.35, 0.52], [fontPx * 0.14, 0.72]]
            : [[fontPx * 0.62, 0.48], [fontPx * 0.28, 0.78], [fontPx * 0.12, 0.94]];
        for (const [blurR, a] of rings) {
          ctx.save();
          ctx.globalAlpha = alpha * a;
          ctx.shadowColor = glowHex;
          ctx.shadowBlur = blurR;
          ctx.fillStyle = fill;
          ctx.fillText(text, 0, 0);
          ctx.restore();
        }
      }
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(0,0,0,0.85)";
      ctx.shadowBlur = Math.max(4, fontPx * 0.14);
      ctx.shadowOffsetY = 3;
      ctx.fillStyle = fill;
      ctx.fillText(text, 0, 0);
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
      ctx.font = "800 " + Math.round(fSize) + "px 'Space Grotesk', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillText(labelText, 0, -Math.max(16, len * 0.045));
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
      ctx.clearRect(0, 0, W, H);
      for (const layer of layers || []) {
        const tStart = layer.start_s ?? 0;
        const tEnd = layer.end_s ?? 1e9;
        if (t < tStart - 0.001 || t > tEnd + 0.001) continue;
        const tLoc = t - tStart;
        const fadeIn = layer.fade_in_s ? easeOutCubic(seg(t, tStart, tStart + layer.fade_in_s)) : 1;
        const fadeOut = layer.fade_out_s ? 1 - seg(t, tEnd - layer.fade_out_s, tEnd) : 1;
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
          const fillReveal = layer.fill_draw_s
            ? easeOutCubic(seg(t, tStart, tStart + layer.fill_draw_s))
            : 1.0;
          if (layer.dissolve) {
            drawDissolvedPolygon(geom, { fillHex, fillAlpha, rimHex, rimWidth, bloomHex, bloomScale, alpha: baseAlpha, borderReveal, fillReveal });
          } else {
            drawStandardPolygon(geom, { fillHex, fillAlpha, rimHex, rimWidth, bloomHex, bloomScale, alpha: baseAlpha });
          }
        } else if (layer.type === "route") {
          let coords = resolveGeom(layer.coords_ref) || layer.coords || [];
          if (layer.reverse) coords = [...coords].reverse();
          const prog = layer.draw_duration_s
            ? easeOutCubic(seg(t, tStart, tStart + layer.draw_duration_s))
            : 1;
          drawPartialRoute(coords, prog, {
            color: layer.color || "#FDE047",
            bloom: layer.bloom || "#F5C542",
            core: layer.core ?? "#FFFFFF",
            width: layer.width || 8,
            dash: layer.dash || null,
            alpha: baseAlpha,
          });
          if (layer.beacon_coord) {
            const bA = baseAlpha * easeOutCubic(seg(t, layer.beacon_start_s ?? tStart, (layer.beacon_start_s ?? tStart) + 0.7));
            if (bA > 0.01) {
              const bp = map.project(layer.beacon_coord);
              const bg = ctx.createRadialGradient(bp.x, bp.y, 10, bp.x, bp.y, 130);
              bg.addColorStop(0, "rgba(255,255,255," + (0.95 * bA).toFixed(2) + ")");
              bg.addColorStop(0.35, rgbaStr(layer.beacon_color || "#4ADE80", 0.78 * bA));
              bg.addColorStop(1, "rgba(34,197,94,0)");
              ctx.fillStyle = bg;
              ctx.beginPath(); ctx.arc(bp.x, bp.y, 130, 0, Math.PI * 2); ctx.fill();
            }
          }
        } else if (layer.type === "glow_label") {
          const pt = map.project(layer.coord);
          let sc = layer.pop_scale ? lerp(0.92, 1.0, easeOutExpo(seg(t, tStart, tStart + 0.35))) : 1.0;
          let yFly = 0;
          if (layer.fly_through) {
            const enterP = easeOutExpo(seg(t, tStart, tStart + 0.52));
            const exitP = easeInExpo(seg(t, tEnd - 0.42, tEnd));
            sc = lerp(5.2, 1.0, enterP) * lerp(1.0, 4.8, exitP);
            yFly = lerp(320, 0, enterP) - lerp(0, 220, exitP);
          }
          const angDeg = layer.angle_end != null
            ? lerp(layer.angle_start || 0, layer.angle_end, seg(t, tStart, tEnd))
            : (layer.angle || 0);
          const angRad = angDeg * Math.PI / 180;
          drawGlowingText(layer.text, pt.x + (layer.dx || 0), pt.y + (layer.dy || 0) + yFly, (layer.font_px || 64) * sc, {
            fill: layer.fill || "#FFFFFF",
            glowHex: layer.glow_hex || "#22C55E",
            glowStrength: layer.glow_strength || "luminous",
            angle: angRad,
            alpha: baseAlpha,
          });
        } else if (layer.type === "crimson_x") {
          const pt = map.project(layer.coord);
          const pop = easeOutBack(seg(t, tStart, tStart + 0.32));
          const sz = lerp(layer.size_start || 56, layer.size_end || 90, seg(t, tStart, tEnd)) * clamp(pop, 0, 1.25);
          drawCrimsonX(pt.x, pt.y, sz, baseAlpha);
        } else if (layer.type === "skull") {
          const pt = map.project(layer.coord);
          const pop = easeOutBack(seg(t, tStart, tStart + 0.32));
          const refZoom = layer.ref_zoom ?? 7.3;
          const zoomScale = Math.pow(2, map.getZoom() - refZoom);
          const sz = (layer.size_start || 155) * zoomScale * clamp(pop, 0, 1.15);
          const rotRad = -map.getBearing() * Math.PI / 180;
          const pitchScale = Math.cos((map.getPitch() || 0) * Math.PI / 180);
          drawSkull(pt.x, pt.y + (layer.dy || 0), sz, baseAlpha, { rotRad, pitchScale });
        } else if (layer.type === "endpoint_dots") {
          const pulse = 1 + 0.16 * Math.sin(t * 14);
          const dr = lerp(layer.r_start || 12, layer.r_end || 28, seg(t, tStart, tEnd)) * pulse;
          for (const c of layer.coords || []) {
            const pt = map.project(c);
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
          const p1 = map.project(layer.from);
          const p2 = map.project(layer.to);
          const arrP = easeOutExpo(seg(t, tStart, tStart + (layer.draw_s || 0.75)));
          const val = Math.round(lerp(layer.count_from ?? 0, layer.count_to ?? 160, easeOutCubic(seg(t, tStart, tStart + (layer.count_s || 1.1)))));
          drawDoubleArrow(p1, p2, val + " " + (layer.unit || "km"), arrP, baseAlpha);
        } else if (layer.type === "weather_clouds_rain") {
          const pt = map.project(layer.coord);
          const sc = lerp(layer.scale_start || 0.85, layer.scale_end || 1.22, easeOutCubic(seg(t, tStart, tStart + 0.8)));
          drawWeatherCloudsRain(pt.x, pt.y + (layer.dy || -30), sc, baseAlpha, tLoc);
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
            const pt = map.project([
              lerp(lerp(sLng0, sLng1, sd1), lerp(eLng0, eLng1, sd1), prog),
              lerp(lerp(sLat0, sLat1, sd2), lerp(eLat0, eLat1, sd2), prog),
            ]);
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
            const pt = map.project(item.coord);
            drawTeardropPin(pt.x, pt.y, (layer.radius || 76) * clamp(pop, 0, 1.15), item.kind, baseAlpha);
          }
        } else if (layer.type === "prohibition_badge") {
          const pt = map.project(layer.coord);
          const inP = easeOutExpo(seg(t, tStart, tStart + 0.65));
          const outP = easeInCubic(seg(t, tEnd - 0.95, tEnd));
          const rad = lerp(layer.r_enter || 340, layer.r_hold || 150, inP) * lerp(1.0, 2.8, outP);
          const cy = lerp(220, pt.y - 20, inP) - outP * 380;
          drawNoPoliceBadge(pt.x, cy, rad, baseAlpha);
        } else if (layer.type === "radar_rings") {
          for (const hub of layer.hubs || []) {
            if (t < hub.start_s) continue;
            const age = t - hub.start_s;
            const pt = map.project(hub.coord);
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
          const pt = layer.coord ? map.project(layer.coord) : { x: W * 0.5, y: H * 0.48 };
          ctx.save();
          const vg = ctx.createRadialGradient(pt.x, pt.y, layer.inner_r || 130, pt.x, pt.y, layer.outer_r || 1050);
          vg.addColorStop(0, "rgba(4,10,14," + (0.22 * baseAlpha).toFixed(3) + ")");
          vg.addColorStop(0.5, "rgba(4,9,12," + (0.76 * baseAlpha).toFixed(3) + ")");
          vg.addColorStop(1, "rgba(2,5,8," + (0.95 * baseAlpha).toFixed(3) + ")");
          ctx.fillStyle = vg;
          ctx.fillRect(0, 0, W, H);
          ctx.restore();
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
            const lp = map.project([layer.label_lng ?? ((lngMin + lngMax) * 0.5), lat]);
            drawGlowingText(layer.label, lp.x + (layer.dx || 0), lp.y + (layer.dy || -34), layer.font_px || 36, {
              fill: "#FFFBEB",
              glowHex: layer.bloom || "#F5C542",
              glowStrength: "luminous",
              alpha: baseAlpha * easeOutCubic(seg(prog, 0.35, 0.7)),
            });
          }
        } else if (layer.type === "survey_pin") {
          const pt = map.project(layer.coord);
          const drop = easeOutBack(seg(t, tStart, tStart + 0.38));
          const col = layer.color || "#F5C542";
          const stemH = (layer.stem_px ?? 78) * clamp(drop, 0, 1.15);
          const headR = (layer.radius ?? 26) * clamp(drop, 0, 1.15);
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          // Ground pulse ring
          const pulse = (tLoc * 0.9) % 1;
          ctx.strokeStyle = rgbaStr(col, (1 - pulse) * 0.85);
          ctx.lineWidth = lerp(5, 1.5, pulse);
          ctx.beginPath(); ctx.ellipse(pt.x, pt.y, lerp(12, 68, pulse), lerp(6, 30, pulse), 0, 0, Math.PI * 2); ctx.stroke();
          // Ground anchor dot
          ctx.fillStyle = "#FFFFFF";
          ctx.beginPath(); ctx.arc(pt.x, pt.y, 7, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = col; ctx.lineWidth = 4; ctx.stroke();
          // Vertical 3D beacon stem
          const sg = ctx.createLinearGradient(pt.x, pt.y, pt.x, pt.y - stemH);
          sg.addColorStop(0, col); sg.addColorStop(1, "#FFFFFF");
          ctx.strokeStyle = sg; ctx.lineWidth = 5;
          ctx.beginPath(); ctx.moveTo(pt.x, pt.y); ctx.lineTo(pt.x, pt.y - stemH); ctx.stroke();
          // Beacon head with icon
          const hy = pt.y - stemH - headR * 0.6;
          ctx.shadowColor = col; ctx.shadowBlur = 24;
          ctx.fillStyle = "#081C26";
          ctx.beginPath(); ctx.arc(pt.x, hy, headR, 0, Math.PI * 2); ctx.fill();
          ctx.shadowBlur = 0;
          ctx.strokeStyle = col; ctx.lineWidth = 4.5; ctx.stroke();
          ctx.fillStyle = "#FFFFFF";
          ctx.strokeStyle = "#FFFFFF";
          const st = layer.style || "monument";
          if (st === "monument") {
            // Equator monument globe + ring icon
            ctx.lineWidth = 2.6;
            ctx.beginPath(); ctx.arc(pt.x, hy, headR * 0.42, 0, Math.PI * 2); ctx.stroke();
            ctx.beginPath(); ctx.ellipse(pt.x, hy, headR * 0.66, headR * 0.22, -0.25, 0, Math.PI * 2); ctx.stroke();
          } else if (st === "gps") {
            ctx.lineWidth = 2.8;
            ctx.beginPath(); ctx.arc(pt.x, hy, headR * 0.22, 0, Math.PI * 2); ctx.fill();
            ctx.beginPath(); ctx.arc(pt.x, hy, headR * 0.52, -0.7, 0.7); ctx.stroke();
            ctx.beginPath(); ctx.arc(pt.x, hy, headR * 0.52, Math.PI - 0.7, Math.PI + 0.7); ctx.stroke();
          } else if (st === "stake") {
            ctx.lineWidth = 4;
            ctx.beginPath(); ctx.moveTo(pt.x, hy - headR * 0.48); ctx.lineTo(pt.x, hy + headR * 0.48); ctx.stroke();
            ctx.strokeStyle = "#EF4444"; ctx.lineWidth = 3.5;
            ctx.beginPath(); ctx.moveTo(pt.x - headR * 0.35, hy - headR * 0.15); ctx.lineTo(pt.x + headR * 0.42, hy + headR * 0.05); ctx.stroke();
          } else if (st === "house") {
            ctx.lineWidth = 2.8;
            ctx.beginPath();
            ctx.moveTo(pt.x - headR * 0.44, hy + headR * 0.02);
            ctx.lineTo(pt.x, hy - headR * 0.42);
            ctx.lineTo(pt.x + headR * 0.44, hy + headR * 0.02);
            ctx.lineTo(pt.x + headR * 0.34, hy + headR * 0.02);
            ctx.lineTo(pt.x + headR * 0.34, hy + headR * 0.42);
            ctx.lineTo(pt.x - headR * 0.34, hy + headR * 0.42);
            ctx.lineTo(pt.x - headR * 0.34, hy + headR * 0.02);
            ctx.closePath(); ctx.stroke();
          }
          ctx.restore();
          if (layer.label) {
            drawGlowingText(layer.label, pt.x + (layer.label_dx || 0), hy - headR - 26 + (layer.label_dy || 0), layer.font_px || 36, {
              fill: "#FFFFFF",
              glowHex: col,
              glowStrength: "luminous",
              alpha: baseAlpha,
            });
          }
          if (layer.sublabel) {
            drawGlowingText(layer.sublabel, pt.x + (layer.label_dx || 0), hy - headR + 8 + (layer.label_dy || 0), Math.round((layer.font_px || 36) * 0.62), {
              fill: "#E2F4FA",
              glowHex: "#03161F",
              glowStrength: "subtle",
              alpha: baseAlpha * 0.92,
            });
          }
        } else if (layer.type === "year_badge") {
          const x = W * (layer.x_pct ?? 0.5);
          const y = H * (layer.y_pct ?? 0.21);
          const sc = lerp(0.92, 1.0, easeOutExpo(seg(t, tStart, tStart + 0.30)));
          drawGlowingText(String(layer.text || "1928"), x, y, Math.round((layer.font_px || 96) * sc), {
            fill: layer.fill || "#FFFBEB",
            glowHex: layer.glow_hex || "#F5C542",
            glowStrength: layer.glow_strength || "intense",
            alpha: baseAlpha,
          });
          if (layer.subtitle) {
            drawGlowingText(String(layer.subtitle), x, y + 66, 30, {
              fill: "#E2F4FA",
              glowHex: "#03161F",
              glowStrength: "subtle",
              alpha: baseAlpha * 0.95,
            });
          }
        } else if (layer.type === "scale_comparison") {
          const cy = H * (layer.y_pct ?? 0.44);
          const grow1 = easeOutExpo(seg(t, tStart, tStart + 0.65));
          const grow2 = easeOutExpo(seg(t, tStart + 0.9, tStart + 1.65));
          const xL = W * 0.14;
          const maxW = W * 0.72;
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          // Top bar: tectonic drift (cm-dm)
          const w1 = Math.max(10, maxW * 0.028 * grow1);
          ctx.fillStyle = "#38BDF8";
          ctx.shadowColor = "#38BDF8"; ctx.shadowBlur = 16;
          ctx.fillRect(xL, cy - 82, w1, 22);
          ctx.shadowBlur = 0;
          drawGlowingText(layer.top_label || "Reference Drift", xL + 220, cy - 114, 30, { fill: "#BAE6FD", glowHex: "#03161F", glowStrength: "subtle", alpha: baseAlpha });
          drawGlowingText(layer.top_value || "~cm", xL + w1 + 110, cy - 70, 38, { fill: "#38BDF8", glowHex: "#38BDF8", glowStrength: "luminous", alpha: baseAlpha * grow1 });
          // Bottom bar: comparative measured distance
          const w2 = maxW * grow2;
          const grad = ctx.createLinearGradient(xL, 0, xL + maxW, 0);
          grad.addColorStop(0, "#F5C542"); grad.addColorStop(1, "#EF4444");
          ctx.fillStyle = grad;
          ctx.shadowColor = "#EF4444"; ctx.shadowBlur = 24;
          ctx.fillRect(xL, cy + 44, w2, 28);
          ctx.shadowBlur = 0;
          drawGlowingText(layer.bottom_label || "Measured Offset", xL + 180, cy + 12, 30, { fill: "#FDE68A", glowHex: "#03161F", glowStrength: "subtle", alpha: baseAlpha * seg(t, tStart + 0.7, tStart + 1.0) });
          if (grow2 > 0.25) {
            drawGlowingText(layer.bottom_value || "100 m", xL + w2 * 0.52, cy + 114, 56, { fill: "#FFFFFF", glowHex: "#EF4444", glowStrength: "intense", alpha: baseAlpha * grow2 });
          }
          ctx.restore();
        } else if (layer.type === "orbital_sightlines") {
          const target = map.project(layer.coord);
          const mode = layer.mode || "stars";
          const prog = easeOutCubic(seg(t, tStart, tStart + 0.85));
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          if (mode === "stars") {
            // Celestial sightlines from high stars to target coordinate
            const stars = [
              { x: W * 0.22, y: H * 0.16 },
              { x: W * 0.50, y: H * 0.13 },
              { x: W * 0.78, y: H * 0.18 },
            ];
            for (let i = 0; i < stars.length; i++) {
              const s = stars[i];
              const tw = 0.75 + 0.25 * Math.sin(tLoc * 7 + i * 2);
              // Dashed celestial ray
              ctx.save();
              ctx.setLineDash([12, 10]);
              ctx.strokeStyle = rgbaStr("#FDE68A", 0.72 * prog);
              ctx.lineWidth = 3;
              ctx.beginPath();
              ctx.moveTo(s.x, s.y);
              ctx.lineTo(lerp(s.x, target.x, prog), lerp(s.y, target.y, prog));
              ctx.stroke();
              ctx.restore();
              // 4-point star glow
              const r = 18 * tw;
              ctx.fillStyle = "#FFFBEB";
              ctx.shadowColor = "#F5C542"; ctx.shadowBlur = 22;
              ctx.beginPath();
              ctx.moveTo(s.x, s.y - r); ctx.lineTo(s.x + r * 0.28, s.y - r * 0.28);
              ctx.lineTo(s.x + r, s.y); ctx.lineTo(s.x + r * 0.28, s.y + r * 0.28);
              ctx.lineTo(s.x, s.y + r); ctx.lineTo(s.x - r * 0.28, s.y + r * 0.28);
              ctx.lineTo(s.x - r, s.y); ctx.lineTo(s.x - r * 0.28, s.y - r * 0.28);
              ctx.closePath(); ctx.fill();
              ctx.shadowBlur = 0;
            }
          } else {
            // 2005 GPS satellite constellation beaming hydro-cyan telemetry lock
            const sats = [
              { x: W * 0.20 + Math.sin(tLoc * 1.1) * 45, y: H * 0.18 },
              { x: W * 0.52 + Math.cos(tLoc * 0.9) * 35, y: H * 0.14 },
              { x: W * 0.82 - Math.sin(tLoc * 1.2) * 40, y: H * 0.20 },
            ];
            for (const s of sats) {
              // Translucent lock cone
              const cg = ctx.createLinearGradient(s.x, s.y, target.x, target.y);
              cg.addColorStop(0, "rgba(56, 189, 248, 0.55)");
              cg.addColorStop(1, "rgba(56, 189, 248, 0.10)");
              ctx.strokeStyle = cg;
              ctx.lineWidth = 4;
              ctx.beginPath();
              ctx.moveTo(s.x, s.y);
              ctx.lineTo(lerp(s.x, target.x, prog), lerp(s.y, target.y, prog));
              ctx.stroke();
              // Satellite body + solar panels
              ctx.save();
              ctx.translate(s.x, s.y);
              ctx.rotate(-0.22);
              ctx.fillStyle = "#38BDF8";
              ctx.shadowColor = "#38BDF8"; ctx.shadowBlur = 18;
              ctx.fillRect(-34, -8, 22, 16);
              ctx.fillRect(12, -8, 22, 16);
              ctx.fillStyle = "#F4F1EA";
              ctx.fillRect(-10, -11, 20, 22);
              ctx.restore();
            }
            // Precision GPS target reticle
            ctx.strokeStyle = "#38BDF8"; ctx.lineWidth = 3.5;
            ctx.beginPath(); ctx.arc(target.x, target.y, 44 * prog, 0, Math.PI * 2); ctx.stroke();
          }
          ctx.restore();
        } else if (layer.type === "culmination_sun") {
          const target = map.project(layer.coord);
          const zenith = easeInOutCubic(seg(t, tStart, tStart + 2.2));
          const sunX = lerp(target.x - 160, target.x, zenith);
          const sunY = H * 0.18;
          ctx.save();
          ctx.globalAlpha = baseAlpha;
          // Golden zenith beam down to monument
          const bg = ctx.createLinearGradient(sunX, sunY, target.x, target.y);
          bg.addColorStop(0, "rgba(254, 240, 138, 0.72)");
          bg.addColorStop(1, "rgba(254, 240, 138, 0.05)");
          ctx.fillStyle = bg;
          ctx.beginPath();
          ctx.moveTo(sunX - 24, sunY);
          ctx.lineTo(sunX + 24, sunY);
          ctx.lineTo(target.x + 76, target.y);
          ctx.lineTo(target.x - 76, target.y);
          ctx.closePath();
          ctx.fill();
          // Shrinking shadow bar on ground (disappears at zenith!)
          const shLen = lerp(130, 4, zenith);
          ctx.strokeStyle = "rgba(3, 15, 22, 0.85)";
          ctx.lineWidth = 14;
          ctx.lineCap = "round";
          ctx.beginPath(); ctx.moveTo(target.x, target.y); ctx.lineTo(target.x + shLen, target.y + shLen * 0.18); ctx.stroke();
          // Radiant sun disc
          const sg = ctx.createRadialGradient(sunX, sunY, 8, sunX, sunY, 96);
          sg.addColorStop(0, "#FFFFFF");
          sg.addColorStop(0.32, "rgba(253, 224, 71, 0.95)");
          sg.addColorStop(1, "rgba(245, 197, 66, 0)");
          ctx.fillStyle = sg;
          ctx.beginPath(); ctx.arc(sunX, sunY, 96, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
          if (layer.label) {
            drawGlowingText(layer.label, target.x, sunY + 110, 34, {
              fill: "#FFFBEB",
              glowHex: "#F5C542",
              glowStrength: "luminous",
              alpha: baseAlpha,
            });
          }
        } else if (layer.type === "coord_plaque") {
          const cx = W * (layer.x_pct ?? 0.5);
          const cy = H * (layer.y_pct ?? 0.34);
          const pop = easeOutBack(seg(t, tStart, tStart + 0.35));
          ctx.save();
          ctx.translate(cx, cy);
          ctx.scale(clamp(pop, 0.85, 1.05), clamp(pop, 0.85, 1.05));
          ctx.globalAlpha = baseAlpha;
          // Engraved metallic archival plaque (authentic physical artifact, zero SaaS slop)
          const pw = 660, ph = 180;
          ctx.shadowColor = "rgba(0,0,0,0.68)"; ctx.shadowBlur = 32; ctx.shadowOffsetY = 14;
          const pg = ctx.createLinearGradient(-pw / 2, -ph / 2, pw / 2, ph / 2);
          pg.addColorStop(0, "#3A3124"); pg.addColorStop(0.5, "#5A4A33"); pg.addColorStop(1, "#2C241A");
          ctx.fillStyle = pg;
          ctx.fillRect(-pw / 2, -ph / 2, pw, ph);
          ctx.shadowBlur = 0;
          ctx.strokeStyle = "#E5C17B"; ctx.lineWidth = 5;
          ctx.strokeRect(-pw / 2 + 10, -ph / 2 + 10, pw - 20, ph - 20);
          ctx.strokeStyle = "rgba(229,193,123,0.45)"; ctx.lineWidth = 2;
          ctx.strokeRect(-pw / 2 + 20, -ph / 2 + 20, pw - 40, ph - 40);
          // 4 brass rivets
          ctx.fillStyle = "#F5D08A";
          for (const [rx, ry] of [[-pw / 2 + 34, -ph / 2 + 34], [pw / 2 - 34, -ph / 2 + 34], [-pw / 2 + 34, ph / 2 - 34], [pw / 2 - 34, ph / 2 - 34]]) {
            ctx.beginPath(); ctx.arc(rx, ry, 7, 0, Math.PI * 2); ctx.fill();
          }
          ctx.fillStyle = "#FFF3D1";
          ctx.font = "900 54px 'Archivo Black', sans-serif";
          ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(layer.coord_text || "0° 00' 00\\"", 0, -14);
          ctx.fillStyle = "#E5C17B";
          ctx.font = "600 24px 'Space Grotesk', sans-serif";
          ctx.fillText(layer.caption || "SURVEY COORDINATE PLAQUE", 0, 44);
          ctx.restore();
        }
      }
    }

    const ALLOW_WORLD_VOID = ${Boolean(mapOpts.allow_world_void || mapOpts.projection === "globe")};
    function clampMercatorCamera(cam) {
      if (ALLOW_WORLD_VOID) return cam;
      const bearing = cam.bearing || 0;
      const pitch = Math.max(0, Math.min(72, cam.pitch || 0));
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
      };
    }

    // Smooth camera sampling (pre-expanded camera_samples or scale-coupled inline keyframes)
    window.__setSceneCamera = function(cam) {
      const safe = clampMercatorCamera(cam);
      map.jumpTo({
        center: safe.center,
        zoom: safe.zoom,
        bearing: safe.bearing,
        pitch: safe.pitch,
      });
    };

    window.__drawSceneLayers = function(layers, t) {
      drawLayers(layers, t);
    };

    // Optical sub-frame shutter accumulator (blends MapLibre WebGL canvas + overlay canvas)
    window.__beginShutterAccum = function() {
      compCanvas.style.display = "block";
      compCtx.clearRect(0, 0, W, H);
    };
    window.__accumSubframe = function(subIdx) {
      compCtx.save();
      compCtx.globalAlpha = 1 / (subIdx + 1);
      compCtx.drawImage(map.getCanvas(), 0, 0, W, H);
      compCtx.drawImage(ovCanvas, 0, 0, W, H);
      compCtx.restore();
    };
    window.__endShutterAccum = function() {
      compCanvas.style.display = "none";
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
    @font-face { font-family: "EB Garamond"; src: url("${baseUrl}/fonts/EBGaramond-Variable.ttf") format("truetype"); font-weight: 400 800; }
    @font-face { font-family: "Archivo Black"; src: url("${baseUrl}/fonts/ArchivoBlack-Regular.ttf") format("truetype"); font-weight: 400 900; }
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
    shutter_samples: a.shutter_samples || 1,
  };
}

async function bakeAct(browser, baseUrl, vectorsJson, width, height, fps, act, outDir) {
  const outMp4 = join(outDir, act.output_file || act.output_name || `${act.act_id}.mp4`);
  const actKind = act.kind || act.mode || "map";
  const totalFrames = Math.max(1, Math.round(act.duration_s * fps));
  console.log(`\n=== Baking ${act.act_id} (${actKind}): ${act.duration_s.toFixed(3)}s (${totalFrames} frames) -> ${outMp4} ===`);

  const page = await browser.newPage();
  page.on("pageerror", (err) => console.error(`  [${act.act_id} pageerror]`, err));
  await page.setViewport({ width, height, deviceScaleFactor: 1 });
  const shotter = await createCdpScreenshotter(page, width, height, { quality: 92 });
  const encoder = spawnMjpegPipeEncoder(outMp4, { fps, crf: 15, gop: 1, preset: "fast", useVideoToolbox: false });
  const t0 = Date.now();
  const trackLog = [];

  try {
    if (actKind === "blueprint_paper") {
      await page.setContent(buildBlueprintHtml(baseUrl, width, height, vectorsJson, act), { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      for (let f = 0; f < totalFrames; f++) {
        await page.evaluate((sec) => window.__renderBlueprint(sec), f / fps);
        await encoder.writeFrame(await shotter.captureJpegBuffer());
        if (f % 60 === 0 || f === totalFrames - 1) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
    } else {
      await page.setContent(
        buildMapSceneHtml(baseUrl, width, height, vectorsJson, {
          tile_source: act.tile_source || "graded",
          projection: act.projection || "mercator",
          terrain_3d: Boolean(act.terrain_3d),
          terrain_exaggeration: act.terrain_exaggeration ?? 2.4,
          dem_maxzoom: act.dem_maxzoom ?? 10,
          allow_world_void: Boolean(act.allow_world_void),
        }),
        { waitUntil: "load" }
      );
      await page.evaluate(() => window.__ready);
      const samples = act.camera_samples || [];
      const layers = act.layers || [];
      const enableShutter = act.optical_shutter_blur !== false;

      // Pre-warm tiles across act timeline
      for (let f = 0; f < totalFrames; f += Math.max(15, Math.floor(totalFrames / 8))) {
        const cam = sampleCameraAt(samples, f, 0);
        await page.evaluate((c) => window.__setSceneCamera(c), cam);
        await page.evaluate((ms) => window.__waitIdle(ms), 1500);
      }

      for (let f = 0; f < totalFrames; f++) {
        const cam = sampleCameraAt(samples, f, 0);
        const subN = enableShutter ? Math.min(5, Math.max(1, cam.shutter_samples || 1)) : 1;
        if (subN > 1 && f > 0) {
          await page.evaluate(() => window.__beginShutterAccum());
          for (let k = 0; k < subN; k++) {
            const subOff = -0.5 + (k / (subN - 1)) * 0.5;
            const subCam = sampleCameraAt(samples, f, subOff);
            const subT = Math.max(0, (f + subOff) / fps);
            await page.evaluate((c) => window.__setSceneCamera(c), subCam);
            await page.evaluate((ms) => window.__waitIdle(ms), 1500);
            await page.evaluate(([ls, sec]) => window.__drawSceneLayers(ls, sec), [layers, subT]);
            await page.evaluate((idx) => window.__accumSubframe(idx), k);
          }
          await encoder.writeFrame(await shotter.captureJpegBuffer());
          await page.evaluate(() => window.__endShutterAccum());
        } else {
          await page.evaluate((c) => window.__setSceneCamera(c), cam);
          await page.evaluate((ms) => window.__waitIdle(ms), 1500);
          await page.evaluate(([ls, sec]) => window.__drawSceneLayers(ls, sec), [layers, f / fps]);
          await encoder.writeFrame(await shotter.captureJpegBuffer());
        }
        if (act.export_camera_track) {
          trackLog.push({ frame: f, t: Number((f / fps).toFixed(4)), ...cam });
        }
        if (f % 60 === 0 || f === totalFrames - 1) {
          console.log(`  [${act.act_id}] frame ${f + 1}/${totalFrames} (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
        }
      }
      if (act.export_camera_track) {
        writeFileSync(join(outDir, `${act.act_id}_camera_track.json`), JSON.stringify(trackLog));
      }
    }
  } finally {
    await shotter.close();
    await page.close();
  }
  await encoder.finish();
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args["scene-file"] || !args["out-dir"]) {
    console.error("Usage: render_map_scene.mjs --scene-file <spec.json> --out-dir <dir> [--base-dir <dir>]");
    process.exit(1);
  }
  const sceneFile = resolve(args["scene-file"]);
  const baseDir = resolve(args["base-dir"] || dirname(sceneFile));
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
  // Fail loud if any layer geom_ref is missing from the loaded vectors bundle.
  for (const act of spec.acts || []) {
    for (const layer of act.layers || []) {
      if (typeof layer.geom_ref === "string") {
        let cur = vectorsObj;
        for (const p of layer.geom_ref.split(".")) cur = cur && typeof cur === "object" ? cur[p] : undefined;
        if (!cur) {
          throw new Error(`Act '${act.act_id}' references missing geom_ref '${layer.geom_ref}' (loaded keys: ${Object.keys(vectorsObj).join(", ")})`);
        }
      }
    }
  }
  const vectorsJson = JSON.stringify(vectorsObj);

  const server = await startTileServer(0);
  const url = `http://127.0.0.1:${server.address().port}`;
  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: "new",
    args: getChromeArgs(width, height),
  });
  try {
    for (const act of spec.acts || []) {
      await bakeAct(browser, url, vectorsJson, width, height, fps, act, outDir);
    }
  } finally {
    await browser.close();
    server.close();
  }
  console.log("Declarative map scene bake complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
