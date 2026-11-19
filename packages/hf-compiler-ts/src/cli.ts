#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";
import { compileEditPlanToHyperframes } from "./compiler.js";
import type { EditPlan, PlatformTarget } from "./contracts.js";
import {
  assembleDistributedPlan,
  createDistributedPlan,
  executeDistributedChunk,
} from "./distributed.js";
import { lintHyperframesProjectDir } from "./lint.js";

function readJson<T>(filePath: string): T {
  return JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
}

async function main(): Promise<void> {
  const [command, ...rest] = process.argv.slice(2);
  if (!command) {
    console.error("Usage: hf-compiler <compile|lint|plan-v2|render-chunk-v2|assemble-v2> ...");
    process.exit(2);
  }

  if (command === "compile") {
    const { values } = parseArgs({
      args: rest,
      options: {
        plan: { type: "string" },
        "out-dir": { type: "string" },
        platform: { type: "string" },
        lint: { type: "boolean", default: true },
        "copy-assets": { type: "boolean", default: true },
      },
      allowNegative: true,
    });
    if (!values.plan || !values["out-dir"]) {
      throw new Error("compile requires --plan and --out-dir");
    }
    const plan = readJson<EditPlan>(values.plan);
    const compileOpts = values.platform
      ? {
          platformTarget: readJson<PlatformTarget>(values.platform),
          copyAssets: values["copy-assets"] ?? true,
        }
      : { copyAssets: values["copy-assets"] ?? true };

    const compiled = compileEditPlanToHyperframes(plan, path.resolve(values["out-dir"]), compileOpts);
    const lintSummary = values.lint ? await lintHyperframesProjectDir(compiled.outDir) : null;
    console.log(JSON.stringify({ compiled, lint: lintSummary }, null, 2));
    if (lintSummary && !lintSummary.ok) {
      process.exitCode = 1;
    }
    return;
  }

  if (command === "lint") {
    const { values } = parseArgs({
      args: rest,
      options: { "project-dir": { type: "string" }, entry: { type: "string" } },
    });
    if (!values["project-dir"]) {
      throw new Error("lint requires --project-dir");
    }
    const summary = await lintHyperframesProjectDir(
      path.resolve(values["project-dir"]),
      values.entry ?? "index.html"
    );
    console.log(JSON.stringify(summary, null, 2));
    if (!summary.ok) {
      process.exitCode = 1;
    }
    return;
  }

  if (command === "plan-v2") {
    const { values } = parseArgs({
      args: rest,
      options: {
        "project-dir": { type: "string" },
        "plan-v2-dir": { type: "string" },
        fps: { type: "string" },
        width: { type: "string" },
        height: { type: "string" },
        format: { type: "string", default: "mp4" },
        quality: { type: "string", default: "high" },
        "chunk-frames": { type: "string" },
        "max-parallel-chunks": { type: "string" },
      },
    });
    if (
      !values["project-dir"] ||
      !values["plan-v2-dir"] ||
      !values.fps ||
      !values.width ||
      !values.height
    ) {
      throw new Error("plan-v2 requires --project-dir, --plan-v2-dir, --fps, --width, --height");
    }
    const fmt = values.format === "mov" ? "mov" : "mp4";
    const quality =
      values.quality === "draft" || values.quality === "standard" ? values.quality : "high";
    const result = await createDistributedPlan({
      projectDir: path.resolve(values["project-dir"]),
      planV2Dir: path.resolve(values["plan-v2-dir"]),
      fps: Number(values.fps),
      width: Number(values.width),
      height: Number(values.height),
      format: fmt,
      quality,
      ...(values["chunk-frames"] ? { targetChunkFrames: Number(values["chunk-frames"]) } : {}),
      ...(values["max-parallel-chunks"]
        ? { maxParallelChunks: Number(values["max-parallel-chunks"]) }
        : {}),
    });
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  if (command === "render-chunk-v2") {
    const { values } = parseArgs({
      args: rest,
      options: {
        "plan-v2-dir": { type: "string" },
        "chunk-index": { type: "string" },
        out: { type: "string" },
        "max-capture-workers": { type: "string" },
      },
    });
    if (!values["plan-v2-dir"] || values["chunk-index"] === undefined || !values.out) {
      throw new Error("render-chunk-v2 requires --plan-v2-dir, --chunk-index, and --out");
    }
    const maxWorkers = values["max-capture-workers"]
      ? Number(values["max-capture-workers"])
      : undefined;
    const chunk = await executeDistributedChunk(
      path.resolve(values["plan-v2-dir"]),
      Number(values["chunk-index"]),
      path.resolve(values.out),
      maxWorkers && Number.isFinite(maxWorkers) && maxWorkers > 0
        ? { maxCaptureWorkers: Math.round(maxWorkers) }
        : undefined
    );
    console.log(JSON.stringify(chunk, null, 2));
    return;
  }

  if (command === "assemble-v2") {
    const { values } = parseArgs({
      args: rest,
      options: {
        "plan-v2-dir": { type: "string" },
        "chunks-json": { type: "string" },
        out: { type: "string" },
      },
    });
    if (!values["plan-v2-dir"] || !values["chunks-json"] || !values.out) {
      throw new Error("assemble-v2 requires --plan-v2-dir, --chunks-json, and --out");
    }
    const chunkPaths = readJson<string[]>(values["chunks-json"]);
    const assembled = await assembleDistributedPlan(
      path.resolve(values["plan-v2-dir"]),
      chunkPaths,
      path.resolve(values.out)
    );
    console.log(JSON.stringify(assembled, null, 2));
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
