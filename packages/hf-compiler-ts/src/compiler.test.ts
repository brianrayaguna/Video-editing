import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { compileEditPlanToHyperframes } from "./compiler.js";
import type { EditPlan, PlatformTarget } from "./contracts.js";
import { buildDistributedConfig, clampChunkFrameBudget } from "./distributed.js";
import { lintHyperframesProjectDir } from "./lint.js";

function makeSamplePlan(overrides: Partial<EditPlan> = {}): EditPlan {
  return {
    schema_version: "1.0",
    job_id: "job_hf_test",
    project_id: "proj_hf_test",
    brand_id: "sample_brand",
    platform_target_id: "reels_9x16_1080p",
    render_strategy: "hybrid",
    duration_s: 8.0,
    fps: 30,
    width: 1080,
    height: 1920,
    assets: [
      {
        asset_id: "src_1",
        sha256: "a".repeat(64),
        kind: "video",
        path: "/nonexistent/sample.mp4",
        duration_s: 8.0,
        has_audio: true,
      },
    ],
    video_tracks: [
      {
        clip_id: "clip_1",
        asset_id: "src_1",
        timeline_start_s: 0.0,
        timeline_duration_s: 8.0,
        source_start_s: 0.0,
        role: "a_roll",
        reframed_to_target: true,
      },
    ],
    overlay_compositions: [
      {
        overlay_id: "cap_1",
        kind: "caption_rail",
        timeline_start_s: 0.2,
        timeline_duration_s: 2.0,
        transparent: true,
        safe_band: "upper_safe",
        props: {
          text: "Retention climbed 42%",
          font_family: "Inter",
          fg_color: "#F8FAFC",
          bg_color: "#0B0F19",
        },
      },
      {
        overlay_id: "card_1",
        kind: "data_card",
        timeline_start_s: 0.4,
        timeline_duration_s: 2.2,
        transparent: true,
        safe_band: "lower_third",
        props: {
          headline: "+42% Retention",
          subtitle: "Q4 Cohort",
          font_family: "Unknown Custom Font",
          accent_color: "#38BDF8",
          fg_color: "#F8FAFC",
          bg_color: "#0B0F19",
        },
      },
    ],
    audio_tracks: [],
    verifier_passed: true,
    ...overrides,
  };
}

test("compileEditPlanToHyperframes produces lint-clean hybrid composition", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-compile-"));
  const target: PlatformTarget = {
    platform_id: "reels_9x16_1080p",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zone: { top_pct: 0.14, bottom_pct: 0.2, left_pct: 0.06, right_pct: 0.12 },
  };

  const compiled = compileEditPlanToHyperframes(makeSamplePlan(), tmpDir, {
    platformTarget: target,
    copyAssets: false,
  });

  assert.equal(compiled.recommendedFormat, "mov");
  assert.equal(compiled.compositionFiles.length, 2);

  const indexHtml = fs.readFileSync(compiled.indexHtmlPath, "utf8");
  assert.match(indexHtml, /data-track-index="1"/);
  assert.match(indexHtml, /data-track-index="2"/);
  assert.match(indexHtml, /window\.__timelines\["main"\] = tl;/);

  const sceneHtml = fs.readFileSync(compiled.compositionFiles[1]!, "utf8");
  assert.match(sceneHtml, /^<template>/);
  assert.match(sceneHtml, /font-family: 'Inter', sans-serif;/);
  assert.match(sceneHtml, /window\.__timelines\["card_1"\] = tl;/);

  const lintResult = await lintHyperframesProjectDir(tmpDir);
  assert.equal(
    lintResult.totalErrors,
    0,
    `Expected 0 HyperFrames lint errors, found: ${JSON.stringify(lintResult.hyperframesFindings)}`
  );
  assert.equal(lintResult.ok, true);
});

test("compileEditPlanToHyperframes rejects heavy CSS blur props", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-blur-"));
  const badPlan = makeSamplePlan({
    overlay_compositions: [
      {
        overlay_id: "bad_blur",
        kind: "data_card",
        timeline_start_s: 0.0,
        timeline_duration_s: 2.0,
        transparent: true,
        safe_band: "lower_third",
        props: {
          headline: "Glass Card",
          backdropFilter: "blur(14px)",
        },
      },
    ],
  });

  assert.throws(() => compileEditPlanToHyperframes(badPlan, tmpDir), /CSS performance gate failed/);
});

test("buildDistributedConfig clamps chunk frames and enforces SDR & fonts", () => {
  assert.equal(clampChunkFrameBudget(40), 150);
  assert.equal(clampChunkFrameBudget(180), 180);
  assert.equal(clampChunkFrameBudget(999), 240);

  const hybridCfg = buildDistributedConfig({
    projectDir: "/tmp/proj",
    planV2Dir: "/tmp/plan",
    fps: 30,
    width: 1080,
    height: 1920,
    format: "mov",
    targetChunkFrames: 190,
  });
  assert.equal(hybridCfg.proresProfile, "4444");
  assert.equal(hybridCfg.hdrMode, "force-sdr");
  assert.equal(hybridCfg.rejectOnSystemFonts, true);
  assert.equal(hybridCfg.targetChunkFrames, 190);
});

test("compileEditPlanToHyperframes emits media and audio elements in full_hf mode", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-full-"));
  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      render_strategy: "full_hf",
      audio_tracks: [
        {
          track_id: "vo_1",
          asset_id: "src_1",
          audio_group: "voiceover",
          timeline_start_s: 0.0,
          timeline_duration_s: 8.0,
          source_start_s: 0.0,
          gain_db: 0.0,
        },
      ],
    }),
    tmpDir,
    { copyAssets: false }
  );

  assert.equal(compiled.recommendedFormat, "mp4");
  const indexHtml = fs.readFileSync(compiled.indexHtmlPath, "utf8");
  assert.match(indexHtml, /<video id="clip_1" class="clip"/);
  assert.match(indexHtml, /<audio id="vo_1" class="clip"/);
  assert.match(indexHtml, /background: #000000;/);
});

test("compileEditPlanToHyperframes emits local font-face rules and custom HTML overlays", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-fonts-"));
  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      assets: [
        {
          asset_id: "font_sg",
          sha256: "b".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceGrotesk-Variable.ttf",
        },
      ],
      video_tracks: [],
      overlay_compositions: [
        {
          overlay_id: "cap_accent",
          kind: "caption_rail",
          timeline_start_s: 0.2,
          timeline_duration_s: 1.5,
          transparent: true,
          safe_band: "lower_third",
          props: {
            text: "Mengapa Sulawesi patah",
            highlight_text: "Sulawesi",
            font_family: "Space Grotesk",
            accent_color: "#F5C542",
          },
        },
        {
          overlay_id: "bug_corner",
          kind: "full_scene",
          timeline_start_s: 0.0,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "fullscreen",
          props: {
            font_family: "Space Grotesk",
            custom_html: "<div class=\"geo-bug\">geoverum</div>",
            custom_css: ".geo-bug { position: absolute; top: 80px; right: 72px; color: #F4F1EA; }",
          },
        },
      ],
    }),
    tmpDir,
    { copyAssets: false }
  );

  const indexHtml = fs.readFileSync(compiled.indexHtmlPath, "utf8");
  assert.match(indexHtml, /data-vedit-local-fonts="true"/);
  assert.match(indexHtml, /font-family: 'Space Grotesk';/);
  assert.match(indexHtml, /src: url\('assets\/font_sg\.ttf'\) format\('truetype'\);/);

  const capHtml = fs.readFileSync(compiled.compositionFiles[0]!, "utf8");
  assert.match(capHtml, /font-family: 'Space Grotesk', sans-serif;/);
  assert.match(capHtml, /<span class="vedit-caption-accent" style="color: #F5C542;">Sulawesi<\/span>/);

  const bugHtml = fs.readFileSync(compiled.compositionFiles[1]!, "utf8");
  assert.match(bugHtml, /<div class="geo-bug">geoverum<\/div>/);
});

test("compileEditPlanToHyperframes resolves font family across CAS SHA paths", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-cas-fonts-"));
  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      assets: [
        {
          asset_id: "font_space_grotesk",
          sha256: "f".repeat(64),
          kind: "font",
          path: "/vol/cas/sources/ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff.ttf",
        },
      ],
      video_tracks: [],
      overlay_compositions: [
        {
          overlay_id: "bug_cas",
          kind: "full_scene",
          timeline_start_s: 0.0,
          timeline_duration_s: 2.0,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            custom_html: "<div class=\"geo-bug\">geoverum</div>",
            custom_css: ".geo-bug { font-family: 'Space Grotesk', sans-serif; color: #F4F1EA; }",
          },
        },
      ],
    }),
    tmpDir,
    { copyAssets: false }
  );

  const indexHtml = fs.readFileSync(compiled.indexHtmlPath, "utf8");
  assert.match(indexHtml, /font-family: 'Space Grotesk';/);
  assert.match(indexHtml, /src: url\('assets\/font_space_grotesk\.ttf'\) format\('truetype'\);/);
});

test("caption centering is symmetric (x=50%) with y=70% portrait band and proportional scaling", async () => {
  const shortsTarget: PlatformTarget = {
    platform_id: "shorts_9x16_1080p",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zone: { top_pct: 0.14, bottom_pct: 0.22, left_pct: 0.06, right_pct: 0.16 },
  };
  const tmpShorts = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-sym-9x16-"));
  const compiledShorts = compileEditPlanToHyperframes(
    makeSamplePlan({
      width: 1080,
      height: 1920,
      overlay_compositions: [
        {
          overlay_id: "cap_plain",
          kind: "caption_rail",
          timeline_start_s: 0.5,
          timeline_duration_s: 1.5,
          transparent: true,
          safe_band: "lower_third",
          props: {
            text: "Three tectonic plates",
            caption_style: "plain",
            font_family: "Inter",
          },
        },
        {
          overlay_id: "card_disp",
          kind: "data_card",
          timeline_start_s: 2.0,
          timeline_duration_s: 2.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            headline: "42 mm/yr",
            subtitle: "Slip rate",
            font_family: "Inter",
            display_family: "Archivo Black",
          },
        },
      ],
    }),
    tmpShorts,
    { platformTarget: shortsTarget, copyAssets: false }
  );

  const capHtml = fs.readFileSync(compiledShorts.compositionFiles[0]!, "utf8");
  // Symmetric left & right = max(6%, 16%) = 16% -> true x=50% center.
  assert.match(capHtml, /left: 16%;\s*right: 16%;/);
  // Portrait lower_third sits around y=70% (bottom: 28.5%).
  assert.match(capHtml, /bottom: 28\.5%;/);
  // Plain documentary style (no pill box) and 44px proportional font size.
  assert.match(capHtml, /class="vedit-caption-plain"/);
  assert.match(capHtml, /font-size: 44px;/);
  // Hard cut transition (0.033s <= 33ms @ 30fps).
  assert.match(capHtml, /duration: 0\.033/);

  const cardHtml = fs.readFileSync(compiledShorts.compositionFiles[1]!, "utf8");
  assert.match(cardHtml, /justify-content: center;\s*align-items: center;/);
  assert.match(cardHtml, /font-family: 'Archivo Black', sans-serif;/);

  // 4K 16:9 proportional scaling check.
  const uhdTarget: PlatformTarget = {
    platform_id: "youtube_16x9_4k",
    aspect_ratio: "16:9",
    width: 3840,
    height: 2160,
    fps: 30,
    safe_zone: { top_pct: 0.05, bottom_pct: 0.08, left_pct: 0.05, right_pct: 0.05 },
  };
  const tmpUhd = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-4k-"));
  const compiledUhd = compileEditPlanToHyperframes(
    makeSamplePlan({
      width: 3840,
      height: 2160,
      overlay_compositions: [
        {
          overlay_id: "cap_4k",
          kind: "caption_rail",
          timeline_start_s: 0.0,
          timeline_duration_s: 2.0,
          transparent: true,
          safe_band: "lower_third",
          props: { text: "Banda Arc convergence", caption_style: "plain" },
        },
      ],
    }),
    tmpUhd,
    { platformTarget: uhdTarget, copyAssets: false }
  );
  const uhdHtml = fs.readFileSync(compiledUhd.compositionFiles[0]!, "utf8");
  assert.match(uhdHtml, /font-size: 84px;/);
  assert.match(uhdHtml, /bottom: 9\.5%;/);
});

test("parameterized Geoverum brand templates compile cleanly without SVG logo on watermark", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-geoverum-tpl-"));
  const target: PlatformTarget = {
    platform_id: "shorts_9x16_1080p",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zone: { top_pct: 0.14, bottom_pct: 0.22, left_pct: 0.06, right_pct: 0.16 },
  };

  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      brand_id: "geoverum",
      assets: [
        {
          asset_id: "font_sg",
          sha256: "c".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceGrotesk-Variable.ttf",
        },
      ],
      overlay_compositions: [
        {
          overlay_id: "gv_cap",
          kind: "caption_rail",
          template_id: "caption_rail",
          timeline_start_s: 0.2,
          timeline_duration_s: 1.6,
          transparent: true,
          safe_band: "lower_third",
          props: {
            font_family: "Space Grotesk",
            composition_path: "profiles/brands/geoverum/templates/components/caption_rail.html",
          },
          variables: {
            text: "Three plates collide",
            fg_color: "#F4F1EA",
            accent_color: "#F5C542",
          },
        },
        {
          overlay_id: "gv_bug",
          kind: "full_scene",
          template_id: "broadcast_bug",
          timeline_start_s: 0.0,
          timeline_duration_s: 4.0,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            composition_path: "profiles/brands/geoverum/templates/components/broadcast_bug.html",
          },
          variables: {
            brand_label: "geoverum",
            fg_color: "#F4F1EA",
          },
        },
        {
          overlay_id: "gv_metric",
          kind: "data_card",
          template_id: "metric_callout",
          timeline_start_s: 2.0,
          timeline_duration_s: 2.0,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            composition_path: "profiles/brands/geoverum/templates/components/metric_callout.html",
          },
          variables: {
            value: "42 mm/yr",
            label: "Palu-Koro slip rate",
            accent_color: "#F5C542",
            fg_color: "#F4F1EA",
            bg_color: "#03161F",
          },
        },
      ],
    }),
    tmpDir,
    { platformTarget: target, copyAssets: false }
  );

  const capHtml = fs.readFileSync(compiled.compositionFiles[0]!, "utf8");
  assert.match(capHtml, /Three plates collide/);
  assert.match(capHtml, /left: 16%;\s*right: 16%;/);
  assert.match(capHtml, /bottom: 28\.5%;/);

  const bugHtml = fs.readFileSync(compiled.compositionFiles[1]!, "utf8");
  assert.match(bugHtml, />geoverum</);
  assert.doesNotMatch(bugHtml, /<svg/i);
  assert.match(bugHtml, /top: 16%;/);
  assert.match(bugHtml, /right: 5\.5%;/);
  assert.match(bugHtml, /font-size: 18px;/);

  const lintResult = await lintHyperframesProjectDir(tmpDir);
  assert.equal(
    lintResult.totalErrors,
    0,
    `Expected 0 lint errors for Geoverum templates, got: ${JSON.stringify(lintResult.hyperframesFindings)}`
  );
  assert.equal(lintResult.ok, true);
});

test("compiler fails loudly on missing composition_path and heavy blur inside variables", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-errors-"));
  assert.throws(
    () =>
      compileEditPlanToHyperframes(
        makeSamplePlan({
          overlay_compositions: [
            {
              overlay_id: "missing_tpl",
              kind: "full_scene",
              timeline_start_s: 0.0,
              timeline_duration_s: 2.0,
              transparent: true,
              safe_band: "upper_safe",
              props: {
                composition_path:
                  "profiles/brands/geoverum/templates/components/does_not_exist.html",
              },
            },
          ],
        }),
        tmpDir,
        { copyAssets: false }
      ),
    /references missing composition_path/
  );

  assert.throws(
    () =>
      compileEditPlanToHyperframes(
        makeSamplePlan({
          overlay_compositions: [
            {
              overlay_id: "var_blur",
              kind: "data_card",
              timeline_start_s: 0.0,
              timeline_duration_s: 2.0,
              transparent: true,
              safe_band: "upper_safe",
              props: {},
              variables: { style: "backdrop-filter: blur(18px)" },
            },
          ],
        }),
        tmpDir,
        { copyAssets: false }
      ),
    /CSS performance gate failed/
  );
});

test("buildDistributedConfig defaults to 48 maxParallelChunks and forwards quality", () => {
  const cfg = buildDistributedConfig({
    projectDir: "/tmp/proj",
    planV2Dir: "/tmp/plan",
    fps: 30,
    width: 1920,
    height: 1080,
    format: "mp4",
    quality: "draft",
  });
  assert.equal(cfg.maxParallelChunks, 48);
  assert.equal(cfg.quality, "draft");
});

test("hero explainer Geoverum templates support data-motion-blur and pass official HyperFrames lint", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-hero-explainers-"));
  const target: PlatformTarget = {
    platform_id: "shorts_9x16_1080p",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zone: { top_pct: 0.14, bottom_pct: 0.22, left_pct: 0.06, right_pct: 0.16 },
  };
  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      brand_id: "geoverum",
      duration_s: 12.0,
      assets: [
        {
          asset_id: "font_sg",
          sha256: "d".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceGrotesk-Variable.ttf",
        },
        {
          asset_id: "font_ab",
          sha256: "e".repeat(64),
          kind: "font",
          path: "/nonexistent/ArchivoBlack-Regular.ttf",
        },
      ],
      overlay_compositions: [
        {
          overlay_id: "hero_chart",
          kind: "data_card",
          template_id: "comparison_bar_chart",
          timeline_start_s: 0.0,
          timeline_duration_s: 4.0,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/comparison_bar_chart.html",
          },
          variables: {
            title: "TIGA SUNGAI TERPANJANG",
            bar1_label: "Kapuas",
            bar1_value: 1143,
            bar2_label: "Barito",
            bar2_value: 1090,
            bar3_label: "Mahakam",
            bar3_value: 980,
          },
        },
        {
          overlay_id: "hero_diag",
          kind: "full_scene",
          template_id: "cross_section_diagram",
          timeline_start_s: 4.5,
          timeline_duration_s: 4.5,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/cross_section_diagram.html",
          },
          variables: {
            title: "PENAMPANG LAHAN KALIMANTAN",
          },
        },
        {
          overlay_id: "hero_chap",
          kind: "title_scene",
          template_id: "chapter_morph_card",
          timeline_start_s: 9.2,
          timeline_duration_s: 2.5,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/chapter_morph_card.html",
          },
          variables: {
            title: "KONEKTIVITAS DARAT",
          },
        },
      ],
    }),
    tmpDir,
    { platformTarget: target, copyAssets: false }
  );

  for (const file of compiled.compositionFiles) {
    const html = fs.readFileSync(file, "utf8");
    assert.match(html, /data-motion-blur="on"/);
  }
  const lintResult = await lintHyperframesProjectDir(tmpDir);
  assert.equal(
    lintResult.totalErrors,
    0,
    `Expected 0 lint errors for hero explainer templates, got: ${JSON.stringify(lintResult.hyperframesFindings)}`
  );
  assert.equal(lintResult.ok, true);
});

test("all cartographic editorial Geoverum templates compile cleanly with zero dashboard slop", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-carto-suite-"));
  const target: PlatformTarget = {
    platform_id: "shorts_9x16_1080p",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zone: { top_pct: 0.14, bottom_pct: 0.22, left_pct: 0.06, right_pct: 0.16 },
  };
  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      brand_id: "geoverum",
      duration_s: 20.0,
      assets: [
        {
          asset_id: "font_sg",
          sha256: "d".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceGrotesk-Variable.ttf",
        },
        {
          asset_id: "font_ab",
          sha256: "e".repeat(64),
          kind: "font",
          path: "/nonexistent/ArchivoBlack-Regular.ttf",
        },
      ],
      overlay_compositions: [
        {
          overlay_id: "pin_1",
          kind: "kinetic_callout",
          template_id: "coordinate_pin_callout",
          timeline_start_s: 0.0,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "fullscreen",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/coordinate_pin_callout.html",
          },
          variables: {
            label: "MADRID",
            subtitle: "40.4° N",
            population_badge: "3.3M",
            anchor_x_pct: 52,
            anchor_y_pct: 54,
            pin_style: "vertical",
          },
        },
        {
          overlay_id: "dist_1",
          kind: "kinetic_callout",
          template_id: "dual_unit_distance_bracket",
          timeline_start_s: 3.2,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "fullscreen",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/dual_unit_distance_bracket.html",
          },
          variables: {
            primary_distance: "2.4 mi",
            secondary_distance: "(3.8 km)",
            line_style: "double_arrow",
            angle_deg: -14,
          },
        },
        {
          overlay_id: "bp_1",
          kind: "full_scene",
          template_id: "blueprint_tabletop_frame",
          timeline_start_s: 6.4,
          timeline_duration_s: 3.0,
          transparent: false,
          safe_band: "fullscreen",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/blueprint_tabletop_frame.html",
          },
          variables: {
            metric: "83,600 KM²",
            title: "UNITED ARAB EMIRATES",
          },
        },
        {
          overlay_id: "split_1",
          kind: "full_scene",
          template_id: "split_wipe_divider",
          timeline_start_s: 9.6,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "fullscreen",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/split_wipe_divider.html",
          },
          variables: {
            left_label: "GIBRALTAR",
            left_metric: "945 m",
            right_label: "CHANNEL",
            right_metric: "75 m",
            layout_mode: "vertical",
          },
        },
        {
          overlay_id: "arch_1",
          kind: "data_card",
          template_id: "historical_parchment_plate",
          timeline_start_s: 12.8,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/historical_parchment_plate.html",
          },
          variables: {
            year: "1803",
            title: "LOUISIANA PURCHASE",
            excerpt: "828,000 square miles transferred west of the Mississippi.",
          },
        },
        {
          overlay_id: "debunk_1",
          kind: "kinetic_callout",
          template_id: "myth_debunk_badge",
          timeline_start_s: 16.0,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/myth_debunk_badge.html",
          },
          variables: {
            mode: "red_x",
            claim_text: "MOUNT EVEREST",
            correction_text: "FARTHEST: MT. CHIMBORAZO",
          },
        },
      ],
    }),
    tmpDir,
    { platformTarget: target, copyAssets: false }
  );

  for (const file of compiled.compositionFiles) {
    const html = fs.readFileSync(file, "utf8");
    assert.match(html, /data-motion-blur="on"/);
    assert.doesNotMatch(html, /metric-rule|outro-rule|125,\s*211,\s*252|border-left:\s*[457]px|border-top:\s*4px/);
  }
  const lintResult = await lintHyperframesProjectDir(tmpDir);
  assert.equal(
    lintResult.totalErrors,
    0,
    `Expected 0 lint errors for cartographic suite, got: ${JSON.stringify(lintResult.hyperframesFindings)}`
  );
  assert.equal(lintResult.ok, true);
});

test("expanded documentary components and multi-family italic fonts compile lint-clean", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vedit-hf-expanded-suite-"));
  const target: PlatformTarget = {
    platform_id: "shorts_9x16_1080p",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zone: { top_pct: 0.14, bottom_pct: 0.22, left_pct: 0.06, right_pct: 0.16 },
  };
  const compiled = compileEditPlanToHyperframes(
    makeSamplePlan({
      brand_id: "geoverum",
      duration_s: 40.0,
      assets: [
        {
          asset_id: "font_sg",
          sha256: "1".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceGrotesk-Variable.ttf",
        },
        {
          asset_id: "font_ab",
          sha256: "2".repeat(64),
          kind: "font",
          path: "/nonexistent/ArchivoBlack-Regular.ttf",
        },
        {
          asset_id: "font_ebg",
          sha256: "3".repeat(64),
          kind: "font",
          path: "/nonexistent/EBGaramond-Variable.ttf",
        },
        {
          asset_id: "font_ebg_it",
          sha256: "4".repeat(64),
          kind: "font",
          path: "/nonexistent/EBGaramond-Italic-Variable.ttf",
        },
        {
          asset_id: "font_playfair",
          sha256: "5".repeat(64),
          kind: "font",
          path: "/nonexistent/PlayfairDisplay-Variable.ttf",
        },
        {
          asset_id: "font_mono_reg",
          sha256: "6".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceMono-Regular.ttf",
        },
        {
          asset_id: "font_mono_bold",
          sha256: "7".repeat(64),
          kind: "font",
          path: "/nonexistent/SpaceMono-Bold.ttf",
        },
        {
          asset_id: "font_mont",
          sha256: "8".repeat(64),
          kind: "font",
          path: "/nonexistent/Montserrat-Variable.ttf",
        },
      ],
      overlay_compositions: [
        {
          overlay_id: "tag_1",
          kind: "kinetic_callout",
          template_id: "coordinate_pin_callout",
          timeline_start_s: 0.0,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/coordinate_pin_callout.html",
          },
          variables: {
            pin_style: "highlight_tag",
            tag_tone: "amber",
            label: "2,000,000+ LAKES",
            anchor_x_pct: 50,
            anchor_y_pct: 46,
          },
        },
        {
          overlay_id: "etym_1",
          kind: "kinetic_callout",
          template_id: "coordinate_pin_callout",
          timeline_start_s: 3.2,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/coordinate_pin_callout.html",
          },
          variables: {
            pin_style: "etymology_arrow",
            label: "FLORIDA",
            meaning_text: "Land of flowers",
          },
        },
        {
          overlay_id: "rad_1",
          kind: "kinetic_callout",
          template_id: "dual_unit_distance_bracket",
          timeline_start_s: 6.4,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/dual_unit_distance_bracket.html",
          },
          variables: {
            line_style: "radius_ring",
            primary_distance: "8 km",
            secondary_distance: "(5 mi)",
          },
        },
        {
          overlay_id: "lasso_1",
          kind: "kinetic_callout",
          template_id: "organic_focus_lasso",
          timeline_start_s: 9.6,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/organic_focus_lasso.html",
          },
          variables: {
            stroke_tone: "amber",
            label: "GREAT BRITAIN",
          },
        },
        {
          overlay_id: "dual_1",
          kind: "kinetic_callout",
          template_id: "dual_metric_compare",
          timeline_start_s: 12.8,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/dual_metric_compare.html",
          },
          variables: {
            left_value: "4,700°C",
            left_secondary: "(8,492°F)",
            left_label: "CAVITATION",
            right_value: "5,500°C",
            right_secondary: "(9,932°F)",
            right_label: "SUN SURFACE",
          },
        },
        {
          overlay_id: "gauge_1",
          kind: "kinetic_callout",
          template_id: "physical_gauge_callout",
          timeline_start_s: 16.0,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/physical_gauge_callout.html",
          },
          variables: {
            gauge_mode: "decibel",
            start_value: 80,
            end_value: 210,
            unit: "dB",
            label: "PISTOL SHRIMP",
          },
        },
        {
          overlay_id: "mp_1",
          kind: "full_scene",
          template_id: "multi_panel_split",
          timeline_start_s: 19.2,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/multi_panel_split.html",
          },
          variables: {
            split_mode: "diagonal_3panel",
            panel1_label: "UAE",
            panel2_label: "ABU DHABI",
            panel3_label: "DUBAI",
          },
        },
        {
          overlay_id: "scale_1",
          kind: "full_scene",
          template_id: "scale_ladder_and_bands",
          timeline_start_s: 22.4,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/scale_ladder_and_bands.html",
          },
          variables: {
            mode: "altitude_ladder",
            title: "TIBETAN CEILING",
            t1_val: "33,000 FT",
            t1_label: "CRUISE ALTITUDE",
            t2_val: "14,800 FT",
            t2_label: "PLATEAU FLOOR",
            t3_val: "10,000 FT",
            t3_label: "OXYGEN LIMIT",
          },
        },
        {
          overlay_id: "portal_1",
          kind: "title_scene",
          template_id: "kinetic_portal_title",
          timeline_start_s: 25.6,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/kinetic_portal_title.html",
          },
          variables: {
            mode: "zoom_through",
            title: "ISLANDS",
          },
        },
        {
          overlay_id: "curtain_1",
          kind: "full_scene",
          template_id: "soft_curtain_transition",
          timeline_start_s: 28.8,
          timeline_duration_s: 2.4,
          transparent: true,
          safe_band: "center_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/soft_curtain_transition.html",
          },
          variables: {
            mode: "curtain_sweep",
            direction: "ltr",
            label: "NEXT CHAPTER",
          },
        },
        {
          overlay_id: "demo_1",
          kind: "data_card",
          template_id: "demographic_icon_grid",
          timeline_start_s: 31.4,
          timeline_duration_s: 3.0,
          transparent: true,
          safe_band: "upper_safe",
          props: {
            font_family: "Space Grotesk",
            display_family: "Archivo Black",
            motion_blur: true,
            composition_path:
              "profiles/brands/geoverum/templates/components/demographic_icon_grid.html",
          },
          variables: {
            title: "100TH MERIDIAN SPLIT",
            highlight_count: 2,
            left_pct: "20%",
            left_label: "WEST",
            right_pct: "80%",
            right_label: "EAST",
          },
        },
      ],
    }),
    tmpDir,
    { platformTarget: target, copyAssets: false }
  );

  const indexHtml = fs.readFileSync(compiled.indexHtmlPath, "utf8");
  assert.match(indexHtml, /font-family: 'EB Garamond';[\s\S]*?font-style: italic;/);
  assert.match(indexHtml, /font-family: 'Playfair Display';/);
  assert.match(indexHtml, /font-family: 'Space Mono';[\s\S]*?font-weight: 700;/);
  assert.match(indexHtml, /font-family: 'Montserrat';/);

  for (const file of compiled.compositionFiles) {
    const html = fs.readFileSync(file, "utf8");
    assert.match(html, /data-motion-blur="on"/);
    assert.doesNotMatch(
      html,
      /metric-rule|outro-rule|gv-bp-cross|gv-bp-kicker|gv-chap-kicker|gv-kp-kicker|gv-xs-kicker|gv-kicker|125,\s*211,\s*252|border-left:\s*[457]px|border-top:\s*4px|filter:\s*blur|backdrop-filter/
    );
  }
  const lintResult = await lintHyperframesProjectDir(tmpDir);
  assert.equal(
    lintResult.totalErrors,
    0,
    `Expected 0 lint errors for expanded documentary suite, got: ${JSON.stringify(lintResult.hyperframesFindings)}`
  );
  assert.equal(lintResult.ok, true);
});
