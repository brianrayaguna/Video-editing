# Geoverum Region Highlight — Cartographic Region Highlighting (`region-highlight`)

```text
GOAL:    Verify Geoverum's four region-highlighting primitives (terrain-preserving silhouette tint,
         progressive 4-peninsula clip-path sweep recolor, non-uniform staggered tectonic pulse markers,
         and diagonal tectonic zone hatching) over a continuously pushing satellite camera at 1080x1920
         (30 fps) with zero internal provincial seams and one clear visual signal per beat.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (300 frames = 10.0s)
TIME:    10.0 seconds x 30 fps = 300 frames
LOOK:    ground: #03161F (abyssal ocean) + graded EOX Sentinel-2 cloudless 2016 basemap (z6.0);
         primary silhouette tint: #800E16 (64% multiply) + #A81820 (26% normal) + #F4F1EA 2.0px exterior rim;
         sweep recolor accent: #2E74E6 (cobalt-azure, 52% overlay + #8CC2FF 1.8px coastal rim — zero violet);
         pulse & hatching accent: #F5C542 (signal amber) with #F4F1EA (bone white) core rim;
         fonts: Space Grotesk 700 (32px wordmark), Space Grotesk 400 (13px attribution).
OBJECTS: 1. Shared Camera Rig (`#camera-rig`): carries both the 1080x1920 Sulawesi satellite plate and
            the screen-projected SVG overlay in a single transform matrix (`scale: 1.00 -> 1.13`,
            `x: 0 -> -12px`, `y: 0 -> -16px`) so vectors stay sub-pixel locked during the push-in.
         2. Unified Sulawesi Exterior Coastline (`#sulawesi-exterior`, 1,792 mainland vertices + 30 islands,
            zero internal administrative seams) acting as both the visible rim and the master `<clipPath>`.
         3. Four Directional Peninsula Sweep Masks (`#sweep-north`, `#sweep-east`, `#sweep-se`, `#sweep-south`)
            clipped inside `#sulawesi-land-clip`.
         4. Four Tectonic Pulse Nodes (`#pulse-north`, `#pulse-east`, `#pulse-se`, `#pulse-south`).
         5. Diagonal 45° Tectonic Collision Hatching Layer (`#tectonic-hatch`) clipped inside `#sulawesi-land-clip`.
MOTION:  Continuous camera push-in: linear scale 1.00 -> 1.13 over 10.0s (3.9% scale per 3s);
         Silhouette entrance: opacity 0 -> 1 over 10 frames (0.33s) on cubic-bezier(0.23, 1, 0.32, 1) (expo.out);
         Peninsula sweep wipes: 20 frames (0.67s) per arm on cubic-bezier(0.77, 0, 0.175, 1) (power2.inOut);
         Pulse marker cores: scale(0.92) -> 1.0, opacity 0 -> 1 in 0.18s (never scale(0));
         Pulse shockwave rings: scale(0.45) -> 2.8, opacity 0.85 -> 0 in 0.55s (expo.out), non-uniform stagger (270ms, 230ms, 190ms);
         Diagonal hatching reveal: clip-path inset(100% 0% 0% 0%) -> inset(32% 0% 0% 0%) in 0.55s (power2.inOut).
SHOTS:   f000-f072 (0.00s-2.40s): Beat 1 — Terrain-Preserving Crimson Silhouette Reveal
           f000-f010: Clean satellite basemap push-in starts;
           f010-f020: Unified crimson silhouette + white exterior coastline rim fades in (10f);
           f020-f072: Holds silhouette while terrain ridges remain crisp underneath.
         f072-f186 (2.40s-6.20s): Beat 2 — Progressive 4-Peninsula Sweep Recolor (No Seams)
           f075-f095: Arm 1 (Northern Peninsula: Minahasa-Gorontalo) sweeps to cobalt-azure;
           f100-f120: Arm 2 (Eastern Peninsula: Luwuk-Banggai) sweeps to cobalt-azure;
           f124-f144: Arm 3 (Southeastern Peninsula: Kendari-Buton) sweeps to cobalt-azure;
           f148-f168: Arm 4 (Southern Peninsula: Makassar-Bone) completes the island sweep;
           f168-f186: Full azure-highlighted island holds for reading clarity.
         f186-f246 (6.20s-8.20s): Beat 3 — Staggered Tectonic Pulse Markers on the 4 Arms
           f186-f195: Azure sweep recedes cleanly (9f) back to crimson base so pulses do not compete;
           f195 (6.50s): Pulse 1 fires on Northern Peninsula;
           f203 (6.77s, +270ms): Pulse 2 fires on Eastern Peninsula;
           f210 (7.00s, +230ms): Pulse 3 fires on Southeastern Peninsula;
           f216 (7.20s, +200ms): Pulse 4 fires on Southern Peninsula;
           f216-f246: All 4 amber core nodes hold in formation.
         f246-f300 (8.20s-10.00s): Beat 4 — Tectonic Collision Zone Diagonal Hatching
           f246-f251: Pulse nodes exit simultaneously in 5 frames (0.17s);
           f251-f268: Diagonal 45° amber hatching wipes upward across Southern & Central Sulawesi;
           f268-f300: Holds tectonic hatching state to end of study.
BANNED:  - Internal provincial border lines cutting across Sulawesi's landmass (onion-skin seams)
         - Violet or purple fills (OKLCH 270°-330°)
         - Animating from scale(0)
         - Uniform robotic stagger delays
         - Stacking sweep recolor, pulse rings, and hatching simultaneously
         - Runtime CSS filter: blur() or backdrop-filter
QA:      Inspect f005 (clean satellite), f045 (Beat 1 crimson silhouette), f115 (Beat 2 mid-sweep 2 arms),
         f175 (Beat 2 full 4-arm azure sweep), f218 (Beat 3 staggered pulses active), f280 (Beat 4 diagonal hatching).
```

---

## Choreography Table (`choreograph` Skill Format)

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Shared Camera Rig (`#camera-rig`) | **Lead (Global)** | `0ms` (`f0`) | `10000ms` (`300f`) | Continuous push-in `scale: 1.00 -> 1.13`, `x: 0 -> -12`, `y: 0 -> -16` | Carries basemap & all SVG layers in lockstep |
| Unified Crimson Silhouette (`#crimson-base`) | **Lead (Beat 1)** | `333ms` (`f10`) | `333ms` (`10f`) | `opacity: 0 -> 1` (`expo.out`) | Establishes island figure against dark sea |
| 4-Arm Sweep Masks (`#sweep-1..4`) | **Lead (Beat 2)** | `2500ms` (`f75`) | `3100ms` (`93f`) | Sequential directional polygon wipes (`20f` each, `power2.inOut`) | Overlaps Beat 1 base; recedes at `6200ms` (`f186`) |
| 4 Tectonic Pulse Nodes (`#pulse-1..4`) | **Lead (Beat 3)** | `6500ms` (`f195`) | `1700ms` (`51f`) | Core `scale(0.92)->1` + ring `scale(0.45)->2.8` (`expo.out`), shrinking stagger (`270ms, 230ms, 200ms`) | Starts as Beat 2 sweep recedes; simultaneous exit at `f246` |
| Diagonal Hatching (`#hatch-zone`) | **Lead (Beat 4)** | `8367ms` (`f251`) | `567ms` (`17f`) | `clip-path: inset(100% 0 0 0) -> inset(32% 0 0 0)` (`power2.inOut`) | Starts as Beat 3 pulses clear |
| Exterior Coastline Rim (`#coast-rim`) | **Support** | `333ms` (`f10`) | `9667ms` (`290f`) | Fades in with Beat 1 (`0.33s`), holds steady | Bounds all interior fills |
| Broadcast Watermark (`#watermark`) | **Decoration** | `100ms` (`f3`) | `200ms` (`6f`) | `opacity: 0 -> 0.86`, then dead still | Top safe-zone identity |
| Satellite Basemap (`#basemap-plate`) | **Static (in rig)** | `0ms` (`f0`) | `10000ms` (`300f`) | Carried by `#camera-rig` | Terrain relief foundation |
