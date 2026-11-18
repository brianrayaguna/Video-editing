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
