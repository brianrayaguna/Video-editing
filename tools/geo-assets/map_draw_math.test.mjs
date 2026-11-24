import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  clothWaveStops,
  coverRect,
  cutBlurAmount,
  nearestVertexIndex,
  organicRevealRadii,
  perimeterPartialPaths,
  polygonRings,
  ringClusters,
  scaledWidth,
  signedArea,
  wipeFrontEdge,
} from "./map_draw_math.mjs";

const SQUARE = [
  { x: 0, y: 0 },
  { x: 100, y: 0 },
  { x: 100, y: 100 },
  { x: 0, y: 100 },
];
const SMALL = [
  { x: 200, y: 200 },
  { x: 240, y: 200 },
  { x: 240, y: 240 },
  { x: 200, y: 240 },
];

function pathLength(path) {
  let len = 0;
  for (let i = 1; i < path.length; i++) {
    len += Math.hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);
  }
  return len;
}

function close(a, b, eps = 1e-6) {
  return Math.abs(a - b) <= eps;
}

test("one head at half progress covers half the perimeter", () => {
  const paths = perimeterPartialPaths([SQUARE], 0.5, { heads: 1 });
  assert.equal(paths.length, 1);
  assert.ok(close(pathLength(paths[0]), 200));
  assert.deepEqual(paths[0][0], { x: 0, y: 0 });
  assert.deepEqual(paths[0].at(-1), { x: 100, y: 100 });
});

test("two heads run in opposite directions, a quarter each", () => {
  const paths = perimeterPartialPaths([SQUARE], 0.5, { heads: 2 });
  assert.equal(paths.length, 2);
  for (const p of paths) assert.ok(close(pathLength(p), 100));
  const ends = paths.map((p) => p.at(-1));
  assert.deepEqual(ends, [{ x: 100, y: 0 }, { x: 0, y: 100 }]);
});

test("direction -1 walks the ring backwards", () => {
  const [path] = perimeterPartialPaths([SQUARE], 0.25, { heads: 1, direction: -1 });
  assert.deepEqual(path.at(-1), { x: 0, y: 100 });
});

test("progress 1 returns each ring closed; progress 0 returns nothing", () => {
  const full = perimeterPartialPaths([SQUARE], 1, { heads: 2 });
  assert.equal(full.length, 1);
  assert.ok(close(pathLength(full[0]), 400));
  assert.deepEqual(full[0][0], full[0].at(-1));
  assert.deepEqual(perimeterPartialPaths([SQUARE], 0, { heads: 2 }), []);
});

test("every ring is drawn by the same fraction of its own length", () => {
  const paths = perimeterPartialPaths([SQUARE, SMALL], 0.25, { heads: 1 });
  assert.equal(paths.length, 2);
  assert.ok(close(pathLength(paths[0]), 100));
  assert.ok(close(pathLength(paths[1]), 40));
  const done = perimeterPartialPaths([SQUARE, SMALL], 1, { heads: 2 });
  assert.equal(done.length, 2);
  assert.ok(close(pathLength(done[1]), 160));
});

test("explicitly closed rings and per-ring start indices", () => {
  const closed = [...SQUARE, { x: 0, y: 0 }];
  const [path] = perimeterPartialPaths([closed], 0.5, { heads: 1, startIndex: [2] });
  assert.ok(close(pathLength(path), 200));
  assert.deepEqual(path[0], { x: 100, y: 100 });
  assert.deepEqual(path.at(-1), { x: 0, y: 0 });
  assert.equal(nearestVertexIndex(SQUARE, { x: 96, y: 97 }), 2);
});

test("degenerate rings are skipped", () => {
  const paths = perimeterPartialPaths([[{ x: 1, y: 1 }], SQUARE], 0.5, { heads: 1 });
  assert.equal(paths.length, 1);
  const zeroLen = [{ x: 5, y: 5 }, { x: 5, y: 5 }, { x: 5, y: 5 }];
  assert.deepEqual(perimeterPartialPaths([zeroLen], 0.5, { heads: 1 }), []);
  assert.deepEqual(perimeterPartialPaths([zeroLen], 1.0, { heads: 2 }), []);
});

test("signedArea is positive for clockwise rings in screen space (y down)", () => {
  assert.ok(signedArea(SQUARE) > 0);
  assert.ok(signedArea([...SQUARE].reverse()) < 0);
});

test("coverRect is the smallest centred rect of the aspect covering the bounds", () => {
  const r = coverRect({ minX: 0, minY: 0, maxX: 100, maxY: 50 }, 1.5);
  assert.ok(close(r.w, 100));
  assert.ok(close(r.h, 100 / 1.5));
  assert.ok(close(r.x, 0));
  assert.ok(close(r.y + r.h / 2, 25));
  const tall = coverRect({ minX: 0, minY: 0, maxX: 10, maxY: 100 }, 2);
  assert.ok(close(tall.h, 100));
  assert.ok(close(tall.w, 200));
  assert.ok(close(tall.x + tall.w / 2, 5));
  const inf = coverRect({ minX: 0, minY: 0, maxX: 100, maxY: 50 }, Number.POSITIVE_INFINITY);
  assert.ok(Number.isFinite(inf.w) && Number.isFinite(inf.h) && Number.isFinite(inf.x));
});

test("scaledWidth doubles per zoom level and clamps", () => {
  assert.equal(scaledWidth(4, 13, null), 4);
  assert.equal(scaledWidth(4, 13, ""), 4);
  assert.equal(scaledWidth(4, 13, false), 4);
  assert.equal(scaledWidth(4, 13, 10, Number.NaN), 4);
  assert.equal(scaledWidth(4, Number.NaN, 10), 4);
  assert.equal(scaledWidth(4, 11, 10), 8);
  assert.equal(scaledWidth(4, 12, 10), 16);
  assert.equal(scaledWidth(4, 20, 10), 24);
  assert.ok(close(scaledWidth(4, 5, 10), 1.6));
  assert.ok(close(scaledWidth(4, 12, 10, 0.5), 8));
  assert.ok(close(scaledWidth(4, 12, 10, 1, 0.4, 3), 12));
});

test("module is dependency-free so it can be inlined into the page", () => {
  const src = readFileSync(new URL("./map_draw_math.mjs", import.meta.url), "utf8");
  assert.ok(!/^\s*import\s/m.test(src));
  assert.ok(!/<\/script/i.test(src));
  assert.doesNotThrow(() => new Function(src.replace(/^export\s+/gm, "")));
});

test("wipeFrontEdge names the travel direction of the reveal", () => {
  const b = { minX: 0, maxX: 100, minY: 0, maxY: 200 };
  const up = wipeFrontEdge("wipe_up", 0.3, b);
  assert.equal(up.horiz, false);
  assert.ok(up.front > 100 && up.back > up.front, "wipe_up rises from the bottom edge");
  const down = wipeFrontEdge("wipe_down", 0.3, b);
  assert.ok(down.front < 100 && down.back < down.front, "wipe_down falls from the top edge");
  const right = wipeFrontEdge("wipe_right", 0.3, b);
  assert.equal(right.horiz, true);
  assert.ok(right.front < 50 && right.back < right.front, "wipe_right enters at the left edge");
  const left = wipeFrontEdge("wipe_left", 0.3, b);
  assert.ok(left.front > 50 && left.back > left.front, "wipe_left enters at the right edge");
  const doneUp = wipeFrontEdge("wipe_up", 1, b);
  assert.ok(doneUp.back <= b.minY + 1e-9, "fully revealed at progress 1");
  const startRight = wipeFrontEdge("wipe_right", 0, b);
  assert.ok(startRight.front <= b.minX + 1e-9, "nothing revealed at progress 0");
});

test("cutBlurAmount peaks on the cut frames and decays into the act", () => {
  const fps = 30;
  const total = 120;
  assert.equal(cutBlurAmount(0, total, fps, 0.4, 0.4, 0.12), 0.12);
  assert.equal(cutBlurAmount(total - 1, total, fps, 0.4, 0.4, 0.12), 0.12);
  const a3 = cutBlurAmount(3, total, fps, 0.4, 0.4, 0.12);
  const a6 = cutBlurAmount(6, total, fps, 0.4, 0.4, 0.12);
  assert.ok(a3 < 0.12 && a6 < a3 && a6 > 0, "decays monotonically after the in-cut");
  assert.equal(cutBlurAmount(12, total, fps, 0.4, 0.4, 0.12), 0, "zero once the in window ends");
  assert.equal(cutBlurAmount(60, total, fps, 0.4, 0.4, 0.12), 0, "zero mid-act");
  const b3 = cutBlurAmount(total - 4, total, fps, 0.4, 0.4, 0.12);
  assert.ok(close(b3, a3), "out window mirrors the in window");
});

test("cutBlurAmount is off without windows and clamps hostile input", () => {
  assert.equal(cutBlurAmount(0, 90, 30, 0, 0, 0.12), 0);
  assert.equal(cutBlurAmount(0, 90, 30, 0.4, 0, 0.12) > 0, true);
  assert.equal(cutBlurAmount(89, 90, 30, 0.4, 0, 0.12), 0, "only the in-cut is blurred");
  assert.equal(cutBlurAmount(0, 90, 30, 0.4, 0.4, 5), 0.4, "strength clamps to 0.4");
  assert.equal(cutBlurAmount(0, 90, 30, 0.4, 0.4, -1), 0);
  assert.equal(cutBlurAmount(0, 90, 30, Number.NaN, Number.NaN, 0.12), 0);
  assert.equal(cutBlurAmount(0, 90, 30, 0.4, 0.4, Number.NaN), 0);
  assert.equal(cutBlurAmount(-12, 90, 30, 0.4, 0, 0.12), 0);
  assert.equal(cutBlurAmount(100, 90, 30, 0, 0.4, 0.12), 0);
  assert.equal(cutBlurAmount(Number.NaN, 90, 30, 0.4, 0.4, 0.12), 0);
  assert.equal(cutBlurAmount(0, Number.NaN, 30, 0.4, 0.4, 0.12), 0);
});

test("clothWaveStops shades within the amplitude and scrolls with time", () => {
  const opts = { amplitude: 0.2, cycles: 2.5, speed: 0.5, stops: 25 };
  const a = clothWaveStops(0.3, opts);
  assert.equal(a.length, 25);
  assert.equal(a[0].offset, 0);
  assert.equal(a[24].offset, 1);
  for (let i = 1; i < a.length; i++) assert.ok(a[i].offset > a[i - 1].offset);
  assert.ok(a.every((s) => Math.abs(s.light) <= 0.2 + 1e-9));
  assert.ok(a.some((s) => s.light > 0.05) && a.some((s) => s.light < -0.05), "both highlights and shadows");
  // Periodic: one full cycle later the cloth looks the same.
  const later = clothWaveStops(0.3 + 1 / 0.5, opts);
  a.forEach((s, i) => assert.ok(close(s.light, later[i].light)));
  // Bands travel towards higher offsets: one stop further on, one step of time later.
  const step = 1 / 24;
  const shifted = clothWaveStops(0.3 + (2.5 * step) / 0.5, opts);
  for (let i = 0; i < 24; i++) assert.ok(close(a[i].light, shifted[i + 1].light));
});

test("clothWaveStops is flat at zero amplitude and clamps hostile input", () => {
  assert.ok(clothWaveStops(1, { amplitude: 0 }).every((s) => s.light === 0));
  assert.ok(clothWaveStops(1, { amplitude: 5 }).every((s) => Math.abs(s.light) <= 0.6 + 1e-9));
  const nan = clothWaveStops(Number.NaN, { amplitude: Number.NaN, stops: Number.NaN });
  assert.ok(nan.length >= 2 && nan.every((s) => Number.isFinite(s.light)));
});

test("organicRevealRadii grows a noise-edged seed that covers the bounds at the end", () => {
  const maxR = 300;
  const mid = organicRevealRadii(0.5, maxR, { points: 90, roughness: 0.25, seed: 7 });
  assert.equal(mid.length, 90);
  const spread = Math.max(...mid) - Math.min(...mid);
  assert.ok(spread > 20, "edge is irregular, not a circle");
  assert.ok(Math.min(...mid) >= 0.5 * maxR - 1e-9, "never smaller than the plain radial front");
  const done = organicRevealRadii(1, maxR, { points: 90, roughness: 0.25, seed: 7 });
  assert.ok(Math.min(...done) >= maxR - 1e-9, "fully covers the bounds at progress 1");
  assert.ok(organicRevealRadii(0, maxR, { seed: 7 }).every((r) => r === 0));
  // Smooth: neighbouring samples stay close.
  for (let i = 0; i < mid.length; i++) {
    const j = (i + 1) % mid.length;
    assert.ok(Math.abs(mid[i] - mid[j]) < 0.12 * maxR);
  }
  // Deterministic per seed, different across seeds.
  assert.deepEqual(organicRevealRadii(0.5, maxR, { points: 90, roughness: 0.25, seed: 7 }), mid);
  const other = organicRevealRadii(0.5, maxR, { points: 90, roughness: 0.25, seed: 8 });
  assert.ok(other.some((r, i) => Math.abs(r - mid[i]) > 1));
});

test("organicRevealRadii is a plain circle at zero roughness and clamps hostile input", () => {
  const circle = organicRevealRadii(0.4, 100, { roughness: 0 });
  assert.ok(circle.every((r) => close(r, 40)));
  const hostile = organicRevealRadii(Number.NaN, Number.NaN, { points: Number.NaN, roughness: 9 });
  assert.ok(hostile.length >= 8 && hostile.every((r) => Number.isFinite(r) && r >= 0));
});

function box(x0, y0, x1, y1) {
  return [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
}

test("ringClusters keeps nearby islands with the mainland and splits remote parts", () => {
  const mainland = box(0, 0, 1000, 1000);
  const island = box(1100, 600, 1180, 760);
  const remote = box(-6000, 4000, -5800, 4200);
  const clusters = ringClusters([remote, mainland, island], { viewport: { w: 1080, h: 1920 } });
  assert.equal(clusters.length, 2);
  assert.deepEqual(clusters[0].bounds, { minX: 0, minY: 0, maxX: 1180, maxY: 1000 });
  assert.deepEqual([...clusters[0].rings].sort(), [1, 2]);
  assert.deepEqual(clusters[1].rings, [0]);
});

test("ringClusters puts the cluster the viewer sees first", () => {
  const mainland = box(5000, 5000, 6000, 6000);
  const remote = box(100, 100, 300, 300);
  const clusters = ringClusters([mainland, remote], { viewport: { w: 1080, h: 1920 } });
  assert.deepEqual(clusters[0].rings, [1], "the on-screen part leads even though it is smaller");
  const offscreen = ringClusters([mainland, remote], { viewport: { w: 50, h: 50 } });
  assert.deepEqual(offscreen[0].rings, [0], "largest area leads when nothing is on screen");
});

test("ringClusters chains an archipelago and ignores non-finite points", () => {
  // Each island lies 300 px past the previous one: beyond half the mainland's width
  // from the mainland itself only for the later islands, so they join through the chain.
  const mainland = box(0, 0, 1000, 400);
  const chain = Array.from({ length: 8 }, (_, i) => box(1300 + i * 350, 100, 1350 + i * 350, 150));
  assert.equal(ringClusters([mainland, ...chain]).length, 1);
  const broken = [box(0, 0, 10, 10), [{ x: Number.NaN, y: 1 }, { x: Infinity, y: 2 }]];
  const out = ringClusters(broken);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0].rings, [0]);
  assert.deepEqual(ringClusters([]), []);
});

test("polygonRings separates exterior rings from hole rings across geometry shapes", () => {
  const outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]];
  const hole = [[3, 3], [6, 3], [6, 6], [3, 3]];
  const island = [[20, 0], [22, 0], [22, 2], [20, 0]];
  const poly = { type: "Polygon", coordinates: [outer, hole] };
  assert.deepEqual(polygonRings(poly), { outer: [outer], inner: [hole] });
  const multi = { type: "MultiPolygon", coordinates: [[outer, hole], [island]] };
  assert.deepEqual(polygonRings(multi), { outer: [outer, island], inner: [hole] });
  const featureList = [{ type: "Feature", geometry: poly }, { type: "Feature", geometry: { type: "Polygon", coordinates: [island] } }];
  assert.deepEqual(polygonRings(featureList), { outer: [outer, island], inner: [hole] });
  const collection = { type: "FeatureCollection", features: featureList };
  assert.deepEqual(polygonRings(collection), { outer: [outer, island], inner: [hole] });
  const degenerate = { type: "Polygon", coordinates: [outer, [[1, 1], [2, 2]]] };
  assert.deepEqual(polygonRings(degenerate), { outer: [outer], inner: [] });
  assert.deepEqual(polygonRings(null), { outer: [], inner: [] });
  assert.deepEqual(polygonRings({ type: "LineString", coordinates: outer }), { outer: [], inner: [] });
  const wrapped = [{ name: "France", geometry: poly }];
  assert.deepEqual(polygonRings(wrapped), { outer: [outer], inner: [hole] });
  const geomColl = { type: "GeometryCollection", geometries: [poly, { type: "Polygon", coordinates: [island] }] };
  assert.deepEqual(polygonRings(geomColl), { outer: [outer, island], inner: [hole] });
});
