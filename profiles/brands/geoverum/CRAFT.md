# Geoverum Craft

Brand-specific visual, typographic, and cartographic rules. Engine-wide motion and layer boundaries live in [`../../../DESIGN.md`](../../../DESIGN.md). Runtime pacing and guardrails live in [`brand_style_policy.json`](brand_style_policy.json). Advisory directing heuristics live in [`editorial_playbook.json`](editorial_playbook.json).

---

## Surfaces and hierarchy

- **90–95% neutral canvas**: abyssal ocean `#03161F` and natural satellite relief. One saturated focal signal per beat.
- Do not stack competing fills, fault grids, and multi-region labels in one still.
- No violet or lavender accents (`OKLCH` hue `270°–330°`).
- Dissolve internal administrative seams into a single exterior coastline before highlighting landmasses. Preserve terrain relief inside fills (build-time grade or multiply blend), not opaque pastel washes.

## Broadcast mark

- Unboxed wordmark or meridian emblem + wordmark in the upper safe zone at roughly `78–86%` opacity.
- `9:16`: top-center mark. `16:9`: compact top-right mark (wordmark optional).
- No pill containers, glowing status dots, film-strip chrome, or corner sticker clusters.

## Annotations

- Callouts sit in open water or quiet margins—never on the focal landmass or fault they explain.
- Keep `>= 12px` clearance (`>= 24px` preferred at 1080p portrait) from coastlines and neighboring labels.
- Hydrographic labels (`TELUK TOMINI`, `TELUK BONE`, `TELUK TOLO`) only when zoom provides open-water clearance for a curved `<textPath>` (`z >= 7.2`, shoreline clearance `>= 24px`).
- Leaders are `1.5–2px` and stop `4–6px` short of the target.
- Rely on contrast (`>= 7:1` primary, `>= 4.5:1` minimum), not decorative colored borders.

## Typography

- Caption rail: sentence case, `3–6` words per group, clause/pause breaks `>= 150ms`, center near `76%` frame height on `1080x1920`, dark backing `rgba(3, 22, 31, 0.78)`, ink `#F4F1EA`, Space Grotesk `500–600`.
- Feature badges: amber `#F5C542` or bone `#F4F1EA` on `#03161F` ink, Archivo Black / bold geometric sans.
- Tabular numerals for metrics and coordinates.

## Dual-entity and long-form grammar

- Comparing two territories: stagger fills (`>= 0.6s`), crimson / cobalt / amber—never simultaneous multi-neon fills.
- Asymmetric compare (sovereignty vs neighbor): one terrain-preserving tint plus one quieter terrain hold is allowed after stagger; do not paint both sides neon.
- Distance metrics (`±20 KM`): Archivo Black tabular numerals in open water between territories, never on land interiors.
- Maritime corridors: one amber stroke-dash path per beat; no red bloom, no dual light-beam spears, no cargo-ship or other 3D route props.
- Border anomalies: pair an amber geodesic/meridian stroke with a hydro meander only when narration contrasts political vs natural boundaries.
- Long-form chapter plates: numbered amber `#F5C542` surface + `#03161F` ink in lower-third safe band; never shouty full-width yellow bars.
- Tabular metrics on live B-roll (`1.500 M`, megawatt / elevation callouts): Archivo Black numerals with `>= 12px` clearance from the subject silhouette.
- Hydro lake outlines and rift-lake name stacks: `hydro_accent` `#7CE0F9` only when open-water clearance allows; one lake group per beat.
- Afar / triple-junction beats: staggered plate vectors and labels-lines after a single territory fill—not a second neon wash on the same still.
- Long-form zoom chain: continent or basin wide → single country/region fill → optional detail push, then map ↔ ground evidence loops.
- Map → archival or live B-roll: hard cut, clean crossfade, or amber light-leak; no double-exposure faces; no vendor basemap chrome in frame.
- `16:9` broadcast bug stays top-right and unboxed for the full runtime; do not add a second center watermark.

## Rejected chrome

- Violet / magenta default country washes
- Simultaneous multi-neon neighbor fills
- Thematic 3D map props (volcanoes, ships, collage inserts)
- Shouty full-width yellow `#FFD60A` fact bars
- Document / UNESCO walls covering the focal subject
- Isometric factory / money-bag / regulation raster props
- Dual yellow light-beam spears
- Vendor basemap attribution stacks inside the master frame
- ALL-CAPS land labels covering the focal landmass
- Film-strip / viewfinder chrome and corner sticker clusters
- On-map calendar widgets, rain-cloud icons, equator gimmick strokes
- False-color thermal / magenta analysis grades as default look
- Film-reel archival frames and red-circle evidence stickers
- Double-exposure faces on contemporary B-roll
