# Geo Assets — Offline Cartography Bake Contract

This directory owns graded satellite tiles, curated vectors, the local XYZ tile server, and MapLibre → MP4 A-roll bakers for Geoverum (and other brands using the same stack).

## System split (read this first)

| Stage | Where it runs | Canonical entry |
| --- | --- | --- |
| Tile fetch / grade | Local | `fetch_assets.py`, `build_tiles.mjs` |
| Tile serve | Local | `serve_tiles.mjs` |
| **MapLibre A-roll bake** (camera + fills) | **Local only** | Production-proven: `render_sulawesi_shots.mjs`; shared continuous helper: `bake_vertical_basemap.mjs` |
| HyperFrames overlays + hybrid master | Local dry-run or **Modal** | `vedit compile` → `vedit cloud render` |
| Loudness / QC | Modal worker + local re-audit | `vedit audit` |

Modal never replaces MapLibre basemap baking. Upload finished silent A-roll MP4s as `AssetRef` video, then overlay captions/bug via EditPlan.

## Production-proven MapLibre bake knobs

Authoritative reference implementation: **`render_sulawesi_shots.mjs`** (used by `studies/geoverum/pilot-sulawesi`).

Any new continuous or multi-shot MapLibre baker **must** match these knobs unless a SPEC explicitly requires otherwise:

1. **JPEG intermediates** (`type: "jpeg", quality: 92`) — not PNG frame dumps (~2–3 MB/frame at 1080×1920).
2. **Tile idle** — poll every ~20 ms, timeout ~**1500 ms**, then double `requestAnimationFrame`.
3. **Darwin Chromium** — `["--no-sandbox", "--hide-scrollbars", "--use-gl=angle"]` (host GPU). Do **not** force `--use-angle=swiftshader` on macOS directing hosts.
4. **Linux / CI** — SwiftShader is appropriate (`--use-gl=angle --use-angle=swiftshader`), matching cloud HyperFrames workers.
5. **Resume** — skip frames that already exist and are >1 KB unless `REBAKE=1`.
6. **Encode** — all-intra H.264 (`-g 1`), `yuv420p`, explicit `bt709`, CRF ≈ 16.

Shared helper `bake_vertical_basemap.mjs` must stay aligned with this contract so study scripts that call it inherit the proven path.

## When to use which baker

| Need | Use |
| --- | --- |
| Multi-shot documentary beds with fills (pilot) | `render_sulawesi_shots.mjs` |
| Single continuous camera trajectory (camera-moves, tectonics A-roll) | `bake_vertical_basemap.mjs` **or** a study baker that copies its knobs + `render_sulawesi_shots` GL/JPEG/idle contract |
| One still plate + GSAP camera-rig (region-highlight) | MapLibre once → JPEG plate; animate in HyperFrames (no per-frame MapLibre) |
| Labels / projected SVG at discrete poses | Plate bake + `project` extract (see `labels-lines`) |

## Anti-patterns

- Copying an older PNG + 9 s `__waitIdle` + forced SwiftShader-on-Darwin loop for long bakes
- Treating `studies/*/bake_and_render.mjs` overlay remasters of reference encodes as production masters
- Assuming Modal will bake MapLibre satellite beds

## Related

- Production Modal spine: `studies/geoverum/MODAL_PRODUCTION_WORKFLOW.md`
- Architecture invariants: `.agents/rules/editing-system.md` §4b
- Brand directing playbook: `.agents/skills/brand-director/SKILL.md`
