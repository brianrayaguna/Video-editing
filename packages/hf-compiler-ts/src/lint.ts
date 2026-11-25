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
    if (
      ov.timeline_duration_s < 0.45 &&
      (ov.kind === "caption_rail" || ov.kind === "kinetic_callout" || ov.kind === "data_card")
    ) {
      const txtRaw = String(
        ov.props.text ?? ov.props.headline ?? (ov.variables?.text ?? ov.variables?.headline ?? "")
      ).trim();
      const words = txtRaw ? txtRaw.split(/\s+/).length : 0;
      if (words > 3) {
        findings.push({
          code: "KINETIC_LEGIBILITY_DURATION",
          message: `Text overlay displays ${words} words for ${ov.timeline_duration_s.toFixed(2)}s (< 0.45s); may be unreadable in motion.`,
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
  if (fs.existsSync(rootHtml)) {
    candidates.push(rootHtml);
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
    if (CSS_BLUR_RE.test(html)) {
      findings.push({
        code: "FORBIDDEN_CSS_BLUR",
        message: "HTML/CSS output contains disallowed CSS blur or backdrop-filter.",
        location: path.relative(projectDir, filePath),
      });
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

  const fatalPerf = perfFindings.filter((f) => f.code !== "KINETIC_LEGIBILITY_DURATION");
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
