import assert from "node:assert/strict";
import test from "node:test";
import { buildConcatTimeline, parseAssCaptions } from "./render_captions_overlay.mjs";

test("parseAssCaptions extracts Default style and strips ASS override tags", () => {
  const sample = `[Script Info]
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter,52,&H00EAF1F4,&H00EAF1F4,&H1F1F1603,&H1F000000,-1,0,0,0,100,100,0.46,0,1,0.55,2.2,2,84,84,525,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.40,Default,,0,0,0,,{\\fad(110,0)\\blur1.1}Dari Pulau Sabang
Dialogue: 0,0:00:01.50,0:00:02.60,Default,,0,0,0,,{\\fad(110,0)\\blur1.1}di ujung barat\\NAceh
Dialogue: 0,0:00:00.00,0:00:05.00,SourceCredit,,0,0,0,,Imagery ©Google
`;

  const parsed = parseAssCaptions(sample);
  assert.equal(parsed.style.fontFamily, "Inter");
  assert.equal(parsed.style.fontSize, 52);
  assert.equal(parsed.style.marginV, 525);
  assert.equal(parsed.style.colorHex, "#F4F1EA");
  assert.equal(parsed.style.fadeInMs, 110);
  assert.equal(parsed.cues.length, 2);
  assert.equal(parsed.cues[0].text, "Dari Pulau Sabang");
  assert.equal(parsed.cues[1].text, "di ujung barat\nAceh");
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
