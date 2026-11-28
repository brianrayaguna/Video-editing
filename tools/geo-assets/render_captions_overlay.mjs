#!/usr/bin/env node
/**
 * High-speed Chromium HTML/CSS transparent caption strip renderer for FFmpeg overlay.
 *
 * Renders one transparent PNG per unique subtitle cue (plus optional alpha-ramped fade-in
 * frames via `sharp`) into a compact `width x bandHeight` strip positioned at the exact
 * `MarginV` anchor, and writes an FFmpeg `ffconcat` timeline for single-pass `overlay`
 * compositing with subpixel variable-font rendering and multi-layer Gaussian drop shadows.
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
import { dirname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
import sharp from "sharp";
import { getChromeArgs } from "./fast_capture.mjs";
import { isMainModule } from "./entry_point.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");

const FONTS_DIR = join(REPO_ROOT, "assets/geo/fonts");

function isExecutable(p) {
  try {
    accessSync(p, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

export function resolveChrome() {
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

function parseAssTime(raw) {
  const m = /^(\d+):(\d{2}):(\d{2})\.(\d{2,3})$/.exec(String(raw || "").trim());
  if (!m) return null;
  const frac = m[4].length === 3 ? Number(m[4]) / 1000 : Number(m[4]) / 100;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + frac;
}

function assColorToHex(assColor, fallback = "#F7F9FB") {
  const m = /^&H([0-9A-Fa-f]{2})?([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})&?$/.exec(
    String(assColor || "").trim()
  );
  if (!m) return fallback;
  const bb = m[2].toUpperCase();
  const gg = m[3].toUpperCase();
  const rr = m[4].toUpperCase();
  return `#${rr}${gg}${bb}`;
}

/**
 * Parse an ASS subtitle file into style metadata and sorted `{ start_s, end_s, text }` cues.
 */
export function parseAssCaptions(assText) {
  const style = {
    fontFamily: "Inter",
    fontSize: null,
    marginV: null,
    marginX: null,
    colorHex: "#F7F9FB",
    fadeInMs: 110,
  };
  const cues = [];
  for (const rawLine of String(assText || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line.startsWith("Style:")) {
      const parts = line.slice(6).split(",").map((s) => s.trim());
      if (parts.length >= 22 && (parts[0] === "Default" || parts[0] === "CaptionLower")) {
        if (parts[1]) style.fontFamily = parts[1];
        const fs = Number(parts[2]);
        if (Number.isFinite(fs) && fs > 0) style.fontSize = fs;
        if (parts[3]) style.colorHex = assColorToHex(parts[3], style.colorHex);
        const ml = Number(parts[19]);
        if (Number.isFinite(ml) && ml >= 0) style.marginX = ml;
        const mv = Number(parts[21]);
        if (Number.isFinite(mv) && mv >= 0) style.marginV = mv;
      }
      continue;
    }
    if (!line.startsWith("Dialogue:")) continue;
    const parts = line.split(",");
    if (parts.length < 10) continue;
    const styleName = parts[3].trim();
    if (styleName === "Watermark" || styleName === "SourceCredit") continue;
    const start_s = parseAssTime(parts[1]);
    const end_s = parseAssTime(parts[2]);
    if (start_s === null || end_s === null || end_s <= start_s) continue;
    const rawPayload = parts.slice(9).join(",");
    const fadMatch = /\\fad\((\d+)\s*,\s*(\d+)\)/.exec(rawPayload);
    if (fadMatch) {
      style.fadeInMs = Math.max(0, Math.min(200, Number(fadMatch[1])));
    }
    const text = rawPayload
      .replace(/\{[^}]*\}/g, "")
      .replace(/\\N/g, "\n")
      .replace(/\\n/g, "\n")
      .replace(/\\\u2060/g, "\\")
      .trim();
    if (!text) continue;
    cues.push({ start_s, end_s, text });
  }
  cues.sort((a, b) => a.start_s - b.start_s);
  return { style, cues };
}

/**
 * Parse a JSON caption payload (`segments` or array of `{start/start_s, end/end_s, text}`).
 */
export function parseJsonCaptions(rawObj) {
  const arr = Array.isArray(rawObj) ? rawObj : rawObj?.segments || rawObj?.cues || [];
  const cues = [];
  for (const item of arr) {
    const start_s = Number(item.start_s ?? item.start ?? 0);
    const end_s = Number(item.end_s ?? item.end ?? 0);
    const text = String(item.text || "").trim();
    if (!text || !Number.isFinite(start_s) || !Number.isFinite(end_s) || end_s <= start_s) {
      continue;
    }
    cues.push({ start_s, end_s, text });
  }
  cues.sort((a, b) => a.start_s - b.start_s);
  return {
    style: {
      fontFamily: "Inter",
      fontSize: null,
      marginV: null,
      marginX: null,
      colorHex: "#F7F9FB",
      fadeInMs: 110,
    },
    cues,
  };
}

/**
 * Build a drift-free FFmpeg `ffconcat` segment list covering `[0, totalDurationS]`.
 *
 * Each entry has `{ file, duration_s }`. When `fadeInMs >= 60`, each cue opens with two
 * 1-frame alpha ramp entries (`fade1`, `fade2`) before holding on `main`.
 */
export function buildConcatTimeline(cues, totalDurationS, fps = 30, fadeInMs = 110) {
  const frameDur = 1 / Math.max(1, Number(fps) || 30);
  const useFade = Number(fadeInMs) >= 60;
  const segments = [];
  let cursor = 0;

  for (let i = 0; i < cues.length; i++) {
    const cue = cues[i];
    const start = Math.max(cursor, cue.start_s);
    const nextStart = i + 1 < cues.length ? cues[i + 1].start_s : totalDurationS;
    const end = Math.min(totalDurationS, Math.max(start, Math.min(cue.end_s, nextStart)));
    if (end <= start + 0.004) continue;

    if (start - cursor > 0.002) {
      segments.push({ file: "blank.png", duration_s: start - cursor });
      cursor = start;
    }

    const dur = end - cursor;
    const prefix = `cue_${String(i).padStart(4, "0")}`;
    if (useFade && dur >= frameDur * 3.5) {
      segments.push({ file: `${prefix}_f1.png`, duration_s: frameDur });
      segments.push({ file: `${prefix}_f2.png`, duration_s: frameDur });
      segments.push({ file: `${prefix}.png`, duration_s: dur - frameDur * 2 });
    } else {
      segments.push({ file: `${prefix}.png`, duration_s: dur });
    }
    cursor = end;
  }

  if (totalDurationS - cursor > 0.002 || segments.length === 0) {
    segments.push({
      file: "blank.png",
      duration_s: Math.max(frameDur, totalDurationS - cursor),
    });
  }
  return segments;
}

function resolveFontDataUri(family) {
  const norm = String(family || "Inter").toLowerCase().replace(/[^a-z0-9]/g, "");
  const candidates = [
    norm.includes("montserrat") ? "Montserrat-Variable.ttf" : null,
    norm.includes("montserrat") ? "Montserrat-Bold.ttf" : null,
    norm.includes("rubik") ? "Rubik-Variable.ttf" : null,
    norm.includes("rubik") ? "Rubik-Bold.ttf" : null,
    norm.includes("outfit") ? "Outfit-Variable.ttf" : null,
    norm.includes("outfit") ? "Outfit-Bold.ttf" : null,
    "Inter-Variable.ttf",
    "Inter-Bold.ttf",
  ].filter(Boolean);

  const rules = [];
  const loaded = new Set();
  for (const fn of candidates) {
    const fp = join(FONTS_DIR, fn);
    if (!existsSync(fp) || loaded.has(fn)) continue;
    loaded.add(fn);
    const b64 = readFileSync(fp).toString("base64");
    const isVar = /variable/i.test(fn);
    const fam = fn.startsWith("Montserrat")
      ? "Montserrat"
      : fn.startsWith("Rubik")
        ? "Rubik"
        : fn.startsWith("Outfit")
          ? "Outfit"
          : "Inter";
    rules.push(
      `@font-face { font-family: "${fam}"; src: url("data:font/ttf;base64,${b64}") format("truetype"); font-weight: ${isVar ? "100 900" : "700"}; font-style: normal; font-display: block; }`
    );
  }
  return rules.join("\n");
}

async function scalePngAlpha(pngBuf, alphaScale) {
  const { data, info } = await sharp(pngBuf)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const out = Buffer.from(data);
  for (let i = 3; i < out.length; i += 4) {
    out[i] = Math.round(out[i] * alphaScale);
  }
  return sharp(out, {
    raw: { width: info.width, height: info.height, channels: 4 },
  })
    .png({ compressionLevel: 4 })
    .toBuffer();
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith("--")) continue;
    const name = k.slice(2);
    const val = i + 1 < argv.length && !argv[i + 1].startsWith("--") ? argv[++i] : true;
    args[name] = val;
  }
  return args;
}

export async function renderCaptionsOverlay({
  captionsPath,
  outDir,
  width = 1080,
  height = 1920,
  fps = 30,
  durationS = null,
  fontSizeOverride = null,
  marginVOverride = null,
  fontFamilyOverride = null,
  fadeInMsOverride = null,
}) {
  const absCap = resolve(captionsPath);
  const absOut = resolve(outDir);
  mkdirSync(absOut, { recursive: true });

  const rawText = readFileSync(absCap, "utf8");
  const parsed = absCap.toLowerCase().endsWith(".json")
    ? parseJsonCaptions(JSON.parse(rawText))
    : parseAssCaptions(rawText);

  const isPortrait = height > width;
  const scale = Math.min(width, height) / 1080.0;
  const fontFamily = fontFamilyOverride || parsed.style.fontFamily || "Inter";
  const fontSize = Math.round(
    Number(fontSizeOverride) ||
      parsed.style.fontSize ||
      (isPortrait ? 46 * scale : 42 * scale)
  );
  const marginV = Math.round(
    Number(marginVOverride) ||
      parsed.style.marginV ||
      (isPortrait ? 525 * (height / 1920.0) : height * 0.1)
  );
  const marginX = Math.round(
    parsed.style.marginX ?? width * (isPortrait ? 0.078 : 0.125)
  );
  const fadeInMs =
    fadeInMsOverride !== null && fadeInMsOverride !== undefined
      ? Number(fadeInMsOverride)
      : parsed.style.fadeInMs;
  const colorHex = parsed.style.colorHex || "#F5F7FA";

  const bandHeight = Math.min(height, Math.max(240, Math.round(fontSize * 4.6)));
  const padBottom = Math.round(fontSize * 0.95);
  const yTop = Math.max(0, Math.min(height - bandHeight, height - marginV - (bandHeight - padBottom)));

  const cues = parsed.cues;
  const inferredDur = cues.length > 0 ? Math.max(...cues.map((c) => c.end_s)) + 0.25 : 1.0;
  const totalDurationS = Math.max(0.5, Number(durationS) || inferredDur);

  // Write transparent blank strip first.
  const blankPng = await sharp({
    create: { width, height: bandHeight, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } },
  })
    .png({ compressionLevel: 4 })
    .toBuffer();
  writeFileSync(join(absOut, "blank.png"), blankPng);

  if (cues.length > 0) {
    const fontCss = resolveFontDataUri(fontFamily);
    const chromePath = resolveChrome();
    const browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: true,
      args: getChromeArgs(width, bandHeight),
      defaultViewport: { width, height: bandHeight, deviceScaleFactor: 1 },
    });

    try {
      const page = await browser.newPage();
      const cdp = await page.createCDPSession();
      await cdp.send("Emulation.setDefaultBackgroundColorOverride", {
        color: { r: 0, g: 0, b: 0, a: 0 },
      });

      const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
${fontCss}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  width: ${width}px;
  height: ${bandHeight}px;
  background: transparent;
  overflow: hidden;
  font-synthesis: none;
  font-optical-sizing: auto;
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
}
#wrap {
  position: absolute;
  left: ${marginX}px;
  right: ${marginX}px;
  bottom: ${padBottom}px;
  display: flex;
  justify-content: center;
  align-items: flex-end;
  text-align: center;
}
#cap {
  font-family: "${fontFamily}", "Inter", "Montserrat", sans-serif;
  font-weight: 700;
  font-size: ${fontSize}px;
  line-height: 1.22;
  letter-spacing: -0.012em;
  color: ${colorHex};
  text-wrap: balance;
  white-space: pre-wrap;
  text-shadow:
    0 1px 2px rgba(0, 0, 0, 0.94),
    0 2px 6px rgba(0, 0, 0, 0.82),
    0 6px 18px rgba(0, 0, 0, 0.56),
    0 0 24px rgba(0, 0, 0, 0.32);
}
</style>
</head>
<body>
  <div id="wrap"><div id="cap"></div></div>
</body>
</html>`;

      await page.setContent(html, { waitUntil: "load" });
      await page.evaluate(async () => {
        await document.fonts.ready;
      });

      const useFade = fadeInMs >= 60;
      const frameDur = 1 / Math.max(1, fps);
      const fadeTasks = [];

      for (let i = 0; i < cues.length; i++) {
        const cue = cues[i];
        await page.evaluate((txt) => {
          document.getElementById("cap").textContent = txt;
        }, cue.text);
        const { data } = await cdp.send("Page.captureScreenshot", {
          format: "png",
          fromSurface: true,
        });
        const pngBuf = Buffer.from(data, "base64");
        const prefix = `cue_${String(i).padStart(4, "0")}`;
        writeFileSync(join(absOut, `${prefix}.png`), pngBuf);

        const nextStart = i + 1 < cues.length ? cues[i + 1].start_s : totalDurationS;
        const cueDur = Math.min(cue.end_s, nextStart) - cue.start_s;
        if (useFade && cueDur >= frameDur * 3.5) {
          fadeTasks.push(
            (async () => {
              const [f1, f2] = await Promise.all([
                scalePngAlpha(pngBuf, 0.36),
                scalePngAlpha(pngBuf, 0.72),
              ]);
              writeFileSync(join(absOut, `${prefix}_f1.png`), f1);
              writeFileSync(join(absOut, `${prefix}_f2.png`), f2);
            })()
          );
        }
      }
      await Promise.all(fadeTasks);
    } finally {
      await browser.close();
    }
  }

  const timeline = buildConcatTimeline(cues, totalDurationS, fps, fadeInMs);
  const concatLines = ["ffconcat version 1.0"];
  for (const seg of timeline) {
    concatLines.push(`file '${seg.file}'`);
    concatLines.push(`duration ${seg.duration_s.toFixed(6)}`);
  }
  concatLines.push(`file '${timeline[timeline.length - 1].file}'`);

  const concatPath = join(absOut, "captions_concat.txt");
  writeFileSync(concatPath, `${concatLines.join("\n")}\n`, "utf8");

  return {
    ok: true,
    concat_file: concatPath,
    y_top: yTop,
    band_height: bandHeight,
    width,
    height,
    cues_rendered: cues.length,
    font_family: fontFamily,
    font_size: fontSize,
    margin_v: marginV,
  };
}

if (isMainModule(import.meta.url)) {
  const args = parseArgs(process.argv);
  if (!args.captions || !args["out-dir"]) {
    console.error(
      "Usage: render_captions_overlay.mjs --captions <file.ass|json> --out-dir <dir> [--width 1080] [--height 1920] [--fps 30] [--duration 57.3]"
    );
    process.exit(2);
  }
  renderCaptionsOverlay({
    captionsPath: String(args.captions),
    outDir: String(args["out-dir"]),
    width: Number(args.width || 1080),
    height: Number(args.height || 1920),
    fps: Number(args.fps || 30),
    durationS: args.duration !== undefined ? Number(args.duration) : null,
    fontSizeOverride: args["font-size"] !== undefined ? Number(args["font-size"]) : null,
    marginVOverride: args["margin-v"] !== undefined ? Number(args["margin-v"]) : null,
    fontFamilyOverride: args["font-family"] ? String(args["font-family"]) : null,
    fadeInMsOverride: args["fade-in-ms"] !== undefined ? Number(args["fade-in-ms"]) : null,
  })
    .then((meta) => {
      process.stdout.write(`${JSON.stringify(meta)}\n`);
    })
    .catch((err) => {
      console.error(err?.stack || String(err));
      process.exit(1);
    });
}
