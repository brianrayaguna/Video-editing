# Geoverum Craft

Brand-specific visual, typographic, and cartographic documentary rules across two documentary formats (`9:16` portrait and `16:9` landscape). Engine-wide motion and layer boundaries live in [`../../../DESIGN.md`](../../../DESIGN.md). Runtime pacing, tokens, and guardrails live in [`brand_style_policy.json`](brand_style_policy.json). Advisory directing heuristics live in [`editorial_playbook.json`](editorial_playbook.json).

---

## Two documentary formats

Both formats share the same Geoverum cartographic documentary visual DNA and differ only in canvas geometry, pacing envelope, and chapter layout:

- **`9:16` (`1080x1920`, short documentary)**: Vertical documentary supporting both continuous map glides and map ↔ live B-roll narratives (`min_shot >= 1.8s`, `max_hold <= 30.0s`).
- **`16:9` (`1920x1080` / `3840x2160`, long documentary)**: Landscape documentary alternating cartographic context with archival and live field evidence (`min_shot >= 1.5s`, `max_hold <= 20.0s`).

---

## Three-tier visual hierarchy

Keep the canvas legible through luminance and depth separation rather than emptying the screen:

1. **Tier 1 — Ground (75–85% calm energy)**: Abyssal ocean `#03161F`, desaturated satellite relief, and subtle geographic context lines.
2. **Tier 2 — Context (10–15%)**: Low-contrast orientation labels with crisp dark halos, muted borders, or quieter terrain holds for neighboring regions.
3. **Tier 3 — Focal Lead (1 primary signal per beat)**: One high-contrast focal element timed to the narration — crimson `#C2412D` primary territory fill, cobalt `#2E74E6` comparative territory fill, amber `#F5C542` corridor/metric, or hydro cyan `#7CE0F9` waterbody/river vector.

Additional surface rules:

- No violet or magenta accents (`OKLCH` / `HSL` hue `265°–335°`).
- Dissolve internal administrative seams into a single exterior coastline before highlighting landmasses. Preserve terrain relief inside fills (build-time grade or multiply blend), never opaque pastel washes.

---

## Watermark (optional)

- **Optional and disabled by default** (`watermark_default: false`).
- When enabled: **text-only lowercase `geoverum`** — **no logo or globe icon**.
- Small, understated proportion (`18px` at 1080p, `36px` at 4K), `Space Grotesk` `600`, `letter-spacing: 0.12em`, `opacity: 0.72` (range `0.55–0.85`), subtle dark shadow for legibility.
- Position: **top-right, slightly down** on both formats:
  - `9:16`: `top: 16.0%`, `right: 5.5%` (just below platform top chrome, clear of lower-right action buttons).
  - `16:9`: `top: 7.5%`, `right: 5.0%`.
- Never use pill containers, glowing status dots, or double watermarks.

---

## Captions and typography

- **Style**: Plain documentary subtitle style (`caption_style: "plain"`) — clean `#F4F1EA` text with crisp dark `text-shadow`, **no rounded pill box**, **no automatic yellow word highlighting**, and **no slide/scale bounce**.
- **Phrasing**: Sentence case, **2–3 words per group** (`max_words_per_caption_group: 3`), split cleanly at clause/pause gaps (`>= 150ms`) and punctuation.
- **Horizontal alignment**: True horizontal center (`x = 50%`) using symmetric horizontal margins (`max(left_pct, right_pct)`) so captions never drift left on asymmetric vertical safe zones.
- **Vertical anchor**:
  - `9:16`: Lower-center at **`y ≈ 70%`** (`bottom ≈ 28.5%`, clear of bottom Shorts/Reels/TikTok UI while avoiding center obstruction).
  - `16:9`: Standard documentary lower-third (`bottom ≈ 9.5%`).
- **Proportional sizing**: Scales with canvas resolution (`44px` on `1080x1920`, `42px` on `1920x1080`, `84px` on `3840x2160`), `Space Grotesk` `600`, `line-height: 1.24`.
- **Transitions**: Hard cut (`<= 50ms`, opacity-only).
- **Display metrics & chapter plates**: `Archivo Black` tabular numerals for distances, elevations, and capacities; `Unbounded` reserved for title/basin display marks.

---

## Cartographic annotations and B-roll cohesion

- Place callouts in open water or quiet margins — never over the focal landmass or fault they explain.
- Keep `>= 12px` clearance (`>= 24px` preferred at 1080p portrait) from coastlines and neighboring labels.
- Curved hydrographic labels (`#7CE0F9`) appear only when zoom provides open-water clearance (`z >= 7.2`, shoreline clearance `>= 24px`).
- Leaders are `1.5–2px` and stop `4–6px` short of the target.
- Comparing two territories: stagger fills (`>= 0.6s`) using crimson `#C2412D` and cobalt `#2E74E6` (or asymmetric tint + terrain hold) — never simultaneous multi-neon fills.
- Maritime corridors and river highways: one amber `#F5C542` or hydro `#7CE0F9` stroke-dash path per beat; no red bloom, no dual light-beam spears, no 3D ship props.
- Border anomalies: pair an amber geodesic/meridian stroke with a hydro meander only when narration contrasts political vs natural boundaries.
- Long-form `16:9` chapter plates: compact amber `#F5C542` surface + `#03161F` ink in lower-third safe band; never full-width shouty yellow bars.
- Map ↔ live or archival B-roll handoffs: hard cut, J/L audio cut, clean crossfade, or amber light-leak; add quiet `source_credit` attribution when using external imagery or stock footage; no double-exposure faces and no vendor basemap chrome inside the master frame.

---

## Rejected chrome

- Violet / magenta default country washes
- Simultaneous multi-neon neighbor fills
- Thematic 3D map props (volcanoes, ships, collage inserts)
- Shouty full-width yellow `#FFD60A` fact bars
- Document / paper walls covering the focal subject
- Isometric factory / money-bag / regulation raster props
- Dual yellow light-beam spears
- Vendor basemap attribution stacks inside the master frame
- ALL-CAPS land labels covering the focal landmass
- Film-strip / viewfinder chrome and corner sticker clusters
- On-map calendar widgets, rain-cloud icons, equator gimmick strokes
- False-color thermal / magenta analysis grades as default look
- Film-reel archival frames and red-circle evidence stickers
- Double-exposure faces on contemporary B-roll
