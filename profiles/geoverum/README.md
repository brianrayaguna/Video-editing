# Geoverum — Cartographic Documentary Brand Profile

**Geoverum** is a short-form (`9:16`, `1080x1920` @ `30 fps`) and long-form (`16:9`) cartographic documentary brand profile built on the `vedit` directing and mastering engine. It pairs empirical satellite imagery and tectonic vector data with single-signal cartographic annotations and word-synchronized Indonesian voiceover narration.

---

## 1. Visual & Editorial Identity

Geoverum adapts the pacing and spatial storytelling grammar of high-retention geographic explainers while enforcing the anti-slop rules defined in [`../../DESIGN.md`](../../DESIGN.md):

1. **Continuous Camera Choreography**: Scenes play across a continuous virtual satellite camera (`globe` projection at space scale `z1.8–z4.5` transitioning smoothly to `mercator` / 3D terrain tilt `pitch 20°–42°` at regional and local scales `z5.8–z10.5`).
2. **90–95% Neutral Canvas**: Deep abyssal ocean (`#03161F`) and natural satellite relief carry the frame. Each narrative beat introduces **at most one focal color signal** ("Say it once").
3. **Terrain-Preserving Landmass Highlights**: Highlighted islands or countries are rendered using a unified exterior coastline (`sulawesi_outline` without internal provincial seams), blending deep crimson-terracotta (`#8E1B1B`) over the satellite relief (`mix-blend-mode: multiply` + subtle inner/outer coastal rim) so mountain chains and valleys remain visible.
4. **Unboxed Broadcast Bug**: The top-center watermark uses a clean monochrome geometric compass/meridian emblem and plain typographic wordmark (`GEOVERUM`) at `82%` opacity—never a pill container or glowing status dot.
5. **Zero-Collision Annotations**:
   - **Callouts** (`SESAR PALU-KORO`, country labels) sit in calm open water or margin areas outside the focal landmass, connected by a crisp pointer or `1.5px` leader stopping `4–6px` from the feature.
   - **Hydrographic Labels** (`TELUK TOMINI`, `TELUK TOLO`, `TELUK BONE`) appear only on close-up shots (`z >= 7.4`) along a smooth curved `<textPath>` with `>= 24px` shoreline clearance.

---

## 2. Design Tokens

| Token Role | Value | Usage |
| :--- | :--- | :--- |
| `ground` | `#03161F` | Deep abyssal ocean base and dark card/caption backing (`rgba(3, 22, 31, 0.82)`). |
| `ink` | `#F4F1EA` | Warm bone-white primary typography and exterior coastline stroke. |
| `accent` | `#F5C542` | Signal amber for primary fault traces, active distance lines, and primary callout badges (`#03161F` ink on `#F5C542`). |
| `secondary_accent` | `#C2412D` | Terracotta-crimson for landmass silhouette tinting and tectonic impact markers. |
| `hydro_accent` | `#7CE0F9` | High-legibility cyan reserved strictly for close-up curved waterbody `<textPath>` labels over dark water. |
| `display_family` | `Archivo Black` | Cartographic callout badges and metric callouts (`+4.000 KM`). |
| `body_family` | `Space Grotesk` | Narrative caption rail (`500` weight, `sentence` case, `3–6` words per group, `tabular-nums`). |
| `title_family` | `Unbounded` | Broadcast wordmark and curved hydrographic basin labels (`700–800` weight). |

---

## 3. Open Geospatial Asset Provenance

All raster and vector assets consumed by Geoverum compositions are fetched and verified via [`../../tools/geo-assets/fetch_assets.py`](../../tools/geo-assets/fetch_assets.py) against [`../../assets/geo/MANIFEST.json`](../../assets/geo/MANIFEST.json):

- **Global Satellite & Bathymetry (`z0–z4`)**: NASA Blue Marble: Next Generation (Shaded Relief & Bathymetry), *Public Domain*.
- **Regional & Local Cloudless Imagery (`z0–z11`)**: EOX Sentinel-2 cloudless 2016 (`s2cloudless_3857`), *Creative Commons Attribution 4.0 (CC BY 4.0)* — commercially safe with attribution.
- **Cultural & Physical Boundaries**: Natural Earth 1:10m, *Public Domain (CC0)*.
- **Tectonic Plates & Active Faults**: Peter Bird (2003) `PB2002` (*ODC-By 1.0*) and GEM Global Active Faults Database (*CC BY-SA 4.0*).
