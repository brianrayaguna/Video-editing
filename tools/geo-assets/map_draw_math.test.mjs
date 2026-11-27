import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  buildWorldHatchLines,
  clipHomogeneousPolyline,
  clipHomogeneousRing,
  clothWaveStops,
  computeOctaveHatchSpacing,
  coverRect,
  cubicBezier,
  cutBlurAmount,
  easeInOutQuart,
  easeInQuad,
  easeOutQuint,
  editorialOut,
  evalEase,
  hatchLineRevealState,
  lngLatToMercNorm,
  mercNormToLngLat,
  nearestVertexIndex,
  organicRevealRadii,
  perimeterPartialPaths,
  perimeterPartialPathsLngLat,
  perimeterWindowPathsLngLat,
  polygonRings,
  ringClusters,
  sampleQuadraticBezierTo,
  scaledWidth,
  shutterSubframeSchedule,
  signedArea,
  slicePolylineFraction,
  springClosedForm,
  sunDirectionFromAzimuthElevation,
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

test("clipHomogeneousRing clips near-plane crossings and drops behind-camera rings", () => {
  const inFront = [
    { x: -1, y: -1, z: 0, w: 2 },
    { x: 1, y: -1, z: 0, w: 2 },
    { x: 0, y: 1, z: 0, w: 2 },
  ];
  assert.equal(clipHomogeneousRing(inFront).length, 3);

  const behind = [
    { x: -1, y: -1, z: -2, w: -1 },
    { x: 1, y: -1, z: -2, w: -1 },
    { x: 0, y: 1, z: -2, w: -1 },
  ];
  assert.deepEqual(clipHomogeneousRing(behind), []);

  // Triangle spanning w = -1 to w = 3 gets clipped cleanly to positive w >= eps and z + w >= 0.
  const crossing = [
    { x: -2, y: -1, z: 0, w: 3 },
    { x: 2, y: -1, z: 0, w: 3 },
    { x: 0, y: 2, z: -2, w: -1 },
  ];
  const clipped = clipHomogeneousRing(crossing, 1e-4);
  assert.equal(clipped.length, 4);
  assert.ok(clipped.every((v) => v.w >= 1e-4 - 1e-9 && v.z + v.w >= -1e-9));
});

test("clipHomogeneousPolyline clips near-plane crossings and splits out-and-in paths", () => {
  const behind = [
    { x: -1, y: 0, z: -2, w: -1 },
    { x: 1, y: 0, z: -2, w: -1 },
  ];
  assert.deepEqual(clipHomogeneousPolyline(behind), []);

  const cross = [
    { x: -1, y: 0, z: 0, w: 3 },
    { x: 1, y: 0, z: -2, w: -1 },
  ];
  const clipped = clipHomogeneousPolyline(cross, 1e-4);
  assert.equal(clipped.length, 1);
  assert.equal(clipped[0].length, 2);
  assert.ok(clipped[0].every((v) => v.w >= 1e-4 - 1e-9 && v.z + v.w >= -1e-9));

  // Path exits behind camera and re-enters -> two disjoint sub-polylines
  const reentry = [
    { x: -2, y: 0, z: 0, w: 2 },
    { x: -1, y: 0, z: -2, w: -2 },
    { x: 1, y: 0, z: -2, w: -2 },
    { x: 2, y: 0, z: 0, w: 2 },
  ];
  const split = clipHomogeneousPolyline(reentry, 1e-4);
  assert.equal(split.length, 2);
  assert.ok(split.every((seg) => seg.length === 2 && seg.every((v) => v.w >= 1e-4 - 1e-9)));
});

test("editorial easing curves hit exact endpoints and stay monotonic", () => {
  const curve = cubicBezier(0.16, 1, 0.3, 1);
  assert.equal(curve(0), 0);
  assert.equal(curve(1), 1);
  assert.equal(editorialOut(0), 0);
  assert.equal(editorialOut(1), 1);
  assert.ok(editorialOut(0.25) > 0.55, "editorial out accelerates sharply out of gate");
  assert.ok(easeOutQuint(0.5) > 0.9);
  assert.ok(close(easeInOutQuart(0.5), 0.5));
  assert.ok(close(easeInQuad(0.5), 0.25));
  let prev = -1;
  for (let i = 0; i <= 20; i++) {
    const val = editorialOut(i / 20);
    assert.ok(val >= prev - 1e-9);
    prev = val;
  }
});

test("springClosedForm is seek-safe, crisp monotonic, tactile overshoots, and clamps hostile inputs", () => {
  assert.equal(springClosedForm(0), 0);
  assert.equal(springClosedForm(1), 1);
  assert.equal(springClosedForm(-0.5), 0);
  assert.equal(springClosedForm(1.5), 1);
  assert.equal(springClosedForm(Number.NaN), 0);

  // Critically/overdamped crisp spring never overshoots and rises monotonically.
  let prev = 0;
  for (let i = 1; i <= 40; i++) {
    const val = evalEase("spring_crisp", i / 40);
    assert.ok(val >= prev - 1e-9 && val <= 1 + 1e-9, `crisp spring step ${i}: ${val}`);
    prev = val;
  }

  // Tactile spring has controlled gentle overshoot above 1.0 before settling cleanly to 1.0.
  let maxVal = 0;
  for (let i = 0; i <= 60; i++) {
    maxVal = Math.max(maxVal, evalEase("spring_tactile", i / 60));
  }
  assert.ok(maxVal > 1.01 && maxVal < 1.12, `expected subtle tactile overshoot, got ${maxVal}`);
  assert.equal(evalEase("spring_tactile", 1), 1);
  assert.equal(evalEase("linear", 0.35), 0.35);
  assert.ok(evalEase("expo_out", 0.5) > 0.95);
  assert.ok(Number.isFinite(evalEase("unknown_curve", 0.4)));
});

test("lngLatToMercNorm and mercNormToLngLat round-trip and clamp polar latitudes", () => {
  const orig = [106.8456, -6.2088];
  const m = lngLatToMercNorm(orig);
  const back = mercNormToLngLat(m.x, m.y);
  assert.ok(close(back[0], orig[0], 1e-6));
  assert.ok(close(back[1], orig[1], 1e-6));

  const pole = lngLatToMercNorm([0, 90]);
  assert.ok(Number.isFinite(pole.x) && Number.isFinite(pole.y));
  const nanPt = lngLatToMercNorm([Number.NaN, Number.NaN]);
  assert.ok(Number.isFinite(nanPt.x) && Number.isFinite(nanPt.y));
});

test("perimeterPartialPathsLngLat traces at constant Mercator speed and returns comet tail", () => {
  const ring = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
    [0, 0],
  ];
  assert.deepEqual(perimeterPartialPathsLngLat([ring], 0), { paths: [], comets: [] });

  const mid = perimeterPartialPathsLngLat([ring], 0.5, { heads: 1, cometFraction: 0.1 });
  assert.equal(mid.paths.length, 1);
  assert.equal(mid.comets.length, 1);
  const tip = mid.paths[0].at(-1);
  assert.ok(close(tip[0], 10, 0.25) && close(tip[1], 10, 0.25), `unexpected mid tip: ${tip}`);
  assert.deepEqual(mid.comets[0].at(-1), tip);
  assert.ok(mid.comets[0].length >= 2);

  const done = perimeterPartialPathsLngLat([ring], 1, { heads: 2 });
  assert.equal(done.paths.length, 1);
  assert.equal(done.comets.length, 0);
  assert.ok(close(done.paths[0][0][0], done.paths[0].at(-1)[0], 1e-5));

  // Travelling window for rim_glint wraps cleanly across ring start/end.
  const win = perimeterWindowPathsLngLat([ring], 0.95, 0.12);
  assert.equal(win.length, 1);
  assert.ok(win[0].length >= 3);
});

test("computeOctaveHatchSpacing stays C0 continuous across zoom octaves", () => {
  const atRef = computeOctaveHatchSpacing(14, 6, 6);
  assert.ok(close(atRef.screenSpacingPx, 14, 1e-6));
  assert.equal(atRef.subAlpha, 0);

  const beforeBoundary = computeOctaveHatchSpacing(14, 6.9999, 6);
  const afterBoundary = computeOctaveHatchSpacing(14, 7.0001, 6);
  assert.ok(beforeBoundary.subAlpha > 0.99);
  assert.ok(afterBoundary.subAlpha < 0.01);
  assert.ok(close(beforeBoundary.subSpacingMerc, afterBoundary.primarySpacingMerc, 1e-9));
});

test("buildWorldHatchLines caps line count, aligns to global Mercator grid, and slices cleanly", () => {
  const bounds = { minLng: 95, maxLng: 141, minLat: -11, maxLat: 6 };
  const spacing = computeOctaveHatchSpacing(18, 5, 5).primarySpacingMerc;
  const lines = buildWorldHatchLines(bounds, { angleDeg: 45, spacingMerc: spacing, maxLines: 60, segmentsPerLine: 6 });
  assert.ok(lines.length > 4 && lines.length <= 60, `got ${lines.length} lines`);
  assert.equal(lines[0].coords.length, 7);

  // Hostile tiny spacing still respects maxLines cap without hanging or NaN.
  const capped = buildWorldHatchLines(
    { minLng: -179, maxLng: 179, minLat: -85, maxLat: 85 },
    { angleDeg: 45, spacingMerc: 1e-9, maxLines: 120 }
  );
  assert.ok(capped.length > 0 && capped.length <= 120);
  assert.ok(capped.every((l) => l.coords.every((c) => Number.isFinite(c[0]) && Number.isFinite(c[1]))));

  const sub = slicePolylineFraction(lines[0].coords, 0.2, 0.7);
  assert.ok(sub.length >= 2);
  assert.deepEqual(slicePolylineFraction(lines[0].coords, 0.5, 0.5), []);
});

test("hatchLineRevealState supports staggered_draw, venetian_grow, contour_ripple, fade, and all directions", () => {
  const n = 10;
  const earlyLtr0 = hatchLineRevealState(0, n, 0.2, { mode: "staggered_draw", direction: "ltr" });
  const earlyLtr9 = hatchLineRevealState(9, n, 0.2, { mode: "staggered_draw", direction: "ltr" });
  assert.ok(earlyLtr0.active && earlyLtr0.drawTo > 0);
  assert.equal(earlyLtr9.active, false);

  const earlyRtl0 = hatchLineRevealState(0, n, 0.2, { mode: "staggered_draw", direction: "rtl" });
  const earlyRtl9 = hatchLineRevealState(9, n, 0.2, { mode: "staggered_draw", direction: "rtl" });
  assert.equal(earlyRtl0.active, false);
  assert.ok(earlyRtl9.active && earlyRtl9.drawTo > 0);

  const midCenter = hatchLineRevealState(5, n, 0.2, { mode: "staggered_draw", direction: "center_out" });
  const edgeCenter = hatchLineRevealState(0, n, 0.2, { mode: "staggered_draw", direction: "center_out" });
  assert.ok(midCenter.active && midCenter.drawTo > edgeCenter.drawTo);

  const altOdd = hatchLineRevealState(1, n, 0.4, { mode: "staggered_draw", direction: "alternate" });
  assert.ok(altOdd.active && altOdd.drawTo === 1 && altOdd.drawFrom > 0 && altOdd.drawFrom < 1);

  const venetian = hatchLineRevealState(0, n, 0.25, { mode: "venetian_grow" });
  assert.ok(venetian.active && venetian.drawFrom === 0 && venetian.drawTo === 1 && venetian.widthScale > 0);

  const ripple = hatchLineRevealState(0, 5, 0.3, { mode: "contour_ripple" });
  assert.ok(ripple.active && ripple.alpha > 0);

  const fade = hatchLineRevealState(7, n, 0.4, { mode: "fade" });
  assert.ok(fade.active && close(fade.alpha, 0.4) && fade.drawTo === 1);

  const done = hatchLineRevealState(9, n, 1.0, { mode: "staggered_draw" });
  assert.ok(done.active && close(done.drawTo, 1) && close(done.alpha, 1));
});

test("sampleQuadraticBezierTo terminates exactly at arbitrary progress with analytic tangent", () => {
  const p1 = { x: 0, y: 0 };
  const ctrl = { x: 50, y: 100 };
  const p2 = { x: 100, y: 0 };
  for (const prog of [0.137, 0.503, 0.991]) {
    const res = sampleQuadraticBezierTo(p1, ctrl, p2, prog, 24);
    const inv = 1 - prog;
    const expectedX = inv * inv * p1.x + 2 * inv * prog * ctrl.x + prog * prog * p2.x;
    const expectedY = inv * inv * p1.y + 2 * inv * prog * ctrl.y + prog * prog * p2.y;
    assert.ok(close(res.tip.x, expectedX, 1e-6));
    assert.ok(close(res.tip.y, expectedY, 1e-6));
    assert.deepEqual(res.points.at(-1), res.tip);
    assert.ok(Number.isFinite(res.angleRad));
  }
  // At apex u = 0.5, tangent is purely horizontal (+x -> angle 0).
  const apex = sampleQuadraticBezierTo(p1, ctrl, p2, 0.5, 20);
  assert.ok(close(apex.angleRad, 0, 1e-6));
});

test("shutterSubframeSchedule returns symmetric centered weights summing to 1", () => {
  const cos = shutterSubframeSchedule(5, 180, "cosine");
  assert.equal(cos.length, 5);
  const sum = cos.reduce((acc, s) => acc + s.weight, 0);
  assert.ok(close(sum, 1, 1e-9));
  assert.ok(close(cos[0].offset, -cos[4].offset, 1e-9));
  assert.ok(close(cos[2].offset, 0, 1e-9));
  assert.ok(cos[2].weight > cos[0].weight, "cosine window peaks at center");
  assert.deepEqual(shutterSubframeSchedule(1, 180, "cosine"), [{ offset: 0, weight: 1 }]);
});

test("sunDirectionFromAzimuthElevation returns unit vector and matching 2D cast shadow vector", () => {
  const sun = sunDirectionFromAzimuthElevation(335, 42);
  const len = Math.hypot(sun.x, sun.y, sun.z);
  assert.ok(close(len, 1, 1e-6));
  // 335 deg (NNW) sun is West (-x), North (+y), Up (+z); casts shadow South-East (+shadowDx, +shadowDy).
  assert.ok(sun.x < 0 && sun.y > 0 && sun.z > 0);
  assert.ok(sun.shadowDx > 0 && sun.shadowDy > 0);
});

test("cubicBezier preserves x2 = 0 and clipHomogeneousPolyline drops non-finite y/z vertices", () => {
  const ease = cubicBezier(0, 0, 0, 1);
  // With x1=0, x2=0: x(t) = t^3, so at x=0.5, t=0.5^(1/3) and y(t)=3t^2-2t^3 ~= 0.8899.
  // If x2=0 were coerced to 1 via `|| 1`, ease(0.5) would incorrectly return 0.5.
  assert.ok(ease(0.5) > 0.85, `expected cubicBezier(0,0,0,1)(0.5) > 0.85, got ${ease(0.5)}`);

  const badPoly = [
    { x: -1, y: 0, z: 0, w: 2 },
    { x: 0, y: Number.NaN, z: 0, w: 2 },
    { x: 1, y: 0, z: Number.POSITIVE_INFINITY, w: 2 },
    { x: 2, y: 0, z: 0, w: 2 },
  ];
  const clipped = clipHomogeneousPolyline(badPoly);
  assert.deepEqual(clipped, []);
});

test("render_map_scene and fast_capture satisfy WebGL, compositing, and pipe error invariants", async () => {
  const renderSrc = readFileSync(new URL("./render_map_scene.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(
    renderSrc,
    /smoothstep\(\s*localP\s*\+\s*0\.04\s*,\s*localP\s*-\s*0\.04/,
    "GLSL smoothstep(edge0, edge1, x) with edge0 > edge1 is undefined behavior"
  );
  assert.match(renderSrc, /shadowMap\.autoUpdate\s*=\s*false/);
  assert.match(renderSrc, /spacingStep\.toPrecision\(8\)/);
  assert.match(renderSrc, /if\s*\(\s*revealAxis\s*&&\s*revealProgress\s*<=\s*0\.001\s*\)\s*return;/);
  assert.doesNotMatch(
    renderSrc,
    /compCtx\.globalAlpha\s*=\s*blendAlpha;[\s\S]{0,400}compCtx\.drawImage\(map\.getCanvas\(\)[\s\S]{0,120}compCtx\.drawImage\(ovCanvas/,
    "__accumSubframe must composite map + ovCanvas at full alpha before blending once onto compCtx"
  );

  // fast_capture writeFrame must reject with an Error instance (never a raw numeric exit code).
  const { spawnFramePipeEncoder } = await import("./fast_capture.mjs");
  const enc = spawnFramePipeEncoder("/nonexistent_dir_vedit_test/out.mp4", { fps: 30 });
  const bigBuf = Buffer.alloc(1024 * 1024, 0xff);
  let caught = null;
  try {
    for (let i = 0; i < 64; i++) {
      await enc.writeFrame(bigBuf);
    }
    await enc.finish();
  } catch (err) {
    caught = err;
  } finally {
    await enc.abort();
  }
  assert.ok(caught instanceof Error, `Expected Error rejection from failed encoder, got ${typeof caught}: ${caught}`);
});

test("study_runner asset server rejects NUL byte URLs cleanly without crashing", async () => {
  const { startStudyAssetServer } = await import("./study_runner.mjs");
  const { server, baseUrl } = await startStudyAssetServer(null, 0, "127.0.0.1");
  try {
    const resp = await fetch(`${baseUrl}/geo/fonts/foo%00bar.ttf`);
    assert.ok(resp.status === 400 || resp.status === 404, `Unexpected status ${resp.status}`);
  } finally {
    server.close();
  }
});

test("geo scripts use neutral episode-agnostic defaults and validate BBOX/CENTER cleanly", async () => {
  const { spawnSync } = await import("node:child_process");
  const { fileURLToPath } = await import("node:url");
  const {
    DEFAULT_MAP_CENTER,
    DEFAULT_DEM_ZOOMS,
    DEFAULT_DEM_BOUNDS,
    parseCenterEnv,
    parseBboxEnv,
  } = await import("./geo_defaults.mjs");

  assert.deepEqual(DEFAULT_MAP_CENTER, [0, 0]);
  assert.deepEqual(DEFAULT_DEM_ZOOMS, [4, 5, 6, 7]);
  assert.deepEqual(DEFAULT_DEM_BOUNDS, [-180, -85, 180, 85]);
  assert.deepEqual(parseCenterEnv(undefined), [0, 0]);
  assert.deepEqual(parseCenterEnv("12.5, -4.25"), [12.5, -4.25]);
  assert.throws(() => parseCenterEnv("999,0"), /Invalid CENTER/);
  assert.throws(() => parseBboxEnv(""), /Missing required BBOX/);
  assert.throws(() => parseBboxEnv("10,10,5,20"), /Invalid BBOX/);
  assert.deepEqual(parseBboxEnv("-10,35,5,45"), [-10, 35, 5, 45]);

  for (const script of ["render_map_scene.mjs", "bake_vertical_basemap.mjs", "fetch_dem_tiles.mjs"]) {
    const src = readFileSync(new URL(`./${script}`, import.meta.url), "utf8");
    assert.doesNotMatch(src, /-77\.55/, `${script} must not hardcode episode-specific longitude`);
    assert.doesNotMatch(src, /121\.2,-1\.6/, `${script} must not hardcode episode-specific center`);
    assert.doesNotMatch(src, /107\.5,-6\.0,125\.5,7\.5/, `${script} must not hardcode regional BBOX`);
    assert.doesNotMatch(src, /Kalimantan|Sulawesi/i, `${script} must stay episode-agnostic`);
  }

  const fetchScript = fileURLToPath(new URL("./fetch_dem_tiles.mjs", import.meta.url));
  const cleanEnv = { ...process.env };
  delete cleanEnv.BBOX;
  const missingRes = spawnSync(process.execPath, [fetchScript], {
    env: cleanEnv,
    encoding: "utf8",
  });
  assert.notEqual(missingRes.status, 0, "fetch_dem_tiles.mjs must fail cleanly when BBOX is unset");
  assert.match(missingRes.stderr, /BBOX/i);
});
