# Geoverum Policy Catalog — Reference Calibration

Canonical mapping from calibrated reference films into the Geoverum brand profile.  
Runtime file: [`profiles/brands/geoverum/brand_style_policy.json`](../../../profiles/brands/geoverum/brand_style_policy.json).  
Advisory file: [`profiles/brands/geoverum/editorial_playbook.json`](../../../profiles/brands/geoverum/editorial_playbook.json).  
Craft: [`profiles/brands/geoverum/CRAFT.md`](../../../profiles/brands/geoverum/CRAFT.md).  
Templates: [`profiles/brands/geoverum/templates/catalog.json`](../../../profiles/brands/geoverum/templates/catalog.json).

Source folders use content ids only: `ref-tectonics/`, `ref-ethiopia-toba/`, `ref-batam/`, `ref-png-border/`.

---

## 1. Provenance hashes

| Source id | SHA-256 | Role |
| :--- | :--- | :--- |
| `ref_sulawesi` / tectonics sister | `9a8fcd97…` / `c9ca22bc…` | Short-form continuous cartography |
| `ref_ethiopia_toba` | `0719155d7f16d20cd16819b696657c022d0e2bb4c255fe5d8f6aadf64cbaa686` | Long-form map↔evidence documentary |
| `ref_batam` | `f0d083936286f88bf0db36580e8cebe3bba4aa51f33df07dc45968674adc3530` | Short-form dual-territory + corridor |
| `ref_png_border` | `dd9ae48f8d67452d9bb1ca2aea367c5ed77b65c3e4efa1c876d7c49074d8c802` | Border diagram + archival handoff |

---

## 2. Runtime soft priors (section pacing)

| Section | ASL p25 / p50 / p75 (s) | Cuts / min | Notes |
| :--- | :--- | :--- | :--- |
| hook | `7.5 / 10.067 / 12.0` | `5–8` | Short-form globe dive still primary |
| setup | `4.8 / 6.4 / 8.5` | `6–11` | Admits denser long-form setup |
| body | `2.4 / 3.8 / 6.9` | `6–11` | Calibrated to long-form documentary density |
| escalation | `5.5 / 7.8 / 10.5` | `5.5–9.5` | Hydro / heritage / corridor beats |
| climax | `6.5 / 9.2 / 11.5` | `5.2–8.2` | Evidence / relief reveals |
| outro | `3.7 / 4.633 / 5.8` | `10–16` | Compact settle / CTA |

Continuous short-form glides (~1 cut/min, ASL ≈`23–26s`) remain valid via exemplars `ref_batam_*` and `ref_png_border_*`; the body soft prior is the wide envelope, not a forced cut rate.

---

## 3. Runtime hard bans

| Pattern id | Intent |
| :--- | :--- |
| `violet_generic_accent` | No violet/magenta default fills |
| `simultaneous_multi_neon_fills` | Never two neon territory washes on one still |
| `thematic_3d_map_props` | No volcano/ship/collage 3D props on maps |
| `thematic_emoji_raster_props` | No money-bag / emoji metaphor rasters |
| `isometric_economy_props` | No isometric factory/economy props |
| `dual_light_beam_chrome` | No dual yellow spear beams |
| `vendor_basemap_chrome` | No Landsat/GEBCO/Google stacks in master |
| `document_wall_on_subject` | No full-frame paper/UNESCO walls |
| `shouty_yellow_fact_bar` | No full-width `#FFD60A` shout bars |
| `on_map_calendar_weather_chrome` | No calendar widgets / rain icons on map |
| `false_color_thermal_grade` | No thermal/magenta analysis grade as default |
| `film_reel_archival_frame` | No film-reel rounded archival frames |
| `film_strip_viewfinder_chrome` | No viewfinder / film-strip UI |
| `double_exposure_broll` | No ghosted double-exposure faces |
| `saas_pill_watermark` / `heavy_css_blur_glass` / `scale_zero_pop_in` / `dual_redundant_labels` / `internal_provincial_borders` | Existing engine craft bans |

---

## 4. Adopted grammar (by theme)

| Theme | Adopt | Adapt |
| :--- | :--- | :--- |
| Orientation | Continent→country zoom chain; locator before detail | Remap purple fills to crimson/cobalt |
| Dual territory | Distance metric `±KM`; staggered fills ≥`0.6s` | Never simultaneous neon |
| Maritime / hydro | One amber corridor; hydro cyan lake labels | No ships, no red bloom |
| Borders | Amber geodesic vs hydro meander diagram | Asymmetric tint vs terrain hold |
| Long-form chapters | Numbered amber fact plates; tabular B-roll metrics | Off-landmass plates |
| Evidence | Map → archival/live B-roll; Afar vectors after fill | Clean source cards, not document walls |
| Branding | Aspect-aware unboxed bug (`9:16` top-center; `16:9` top-right) | Never copy source channel mark |

---

## 5. Advisory playbook triggers

| Trigger id | Purpose |
| :--- | :--- |
| `hook_opening_map_dive` | Globe/basin dive + first silhouette |
| `continent_to_country_zoom_chain` | Wide→country→detail |
| `staggered_dual_territory_compare` | Two fills by mention order |
| `dual_territory_distance_metric` | Tabular ±KM in open water |
| `maritime_corridor_draw_on` | Single amber corridor |
| `asymmetric_dual_fill_compare` | Tint vs terrain-preserve |
| `geometric_vs_natural_border_diagram` | Meridian vs river |
| `numbered_fact_card_longform` | Amber chapter plate |
| `hydro_lake_outline_stack` | One hydro lake group |
| `afar_triple_junction_vectors` | Plate vectors after fill |
| `tabular_metric_on_broll` | Elevation / MW metrics |
| `map_to_live_broll_handoff` / `map_to_archival_or_live_broll_handoff` | Clean dissolve / hard cut / amber leak |

These triggers are **not** executed by planner or verifier.

---

## 6. Typed templates

| `template_id` | Composition |
| :--- | :--- |
| `caption_rail` | `studies/geoverum/captions/compositions/caption-rail.html` |
| `broadcast_bug` | `studies/geoverum/branding/compositions/top-bug.html` |
| `distance_metric` | `studies/geoverum/labels-lines/compositions/labels-lines-scene.html` |
| `region_highlight` | `studies/geoverum/region-highlight/compositions/region-highlight-scene.html` |
| `amber_fact_card` | caption-rail `.fact-card` |
| `tabular_metric` | labels-lines scene |

---

## 7. Analysis index

| Document | Source |
| :--- | :--- |
| [`analysis-ref-tectonics.md`](analysis-ref-tectonics.md) / [`frame-ledger-ref-tectonics.md`](frame-ledger-ref-tectonics.md) | `ref-tectonics/` |
| [`analysis-ref-ethiopia-toba.md`](analysis-ref-ethiopia-toba.md) / [`frame-ledger-ref-ethiopia-toba.md`](frame-ledger-ref-ethiopia-toba.md) / [`visual-directing-ledger-ref-ethiopia-toba.md`](visual-directing-ledger-ref-ethiopia-toba.md) | `ref-ethiopia-toba/` |
| [`analysis-ref-batam.md`](analysis-ref-batam.md) / [`frame-ledger-ref-batam.md`](frame-ledger-ref-batam.md) / [`visual-directing-ledger-ref-batam.md`](visual-directing-ledger-ref-batam.md) | `ref-batam/` |
| [`analysis-ref-png-border.md`](analysis-ref-png-border.md) / [`frame-ledger-ref-png-border.md`](frame-ledger-ref-png-border.md) / [`visual-directing-ledger-ref-png-border.md`](visual-directing-ledger-ref-png-border.md) | `ref-png-border/` |
