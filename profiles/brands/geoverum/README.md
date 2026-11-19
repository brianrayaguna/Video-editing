# Geoverum — Cartographic Documentary Brand Profile

**Geoverum** is a cartographic documentary brand profile for the `vedit` engine across two documentary formats: **`9:16` portrait** (`1080x1920` @ `30 fps`) and **`16:9` landscape** (`1920x1080` / `3840x2160` @ `30 fps`). Both formats pair graded satellite imagery, geospatial vectors, and field B-roll with clean plain centered captions and single-lead cartographic annotations.

| File | Role |
| :--- | :--- |
| [`brand_style_policy.json`](brand_style_policy.json) | Runtime policy (soft priors, format overrides for `9:16` & `16:9`, hard guardrails, calibration). |
| [`editorial_playbook.json`](editorial_playbook.json) | Advisory grammar triggers and exemplars (not executed by `vedit`). |
| [`CRAFT.md`](CRAFT.md) | Brand visual, typographic, and cartographic documentary craft rules. |
| [`templates/`](templates/) | Parameterized, aspect-responsive brand templates (`catalog.json` + `components/*.html`). |
| Engine [`DESIGN.md`](../../../DESIGN.md) | Cross-brand motion and layer boundaries. |

---

## Visual identity (summary)

Full craft rules: [`CRAFT.md`](CRAFT.md).

1. Continuous satellite cartography (`globe` → `mercator` / terrain tilt) paired with grounded live or archival B-roll.
2. Three-tier visual hierarchy: calm abyssal ground, muted orientation context, and one clear focal lead per beat.
3. Unified exterior coastlines with terrain-preserving fills.
4. Plain true-centered (`x = 50%`) 2–3 word Space Grotesk captions (`y ≈ 70%` on `9:16`, lower-third on `16:9`).
5. Optional text-only lowercase `geoverum` watermark (no logo, small, top-right slightly down, disabled by default).
6. Staggered dual-territory compares, tabular metrics, amber `16:9` chapter plates, and quiet source credits.

---

## Design tokens

| Token Role | Value | Usage |
| :--- | :--- | :--- |
| `ground` | `#03161F` | Abyssal base and dark surface backing. |
| `ink` | `#F4F1EA` | Primary typography, captions, and coastline stroke. |
| `accent` | `#F5C542` | Corridors, metrics, `16:9` chapter plates, primary callouts. |
| `secondary_accent` | `#C2412D` | Primary territory fill tint and hazard markers. |
| `hydro_accent` | `#7CE0F9` | Rivers, lakes, and curved open-water labels. |
| `comparison_accent` | `#2E74E6` | Secondary comparative territory tint (staggered). |
| `surface_elevated` | `#0A2230` | Elevated card backing when non-transparent. |
| `muted_ink` | `#9DB2BE` | Secondary labels and quiet source credits. |
| `display_family` | `Archivo Black` | Metrics and callout numerals. |
| `body_family` | `Space Grotesk` | Plain captions, labels, and optional watermark. |
| `title_family` | `Unbounded` | Display titles and curved basin labels. |

---

## Geospatial provenance

Assets are fetched via [`../../../tools/geo-assets/fetch_assets.py`](../../../tools/geo-assets/fetch_assets.py) against [`../../../assets/geo/MANIFEST.json`](../../../assets/geo/MANIFEST.json):

- NASA Blue Marble NG (shaded relief & bathymetry) — Public Domain
- EOX Sentinel-2 cloudless 2016 — CC BY 4.0
- Natural Earth 1:10m — CC0
- Peter Bird `PB2002` plates — ODC-By 1.0; GEM active faults — CC BY-SA 4.0
