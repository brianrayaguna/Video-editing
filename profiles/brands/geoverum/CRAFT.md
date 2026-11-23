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
- **Alignment & Anchor**: True horizontal center (`x = 50%`) using symmetric horizontal margins (`max(left_pct, right_pct)`). Anchored at **`y = 70–72%`** on `9:16` and standard lower-third (`bottom ≈ 9.5%`) on `16:9`. When the focal subject must occupy the caption band, move the caption group to a clear band (`y ≈ 20%` or `y ≈ 45%`) for that group only, then return.
- **Proportional Sizing & Transitions**: `36–46px` on `1080x1920` (smaller sizes for dense 5–7 word clauses are acceptable down to `30px` when legibility holds), `42px` on `1920x1080`, `84px` on `3840x2160`, `Space Grotesk` / `Inter` / `Montserrat` `500–600`, `line-height: 1.24`, swapped by a short opacity cross-fade (`120–200ms`, default `150ms`) or a hard swap; never slide or scale. Each phrase fades in over `3–5` frames and leaves with a hard cut or a `3`-frame dip into the next phrase; a new phrase lands about every `1.0–1.5 s`.

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

1. **Continuous Camera Motion (`>= 94%` active)**: Keep virtual map cameras smoothly pushing, pulling, tilting, or tracking across nearly every `0.5s` window using Van Wijk & Nuij `fly_to` arcs or scale-coupled Mercator pans, `C¹` velocity blending across chained moves (`blend_s`), subtle `ambient_drift` during holds, and damped impulse `shake` on verdict stamps. Avoid abrupt velocity corners or unmotivated static holds.
   - *Velocity shapes*: every camera key is a rest point reached at zero velocity. Reframes are bells peaking `30–60 %` into a `1–2 s` move (pans up to about one screen width per second, informational zooms `3–6 log2/s`; `curve: "glide"` or `"orbit_cruise"`). Dives accelerate exponentially to `12–22 log2/s` and end on a cut at peak speed: place the destination key past the act end so the act cuts while the move is still accelerating (`"snap_dive"` or `"whip_snap"`). Snap pull-outs start at peak speed and decay: place the origin key before `t = 0`. Cross-region hops use `"hyperbolic_fly"`; mark `"through": true` only on keys inside one continuous flight.
   - *Crisp frames*: map frames carry no sub-frame shutter blur at any camera speed (`optical_shutter_blur` and `auto_shutter` stay off). Blur belongs only to designed transitions (a radial zoom blur peaking on the cut frame and decaying over `8–14` frames, whip-pans) and to sprite entrances.
   - *No tile pops*: bake with `vedit geo bake-scene --fill-tiles` so no frame is captured on upscaled ancestor tiles; hide an unavoidable imagery-resolution swap inside a fast zoom, a disc sweep, or a dark feathered ellipse around the high-resolution patch.
   - *Measured tracks are denoised before baking*: a camera track solved from reference frames or hand-keyed at irregular times carries small direction flips that monotone interpolation turns into visible shake. Run `vedit geo camera-track <track.json> -o <smoothed.json> --cut <t> --anchor <t>` (Gaussian window `0.6 s`, per-key correction capped at `24 px` and `0.08` zoom so deliberate snap moves keep their timing). Pass every hard cut as `--cut` and every deliberate story-beat framing as `--anchor`.
   - *Shake budget*: shake is measured as direction flips, not as acceleration (a snap zoom is large but one-directional). Accept a baked track with at most one pan flip per `15 s` and one zoom flip per `30 s` of continuous camera; fast moves are always one-directional with eased ends.
   - *Zoom and route width move together*: when a move changes zoom regime, the route stroke eases across the same frames (see *Journey route & overlay scale*), so the line neither pops nor thins mid-move.
2. **Luminous Cartographic Typography**: Pair dark contrast grounding with multi-ring `text-shadow` / Canvas shadow halos (`glow_color`, `glow_strength`) on hero place names and route titles so high-energy labels radiate against satellite relief without runtime CSS `filter: blur()`.
3. **Transition Grammar (`9:16`)**:
   - **Radial whip-zoom blur (`0.3–1.0s`)** for regional leaps and plunges into 2D cross-sections or aerial B-roll.
   - **Vertical white-bar split wipe (`0.3–0.6s`)** between satellite relief and dark obsidian vector or blueprint measurement surfaces.
   - **Feathered dark curtain sweep & optical spyglass iris (`0.4–0.7s`)** using pure alpha gradients (zero CSS blur) or circular SVG masks so `y = 70%` plain captions remain legible in front.
   - **Oversized kinetic letter portal (`0.5–0.8s`)** scaling bold display lettering cleanly into the next cartographic view, or **3D horizontal card-flip** shifting between flat-map projections and a 3D spherical globe.
   - **Zoom-through icon** from map to diagram, **dip to black** for chapter resets, **page curl** for archive pivots, **wash dissolve** for weather, **colour-flash cut** for hook flips, **lens/iris dissolve** between map level and character level, and **whip into a real aerial** to resolve an abstraction. Keep one device per jump type within a film.
   - **Feathered black-disc sweep (`5–6` frames)**: a soft black disc (`~1000–1300 px`, feather `~15 %` of the width) crosses right to left (`transition_in: "disc_sweep"`, black on roughly `6 %`, `70 %`, `100 %`, `90 %`, `20 %`, `0 %` of the frame across the six frames); swap the basemap register while the frame is fully black, match-frame both sides, and leave captions unmasked.
   - **Projection switch inside a zoom**: continue the zoom through a radial blur that peaks on the cut frame into the other projection (flat map ↔ globe), already framed on the same place: the outgoing act keeps accelerating into the cut (destination key after `duration_s`, `cut_blur_out_s` `0.3–0.45 s`) and the incoming act opens blurred (`cut_blur_in_s` `0.3–0.45 s`).
   - **Clean crossfade (`0.4–0.5s`)** and **hard cuts** for rapid proof bursts. Reserve `amber_light_leak` strictly for `16:9` long-form transitions.
4. **Dual-Unit Dimension Brackets, T-Brackets & Radius Rings**: Stack imperial and metric units (`2.4 mi (3.8 km)`, `50.5 km (31.38 mi)`, `700 m / 2300 ft`) along white double-headed arrows, technical T-bracket callipers, dashed amber corridors, or expanding concentric acoustic/distance radius rings drawn via `SVG stroke-dashoffset`.
5. **Full-Bleed 2D Animated Cross-Sections, Scale Ladders & Longitude Bands**: Cut via radial whip-zoom from overhead maps into full-bleed (`inset: 0`) flat-vector 2D cross-sections (`6–19s`: exploded geological strata separating layer-by-layer with curved white arrows, volcanic hotspot plumes, soil/roots, underground mines, underwater trenches, amber vertical split depth comparisons, or monochrome 2D historical ink cutaways), paired with left-anchored altitude/depth ladders and translucent vertical longitude/UTC columns. Never enclose a cross-section inside a floating dark dashboard panel.
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
   - *Tool action*: a stamp, pencil, or cursor performing the spoken verb on the map.
   - *Repetition marker*: pulse rings repeating at one spot for loops, then a duration numeral.
   - *Travelling avatar*: a portrait marker that rides the route tip; its count matches the companions remaining.
   - *Paired values across a line*: clocks, dates, or owners shown on each side of a thin glowing boundary.
   - *Absence icon*: one facility icon with a prohibition mark, then the few real items placed one at a time on a wide shot.
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
- **Journey captions**: dense chronological narration over a busy satellite route reads better with a larger plain caption than the default rail: `60–66 px` medium-weight geometric sans, white at `~0.9` opacity with a soft `2 px / 6 px blur` shadow, bottom edge at `~27%` of frame height. The caption band (`y ≈ 66–76%`) stays free of route heads and callouts.

### Visual hierarchy

Every journey frame has one reading order, enforced by size, contrast, and layer order (top to bottom):

1. **Route head and the leg being drawn**: the only element allowed to move continuously; highest saturation in frame.
2. **Travelling avatar or event icon** at the head: the human subject of the current clause.
3. **Duration numeral or count** on the measured leg: the largest type in frame while present.
4. **Place labels and territory fills**: lower contrast than the route; fills sit under the route, never over it.
5. **Caption rail**: screen-fixed, neutral white, never competing in colour with the route yellow.

At most **three transient callouts** (avatar, icon cluster, bubble, numeral) are on screen at once; a new one entering on a stressed word retires the oldest within `0.3 s` (one in, one out). Callouts that belong to a finished leg exit before the camera leaves that leg.

### Layout relative to the route head

- Callouts **trail the head**: place them `200–320 px` from the head on the side the route came from (opposite the direction of travel) and slightly above it, so the next `1 s` of route stays visible.
- Keep a `~120 px` clear radius around the head; a callout never overlaps the head or the segment drawn in the next second.
- Numerals sit on the midpoint of the leg they measure, offset `~30–40 px` perpendicular to the line and rotated with it (within the `|angle| <= 12°` rule).
- Speech bubbles point their tail at the speaker and stay inside the upper `60%` of the frame; dashed connector arrows (`~20 px` width, `2:1` dash) link a callout to a remote place instead of moving the callout there.
- Horizontal side margins of `>= 60 px` for every callout; nothing crosses into the caption band.

---

## World-space & object-tracked overlays

- **Camera-locked 3-tier spatial tracking (`map_plane`, `world_billboard`, `screen`)**: Every graphic element must declare its spatial relationship to the moving 3D camera rather than floating statically at frozen pixel sizes:
  - `map_plane` (MapLibre local projection Jacobian `ctx.transform`): Country/region names, ground flags, territory emblems, and ground measurements lie physically on the map surface, automatically scaling with `zoom`, rotating with `bearing`, and foreshortening with `pitch` using continuous floating-point transform scaling (never integer-rounded font sizes that jitter by `1 px` during smooth zooms).
  - `world_billboard` (world-anchored upright with damped zoom coupling): Vertical coordinate pins, curved hand-drawn pointers, and compact metric pills stay glued to `[lng, lat]` at sub-pixel precision while remaining upright during orbits and scaling smoothly via `2^((zoom - ref_zoom) * scale_coupling)` (`scale_coupling: 0.35–0.50`).
  - `screen`: Strictly viewport-locked HUD elements (odometer counters, vertical dark-void wipers, bottom captions).
  - For HyperFrames overlays composited over pitched map footage, project `[lng, lat]` anchors through the 3D camera track (`project_world_anchor_to_track`) into `OverlayCompositionOp.track_keyframes` with optional `rotateX_deg` and `perspective_px`.
- **3D cinema camera choreography (beyond zoom-only)**: Combine lateral trucking (sideways sweeps), gentle orbital `bearing` rotation (`±8°–18°`), targeted 3D `pitch`, and subtle optical banking (`roll: ±1°–4°` with automatic overscan scaling) so held beats remain alive in 3D space. Use van Wijk & Nuij hyperbolic geodesics (`curve: "hyperbolic_fly"`) for cross-region hops, exponential `snap_dive` curves for landmark approaches, optional low-frequency stabilized-rig `micro_drift`, and rest-to-rest keyframes (zero velocity at each key unless it is marked `"through": true`). Map frames stay crisp at every speed: no sub-frame shutter blur on camera moves (`optical_shutter_blur` off); motion blur belongs only to whip and plunge transitions. Keep dense pin/radar clusters and wide continental reveals upright (`pitch: 0–10°`), reserving deeper oblique tilt (`pitch: 24–52°`) for corridor flyovers, river/isthmus reveals, and dramatic mood-dip vignettes.
- **Territory reveal: trace, then fill**: Introduce a focal territory by drawing its outline along the real perimeter (`border_trace_s` `0.8–2.0 s`, constant world speed): two heads leave the story anchor (a summit, a border point, the northern tip) in opposite directions, bright lemon at `7–8 px` constant screen width with round caps and no glow, cross-fading to a `3–4 px` white rim within `~0.1 s` of closing. Fill only after the outline closes: a flat tint at `0.85–0.95` alpha fading in over `3–6` frames, or a seed-grown radial reveal (`~0.7 s`). Keep relief readable through the tint; drop to `0.48–0.58` translucent fills only where terrain detail is the point. A border shared by two filled countries is one line: draw it with one head along the true polyline, north to south, on top of both fills (dashed with round caps where it continues at sea). Transition fill hue on narrative turns (for example emerald green `#15803D` shifting to crimson `#991B1B` when danger is introduced).
- **Flag fills for ownership**: When nationality is the point, cover the territory with its flag (`flag_fill`): upright and mapped onto the territory bounds, or turned a quarter so its long axis follows a tall territory (`flag_rotate_deg: 90`, `flag_fit: "cover"`); clipped to the coast under a `2–4 px` light rim; revealed by a seed-grown mask with an irregular edge (`flag_reveal: "organic"`, `~0.7 s`), a bottom-up wipe (`wipe_up`, `~0.27 s`), or a `0.33–0.4 s` fade; blended with the terrain on satellite relief and opaque on flat plates; a gentle cloth ripple (`flag_wave` `0.15–0.25`) keeps a held flag alive. A flag may be a territory's first fill and give way to the story's flat cast colour through a second seed-grown reveal (`fill_reveal_mode: "organic"`).
- **Spatial hierarchy & calm ground**: Target `<= 1.5` competing Tier-1 visual signals per frame and `>= 85%` calm map/ocean ground. Maintain a `2.2–2.5x` display-to-caption height ratio (`display ~6.5–7.0%` of frame height vs. boxless `1-row` captions at `~3.0–3.5%` / `~68 px` on `1080×1920`, `y = 69–72%`, local WCAG contrast `>= 4.5:1`, no trailing mid-sentence punctuation).
- **Atmospheric cutaway triplets**: When plunging from a map into real-world terrain proof, use a radial zoom-blur plunge followed by three rapid atmospheric B-roll cuts (`0.8–1.2 s` each) before pulling back to the satellite spine.
- **Vertical wipe-to-void isolation**: When isolating a territory count or border anomaly from busy satellite terrain, sweep a crisp glowing white vertical wiper bar (`~250–300 ms`) across the frame to dim the basemap to matte charcoal (`#0C0E11`, `0.85–0.90` alpha) while keeping diagonal-hatched or rimmed focal polygons illuminated above the void layer. Pair with a tilted odometer counter (`fly-up ~280 ms`, vertical digit roll `~140 ms`) when debunking a misconception count.
- **Alternating ownership tint-flash & shifting border**: For alternating sovereignty or moving boundary stories, smoothly interpolate the glowing border spline between both alignments (`~500 ms` ease-in-out) while surging a luminous bank-and-island tint flash (`~650 ms` bell curve) on the active territory and anchoring waving SVG flag markers on each side.
- **True-scale ghost silhouette & dual-unit callouts**: To prove microstate or corridor scale, slide a translucent cyan reference silhouette horizontally (`~260 ms` ease-out) directly over the focal landmass after retiring any numeric population pill. Pair dashed distance brackets and micro-border lines with stacked primary metric and parenthesized imperial units (`85 m` / `(279 ft)`).
- **Directional geographic sweeps & demographic splits**: Reveal elongated natural corridors (mountain ranges, rift valleys, coast belts) with world-space directional clips (`north_south` / `west_east`) paired with character-by-character typewriter `map_plane` labels so the sweep stays locked to terrain during bearing rotations. For percentage splits across a glowing meridian or border, animate a 10-figure human silhouette row physically dividing across the line before swapping into compact color-matched population pills.
- **Atmospheric kinematics & two-stage prohibition pins**: Represent meteorological barriers and wind deflection with multi-puff shaded clouds casting soft ground shadows along `[lng, lat]` spline paths paired with tapered white wind streamlines. For environmental or agricultural deficits, stagger teardrop map pins that pop the positive domain icon first (`~260 ms` spring) and draw a crimson prohibition ring and slash `~350 ms` later.

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
- Third-party basemap attribution watermarks or vendor UI chrome inside master frames (rebuild data visualizations such as air-traffic or weather layers procedurally)
- Unbordered flat neon mud fills lacking crisp exterior coastline rims or terrain texture
- Comic elements (characters, flag avatars with faces, reaction faces, speech bubbles, stickers) placed without a narrated action or covering the focal geography; comic register itself is part of the brand vocabulary (see [`DIRECTING.md`](DIRECTING.md) §10)
- Unmotivated static map holds without camera motion or graphic progression
- Heavy CSS `backdrop-filter` / `filter: blur()` glass cards and SaaS pill watermarks
- Shouty full-width yellow `#FFD60A` fact bars and document/paper walls covering the focal subject
- Isometric factory / money-bag raster props (flat vector pictograms and reaction faces tied to a spoken noun or beat are permitted)
- Dual yellow light-beam spears
- Film-strip / viewfinder chrome, film-reel archival frames, false-color thermal grades, and double-exposure faces on contemporary B-roll
