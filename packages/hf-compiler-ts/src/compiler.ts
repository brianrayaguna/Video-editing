import fs from "node:fs";
import path from "node:path";
import { GSAP_CDN } from "@hyperframes/core";
import {
  type EditPlan,
  type OverlayCompositionOp,
  type PlatformTarget,
  type SafeBand,
  type SafeZoneMargins,
} from "./contracts.js";
import { assertPlanStructure } from "./index.js";
import { lintPlanPerformance } from "./lint.js";

export interface CompileOptions {
  platformTarget?: PlatformTarget;
  copyAssets?: boolean;
}

export interface CompiledProjectResult {
  outDir: string;
  renderStrategy: EditPlan["render_strategy"];
  indexHtmlPath: string;
  compositionFiles: string[];
  copiedAssets: string[];
  recommendedFormat: "mov" | "mp4";
}

const BUNDLED_FAMILIES = [
  "Inter",
  "Montserrat",
  "Outfit",
  "Nunito",
  "Oswald",
  "League Gothic",
  "Archivo Black",
  "Space Mono",
  "IBM Plex Mono",
  "JetBrains Mono",
  "EB Garamond",
  "Playfair Display",
  "Source Code Pro",
  "Noto Sans JP",
  "Roboto",
  "Open Sans",
  "Lato",
  "Poppins",
];

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeId(raw: string): string {
  const cleaned = raw.replace(/[^a-zA-Z0-9_-]/g, "_").replace(/^[^a-zA-Z]+/, "id_");
  return cleaned || "scene_item";
}

function resolveFontFamily(raw: unknown): string {
  if (typeof raw !== "string" || !raw.trim()) {
    return "Inter";
  }
  const primary = raw.split(",")[0]?.replace(/['"]/g, "").trim() ?? "Inter";
  const found = BUNDLED_FAMILIES.find((f) => f.toLowerCase() === primary.toLowerCase());
  return found ?? "Inter";
}

function resolveCssHex(raw: unknown, fallback: string): string {
  if (typeof raw === "string" && /^#[0-9A-Fa-f]{6}$/.test(raw.trim())) {
    return raw.trim().toUpperCase();
  }
  return fallback;
}

function computeBandPositionCss(safeBand: SafeBand, safeZone: SafeZoneMargins): string {
  const topPct = Math.round(safeZone.top_pct * 1000) / 10;
  const bottomPct = Math.round(safeZone.bottom_pct * 1000) / 10;
  const leftPct = Math.round(Math.max(safeZone.left_pct, 0.06) * 1000) / 10;
  const rightPct = Math.round(Math.max(safeZone.right_pct, 0.06) * 1000) / 10;

  if (safeBand === "fullscreen") {
    return "inset: 0; display: flex; align-items: center; justify-content: center;";
  }
  if (safeBand === "upper_safe") {
    return (
      `top: ${topPct}%; left: ${leftPct}%; right: ${rightPct}%; ` +
      "display: flex; justify-content: center; align-items: flex-start;"
    );
  }
  if (safeBand === "center_safe") {
    return (
      `top: 50%; left: ${leftPct}%; right: ${rightPct}%; ` +
      "display: flex; justify-content: center; align-items: center; transform-origin: center center;"
    );
  }
  if (safeBand === "left_rail") {
    return (
      `top: ${topPct}%; bottom: ${bottomPct}%; left: ${leftPct}%; width: 34%; ` +
      "display: flex; flex-direction: column; justify-content: center;"
    );
  }
  if (safeBand === "right_rail") {
    return (
      `top: ${topPct}%; bottom: ${bottomPct}%; right: ${rightPct}%; width: 34%; ` +
      "display: flex; flex-direction: column; justify-content: center;"
    );
  }
  return (
    `bottom: ${bottomPct}%; left: ${leftPct}%; right: ${rightPct}%; ` +
    "display: flex; justify-content: center; align-items: flex-end;"
  );
}

function assignTrackLane(
  lanes: Array<Array<{ start: number; end: number }>>,
  start: number,
  duration: number
): number {
  const end = start + duration;
  for (let i = 0; i < lanes.length; i += 1) {
    const lane = lanes[i];
    if (!lane) {
      continue;
    }
    const overlaps = lane.some((slot) => Math.min(slot.end, end) - Math.max(slot.start, start) > 0.001);
    if (!overlaps) {
      lane.push({ start, end });
      return i + 1;
    }
  }
  lanes.push([{ start, end }]);
  return lanes.length;
}

function buildOverlayMarkup(ov: OverlayCompositionOp, innerId: string): string {
  const font = resolveFontFamily(ov.props.font_family);
  const headline = typeof ov.props.headline === "string"
    ? ov.props.headline
    : typeof ov.props.text === "string"
      ? ov.props.text
      : ov.overlay_id;
  const subtitle = typeof ov.props.subtitle === "string" ? ov.props.subtitle : "";

  if (ov.kind === "data_card" || ov.kind === "kinetic_callout" || ov.kind === "title_scene") {
    const subHtml = subtitle
      ? `<p class="vedit-subtitle">${escapeHtml(subtitle)}</p>`
      : "";
    return `<div id="${innerId}" class="vedit-card" style="font-family: '${font}', sans-serif;">
        <span class="vedit-badge">${escapeHtml(ov.kind.replace("_", " ").toUpperCase())}</span>
        <div class="vedit-headline">${escapeHtml(headline)}</div>
        ${subHtml}
      </div>`;
  }

  return `<div id="${innerId}" class="vedit-caption-pill" style="font-family: '${font}', sans-serif;">
      <span class="vedit-caption-text">${escapeHtml(headline)}</span>
    </div>`;
}

function buildOverlayCompositionHtml(
  ov: OverlayCompositionOp,
  sceneId: string,
  width: number,
  height: number,
  safeZone: SafeZoneMargins
): string {
  const band: SafeBand = ov.safe_band ?? "lower_third";
  const fg = resolveCssHex(ov.props.fg_color, "#F8FAFC");
  const bg = resolveCssHex(ov.props.bg_color, "#0B0F19");
  const accent = resolveCssHex(ov.props.accent_color, "#38BDF8");
  const clipId = `${sceneId}-clip`;
  const innerId = `${sceneId}-inner`;
  const duration = Number(ov.timeline_duration_s.toFixed(3));
  const enterDur = Number(Math.min(0.24, duration * 0.25).toFixed(3));
  const exitAt = Number(Math.max(0.05, duration - Math.min(0.18, duration * 0.2)).toFixed(3));
  const posCss = computeBandPositionCss(band, safeZone);
  const bgFill = ov.transparent ? "transparent" : "var(--vedit-ground)";
  const rootBgLayer = ov.transparent
    ? ""
    : `<div id="${sceneId}-bg" style="position: absolute; inset: 0; background: var(--vedit-ground);"></div>`;

  const innerMarkup = buildOverlayMarkup(ov, innerId);
  return `<template>
  <style>
    #root {
      position: absolute;
      inset: 0;
      overflow: hidden;
      background: ${bgFill};
      --vedit-ground: ${bg};
      --vedit-ink: ${fg};
      --vedit-accent: ${accent};
    }
    #${clipId} {
      position: absolute;
      ${posCss}
    }
    .vedit-caption-pill {
      background: rgba(11, 15, 25, 0.88);
      color: var(--vedit-ink);
      border: 2px solid var(--vedit-accent);
      border-radius: 12px;
      padding: 16px 24px;
      max-width: 100%;
      text-align: center;
      font-size: 40px;
      font-weight: 700;
      line-height: 1.2;
    }
    .vedit-card {
      background: var(--vedit-ground);
      color: var(--vedit-ink);
      border-left: 6px solid var(--vedit-accent);
      border-radius: 14px;
      padding: 20px 26px;
      max-width: 100%;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .vedit-badge {
      color: var(--vedit-accent);
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0.08em;
    }
    .vedit-headline {
      font-size: 44px;
      font-weight: 800;
      line-height: 1.15;
    }
    .vedit-subtitle {
      font-size: 28px;
      font-weight: 500;
      opacity: 0.9;
    }
  </style>
  <div id="root" data-composition-id="${sceneId}" data-width="${width}" data-height="${height}">
    ${rootBgLayer}
    <div id="${clipId}" class="clip" data-start="0" data-duration="${duration}">
      ${innerMarkup}
    </div>
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#${innerId}",
      { opacity: 0, y: 14 },
      { opacity: 1, y: 0, duration: ${enterDur}, ease: "power3.out" },
      0
    );
    tl.to("#${innerId}", { opacity: 0, duration: 0.14, ease: "power2.in" }, ${exitAt});
    window.__timelines = window.__timelines || {};
    window.__timelines["${sceneId}"] = tl;
  </script>
</template>
`;
}

function stageLocalAssets(plan: EditPlan, outDir: string, copyAssets: boolean): {
  assetPathsById: Map<string, string>;
  copiedAssets: string[];
} {
  const assetsDir = path.join(outDir, "assets");
  fs.mkdirSync(assetsDir, { recursive: true });
  const assetPathsById = new Map<string, string>();
  const copiedAssets: string[] = [];

  for (const asset of plan.assets) {
    const cleanId = sanitizeId(asset.asset_id);
    const ext = path.extname(asset.path) || (asset.kind.startsWith("audio") ? ".mp3" : ".mp4");
    const relPath = `assets/${cleanId}${ext}`;
    assetPathsById.set(asset.asset_id, relPath);

    if (copyAssets && fs.existsSync(asset.path) && fs.statSync(asset.path).isFile()) {
      const destPath = path.join(outDir, relPath);
      fs.copyFileSync(asset.path, destPath);
      copiedAssets.push(destPath);
    }
  }
  return { assetPathsById, copiedAssets };
}

export function compileEditPlanToHyperframes(
  plan: EditPlan,
  outDir: string,
  options: CompileOptions = {}
): CompiledProjectResult {
  assertPlanStructure(plan);
  const perfViolations = lintPlanPerformance(plan);
  if (perfViolations.length > 0) {
    const first = perfViolations[0];
    throw new Error(`CSS performance gate failed (${first?.location}): ${first?.message}`);
  }

  const safeZone: SafeZoneMargins = options.platformTarget?.safe_zone ?? {
    top_pct: 0.1,
    bottom_pct: 0.14,
    left_pct: 0.06,
    right_pct: 0.06,
  };

  fs.mkdirSync(outDir, { recursive: true });
  const compDir = path.join(outDir, "compositions");
  fs.mkdirSync(compDir, { recursive: true });

  const { assetPathsById, copiedAssets } = stageLocalAssets(
    plan,
    outDir,
    options.copyAssets ?? true
  );

  const lanes: Array<Array<{ start: number; end: number }>> = [];
  const hostTags: string[] = [];
  const compositionFiles: string[] = [];

  if (plan.render_strategy === "full_hf") {
    const videoLane = assignTrackLane(lanes, 0, plan.duration_s);
    for (const clip of plan.video_tracks) {
      const relSrc = assetPathsById.get(clip.asset_id) ?? "assets/missing.mp4";
      const cid = sanitizeId(clip.clip_id);
      const start = Number(clip.timeline_start_s.toFixed(3));
      const dur = Number(clip.timeline_duration_s.toFixed(3));
      const mediaStart = Number(clip.source_start_s.toFixed(3));
      hostTags.push(
        `      <video id="${cid}" class="clip" src="${escapeHtml(relSrc)}" ` +
          `data-start="${start}" data-duration="${dur}" data-media-start="${mediaStart}" ` +
          `data-track-index="${videoLane}" muted playsinline ` +
          `style="position: absolute; left: 0; top: 0; width: ${plan.width}px; height: ${plan.height}px; object-fit: cover;"></video>`
      );
    }
    for (const track of plan.audio_tracks) {
      const relSrc = assetPathsById.get(track.asset_id) ?? "assets/missing.mp3";
      const tid = sanitizeId(track.track_id);
      const start = Number(track.timeline_start_s.toFixed(3));
      const dur = Number(track.timeline_duration_s.toFixed(3));
      const mediaStart = Number(track.source_start_s.toFixed(3));
      const linearVol = Number(Math.min(3.98, Math.max(0.05, 10 ** ((track.gain_db ?? 0) / 20))).toFixed(3));
      const audioLane = assignTrackLane(lanes, start, dur);
      hostTags.push(
        `      <audio id="${tid}" class="clip" src="${escapeHtml(relSrc)}" ` +
          `data-start="${start}" data-duration="${dur}" data-media-start="${mediaStart}" ` +
          `data-volume="${linearVol}" data-track-index="${audioLane}"></audio>`
      );
    }
  }

  for (const ov of plan.overlay_compositions) {
    const sceneId = sanitizeId(ov.overlay_id);
    const scenePath = path.join(compDir, `${sceneId}.html`);
    const sceneHtml = buildOverlayCompositionHtml(ov, sceneId, plan.width, plan.height, safeZone);
    fs.writeFileSync(scenePath, sceneHtml, "utf8");
    compositionFiles.push(scenePath);

    const start = Number(ov.timeline_start_s.toFixed(3));
    const dur = Number(ov.timeline_duration_s.toFixed(3));
    const lane = assignTrackLane(lanes, start, dur);
    const trackKind = ov.kind === "caption_rail" ? "captions" : "graphics";
    hostTags.push(
      `      <div id="${sceneId}" data-composition-id="${sceneId}" ` +
        `data-composition-src="compositions/${sceneId}.html" ` +
        `data-start="${start}" data-duration="${dur}" ` +
        `data-track-index="${lane}" data-track-kind="${trackKind}" ` +
        `data-width="${plan.width}" data-height="${plan.height}"></div>`
    );
  }

  const rootBg = plan.render_strategy === "hybrid" ? "transparent" : "#000000";
  const totalDur = Number(plan.duration_s.toFixed(3));
  const indexHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(plan.project_id)} - ${escapeHtml(plan.job_id)}</title>
  <script src="${GSAP_CDN}"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: ${rootBg};
    }
    #root {
      position: relative;
      width: ${plan.width}px;
      height: ${plan.height}px;
      overflow: hidden;
      background: ${rootBg};
    }
  </style>
</head>
<body>
  <div id="root" data-composition-id="main" data-start="0" data-duration="${totalDur}" data-width="${plan.width}" data-height="${plan.height}">
${hostTags.join("\n")}
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.to({}, { duration: ${totalDur} });
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
`;

  const indexHtmlPath = path.join(outDir, "index.html");
  fs.writeFileSync(indexHtmlPath, indexHtml, "utf8");

  return {
    outDir,
    renderStrategy: plan.render_strategy,
    indexHtmlPath,
    compositionFiles,
    copiedAssets,
    recommendedFormat: plan.render_strategy === "hybrid" ? "mov" : "mp4",
  };
}
