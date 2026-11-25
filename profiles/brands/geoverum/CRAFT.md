# Geoverum Craft

Brand-specific visual, typographic, storytelling, audio, and cartographic documentary rules across two documentary formats (`9:16` portrait and `16:9` landscape). Engine-wide motion and layer boundaries live in [`../../../DESIGN.md`](../../../DESIGN.md). Runtime pacing, tokens, and guardrails live in [`brand_style_policy.json`](brand_style_policy.json). Story structure, storyboard derivation, and variation rules live in [`DIRECTING.md`](DIRECTING.md); read it first. Advisory directing heuristics and concrete exemplars live in [`editorial_playbook.json`](editorial_playbook.json).

---

## Two documentary formats

Both formats share the same Geoverum cartographic documentary visual DNA and differ in canvas geometry, pacing envelope, transition grammar, and chapter layout:

- **`9:16` (`1080x1920` @ `30 fps`, short documentary)**: Vertical cartographic explainer of roughly 60–100 seconds driven by dense narration (`180–200` words per minute, `<= 4%` silence). Most films run on one dominant surface—graded satellite relief—for `70–90%` of runtime, often as a single continuous virtual-camera take with `0–4` hard cuts per minute, and switch surface only when the narrative mode changes (see [`DIRECTING.md`](DIRECTING.md) §6). Graphic state changes land every `0.25–1.5s` (about one event per stressed noun), the camera is active across `>= 94%` of `0.5s` windows, `min_shot >= 0.75s`, `max_hold <= 45.0s`, and generative video is `0%`.
- **`16:9` (`1920x1080` / `3840x2160` @ `30 fps`, long documentary)**: Landscape documentary alternating cartographic context with archival and live field evidence (`min_shot >= 1.5s`, `max_hold <= 20.0s`).

---

## Storytelling architecture

Structure is derived from each narration, never from a fixed beat timetable. [`DIRECTING.md`](DIRECTING.md) defines the story brief, the repertoire of story shapes and hook mechanisms, the clause-level storyboard method, and the variation contract. Brand-wide invariants that hold for every shape:

1. **Story world at frame `0`**: the first frame is the map, shape, or route the story is about; no intro bumper, title card, or logo sting.
2. **A central question within `3s`**, spoken or performed by the image, and at least one curiosity loop that outlives the hook.
3. **One signature image** that appears in the hook, mutates through the body, and is still on screen, transformed, at the end.
4. **Hinge words change something visible** (mood, register, clean frame, or an executed decision).
5. **No call-to-action, outro plate, or recap**: the film ends on its ending note (irony, consequence, callback, open projection, reversal, measurement, or hard stop on the worst fact) unless the brief requests otherwise.

---

## Basemap surface vocabulary & semantic color system

The surfaces below are a vocabulary. A film uses as many as its narrative modes require—frequently one or two—and switches only when the mode changes (where → satellite, history → parchment, mechanism → cross-section, vertical fact → horizon terrain view). Additional surfaces in the vocabulary:

- **Pale high-key headline map**: flat light-cyan land and sea for a stated headline fact before the camera returns to satellite evidence.
- **Horizon-level 3D terrain view**: oblique or horizon camera over relief with screen-fixed dual-unit altitude chips anchored to horizontal reference lines from the left edge, for altitude, depth, and barrier stories.
- **High-resolution aerial ortho**: for features under a few kilometres (islets, enclaves, villages), reached by dive-zoom.
- **Globe**: for planetary totals and summaries.
- **Flat ground-level illustration**: for atmospheric events seen from the ground (storms, crowds) with a height line.

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
- **Border-trace lemon `#F3FA23` / `#FDFD09`**: the travelling head of a border reveal and a single land-border line on satellite relief; it settles to the white rim once the outline closes.
- **Per-story casting**: The accents above are the default cast. Each film assigns one hue per entity at first mention and keeps it across every surface; flags may serve as fills when nationality is the point; problem and cure, or blocked and permitted, may take opposite hues; one single-use colour may be reserved for the key metric. An opaque saturated pair (lime `#58BC16` / cobalt `#1B5BA8`, `0.9–1.0` alpha, `3 px` white rims) stays legible on busy satellite relief for a two-country contrast. Record the cast in the project storyboard.
- **Grade as emotion**: Warm brown grading may carry a catastrophe sequence and release to full colour on the human-stakes beat; progressive vignette and desaturation may prove darkness or dread at the ending.
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
- **Alignment & Anchor**: True horizontal center (`x = 50%`) using symmetric horizontal margins (`max(left_pct, right_pct)`). On `9:16` (`1080x1920`), render **`Rubik` Bold `56 px`** with `MarginV = 348 px` (`line-height: 1.24`, bottom band `y ≈ 76–82%` inside the protected clearance band `y = 66–84%`, fade-in `120 ms` and hard cut out `0 ms`), matching `brand_style_policy.json` as single source of truth; on `16:9` (`1920x1080` / `3840x2160`), anchor at the lower-third (`bottom ≈ 9.5%`) in `Space Grotesk` / `Inter` / `Montserrat`. When the focal subject must occupy the caption band, move the caption group to a clear band (`y ≈ 20%` or `y ≈ 45%`) for that group only, then return.
- **Proportional Sizing & Transitions**: `56 px` (`Rubik` Bold) on `1080x1920`, `42px` on `1920x1080`, `84px` on `3840x2160`, swapped by a short fade-in (`120–150ms`) and hard cut or `3`-frame dip into the next phrase; never slide or scale. A new phrase lands about every `1.0–1.5 s`.

### Layer B — In-World Cartographic & Diagram Typography

- **Direct Axis-Aligned Map Labels**: Place shadowed bold `Archivo Black` / `Space Grotesk` labels directly on or beside the focal territory, rotating dimension lines and short place labels parallel to the geographic axis (crater walls, borders, island chains, river spans) while keeping Layer A captions strictly horizontal.
- **Tight Color-Matched District Tags**: On dense satellite or dark-vector maps, use tight `0–2px`-radius solid amber, emerald, cobalt, charcoal, or crimson label tags sized strictly to text width directly over the matching hatched polygon—zero borders, zero glass blur, zero oversized cards.
- **Stacked Dual-Unit Counters & Era Markers**: Pair large primary figures with compact stacked secondary units (`700 m / 2300 ft`, `9,537 mi / 15,349 km`, `137 islands and atolls`, `19.9M / 8.5M (42.8%)`), and anchor bold standalone years (`1803`, `1929`, `1971`) or horizontal golden timeline bars directly in the upper safe zone.
- **Bundled Typography Palette (8 local OFL families staged for Chromium & `libass`)**: Every referenced font weight and italic face across these 8 families must be declared via explicit local `@font-face` rules and resolved before frame `0` so text width, line wrapping, and dynamically anchored callouts/pins stay metric-stable:
  - **Display & counters**: `Archivo Black` for tabular distances, years, count-ups, acronym initials, kinetic portal titles, and map callouts; `Unbounded` for major basin marks and hero display titles.
  - **Editorial sans & captions**: `Rubik`, `Space Grotesk`, `Inter`, and `Montserrat` for plain centered captions, highlight tags, sub-labels, and quiet credits.
  - **Historical & archival serif**: `EB Garamond` (upright + italic) and `Playfair Display` for historical parchment plates, era stamps, and archival decrees.
  - **Technical telemetry**: `Space Mono` (regular + bold) for coordinates, elevation ladders, and technical blueprint rulers.

---

## Core motion, transition & storytelling grammar

1. **Continuous Camera Motion (`>= 94%` active)**: Keep virtual map cameras smoothly pushing, pulling, tilting, or tracking across nearly every `0.5s` window using Van Wijk & Nuij `fly_to` arcs or scale-coupled Mercator pans, `C¹` velocity blending across chained moves (`blend_s`), subtle `ambient_drift` during holds, and damped impulse `shake` on verdict stamps. Avoid abrupt velocity corners or unmotivated static holds.
   - *Velocity shapes*: every camera key is a rest point reached at zero velocity. Reframes are bells peaking `30–60 %` into a `1–2 s` move (pans up to about one screen width per second, informational zooms `3–6 log2/s`; `curve: "glide"` or `"orbit_cruise"`). Dives accelerate exponentially to `12–22 log2/s` and end on a cut at peak speed: place the destination key past the act end so the act cuts while the move is still accelerating (`"snap_dive"` or `"whip_snap"`). Snap pull-outs start at peak speed and decay: place the origin key before `t = 0`. Cross-region hops use `"hyperbolic_fly"`; mark `"through": true` only on keys inside one continuous flight.
   - *Crisp frames*: map frames carry no sub-frame shutter blur at any camera speed (`optical_shutter_blur` and `auto_shutter` stay off). Blur belongs only to designed transitions (a radial zoom blur peaking on the cut frame and decaying over `8–14` frames, whip-pans), transient **1-axis directional SVG `<feGaussianBlur>`** (`stdDeviation="0 blurY"` or `"blurX 0"` across `2–4` peak-velocity frames on rapid odometer digit rolls or directional sweeps), brief `0.25–0.42 s` `expo.out` rack-focus entry/exit decays on register swaps, and sprite entrances—returning cleanly to `0` on held frames, with CSS `filter: blur()` and `backdrop-filter` always banned.
   - *No tile pops*: bake with `vedit geo bake-scene --fill-tiles` so no frame is captured on upscaled ancestor tiles; hide an unavoidable imagery-resolution swap inside a fast zoom, a disc sweep, or a dark feathered ellipse around the high-resolution patch.
   - *Measured tracks are denoised before baking*: a camera track solved from reference frames or hand-keyed at irregular times carries small direction flips that monotone interpolation turns into visible shake. Run `vedit geo camera-track <track.json> -o <smoothed.json> --cut <t> --anchor <t>` (Gaussian window `0.6 s`, per-key correction capped at `24 px` and `0.08` zoom so deliberate snap moves keep their timing). Pass every hard cut as `--cut` and every deliberate story-beat framing as `--anchor`.
   - *Shake budget*: shake is measured as direction flips, not as acceleration (a snap zoom is large but one-directional). Accept a baked track with at most one pan flip per `15 s` and one zoom flip per `30 s` of continuous camera; fast moves are always one-directional with eased ends.
   - *Zoom and route width move together*: when a move changes zoom regime, the route stroke eases across the same frames (see *Journey route & overlay scale*), so the line neither pops nor thins mid-move.
   - *Non-map camera continuity (`#cam`)*: wrap full-bleed cross-sections, archival plates, and multi-panel splits in a unified `#cam` container (`perspective: 1400–1600px`) that inherits incoming dive or whip momentum (`expo.out` decay into a flat `0°` hold) and keeps content and callout/pointer layers locked to the same transform during internal pans or zooms.
2. **Luminous Cartographic Typography**: Pair dark contrast grounding with multi-ring `text-shadow` / Canvas shadow halos (`glow_color`, `glow_strength`) on hero place names and route titles so high-energy labels radiate against satellite relief without runtime CSS `filter: blur()`.
3. **Transition Grammar (`9:16`)**:
   - **Continuous Match-Framed Acts (default)**: For multi-act stories sharing the same map world, preserve seamless spatial continuity by matching the outgoing act's final camera coordinates (`center`, `zoom`, `bearing`, `pitch`) to the incoming act's opening frame (`hard_cut` invisible join) instead of inserting decorative wipes or artificial resets. Reserve stylized transitions strictly for genuine scale discontinuities or narrative register shifts:
   - **Radial whip-zoom blur (`0.3–1.0s`)** for regional leaps and plunges into 2D cross-sections or aerial B-roll.
   - **Vertical white-bar split wipe (`0.3–0.6s`)** between satellite relief and dark obsidian vector or blueprint measurement surfaces.
   - **Feathered dark curtain sweep & optical spyglass iris (`0.4–0.7s`)** using pure alpha gradients (zero CSS blur) or circular SVG masks so `y = 66–84%` plain captions remain legible in front.
   - **Oversized kinetic letter portal (`0.5–0.8s`)** scaling bold display lettering cleanly into the next cartographic view, or **3D horizontal card-flip** shifting between flat-map projections and a 3D spherical globe.
   - **Zoom-through icon** from map to diagram, **dip to black** for chapter resets, **page curl** for archive pivots, **wash dissolve** for weather, **colour-flash cut** for hook flips, **lens/iris dissolve** between map level and character level, and **whip into a real aerial** to resolve an abstraction. Keep one device per jump type within a film.
   - **Feathered black-disc sweep (`5–6` frames)**: a soft black disc (`~1000–1300 px`, feather `~15 %` of the width) crosses right to left (`transition_in: "disc_sweep"`, black on roughly `6 %`, `70 %`, `100 %`, `90 %`, `20 %`, `0 %` of the frame across the six frames); swap the basemap register while the frame is fully black, match-frame both sides, and leave captions unmasked.
   - **Projection switch inside a zoom**: continue the zoom through a radial blur that peaks on the cut frame into the other projection (flat map ↔ globe), already framed on the same place: the outgoing act keeps accelerating into the cut (destination key after `duration_s`, `cut_blur_out_s` `0.3–0.45 s`) and the incoming act opens blurred (`cut_blur_in_s` `0.3–0.45 s`).
   - **Clean crossfade (`0.4–0.5s`)** and **hard cuts** for rapid proof bursts. Reserve `amber_light_leak` strictly for `16:9` long-form transitions.
4. **Dual-Unit Dimension Brackets, T-Brackets & Radius Rings**: Stack imperial and metric units (`2.4 mi (3.8 km)`, `50.5 km (31.38 mi)`, `700 m / 2300 ft`) along white double-headed arrows, technical T-bracket callipers, dashed amber corridors, or expanding concentric acoustic/distance radius rings drawn via `SVG stroke-dashoffset`.
5. **Full-Bleed 2D Animated Cross-Sections, Scale Ladders & Longitude Bands**: Reserve full-bleed (`inset: 0`) flat-vector 2D cross-sections (`6–19s`) strictly for subsurface geology, planetary strata, or depth columns that have no surface map representation; whenever an energy, corridor, maritime, or infrastructure topic occurs on earth geography, render it directly on the 3D pitched map using 3D geometry (`cable_3d`, `model_3d`, `volume_3d`) instead of a 2D cartoon cutaway. When a subsurface cutaway applies, pair it with left-anchored altitude/depth ladders and translucent vertical longitude/UTC columns, never enclosing it inside a floating dark dashboard panel.
6. **Quad/Diagonal Multi-Panel, Horizontal Analogy & Demographic Splits**: Disambiguate nested political entities with crisp white-seamed `2×2` quad splits, 2- or 3-panel diagonal splits, or top/bottom analogy splits, and quantify population ratios with boxless 10-figure SVG silhouette grids directly over a soft scrim.
7. **Boxless Coordinate Pins, Tight Highlight Tags, Etymology Arrows, Lassos, Gauges & Myth Debunks**:
   - Place crisp `2px` white vertical or angled elbow leader pins (`SVG stroke-dashoffset` draw-on from a minimal anchor dot) leading directly to shadowed bold text with zero HUD box; add a compact dark-and-amber population badge only when citing discrete headcounts.
   - Link place-name origins with a curved hand-drawn white SVG etymology arrow; isolate islands or subregions with hand-drawn overlapping SVG focus lassos (`amber`, `white`, or `crimson`); quantify extremes with live boxless physical gauges (mercury thermometer, acoustic decibel meter) and crimson circular `X` myth-debunk stamps.
8. **Rapid Field B-Roll, Choropleths & Radar Evidence**: Follow a whip-zoom dive with `3–4` concise real aerial/field proof clips (`0.85–2.2s` each), clean light-neutral data choropleths/heatmaps, or dark-mode traffic/radar visualizations; add quiet `source_credit` attribution when external imagery or archival footage requires it.
9. **Story devices** (selected by story need per [`DIRECTING.md`](DIRECTING.md) §5.3):
   - *Signature-image persistence*: the focal line or shape survives zooms and surface cuts and is re-purposed later (a divider becomes the mechanism's barrier edge).
   - *Count-up measurement*: a dimension arrow whose number counts up and lands on the spoken value, re-proven at each new zoom level.
   - *Live misconception counter*: a large counter that shows a believed number and keeps ticking as ghost shapes appear.
   - *Familiar-silhouette tiling and shape transplant*: tile a familiar country silhouette across a zone, or lift the focal shape and drop it onto a familiar region at true scale.
   - *Full-frame tint flash* (`0.4–0.5s`) on an owning or time-changing verb, with the camera locked.
   - *Mood dip on "why"*: vignette or darkening for the question phrase, answer opened by a whip-zoom.
   - *Edge-grown state mask*: ice, drought, or flood masks growing from the edges over the basemap while borders stay on top.
   - *Particles for invisible qualities*: clouds, snow, wind streaks, turbulence spirals, dust billows tied to the place.
   - *Abstract people markers*: dots or pictograms that converge, change colour on loss, scatter, and return.
   - *Tool action*: a stamp, stylus, or cursor performing the spoken verb on the map. Calibrate `transform-origin` and negative offsets to the active contact hotspot (tip of stylus/cursor or center of stamp), move along curved approach arcs with directional banking (`±6°–16°`), land a brief contact squash synced `0 ms` to the map reaction (border trace, stamp, or debunk mark), match sprite scale across scale-jump handoffs, and sweep out `40–50%` faster than entry.
   - *Repetition marker*: pulse rings repeating at one spot for loops, then a duration numeral.
   - *Travelling avatar*: a portrait marker that rides the route tip; its count matches the companions remaining.
   - *Paired values across a line*: clocks, dates, or owners shown on each side of a thin glowing boundary.
   - *Absence & spatial negation*: Default to physical and spatial proof directly on the 3D map—an unpowered tower grid (`powered: false`), a cable or corridor physically bypassing an excluded port, or a true-meter `volume_3d` architectural prism extending beyond a territory's coastline—so limitation and exclusion are visually self-evident without stamped red `X` graphics. Reserve prohibition marks strictly for literal regulatory bans or closed border blockades.
   - *Real-data credibility*: the same focal outline redrawn over real imagery or a procedurally rebuilt data visualization.
10. **Non-Generative Asset Policy**: Produce all cartography, 2D cross-sections, weather/ice animations, gauges, and charts deterministically via MapLibre and procedural HyperFrames HTML/SVG/GSAP alongside real archival or stock B-roll—never generative video synthesis.

---

## Journey route & overlay scale (`9:16`)

Route-driven films (story shape *Journey chain* in [`DIRECTING.md`](DIRECTING.md) §3) read on a phone only when the route and its markers are drawn at screen-constant, generous sizes. Measured on `1080x1920` frames:

- **Route stroke follows the camera regime, not the map scale**: `4–8 px` on continental and recap shots, `10–16 px` on regional legs, `20–30 px` on close obstacle shots, up to `40 px` on a held close-up of a single event (arrest, crossing point). Ease the width between regimes in step with the zoom so the line never thins to a hairline mid-move. Pure saturated yellow (`#FBEA12`), round joins, no casing.
- **The drawn head is the camera's subject**: the camera keeps the growing route tip inside the middle `60%` of the frame and leads it slightly in the direction of travel; the line never draws off-screen except when a whip-out reveals the full leg.
- **Duration numerals ride the leg they measure**: `2 years`, `6 years`, `11 years`, `32 days` in heavy (optionally italic) white with a soft dark shadow, `60–120 px` cap height, placed along the measured segment and kept close to upright (`|angle| <= 12°`) unless the numeral is set parallel to a straight crossing.
- **Character and icon scale**: travelling portrait avatar `180–240 px` diameter with a `4–6 px` white rim; detention cage or stamp icon `~300 px`; speech bubble `~380 px` wide with `38–48 px` black heavy text; hazard icon clusters (rebels, viruses) `80–140 px` each, popping one per stressed noun. Markers smaller than `~100 px` read as noise at phone scale.
- **Repetition marker**: a forced periodic return ("every 90 days") shows as pulse rings at the exit point, then one solid route dot per return, each dot popping as the head passes it.
- **Obstacle → fill pairing**: each obstacle on the route gets one distinct territory treatment (glowing jungle-green region, edge-grown ice mask, flat national red fill, cyan water body with glow, hatched red/green neighbour pair for "can't go through X or Y"), so no two consecutive obstacles share a colour or texture.
- **Recap globe**: totals are spoken over the whole route on a globe filling `80–90%` of the frame width, with the totals stacked top-centre as solid saturated blue chips with yellow heavy text (`~60 px`). The globe then flies down into the flat map for the remaining leg.
- **Future path**: the not-yet-walked remainder is a dashed white line (`4–6 px`, `10/10` dash) from the current position to a yellow destination label carrying the year.
- **Journey captions**: dense chronological narration over a busy satellite route reads better with a larger plain caption than the default rail: `60–66 px` medium-weight geometric sans, white at `~0.9` opacity paired with a crisp two-layer dark halo (`0 2px 10px rgba(0, 0, 0, 0.88), 0 0 4px rgba(0, 0, 0, 0.92)`) so captions hold `>= 4.5:1` contrast even over bright snow, clouds, desert, or sunlit ocean, bottom edge at `~27%` of frame height. The caption band (`y ≈ 66–76%`) stays free of route heads and callouts.

### Visual hierarchy

Every frame has one reading order, enforced by size, contrast, safe margins, and numeric accuracy:

1. **Route head and the leg being drawn**: the only element allowed to move continuously; highest saturation in frame.
2. **Travelling avatar or event icon** at the head: the human subject of the current clause.
3. **Duration numeral or measurement gauge** on the measured zone: the largest type in frame while present. Spoken figures must never disagree with on-screen callouts (enforce numeric parity and paired dual-unit labels where appropriate).
4. **Place labels and territory fills**: lower contrast than the route; fills sit under the route, never over it.
5. **Caption rail**: screen-fixed, neutral white with a clean dark halo, never competing in colour with the route yellow.

At most **three transient callouts** (avatar, icon cluster, bubble, numeral, gauge) are on screen at once; a new one entering on a stressed word retires the oldest within `0.3 s` (one in, one out). Callouts that belong to a finished leg exit before the camera leaves that leg.

### Layout relative to the route head & safe zones

- Callouts **trail the head**: place them `200–320 px` from the head on the side the route came from (opposite the direction of travel) and slightly above it, so the next `1 s` of route stays visible.
- Keep a `~120 px` clear radius around the head; a callout never overlaps the head or the segment drawn in the next second.
- Keep callout centers inside broadcast safe zones (`8%–92%` horizontal, `12%–88%` vertical) with scale rulers placed center- or bottom-safe (`y >= 12%`) rather than crowded into upper corner margins.
- Numerals sit on the midpoint of the leg they measure, offset `~30–40 px` perpendicular to the line and rotated with it (within the `|angle| <= 12°` rule).
- Speech bubbles point their tail at the speaker and stay inside the upper `60%` of the frame; dashed connector arrows (`~20 px` width, `2:1` dash) link a callout to a remote place instead of moving the callout there.
- Horizontal side margins of `>= 60 px` for every callout; nothing crosses into the caption band.

### Directional corridors, vertical gauges & parchment transitions

- **Wind and atmospheric corridors (`chevron_flow_band`)**: Use staggered animated directional chevrons along a dashed streamline to visualize jet streams, prevailing winds, or corridor deflection over shaded relief maps.
- **Elevation, altitude & geological depth gauges (`cutaway_height_gauge`)**: Pair vertical graduated tick rails inside right/left safe margins (`8%–92%` x) with animated column fills and dual-unit readouts (metric + imperial) locked to narration clauses.
- **Feathered dark sweeps & archival page unfolds**: Use a `3–5` frame feathered dark curtain wipe (`soft_curtain_transition`, `mode: "feathered_dark_wipe"`, default right-to-left) to bridge macro-scale or projection jumps without masking captions, and use an upright `0°` parchment unfold (`historical_parchment_plate`, `variant: "page_unfold"`) when entering archival map history.

---

## World-space & object-tracked overlays

- **Camera-locked 3-tier spatial tracking (`map_plane`, `world_billboard`, `screen`)**: Every graphic element must declare its spatial relationship to the moving 3D camera rather than floating statically at frozen pixel sizes:
  - `map_plane` (MapLibre local projection Jacobian `ctx.transform`): Country/region names, ground flags, territory emblems, and ground measurements lie physically on the map surface, automatically scaling with `zoom`, rotating with `bearing`, and foreshortening with `pitch` using continuous floating-point transform scaling (never integer-rounded font sizes that jitter by `1 px` during smooth zooms).
  - `world_billboard` (world-anchored upright with damped zoom coupling): Vertical coordinate pins, curved hand-drawn pointers, and compact metric pills stay glued to `[lng, lat]` at sub-pixel precision while remaining upright during orbits and scaling smoothly via `2^((zoom - ref_zoom) * scale_coupling)` (`scale_coupling: 0.35–0.50`).
  - `screen`: Strictly viewport-locked HUD elements (odometer counters, vertical dark-void wipers, bottom captions).
  - For HyperFrames overlays composited over pitched map footage, project `[lng, lat]` anchors through the 3D camera track (`project_world_anchor_to_track`) into `OverlayCompositionOp.track_keyframes` with optional `rotateX_deg` and `perspective_px`.
- **3D cinema camera choreography (beyond zoom-only)**: Combine lateral trucking (sideways sweeps), gentle orbital `bearing` rotation (`±8°–18°`), targeted 3D `pitch`, and subtle optical banking (`roll: ±1°–4°` with automatic overscan scaling) so held beats remain alive in 3D space. Use van Wijk & Nuij hyperbolic geodesics (`curve: "hyperbolic_fly"`) for cross-region hops, exponential `snap_dive` curves for landmark approaches, optional low-frequency stabilized-rig `micro_drift`, and rest-to-rest keyframes (zero velocity at each key unless it is marked `"through": true`). Map frames stay crisp at every speed: no sub-frame shutter blur on camera moves (`optical_shutter_blur` off); motion blur belongs only to whip and plunge transitions. Keep dense pin/radar clusters and wide continental reveals upright (`pitch: 0–10°`), reserving deeper oblique tilt (`pitch: 24–52°`) for corridor flyovers, river/isthmus reveals, and dramatic mood-dip vignettes.
- **Territory reveal: trace, then fill**: Introduce a focal territory by drawing its outline along the real perimeter (`border_trace_s` `0.8–2.0 s`, constant world speed): two heads leave the story anchor (a summit, a border point, the northern tip) in opposite directions, bright lemon at `7–8 px` constant screen width with round caps and no glow, cross-fading to a `3–4 px` white rim within `~0.1 s` of closing. Fill only after the outline closes: a flat tint at `0.85–0.95` alpha fading in over `3–6` frames, or a seed-grown radial reveal (`~0.7 s`). Keep relief readable through the tint; drop to `0.48–0.58` translucent fills only where terrain detail is the point. A border shared by two filled countries is one line: draw it with one head along the true polyline, north to south, on top of both fills (dashed with round caps where it continues at sea). Transition fill hue on narrative turns (for example emerald green `#15803D` shifting to crimson `#991B1B` when danger is introduced).
- **Flag fills for ownership**: When nationality is the point, cover the territory with its flag (`flag_fill`): upright and mapped onto the territory bounds, or turned a quarter so its long axis follows a tall territory (`flag_rotate_deg: 90`, `flag_fit: "cover"`); clipped to the coast under a `2–4 px` light rim; revealed by a seed-grown mask with an irregular edge (`flag_reveal: "organic"`, `~0.7 s`), a bottom-up wipe (`wipe_up`, `~0.27 s`), or a `0.33–0.4 s` fade; rendered with `flag_blend: "source-over"` (controlled `flag_alpha`, avoiding murky `multiply` darkening over ocean/forest terrain) and dynamic wind-gust cloth deformation (`flag_wave: 0.15–0.25`, seamless horizontal `flag_wave_warp`, and satin specular sheen `flag_gloss`) so the territory reads like living fabric anchored to the map. A flag may be a territory's first fill and give way to the story's flat cast colour through a second seed-grown reveal (`fill_reveal_mode: "organic"`).
- **3D In-Map Infrastructure & Scale Geometry**: Whenever explaining real-world corridors, subsea cables, power grids, ports, maritime routes, or volumetric capacity over geography, render WebGL 3D geometry directly inside the pitched satellite map coordinate space rather than falling back to 2D cutaways or flat neon strokes:
  - **`cable_3d`**: Procedurally stranded steel-wire and metallic armor `TubeGeometry` with ground/seabed shadow ribbons, animated induction pulse rings, optional overhead tower-to-tower catenary sag (`catenary: true`), clean terminal collars or ground tapers (`landing_collar`, `end_taper_m`), and minimum screen-space thickness so corridors stay physical at any zoom. Route spans between tower/landing coordinates without piercing building roofs.
  - **`model_3d`**: 3D geographic structures (`transmission_tower`, `substation`, `solar_farm`, `survey_vessel`, or verified `.glb`/`.gltf` assets via `gltf_url`) scaled smoothly with zoom coupling, obeying heading alignment along travel paths and explicit `powered` emissive state (`true` vs `false`) to contrast active vs bypassed infrastructure.
  - **`volume_3d`**: True-meter architectural prisms positioned at exact `[lng, lat]` coordinates over graded terrain (`width_m`, `length_m`, `height_m`) to prove area deficits, urban density, or facility footprints geometrically against surrounding landmasses.
- **Spatial hierarchy & calm ground**: Target `<= 1.5` competing Tier-1 visual signals per frame and `>= 85%` calm map/ocean ground. Maintain safe clearance above the protected `9:16` caption band (`y = 66–84%`, plain `Rubik` Bold `56 px` at `MarginV = 348 px`, local WCAG contrast `>= 4.5:1`, no trailing mid-sentence punctuation) and keep all edge-anchored pins/labels inside `6%–94%` horizontal bounds.
- **Atmospheric cutaway triplets**: When plunging from a map into real-world terrain proof, use a radial zoom-blur plunge followed by three rapid atmospheric B-roll cuts (`0.8–1.2 s` each) before pulling back to the satellite spine.
- **Vertical wipe-to-void isolation**: When isolating a territory count or border anomaly from busy satellite terrain, sweep a crisp glowing white vertical wiper bar (`~250–300 ms`) across the frame to dim the basemap to matte charcoal (`#0C0E11`, `0.85–0.90` alpha) while keeping diagonal-hatched or rimmed focal polygons illuminated above the void layer. Pair with a tilted odometer counter (`fly-up ~280 ms`, vertical digit roll `~140 ms`, optionally applying a brief `2–4` frame vertical 1-axis SVG `<feGaussianBlur>` with `stdDeviation="0 blurY"` that decays cleanly to `0` on landing) when debunking a misconception count.
- **Alternating ownership tint-flash & shifting border**: For alternating sovereignty or moving boundary stories, smoothly interpolate the glowing border spline between both alignments (`~500 ms` ease-in-out) while surging a luminous bank-and-island tint flash (`~650 ms` bell curve) on the active territory and anchoring waving SVG flag markers on each side.
- **True-scale ghost silhouette & dual-unit callouts**: To prove microstate or corridor scale, slide a translucent cyan reference silhouette horizontally (`~260 ms` ease-out) directly over the focal landmass after retiring any numeric population pill. Pair dashed distance brackets and micro-border lines with stacked primary metric and parenthesized imperial units (`85 m` / `(279 ft)`).
- **Directional geographic sweeps & demographic splits**: Reveal elongated natural corridors (mountain ranges, rift valleys, coast belts) with world-space directional clips (`north_south` / `west_east`) paired with character-by-character typewriter `map_plane` labels so the sweep stays locked to terrain during bearing rotations. For percentage splits across a glowing meridian or border, animate a 10-figure human silhouette row physically dividing across the line before swapping into compact color-matched population pills.
- **Atmospheric kinematics & spatial deficit proof**: Represent meteorological barriers and wind deflection with multi-puff shaded clouds casting soft ground shadows along `[lng, lat]` spline paths paired with tapered white wind streamlines. For resource, capacity, or spatial deficits, prefer true-scale `volume_3d` prisms, dimmed/unpowered `model_3d` infrastructure, or domain icon sequences directly on terrain; apply two-stage prohibition slashes only when conveying a literal regulatory ban or blocked route.

---

## Audio, VO & kinetic SFX craft

- **Voiceover pacing & pre-ingest audio hygiene**: Inspect raw dialogue (`vedit inspect-audio`) for clipping, low SNR, sub-80 Hz rumble, and plosives prior to denoising; clean crisp continuous narration (`50–80%` speech density, minimal dead air `<= 4%` silence) with `highpass` (`75–120 Hz`) and short splice crossfades (`~12 ms`) over a quiet continuous room-tone floor so pauses never drop to dead zero. Cuts and graphic beats align to narration clauses (with J-cut/L-cut pre-laps and post-laps where dialogue/ambience bridges a cut) rather than rigid musical grid lines.
- **BGM bed & psychoacoustic carving**: Section-adaptive ambient/ostinato or granular bed (`76–136 BPM`, `ducking_strength: 0.90`) carved with multi-band vocal pockets (`380 Hz` low-mid cleanup + `2.4 kHz` presence dip), WPM-adaptive sidechain release (`400 ms` on rapid speech to avoid pumping), balanced stereo reverb returns and subtle precedence widening on non-sub beds, and strategic `180–300 ms` silence drop-outs right before climax impacts; mastered via two-pass linear `loudnorm` to `-14.0 LUFS` integrated (`streaming_web`), `<= -1.0 dBTP` true peak, and `>= +0.15` mono phase correlation (`48 kHz` stereo AAC-LC).
- **Kinetic SFX (`sfx_policy: "kinetic_accents"`) & narrative cues**: Place short, clean `pop`, `ding`, `click`, `stinger`, and Doppler `whoosh` accents at **`15–28` hits/min** (guarding against mechanical clustering above ~`1.5` discrete cues/s) locked directly (`0 ms` offset) to territory fills, glowing border draws, text/metric callouts, timeline ticks, counters, and transition midpoints, supported by transient-aligned 4-layer impacts (`sub` with upper-bass warmth for consumer playback, `body`, `detail`, `tail`), rising pitch cues before dives, and low tension drones under mood dips.

---

## Rejected chrome

- Dark translucent rounded dashboard/HUD cards (`rgba(..., 0.85–0.92)`), thin cyan/neon outlines, decorative viewfinder corner-bracket KPI boxes (`┌ ┐ └ ┘`), and thick left- or top-accent border strips (`border-left: 4–7px`, `border-top: 4px`) wrapping map labels, charts, or diagrams
- Forced decorative tilt (`-2°` to `-3°`) on text HUD containers or floating mini sepia quote cards with thin middle divider lines (reserve subtle angle solely for white-bordered framed map/photo cards on blueprint surfaces; keep text plates straight `0°`)
- Presentation-style uppercase eyebrow/kicker labels (`PART 02`, `CHAPTER 1`, `TERRITORY SCALE`, `POLITICAL GEOGRAPHY`, `GEOLOGICAL MECHANISM`) stacked above short-form (`9:16`) display titles, charts, or cross-sections (reserve numbered chapter plates strictly for long-form `16:9` `amber_fact_card`)
- Floating short horizontal decorative accent rules positioned above numbers, metrics, or titles (`.metric-rule`, `.outro-rule`) or decorative divider bars between blueprint numbers and titles
- Uniform `power2.out` fade-and-slide-up entrances across every component; animate with purposeful `SVG stroke-dashoffset` draw-on, `clip-path` wipes, 3D perspective flips, or baseline mask reveals
- Third-party basemap attribution watermarks or vendor UI chrome inside master frames (rebuild data visualizations such as air-traffic or weather layers procedurally)
- Unbordered flat neon mud fills lacking crisp exterior coastline rims or terrain texture
- Comic elements (characters, flag avatars with faces, reaction faces, speech bubbles, stickers) placed without a narrated action or covering the focal geography; comic register itself is part of the brand vocabulary (see [`DIRECTING.md`](DIRECTING.md) §10)
- Unmotivated static map holds without camera motion or graphic progression
- Heavy CSS `backdrop-filter` / `filter: blur()` glass cards and SaaS pill watermarks
- Shouty full-width yellow `#FFD60A` fact bars and document/paper walls covering the focal subject
- Isometric factory / money-bag raster props (flat vector pictograms and reaction faces tied to a spoken noun or beat are permitted)
- Dual yellow light-beam spears
- Film-strip / viewfinder chrome, film-reel archival frames, false-color thermal grades, and double-exposure faces on contemporary B-roll
