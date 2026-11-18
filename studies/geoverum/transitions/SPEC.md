# Geoverum Transitions — Transitions & Aerial Relief Cutaways (`transitions`)

```text
GOAL:    Verify Geoverum's four editorial transition primitives (pre-rendered 6-frame radial zoom-blur
         whip at peak ease velocity, warm amber-cream optical light-leak flash, dissolve into cloudless
         Sentinel-2 z11 aerial relief B-roll, and documentary dip-out fade) at 1080x1920 (30 fps) with
         zero runtime CSS blur or violet leaks.
OUTPUT:  HyperFrames, 1080 x 1920, 30 fps (300 frames = 10.0s)
TIME:    10.0 seconds x 30 fps = 300 frames
LOOK:    ground: #03161F (abyssal ocean) + graded NASA BMNG & EOX Sentinel-2 cloudless 2016 basemaps;
         light-leak optical palette: #F5C542 (signal amber) -> #E67E22 (solar orange) -> #FFFDF8 (peak flash);
         fonts: Space Grotesk 700 (32px watermark) & 400 (13px attribution).
OBJECTS: 1. Shot A (`0.00s-2.13s`, f000-f064): Orbital globe dive into Sulawesi (`z1.85 -> z6.15`).
         2. Transition 1 (Whip): Pre-rendered 6-frame radial zoom-blur acceleration sequence (`f058-f063`)
            cutting cleanly on peak velocity at `f064` into Shot B.
         3. Shot B (`2.13s-4.93s`, f064-f148): 3D Gulf of Tomini coastline tilt (`z7.55`, `pitch 38°`).
         4. Transition 2 (Light Leak): Pre-rendered warm amber-cream film-burn sequence (`f143-f160`,
            peak exposure flash frame at `f148`) bridging cleanly into Shot C.
         5. Shot C (`4.93s-6.70s`, f148-f201): Palu-Koro fault corridor fly-over (`z8.5 -> z9.2`, `pitch 42°`).
         6. Transition 3 (Aerial Relief Crossfade): 10-frame (`0.33s`) linear-luminance cross-dissolve (`f191-f201`)
            revealing raw Sentinel-2 `z10.9` high-altitude aerial pass over Maros-Pangkep karst (`pitch 50°`).
         7. Shot D (`6.70s-10.00s`, f201-f300): Aerial topography pass + 15-frame documentary dip-out (`f285-f300`).
MOTION:  Whip acceleration: radial scale `1.00 -> 1.38` baked into 6 multi-tap radial blur plates (`power3.in`);
         Incoming Shot B settle: `scale 1.07 -> 1.00` over `0.20s` (`expo.out`) matching whip direction;
         Light-leak rise: `5` frames up to `#FFFDF8` peak at `f148`, decaying warm amber halation over `12` frames (`expo.out`);
         Aerial crossfade: `0.33s` (`power2.inOut`) smooth opacity cross-dissolve;
         Outro dip: `0.50s` (`15f`) smooth dark abyssal fade (`power2.in`).
LONGFORM HANDOFF:
         Cartographic context → live aerial/wildlife/cultural B-roll: prefer `clean_crossfade`
         (0.25–0.40s) or `amber_light_leak` when energy rises; return to map with hard cut or
         J-cut on speech gaps. Optional evidence/source card may bridge map and B-roll for ≤2.5s.

BANNED:  - Runtime CSS `filter: blur()` or `backdrop-filter` in HTML/CSS
         - Purple, violet, or neon magenta light leaks
         - Static paused shots flanking a cut
         - Abrupt cuts leaving outgoing elements mid-motion without velocity match
QA:      Inspect f030 (Shot A dive), f061 (mid radial zoom-blur whip), f095 (Shot B crisp settle),
         f147 (warm amber light leak pre-flash), f149 (post-flash reveal on Shot C),
         f196 (mid aerial karst crossfade), f250 (raw Sentinel-2 Maros relief), f292 (outro dip-out).
```

---

## Choreography Table

### Part 1 — Timeline

| Element | Role | Starts | Duration | Motion | Relationship |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Shot A -> Pre-Rendered Whip (`f058-f063`) | **Lead (T1)** | `0ms` (`f0`) | `2133ms` (`64f`) | Globe dive + 6-frame baked radial zoom blur | Hands off at peak whip velocity (`f064`) |
| Shot B + 6f Velocity Settle | **Lead (T1 Out)** | `2133ms` (`f064`) | `2800ms` (`84f`) | Arrives at `scale(1.07) -> 1.00` (`expo.out`), continues 3D glide | Matches incoming whip momentum |
| Warm Amber Light-Leak Plate | **Lead (T2)** | `4767ms` (`f143`) | `567ms` (`17f`) | Baked amber halation -> `#FFFDF8` flash (`f148`) -> warm decay | Bridges Shot B to Shot C seamlessly |
| Shot C (`f148-f201`) | **Lead (T2 Out)** | `4933ms` (`f148`) | `1767ms` (`53f`) | Palu-Koro valley 3D pass | Revealed underneath decaying golden light leak |
| Aerial Karst Relief (`Shot D`) | **Lead (T3/T4)** | `6367ms` (`f191`) | `3633ms` (`109f`) | `0.33s` cross-dissolve in (`f191-f201`), slow aerial glide, `0.50s` dip-out | Strips map symbology to real Earth surface |
| Broadcast Bug (`broadcast-layer`) | **Decoration** | `100ms` (`f3`) | `9400ms` (`282f`) | Fades in cleanly, exits gently during final `0.50s` dip | Never pops across transition cuts |

### Part 2 — What Does Not Move and Why
- **Attribution footer**: Locked static inside safe bottom margin until the final documentary dip so viewers stay grounded across fast camera cuts.

### Part 3 — Feel Check
- Scrub frame-by-frame around `f058-f068` and `f144-f156` to confirm zero crisp-freeze artifacts before transitions and smooth warm-gold exposure decay without muddy gray intermediates.
