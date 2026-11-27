import fs from "node:fs";
import path from "node:path";
import { lintProject, type HyperframeLintFinding } from "@hyperframes/lint";
import type { EditPlan } from "./contracts.js";

export interface PerformanceFinding {
  code: string;
  message: string;
  location: string;
}

export interface ProjectValidationSummary {
  ok: boolean;
  totalErrors: number;
  totalWarnings: number;
  performanceViolations: PerformanceFinding[];
  hyperframesFindings: Array<HyperframeLintFinding & { file: string }>;
}

const CSS_BLUR_RE = /(backdrop-filter\s*:|filter\s*:[^;"'}]*blur\s*\(|blur\s*\()/i;
const MICRO_FONT_RE = /font-size\s*:\s*(?:calc\(\s*)?(\d+(?:\.\d+)?)px/gi;
const NON_FATAL_WARNING_CODES = new Set([
  "KINETIC_LEGIBILITY_DURATION",
  "CAPTION_CPS_TOO_FAST",
  "CAPTION_DURATION_SHORT",
  "MICRO_TEXT_DETECTED",
  "TYPO_UNAVAILABLE_WEIGHT",
  "TYPO_MISSING_DISPLAY_WEIGHT",
  "TYPO_INVERSE_TRACKING",
  "TYPO_INVERSE_LEADING",
]);

interface FontWeightBounds {
  min: number;
  max: number;
  staticWeights?: readonly number[] | undefined;
  multiWeight: boolean;
}

const KNOWN_FONT_WEIGHT_BOUNDS: Readonly<Record<string, FontWeightBounds>> = {
  "barlow condensed": { min: 400, max: 800, staticWeights: [400, 600, 700, 800], multiWeight: true },
  "archivo black": { min: 400, max: 400, staticWeights: [400], multiWeight: false },
  "ibm plex mono": { min: 400, max: 700, staticWeights: [400, 500, 600, 700], multiWeight: true },
  inter: { min: 100, max: 900, multiWeight: true },
  rubik: { min: 300, max: 900, multiWeight: true },
  lora: { min: 400, max: 700, multiWeight: true },
  "space grotesk": { min: 300, max: 700, multiWeight: true },
  "playfair display": { min: 400, max: 900, multiWeight: true },
  "eb garamond": { min: 400, max: 800, multiWeight: true },
  unbounded: { min: 200, max: 900, multiWeight: true },
  "jetbrains mono": { min: 100, max: 800, multiWeight: true },
};

function parseStagedFontWeightMap(indexHtml: string): Map<string, FontWeightBounds> {
  const map = new Map<string, FontWeightBounds>();
  for (const [k, v] of Object.entries(KNOWN_FONT_WEIGHT_BOUNDS)) {
    map.set(k, v);
  }
  const ffRe = /@font-face\s*\{([^}]*)\}/gi;
  const collected = new Map<string, { min: number; max: number; weights: Set<number>; isRange: boolean }>();
  let match: RegExpExecArray | null;
  while ((match = ffRe.exec(indexHtml)) !== null) {
    const body = match[1] ?? "";
    const famM = body.match(/font-family\s*:\s*['"]?([^'";,}]+)['"]?/i);
    const wtM = body.match(/font-weight\s*:\s*(\d{3})(?:\s+(\d{3}))?/i);
    if (!famM || !wtM) continue;
    const fam = famM[1]!.trim().toLowerCase();
    const w1 = Number(wtM[1]);
    const w2 = wtM[2] ? Number(wtM[2]) : w1;
    const cur = collected.get(fam) ?? { min: 999, max: 0, weights: new Set<number>(), isRange: false };
    cur.min = Math.min(cur.min, w1, w2);
    cur.max = Math.max(cur.max, w1, w2);
    if (w2 > w1) {
      cur.isRange = true;
    } else {
      cur.weights.add(w1);
    }
    collected.set(fam, cur);
  }
  for (const [fam, info] of collected.entries()) {
    map.set(fam, {
      min: info.min,
      max: info.max,
      staticWeights: info.isRange ? undefined : [...info.weights].sort((a, b) => a - b),
      multiWeight: info.isRange || info.weights.size > 1,
    });
  }
  return map;
}

function scanCssTypographyRules(
  html: string,
  relPath: string,
  fontBounds: ReadonlyMap<string, FontWeightBounds>,
  findings: PerformanceFinding[]
): void {
  const styleRe = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  const seenCodes = new Set<string>();
  let styleMatch: RegExpExecArray | null;
  while ((styleMatch = styleRe.exec(html)) !== null) {
    const cssText = (styleMatch[1] ?? "")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/@(?:font-face|keyframes|media)[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/gi, "");
    const ruleRe = /([^{}@]+)\{([^{}]+)\}/g;
    let ruleMatch: RegExpExecArray | null;
    while ((ruleMatch = ruleRe.exec(cssText)) !== null) {
      const selector = ruleMatch[1]!.trim();
      const body = ruleMatch[2]!;
      if (!selector || selector.startsWith("@")) continue;

      const famM = body.match(/font-family\s*:\s*([^;]+)/i);
      const primaryFam = famM
        ? famM[1]!.split(",")[0]!.trim().replace(/^['"]|['"]$/g, "").toLowerCase()
        : null;
      const sizeM = body.match(/font-size\s*:\s*(?:calc\(\s*)?(\d+(?:\.\d+)?)px/i);
      const sizePx = sizeM ? Number(sizeM[1]) : null;
      const wtM = body.match(/font-weight\s*:\s*(\d{3})\b/i);
      const weight = wtM ? Number(wtM[1]) : null;
      const lhM = body.match(/line-height\s*:\s*(\d+(?:\.\d+)?)\s*(?:;|$)/im);
      const lineHeight = lhM ? Number(lhM[1]) : null;
      const lsM = body.match(/letter-spacing\s*:\s*(-?\d+(?:\.\d+)?)(em|px)/i);
      const letterSpacingVal = lsM ? Number(lsM[1]) : null;

      if (primaryFam) {
        const bounds = fontBounds.get(primaryFam);
        if (bounds) {
          if (weight !== null) {
            const validWeight = bounds.staticWeights
              ? bounds.staticWeights.includes(weight)
              : weight >= bounds.min && weight <= bounds.max;
            if (!validWeight && !seenCodes.has(`UNAVAIL:${selector}`)) {
              seenCodes.add(`UNAVAIL:${selector}`);
              findings.push({
                code: "TYPO_UNAVAILABLE_WEIGHT",
                message: `Selector '${selector}' requests font-weight ${weight} on '${primaryFam}', outside supported range (${bounds.min}-${bounds.max}).`,
                location: relPath,
              });
            }
          } else if (
            bounds.multiWeight &&
            sizePx !== null &&
            sizePx >= 36 &&
            !selector.startsWith("#root") &&
            !seenCodes.has(`MISSWT:${selector}`)
          ) {
            seenCodes.add(`MISSWT:${selector}`);
            findings.push({
              code: "TYPO_MISSING_DISPLAY_WEIGHT",
              message: `Display selector '${selector}' (${sizePx}px, '${primaryFam}') omits explicit font-weight and collapses to Regular 400 under font-synthesis: none.`,
              location: relPath,
            });
          }
        }
      }

      if (
        sizePx !== null &&
        sizePx <= 34 &&
        letterSpacingVal !== null &&
        letterSpacingVal < 0 &&
        !seenCodes.has(`TRACK:${selector}`)
      ) {
        seenCodes.add(`TRACK:${selector}`);
        findings.push({
          code: "TYPO_INVERSE_TRACKING",
          message: `Small text selector '${selector}' (${sizePx}px) uses negative letter-spacing (${lsM?.[1]}${lsM?.[2]}); use positive tracking for legibility.`,
          location: relPath,
        });
      }

      if (sizePx !== null && lineHeight !== null && !seenCodes.has(`LEAD:${selector}`)) {
        if (sizePx <= 34 && lineHeight < 1.18) {
          seenCodes.add(`LEAD:${selector}`);
          findings.push({
            code: "TYPO_INVERSE_LEADING",
            message: `Small text selector '${selector}' (${sizePx}px) uses tight line-height ${lineHeight} (< 1.18).`,
            location: relPath,
          });
        } else if (sizePx >= 72 && lineHeight > 1.25) {
          seenCodes.add(`LEAD:${selector}`);
          findings.push({
            code: "TYPO_INVERSE_LEADING",
            message: `Large display selector '${selector}' (${sizePx}px) uses loose line-height ${lineHeight} (> 1.25).`,
            location: relPath,
          });
        }
      }
    }
  }
}

export function scanValueForCssBlur(
  value: unknown,
  location: string,
  out: PerformanceFinding[]
): void {
  if (value === null || value === undefined) {
    return;
  }
  if (typeof value === "string") {
    if (CSS_BLUR_RE.test(value)) {
      out.push({
        code: "FORBIDDEN_CSS_BLUR",
        message: "Animated/runtime CSS blur or backdrop-filter is prohibited in HyperFrames.",
        location,
      });
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, idx) => scanValueForCssBlur(item, `${location}[${idx}]`, out));
    return;
  }
  if (typeof value === "object") {
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      const lower = key.toLowerCase();
      if (lower === "caption_shadow_blur_px" || lower === "caption_glow_px") {
        continue;
      }
      if ((lower === "backdropfilter" || lower === "backdrop_filter") && Boolean(nested)) {
        out.push({
          code: "FORBIDDEN_CSS_BLUR",
          message: `Forbidden property '${key}' detected; pre-render static blurred assets instead.`,
          location: `${location}.${key}`,
        });
        continue;
      }
      if ((lower === "blur_px" || lower === "css_blur_px") && typeof nested === "number" && nested > 0) {
        out.push({
          code: "FORBIDDEN_CSS_BLUR",
          message: `Forbidden numeric blur '${key}=${nested}'; pre-render blurred assets instead.`,
          location: `${location}.${key}`,
        });
        continue;
      }
      scanValueForCssBlur(nested, `${location}.${key}`, out);
    }
  }
}

export function lintPlanPerformance(plan: EditPlan): PerformanceFinding[] {
  const findings: PerformanceFinding[] = [];
  for (const ov of plan.overlay_compositions) {
    scanValueForCssBlur(ov.props, `overlay[${ov.overlay_id}].props`, findings);
    if (ov.variables) {
      scanValueForCssBlur(ov.variables, `overlay[${ov.overlay_id}].variables`, findings);
    }
    const txtRaw = String(
      ov.props.text ?? ov.props.headline ?? (ov.variables?.text ?? ov.variables?.headline ?? "")
    ).trim();
    const words = txtRaw ? txtRaw.split(/\s+/).length : 0;
    if (
      ov.timeline_duration_s < 0.45 &&
      (ov.kind === "caption_rail" || ov.kind === "kinetic_callout" || ov.kind === "data_card") &&
      words > 3
    ) {
      findings.push({
        code: "KINETIC_LEGIBILITY_DURATION",
        message: `Text overlay displays ${words} words for ${ov.timeline_duration_s.toFixed(2)}s (< 0.45s); may be unreadable in motion.`,
        location: `overlay[${ov.overlay_id}]`,
      });
    }
    if (ov.kind === "caption_rail" && txtRaw.length >= 10 && ov.timeline_duration_s >= 0.25) {
      const cps = txtRaw.length / ov.timeline_duration_s;
      if (cps > 20) {
        findings.push({
          code: "CAPTION_CPS_TOO_FAST",
          message: `Caption runs at ${cps.toFixed(1)} cps (> 20 cps ceiling) over ${ov.timeline_duration_s.toFixed(2)}s.`,
          location: `overlay[${ov.overlay_id}]`,
        });
      }
      if (words >= 4 && ov.timeline_duration_s < 0.75) {
        findings.push({
          code: "CAPTION_DURATION_SHORT",
          message: `4+-word caption lasts ${ov.timeline_duration_s.toFixed(2)}s (< 0.75s minimum comfortable dwell).`,
          location: `overlay[${ov.overlay_id}]`,
        });
      }
    }
  }
  return findings;
}

function scanHtmlFilesForPerformance(projectDir: string): PerformanceFinding[] {
  const findings: PerformanceFinding[] = [];
  const candidates: string[] = [];
  const rootHtml = path.join(projectDir, "index.html");
  let fontBounds: ReadonlyMap<string, FontWeightBounds> = parseStagedFontWeightMap("");
  if (fs.existsSync(rootHtml)) {
    candidates.push(rootHtml);
    fontBounds = parseStagedFontWeightMap(fs.readFileSync(rootHtml, "utf8"));
  }
  const compDir = path.join(projectDir, "compositions");
  if (fs.existsSync(compDir) && fs.statSync(compDir).isDirectory()) {
    for (const entry of fs.readdirSync(compDir)) {
      if (entry.endsWith(".html")) {
        candidates.push(path.join(compDir, entry));
      }
    }
  }

  for (const filePath of candidates) {
    const html = fs.readFileSync(filePath, "utf8");
    const rel = path.relative(projectDir, filePath);
    if (CSS_BLUR_RE.test(html)) {
      findings.push({
        code: "FORBIDDEN_CSS_BLUR",
        message: "HTML/CSS output contains disallowed CSS blur or backdrop-filter.",
        location: rel,
      });
    }
    if (rel !== "index.html" && !html.includes('data-layout-ignore="true"')) {
      MICRO_FONT_RE.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = MICRO_FONT_RE.exec(html)) !== null) {
        const px = Number(m[1]);
        if (Number.isFinite(px) && px > 0 && px < 20) {
          findings.push({
            code: "MICRO_TEXT_DETECTED",
            message: `Font size ${px}px is below the 20px broadcast legibility floor.`,
            location: rel,
          });
          break;
        }
      }
      scanCssTypographyRules(html, rel, fontBounds, findings);
    }
  }
  return findings;
}

export async function lintHyperframesProjectDir(
  projectDir: string,
  entryFile?: string
): Promise<ProjectValidationSummary> {
  const realDir = fs.realpathSync(path.resolve(projectDir));
  const resolvedEntry = entryFile ? path.resolve(realDir, entryFile) : undefined;
  const perfFindings = scanHtmlFilesForPerformance(realDir);
  const projectLint = await lintProject(
    realDir,
    resolvedEntry,
    { host: "cli" },
    { includeUnmounted: true }
  );

  const flattened: Array<HyperframeLintFinding & { file: string }> = [];
  for (const item of projectLint.results) {
    for (const finding of item.result.findings) {
      flattened.push({ ...finding, file: item.file });
    }
  }

  const fatalPerf = perfFindings.filter((f) => !NON_FATAL_WARNING_CODES.has(f.code));
  const warnPerfCount = perfFindings.length - fatalPerf.length;
  const totalErrors = projectLint.totalErrors + fatalPerf.length;
  return {
    ok: totalErrors === 0,
    totalErrors,
    totalWarnings: projectLint.totalWarnings + warnPerfCount,
    performanceViolations: perfFindings,
    hyperframesFindings: flattened,
  };
}
