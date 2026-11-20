# Geoverum Craft

Brand-specific visual, typographic, storytelling, audio, and cartographic documentary rules across two documentary formats (`9:16` portrait and `16:9` landscape). Engine-wide motion and layer boundaries live in [`../../../DESIGN.md`](../../../DESIGN.md). Runtime pacing, tokens, and guardrails live in [`brand_style_policy.json`](brand_style_policy.json). Advisory directing heuristics and concrete exemplars live in [`editorial_playbook.json`](editorial_playbook.json).

---

## Two documentary formats

Both formats share the same Geoverum cartographic documentary visual DNA and differ in canvas geometry, pacing envelope, transition grammar, and chapter layout:

- **`9:16` (`1080x1920` @ `30 fps`, short documentary)**: Vertical cartographic explainer built on five distinct visual surfaces—2.5D/3D graded satellite relief (~65–75%), blueprint drafting grids and dark obsidian vector maps (~10–12%), full-bleed 2D animated geological/depth cutaways (~8–10%), sepia historical parchment maps (~5%), and rapid aerial/field proof B-roll or radar visualizations (~5%), with `0%` generative video. Supports both **continuous map glides** (`2–4 cuts/min`, sustained `15–60s` camera motion where map blocks, highlights, and labels mutate every `1.5–4.0s`) and **brisk multi-surface documentaries** (`6–17 cuts/min`, `0.85–2.2s` field proof bursts, `1.2–4.0s` kinetic hooks) under `min_shot >= 0.75s`, `max_hold <= 45.0s`, active camera motion across `>= 94%` of `0.5s` windows, and graphic state changes every `2–6s`.
- **`16:9` (`1920x1080` / `3840x2160` @ `30 fps`, long documentary)**: Landscape documentary alternating cartographic context with archival and live field evidence (`min_shot >= 1.5s`, `max_hold <= 20.0s`).

---

## Storytelling architecture (`9:16` five-beat spine)

Structure short-form cartographic explainers around a tight, map-first five-beat narrative arc with zero intro bumpers or generic subscription outros:

1. **Immediate Geographic Paradox or Anomaly Hook (`0.0–5.0s`)**: Open directly on the map at frame `0` with one of four high-retention curiosity patterns:
   - *Border or ecological anomaly*: Reveal a glowing border line, invisible boundary, or counterintuitive spatial rule immediately on the map.
   - *Nested-entity disambiguation*: Split the canvas into a `2×2` quad or diagonal multi-panel map grid contrasting commonly confused territories.
   - *Extreme scale or duration shock*: Juxtapose an astonishing number or glowing footprint comparison directly against a familiar reference.
   - *Boundary-shape mystery*: Spotlight an unusual coastline, panhandle, or enclave with a pointer arrow and ask why the border stops where it does.
2. **Visual Scope & Scale Proof (`5.0–20.0s`)**: Pull out or shift basemap surface (`satellite -> blueprint drafting grid` or `satellite -> dark obsidian vector`) to prove true geographic extent, network numbering rules, or comparative area.
3. **Mechanism or Historical Origin Pivot (`20.0–45.0s`)**: Pivot on a crisp verbal hinge (*why*, *how*, *in the past*) paired with an immediate surface change—cutting into a full-bleed 2D geological/underwater cutaway for physical causes, a sepia parchment map with compass rose and era timeline bar for historical origins, or a dark obsidian vector network for structural systems.
4. **Escalation & Concrete Consequence (`45.0–54.0s`)**: Accelerate visual beats every `2–4s` using axis-aligned dual-unit crater/corridor measurements, stacked population counters, high-resolution urban ortho landmark masks, or circular portrait/flag leader clusters.
5. **Direct Cartographic Resolution (`54.0s+`)**: Resolve on a wide cartographic pull-back or final visual irony—avoid generic call-to-subscribe bumper plates unless explicitly requested by the brief.

---

## Five basemap surfaces & semantic color system

Switch intentionally between five distinct cartographic surfaces to signal narrative mode shifts and keep the canvas legible through luminance separation rather than clutter:

### Tier 1 — Ground & Basemap Surfaces (70–80% calm energy)

1. **Graded Marine-Teal Satellite Relief (primary spine)**:
   - Deep marine teal ocean **`#083847`**–`#154957` (`surface_elevated: #083847`; band luminance `75–115`), natural desaturated vegetation/desert relief with subtle 3D hillshade, paired with abyssal `#03161F` for dark surface backing and shadow anchors.
2. **Deep Blueprint Drafting Grid (`#14427A`)** (hooks, scale proofs, and spatial comparisons):
   - Default to straight `0°` framing across four concrete visual modes:
     - *Boxless editorial grid typography*: Direct Archivo Black numbers and titles over the architectural grid.
     - *Lifted relief cutout*: A satellite continent or territory cutout floating with soft drop shadow over faint monochrome world coastline outlines on the grid.
     - *White-bordered map or media card*: A crisp `8–12px` white-framed satellite world map or photographic plate with soft drop shadow (a subtle `±2–3°` angle is permitted solely on framed photographic/map cards, never on text HUD cards).
     - *Glowing footprint compare & calibrated scale ruler*: Side-by-side glowing cobalt/cyan true-scale architectural footprints or horizontal height/size comparison hairlines (`0 m`, `1 m`, `2 m` with dual imperial units).
3. **Dark Obsidian Vector Basemap (`#0B0E11` / `#101318`)** (route networks & urban district systems):
   - Deep charcoal landmass (`#16191D`), near-black water (`#080A0D`), and ultra-faint vector road grids (`#262B32`), engineered to maximize figure-ground separation for luminous dual-color route corridors or vivid `45°` diagonal-hatched city districts.
4. **Historical Parchment Relief & Parchment Drafting Grid (`#B9A386` / `#9E8B70`)** (historical origins & schematic rules):
   - Warm sepia landmass (`#B9A386`) with muted slate-teal ocean (`#5A7D80`), vintage compass rose anchored in open water, crisp white-rimmed historical territory blocks, and a thin **horizontal golden era timeline bar** (`start – end` year ticks) in the upper safe band.
   - Warm textured **parchment drafting grid** (`#8F7D66`) for schematic branching/numbering route diagrams with glowing vector branches, plus straight `0°` full archival treaty/manuscript sheets and boxless serif era stamps over footage.
5. **Full-Bleed 2D Vector Cutaways & Depth Columns (`inset: 0`)** (geology, volcanoes, ecology, underwater depth):
   - Flat-vector edge-to-edge cross-sections with sky/ocean/crust/mantle or seabed bands, crisp thin white outlines around active magma plumes or subsurface channels, concise horizontal surface labels, and an understated uppercase **`NOT TO SCALE`** micro-disclaimer in the bottom-left safe area when vertical exaggeration is applied.

### Tier 2 — Orientation Context (10–15%)

Low-contrast regional labels with crisp dark halos, subtle coastline strokes, faint reference grids, and quiet attribution labels.

### Tier 3 — Focal Signal Palette (synced to narration)

- **Amber / gold `#F5C542`**: Glowing border seams, routes, geodesic arcs, dual-unit distance brackets, UTC/etymology headers, counters, era timeline bars, vertical depth split dividers, and `16:9` chapter plates.
- **Crimson `#C2412D` / luminous `#EF4444`**: Primary territory highlight, glowing corridor dividers, pulsing hazard beacons, circular myth-debunk markers, and stark ortho border strokes.
- **Cobalt `#2E74E6`**: Secondary comparative territory fill, elevation zones, glowing blueprint footprints, and vertical longitude columns.
- **Hydro cyan `#7CE0F9` / `#38BDF8`**: Meridian/parallel lasers, altitude ladders, river and waterbody highlights, north–south schematic corridors, below-sea-level masks, and curved open-water labels.
- **Ecological emerald `#2E9E44`** *(domain accent)*: Rainforest, park/landmark masks, shelterbelt, and low-elevation ecological fills.
- Avoid violet or magenta default accents (`OKLCH` / `HSL` hue `265°–335°`) except when differentiating 5+ simultaneous administrative districts on a dark vector basemap.

---

## Map blocks, territory fills, glowing seams & split grids

Use disciplined cartographic geometry so territory blocks always preserve spatial clarity and never look like flat mud washes:

1. **45° Diagonal-Hatched Terrain Blocks**: Overlay semi-transparent `45°` diagonal stripes (`~6px` stripe / `6px` gap) on satellite or dark-vector polygons so cities, roads, and relief remain readable underneath; always seal every block with a crisp **`2–3px` pure white exterior rim (`#F4F1EA`)** and subtle drop shadow.
2. **Three-Layer Luminous Glowing Borders & Corridors**: Construct glowing borders, coastlines, island chains, and highway corridors as a three-layer stack—wide soft outer bloom (`12–18px`, `opacity 0.30`), mid glow (`6–8px`, `opacity 0.65`), and hot white-tinted inner core (`2.5–3.5px`, `opacity 1.0`)—in amber, crimson, or hydro-blue.
3. **Multi-Bloc Geopolitical Fills & Luminance Spotlight**: Dissolve internal administrative seams into unified exterior coastlines unless explicitly explaining internal federal subdivisions or multi-country blocs. When mapping multi-country blocs, separate internal borders with thin `1.5px` white lines, seal the exterior perimeter at `2.5px`, stagger fills in narration mention order (`>= 0.5s`), and spotlight active sub-groups by boosting saturation/luminance while dimming surrounding regions.
4. **`2×2` Quad & Diagonal Multi-Panel Map Grids**: Split the `9:16` canvas with sharp `4–6px` solid white dividers into 2, 3, or 4 simultaneous map views (each showing a hatched/rimmed block and bold label), then expand the active pane full-screen as narration dives into it.
5. **High-Resolution Urban Ortho + Landmark Footprint Masks**: On zoomed city imagery, draw a bright white exterior perimeter around the focal island or enclave and tint individual landmarks (parks in luminous emerald, corridors in crimson, financial districts in amber) linked by ultra-thin white leader lines.

---

## Watermark (disabled by default)

- Disabled by default (`watermark_default: false`) to keep vertical and widescreen masters clean.
- When explicitly enabled for distribution: **text-only lowercase `geoverum`** (no logo or globe icon), `18px` at 1080p (`36px` at 4K), `Space Grotesk` `600`, `letter-spacing: 0.12em`, `opacity: 0.72` (range `0.55–0.85`), subtle dark shadow for legibility, positioned top-right slightly down (`9:16`: `top: 16.0%`, `right: 5.5%`; `16:9`: `top: 7.5%`, `right: 5.0%`). Never use pill containers or glowing status dots.

---

## Dual-layer typography & layout

Maintain a strict visual separation between screen-fixed documentary captions and in-world cartographic labels:

### Layer A — Screen-Fixed Documentary Captions

- **Style**: Plain documentary subtitle style (`caption_style: "plain"`) — crisp `#F4F1EA` / `#FFFFFF` geometric sans text with subtle dark `text-shadow` for legibility over desert, snow, or dark ocean; no pill box, no bar background, no automatic word-color karaoke highlight, and no slide/bounce entrance.
- **Phrasing**: Natural clause-split **sentence case**, **2–4 words per group** (`max_words_per_caption_group: 4`). Mid-sentence continuations naturally begin lowercase; never force Title Case or ALL-CAPS on captions.
- **Alignment & Anchor**: True horizontal center (`x = 50%`) using symmetric horizontal margins (`max(left_pct, right_pct)`). Anchored at **`y = 70.0%`** (`bottom ≈ 28.5%`) on `9:16` and standard lower-third (`bottom ≈ 9.5%`) on `16:9`.
- **Proportional Sizing & Cuts**: `42–46px` (`~3.0%` frame height) on `1080x1920`, `42px` on `1920x1080`, `84px` on `3840x2160`, `Space Grotesk` / `Inter` / `Montserrat` `500–600`, `line-height: 1.24`, using instant **1-frame hard cuts (`<= 33ms` @ `30 fps`)**, opacity-only.

### Layer B — In-World Cartographic & Diagram Typography

- **Direct Axis-Aligned Map Labels**: Place shadowed bold `Archivo Black` / `Space Grotesk` labels directly on or beside the focal territory, rotating dimension lines and short place labels parallel to the geographic axis (crater walls, borders, island chains, river spans) while keeping Layer A captions strictly horizontal.
- **Tight Color-Matched District Tags**: On dense satellite or dark-vector maps, use tight `0–2px`-radius solid amber, emerald, cobalt, charcoal, or crimson label tags sized strictly to text width directly over the matching hatched polygon—zero borders, zero glass blur, zero oversized cards.
- **Stacked Dual-Unit Counters & Era Markers**: Pair large primary figures with compact stacked secondary units (`700 m / 2300 ft`, `9,537 mi / 15,349 km`, `137 islands and atolls`, `19.9M / 8.5M (42.8%)`), and anchor bold standalone years (`1803`, `1929`, `1971`) or horizontal golden timeline bars directly in the upper safe zone.
- **Bundled Typography Palette (8 local OFL families staged for Chromium & `libass`)**:
  - **Display & counters**: `Archivo Black` for tabular distances, years, count-ups, acronym initials, kinetic portal titles, and map callouts; `Unbounded` for major basin marks and hero display titles.
  - **Editorial sans & captions**: `Space Grotesk`, `Inter`, and `Montserrat` for plain centered captions, highlight tags, sub-labels, and quiet credits.
  - **Historical & archival serif**: `EB Garamond` (upright + italic) and `Playfair Display` for historical parchment plates, era stamps, and archival decrees.
  - **Technical telemetry**: `Space Mono` (regular + bold) for coordinates, elevation ladders, and technical blueprint rulers.

---

## Core motion, transition & storytelling grammar

1. **Continuous Camera Motion (`>= 94%` active)**: Keep virtual map cameras smoothly pushing, pulling, tilting, or tracking across nearly every `0.5s` window. Avoid unmotivated static holds.
2. **Transition Grammar (`9:16`)**:
   - **Radial whip-zoom blur (`0.3–1.0s`)** for regional leaps and plunges into 2D cross-sections or aerial B-roll.
   - **Vertical white-bar split wipe (`0.3–0.6s`)** between satellite relief and dark obsidian vector or blueprint measurement surfaces.
   - **Feathered dark curtain sweep & optical spyglass iris (`0.4–0.7s`)** using pure alpha gradients (zero CSS blur) or circular SVG masks so `y = 70%` plain captions remain legible in front.
   - **Oversized kinetic letter portal (`0.5–0.8s`)** scaling bold display lettering cleanly into the next cartographic view, or **3D horizontal card-flip** shifting between flat-map projections and a 3D spherical globe.
   - **Clean crossfade (`0.4–0.5s`)** and **hard cuts** for rapid proof bursts. Reserve `amber_light_leak` strictly for `16:9` long-form transitions.
3. **Dual-Unit Dimension Brackets, T-Brackets & Radius Rings**: Stack imperial and metric units (`2.4 mi (3.8 km)`, `50.5 km (31.38 mi)`, `700 m / 2300 ft`) along white double-headed arrows, technical T-bracket callipers, dashed amber corridors, or expanding concentric acoustic/distance radius rings drawn via `SVG stroke-dashoffset`.
4. **Full-Bleed 2D Animated Cross-Sections, Scale Ladders & Longitude Bands**: Cut via radial whip-zoom from overhead maps into full-bleed (`inset: 0`) flat-vector 2D cross-sections (`6–19s`: exploded geological strata separating layer-by-layer with curved white arrows, volcanic hotspot plumes, soil/roots, underground mines, underwater trenches, amber vertical split depth comparisons, or monochrome 2D historical ink cutaways), paired with left-anchored altitude/depth ladders and translucent vertical longitude/UTC columns. Never enclose a cross-section inside a floating dark dashboard panel.
5. **Quad/Diagonal Multi-Panel, Horizontal Analogy & Demographic Splits**: Disambiguate nested political entities with crisp white-seamed `2×2` quad splits, 2- or 3-panel diagonal splits, or top/bottom analogy splits, and quantify population ratios with boxless 10-figure SVG silhouette grids directly over a soft scrim.
6. **Boxless Coordinate Pins, Tight Highlight Tags, Etymology Arrows, Lassos, Gauges & Myth Debunks**:
   - Place crisp `2px` white vertical or angled elbow leader pins (`SVG stroke-dashoffset` draw-on from a minimal anchor dot) leading directly to shadowed bold text with zero HUD box; add a compact dark-and-amber population badge only when citing discrete headcounts.
   - Link place-name origins with a curved hand-drawn white SVG etymology arrow; isolate islands or subregions with hand-drawn overlapping SVG focus lassos (`amber`, `white`, or `crimson`); quantify extremes with live boxless physical gauges (mercury thermometer, acoustic decibel meter) and crimson circular `X` myth-debunk stamps.
7. **Rapid Field B-Roll, Choropleths & Radar Evidence**: Follow a whip-zoom dive with `3–4` concise real aerial/field proof clips (`0.85–2.2s` each), clean light-neutral data choropleths/heatmaps, or dark-mode traffic/radar visualizations; add quiet `source_credit` attribution when external imagery or archival footage requires it.
8. **Non-Generative Asset Policy**: Produce all cartography, 2D cross-sections, weather/ice animations, gauges, and charts deterministically via MapLibre and procedural HyperFrames HTML/SVG/GSAP alongside real archival or stock B-roll—never generative video synthesis.

---

## Audio, VO & kinetic SFX craft

- **Voiceover pacing**: Crisp, continuous narration (`50–80%` speech density, minimal dead air `<= 4%` silence). Cuts and graphic beats align to narration clauses rather than musical beats.
- **BGM bed**: Quiet, heavy-ducked (`ducking_strength: 0.90`) mysterious, dramatic, or focused ambient bed (`76–136 BPM` normalized) sitting well beneath voiceover; master all deliverables to `-14.0 LUFS` integrated, `<= -1.0 dBTP` true peak (`48 kHz` stereo AAC-LC).
- **Kinetic SFX (`sfx_policy: "kinetic_accents"`)**: Place short, clean `pop`, `ding`, `click`, and `whoosh` accents at **`15–28` hits/min** locked directly (`0 ms` offset) to territory fills, glowing border draws, text/metric callouts, timeline ticks, counters, and transition midpoints.

---

## Rejected chrome

- Dark translucent rounded dashboard/HUD cards (`rgba(..., 0.85–0.92)`), thin cyan/neon outlines, decorative viewfinder corner-bracket KPI boxes (`┌ ┐ └ ┘`), and thick left- or top-accent border strips (`border-left: 4–7px`, `border-top: 4px`) wrapping map labels, charts, or diagrams
- Forced decorative tilt (`-2°` to `-3°`) on text HUD containers or floating mini sepia quote cards with thin middle divider lines (reserve subtle angle solely for white-bordered framed map/photo cards on blueprint surfaces; keep text plates straight `0°`)
- Presentation-style uppercase eyebrow/kicker labels (`PART 02`, `CHAPTER 1`, `TERRITORY SCALE`, `POLITICAL GEOGRAPHY`, `GEOLOGICAL MECHANISM`) stacked above short-form (`9:16`) display titles, charts, or cross-sections (reserve numbered chapter plates strictly for long-form `16:9` `amber_fact_card`)
- Floating short horizontal decorative accent rules positioned above numbers, metrics, or titles (`.metric-rule`, `.outro-rule`) or decorative divider bars between blueprint numbers and titles
- Uniform `power2.out` fade-and-slide-up entrances across every component; animate with purposeful `SVG stroke-dashoffset` draw-on, `clip-path` wipes, 3D perspective flips, or baseline mask reveals
- Third-party basemap attribution watermarks or vendor UI chrome inside master frames
- Unbordered flat neon mud fills lacking crisp exterior coastline rims or terrain texture
- Cartoon character skits, countryball googly-eye memes, and casual angry/smiling emoji stickers over maps (use authoritative circular flag/portrait markers, clean vector icons, or leader pins instead)
- Unmotivated static map holds without camera motion or graphic progression
- Heavy CSS `backdrop-filter` / `filter: blur()` glass cards and SaaS pill watermarks
- Shouty full-width yellow `#FFD60A` fact bars and document/paper walls covering the focal subject
- Isometric factory / money-bag / emoji raster props
- Dual yellow light-beam spears
- Film-strip / viewfinder chrome, film-reel archival frames, false-color thermal grades, and double-exposure faces on contemporary B-roll
