# Geoverum Tectonics 30s — Native Rebuild (`tectonics-30s`)

```text
GOAL:    Rebuild Shot 0 of ref_tectonics (first 30.0s) as a native Geoverum cut:
         clean graded satellite basemap + Geoverum region fills/corridor/LOC/hatch,
         broadcast bug, caption rail, VO — assembled as a verified EditPlan and
         mastered on Modal (`vedit cloud render`), not a source-encode remaster.
OUTPUT:  Hybrid EditPlan → Modal master, 1080 x 1920, 30 fps, bt709, 48 kHz stereo AAC-LC
TIME:    30.0 seconds x 30 fps = 900 frames
LOOK:    ground #03161F; ink #F4F1EA; accent #F5C542; secondary #C2412D;
         dual compare cobalt #2E74E6 then crimson; corridor #D9383A; caption chip
         rgba(6,16,22,0.80) / Space Grotesk 500; Archivo Black metric.
OBJECTS: 1. Continuous MapLibre ME–South Asia camera bed (silent A-roll)
         2. Staggered TR/IN/PK fills + dashed corridor + LOC + Kashmir hatch
         3. Open-water callout chips (not yellow-on-land pills)
         4. Unboxed GEOVERUM meridian bug
         5. Sentence-case caption rail on measured phrase schedule
         6. VO stem mastered to −14 LUFS / ≤ −1.0 dBTP
SHOTS:   Single continuous glide (ASL ≈ 30s / 1 cut), hybrid overlays for chrome.
BANNED:  Source neon/violet multi-fills; GEOGRAFYI chrome; figurative soldiers/drones;
         bake_and_render.mjs as production master; frozen camera holds >0.5s.
QA:      vedit audit on Modal master; contact frames at beat midpoints.
```

## Production path

See [`../MODAL_PRODUCTION_WORKFLOW.md`](../MODAL_PRODUCTION_WORKFLOW.md) and the MapLibre bake contract in [`../../../tools/geo-assets/README.md`](../../../tools/geo-assets/README.md) (JPEG / 1.5s idle / Darwin GPU — same knobs as `render_sulawesi_shots.mjs`).

1. `node bake_tectonics_basemap.mjs` → `assets/basemap-tectonics-30s.mp4` + projected coords
2. `python build_tectonics_30s.py` → verified `edit_plan.json`
3. `vedit compile --lint` → `vedit cloud render` → `vedit audit`

## Beat table

| Time | Signal |
| --- | --- |
| 0.0–1.0s | Globe settle; bug lands @0.10s |
| 1.0–7.0s | Turkey cobalt then India crimson (≥0.65s); corridor + `+4.000 KM` |
| 7.0–12.0s | Hold-drift push toward Pakistan |
| 12.0–15.0s | Single-signal Pakistan crimson |
| 15.0–19.0s | Turkey–Pakistan dual; amber open-water chips |
| 19.0–24.0s | India–Pakistan + dashed LOC |
| 24.0–30.0s | Kashmir amber hatch + abstract UAV glyph; captions through end |

## Deliverable

`renders/geoverum_tectonics_30s_master.mp4`
