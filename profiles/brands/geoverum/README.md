# Geoverum — Cartographic Documentary Brand Profile

**Geoverum** is a cartographic documentary brand profile for the `vedit` engine across two documentary formats: **`9:16` portrait** (`1080x1920` @ `30 fps`) and **`16:9` landscape** (`1920x1080` / `3840x2160` @ `30 fps`). Both formats pair graded marine-teal satellite cartography, 2D animated mechanism and underwater cross-sections, geospatial vectors, and grounded field B-roll with plain true-centered captions and visual-locked kinetic SFX.

| File | Role |
| :--- | :--- |
| [`brand_style_policy.json`](brand_style_policy.json) | Runtime policy (soft priors, format overrides for `9:16` & `16:9`, hard guardrails, calibration, provenance). |
| [`editorial_playbook.json`](editorial_playbook.json) | Advisory grammar triggers and empirically measured exemplars (not executed by `vedit`). |
| [`directing_idioms.json`](directing_idioms.json) | Executable directing defaults: idiom checks with parameters, automatic-director rules, camera regimes, and the critique rubric (`vedit storyboard`, `vedit critique`). |
| [`DIRECTING.md`](DIRECTING.md) | Story-first directing method: story brief, story shapes, hook mechanisms, clause-level storyboard, colour casting, sync, and the variation contract. Read first. |
| [`CRAFT.md`](CRAFT.md) | Brand visual, typographic, audio/SFX, and cartographic documentary craft rules. |
| [`templates/`](templates/) | Parameterized, aspect-responsive brand templates (`catalog.json` + `components/*.html`). |
| Engine [`DESIGN.md`](../../../DESIGN.md) | Cross-brand motion and layer boundaries. |

---

## Visual & audio identity (summary)

Full craft rules: [`CRAFT.md`](CRAFT.md).

1. **Story-first directing**: Each narration's own question, withheld answer, and ending note determine its structure, hook mechanism, signature image, surface count, colour casting, and ending ([`DIRECTING.md`](DIRECTING.md)); two narrations must not produce the same film shape.
2. **Satellite spine with story-motivated registers (`9:16`)**: Graded marine-teal satellite relief usually carries `70–90%` of runtime as a continuous virtual-camera take; dark vector, blueprint, parchment, cross-section, horizon terrain, aerial ortho, globe, or real-footage registers appear only when the narrative mode changes, with zero generative video.
3. **Map blocks & luminous seams**: `45°` diagonal-hatched terrain blocks and multi-bloc regional fills sealed by crisp `2–3px` white exterior rims, three-layer luminous glowing border/route strokes (outer bloom + mid glow + bright core), `2×2` quad and diagonal white-seamed splits, and high-res urban ortho landmark masks.
4. **Dual-layer typography & plain captions (`y = 70–72%`)**: True-centered (`x = 50%`) 2–4 word sentence-case `Space Grotesk` / `Inter` plain white captions with subtle dark drop shadow, short opacity cross-fades (`~150ms`), and zero default watermark (`watermark_default: false`), paired with axis-aligned in-world map labels and tight color-matched district tags.
5. **Dual-unit, cross-section & split grammar**: White double-headed arrows, T-brackets, and dashed amber corridors (`mi` + `km`, `ft` + `m`), 2D underwater/volcanic/altitude cross-sections (with subtle `NOT TO SCALE` disclaimer when schematic), compact population pin pills, true-scale silhouette overlays, and whip-zoom / split-wipe / soft-iris / 3D card-flip transitions.
6. **Kinetic SFX & heavy-ducked BGM**: Continuous narration-led editing (`50–80%` voice density), quiet ambient/dramatic BGM (`ducking_strength: 0.90`, `76–136 BPM`), and `15–28` visual-locked `pop`/`ding`/`click`/`whoosh` accents per minute (`sfx_policy: "kinetic_accents"`).

---

## Design tokens

| Token Role | Value | Usage |
| :--- | :--- | :--- |
| `ground` | `#03161F` | Abyssal dark surface backing and shadow anchor. |
| `surface_elevated` | `#083847` | Marine deep-teal satellite ocean bed and elevated dark panels. |
| `ink` | `#F4F1EA` | Primary typography, plain captions, and `2–3px` coastline rims. |
| `accent` | `#F5C542` | Routes, dual-unit metrics, UTC/etymology headers, depth splits, counters, `16:9` chapter plates. |
| `secondary_accent` | `#C2412D` | Primary crimson territory fill, pulsing hazard beacons, myth-debunk X, ortho borders. |
| `hydro_accent` | `#7CE0F9` | Meridian/parallel lasers, altitude rulers, waterbodies, and curved open-water labels. |
| `comparison_accent` | `#2E74E6` | Secondary comparative territory tint, elevation zones, and vertical longitude bands. |
| `muted_ink` | `#9DB2BE` | Secondary orientation labels and quiet source credits. |
| `display_family` | `Archivo Black` | Tabular metrics, counters, acronym initials, kinetic portals, and map display callouts. |
| `body_family` | `Space Grotesk, Inter, Montserrat` | Plain captions (`2–4` words), highlight tags, labels, and optional watermark. |
| `title_family` | `Unbounded` | Major display titles and curved basin marks. |
| `serif_family` | `EB Garamond, Playfair Display` | Historical parchment canvases, era stamps, and archival decrees (upright + italic). |
| `mono_family` | `Space Mono` | Technical blueprint rulers, coordinates, and elevation scales. |

---

## Geospatial provenance

Assets are fetched via [`../../../tools/geo-assets/fetch_assets.py`](../../../tools/geo-assets/fetch_assets.py) against [`../../../assets/geo/MANIFEST.json`](../../../assets/geo/MANIFEST.json):

- NASA Blue Marble NG (shaded relief & bathymetry) — Public Domain
- EOX Sentinel-2 cloudless 2016 — CC BY 4.0
- Natural Earth 1:10m — CC0
- Peter Bird `PB2002` plates — ODC-By 1.0; GEM active faults — CC BY-SA 4.0
