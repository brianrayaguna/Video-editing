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

Active project shot scripts and baked MP4 outputs belong under `VEDIT_PROJECTS_ROOT/<brand_id>/<project_id>/`, never inside this engine directory.

## MapLibre Capture Contract

All continuous or multi-shot MapLibre bakers must adhere to these verified capture knobs:

1. **Fast CDP JPEG capture** (`Page.captureScreenshot` with `format: "jpeg", quality: 92, optimizeForSpeed: true` via `fast_capture.mjs`) — pipe directly to FFmpeg `image2pipe` MJPEG unless `KEEP_FRAMES=1` or boundary post-processing is required.
2. **Tile idle** — fast-path single `requestAnimationFrame` when `map.loaded() && map.areTilesLoaded()` immediately; otherwise poll every ~20 ms up to ~**1500 ms**.
3. **Darwin Chromium** — `["--no-sandbox", "--hide-scrollbars", "--use-gl=angle", "--use-angle=metal"]` (host GPU). Do not force `--use-angle=swiftshader` on macOS hosts.
4. **Linux / CI** — SwiftShader is appropriate (`--use-gl=angle --use-angle=swiftshader`), matching cloud HyperFrames workers.
5. **Parallel workers & resume** — default `WORKERS=2` independent Chromium processes for long (`>= 120` frames) bakes; skip frames that already exist and are >1 KB when writing frame sequences unless `REBAKE=1`.
6. **Encode** — all-intra H.264 (`-g 1 -preset fast`), `yuv420p`, explicit `bt709`, CRF ≈ 16 (`HW_ENCODE=1` opts into `h264_videotoolbox` on macOS).

## Camera Move Presets & Declarative Map Scenes

`camera_presets.json` holds reusable map camera moves (zoom and bearing deltas on normalized progress curves, plus pan modes: `hold`, `drift`, `to_target`, `fly_to`, `path`). A shot is described as a start state plus chained moves; each move starts where the previous ended, and `cut` entries jump state (optionally advancing the timeline with `at_s`).

- `vedit camera list` — show presets, default durations, and purposes (including `cinema_fly_dive`, `whip_plunge_blur`, `impact_settle_shake`, `orbital_vignette_drift`).
- `vedit camera expand --plan-file moves.json -o keys.json` — per-frame `KEYFRAMES_JSON` for `bake_vertical_basemap.mjs` (`--format scene` emits `[t, lng, lat, zoom, bearing]` rows for custom scene players).
- Physics options: `fly_to` (Van Wijk & Nuij optimal zoom-pan trajectory), scale-coupled `to_target` pan (`2^-z` weighting so targets stay centered during deep dives), cross-move `C¹` velocity blending (`blend_s`), damped impulse `shake`, `ambient_drift`, and `optical_shutter_blur` (`shutter_samples` sub-frame accumulation during rapid whip zooms).
- `vedit geo prepare` — fetch AOI satellite tiles, re-grade with marine-teal bathymetry preservation, and extract project-scoped Natural Earth country/admin-1 vectors into `<project>/media/maps/vectors.json` without dirtying tracked engine manifests.
- `vedit geo bake-scene --scene-file plan/map_scene.json -o media/maps` — compile declarative multi-act cartographic scenes (smooth camera trajectories, exterior-dissolved territory polygons with zero internal administrative seams, multi-ring glowing labels, 3-layer glowing routes, pins, radar rings, weather clouds/rain, migrant flow swarms, and blueprint paper mode) directly to `bt709` CFR H.264 MP4 acts.
- Zooms below the viewport-fill limit (world-card shots) need the renderer's camera constraint disabled (MapLibre `transformConstrain` returning the requested center and zoom).

## Caption Typography

Plain captions burned through libass accept optional props on the first `caption_rail` overlay: `caption_font_family`, `caption_font_px`, `caption_bottom_pct`, `caption_bold`, `caption_opacity`, `caption_outline_px`, `caption_shadow_px`, `caption_shadow_opacity`, `caption_shadow_blur_px` (soft blurred shadow layer), `caption_glow_color`, `caption_glow_px` (outer luminous halo layer), `caption_transition_ms` (cross-fade up to `200ms`), and `caption_letter_spacing`. The engine font library (`assets/geo/fonts`) is staged for libass automatically; `fetch_assets.py` derives static `Inter-Bold.ttf` (requires `fonttools`) because libass renders only the default instance of variable fonts.

## Related Docs

- Cloud Modal spine: [`docs/CLOUD_WORKFLOW.md`](../../docs/CLOUD_WORKFLOW.md)
- External project layout: [`docs/PROJECT_WORKSPACE.md`](../../docs/PROJECT_WORKSPACE.md)
- Architecture invariants: [`.agents/rules/editing-system.md`](../../.agents/rules/editing-system.md) §5
- Brand directing playbook: [`.agents/skills/brand-director/SKILL.md`](../../.agents/skills/brand-director/SKILL.md)
