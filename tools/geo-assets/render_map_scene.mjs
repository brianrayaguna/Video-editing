#!/usr/bin/env node
/**
 * Declarative Camera-Synced World-Space Map Scene Engine (`vedit geo bake-scene`).
 *
 * Thin CLI entrypoint delegating HTML builders, runtime modules, and Chromium
 * capture loops to `./scene/*.mjs`.
 */

import { existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import puppeteer from "puppeteer-core";
import sharp from "sharp";
import { getChromeArgs } from "./fast_capture.mjs";
import { coverageReport, startTileServer } from "./serve_tiles.mjs";
import { parseArgs, resolveChrome } from "./scene/cli_args.mjs";
import { bakeAct, coverageAct } from "./scene/bake_act.mjs";

async function main() {
  const args = parseArgs(process.argv);
  if (typeof args["scene-file"] !== "string" || typeof args["out-dir"] !== "string") {
    console.error("Usage: render_map_scene.mjs --scene-file <spec.json> --out-dir <dir> [--base-dir <dir>]");
    process.exit(1);
  }
  if (args["coverage-out"] === true) {
    throw new Error("--coverage-out requires a file path argument");
  }
  const coverageOnly = Boolean(args["coverage-only"]);
  const coverageOut = typeof args["coverage-out"] === "string" ? resolve(args["coverage-out"]) : null;
  if (coverageOnly && !coverageOut) {
    throw new Error("--coverage-only requires --coverage-out <file>");
  }
  if (coverageOut) {
    mkdirSync(dirname(coverageOut), { recursive: true });
  }
  const sceneFile = resolve(args["scene-file"]);
  const baseDir = resolve(typeof args["base-dir"] === "string" ? args["base-dir"] : dirname(sceneFile));
  const outDir = resolve(args["out-dir"]);
  mkdirSync(outDir, { recursive: true });

  const spec = JSON.parse(readFileSync(sceneFile, "utf8"));
  const width = Number(spec.width || 1080);
  const height = Number(spec.height || 1920);
  const fps = Number(spec.fps || 30);

  let vectorsObj = {};
  const vecSpec = spec.vectors_file || spec.vectors_path;
  if (vecSpec) {
    const vPath = isAbsolute(vecSpec) ? vecSpec : resolve(baseDir, vecSpec);
    if (!existsSync(vPath)) {
      throw new Error(`Map scene vectors file not found: ${vPath}`);
    }
    vectorsObj = JSON.parse(readFileSync(vPath, "utf8"));
  }
  if (spec.inline_vectors && typeof spec.inline_vectors === "object") {
    vectorsObj = { ...vectorsObj, ...spec.inline_vectors };
  }
  // Fail loud if any layer geom_ref or geom_refs entry is missing from the loaded vectors bundle.
  const checkGeomRef = (actId, ref) => {
    if (typeof ref !== "string") return;
    let cur = vectorsObj;
    for (const p of ref.split(".")) cur = cur && typeof cur === "object" ? cur[p] : undefined;
    if (!cur) {
      throw new Error(`Act '${actId}' references missing geom_ref '${ref}' (loaded keys: ${Object.keys(vectorsObj).join(", ")})`);
    }
  };
  for (const act of spec.acts || []) {
    for (const layer of act.layers || []) {
      if (typeof layer.geom_ref === "string") checkGeomRef(act.act_id, layer.geom_ref);
      if (Array.isArray(layer.geom_refs)) {
        for (const r of layer.geom_refs) checkGeomRef(act.act_id, r);
      }
    }
  }
  const vectorsJson = JSON.stringify(vectorsObj);

  const projectTilesSpec = spec.project_tiles_dir;
  const projectTilesDir = projectTilesSpec
    ? (isAbsolute(projectTilesSpec) ? projectTilesSpec : resolve(baseDir, projectTilesSpec))
    : null;
  const projectModelsSpec = spec.project_models_dir;
  const projectModelsDir = projectModelsSpec
    ? (isAbsolute(projectModelsSpec) ? projectModelsSpec : resolve(baseDir, projectModelsSpec))
    : (existsSync(resolve(baseDir, "models")) ? resolve(baseDir, "models") : null);
  const projectGraphicsSpec = spec.project_graphics_dir;
  const projectGraphicsDir = projectGraphicsSpec
    ? (isAbsolute(projectGraphicsSpec) ? projectGraphicsSpec : resolve(baseDir, projectGraphicsSpec))
    : (existsSync(resolve(baseDir, "../media/graphics"))
      ? resolve(baseDir, "../media/graphics")
      : (existsSync(resolve(baseDir, "graphics")) ? resolve(baseDir, "graphics") : null));

  let selectedActs = spec.acts || [];
  const onlyActs = args["only-act"];
  if (Array.isArray(onlyActs) && onlyActs.length > 0) {
    const known = new Set(selectedActs.map((a) => a.act_id));
    for (const id of onlyActs) {
      if (!known.has(id)) {
        throw new Error(`Unknown act_id '${id}' passed to --only-act (available: ${[...known].join(", ")})`);
      }
    }
    const want = new Set(onlyActs);
    selectedActs = selectedActs.filter((a) => want.has(a.act_id));
  }

  const rawPreview = args["preview-keyframes"];
  const previewTotal = rawPreview === true ? 12 : (typeof rawPreview === "string" ? Math.max(1, Number(rawPreview) || 12) : 0);
  const renderBackend =
    typeof args["render-backend"] === "string"
      ? args["render-backend"]
      : spec.render_backend || "auto";
  const cliCaptureFormat =
    typeof args["capture-format"] === "string" ? args["capture-format"] : undefined;
  const dedupStaticFrames = !Boolean(args["no-dedup-static-frames"]);

  const server = await startTileServer(0, "127.0.0.1", {
    recordGaps: Boolean(coverageOut),
    projectTilesDir,
    projectModelsDir,
    projectGraphicsDir,
  });
  const url = `http://127.0.0.1:${server.address().port}`;
  let browser = null;
  const allPreviewFrames = [];
  try {
    browser = await puppeteer.launch({
      executablePath: resolveChrome(),
      headless: "new",
      args: getChromeArgs(width, height, { backend: renderBackend }),
    });
    for (const act of selectedActs) {
      if (coverageOnly) {
        await coverageAct(browser, url, vectorsJson, width, height, fps, act);
      } else {
        const perActPreview = previewTotal > 0 ? Math.max(2, Math.ceil(previewTotal / Math.max(1, selectedActs.length))) : 0;
        const pFrames = await bakeAct(browser, url, vectorsJson, width, height, fps, act, outDir, {
          baseDir,
          previewKeyframes: perActPreview,
          ovScale: spec.ov_scale,
          captureFormat: cliCaptureFormat || spec.capture_format,
          captureQuality: spec.capture_quality,
          dedupStaticFrames,
          sunAzimuthDeg: spec.sun_azimuth_deg,
          sunElevationDeg: spec.sun_elevation_deg,
          hdrBloom: spec.hdr_bloom,
          showCredit: spec.show_credit,
        });
        if (perActPreview > 0 && Array.isArray(pFrames)) allPreviewFrames.push(...pFrames);
      }
    }
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.close();
  }
  if (previewTotal > 0 && allPreviewFrames.length > 0) {
    const previewDir = join(outDir, "preview_keyframes");
    mkdirSync(previewDir, { recursive: true });
    for (const pf of allPreviewFrames) {
      const pName = `${pf.act_id}_${pf.t_s.toFixed(2).replace(".", "_")}s.jpg`;
      writeFileSync(join(previewDir, pName), pf.buf);
    }
    const cols = Math.min(4, allPreviewFrames.length);
    const rows = Math.ceil(allPreviewFrames.length / cols);
    const thumbW = 360;
    const thumbH = Math.max(120, Math.round((height / width) * thumbW));
    const composites = await Promise.all(
      allPreviewFrames.map(async (pf, idx) => ({
        input: await sharp(pf.buf).resize(thumbW, thumbH).toBuffer(),
        left: (idx % cols) * thumbW,
        top: Math.floor(idx / cols) * thumbH,
      }))
    );
    const sheetPath = join(outDir, "preview_contact_sheet.jpg");
    await sharp({
      create: { width: cols * thumbW, height: rows * thumbH, channels: 3, background: { r: 6, g: 16, b: 24 } },
    })
      .composite(composites)
      .jpeg({ quality: 88 })
      .toFile(sheetPath);
    console.log(JSON.stringify({ ok: true, preview_frames: allPreviewFrames.length, contact_sheet: sheetPath }));
    return;
  }
  if (coverageOut) {
    const report = coverageReport(server.tileGaps);
    const tmpCov = `${coverageOut}.tmp`;
    try {
      writeFileSync(tmpCov, JSON.stringify(report));
      renameSync(tmpCov, coverageOut);
    } catch (err) {
      try {
        if (existsSync(tmpCov)) unlinkSync(tmpCov);
      } catch {
        // Ignore cleanup errors.
      }
      throw err;
    }
    console.log(`Coverage pass complete: ${report.tiles.length} tiles served from an upscaled ancestor -> ${coverageOut}`);
    if (coverageOnly) return;
  }
  console.log("Declarative map scene bake complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
