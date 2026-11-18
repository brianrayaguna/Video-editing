# Geoverum Branding — Channel Watermark & Documentary Outro End-Card (`branding`)

```text
GOAL:    Verify Geoverum's finalized brand identity surfaces (unboxed upper-safe broadcast meridian bug
         during map pullback plus an editorial documentary closing question & source colophon end-card) at
         1080x1920 (30 fps) with zero SaaS pills, zero glowing dots, and zero blur chrome.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (180 frames = 6.0s)
TIME:    6.0 seconds x 30 fps = 180 frames
LOOK:    ground: #03161F (abyssal ocean) + graded Sulawesi satellite relief plate + clean `#03161F` scrim (66%);
         ink: #F4F1EA (warm alabaster primary type & meridian mark), #F5C542 (signal amber CTA rule & icon),
         muted source colophon `rgba(244, 241, 234, 0.54)`;
         fonts: Space Grotesk 700 (32px watermark, 48px outro prompt), 500 (28px CTA line), 400 (15px colophon).
OBJECTS: 1. Sulawesi Pullback Plate (`#rig-outro`): continuous slow zoom-out/drift revealing Sulawesi island.
         2. Broadcast Watermark (`#watermark-inner`): unboxed monochrome 34px meridian-globe + `GEOVERUM`
            wordmark in upper safe zone (`y = 72px`, `opacity: 0.86`, zero container pill or dot).
         3. Editorial Engagement Card (`#endcard-group`):
            - Meridian rule & subtle series kicker (`SERI GEOGRAFI NUSANTARA`)
            - Closing documentary prompt (`"Ada yang berasal dari Sulawesi?"`)
            - Interactive comment cue with Material `location_on` glyph (`"Tulis asal daerahmu di komentar"`)
            - Data provenance colophon (`Imagery: NASA Blue Marble · Copernicus Sentinel-2 · Natural Earth · GEM`)
MOTION:  Continuous map drift: `scale: 1.12 -> 1.00`, `y: -28 -> 0` linear across 6.0s (no dead pause);
         Watermark bug: `scale(0.96)->1`, `opacity:0->0.86` at `0.10s` (`expo.out`), fades gently into endcard;
         End-card reveal (`2.20s`): smooth scrim deepen (`0.40s` `power2.inOut`) -> series lockup & headline
         word-group rise (`8px -> 0`, `opacity: 0 -> 1`, `0.26s` `expo.out`) -> amber comment cue overlapping
         by `80ms` -> static read hold (`2.80s–5.50s`) -> clean `0.50s` dip-out fade (`5.50s–6.00s`).
BANNED:  - Pill-shaped dark container (`border-radius: 999px`) or glowing status dot beside `GEOVERUM`
         - Bento grid CTA boxes, neon buttons, or violet gradients
         - Runtime CSS `filter: blur()` or `backdrop-filter`
         - Leaving platform bottom 20% occupied (Shorts comment/share chrome collision)
         - Film-strip / camera-viewfinder chrome frames around the deliverable
         - Corner political stickers or non-brand badge clusters

ASPECT:  9:16 keeps unboxed top-center meridian + wordmark (`y ≈ 72px` on 1920).
         16:9 long-form may park a compact meridian mark at top-right safe inset (12–24px)
         without the full wordmark when landscape B-roll needs horizontal headroom.
QA:      Inspect f020 (unboxed broadcast bug over moving Sulawesi), f066 (scrim deepening transition),
         f090 (headline + comment cue landed), f145 (full readable hold state), f174 (outro dip-out fade).
```

---

## Choreography Table

### Part 1 — Timeline

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Sulawesi Pullback Plate | **Lead (Global)** | `0ms` (`f0`) | `6000ms` (`180f`) | Linear drift `scale: 1.12 -> 1.00`, `y: -28 -> 0` | Provides calm geographic continuity behind endcard |
| Unboxed Broadcast Bug | **Decoration** | `100ms` (`f3`) | `2100ms` (`63f`) | `scale(0.96)->1`, `opacity:0->0.86`; exits cleanly as endcard rises | Avoids duplicate brand text ("Say it once") |
| Dark Abyssal Scrim | **Support** | `2100ms` (`f63`) | `420ms` (`13f`) | `opacity: 0.14 -> 0.72` (`power2.inOut`) | Prepares >= 10:1 legibility canvas for outro copy |
| Closing Headline & Lockup | **Lead (End-Card)** | `2320ms` (`f70`) | `260ms` (`8f`) | `y: 10px -> 0`, `opacity: 0 -> 1` (`expo.out`) | Anchors vertical center safe area (`38%-58%`) |
| Comment CTA Cue & Rule | **Support (End-Card)** | `2460ms` (`f74`) | `220ms` (`7f`) | `y: 8px -> 0`, `scale(0.96)->1`, `opacity: 0->1` (`expo.out`) | Overlaps headline settle cleanly |
| Outro Fade-to-Abyss | **Exit** | `5500ms` (`f165`) | `500ms` (`15f`) | Unified `opacity: 1 -> 0` to `#03161F` | Clean broadcast tail fade |

### Part 2 — What Does Not Move and Why
- **Headline & colophon during the read hold (`f85–f165`)**: Strictly stationary after landing so the viewer reads effortlessly without text drift (`hyperframes/references/motion.md`).
- **Simultaneous broadcast watermark**: Replaced cleanly by the end-card lockup during Beat 2 instead of showing "GEOVERUM" twice on the same frame ("Say it once").

### Part 3 — Feel Check
- Inspect `f020`, `f090`, and `f145`: confirm the top broadcast bug looks crisp without any pill box or dot, the word `GEOVERUM` never appears duplicated during the end-card, and all outro copy holds >= 10:1 contrast completely inside the central 28%–68% safe vertical band.
