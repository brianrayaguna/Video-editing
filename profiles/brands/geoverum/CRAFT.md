# Geoverum Craft

Brand-specific visual, typographic, audio, and cartographic documentary rules across two documentary formats (`9:16` portrait and `16:9` landscape). Engine-wide motion and layer boundaries live in [`../../../DESIGN.md`](../../../DESIGN.md). Runtime pacing, tokens, and guardrails live in [`brand_style_policy.json`](brand_style_policy.json). Advisory directing heuristics and concrete exemplars live in [`editorial_playbook.json`](editorial_playbook.json).

---

## Two documentary formats

Both formats share the same Geoverum cartographic documentary visual DNA and differ in canvas geometry, pacing envelope, transition grammar, and chapter layout:

- **`9:16` (`1080x1920` @ `30 fps`, short documentary)**: Vertical cartographic explainer combining ~80% 2.5D/3D satellite and parchment cartography, ~10% full-bleed 2D animated mechanism and geological/underwater cross-sections, ~5% aerial/archival field proof B-roll, ~3% light-neutral/dark vector choropleths and multi-panel splits, and ~2% dark-mode traffic/radar visualizations (`0%` generative video). Supports both brisk multi-beat editing (~`5.3 cuts/min` mean, `0.85–2.2s` field proof bursts, `1.2–4.0s` kinetic hooks) and continuous `15–60s` map glides (`min_shot >= 0.75s`, `max_hold <= 45.0s`) while maintaining active camera motion across `>= 94%` of `0.5s` windows and cycling graphic states every `3–6s`.
- **`16:9` (`1920x1080` / `3840x2160` @ `30 fps`, long documentary)**: Landscape documentary alternating cartographic context with archival and live field evidence (`min_shot >= 1.5s`, `max_hold <= 20.0s`).

---

## Visual hierarchy & semantic color system

Keep the canvas legible through luminance separation and crisp exterior borders rather than emptying the screen:

1. **Tier 1 — Ground & Basemap (70–80% calm energy)**:
   - **Marine satellite ocean**: Deep marine teal **`#083847`**–`#154957` (`surface_elevated: #083847`; band luminance `75–115`), paired with abyssal `#03161F` for dark surface backing and shadow anchors.
   - **Blueprint tabletop & measurement mode** (opening hooks and scale analysis): Full-frame deep blueprint drafting grid **`#14427A`** defaulted to straight `0°` framing—supporting direct boxless editorial typography on the grid, crisp continent/territory silhouette cutouts with T-bracket dimensions, or clean photographic media plates (never a tilted dark KPI crosshair box).
   - **Historical parchment mode** (past centuries, archival decrees, and ink cutaways): Warm sepia parchment **`#B9A386`** landmass with muted slate-teal `#5A7D80` ocean, straight `0°` full-bleed sepia parchment canvases, boxless serif era stamps directly over footage, or full archival manuscript sheets (never a floating tilted mini quote card).
2. **Tier 2 — Context (10–15%)**: Low-contrast orientation labels with crisp dark halos, subtle coastline strokes, and clean dark monochrome vector basemaps (`#0B0E11`) during vertical split-wipe comparisons and trade-arc diagrams.
3. **Tier 3 — Focal Lead (high-contrast signal synced to narration)**:
   - **Amber / yellow `#F5C542`**: Routes, geodesic arcs, dual-unit distance brackets, UTC/etymology headers, counters, vertical depth split dividers, and `16:9` chapter plates.
   - **Crimson `#C2412D`**: Primary territory highlight, hazard beacons, circular myth-debunk markers, and stark ortho border strokes.
   - **Cobalt `#2E74E6`**: Secondary comparative territory fill, elevation zones, and vertical longitude columns.
   - **Hydro cyan `#7CE0F9`**: Meridian/parallel lasers, altitude ladders, waterbody highlights, below-sea-level masks, and curved open-water labels.
   - **Ecological emerald `#2E9E44`** *(domain accent)*: Rainforest, shelterbelt, and low-elevation ecological fills.

Territory fill and border rules:
- Dissolve internal administrative seams into unified exterior coastlines before highlighting landmasses, except when explicitly explaining internal federal subdivisions with numbered leader lines.
- For multi-territory comparisons, stagger fills in narration mention order (`>= 0.5s`), preserve terrain relief via multiply tint or clean diagonal hatch stripes, and outline highlighted territories with crisp **`2–3px` white exterior rims** (`#F4F1EA`) so adjacent colors remain sharp and legible.
- Avoid violet or magenta default accents (`OKLCH` / `HSL` hue `265°–335°`).

---

## Watermark (disabled by default)

- Disabled by default (`watermark_default: false`) to keep vertical and widescreen masters clean.
- When explicitly enabled for distribution: **text-only lowercase `geoverum`** (no logo or globe icon), `18px` at 1080p (`36px` at 4K), `Space Grotesk` `600`, `letter-spacing: 0.12em`, `opacity: 0.72` (range `0.55–0.85`), subtle dark shadow for legibility, positioned top-right slightly down (`9:16`: `top: 16.0%`, `right: 5.5%`; `16:9`: `top: 7.5%`, `right: 5.0%`). Never use pill containers or glowing status dots.

---

## Captions and typography

- **Style**: Plain documentary subtitle style (`caption_style: "plain"`) — crisp `#F4F1EA` / `#FFFFFF` geometric sans text with subtle dark `text-shadow` for legibility over desert, snow, or dark ocean; no pill box, no bar background, no automatic word-color karaoke highlight, and no slide/bounce entrance.
- **Phrasing**: Natural clause-split **sentence case**, **2–4 words per group** (`max_words_per_caption_group: 4`). Mid-sentence continuations naturally begin lowercase; never force Title Case or ALL-CAPS on captions.
- **Horizontal alignment**: True horizontal center (`x = 50%`) using symmetric horizontal margins (`max(left_pct, right_pct)`).
- **Vertical anchor**:
  - `9:16`: Anchored at **`y = 70.0%`** (`bottom ≈ 28.5%`, clear of vertical platform bottom UI chrome while leaving central cartography unobstructed).
  - `16:9`: Standard documentary lower-third (`bottom ≈ 9.5%`).
- **Proportional sizing**: `42–46px` font size (~`3.0%` frame height line box) on `1080x1920`, `42px` on `1920x1080`, `84px` on `3840x2160`, `Space Grotesk` / `Inter` / `Montserrat` `500–600`, `line-height: 1.24`.
- **Transitions**: Instant **1-frame hard cut (`<= 33ms` @ `30 fps`)**, opacity-only.
- **Bundled typography palette (8 local OFL families staged for Chromium & `libass`)**:
  - **Display & counters**: `Archivo Black` for tabular distances, years, count-ups, acronym initials, kinetic portal titles, and map callouts; `Unbounded` for major basin marks and hero display titles.
  - **Editorial sans & captions**: `Space Grotesk`, `Inter`, and `Montserrat` for plain centered captions, highlight tags, sub-labels, and quiet credits.
  - **Historical & archival serif**: `EB Garamond` (upright + italic) and `Playfair Display` for historical parchment plates, era stamps, and archival decrees.
  - **Technical telemetry**: `Space Mono` (regular + bold) for coordinates, elevation ladders, and technical blueprint rulers.

---

## Core cartographic & visual storytelling grammar

1. **Continuous Camera Motion (`>= 94%` active)**: Keep virtual map cameras smoothly pushing, pulling, tilting, or tracking across nearly every `0.5s` window. Avoid unmotivated static holds.
2. **Transition Grammar (`9:16`)**:
   - **Radial whip-zoom blur (`0.3–1.0s`)** for regional leaps and plunges into 2D cross-sections or aerial B-roll.
   - **Vertical white-bar split wipe (`0.3–0.6s`)** between satellite relief and dark monochrome vector or blueprint measurement surfaces.
   - **Feathered dark curtain sweep & optical spyglass iris (`0.4–0.7s`)** using pure alpha gradients (zero CSS blur) or circular SVG masks so `y = 70%` plain captions remain legible in front.
   - **Oversized kinetic letter portal (`0.5–0.8s`)** scaling bold display lettering cleanly into the next cartographic view, or **3D horizontal card-flip** shifting between flat-map projections and a 3D spherical globe.
   - **Clean crossfade (`0.4–0.5s`)** and **hard cuts** for rapid proof bursts. Reserve `amber_light_leak` strictly for `16:9` long-form transitions.
3. **Dual-Unit Dimension Brackets, T-Brackets & Radius Rings**: Stack imperial and metric units (`2.4 mi (3.8 km)`, `50.5 km (31.38 mi)`, `945 m (3,100 ft)`) along white double-headed arrows, technical T-bracket callipers, dashed amber corridors, or expanding concentric acoustic/distance radius rings drawn via `SVG stroke-dashoffset`.
4. **Full-Bleed 2D Animated Cross-Sections, Scale Ladders & Longitude Bands**: Cut via radial whip-zoom from overhead maps into full-bleed (`inset: 0`) flat-vector 2D cross-sections (`6–19s`: exploded geological strata separating layer-by-layer with curved white arrows, soil/roots, underground mines, underwater trenches, amber vertical split depth comparisons, or monochrome 2D historical ink cutaways), paired with left-anchored altitude/depth ladders and translucent vertical longitude/UTC columns. Never enclose a cross-section inside a floating dark dashboard panel.
5. **Diagonal Multi-Panel, Horizontal Analogy & Demographic Splits**: Disambiguate nested political entities with crisp white-seamed 2- or 3-panel diagonal splits or top/bottom analogy splits, and quantify population ratios with boxless 10-figure SVG silhouette grids directly over a soft scrim.
6. **Boxless Coordinate Pins, Tight Highlight Tags, Etymology Arrows, Lassos, Gauges & Myth Debunks**:
   - Place crisp `2px` white vertical or angled elbow leader pins (`SVG stroke-dashoffset` draw-on from a minimal anchor dot) leading directly to shadowed bold text with zero HUD box; add a compact dark-and-amber population badge only when citing discrete headcounts.
   - For sharp single-line stat callouts directly on maps, use tight `0px`-radius solid amber, charcoal, or crimson highlight tags sized strictly to text width; for place-name origins, link the source name to its meaning with a curved hand-drawn white SVG etymology arrow.
   - Use hand-drawn overlapping SVG focus lassos (`amber`, `white`, or `crimson`) around focal islands/territories, live boxless physical gauges (rising/dropping mercury thermometer and staggered SVG acoustic decibel meter), crimson circular `X` overlays for myth busting, boxless side-by-side dual-unit numeric count-ups, and true-scale silhouette overlays to make scale tangible.
7. **Rapid Field B-Roll, Choropleths & Radar Evidence**: Follow a whip-zoom dive with `3–4` concise real aerial/field proof clips (`0.85–2.2s` each), clean light-neutral data choropleths/heatmaps, or dark-mode air-traffic radar visualizations; add quiet `source_credit` attribution when external imagery or archival footage requires it.
8. **Non-Generative Asset Policy**: Produce all cartography, 2D cross-sections, weather/ice animations, gauges, and charts deterministically via MapLibre and procedural HyperFrames HTML/SVG/GSAP alongside real archival or stock B-roll—never generative video synthesis.

---

## Audio, VO & kinetic SFX craft

- **Voiceover pacing**: Crisp, continuous narration (`53–80%` speech density, minimal dead air `<= 3%` median silence). Cuts align to narration clauses rather than musical beats.
- **BGM bed**: Quiet, heavy-ducked (`ducking_strength: 0.90`) mysterious, dramatic, or focused ambient bed (`76–135 BPM` normalized) sitting well beneath voiceover; master all deliverables to `-14.0 LUFS` integrated, `<= -1.0 dBTP` true peak (`48 kHz` stereo AAC-LC).
- **Kinetic SFX (`sfx_policy: "kinetic_accents"`)**: Place short, clean `pop`, `ding`, `click`, and `whoosh` accents at **`15–28` hits/min** locked directly (`0 ms` offset) to territory fills, text/metric callouts, counters, and transition midpoints.

---

## Rejected chrome

- Dark translucent rounded dashboard/HUD cards (`rgba(..., 0.85–0.92)`), thin cyan/neon outlines, decorative viewfinder corner-bracket KPI boxes (`┌ ┐ └ ┘`), and thick left- or top-accent border strips (`border-left: 4–7px`, `border-top: 4px`) wrapping map labels, charts, or diagrams
- Forced decorative tilt (`-2°` to `-3°`) on text containers or floating mini sepia quote cards with thin middle divider lines (default blueprint and historical plates to straight `0°` framing)
- Presentation-style uppercase eyebrow/kicker labels (`PART 02`, `CHAPTER 1`, `TERRITORY SCALE`, `POLITICAL GEOGRAPHY`, `GEOLOGICAL MECHANISM`) stacked above short-form (`9:16`) display titles, charts, or cross-sections (reserve numbered chapter plates strictly for long-form `16:9` `amber_fact_card`)
- Floating short horizontal decorative accent rules positioned above numbers, metrics, or titles (`.metric-rule`, `.outro-rule`) or decorative divider bars between blueprint numbers and titles
- Uniform `power2.out` fade-and-slide-up entrances across every component; animate with purposeful `SVG stroke-dashoffset` draw-on, `clip-path` wipes, 3D perspective flips, or baseline mask reveals
- Third-party basemap attribution watermarks or vendor UI chrome inside master frames
- Unbordered flat neon mud fills lacking crisp exterior coastline rims or terrain texture
- Cartoon countryball or googly-eye meme overlays (use authoritative vector flag markers or pins instead)
- Unmotivated static map holds without camera motion or graphic progression
- Violet / magenta default country washes
- Heavy CSS `backdrop-filter` / `filter: blur()` glass cards and SaaS pill watermarks
- Shouty full-width yellow `#FFD60A` fact bars and document/paper walls covering the focal subject
- Isometric factory / money-bag / emoji raster props
- Dual yellow light-beam spears
- Film-strip / viewfinder chrome, film-reel archival frames, false-color thermal grades, and double-exposure faces on contemporary B-roll
