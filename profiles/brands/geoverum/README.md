# Geoverum — Cartographic Documentary Brand Profile

**Geoverum** is a cartographic documentary brand profile for the `vedit` engine across two documentary formats: **`9:16` portrait** (`1080x1920` @ `30 fps`) and **`16:9` landscape** (`1920x1080` / `3840x2160` @ `30 fps`). Both formats pair graded marine-teal satellite cartography, 2D animated mechanism and underwater cross-sections, geospatial vectors, and grounded field B-roll with plain true-centered captions and visual-locked kinetic SFX.

| File | Role |
| :--- | :--- |
| [`brand_style_policy.json`](brand_style_policy.json) | Runtime policy (soft priors, format overrides for `9:16` & `16:9`, hard guardrails, calibration, provenance). |
| [`editorial_playbook.json`](editorial_playbook.json) | Advisory grammar triggers and empirically measured exemplars (not executed by `vedit`). |
| [`CRAFT.md`](CRAFT.md) | Brand visual, typographic, audio/SFX, and cartographic documentary craft rules. |
| [`templates/`](templates/) | Parameterized, aspect-responsive brand templates (`catalog.json` + `components/*.html`). |
| Engine [`DESIGN.md`](../../../DESIGN.md) | Cross-brand motion and layer boundaries. |

---

## Visual & audio identity (summary)

Full craft rules: [`CRAFT.md`](CRAFT.md).

1. **Production mix (`9:16`)**: Continuous 2.5D/3D satellite and parchment cartography (~80%) paired with full-bleed 2D animated mechanism and geological/underwater cross-sections (~10%), rapid aerial/field proof B-roll (~5%), vector choropleths and multi-panel splits (~3%), and dark-mode radar visualizations (~2%), with zero generative video.
2. **Marine-teal basemap & domain modes**: Deep marine teal satellite ocean (`#083847`–`#154957`) over abyssal `#03161F` dark surfaces, shifting to blueprint tabletop (`#14427A`) for concept/area cards and sepia parchment (`#B9A386`) for historical context.
3. **Rimmed territory comparisons**: Unified exterior coastlines with `2–3px` white rims and terrain-preserving multiply or diagonal-hatched fills, staggered in narration mention order.
4. **Plain centered captions (`y = 70%`)**: True-centered (`x = 50%`) 2–4 word sentence-case `Space Grotesk` / `Inter` plain white captions with subtle dark drop shadow, 1-frame hard cuts (`<= 33ms`), and zero default watermark (`watermark_default: false`).
5. **Dual-unit, cross-section & split grammar**: White double-headed arrows and dashed amber brackets (`mi` + `km`, `ft` + `m`), 2D underwater/altitude depth splits, diagonal 2- or 3-panel splits, compact population pin pills, true-scale silhouette overlays, and whip-zoom / split-wipe / soft-iris / 3D card-flip transitions.
6. **Kinetic SFX & heavy-ducked BGM**: Continuous narration-led editing, quiet ambient/dramatic BGM (`ducking_strength: 0.90`, `76–135 BPM`), and `15–28` visual-locked `pop`/`ding`/`click`/`whoosh` accents per minute (`sfx_policy: "kinetic_accents"`).

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
