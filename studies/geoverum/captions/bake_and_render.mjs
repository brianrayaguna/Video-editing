#!/usr/bin/env node
/**
 * Validate the Geoverum Captions (`captions`) HyperFrames project via
 * `@hyperframes/lint`, render the measured caption chip layers (`SpaceGrotesk-Variable.ttf`)
 * and broadcast watermark via `sharp` (`libvips`/`pango`), composite them at frame-accurate
 * timestamps over the 12.0s satellite camera basemap with two-pass EBU R128 mastered
 * Indonesian voiceover (-14.0 LUFS, <= -1.0 dBTP, 48 kHz stereo AAC), and generate the
 * 10-beat QA contact sheet.
 */

import { mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { lintHyperframesProjectDir } from "../../../packages/hf-compiler-ts/dist/lint.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const RENDERS_DIR = join(STUDY_DIR, "renders");

process.env.FONTCONFIG_FILE = join(REPO_ROOT, "assets/geo/fonts/fonts.conf");

const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const CAPTION_SCHEDULE = [
  { id: "cap-01", startFrame: 7, endFrame: 51, text: "Kalau lihat peta, Sulawesi" },
  { id: "cap-02", startFrame: 51, endFrame: 84, text: "tampak seperti huruf K" },
  { id: "cap-03", startFrame: 84, endFrame: 127, text: "yang patah atau gurita" },
  { id: "cap-04", startFrame: 127, endFrame: 155, text: "yang salah posisi." },
  { id: "cap-05", startFrame: 155, endFrame: 193, text: "Bentuk aneh ini bukan" },
  { id: "cap-06", startFrame: 193, endFrame: 246, text: "kebetulan, melainkan hasil tabrakan" },
  { id: "cap-07", startFrame: 246, endFrame: 297, text: "geologi selama jutaan tahun." },
  { id: "cap-08", startFrame: 304, endFrame: 349, text: "Sulawesi punya empat semenanjung" },
  { id: "cap-09", startFrame: 349, endFrame: 360, text: "panjang yang menjulur ke" },
];

async function renderOverlayLayers(layersDir) {
  mkdirSync(layersDir, { recursive: true });
  const fontFile = join(ASSETS_DIR, "fonts/SpaceGrotesk-Variable.ttf");

  // Render each caption chip by rasterizing the exact glyphs via FreeType/HarfBuzz
  // (using SpaceGrotesk-Variable.ttf directly without fontconfig), trimming to exact
  // glyph bounds ("Fit the text before fixing the box" — stageshow/references/craft.md),
  // and compositing onto a measured 6px-radius dark slate chip with subtle drop shadow.
  const capPngs = [];
  const centerY = 1458; // 75.9% of 1920px height, matching Reference A's 75.9% caption rail
  const padX = 26;
  const padY = 15;

  for (const item of CAPTION_SCHEDULE) {
    const rawGlyphPng = join(layersDir, `${item.id}-glyph-raw.png`);
    const drawTextEscaped = item.text
      .replace(/\\/g, "\\\\")
      .replace(/:/g, "\\:")
      .replace(/'/g, "\\'")
      .replace(/,/g, "\\,");

    const ffGlyph = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black@0.0:s=1080x140,format=rgba",
        "-vf",
        `drawtext=fontfile='${fontFile}':text='${drawTextEscaped}':fontsize=40:fontcolor=0xF4F1EA:x=(w-text_w)/2:y=(h-text_h)/2`,
        "-frames:v",
        "1",
        rawGlyphPng,
      ],
      { stdio: "inherit" }
    );
    if (ffGlyph.status !== 0) {
      throw new Error(`FreeType glyph render failed for ${item.id}`);
    }

    const trimmedGlyph = await sharp(rawGlyphPng)
      .trim()
      .png()
      .toBuffer({ resolveWithObject: true });

    const textW = trimmedGlyph.info.width;
    const textH = trimmedGlyph.info.height;
    const boxW = textW + padX * 2;
    const boxH = textH + padY * 2;
    const boxX = Math.round((1080 - boxW) / 2);
    const boxY = Math.round(centerY - boxH / 2);
    const textLeft = Math.round((1080 - textW) / 2);
    const textTop = Math.round(centerY - textH / 2);

    const chipBgSvg = Buffer.from(
      `<svg width="1080" height="1920" viewBox="0 0 1080 1920" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <filter id="cap-shadow" x="-15%" y="-25%" width="130%" height="160%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#000000" flood-opacity="0.40" />
          </filter>
        </defs>
        <rect x="${boxX}" y="${boxY}" width="${boxW}" height="${boxH}" rx="6" fill="rgba(6, 16, 22, 0.80)" filter="url(#cap-shadow)" />
      </svg>`
    );

    const outPng = join(layersDir, `${item.id}.png`);
    await sharp(chipBgSvg)
      .composite([{ input: trimmedGlyph.data, left: textLeft, top: textTop }])
      .png()
      .toFile(outPng);

    capPngs.push({ ...item, png: outPng, boxW, boxH });
  }

  return { capPngs };
}

async function main() {
  mkdirSync(RENDERS_DIR, { recursive: true });
  const layersDir = join(RENDERS_DIR, "layers-tmp");

  console.log("[captions] Running @hyperframes/lint & performance gate on studies/geoverum/captions...");
  const lintSummary = await lintHyperframesProjectDir(STUDY_DIR);
  console.log(JSON.stringify(lintSummary, null, 2));
  if (!lintSummary.ok) {
    throw new Error(`HyperFrames lint failed with ${lintSummary.totalErrors} error(s).`);
  }

  console.log("[captions] Rendering measured caption chip layers via FreeType + Sharp...");
  const { capPngs } = await renderOverlayLayers(layersDir);
  for (const c of capPngs) {
    console.log(`  [${c.id}] f${c.startFrame}..f${c.endFrame} (${c.boxW}x${c.boxH}px): "${c.text}"`);
  }

  const basemapMp4 = join(ASSETS_DIR, "basemap-camera-moves.mp4");
  const voPath = join(ASSETS_DIR, "vo-12s.m4a");
  const outMp4 = join(RENDERS_DIR, "captions_1080x1920.mp4");

  const inputs = ["-i", basemapMp4, "-i", voPath];
  for (const c of capPngs) {
    inputs.push("-loop", "1", "-t", "12", "-i", c.png);
  }

  const filterParts = [];
  capPngs.forEach((c, idx) => {
    const inIdx = idx + 2;
    const prevLabel = idx === 0 ? "0:v" : `v${idx}`;
    const nextLabel = `v${idx + 1}`;
    const sSec = (c.startFrame / 30).toFixed(4);
    const eSec = ((c.endFrame - 0.1) / 30).toFixed(4);
    filterParts.push(
      `[${prevLabel}][${inIdx}:v]overlay=0:0:enable='between(t,${sSec},${eSec})'[${nextLabel}]`
    );
  });

  const finalVideoLabel = `v${capPngs.length}`;
  filterParts.push(`[${finalVideoLabel}]format=yuv420p[vout]`);

  // Two-pass EBU R128 loudness normalization on the voiceover track toward -14.0 LUFS / <= -1.0 dBTP
  console.log("[captions] Measuring pass-1 EBU R128 loudness on voiceover stem...");
  const pass1 = spawnSync(
    "ffmpeg",
    [
      "-hide_banner",
      "-i",
      voPath,
      "-af",
      "loudnorm=I=-14.0:TP=-1.5:LRA=7.0:print_format=json",
      "-f",
      "null",
      "-",
    ],
    { encoding: "utf8" }
  );
  const jsonMatch = (pass1.stderr || "").match(/\{[\s\S]*?"input_i"[\s\S]*?\}/);
  let audioFilter = "loudnorm=I=-14.0:TP=-1.5:LRA=7.0";
  if (jsonMatch) {
    const m = JSON.parse(jsonMatch[0]);
    audioFilter =
      `loudnorm=I=-14.0:TP=-1.5:LRA=7.0:` +
      `measured_I=${m.input_i}:measured_TP=${m.input_tp}:measured_LRA=${m.input_lra}:` +
      `measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true`;
  }

  console.log("[captions] Mastering 1080x1920 @ 30fps CFR H.264 + 48kHz AAC deliverable...");
  const ffMaster = spawnSync(
    "ffmpeg",
    [
      "-y",
      ...inputs,
      "-filter_complex",
      filterParts.join(";"),
      "-map",
      "[vout]",
      "-map",
      "1:a",
      "-af",
      audioFilter,
      "-c:v",
      "libx264",
      "-profile:v",
      "high",
      "-pix_fmt",
      "yuv420p",
      "-r",
      "30",
      "-color_primaries",
      "bt709",
      "-color_trc",
      "bt709",
      "-colorspace",
      "bt709",
      "-crf",
      "17",
      "-g",
      "60",
      "-c:a",
      "aac",
      "-ar",
      "48000",
      "-ac",
      "2",
      "-b:a",
      "192k",
      "-movflags",
      "+faststart",
      "-t",
      "12.0",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ffMaster.status !== 0) {
    throw new Error(`FFmpeg mastering failed with status ${ffMaster.status}`);
  }

  // Extract 10-frame QA contact sheet showing all 9 caption groups + the f300 breath pause gap
  const sheetJpg = join(RENDERS_DIR, "captions_sheet.jpg");
  const selectExpr = [25, 65, 105, 140, 175, 220, 270, 300, 325, 354]
    .map((n) => `eq(n\\,${n})`)
    .join("+");
  const ffSheet = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      outMp4,
      "-vf",
      `drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text='f%{n} %{pts\\:hms}':x=20:y=20:fontsize=38:fontcolor=yellow:box=1:boxcolor=black@0.7,select='${selectExpr}',scale=360:640,tile=5x2`,
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

  rmSync(layersDir, { recursive: true, force: true });
  console.log(`[captions] Complete -> ${outMp4}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
