# Geo Assets — Offline Cartography Bake Contract

This directory owns reusable geospatial asset fetchers, tile grading scripts, the offline XYZ tile server, and generic MapLibre -> MP4 A-roll capture helpers.

## System Split

| Stage | Where It Runs | Canonical Entry |
| --- | --- | --- |
| Tile fetch / grade | Host / Cache | `fetch_assets.py` (with optional `--aoi-config <json>`), `build_tiles.mjs`, `fetch_dem_tiles.mjs` (Terrarium DEM) |
| Tile serve | Offline HTTP | `serve_tiles.mjs` (`/tiles/*.jpg` + `/dem/*.png` + `/vector/*` + `/fonts/*`) |
| MapLibre A-roll bake | Project-scoped baker | `bake_vertical_basemap.mjs` + `fast_capture.mjs` (writes into external project `media/maps/`) |
| HyperFrames overlays + hybrid master | Local or **Modal Cloud** | `vedit compile` -> `vedit cloud render` |
| Loudness / visual QC | Modal worker + local re-audit | `vedit audit` |
| Brand component studies | Host | `study_runner.mjs` (shared helpers to serve, lint, render, and encode standalone template studies with contact sheets) |

Active project shot scripts and baked MP4 outputs belong under `VEDIT_PROJECTS_ROOT/<brand_id>/<project_id>/`, never inside this engine directory.

## MapLibre Capture Contract

All continuous or multi-shot MapLibre bakers must adhere to these verified capture knobs:

1. **Fast CDP JPEG capture** (`Page.captureScreenshot` with `format: "jpeg", quality: 92, optimizeForSpeed: true` via `fast_capture.mjs`) — pipe directly to FFmpeg `image2pipe` MJPEG unless `KEEP_FRAMES=1` or boundary post-processing is required.
2. **Tile idle** — fast-path single `requestAnimationFrame` when `map.loaded() && map.areTilesLoaded()` immediately; otherwise poll every ~20 ms up to ~**1500 ms**.
3. **Darwin Chromium** — `["--no-sandbox", "--hide-scrollbars", "--use-gl=angle", "--use-angle=metal"]` (host GPU). Do not force `--use-angle=swiftshader` on macOS hosts.
4. **Linux / CI** — SwiftShader is appropriate (`--use-gl=angle --use-angle=swiftshader`), matching cloud HyperFrames workers.
5. **Parallel workers & resume** — default `WORKERS=2` independent Chromium processes for long (`>= 120` frames) bakes; skip frames that already exist and are >1 KB when writing frame sequences unless `REBAKE=1`.
6. **Encode** — all-intra H.264 (`-g 1 -preset fast`), `yuv420p`, explicit `bt709`, CRF ≈ 16 (`HW_ENCODE=1` opts into `h264_videotoolbox` on macOS).

## Related Docs

- Cloud Modal spine: [`docs/CLOUD_WORKFLOW.md`](../../docs/CLOUD_WORKFLOW.md)
- External project layout: [`docs/PROJECT_WORKSPACE.md`](../../docs/PROJECT_WORKSPACE.md)
- Architecture invariants: [`.agents/rules/editing-system.md`](../../.agents/rules/editing-system.md) §5
- Brand directing playbook: [`.agents/skills/brand-director/SKILL.md`](../../.agents/skills/brand-director/SKILL.md)
