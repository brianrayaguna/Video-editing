# Geoverum Visual & Audio Craft (Layer 1 — Brand DNA)

Permanent art-direction standards for Geoverum across `9:16` portrait (`1080x1920`) and `16:9` landscape (`1920x1080` / `3840x2160`). Exact hex codes, font stacks, pixel sizes, and guardrails live in a single source of truth: [`brand_style_policy.json`](brand_style_policy.json). Story structure and concept divergence live in [`DIRECTING.md`](DIRECTING.md); engine-wide compositing rules live in [`../../../DESIGN.md`](../../../DESIGN.md).

---

## 1. Color Grading & Five Surface Registers

Geoverum is **rich, vivid, and dimensional—never muddy or artificially crushed to black**. Choose only the surfaces required by the episode's narrative modes:

1. **Bathymetric Satellite Relief Spine (Primary, 70–90% of most films)**:
   - Deep marine-teal ocean (`#093B4B`–`#134F5F`) with clearly visible **cyan-turquoise continental shelves** (`#227282`–`#3A8F9D`) and coastal shading.
   - Warm, natural 3D landmass relief: textured olive greens, warm ochre/sand deserts, crisp polar snow, and gentle directional hillshade.
2. **Cobalt Blueprint Backdrop (`#2059DC`)**:
   - Vivid royal-cobalt drafting grid with crisp translucent white coordinate lines (`theme: "cobalt"` or `blueprint_tabletop_frame`) for global rules, tilted 3D map framing, lifted territory cutouts, and true-scale comparisons.
3. **Matte Slate Radar / Traffic Canvas (`#2C3137`–`#3A4047`)**:
   - Neutral matte charcoal ground engineered so dense yellow vehicle swarms, crisp white-rimmed circular zoom loupes, and neon green vs crimson coverage zones read instantaneously.
4. **Daylight 3D Horizon Terrain (`surface_register: "daylight_terrain"`)**:
   - Natural sunlit sky gradient (`#2B7AE4` -> `#A3CEF5`) over bright snow/mountain relief for vertical altitude, barrier, and clearance proofs—never darkened into night mud.
5. **Deep Tactical 2D / Historical Parchment Canvas**:
   - Abyssal slate-teal (`#091E26`) for stylized 2D systems diagrams, full-bleed mechanism cutaways (`cutaway_2d`), and quiet geometric closers; warm sepia parchment (`#B9A386`) with slate ocean (`#5A7D80`) for treaty history and era timelines.

---

## 2. Adaptive Ink, Glow & Territory Styling

Typography and map fills adapt to their underlying luminance and narrative role rather than locking every label to flat white:

| Element | Visual Rule |
| :--- | :--- |
| **Primary light ink** | Crisp snow-white (`palette_roles.ink`) with soft directional drop shadow (`strokeWidth: 0`) over ocean, dark terrain, or slate radar. |
| **Dark ink on bright fills** | Deep charcoal (`#140E0E`, `dark_on_fill` preset) with subtle soft lift whenever bold country/territory labels sit on high-luma crimson or amber fills. |
| **Hero acronyms & offsets** | Vivid editorial yellow (`palette_roles.accent`, `acronym_hero` preset) for system acronyms, UTC/numeric offsets, and single-location highlights. |
| **Atmospheric speed & altitude** | Luminous sky-cyan (`palette_roles.hydro_accent`, `velocity_cyan` italic) for wind speeds, and left-anchored translucent cyan dual-unit altitude chips (`33,000 ft (10,000 m)`) tied to horizontal white T-cap hairlines. |
| **Semantic contrast pairs** | Vivid green (`#4ADE4A`) vs crimson-red (`#EF233C`) for opposing directions, open vs blocked corridors, or faster vs slower legs. |
| **Open-water labels** | Subdued translucent cyan-teal italic `Lora` (`water_subtle` preset) integrated quietly into ocean bathymetry so water names never fight foreground graphics. |
| **Territory fills** | Trace exterior coastlines first; land either a crisp `2–3 px` white-rimmed fill, a **molten crimson fill with bright amber-gold rim glow** for focal hazards/plateaus, or a **full-territory animated waving flag** (`flag_fill`, never small floating rectangular flag pins). |
| **Focus lassos** | Hand-drawn overlapping electric-yellow Bezier ovals (`organic_focus_lasso`), optionally paired with subtle surrounding desaturation. |

---

## 3. Typography & Layout Composition

All font families, sizes, and weights derive from `brand_style_policy.json` (`soft_priors.visual_tokens.typography`):

- **Role separation**: `Montserrat` (`800`–`900`, never `400`!) for hero numerals, acronyms, and map display titles; `Inter` (`500`–`700`) for captions, city labels, and diagram body copy; `Lora` italic for hydrography and archival headers; `IBM Plex Mono` (`600`–`700`) for tabular telemetry and coordinates.
- **Calm, broadcast-scale lower-band captions**: Plain sentence-case `Inter` Bold (`46 px` on `1080x1920`, `42 px` on `1920x1080`), 2–4 words per cue (`12–17 cps`), true horizontal center (`x = 50%`), anchored inside `y = 66%–84%` (`MarginV = 525 px` on `9:16`, `y ≈ 72.7%`), `110 ms` fade-in, `0 ms` hard cut out with `67 ms` gap. Render via the Chromium HTML/CSS strip overlay with a **4-layer soft Gaussian drop shadow** (tight dark contact halo + wide soft ambient falloff, zero pill box, zero harsh black karaoke stroke) so text stays crisp even over bright sunlit snow.
- **Upper-Center Action Stage (`y = 22%–62%`, `x = 8%–92%`)**: Concentrate the single dominant visual signal in the upper-center zone with generous geographic negative space around it. Keep `<= 1.5` competing Tier-1 signals per frame, `<= 3` transient callouts (one in, one out), and zero overlap with the protected caption band.
- **Watermark**: Disabled by default (`watermark_default: false`).

---

## 4. Motion, Camera & Spatial Grounding

- **Continuous, rest-to-rest camera craft**: Keep virtual map cameras smoothly active (`>= 94%` of `0.5 s` windows) with rest-to-rest C² curves (`glide`, `snap_dive`, `hyperbolic_fly`, `orbit_cruise`), zero velocity corners, and crisp sharp map frames (`optical_shutter_blur` off; reserve blur strictly for radial zoom cuts, whip-pans, and brief register-swap transitions). Bake with `--fill-tiles` to prevent mid-move tile pops, and denoise measured camera tracks before baking.
- **3-tier spatial lock**: Declare `map_plane` for ground-locked titles/flags/measurements, `world_billboard` for upright coordinate pins/pointers/sprites, and `screen` strictly for viewport HUDs (altitude rails, odometers, captions).
- **One transition device per jump type**: Match-framed `hard_cut` between contiguous map acts; radial `whip_zoom_blur` (`0.3–0.8 s`) into cutaways or B-roll triplets; 6-frame `disc_sweep` / `feathered_dark_wipe` for match-framed register swaps; `split_wipe_divider` for satellite-vs-dark comparisons.
- **Physicality**: Enter from `scale(0.92–0.96)`, `clip-path` wipes, or `SVG stroke-dashoffset` draw-ons with `expo.out` (`180–360 ms`), never `scale(0)`. Hold landed text dead still. Exit `40–50%` faster with `power3.in`.

---

## 5. Audio, Scoring & Foley (`audio_themes.json`)

- **Clean continuous VO**: Pre-audit dialogue (`vedit inspect-audio`), denoise before transcription, maintain `50–80%` speech density (`<= 4%` silence) over a subtle `-52 dBFS` room-tone floor.
- **Studio BGM & narrative pivot scoring**: Resolve domain-matched real instrumental tracks via `vedit geo auto-audio --brand geoverum` (`audio_themes.json`)—switching through a crisp `250–300 ms` breath into a tension bed at the narrative pivot. Apply vocal pocket carving (`380 Hz` / `2.4 kHz`), heavy sidechain ducking (`ducking_strength: 0.90`), and two-pass linear `loudnorm` to `-14.0 LUFS` / `<= -1.4 dBTP` (`48 kHz` stereo AAC-LC).
- **Recorded kinetic foley**: Sync real recorded pops, clicks, whooshes, paper unfolds, and environmental ambiences `0 ms` to visual actions (`15–28 hits/min`)—never oscillator/sine-wave synthetic audio.

---

## 6. Rejected Chrome (Hard Bans)

- Collapsed `weight: 400` hero/display typography or heavy `3–4 px` black outlines on map labels.
- Dark translucent rounded dashboard/HUD cards, cyan-bordered KPI boxes, viewfinder corner brackets, thick left/top accent strips, floating short accent rule bars, or uppercase eyebrow/kicker headers on `9:16`.
- Forced decorative tilt (`-2°..3°`) on text containers (permitted only on white-bordered photographic/map plates on blueprint grids).
- Small floating rectangular flag pins instead of full-territory waving flag fills.
- Boxed captions, harsh karaoke outlines, third-party basemap attribution chrome, heavy CSS `filter: blur()` / `backdrop-filter`, synthetic sine-wave audio, or generative AI video.
