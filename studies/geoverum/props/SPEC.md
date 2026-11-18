# Geoverum Props — Cartographic Props, Circular Flag Pins, Single-Family Icons, and Flow Arrows (`props`)

```text
GOAL:    Verify Geoverum's spatial prop vocabulary (circular vector country flag pins from `flag-icons`,
         single-family Google Material Symbols Rounded hazard & orientation markers, and directional tectonic
         convergence flow arrows with synced arrowheads) over moving satellite canvases at 1080x1920 (30 fps).
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (240 frames = 8.0s)
TIME:    8.0 seconds x 30 fps = 240 frames
LOOK:    ground: #03161F (abyssal ocean) + graded NASA BMNG & EOX Sentinel-2 cloudless 2016 basemaps;
         flags: real `assets/geo/flags/1x1/*.svg` (Turkey, India, Pakistan) in 2.5px `#F4F1EA` circular medallions;
         icons: single family `assets/geo/icons/` (`tsunami`, `warning`, `explore`, `location_on`) inside 46px
         solid opaque discs (#03161F backing, #F5C542 amber glyph ring or #C2412D hazard fill, zero duotone);
         flow arrows: #F5C542 (signal amber, 4.5px stroke) + #F4F1EA (understroke) converging onto #F4F1EA hub;
         fonts: Archivo Black 900 (17px compact pin tags), Space Grotesk 700 (32px watermark) & 400 (attribution).
OBJECTS: 1. Beat 1 (`0.00s-2.67s`, f000-f080): Eurasia Corridor Flag Pins (`Turkey`, `Pakistan`, `India`)
            standing vertically on pinpoint `1.5px` stalks anchored at exact geographic coordinates.
         2. Beat 2 (`2.67s-5.33s`, f080-f160): Sulawesi Hazard & Basin Icons (`tsunami` at Palu Bay,
            `warning` on Palu-Koro fault, `explore` in Tomini open water) using 1 icon family only.
         3. Beat 3 (`5.33s-8.00s`, f160-f240): Three-plate Tectonic Convergence Flow Vectors pushing
            into Central Sulawesi (`location_on` convergence hub), arrowheads landing at 85% route reveal.
MOTION:  Pin & badge entrances: scale(0.92) -> 1.0, opacity 0 -> 1 over 0.20s (expo.out), transform-origin
         locked at stalk foot (`center bottom`); non-uniform staggers (`0ms -> 150ms -> 250ms`);
         Convergence flow arrows: `stroke-dashoffset` draw-on over 0.56s (power2.inOut) with arrowheads
         entering on route completion (final 15% overlap handoff).
INFLUENCE: Foreign circular flag pins may mark presence/influence inside a third country,
         anchored at geographic coordinates with the same stalk/medallion system.
         One pin family only; max one foreign-flag signal per beat.

BANNED:  - Hand-drawn custom pin shapes or emoji glyphs
         - Thematic raster props (dollar bills, soldiers, drones-as-toys) — use Material Symbols
         - Mixing multiple icon packs or varying stroke weights across markers
         - Translucent overlapping circles creating dark onion-skin seams
         - Animating markers from scale(0) or floating after settle
QA:      Inspect f022 (Turkey+India flag pins active), f062 (all 3 flags settled), f115 (Sulawesi single-family
         Material icons), f150 (icons held steady), f192 (convergence shafts drawing), f225 (arrows landed on hub).
```

---

## Choreography Table

### Part 1 — Timeline

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Beat Camera Rigs (`#rig-*`) | **Lead (Carrier)** | Beat start | Beat dur | Linear subtle push `scale: 1.00 -> 1.05` | Carries map imagery & pinned coordinates together |
| Flag Pin Stalks & Medallions | **Lead (Beat 1)** | `200ms`, `350ms`, `450ms` | `200ms` (`6f`) | `scale(0.92)->1`, `opacity:0->1` (`expo.out`), bottom anchor | Non-uniform `150ms -> 100ms` stagger |
| Material Hazard Icons | **Lead (Beat 2)** | `2867ms`, `3000ms`, `3090ms` | `200ms` (`6f`) | `scale(0.92)->1`, `opacity:0->1` (`expo.out`), bottom anchor | Non-uniform `133ms -> 90ms` stagger |
| Tectonic Convergence Shafts | **Lead (Beat 3)** | `5533ms` (`f166`) | `580ms` (`17f`) | `stroke-dashoffset` (`power2.inOut`), `90ms` stagger | Three oceanic/crustal vectors converging inland |
| Convergence Arrowheads & Hub | **Support (Beat 3)** | `6000ms` (`f180`) | `180ms` (`5f`) | `scale(0.92)->1`, `opacity:0->1` (`expo.out`) | Lands strictly as each shaft reaches its terminus |
| Broadcast Watermark | **Decoration** | `100ms` (`f3`) | `200ms` (`6f`) | `scale(0.96)->1`, `opacity:0->0.86` | Static after landing |

### Part 2 — What Does Not Move and Why
- **Landed flag pins, icons, and text tags**: Once each marker settles (`200ms`), it holds dead still over its geographic coordinate (no idle bobbing/bouncing loops per `hyperframes/references/motion.md`).

### Part 3 — Feel Check
- Inspect `f062`, `f115`, and `f225` to verify that every circular icon/flag has opaque backing with zero onion-skin overlap, consistent visual stroke weight, and exact arrowhead docking at the end of each flow shaft.
