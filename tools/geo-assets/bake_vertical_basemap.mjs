#!/usr/bin/env node
/**
 * Offline deterministic vertical (1080x1920) & horizontal (1920x1080) map camera baker
 * for Geoverum compositions.
 *
 * Uses raw CDP JPEG capture (`optimizeForSpeed: true`, q92), direct FFmpeg `image2pipe`
 * encoding (zero JPEG disk round-trip unless `KEEP_FRAMES=1`), Metal ANGLE on macOS,
 * and optional multi-process Chrome frame-range sharding (`WORKERS=2` default when `N>=120`).
 *
 * Optional GeoJSON coordinate projection is opt-in via `REGIONS_GEOJSON` and
 * `TECTONICS_GEOJSON` (relative paths under `/vector/` on the local tile server).
 */

import {
  accessSync,
  constants,
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import {
  concatMp4Slices,
  createCdpScreenshotter,
  getChromeArgs,
  spawnMjpegPipeEncoder,
} from "./fast_capture.mjs";
import { startTileServer } from "./serve_tiles.mjs";
import { DEFAULT_DEM_BOUNDS, parseCenterEnv } from "./geo_defaults.mjs";

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
  throw new Error("Chrome / chrome-headless-shell not found.");
}

const NAME = process.env.NAME || "basemap";
const WIDTH = Number(process.env.WIDTH || 1080);
const HEIGHT = Number(process.env.HEIGHT || 1920);
const FPS = Number(process.env.FPS || 30);
const DUR = Number(process.env.DUR || 5);
const N = Math.max(1, Math.round(FPS * DUR));
const PROJECTION = process.env.PROJECTION === "mercator" ? "mercator" : "globe";
const CENTER = parseCenterEnv(process.env.CENTER);
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
const USE_HW_ENCODE = process.env.HW_ENCODE === "1";
const REGIONS_GEOJSON = process.env.REGIONS_GEOJSON || "";
const TECTONICS_GEOJSON = process.env.TECTONICS_GEOJSON || "";
const TERRAIN = process.env.TERRAIN === "1";
const TERRAIN_EXAG = Number(process.env.TERRAIN_EXAG || 2.2);
const DEM_BOUNDS = (process.env.DEM_BOUNDS || DEFAULT_DEM_BOUNDS.join(",")).split(",").map(Number);
const HIGHLIGHT_PROP = process.env.HIGHLIGHT_PROP || "highlight";
const WORKERS = Math.max(
  1,
  Number(process.env.WORKERS || (!KEEP_FRAMES && N >= 120 ? 2 : 1))
);

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
    const TERRAIN = ${TERRAIN};
    const TERRAIN_EXAG = ${TERRAIN_EXAG};
    const REGIONS_GEOJSON = ${JSON.stringify(REGIONS_GEOJSON)};
    const TECTONICS_GEOJSON = ${JSON.stringify(TECTONICS_GEOJSON)};

    let regionsData = null;
    let tectonicsData = null;

    const initCam = KEYFRAMES && KEYFRAMES.length
      ? KEYFRAMES[0]
      : { center: FROM || CENTER, zoom: ZSTART, pitch: PITCH_START, bearing: BEARING_START };

    const styleSources = {
      sat: {
        type: "raster",
        tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"],
        tileSize: 256,
        maxzoom: 11
      }
    };
    const styleLayers = (GLOBE ? [] : [{ id: "bg", type: "background", paint: { "background-color": "#03161F" } }])
      .concat([{ id: "sat", type: "raster", source: "sat" }]);
    if (TERRAIN) {
      const DEM_B = ${JSON.stringify(DEM_BOUNDS)};
      styleSources.dem = {
        type: "raster-dem",
        tiles: [BASE_URL + "/dem/{z}/{x}/{y}.png"],
        tileSize: 256,
        encoding: "terrarium",
        bounds: DEM_B,
        minzoom: 4,
        maxzoom: 7
      };
      styleSources.hillshadeDem = {
        type: "raster-dem",
        tiles: [BASE_URL + "/dem/{z}/{x}/{y}.png"],
        tileSize: 256,
        encoding: "terrarium",
        bounds: DEM_B,
        minzoom: 4,
        maxzoom: 7
      };
      styleLayers.push({
        id: "hills",
        type: "hillshade",
        source: "hillshadeDem",
        paint: {
          "hillshade-exaggeration": 0.48,
          "hillshade-shadow-color": "#03161F",
          "hillshade-highlight-color": "#F4F1EA",
          "hillshade-accent-color": "#0B2938"
        }
      });
    }

    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: GLOBE ? "globe" : "mercator" },
        sky: GLOBE ? { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 4.5, 0.85, 6.0, 0] } : undefined,
        sources: styleSources,
        layers: styleLayers,
        terrain: TERRAIN ? { source: "dem", exaggeration: TERRAIN_EXAG } : undefined
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

    function wrapDelta(fromDeg, toDeg) {
      return ((((toDeg - fromDeg) + 180) % 360) + 360) % 360 - 180;
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
                k0.center[0] + wrapDelta(k0.center[0], k1.center[0]) * panT,
                k0.center[1] + (k1.center[1] - k0.center[1]) * panT,
              ],
              zoom: k0.zoom + (k1.zoom - k0.zoom) * eT,
              pitch: (k0.pitch || 0) + ((k1.pitch || 0) - (k0.pitch || 0)) * eT,
              bearing: (k0.bearing || 0) + wrapDelta(k0.bearing || 0, k1.bearing || 0) * eT,
            };
          }
        }
      }

      const p = totalFrames <= 1 ? 1 : frameIndex / (totalFrames - 1);
      const s = FROM ? EASE_SINE_IN_OUT(seg(p, 0, PAN)) : 1;
      const t = EASE_STRONG_IN_OUT(seg(p, FROM ? PAN * 0.4 : 0, HOLD));
      const holdProgress = p > HOLD ? seg(p, HOLD, 1.0) : 0;
      const center = FROM
        ? [FROM[0] + wrapDelta(FROM[0], CENTER[0]) * s, FROM[1] + (CENTER[1] - FROM[1]) * s]
        : CENTER;
      const zoom = ZSTART + (ZEND - ZSTART) * t + DRIFT_ZOOM * holdProgress;
      const pitch = PITCH_START + (PITCH - PITCH_START) * t;
      const bearing = BEARING_START + wrapDelta(BEARING_START, BEARING) * t;
      return { center, zoom, pitch, bearing };
    }

    async function fetchOptionalGeoJson(relName) {
      if (!relName) return null;
      const path = relName.startsWith("/") ? relName : "/vector/" + relName;
      const resp = await fetch(BASE_URL + path);
      if (!resp.ok) return null;
      return resp.json();
    }

    window.__ready = new Promise((res, rej) => {
      map.on("load", async () => {
        try {
          const [r1, r3] = await Promise.all([
            fetchOptionalGeoJson(REGIONS_GEOJSON),
            fetchOptionalGeoJson(TECTONICS_GEOJSON),
          ]);
          regionsData = r1;
          tectonicsData = r3;
          res();
        } catch (err) {
          rej(err);
        }
      });
    });

    window.__setCamFrame = function(frameIdx, totalFrames) {
      map.jumpTo(camAtFrame(frameIdx, totalFrames));
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
        regions: (regionsData?.features || []).map((f) => ({
          name: f.properties?.name,
          peninsula: f.properties?.peninsula || null,
          feature_type: f.properties?.feature_type || "province",
          d: geomToPath(f.geometry),
        })),
        tectonics: (tectonicsData?.features || [])
          .filter(
            (f) =>
              f.properties?.layer === "callout_trace" ||
              Boolean(f.properties?.[${JSON.stringify(HIGHLIGHT_PROP)}])
          )
          .map((f) => ({
            id: f.properties?.id || f.properties?.name,
            label: f.properties?.label || f.properties?.name,
            layer: f.properties?.layer,
            d: geomToPath(f.geometry),
          })),
      };
    };
  </script>
</body>
</html>`;
}

async function renderRangeToPipe({
  baseUrl,
  startFrame,
  endFrame,
  outMp4,
  coordsTargetFrame,
  workerId,
}) {
  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: "new",
    args: getChromeArgs(WIDTH, HEIGHT),
  });
  let coords = null;
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
    await page.setContent(buildPageHtml(baseUrl), { waitUntil: "load" });
    await page.evaluate(() => window.__ready);

    // Pre-warm tiles at boundary poses for this slice.
    const warmFrames = KEYFRAMES && KEYFRAMES.length
      ? KEYFRAMES.map((k) => k.frame).filter((f) => f >= startFrame && f < endFrame)
      : [];
    warmFrames.unshift(startFrame);
    warmFrames.push(Math.max(startFrame, endFrame - 1));
    for (const wf of new Set(warmFrames)) {
      await page.evaluate(([idx, total]) => window.__setCamFrame(idx, total), [wf, N]);
      await page.evaluate((ms) => window.__waitIdle(ms), 1500);
    }

    const shotter = await createCdpScreenshotter(page, WIDTH, HEIGHT, { quality: 92 });
    const encoder = spawnMjpegPipeEncoder(outMp4, {
      fps: FPS,
      crf: 16,
      gop: 1,
      preset: "fast",
      useVideoToolbox: USE_HW_ENCODE,
    });

    const t0 = Date.now();
    let succeeded = false;
    try {
      for (let i = startFrame; i < endFrame; i++) {
        await page.evaluate(([idx, total]) => window.__setCamFrame(idx, total), [i, N]);
        await page.evaluate((ms) => window.__waitIdle(ms), 1500);
        const buf = await shotter.captureJpegBuffer();
        await encoder.writeFrame(buf);
        if (coords === null && i === coordsTargetFrame && (REGIONS_GEOJSON || TECTONICS_GEOJSON)) {
          coords = await page.evaluate(() => window.__projectAll());
        }
        if ((i - startFrame) % 45 === 0 || i === endFrame - 1) {
          const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
          console.log(`  [${NAME}:w${workerId}] rendered frame ${i + 1}/${N} (${elapsed}s)`);
        }
      }
      succeeded = true;
    } finally {
      await shotter.close();
      if (!succeeded) {
        await encoder.abort();
      }
    }
    await encoder.finish();
  } finally {
    await browser.close();
  }
  return coords;
}

async function renderFramesToDisk({ baseUrl, framesDir, coordsTargetFrame }) {
  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: "new",
    args: getChromeArgs(WIDTH, HEIGHT),
  });
  let coords = null;
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
    await page.setContent(buildPageHtml(baseUrl), { waitUntil: "load" });
    await page.evaluate(() => window.__ready);

    const warmFrames = KEYFRAMES && KEYFRAMES.length
      ? KEYFRAMES.map((k) => k.frame)
      : [0, Math.max(0, N - 1)];
    for (const wf of warmFrames) {
      await page.evaluate(([idx, total]) => window.__setCamFrame(idx, total), [wf, N]);
      await page.evaluate((ms) => window.__waitIdle(ms), 1500);
    }

    const shotter = await createCdpScreenshotter(page, WIDTH, HEIGHT, { quality: 92 });
    const t0 = Date.now();
    const rebake = process.env.REBAKE === "1";
    try {
      for (let i = 0; i < N; i++) {
        const outFrame = join(framesDir, `f${String(i).padStart(4, "0")}.jpg`);
        if (!rebake && existsSync(outFrame) && statSync(outFrame).size > 1024) {
          continue;
        }
        await page.evaluate(([idx, total]) => window.__setCamFrame(idx, total), [i, N]);
        await page.evaluate((ms) => window.__waitIdle(ms), 1500);
        const buf = await shotter.captureJpegBuffer();
        writeFileSync(outFrame, buf);
        if (coords === null && i >= coordsTargetFrame && (REGIONS_GEOJSON || TECTONICS_GEOJSON)) {
          coords = await page.evaluate(() => window.__projectAll());
        }
        if (i % 45 === 0 || i === N - 1) {
          const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
          console.log(`  [${NAME}] rendered frame ${i + 1}/${N} (${elapsed}s)`);
        }
      }
    } finally {
      await shotter.close();
    }
  } finally {
    await browser.close();
  }
  return coords;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const mp4 = join(OUT, `${NAME}.mp4`);
  const coordsTargetFrame = Math.min(N - 1, Math.round(N * HOLD));

  const port = process.env.TILE_PORT != null ? Number(process.env.TILE_PORT) : 8767;
  const server = await startTileServer(port, "127.0.0.1");
  const boundPort = server.address()?.port ?? port;
  const baseUrl = `http://127.0.0.1:${boundPort}`;

  try {
    let coords = null;
    if (KEEP_FRAMES) {
      const framesDir = join(OUT, `frames-${NAME}`);
      mkdirSync(framesDir, { recursive: true });
      coords = await renderFramesToDisk({ baseUrl, framesDir, coordsTargetFrame });
      const pat = join(framesDir, "f%04d.jpg");
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
          "-preset",
          "fast",
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
    } else if (WORKERS <= 1) {
      coords = await renderRangeToPipe({
        baseUrl,
        startFrame: 0,
        endFrame: N,
        outMp4: mp4,
        coordsTargetFrame,
        workerId: 0,
      });
    } else {
      const sliceCount = Math.min(WORKERS, N);
      const baseLen = Math.floor(N / sliceCount);
      const rem = N % sliceCount;
      const slices = [];
      let cursor = 0;
      for (let w = 0; w < sliceCount; w++) {
        const len = baseLen + (w < rem ? 1 : 0);
        const startFrame = cursor;
        const endFrame = cursor + len;
        cursor = endFrame;
        slices.push({
          workerId: w,
          startFrame,
          endFrame,
          partMp4: join(OUT, `.${NAME}_part_${w}.mp4`),
        });
      }
      const listPath = join(OUT, `.${NAME}_concat.txt`);
      try {
        const results = await Promise.all(
          slices.map((sl) =>
            renderRangeToPipe({
              baseUrl,
              startFrame: sl.startFrame,
              endFrame: sl.endFrame,
              outMp4: sl.partMp4,
              coordsTargetFrame,
              workerId: sl.workerId,
            })
          )
        );
        coords = results.find((c) => c !== null) || null;
        writeFileSync(
          listPath,
          slices.map((sl) => `file '${sl.partMp4.replace(/'/g, "'\\''")}'`).join("\n") + "\n"
        );
        concatMp4Slices(
          slices.map((sl) => sl.partMp4),
          mp4,
          listPath
        );
      } finally {
        rmSync(listPath, { force: true });
        for (const sl of slices) {
          rmSync(sl.partMp4, { force: true });
        }
      }
    }

    if (coords) {
      const coordsPath = join(OUT, `${NAME}-coords.json`);
      writeFileSync(coordsPath, JSON.stringify(coords, null, 2));
      console.log(`[${NAME}] exported projected coordinates -> ${coordsPath}`);
    }
    console.log(`[${NAME}] encoded all-intra basemap -> ${mp4}`);
  } finally {
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
