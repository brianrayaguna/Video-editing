# Geoverum Proof Cut — `ref_tectonics` First 30 Seconds

**Production path:** wire through EditPlan + `vedit compile` + `vedit cloud render` per [`../MODAL_PRODUCTION_WORKFLOW.md`](../MODAL_PRODUCTION_WORKFLOW.md) §6. `bake_and_render.mjs` is a local PNG/ffmpeg sketch only — not the Modal mastering pipeline.

```text
GOAL:    Rebuild the first 30.0s of reference `ref_tectonics` as a Geoverum vertical
         deliverable: locked basemap timing from the source encode, Geoverum broadcast bug,
         sentence-case caption rail on the measured phrase schedule, source chrome covered,
         and two-pass EBU R128 audio at -14.0 LUFS / <= -1.0 dBTP.
OUTPUT:  1080 x 1920, 30 fps CFR, H.264 High yuv420p bt709, 48 kHz stereo AAC
TIME:    30.0 seconds x 30 fps = 900 frames
LOOK:    Source cartographic bed (scaled); Geoverum meridian bug + wordmark (unboxed);
         caption chips rgba(6,16,22,0.80) / #F4F1EA Space Grotesk 500; abyssal cover patches
         over source watermark and source subtitle chrome.
OBJECTS: 1. Basemap video `assets/basemap-30s.mp4` (900 frames)
         2. Mastered VO `assets/vo-30s.wav`
         3. Geoverum broadcast watermark (lands f3, holds)
         4. Caption rail groups timed to the reference phrase ledger
MOTION:  Basemap camera is inherited frame-for-frame from the source.
         Watermark: opacity 0 -> 0.86 over 6f at t=0.10s, then dead still.
         Captions: hard 1-frame switches; soft 100ms fade on first entrance.
BANNED:  - GEOGRAFYI glyph/wordmark visible in the deliverable
         - Source subtitle chips visible under Geoverum captions
         - Violet/magenta multi-fill remakes (source fills remain in the bed; not re-authored)
         - Karaoke word-pop, SaaS pills, runtime CSS blur
QA:      Contact sheet at f015, f075, f165, f255, f390, f510, f615, f750, f840, f885.
```
