import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
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
  style: "normal" | "italic";
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

function inferFontDescriptor(
  assetPath: string,
  assetId: string
): { family: string; weight: string; style: "normal" | "italic" } {
  const knownMap: Record<string, string> = {
    spacegrotesk: "Space Grotesk",
    archivoblack: "Archivo Black",
    unbounded: "Unbounded",
    spacemono: "Space Mono",
    inter: "Inter",
    montserrat: "Montserrat",
    ebgaramond: "EB Garamond",
    ebgaramonditalic: "EB Garamond",
    playfairdisplay: "Playfair Display",
  };
  const base = path.basename(assetPath, path.extname(assetPath));
  const style: "normal" | "italic" = /italic/i.test(base) || /italic/i.test(assetId) ? "italic" : "normal";
  const stem = base
    .replace(/[-_](Italic[-_])?(Variable|Regular|Medium|SemiBold|Bold|Black|Light|Italic)$/i, "")
    .replace(/[-_]Italic$/i, "");
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
  if (
    /variable/i.test(base) ||
    /space.?grotesk|unbounded|inter|montserrat|eb.?garamond|playfair.?display/i.test(family)
  ) {
    weight = "100 900";
  } else if (/black/i.test(base) || /archivo.?black/i.test(family)) {
    weight = "400 900";
  } else if (/bold/i.test(base)) {
    weight = "700";
  }
  return { family, weight, style };
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

function hexToRgba(hex: string, alpha: number): string {
  const clean = resolveCssHex(hex, "#0F172A");
  const r = parseInt(clean.slice(1, 3), 16);
  const g = parseInt(clean.slice(3, 5), 16);
  const b = parseInt(clean.slice(5, 7), 16);
  const clamped = Math.max(0, Math.min(1, alpha));
  return `rgba(${r}, ${g}, ${b}, ${Number(clamped.toFixed(2))})`;
}

function buildTextGlowCss(glowColorRaw: unknown, glowStrengthRaw: unknown): {
  glowColor: string;
  textShadow: string;
} {
  const defaultShadow = "0 2px 6px rgba(0, 0, 0, 0.88), 0 0 2px rgba(0, 0, 0, 0.96)";
  let strength = "none";
  if (typeof glowStrengthRaw === "number" && Number.isFinite(glowStrengthRaw)) {
    if (glowStrengthRaw > 0.8) strength = "intense";
    else if (glowStrengthRaw > 0.4) strength = "luminous";
    else if (glowStrengthRaw > 0) strength = "subtle";
  } else if (typeof glowStrengthRaw === "string") {
    strength = glowStrengthRaw.trim().toLowerCase();
  }
  if (strength === "none" || strength === "" || strength === "off") {
    return { glowColor: "", textShadow: defaultShadow };
  }
  const color = resolveCssHex(glowColorRaw, "");
  if (!color) {
    return { glowColor: "", textShadow: defaultShadow };
  }
  if (strength === "subtle") {
    return {
      glowColor: color,
      textShadow: `0 0 10px ${hexToRgba(color, 0.72)}, 0 0 22px ${hexToRgba(color, 0.42)}, ${defaultShadow}`,
    };
  }
  if (strength === "intense") {
    return {
      glowColor: color,
      textShadow: `0 0 8px ${hexToRgba(color, 0.98)}, 0 0 20px ${hexToRgba(color, 0.86)}, 0 0 42px ${hexToRgba(color, 0.62)}, 0 0 72px ${hexToRgba(color, 0.36)}, ${defaultShadow}`,
    };
  }
  // Default luminous glow
  return {
    glowColor: color,
    textShadow: `0 0 8px ${hexToRgba(color, 0.92)}, 0 0 22px ${hexToRgba(color, 0.68)}, 0 0 46px ${hexToRgba(color, 0.4)}, ${defaultShadow}`,
  };
}

interface CatalogTemplateMatch {
  compositionPath: string;
  defaults: Record<string, unknown>;
}

const brandCatalogCache = new Map<string, Map<string, CatalogTemplateMatch> | null>();

function resolveBrandTemplateEntry(
  brandId: string,
  templateId: string
): CatalogTemplateMatch | null {
  if (!brandId || !templateId) return null;
  const repoRoot = findRepoRootForTemplates();
  if (!repoRoot) return null;
  const cacheKey = `${repoRoot}::${brandId}`;
  let table = brandCatalogCache.get(cacheKey);
  if (table === undefined) {
    const catalogFile = path.join(repoRoot, "profiles", "brands", brandId, "templates", "catalog.json");
    if (!fs.existsSync(catalogFile)) {
      brandCatalogCache.set(cacheKey, null);
      return null;
    }
    try {
      const parsed = JSON.parse(fs.readFileSync(catalogFile, "utf8")) as {
        templates?: Array<{
          template_id?: string;
          composition_path?: string;
          variables?: Array<{ id?: string; default?: unknown }>;
        }>;
      };
      table = new Map<string, CatalogTemplateMatch>();
      for (const entry of parsed.templates ?? []) {
        if (!entry.template_id || !entry.composition_path) continue;
        const defaults: Record<string, unknown> = {};
        for (const v of entry.variables ?? []) {
          if (v.id && v.default !== undefined) {
            defaults[v.id] = v.default;
          }
        }
        table.set(entry.template_id, {
          compositionPath: entry.composition_path,
          defaults,
        });
      }
      brandCatalogCache.set(cacheKey, table);
    } catch {
      brandCatalogCache.set(cacheKey, null);
      return null;
    }
  }
  return table?.get(templateId) ?? null;
}

function findRepoRootForTemplates(): string | null {
  const envRoot = process.env.VEDIT_REPO_ROOT?.trim();
  if (envRoot && fs.existsSync(path.join(envRoot, "contracts"))) {
    return path.resolve(envRoot);
  }
  const moduleDir = path.dirname(fileURLToPath(import.meta.url));
  for (const start of [path.resolve(process.cwd()), moduleDir]) {
    let cursor = start;
    for (let i = 0; i < 8; i += 1) {
      if (fs.existsSync(path.join(cursor, "contracts"))) {
        return cursor;
      }
      const parent = path.dirname(cursor);
      if (parent === cursor) break;
      cursor = parent;
    }
  }
  return null;
}

function resolveTemplateCompositionPath(rawPath: string): string | null {
  if (!rawPath) return null;
  if (path.isAbsolute(rawPath)) {
    return fs.existsSync(rawPath) && fs.statSync(rawPath).isFile() ? rawPath : null;
  }
  const cwdCandidate = path.resolve(process.cwd(), rawPath);
  if (fs.existsSync(cwdCandidate) && fs.statSync(cwdCandidate).isFile()) {
    return cwdCandidate;
  }
  const repoRoot = findRepoRootForTemplates();
  if (repoRoot) {
    const rootCandidate = path.resolve(repoRoot, rawPath);
    if (fs.existsSync(rootCandidate) && fs.statSync(rootCandidate).isFile()) {
      return rootCandidate;
    }
  }
  return null;
}

function computeSymmetricMarginPct(safeZone: SafeZoneMargins): number {
  return Math.round(Math.max(safeZone.left_pct, safeZone.right_pct, 0.06) * 1000) / 10;
}

function computeCaptionBottomPct(safeZone: SafeZoneMargins, width: number, height: number): number {
  const isPortrait = height > width;
  // On 9:16, center captions vertically around y=70% (bottom ~28.5%) inside safe margins.
  const floor = isPortrait ? 0.285 : 0.095;
  return Math.round(Math.max(safeZone.bottom_pct, floor) * 1000) / 10;
}

function computeProportionalCaptionFontPx(width: number, height: number): number {
  const isPortrait = height > width;
  return isPortrait ? Math.round(width * 0.041) : Math.round(height * 0.039);
}

function computeBandPositionCss(
  safeBand: SafeBand,
  safeZone: SafeZoneMargins,
  width: number,
  height: number,
  explicitBox?: unknown
): string {
  if (
    explicitBox &&
    typeof explicitBox === "object" &&
    typeof (explicitBox as { top?: unknown }).top === "number" &&
    typeof (explicitBox as { bottom?: unknown }).bottom === "number"
  ) {
    const b = explicitBox as { top: number; bottom: number; left?: number; right?: number };
    const leftVal = typeof b.left === "number" ? b.left : safeZone.left_pct;
    const rightVal = typeof b.right === "number" ? b.right : 1 - safeZone.right_pct;
    const leftPct = Math.round(leftVal * 1000) / 10;
    const rightPct = Math.round((1 - rightVal) * 1000) / 10;
    if (safeBand === "upper_safe") {
      const topPct = Math.round(b.top * 1000) / 10;
      return `top: ${topPct}%; left: ${leftPct}%; right: ${rightPct}%; display: flex; justify-content: center; align-items: flex-start;`;
    }
    const bottomPct = Math.round((1 - b.bottom) * 1000) / 10;
    return `bottom: ${bottomPct}%; left: ${leftPct}%; right: ${rightPct}%; display: flex; justify-content: center; align-items: flex-end;`;
  }

  const topPct = Math.round(safeZone.top_pct * 1000) / 10;
  const bottomPct = computeCaptionBottomPct(safeZone, width, height);
  const leftPct = Math.round(Math.max(safeZone.left_pct, 0.06) * 1000) / 10;
  const rightPct = Math.round(Math.max(safeZone.right_pct, 0.06) * 1000) / 10;
  // Symmetric horizontal padding guarantees true horizontal centering (x = 50%)
  // while respecting asymmetric platform UI safe margins (e.g., Shorts right rail).
  const symX = computeSymmetricMarginPct(safeZone);

  if (safeBand === "fullscreen") {
    return "inset: 0; display: flex; align-items: center; justify-content: center;";
  }
  if (safeBand === "upper_safe") {
    return (
      `top: ${topPct}%; left: ${symX}%; right: ${symX}%; ` +
      "display: flex; justify-content: center; align-items: flex-start;"
    );
  }
  if (safeBand === "center_safe") {
    return (
      `top: ${topPct}%; bottom: ${bottomPct}%; left: ${symX}%; right: ${symX}%; ` +
      "display: flex; justify-content: center; align-items: center;"
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
    `bottom: ${bottomPct}%; left: ${symX}%; right: ${symX}%; ` +
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

  const bodyFont = resolveFontFamily(ov.props.font_family, extraFamilies);
  const displayFont = resolveFontFamily(
    ov.props.display_family ?? ov.props.font_family,
    extraFamilies
  );
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
    return `<div id="${innerId}" class="vedit-card" style="font-family: '${bodyFont}', sans-serif;">
        ${badgeHtml}
        <div class="vedit-headline" style="font-family: '${displayFont}', sans-serif;">${escapeHtml(headline)}</div>
        ${subHtml}
      </div>`;
  }

  const accent = resolveCssHex(ov.props.accent_color, "#38BDF8");
  const captionStyle =
    typeof ov.props.caption_style === "string" ? ov.props.caption_style : "plain";
  const captionClass = captionStyle === "chip" ? "vedit-caption-pill" : "vedit-caption-plain";
  const renderedCaption = renderCaptionHtml(headline, ov.props.highlight_text, accent);
  return `<div id="${innerId}" class="${captionClass}" style="font-family: '${bodyFont}', sans-serif;">
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
  const fg = resolveCssHex(ov.props.fg_color, "#F8FAFC");
  const bg = resolveCssHex(ov.props.bg_color, "#0F172A");
  const accent = resolveCssHex(ov.props.accent_color, "#38BDF8");
  const bgRgba = hexToRgba(bg, 0.8);
  const { textShadow: glowTextShadow } = buildTextGlowCss(
    ov.props.glow_color,
    ov.props.glow_strength
  );
  const clipId = `${sceneId}-clip`;
  const innerId = `${sceneId}-inner`;
  const duration = Number(ov.timeline_duration_s.toFixed(3));
  const isCaption = ov.kind === "caption_rail";
  const scaleFactor = Math.min(width, height) / 1080;
  const captionFontPx = computeProportionalCaptionFontPx(width, height);
  const headlineFontPx = Math.round(48 * scaleFactor);
  const subtitleFontPx = Math.round(24 * scaleFactor);
  const badgeFontPx = Math.round(16 * scaleFactor);

  const entranceMs =
    typeof ov.props.entrance_ms === "number" && Number.isFinite(ov.props.entrance_ms)
      ? Math.max(40, Math.min(2000, Number(ov.props.entrance_ms)))
      : null;
  const captionTransitionMs =
    typeof ov.props.caption_transition_ms === "number" && Number.isFinite(ov.props.caption_transition_ms)
      ? Math.max(0, Math.min(200, Number(ov.props.caption_transition_ms)))
      : 33;
  const easingFeel =
    typeof ov.props.easing_feel === "string" ? String(ov.props.easing_feel) : "snappy_ease_out";
  const easeName =
    easingFeel === "smooth_editorial"
      ? "expo.out"
      : easingFeel === "energetic_pop"
        ? "back.out(1.4)"
        : easingFeel === "minimal_static"
          ? "none"
          : "expo.out";
  const enterDur = Number(
    (isCaption
      ? Math.min(captionTransitionMs / 1000, duration * 0.2)
      : entranceMs != null
        ? Math.min(entranceMs / 1000, duration * 0.45)
        : Math.min(0.26, duration * 0.25)
    ).toFixed(3)
  );
  const exitDur = Number((isCaption ? Math.min(captionTransitionMs / 1000, 0.033) : Math.max(0.11, enterDur * 0.48)).toFixed(3));
  const exitAt = Number(Math.max(0.05, duration - exitDur).toFixed(3));
  const posCss = hasCustomHtml
    ? "inset: 0;"
    : computeBandPositionCss(band, safeZone, width, height, ov.props.box);
  const bgFill = ov.transparent ? "transparent" : "var(--vedit-ground)";
  const rootBgLayer = ov.transparent
    ? ""
    : `<div id="${sceneId}-bg" style="position: absolute; inset: 0; background: var(--vedit-ground);"></div>`;
  const customCss = typeof ov.props.custom_css === "string" ? ov.props.custom_css : "";

  const innerMarkup = buildOverlayMarkup(ov, innerId, extraFamilies);
  const timelineScript =
    typeof ov.props.custom_timeline_js === "string" && ov.props.custom_timeline_js.trim()
      ? ov.props.custom_timeline_js
      : isCaption
        ? `const tl = gsap.timeline({ paused: true });
    ${
      enterDur > 0
        ? `tl.fromTo("#${innerId}", { opacity: 0 }, { opacity: 1, duration: ${enterDur}, ease: "none" }, 0);`
        : `tl.set("#${innerId}", { opacity: 1 }, 0);`
    }
    ${
      exitDur > 0
        ? `tl.to("#${innerId}", { opacity: 0, duration: ${exitDur}, ease: "none" }, ${exitAt});`
        : `tl.set("#${innerId}", { opacity: 0 }, ${duration});`
    }
    window.__timelines = window.__timelines || {};
    window.__timelines["${sceneId}"] = tl;`
        : hasCustomHtml
          ? `const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#${innerId}",
      { opacity: 0 },
      { opacity: 1, duration: ${enterDur}, ease: "${easeName}" },
      0
    );
    tl.to("#${innerId}", { opacity: 0, duration: ${exitDur}, ease: "power3.in" }, ${exitAt});
    window.__timelines = window.__timelines || {};
    window.__timelines["${sceneId}"] = tl;`
          : `const tl = gsap.timeline({ paused: true });
    tl.fromTo(
      "#${innerId}",
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: ${enterDur}, ease: "${easeName}" },
      0
    );
    tl.to("#${innerId}", { opacity: 0, y: -8, duration: ${exitDur}, ease: "power3.in" }, ${exitAt});
    window.__timelines = window.__timelines || {};
    window.__timelines["${sceneId}"] = tl;`;

  const motionBlurAttr = ov.props.motion_blur
    ? ` data-motion-blur="on"${
        typeof ov.props.motion_blur_shutter === "number"
          ? ` data-motion-blur-shutter="${Math.round(ov.props.motion_blur_shutter)}"`
          : ""
      }`
    : "";

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
      --vedit-text-glow: ${glowTextShadow};
      font-variant-numeric: tabular-nums;
    }
    #${clipId} {
      position: absolute;
      ${posCss}
    }
    .vedit-caption-plain {
      background: transparent;
      color: var(--vedit-ink);
      padding: 0;
      max-width: 100%;
      text-align: center;
      font-size: ${captionFontPx}px;
      font-weight: 600;
      line-height: 1.24;
      letter-spacing: -0.01em;
      text-shadow: var(--vedit-text-glow);
    }
    .vedit-caption-pill {
      background: ${bgRgba};
      color: var(--vedit-ink);
      border-radius: 6px;
      padding: 8px 20px;
      max-width: 100%;
      text-align: center;
      font-size: ${captionFontPx}px;
      font-weight: 600;
      line-height: 1.24;
      letter-spacing: -0.01em;
    }
    .vedit-card {
      background: transparent;
      color: var(--vedit-ink);
      padding: 0;
      max-width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: ${Math.round(6 * scaleFactor)}px;
      text-shadow: var(--vedit-text-glow);
    }
    .vedit-badge {
      color: var(--vedit-accent);
      font-size: ${badgeFontPx}px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .vedit-headline {
      font-size: ${headlineFontPx}px;
      font-weight: 800;
      line-height: 1.08;
      letter-spacing: -0.02em;
    }
    .vedit-subtitle {
      font-size: ${subtitleFontPx}px;
      font-weight: 600;
      line-height: 1.3;
      opacity: 0.9;
    }
    ${customCss}
  </style>
  <div id="root" data-composition-id="${sceneId}" data-width="${width}" data-height="${height}"${motionBlurAttr}>
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

function renderParameterizedTemplate(
  templateHtml: string,
  ov: OverlayCompositionOp,
  sceneId: string,
  width: number,
  height: number,
  safeZone: SafeZoneMargins,
  extraFamilies: readonly string[]
): string {
  const isPortrait = height > width;
  const scaleFactor = Math.min(width, height) / 1080;
  const duration = Number(ov.timeline_duration_s.toFixed(3));
  const fg = resolveCssHex(ov.props.fg_color, "#F8FAFC");
  const bg = resolveCssHex(ov.props.bg_color, "#0F172A");
  const accent = resolveCssHex(ov.props.accent_color, "#38BDF8");
  const bodyFont = resolveFontFamily(ov.props.font_family, extraFamilies);
  const displayFont = resolveFontFamily(
    ov.props.display_family ?? ov.props.font_family,
    extraFamilies
  );
  const captionTransitionMs =
    typeof ov.props.caption_transition_ms === "number" && Number.isFinite(ov.props.caption_transition_ms)
      ? Math.max(0, Math.min(200, Number(ov.props.caption_transition_ms)))
      : 33;
  const captionTransitionS = Number(Math.min(captionTransitionMs / 1000, duration * 0.2).toFixed(3));
  const entranceMs =
    typeof ov.props.entrance_ms === "number" && Number.isFinite(ov.props.entrance_ms)
      ? Math.max(40, Math.min(2000, Number(ov.props.entrance_ms)))
      : 260;
  const enterS = Number(Math.min(entranceMs / 1000, duration * 0.45).toFixed(3));
  const exitS = Number(Math.min(Math.max(0.12, enterS * 0.48), duration * 0.25).toFixed(3));
  const exitAtS = Number(Math.max(0.05, duration - exitS).toFixed(3));
  const captionExitAtS = Number(Math.max(0.02, duration - captionTransitionS).toFixed(3));
  const easingFeel =
    typeof ov.props.easing_feel === "string" ? String(ov.props.easing_feel) : "smooth_editorial";
  const easeName =
    easingFeel === "smooth_editorial"
      ? "expo.out"
      : easingFeel === "energetic_pop"
        ? "back.out(1.4)"
        : easingFeel === "minimal_static"
          ? "none"
          : "expo.out";

  const symXPct = computeSymmetricMarginPct(safeZone);
  const captionBottomPct = computeCaptionBottomPct(safeZone, width, height);
  const captionFontPx = computeProportionalCaptionFontPx(width, height);
  const watermarkFontPx = Math.round(18 * scaleFactor);
  const watermarkTopPct = isPortrait ? 16.0 : 7.5;
  const watermarkRightPct = isPortrait ? 5.5 : 5.0;
  const rawText =
    typeof ov.props.text === "string"
      ? ov.props.text
      : typeof ov.props.label === "string"
        ? ov.props.label
        : typeof ov.props.headline === "string"
          ? ov.props.headline
          : "";
  const captionMarkup = renderCaptionHtml(rawText, ov.props.highlight_text, accent);
  const { glowColor, textShadow: textGlowCss } = buildTextGlowCss(
    ov.props.glow_color ?? accent,
    ov.props.glow_strength ?? "none"
  );

  const tokens: Record<string, string> = {
    SCENE_ID: sceneId,
    WIDTH: String(width),
    HEIGHT: String(height),
    DURATION_S: String(duration),
    SCALE_FACTOR: String(Number(scaleFactor.toFixed(3))),
    IS_PORTRAIT: isPortrait ? "true" : "false",
    ASPECT_MODE: isPortrait ? "9x16" : "16x9",
    SAFE_TOP_PCT: String(Math.round(safeZone.top_pct * 1000) / 10),
    SAFE_BOTTOM_PCT: String(Math.round(safeZone.bottom_pct * 1000) / 10),
    SAFE_LEFT_PCT: String(Math.round(safeZone.left_pct * 1000) / 10),
    SAFE_RIGHT_PCT: String(Math.round(safeZone.right_pct * 1000) / 10),
    SYM_X_PCT: String(symXPct),
    CAPTION_BOTTOM_PCT: String(captionBottomPct),
    CAPTION_FONT_PX: String(captionFontPx),
    WATERMARK_FONT_PX: String(watermarkFontPx),
    WATERMARK_TOP_PCT: String(watermarkTopPct),
    WATERMARK_RIGHT_PCT: String(watermarkRightPct),
    FG_COLOR: fg,
    BG_COLOR: bg,
    BG_RGBA_78: hexToRgba(bg, 0.78),
    ACCENT_COLOR: accent,
    GLOW_COLOR: glowColor || accent,
    TEXT_GLOW_CSS: textGlowCss,
    BODY_FONT: bodyFont,
    DISPLAY_FONT: displayFont,
    EASE_NAME: easeName,
    ENTRANCE_S: String(enterS),
    EXIT_S: String(exitS),
    EXIT_AT_S: String(exitAtS),
    CAPTION_TRANSITION_S: String(captionTransitionS),
    CAPTION_EXIT_AT_S: String(captionExitAtS),
    CAPTION_HTML: captionMarkup,
    MOTION_BLUR_ATTR: ov.props.motion_blur
      ? `data-motion-blur="on"${
          typeof ov.props.motion_blur_shutter === "number"
            ? ` data-motion-blur-shutter="${Math.round(ov.props.motion_blur_shutter)}"`
            : ""
        }`
      : "",
  };

  for (const [key, val] of Object.entries(ov.props)) {
    if (val === undefined || val === null) continue;
    const upper = key.toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    if (typeof val === "string") {
      tokens[`VAR_${upper}`] = /^#[0-9A-Fa-f]{6}$/.test(val.trim())
        ? val.trim().toUpperCase()
        : escapeHtml(val);
    } else if (typeof val === "number" || typeof val === "boolean") {
      tokens[`VAR_${upper}`] = String(val);
    }
  }

  return templateHtml.replace(/\{\{([A-Z0-9_]+)(?:\|([^}]*))?\}\}/g, (_match, key: string, fallback?: string) => {
    if (Object.prototype.hasOwnProperty.call(tokens, key)) {
      return tokens[key] ?? "";
    }
    return fallback !== undefined ? fallback : "";
  });
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
    if (plan.render_strategy === "hybrid" && asset.kind !== "font" && asset.kind !== "image") {
      continue;
    }
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
        style: desc.style,
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
      font-style: ${f.style};
      font-display: block;
    }`
    )
    .join("\n");
}

function injectOverlayTrackKeyframes(
  html: string,
  ov: OverlayCompositionOp,
  width: number,
  height: number
): string {
  const kfs = ov.track_keyframes;
  if (!kfs || kfs.length === 0) {
    return html;
  }
  const sorted = [...kfs].sort((a, b) => a.t_s - b.t_s);
  const first = sorted[0]!;
  const baseX = first.x_pct;
  const baseY = first.y_pct;
  const payload = sorted.map((kf) => ({
    t: Number(kf.t_s.toFixed(4)),
    dx: Number((((kf.x_pct - baseX) / 100) * width).toFixed(2)),
    dy: Number((((kf.y_pct - baseY) / 100) * height).toFixed(2)),
    scale: kf.scale ?? 1,
    rotation: kf.rotation_deg ?? 0,
    rotationX: kf.rotateX_deg ?? 0,
    perspective: kf.perspective_px ?? 0,
    opacity: kf.opacity ?? 1,
  }));
  const originX = Number(((baseX / 100) * width).toFixed(1));
  const originY = Number(((baseY / 100) * height).toFixed(1));
  const has3d = payload.some((k) => Math.abs(k.rotationX) > 0.01 || k.perspective > 0);
  const trackScript = `
  <script data-vedit-object-track="true">
    (function() {
      var target = document.getElementById("root") || document.body.firstElementChild;
      if (!target || typeof gsap === "undefined") return;
      var kfs = ${JSON.stringify(payload)};
      gsap.set(target, {
        transformOrigin: "${originX}px ${originY}px",
        x: kfs[0].dx,
        y: kfs[0].dy,
        scale: kfs[0].scale,
        rotation: kfs[0].rotation,${
          has3d
            ? `
        rotationX: kfs[0].rotationX,
        transformPerspective: kfs[0].perspective || 1600,`
            : ""
        }
        opacity: kfs[0].opacity
      });
      var trackTl = gsap.timeline({ paused: true });
      for (var i = 1; i < kfs.length; i++) {
        var prev = kfs[i - 1];
        var curr = kfs[i];
        var segDur = Math.max(0.001, curr.t - prev.t);
        trackTl.to(target, {
          x: curr.dx,
          y: curr.dy,
          scale: curr.scale,
          rotation: curr.rotation,${
            has3d
              ? `
          rotationX: curr.rotationX,
          transformPerspective: curr.perspective || 1600,`
              : ""
          }
          opacity: curr.opacity,
          duration: segDur,
          ease: "none"
        }, prev.t);
      }
      if (window.__hf && typeof window.__hf.register === "function") {
        window.__hf.register(trackTl);
      } else {
        trackTl.play();
      }
    })();
  </script>`;
  if (html.includes("</body>")) {
    return html.replace("</body>", `${trackScript}\n</body>`);
  }
  return `${html}\n${trackScript}`;
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

  const hasCaptions = plan.overlay_compositions.some((ov) => ov.kind === "caption_rail");
  const captionLane = hasCaptions ? assignTrackLane(lanes, 0, plan.duration_s) : -1;

  for (const ov of plan.overlay_compositions) {
    const sceneId = sanitizeId(ov.overlay_id);
    const scenePath = path.join(compDir, `${sceneId}.html`);
    const catalogMatch =
      ov.template_id && typeof ov.props.composition_path !== "string"
        ? resolveBrandTemplateEntry(plan.brand_id, ov.template_id)
        : null;
    const mergedProps: Record<string, unknown> = {
      ...(catalogMatch?.defaults ?? {}),
      ...(ov.variables ?? {}),
      ...ov.props,
    };
    if (catalogMatch && typeof mergedProps.composition_path !== "string") {
      mergedProps.composition_path = catalogMatch.compositionPath;
    }
    const effectiveOv: OverlayCompositionOp = { ...ov, props: mergedProps };
    const catalogPathRaw =
      typeof mergedProps.composition_path === "string" ? String(mergedProps.composition_path).trim() : "";
    const resolvedTemplatePath = catalogPathRaw ? resolveTemplateCompositionPath(catalogPathRaw) : null;
    if (catalogPathRaw && !resolvedTemplatePath) {
      throw new Error(
        `Overlay ${ov.overlay_id} (template_id=${ov.template_id ?? "none"}) references missing composition_path: ${catalogPathRaw}`
      );
    }
    if (
      ov.template_id &&
      !resolvedTemplatePath &&
      findRepoRootForTemplates() !== null &&
      fs.existsSync(
        path.join(findRepoRootForTemplates()!, "profiles", "brands", plan.brand_id, "templates", "catalog.json")
      )
    ) {
      throw new Error(
        `Overlay ${ov.overlay_id} references unknown template_id '${ov.template_id}' for brand '${plan.brand_id}'.`
      );
    }
    if (resolvedTemplatePath) {
      const rawTemplate = fs.readFileSync(resolvedTemplatePath, "utf8");
      const rendered = renderParameterizedTemplate(
        rawTemplate,
        effectiveOv,
        sceneId,
        plan.width,
        plan.height,
        safeZone,
        extraFontFamilies
      );
      fs.writeFileSync(
        scenePath,
        injectOverlayTrackKeyframes(rendered, effectiveOv, plan.width, plan.height),
        "utf8"
      );
    } else {
      const sceneHtml = buildOverlayCompositionHtml(
        effectiveOv,
        sceneId,
        plan.width,
        plan.height,
        safeZone,
        extraFontFamilies
      );
      fs.writeFileSync(
        scenePath,
        injectOverlayTrackKeyframes(sceneHtml, effectiveOv, plan.width, plan.height),
        "utf8"
      );
    }
    compositionFiles.push(scenePath);

    const start = Number(ov.timeline_start_s.toFixed(3));
    const dur = Number(ov.timeline_duration_s.toFixed(3));
    const lane = ov.kind === "caption_rail" ? captionLane : assignTrackLane(lanes, start, dur);
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
