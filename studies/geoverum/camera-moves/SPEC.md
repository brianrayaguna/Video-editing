# Geoverum Camera Moves — Continuous Map Camera Choreography (`camera-moves`)

```text
GOAL:    Verify that Geoverum's continuous one-take virtual satellite camera reproduces the
         empirical speed, easing, 3D tilt, and non-static hold rhythm of the reference videos
         at 1080x1920 (30 fps) with zero frozen holds and zero tile-loading artifacts.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (all-intra H.264 bt709 basemap + HTML/SVG broadcast layer)
TIME:    12.0 seconds x 30 fps = 360 frames
LOOK:    ground: #03161F (abyssal ocean) + graded NASA BMNG (z0-z4) & EOX Sentinel-2 2016 (z5-z11);
         ink: #F4F1EA (warm bone white, 86% opacity on top-center broadcast watermark);
         font: Space Grotesk 700 (32px, 0.12em tracking on GEOVERUM wordmark),
               Space Grotesk 400 (13px, 40% opacity on single-line footer credit);
         shadow: drop-shadow(0 2px 10px rgba(0, 0, 0, 0.68)) on watermark.
OBJECTS: 1. Earth globe in starfield (220 deterministic stars, atmosphere blend z0->z6)
         2. Sulawesi island & surrounding gulfs (Tomini, Tolo, Bone, Palu-Koro valley)
         3. Unboxed Geoverum meridian-globe mark + wordmark at top safe zone (y = 72px)
         4. Single-line attribution credit at bottom edge (y = 1882px, data-layout-ignore)
MOTION:  Camera interpolation curve (move/fly-to): cubic-bezier(0.77, 0, 0.175, 1) (emil-design-eng --ease-in-out);
         Camera hold drift: linear / sine-smoothed continuous creep (+4% to +6% scale per 3s);
         Watermark entrance: opacity 0 -> 0.86 over 6 frames (200ms) on cubic-bezier(0.23, 1, 0.32, 1), then dead still.
SHOTS:   f000-f040 (0.00s-1.33s): Beat 1 — Orbital Globe Dive
           globe projection, center [108.0, 8.0] -> [121.35, -1.75], zoom 1.85 -> 5.95, pitch 0° -> 0°, bearing 0° -> 0°.
         f040-f126 (1.33s-4.20s): Beat 2 — Slow Push-In Hold over Sulawesi
           mercator transition, center [121.35, -1.75] -> [121.25, -1.55], zoom 5.95 -> 6.18, pitch 0° -> 10°, bearing 0° -> -2°.
         f126-f165 (4.20s-5.50s): Beat 3a — 3D Fly-To into Gulf of Tomini
           center [121.25, -1.55] -> [120.88, -0.25], zoom 6.18 -> 7.65, pitch 10° -> 38°, bearing -2° -> -10°.
         f165-f240 (5.50s-8.00s): Beat 3b — 3D Coastal Glide to Gulf of Tolo
           center [120.88, -0.25] -> [122.15, -1.85], zoom 7.65 -> 7.42, pitch 38° -> 34°, bearing -10° -> +14°.
         f240-f276 (8.00s-9.20s): Beat 4a — Fly-To Palu-Koro Fault Valley
           center [122.15, -1.85] -> [119.92, -1.12], zoom 7.42 -> 8.85, pitch 34° -> 42°, bearing +14° -> -16°.
         f276-f318 (9.20s-10.60s): Beat 4b — Fault Valley Drift toward Palu Bay
           center [119.92, -1.12] -> [119.85, -0.82], zoom 8.85 -> 9.10, pitch 42° -> 40°, bearing -16° -> -8°.
         f318-f359 (10.60s-12.00s): Beat 4c — Regional Pull-Back Settle
           center [119.85, -0.82] -> [121.35, -1.68], zoom 9.10 -> 6.08, pitch 40° -> 14°, bearing -8° -> -4°.
BANNED:  - Pill-wrapped watermark or glowing status dot
         - Decorative HUD brackets, fake telemetry coordinates, or corner labels
         - Frozen camera holds (any 0.5s window with mean YDIF < 0.8)
         - Runtime CSS filter: blur() or backdrop-filter
QA:      Check frames f005 (globe in space), f040 (Sulawesi arrival), f100 (push-in hold),
         f165 (Tomini 3D tilt), f235 (Tolo coastal sweep), f285 (Palu-Koro valley close-up),
         f355 (regional pull-back).
```

---

## Choreography Table (`choreograph` Skill Format)

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Virtual Satellite Camera (`#basemap-video`) | **Lead** | `0ms` (`f0`) | `12000ms` (`360f`) | 7-segment continuous keyframe trajectory (`z1.85` globe dive → push-in → 3D coastal glide → fault valley → pull-back) | Primary narrative driver |
| Broadcast Watermark (`#watermark`) | **Support** | `100ms` (`f3`) | `200ms` (`6f`) | `opacity: 0 -> 0.86` (`cubic-bezier(0.23, 1, 0.32, 1)`), then holds dead still | Enters during opening globe dive |
| Starfield & Atmosphere | **Decoration** | `0ms` (`f0`) | `1333ms` (`40f`) | Atmosphere fades naturally as camera dives from `z1.85` to `z5.95` | Carried by camera zoom |
| Footer Attribution (`#credit`) | **Static** | `0ms` (`f0`) | `12000ms` (`360f`) | Static (`opacity: 0.40`) | Static ground metadata |

### What Doesn't Move, and Why
1. **Broadcast Watermark after `f9`**: Once landed at `t = 0.30s`, the `GEOVERUM` mark remains dead still across all camera moves so it acts as a stable broadcast anchor (`hyperframes/references/motion.md`: *"a landed title is dead still; the motion moves to the camera or the world behind"*).
2. **Footer Attribution**: Static throughout; animating legal/attribution text draws unintended eye movement away from the map camera.
