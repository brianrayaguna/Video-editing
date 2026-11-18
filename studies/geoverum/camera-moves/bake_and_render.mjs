#!/usr/bin/env node
/**
 * Bake the 12-second (360-frame @ 30fps, 1080x1920) continuous camera trajectory
 * for Geoverum Camera Moves (`camera-moves`), validate the HyperFrames project
 * via `@vedit/hf-compiler`, and render the deliverable MP4 + 12-beat contact sheet.
 */

import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { lintHyperframesProjectDir } from "../../../packages/hf-compiler-ts/dist/lint.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const STUDY_DIR = __dirname;
const ASSETS_DIR = join(STUDY_DIR, "assets");
const RENDERS_DIR = join(STUDY_DIR, "renders");

// 7-beat continuous camera trajectory defined in SPEC.md
const KEYFRAMES = [
  // f000 (0.00s): Orbital Globe Start
  { frame: 0, center: [108.0, 8.0], zoom: 1.85, pitch: 0, bearing: 0, ease: "strongInOut" },
  // f040 (1.33s): Arrive at Sulawesi Island
  { frame: 40, center: [121.35, -1.75], zoom: 5.95, pitch: 0, bearing: 0, ease: "strongInOut", panEase: "sineInOut" },
  // f126 (4.20s): Slow Push-In Hold (never frozen; +5.5% scale creep + 10° pitch emergence)
  { frame: 126, center: [121.25, -1.55], zoom: 6.18, pitch: 10, bearing: -2, ease: "linear" },
  // f165 (5.50s): 3D Fly-To into Gulf of Tomini
  { frame: 165, center: [120.88, -0.25], zoom: 7.65, pitch: 38, bearing: -10, ease: "strongInOut" },
  // f240 (8.00s): 3D Coastal Glide along East Peninsula to Gulf of Tolo
  { frame: 240, center: [122.15, -1.85], zoom: 7.42, pitch: 34, bearing: 14, ease: "sineInOut" },
  // f276 (9.20s): Fly-To Palu-Koro Fault Valley
  { frame: 276, center: [119.92, -1.12], zoom: 8.85, pitch: 42, bearing: -16, ease: "strongInOut" },
  // f318 (10.60s): Fault Valley Drift toward Palu Bay
  { frame: 318, center: [119.85, -0.82], zoom: 9.10, pitch: 40, bearing: -8, ease: "linear" },
  // f359 (12.00s): Regional Pull-Back Settle over Sulawesi
  { frame: 359, center: [121.35, -1.68], zoom: 6.08, pitch: 14, bearing: -4, ease: "strongInOut" },
];

async function main() {
  console.log("[camera-moves] Baking 360-frame (12.0s @ 30fps) continuous basemap trajectory...");
  const bakeRes = spawnSync(
    process.execPath,
    [join(REPO_ROOT, "tools/geo-assets/bake_vertical_basemap.mjs")],
    {
      stdio: "inherit",
      env: {
        ...process.env,
        NAME: "basemap-camera-moves",
        WIDTH: "1080",
        HEIGHT: "1920",
        FPS: "30",
        DUR: "12",
        PROJECTION: "globe",
        HOLD: "0.95",
        OUT: ASSETS_DIR,
        KEYFRAMES_JSON: JSON.stringify(KEYFRAMES),
      },
    }
  );
  if (bakeRes.status !== 0) {
    throw new Error(`Basemap bake failed with status ${bakeRes.status}`);
  }

  console.log("[camera-moves] Running @hyperframes/lint & performance gate on studies/geoverum/camera-moves...");
  const lintSummary = await lintHyperframesProjectDir(STUDY_DIR);
  console.log(JSON.stringify(lintSummary, null, 2));
  if (!lintSummary.ok) {
    throw new Error(`HyperFrames lint failed with ${lintSummary.totalErrors} error(s).`);
  }

  // Render the clean unboxed broadcast overlay PNG and composite over the all-intra basemap
  const basemapMp4 = join(ASSETS_DIR, "basemap-camera-moves.mp4");
  const outMp4 = join(RENDERS_DIR, "camera_moves_1080x1920.mp4");
  const overlayPng = join(RENDERS_DIR, "broadcast_overlay.png");

  const { createRequire } = await import("node:module");
  const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
  const sharp = require("sharp");

  const overlaySvg = Buffer.from(`<svg width="1080" height="1920" viewBox="0 0 1080 1920" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <filter id="wm-shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="6" flood-color="#000000" flood-opacity="0.68" />
      </filter>
    </defs>
    <g transform="translate(385, 72)" opacity="0.86" filter="url(#wm-shadow)">
      <circle cx="17" cy="17" r="13" fill="none" stroke="#F4F1EA" stroke-width="2.2" />
      <ellipse cx="17" cy="17" rx="6" ry="13" fill="none" stroke="#F4F1EA" stroke-width="1.6" />
      <line x1="4" y1="17" x2="30" y2="17" stroke="#F4F1EA" stroke-width="1.6" />
      <text x="48" y="28" font-family="Space Grotesk, sans-serif" font-weight="700" font-size="32" letter-spacing="3.8" fill="#F4F1EA">GEOVERUM</text>
    </g>
    <text x="540" y="1894" text-anchor="middle" font-family="Space Grotesk, sans-serif" font-weight="400" font-size="13" fill="rgba(244, 241, 234, 0.40)">
      Imagery: NASA Blue Marble, EOX Sentinel-2 cloudless 2016 (Copernicus) · Vectors: Natural Earth, PB2002, GEM
    </text>
  </svg>`);

  await sharp(overlaySvg).png().toFile(overlayPng);

  console.log("[camera-moves] Mastering final 1080x1920 @ 30fps CFR H.264 bt709 deliverable...");
  const ffMaster = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      basemapMp4,
      "-loop",
      "1",
      "-i",
      overlayPng,
      "-filter_complex",
      "[1:v]fade=t=in:st=0.10:d=0.20:alpha=1[ov];[0:v][ov]overlay=0:0:shortest=1,format=yuv420p[v]",
      "-map",
      "[v]",
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
      "-movflags",
      "+faststart",
      outMp4,
    ],
    { stdio: "inherit" }
  );
  if (ffMaster.status !== 0) {
    throw new Error(`FFmpeg mastering failed with status ${ffMaster.status}`);
  }

  // Extract 12-frame contact sheet (1 frame per second across the 12s timeline)
  const sheetJpg = join(RENDERS_DIR, "camera_moves_sheet.jpg");
  const ffSheet = spawnSync(
    "ffmpeg",
    [
      "-y",
      "-i",
      outMp4,
      "-vf",
      "drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial.ttf:text='f%{n} %{pts\\:hms}':x=20:y=20:fontsize=38:fontcolor=yellow:box=1:boxcolor=black@0.7,select='not(mod(n\\,30))',scale=360:640,tile=4x3",
      "-fps_mode",
      "passthrough",
      "-frames:v",
      "1",
      sheetJpg,
    ],
    { stdio: "inherit" }
  );
  if (ffSheet.status !== 0) {
    throw new Error(`Contact sheet extraction failed with status ${ffSheet.status}`);
  }

  console.log(`[camera-moves] Complete -> ${outMp4}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
