# Geoverum — Cartographic Documentary Brand Profile

**Geoverum** is a short-form (`9:16`, `1080x1920` @ `30 fps`) and long-form (`16:9`) cartographic documentary brand profile for the `vedit` engine. It pairs satellite imagery and tectonic vectors with single-signal cartographic annotations and word-synchronized Indonesian voiceover.

| File | Role |
| :--- | :--- |
| [`brand_style_policy.json`](brand_style_policy.json) | Runtime policy (soft priors, hard guardrails, calibration). |
| [`editorial_playbook.json`](editorial_playbook.json) | Advisory grammar triggers and exemplars (not executed by `vedit`). |
| [`CRAFT.md`](CRAFT.md) | Brand visual and cartographic craft rules. |
| [`templates/`](templates/) | Typed brand templates (locked compositions + variables). |
| Calibration catalog | [`studies/geoverum/reference-calibration/applied-policy-deltas.md`](../../../studies/geoverum/reference-calibration/applied-policy-deltas.md) |
| Engine [`DESIGN.md`](../../../DESIGN.md) | Cross-brand motion and layer boundaries. |

---

## Visual identity (summary)

Full craft rules: [`CRAFT.md`](CRAFT.md).

1. Continuous virtual satellite camera (`globe` → `mercator` / terrain tilt).
2. 90–95% neutral canvas; one focal color signal per beat.
3. Unified exterior coastlines with terrain-preserving fills.
4. Unboxed, aspect-aware broadcast mark.
5. Zero-collision annotations and scale-matched hydrographic labels.
6. Staggered dual-territory compares; amber long-form fact cards; map ↔ live B-roll handoffs.

---

## Design tokens

| Token Role | Value | Usage |
| :--- | :--- | :--- |
| `ground` | `#03161F` | Abyssal base and dark caption backing. |
| `ink` | `#F4F1EA` | Primary typography and coastline stroke. |
| `accent` | `#F5C542` | Fault traces, metrics, primary callouts. |
| `secondary_accent` | `#C2412D` | Landmass silhouette tint and impact markers. |
| `hydro_accent` | `#7CE0F9` | Close-up curved waterbody labels only. |
| `display_family` | `Archivo Black` | Callout badges and metrics. |
| `body_family` | `Space Grotesk` | Caption rail. |
| `title_family` | `Unbounded` | Wordmark and curved basin labels. |

---

## Geospatial provenance

Assets are fetched via [`../../../tools/geo-assets/fetch_assets.py`](../../../tools/geo-assets/fetch_assets.py) against [`../../../assets/geo/MANIFEST.json`](../../../assets/geo/MANIFEST.json):

- NASA Blue Marble NG (shaded relief & bathymetry) — Public Domain
- EOX Sentinel-2 cloudless 2016 — CC BY 4.0
- Natural Earth 1:10m — CC0
- Peter Bird `PB2002` plates — ODC-By 1.0; GEM active faults — CC BY-SA 4.0
