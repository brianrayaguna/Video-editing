# Analysis — `ref_tectonics`

| Field | Value |
| :--- | :--- |
| Source id | `ref_tectonics` |
| SHA-256 | `c9ca22bcb18c2756947fa21796e1bc270dbb78a0872fcf6fa08342d554c4a8b6` |
| Container | `480×854`, `30 fps` CFR, `bt709`, `65.267s`, `1958` frames |
| Probe | [`ref-tectonics/probe.json`](ref-tectonics/probe.json) |
| Frame ledger | [`frame-ledger-ref-tectonics.md`](frame-ledger-ref-tectonics.md) |
| Samples | [`ref-tectonics/craft-samples/`](ref-tectonics/craft-samples/), [`event-frames/`](ref-tectonics/event-frames/), [`contact/`](ref-tectonics/contact/) |

The source channel watermark reads GEOGRAFYI. Geoverum treats the clip as an empirical reference only; glyph and wordmark are not copied.

---

## 1. Telemetry

| Metric | Measured | Geoverum implication |
| :--- | :--- | :--- |
| Shot count | 2 (`0–33.8s`, `33.8–65.267s`) | Exemplar bank already mirrors both shots |
| ASL p50 | `32.6s` | Continuous cartographic glide, not cut-heavy body pacing |
| Cuts / min | `0.92` | Proof-role prior near one cut per minute |
| Ground palette | `#061C29` / `#010E1A` + earth `#636148` | Compatible with abyssal `#03161F` |
| Audio | `−10.5 LUFS`, TP `+1.8 dBTP`, silence ratio `0` | Source is hot; deliverables still master to `−14.0 LUFS` / `≤ −1.0 dBTP` |
| Lower-third luma | shot0 `48.5` / shot1 `18.5` | Caption band is safer on darker water (shot1) |

---

## 2. Craft inventory (sampled beats)

| t (s) | Camera | Highlight / props | Caption | Note |
| ---: | :--- | :--- | :--- | :--- |
| 0.5 | Fade from black; watermark lands | — | — | Cold open |
| 3 | Ortho-regional Middle East–South Asia | Dual Turkey blue + India magenta; dashed red corridor; `+4.000 KM` | km, tidak berbagi perbatasan, | Metric + dual-country compare |
| 8 | Slow push / pan | Dual fills + yellow chips | Namun hubungan keduanya kini | Compare hold |
| 12 | Push to Pakistan | Single red Pakistan fill | — | Closest to single-signal rule |
| 16 | Slight tilt | Pakistan red + Turkey blue + protest icons | Pakistan dalam isu Kashmir | Figurative icons |
| 20 | Himalaya tilt | Pakistan red + India magenta + dashed LOC | Ketegangan makin terasa setelah | Dual fill |
| 24 | Mountain close | Disputed stripe hatch + drone props | 2025 ketika pesawat nirawak | Hatch + 3D prop |
| 28 | Pull / pan | Dual India / Pakistan + Kashmir stripe | India tidak membalas dengan | Multi-region |
| 32 | Regional | Triple fills + soldier figurines | Mereka memilih cara yang | Reject figurative 3D cast |
| 36 | Caucasus push | Armenia cyan + India flag marble | dengan Armenia, rival utama | Influence flag pin |
| 40 | Border close | Azerbaijan green + Armenia cyan + red border + flags | — | Dual + border stroke |
| 45 | Aegean | Turkey blue + Greece purple + Cyprus lime + yellow chips | sengketa panjang dengan Turki | Three or more simultaneous colors |
| 50 | South Asia | India magenta + Pakistan orange + Turkey flag on north Pakistan | mendekati Pakistan di halaman | Influence pin |
| 55 | Anatolia | Multi-neighbor fills + dual India flag marbles | berada di sekitar Turki. | Multi-signal |
| 60 | Wide arcs | Dual fills + dual yellow trade arcs + dollar icons | — | Thematic raster icons |
| 64 | Turkey settle | Turkey blue + red heat hotspots + neighbors | saling mengawasi. | Pulse / heat markers |

**Camera.** Near-zero hard cuts; one continuous Earth-studio glide with pitch roughly `20°–45°` and zoom regional → local → regional. Watermark remains dead still after landing.

**Captions.** Dark rounded chip, white sentence case, three to six words, hard phrase switches, lower-third vertical band. No karaoke word-pop.

**Labels.** Yellow rounded chips with black ALL-CAPS country names often overlap landmass interiors; Geoverum relocates the same mechanic to open water with a short leader.

---

## 3. Adopt / adapt / reject

### Adopt

1. Continuous cartographic glide with long ASL and hold-drift (`camera-moves`, exemplars `ref_tectonics_*`).
2. Sentence-case caption rail with hard phrase cuts (`captions`; cadence ≈ `1.0–1.5s` per group).
3. Dashed geodesic corridor + tabular metric (`labels-lines`).
4. Circular flag pins at geographic coordinates (`props`).
5. Terrain-visible country fill + white exterior rim (`region-highlight`).
6. Disputed / zone hatching (Kashmir stripes → tectonic hatch).
7. Heat / pulse hotspots after a readable fill hold.
8. Unboxed top watermark (mapped to the Geoverum meridian lockup).

### Adapt

| Source mechanic | Geoverum mapping |
| :--- | :--- |
| Neon magenta / purple / lime multi-fills | One signal per beat: crimson `#C2412D`, cobalt `#2E74E6`, or amber `#F5C542`, staggered |
| Yellow `#FFD60A` chips on land | Amber `#F5C542` + ink `#03161F`, open-water / margin + `4–6px` leader |
| Italic yellow metric + heavy shadow | Archivo Black tabular over open water; avoid heavy drop-shadow chrome |
| Dual trade arcs + dollar icons | Amber flow arrows / stroke-dash corridors; Material Symbols only |
| Red heat bloom hotspots | Amber pulse rings (bake blur plates; no runtime CSS blur) |

### Reject

1. Simultaneous violet / magenta / neon multi-country fills (`violet_generic_accent`, `simultaneous_multi_neon_fills`).
2. Soldier, drone, or protest figurines outside the Material Symbols vocabulary.
3. Label pills covering the focal landmass (`never_overlap_subject_boxes`).
4. Source loudness as a deliverable target.
5. Source channel glyph or wordmark.

---

## 4. Gaps addressed in policy

| Area | Gap | Resolution |
| :--- | :--- | :--- |
| Temporal prior | Body ASL under-represented continuous proof glides | Exemplar notes retain ≈ `30s` ASL / ≈ `1.0` cuts/min for proof role |
| Dual-entity compare | Missing staggered two-territory grammar | Trigger `staggered_dual_territory_compare` |
| Influence pins | Foreign flag on a third country underspecified | Props SPEC allows one-family influence flag pins |
| Thematic raster icons | Flow arcs paired with dollar bills / emoji | Ban `thematic_emoji_raster_props` |
| Heat after hold | Pulse primitives existed without settle-then-pulse grammar | Trigger `heat_pulse_after_fill_hold` |
| Caption vs busy map | Lower-third safer over dark water | Keep `dynamic_away_from_subject` |
| Cold open | Black pre-roll before watermark | Optional soft `6–10f` black pre-roll before globe dive |
