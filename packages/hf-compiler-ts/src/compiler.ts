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
import { lintPlanPerformance, NON_FATAL_WARNING_CODES } from "./lint.js";

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
  "Archivo Black",
  "Unbounded",
  "Bebas Neue",
  "Oswald",
  "Anton",
  "League Gothic",
  "Syne",
  "Barlow Condensed",
  "Cinzel",
  "Rubik",
  "Space Grotesk",
  "Inter",
  "Montserrat",
  "Plus Jakarta Sans",
  "Roboto",
  "Poppins",
  "Outfit",
  "DM Sans",
  "Manrope",
  "Open Sans",
  "Lato",
  "Nunito",
  "Sora",
  "Work Sans",
  "EB Garamond",
  "Playfair Display",
  "Lora",
  "Merriweather",
  "Libre Baskerville",
  "Instrument Serif",
  "Space Mono",
  "IBM Plex Mono",
  "JetBrains Mono",
  "Source Code Pro",
  "Courier Prime",
  "Caveat",
  "Permanent Marker",
  "Patrick Hand",
];

interface StagedFontFace {
  family: string;
  relPath: string;
  format: string;
  weight: string;
  style: "normal" | "italic";
  isVariable?: boolean;
}

interface TtfWeightAxisInfo {
  isVariable: boolean;
  minWeight: number;
  maxWeight: number;
}

interface TtfMetadata {
  familyName: string | null;
  weightAxis: TtfWeightAxisInfo | null;
}

const ttfMetadataCache = new Map<string, TtfMetadata>();

const KNOWN_FONT_FAMILY_MAP: Readonly<Record<string, string>> = {
  archivoblack: "Archivo Black",
  unbounded: "Unbounded",
  bebasneue: "Bebas Neue",
  oswald: "Oswald",
  anton: "Anton",
  leaguegothic: "League Gothic",
  syne: "Syne",
  barlowcondensed: "Barlow Condensed",
  cinzel: "Cinzel",
  rubik: "Rubik",
  spacegrotesk: "Space Grotesk",
  inter: "Inter",
  montserrat: "Montserrat",
  plusjakartasans: "Plus Jakarta Sans",
  roboto: "Roboto",
  poppins: "Poppins",
  outfit: "Outfit",
  dmsans: "DM Sans",
  manrope: "Manrope",
  opensans: "Open Sans",
  lato: "Lato",
  nunito: "Nunito",
  sora: "Sora",
  worksans: "Work Sans",
  ebgaramond: "EB Garamond",
  ebgaramonditalic: "EB Garamond",
  playfairdisplay: "Playfair Display",
  lora: "Lora",
  merriweather: "Merriweather",
  librebaskerville: "Libre Baskerville",
  instrumentserif: "Instrument Serif",
  spacemono: "Space Mono",
  ibmplexmono: "IBM Plex Mono",
  jetbrainsmono: "JetBrains Mono",
  sourcecodepro: "Source Code Pro",
  courierprime: "Courier Prime",
  caveat: "Caveat",
  permanentmarker: "Permanent Marker",
  patrickhand: "Patrick Hand",
};

function readTtfMetadata(filePath: string): TtfMetadata {
  try {
    if (!fs.existsSync(filePath)) {
      return { familyName: null, weightAxis: null };
    }
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) {
      return { familyName: null, weightAxis: null };
    }
    const cacheKey = `${path.resolve(filePath)}::${stat.mtimeMs}::${stat.size}`;
    const cached = ttfMetadataCache.get(cacheKey);
    if (cached) return cached;

    const buf = fs.readFileSync(filePath);
    let weightAxis: TtfWeightAxisInfo | null = null;
    let familyName: string | null = null;
    if (buf.length >= 12) {
      const numTables = buf.readUInt16BE(4);
      let fvarOff = 0;
      let os2Off = 0;
      let nameOffset = 0;
      let nameLength = 0;
      for (let i = 0; i < numTables; i += 1) {
        const rec = 12 + i * 16;
        if (rec + 16 > buf.length) break;
        const tag = buf.toString("ascii", rec, rec + 4);
        if (tag === "fvar") fvarOff = buf.readUInt32BE(rec + 8);
        else if (tag === "OS/2") os2Off = buf.readUInt32BE(rec + 8);
        else if (tag === "name") {
          nameOffset = buf.readUInt32BE(rec + 8);
          nameLength = buf.readUInt32BE(rec + 12);
        }
      }
      if (fvarOff && fvarOff + 12 <= buf.length) {
        const axesOff = buf.readUInt16BE(fvarOff + 4);
        const axisCount = buf.readUInt16BE(fvarOff + 8);
        const axisSize = buf.readUInt16BE(fvarOff + 10);
        for (let i = 0; i < axisCount; i += 1) {
          const off = fvarOff + axesOff + i * axisSize;
          if (off + 16 > buf.length) break;
          const axisTag = buf.toString("ascii", off, off + 4);
          if (axisTag === "wght") {
            const minW = Math.max(1, Math.min(1000, Math.round(buf.readInt32BE(off + 4) / 65536)));
            const maxW = Math.max(minW, Math.min(1000, Math.round(buf.readInt32BE(off + 12) / 65536)));
            weightAxis = { isVariable: true, minWeight: minW, maxWeight: maxW };
            break;
          }
        }
      }
      if (!weightAxis && os2Off && os2Off + 6 <= buf.length) {
        const w = Math.max(100, Math.min(1000, buf.readUInt16BE(os2Off + 4)));
        weightAxis = { isVariable: false, minWeight: w, maxWeight: w };
      }
      if (nameOffset && nameOffset + 6 <= buf.length && nameLength >= 6) {
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
          if ((platformId === 3 || platformId === 0) && len % 2 !== 0) continue;
          const slice = Buffer.from(buf.subarray(off, off + len));
          const decoded =
            platformId === 3 || platformId === 0
              ? slice.swap16().toString("utf16le").replace(/\0/g, "").trim()
              : slice.toString("latin1").trim();
          if (!decoded) continue;
          if (nameId === 16) {
            familyName = decoded;
            break;
          }
          fallbackName ??= decoded;
        }
        familyName ??= fallbackName;
      }
    }
    const meta: TtfMetadata = { familyName, weightAxis };
    ttfMetadataCache.set(cacheKey, meta);
    return meta;
  } catch {
    return { familyName: null, weightAxis: null };
  }
}

function inferKnownFontFamilyHint(fileName: string): string | null {
  const base = path.basename(fileName, path.extname(fileName));
  const stem = base
    .replace(
      /[-_](Italic[-_])?(Variable|Regular|ExtraLight|Light|Medium|SemiBold|Bold|ExtraBold|Black|Italic)+$/i,
      ""
    )
    .replace(/[-_](BoldItalic|BlackItalic|Italic)$/i, "");
  const pathCompact = stem.toLowerCase().replace(/[^a-z0-9]/g, "");
  return KNOWN_FONT_FAMILY_MAP[pathCompact] ?? null;
}

function inferFontDescriptor(
  assetPath: string,
  assetId: string
): { family: string; weight: string; style: "normal" | "italic"; isVariable: boolean } {
  const base = path.basename(assetPath, path.extname(assetPath));
  const style: "normal" | "italic" = /italic/i.test(base) || /italic/i.test(assetId) ? "italic" : "normal";
  const stem = base
    .replace(
      /[-_](Italic[-_])?(Variable|Regular|ExtraLight|Light|Medium|SemiBold|Bold|ExtraBold|Black|Italic)+$/i,
      ""
    )
    .replace(/[-_](BoldItalic|BlackItalic|Italic)$/i, "");
  const pathCompact = stem.toLowerCase().replace(/[^a-z0-9]/g, "");
  const idClean = assetId.replace(/^font[_-]?/i, "");
  const idCompact = idClean.toLowerCase().replace(/[^a-z0-9]/g, "");

  const ttfMeta = readTtfMetadata(assetPath);
  const family =
    KNOWN_FONT_FAMILY_MAP[pathCompact] ??
    KNOWN_FONT_FAMILY_MAP[idCompact] ??
    ttfMeta.familyName ??
    (stem.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim() || assetId);

  const axisInfo = ttfMeta.weightAxis;
  let isVariable = axisInfo ? axisInfo.isVariable : /variable/i.test(base);
  let weight = "400";
  if (axisInfo?.isVariable) {
    weight = `${axisInfo.minWeight} ${axisInfo.maxWeight}`;
    isVariable = true;
  } else if (axisInfo && !axisInfo.isVariable) {
    weight = String(axisInfo.minWeight);
    isVariable = false;
  } else if (/variable/i.test(base)) {
    weight = "100 900";
    isVariable = true;
  } else if (/(?:^|[-_])(extra[-_]?bold|ultrabold)(?:italic)?$/i.test(base)) {
    weight = "800";
  } else if (/(?:^|[-_])(semi[-_]?bold|demibold)(?:italic)?$/i.test(base)) {
    weight = "600";
  } else if (/(?:^|[-_])black(?:italic)?$/i.test(base)) {
    weight = "900";
  } else if (/(?:^|[-_])bold(?:italic)?$/i.test(base)) {
    weight = "700";
  } else if (/(?:^|[-_])medium(?:italic)?$/i.test(base)) {
    weight = "500";
  } else if (/(?:^|[-_])(extra[-_]?light|ultralight)(?:italic)?$/i.test(base)) {
    weight = "200";
  } else if (/(?:^|[-_])light(?:italic)?$/i.test(base)) {
    weight = "300";
  } else if (
    !/[-_](regular|italic)$/i.test(base) &&
    /space.?grotesk|unbounded|inter|montserrat|eb.?garamond|playfair.?display|rubik|plus.?jakarta.?sans|oswald|outfit|dm.?sans|manrope|open.?sans|nunito|sora|work.?sans|lora|merriweather|cinzel|syne|jetbrains.?mono|source.?code.?pro|caveat/i.test(
      family
    )
  ) {
    weight = "100 900";
    isVariable = true;
  }
  return { family, weight, style, isVariable };
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

function escapeCssString(text: string): string {
  return text
    .replace(/[\r\n]+/g, " ")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/<\/style/gi, "<\\/style")
    .trim();
}

function sanitizeId(raw: string): string {
  const cleaned = raw.replace(/[^a-zA-Z0-9_-]/g, "_");
  if (!cleaned) return "scene_item";
  return /^[a-zA-Z]/.test(cleaned) ? cleaned : `id_${cleaned}`;
}

function allocateUniqueId(raw: string, usedIds: Set<string>): string {
  const base = sanitizeId(raw);
  if (!usedIds.has(base)) {
    usedIds.add(base);
    return base;
  }
  let suffix = 2;
  while (usedIds.has(`${base}_${suffix}`)) {
    suffix += 1;
  }
  const unique = `${base}_${suffix}`;
  usedIds.add(unique);
  return unique;
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
  variableTypes: Record<string, string>;
  variableEnums: Record<string, string[]>;
}

const ALLOWED_BLEND_MODES = new Set(["normal", "screen", "multiply", "overlay", "lighten"]);

function isPathContainedIn(candidate: string, baseDir: string): boolean {
  try {
    const resolvedBase = fs.existsSync(baseDir) ? fs.realpathSync(baseDir) : path.resolve(baseDir);
    const resolvedCand = fs.existsSync(candidate) ? fs.realpathSync(candidate) : path.resolve(candidate);
    const rel = path.relative(resolvedBase, resolvedCand);
    return rel !== "" && !rel.startsWith("..") && !path.isAbsolute(rel);
  } catch {
    return false;
  }
}

const brandCatalogCache = new Map<string, Map<string, CatalogTemplateMatch> | null>();

function resolveBrandTemplateEntry(
  brandId: string,
  templateId: string
): CatalogTemplateMatch | null {
  if (!brandId || !templateId) return null;
  if (!/^[a-zA-Z0-9_-]+$/.test(brandId)) return null;
  const repoRoot = findRepoRootForTemplates();
  if (!repoRoot) return null;
  const cacheKey = `${repoRoot}::${brandId}`;
  let table = brandCatalogCache.get(cacheKey);
  if (table === undefined) {
    const brandsRoot = path.join(repoRoot, "profiles", "brands");
    const catalogFile = path.join(brandsRoot, brandId, "templates", "catalog.json");
    if (!fs.existsSync(catalogFile) || !isPathContainedIn(catalogFile, brandsRoot)) {
      brandCatalogCache.set(cacheKey, null);
      return null;
    }
    try {
      const parsed = JSON.parse(fs.readFileSync(catalogFile, "utf8")) as {
        templates?: Array<{
          template_id?: string;
          composition_path?: string;
          variables?: Array<{ id?: string; type?: string; default?: unknown; enum_values?: unknown }>;
        }>;
      };
      table = new Map<string, CatalogTemplateMatch>();
      for (const entry of parsed.templates ?? []) {
        if (!entry.template_id || !entry.composition_path) continue;
        const defaults: Record<string, unknown> = {};
        const variableTypes: Record<string, string> = {};
        const variableEnums: Record<string, string[]> = {};
        for (const v of entry.variables ?? []) {
          if (v.id) {
            if (v.type) variableTypes[v.id] = v.type;
            if (v.default !== undefined) defaults[v.id] = v.default;
            if (Array.isArray(v.enum_values)) {
              variableEnums[v.id] = v.enum_values.map((item) => String(item));
            }
          }
        }
        table.set(entry.template_id, {
          compositionPath: entry.composition_path,
          defaults,
          variableTypes,
          variableEnums,
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
  const repoRoot = findRepoRootForTemplates();
  const allowedRoots = [repoRoot, process.cwd()].filter((r): r is string => Boolean(r));
  if (path.isAbsolute(rawPath)) {
    if (!fs.existsSync(rawPath) || !fs.statSync(rawPath).isFile()) return null;
    return allowedRoots.some((root) => isPathContainedIn(rawPath, root)) ? rawPath : null;
  }
  const cwdCandidate = path.resolve(process.cwd(), rawPath);
  if (
    fs.existsSync(cwdCandidate) &&
    fs.statSync(cwdCandidate).isFile() &&
    allowedRoots.some((root) => isPathContainedIn(cwdCandidate, root))
  ) {
    return cwdCandidate;
  }
  if (repoRoot) {
    const rootCandidate = path.resolve(repoRoot, rawPath);
    if (
      fs.existsSync(rootCandidate) &&
      fs.statSync(rootCandidate).isFile() &&
      isPathContainedIn(rootCandidate, repoRoot)
    ) {
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
  const scale = Math.min(width, height) / 1080;
  return isPortrait ? Math.round(56 * scale) : Math.round(46 * scale);
}

function resolveCaptionLetterSpacingEm(props: Record<string, unknown>): number {
  const raw = props.caption_letter_spacing_em;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return Number(Math.max(-0.05, Math.min(0.25, raw)).toFixed(4));
  }
  return 0.015;
}

interface ResolvedTypeScaleStep {
  sizePx: number;
  weight: number;
  lineHeight: number;
  letterSpacingEm: number;
}

function buildTypeScaleCssVars(
  props: Record<string, unknown>,
  width: number,
  height: number
): string {
  const isPortrait = height > width;
  const scaleFactor = Math.min(width, height) / 1080;
  const defaults: Record<string, ResolvedTypeScaleStep> = {
    hero: { sizePx: isPortrait ? 112 : 108, weight: 400, lineHeight: 0.98, letterSpacingEm: -0.02 },
    display: { sizePx: isPortrait ? 76 : 72, weight: 800, lineHeight: 1.04, letterSpacingEm: -0.01 },
    title: { sizePx: isPortrait ? 48 : 44, weight: 700, lineHeight: 1.12, letterSpacingEm: 0.01 },
    caption: { sizePx: isPortrait ? 56 : 46, weight: 700, lineHeight: 1.24, letterSpacingEm: 0.015 },
    telemetry: { sizePx: isPortrait ? 34 : 30, weight: 600, lineHeight: 1.22, letterSpacingEm: 0.02 },
    body: { sizePx: isPortrait ? 28 : 26, weight: 500, lineHeight: 1.32, letterSpacingEm: 0.01 },
    micro: { sizePx: isPortrait ? 22 : 20, weight: 600, lineHeight: 1.35, letterSpacingEm: 0.06 },
  };
  const rawScale =
    props.type_scale && typeof props.type_scale === "object"
      ? (props.type_scale as Record<string, unknown>)
      : {};
  const lines: string[] = [
    `--vedit-scale: ${Number(scaleFactor.toFixed(4))};`,
    `--space-1: ${Math.round(4 * scaleFactor)}px;`,
    `--space-2: ${Math.round(8 * scaleFactor)}px;`,
    `--space-3: ${Math.round(12 * scaleFactor)}px;`,
    `--space-4: ${Math.round(16 * scaleFactor)}px;`,
    `--space-6: ${Math.round(24 * scaleFactor)}px;`,
    `--space-8: ${Math.round(32 * scaleFactor)}px;`,
    `--grid-cols: ${isPortrait ? 6 : 12};`,
    `--grid-gutter: ${Math.round(16 * scaleFactor)}px;`,
    `--measure-editorial: ${isPortrait ? "84%" : "68%"};`,
  ];
  for (const [level, fallback] of Object.entries(defaults)) {
    const custom =
      rawScale[level] && typeof rawScale[level] === "object"
        ? (rawScale[level] as Record<string, unknown>)
        : null;
    const rawSize = custom
      ? isPortrait
        ? custom.size_px_9x16
        : custom.size_px_16x9
      : undefined;
    const basePx =
      typeof rawSize === "number" && Number.isFinite(rawSize) ? rawSize : fallback.sizePx;
    const scaledPx = Math.round(basePx * scaleFactor);
    const weight =
      custom && typeof custom.weight === "number" && Number.isFinite(custom.weight)
        ? Math.round(custom.weight)
        : fallback.weight;
    const lh =
      custom && typeof custom.line_height === "number" && Number.isFinite(custom.line_height)
        ? Number(custom.line_height.toFixed(3))
        : fallback.lineHeight;
    const ls =
      custom &&
      typeof custom.letter_spacing_em === "number" &&
      Number.isFinite(custom.letter_spacing_em)
        ? Number(custom.letter_spacing_em.toFixed(4))
        : fallback.letterSpacingEm;
    lines.push(`--type-${level}-size: ${scaledPx}px;`);
    lines.push(`--type-${level}-weight: ${weight};`);
    lines.push(`--type-${level}-leading: ${lh};`);
    lines.push(`--type-${level}-tracking: ${ls}em;`);
  }
  return lines.join("\n      ");
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
  // while respecting asymmetric platform UI safe margins (e.g., vertical platform right UI rail).
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
  const safe = escapeHtml(text).replace(/\r?\n/g, "<br>");
  if (typeof highlightRaw !== "string" || !highlightRaw.trim()) {
    return safe;
  }
  const needle = highlightRaw.trim();
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx === -1) {
    return safe;
  }
  const before = escapeHtml(text.slice(0, idx)).replace(/\r?\n/g, "<br>");
  const match = escapeHtml(text.slice(idx, idx + needle.length)).replace(/\r?\n/g, "<br>");
  const after = escapeHtml(text.slice(idx + needle.length)).replace(/\r?\n/g, "<br>");
  return `${before}<span class="vedit-caption-accent" style="color: ${accentColor};">${match}</span>${after}`;
}

function buildOverlayMarkup(
  ov: OverlayCompositionOp,
  innerId: string,
  extraFamilies: readonly string[]
): string {
  if (typeof ov.props.custom_html === "string" && ov.props.custom_html.trim()) {
    const font = escapeHtml(escapeCssString(resolveFontFamily(ov.props.font_family, extraFamilies)));
    return `<div id="${innerId}" class="vedit-custom-layer" style="width: 100%; height: 100%; font-family: '${font}', sans-serif;">
        ${ov.props.custom_html}
      </div>`;
  }

  const bodyFont = escapeHtml(
    escapeCssString(resolveFontFamily(ov.props.caption_font_family ?? ov.props.font_family, extraFamilies))
  );
  const displayFont = escapeHtml(
    escapeCssString(resolveFontFamily(ov.props.display_family ?? ov.props.font_family, extraFamilies))
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

interface ResolvedMotionPhysics {
  registerName: "documentary" | "wry" | "comic";
  easeName: string;
  enterScale: number;
  anticipationS: number;
  overlapStaggerS: number;
  squashSettle: boolean;
}

function resolveMotionPhysics(ov: OverlayCompositionOp, duration: number): ResolvedMotionPhysics {
  const regRaw =
    ov.motion_register ??
    (typeof ov.props.motion_register === "string" ? ov.props.motion_register : null);
  const reg: "documentary" | "wry" | "comic" =
    regRaw === "comic" || regRaw === "wry" || regRaw === "documentary"
      ? regRaw
      : "documentary";
  const easingFeel =
    typeof ov.props.easing_feel === "string" ? String(ov.props.easing_feel) : "smooth_editorial";

  let easeName =
    easingFeel === "energetic_pop"
      ? "back.out(1.4)"
      : easingFeel === "minimal_static"
        ? "none"
        : "expo.out";
  let enterScale = 0.94;
  let defaultAnticMs = 0;
  let squashSettle = false;

  if (reg === "wry") {
    easeName = easingFeel === "minimal_static" ? "none" : "power4.out";
    enterScale = 0.96;
    defaultAnticMs = 55;
  } else if (reg === "comic") {
    easeName = easingFeel === "minimal_static" ? "none" : "back.out(1.6)";
    enterScale = 0.94;
    defaultAnticMs = 75;
    squashSettle = true;
  }

  const rawAnticMs =
    typeof ov.anticipation_ms === "number" && Number.isFinite(ov.anticipation_ms)
      ? ov.anticipation_ms
      : typeof ov.props.anticipation_ms === "number" && Number.isFinite(ov.props.anticipation_ms)
        ? Number(ov.props.anticipation_ms)
        : defaultAnticMs;
  const rawStaggerMs =
    typeof ov.overlap_stagger_ms === "number" && Number.isFinite(ov.overlap_stagger_ms)
      ? ov.overlap_stagger_ms
      : typeof ov.props.overlap_stagger_ms === "number" && Number.isFinite(ov.props.overlap_stagger_ms)
        ? Number(ov.props.overlap_stagger_ms)
        : 45;

  return {
    registerName: reg,
    easeName,
    enterScale,
    anticipationS: Number(Math.min(Math.max(0, rawAnticMs) / 1000, duration * 0.18).toFixed(3)),
    overlapStaggerS: Number(Math.min(Math.max(0, rawStaggerMs) / 1000, duration * 0.12).toFixed(3)),
    squashSettle,
  };
}

function resolveCaptionTypographyOverrides(
  ov: OverlayCompositionOp,
  width: number,
  height: number,
  safeZone: SafeZoneMargins
): {
  symXPct: number;
  captionFontPx: number;
  hasBottomOverride: boolean;
  captionBottomPct: number;
} {
  const symXPct = computeSymmetricMarginPct(safeZone);
  const rawBottomPct = ov.props.caption_bottom_pct;
  const hasBottomOverride = typeof rawBottomPct === "number" && Number.isFinite(rawBottomPct);
  const scaledBottomPct =
    hasBottomOverride && rawBottomPct > 0 && rawBottomPct <= 1.0
      ? rawBottomPct * 100
      : rawBottomPct;
  const captionBottomPct = hasBottomOverride
    ? Math.max(0, Math.min(90, Number((scaledBottomPct as number).toFixed(1))))
    : computeCaptionBottomPct(safeZone, width, height);
  const rawFontPx = ov.props.caption_font_px;
  const captionFontPx =
    typeof rawFontPx === "number" && Number.isFinite(rawFontPx)
      ? Math.max(16, Math.min(160, Math.round(rawFontPx)))
      : computeProportionalCaptionFontPx(width, height);
  return { symXPct, captionFontPx, hasBottomOverride, captionBottomPct };
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
  const { symXPct, captionFontPx, hasBottomOverride, captionBottomPct } =
    resolveCaptionTypographyOverrides(ov, width, height, safeZone);
  const headlineFontPx = Math.round(48 * scaleFactor);
  const subtitleFontPx = Math.round(24 * scaleFactor);
  const badgeFontPx = Math.max(22, Math.round(22 * scaleFactor));
  const captionLetterSpacingEm = resolveCaptionLetterSpacingEm(ov.props);
  const typeScaleVarsCss = buildTypeScaleCssVars(ov.props, width, height);

  const entranceMs =
    typeof ov.props.entrance_ms === "number" && Number.isFinite(ov.props.entrance_ms)
      ? Math.max(40, Math.min(2000, Number(ov.props.entrance_ms)))
      : null;
  const { inMs: captionTransitionMs, outMs: captionFadeOutMs } = captionFadeMs(ov.props);
  const physics = resolveMotionPhysics(ov, duration);
  const easeName = physics.easeName;
  const enterDur = Number(
    (isCaption
      ? Math.min(captionTransitionMs / 1000, duration * 0.2)
      : entranceMs != null
        ? Math.min(entranceMs / 1000, duration * 0.45)
        : Math.min(0.26, duration * 0.25)
    ).toFixed(3)
  );
  const exitDur = Number(
    (isCaption ? Math.min(captionFadeOutMs / 1000, duration * 0.2) : Math.max(0.11, enterDur * 0.48)).toFixed(3)
  );
  const safeBlendMode =
    ov.blend_mode && ov.blend_mode !== "normal" && ALLOWED_BLEND_MODES.has(ov.blend_mode)
      ? ov.blend_mode
      : null;
  const blendCss = safeBlendMode ? `mix-blend-mode: ${safeBlendMode};` : "";
  const matteCss =
    ov.matte_mode === "alpha_matte"
      ? "mask-mode: alpha;"
      : ov.matte_mode === "luma_matte"
        ? "mask-mode: luminance;"
        : ov.matte_mode === "inverted_alpha"
          ? "mask-mode: alpha; mask-composite: exclude;"
          : "";
  const matteAttr =
    ov.matte_mode && ov.matte_mode !== "none"
      ? ` data-matte-mode="${escapeHtml(ov.matte_mode)}"`
      : "";
  const parentAttr = ov.parent_overlay_id
    ? ` data-parent-overlay="${escapeHtml(ov.parent_overlay_id)}"`
    : "";
  const posCss = hasCustomHtml
    ? "inset: 0;"
    : band === "lower_third" && hasBottomOverride && !ov.props.box
      ? `bottom: ${captionBottomPct}%; left: ${symXPct}%; right: ${symXPct}%; display: flex; justify-content: center; align-items: flex-end;`
      : computeBandPositionCss(band, safeZone, width, height, ov.props.box);
  const bgFill = ov.transparent ? "transparent" : "var(--vedit-ground)";
  const rootBgLayer = ov.transparent
    ? ""
    : `<div id="${sceneId}-bg" style="position: absolute; inset: 0; background: var(--vedit-ground);"></div>`;
  const customCss = typeof ov.props.custom_css === "string" ? ov.props.custom_css : "";

  const innerMarkup = buildOverlayMarkup(ov, innerId, extraFamilies);
  const anticDipScale = Number(Math.max(0.92, physics.enterScale - 0.02).toFixed(3));
  const anticPrep =
    physics.anticipationS > 0.01
      ? `tl.fromTo("#${innerId}", { opacity: 0.4, y: 18, scale: ${physics.enterScale} }, { opacity: 0.85, y: 22, scale: ${anticDipScale}, duration: ${physics.anticipationS}, ease: "power2.in" }, 0);\n    `
      : "";
  const anticOffset = physics.anticipationS > 0.01 ? physics.anticipationS : 0;
  const enterStartScale = anticOffset > 0 ? anticDipScale : physics.enterScale;
  const squashStart = anticOffset + enterDur;
  const minExitAt = isCaption
    ? enterDur
    : squashStart + (physics.squashSettle ? 0.18 : 0.05);
  const exitAt = Number(
    (isCaption
      ? Math.max(enterDur, duration - exitDur)
      : Math.min(duration, Math.max(minExitAt, duration - exitDur))
    ).toFixed(3)
  );
  const squashTweens = physics.squashSettle
    ? `tl.to("#${innerId}", { scaleX: 1.03, scaleY: 0.97, duration: 0.06, ease: "power1.out" }, ${squashStart.toFixed(3)});\n    tl.to("#${innerId}", { scaleX: 1.0, scaleY: 1.0, duration: 0.12, ease: "power2.out" }, ${(squashStart + 0.06).toFixed(3)});\n    `
    : "";
  const overlapChildren =
    physics.overlapStaggerS > 0.005
      ? `var kids = document.querySelectorAll("#${innerId} .vedit-badge, #${innerId} .vedit-headline, #${innerId} .vedit-subtitle");
    if (kids.length > 1) {
      tl.fromTo(kids, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: ${Math.max(0.12, enterDur * 0.8).toFixed(3)}, stagger: ${physics.overlapStaggerS}, ease: "${easeName}" }, ${(anticOffset + 0.02).toFixed(3)});
    }\n    `
      : "";
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
    ${anticPrep}tl.fromTo(
      "#${innerId}",
      { opacity: ${anticOffset > 0 ? 0.85 : 0}, y: ${anticOffset > 0 ? 22 : 12}, scale: ${enterStartScale} },
      { opacity: 1, y: 0, scale: 1, duration: ${enterDur}, ease: "${easeName}"${anticOffset > 0 ? ", immediateRender: false" : ""} },
      ${anticOffset}
    );
    ${overlapChildren}${squashTweens}tl.to("#${innerId}", { opacity: 0, y: -8, duration: ${exitDur}, ease: "power3.in" }, ${exitAt});
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
      ${typeScaleVarsCss}
      font-variant-numeric: tabular-nums;
      font-kerning: normal;
      ${blendCss}
      ${matteCss}
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
      text-wrap: balance;
      font-size: ${captionFontPx}px;
      font-weight: 700;
      line-height: 1.24;
      letter-spacing: ${captionLetterSpacingEm}em;
      font-kerning: normal;
      text-shadow: var(--vedit-text-glow);
    }
    .vedit-caption-pill {
      background: ${bgRgba};
      color: var(--vedit-ink);
      border-radius: 6px;
      padding: 8px 20px;
      max-width: 100%;
      text-align: center;
      text-wrap: balance;
      font-size: ${captionFontPx}px;
      font-weight: 700;
      line-height: 1.24;
      letter-spacing: ${captionLetterSpacingEm}em;
      font-kerning: normal;
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
      gap: ${Math.round(8 * scaleFactor)}px;
      text-shadow: var(--vedit-text-glow);
    }
    .vedit-badge {
      color: var(--vedit-accent);
      font-size: ${badgeFontPx}px;
      font-weight: 700;
      line-height: 1.3;
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
      line-height: 1.32;
      letter-spacing: 0.01em;
      opacity: 0.9;
    }
    ${customCss}
  </style>
  <div id="root" data-composition-id="${sceneId}" data-width="${width}" data-height="${height}"${motionBlurAttr}${matteAttr}${parentAttr}>
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
  extraFamilies: readonly string[],
  variableTypes: Record<string, string> = {},
  variableEnums: Record<string, readonly string[]> = {}
): string {
  const isPortrait = height > width;
  const scaleFactor = Math.min(width, height) / 1080;
  const duration = Number(ov.timeline_duration_s.toFixed(3));
  const fg = resolveCssHex(ov.props.fg_color, "#F8FAFC");
  const bg = resolveCssHex(ov.props.bg_color, "#0F172A");
  const accent = resolveCssHex(ov.props.accent_color, "#38BDF8");
  const bodyFont = escapeCssString(
    resolveFontFamily(ov.props.font_family ?? ov.props.caption_font_family, extraFamilies)
  );
  const captionFont = escapeCssString(
    resolveFontFamily(ov.props.caption_font_family ?? ov.props.font_family, extraFamilies)
  );
  const captionLetterSpacingEm = resolveCaptionLetterSpacingEm(ov.props);
  const baseRemPx =
    typeof ov.props.base_rem_px === "number" && Number.isFinite(ov.props.base_rem_px)
      ? Math.max(8, Math.min(32, ov.props.base_rem_px))
      : 16;
  const displayFont = escapeCssString(
    resolveFontFamily(ov.props.display_family ?? ov.props.font_family, extraFamilies)
  );
  const titleFont = escapeCssString(
    resolveFontFamily(
      ov.props.title_family ?? ov.props.display_family ?? ov.props.font_family,
      extraFamilies
    )
  );
  const serifFont = escapeCssString(
    resolveFontFamily(ov.props.serif_family ?? "Lora", extraFamilies)
  );
  const monoFont = escapeCssString(
    resolveFontFamily(ov.props.mono_family ?? "IBM Plex Mono", extraFamilies)
  );
  const captionFade = captionFadeMs(ov.props);
  const captionTransitionS = Number(Math.min(captionFade.inMs / 1000, duration * 0.2).toFixed(3));
  const captionFadeOutS = Number(Math.min(captionFade.outMs / 1000, duration * 0.2).toFixed(3));
  const entranceMs =
    typeof ov.props.entrance_ms === "number" && Number.isFinite(ov.props.entrance_ms)
      ? Math.max(40, Math.min(2000, Number(ov.props.entrance_ms)))
      : 260;
  const enterS = Number(Math.min(entranceMs / 1000, duration * 0.45).toFixed(3));
  const exitS = Number(Math.min(Math.max(0.12, enterS * 0.48), duration * 0.25).toFixed(3));
  const exitAtS = Number(Math.max(0.05, duration - exitS).toFixed(3));
  const captionExitAtS = Number(Math.max(captionTransitionS, duration - captionFadeOutS).toFixed(3));

  const { symXPct, captionFontPx, hasBottomOverride, captionBottomPct } =
    resolveCaptionTypographyOverrides(ov, width, height, safeZone);
  const safeBand: SafeBand = ov.safe_band ?? "lower_third";
  const bandPositionCss =
    safeBand === "lower_third" && hasBottomOverride && !ov.props.box
      ? `bottom: ${captionBottomPct}%; left: ${symXPct}%; right: ${symXPct}%; display: flex; justify-content: center; align-items: flex-end;`
      : computeBandPositionCss(safeBand, safeZone, width, height, ov.props.box);
  const watermarkFontPx = Math.max(22, Math.round(24 * scaleFactor));
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

  const physics = resolveMotionPhysics(ov, duration);
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
    CAPTION_LETTER_SPACING_EM: String(captionLetterSpacingEm),
    BASE_REM_PX: String(Number((baseRemPx * scaleFactor).toFixed(2))),
    GRID_COLS: isPortrait ? "6" : "12",
    BAND_POSITION_CSS: bandPositionCss,
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
    CAPTION_FONT: captionFont,
    DISPLAY_FONT: displayFont,
    TITLE_FONT: titleFont,
    SERIF_FONT: serifFont,
    MONO_FONT: monoFont,
    EASE_NAME: physics.easeName,
    MOTION_REGISTER: physics.registerName,
    ANTICIPATION_S: String(physics.anticipationS),
    OVERLAP_STAGGER_S: String(physics.overlapStaggerS),
    BLEND_MODE:
      ov.blend_mode && ALLOWED_BLEND_MODES.has(ov.blend_mode) ? ov.blend_mode : "normal",
    MATTE_MODE: ov.matte_mode ?? "none",
    PARENT_OVERLAY_ID: ov.parent_overlay_id ?? "",
    ENTRANCE_S: String(enterS),
    EXIT_S: String(exitS),
    EXIT_AT_S: String(exitAtS),
    CAPTION_TRANSITION_S: String(captionTransitionS),
    CAPTION_FADE_OUT_S: String(captionFadeOutS),
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
    const expectedType = variableTypes[key];
    const upper = key.toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    if (expectedType === "number") {
      const n = typeof val === "number" ? val : Number(String(val).trim());
      if (typeof val === "boolean" || String(val).trim() === "" || !Number.isFinite(n)) {
        throw new Error(`Overlay ${ov.overlay_id} variable '${key}' expects a finite number, got ${JSON.stringify(val)}`);
      }
      tokens[`VAR_${upper}`] = String(n);
      continue;
    }
    if (expectedType === "color") {
      const rawColor = typeof val === "string" ? val.trim() : "";
      if (!/^#[0-9A-Fa-f]{6}$/.test(rawColor)) {
        throw new Error(`Overlay ${ov.overlay_id} variable '${key}' expects a hex color (#RRGGBB), got ${JSON.stringify(val)}`);
      }
      tokens[`VAR_${upper}`] = rawColor.toUpperCase();
      continue;
    }
    if (expectedType === "enum") {
      const allowed = variableEnums[key];
      const rawEnum = typeof val === "string" ? val.trim() : "";
      if (allowed && allowed.length > 0 && !allowed.includes(rawEnum)) {
        throw new Error(
          `Overlay ${ov.overlay_id} variable '${key}' must be one of [${allowed.join(", ")}], got ${JSON.stringify(val)}`
        );
      }
      tokens[`VAR_${upper}`] = escapeHtml(rawEnum);
      continue;
    }
    if (typeof val === "string") {
      tokens[`VAR_${upper}`] = /^#[0-9A-Fa-f]{6}$/.test(val.trim())
        ? val.trim().toUpperCase()
        : escapeHtml(val).replace(/\\/g, "\\\\").replace(/\r?\n/g, " ");
    } else if (typeof val === "number") {
      if (Number.isFinite(val)) {
        tokens[`VAR_${upper}`] = String(val);
      }
    } else if (typeof val === "boolean") {
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

  const usedAssetIds = new Set<string>();
  for (const asset of plan.assets) {
    if (plan.render_strategy === "hybrid" && asset.kind !== "font" && asset.kind !== "image") {
      continue;
    }
    const cleanId = allocateUniqueId(asset.asset_id, usedAssetIds);
    const fallbackExt =
      asset.kind === "font"
        ? ".ttf"
        : asset.kind === "image"
          ? ".png"
          : asset.kind.startsWith("audio")
            ? ".mp3"
            : ".mp4";
    const rawExt = path.extname(asset.path).replace(/[^a-zA-Z0-9.]/g, "");
    const ext = rawExt && rawExt.startsWith(".") ? rawExt : fallbackExt;
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
        isVariable: desc.isVariable,
      });
    }
  }
  const hasVarByKey = new Set<string>();
  for (const f of stagedFonts) {
    if (f.isVariable) {
      hasVarByKey.add(`${f.family.toLowerCase()}::${f.style}`);
    }
  }
  const dedupedFonts = stagedFonts.filter(
    (f) => f.isVariable || !hasVarByKey.has(`${f.family.toLowerCase()}::${f.style}`)
  );
  return { assetPathsById, copiedAssets, stagedFonts: dedupedFonts };
}

function extractReferencedFontFamilies(html: string): string[] {
  const found = new Set<string>();
  const re = /font-family\s*:\s*([^;\n}]+)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const raw = m[1] ?? "";
    for (const part of raw.split(",")) {
      const cleaned = part.trim().replace(/^['"]|['"]$/g, "").trim();
      if (!cleaned) continue;
      if (/^(?:sans-serif|serif|monospace|cursive|fantasy|system-ui|ui-sans-serif|ui-serif|ui-monospace|inherit|initial|unset|georgia|arial|helvetica)$/i.test(cleaned)) {
        continue;
      }
      found.add(cleaned);
    }
  }
  return [...found];
}

function autoStageBundledFonts(
  referencedFamilies: readonly string[],
  existingFonts: readonly StagedFontFace[],
  outDir: string,
  copyAssets: boolean
): { addedFonts: StagedFontFace[]; addedFiles: string[] } {
  const repoRoot = findRepoRootForTemplates();
  if (!repoRoot) return { addedFonts: [], addedFiles: [] };
  const fontsDir = path.join(repoRoot, "assets", "geo", "fonts");
  if (!fs.existsSync(fontsDir) || !fs.statSync(fontsDir).isDirectory()) {
    return { addedFonts: [], addedFiles: [] };
  }

  const existingNormalFamilies = new Set(
    existingFonts.filter((f) => f.style === "normal").map((f) => f.family.toLowerCase())
  );
  const existingKeys = new Set(existingFonts.map((f) => `${f.family.toLowerCase()}::${f.style}`));
  const needed = new Set<string>();
  for (const fam of referencedFamilies) {
    const lc = fam.toLowerCase();
    if (!existingNormalFamilies.has(lc) && BUNDLED_FAMILIES.some((b) => b.toLowerCase() === lc)) {
      needed.add(lc);
    }
  }
  if (needed.size === 0) return { addedFonts: [], addedFiles: [] };

  const candidates: Array<{ srcPath: string; fileName: string; desc: ReturnType<typeof inferFontDescriptor> }> = [];
  for (const fn of fs.readdirSync(fontsDir).sort()) {
    if (!/\.(?:ttf|otf|woff2?)$/i.test(fn)) continue;
    const hint = inferKnownFontFamilyHint(fn);
    if (hint && !needed.has(hint.toLowerCase())) continue;
    const srcPath = path.join(fontsDir, fn);
    const desc = inferFontDescriptor(srcPath, fn);
    const key = `${desc.family.toLowerCase()}::${desc.style}`;
    if (needed.has(desc.family.toLowerCase()) && !existingKeys.has(key)) {
      candidates.push({ srcPath, fileName: fn, desc });
    }
  }

  const hasVarByKey = new Set<string>();
  for (const c of candidates) {
    if (c.desc.isVariable) {
      hasVarByKey.add(`${c.desc.family.toLowerCase()}::${c.desc.style}`);
    }
  }
  const selected = candidates.filter(
    (c) => c.desc.isVariable || !hasVarByKey.has(`${c.desc.family.toLowerCase()}::${c.desc.style}`)
  );

  const addedFonts: StagedFontFace[] = [];
  const addedFiles: string[] = [];
  const destFontsDir = path.join(outDir, "assets", "fonts");
  for (const item of selected) {
    const relPath = `assets/fonts/${item.fileName}`;
    if (copyAssets) {
      fs.mkdirSync(destFontsDir, { recursive: true });
      const destPath = path.join(destFontsDir, item.fileName);
      if (!fs.existsSync(destPath)) {
        fs.copyFileSync(item.srcPath, destPath);
      }
      addedFiles.push(destPath);
    }
    addedFonts.push({
      family: item.desc.family,
      relPath,
      format: resolveFontFormat(relPath),
      weight: item.desc.weight,
      style: item.desc.style,
      isVariable: item.desc.isVariable,
    });
  }
  return { addedFonts, addedFiles };
}

function buildLocalFontFaceCss(fonts: readonly StagedFontFace[]): string {
  if (fonts.length === 0) {
    return "";
  }
  const faces = fonts
    .map(
      (f) => `    @font-face {
      font-family: '${escapeCssString(f.family)}';
      src: url('${escapeCssString(f.relPath)}') format('${f.format}');
      font-weight: ${f.weight};
      font-style: ${f.style};
      font-display: block;
    }`
    )
    .join("\n");
  return `${faces}\n    :root { font-synthesis: none; font-optical-sizing: auto; font-kerning: normal; }`;
}

function injectOverlayTrackKeyframes(
  html: string,
  ov: OverlayCompositionOp,
  width: number,
  height: number,
  sceneId: string
): string {
  const kfs = ov.track_keyframes;
  if (!kfs || kfs.length === 0) {
    return html;
  }
  const sorted = [...kfs].sort((a, b) => a.t_s - b.t_s);
  const first = sorted[0]!;
  const baseX = first.x_pct;
  const baseY = first.y_pct;
  let activePerspective = first.perspective_px ?? 1600;
  const payload = sorted.map((kf) => {
    if (kf.perspective_px && kf.perspective_px > 0) {
      activePerspective = kf.perspective_px;
    }
    return {
      t: Number(kf.t_s.toFixed(4)),
      dx: Number((((kf.x_pct - baseX) / 100) * width).toFixed(2)),
      dy: Number((((kf.y_pct - baseY) / 100) * height).toFixed(2)),
      scale: kf.scale ?? 1,
      rotation: kf.rotation_deg ?? 0,
      rotationX: kf.rotateX_deg ?? 0,
      perspective: kf.perspective_px ?? activePerspective,
      opacity: kf.opacity ?? 1,
      curve: kf.curve ?? "linear",
      arcHeightPx:
        typeof kf.arc_height_px === "number" && Number.isFinite(kf.arc_height_px)
          ? kf.arc_height_px
          : kf.curve === "arc_up"
            ? -48
            : kf.curve === "arc_down"
              ? 48
              : 0,
    };
  });
  const originX = Number(((baseX / 100) * width).toFixed(1));
  const originY = Number(((baseY / 100) * height).toFixed(1));
  const has3d = sorted.some(
    (k) => Math.abs(k.rotateX_deg ?? 0) > 0.01 || (k.perspective_px ?? 0) > 0
  );
  const trackScript = `
  <script data-vedit-object-track="true">
    (function() {
      var target = document.getElementById("root");
      if (!target || typeof gsap === "undefined") return;
      var kfs = ${JSON.stringify(payload).replace(/</g, "\\u003c")};
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
        if (curr.curve === "arc_up" || curr.curve === "arc_down") {
          var steps = 24;
          var ctrlX = (prev.dx + curr.dx) * 0.5;
          var ctrlY = (prev.dy + curr.dy) * 0.5 + curr.arcHeightPx;
          for (var s = 1; s <= steps; s++) {
            var u = s / steps;
            var eu = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
            var inv = 1 - eu;
            var bx = inv * inv * prev.dx + 2 * inv * eu * ctrlX + eu * eu * curr.dx;
            var by = inv * inv * prev.dy + 2 * inv * eu * ctrlY + eu * eu * curr.dy;
            var subDur = segDur / steps;
            trackTl.to(target, {
              x: Number(bx.toFixed(2)),
              y: Number(by.toFixed(2)),
              scale: prev.scale + (curr.scale - prev.scale) * eu,
              rotation: prev.rotation + (curr.rotation - prev.rotation) * eu,${
                has3d
                  ? `
              rotationX: prev.rotationX + (curr.rotationX - prev.rotationX) * eu,
              transformPerspective: curr.perspective || 1600,`
                  : ""
              }
              opacity: prev.opacity + (curr.opacity - prev.opacity) * eu,
              duration: subDur,
              ease: "none"
            }, prev.t + (s - 1) * subDur);
          }
        } else {
          var segEase = curr.curve === "ease_out" ? "power3.out" : curr.curve === "ease_in_out" ? "power2.inOut" : "none";
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
            ease: segEase
          }, prev.t);
        }
      }
      window.__timelines = window.__timelines || {};
      var parentTl = window.__timelines[${JSON.stringify(sceneId).replace(/</g, "\\u003c")}];
      if (parentTl && typeof parentTl.add === "function") {
        trackTl.paused(false);
        parentTl.add(trackTl, 0);
      } else {
        window.__timelines[${JSON.stringify(sceneId).replace(/</g, "\\u003c")}] = trackTl;
      }
    })();
  </script>`;
  if (html.includes("</template>")) {
    return html.replace("</template>", `${trackScript}\n</template>`);
  }
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
  const perfViolations = lintPlanPerformance(plan).filter(
    (v) => !NON_FATAL_WARNING_CODES.has(v.code)
  );
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
  const usedSceneIds = new Set<string>();

  if (plan.render_strategy === "full_hf") {
    for (const clip of plan.video_tracks) {
      const relSrc = assetPathsById.get(clip.asset_id) ?? "assets/missing.mp4";
      const cid = allocateUniqueId(clip.clip_id, usedSceneIds);
      const start = Number(clip.timeline_start_s.toFixed(3));
      const dur = Number(clip.timeline_duration_s.toFixed(3));
      const mediaStart = Number(clip.source_start_s.toFixed(3));
      const videoLane = assignTrackLane(lanes, start, dur);
      hostTags.push(
        `      <video id="${cid}" class="clip" src="${escapeHtml(relSrc)}" ` +
          `data-start="${start}" data-duration="${dur}" data-media-start="${mediaStart}" ` +
          `data-track-index="${videoLane}" muted playsinline ` +
          `style="position: absolute; left: 0; top: 0; width: ${plan.width}px; height: ${plan.height}px; object-fit: cover;"></video>`
      );
    }
    for (const track of plan.audio_tracks) {
      const relSrc = assetPathsById.get(track.asset_id) ?? "assets/missing.mp3";
      const tid = allocateUniqueId(track.track_id, usedSceneIds);
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

  const referencedFamilies = new Set<string>();
  const captionHostPending: Array<{
    sceneId: string;
    start: number;
    dur: number;
    extraAttrs: string;
    hostStyleAttr: string;
  }> = [];
  for (const ov of plan.overlay_compositions) {
    const sceneId = allocateUniqueId(ov.overlay_id, usedSceneIds);
    const scenePath = path.join(compDir, `${sceneId}.html`);
    const catalogMatch = ov.template_id
      ? resolveBrandTemplateEntry(plan.brand_id, ov.template_id)
      : null;
    const mergedProps: Record<string, unknown> = {
      ...(catalogMatch?.defaults ?? {}),
      ...ov.props,
      ...(ov.variables ?? {}),
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
    let finalSceneHtml: string;
    if (resolvedTemplatePath) {
      const rawTemplate = fs.readFileSync(resolvedTemplatePath, "utf8");
      const rendered = renderParameterizedTemplate(
        rawTemplate,
        effectiveOv,
        sceneId,
        plan.width,
        plan.height,
        safeZone,
        extraFontFamilies,
        catalogMatch?.variableTypes ?? {},
        catalogMatch?.variableEnums ?? {}
      );
      finalSceneHtml = injectOverlayTrackKeyframes(rendered, effectiveOv, plan.width, plan.height, sceneId);
    } else {
      const sceneHtml = buildOverlayCompositionHtml(
        effectiveOv,
        sceneId,
        plan.width,
        plan.height,
        safeZone,
        extraFontFamilies
      );
      finalSceneHtml = injectOverlayTrackKeyframes(sceneHtml, effectiveOv, plan.width, plan.height, sceneId);
    }
    for (const fam of extractReferencedFontFamilies(finalSceneHtml)) {
      referencedFamilies.add(fam);
    }
    fs.writeFileSync(scenePath, finalSceneHtml, "utf8");
    compositionFiles.push(scenePath);

    const start = Number(ov.timeline_start_s.toFixed(3));
    const dur = Number(ov.timeline_duration_s.toFixed(3));
    const templateAttr = ov.template_id
      ? ` data-template-id="${escapeHtml(ov.template_id)}"`
      : "";
    const hostParentAttr = ov.parent_overlay_id
      ? ` data-parent-overlay="${escapeHtml(ov.parent_overlay_id)}"`
      : "";
    const hostMatteAttr =
      ov.matte_mode && ov.matte_mode !== "none"
        ? ` data-matte-mode="${escapeHtml(ov.matte_mode)}"`
        : "";
    const hostStyleParts: string[] = [];
    if (ov.blend_mode && ov.blend_mode !== "normal" && ALLOWED_BLEND_MODES.has(ov.blend_mode)) {
      hostStyleParts.push(`mix-blend-mode: ${ov.blend_mode};`);
    }
    if (ov.matte_mode === "alpha_matte") {
      hostStyleParts.push("mask-mode: alpha;");
    } else if (ov.matte_mode === "luma_matte") {
      hostStyleParts.push("mask-mode: luminance;");
    } else if (ov.matte_mode === "inverted_alpha") {
      hostStyleParts.push("mask-mode: alpha; mask-composite: exclude;");
    }
    const hostStyleAttr =
      hostStyleParts.length > 0 ? ` style="${hostStyleParts.join(" ")}"` : "";
    const extraAttrs = `${templateAttr}${hostParentAttr}${hostMatteAttr}`;

    if (ov.kind === "caption_rail") {
      captionHostPending.push({ sceneId, start, dur, extraAttrs, hostStyleAttr });
    } else {
      const lane = assignTrackLane(lanes, start, dur);
      hostTags.push(
        `      <div id="${sceneId}" data-composition-id="${sceneId}" ` +
          `data-composition-src="compositions/${sceneId}.html" ` +
          `data-start="${start}" data-duration="${dur}" ` +
          `data-track-index="${lane}" data-track-kind="graphics"` +
          `${extraAttrs}${hostStyleAttr} ` +
          `data-width="${plan.width}" data-height="${plan.height}"></div>`
      );
    }
  }

  if (captionHostPending.length > 0) {
    const captionLane = assignTrackLane(lanes, 0, plan.duration_s);
    for (const cap of captionHostPending) {
      hostTags.push(
        `      <div id="${cap.sceneId}" data-composition-id="${cap.sceneId}" ` +
          `data-composition-src="compositions/${cap.sceneId}.html" ` +
          `data-start="${cap.start}" data-duration="${cap.dur}" ` +
          `data-track-index="${captionLane}" data-track-kind="captions"` +
          `${cap.extraAttrs}${cap.hostStyleAttr} ` +
          `data-width="${plan.width}" data-height="${plan.height}"></div>`
      );
    }
  }

  const { addedFonts, addedFiles } = autoStageBundledFonts(
    [...referencedFamilies],
    stagedFonts,
    outDir,
    options.copyAssets ?? true
  );
  const allStagedFonts = [...stagedFonts, ...addedFonts];
  const allCopiedAssets = [...copiedAssets, ...addedFiles];

  const rootBg = plan.render_strategy === "hybrid" ? "transparent" : "#000000";
  const totalDur = Number(plan.duration_s.toFixed(3));
  const localFontCss = buildLocalFontFaceCss(allStagedFonts);
  const firstTypoProps =
    plan.overlay_compositions.find(
      (o) => o.props && (o.props.type_scale || o.props.base_rem_px)
    )?.props ?? {};
  const rootScaleFactor = Math.min(plan.width, plan.height) / 1080;
  const rootBaseRemPx =
    typeof firstTypoProps.base_rem_px === "number" && Number.isFinite(firstTypoProps.base_rem_px)
      ? Math.max(8, Math.min(32, firstTypoProps.base_rem_px))
      : 16;
  const rootRemPx = Number((rootBaseRemPx * rootScaleFactor).toFixed(2));
  const rootTypeScaleCss = buildTypeScaleCssVars(firstTypoProps, plan.width, plan.height);
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
    :root {
      font-size: ${rootRemPx}px;
      font-kerning: normal;
      font-optical-sizing: auto;
      ${rootTypeScaleCss}
    }
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
    copiedAssets: allCopiedAssets,
    recommendedFormat: plan.render_strategy === "hybrid" ? "mov" : "mp4",
  };
}

/**
 * Caption fade-in and fade-out in ms (each 0-200). `caption_fade_in_ms` and
 * `caption_fade_out_ms` override the symmetric `caption_transition_ms` (default 33).
 */
export function captionFadeMs(props: Record<string, unknown>): { inMs: number; outMs: number } {
  const ms = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? Math.max(0, Math.min(200, v)) : null;
  const symmetric = ms(props.caption_transition_ms) ?? 33;
  return {
    inMs: ms(props.caption_fade_in_ms) ?? symmetric,
    outMs: ms(props.caption_fade_out_ms) ?? symmetric,
  };
}
