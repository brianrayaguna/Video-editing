#!/usr/bin/env node
/**
 * Download and cache AWS Mapzen Terrarium RGB elevation tiles (`encoding: "terrarium"`)
 * into `assets/geo/dem/{z}/{x}/{y}.png` for offline MapLibre GL 3D terrain & hillshade.
 *
 * Env:
 *   BBOX="minLon,minLat,maxLon,maxLat" (default: Kalimantan + Sulawesi "107.5,-6.0,125.5,7.5")
 *   ZOOMS="4,5,6,7" (default: "4,5,6,7")
 *   CONCURRENCY="6"
 */

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const DEM_ROOT = join(REPO_ROOT, "assets/geo/dem");

const BBOX = (process.env.BBOX || "107.5,-6.0,125.5,7.5").split(",").map(Number);
const ZOOMS = (process.env.ZOOMS || "4,5,6,7").split(",").map(Number);
const CONCURRENCY = Math.max(1, Number(process.env.CONCURRENCY || 6));

function lon2x(lon, z) {
  return Math.floor(((lon + 180) / 360) * (1 << z));
}
function lat2y(lat, z) {
  const rad = (lat * Math.PI) / 180;
  return Math.floor(
    ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * (1 << z)
  );
}

async function main() {
  const [minLon, minLat, maxLon, maxLat] = BBOX;
  const jobs = [];
  for (const z of ZOOMS) {
    const x0 = Math.max(0, lon2x(minLon, z));
    const x1 = Math.min((1 << z) - 1, lon2x(maxLon, z));
    const y0 = Math.max(0, lat2y(maxLat, z));
    const y1 = Math.min((1 << z) - 1, lat2y(minLat, z));
    for (let x = x0; x <= x1; x++) {
      for (let y = y0; y <= y1; y++) {
        const dest = join(DEM_ROOT, String(z), String(x), `${y}.png`);
        if (!existsSync(dest)) {
          jobs.push({ z, x, y, dest });
        }
      }
    }
  }

  console.log(`[dem] ${jobs.length} elevation tiles to fetch into ${DEM_ROOT}`);
  if (jobs.length === 0) return;

  const t0 = Date.now();
  let ok = 0;
  let failed = 0;
  let cursor = 0;

  async function worker() {
    while (cursor < jobs.length) {
      const idx = cursor++;
      const { z, x, y, dest } = jobs[idx];
      const url = `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/${z}/${x}/${y}.png`;
      try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const buf = Buffer.from(await resp.arrayBuffer());
        mkdirSync(dirname(dest), { recursive: true });
        writeFileSync(dest, buf);
        ok++;
      } catch (err) {
        failed++;
        console.warn(`[dem] failed ${z}/${x}/${y}: ${err.message}`);
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, jobs.length) }, worker));
  const dt = ((Date.now() - t0) / 1000).toFixed(2);
  console.log(`[dem] fetched ${ok} tiles (${failed} failed) in ${dt}s`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
