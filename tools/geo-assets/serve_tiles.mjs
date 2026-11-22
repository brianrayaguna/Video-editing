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
import { existsSync, readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const GEO_ROOT = join(REPO_ROOT, "assets/geo");
const TILES_DIR = join(GEO_ROOT, "tiles");
const TILES_HQ_DIR = join(GEO_ROOT, "tiles_hq");
const DEM_DIR = join(GEO_ROOT, "dem");

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
const demFallbackCache = new Map();

/**
 * Resolve a lossless Terrarium DEM PNG tile `{z}/{x}/{y}` from `assets/geo/dem/`
 * with nearest-neighbor ancestor fallback so RGB elevation encoding stays uncorrupted.
 */
async function resolveDemBuffer(z, x, y) {
  const exactPath = join(DEM_DIR, String(z), String(x), `${y}.png`);
  if (existsSync(exactPath)) {
    return readFileSync(exactPath);
  }
  const cacheKey = `${z}/${x}/${y}`;
  if (demFallbackCache.has(cacheKey)) {
    return demFallbackCache.get(cacheKey);
  }
  for (let pz = z - 1; pz >= 0; pz--) {
    const scale = 2 ** (z - pz);
    const px = Math.floor(x / scale);
    const py = Math.floor(y / scale);
    const parentPath = join(DEM_DIR, String(pz), String(px), `${py}.png`);
    if (existsSync(parentPath)) {
      const subSize = Math.max(1, Math.floor(256 / scale));
      const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
      const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
      const buf = await sharp(parentPath)
        .extract({ left, top, width: subSize, height: subSize })
        .resize(256, 256, { kernel: sharp.kernel.nearest })
        .png()
        .toBuffer();
      if (demFallbackCache.size > 512) {
        const firstKey = demFallbackCache.keys().next().value;
        demFallbackCache.delete(firstKey);
      }
      demFallbackCache.set(cacheKey, buf);
      return buf;
    }
  }
  return null;
}

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
    const scale = 2 ** (z - pz);
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

const MAX_TILE_ZOOM = 22;

/** Zoom of the nearest existing tile at or above `{z}/{x}/{y}` (the tile itself first), or -1. */
function nearestTileLevel(z, x, y, exists) {
  for (let pz = z; pz >= 0; pz--) {
    const scale = 2 ** (z - pz);
    if (exists(pz, Math.floor(x / scale), Math.floor(y / scale))) return pz;
  }
  return -1;
}

/**
 * Choose the source for a `/tiles_hq` request: whichever of the HQ aerial and regular tile sets
 * holds the nearest ancestor (least upscaling) of `{z}/{x}/{y}`; HQ wins ties. Returns
 * `{ source: "hq" | "regular", level }`, or `null` when neither set covers the tile.
 */
export function pickHqTileSource(z, x, y, hasHq, hasRegular) {
  const hq = nearestTileLevel(z, x, y, hasHq);
  const regular = nearestTileLevel(z, x, y, hasRegular);
  if (hq < 0 && regular < 0) return null;
  return hq >= regular ? { source: "hq", level: hq } : { source: "regular", level: regular };
}

export function startTileServer(port = PORT, host = HOST) {
  const geoRootReal = existsSync(GEO_ROOT) ? realpathSync(GEO_ROOT) : resolve(GEO_ROOT);
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url || "/", `http://${host}:${port}`);
      let pathname;
      try {
        pathname = decodeURIComponent(url.pathname);
      } catch {
        res.writeHead(400, { "Content-Type": "text/plain" });
        res.end("Bad request");
        return;
      }

      res.setHeader("Access-Control-Allow-Origin", "*");

      if (pathname === "/health") {
        res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
        res.end(JSON.stringify({ status: "ok", root: "assets/geo" }));
        return;
      }

      const hybridMatch = pathname.match(/^\/tiles_hybrid\/(\d+)\/(\d+)\/(\d+)\.(?:jpg|jpeg)$/);
      if (hybridMatch) {
        const z = Number(hybridMatch[1]);
        const x = Number(hybridMatch[2]);
        const y = Number(hybridMatch[3]);
        if (z > MAX_TILE_ZOOM) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        let buf = null;
        if (z >= 12) {
          const exactHq = join(TILES_HQ_DIR, String(z), String(x), `${y}.jpg`);
          if (existsSync(exactHq)) {
            buf = readFileSync(exactHq);
          } else {
            for (let pz = z - 1; pz >= 12; pz--) {
              const scale = 2 ** (z - pz);
              const px = Math.floor(x / scale);
              const py = Math.floor(y / scale);
              const parentHq = join(TILES_HQ_DIR, String(pz), String(px), `${py}.jpg`);
              if (existsSync(parentHq)) {
                const subSize = Math.max(1, Math.floor(256 / scale));
                const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
                const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
                buf = await sharp(parentHq)
                  .extract({ left, top, width: subSize, height: subSize })
                  .resize(256, 256, { kernel: sharp.kernel.lanczos3 })
                  .jpeg({ quality: 88 })
                  .toBuffer();
                break;
              }
            }
          }
        }
        if (!buf) buf = await resolveTileBuffer(z, x, y);
        if (!buf) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        res.writeHead(200, {
          "Content-Type": "image/jpeg",
          "Cache-Control": "public, max-age=31536000, immutable",
        });
        res.end(buf);
        return;
      }

      const hqMatch = pathname.match(/^\/tiles_hq\/(\d+)\/(\d+)\/(\d+)\.(?:jpg|jpeg)$/);
      if (hqMatch) {
        const z = Number(hqMatch[1]);
        const x = Number(hqMatch[2]);
        const y = Number(hqMatch[3]);
        if (z > MAX_TILE_ZOOM) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        const tilePath = (dir) => (pz, px, py) => join(dir, String(pz), String(px), `${py}.jpg`);
        const hqPath = tilePath(TILES_HQ_DIR);
        const regularPath = tilePath(TILES_DIR);
        const pick = pickHqTileSource(
          z,
          x,
          y,
          (pz, px, py) => existsSync(hqPath(pz, px, py)),
          (pz, px, py) => existsSync(regularPath(pz, px, py)),
        );
        let buf = null;
        if (pick?.source === "hq") {
          const scale = 2 ** (z - pick.level);
          const parentHq = hqPath(pick.level, Math.floor(x / scale), Math.floor(y / scale));
          if (scale === 1) {
            buf = readFileSync(parentHq);
          } else {
            const subSize = Math.max(1, Math.floor(256 / scale));
            const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
            const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
            buf = await sharp(parentHq)
              .extract({ left, top, width: subSize, height: subSize })
              .resize(256, 256, { kernel: sharp.kernel.lanczos3 })
              .jpeg({ quality: 90 })
              .toBuffer();
          }
        }
        if (!buf) buf = await resolveTileBuffer(z, x, y);
        if (!buf) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        res.writeHead(200, {
          "Content-Type": "image/jpeg",
          "Cache-Control": "public, max-age=31536000, immutable",
        });
        res.end(buf);
        return;
      }

      const tileMatch = pathname.match(/^\/tiles\/(\d+)\/(\d+)\/(\d+)\.(?:jpg|jpeg)$/);
      if (tileMatch) {
        const z = Number(tileMatch[1]);
        const x = Number(tileMatch[2]);
        const y = Number(tileMatch[3]);
        if (z > MAX_TILE_ZOOM) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        const buf = await resolveTileBuffer(z, x, y);
        if (!buf) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        res.writeHead(200, {
          "Content-Type": "image/jpeg",
          "Cache-Control": "public, max-age=31536000, immutable",
        });
        res.end(buf);
        return;
      }

      const demMatch = pathname.match(/^\/dem\/(\d+)\/(\d+)\/(\d+)\.png$/);
      if (demMatch) {
        const z = Number(demMatch[1]);
        const x = Number(demMatch[2]);
        const y = Number(demMatch[3]);
        if (z > MAX_TILE_ZOOM) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("DEM tile not found");
          return;
        }
        const buf = await resolveDemBuffer(z, x, y);
        if (!buf) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("DEM tile not found");
          return;
        }
        res.writeHead(200, {
          "Content-Type": "image/png",
          "Cache-Control": "public, max-age=31536000, immutable",
        });
        res.end(buf);
        return;
      }

      const safeRel = normalize(pathname).replace(/^(\.\.(\/|\\|$))+/, "").replace(/^\/+/, "");
      const filePath = resolve(geoRootReal, safeRel);
      if (
        (filePath !== geoRootReal && !filePath.startsWith(geoRootReal + sep)) ||
        !existsSync(filePath) ||
        !statSync(filePath).isFile()
      ) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("Not found");
        return;
      }
      const realFile = realpathSync(filePath);
      if (realFile !== geoRootReal && !realFile.startsWith(geoRootReal + sep)) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("Not found");
        return;
      }

      const ext = extname(realFile).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      const data = readFileSync(realFile);
      res.writeHead(200, {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=31536000, immutable",
      });
      res.end(data);
    } catch {
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end("Internal server error");
    }
  });

  return new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(port, host, () => {
      resolvePromise(server);
    });
  });
}

if (process.argv[1] && import.meta.url === `file://${resolve(process.argv[1])}`) {
  startTileServer(PORT, HOST)
    .then(() => {
      console.log(`Geoverum local tile & asset server listening on http://${HOST}:${PORT}`);
    })
    .catch((err) => {
      console.error("Failed to start local tile server:", err);
      process.exit(1);
    });
}
