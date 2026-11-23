import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { pickTileSource, startTileServer } from "./serve_tiles.mjs";

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

test("no gap above the fetchable zoom ceiling", async () => {
  const { gapForTile } = await import("./serve_tiles.mjs");
  assert.equal(gapForTile(17, 1, 1, tiles("16/0/0"), tiles("0/0/0")), null);
});

test("server records ancestor-served raster tiles only when asked", async () => {
  const { existsSync } = await import("node:fs");
  const root = new URL("../../assets/geo/tiles/0/0/0.jpg", import.meta.url);
  if (!existsSync(root)) return;
  const server = await startTileServer(0, "127.0.0.1", { recordGaps: true });
  try {
    const { port } = server.address();
    const get = (p) => fetch(`http://127.0.0.1:${port}${p}`).then((r) => r.arrayBuffer());
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

test("coverage gaps carry their routes and the regular route stops at the Sentinel-2 native zoom", async () => {
  const { existsSync } = await import("node:fs");
  const root = new URL("../../assets/geo/tiles/0/0/0.jpg", import.meta.url);
  if (!existsSync(root)) return;
  const server = await startTileServer(0, "127.0.0.1", { recordGaps: true });
  try {
    const { port } = server.address();
    const get = (p) => fetch(`http://127.0.0.1:${port}${p}`).then((r) => r.arrayBuffer());
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
