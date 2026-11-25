import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { gapForTile, isValidTileCoord, pickTileSource, startTileServer } from "./serve_tiles.mjs";

const require = createRequire(new URL("../../packages/hf-compiler-ts/package.json", import.meta.url));
const sharp = require("sharp");

/** Build an existence predicate from a list of `"z/x/y"` keys. */
function tiles(...keys) {
  const set = new Set(keys);
  return (z, x, y) => set.has(`${z}/${x}/${y}`);
}

test("exact HQ tile wins", () => {
  const pick = pickTileSource(12, 100, 200, tiles("12/100/200"), tiles("12/100/200"));
  assert.deepEqual(pick, { source: "hq", level: 12 });
});

test("exact regular tile beats a far HQ ancestor", () => {
  const pick = pickTileSource(12, 100, 200, tiles("4/1/3"), tiles("12/100/200"));
  assert.deepEqual(pick, { source: "regular", level: 12 });
});

test("closer HQ ancestor beats a farther regular ancestor", () => {
  const pick = pickTileSource(14, 400, 800, tiles("12/100/200"), tiles("10/25/50"));
  assert.deepEqual(pick, { source: "hq", level: 12 });
});

test("HQ wins a tie at the same ancestor level", () => {
  const pick = pickTileSource(14, 400, 800, tiles("12/100/200"), tiles("12/100/200"));
  assert.deepEqual(pick, { source: "hq", level: 12 });
});

test("low-zoom HQ ancestor still serves when no regular tile exists", () => {
  const pick = pickTileSource(9, 300, 150, tiles("0/0/0"), tiles());
  assert.deepEqual(pick, { source: "hq", level: 0 });
});

test("no tile anywhere returns null", () => {
  assert.equal(pickTileSource(9, 300, 150, tiles(), tiles()), null);
});

const HYBRID_HQ_MIN_ZOOM = 12;

test("hybrid: exact regular tile beats an upscaled HQ ancestor", () => {
  const pick = pickTileSource(
    14, 400, 800, tiles("12/100/200"), tiles("14/400/800"), HYBRID_HQ_MIN_ZOOM,
  );
  assert.deepEqual(pick, { source: "regular", level: 14 });
});

test("hybrid: closer HQ ancestor beats a farther regular ancestor", () => {
  const pick = pickTileSource(
    14, 400, 800, tiles("12/100/200"), tiles("10/25/50"), HYBRID_HQ_MIN_ZOOM,
  );
  assert.deepEqual(pick, { source: "hq", level: 12 });
});

test("hybrid: HQ tiles below the floor are ignored", () => {
  const pick = pickTileSource(10, 25, 50, tiles("10/25/50"), tiles("8/6/12"), HYBRID_HQ_MIN_ZOOM);
  assert.deepEqual(pick, { source: "regular", level: 8 });
});

test("hybrid: HQ ancestor below the floor does not count", () => {
  const pick = pickTileSource(14, 400, 800, tiles("11/50/100"), tiles(), HYBRID_HQ_MIN_ZOOM);
  assert.equal(pick, null);
});

test("gap recorded when only an ancestor tile exists", async () => {
  const { gapForTile } = await import("./serve_tiles.mjs");
  assert.deepEqual(gapForTile(12, 100, 200, tiles(), tiles("10/25/50")), { z: 12, x: 100, y: 200, level: 10 });
  assert.deepEqual(gapForTile(12, 100, 200, tiles(), tiles()), { z: 12, x: 100, y: 200, level: -1 });
});

test("no gap when the exact tile exists in the chosen set", async () => {
  const { gapForTile } = await import("./serve_tiles.mjs");
  assert.equal(gapForTile(12, 100, 200, tiles(), tiles("12/100/200")), null);
  assert.equal(gapForTile(13, 100, 200, tiles("13/100/200"), tiles("10/12/25"), 12), null);
});

test("no gap above the fetchable zoom ceiling or outside the web-mercator grid", () => {
  assert.equal(gapForTile(17, 1, 1, tiles("16/0/0"), tiles("0/0/0")), null);
  assert.equal(gapForTile(2, 4, 0, tiles(), tiles()), null);
  assert.equal(gapForTile(0, 1, 0, tiles(), tiles()), null);
  assert.equal(isValidTileCoord(14, 16384, 0), false);
  assert.equal(isValidTileCoord(14, 16383, 16383), true);
});

test("server records ancestor-served raster tiles only when asked", async (t) => {
  const root = new URL("../../assets/geo/tiles/0/0/0.jpg", import.meta.url);
  if (!existsSync(root)) {
    t.skip("local assets/geo/tiles/0/0/0.jpg not present");
    return;
  }
  const server = await startTileServer(0, "127.0.0.1", { recordGaps: true });
  try {
    const { port } = server.address();
    const get = async (p) => {
      const r = await fetch(`http://127.0.0.1:${port}${p}`);
      assert.equal(r.status, 200);
      return r.arrayBuffer();
    };
    await get("/tiles/0/0/0.jpg");
    assert.equal(server.tileGaps.size, 0);
    await get("/tiles/14/0/0.jpg");
    await get("/tiles_hybrid/14/0/0.jpg");
    assert.ok(server.tileGaps.has("14/0/0"));
    assert.ok(server.tileGaps.get("14/0/0").level < 14);
    await get("/tiles/20/0/0.jpg");
    assert.ok(!server.tileGaps.has("20/0/0"));
  } finally {
    await new Promise((r) => server.close(r));
  }
  const plain = await startTileServer(0, "127.0.0.1");
  try {
    assert.equal(plain.tileGaps, undefined);
  } finally {
    await new Promise((r) => plain.close(r));
  }
});

test("coverage gaps carry their routes and the regular route stops at the Sentinel-2 native zoom", async (t) => {
  const root = new URL("../../assets/geo/tiles/0/0/0.jpg", import.meta.url);
  if (!existsSync(root)) {
    t.skip("local assets/geo/tiles/0/0/0.jpg not present");
    return;
  }
  const server = await startTileServer(0, "127.0.0.1", { recordGaps: true });
  try {
    const { port } = server.address();
    const get = async (p) => {
      const r = await fetch(`http://127.0.0.1:${port}${p}`);
      assert.equal(r.status, 200);
      return r.arrayBuffer();
    };
    await get("/tiles/14/0/0.jpg");
    assert.deepEqual(server.tileGaps.get("14/0/0").routes, ["tiles"]);
    await get("/tiles_hybrid/14/0/0.jpg");
    assert.deepEqual(server.tileGaps.get("14/0/0").routes, ["tiles", "tiles_hybrid"]);
    await get("/tiles/15/0/0.jpg");
    assert.ok(!server.tileGaps.has("15/0/0"));
    await get("/tiles_hq/15/0/0.jpg");
    assert.deepEqual(server.tileGaps.get("15/0/0").routes, ["tiles_hq"]);
  } finally {
    await new Promise((r) => server.close(r));
  }
});

test("out-of-grid tile requests return 404 without poisoning tileGaps, and hybrid cache invalidates on new exact tile", async () => {
  const geoRoot = mkdtempSync(join(tmpdir(), "geo-srv-"));
  try {
    const parentPath = join(geoRoot, "tiles_hq", "14", "0", "0.jpg");
    mkdirSync(join(geoRoot, "tiles_hq", "14", "0"), { recursive: true });
    await sharp({
      create: { width: 256, height: 256, channels: 3, background: { r: 200, g: 40, b: 40 } },
    })
      .jpeg({ quality: 90 })
      .toFile(parentPath);

    const server = await startTileServer(0, "127.0.0.1", { recordGaps: true, geoRoot });
    try {
      const { port } = server.address();
      const bad = await fetch(`http://127.0.0.1:${port}/tiles/2/100/200.jpg`);
      assert.equal(bad.status, 404);
      assert.equal(server.tileGaps.size, 0);

      const first = await fetch(`http://127.0.0.1:${port}/tiles_hybrid/15/0/0.jpg`);
      assert.equal(first.status, 200);
      const firstPx = await sharp(Buffer.from(await first.arrayBuffer())).raw().toBuffer();

      const exactDir = join(geoRoot, "tiles_hq", "15", "0");
      mkdirSync(exactDir, { recursive: true });
      await sharp({
        create: { width: 256, height: 256, channels: 3, background: { r: 40, g: 200, b: 40 } },
      })
        .jpeg({ quality: 90 })
        .toFile(join(exactDir, "0.jpg"));

      const second = await fetch(`http://127.0.0.1:${port}/tiles_hybrid/15/0/0.jpg`);
      assert.equal(second.status, 200);
      const secondPx = await sharp(Buffer.from(await second.arrayBuffer())).raw().toBuffer();
      assert.ok(secondPx[1] > firstPx[1] + 50, "cache should reflect newly installed exact tile");
    } finally {
      await new Promise((r) => server.close(r));
    }
  } finally {
    rmSync(geoRoot, { recursive: true, force: true });
  }
});

test("listTilesRecursive ignores non-numeric jpg files and non-directory levels", async () => {
  const { listTilesRecursive } = await import("./build_tiles.mjs");
  const dir = mkdtempSync(join(tmpdir(), "geo-build-"));
  try {
    mkdirSync(join(dir, "10", "5"), { recursive: true });
    writeFileSync(join(dir, "10", "5", "7.jpg"), "ok");
    writeFileSync(join(dir, "10", "5", "preview.jpg"), "ignore");
    writeFileSync(join(dir, "not_a_dir"), "ignore");
    const items = listTilesRecursive(dir);
    assert.equal(items.length, 1);
    assert.deepEqual({ z: items[0].z, x: items[0].x, y: items[0].y }, { z: 10, x: 5, y: 7 });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("coverageReport lists every gap once and groups them by route", async () => {
  const { coverageReport } = await import("./serve_tiles.mjs");
  const gaps = new Map([
    ["14/3/4", { z: 14, x: 3, y: 4, level: 12, routes: ["tiles", "tiles_hybrid"] }],
    ["9/1/1", { z: 9, x: 1, y: 1, level: 8, routes: ["tiles_hq"] }],
    ["17/0/0", { z: 17, x: 0, y: 0, level: 14, routes: ["tiles_hq"] }],
  ]);
  assert.deepEqual(coverageReport(gaps), {
    tiles: [[9, 1, 1], [14, 3, 4]],
    by_route: { tiles: [[14, 3, 4]], tiles_hq: [[9, 1, 1]], tiles_hybrid: [[14, 3, 4]] },
  });
  assert.deepEqual(coverageReport(new Map()), {
    tiles: [],
    by_route: { tiles: [], tiles_hq: [], tiles_hybrid: [] },
  });
});

test("gradeRgb pulls pure ocean blue toward teal and keeps the buffer size", async () => {
  const { gradeRgb } = await import("./build_tiles.mjs");
  const px = Buffer.from([10, 40, 120, 10, 40, 120]);
  const out = gradeRgb(px, 10);
  assert.equal(out.length, px.length);
  assert.ok(out[1] > 40, `green ${out[1]}`);
  assert.ok(out[2] < 120, `blue ${out[2]}`);
});

test("the server starts when launched through a symlink in a directory with a space", async () => {
  const dir = mkdtempSync(join(tmpdir(), "geo tiles "));
  const link = join(dir, "serve tiles.mjs");
  symlinkSync(fileURLToPath(new URL("./serve_tiles.mjs", import.meta.url)), link);
  const child = spawn(process.execPath, [link], {
    env: { ...process.env, PORT: "0", HOST: "127.0.0.1" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  try {
    const started = await new Promise((resolveStarted) => {
      let out = "";
      const timer = setTimeout(() => resolveStarted(false), 8000);
      child.stdout.on("data", (chunk) => {
        out += chunk;
        if (out.includes("listening")) {
          clearTimeout(timer);
          resolveStarted(true);
        }
      });
      child.on("exit", () => {
        clearTimeout(timer);
        resolveStarted(out.includes("listening"));
      });
    });
    assert.equal(started, true, "main entry point did not run");
  } finally {
    child.kill();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("projectTilesDir serves exact and ancestor-cropped tiles on /tiles_project/", async () => {
  const geoRoot = mkdtempSync(join(tmpdir(), "geo-proj-"));
  const projectTilesDir = join(geoRoot, "project_tiles");
  try {
    mkdirSync(join(projectTilesDir, "13", "6460"), { recursive: true });
    await sharp({
      create: { width: 256, height: 256, channels: 3, background: { r: 24, g: 168, b: 96 } },
    })
      .jpeg({ quality: 90 })
      .toFile(join(projectTilesDir, "13", "6460", "4072.jpg"));

    const server = await startTileServer(0, "127.0.0.1", { geoRoot, projectTilesDir });
    try {
      const { port } = server.address();
      const exact = await fetch(`http://127.0.0.1:${port}/tiles_project/13/6460/4072.jpg`);
      assert.equal(exact.status, 200);
      const child = await fetch(`http://127.0.0.1:${port}/tiles_project/14/12920/8144.jpg`);
      assert.equal(child.status, 200);
      const px = await sharp(Buffer.from(await child.arrayBuffer())).raw().toBuffer();
      assert.ok(px[1] > 120, "expected green ancestor crop from projectTilesDir");
    } finally {
      await new Promise((r) => server.close(r));
    }
  } finally {
    rmSync(geoRoot, { recursive: true, force: true });
  }
});

test("projectModelsDir serves .glb and .wasm with proper MIME and blocks traversal, and project tile routes record coverage gaps", async () => {
  const geoRoot = mkdtempSync(join(tmpdir(), "geo-mod-"));
  const projectModelsDir = join(geoRoot, "proj_models");
  try {
    mkdirSync(join(geoRoot, "tiles", "10", "5"), { recursive: true });
    mkdirSync(projectModelsDir, { recursive: true });
    await sharp({
      create: { width: 256, height: 256, channels: 3, background: { r: 20, g: 80, b: 120 } },
    })
      .jpeg({ quality: 90 })
      .toFile(join(geoRoot, "tiles", "10", "5", "5.jpg"));
    writeFileSync(join(projectModelsDir, "tower.glb"), Buffer.from("glTF-binary-stub"));
    writeFileSync(join(projectModelsDir, "decoder.wasm"), Buffer.from("wasm-stub"));
    writeFileSync(join(geoRoot, "secret.txt"), "secret");

    const server = await startTileServer(0, "127.0.0.1", {
      geoRoot,
      projectModelsDir,
      recordGaps: true,
    });
    try {
      const { port } = server.address();
      const glbRes = await fetch(`http://127.0.0.1:${port}/project_models/tower.glb`);
      assert.equal(glbRes.status, 200);
      assert.equal(glbRes.headers.get("content-type"), "model/gltf-binary");

      const wasmRes = await fetch(`http://127.0.0.1:${port}/project_models/decoder.wasm`);
      assert.equal(wasmRes.status, 200);
      assert.equal(wasmRes.headers.get("content-type"), "application/wasm");

      const badRes = await fetch(`http://127.0.0.1:${port}/project_models/..%2fsecret.txt`);
      assert.equal(badRes.status, 404);

      const tileRes = await fetch(`http://127.0.0.1:${port}/tiles_project/14/80/80.jpg`);
      assert.equal(tileRes.status, 200);
      assert.ok(server.tileGaps.has("14/80/80"));
      assert.deepEqual(server.tileGaps.get("14/80/80").routes, ["tiles_project"]);
    } finally {
      await new Promise((r) => server.close(r));
    }
  } finally {
    rmSync(geoRoot, { recursive: true, force: true });
  }
});
