import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const GEO_DIR = fileURLToPath(new URL("..", import.meta.url));

test("render_map_scene.mjs is a thin CLI entrypoint under 250 lines", () => {
  const src = readFileSync(`${GEO_DIR}/render_map_scene.mjs`, "utf8");
  const lines = src.split("\n").length;
  assert.ok(lines <= 250, `Expected render_map_scene.mjs <= 250 lines, got ${lines}`);
});

test("modular scene builders emit valid HTML with required browser runtime hooks", async () => {
  const { parseArgs } = await import("./cli_args.mjs");
  const { buildDynamicFontFaceCss } = await import("./font_css.mjs");
  const { buildBlueprintHtml } = await import("./html_blueprint.mjs");
  const { buildCutaway2dHtml } = await import("./html_cutaway.mjs");
  const { buildMapSceneHtml, defaultTileSource, resolveImageryCredit } = await import("./html_map_scene.mjs");
  const { sampleCameraAt, wrapDeltaDeg } = await import("./bake_act.mjs");

  const parsed = parseArgs(["node", "render_map_scene.mjs", "--scene-file", "a.json", "--only-act", "act1", "--only-act", "act2"]);
  assert.equal(parsed["scene-file"], "a.json");
  assert.deepEqual(parsed["only-act"], ["act1", "act2"]);

  assert.equal(typeof buildDynamicFontFaceCss("http://127.0.0.1:9999"), "string");
  assert.equal(typeof defaultTileSource(), "string");
  assert.equal(typeof resolveImageryCredit({ tile_source: "realistic" }), "string");

  const bpHtml = buildBlueprintHtml("http://127.0.0.1:9999", 1080, 1920, "{}", { act_id: "bp1", duration_s: 2 });
  assert.match(bpHtml, /window\.__renderBlueprint/);

  const cutHtml = buildCutaway2dHtml("http://127.0.0.1:9999", 1080, 1920, { act_id: "cut1", duration_s: 2 });
  assert.match(cutHtml, /window\.__renderCutaway/);

  const mapHtml = buildMapSceneHtml("http://127.0.0.1:9999", 1080, 1920, "{}", { tile_source: "realistic" });
  assert.match(mapHtml, /window\.__drawSceneLayers/);
  assert.match(mapHtml, /window\.__setSceneCamera/);
  assert.match(mapHtml, /window\.__accumSubframe/);

  assert.equal(wrapDeltaDeg(350, 10), 20);
  const midCam = sampleCameraAt(
    [
      { center: [0, 0], zoom: 4, bearing: 350, pitch: 0 },
      { center: [2, 2], zoom: 6, bearing: 10, pitch: 20 },
    ],
    0,
    0.5
  );
  assert.equal(midCam.bearing % 360, 0);
  assert.equal(midCam.zoom, 5);
});
