# Design Engineering and Motion Standards

Permanent visual and motion-engineering rules for compositions and overlays compiled or rendered in this repository. Brand-specific cartography, tokens, and narrative craft live under `profiles/brands/<brand_id>/` (for example [`profiles/brands/geoverum/CRAFT.md`](profiles/brands/geoverum/CRAFT.md)).

Read this file with [`.agents/rules/engineering-standards.md`](.agents/rules/engineering-standards.md) and [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md) before changing engine-facing compositions or contracts.

---

## Part I — System vs. Project Boundary

| Layer | Paths | Responsibility |
| :--- | :--- | :--- |
| **1. Core engine (`vedit`)** | `packages/*`, `contracts/`, `profiles/platforms/` | Probe, ports/providers, external project lifecycle, `EditPlan` verify, HyperFrames compile, EBU R128 master, visual/technical QC audit, OTIO export, MCP server. |
| **2. Domain asset tooling** | `tools/geo-assets/`, `tools/rea-video/`, `tools/spatial-forensics/`, `assets/` | Shared deterministic geospatial fetch/grade/serve helpers, isolated forensic breakdown and spatial/grid/hierarchy vision toolchains, and gitignored shared asset caches. |
| **3. Brand profiles** | `profiles/brands/<brand_id>/` | Runtime `brand_style_policy.json`, executable `directing_idioms.json`, optional `editorial_playbook.json`, craft/directing docs (`CRAFT.md`, `DIRECTING.md`), and parameterized brand templates. |
| **4. Active editing projects** | External directory (`VEDIT_PROJECTS_ROOT/<brand_id>/<project_id>/`) | Self-contained editing projects managed by `vedit project init|status|validate`, completely separate from the engine repository. |

Engine code must stay brand-agnostic and free of historical episode artifacts. Brand rules enter only as profile files; active projects live strictly outside the engine repository.

---

## Part II — Cross-Brand Composition Rules

- Keep most of the frame calm; isolate **one** primary visual signal per beat.
- Never invent SaaS-style watermark chrome (pill containers, glowing status dots, film-strip viewfinders).
- Never render generic dashboard HUD chrome over footage or maps: prohibit dark translucent rounded cards with thin cyan/neon borders, thick left/top accent border strips on callout boxes, floating short decorative accent bars above metrics or titles, decorative corner-bracket viewfinder KPI boxes (`┌ ┐ └ ┘`), floating mini quote cards, forced decorative tilt (`-2°` to `-3°`) on text containers, and uppercase presentation-style eyebrow/kicker labels (such as `PART 02`, `TERRITORY SCALE`, `POLITICAL GEOGRAPHY`) stacked above short-form display titles or diagrams.
- Never render internal schema kind names (`KINETIC CALLOUT`, `DATA CARD`, `LOWER THIRD`) as on-screen badge copy.
- Caption and card placement must respect platform safe zones and clear detected subject boxes.
- Prefer direct boxless typography with crisp readability shadows, full-bleed vector diagrams, straight `0°` framing by default, or functional pointers/brackets/lassos over decorative containers.
- Stage local font binaries explicitly for both browser `@font-face` compilation and headless worker fontconfig registration so Chromium and `libass` never silently fall back to system sans fonts.

Brand palettes, typography families, and cartographic label rules belong in the brand profile craft document—not here.

---

## Part III — Motion & Choreography

### Execution boundary (HyperFrames vs. engine fast-paths)

- **MapLibre / offline basemap baking (`tools/geo-assets/`)**: Owns all deterministic 2.5D/3D satellite, terrain, and world-space vector map A-roll (`vedit geo prepare` and `vedit geo bake-scene`). Never fetch live tiles during HyperFrames renders.
- **FFmpeg native `libass` fast-path (`ass_captions.py`)**: Owns static/hard-cut or cross-faded (`120–200ms`) plain captions with optional outer glow halos (`caption_glow_color`, `caption_glow_px`), text-only watermarks, and quiet source credits in `hybrid` mode.
- **HyperFrames (`packages/hf-compiler-ts/` + brand templates)**: Owns high-value animated overlays rendered over sparse active windows (`ProRes 4444` alpha `.mov`)—vector draw-on (`SVG stroke-dashoffset`), full-bleed layered 2D cross-sections, `clip-path` wipes and splits, 3D CSS perspective flips, kinetic typography with multi-ring `text-shadow` glow (`glow_color`, `glow_strength`), tabular count-ups, and native shutter motion blur (`data-motion-blur="on"`). All `template_id` references auto-resolve from `profiles/brands/<brand_id>/templates/catalog.json` and fail loud when unknown.

### Physicality & easing

- Entrances start from `scale(0.92)`–`scale(0.96)` with opacity, or use `clip-path` mask reveals and SVG `stroke-dashoffset` draw-ons—never `scale(0)` and never uniform `power2.out` fade-and-slide-up on every element.
- Pointer-led callouts set `transform-origin` at the pointer tip / anchor and draw leader lines outward from the coordinate dot.
- Enter with long-tail ease-out (`expo.out` / `power4.out`, `180–360ms`). Camera morphs use ease-in-out (`700–1350ms`). Exits are `40–50%` shorter than entrances using `power3.in` and simultaneous within a group. Landed titles hold dead still with zero idle drift or breathing loops.
- Caption phrase switches use opacity-only transitions (configurable fade-in and fade-out or hard cut), never bouncy slides.
- **Cross-scene velocity carry-over & unified camera rig (`#cam`)**: Non-map surfaces (cross-sections, archival plates, splits, diagrams) entering from a high-speed camera move open at peak carry-over velocity and decay with `expo.out` / `power4.out` (`250–450ms`), while outgoing moves accelerate into the cut (`power2.in`). When panning or zooming inside a HyperFrames composition, wrap both content and pointer/callout layers inside a single `#cam` container (optional `perspective: 1400–1600px`) so focus tracking stays sub-pixel locked and settles flat (`0°`) for held text.
- **Tool & pointer kinematics**: Tool sprites (cursors, styluses, stamps, pointers) anchor `transform-origin` and negative offsets at the exact active contact hotspot (tip or stamp center), travel along curved arcs with subtle directional banking (`±6°–16°`), trigger a brief contact squash (`0ms` offset to the target reaction), scale-match across adjacent framing cuts, and exit `40–50%` faster than entry.

### Choreography roles (one lead per beat)

1. **Lead** — primary narrative motion.
2. **Support** — arrives on an overlap handoff near the lead’s completion.
3. **Decoration** — opacity-only accents.
4. **Static** — basemap / channel mark; does not re-animate per beat.

### Rendering performance

- Animate only `transform`, `opacity`, `clip-path`, or SVG `stroke-dashoffset`.
- Never animate layout properties or runtime CSS `filter: blur()` / `backdrop-filter`. For luminous glowing typography, use multi-ring `text-shadow` stacks (`glow_color`, `glow_strength`) in HTML or native `libass` blur tags (`\blur`) on subtitles rather than CSS filter blurs. Transient 1-axis SVG `<feGaussianBlur>` (`stdDeviation="0 blurY"` or `"blurX 0"` for `2–4` peak-velocity frames on rapid odometer/digit rolls or directional sweeps, or brief `0.25–0.42s` `expo.out` rack-focus decays at register-swap cuts) is permitted when animated strictly inside transition or peak-velocity windows and returning cleanly to `0` on held frames.
- Pre-bake whip/blur optical transitions, and camera motion blur only when an act opts in (`optical_shutter_blur: true`, `shutter_samples` sub-frame accumulation), into map media; map frames are otherwise captured crisp. Do not compute live filter blurs in Chromium.
- **HyperFrames composition invariants**:
  - *Parked-scene coordinate compensation*: Inactive HyperFrames scenes are parked off-screen (`data-hf-parked-scene`) during `t=0` script initialization; always compute dynamic layout anchors relative to the composition root (`target.getBoundingClientRect()` minus `root.getBoundingClientRect()`) rather than raw viewport coordinates.
  - *Timed `.clip` wrapper discipline*: Apply `class="clip" data-start="0" data-duration="{{DURATION_S}}"` only on timed scene/clip wrappers with an explicit `data-duration`; never attach a durationless `.clip` class to nested GSAP-animated `<img>` sprites, which causes HyperFrames' `hf-hidden-clip` rule to hide the image.
  - *Deterministic local font readiness*: Bundle every referenced font weight and italic style locally via explicit `@font-face` declarations and resolve fonts before frame `0` so text wrapping and dynamically measured pointer/pin coordinates never drift in headless Chromium.
