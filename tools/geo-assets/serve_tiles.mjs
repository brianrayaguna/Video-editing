#!/usr/bin/env node
/**
 * Local offline HTTP asset & XYZ tile server for Geoverum compositions and basemap baking.
 *
 * Serves:
 * - `GET /tiles/{z}/{x}/{y}.jpg` from `assets/geo/tiles/{z}/{x}/{y}.jpg` with automatic
 *   parent-tile quadrant cropping via `sharp` when an out-of-AOI high-zoom tile is requested.
 * - `GET /vector/*`, `/fonts/*`, `/flags/*`, `/icons/*`, `/vendor/*` from `assets/geo/`.
 * - `GET /health` -> `200 OK` JSON status.
 */

import { createServer } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const GEO_ROOT = join(REPO_ROOT, "assets/geo");
const TILES_DIR = join(GEO_ROOT, "tiles");

const PORT = Number(process.env.PORT || 8765);
const HOST = process.env.HOST || "127.0.0.1";

const MIME_TYPES = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/geo+json; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".ttf": "font/ttf",
  ".woff2": "font/woff2",
};

const fallbackCache = new Map();

/**
 * Resolve a tile `{z}/{x}/{y}` from disk, or synthesize it deterministically by cropping
 * the nearest ancestor tile in `assets/geo/tiles/` so out-of-AOI tiles never 404.
 */
async function resolveTileBuffer(z, x, y) {
  const exactPath = join(TILES_DIR, String(z), String(x), `${y}.jpg`);
  if (existsSync(exactPath)) {
    return readFileSync(exactPath);
  }

  const cacheKey = `${z}/${x}/${y}`;
  if (fallbackCache.has(cacheKey)) {
    return fallbackCache.get(cacheKey);
  }

  for (let pz = z - 1; pz >= 0; pz--) {
    const scale = 1 << (z - pz);
    const px = Math.floor(x / scale);
    const py = Math.floor(y / scale);
    const parentPath = join(TILES_DIR, String(pz), String(px), `${py}.jpg`);
    if (existsSync(parentPath)) {
      const subSize = Math.max(1, Math.floor(256 / scale));
      const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
      const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
      const buf = await sharp(parentPath)
        .extract({ left, top, width: subSize, height: subSize })
        .resize(256, 256, { kernel: sharp.kernel.lanczos3 })
        .jpeg({ quality: 85 })
        .toBuffer();
      if (fallbackCache.size > 1024) {
        const firstKey = fallbackCache.keys().next().value;
        fallbackCache.delete(firstKey);
      }
      fallbackCache.set(cacheKey, buf);
      return buf;
    }
  }
  return null;
}

export function startTileServer(port = PORT, host = HOST) {
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url || "/", `http://${host}:${port}`);
      const pathname = decodeURIComponent(url.pathname);

      res.setHeader("Access-Control-Allow-Origin", "*");
      res.setHeader("Cache-Control", "public, max-age=31536000, immutable");

      if (pathname === "/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "ok", root: "assets/geo" }));
        return;
      }

      const tileMatch = pathname.match(/^\/tiles\/(\d+)\/(\d+)\/(\d+)\.(?:jpg|jpeg)$/);
      if (tileMatch) {
        const z = Number(tileMatch[1]);
        const x = Number(tileMatch[2]);
        const y = Number(tileMatch[3]);
        const buf = await resolveTileBuffer(z, x, y);
        if (!buf) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        res.writeHead(200, { "Content-Type": "image/jpeg" });
        res.end(buf);
        return;
      }

      const safeRel = normalize(pathname).replace(/^(\.\.(\/|\\|$))+/, "").replace(/^\/+/, "");
      const filePath = join(GEO_ROOT, safeRel);
      if (!filePath.startsWith(GEO_ROOT) || !existsSync(filePath)) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("Not found");
        return;
      }

      const ext = extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      const data = readFileSync(filePath);
      res.writeHead(200, { "Content-Type": contentType });
      res.end(data);
    } catch (err) {
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end(String(err));
    }
  });

  return new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(port, host, () => {
      resolvePromise(server);
    });
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  startTileServer(PORT, HOST).then(() => {
    console.log(`Geoverum local tile & asset server listening on http://${HOST}:${PORT}`);
  });
}
