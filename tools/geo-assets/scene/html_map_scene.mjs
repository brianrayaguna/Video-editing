import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DEFAULT_MAP_CENTER } from "../geo_defaults.mjs";
import { buildDynamicFontFaceCss } from "./font_css.mjs";
import { buildProjectionRuntime } from "./runtime_projection.mjs";
import { buildPolygonsRuntime } from "./runtime_polygons.mjs";
import { buildTypographyRuntime } from "./runtime_typography.mjs";
import { buildSpritesRuntime } from "./runtime_sprites.mjs";
import { buildLayersRuntime } from "./runtime_layers.mjs";
import { buildWebglCameraRuntime } from "./runtime_webgl_camera.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const DRAW_MATH_SRC = readFileSync(join(__dirname, "../map_draw_math.mjs"), "utf8").replace(/^export\s+/gm, "");
export const FLAG_RASTER_WIDTH = 1600;

export function defaultTileSource() {
  const attrPath = join(REPO_ROOT, "assets/geo/tiles_hq/attribution.json");
  if (existsSync(attrPath)) {
    try {
      const parsed = JSON.parse(readFileSync(attrPath, "utf8"));
      if (Array.isArray(parsed.sources) && parsed.sources.includes("google_map_tiles")) {
        return "realistic_graded";
      }
    } catch {
      // Fall through to default below.
    }
  }
  const hasTiles = existsSync(join(REPO_ROOT, "assets/geo/tiles/0/0/0.jpg"));
  const hasHq = existsSync(join(REPO_ROOT, "assets/geo/tiles_hq"));
  return !hasTiles && hasHq ? "realistic_graded" : "realistic";
}

export function resolveImageryCredit(mapOpts = {}) {
  const sourceMode = mapOpts.tile_source || defaultTileSource();
  let hqAttr = null;
  if (
    sourceMode === "hybrid" ||
    sourceMode === "realistic" ||
    sourceMode === "realistic_graded"
  ) {
    const attrPath = join(REPO_ROOT, "assets/geo/tiles_hq/attribution.json");
    if (existsSync(attrPath)) {
      try {
        hqAttr = JSON.parse(readFileSync(attrPath, "utf8"));
      } catch {
        hqAttr = null;
      }
    }
  }
  const usesGoogleTiles =
    Array.isArray(hqAttr?.sources) && hqAttr.sources.includes("google_map_tiles");
  if (usesGoogleTiles) {
    const gCredit =
      (typeof hqAttr?.credit_line === "string" && hqAttr.credit_line.trim()) ||
      (typeof hqAttr?.google_copyright === "string" && hqAttr.google_copyright.trim()) ||
      "Imagery ©Google";
    return gCredit;
  }
  if (mapOpts.show_credit === false) return "";
  if (typeof mapOpts.imagery_credit === "string" && mapOpts.imagery_credit.trim()) {
    return mapOpts.imagery_credit.trim();
  }
  if (typeof hqAttr?.credit_line === "string" && hqAttr.credit_line.trim()) {
    return hqAttr.credit_line.trim();
  }
  return "Sentinel-2 cloudless 2024 · EOX";
}

export function buildMapSceneHtml(baseUrl, width, height, vectorsJson, mapOpts = {}) {
  const imageryCredit =
    typeof resolveImageryCredit === "function"
      ? resolveImageryCredit(mapOpts)
      : typeof mapOpts.imagery_credit === "string"
        ? mapOpts.imagery_credit.trim()
        : "";
  const isPortrait = height > width;
  const sourceMode = mapOpts.tile_source || "realistic";
  const tileRoute =
    sourceMode === "project"
      ? "/tiles_project/{z}/{x}/{y}.jpg"
      : sourceMode === "project_graded"
        ? "/tiles_project_graded/{z}/{x}/{y}.jpg"
        : sourceMode === "realistic_graded"
          ? "/tiles_hq_graded/{z}/{x}/{y}.jpg"
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
    try {
      const THREE = await import("three");
      const { GLTFLoader } = await import("three/addons/loaders/GLTFLoader.js");
      const { DRACOLoader } = await import("three/addons/loaders/DRACOLoader.js");
      const { RoomEnvironment } = await import("three/addons/environments/RoomEnvironment.js");
      window.THREE = THREE;
      window.THREE_ADDONS = { GLTFLoader, DRACOLoader, RoomEnvironment };
      if (window.__resolveThreeReady) window.__resolveThreeReady();
    } catch (err) {
      window.__threeReadyError = err;
      if (window.__rejectThreeReady) window.__rejectThreeReady(err);
    }
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
    #imagery-credit {
      position: absolute;
      ${isPortrait ? "top: 44px; left: 36px; max-width: 72%;" : "bottom: 24px; right: 28px; max-width: 60%;"}
      z-index: 40;
      pointer-events: none;
      font-family: "Inter", sans-serif;
      font-size: ${isPortrait ? "18px" : "15px"};
      font-weight: 600;
      letter-spacing: 0.01em;
      line-height: 1.25;
      color: rgba(244, 241, 234, 0.80);
      text-shadow: 0 1px 4px rgba(3, 22, 31, 0.9), 0 0 10px rgba(3, 22, 31, 0.65);
    }
  </style>
</head>
<body>
  <div id="stage">
    <div id="map"></div>
    <canvas id="ov" width="${ovW}" height="${ovH}"></canvas>
  </div>${imageryCredit ? `\n  <div id="imagery-credit">${imageryCredit.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>` : ""}
  <canvas id="comp" width="${width}" height="${height}"></canvas>
  <script>
    const BASE_URL = ${JSON.stringify(baseUrl).replace(/</g, "\\u003c")};
    const VEC = ${vectorsJson.replace(/</g, "\\u003c")};
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
      ? new Promise((resolve, reject) => {
          if (typeof window.THREE !== "undefined") resolve();
          else if (window.__threeReadyError) reject(window.__threeReadyError);
          else {
            window.__resolveThreeReady = resolve;
            window.__rejectThreeReady = reject;
          }
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

${buildProjectionRuntime({ terrain3d })}
${buildPolygonsRuntime()}
${buildTypographyRuntime()}
${buildSpritesRuntime()}
${buildLayersRuntime({ allowWorldVoid: Boolean(mapOpts.allow_world_void || mapOpts.projection === "globe") })}
${buildWebglCameraRuntime({ terrain3d })}
  </script>
</body>
</html>`;
}

