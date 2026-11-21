#!/usr/bin/env node
/**
 * Build calibrated XYZ satellite tiles (`assets/geo/tiles/{z}/{x}/{y}.jpg`)
 * from raw downloaded assets in `assets/geo/raw/`.
 *
 * Uses `sharp` (libvips) to apply a deterministic documentary color grade at
 * build time: preserving marine-teal ocean bathymetry (`#083847`–`#164F60`)
 * while enhancing natural landmass relief clarity, avoiding runtime CSS filters.
 */

import { existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const GEO_ROOT = join(REPO_ROOT, "assets/geo");
const RAW_DIR = join(GEO_ROOT, "raw");
const TILES_OUT = join(GEO_ROOT, "tiles");

/**
 * Resolve a Blue Marble bathymetry buffer for `(z, x, y)` up to z=6 by cropping
 * the z=4 ancestor tile when `z > 4`, giving continuous marine bathymetry detail.
 */
async function resolveBmngRgbBuffer(z, x, y) {
  const maxBmngZ = 4;
  if (z <= maxBmngZ) {
    const p = join(RAW_DIR, "tiles_bmng", String(z), String(x), `${y}.jpg`);
    if (!existsSync(p) || statSync(p).size <= 250) return null;
    return sharp(p)
      .flatten({ background: { r: 8, g: 56, b: 71 } })
      .removeAlpha()
      .resize(256, 256)
      .raw()
      .toBuffer();
  }
  if (z > 6) return null;
  const scale = 1 << (z - maxBmngZ);
  const px = Math.floor(x / scale);
  const py = Math.floor(y / scale);
  const ancestor = join(RAW_DIR, "tiles_bmng", String(maxBmngZ), String(px), `${py}.jpg`);
  if (!existsSync(ancestor) || statSync(ancestor).size <= 250) return null;
  const subSize = Math.max(1, Math.floor(256 / scale));
  const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
  const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
  return sharp(ancestor)
    .flatten({ background: { r: 8, g: 56, b: 71 } })
    .removeAlpha()
    .extract({ left, top, width: subSize, height: subSize })
    .resize(256, 256)
    .raw()
    .toBuffer();
}

/**
 * Apply documentary marine-teal ocean bathymetry and natural relief grading to a 256x256 tile.
 */
async function gradeTile(item, outPath) {
  const inputPath = item.path;
  const inputSize = statSync(inputPath).size;
  const bmngData = await resolveBmngRgbBuffer(item.z, item.x, item.y);

  if (inputSize <= 250 && !bmngData) {
    mkdirSync(dirname(outPath), { recursive: true });
    await sharp({
      create: { width: 256, height: 256, channels: 3, background: { r: 10, g: 56, b: 70 } },
    })
      .jpeg({ quality: 86, mozjpeg: true })
      .toFile(outPath);
    return;
  }

  let data;
  let width = 256;
  let height = 256;
  if (inputSize <= 250 && bmngData) {
    data = bmngData;
  } else {
    const res = await sharp(inputPath)
      .flatten({ background: { r: 10, g: 56, b: 70 } })
      .removeAlpha()
      .resize(256, 256)
      .raw()
      .toBuffer({ resolveWithObject: true });
    data = res.data;
    width = res.info.width;
    height = res.info.height;
  }

  const landBlend = item.z <= 2 ? 0.42 : item.z <= 4 ? 0.24 : 0.0;
  const oceanBathymetryBlend = item.z <= 4 ? 0.65 : item.z <= 6 ? 0.45 : 0.0;

  const out = Buffer.allocUnsafe(data.length);
  for (let i = 0; i < data.length; i += 3) {
    let r = data[i];
    let g = data[i + 1];
    let b = data[i + 2];

    const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    const blueDominance = b - Math.max(r * 1.05, g * 0.88);
    const maxCh = Math.max(r, g, b);
    const isOcean = maxCh < 24 || (blueDominance > 3 && luma < 155);

    if (bmngData) {
      const w = isOcean ? oceanBathymetryBlend : landBlend;
      if (w > 0) {
        r = r * (1 - w) + bmngData[i] * w;
        g = g * (1 - w) + bmngData[i + 1] * w;
        b = b * (1 - w) + bmngData[i + 2] * w;
      }
    }

    if (isOcean) {
      // Preserve marine-teal bathymetry shelf (#083847 -> #164F60) without crushing to pure black.
      const nodataStrength = maxCh < 24 ? Math.min(1, (24 - maxCh) / 16) : 0;
      const waterStrength = Math.max(
        nodataStrength,
        Math.min(1, Math.max(0, blueDominance) / 28) * Math.min(1, (160 - luma) / 95)
      );
      const targetR = 7 + r * 0.28;
      const targetG = 46 + g * 0.42;
      const targetB = 60 + b * 0.46;
      r = r * (1 - waterStrength) + targetR * waterStrength;
      g = g * (1 - waterStrength) + targetG * waterStrength;
      b = b * (1 - waterStrength) + targetB * waterStrength;
    } else {
      // Landmass relief: subtle contrast and natural vegetation/terrain warmth.
      const c = 1.07;
      r = (r - 110) * c + 107;
      g = (g - 110) * (c * 1.02) + 109;
      b = (b - 110) * (c * 0.96) + 103;
    }

    out[i] = Math.max(0, Math.min(255, Math.round(r)));
    out[i + 1] = Math.max(0, Math.min(255, Math.round(g)));
    out[i + 2] = Math.max(0, Math.min(255, Math.round(b)));
  }

  mkdirSync(dirname(outPath), { recursive: true });
  await sharp(out, { raw: { width, height, channels: 3 } })
    .jpeg({ quality: 86, mozjpeg: true })
    .toFile(outPath);
}

function listTilesRecursive(rootDir) {
  const results = [];
  if (!existsSync(rootDir)) return results;
  for (const zStr of readdirSync(rootDir)) {
    const zDir = join(rootDir, zStr);
    const z = Number(zStr);
    if (!Number.isInteger(z)) continue;
    for (const xStr of readdirSync(zDir)) {
      const xDir = join(zDir, xStr);
      const x = Number(xStr);
      if (!Number.isInteger(x)) continue;
      for (const yFile of readdirSync(xDir)) {
        if (!yFile.endsWith(".jpg")) continue;
        const y = Number(yFile.replace(/\.jpg$/, ""));
        results.push({ z, x, y, path: join(xDir, yFile) });
      }
    }
  }
  return results;
}

async function main() {
  mkdirSync(TILES_OUT, { recursive: true });
  const s2Tiles = listTilesRecursive(join(RAW_DIR, "tiles_s2_2016"));
  console.log(`[tiles] Grading ${s2Tiles.length} tiles into assets/geo/tiles/ ...`);

  const concurrency = 16;
  let idx = 0;
  let done = 0;
  const t0 = Date.now();

  async function worker() {
    while (idx < s2Tiles.length) {
      const item = s2Tiles[idx++];
      const outPath = join(TILES_OUT, String(item.z), String(item.x), `${item.y}.jpg`);
      await gradeTile(item, outPath);
      done++;
      if (done % 400 === 0 || done === s2Tiles.length) {
        const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
        console.log(`  [tiles] ${done}/${s2Tiles.length} graded (${elapsed}s)`);
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
