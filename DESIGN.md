# Design Engineering and Motion Standards

Permanent visual and motion-engineering rules for compositions and overlays compiled or rendered in this repository. Brand-specific cartography, tokens, and narrative craft live under `profiles/brands/<brand_id>/` (for example [`profiles/brands/geoverum/CRAFT.md`](profiles/brands/geoverum/CRAFT.md)).

Read this file with [`.agents/rules/engineering-standards.md`](.agents/rules/engineering-standards.md) and [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md) before changing engine-facing compositions or contracts.

---

## Part I — System vs. Project Boundary

| Layer | Paths | Responsibility |
| :--- | :--- | :--- |
| **1. Core engine (`vedit`)** | `packages/*`, `contracts/`, `profiles/platforms/` | Probe, ports/providers, `EditPlan` verify, HyperFrames compile, EBU R128 master, QC audit. |
| **2. Domain asset tooling** | `tools/geo-assets/`, `assets/geo/` | Deterministic geospatial fetch, tile grade, offline XYZ serve, local MapLibre A-roll bake. |
| **3. Brand profiles** | `profiles/brands/<brand_id>/` | Runtime `brand_style_policy.json`, optional `editorial_playbook.json`, craft docs, license notes. |
| **4. Studies & productions** | `studies/<brand_id>/<study_id>/` | Isolated HyperFrames studies and full EditPlan productions. |

Engine code must stay brand-agnostic. Brand rules enter only as policy files and study assets.

---

## Part II — Cross-Brand Composition Rules

- Keep most of the frame calm; isolate **one** primary visual signal per beat.
- Never invent SaaS-style watermark chrome (pill containers, glowing status dots, film-strip viewfinders).
- Never render internal schema kind names (`KINETIC CALLOUT`, `DATA CARD`, `LOWER THIRD`) as on-screen badge copy.
- Caption and card placement must respect platform safe zones and clear detected subject boxes.
- Prefer surface contrast over decorative borders for readable text.

Brand palettes, typography families, and cartographic label rules belong in the brand profile craft document—not here.

---

## Part III — Motion & Choreography

### Physicality & easing

- Entrances start from `scale(0.92)`–`scale(0.96)` with opacity, never `scale(0)`.
- Pointer-led callouts set `transform-origin` at the pointer tip / anchor.
- Enter with ease-out (`150–240ms`). Camera morphs use ease-in-out (`700–1350ms`). Exits are `40–50%` shorter than entrances and simultaneous within a group.
- Caption phrase switches are hard cuts (`<= 80ms`), not bouncy slides.

### Choreography roles (one lead per beat)

1. **Lead** — primary narrative motion.
2. **Support** — arrives on an overlap handoff near the lead’s completion.
3. **Decoration** — opacity-only accents.
4. **Static** — basemap / channel mark; does not re-animate per beat.

### Rendering performance

- Animate only `transform`, `opacity`, `clip-path`, or SVG `stroke-dashoffset`.
- Never animate layout properties or runtime CSS `filter: blur()` / `backdrop-filter`.
- Pre-bake whip/blur optical transitions into media; do not compute them live in Chromium.
