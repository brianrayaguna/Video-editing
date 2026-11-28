import assert from "node:assert/strict";
import test from "node:test";
import { getChromeArgs } from "../fast_capture.mjs";
import {
  CONTINUOUSLY_ANIMATED_LAYER_TYPES,
  computeMapFrameStateKey,
  isLayerStaticAtFrame,
} from "./static_hold.mjs";

test("getChromeArgs supports explicit swiftshader and metal backend parity overrides", () => {
  const swiftOnMac = getChromeArgs(1080, 1920, { backend: "swiftshader", platform: "darwin" });
  assert.ok(swiftOnMac.includes("--use-angle=swiftshader"));
  assert.ok(swiftOnMac.includes("--enable-unsafe-swiftshader"));
  assert.ok(swiftOnMac.includes("--window-size=1080,1920"));
  assert.ok(!swiftOnMac.includes("--use-angle=metal"));

  const metalOnMac = getChromeArgs(1080, 1920, { backend: "metal", platform: "darwin" });
  assert.ok(metalOnMac.includes("--use-angle=metal"));
  assert.ok(!metalOnMac.includes("--use-angle=swiftshader"));

  const autoLinux = getChromeArgs(1080, 1920, { backend: "auto", platform: "linux" });
  assert.ok(autoLinux.includes("--use-angle=swiftshader"));
});

test("computeMapFrameStateKey deduplicates settled static map holds and refuses animated frames", () => {
  for (const animatedType of [
    "flag_fill",
    "weather_clouds_rain",
    "radar_rings",
    "map_sprites",
    "model_3d",
  ]) {
    assert.ok(
      CONTINUOUSLY_ANIMATED_LAYER_TYPES.has(animatedType),
      `Expected ${animatedType} in CONTINUOUSLY_ANIMATED_LAYER_TYPES`
    );
  }

  const cam = { center: [106.8, -6.2], zoom: 11.5, bearing: 0, pitch: 25, roll: 0 };
  const settledLabel = {
    type: "glow_label",
    text: "JAKARTA",
    coord: [106.8, -6.2],
    start_s: 0.0,
    end_s: 5.0,
    fade_in_s: 0.3,
    fade_out_s: 0.3,
  };

  // Settled consecutive frames produce identical deterministic state keys.
  assert.equal(isLayerStaticAtFrame(settledLabel, 2.0, 1.9667), true);
  const k1 = computeMapFrameStateKey({ cam, layers: [settledLabel], t: 2.0, prevT: 1.9667, blurAmt: 0, subN: 1 });
  const k2 = computeMapFrameStateKey({ cam, layers: [settledLabel], t: 2.0333, prevT: 2.0, blurAmt: 0, subN: 1 });
  assert.equal(typeof k1, "string");
  assert.equal(k1, k2);

  // Active entrance or exit transition returns null (never deduplicates).
  assert.equal(
    computeMapFrameStateKey({ cam, layers: [settledLabel], t: 0.15, prevT: 0.1167, blurAmt: 0, subN: 1 }),
    null
  );
  assert.equal(
    computeMapFrameStateKey({ cam, layers: [settledLabel], t: 4.85, prevT: 4.8167, blurAmt: 0, subN: 1 }),
    null
  );

  // Continuously animated layers force null even when camera is frozen.
  for (const type of ["flag_fill", "weather_clouds_rain", "radar_rings", "map_sprites", "model_3d"]) {
    const animatedLayer = { type, start_s: 0, end_s: 5 };
    assert.equal(
      computeMapFrameStateKey({ cam, layers: [settledLabel, animatedLayer], t: 2.0, prevT: 1.9667, blurAmt: 0, subN: 1 }),
      null,
      `Expected null state key when ${type} is active`
    );
  }

  // Polygon with animated flag_fill property forces null.
  assert.equal(
    computeMapFrameStateKey({
      cam,
      layers: [{ type: "polygon", flag_fill: "id", start_s: 0, end_s: 5 }],
      t: 2.0,
      prevT: 1.9667,
      blurAmt: 0,
      subN: 1,
    }),
    null
  );

  // Cut blur or optical shutter subframes force null.
  assert.equal(
    computeMapFrameStateKey({ cam, layers: [settledLabel], t: 2.0, prevT: 1.9667, blurAmt: 0.05, subN: 1 }),
    null
  );
  assert.equal(
    computeMapFrameStateKey({ cam, layers: [settledLabel], t: 2.0, prevT: 1.9667, blurAmt: 0, subN: 4 }),
    null
  );
});
