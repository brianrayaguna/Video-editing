# Geo Assets — Offline Cartography Bake Contract

This directory owns reusable geospatial asset fetchers, tile grading scripts, the offline XYZ tile server, and generic MapLibre -> MP4 A-roll capture helpers.

## System Split

| Stage | Where It Runs | Canonical Entry |
| --- | --- | --- |
| Tile fetch / grade | Host / Cache | `vedit geo prepare` (`--hq` auto-enabled for `z >= 13`, `build_tiles.mjs`, `fetch_dem_tiles.mjs`) |
| Tile serve | Offline HTTP | `serve_tiles.mjs` (`/tiles_hybrid/*.jpg`, `/tiles_hq/*.jpg`, `/tiles/*.jpg`, `/dem/*.png`, `/vector/*`, `/fonts/*`) |
| MapLibre A-roll & world-space scenes | Project-scoped baker | `vedit geo validate-scene`, `vedit geo bake-scene` (`render_map_scene.mjs`), `vedit geo build-captions`, `vedit geo mix-audio` |
| HyperFrames overlays + hybrid master | Local or **Modal Cloud** | `vedit compile` -> `vedit cloud render` |
| Loudness / visual QC | Modal worker + local re-audit | `vedit audit` |
| Brand component studies | Host | `study_runner.mjs` (shared helpers to serve, lint, render, and encode standalone template studies with contact sheets) |

`/tiles_hq` and `/tiles_hybrid` fill a missing tile from whichever set (`tiles_hq/` or graded `tiles/`) holds the nearest ancestor, so an exact graded tile is never replaced by an upscaled aerial tile; aerial wins ties. `/tiles_hybrid` ignores aerial tiles below `z = 12`. Tile-source selection tests: `node --test tools/geo-assets/serve_tiles.test.mjs`.

## Open Imagery Sources

Every tile source is open-licensed; credit the sources used in the on-screen credit line.

| Set | Source | License | Native detail |
| --- | --- | --- | --- |
| `raw/tiles_s2_2016/` -> graded `tiles/` | Sentinel-2 cloudless 2016 (EOX IT Services GmbH; modified Copernicus Sentinel data 2016) | CC BY 4.0 | `~10 m` (`z14`) |
| `tiles_hq/` | National orthoimagery (U.S. Geological Survey, The National Map) where covered, otherwise Sentinel-2 cloudless 2016 | Public domain / CC BY 4.0 | `~1 m` to `z16` / `z14` |
| `dem/` | Terrarium elevation tiles (open terrain tiles; SRTM, GMTED, ETOPO1 and regional sources) | Open data, attribution per source | varies |
| `raw/tiles_bmng/` | NASA Blue Marble: Next Generation | Public domain | `z0–4` |

`--hq` stores no tile deeper than a source's native zoom; the server upsamples the nearest stored ancestor.

Active project shot scripts and baked MP4 outputs belong under `VEDIT_PROJECTS_ROOT/<brand_id>/<project_id>/`, never inside this engine directory.

## Reusable Asset Library

`assets/geo/` is a shared, episode-independent library served by `serve_tiles.mjs` at `/<path>`. Project-specific geometry and plates belong in the project (`<project>/media/maps/`), never here. `LIBRARY.json` lists what is installed (paths, file counts, bytes, licenses).

| Path | Content | Built by |
| --- | --- | --- |
| `tiles/`, `tiles_hq/`, `dem/` | Graded satellite, high-resolution, and elevation XYZ tiles | `vedit geo prepare`, `build_tiles.mjs`, `fetch_dem_tiles.mjs` |
| `raw/vector/*.{geojson,json}` | Natural Earth 1:10m layers (countries, subdivisions, rivers, lakes, coastline, land, ocean, bathymetry bands, boundaries, disputed areas, time zones, places, urban areas, roads, railroads, ports, airports, reefs, glaciers), tectonic plates, active faults | `fetch_assets.py`, `fetch_library_pack.py` |
| `vector/` | Curated shared vectors | hand-curated |
| `svg/countries/<iso2>.svg` | Country silhouettes (`fill="currentColor"`) | `fetch_library_pack.py` |
| `svg/subdivisions/<iso2>/<slug>.svg` | First-level subdivision silhouettes for the requested countries | `fetch_library_pack.py --subdivisions id,my,...` |
| `svg/world.svg` | Equirectangular world map, one `<path id="<iso2>">` per country | `fetch_library_pack.py` |
| `flags/<iso2>.svg` (`4x3/`, `1x1/`) | Country flags | `fetch_assets.py`, `fetch_library_pack.py` |
| `icons/<name>.svg` | Stroke icon set | `fetch_assets.py`, `fetch_lightweight_pack.py`, `fetch_library_pack.py` |
| `fonts/`, `textures/`, `vendor/` | Curated 38-family open-license font library (`Display`, `Sans`, `Serif`, `Mono`, `Handwriting`), paper and grain textures, pinned runtimes | `vedit geo fetch-fonts` (`fetch_fonts.py`), `fetch_assets.py`, `fetch_lightweight_pack.py` |

Silhouettes use a cosine-latitude equirectangular projection, so they read as shapes, not as measurable maps; use MapLibre scenes for anything to scale. Natural Earth subdivisions follow its release boundaries and may lag recent administrative splits.

## MapLibre Capture Contract

All continuous or multi-shot MapLibre bakers must adhere to these verified capture knobs:

1. **Fast CDP JPEG capture** (`Page.captureScreenshot` with `format: "jpeg", quality: 92, optimizeForSpeed: true` via `fast_capture.mjs`) — pipe directly to FFmpeg `image2pipe` MJPEG unless `KEEP_FRAMES=1` or boundary post-processing is required.
2. **Tile idle** — fast-path single `requestAnimationFrame` when `map.loaded() && map.areTilesLoaded()` immediately; otherwise poll every ~20 ms up to ~**1500 ms** (`render_map_scene.mjs`: up to **6000 ms** per frame, logging how many frames were captured with tiles still pending — a non-zero count means the act needs `--fill-tiles` or a `geo prepare` pass).
3. **Darwin Chromium** — `["--no-sandbox", "--hide-scrollbars", "--use-gl=angle", "--use-angle=metal"]` (host GPU). Do not force `--use-angle=swiftshader` on macOS hosts.
4. **Linux / CI** — SwiftShader is appropriate (`--use-gl=angle --use-angle=swiftshader`), matching cloud HyperFrames workers.
5. **Parallel workers & resume** — default `WORKERS=2` independent Chromium processes for long (`>= 120` frames) bakes; skip frames that already exist and are >1 KB when writing frame sequences unless `REBAKE=1`.
6. **Encode** — all-intra H.264 (`-g 1 -preset fast`), `yuv420p`, explicit `bt709`, CRF ≈ 16 (`HW_ENCODE=1` opts into `h264_videotoolbox` on macOS).

## Camera Move Presets & Declarative Map Scenes

`camera_presets.json` holds reusable map camera moves (zoom and bearing deltas on normalized progress curves, plus pan modes: `hold`, `drift`, `to_target`, `fly_to`, `path`). A shot is described as a start state plus chained moves; each move starts where the previous ended, and `cut` entries jump state (optionally advancing the timeline with `at_s`).

- `vedit camera list` — show presets, default durations, and purposes (including `cinema_fly_dive`, `whip_plunge_blur`, `impact_settle_shake`, `orbital_vignette_drift`).
- `vedit camera expand --plan-file moves.json -o keys.json` — per-frame `KEYFRAMES_JSON` for `bake_vertical_basemap.mjs` (`--format scene` emits `[t, lng, lat, zoom, bearing]` rows for custom scene players).
- Physics options: `fly_to` (Van Wijk & Nuij optimal zoom-pan trajectory), scale-coupled `to_target` pan (`2^-z` weighting so targets stay centered during deep dives), cross-move `C¹` velocity blending (`blend_s`), damped impulse `shake`, `ambient_drift`, and opt-in `optical_shutter_blur: true` (`shutter_samples` sub-frame accumulation; off by default so every frame stays crisp).
- `vedit geo prepare` — fetch AOI satellite tiles, re-grade with marine-teal bathymetry preservation, and extract project-scoped Natural Earth country/admin-1 vectors into `<project>/media/maps/vectors.json` without dirtying tracked engine manifests.
- `vedit geo bake-scene --scene-file plan/map_scene.json -o media/maps` — compile declarative multi-act cartographic scenes (smooth camera trajectories, exterior-dissolved territory polygons with zero internal administrative seams, multi-ring glowing labels, 3-layer glowing routes, pins, radar rings, weather clouds/rain, migrant flow swarms, and blueprint paper mode) directly to `bt709` CFR H.264 MP4 acts.
- `vedit geo bake-scene --fill-tiles` — first runs a coverage pass over every expanded camera track (`render_map_scene.mjs --coverage-out <file>`), lists tiles that would be served from an upscaled ancestor or not at all, fetches and grades them through the source each route serves, then bakes. The report is `{"tiles": [[z, x, y], ...], "by_route": {"tiles": [...], "tiles_hq": [...], "tiles_hybrid": [...]}}`: `/tiles` gaps are listed up to the Sentinel-2 native zoom (z14) and fetched from Sentinel-2 only; `/tiles_hq` and `/tiles_hybrid` gaps are listed up to z16 and fetched high-resolution from z13. The printed summary reports `coverage_unfillable`, the tiles no open source supplied (for example z15–16 outside the orthoimagery coverage); those frames still upscale an ancestor. `vedit geo prepare --tile-list <file>` fetches the `tiles` list of the same report on its own. High-resolution tiles on the `hybrid` route receive the same documentary grade as the graded library, so mixed-zoom frames match in colour.
- Zooms below the viewport-fill limit (world-card shots) need the renderer's camera constraint disabled (MapLibre `transformConstrain` returning the requested center and zoom).

### Camera Keyframe Timing

`camera_keyframes` are rest-to-rest by default: the camera reaches every key with zero velocity, and each segment follows a C² beta velocity profile chosen by the arriving key's `curve` (`glide` symmetric; `snap_dive` peaks early for dives; `whip_snap` short and steep; `hyperbolic_fly` for van Wijk–Nuij zoom-out/zoom-in hops; `orbit_cruise` broad). A key marked `"through": true` keeps the camera moving: consecutive through keys form one monotone cubic Hermite run, eased as a whole between the surrounding rest keys. Hops wider than ~0.35 viewport widths use the van Wijk–Nuij path automatically. `camera_smooth_s` (Gaussian smoothing) and `auto_shutter` default to off.

### Cut-Accent Zoom Blur

Every frame stays crisp except at an act's cuts. `cut_blur_in_s` and `cut_blur_out_s` add a radial zoom blur around the frame centre that peaks on the act's first and last frame and falls off quadratically to zero over the given window (0.25–0.45 s reads as a cut accent). `cut_blur_strength` (default `0.12`, max `0.4`) is the extra scale of the outermost of 12 averaged copies. Pair a destination key placed after `duration_s` (the dive is still accelerating at the cut) with `cut_blur_out_s`, and the next act's opening with `cut_blur_in_s`, to carry a zoom through a hard cut or a projection switch. `validate-scene` rejects negative or non-numeric windows and strengths above `0.4`, and warns when the two windows together exceed the act.

### Territory Trace, Flag Fill, and Route Draw-On

Polygon layers (exterior rim only, no internal seams):

| Key | Meaning |
|---|---|
| `border_trace_s`, `border_trace_delay_s` | Draw the rim along the perimeter over this duration; every exterior and hole ring closes at the same moment, so the finished trace of a single Polygon or MultiPolygon equals its static rim. A feature list, FeatureCollection or seam-dissolved region traces each part from its own start and grows in fragments (`vedit geo validate-scene` warns); trace one country outline or use `border_draw_s` for those. |
| `border_trace_heads` | `2` (default): two heads leave the start vertex in opposite directions; `1`: one head. |
| `border_trace_start`, `border_trace_dir` | Start point `[lng, lat]` (nearest vertex; default the northernmost) and walk direction `cw` / `ccw`. |
| `border_trace_ease` | `linear` (constant speed, default), `in_out`, `out`. |
| `border_trace_hex`, `border_trace_width`, `border_trace_settle_s` | Trace colour and width, cross-faded to `rim_hex` / `rim_width` over the settle time after the trace closes. |
| `border_trace_head_glow` | Opt-in glow dot at each head. |
| `fill_delay_s`, `fill_draw_s` | Fill timing; a traced layer fills when the trace closes, over 0.15 s unless set. |
| `fill_reveal_mode`, `fill_reveal_origin` | `fade`, `radial` (soft disc grown from the origin `[lng, lat]`, default the centre of the territory bounds), `organic` (a feathered seed with an irregular, creeping edge grown from the same origin), or a feathered linear wipe named for its travel direction (`wipe_right`, `wipe_left`, `wipe_down`, `wipe_up` — `wipe_up` rises from the bottom edge). |
| `fill_reveal_roughness`, `fill_reveal_seed` | Edge irregularity of the `organic` reveal (`0`–`0.6`, default `0.22`; `0` is a plain disc) and the seed that fixes its shape. |
| `flag_fill` | Flag code (`assets/geo/flags/<code>.svg`) clipped to the territory; a missing asset fails `validate-scene` and falls back to the colour fill when validation is skipped. |
| `flag_fit`, `flag_rotate_deg` | `stretch` (flag design mapped onto the territory bounds, default) or `cover`; rotation, rounded to the nearest quarter turn. |
| `flag_reveal`, `flag_alpha`, `flag_blend` | Reveal mode (as `fill_reveal_mode`), opacity, and `normal` / `multiply` / `overlay` / `soft-light` / `screen` blending with the terrain. |
| `flag_wave`, `flag_wave_speed`, `flag_wave_cycles`, `flag_wave_angle_deg` | Cloth shading on the flag: highlight and shadow bands (`true` = amplitude `0.22`, max `0.6`) that scroll across the territory at `flag_wave_speed` cycles per second (default `0.5`), `flag_wave_cycles` bands across the bounds diagonal (default `2.5`), tilted `flag_wave_angle_deg` from horizontal (default `20`). |

Route layers draw on over `draw_duration_s` (default 0.9 s) after `draw_delay_s`, eased by `draw_ease` (`out` default, `in_out`, `linear`); `instant: true` skips the draw. `width_ref_zoom` makes line width follow the map scale (doubling per zoom level above the reference, scaled by `width_coupling`, clamped to `width_min_scale`–`width_max_scale` × `width`).

## Caption Typography

Plain captions burned through libass accept optional props on the first `caption_rail` overlay: `caption_font_family`, `caption_font_px`, `caption_bottom_pct`, `caption_bold`, `caption_opacity`, `caption_outline_px`, `caption_shadow_px`, `caption_shadow_opacity`, `caption_shadow_blur_px` (soft blurred shadow layer), `caption_glow_color`, `caption_glow_px` (outer luminous halo layer), `caption_transition_ms` (symmetric cross-fade up to `200ms`), `caption_fade_in_ms` / `caption_fade_out_ms` (asymmetric fade-in / fade-out up to `200ms`, `0` for hard cut), and `caption_letter_spacing`. The engine font library (`assets/geo/fonts`) holds 38 open-license families across `display`, `sans`, `serif`, `mono`, and `handwriting` categories managed via `vedit geo list-fonts` and `vedit geo fetch-fonts` (`fetch_fonts.py`), and is staged automatically for HyperFrames, MapLibre `render_map_scene.mjs`, and FFmpeg `libass` (static weights derived from variable fonts when `fonttools` is available).

## Related Docs

- Cloud Modal spine: [`docs/CLOUD_WORKFLOW.md`](../../docs/CLOUD_WORKFLOW.md)
- External project layout: [`docs/PROJECT_WORKSPACE.md`](../../docs/PROJECT_WORKSPACE.md)
- Architecture invariants: [`.agents/rules/editing-system.md`](../../.agents/rules/editing-system.md) §5
- Brand directing playbook: [`.agents/skills/brand-director/SKILL.md`](../../.agents/skills/brand-director/SKILL.md)
