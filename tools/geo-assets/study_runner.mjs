#!/usr/bin/env node
/**
 * Shared offline rendering, linting, and FFmpeg mastering utilities for
 * standalone brand HyperFrames component studies.
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, resolve, sep } from "node:path";
import { homedir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { lintHyperframesProjectDir } from "../../packages/hf-compiler-ts/dist/lint.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(__dirname, "../..");

const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
export const puppeteer = require("puppeteer-core");
export const sharp = require("sharp");

const MIME_BY_EXT = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ttf": "font/ttf",
  ".woff2": "font/woff2",
  ".mp4": "video/mp4",
};

/** Resolve local Chromium or chrome-headless-shell executable path. */
export function resolveChrome() {
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
        /* ignore unreadable directories */
      }
    }
  }
  for (const candidate of [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ]) {
    if (existsSync(candidate)) return candidate;
  }
  throw new Error("Chrome or chrome-headless-shell binary not found.");
}

/**
 * Start a deterministic loopback HTTP server exposing both the global geo assets
 * (`assets/geo/`) and an optional study directory so all relative `assets/...` URLs
 * resolve locally without external network calls.
 */
function resolveContainedFile(rootDir, relPath) {
  const rootResolved = resolve(rootDir);
  const candidate = resolve(rootResolved, relPath.replace(/^\/+/, ""));
  if (candidate !== rootResolved && !candidate.startsWith(rootResolved + sep)) {
    return null;
  }
  return candidate;
}

export function startStudyAssetServer(studyDir, port = 0, host = "127.0.0.1") {
  const geoRoot = resolve(REPO_ROOT, "assets/geo");
  const resolvedStudyDir = studyDir ? resolve(studyDir) : null;
  const server = createServer((req, res) => {
    let cleanUrl;
    try {
      cleanUrl = decodeURIComponent((req.url || "/").split("?")[0]);
    } catch {
      res.writeHead(400);
      res.end("Bad request");
      return;
    }
    let filePath = null;

    if (cleanUrl === "/" || cleanUrl === "/host.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end("<!doctype html><html><body></body></html>");
      return;
    }

    if (cleanUrl.startsWith("/geo/")) {
      filePath = resolveContainedFile(geoRoot, cleanUrl.slice(5));
    } else if (resolvedStudyDir) {
      filePath = resolveContainedFile(resolvedStudyDir, cleanUrl);
      if (!filePath || !existsSync(filePath) || statSync(filePath).isDirectory()) {
        // Fallback to assets/geo for shared fonts/flags/icons referenced inside study templates
        const rel = cleanUrl.replace(/^\/+/, "");
        if (rel.startsWith("assets/")) {
          const geoCandidate = resolveContainedFile(geoRoot, rel.slice("assets/".length));
          if (geoCandidate && existsSync(geoCandidate) && !statSync(geoCandidate).isDirectory()) {
            filePath = geoCandidate;
          }
        }
      }
    }

    try {
      if (!filePath || !existsSync(filePath) || statSync(filePath).isDirectory()) {
        res.writeHead(404);
        res.end("Not found");
        return;
      }

      const body = readFileSync(filePath);
      const mime = MIME_BY_EXT[extname(filePath).toLowerCase()] || "application/octet-stream";
      res.writeHead(200, {
        "Content-Type": mime,
        "Cache-Control": "no-store",
      });
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end("Not found");
    }
  });

  return new Promise((resolvePromise, rejectPromise) => {
    server.on("error", rejectPromise);
    server.listen(port, host, () => {
      const addr = server.address();
      resolvePromise({
        server,
        baseUrl: `http://${host}:${addr.port}`,
      });
    });
  });
}

/** Validate a HyperFrames study directory and throw on any lint or performance error. */
export async function validateStudyProject(studyDir, label) {
  console.log(`[${label}] Running @hyperframes/lint & performance gate...`);
  const summary = await lintHyperframesProjectDir(studyDir);
  console.log(JSON.stringify(summary, null, 2));
  if (!summary.ok || summary.performanceViolations.length > 0) {
    throw new Error(
      `HyperFrames validation failed (${summary.totalErrors} errors, ${summary.performanceViolations.length} performance violations).`
    );
  }
  return summary;
}

/**
 * Render all frames of a HyperFrames `<template>` composition via headless Chromium
 * seeking its paused GSAP timeline deterministically (`window.__timelines[id].seek(t)`).
 */
export async function renderTemplateFrames({
  browser,
  baseUrl,
  compositionHtmlPath,
  compositionId,
  totalFrames,
  fps = 30,
  framesDir,
  width = 1080,
  height = 1920,
}) {
  mkdirSync(framesDir, { recursive: true });
  const page = await browser.newPage();
  try {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });

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

    const tplRaw = readFileSync(compositionHtmlPath, "utf8");
    const innerMatch = tplRaw.match(/<template>([\s\S]*?)<\/template>/i);
    const tplContent = innerMatch ? innerMatch[1] : tplRaw;

    const hostHtml = `<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <base href="${baseUrl}/">
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>* { margin: 0; padding: 0; box-sizing: border-box; } html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #03161F; }</style>
</head>
<body>
  ${tplContent}
</body>
</html>`;

    await page.setContent(hostHtml, { waitUntil: "networkidle0" });
    await page.evaluate(() => document.fonts.ready);

    const t0 = Date.now();
    for (let i = 0; i < totalFrames; i++) {
      const tSec = i / fps;
      await page.evaluate(
        ([id, t]) => {
          window.__timelines[id].seek(t, false);
        },
        [compositionId, tSec]
      );
      await page.screenshot({
        path: join(framesDir, `f${String(i).padStart(4, "0")}.png`),
        clip: { x: 0, y: 0, width, height },
        optimizeForSpeed: true,
      });
      if (i % 60 === 0 || i === totalFrames - 1) {
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        console.log(`  [${compositionId}] rendered frame ${i + 1}/${totalFrames} (${elapsed}s)`);
      }
    }
  } finally {
    await page.close();
  }
}

/**
 * Render an entire multi-composition HyperFrames project (`index.html` + `compositions/*.html`)
 * in headless Chromium by mounting all `<template>` sub-compositions with scoped styles, IIFE-isolated
 * timeline scripts, and frame-synchronized `[data-start, data-start + data-duration)` gating.
 */
export async function renderProjectFrames({
  browser,
  baseUrl,
  studyDir,
  totalFrames,
  fps = 30,
  framesDir,
  width = 1080,
  height = 1920,
}) {
  mkdirSync(framesDir, { recursive: true });
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 1 });

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

  const indexHtml = readFileSync(join(studyDir, "index.html"), "utf8");
  const hostRe = /<div\b([^>]*\bdata-composition-src=["']([^"']+)["'][^>]*)>/gi;
  const hosts = [];
  for (const m of indexHtml.matchAll(hostRe)) {
    const attrs = m[1];
    const src = m[2];
    const compId = (attrs.match(/\bdata-composition-id=["']([^"']+)["']/i) || [])[1];
    const start = Number((attrs.match(/\bdata-start=["']([^"']+)["']/i) || [])[1] || 0);
    const duration = Number((attrs.match(/\bdata-duration=["']([^"']+)["']/i) || [])[1] || 10);
    const trackIndex = Number((attrs.match(/\bdata-track-index=["']([^"']+)["']/i) || [])[1] || 1);
    if (!compId) continue;

    const raw = readFileSync(join(studyDir, src), "utf8");
    const tplInner = (raw.match(/<template>([\s\S]*?)<\/template>/i) || [])[1] || raw;
    let bodyChunk = tplInner;

    const styles = [];
    bodyChunk = bodyChunk.replace(/<style\b[^>]*>([\s\S]*?)<\/style>/gi, (_, css) => {
      styles.push(css.replace(/#root\b/g, `[data-composition-id="${compId}"]`));
      return "";
    });

    const scripts = [];
    bodyChunk = bodyChunk.replace(/<script\b[^>]*>([\s\S]*?)<\/script>/gi, (_, js) => {
      scripts.push(`(() => {\n${js}\n})();`);
      return "";
    });

    // Replace duplicate #root id inside sub-composition markup so each host stays unique
    bodyChunk = bodyChunk.replace(/\bid=["']root["']/i, `id="host-${compId}"`);

    hosts.push({
      compId,
      start,
      duration,
      trackIndex,
      styles: styles.join("\n"),
      html: bodyChunk,
      scripts: scripts.join("\n"),
    });
  }

  const combinedStyles = hosts.map((h) => h.styles).join("\n");
  const combinedMarkup = hosts
    .map(
      (h) => `
    <div
      class="hf-comp-host"
      data-comp-id="${h.compId}"
      data-start="${h.start}"
      data-duration="${h.duration}"
      style="position: absolute; inset: 0; width: ${width}px; height: ${height}px; overflow: hidden; pointer-events: none; z-index: ${h.trackIndex};"
    >
      ${h.html}
    </div>`
    )
    .join("\n");
  const combinedScripts = hosts.map((h) => h.scripts).join("\n");

  const hostHtml = `<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <base href="${baseUrl}/">
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #03161F; }
    ${combinedStyles}
  </style>
</head>
<body>
  <div id="stage-root" style="position: relative; width: ${width}px; height: ${height}px; overflow: hidden; background: #03161F;">
    ${combinedMarkup}
  </div>
  <script>
    window.__timelines = window.__timelines || {};
    ${combinedScripts}
    window.__seekProject = function(tSec) {
      const nodes = document.querySelectorAll(".hf-comp-host");
      for (const el of nodes) {
        const compId = el.getAttribute("data-comp-id");
        const start = Number(el.getAttribute("data-start") || 0);
        const dur = Number(el.getAttribute("data-duration") || 0);
        if (tSec >= start && tSec < start + dur) {
          el.style.display = "block";
          const tl = window.__timelines[compId];
          if (tl) tl.seek(tSec - start, false);
        } else {
          el.style.display = "none";
        }
      }
    };
  </script>
</body>
</html>`;

  await page.setContent(hostHtml, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);

  const t0 = Date.now();
  for (let i = 0; i < totalFrames; i++) {
    const tSec = i / fps;
    await page.evaluate((t) => window.__seekProject(t), tSec);
    await page.screenshot({
      path: join(framesDir, `f${String(i).padStart(4, "0")}.png`),
      clip: { x: 0, y: 0, width, height },
      optimizeForSpeed: true,
    });
    if (i % 60 === 0 || i === totalFrames - 1) {
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
      console.log(`  [project] rendered frame ${i + 1}/${totalFrames} (${elapsed}s)`);
    }
  }
  await page.close();
}

/** Generate clean unboxed broadcast watermark + attribution composition HTML. */
export function buildBroadcastLayerHtml(durationSec, exitAtSec = null) {
  const exitTween =
    exitAtSec !== null
      ? `\n    tl.to("#watermark-inner", { opacity: 0, duration: 0.45, ease: "power2.in" }, ${exitAtSec.toFixed(2)});\n    tl.to("#credit-inner", { opacity: 0, duration: 0.45, ease: "power2.in" }, ${exitAtSec.toFixed(2)});`
      : "";
  return `<template>
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
      font-variant-numeric: tabular-nums;
    }
    #watermark-clip {
      position: absolute;
      top: 72px;
      left: 108px;
      right: 108px;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }
    #watermark-inner {
      display: flex;
      align-items: center;
      gap: 14px;
      opacity: 0;
    }
    .wm-wordmark {
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      font-size: 32px;
      letter-spacing: 0.12em;
      color: #F4F1EA;
      line-height: 1;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.68);
    }
    #credit-clip {
      position: absolute;
      bottom: 24px;
      left: 84px;
      right: 84px;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }
    #credit-inner {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 13px;
      font-weight: 400;
      color: rgba(244, 241, 234, 0.40);
      letter-spacing: 0.01em;
      text-align: center;
    }
  </style>
  <div id="root" data-composition-id="broadcast-layer" data-width="1080" data-height="1920">
    <div id="watermark-clip" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="1">
      <div id="watermark-inner">
        <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
          <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.2" />
          <ellipse cx="17" cy="17" rx="6" ry="13" stroke="#F4F1EA" stroke-width="1.6" />
          <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.6" />
        </svg>
        <span class="wm-wordmark" data-var-text="brand-name">GEOVERUM</span>
      </div>
    </div>

    <div id="credit-clip" class="clip" data-start="0" data-duration="${durationSec}" data-track-index="2" data-layout-ignore="true">
      <div id="credit-inner" data-layout-ignore="true">
        Imagery: NASA Blue Marble, EOX Sentinel-2 cloudless 2016 (Copernicus) · Vectors: Natural Earth, PB2002, GEM
      </div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#watermark-inner",
      { opacity: 0, scale: 0.96 },
      { opacity: 0.86, scale: 1.0, duration: 0.2, ease: "expo.out" },
      0.1
    );${exitTween}
    window.__timelines = window.__timelines || {};
    window.__timelines["broadcast-layer"] = tl;
  </script>
</template>
`;
}

/** Encode rendered PNG frame sequence to `bt709` CFR MP4 and extract annotated QA sheet. */
export function encodeDeliverableAndSheet({
  framesDir,
  outMp4,
  sheetJpg,
  fps = 30,
  crf = 16,
  selectFrames,
  tileCols = 3,
  tileRows = 2,
  scaleW = 540,
  scaleH = 960,
  cleanupFrames = true,
}) {
  mkdirSync(dirname(outMp4), { recursive: true });
  const ff = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-framerate",
      String(fps),
      "-i",
      join(framesDir, "f%04d.png"),
      "-c:v",
      "libx264",
      "-profile:v",
      "high",
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
      String(crf),
      "-g",
      String(fps * 2),
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ff.status !== 0) {
    throw new Error(`FFmpeg encoding failed with status ${ff.status}`);
  }

  const selectExpr = selectFrames.map((n) => `eq(n\\,${n})`).join("+");
  const ffSheet = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      outMp4,
      "-vf",
      `drawtext=text='f%{n} %{pts\\:hms}':x=20:y=20:fontsize=38:fontcolor=yellow:box=1:boxcolor=black@0.7,select='${selectExpr}',scale=${scaleW}:${scaleH},tile=${tileCols}x${tileRows}`,
      "-fps_mode",
      "passthrough",
      "-frames:v",
      "1",
      "-update",
      "1",
      sheetJpg,
    ],
    { stdio: "inherit" }
  );
  if (ffSheet.status !== 0) {
    throw new Error(`Contact sheet extraction failed with status ${ffSheet.status}`);
  }

  if (cleanupFrames) {
    rmSync(framesDir, { recursive: true, force: true });
  }
}

/** Build a smooth Catmull-Rom cubic Bezier SVG path through projected screen points. */
export function buildSmoothCatmullRomPath(pts) {
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

/** Build a tapered crescent SVG polygon along a polyline of screen coordinates. */
export function buildTaperedFaultPath(pts, peakHalfWidth = 5.4, tipHalfWidth = 0.8) {
  const leftSide = [];
  const rightSide = [];
  for (let i = 0; i < pts.length; i++) {
    const t = pts.length <= 1 ? 0.5 : i / (pts.length - 1);
    const halfWidth = Math.sin(Math.PI * t) * peakHalfWidth + tipHalfWidth;
    const pPrev = pts[Math.max(0, i - 1)];
    const pNext = pts[Math.min(pts.length - 1, i + 1)];
    const dx = pNext.x - pPrev.x;
    const dy = pNext.y - pPrev.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    leftSide.push({ x: pts[i].x + nx * halfWidth, y: pts[i].y + ny * halfWidth });
    rightSide.unshift({ x: pts[i].x - nx * halfWidth, y: pts[i].y - ny * halfWidth });
  }
  const ring = [...leftSide, ...rightSide];
  return (
    ring
      .map((p, i) => (i === 0 ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1))
      .join(" ") + "Z"
  );
}
