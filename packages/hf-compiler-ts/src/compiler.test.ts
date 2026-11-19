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
  // Hard cut transition (0.05s <= 50ms).
  assert.match(capHtml, /duration: 0\.05/);

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
            kicker: "BAB 02",
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
