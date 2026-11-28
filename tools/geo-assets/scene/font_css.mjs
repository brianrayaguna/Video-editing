import { existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readTtfWeightAxis } from "../lib/ttf_metadata.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");

export const __FONT_KNOWN_FAMILIES = Object.freeze({
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
});

let __cachedDynamicFontFaces = null;

export function buildDynamicFontFaceCss(baseUrl) {
  if (__cachedDynamicFontFaces === null) {
    const fontsDir = join(REPO_ROOT, "assets", "geo", "fonts");
    const faces = [];
    if (existsSync(fontsDir)) {
      const files = readdirSync(fontsDir)
        .filter((fn) => /\.(?:ttf|otf)$/i.test(fn))
        .sort();
      for (const fn of files) {
        const fullPath = join(fontsDir, fn);
        const base = fn.replace(/\.(?:ttf|otf)$/i, "");
        const style = /italic/i.test(base) ? "italic" : "normal";
        const stem = base
          .replace(
            /[-_](Italic[-_])?(Variable|Regular|ExtraLight|Light|Medium|SemiBold|Bold|ExtraBold|Black|Italic)+$/i,
            ""
          )
          .replace(/[-_](BoldItalic|BlackItalic|Italic)$/i, "");
        const compact = stem.toLowerCase().replace(/[^a-z0-9]/g, "");
        const family =
          __FONT_KNOWN_FAMILIES[compact] ||
          stem.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").trim();
        if (!family) continue;
        const axis = readTtfWeightAxis(fullPath);
        const isVariable = axis ? axis.isVariable : /variable/i.test(base);
        let weight = "400";
        if (axis?.isVariable) {
          weight = `${axis.minWeight} ${axis.maxWeight}`;
        } else if (axis && !axis.isVariable) {
          weight = String(axis.minWeight);
        } else if (/variable/i.test(base)) {
          weight = "100 900";
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
        }
        const fmt = fn.toLowerCase().endsWith(".otf") ? "opentype" : "truetype";
        faces.push({ fn, family, weight, style, fmt, isVariable });
      }
    }
    // Deduplicate static vs variable collisions per (family, style) so Chromium resolves exact fvar axes cleanly.
    const varKeys = new Set(faces.filter((f) => f.isVariable).map((f) => `${f.family.toLowerCase()}::${f.style}`));
    __cachedDynamicFontFaces = faces.filter(
      (f) => f.isVariable || !varKeys.has(`${f.family.toLowerCase()}::${f.style}`)
    );
  }
  const deduped = __cachedDynamicFontFaces;
  if (deduped.length > 0) {
    const rules = deduped.map(
      (f) =>
        `    @font-face { font-family: "${f.family}"; src: url("${baseUrl}/fonts/${encodeURIComponent(f.fn)}") format("${f.fmt}"); font-weight: ${f.weight}; font-style: ${f.style}; font-display: block; }`
    );
    rules.push("    :root, body { font-synthesis: none; font-optical-sizing: auto; }");
    return rules.join("\n");
  }
  return `    @font-face { font-family: "Barlow Condensed"; src: url("${baseUrl}/fonts/BarlowCondensed-Bold.ttf") format("truetype"); font-weight: 700; font-display: block; }
    @font-face { font-family: "Barlow Condensed"; src: url("${baseUrl}/fonts/BarlowCondensed-ExtraBold.ttf") format("truetype"); font-weight: 800; font-display: block; }
    @font-face { font-family: "Inter"; src: url("${baseUrl}/fonts/Inter-Variable.ttf") format("truetype"); font-weight: 100 900; font-display: block; }
    @font-face { font-family: "Rubik"; src: url("${baseUrl}/fonts/Rubik-Variable.ttf") format("truetype"); font-weight: 300 900; font-display: block; }
    @font-face { font-family: "Lora"; src: url("${baseUrl}/fonts/Lora-Italic-Variable.ttf") format("truetype"); font-weight: 400 700; font-style: italic; font-display: block; }
    @font-face { font-family: "IBM Plex Mono"; src: url("${baseUrl}/fonts/IBMPlexMono-Bold.ttf") format("truetype"); font-weight: 700; font-display: block; }
    :root, body { font-synthesis: none; font-optical-sizing: auto; }`;
}

