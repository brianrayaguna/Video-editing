#!/usr/bin/env node
/**
 * Bake a native Geoverum 30s ME–South Asia A-roll:
 * graded satellite + staggered TR/IN/PK fills + corridor/LOC/Kashmir hatch,
 * locked to a continuous MapLibre camera (no source neon remaster).
 *
 * Bake knobs follow tools/geo-assets/README.md and render_sulawesi_shots.mjs
 * (JPEG q92, ~1500ms idle, Darwin GPU angle, frame resume unless REBAKE=1).
 */
import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync, copyFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { startTileServer } from "../../../tools/geo-assets/serve_tiles.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const REPO_ROOT = resolve(__dirname, "../../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const puppeteer = require("puppeteer-core");

const WIDTH = 1080;
const HEIGHT = 1920;
const FPS = 30;
const DUR = 30;
const N = FPS * DUR;
const NAME = "basemap-tectonics-30s";
const KEEP_FRAMES = process.env.KEEP_FRAMES === "1";

const KEYFRAMES = [
  { frame: 0, center: [48.0, 22.0], zoom: 2.05, pitch: 0, bearing: 0, ease: "strongOut" },
  { frame: 30, center: [55.0, 28.0], zoom: 3.05, pitch: 8, bearing: -2, ease: "strongInOut" },
  { frame: 90, center: [57.5, 28.5], zoom: 3.22, pitch: 10, bearing: 0, ease: "sineInOut", panEase: "sineInOut" },
  { frame: 210, center: [62.0, 28.0], zoom: 3.45, pitch: 14, bearing: 4, ease: "strongInOut" },
  { frame: 360, center: [69.5, 30.2], zoom: 4.35, pitch: 22, bearing: -6, ease: "strongInOut" },
  { frame: 480, center: [66.0, 31.5], zoom: 3.85, pitch: 18, bearing: -4, ease: "sineInOut" },
  { frame: 570, center: [58.5, 33.0], zoom: 3.55, pitch: 16, bearing: 2, ease: "strongInOut" },
  { frame: 645, center: [74.5, 33.8], zoom: 5.05, pitch: 34, bearing: -10, ease: "strongInOut" },
  { frame: 750, center: [72.0, 28.5], zoom: 4.15, pitch: 24, bearing: -4, ease: "sineInOut" },
  { frame: 899, center: [68.0, 28.0], zoom: 3.78, pitch: 16, bearing: 0, ease: "strongInOut" },
];

const PROJECT_FRAMES = [45, 120, 390, 525, 660, 780, 870];

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

function buildPageHtml(baseUrl) {
  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stars = Array.from({ length: 180 }, () => {
    const x = (rnd() * WIDTH).toFixed(0);
    const y = (rnd() * HEIGHT).toFixed(0);
    const r = (rnd() * 1.2 + 0.3).toFixed(2);
    const a = (rnd() * 0.5 + 0.15).toFixed(2);
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
      width: ${WIDTH}px; height: ${HEIGHT}px; overflow: hidden;
      background: radial-gradient(ellipse at 50% 46%, #061D28 0%, #03161F 56%, #01090E 100%);
    }
    #stars { position: absolute; inset: 0; }
    #map { position: absolute; inset: 0; width: ${WIDTH}px; height: ${HEIGHT}px; }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <svg id="stars" width="${WIDTH}" height="${HEIGHT}">${stars}</svg>
  <div id="map"></div>
  <script>
    const BASE_URL = ${JSON.stringify(baseUrl)};
    const KEYFRAMES = ${JSON.stringify(KEYFRAMES)};
    const W = ${WIDTH}, H = ${HEIGHT};

    const CORRIDOR = {
      type: "Feature",
      properties: { id: "corridor" },
      geometry: {
        type: "LineString",
        coordinates: [[35.2, 39.0], [42.0, 36.5], [52.0, 32.0], [65.0, 27.5], [78.5, 22.8]]
      }
    };
    const LOC = {
      type: "Feature",
      properties: { id: "loc" },
      geometry: {
        type: "LineString",
        coordinates: [[73.6, 34.9], [74.2, 34.5], [74.8, 34.1], [75.4, 33.7], [76.0, 33.2]]
      }
    };
    const KASHMIR = {
      type: "Feature",
      properties: { id: "kashmir" },
      geometry: {
        type: "Polygon",
        coordinates: [[
          [73.4, 35.6], [75.8, 35.4], [77.2, 34.6], [76.6, 33.4],
          [74.8, 33.2], [73.5, 34.0], [73.4, 35.6]
        ]]
      }
    };

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
    function seg(p, a, b) { return b <= a ? 1 : Math.min(1, Math.max(0, (p - a) / (b - a))); }

    function camAtFrame(frameIndex) {
      if (frameIndex <= KEYFRAMES[0].frame) return KEYFRAMES[0];
      const last = KEYFRAMES[KEYFRAMES.length - 1];
      if (frameIndex >= last.frame) return last;
      for (let i = 0; i < KEYFRAMES.length - 1; i++) {
        const k0 = KEYFRAMES[i], k1 = KEYFRAMES[i + 1];
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
      return last;
    }

    // Beat opacity envelopes (frame → opacity 0..1)
    function env(frame, on, peak, holdEnd, off) {
      if (frame < on || frame > off) return 0;
      if (frame < peak) return seg(frame, on, peak);
      if (frame <= holdEnd) return 1;
      return 1 - seg(frame, holdEnd, off);
    }

    function beatState(f) {
      // Staggered dual: Turkey cobalt first, India crimson ≥0.65s later
      const trDual = env(f, 30, 42, 200, 230);
      const inDual = env(f, 52, 64, 200, 230);
      const corridor = Math.max(trDual, inDual) * env(f, 36, 48, 195, 225);
      // Pakistan single-signal
      const pkSolo = env(f, 360, 375, 445, 470);
      // Turkey–Pakistan dual
      const trPk = env(f, 480, 495, 560, 585);
      const pkDual = env(f, 500, 512, 560, 585);
      // India–Pakistan + LOC
      const inLoc = env(f, 590, 605, 720, 750);
      const pkLoc = env(f, 605, 618, 720, 750);
      const locLine = Math.max(inLoc, pkLoc);
      // Kashmir hatch
      const hatch = env(f, 720, 740, 880, 899);

      return {
        turkey: Math.max(trDual, trPk * 0.85),
        india: Math.max(inDual, inLoc),
        pakistan: Math.max(pkSolo, pkDual, pkLoc),
        turkeyCobalt: trDual > 0.01 && trPk < 0.2,
        corridor,
        loc: locLine,
        hatch,
      };
    }

    let countries = null;
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: "globe" },
        sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 3.5, 0.7, 5.5, 0] },
        sources: {
          sat: {
            type: "raster",
            tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"],
            tileSize: 256,
            maxzoom: 11
          }
        },
        layers: [{ id: "sat", type: "raster", source: "sat" }]
      },
      center: KEYFRAMES[0].center,
      zoom: KEYFRAMES[0].zoom,
      pitch: 0,
      bearing: 0,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true,
      maxTileCacheSize: 6000,
      canvasContextAttributes: { alpha: true, preserveDrawingBuffer: true }
    });

    window.__ready = new Promise((res) => {
      map.on("load", async () => {
        countries = await fetch(BASE_URL + "/vector/countries_curated.geojson").then((r) => r.json());
        map.addSource("countries", { type: "geojson", data: countries });
        map.addSource("corridor", { type: "geojson", data: CORRIDOR });
        map.addSource("loc", { type: "geojson", data: LOC });
        map.addSource("kashmir", { type: "geojson", data: KASHMIR });

        // Crimson multiply stack approximated as two fill layers
        map.addLayer({
          id: "fill-pk-base",
          type: "fill",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "PK"],
          paint: { "fill-color": "#800E16", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "fill-pk-top",
          type: "fill",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "PK"],
          paint: { "fill-color": "#A81820", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "rim-pk",
          type: "line",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "PK"],
          paint: { "line-color": "#F4F1EA", "line-width": 2.0, "line-opacity": 0, "line-opacity-transition": { duration: 0 } }
        });

        map.addLayer({
          id: "fill-in-base",
          type: "fill",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "IN"],
          paint: { "fill-color": "#800E16", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "fill-in-top",
          type: "fill",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "IN"],
          paint: { "fill-color": "#C2412D", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "rim-in",
          type: "line",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "IN"],
          paint: { "line-color": "#F4F1EA", "line-width": 2.0, "line-opacity": 0, "line-opacity-transition": { duration: 0 } }
        });

        map.addLayer({
          id: "fill-tr-cobalt",
          type: "fill",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "TR"],
          paint: { "fill-color": "#2E74E6", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "fill-tr-crimson",
          type: "fill",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "TR"],
          paint: { "fill-color": "#C2412D", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "rim-tr",
          type: "line",
          source: "countries",
          filter: ["==", ["get", "iso_a2"], "TR"],
          paint: { "line-color": "#8CC2FF", "line-width": 1.8, "line-opacity": 0, "line-opacity-transition": { duration: 0 } }
        });

        map.addLayer({
          id: "corridor-line",
          type: "line",
          source: "corridor",
          paint: {
            "line-color": "#D9383A",
            "line-width": 2.4,
            "line-dasharray": [2.2, 1.6],
            "line-opacity": 0,
            "line-opacity-transition": { duration: 0 }
          }
        });
        map.addLayer({
          id: "loc-line",
          type: "line",
          source: "loc",
          paint: {
            "line-color": "#F5C542",
            "line-width": 2.2,
            "line-dasharray": [1.8, 1.4],
            "line-opacity": 0,
            "line-opacity-transition": { duration: 0 }
          }
        });
        map.addLayer({
          id: "kashmir-fill",
          type: "fill",
          source: "kashmir",
          paint: { "fill-color": "#F5C542", "fill-opacity": 0, "fill-opacity-transition": { duration: 0 } }
        });
        map.addLayer({
          id: "kashmir-hatch",
          type: "line",
          source: "kashmir",
          paint: {
            "line-color": "#F5C542",
            "line-width": 1.4,
            "line-dasharray": [0.6, 1.2],
            "line-opacity": 0,
            "line-opacity-transition": { duration: 0 }
          }
        });

        const stars = document.getElementById("stars");
        map.on("zoom", () => {
          const z = map.getZoom();
          stars.style.opacity = String(Math.max(0, Math.min(1, (3.2 - z) / 1.4)));
        });
        res();
      });
    });

    window.__setFrame = function(frameIdx) {
      map.jumpTo(camAtFrame(frameIdx));
      const s = beatState(frameIdx);

      map.setPaintProperty("fill-tr-cobalt", "fill-opacity", s.turkeyCobalt ? s.turkey * 0.52 : 0);
      map.setPaintProperty("fill-tr-crimson", "fill-opacity", s.turkeyCobalt ? 0 : s.turkey * 0.48);
      map.setPaintProperty("rim-tr", "line-opacity", s.turkey * 0.92);
      map.setPaintProperty("rim-tr", "line-color", s.turkeyCobalt ? "#8CC2FF" : "#F4F1EA");

      map.setPaintProperty("fill-in-base", "fill-opacity", s.india * 0.64);
      map.setPaintProperty("fill-in-top", "fill-opacity", s.india * 0.26);
      map.setPaintProperty("rim-in", "line-opacity", s.india * 0.95);

      map.setPaintProperty("fill-pk-base", "fill-opacity", s.pakistan * 0.64);
      map.setPaintProperty("fill-pk-top", "fill-opacity", s.pakistan * 0.26);
      map.setPaintProperty("rim-pk", "line-opacity", s.pakistan * 0.95);

      map.setPaintProperty("corridor-line", "line-opacity", s.corridor * 0.95);
      map.setPaintProperty("loc-line", "line-opacity", s.loc * 0.92);
      map.setPaintProperty("kashmir-fill", "fill-opacity", s.hatch * 0.22);
      map.setPaintProperty("kashmir-hatch", "line-opacity", s.hatch * 0.85);
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
      return "";
    }
    function findCountry(iso) {
      return countries.features.find((f) => f.properties.iso_a2 === iso);
    }

    window.__projectBeat = function(frameIdx) {
      window.__setFrame(frameIdx);
      const tr = findCountry("TR");
      const ind = findCountry("IN");
      const pk = findCountry("PK");
      const mid = CORRIDOR.geometry.coordinates[2];
      const midP = map.project(mid);
      const badgeTr = map.project([32.5, 36.2]);
      const badgeIn = map.project([72.0, 18.5]);
      const badgePk = map.project([66.5, 26.8]);
      const uav = map.project([74.8, 32.2]);
      return {
        frame: frameIdx,
        view: {
          center: [map.getCenter().lng, map.getCenter().lat],
          zoom: map.getZoom(),
          pitch: map.getPitch(),
          bearing: map.getBearing(),
        },
        turkeyD: geomToPath(tr.geometry),
        indiaD: geomToPath(ind.geometry),
        pakistanD: geomToPath(pk.geometry),
        corridorD: geomToPath(CORRIDOR.geometry),
        locD: geomToPath(LOC.geometry),
        kashmirD: geomToPath(KASHMIR.geometry),
        metric: { x: midP.x, y: midP.y },
        badgeTurkey: { x: badgeTr.x, y: badgeTr.y },
        badgeIndia: { x: badgeIn.x, y: badgeIn.y },
        badgePakistan: { x: badgePk.x, y: badgePk.y },
        uav: { x: uav.x, y: uav.y },
        beat: beatState(frameIdx),
      };
    };
  </script>
</body>
</html>`;
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });
  const framesDir = join(ASSETS_DIR, `frames-${NAME}`);
  mkdirSync(framesDir, { recursive: true });

  const port = Number(process.env.TILE_PORT || 8771);
  const server = await startTileServer(port, "127.0.0.1");
  const baseUrl = `http://127.0.0.1:${port}`;

  const chromeArgs =
    process.platform === "darwin"
      ? ["--no-sandbox", "--hide-scrollbars", "--use-gl=angle", `--window-size=${WIDTH},${HEIGHT}`]
      : [
          "--no-sandbox",
          "--disable-dev-shm-usage",
          "--use-gl=angle",
          "--use-angle=swiftshader",
          "--enable-unsafe-swiftshader",
          "--enable-webgl",
          `--window-size=${WIDTH},${HEIGHT}`,
        ];
  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: "new",
    args: chromeArgs,
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
    await page.setContent(buildPageHtml(baseUrl), { waitUntil: "load" });
    await page.evaluate(() => window.__ready);

    for (const wf of KEYFRAMES.map((k) => k.frame)) {
      await page.evaluate((idx) => window.__setFrame(idx), wf);
      await page.evaluate((ms) => window.__waitIdle(ms), 1500);
    }

    const projections = {};
    const t0 = Date.now();
    const rebake = process.env.REBAKE === "1";
    for (let i = 0; i < N; i++) {
      const outFrame = join(framesDir, `f${String(i).padStart(4, "0")}.jpg`);
      if (!rebake && existsSync(outFrame) && statSync(outFrame).size > 1024) {
        if (PROJECT_FRAMES.includes(i) && !projections[`f${String(i).padStart(4, "0")}`]) {
          projections[`f${String(i).padStart(4, "0")}`] = await page.evaluate(
            (idx) => window.__projectBeat(idx),
            i
          );
        }
        continue;
      }
      await page.evaluate((idx) => window.__setFrame(idx), i);
      await page.evaluate((ms) => window.__waitIdle(ms), 1500);
      await page.screenshot({
        path: outFrame,
        type: "jpeg",
        quality: 92,
        clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT },
      });
      if (PROJECT_FRAMES.includes(i)) {
        projections[`f${String(i).padStart(4, "0")}`] = await page.evaluate(
          (idx) => window.__projectBeat(idx),
          i
        );
      }
      if (i % 30 === 0 || i === N - 1) {
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        console.log(`  [${NAME}] frame ${i + 1}/${N} (${elapsed}s)`);
      }
    }

    writeFileSync(join(ASSETS_DIR, "projected-coords.json"), JSON.stringify(projections, null, 2));

    const mp4 = join(ASSETS_DIR, `${NAME}.mp4`);
    const pat = join(framesDir, "f%04d.jpg");
    const ff = spawnSync(
      "ffmpeg",
      [
        "-y", "-framerate", String(FPS), "-i", pat,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-g", "1", "-crf", "16", "-movflags", "+faststart", mp4,
      ],
      { stdio: "inherit" }
    );
    if (ff.status !== 0) throw new Error(`FFmpeg failed: ${ff.status}`);

    for (const f of [45, 120, 390, 660, 780]) {
      const src = join(framesDir, `f${String(f).padStart(4, "0")}.jpg`);
      if (existsSync(src)) copyFileSync(src, join(ASSETS_DIR, `qa_f${String(f).padStart(4, "0")}.jpg`));
    }

    if (!KEEP_FRAMES) rmSync(framesDir, { recursive: true, force: true });
    console.log(`[${NAME}] encoded -> ${mp4}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
