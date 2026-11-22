import assert from "node:assert/strict";
import { test } from "node:test";

import { pickTileSource } from "./serve_tiles.mjs";

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
