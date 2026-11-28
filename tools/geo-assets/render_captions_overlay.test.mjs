import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { buildConcatTimeline, parseAssCaptions, parseJsonCaptions } from "./render_captions_overlay.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("parseAssCaptions extracts Default style and strips ASS override tags", () => {
  const sample = `[Script Info]
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter,46,&H00FAF7F5,&H00FAF7F5,&H1F261D07,&H1F000000,-1,0,0,0,100,100,0.46,0,1,0.55,2.2,2,84,84,525,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.40,Default,,0,0,0,,{\\fad(110,0)\\blur1.1}Dari Pulau Sabang
Dialogue: 0,0:00:01.50,0:00:02.60,Default,,0,0,0,,{\\fad(110,0)\\blur1.1}di ujung barat\\NAceh
Dialogue: 0,0:00:00.00,0:00:05.00,SourceCredit,,0,0,0,,Imagery ©Google
`;

  const parsed = parseAssCaptions(sample);
  assert.equal(parsed.style.fontFamily, "Inter");
  assert.equal(parsed.style.fontSize, 46);
  assert.equal(parsed.style.marginV, 525);
  assert.equal(parsed.style.colorHex, "#F5F7FA");
  assert.equal(parsed.style.fadeInMs, 110);
  assert.equal(parsed.cues.length, 2);
  assert.equal(parsed.cues[0].text, "Dari Pulau Sabang");
  assert.equal(parsed.cues[1].text, "di ujung barat\nAceh");
});

test("render_captions_overlay uses calibrated 46/42 fallback sizes, #F5F7FA ink, +0.01em tracking, and 4-layer snow-safe shadow", () => {
  const src = readFileSync(join(__dirname, "render_captions_overlay.mjs"), "utf8");
  assert.match(src, /isPortrait \? 46 \* scale : 42 \* scale/);
  assert.match(src, /0 0 24px rgba\(0, 0, 0, 0\.32\)/);
  assert.match(src, /letter-spacing:\s*0\.01em;/);
  const parsedJson = parseJsonCaptions({ segments: [{ start: 0, end: 1.5, text: "Test" }] });
  assert.equal(parsedJson.style.colorHex, "#F5F7FA");
  const parsedNoStyle = parseAssCaptions("Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hi");
  assert.equal(parsedNoStyle.style.colorHex, "#F5F7FA");
});

test("buildConcatTimeline stays drift-free and inserts two fade-in ramp frames per cue", () => {
  const cues = [
    { start_s: 0.2, end_s: 1.4, text: "First" },
    { start_s: 1.5, end_s: 2.6, text: "Second" },
  ];
  const segs = buildConcatTimeline(cues, 3.0, 30, 110);
  const total = segs.reduce((acc, s) => acc + s.duration_s, 0);
  assert.ok(Math.abs(total - 3.0) < 1e-6, `expected 3.0s total, got ${total}`);
  assert.equal(segs[0].file, "blank.png");
  assert.equal(segs[1].file, "cue_0000_f1.png");
  assert.equal(segs[2].file, "cue_0000_f2.png");
  assert.equal(segs[3].file, "cue_0000.png");
  assert.equal(segs[segs.length - 1].file, "blank.png");
});
