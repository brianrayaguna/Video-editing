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
  const sourceMode = mapOpts.tile_source || "hybrid";
  const tileRoute =
    sourceMode === "realistic"
      ? "/tiles_hq/{z}/{x}/{y}.jpg"
      : sourceMode === "graded"
        ? "/tiles/{z}/{x}/{y}.jpg"
        : "/tiles_hybrid/{z}/{x}/{y}.jpg";
  const satMaxZoom = 18;
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
      font-family: "Rubik";
      src: url("${baseUrl}/fonts/Rubik-Bold.ttf") format("truetype");
      font-weight: 700;
    }
    @font-face {
      font-family: "Rubik";
      src: url("${baseUrl}/fonts/Rubik-ExtraBold.ttf") format("truetype");
      font-weight: 800;
    }
    @font-face {
      font-family: "Rubik";
      src: url("${baseUrl}/fonts/Rubik-Black.ttf") format("truetype");
      font-weight: 900;
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
    <canvas id="ov" width="${width}" height="${height}"></canvas>
  </div>
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
    window.__imgCache = Object.create(null);
    window.__preloadAssets = async function(urls) {
      const unique = [...new Set((urls || []).filter(Boolean))];
      await Promise.all(unique.map((u) => new Promise((resolve) => {
        if (window.__imgCache[u]) { resolve(); return; }
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          // Rasterize SVG into a crisp fixed-size offscreen canvas so drawImage slicing works reliably
          const c = document.createElement("canvas");
          c.width = 360;
          c.height = 240;
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
        if (Array.isArray(g)) { for (const it of g) visit(it.geometry || it); return; }
        if (g.type === "Polygon") { for (const r of g.coordinates) visitRing(r); }
        else if (g.type === "MultiPolygon") { for (const p of g.coordinates) for (const r of p) visitRing(r); }
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
      targetCtx.beginPath();
      for (let i = 0; i < corners.length; i++) {
        const sp = map.project(corners[i]);
        if (i === 0) targetCtx.moveTo(sp.x, sp.y);
        else targetCtx.lineTo(sp.x, sp.y);
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
        if (Array.isArray(g)) { for (const it of g) collect(it.geometry || it); return; }
        if (g.type === "Polygon" && g.coordinates[0]) rings.push(g.coordinates[0]);
        else if (g.type === "MultiPolygon") { for (const p of g.coordinates) if (p[0]) rings.push(p[0]); }
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

    // Seamless exterior polygon dissolve + exterior-only feathered bloom + animated perimeter/directional reveal + optional diagonal hatch & flash surge
    function drawDissolvedPolygon(geom, { fillHex, fillAlpha = 0.56, rimHex = "#F4F1EA", rimWidth = 3.0, bloomHex = "#22C55E", bloomScale = 1.0, alpha = 1.0, preserveTerrain = true, borderReveal = 1.0, fillReveal = 1.0, revealAxis = null, revealProgress = 1.0, revealBounds = null, outlineOnly = false, perimeterProgress = 1.0, featherPx = 0, hatch = false, hatchColor = "rgba(255,255,255,0.22)", hatchSpacing = 22, hatchWidth = 6, flashHex = null, flashIntensity = 0 } = {}) {
      if (alpha <= 0.005 || !geom) return;
      if (outlineOnly && perimeterProgress < 0.999) {
        drawProgressiveGeomPerimeter(geom, perimeterProgress, { rimHex, rimWidth, bloomHex, bloomScale, alpha });
        return;
      }

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
      if (revealAxis && revealProgress < 0.999) {
        if (!applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds)) {
          ctx.restore();
          return;
        }
      } else if (borderReveal < 0.999) {
        ctx.beginPath();
        ctx.rect(0, 0, W, H * clamp(borderReveal, 0, 1));
        ctx.clip();
      }
      const effBloomHex = (flashHex && flashIntensity > 0.01) ? flashHex : bloomHex;
      const effBloomScale = bloomScale + flashIntensity * 1.15;
      if (effBloomHex && effBloomScale > 0) {
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = effBloomHex;
        rimCtx.fillRect(0, 0, W, H);
        const passes = [
          [42 * effBloomScale, Math.min(0.95, 0.45 + flashIntensity * 0.45)],
          [20 * effBloomScale, Math.min(0.98, 0.65 + flashIntensity * 0.30)],
          [8 * effBloomScale, Math.min(1.0, 0.80 + flashIntensity * 0.20)],
        ];
        for (const [blurPx, a] of passes) {
          ctx.save();
          ctx.globalAlpha = alpha * a;
          ctx.shadowColor = effBloomHex;
          ctx.shadowBlur = blurPx;
          ctx.drawImage(rimCanvas, 0, 0);
          ctx.restore();
        }
      }

      // 4. Crisp exterior rim (animated by borderReveal)
      if (rimHex && rimWidth > 0) {
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = (flashHex && flashIntensity > 0.25) ? "#FFFFFF" : rimHex;
        rimCtx.fillRect(0, 0, W, H);
        ctx.globalCompositeOperation = "source-over";
        ctx.globalAlpha = alpha * 0.92;
        ctx.drawImage(rimCanvas, 0, 0);
      }
      ctx.restore();

      // 5. Terrain-preserving interior fill (single clean translucent pass so mountain ridges shine through)
      if (!outlineOnly && fillReveal > 0.005) {
        rimCtx.clearRect(0, 0, W, H);
        rimCtx.globalCompositeOperation = "source-over";
        rimCtx.drawImage(maskCanvas, 0, 0);
        rimCtx.globalCompositeOperation = "source-in";
        rimCtx.fillStyle = fillHex;
        rimCtx.fillRect(0, 0, W, H);

        ctx.save();
        if (revealAxis && revealProgress < 0.999) {
          if (!applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds)) {
            ctx.restore();
            return;
          }
        }
        ctx.globalCompositeOperation = "source-over";
        ctx.globalAlpha = alpha * fillAlpha * clamp(fillReveal, 0, 1);
        if (featherPx > 0) {
          ctx.shadowColor = fillHex;
          ctx.shadowBlur = featherPx;
        }
        ctx.drawImage(rimCanvas, 0, 0);
        ctx.restore();

        // Optional 45-degree forward-slash (/) diagonal stripe hatch clipped cleanly to polygon silhouette
        if (hatch) {
          rimCtx.clearRect(0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-over";
          rimCtx.drawImage(maskCanvas, 0, 0);
          rimCtx.globalCompositeOperation = "source-in";
          rimCtx.strokeStyle = hatchColor;
          rimCtx.lineWidth = hatchWidth;
          rimCtx.beginPath();
          const diag = W + H;
          for (let x = -H; x < diag; x += hatchSpacing) {
            rimCtx.moveTo(x, H);
            rimCtx.lineTo(x + H, 0);
          }
          rimCtx.stroke();
          ctx.save();
          if (revealAxis && revealProgress < 0.999) {
            applyWorldDirectionalClip(ctx, geom, revealAxis, revealProgress, revealBounds);
          }
          ctx.globalAlpha = alpha * clamp(fillReveal, 0, 1);
          ctx.drawImage(rimCanvas, 0, 0);
          ctx.restore();
        }

        // Optional ownership tint-flash surge over interior silhouette
        if (flashHex && flashIntensity > 0.01) {
          rimCtx.clearRect(0, 0, W, H);
          rimCtx.globalCompositeOperation = "source-over";
          rimCtx.drawImage(maskCanvas, 0, 0);
          rimCtx.globalCompositeOperation = "source-in";
          rimCtx.fillStyle = flashHex;
          rimCtx.fillRect(0, 0, W, H);
          ctx.save();
          ctx.globalCompositeOperation = "screen";
          ctx.globalAlpha = alpha * Math.min(0.85, flashIntensity * 0.72);
          ctx.drawImage(rimCanvas, 0, 0);
          ctx.restore();
        }
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

    // Multi-ring luminous text glow with continuous sub-pixel transform scaling (zero 1px font-step jitter),
    // optional stroke outline, multi-line text support, and compact sub-pill for discrete headcounts.
    function drawGlowingText(text, x, y, fontPx, { fill = "#FFFFFF", glowHex = "#22C55E", glowStrength = "luminous", angle = 0, scale = 1.0, alpha = 1, family = "Space Grotesk", weight = 800, strokeHex = null, strokeWidth = 0, lineHeightMult = 1.08, subPill = null } = {}) {
      if (alpha <= 0.005 || scale <= 0.01) return;
      const lines = String(text ?? "").split("\\n");
      const lineStep = fontPx * lineHeightMult;
      const totalH = (lines.length - 1) * lineStep;
      ctx.save();
      ctx.translate(x, y);
      if (angle) ctx.rotate(angle);
      if (Math.abs(scale - 1.0) > 1e-4) ctx.scale(scale, scale);
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
          for (let li = 0; li < lines.length; li++) {
            ctx.fillText(lines[li], 0, -totalH * 0.5 + li * lineStep);
          }
          ctx.restore();
        }
      }
      ctx.globalAlpha = alpha;
      ctx.shadowColor = "rgba(0,0,0,0.85)";
      ctx.shadowBlur = Math.max(4, fontPx * 0.14);
      ctx.shadowOffsetY = 3;
      if (strokeHex && strokeWidth > 0) {
        ctx.strokeStyle = strokeHex;
        ctx.lineWidth = strokeWidth;
        ctx.lineJoin = "round";
        for (let li = 0; li < lines.length; li++) {
          ctx.strokeText(lines[li], 0, -totalH * 0.5 + li * lineStep);
        }
      }
      ctx.fillStyle = fill;
      for (let li = 0; li < lines.length; li++) {
        ctx.fillText(lines[li], 0, -totalH * 0.5 + li * lineStep);
      }

      if (subPill && subPill.alpha > 0.01 && subPill.text) {
        const pScale = subPill.scale ?? 1.0;
        const pFont = subPill.font_px ?? Math.max(18, Math.round(fontPx * 0.26));
        const pY = (totalH * 0.5) + fontPx * 0.52 + (subPill.dy ?? 6);
        ctx.save();
        ctx.translate(0, pY);
        ctx.scale(pScale, pScale);
        ctx.globalAlpha = alpha * subPill.alpha;
        ctx.font = "800 " + pFont + "px '" + family + "', sans-serif";
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

    function drawLandmarkSilhouette(x, y, heightPx, landmark = "statue_of_liberty", { fillHex = "#94A3B8", accentHex = "#CBD5E1", rimHex = "#E2E8F0", alpha = 1.0, riseProgress = 1.0 } = {}) {
      if (alpha <= 0.005 || heightPx <= 2 || riseProgress <= 0.01) return;
      ctx.save();
      ctx.translate(x, y);
      ctx.globalAlpha = alpha;
      // Clip from baseline upward so the monument rises out of the map anchor cleanly
      ctx.beginPath();
      ctx.rect(-heightPx * 0.9, -heightPx * 1.35, heightPx * 1.8, heightPx * 1.40);
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
        pts.push(map.project(c));
      }
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
          const revealProgress = layer.reveal_duration_s
            ? easeInOutCubic(seg(t, tStart + (layer.reveal_delay_s ?? 0), tStart + (layer.reveal_delay_s ?? 0) + layer.reveal_duration_s))
            : 1.0;
          const perimeterProgress = layer.perimeter_draw_s
            ? easeOutCubic(seg(t, tStart + (layer.perimeter_delay_s ?? 0), tStart + (layer.perimeter_delay_s ?? 0) + layer.perimeter_draw_s))
            : 1.0;
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
          if (layer.dissolve) {
            drawDissolvedPolygon(geom, {
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
              hatchSpacing: layer.hatch_spacing ?? 22,
              hatchWidth: layer.hatch_width ?? 6,
              flashHex,
              flashIntensity,
            });
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
          const space = layer.space || (layer.ref_zoom != null ? "map_plane" : "world_billboard");
          let sc = layer.pop_scale ? lerp(0.84, 1.0, easeOutBack(seg(t, tStart, tStart + (layer.pop_duration_s ?? 0.35)))) : 1.0;
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
          if (layer.count_to != null) {
            const cStart = tStart + (layer.count_delay_s ?? 0);
            const cDur = layer.count_duration_s ?? 0.85;
            const cu = easeOutCubic(seg(t, cStart, cStart + cDur));
            const val = Math.round(lerp(layer.count_from ?? 0, layer.count_to, cu));
            displayText = (layer.count_prefix || "") + val.toLocaleString("en-US") + (layer.count_suffix || "");
          } else if (layer.typewriter_s) {
            const twStart = tStart + (layer.typewriter_delay_s ?? 0);
            const twU = clamp(seg(t, twStart, twStart + layer.typewriter_s), 0, 1);
            const chars = Math.max(0, Math.round(displayText.length * twU));
            displayText = displayText.slice(0, chars);
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
              const spIn = easeOutBack(seg(t, spStart, spStart + (layer.sub_pill.pop_s ?? 0.28)));
              const spOut = layer.sub_pill.fade_out_s ? 1 - seg(t, spEnd - layer.sub_pill.fade_out_s, spEnd) : 1;
              subPill = {
                ...layer.sub_pill,
                alpha: clamp(spOut, 0, 1),
                scale: clamp(spIn, 0, 1.15),
              };
            }
          }
          const angDeg = layer.angle_end != null
            ? lerp(layer.angle_start || 0, layer.angle_end, seg(t, tStart, tEnd))
            : (layer.angle || 0);
          const angRad = angDeg * Math.PI / 180;
          const baseFont = layer.font_px || 64;
          const textOpts = {
            fill: layer.fill || "#FFFFFF",
            glowHex: layer.glow_hex ?? "#22C55E",
            glowStrength: layer.glow_strength || "luminous",
            angle: angRad,
            scale: sc,
            alpha: baseAlpha,
            family: layer.family || "Rubik",
            weight: layer.weight || 800,
            strokeHex: layer.stroke_hex || null,
            strokeWidth: layer.stroke_width ?? 0,
            lineHeightMult: layer.line_height_mult ?? 1.08,
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
          } else {
            const pt = map.project(curCoord);
            if (layer.ref_zoom != null) {
              const coupling = layer.scale_coupling ?? 0.45;
              const zScale = Math.pow(2, (map.getZoom() - layer.ref_zoom) * coupling);
              sc *= clamp(zScale, layer.min_scale ?? 0.45, layer.max_scale ?? 2.4);
              textOpts.scale = sc;
            }
            drawGlowingText(displayText, pt.x + (layer.dx || 0), pt.y + (layer.dy || 0) + yFly, baseFont, textOpts);
          }
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
              const pt = map.project(layer.coord);
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
          const p1 = map.project(layer.from);
          const p2 = map.project(layer.to);
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
              glowHex: "#03161F",
              glowStrength: "subtle",
              alpha: labelAlpha,
              family: "Rubik",
              weight: 900,
            });
            if (secondaryTxt) {
              drawGlowingText(String(secondaryTxt), 0, fPx * 0.55, Math.round(fPx * 0.58), {
                fill: lblCol,
                glowHex: "#03161F",
                glowStrength: "subtle",
                alpha: labelAlpha * 0.96,
                family: "Rubik",
                weight: 800,
              });
            }
            ctx.restore();
          }
        } else if (layer.type === "curved_arc_arrow") {
          const p1 = map.project(layer.from);
          const p2 = map.project(layer.to);
          const prog = layer.draw_s ? easeOutCubic(seg(t, tStart, tStart + layer.draw_s)) : 1.0;
          if (prog > 0.01) {
            const dx = p2.x - p1.x, dy = p2.y - p1.y;
            const len = Math.max(1, Math.hypot(dx, dy));
            const nx = -dy / len, ny = dx / len;
            const bend = layer.arc_offset_px != null ? layer.arc_offset_px : len * (layer.arc_ratio ?? 0.26);
            const cx = (p1.x + p2.x) * 0.5 + nx * bend;
            const cy = (p1.y + p2.y) * 0.5 + ny * bend;
            const steps = 40;
            const maxI = Math.max(2, Math.round(steps * prog));
            const pts = [];
            for (let i = 0; i <= maxI; i++) {
              const u = (i / steps);
              const inv = 1 - u;
              pts.push({
                x: inv * inv * p1.x + 2 * inv * u * cx + u * u * p2.x,
                y: inv * inv * p1.y + 2 * inv * u * cy + u * u * p2.y,
              });
            }
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
            // Arrowhead at tip
            const tip = pts[pts.length - 1];
            const prev = pts[Math.max(0, pts.length - 2)];
            const ang = Math.atan2(tip.y - prev.y, tip.x - prev.x);
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
              const lp = map.project(layer.label_coord);
              drawGlowingText(String(layer.label), lp.x + (layer.label_dx || 0), lp.y + (layer.label_dy || -90), layer.font_px || 54, {
                fill: "#E0F2FE",
                glowHex: layer.bloom_hex || "#38BDF8",
                glowStrength: "luminous",
                alpha: baseAlpha * slideP,
                family: "Rubik",
                weight: 800,
              });
            }
            ctx.restore();
          }
        } else if (layer.type === "counter_odometer") {
          const steps = layer.steps || [{ at_s: tStart, value: "0" }];
          const flyP = easeOutBack(seg(t, tStart, tStart + (layer.fly_up_s ?? 0.28)));
          const cx = W * (layer.x_pct ?? 0.5);
          const cy = H * (layer.y_pct ?? 0.22) + lerp(280, 0, clamp(flyP, 0, 1.06));
          const fPx = layer.font_px || 152;
          let curIdx = 0;
          for (let i = 0; i < steps.length; i++) {
            if (t >= steps[i].at_s) curIdx = i;
          }
          const curStep = steps[curIdx];
          const prevStep = curIdx > 0 ? steps[curIdx - 1] : null;
          const rollDur = layer.roll_s ?? 0.14;
          const rollP = prevStep ? easeOutCubic(seg(t, curStep.at_s, curStep.at_s + rollDur)) : 1.0;
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(((layer.angle_deg ?? -7) * Math.PI) / 180);
          ctx.beginPath();
          ctx.rect(-fPx * 1.6, -fPx * 0.72, fPx * 3.2, fPx * 1.44);
          ctx.clip();
          if (prevStep && rollP < 0.995) {
            drawGlowingText(String(prevStep.value), 0, lerp(0, -fPx * 1.15, rollP), fPx, {
              fill: layer.fill || "#FDE047",
              glowHex: layer.glow_hex || "#F59E0B",
              glowStrength: "intense",
              alpha: baseAlpha * (1 - rollP),
              family: "Rubik",
              weight: 900,
            });
          }
          drawGlowingText(String(curStep.value), 0, lerp(fPx * 1.15, 0, rollP), fPx, {
            fill: layer.fill || "#FDE047",
            glowHex: layer.glow_hex || "#F59E0B",
            glowStrength: "intense",
            alpha: baseAlpha,
            family: "Rubik",
            weight: 900,
          });
          ctx.restore();
        } else if (layer.type === "question_arc") {
          const pt = map.project(layer.coord);
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
            drawGlowingText("?", qx, qy, Math.round((layer.font_px || 66) * clamp(pop, 0, 1.15)), {
              fill: layer.fill || "#FDE047",
              glowHex: layer.glow_hex || "#F59E0B",
              glowStrength: "intense",
              angle: frac * 0.35,
              alpha: baseAlpha,
              family: "Rubik",
              weight: 900,
            });
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
          const anchor = layer.coord ? map.project(layer.coord) : { x: W * (layer.x_pct ?? 0.5), y: H * (layer.y_pct ?? 0.25) };
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
          ctx.font = "900 " + fPx + "px 'Rubik', sans-serif";
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
                fill: layer.fill || "#FFFFFF",
                glowHex: "#03161F",
                glowStrength: "subtle",
                alpha: baseAlpha * pop,
                family: "Rubik",
                weight: 900,
              });
            }
          }
          ctx.restore();
          // Graceful hand-drawn curved white Bezier arrow with open chevron tip
          if (layer.pointer_coord) {
            const tp = map.project(layer.pointer_coord);
            const sx = bx + (layer.arrow_start_dx || 0);
            const sy = by + (layer.arrow_start_dy ?? Math.round(lines.length * lineH * 0.5 + 14));
            const arrowProg = easeOutCubic(seg(t, tStart + 0.08, tStart + 0.44));
            if (arrowProg > 0.01) {
              const dx = tp.x - sx, dy = tp.y - sy;
              const len = Math.max(1, Math.hypot(dx, dy));
              const nx = -dy / len, ny = dx / len;
              const bend = layer.arrow_bend_px ?? (len * 0.24);
              const cx = (sx + tp.x) * 0.5 + nx * bend;
              const cy = (sy + tp.y) * 0.5 + ny * bend;
              const steps = 32;
              const maxI = Math.max(2, Math.round(steps * arrowProg));
              const pts = [];
              for (let i = 0; i <= maxI; i++) {
                const u = i / steps, inv = 1 - u;
                pts.push({
                  x: inv * inv * sx + 2 * inv * u * cx + u * u * tp.x,
                  y: inv * inv * sy + 2 * inv * u * cy + u * u * tp.y,
                });
              }
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
              // Open chevron V-head (hand-drawn style)
              const tip = pts[pts.length - 1];
              const prev = pts[Math.max(0, pts.length - 2)];
              const ang = Math.atan2(tip.y - prev.y, tip.x - prev.x);
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
          const pt = map.project(layer.coord);
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
          drawGlowingText(String(layer.text || ""), pt.x + (layer.dx || 0), pt.y - stemH - (layer.font_px || 40) * 0.65 * zSc + (layer.dy || 0), layer.font_px || 40, {
            fill: "#FFFFFF",
            glowHex: "#03161F",
            glowStrength: "subtle",
            scale: zSc,
            alpha: baseAlpha * pop,
            family: "Rubik",
            weight: 800,
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

          const basePt = map.project(layer.coord);
          const leftPt = layer.left_coord ? map.project(layer.left_coord) : basePt;
          const rightPt = layer.right_coord ? map.project(layer.right_coord) : basePt;
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
          const pt = map.project(layer.coord);
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
            const pt = map.project(coord);
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
            const pt = map.project(pin.coord);
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

    window.__drawSceneLayers = function(layers, t) {
      drawLayers(layers, t);
    };

    // Optical sub-frame shutter accumulator (blends MapLibre WebGL canvas + overlay canvas with roll overscan)
    window.__beginShutterAccum = function() {
      compCanvas.style.display = "block";
      compCtx.clearRect(0, 0, W, H);
    };
    window.__accumSubframe = function(subIdx) {
      compCtx.save();
      compCtx.globalAlpha = 1 / (subIdx + 1);
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
    roll: (a.roll || 0) + ((b.roll || 0) - (a.roll || 0)) * u,
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
      await page.setContent(
        buildMapSceneHtml(baseUrl, width, height, vectorsJson, {
          tile_source: act.tile_source || "hybrid",
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
      const preloadUrls = [];
      for (const layer of layers) {
        if (layer.type === "flag_pin" && layer.code) {
          preloadUrls.push(`${baseUrl}/flags/${String(layer.code).toLowerCase()}.svg`);
        }
      }
      if (preloadUrls.length > 0) {
        await page.evaluate((urls) => window.__preloadAssets(urls), preloadUrls);
      }
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
