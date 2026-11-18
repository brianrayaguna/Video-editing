# Geoverum Labels & Lines — Map Labels, Curved Hydrography, Fault Traces, and Distance Corridors (`labels-lines`)

```text
GOAL:    Verify all four cartographic annotation and line-drawing primitives (dashed geodesic distance
         corridor with tabular counter & country badges, close-up curved `<textPath>` waterbody reveal,
         dual-stroke K progressive `stroke-dashoffset` draw-on, and tapered active fault trace with
         open-water pointer callout) at 1080x1920 (30 fps) with zero coastline/label collisions.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (300 frames = 10.0s)
TIME:    10.0 seconds x 30 fps = 300 frames
LOOK:    ground: #03161F (abyssal ocean) + graded NASA BMNG & EOX Sentinel-2 cloudless 2016 basemaps;
         badges & primary strokes: #F5C542 (signal amber), #F4F1EA (warm alabaster), #03161F (badge ink);
         corridor line: #D9383A (geodesic red dashed 18/12) with circular terminal nodes;
         hydrographic curved label: #7CE0F9 (hydro cyan, zoom >= 7.5 only);
         fonts: Archivo Black 900 (19px badges, 44px distance metric), Unbounded 800 (30px bay label),
         Space Grotesk 700 (32px watermark) & 400 (13px attribution), all `tabular-nums`.
OBJECTS: 1. Eurasia Corridor Rig (`#rig-corridor`): Turkey (#2E6BE6) & India (#C2412D) mainland paths,
            masked dashed corridor line, tabular `+4.000 KM` readout, origin-aware `TURKI` / `INDIA` chips.
         2. Tomini Close-Up Rig (`#rig-tomini`): `z7.65` 3D coast rim + curved `<textPath>` `TELUK TOMINI`
            placed inside open western-central bay clearing shorelines by >= 36px.
         3. Sulawesi K-Shape Rig (`#rig-kshape`): `z5.95` unified silhouette + 3 dual-stroke progressive paths.
         4. Palu-Koro Fault Rig (`#rig-palu`): `z6.05` tapered fault crescent + `SESAR PALU-KORO` callout badge
            placed over calm Makassar Strait open water west of the fault trace (zero land overlap).
MOTION:  Corridor reveal: clip wipe 0.80s (power2.inOut) + synced tabular numeral count `+0` -> `+4.000 KM`;
         Origin-aware chips: scale(0.92) -> 1.0, opacity 0 -> 1 in 0.20s (expo.out), origin at pointer tip;
         Tomini `<textPath>`: non-uniform letter reveal (48ms -> 26ms per glyph);
         K-strokes: SVG stroke-dashoffset 0.48s spine then 0.42s overlapping upper/lower arms (power2.inOut);
         Palu-Koro fault: downward clip wipe 0.68s (power2.inOut) with callout handoff during final 20%.
SHOTS:   f000-f084 (0.00s-2.80s): Beat 1 — Turkey-India Dashed Corridor, Tabular Metric & Country Chips
         f084-f159 (2.80s-5.30s): Beat 2 — Close-Up Gulf of Tomini Curved `<textPath>` Reveal
         f159-f234 (5.30s-7.80s): Beat 3 — Sulawesi Unified Silhouette & Progressive Dual-Stroke "K"
         f234-f300 (7.80s-10.00s): Beat 4 — Palu-Koro Tapered Fault Draw-On & Open-Water Pointer Callout
BANNED:  - Animating chips/callouts from scale(0) or default center origin when pointer-anchored
         - Placing bay labels (`TELUK TOMINI`) at wide regional zoom or colliding with coastline (< 24px)
         - Covering central landmass with `SESAR PALU-KORO` box or internal provincial seams
         - Stretching stroke-dasharray dots during draw-on (must reveal via geometry-independent clip mask)
         - Runtime CSS filter: blur() or backdrop-filter
QA:      Inspect f018 (corridor draw + Turki badge), f056 (corridor full + +4.000 KM), f128 (Teluk Tomini curve),
         f190 (K-shape mid-draw), f220 (full K-strokes), f276 (Palu-Koro fault + clean Makassar Strait callout).
```

---

## Choreography Table

### Part 1 — Timeline

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Beat Camera Rigs (`#rig-*`) | **Lead (Carrier)** | Beat start | Beat dur | Linear subtle push `scale: 1.00 -> 1.06` | Carries map plate & vectors in lockstep |
| Dashed Geodesic Line | **Lead (Beat 1)** | `350ms` (`f10`) | `800ms` (`24f`) | Horizontal `<clipPath>` wipe (`power2.inOut`) | Preserves constant `18 12` dash spacing |
| `TURKI` & `INDIA` Chips | **Support (Beat 1)** | `180ms`, `980ms` | `200ms` (`6f`) | `scale(0.92)->1`, `opacity:0->1` (`expo.out`), tip origin | `INDIA` lands as line nears east node |
| `+4.000 KM` Counter | **Support (Beat 1)** | `420ms` (`f13`) | `720ms` (`22f`) | Tabular count `+0` -> `+4.000 KM` (`power2.inOut`) | Syncs directly with dashed line span |
| `TELUK TOMINI` `<textPath>` | **Support (Beat 2)** | `3200ms` (`f96`) | `460ms` (`14f`) | Per-glyph opacity cascade along curve | Starts after cyan coastal rim settles |
| K-Shape Spine & Arms | **Lead (Beat 3)** | `5550ms` (`f166`) | `950ms` (`29f`) | `stroke-dashoffset` (`power2.inOut`), `300ms`/`230ms` overlap | Arms fire mid-spine stroke |
| Palu-Koro Tapered Fault | **Lead (Beat 4)** | `8000ms` (`f240`) | `680ms` (`20f`) | Downward reveal wipe (`power2.inOut`) | Draws trace across Central Sulawesi neck |
| `SESAR PALU-KORO` Badge | **Support (Beat 4)** | `8540ms` (`f256`) | `200ms` (`6f`) | `scale(0.92)->1` (`expo.out`), right pointer tip origin | Enters on final 20% of fault draw-on |
| Watermark Bug | **Decoration** | `100ms` (`f3`) | `200ms` (`6f`) | `scale(0.96)->1`, `opacity:0->0.86`, then holds static | Fixed upper-safe broadcast identifier |

### Part 2 — What Does Not Move and Why
- **Country silhouettes, attribution footer, and coastline rims after entry**: They provide spatial ground once settled so eye tracking locks onto the animated trace and callout landing.
- **Map projection inside each beat**: Fixed MapLibre projections per beat locked inside `#rig-*` ensure vector strokes and coastlines remain sub-pixel aligned.

### Part 3 — Feel Check
- Inspect `f056`, `f128`, `f220`, and `f276` on the QA contact sheet to verify: zero digit width shift on `+4.000 KM`, >= 36px shoreline clearance around `TELUK TOMINI`, clean dual-stroke K caps without miter artifacts, and completely unobscured land around `SESAR PALU-KORO` over calm Makassar Strait water.
