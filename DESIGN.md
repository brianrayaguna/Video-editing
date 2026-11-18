# Design Engineering, Cartographic Restraint, and Motion Standards

This document defines the permanent visual, typographic, spatial, and motion-engineering rules for all compositions, overlays, and brand profiles compiled or rendered in this repository. It synthesizes the enforcement rules of `taste-skill`, `stageshow`, Emil Kowalski's design-engineering standards (`emil-design-eng`, `choreograph`, `review-animations`), and the HyperFrames composition specification.

Before creating or modifying any overlay template, cartographic scene, or `BrandStylePolicy`, read this file alongside [`.agents/rules/engineering-standards.md`](.agents/rules/engineering-standards.md) and [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md).

---

## Part I — System vs. Project Boundary

To keep the directing engine modular and third-party readable, the repository separates **Engine Infrastructure** from **Brand Profiles and Composition Studies**:

| Layer | Paths | Responsibility |
| :--- | :--- | :--- |
| **1. Core Directing & Mastering Engine (`vedit`)** | `packages/media-probe-rs`<br>`packages/director-py`<br>`packages/hf-compiler-ts`<br>`packages/cloud-modal`<br>`contracts/`<br>`profiles/platforms/` | Provider-agnostic media probing (`vedit-probe`), capability ports (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`), `BrandStylePolicy` synthesis, deterministic `EditPlan` verification, HyperFrames compilation, EBU R128 mastering (`-14.0 LUFS` / `<= -1.0 dBTP`), and QC auditing. |
| **2. Domain Asset Tooling** | `tools/geo-assets/`<br>`assets/geo/` | Deterministic, offline-reproducible acquisition, SHA-256 manifest verification (`assets/geo/MANIFEST.json`), build-time raster tile grading, topological vector preparation, and local XYZ tile serving (`127.0.0.1`). |
| **3. Brand Profiles** | `profiles/<brand_id>/` | Schema-validated `brand_style_policy.json`, brand token specifications, license attribution requirements, and reference exemplar banks for a specific editorial identity (for example, `profiles/geoverum/`). |
| **4. Composition Studies & Productions** | `studies/<brand_id>/<study_id>/` | Isolated, single-responsibility HyperFrames compositions (`1080x1920` or `1920x1080`) verifying individual visual grammar components (camera choreography, region highlights, caption rails, callout annotations, transitions, audio mastering) prior to full-episode assembly. |

---

## Part II — Surfaces, Color, and Cartographic Restraint

### 1. Neutral Ground & Single-Signal Hierarchy
- **90–95% Neutral Canvas**: Keep the base canvas (abyssal ocean `#03161F` and natural satellite terrain relief) calm and neutral. Reserve saturated accent color for **one focal relationship per shot** ("Say it once").
- **Never Combine Competing Signals in One Still**: Do not stack multi-colored administrative subdivisions, fault lines, tectonic plate grids, and multiple region labels in the same beat. Each beat isolates one hero visual statement.
- **No Violet or Lavender Defaults**: Never use violet, purple, or lavender (`OKLCH` hue `270°–330°`) as a brand accent, region fill, gradient, or glow.
- **No Translucent Mud or Onion-Skin Seams**:
  - When highlighting a landmass or island, dissolve internal administrative boundaries into a **single unified exterior coastline polygon** before rendering. Never stroke adjacent sub-regions with translucent borders that double-paint internal seams (`onion skin`).
  - Preserve underlying satellite terrain relief inside highlighted regions using build-time color grading or composite blending rather than opaque pastel washes.

### 2. Brand Marks & Watermarks
- **No Invented SaaS Pills or Status Dots**: Never wrap a documentary channel watermark inside a pill container (`border-radius: 999px`), never add a translucent border around a watermark, and never place a glowing colored dot (`box-shadow` orb) beside the brand name.
  <!-- 2026-11-18: User rejected the pill-wrapped "[ ● GEOVERUM ]" badge as generic AI slop -->
- **Clean Broadcast Bug**: Render the channel mark as an unboxed, high-contrast typographic wordmark (or authentic monochrome geometric emblem + wordmark) directly over the upper safe zone at `78–85%` opacity.

### 3. Annotations, Callouts, and Connecting Lines
- **Never Cover the Payoff**: An annotation or callout badge must never sit on top of the geographic feature, fault line, or region it explains. Place callout badges in calm open water or quiet terrain margins outside the focal geometry.
  <!-- 2026-11-18: User rejected callout boxes and bay labels colliding with Sulawesi coastline and covering central landmass -->
- **Zero Collision (`[collide]`)**: Maintain at least `12px` (at `1080p` portrait scale, `>= 24px` preferred) of clear space between any text label/badge and neighboring coastlines, fault strokes, or other labels.
- **Scale-Matched Labels**: Waterbody and bay labels (`TELUK TOMINI`, `TELUK BONE`, `TELUK TOLO`) may only appear when the camera zoom level (`z >= 7.2`) provides sufficient open-water clearance inside the bay so the curved `<textPath>` never touches land.
- **Leader Geometry**: When a callout badge sits in open water beside a narrow target (such as a fault trace or strait), connect it with a crisp `1.5–2px` leader line or directional pointer that terminates `4–6px` short of the target stroke—never crossing through another label.
- **No Redundant Tonal Borders**: Caption rails and callout chips rely on surface contrast (`>= 7:1` WCAG text contrast for primary copy, `>= 4.5:1` minimum) rather than decorative `2px` colored borders.
- **No Leaked Schema Labels**: Never render internal schema kind names (`KINETIC CALLOUT`, `DATA CARD`, `LOWER THIRD`) as visible badge text on screen.

---

## Part III — Typography

- **Caption Rail (Narrative Subtitles)**:
  - **Case**: `sentence` case (never all-caps for running speech).
  - **Cadence**: `3–6` words per group (`p50` duration `0.95–1.30s`), breaking cleanly at clause boundaries or pauses `>= 150ms`.
  - **Placement**: Fixed horizontal center at `76%` of frame height (`y ≈ 1460px` on `1080x1920`), clear of platform bottom UI chrome (`>= 14%` bottom safe margin).
  - **Surface**: Compact dark backing (`rgba(3, 22, 31, 0.78)`), `6–8px` corner radius, `10px 20px` padding, no border, crisp white-warm ink (`#F4F1EA`), `30–34px` font size (`Space Grotesk` `500–600`).
- **Cartographic Feature Badges (Countries, Faults, Cities)**:
  - High-contrast solid fill (`#F5C542` warm signal amber with `#03161F` ink, or `#F4F1EA` bone white with `#03161F` ink), `4–6px` radius, `Archivo Black` or bold geometric sans (`700–900`), tight tracking (`-0.01em` to `0.02em`), optically centered cap-height to baseline.
- **Hydrographic Labels (Gulfs, Straits, Seas)**:
  - Curved along a smooth cubic Bezier `<path>` following the natural basin axis, rendered only at close-up zoom where the entire word clears the shoreline by `>= 24px`.
- **Tabular Numerals**:
  - Any animated or rolling number (`+4.000 KM`, coordinates, dates, metrics) must set `font-variant-numeric: tabular-nums` so digits never jitter horizontally.

---

## Part IV — Motion & Choreography (`emil-design-eng` + `choreograph` + `hyperframes`)

### 1. Physicality & Easing
- **Never Animate from `scale(0)`**: Elements entering the frame must start from `scale(0.92)`–`scale(0.96)` combined with `opacity: 0` (or a short draw-on reveal), never from zero size.
- **Origin-Aware Entrances**: Callout badges with a pointer or leader must set `transform-origin` to the pointer tip / anchor coordinate (`left center`, `bottom left`, etc.), never a generic `center center` float.
- **Custom Easing Curves by Role**:
  - **Enter (`ease-out`)**: `cubic-bezier(0.23, 1, 0.32, 1)` or GSAP `expo.out` / `power3.out` (`150–240ms`). Never use `ease-in` on entering UI or labels.
  - **Camera Flight & On-Screen Morph (`ease-in-out`)**: `cubic-bezier(0.77, 0, 0.175, 1)` or GSAP `power2.inOut` (`700–1350ms` for map fly-to moves).
  - **Exit**: `40–50%` shorter than entrance (`100–140ms`), simultaneous across a group (never reverse-stagger exits).
  - **Caption Rail Switching**: Instant hard cut between consecutive spoken phrase chunks (or `<= 80ms` cut), never a slow bouncy slide on every subtitle phrase.

### 2. Choreography Casting (One Lead per Beat)
Before coding any multi-element scene, assign each element to one of four roles:
1. **Lead**: The primary visual action carrying the narrative beat (e.g., the camera dive, the progressive fault-line draw-on, or the peninsula clip-path wipe). Moves first and travels the furthest.
2. **Support**: Secondary explanation hooked to the Lead's completion (e.g., the `SESAR PALU-KORO` callout badge arriving during the final `20%` of the fault-line draw-on—an *overlap handoff*).
3. **Decoration**: Subtle coastal glow or graticule lines—fades only, never translates or bounces.
4. **Static**: The basemap and channel watermark—never re-animates per beat.

### 3. Rendering & Performance Invariants
- **Only Animate `transform`, `opacity`, `clip-path`, or SVG `stroke-dashoffset`**: Never animate `top`, `left`, `width`, `height`, `padding`, or CSS `filter: blur()` / `backdrop-filter` at runtime.
- **Pre-Rendered Whip & Blur Transitions**: Fast camera whip-pans or radial zoom-blur transitions (`6` frames ramp-in at peak velocity) must be baked into the video asset or pre-rendered frame sequence, never computed via runtime CSS blur filters.
