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

test("runtime_typography exposes 5 adaptive editorial presets with synced #F5F7FA ink", async () => {
  const { buildTypographyRuntime } = await import("./runtime_typography.mjs");
  const src = buildTypographyRuntime();
  for (const preset of ["dark_on_fill", "acronym_hero", "velocity_cyan", "underlined_city", "water_subtle"]) {
    assert.ok(src.includes(`${preset}:`), `missing typography preset: ${preset}`);
  }
  assert.match(src, /dark_on_fill:[\s\S]*?#140E0E/);
  assert.match(src, /acronym_hero:[\s\S]*?#F7DC28/);
  assert.match(src, /velocity_cyan:[\s\S]*?#7CE8FF/);
  assert.match(src, /underlined_city:[\s\S]*?#F5F7FA/);
  assert.match(src, /country:[\s\S]*?#F5F7FA/);
});

test("html_blueprint supports cobalt theme and html_map_scene supports daylight_terrain register", async () => {
  const { buildBlueprintHtml } = await import("./html_blueprint.mjs");
  const { buildMapSceneHtml } = await import("./html_map_scene.mjs");

  const cobaltHtml = buildBlueprintHtml("http://127.0.0.1:9999", 1080, 1920, "{}", {
    act_id: "bp_cobalt",
    duration_s: 2,
    theme: "cobalt",
  });
  assert.match(cobaltHtml, /#2059DC/);
  assert.doesNotMatch(cobaltHtml, /background:\s*undefined/);

  const paperHtml = buildBlueprintHtml("http://127.0.0.1:9999", 1080, 1920, "{}", {
    act_id: "bp_paper",
    duration_s: 2,
  });
  assert.match(paperHtml, /#D9D2C3/);

  const daylightHtml = buildMapSceneHtml("http://127.0.0.1:9999", 1080, 1920, "{}", {
    tile_source: "realistic",
    terrain_3d: true,
    surface_register: "daylight_terrain",
  });
  assert.match(daylightHtml, /#2B7AE4/);
  assert.match(daylightHtml, /#A3CEF5/);

  const defaultMapHtml = buildMapSceneHtml("http://127.0.0.1:9999", 1080, 1920, "{}", {
    tile_source: "realistic",
  });
  assert.match(defaultMapHtml, /background:\s*#0E4352/);
  assert.match(defaultMapHtml, /"background-color":\s*"#0E4352"/);
});

test("build_tiles gradeRgb preserves marine-teal deep ocean, cyan coastal shelf contrast, and warm land", async () => {
  const { gradeRgb } = await import("../build_tiles.mjs");
  // 3 pixels: deep ocean [10, 28, 48], shallow coastal shelf [38, 128, 148], warm land [160, 145, 110].
  const raw = Buffer.from([10, 28, 48, 38, 128, 148, 160, 145, 110]);
  const gradedA = gradeRgb(raw, 5);
  const gradedB = gradeRgb(raw, 5);
  assert.deepEqual(gradedA, gradedB, "gradeRgb must be deterministic");

  const [dR, dG, dB] = [gradedA[0], gradedA[1], gradedA[2]];
  const [sR, sG, sB] = [gradedA[3], gradedA[4], gradedA[5]];
  const [lR, lG, lB] = [gradedA[6], gradedA[7], gradedA[8]];

  assert.ok(dB > dG && dG > dR && dG >= 58 && dB >= 76, `deep ocean out of range: [${dR},${dG},${dB}]`);
  assert.ok(sG >= 112 && sB >= 130 && sG > dG + 45 && sB > dB + 45, `coastal shelf lost cyan brightness vs deep ocean: shelf=[${sR},${sG},${sB}] deep=[${dR},${dG},${dB}]`);
  assert.ok(lR > lB && lG > lB && lR >= 162, `warm landmass shifted cold/flat: [${lR},${lG},${lB}]`);
});
