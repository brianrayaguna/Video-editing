import { isDistributedFps, type DistributedFps } from "@hyperframes/core";
import {
  assembleV2,
  planV2,
  readPlanV2Manifest,
  renderChunkV2,
  type AssembleResult,
  type DistributedRenderConfig,
  type EffectiveChunkResult,
  type PlanV2Manifest,
  type PlanV2Result,
} from "@hyperframes/producer/distributed";

export const DEFAULT_CHUNK_FRAMES = 180;
export const MIN_BOUNDED_CHUNK_FRAMES = 150;
export const MAX_BOUNDED_CHUNK_FRAMES = 240;

export interface CreateDistributedPlanOptions {
  projectDir: string;
  planV2Dir: string;
  fps: number;
  width: number;
  height: number;
  format: "mp4" | "mov";
  codec?: "h264" | "h265";
  quality?: "draft" | "standard" | "high";
  targetChunkFrames?: number;
  maxParallelChunks?: number;
  cfr?: boolean;
}

export function clampChunkFrameBudget(requested?: number): number {
  const val = requested !== undefined && Number.isFinite(requested) ? requested : DEFAULT_CHUNK_FRAMES;
  if (val < MIN_BOUNDED_CHUNK_FRAMES) {
    return MIN_BOUNDED_CHUNK_FRAMES;
  }
  if (val > MAX_BOUNDED_CHUNK_FRAMES) {
    return MAX_BOUNDED_CHUNK_FRAMES;
  }
  return Math.round(val);
}

export function resolveDistributedFps(fps: number): DistributedFps {
  const rounded = Math.round(fps);
  if (!isDistributedFps(rounded)) {
    throw new Error(
      `Unsupported distributed fps ${fps}. Supported integer rates: 24, 25, 30, 60.`
    );
  }
  return rounded;
}

export function buildDistributedConfig(opts: CreateDistributedPlanOptions): DistributedRenderConfig {
  const fps = resolveDistributedFps(opts.fps);
  const targetChunkFrames = clampChunkFrameBudget(opts.targetChunkFrames);

  const cfg: DistributedRenderConfig = {
    fps,
    width: opts.width,
    height: opts.height,
    format: opts.format,
    quality: opts.quality ?? "high",
    targetChunkFrames,
    maxParallelChunks: opts.maxParallelChunks ?? 48,
    hdrMode: "force-sdr",
    rejectOnSystemFonts: true,
    failClosedFontFetch: true,
    runtimeCap: "none",
  };

  if (opts.format === "mp4") {
    cfg.codec = opts.codec ?? "h264";
    cfg.cfr = opts.cfr ?? true;
  } else if (opts.format === "mov") {
    cfg.proresProfile = "4444";
  }

  return cfg;
}

export async function createDistributedPlan(
  opts: CreateDistributedPlanOptions
): Promise<{ plan: PlanV2Result; manifest: Readonly<PlanV2Manifest> }> {
  const cfg = buildDistributedConfig(opts);
  const plan = await planV2(opts.projectDir, cfg, opts.planV2Dir);
  const manifest = readPlanV2Manifest(opts.planV2Dir);
  return { plan, manifest };
}

export async function executeDistributedChunk(
  planV2Dir: string,
  chunkIndex: number,
  outputChunkPath: string,
  options?: { maxCaptureWorkers?: number }
): Promise<EffectiveChunkResult> {
  if (options?.maxCaptureWorkers !== undefined) {
    return renderChunkV2(planV2Dir, chunkIndex, outputChunkPath, {
      maxCaptureWorkers: options.maxCaptureWorkers,
    });
  }
  return renderChunkV2(planV2Dir, chunkIndex, outputChunkPath);
}

export async function assembleDistributedPlan(
  planV2Dir: string,
  chunkPaths: readonly string[],
  outputPath: string
): Promise<AssembleResult> {
  return assembleV2(planV2Dir, chunkPaths, outputPath);
}
