#!/usr/bin/env node
/**
 * Local offline HTTP asset & XYZ tile server for Geoverum compositions and basemap baking.
 *
 * Serves:
 * - `GET /tiles/{z}/{x}/{y}.jpg` from `assets/geo/tiles/{z}/{x}/{y}.jpg` with automatic
 *   parent-tile quadrant cropping via `sharp` when an out-of-AOI high-zoom tile is requested.
 * - `GET /tiles_hybrid/{z}/{x}/{y}.jpg`: nearest of the graded and high-resolution sets, with
 *   high-resolution tiles passed through the same documentary grade as `assets/geo/tiles/`.
 * - `GET /tiles_project/{z}/{x}/{y}.jpg` and `/tiles_project_graded/{z}/{x}/{y}.jpg`: nearest of
 *   the project-scoped tile directory (when configured) and `assets/geo/tiles/`.
 * - `GET /vector/*`, `/fonts/*`, `/flags/*`, `/icons/*`, `/vendor/*` from `assets/geo/`.
 * - `GET /health` -> `200 OK` JSON status.
 */

import { createServer } from "node:http";
import { existsSync, readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

import { gradeRgb } from "./build_tiles.mjs";
import { isMainModule } from "./entry_point.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../..");
const require = createRequire(join(REPO_ROOT, "packages/hf-compiler-ts/package.json"));
const sharp = require("sharp");

const GEO_ROOT = join(REPO_ROOT, "assets/geo");
const TILES_DIR = join(GEO_ROOT, "tiles");
const TILES_HQ_DIR = join(GEO_ROOT, "tiles_hq");
const DEM_DIR = join(GEO_ROOT, "dem");

const PORT = process.env.PORT !== undefined ? Number(process.env.PORT) : 8765;
const HOST = process.env.HOST || "127.0.0.1";

const MIME_TYPES = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/geo+json; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".ttf": "font/ttf",
  ".woff2": "font/woff2",
  ".glb": "model/gltf-binary",
  ".gltf": "model/gltf+json",
  ".wasm": "application/wasm",
};

const MAX_TILE_ZOOM = 22;

export function isValidTileCoord(z, x, y) {
  if (!Number.isSafeInteger(z) || !Number.isSafeInteger(x) || !Number.isSafeInteger(y)) return false;
  if (z < 0 || z > MAX_TILE_ZOOM) return false;
  const limit = 2 ** z;
  return x >= 0 && x < limit && y >= 0 && y < limit;
}

function setBoundedCache(cache, key, val, limit) {
  if (cache.size >= limit) {
    const firstKey = cache.keys().next().value;
    cache.delete(firstKey);
  }
  cache.set(key, val);
}

/**
 * Resolve a lossless Terrarium DEM PNG tile `{z}/{x}/{y}` from `demDir`
 * with nearest-neighbor ancestor fallback so RGB elevation encoding stays uncorrupted.
 */
async function resolveDemBuffer(demDir, demFallbackCache, z, x, y) {
  const exactPath = join(demDir, String(z), String(x), `${y}.png`);
  if (existsSync(exactPath)) {
    return readFileSync(exactPath);
  }
  for (let pz = z - 1; pz >= 0; pz--) {
    const scale = 2 ** (z - pz);
    const px = Math.floor(x / scale);
    const py = Math.floor(y / scale);
    const parentPath = join(demDir, String(pz), String(px), `${py}.png`);
    if (existsSync(parentPath)) {
      const mtimeMs = statSync(parentPath).mtimeMs;
      const cacheKey = `${z}/${x}/${y}:${parentPath}:${mtimeMs}`;
      if (demFallbackCache.has(cacheKey)) {
        return demFallbackCache.get(cacheKey);
      }
      const subSize = Math.max(1, Math.floor(256 / scale));
      const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
      const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
      const buf = await sharp(parentPath)
        .extract({ left, top, width: subSize, height: subSize })
        .resize(256, 256, { kernel: sharp.kernel.nearest })
        .png()
        .toBuffer();
      setBoundedCache(demFallbackCache, cacheKey, buf, 512);
      return buf;
    }
  }
  return null;
}

/**
 * Resolve a tile `{z}/{x}/{y}` from disk, or synthesize it deterministically by cropping
 * the nearest ancestor tile in `tilesDir` so out-of-AOI tiles never 404.
 */
async function resolveTileBuffer(tilesDir, fallbackCache, z, x, y) {
  const exactPath = join(tilesDir, String(z), String(x), `${y}.jpg`);
  if (existsSync(exactPath)) {
    return readFileSync(exactPath);
  }

  for (let pz = z - 1; pz >= 0; pz--) {
    const scale = 2 ** (z - pz);
    const px = Math.floor(x / scale);
    const py = Math.floor(y / scale);
    const parentPath = join(tilesDir, String(pz), String(px), `${py}.jpg`);
    if (existsSync(parentPath)) {
      const mtimeMs = statSync(parentPath).mtimeMs;
      const cacheKey = `${z}/${x}/${y}:${parentPath}:${mtimeMs}`;
      if (fallbackCache.has(cacheKey)) {
        return fallbackCache.get(cacheKey);
      }
      const subSize = Math.max(1, Math.floor(256 / scale));
      const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
      const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
      const buf = await sharp(parentPath)
        .extract({ left, top, width: subSize, height: subSize })
        .resize(256, 256, { kernel: sharp.kernel.lanczos3 })
        .jpeg({ quality: 85 })
        .toBuffer();
      setBoundedCache(fallbackCache, cacheKey, buf, 1024);
      return buf;
    }
  }
  return null;
}

/** Zoom of the nearest existing tile at or above `{z}/{x}/{y}` (the tile itself first), or -1. */
function nearestTileLevel(z, x, y, exists) {
  for (let pz = z; pz >= 0; pz--) {
    const scale = 2 ** (z - pz);
    if (exists(pz, Math.floor(x / scale), Math.floor(y / scale))) return pz;
  }
  return -1;
}

/** HQ aerial tiles below this zoom are never used by `/tiles_hybrid` (graded tiles serve there). */
const HYBRID_HQ_MIN_ZOOM = 12;

/**
 * Choose the source for a tile request: whichever of the HQ aerial and regular tile sets holds
 * the nearest ancestor (least upscaling) of `{z}/{x}/{y}`; HQ wins ties. HQ tiles below
 * `hqMinZoom` are ignored. Returns `{ source: "hq" | "regular", level }`, or `null` when
 * neither set covers the tile.
 */
export function pickTileSource(z, x, y, hasHq, hasRegular, hqMinZoom = 0) {
  const hq = nearestTileLevel(z, x, y, (pz, px, py) => pz >= hqMinZoom && hasHq(pz, px, py));
  const regular = nearestTileLevel(z, x, y, hasRegular);
  if (hq < 0 && regular < 0) return null;
  return hq >= regular ? { source: "hq", level: hq } : { source: "regular", level: regular };
}

const noTile = () => false;

/** Highest zoom the tile fetchers can supply; requests above it are never reported as gaps. */
export const MAX_FETCH_ZOOM = 16;

/**
 * Highest fetchable zoom per raster route. `/tiles` serves the graded Sentinel-2 set, whose
 * native resolution ends at z14; the HQ routes can also draw on orthoimagery to z16.
 */
export const ROUTE_MAX_FETCH_ZOOM = Object.freeze({ tiles: 14, tiles_hq: MAX_FETCH_ZOOM, tiles_hybrid: MAX_FETCH_ZOOM });
const ALL_COVERAGE_MAX_ZOOM = Object.freeze({
  ...ROUTE_MAX_FETCH_ZOOM,
  tiles_project: MAX_FETCH_ZOOM,
  tiles_project_graded: MAX_FETCH_ZOOM,
});

/**
 * Coverage report for recorded gaps: every gap once under `tiles`, plus the gaps each raster
 * route requested under `by_route`, all sorted by z, x, y. Gaps above `MAX_FETCH_ZOOM` are dropped.
 */
export function coverageReport(tileGaps) {
  const gaps = [...tileGaps.values()]
    .filter((g) => g.z <= MAX_FETCH_ZOOM)
    .sort((a, b) => a.z - b.z || a.x - b.x || a.y - b.y);
  const byRoute = Object.fromEntries(Object.keys(ROUTE_MAX_FETCH_ZOOM).map((route) => [route, []]));
  for (const g of gaps) {
    for (const route of g.routes || []) {
      if (!(route in byRoute) && route in ALL_COVERAGE_MAX_ZOOM) byRoute[route] = [];
      byRoute[route]?.push([g.z, g.x, g.y]);
    }
  }
  return { tiles: gaps.map((g) => [g.z, g.x, g.y]), by_route: byRoute };
}

/**
 * Coverage gap for a tile request: `{ z, x, y, level }` when the chosen source would serve it
 * by upscaling an ancestor at `level` (`-1` when nothing covers it), `null` when an exact tile
 * exists, coordinates are out of grid, or `z` is above `maxZoom`.
 */
export function gapForTile(z, x, y, hasHq, hasRegular, hqMinZoom = 0, maxZoom = MAX_FETCH_ZOOM) {
  if (!isValidTileCoord(z, x, y) || z > maxZoom) return null;
  const pick = pickTileSource(z, x, y, hasHq, hasRegular, hqMinZoom);
  if (!pick) return { z, x, y, level: -1 };
  return pick.level < z ? { z, x, y, level: pick.level } : null;
}

/**
 * Serve `{z}/{x}/{y}` from the HQ set when it holds the nearest ancestor (cropping and upscaling
 * that ancestor's quadrant), otherwise from the regular set via `resolveTileBuffer`.
 */
async function resolveHqOrRegularTile(
  tilesDir,
  tilesHqDir,
  caches,
  z,
  x,
  y,
  hqMinZoom,
  jpegQuality,
  grade = false
) {
  const hqTilePath = (pz, px, py) => join(tilesHqDir, String(pz), String(px), `${py}.jpg`);
  const hasHqTile = (pz, px, py) => existsSync(hqTilePath(pz, px, py));
  const hasRegularTile = (pz, px, py) => existsSync(join(tilesDir, String(pz), String(px), `${py}.jpg`));

  const pick = pickTileSource(z, x, y, hasHqTile, hasRegularTile, hqMinZoom);
  if (pick?.source !== "hq") return resolveTileBuffer(tilesDir, caches.fallbackCache, z, x, y);

  const scale = 2 ** (z - pick.level);
  const parentHq = hqTilePath(pick.level, Math.floor(x / scale), Math.floor(y / scale));
  const mtimeMs = statSync(parentHq).mtimeMs;
  const cacheKey = `${z}/${x}/${y}:${parentHq}:${mtimeMs}:${jpegQuality}:${grade ? 1 : 0}`;
  if (caches.gradedHqCache.has(cacheKey)) {
    return caches.gradedHqCache.get(cacheKey);
  }

  let pipeline = sharp(parentHq);
  if (scale > 1) {
    const subSize = Math.max(1, Math.floor(256 / scale));
    const left = Math.min(256 - subSize, Math.round(((x % scale) / scale) * 256));
    const top = Math.min(256 - subSize, Math.round(((y % scale) / scale) * 256));
    pipeline = pipeline
      .extract({ left, top, width: subSize, height: subSize })
      .resize(256, 256, { kernel: sharp.kernel.lanczos3 });
  }

  let out;
  if (grade) {
    const { data, info } = await pipeline
      .flatten({ background: { r: 10, g: 56, b: 70 } })
      .removeAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    out = await sharp(gradeRgb(data, z), {
      raw: { width: info.width, height: info.height, channels: 3 },
    })
      .jpeg({ quality: jpegQuality })
      .toBuffer();
  } else if (scale === 1) {
    return readFileSync(parentHq);
  } else {
    out = await pipeline.jpeg({ quality: jpegQuality }).toBuffer();
  }

  setBoundedCache(caches.gradedHqCache, cacheKey, out, 1024);
  return out;
}

/**
 * Start the asset and tile server. With `{ recordGaps: true }`, `server.tileGaps` collects every
 * raster tile request (`/tiles`, `/tiles_hybrid`, `/tiles_hq`) that is served by upscaling an
 * ancestor and that the route's fetcher could fill (`ROUTE_MAX_FETCH_ZOOM`), keyed `"z/x/y"` ->
 * `{ z, x, y, level, routes }`, for coverage passes.
 */
export function startTileServer(port = PORT, host = HOST, options = {}) {
  const geoRoot = options.geoRoot ? resolve(options.geoRoot) : GEO_ROOT;
  const tilesDir = join(geoRoot, "tiles");
  const tilesHqDir = join(geoRoot, "tiles_hq");
  const projectTilesDir = options.projectTilesDir ? resolve(options.projectTilesDir) : null;
  const projectModelsDir = options.projectModelsDir ? resolve(options.projectModelsDir) : null;
  const projectModelsReal = projectModelsDir && existsSync(projectModelsDir) ? realpathSync(projectModelsDir) : projectModelsDir;
  const demDir = join(geoRoot, "dem");
  const hasHqTile = (pz, px, py) => existsSync(join(tilesHqDir, String(pz), String(px), `${py}.jpg`));
  const hasProjectTile = (pz, px, py) => Boolean(projectTilesDir) && existsSync(join(projectTilesDir, String(pz), String(px), `${py}.jpg`));
  const hasRegularTile = (pz, px, py) => existsSync(join(tilesDir, String(pz), String(px), `${py}.jpg`));
  const caches = {
    fallbackCache: new Map(),
    demFallbackCache: new Map(),
    gradedHqCache: new Map(),
  };

  const geoRootReal = existsSync(geoRoot) ? realpathSync(geoRoot) : resolve(geoRoot);
  const tileGaps = options.recordGaps ? new Map() : null;
  const noteGap = (route, z, x, y, hasHq, hqMinZoom) => {
    if (!tileGaps) return;
    const gap = gapForTile(z, x, y, hasHq, hasRegularTile, hqMinZoom, ALL_COVERAGE_MAX_ZOOM[route] ?? MAX_FETCH_ZOOM);
    if (!gap) return;
    const key = `${z}/${x}/${y}`;
    const known = tileGaps.get(key);
    if (known) {
      if (!known.routes.includes(route)) known.routes = [...known.routes, route].sort();
      known.level = Math.min(known.level, gap.level);
    } else {
      tileGaps.set(key, { ...gap, routes: [route] });
    }
  };
  const urlHost = host.includes(":") && !host.startsWith("[") ? `[${host}]` : host;
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url || "/", `http://${urlHost}:${port}`);
      let pathname;
      try {
        pathname = decodeURIComponent(url.pathname);
      } catch {
        res.writeHead(400, { "Content-Type": "text/plain" });
        res.end("Bad request");
        return;
      }
      if (pathname.includes("\0")) {
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
        if (!isValidTileCoord(z, x, y)) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        noteGap("tiles_hybrid", z, x, y, hasHqTile, HYBRID_HQ_MIN_ZOOM);
        const buf = await resolveHqOrRegularTile(
          tilesDir,
          tilesHqDir,
          caches,
          z,
          x,
          y,
          HYBRID_HQ_MIN_ZOOM,
          88,
          true
        );
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
        if (!isValidTileCoord(z, x, y)) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        noteGap("tiles_hq", z, x, y, hasHqTile, 0);
        const buf = await resolveHqOrRegularTile(tilesDir, tilesHqDir, caches, z, x, y, 0, 90);
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

      const projectMatch = pathname.match(/^\/tiles_project(_graded)?\/(\d+)\/(\d+)\/(\d+)\.(?:jpg|jpeg)$/);
      if (projectMatch) {
        const gradeProject = Boolean(projectMatch[1]);
        const routeName = gradeProject ? "tiles_project_graded" : "tiles_project";
        const z = Number(projectMatch[2]);
        const x = Number(projectMatch[3]);
        const y = Number(projectMatch[4]);
        if (!isValidTileCoord(z, x, y)) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        noteGap(routeName, z, x, y, projectTilesDir ? hasProjectTile : noTile, 0);
        let buf = null;
        if (projectTilesDir) {
          buf = await resolveHqOrRegularTile(tilesDir, projectTilesDir, caches, z, x, y, 0, 90, gradeProject);
        } else {
          buf = await resolveTileBuffer(tilesDir, caches.fallbackCache, z, x, y);
        }
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
        if (!isValidTileCoord(z, x, y)) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Tile not found");
          return;
        }
        noteGap("tiles", z, x, y, noTile, 0);
        const buf = await resolveTileBuffer(tilesDir, caches.fallbackCache, z, x, y);
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
        if (!isValidTileCoord(z, x, y)) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("DEM tile not found");
          return;
        }
        const buf = await resolveDemBuffer(demDir, caches.demFallbackCache, z, x, y);
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

      if (pathname.startsWith("/project_models/")) {
        if (!projectModelsReal) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Not found");
          return;
        }
        const rawModelRel = pathname.slice("/project_models/".length);
        if (rawModelRel.split(/[\\/]/).includes("..")) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Not found");
          return;
        }
        const relModel = normalize(rawModelRel).replace(/^\/+/, "");
        const modelPath = resolve(projectModelsReal, relModel);
        if (
          (modelPath !== projectModelsReal && !modelPath.startsWith(projectModelsReal + sep)) ||
          !existsSync(modelPath) ||
          !statSync(modelPath).isFile()
        ) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Not found");
          return;
        }
        const realModel = realpathSync(modelPath);
        if (realModel !== projectModelsReal && !realModel.startsWith(projectModelsReal + sep)) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          res.end("Not found");
          return;
        }
        const ext = extname(realModel).toLowerCase();
        res.writeHead(200, {
          "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
          "Cache-Control": "public, max-age=31536000, immutable",
        });
        res.end(readFileSync(realModel));
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
    } catch (err) {
      console.error("Tile server request error:", err);
      if (!res.headersSent) {
        res.writeHead(500, { "Content-Type": "text/plain" });
      }
      res.end("Internal server error");
    }
  });

  if (tileGaps) server.tileGaps = tileGaps;

  return new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(port, host, () => {
      resolvePromise(server);
    });
  });
}

if (isMainModule(import.meta.url)) {
  if (!Number.isInteger(PORT) || PORT < 0 || PORT > 65535) {
    console.error(`Invalid PORT: ${process.env.PORT}`);
    process.exit(1);
  }
  startTileServer(PORT, HOST)
    .then((server) => {
      const addr = server.address();
      const boundPort = typeof addr === "object" && addr ? addr.port : PORT;
      const displayHost = HOST.includes(":") && !HOST.startsWith("[") ? `[${HOST}]` : HOST;
      console.log(`Geoverum local tile & asset server listening on http://${displayHost}:${boundPort}`);
    })
    .catch((err) => {
      console.error("Failed to start local tile server:", err);
      process.exit(1);
    });
}
