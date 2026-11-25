# Geoverum Brand Templates

Parameterized, aspect-responsive (`9:16` and `16:9`) HyperFrames compositions with **typed variables**. Layout, proportion, and motion stay locked in `components/*.html`; automation binds declared variables at compile time.

| File | Role |
| :--- | :--- |
| [`catalog.json`](catalog.json) | Template registry validated by `contracts/brand_template.schema.json` |
| [`components/`](components/) | Topic-agnostic parameterized HTML compositions bundled into local and distributed cloud workers |

This is the operational counterpart to:

- Runtime policy: `../brand_style_policy.json`
- Directing idioms: `../directing_idioms.json`
- Advisory playbook: `../editorial_playbook.json`
- Craft & directing prose: `../CRAFT.md`, `../DIRECTING.md`

---

## HyperFrames Component Invariants

1. **Timed `.clip` wrappers**: Apply `class="clip" data-start="0" data-duration="{{DURATION_S}}"` on timed composition wrappers only; never attach a durationless `.clip` class to nested GSAP-animated `<img>` sprites, which causes HyperFrames' `hf-hidden-clip` rule to hide the image.
2. **Parked-scene coordinate compensation**: Because inactive HyperFrames scenes sit off-screen (`data-hf-parked-scene`) during `t=0` initialization, compute any dynamic anchor relative to the composition root (`target.getBoundingClientRect()` minus `root.getBoundingClientRect()`).
3. **Unified `#cam` transform rig**: Wrap non-map surfaces that pan, zoom, or inherit transition momentum inside a single `#cam` container (`perspective: 1400–1600px`) so content and pointer/callout layers share one transform tree.
4. **Directional SVG blur only**: Restrict runtime blur strictly to transient peak-velocity 1-axis SVG `<feGaussianBlur>` (`stdDeviation="0 blurY"` or `"blurX 0"`) or brief transition rack-focus decays returning cleanly to `0`; never use CSS `filter: blur()` or `backdrop-filter`.
5. **Local `@font-face` bundling**: Stage all referenced font weights and italics locally via `@font-face` and resolve them before frame `0` so headless renders have zero text-metric drift.
