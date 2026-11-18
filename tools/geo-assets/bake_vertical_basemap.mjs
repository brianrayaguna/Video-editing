#!/usr/bin/env node
/**
 * Offline deterministic vertical (1080x1920) & horizontal (1920x1080) map camera baker
 * for Geoverum compositions.
 *
 * Supports both single-move parameters (FROM/CENTER/ZSTART/ZEND) and multi-beat keyframe
 * trajectories (`KEYFRAMES_JSON`), driving local MapLibre GL (`5.24.0`) frame-by-frame
 * against the local offline tile server (`serve_tiles.mjs`) and encoding an all-intra
 * H.264 MP4 (`-g 1 -crf 16 -pix_fmt yuv420p`, explicit `bt709` color metadata).
 */

import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { startTileServer } from "./serve_tiles.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
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

const NAME = process.env.NAME || "basemap";
const WIDTH = Number(process.env.WIDTH || 1080);
const HEIGHT = Number(process.env.HEIGHT || 1920);
const FPS = Number(process.env.FPS || 30);
const DUR = Number(process.env.DUR || 5);
const N = Math.max(1, Math.round(FPS * DUR));
const PROJECTION = process.env.PROJECTION === "mercator" ? "mercator" : "globe";
const CENTER = (process.env.CENTER || "121.2,-1.6").split(",").map(Number);
const FROM = process.env.FROM ? process.env.FROM.split(",").map(Number) : null;
const ZSTART = Number(process.env.ZSTART || 1.85);
const ZEND = Number(process.env.ZEND || 6.0);
const PITCH_START = Number(process.env.PITCH_START || 0);
const PITCH = Number(process.env.PITCH || 0);
const BEARING_START = Number(process.env.BEARING_START || 0);
const BEARING = Number(process.env.BEARING || 0);
const PAN = Number(process.env.PAN || 0.35);
const HOLD = Number(process.env.HOLD || 0.75);
const DRIFT_ZOOM = Number(process.env.DRIFT_ZOOM || 0.12);
const KEYFRAMES = process.env.KEYFRAMES_JSON ? JSON.parse(process.env.KEYFRAMES_JSON) : null;
const OUT = process.env.OUT || process.cwd();
const KEEP_FRAMES = process.env.KEEP_FRAMES === "1";

function buildPageHtml(baseUrl) {
  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stars = Array.from({ length: 220 }, () => {
    const x = (rnd() * WIDTH).toFixed(0);
    const y = (rnd() * HEIGHT).toFixed(0);
    const r = (rnd() * 1.3 + 0.35).toFixed(2);
    const a = (rnd() * 0.55 + 0.18).toFixed(2);
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="#F4F1EA" opacity="${a}"/>`;
  }).join("");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${baseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${baseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    * { margin: 0; padding: 0; }
    html, body {
      width: ${WIDTH}px;
      height: ${HEIGHT}px;
      overflow: hidden;
      background: radial-gradient(ellipse at 50% 46%, #061D28 0%, #03161F 56%, #01090E 100%);
    }
    #stars { position: absolute; inset: 0; }
    #map { position: absolute; inset: 0; width: ${WIDTH}px; height: ${HEIGHT}px; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  ${PROJECTION === "globe" ? `<svg id="stars" width="${WIDTH}" height="${HEIGHT}">${stars}</svg>` : ""}
  <div id="map"></div>
  <script>
    const BASE_URL = ${JSON.stringify(baseUrl)};
    const CENTER = ${JSON.stringify(CENTER)};
    const FROM = ${JSON.stringify(FROM)};
    const ZSTART = ${ZSTART}, ZEND = ${ZEND};
    const PITCH_START = ${PITCH_START}, PITCH = ${PITCH};
    const BEARING_START = ${BEARING_START}, BEARING = ${BEARING};
    const PAN = ${PAN}, HOLD = ${HOLD}, DRIFT_ZOOM = ${DRIFT_ZOOM};
    const KEYFRAMES = ${JSON.stringify(KEYFRAMES)};
    const GLOBE = ${PROJECTION === "globe"};

    let sulawesiRegions = null;
    let sulawesiTectonics = null;

    const initCam = KEYFRAMES && KEYFRAMES.length
      ? KEYFRAMES[0]
      : { center: FROM || CENTER, zoom: ZSTART, pitch: PITCH_START, bearing: BEARING_START };

    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: GLOBE ? "globe" : "mercator" },
        sky: GLOBE ? { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 4.5, 0.85, 6.0, 0] } : undefined,
        sources: {
          sat: {
            type: "raster",
            tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"],
            tileSize: 256,
            maxzoom: 11
          }
        },
        layers: (GLOBE ? [] : [{ id: "bg", type: "background", paint: { "background-color": "#03161F" } }])
          .concat([{ id: "sat", type: "raster", source: "sat" }])
      },
      center: initCam.center,
      zoom: initCam.zoom,
      pitch: initCam.pitch || 0,
      bearing: initCam.bearing || 0,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true,
      maxTileCacheSize: 6000,
      canvasContextAttributes: { alpha: GLOBE, preserveDrawingBuffer: true }
    });

    function makeCubicBezier(x1, y1, x2, y2) {
      function sampleCurveX(t) { return ((1 - 3 * x2 + 3 * x1) * t * t * t) + ((3 * x2 - 6 * x1) * t * t) + (3 * x1 * t); }
      function sampleCurveY(t) { return ((1 - 3 * y2 + 3 * y1) * t * t * t) + ((3 * y2 - 6 * y1) * t * t) + (3 * y1 * t); }
      function sampleCurveDerivativeX(t) { return (3 * (1 - 3 * x2 + 3 * x1) * t * t) + (2 * (3 * x2 - 6 * x1) * t) + (3 * x1); }
      return function(x) {
        if (x <= 0) return 0;
        if (x >= 1) return 1;
        let t2 = x;
        for (let i = 0; i < 8; i++) {
          const xEst = sampleCurveX(t2) - x;
          if (Math.abs(xEst) < 1e-6) return sampleCurveY(t2);
          const d = sampleCurveDerivativeX(t2);
          if (Math.abs(d) < 1e-6) break;
          t2 -= xEst / d;
        }
        return sampleCurveY(t2);
      };
    }

    // Emil Kowalski's custom curves from DESIGN.md
    const EASE_STRONG_IN_OUT = makeCubicBezier(0.77, 0.0, 0.175, 1.0);
    const EASE_STRONG_OUT = makeCubicBezier(0.23, 1.0, 0.32, 1.0);
    const EASE_SINE_IN_OUT = (x) => -(Math.cos(Math.PI * x) - 1) / 2;

    function applyEase(name, t) {
      if (name === "strongInOut") return EASE_STRONG_IN_OUT(t);
      if (name === "strongOut") return EASE_STRONG_OUT(t);
      if (name === "sineInOut") return EASE_SINE_IN_OUT(t);
      return t;
    }

    function seg(p, a, b) {
      return b <= a ? 1 : Math.min(1, Math.max(0, (p - a) / (b - a)));
    }

    function camAtFrame(frameIndex, totalFrames) {
      if (KEYFRAMES && KEYFRAMES.length >= 2) {
        if (frameIndex <= KEYFRAMES[0].frame) return KEYFRAMES[0];
        const last = KEYFRAMES[KEYFRAMES.length - 1];
        if (frameIndex >= last.frame) return last;
        for (let i = 0; i < KEYFRAMES.length - 1; i++) {
          const k0 = KEYFRAMES[i];
          const k1 = KEYFRAMES[i + 1];
          if (frameIndex >= k0.frame && frameIndex <= k1.frame) {
            const rawT = seg(frameIndex, k0.frame, k1.frame);
            const eT = applyEase(k1.ease || "strongInOut", rawT);
            const panT = k1.panEase ? applyEase(k1.panEase, rawT) : eT;
            return {
              center: [
                k0.center[0] + (k1.center[0] - k0.center[0]) * panT,
                k0.center[1] + (k1.center[1] - k0.center[1]) * panT,
              ],
              zoom: k0.zoom + (k1.zoom - k0.zoom) * eT,
              pitch: (k0.pitch || 0) + ((k1.pitch || 0) - (k0.pitch || 0)) * eT,
              bearing: (k0.bearing || 0) + ((k1.bearing || 0) - (k0.bearing || 0)) * eT,
            };
          }
        }
      }

      const p = totalFrames <= 1 ? 1 : frameIndex / (totalFrames - 1);
      const s = FROM ? EASE_SINE_IN_OUT(seg(p, 0, PAN)) : 1;
      const t = EASE_STRONG_IN_OUT(seg(p, FROM ? PAN * 0.4 : 0, HOLD));
      const holdProgress = p > HOLD ? seg(p, HOLD, 1.0) : 0;
      const center = FROM
        ? [FROM[0] + (CENTER[0] - FROM[0]) * s, FROM[1] + (CENTER[1] - FROM[1]) * s]
        : CENTER;
      const zoom = ZSTART + (ZEND - ZSTART) * t + DRIFT_ZOOM * holdProgress;
      const pitch = PITCH_START + (PITCH - PITCH_START) * t;
      const bearing = BEARING_START + (BEARING - BEARING_START) * t;
      return { center, zoom, pitch, bearing };
    }

    window.__ready = new Promise((res) => {
      map.on("load", async () => {
        const [r1, r3] = await Promise.all([
          fetch(BASE_URL + "/vector/sulawesi_regions.geojson").then((r) => r.json()),
          fetch(BASE_URL + "/vector/sulawesi_tectonics.geojson").then((r) => r.json()),
        ]);
        sulawesiRegions = r1;
        sulawesiTectonics = r3;
        res();
      });
    });

    window.__setCamFrame = function(frameIdx, totalFrames) {
      map.jumpTo(camAtFrame(frameIdx, totalFrames));
    };

    window.__waitIdle = function(ms) {
      return new Promise((res) => {
        const t0 = performance.now();
        (function poll() {
          if (map.loaded() && map.areTilesLoaded()) {
            map.triggerRepaint();
            requestAnimationFrame(() => requestAnimationFrame(() => res(false)));
            return;
          }
          if (performance.now() - t0 > (ms || 9000)) {
            res(!map.areTilesLoaded());
            return;
          }
          setTimeout(poll, 35);
        })();
      });
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

    window.__projectAll = function() {
      const center = map.getCenter();
      return {
        canvas: { width: ${WIDTH}, height: ${HEIGHT} },
        view: {
          center: [Number(center.lng.toFixed(4)), Number(center.lat.toFixed(4))],
          zoom: Number(map.getZoom().toFixed(3)),
          pitch: Number(map.getPitch().toFixed(2)),
          bearing: Number(map.getBearing().toFixed(2)),
        },
        sulawesi_regions: sulawesiRegions.features.map((f) => ({
          name: f.properties.name,
          peninsula: f.properties.peninsula || null,
          feature_type: f.properties.feature_type || "province",
          d: geomToPath(f.geometry),
        })),
        tectonics: sulawesiTectonics.features
          .filter((f) => f.properties.layer === "callout_trace" || f.properties.is_palu_koro)
          .map((f) => ({
            id: f.properties.id || f.properties.name,
            label: f.properties.label || f.properties.name,
            layer: f.properties.layer,
            d: geomToPath(f.geometry),
          })),
      };
    };
  </script>
</body>
</html>`;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const framesDir = join(OUT, `frames-${NAME}`);
  mkdirSync(framesDir, { recursive: true });

  const port = Number(process.env.TILE_PORT || 8767);
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
      `--window-size=${WIDTH},${HEIGHT}`,
    ],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
    await page.setContent(buildPageHtml(baseUrl), { waitUntil: "load" });
    await page.evaluate(() => window.__ready);

    const t0 = Date.now();
    let coords = null;
    for (let i = 0; i < N; i++) {
      await page.evaluate(([idx, total]) => window.__setCamFrame(idx, total), [i, N]);
      await page.evaluate((ms) => window.__waitIdle(ms), 9000);
      await page.screenshot({
        path: join(framesDir, `f${String(i).padStart(4, "0")}.png`),
        clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT },
        optimizeForSpeed: true,
      });
      if (!coords && i >= Math.round(N * HOLD)) {
        coords = await page.evaluate(() => window.__projectAll());
      }
      if (i % 45 === 0 || i === N - 1) {
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        console.log(`  [${NAME}] rendered frame ${i + 1}/${N} (${elapsed}s)`);
      }
    }

    const mp4 = join(OUT, `${NAME}.mp4`);
    const pat = join(framesDir, "f%04d.png");
    const ff = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-framerate",
        String(FPS),
        "-i",
        pat,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-g",
        "1",
        "-crf",
        "16",
        "-movflags",
        "+faststart",
        mp4,
      ],
      { stdio: "inherit" }
    );
    if (ff.status !== 0) {
      throw new Error(`FFmpeg encoding failed with status ${ff.status}`);
    }
    if (coords) {
      const coordsPath = join(OUT, `${NAME}-coords.json`);
      writeFileSync(coordsPath, JSON.stringify(coords, null, 2));
      console.log(`[${NAME}] exported projected coordinates -> ${coordsPath}`);
    }
    if (!KEEP_FRAMES) {
      rmSync(framesDir, { recursive: true, force: true });
    }
    console.log(`[${NAME}] encoded all-intra basemap -> ${mp4}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
