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
  "Space Grotesk",
  "Unbounded",
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

interface StagedFontFace {
  family: string;
  relPath: string;
  format: string;
  weight: string;
}

function readTtfFamilyName(filePath: string): string | null {
  try {
    if (!fs.existsSync(filePath)) return null;
    const buf = fs.readFileSync(filePath);
    if (buf.length < 12) return null;
    const numTables = buf.readUInt16BE(4);
    let nameOffset = 0;
    let nameLength = 0;
    for (let i = 0; i < numTables; i += 1) {
      const rec = 12 + i * 16;
      if (rec + 16 > buf.length) break;
      const tag = buf.toString("ascii", rec, rec + 4);
      if (tag === "name") {
        nameOffset = buf.readUInt32BE(rec + 8);
        nameLength = buf.readUInt32BE(rec + 12);
        break;
      }
    }
    if (!nameOffset || nameOffset + 6 > buf.length || nameLength < 6) return null;
    const count = buf.readUInt16BE(nameOffset + 2);
    const strOffset = nameOffset + buf.readUInt16BE(nameOffset + 4);
    let fallbackName: string | null = null;
    for (let i = 0; i < count; i += 1) {
      const rec = nameOffset + 6 + i * 12;
      if (rec + 12 > buf.length) break;
      const platformId = buf.readUInt16BE(rec);
      const nameId = buf.readUInt16BE(rec + 6);
      if (nameId !== 1 && nameId !== 16) continue;
      const len = buf.readUInt16BE(rec + 8);
      const off = strOffset + buf.readUInt16BE(rec + 10);
      if (off + len > buf.length) continue;
      const slice = buf.subarray(off, off + len);
      const decoded =
        platformId === 3 || platformId === 0
          ? slice.swap16().toString("utf16le").replace(/\0/g, "").trim()
          : slice.toString("latin1").trim();
      if (!decoded) continue;
      if (nameId === 16) return decoded;
      fallbackName ??= decoded;
    }
    return fallbackName;
  } catch {
    return null;
  }
}

function inferFontDescriptor(assetPath: string, assetId: string): { family: string; weight: string } {
  const knownMap: Record<string, string> = {
    spacegrotesk: "Space Grotesk",
    archivoblack: "Archivo Black",
    unbounded: "Unbounded",
    spacemono: "Space Mono",
    inter: "Inter",
  };
  const base = path.basename(assetPath, path.extname(assetPath));
  const stem = base.replace(/[-_](Variable|Regular|Medium|SemiBold|Bold|Black|Light|Italic)$/i, "");
  const pathCompact = stem.toLowerCase().replace(/[^a-z0-9]/g, "");
  const idClean = assetId.replace(/^font[_-]?/i, "");
  const idCompact = idClean.toLowerCase().replace(/[^a-z0-9]/g, "");

  const ttfFamily = readTtfFamilyName(assetPath);
  const family =
    knownMap[pathCompact] ??
    knownMap[idCompact] ??
    ttfFamily ??
    (stem.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim() || assetId);

  let weight = "400";
  if (/variable/i.test(base) || /space.?grotesk|unbounded/i.test(family)) {
    weight = "100 900";
  } else if (/black/i.test(base) || /archivo.?black/i.test(family)) {
    weight = "400 900";
  } else if (/bold/i.test(base)) {
    weight = "700";
  }
  return { family, weight };
}

function resolveFontFormat(relPath: string): string {
  const ext = path.extname(relPath).toLowerCase();
  if (ext === ".woff2") return "woff2";
  if (ext === ".woff") return "woff";
  if (ext === ".otf") return "opentype";
  return "truetype";
}

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

function resolveFontFamily(raw: unknown, extraFamilies: readonly string[] = []): string {
  if (typeof raw !== "string" || !raw.trim()) {
    return "Inter";
  }
  const primary = raw.split(",")[0]?.replace(/['"]/g, "").trim() ?? "Inter";
  const found =
    extraFamilies.find((f) => f.toLowerCase() === primary.toLowerCase()) ??
    BUNDLED_FAMILIES.find((f) => f.toLowerCase() === primary.toLowerCase());
  return found ?? "Inter";
}

function resolveCssHex(raw: unknown, fallback: string): string {
  if (typeof raw === "string" && /^#[0-9A-Fa-f]{6}$/.test(raw.trim())) {
    return raw.trim().toUpperCase();
  }
  return fallback;
}

function computeBandPositionCss(
  safeBand: SafeBand,
  safeZone: SafeZoneMargins,
  explicitBox?: unknown
): string {
  if (
    explicitBox &&
    typeof explicitBox === "object" &&
    typeof (explicitBox as { top?: unknown }).top === "number" &&
    typeof (explicitBox as { bottom?: unknown }).bottom === "number"
  ) {
    const b = explicitBox as { top: number; bottom: number; left?: number; right?: number };
    const leftPct = Math.round(Math.max(b.left ?? safeZone.left_pct, safeZone.left_pct) * 1000) / 10;
    const rightPct =
      Math.round((1 - Math.min(b.right ?? 1 - safeZone.right_pct, 1 - safeZone.right_pct)) * 1000) /
      10;
    if (safeBand === "upper_safe") {
      const topPct = Math.round(b.top * 1000) / 10;
      return `top: ${topPct}%; left: ${leftPct}%; right: ${rightPct}%; display: flex; justify-content: center; align-items: flex-start;`;
    }
    const bottomPct = Math.round((1 - b.bottom) * 1000) / 10;
    return `bottom: ${bottomPct}%; left: ${leftPct}%; right: ${rightPct}%; display: flex; justify-content: center; align-items: flex-end;`;
  }

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

function renderCaptionHtml(text: string, highlightRaw: unknown, accentColor: string): string {
  const safe = escapeHtml(text);
  if (typeof highlightRaw !== "string" || !highlightRaw.trim()) {
    return safe;
  }
  const needle = highlightRaw.trim();
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx === -1) {
    return safe;
  }
  const before = escapeHtml(text.slice(0, idx));
  const match = escapeHtml(text.slice(idx, idx + needle.length));
  const after = escapeHtml(text.slice(idx + needle.length));
  return `${before}<span class="vedit-caption-accent" style="color: ${accentColor};">${match}</span>${after}`;
}

function buildOverlayMarkup(
  ov: OverlayCompositionOp,
  innerId: string,
  extraFamilies: readonly string[]
): string {
  if (typeof ov.props.custom_html === "string" && ov.props.custom_html.trim()) {
    const font = resolveFontFamily(ov.props.font_family, extraFamilies);
    return `<div id="${innerId}" class="vedit-custom-layer" style="width: 100%; height: 100%; font-family: '${font}', sans-serif;">
        ${ov.props.custom_html}
      </div>`;
  }

  const font = resolveFontFamily(ov.props.font_family, extraFamilies);
  const headline = typeof ov.props.headline === "string"
    ? ov.props.headline
    : typeof ov.props.text === "string"
      ? ov.props.text
      : ov.overlay_id;
  const subtitle = typeof ov.props.subtitle === "string" ? ov.props.subtitle : "";

  if (ov.kind === "data_card" || ov.kind === "kinetic_callout" || ov.kind === "title_scene") {
    const badgeText = typeof ov.props.badge === "string" ? ov.props.badge.trim() : "";
    const badgeHtml = badgeText
      ? `<span class="vedit-badge">${escapeHtml(badgeText)}</span>`
      : "";
    const subHtml = subtitle
      ? `<p class="vedit-subtitle">${escapeHtml(subtitle)}</p>`
      : "";
    return `<div id="${innerId}" class="vedit-card" style="font-family: '${font}', sans-serif;">
        ${badgeHtml}
        <div class="vedit-headline">${escapeHtml(headline)}</div>
        ${subHtml}
      </div>`;
  }

  const accent = resolveCssHex(ov.props.accent_color, "#F5C542");
  const renderedCaption = renderCaptionHtml(headline, ov.props.highlight_text, accent);
  return `<div id="${innerId}" class="vedit-caption-pill" style="font-family: '${font}', sans-serif;">
      <span class="vedit-caption-text">${renderedCaption}</span>
    </div>`;
}

function buildOverlayCompositionHtml(
  ov: OverlayCompositionOp,
  sceneId: string,
  width: number,
  height: number,
  safeZone: SafeZoneMargins,
  extraFamilies: readonly string[]
): string {
  const hasCustomHtml = typeof ov.props.custom_html === "string" && ov.props.custom_html.trim().length > 0;
  const band: SafeBand = ov.safe_band ?? "lower_third";
  const fg = resolveCssHex(ov.props.fg_color, "#F4F1EA");
  const bg = resolveCssHex(ov.props.bg_color, "#03161F");
  const accent = resolveCssHex(ov.props.accent_color, "#F5C542");
  const clipId = `${sceneId}-clip`;
  const innerId = `${sceneId}-inner`;
  const duration = Number(ov.timeline_duration_s.toFixed(3));
  const isCaption = ov.kind === "caption_rail";
  const entranceMs =
    typeof ov.props.entrance_ms === "number" && Number.isFinite(ov.props.entrance_ms)
      ? Math.max(40, Math.min(2000, Number(ov.props.entrance_ms)))
      : null;
  const easingFeel =
    typeof ov.props.easing_feel === "string" ? String(ov.props.easing_feel) : "snappy_ease_out";
  const easeName =
    easingFeel === "smooth_editorial"
      ? "power2.out"
      : easingFeel === "energetic_pop"
        ? "back.out(1.4)"
        : easingFeel === "minimal_static"
          ? "none"
          : "expo.out";
  const enterDur = Number(
    (
      entranceMs != null
        ? Math.min(entranceMs / 1000, duration * 0.45)
        : isCaption
          ? Math.min(0.12, duration * 0.2)
          : Math.min(0.22, duration * 0.25)
    ).toFixed(3)
  );
  const exitDur = Number((isCaption ? 0.08 : 0.13).toFixed(3));
  const exitAt = Number(Math.max(0.05, duration - exitDur).toFixed(3));
  const posCss = hasCustomHtml
    ? "inset: 0;"
    : computeBandPositionCss(band, safeZone, ov.props.box);
  const bgFill = ov.transparent ? "transparent" : "var(--vedit-ground)";
  const rootBgLayer = ov.transparent
    ? ""
    : `<div id="${sceneId}-bg" style="position: absolute; inset: 0; background: var(--vedit-ground);"></div>`;
  const customCss = typeof ov.props.custom_css === "string" ? ov.props.custom_css : "";

  const innerMarkup = buildOverlayMarkup(ov, innerId, extraFamilies);
  const timelineScript =
    typeof ov.props.custom_timeline_js === "string" && ov.props.custom_timeline_js.trim()
      ? ov.props.custom_timeline_js
      : hasCustomHtml
        ? `const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#${innerId}",
      { opacity: 0 },
      { opacity: 1, duration: ${enterDur}, ease: "expo.out" },
      0
    );
    tl.to("#${innerId}", { opacity: 0, duration: ${exitDur}, ease: "power2.in" }, ${exitAt});
    window.__timelines = window.__timelines || {};
    window.__timelines["${sceneId}"] = tl;`
        : `const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#${innerId}",
      { opacity: 0, scale: 0.96, y: ${isCaption ? 4 : 8} },
      { opacity: 1, scale: 1, y: 0, duration: ${enterDur}, ease: "${easeName}" },
      0
    );
    tl.to("#${innerId}", { opacity: 0, duration: ${exitDur}, ease: "power2.in" }, ${exitAt});
    window.__timelines = window.__timelines || {};
    window.__timelines["${sceneId}"] = tl;`;

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
      font-variant-numeric: tabular-nums;
    }
    #${clipId} {
      position: absolute;
      ${posCss}
    }
    .vedit-caption-pill {
      background: rgba(3, 22, 31, 0.80);
      color: var(--vedit-ink);
      border-radius: 6px;
      padding: 8px 20px;
      max-width: 86%;
      text-align: center;
      font-size: 36px;
      font-weight: 600;
      line-height: 1.24;
      letter-spacing: -0.01em;
    }
    .vedit-card {
      background: var(--vedit-ground);
      color: var(--vedit-ink);
      border-left: 4px solid var(--vedit-accent);
      border-radius: 8px;
      padding: 16px 22px;
      max-width: 88%;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transform-origin: left center;
    }
    .vedit-badge {
      color: var(--vedit-accent);
      font-size: 16px;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
    .vedit-headline {
      font-size: 38px;
      font-weight: 700;
      line-height: 1.18;
      letter-spacing: -0.02em;
    }
    .vedit-subtitle {
      font-size: 24px;
      font-weight: 500;
      line-height: 1.35;
      opacity: 0.88;
    }
    ${customCss}
  </style>
  <div id="root" data-composition-id="${sceneId}" data-width="${width}" data-height="${height}">
    ${rootBgLayer}
    <div id="${clipId}" class="clip" data-start="0" data-duration="${duration}">
      ${innerMarkup}
    </div>
  </div>
  <script>
    ${timelineScript}
  </script>
</template>
`;
}

function stageLocalAssets(plan: EditPlan, outDir: string, copyAssets: boolean): {
  assetPathsById: Map<string, string>;
  copiedAssets: string[];
  stagedFonts: StagedFontFace[];
} {
  const assetsDir = path.join(outDir, "assets");
  fs.mkdirSync(assetsDir, { recursive: true });
  const assetPathsById = new Map<string, string>();
  const copiedAssets: string[] = [];
  const stagedFonts: StagedFontFace[] = [];

  for (const asset of plan.assets) {
    const cleanId = sanitizeId(asset.asset_id);
    const fallbackExt =
      asset.kind === "font"
        ? ".ttf"
        : asset.kind.startsWith("audio")
          ? ".mp3"
          : ".mp4";
    const ext = path.extname(asset.path) || fallbackExt;
    const relPath = `assets/${cleanId}${ext}`;
    assetPathsById.set(asset.asset_id, relPath);

    if (copyAssets && fs.existsSync(asset.path) && fs.statSync(asset.path).isFile()) {
      const destPath = path.join(outDir, relPath);
      fs.copyFileSync(asset.path, destPath);
      copiedAssets.push(destPath);
    }

    if (asset.kind === "font") {
      const desc = inferFontDescriptor(asset.path, asset.asset_id);
      stagedFonts.push({
        family: desc.family,
        relPath,
        format: resolveFontFormat(relPath),
        weight: desc.weight,
      });
    }
  }
  return { assetPathsById, copiedAssets, stagedFonts };
}

function buildLocalFontFaceCss(fonts: readonly StagedFontFace[]): string {
  if (fonts.length === 0) {
    return "";
  }
  return fonts
    .map(
      (f) => `    @font-face {
      font-family: '${f.family}';
      src: url('${f.relPath}') format('${f.format}');
      font-weight: ${f.weight};
      font-style: normal;
      font-display: block;
    }`
    )
    .join("\n");
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

  const { assetPathsById, copiedAssets, stagedFonts } = stageLocalAssets(
    plan,
    outDir,
    options.copyAssets ?? true
  );
  const extraFontFamilies = stagedFonts.map((f) => f.family);

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
    const mergedProps = { ...(ov.variables ?? {}), ...ov.props };
    const effectiveOv: OverlayCompositionOp = { ...ov, props: mergedProps };
    const catalogPath =
      typeof mergedProps.composition_path === "string" ? String(mergedProps.composition_path) : "";
    if (catalogPath && fs.existsSync(catalogPath) && fs.statSync(catalogPath).isFile()) {
      fs.copyFileSync(catalogPath, scenePath);
    } else {
      const sceneHtml = buildOverlayCompositionHtml(
        effectiveOv,
        sceneId,
        plan.width,
        plan.height,
        safeZone,
        extraFontFamilies
      );
      fs.writeFileSync(scenePath, sceneHtml, "utf8");
    }
    compositionFiles.push(scenePath);

    const start = Number(ov.timeline_start_s.toFixed(3));
    const dur = Number(ov.timeline_duration_s.toFixed(3));
    const lane = assignTrackLane(lanes, start, dur);
    const trackKind = ov.kind === "caption_rail" ? "captions" : "graphics";
    const templateAttr = ov.template_id
      ? ` data-template-id="${escapeHtml(ov.template_id)}"`
      : "";
    hostTags.push(
      `      <div id="${sceneId}" data-composition-id="${sceneId}" ` +
        `data-composition-src="compositions/${sceneId}.html" ` +
        `data-start="${start}" data-duration="${dur}" ` +
        `data-track-index="${lane}" data-track-kind="${trackKind}"` +
        `${templateAttr} ` +
        `data-width="${plan.width}" data-height="${plan.height}"></div>`
    );
  }

  const rootBg = plan.render_strategy === "hybrid" ? "transparent" : "#000000";
  const totalDur = Number(plan.duration_s.toFixed(3));
  const localFontCss = buildLocalFontFaceCss(stagedFonts);
  const fontStyleBlock = localFontCss
    ? `\n  <style data-vedit-local-fonts="true">\n${localFontCss}\n  </style>`
    : "";
  const indexHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(plan.project_id)} - ${escapeHtml(plan.job_id)}</title>
  <script src="${GSAP_CDN}"></script>${fontStyleBlock}
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
