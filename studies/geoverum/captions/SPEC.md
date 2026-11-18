# Geoverum Captions — Narrative Caption Rail & Cadence (`captions`)

```text
GOAL:    Verify Geoverum's narrative caption rail (typography, single-line chip geometry, WCAG AAA
         >= 7:1 contrast, 76% vertical placement inside Shorts safe zones, sentence casing,
         punctuation discipline, and frame-accurate hard-switch cadence against spoken Indonesian
         voiceover) over 12.0 seconds (360 frames @ 30 fps) at 1080x1920.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps, with mastered 48 kHz stereo AAC voiceover (-14.0 LUFS)
TIME:    12.0 seconds x 30 fps = 360 frames (9 spoken phrase groups)
LOOK:    caption chip surface: rgba(6, 16, 22, 0.76) (no border, 5px corner radius, 10px 20px padding);
         caption ink: #F4F1EA (warm bone white, contrast ratio 12.8:1 against chip surface);
         caption font: Space Grotesk 500, 32px, line-height 1.25, tracking -0.01em, sentence case,
                       white-space: nowrap, tabular-nums;
         vertical anchor: center at y = 1458px (75.9% of 1920px height, clearing the 14% bottom
                          Shorts/Reels UI safe zone at y = 1651px by 193px).
OBJECTS: 1. Continuous 12.0s satellite camera basemap (`#basemap-video`)
         2. Dedicated captions sub-composition (`data-track-kind="captions"`, `compositions/caption-rail.html`)
            holding 9 timed `.clip` phrase groups (`#cap-01` .. `#cap-09`)
         3. Broadcast watermark (`compositions/broadcast-layer.html`)
         4. Synchronized Indonesian voiceover track (`#vo-main`, 12.0s mastered to -14.0 LUFS)
MOTION:  Consecutive phrase switches (f51, f84, f127, f155, f193, f246, f349): instant 1-frame hard cut
         (zero bounce or slide-up fatigue on running subtitles);
         Initial phrase entrance (f007) & post-breath re-entry (f304): 3-frame (100ms) opacity 0 -> 1
         on cubic-bezier(0.23, 1, 0.32, 1);
         Sentence breath pause (f297-f304, 9.90s-10.13s): 7-frame clean visual silence matching speech pause.
SHOTS:   f007-f051 (0.233s-1.700s, 1.467s, 4 words): "Kalau lihat peta, Sulawesi"
         f051-f084 (1.700s-2.800s, 1.100s, 4 words): "tampak seperti huruf K"
         f084-f127 (2.800s-4.233s, 1.433s, 4 words): "yang patah atau gurita"
         f127-f155 (4.233s-5.167s, 0.933s, 3 words): "yang salah posisi."
         f155-f193 (5.167s-6.433s, 1.267s, 4 words): "Bentuk aneh ini bukan"
         f193-f246 (6.433s-8.200s, 1.767s, 4 words): "kebetulan, melainkan hasil tabrakan"
         f246-f297 (8.200s-9.900s, 1.700s, 4 words): "geologi selama jutaan tahun."
         [f297-f304 (9.900s-10.133s, 0.233s): inter-sentence breath gap — no caption on screen]
         f304-f349 (10.133s-11.633s, 1.500s, 4 words): "Sulawesi punya empat semenanjung"
         f349-f360 (11.633s-12.000s, 0.367s, 4 words): "panjang yang menjulur ke"
BANNED:  - Colored borders around subtitle chips
         - All-caps or title-case running subtitles
         - Word-by-word bouncy karaoke pop/scale on documentary narration
         - Two caption groups visible on the same frame
         - Misspelled Indonesian words (corrected reference typo "semenajung" -> "semenanjung")
         - Shouty full-width yellow all-caps bars covering the focal subject

LONGFORM (16:9 optional fact card, not a running subtitle):
         Amber plate `#F5C542` + ink `#03161F`, Space Grotesk/Archivo Black, form `NN. Judul fakta singkat`,
         lower-third safe, one card per chapter beat, opacity fade 100–180ms; never simultaneous with
         the narrative caption rail on the same frame ("Say it once").
QA:      Verify all 9 caption groups on contact sheet (f025, f065, f105, f140, f175, f220, f270, f300 gap, f325, f355);
         confirm p50 group duration = 1.43s (within target 0.95s-1.45s), WCAG contrast >= 11:1,
         and EBU R128 integrated loudness -14.0 +/- 0.5 LUFS.
```

---

## Choreography Table (`choreograph` Skill Format)

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Narrative Caption Groups (`#cap-01` .. `#cap-09`) | **Lead** | `233ms` (`f7`) | `933ms–1767ms` per group | Instant hard-cut on consecutive words; `100ms` fade on breath boundaries (`f7`, `f297`, `f304`) | Locked to voiceover word timestamps |
| Satellite Camera Basemap (`#basemap-video`) | **Support** | `0ms` (`f0`) | `12000ms` (`360f`) | Continuous 7-beat camera trajectory | Spatial context behind caption rail |
| Broadcast Watermark (`#watermark`) | **Decoration** | `100ms` (`f3`) | `200ms` (`6f`) | `opacity: 0 -> 0.86`, then dead still | Upper safe zone anchor |
| Footer Attribution (`#credit`) | **Static** | `0ms` (`f0`) | `12000ms` (`360f`) | Static (`opacity: 0.40`) | Bottom margin metadata |
