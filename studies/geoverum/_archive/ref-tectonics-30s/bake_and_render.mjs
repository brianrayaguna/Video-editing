#!/usr/bin/env node
/**
 * Bake Geoverum overlay layers for the ref_tectonics 30s proof cut, composite over
 * the locked 1080x1920 basemap, mux the mastered VO stem, and emit a QA contact sheet.
 */

import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const RENDERS_DIR = join(STUDY_DIR, "renders");

const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const CAPTION_SCHEDULE = [
  { id: "cap-01", startFrame: 7, endFrame: 51, text: "Turki dan India terpisah", softIn: true },
  { id: "cap-02", startFrame: 51, endFrame: 150, text: "km, tidak berbagi perbatasan," },
  { id: "cap-03", startFrame: 150, endFrame: 210, text: "bahkan berada di kawasan" },
  { id: "cap-04", startFrame: 210, endFrame: 360, text: "Namun hubungan keduanya kini" },
  { id: "cap-05", startFrame: 375, endFrame: 450, text: "Penyebab utamanya adalah Pakistan.", softIn: true },
  { id: "cap-06", startFrame: 480, endFrame: 570, text: "Pakistan dalam isu Kashmir" },
  { id: "cap-07", startFrame: 590, endFrame: 645, text: "Ketegangan makin terasa setelah" },
  { id: "cap-08", startFrame: 645, endFrame: 720, text: "konflik India-Pakistan pada" },
  { id: "cap-09", startFrame: 735, endFrame: 780, text: "2025 ketika pesawat nirawak" },
  { id: "cap-10", startFrame: 780, endFrame: 840, text: "buatan Turki dilaporkan" },
  { id: "cap-11", startFrame: 840, endFrame: 900, text: "India tidak membalas dengan" },
];

function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, { encoding: "utf8", ...opts });
  if (res.status !== 0) {
    throw new Error(`${cmd} ${args.join(" ")} failed\n${res.stderr || ""}`);
  }
  return res;
}

async function renderCaptionChips(layersDir) {
  const fontFile = join(ASSETS_DIR, "fonts/SpaceGrotesk-Variable.ttf");
  const centerY = 1458;
  const padX = 26;
  const padY = 15;
  const capPngs = [];

  for (const item of CAPTION_SCHEDULE) {
    const rawGlyphPng = join(layersDir, `${item.id}-glyph-raw.png`);
    const drawTextEscaped = item.text
      .replace(/\\/g, "\\\\")
      .replace(/:/g, "\\:")
      .replace(/'/g, "\\'")
      .replace(/,/g, "\\,");

    run("ffmpeg", [
      "-y", "-hide_banner", "-loglevel", "error",
      "-f", "lavfi", "-i", "color=c=black@0.0:s=1080x140,format=rgba",
      "-vf", `drawtext=fontfile='${fontFile}':text='${drawTextEscaped}':fontsize=40:fontcolor=0xF4F1EA:x=(w-text_w)/2:y=(h-text_h)/2`,
      "-frames:v", "1", rawGlyphPng,
    ]);

    const trimmedGlyph = await sharp(rawGlyphPng).trim().png().toBuffer({ resolveWithObject: true });
    const textW = trimmedGlyph.info.width;
    const textH = trimmedGlyph.info.height;
    const boxW = textW + padX * 2;
    const boxH = textH + padY * 2;
    const boxX = Math.round((1080 - boxW) / 2);
    const boxY = Math.round(centerY - boxH / 2);
    const textLeft = Math.round((1080 - textW) / 2);
    const textTop = Math.round(centerY - textH / 2);

    const chipBgSvg = Buffer.from(`<svg width="1080" height="1920" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <filter id="cap-shadow" x="-15%" y="-25%" width="130%" height="160%">
          <feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#000000" flood-opacity="0.40" />
        </filter>
      </defs>
      <rect x="${boxX}" y="${boxY}" width="${boxW}" height="${boxH}" rx="6" fill="rgba(6, 16, 22, 0.80)" filter="url(#cap-shadow)" />
    </svg>`);

    const outPng = join(layersDir, `${item.id}.png`);
    await sharp(chipBgSvg)
      .composite([{ input: trimmedGlyph.data, left: textLeft, top: textTop }])
      .png()
      .toFile(outPng);
    capPngs.push({ ...item, png: outPng });
  }
  return capPngs;
}

async function renderChromeCovers(layersDir) {
  const topCover = join(layersDir, "cover-top.png");
  const capCover = join(layersDir, "cover-caption.png");
  // Opaque top bar hides the source channel watermark completely before Geoverum bug lands.
  const topSvg = Buffer.from(`<svg width="1080" height="1920" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#03161F" stop-opacity="1"/>
        <stop offset="78%" stop-color="#03161F" stop-opacity="0.96"/>
        <stop offset="100%" stop-color="#03161F" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect x="120" y="0" width="840" height="200" fill="url(#g)"/>
  </svg>`);
  const capSvg = Buffer.from(`<svg width="1080" height="1920" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="c" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#03161F" stop-opacity="0"/>
        <stop offset="22%" stop-color="#03161F" stop-opacity="0.85"/>
        <stop offset="100%" stop-color="#03161F" stop-opacity="0.90"/>
      </linearGradient>
    </defs>
    <rect x="40" y="1360" width="1000" height="220" rx="8" fill="url(#c)"/>
  </svg>`);
  await sharp(topSvg).png().toFile(topCover);
  await sharp(capSvg).png().toFile(capCover);
  return { topCover, capCover };
}

async function renderWatermark(layersDir) {
  const fontFile = join(ASSETS_DIR, "fonts/SpaceGrotesk-Variable.ttf");
  const textRaw = join(layersDir, "wm-text-raw.png");
  run("ffmpeg", [
    "-y", "-hide_banner", "-loglevel", "error",
    "-f", "lavfi", "-i", "color=c=black@0.0:s=700x80,format=rgba",
    "-vf", `drawtext=fontfile='${fontFile}':text='GEOVERUM':fontsize=32:fontcolor=0xF4F1EA:x=0:y=(h-text_h)/2`,
    "-frames:v", "1", textRaw,
  ]);
  const trimmed = await sharp(textRaw).trim().png().toBuffer({ resolveWithObject: true });
  const gap = 14;
  const mark = 34;
  const totalW = mark + gap + trimmed.info.width;
  const startX = Math.round((1080 - totalW) / 2);
  const topY = 72;
  const markSvg = Buffer.from(`<svg width="1080" height="1920" xmlns="http://www.w3.org/2000/svg">
    <g transform="translate(${startX} ${topY})" opacity="0.86">
      <circle cx="17" cy="17" r="13" fill="none" stroke="#F4F1EA" stroke-width="2.2"/>
      <ellipse cx="17" cy="17" rx="6" ry="13" fill="none" stroke="#F4F1EA" stroke-width="1.6"/>
      <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.6"/>
    </g>
  </svg>`);
  const out = join(layersDir, "watermark.png");
  await sharp(markSvg)
    .composite([
      {
        input: trimmed.data,
        left: startX + mark + gap,
        top: topY + Math.round((mark - trimmed.info.height) / 2),
      },
    ])
    .png()
    .toFile(out);
  return out;
}

async function main() {
  mkdirSync(RENDERS_DIR, { recursive: true });
  const layersDir = join(RENDERS_DIR, "layers-tmp");
  rmSync(layersDir, { recursive: true, force: true });
  mkdirSync(layersDir, { recursive: true });

  console.log("[ref-tectonics-30s] Rendering caption chips...");
  const capPngs = await renderCaptionChips(layersDir);
  console.log("[ref-tectonics-30s] Rendering chrome covers + watermark...");
  const { topCover, capCover } = await renderChromeCovers(layersDir);
  const watermark = await renderWatermark(layersDir);

  const basemap = join(ASSETS_DIR, "basemap-30s.mp4");
  const vo = join(ASSETS_DIR, "vo-30s.wav");
  const outMp4 = join(RENDERS_DIR, "ref_tectonics_30s_geoverum.mp4");

  const inputs = ["-i", basemap, "-i", vo, "-loop", "1", "-t", "30", "-i", topCover, "-loop", "1", "-t", "30", "-i", capCover, "-loop", "1", "-t", "30", "-i", watermark];
  for (const c of capPngs) {
    inputs.push("-loop", "1", "-t", "30", "-i", c.png);
  }

  // 0 basemap, 1 audio, 2 topCover, 3 capCover, 4 watermark, 5.. captions
  const filterParts = [
    "[0:v][2:v]overlay=0:0[v0]",
    "[v0][3:v]overlay=0:0[v1]",
    "[v1][4:v]overlay=0:0:enable='gte(t,0.10)'[v2]",
  ];
  capPngs.forEach((c, idx) => {
    const inIdx = idx + 5;
    const prev = idx === 0 ? "v2" : `vc${idx}`;
    const next = `vc${idx + 1}`;
    const sSec = (c.startFrame / 30).toFixed(4);
    const eSec = ((c.endFrame - 0.05) / 30).toFixed(4);
    filterParts.push(`[${prev}][${inIdx}:v]overlay=0:0:enable='between(t,${sSec},${eSec})'[${next}]`);
  });
  const finalLabel = `vc${capPngs.length}`;
  filterParts.push(`[${finalLabel}]format=yuv420p[vout]`);

  writeFileSync(join(RENDERS_DIR, "caption-schedule.json"), JSON.stringify(CAPTION_SCHEDULE, null, 2));

  console.log("[ref-tectonics-30s] Compositing 900-frame deliverable...");
  run(
    "ffmpeg",
    [
      "-y", "-hide_banner",
      ...inputs,
      "-filter_complex", filterParts.join(";"),
      "-map", "[vout]", "-map", "1:a",
      "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
      "-r", "30", "-g", "60", "-crf", "17",
      "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
      "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
      "-movflags", "+faststart", "-t", "30.0",
      outMp4,
    ],
    { stdio: "inherit" }
  );

  const sheetJpg = join(RENDERS_DIR, "qa_contact_sheet.jpg");
  const frames = [15, 75, 165, 255, 390, 510, 615, 750, 840, 885];
  const selectExpr = frames.map((n) => `eq(n\\,${n})`).join("+");
  run("ffmpeg", [
    "-y", "-hide_banner", "-i", outMp4,
    "-vf", `select='${selectExpr}',scale=216:384,tile=5x2`,
    "-fps_mode", "passthrough", "-frames:v", "1", "-update", "1",
    sheetJpg,
  ], { stdio: "inherit" });

  // Loudness audit
  const audit = run("ffmpeg", [
    "-hide_banner", "-i", outMp4,
    "-af", "ebur128=peak=true", "-f", "null", "-",
  ]);
  writeFileSync(join(RENDERS_DIR, "ebur128.log"), audit.stderr || "");

  rmSync(layersDir, { recursive: true, force: true });
  console.log(`[ref-tectonics-30s] Complete -> ${outMp4}`);
  console.log(`[ref-tectonics-30s] QA sheet -> ${sheetJpg}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
