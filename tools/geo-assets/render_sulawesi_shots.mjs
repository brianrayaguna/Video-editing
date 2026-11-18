#!/usr/bin/env node
/**
 * Render the 9 time-aligned cartographic base shots (2118 frames total, 70.600s @ 30fps,
 * 1080x1920 bt709) for the Geoverum Sulawesi documentary pilot and modular audio-mix studies.
 *
 * Uses offline Natural Earth / GADM geometry, Copernicus Sentinel-2 tiles served locally,
 * pre-rendered optical radial zoom-blur whips, and pre-rendered solar amber light-leak plates.
 */

import { copyFileSync, existsSync, mkdirSync, rmSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { startTileServer } from "./serve_tiles.mjs";
import { puppeteer, resolveChrome, sharp } from "./study_runner.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = dirname(dirname(__dirname));
const FPS = 30;
const W = 1080;
const H = 1920;

export const SULAWESI_SHOT_SPECS = [
  { id: "shot_01_hook_dive", startS: 0.0, durationS: 10.167, frames: 305 },
  { id: "shot_02_peninsulas", startS: 10.167, durationS: 5.4, frames: 162 },
  { id: "shot_03_three_gulfs", startS: 15.567, durationS: 10.2, frames: 306 },
  { id: "shot_04_three_plates", startS: 25.767, durationS: 10.4, frames: 312 },
  { id: "shot_05_puzzle", startS: 36.167, durationS: 6.133, frames: 184 },
  { id: "shot_06_palu_koro", startS: 42.3, durationS: 8.2, frames: 246 },
  { id: "shot_07_archipelago", startS: 50.5, durationS: 6.3, frames: 189 },
  { id: "shot_08_relief_climax", startS: 56.8, durationS: 9.233, frames: 277 },
  { id: "shot_09_outro_cta", startS: 66.033, durationS: 4.567, frames: 137 },
];

function makeCubicBezier(x1, y1, x2, y2) {
  function sx(t) {
    return (1 - 3 * x2 + 3 * x1) * t ** 3 + (3 * x2 - 6 * x1) * t ** 2 + 3 * x1 * t;
  }
  function sy(t) {
    return (1 - 3 * y2 + 3 * y1) * t ** 3 + (3 * y2 - 6 * y1) * t ** 2 + 3 * y1 * t;
  }
  function dx(t) {
    return 3 * (1 - 3 * x2 + 3 * x1) * t ** 2 + 2 * (3 * x2 - 6 * x1) * t + 3 * x1;
  }
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
const EASE_OUT = makeCubicBezier(0.23, 1.0, 0.32, 1.0);

function computeShotFrameState(shotId, localIdx, shotLen) {
  const u = shotLen <= 1 ? 1 : localIdx / (shotLen - 1);
  const tLocal = localIdx / FPS;

  if (shotId === "shot_01_hook_dive") {
    const eCam = EASE_IN_OUT(Math.min(1, u / 0.88));
    const whipBoost = u > 0.9 ? ((u - 0.9) / 0.1) ** 3 * 0.85 : 0;
    const outlineProg = Math.min(1, Math.max(0, (tLocal - 1.15) / 1.45));
    const kProg = Math.min(1, Math.max(0, (tLocal - 2.35) / 1.45));
    const kOpacity = tLocal < 2.2 ? 0 : tLocal > 5.8 ? Math.max(0.28, 1 - (tLocal - 5.8) / 2.2) : 1;
    return {
      cam: {
        projection: "globe",
        center: [125.0 + (121.25 - 125.0) * eCam, 2.8 + (-1.45 - 2.8) * eCam],
        zoom: 2.15 + (5.72 - 2.15) * eCam + whipBoost,
        pitch: 14 * eCam,
        bearing: -3 * eCam,
      },
      viz: {
        mode: "hook",
        outlineProg,
        kProg,
        kOpacity,
        landTintAlpha: Math.min(0.24, outlineProg * 0.24),
      },
    };
  }

  if (shotId === "shot_02_peninsulas") {
    const e = EASE_OUT(u);
    const activePeninsulas = [
      { key: "northern_peninsula", start: 2.65, color: "#2E6A99", accent: "#7CE0F9" },
      { key: "eastern_peninsula", start: 3.3, color: "#367BA8", accent: "#7CE0F9" },
      { key: "southeastern_peninsula", start: 3.92, color: "#2E6A99", accent: "#F5C542" },
      { key: "southern_peninsula", start: 4.65, color: "#C2412D", accent: "#F5C542" },
    ];
    const penStates = activePeninsulas.map((p) => ({
      ...p,
      alpha: Math.min(1, Math.max(0, (tLocal - p.start) / 0.42)),
    }));
    return {
      cam: {
        projection: "mercator",
        center: [121.28 + 0.1 * e, -1.42 - 0.08 * e],
        zoom: 5.75 + 0.12 * e,
        pitch: 14 + 4 * e,
        bearing: -2 + 2 * e,
      },
      viz: {
        mode: "peninsulas",
        penStates,
      },
    };
  }

  if (shotId === "shot_03_three_gulfs") {
    const e = EASE_IN_OUT(u);
    return {
      cam: {
        projection: "mercator",
        center: [121.35 + 0.15 * e, -1.25 - 0.2 * e],
        zoom: 5.9 + 0.35 * e,
        pitch: 16 + 14 * e,
        bearing: -4 + 10 * e,
      },
      viz: {
        mode: "gulfs",
        tominiAlpha: Math.min(1, Math.max(0, (tLocal - 1.55) / 0.45)),
        toloAlpha: Math.min(1, Math.max(0, (tLocal - 2.6) / 0.45)),
        boneAlpha: Math.min(1, Math.max(0, (tLocal - 3.25) / 0.45)),
        pulsePhase: (tLocal * 0.8) % 1,
      },
    };
  }

  if (shotId === "shot_04_three_plates") {
    const e = EASE_IN_OUT(u);
    const whipBoost = u > 0.94 ? ((u - 0.94) / 0.06) ** 3 * 0.42 : 0;
    return {
      cam: {
        projection: "mercator",
        center: [122.4 + 0.6 * e, -2.0 + 0.25 * e],
        zoom: 4.35 + 0.35 * e + whipBoost,
        pitch: 10 + 6 * e,
        bearing: -6 + 8 * e,
      },
      viz: {
        mode: "plates",
        eurasiaProg: Math.min(1, Math.max(0, (tLocal - 2.35) / 0.95)),
        australiaProg: Math.min(1, Math.max(0, (tLocal - 3.05) / 0.95)),
        pacificProg: Math.min(1, Math.max(0, (tLocal - 3.85) / 0.95)),
        collisionAlpha: Math.min(1, Math.max(0, (tLocal - 6.1) / 0.85)),
        pulsePhase: (tLocal * 0.95) % 1,
      },
    };
  }

  if (shotId === "shot_05_puzzle") {
    const e = EASE_OUT(u);
    const settle = Math.min(1, Math.max(0, (tLocal - 0.4) / 3.4));
    const shakeX = tLocal > 4.9 && tLocal < 5.85 ? Math.sin(tLocal * 44) * 5 * (5.85 - tLocal) : 0;
    const shakeY = tLocal > 4.9 && tLocal < 5.85 ? Math.cos(tLocal * 37) * 4 * (5.85 - tLocal) : 0;
    return {
      cam: {
        projection: "mercator",
        center: [121.2 + 0.14 * e, -1.45],
        zoom: 5.6 + 0.25 * e,
        pitch: 18 - 8 * e,
        bearing: 6 - 7 * e,
      },
      viz: {
        mode: "puzzle",
        settle: EASE_OUT(settle),
        fractureGlow: tLocal > 4.9 ? Math.min(1, (tLocal - 4.9) / 0.45) : 0.35,
        shakeX,
        shakeY,
      },
    };
  }

  if (shotId === "shot_06_palu_koro") {
    const e = EASE_IN_OUT(u);
    return {
      cam: {
        projection: "mercator",
        center: [120.38 + 0.28 * e, -1.25 - 0.12 * e],
        zoom: 6.32 + 0.26 * e,
        pitch: 24 + 6 * e,
        bearing: -6 + 4 * e,
      },
      viz: {
        mode: "palukoro",
        faultProg: Math.min(1, Math.max(0, (tLocal - 0.45) / 1.6)),
        labelAlpha: Math.min(1, Math.max(0, (tLocal - 0.9) / 0.45)),
        upliftPulse: Math.min(1, Math.max(0, (tLocal - 3.3) / 1.2)),
      },
    };
  }

  if (shotId === "shot_07_archipelago") {
    const e = EASE_IN_OUT(u);
    return {
      cam: {
        projection: "mercator",
        center: [118.2 + 2.8 * e, -2.5 + 1.0 * e],
        zoom: 4.65 + 0.72 * e,
        pitch: 12 + 8 * e,
        bearing: -2 + 3 * e,
      },
      viz: {
        mode: "archipelago",
        ringPulse: (tLocal * 0.65) % 1,
        sulawesiFocus: Math.min(1, Math.max(0, tLocal / 1.2)),
      },
    };
  }

  if (shotId === "shot_08_relief_climax") {
    const isKarstPhase = localIdx >= 132;
    const subU = isKarstPhase ? (localIdx - 132) / Math.max(1, shotLen - 133) : localIdx / 131;
    const crossFadeAlpha =
      localIdx >= 122 && localIdx <= 144 ? (localIdx - 122) / 22 : localIdx > 144 ? 1 : 0;
    return {
      cam: isKarstPhase
        ? {
            projection: "mercator",
            center: [119.63 + 0.08 * subU, -4.97 + 0.08 * subU],
            zoom: 10.6 + 0.42 * subU,
            pitch: 46 + 4 * subU,
            bearing: 14 + 7 * subU,
          }
        : {
            projection: "mercator",
            center: [120.02 - 0.04 * subU, -1.18 + 0.22 * subU],
            zoom: 10.25 + 0.42 * subU,
            pitch: 42 + 4 * subU,
            bearing: -10 + 5 * subU,
          },
      viz: {
        mode: "relief",
        phase: isKarstPhase ? "karst" : "palu",
        crossFadeAlpha,
        scaleCueAlpha: Math.min(1, Math.max(0, (tLocal - 0.55) / 0.5)),
        faultOverlayAlpha: isKarstPhase ? 0 : Math.max(0.25, 0.78 - 0.45 * subU),
      },
    };
  }

  // shot_09_outro_cta
  const e = EASE_IN_OUT(u);
  const dipOut = tLocal > 4.25 ? Math.max(0, 1 - (tLocal - 4.25) / 0.3) : 1;
  return {
    cam: {
      projection: "globe",
      center: [121.3 + 2.5 * e, -1.5 + 1.2 * e],
      zoom: 5.5 - 1.85 * e,
      pitch: 12 * (1 - e),
      bearing: 0,
    },
    viz: {
      mode: "outro",
      outlineAlpha: 0.72 * dipOut,
      dipOut,
    },
  };
}

/** Synthesize optical radial zoom-blur frame using concentric Lanczos/cubic taps. */
async function preRenderRadialZoomBlur(srcJpg, outJpg, strength) {
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

/** Synthesize solar amber-cream optical light-leak plate and blend onto a shot frame. */
async function buildWarmLightLeakOverlayBuffer() {
  const buf = Buffer.alloc(W * H * 4);
  for (let y = 0; y < H; y++) {
    const ny = y / H;
    for (let x = 0; x < W; x++) {
      const nx = x / W;
      const d1 = Math.hypot((nx - 0.84) * 1.15, (ny - 0.16) * 0.85);
      const lobe1 = Math.exp(-d1 * d1 * 4.4);
      const d2 = Math.hypot((nx - 0.14) * 1.05, (ny - 0.78) * 0.9);
      const lobe2 = Math.exp(-d2 * d2 * 3.8) * 0.78;
      const diag = Math.exp(-Math.pow(nx * 0.75 + ny * 0.65 - 0.72, 2) * 16.0) * 0.45;
      const intensity = Math.min(1.0, lobe1 * 0.95 + lobe2 * 0.72 + diag * 0.55);

      const off = (y * W + x) * 4;
      buf[off] = Math.min(255, Math.round(240 + 15 * intensity));
      buf[off + 1] = Math.min(255, Math.round(138 + 110 * Math.pow(intensity, 1.3)));
      buf[off + 2] = Math.min(255, Math.round(40 + 195 * Math.pow(intensity, 2.2)));
      buf[off + 3] = Math.min(255, Math.round(255 * Math.pow(intensity, 0.82)));
    }
  }
  return sharp(buf, { raw: { width: W, height: H, channels: 4 } }).png().toBuffer();
}

async function applyLightLeakBlend(srcJpg, outJpg, leakPngBuf, opacity) {
  const overlayBuf = await sharp(leakPngBuf)
    .ensureAlpha()
    .linear([1, 1, 1, opacity], [0, 0, 0, 0])
    .toBuffer();

  await sharp(srcJpg)
    .composite([{ input: overlayBuf, blend: "screen" }])
    .jpeg({ quality: 92 })
    .toFile(outJpg);
}

async function applyCrossfadeBlend(fromJpg, toJpg, outJpg, alpha) {
  const [bufA, bufB] = await Promise.all([
    sharp(fromJpg).raw().toBuffer(),
    sharp(toJpg).raw().toBuffer(),
  ]);
  const out = Buffer.allocUnsafe(bufA.length);
  const a = Math.min(1, Math.max(0, alpha));
  const invA = 1 - a;
  for (let i = 0; i < bufA.length; i++) {
    out[i] = Math.round(bufA[i] * invA + bufB[i] * a);
  }
  await sharp(out, { raw: { width: W, height: H, channels: 3 } })
    .jpeg({ quality: 92 })
    .toFile(outJpg);
}

function encodeSeqToMp4(pattern, outMp4) {
  const ff = spawnSync(
    "ffmpeg",
    [
      "-hide_banner",
      "-y",
      "-framerate",
      String(FPS),
      "-i",
      pattern,
      "-c:v",
      "libx264",
      "-profile:v",
      "high",
      "-pix_fmt",
      "yuv420p",
      "-r",
      String(FPS),
      "-fps_mode",
      "cfr",
      "-color_primaries",
      "bt709",
      "-color_trc",
      "bt709",
      "-colorspace",
      "bt709",
      "-color_range",
      "tv",
      "-crf",
      "17",
      "-g",
      "60",
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ff.status !== 0) {
    throw new Error(`FFmpeg encode failed for ${outMp4}`);
  }
}

function buildRenderPageHtml(tileBaseUrl) {
  let seed = 17;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stars = Array.from({ length: 200 }, () => {
    const x = (rnd() * W).toFixed(0);
    const y = (rnd() * H).toFixed(0);
    const r = (rnd() * 1.2 + 0.35).toFixed(2);
    const a = (rnd() * 0.5 + 0.16).toFixed(2);
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="#F4F1EA" opacity="${a}"/>`;
  }).join("");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <link href="${tileBaseUrl}/vendor/maplibre-gl.css" rel="stylesheet" />
  <script src="${tileBaseUrl}/vendor/maplibre-gl.js"></script>
  <style>
    @font-face {
      font-family: 'Space Grotesk';
      src: url('${tileBaseUrl}/fonts/SpaceGrotesk-Variable.ttf') format('truetype');
      font-weight: 300 700;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 1080px;
      height: 1920px;
      overflow: hidden;
      background: radial-gradient(ellipse at 50% 46%, #061D28 0%, #03161F 58%, #010A0F 100%);
      font-family: 'Space Grotesk', sans-serif;
    }
    #stars, #map, #vector-stage {
      position: absolute;
      inset: 0;
      width: 1080px;
      height: 1920px;
      pointer-events: none;
    }
    .maplibregl-control-container { display: none !important; }
  </style>
</head>
<body>
  <svg id="stars" width="1080" height="1920">${stars}</svg>
  <div id="map"></div>
  <svg id="vector-stage" width="1080" height="1920" viewBox="0 0 1080 1920"></svg>
  <script>
    const BASE_URL = ${JSON.stringify(tileBaseUrl)};
    let countriesGeo = null;
    let sulawesiGeo = null;
    let tectonicsGeo = null;

    function smoothPathFromScreenPts(pts) {
      if (pts.length < 2) return "";
      let d = "M " + pts[0].x.toFixed(1) + " " + pts[0].y.toFixed(1);
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[Math.max(0, i - 1)];
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const p3 = pts[Math.min(pts.length - 1, i + 2)];
        const c1x = p1.x + (p2.x - p0.x) / 6;
        const c1y = p1.y + (p2.y - p0.y) / 6;
        const c2x = p2.x - (p3.x - p1.x) / 6;
        const c2y = p2.y - (p3.y - p1.y) / 6;
        d += " C " + c1x.toFixed(1) + " " + c1y.toFixed(1) + ", " + c2x.toFixed(1) + " " + c2y.toFixed(1) + ", " + p2.x.toFixed(1) + " " + p2.y.toFixed(1);
      }
      return d;
    }

    function taperedFaultD(pts, peakHalf, tipHalf) {
      if (pts.length < 3) return "";
      const left = [], right = [];
      for (let i = 0; i < pts.length; i++) {
        const u = i / (pts.length - 1);
        const taper = Math.sin(Math.PI * u);
        const hw = tipHalf + (peakHalf - tipHalf) * taper;
        const prev = pts[Math.max(0, i - 1)];
        const next = pts[Math.min(pts.length - 1, i + 1)];
        const dx = next.x - prev.x, dy = next.y - prev.y;
        const len = Math.hypot(dx, dy) || 1;
        const nx = -dy / len, ny = dx / len;
        left.push((pts[i].x + nx * hw).toFixed(1) + "," + (pts[i].y + ny * hw).toFixed(1));
        right.push((pts[i].x - nx * hw).toFixed(1) + "," + (pts[i].y - ny * hw).toFixed(1));
      }
      return "M " + left[0] + " L " + left.slice(1).join(" L ") + " L " + right.reverse().join(" L ") + " Z";
    }

    function projRing(ring, ox = 0, oy = 0) {
      const pts = [];
      for (const ll of ring) {
        const p = map.project(ll);
        pts.push({ x: p.x + ox, y: p.y + oy });
      }
      return pts;
    }

    function ringPath(ring, ox = 0, oy = 0, closed = true) {
      const pts = projRing(ring, ox, oy);
      if (pts.length < 2) return "";
      let d = "M " + pts[0].x.toFixed(1) + " " + pts[0].y.toFixed(1);
      for (let i = 1; i < pts.length; i++) d += " L " + pts[i].x.toFixed(1) + " " + pts[i].y.toFixed(1);
      return closed ? d + " Z" : d;
    }

    function geoFeaturePath(feature, ox = 0, oy = 0) {
      const g = feature.geometry;
      if (!g) return "";
      if (g.type === "Polygon") {
        return g.coordinates.map((r) => ringPath(r, ox, oy, true)).join(" ");
      }
      if (g.type === "MultiPolygon") {
        return g.coordinates.flatMap((poly) => poly.map((r) => ringPath(r, ox, oy, true))).join(" ");
      }
      if (g.type === "LineString") {
        return ringPath(g.coordinates, ox, oy, false);
      }
      if (g.type === "MultiLineString") {
        return g.coordinates.map((l) => ringPath(l, ox, oy, false)).join(" ");
      }
      return "";
    }

    function drawArrowHead(pts, color, alpha, size = 13) {
      if (pts.length < 2) return "";
      const a = pts[pts.length - 2];
      const b = pts[pts.length - 1];
      const ang = Math.atan2(b.y - a.y, b.x - a.x);
      const p1x = b.x - size * Math.cos(ang - 0.45);
      const p1y = b.y - size * Math.sin(ang - 0.45);
      const p2x = b.x - size * Math.cos(ang + 0.45);
      const p2y = b.y - size * Math.sin(ang + 0.45);
      return '<polygon points="' + b.x.toFixed(1) + ',' + b.y.toFixed(1) + ' ' + p1x.toFixed(1) + ',' + p1y.toFixed(1) + ' ' + p2x.toFixed(1) + ',' + p2y.toFixed(1) + '" fill="' + color + '" opacity="' + alpha.toFixed(2) + '"/>';
    }

    function renderVectors(viz) {
      const svg = document.getElementById("vector-stage");
      if (!sulawesiGeo || !tectonicsGeo) { svg.innerHTML = ""; return; }

      const mainland = sulawesiGeo.features.filter((f) => f.properties.feature_type === "mainland_exterior");
      const islands = sulawesiGeo.features.filter((f) => f.properties.feature_type === "island_outline");
      const peninsulaMasks = sulawesiGeo.features.filter((f) => f.properties.feature_type === "peninsula_mask");
      const kSpines = tectonicsGeo.features.filter((f) => f.properties.id && f.properties.id.startsWith("sulawesi_k_"));
      const paluKoro = tectonicsGeo.features.find((f) => f.properties.id === "sesar_palu_koro_trace");

      const parts = [];
      parts.push('<defs>' +
        '<filter id="crimson-glow" x="-20%" y="-20%" width="140%" height="140%">' +
        '  <feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>' +
        '</filter>' +
        '<pattern id="tectonic-hatch" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(38)">' +
        '  <line x1="0" y1="0" x2="0" y2="14" stroke="#F5C542" stroke-width="2.2" stroke-opacity="0.32"/>' +
        '</pattern>' +
      '</defs>');

      const drawMainlandBase = (fillHex, fillAlpha, strokeHex, strokeW, strokeAlpha, dashProg = 1) => {
        for (const f of mainland) {
          const d = geoFeaturePath(f);
          if (fillAlpha > 0.01) {
            parts.push('<path d="' + d + '" fill="' + fillHex + '" fill-opacity="' + fillAlpha.toFixed(3) + '" stroke="none"/>');
          }
          if (strokeAlpha > 0.01) {
            const lenEst = 3600;
            const dash = dashProg < 0.999 ? ' stroke-dasharray="' + (lenEst * dashProg).toFixed(0) + ' ' + lenEst + '"' : "";
            parts.push('<path d="' + d + '" fill="none" stroke="' + strokeHex + '" stroke-width="' + strokeW + '" stroke-opacity="' + strokeAlpha.toFixed(3) + '" stroke-linejoin="round" stroke-linecap="round"' + dash + '/>');
          }
        }
        for (const f of islands) {
          const d = geoFeaturePath(f);
          if (strokeAlpha > 0.01 && dashProg > 0.35) {
            parts.push('<path d="' + d + '" fill="none" stroke="' + strokeHex + '" stroke-width="1.6" stroke-opacity="' + (strokeAlpha * 0.65).toFixed(3) + '"/>');
          }
        }
      };

      if (viz.mode === "hook") {
        drawMainlandBase("#C2412D", viz.landTintAlpha, "#C2412D", 3.6, Math.min(1, viz.outlineProg * 1.4), viz.outlineProg);
        if (viz.kProg > 0.01) {
          for (const kf of kSpines) {
            const pts = projRing(kf.geometry.coordinates);
            const pathD = smoothPathFromScreenPts(pts);
            const subLen = 850 * viz.kProg;
            parts.push('<path d="' + pathD + '" fill="none" stroke="#F5C542" stroke-width="11" stroke-opacity="' + (viz.kOpacity * 0.25).toFixed(2) + '" stroke-linecap="round" stroke-dasharray="' + subLen.toFixed(0) + ' 900"/>');
            parts.push('<path d="' + pathD + '" fill="none" stroke="#F5C542" stroke-width="4.4" stroke-opacity="' + viz.kOpacity.toFixed(2) + '" stroke-linecap="round" stroke-dasharray="' + subLen.toFixed(0) + ' 900"/>');
          }
        }
      } else if (viz.mode === "peninsulas") {
        // Unified Sulawesi crimson outline first, then smooth sequential cobalt-azure peninsula washes clipped by mainland exterior
        const clipPaths = mainland.map((f) => '<path d="' + geoFeaturePath(f) + '"/>').join("");
        parts.push('<clipPath id="sulawesi-ext-clip">' + clipPaths + '</clipPath>');
        drawMainlandBase("#C2412D", 0.14, "#F4F1EA", 2.2, 0.55, 1);
        parts.push('<g clip-path="url(#sulawesi-ext-clip)">');
        for (const pState of viz.penStates) {
          if (pState.alpha <= 0.01) continue;
          const matched = peninsulaMasks.filter((m) => m.properties.peninsula === pState.key);
          for (const m of matched) {
            const d = geoFeaturePath(m);
            parts.push('<path d="' + d + '" fill="' + pState.color + '" fill-opacity="' + (0.48 * pState.alpha).toFixed(3) + '" stroke="none"/>');
          }
        }
        parts.push('</g>');
        drawMainlandBase("#C2412D", 0, "#F4F1EA", 3.0, 0.85, 1);
      } else if (viz.mode === "gulfs") {
        drawMainlandBase("#C2412D", 0.16, "#F4F1EA", 2.4, 0.72, 1);
        // Curved Teluk Tomini open-water textPath + Teluk Tolo + Teluk Bone cleanly positioned in ocean
        const tominiCurvePts = projRing([[120.42, -0.58], [121.15, -0.30], [122.05, -0.24], [123.02, -0.35]]);
        const tominiD = smoothPathFromScreenPts(tominiCurvePts);
        if (viz.tominiAlpha > 0.01) {
          parts.push('<path id="bay-tomini-path" d="' + tominiD + '" fill="none" stroke="none"/>');
          parts.push('<path d="' + tominiD + '" fill="none" stroke="#7CE0F9" stroke-width="2" stroke-opacity="' + (viz.tominiAlpha * 0.45).toFixed(2) + '" stroke-dasharray="6 8"/>');
          parts.push('<text font-family="Space Grotesk" font-size="23" font-weight="700" letter-spacing="0.16em" fill="#7CE0F9" opacity="' + viz.tominiAlpha.toFixed(2) + '"><textPath href="#bay-tomini-path" startOffset="50%" text-anchor="middle">TELUK TOMINI</textPath></text>');
        }
        if (viz.toloAlpha > 0.01) {
          const p = map.project([122.72, -2.28]);
          parts.push('<text x="' + p.x.toFixed(1) + '" y="' + p.y.toFixed(1) + '" font-family="Space Grotesk" font-size="21" font-weight="700" letter-spacing="0.14em" fill="#7CE0F9" text-anchor="middle" opacity="' + viz.toloAlpha.toFixed(2) + '">TELUK TOLO</text>');
        }
        if (viz.boneAlpha > 0.01) {
          const p = map.project([120.72, -4.15]);
          parts.push('<text x="' + p.x.toFixed(1) + '" y="' + p.y.toFixed(1) + '" font-family="Space Grotesk" font-size="21" font-weight="700" letter-spacing="0.14em" fill="#7CE0F9" text-anchor="middle" opacity="' + viz.boneAlpha.toFixed(2) + '">TELUK BONE</text>');
        }
      } else if (viz.mode === "plates") {
        drawMainlandBase("#C2412D", 0.24, "#F4F1EA", 2.4, 0.8, 1);
        if (viz.collisionAlpha > 0.02) {
          const hub = map.project([121.1, -1.6]);
          parts.push('<circle cx="' + hub.x.toFixed(1) + '" cy="' + hub.y.toFixed(1) + '" r="' + (125 + 22 * Math.sin(viz.pulsePhase * Math.PI * 2)).toFixed(1) + '" fill="url(#tectonic-hatch)" stroke="#F5C542" stroke-width="1.8" stroke-dasharray="6 6" opacity="' + (0.75 * viz.collisionAlpha).toFixed(2) + '"/>');
        }
        const drawVector = (coords, prog, color, label, labelAnchorLL, textOffset = [0, -16]) => {
          if (prog <= 0.02) return;
          const allPts = projRing(coords);
          const count = Math.max(2, Math.round(allPts.length * prog));
          const sub = allPts.slice(0, count);
          const d = smoothPathFromScreenPts(sub);
          parts.push('<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="5" stroke-linecap="round" stroke-dasharray="10 7" opacity="0.9"/>');
          parts.push(drawArrowHead(sub, color, 0.95, 16));
          const lp = map.project(labelAnchorLL);
          parts.push('<text x="' + (lp.x + textOffset[0]).toFixed(1) + '" y="' + (lp.y + textOffset[1]).toFixed(1) + '" font-family="Space Grotesk" font-size="22" font-weight="700" letter-spacing="0.1em" fill="' + color + '" text-anchor="middle" opacity="' + Math.min(1, prog * 1.4).toFixed(2) + '">' + label + '</text>');
        };
        drawVector([[113.5, 5.2], [116.2, 2.8], [118.4, 0.8], [120.2, -0.5]], viz.eurasiaProg, "#F4F1EA", "EURASIA", [115.6, 4.4], [0, -24]);
        drawVector([[123.5, -10.5], [122.4, -7.8], [121.6, -5.2], [121.2, -3.2]], viz.australiaProg, "#F5C542", "INDO-AUSTRALIA", [124.4, -9.9], [0, 28]);
        drawVector([[134.0, 2.8], [129.8, 1.4], [126.5, 0.2], [123.8, -0.9]], viz.pacificProg, "#7CE0F9", "PASIFIK", [130.6, 2.4], [0, -20]);
      } else if (viz.mode === "puzzle") {
        // Unified coastline plus staggered tectonic suture highlights clipped cleanly inside exterior boundary
        const clipPaths = mainland.map((f) => '<path d="' + geoFeaturePath(f) + '"/>').join("");
        parts.push('<clipPath id="puzzle-ext-clip">' + clipPaths + '</clipPath>');
        drawMainlandBase("#C2412D", 0.2, "#F5C542", 2.8, viz.fractureGlow, 1);
        const frags = [
          { group: "northern_peninsula", dx: 24 * (1 - viz.settle), dy: -32 * (1 - viz.settle), fill: "#7CE0F9" },
          { group: "eastern_peninsula", dx: 36 * (1 - viz.settle), dy: 6 * (1 - viz.settle), fill: "#F5C542" },
          { group: "southeastern_peninsula", dx: 20 * (1 - viz.settle), dy: 28 * (1 - viz.settle), fill: "#2E6A99" },
          { group: "southern_peninsula", dx: -26 * (1 - viz.settle), dy: 24 * (1 - viz.settle), fill: "#C2412D" },
        ];
        parts.push('<g clip-path="url(#puzzle-ext-clip)">');
        for (const fg of frags) {
          const matched = peninsulaMasks.filter((m) => m.properties.peninsula === fg.group);
          for (const m of matched) {
            const d = geoFeaturePath(m, fg.dx + viz.shakeX, fg.dy + viz.shakeY);
            parts.push('<path d="' + d + '" fill="' + fg.fill + '" fill-opacity="0.34" stroke="none"/>');
          }
        }
        parts.push('</g>');
        for (const kf of kSpines) {
          const pts = projRing(kf.geometry.coordinates, viz.shakeX, viz.shakeY);
          parts.push('<path d="' + smoothPathFromScreenPts(pts) + '" fill="none" stroke="#F5C542" stroke-width="3.2" stroke-dasharray="9 6" stroke-opacity="' + viz.fractureGlow.toFixed(2) + '"/>');
        }
        drawMainlandBase("#C2412D", 0, "#F4F1EA", 2.8, 0.88, 1);
      } else if (viz.mode === "palukoro") {
        drawMainlandBase("#C2412D", 0.16, "#F4F1EA", 2.2, 0.65, 1);
        if (paluKoro && viz.faultProg > 0.02) {
          const allPts = projRing(paluKoro.geometry.coordinates);
          const count = Math.max(3, Math.round(allPts.length * viz.faultProg));
          const sub = allPts.slice(0, count);
          const spinePoly = taperedFaultD(sub, 6.2, 1.0);
          parts.push('<path d="' + spinePoly + '" fill="#F5C542" fill-opacity="0.28"/>');
          parts.push('<path d="' + smoothPathFromScreenPts(sub) + '" fill="none" stroke="#F5C542" stroke-width="4.2" stroke-linecap="round"/>');
          // Palu hub marker + clean 45-degree elbow into Makassar Strait open water
          const hub = map.project([119.86, -0.89]);
          const elbow = map.project([118.75, -0.45]);
          const endX = Math.max(96, elbow.x - 190);
          if (viz.labelAlpha > 0.01) {
            parts.push('<circle cx="' + hub.x.toFixed(1) + '" cy="' + hub.y.toFixed(1) + '" r="8" fill="#F5C542" stroke="#03161F" stroke-width="3" opacity="' + viz.labelAlpha.toFixed(2) + '"/>');
            parts.push('<polyline points="' + hub.x.toFixed(1) + ',' + hub.y.toFixed(1) + ' ' + elbow.x.toFixed(1) + ',' + elbow.y.toFixed(1) + ' ' + endX.toFixed(1) + ',' + elbow.y.toFixed(1) + '" fill="none" stroke="#F5C542" stroke-width="2.4" opacity="' + viz.labelAlpha.toFixed(2) + '"/>');
            const boxX = Math.max(54, endX - 246);
            parts.push('<rect x="' + boxX.toFixed(1) + '" y="' + (elbow.y - 44).toFixed(1) + '" width="256" height="44" rx="6" fill="#03161F" fill-opacity="0.88" stroke="#F5C542" stroke-width="2" opacity="' + viz.labelAlpha.toFixed(2) + '"/>');
            parts.push('<text x="' + (boxX + 128).toFixed(1) + '" y="' + (elbow.y - 16).toFixed(1) + '" font-family="Space Grotesk" font-size="20" font-weight="700" letter-spacing="0.06em" fill="#F5C542" text-anchor="middle" opacity="' + viz.labelAlpha.toFixed(2) + '">SESAR PALU-KORO</text>');
          }
        }
      } else if (viz.mode === "archipelago") {
        if (countriesGeo) {
          const idn = countriesGeo.features.filter((f) => (f.properties.ADM0_A3 || f.properties.ISO_A3) === "IDN");
          for (const f of idn) {
            parts.push('<path d="' + geoFeaturePath(f) + '" fill="#2E6A99" fill-opacity="0.16" stroke="#7CE0F9" stroke-width="1.4" stroke-opacity="0.45"/>');
          }
        }
        drawMainlandBase("#C2412D", 0.34, "#F5C542", 3.4, 0.9, 1);
      } else if (viz.mode === "relief") {
        if (viz.faultOverlayAlpha > 0.02 && paluKoro) {
          const pts = projRing(paluKoro.geometry.coordinates);
          parts.push('<path d="' + smoothPathFromScreenPts(pts) + '" fill="none" stroke="#F5C542" stroke-width="3.2" stroke-dasharray="10 8" stroke-opacity="' + viz.faultOverlayAlpha.toFixed(2) + '"/>');
        }
        if (viz.scaleCueAlpha > 0.01) {
          parts.push('<g opacity="' + viz.scaleCueAlpha.toFixed(2) + '">' +
            '<line x1="76" y1="324" x2="216" y2="324" stroke="#F4F1EA" stroke-width="2.5"/>' +
            '<line x1="76" y1="316" x2="76" y2="332" stroke="#F4F1EA" stroke-width="2.5"/>' +
            '<line x1="216" y1="316" x2="216" y2="332" stroke="#F4F1EA" stroke-width="2.5"/>' +
            '<text x="76" y="308" font-family="Space Grotesk" font-size="18" font-weight="600" letter-spacing="0.08em" fill="#F4F1EA">' +
              (viz.phase === "karst" ? "KARST MAROS-PANGKEP" : "ZONA SESAR PALU") +
            '</text>' +
          '</g>');
        }
      } else if (viz.mode === "outro") {
        drawMainlandBase("#C2412D", 0.14 * viz.dipOut, "#F4F1EA", 2.4, viz.outlineAlpha, 1);
      }

      svg.innerHTML = parts.join("");
    }

    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        projection: { type: "globe" },
        sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 4.5, 0.82, 6.2, 0] },
        sources: {
          sat: { type: "raster", tiles: [BASE_URL + "/tiles/{z}/{x}/{y}.jpg"], tileSize: 256, maxzoom: 11 }
        },
        layers: [{ id: "sat", type: "raster", source: "sat" }]
      },
      center: [125, 2.8],
      zoom: 2.15,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      preserveDrawingBuffer: true,
      canvasContextAttributes: { alpha: true, preserveDrawingBuffer: true }
    });

    window.__ready = Promise.all([
      new Promise((res) => { if (map.loaded()) res(); else map.on("load", res); }),
      fetch(BASE_URL + "/vector/countries_curated.geojson").then((r) => r.json()).then((d) => { countriesGeo = d; }),
      fetch(BASE_URL + "/vector/sulawesi_regions.geojson").then((r) => r.json()).then((d) => { sulawesiGeo = d; }),
      fetch(BASE_URL + "/vector/sulawesi_tectonics.geojson").then((r) => r.json()).then((d) => { tectonicsGeo = d; }),
      document.fonts.ready,
    ]);

    window.__applyState = async function(cam, viz) {
      document.getElementById("stars").style.display = cam.projection === "globe" ? "block" : "none";
      map.setProjection({ type: cam.projection });
      map.jumpTo({ center: cam.center, zoom: cam.zoom, pitch: cam.pitch, bearing: cam.bearing });
      await new Promise((res) => {
        const t0 = performance.now();
        (function poll() {
          if (map.loaded() && map.areTilesLoaded()) {
            map.triggerRepaint();
            renderVectors(viz);
            requestAnimationFrame(() => requestAnimationFrame(res));
            return;
          }
          if (performance.now() - t0 > 1500) {
            renderVectors(viz);
            res();
            return;
          }
          setTimeout(poll, 20);
        })();
      });
    };
  </script>
</body>
</html>`;
}

export async function renderSulawesiShots({ outShotsDir, limitShots = null } = {}) {
  const shotsDir = outShotsDir || join(REPO_ROOT, "studies/geoverum/pilot-sulawesi/assets/shots");
  const seqRoot = join(shotsDir, "_frames");
  mkdirSync(shotsDir, { recursive: true });
  mkdirSync(seqRoot, { recursive: true });

  const specs = limitShots
    ? SULAWESI_SHOT_SPECS.filter((s) => limitShots.includes(s.id))
    : SULAWESI_SHOT_SPECS;

  const pending = specs.filter(
    (s) => process.env.REBAKE === "1" || !existsSync(join(shotsDir, `${s.id}.mp4`))
  );

  if (pending.length === 0) {
    console.log(`[sulawesi-shots] Reusing ${specs.length} cached MP4 shots in ${shotsDir}`);
    return specs.map((s) => join(shotsDir, `${s.id}.mp4`));
  }

  const srv = await startTileServer(0, "127.0.0.1");
  const port = srv.address().port;
  const tileBaseUrl = `http://127.0.0.1:${port}`;
  const chromeArgs =
    process.platform === "darwin"
      ? ["--no-sandbox", "--hide-scrollbars", "--use-gl=angle"]
      : ["--no-sandbox", "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader"];
  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: "new",
    args: chromeArgs,
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
    await page.setContent(buildRenderPageHtml(tileBaseUrl), { waitUntil: "load" });
    await page.evaluate(() => window.__ready);

    const leakPngBuf = await buildWarmLightLeakOverlayBuffer();

    for (const s of pending) {
      const fDir = join(seqRoot, s.id);
      mkdirSync(fDir, { recursive: true });
      const lastJpg = join(fDir, `f${String(s.frames - 1).padStart(4, "0")}.jpg`);
      const hasAllFrames =
        process.env.REBAKE !== "1" &&
        existsSync(lastJpg) &&
        Array.from({ length: s.frames }, (_, k) => join(fDir, `f${String(k).padStart(4, "0")}.jpg`)).every(
          (p) => existsSync(p) && statSync(p).size > 1024
        );

      if (hasAllFrames) {
        console.log(`[sulawesi-shots] Reusing frames for ${s.id}`);
      } else {
        console.log(`[sulawesi-shots] Rendering ${s.id} (${s.frames} frames)...`);
        for (let i = 0; i < s.frames; i++) {
          const outFrame = join(fDir, `f${String(i).padStart(4, "0")}.jpg`);
          if (process.env.REBAKE !== "1" && existsSync(outFrame) && statSync(outFrame).size > 1024) {
            continue;
          }
          const st = computeShotFrameState(s.id, i, s.frames);
          await page.evaluate((cam, viz) => window.__applyState(cam, viz), st.cam, st.viz);
          await page.screenshot({
            path: outFrame,
            type: "jpeg",
            quality: 92,
            clip: { x: 0, y: 0, width: W, height: H },
          });
          if ((i + 1) % 30 === 0 || i + 1 === s.frames) {
            console.log(`  [${s.id}] ${i + 1}/${s.frames}`);
          }
        }
      }

      // Pre-render optical transitions directly into boundary frames (zero runtime CSS blur)
      if (s.id === "shot_01_hook_dive") {
        for (let k = 0; k < 4; k++) {
          const idx = s.frames - 4 + k;
          const fn = join(fDir, `f${String(idx).padStart(4, "0")}.jpg`);
          const bak = join(fDir, `.raw_${idx}.jpg`);
          if (!existsSync(bak)) copyFileSync(fn, bak);
          await preRenderRadialZoomBlur(bak, fn, (k + 1) / 4);
        }
      } else if (s.id === "shot_02_peninsulas") {
        for (let k = 0; k < 3; k++) {
          const fn = join(fDir, `f${String(k).padStart(4, "0")}.jpg`);
          const bak = join(fDir, `.raw_${k}.jpg`);
          if (!existsSync(bak)) copyFileSync(fn, bak);
          await preRenderRadialZoomBlur(bak, fn, (3 - k) / 4.5);
        }
      } else if (s.id === "shot_04_three_plates") {
        for (let k = 0; k < 4; k++) {
          const idx = s.frames - 4 + k;
          const fn = join(fDir, `f${String(idx).padStart(4, "0")}.jpg`);
          const bak = join(fDir, `.raw_${idx}.jpg`);
          if (!existsSync(bak)) copyFileSync(fn, bak);
          await preRenderRadialZoomBlur(bak, fn, (k + 1) / 5);
        }
      } else if (s.id === "shot_07_archipelago") {
        const opacities = [0.22, 0.45, 0.72, 0.94];
        for (let k = 0; k < 4; k++) {
          const idx = s.frames - 4 + k;
          const fn = join(fDir, `f${String(idx).padStart(4, "0")}.jpg`);
          const bak = join(fDir, `.raw_${idx}.jpg`);
          if (!existsSync(bak)) copyFileSync(fn, bak);
          await applyLightLeakBlend(bak, fn, leakPngBuf, opacities[k]);
        }
      } else if (s.id === "shot_08_relief_climax") {
        // Crossfade Palu-Koro aerial into Maros-Pangkep karst across frames 122..144 before light leak bloom
        const bakCache = {};
        for (let idx = 122; idx <= 144; idx++) {
          const fn = join(fDir, `f${String(idx).padStart(4, "0")}.jpg`);
          const bak = join(fDir, `.raw_${idx}.jpg`);
          if (!existsSync(bak)) copyFileSync(fn, bak);
          bakCache[idx] = bak;
        }
        const paluHold = bakCache[122];
        for (let idx = 132; idx <= 144; idx++) {
          const alpha = (idx - 132) / 12;
          await applyCrossfadeBlend(paluHold, bakCache[idx], join(fDir, `f${String(idx).padStart(4, "0")}.jpg`), alpha);
        }
        // Decay solar amber light leak on opening frames 0..6
        const decayOpacities = [0.96, 0.78, 0.56, 0.36, 0.2, 0.08, 0.02];
        for (let k = 0; k < decayOpacities.length; k++) {
          const fn = join(fDir, `f${String(k).padStart(4, "0")}.jpg`);
          const bak = join(fDir, `.raw_${k}.jpg`);
          if (!existsSync(bak)) copyFileSync(fn, bak);
          await applyLightLeakBlend(bak, fn, leakPngBuf, decayOpacities[k]);
        }
      }

      const outMp4 = join(shotsDir, `${s.id}.mp4`);
      encodeSeqToMp4(join(fDir, "f%04d.jpg"), outMp4);
      console.log(`[sulawesi-shots] Encoded ${outMp4}`);
    }
  } finally {
    await browser.close();
    await new Promise((r) => srv.close(r));
  }

  // Prune raw JPG sequences once all requested MP4s exist
  if (!limitShots) {
    rmSync(seqRoot, { recursive: true, force: true });
  }
  return specs.map((s) => join(shotsDir, `${s.id}.mp4`));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const only = process.argv.slice(2);
  renderSulawesiShots({ limitShots: only.length ? only : null }).catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
