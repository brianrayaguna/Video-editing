# Geoverum Profile Architecture & Production Calibration Design

## 1. Intent & Why

Geoverum is a cartographic documentary brand profile for the `vedit` engine across `9:16` portrait (`1080x1920`) and `16:9` landscape (`1920x1080` / `3840x2160`) formats. Its current profile tree suffers from five structural defects that degrade visual craft, storytelling originality, and context efficiency:

1. **Split reality between profile and renderer**: The map scene renderer (`tools/geo-assets/scene/` + `vedit/geo/`) evolved toward pitched 3D cartography, expressive world-space geometry, custom sprites/cutaways, and HTML soft-shadow captions, while `profiles/brands/geoverum/` and `.agents/skills/` still carry conflicting legacy tokens (`Rubik 56 px` vs `Inter 52 px`, `MarginV=348` vs `525`, `flag_pin` vs `flag_fill`, `Barlow Condensed` vs `Montserrat`).
2. **Active typographic defect**: `brand_style_policy.json` lists `Montserrat` first in `title_family` while `type_scale.hero` and seven HTML overlay templates declare `font-weight: 400` (intended for single-weight `Archivo Black`). Under `font-synthesis: none`, hero metrics and titles render in thin `Montserrat Regular 400`.
3. **Context bloat and mode collapse**: The six root profile files consume ~57,000 tokens (`editorial_playbook.json` alone holds 74 pseudo-DSL `grammar_triggers` with weight inflation around `0.9`, plus 83 text-only exemplars; `CRAFT.md` duplicates JSON tokens and internal renderer APIs across ~14,000 tokens). Heavy static rule piles dilute LLM attention and push directors toward repetitive template beats instead of concept-driven episodes.
4. **Dead wiring and orphan assets**: 18 of 32 catalog templates (`56%`) are unreferenced by `directing_idioms.json`, and 22 of 37 device types (`59%`) cannot be chosen by `auto_director.device_rules`. Engine-supported hooks (`readiness_phrases`, `audio_themes.json`) are unused.
5. **Misleading profiling mental model**: `.agents/skills/brand-profiling/SKILL.md` frames reference analysis as a monolithic ingestion workflow that dumps triggers and prose into permanent profile files, blurring offline reference calibration with active brand architecture and encouraging rigid imitation rather than creative range.

This design restructures Geoverum around a **Tight Rails, Open Canvas** architecture: lock the ~20% brand invariants as a single source of truth synced to the renderer, open ~80% of episode concepting and visual metaphor staging to structured creative divergence (preventing mode collapse), and demote profiling to calibrating the quality floor and curated visual recipes.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Distinct episode concepts without losing brand identity**: Every narration begins with structured concept divergence (*Verbalized Sampling* across 4–5 distinct visual concepts plus one episode-specific visual anchor) across three independent creative axes (`narrative_strategy` x `tone_register` x `surface_and_metaphor_mix`).
- **Broadcast-grade typography, color grading, and adaptive layout**:
  - Calibrate satellite basemap grading to rich deep bathymetric marine-teal ocean with visible cyan-turquoise continental shelves and warm natural relief land (not crushed dark mud), plus five distinct surface registers (satellite relief, cobalt blueprint grid, matte slate radar, daylight 3D horizon terrain, deep tactical 2D canvas).
  - Define adaptive ink color rules (clean white on dark surfaces, vivid yellow for acronyms/offsets/highlights, glowing cyan for velocities/altitudes, dark ink over bright crimson/amber territory fills, subdued translucent water labels).
  - Unify typography across policy, templates, captions, and map renderer: crisp `Inter` SemiBold/Bold `46 px` plain captions at `y ≈ 72.5%` (`MarginV = 525` on `1080x1920`) with soft multi-layer drop shadow and adaptive local contrast over bright snow/clouds; `Montserrat` `800`/`900` for display and hero titles (eliminating the `weight: 400` defect); `Lora` italic for hydrography; `IBM Plex Mono` for tabular telemetry.
  - Enforce clean upper-center focal composition (`y = 22%–62%`) with generous negative space and zero HUD/dashboard chrome.
- **Radical context efficiency (~65% token reduction)**: Trim the active profile footprint from ~57K tokens to ~18–22K total (with `<5K` tokens needed at initial directing entry via progressive disclosure from `README.md`).
- **Full engine-to-profile wiring**: Sync `brand_style_policy.json`, `directing_idioms.json`, `audio_themes.json`, HTML templates, `tools/geo-assets/` defaults, and `vedit/geo/` captions so zero cross-file contradictions remain.
- **Reframe repository skills**: Update `.agents/skills/brand-director/SKILL.md` and `.agents/skills/brand-profiling/SKILL.md` (and `profiles/README.md`) so profiling clearly calibrates the quality floor without misleading AI directors into template cloning or stale defaults.

### Non-Goals
- Rewriting `contracts/*.schema.json` to a breaking v2 schema or altering `editorial_explainer` or shared cross-brand engine fallback defaults (`vedit/mastering/ass_captions.py`, `packages/hf-compiler-ts/src/compiler.ts`).
- Building new dedicated WebGL/Canvas layer primitives (`radar_traffic`, `loupe_zoom`, `silhouette_tile`, `tactical_2d_canvas`, custom molten-glow shaders) inside `tools/geo-assets/scene/runtime_layers.mjs` in this milestone; those concepts enter as storyboard vocabulary realized via existing open primitives (`cutaway_2d` custom HTML, `map_sprites` custom SVG, `polygon`/`route` layers), leaving native WebGL primitives for a dedicated future renderer milestone.
- Removing existing HTML component files in `profiles/brands/geoverum/templates/components/` (existing compiler tests reference them; we fix defects and wire active components rather than breaking backward compatibility).
- Adding generative video synthesis or external vendor dependencies.

### Anti-Goals (Failure Modes Even If Validating Cleanly)
- **Template stiffness**: Two unrelated narrations producing the same opening hook, same surface sequence, or repetitive `pin_label` / `camera_drift` beats.
- **Prose duplication**: Repeating raw hex tables, font px tables, or internal `render_map_scene.mjs` shader parameter docs inside `CRAFT.md` or `DIRECTING.md` where they will drift from JSON and renderer code.
- **Pseudo-DSL bloat**: Keeping dozens of unexecuted Python-like `grammar_triggers` in `editorial_playbook.json` with uniform `0.9` weights.
- **Over-darkened or flat visuals**: Crushing daylight 3D terrain or satellite bathymetry into muddy dark grey, or rendering thin `weight: 400` hero metrics.

---

## 3. Constraints

- **Schema compatibility**: Every file in `profiles/brands/geoverum/` must pass `vedit contracts validate --json` and `vedit brand validate --brand-dir profiles/brands/geoverum --json` against Draft 2020-12 schemas (`additionalProperties: false` on `brand_style_policy.schema.json`, `directing_idioms.schema.json`, `editorial_playbook.schema.json`, `brand_template.schema.json`).
- **Repository engineering rules**: Timeless, neutral technical English; domain-based naming (`ref_<topic>`); zero third-party consumer/platform/app/channel brand names; zero local absolute paths; zero batch/session counters.
- **Test suite parity**: All existing verification suites (Rust probe, Python `ruff` + `pytest`, TypeScript `typecheck` + `build` + `npm test`, Node geo tests) must pass; Geoverum-specific tests asserting legacy caption pixel defaults (`52` -> `46`), `caption_fade_in_ms` (`120` -> `110`), or legacy Geoverum hex literals (`#F5C542`, `#03161F`) are updated explicitly alongside the single-source token change, while unbranded/cross-brand tests remain untouched.
- **Deterministic rendering**: Zero runtime CSS `filter: blur()` or `backdrop-filter`; bundled local OFL fonts only; pre-baked offline tiles and deterministic HyperFrames/MapLibre execution.

---

## 4. Approaches Considered

| Approach | Summary | Trade-offs | Decision |
| :--- | :--- | :--- | :--- |
| **A. Minimal In-Place Cleanup** | Fix font/color contradictions and prune duplicate triggers while keeping the existing prose-heavy 6-file layout and leaving `tools/geo-assets/` untouched. | Low effort and zero engine touch, but retains ~40K+ token context bloat, leaves profile disconnected from the map/caption renderer, and lacks a structured creativity/divergence loop. | Rejected |
| **B. Layered Studio Production Bible + Engine-Synced Overhaul** | Re-architect Geoverum content around **Tight Rails, Open Canvas** within existing v1.0 JSON schemas, cut token footprint ~65% via progressive disclosure, rewire idioms/templates/audio themes, calibrate `tools/geo-assets/` & `vedit/geo/` defaults to match the profile, and reframe `brand-director` + `brand-profiling` skills. | Balanced engineering scope; eliminates drift between profile, skills, and renderer; unlocks genuine episode-to-episode creative range while keeping 100% contract compatibility. | **Selected** |
| **C. Breaking Schema v2 Rewrite** | Replace `contracts/*.schema.json` with a unified v2 brand spec and rewrite Python/TS loaders and test fixtures across all brands. | High migration cost and regression surface across 30+ test modules; does not solve the core art-direction, typography, grading, or mode-collapse defects any better than Option B. | Rejected |

---

## 5. Architecture & Detailed Design

### 5.1 Three-Layer Model ("Tight Rails, Open Canvas")

```text
Layer 1: Brand DNA / Invariants (~20% locked — Single Source of Truth)
  Files: brand_style_policy.json + CRAFT.md (<3K tokens) + geo renderer defaults
  Role:  Bathymetric/relief color grading, 5 surface register palettes, adaptive ink
         rules, unified typography scale, clean lower-band captions, hard guardrails.
         Guarantees instant brand recognition regardless of episode improvisation.

Layer 2: Creative Sandbox (~80% open — Structured Divergence per Episode)
  Files: DIRECTING.md (<3K tokens) + editorial_playbook.json (~18-22 curated recipes)
         + external brand_memory.json
  Role:  Mandatory Stage 0 Divergent Concept Pitch (Verbalized Sampling: 4-5 distinct
         concepts + tail options p < 0.15 -> pick 1 unique Visual Anchor), 3 decoupled
         creative axes (Narrative Strategy x Tone/Register x Surface/Metaphor Mix),
         explicit permission for episode-custom SVG sprites / 2D cutaways / graphics.

Layer 3: Executable Quality Floor (Machine-Enforced, Never Prescriptive)
  Files: directing_idioms.json + audio_themes.json + templates/catalog.json & components/
  Role:  Mechanical gates (hook <0.8s, sync lead, numeric parity, safe margins,
         variation against recent episodes, visual contact-sheet critique), full
         device-to-template and scene-primitive wiring, bilingual readiness phrases.
```

### 5.2 Layer 1 — `brand_style_policy.json` & `CRAFT.md`

#### Single-Source Typography Calibration (`brand_style_policy.json`)
- `display_family`: `"Montserrat, sans-serif"` (clean wide geometric sans, matching `runtime_typography.mjs`).
- `title_family`: `"Montserrat, sans-serif"` (removes mixed `Montserrat, Archivo Black` ambiguity).
- `body_family`: `"Inter, sans-serif"`.
- `caption_font_family`: `"Inter, sans-serif"` (removes stale `Rubik` fallback ambiguity).
- `serif_family`: `"Lora, Georgia, serif"` (curved water labels and archival plates).
- `mono_family`: `"IBM Plex Mono, monospace"` (tabular coordinates, altitude chips, dual units).
- `caption_font_px_9x16`: **`46`** (down from `52`; `size_px_16x9: 42`, calm broadcast proportion matching measured documentary references), `caption_margin_v_px_9x16: 525` (`y ≈ 72.7%` inside `caption_band_y_pct_9x16: [0.66, 0.84]`), `caption_fade_in_ms: 110`, `caption_fade_out_ms: 0`, `caption_gap_ms: 67`, `caption_letter_spacing_em: -0.01`.
- `type_scale`:
  - `hero`: `108 px` / `100 px`, `weight: 900` (fixes the `400` thin-text bug), `line_height: 0.98`, `letter_spacing_em: -0.02`, `family_role: "title"`.
  - `display`: `72 px` / `68 px`, `weight: 800`, `line_height: 1.04`, `letter_spacing_em: -0.01`, `family_role: "display"`.
  - `title`: `46 px` / `42 px`, `weight: 700`, `line_height: 1.12`, `letter_spacing_em: 0.0`, `family_role: "display"`.
  - `caption`: `46 px` / `42 px`, `weight: 700`, `line_height: 1.22`, `letter_spacing_em: -0.01`, `family_role: "caption"`, `min_wcag_contrast: 7.0`.
  - `telemetry`: `32 px` / `28 px`, `weight: 600`, `line_height: 1.20`, `letter_spacing_em: 0.02`, `family_role: "mono"`, `min_wcag_contrast: 7.0`.
  - `body`: `28 px` / `26 px`, `weight: 500`, `line_height: 1.32`, `letter_spacing_em: 0.01`, `family_role: "body"`, `min_wcag_contrast: 7.0`.
  - `micro`: `22 px` / `20 px`, `weight: 600`, `line_height: 1.35`, `letter_spacing_em: 0.05`, `family_role: "body"`, `min_wcag_contrast: 7.0`.

#### Color Grading & Surface Registers (`brand_style_policy.json` + `CRAFT.md`)
- `palette_roles` in `brand_style_policy.json`:
  - `ground`: `#071D26` (rich abyssal marine-slate backing, avoiding dead black crush)
  - `surface_elevated`: `#0E4352` (deep bathymetric marine-teal ocean spine)
  - `ink`: `#F5F7FA` (crisp editorial snow-white primary ink & captions)
  - `accent`: `#F7DC28` (electric editorial yellow for acronyms, lassos, UTC offsets, highlights)
  - `secondary_accent`: `#D62828` (saturated crimson for primary hazard/territory fills & debunks)
  - `hydro_accent`: `#5EE2FF` (luminous sky-cyan for altitude chips, velocity callouts, silhouette tiling, water highlights)
  - `comparison_accent`: `#2563EB` (vivid cobalt blue for blueprint grids & secondary territories)
  - `muted_ink`: `#9BB3C0` (subdued regional & attribution ink)
- Remove the 33-item verbatim duplication between `hard_guardrails.banned_patterns` and `calibration.rejected_patterns`: keep canonical structural bans in `hard_guardrails.banned_patterns` (concise, deduplicated ~18–22 identifiers) and reserve `calibration.rejected_patterns` strictly for historically observed calibration rejections (empty or non-overlapping deltas).
- **Five Surface Registers documented cleanly in `CRAFT.md` (target `<3,000` tokens, zero token-table duplication, zero renderer shader internals)**:
  1. *Satellite Relief Spine*: Deep bathymetric marine-teal ocean (`#093B4B`–`#145161`) with visible cyan-turquoise continental shelf (`#287B8A`–`#3D919E`) and warm natural olive-green / sand-ochre 3D landmass relief.
  2. *Cobalt Blueprint Backdrop*: Vivid royal-cobalt drafting grid (`#2059DC`) framing tilted 3D maps, lifted silhouettes, and spatial scale proofs.
  3. *Matte Slate Radar / Traffic Mode*: Neutral dark charcoal (`#2C3137`–`#3A4047`) maximizing pop for bright yellow traffic swarms, circular white zoom loupes, and neon green/crimson coverage zones.
  4. *Daylight 3D Horizon Terrain*: Natural bright sky blue (`#2B7AE4` -> `#A3CEF5`) over sunlit snow/mountain relief for vertical altitude, barrier, and clearance proofs—never artificially darkened.
  5. *Deep Tactical 2D / Editorial Canvas*: Abyssal slate-teal (`#091E26`) or warm archival parchment (`#B9A386`) for schematic mechanism cutaways, human-system diagrams, and stylized closers.
- **Adaptive Ink & Glow Rules (`CRAFT.md`)**:
  - White `#F5F7FA` with soft directional shadow on dark terrain/ocean/radar.
  - Dark ink `#140E0E` over bright saturated crimson or amber fills (e.g., high-luma country fills).
  - Vivid yellow `#F7DC28` for hero acronyms, timezone/numeric offsets, and single-location callouts.
  - Glowing cyan `#5EE2FF` / `#7CE8FF` for atmospheric speeds and left-edge altitude chips (`33,000 ft (10,000 m)` with crisp white T-cap leader lines).
  - Semantic contrast pairs (`#4ADE4A` green vs `#EF233C` red/pink) for directional or permitted-vs-blocked splits.
  - Subdued low-contrast translucent teal-blue italic for open-water ocean/sea labels so water names never compete with foreground graphics.
  - Molten rim-glow polygon option (deep crimson core with bright amber-gold outer perimeter glow) alongside clean white-rimmed polygons and full-territory waving flag fills.
- **Layout & Safe Composition**:
  - Primary visual focus lives inside the upper-center action stage (`y = 22%–62%`, `x = 8%–92%`), leaving calm geographic negative space around it and keeping `y = 66%–84%` strictly clear for lower-band captions.

### 5.3 Layer 2 — `DIRECTING.md`, `editorial_playbook.json`, & Anti-Mode-Collapse Loop

- **`README.md` (<800 tokens — Progressive Disclosure Index Map)**:
  - Concise directory map telling human or AI operators *which single file to read for which stage* (Story & Concept -> `DIRECTING.md`; Visual Look & Grading -> `CRAFT.md`; Runtime Tokens -> `brand_style_policy.json`; Checks & Wiring -> `directing_idioms.json`; On-Demand Recipes -> `editorial_playbook.json`). Zero duplicated font/color specs that can go stale.
- **`DIRECTING.md` (<3,000 tokens — Creative Engine)**:
  - Introduces **Stage 0: Divergent Concept Pitch (Verbalized Sampling)** as a lightweight directing workflow in `DIRECTING.md` + `.agents/skills/brand-director/SKILL.md` *(Architect Call: kept out of `semantic_director.py` to avoid extra `DecisionPort` latency and preserve `storyboard.schema.json` simplicity)*:
    1. Generate **4–5 structurally different episode concepts** for the same narration, tagging each with an estimated typicality probability (`p`), forcing at least two low-typicality (`p < 0.15`) non-cliche visual concepts.
    2. Factor each concept along **3 independent axes**:
       - *Narrative Strategy* (e.g., Rule vs Reality, Enumerated Physical Proof, Mystery -> Mechanism -> Human System, Paradox -> Cause -> Consequence, Journey Chain, Impossibility -> Culprit).
       - *Tone / Register* (`documentary`, `investigative`, `wry`, `comic`).
       - *Episode Visual Anchor & Surface Mix* (one memorable evolving motif unique to this script—e.g., tiled country silhouettes, circular radar loupe, split-street comic avatars, glowing altitude ladder, tactical 2D board).
    3. Cross-check against external `brand_memory.json` (`recent_episodes`) so consecutive episodes never reuse hook mechanism + ending type or repeat visual anchors.
    4. Explicitly authorize **Open Primitives**: episodes may author custom episode-scoped SVGs (`map_sprites`), custom full-bleed `cutaway_2d` HTML scenes, or bespoke 2D editorial diagrams whenever the story calls for a metaphor not in the built-in catalog—bound only by Layer 1 Brand DNA.
- **`editorial_playbook.json` (Pruned & Rebalanced)**:
  - Collapse 74 overlapping pseudo-DSL `grammar_triggers` into **~20 distinct, non-overlapping curated Visual Recipes** with calibrated, spread weights (`0.55`–`0.95`) so BM25 retrieval in `exemplar_retrieval.py` ranks accurately by narrative need.
  - Each trigger uses crisp plain-English `condition` and concrete engine-grounded `action` (referencing real `render_map_scene.mjs` layers, custom `cutaway_2d` / `map_sprites` open primitives, or wired templates) rather than fictional Python method calls.
  - Prune and refresh `exemplar_bank` to **~20–24 high-craft, non-redundant exemplars** covering all seven schema roles (`hook`, `setup`, `proof`, `data_callout`, `broll_bridge`, `climax`, `outro`) and aligned with the updated visual standards (removing outdated tilted-badge / legacy chrome notes).

### 5.4 Layer 3 — `directing_idioms.json`, `audio_themes.json`, & `templates/`

- **`directing_idioms.json`**:
  - Keep all 23 executable idiom checks (`hook_event_early`, `numeric_parity`, `caption_band_clear`, `variation_against_recent`, etc.) and update `critique_rubric` so visual review checks **concept distinctiveness**, **adaptive ink legibility**, **bathymetric/surface register contrast**, and **non-collapsed display weights**.
  - Add bilingual (`en` + `id`) **`readiness_phrases`** (`throat_clearing`, `trailing_bloat`, `telling_exposition`) so `vedit storyboard readiness` works natively on Indonesian and English scripts.
  - Expand **`device_classes`** and **`device_realization`** to wire active overlay templates (including previously orphan high-value templates: `coordinate_pin_callout`, `organic_focus_lasso`, `blueprint_tabletop_frame`, `split_wipe_divider`, `multi_panel_split`, `cross_section_diagram`, `demographic_icon_grid`, `dual_metric_compare`, `physical_gauge_callout`, `scale_ladder_and_bands`, `soft_curtain_transition`) plus storyboard vocabulary `"surface": "scene"` devices (`silhouette_tile`, `radar_traffic`, `horizon_3d_flight`, `loupe_zoom`, `acronym_reveal`, `sector_polygons`, `tactical_2d_canvas`) realized through existing open primitives (`cutaway_2d` custom HTML, `map_sprites` custom SVG, `polygon`/`route`, pitched 3D terrain).
  - Expand **`auto_director.device_rules`** (with bilingual EN + ID stems) so automatic storyboards select concrete devices across core documentary concepts instead of collapsing to `pin_and_label` / `camera_drift`. *(Architect Call: omit unread `auto_director.default_device` / `default_story_shape` / `default_pacing` keys since `storyboard.py` reads `default_device` solely from `idioms[default_device_share].params.default_device`, keeping zero dead config keys.)*
- **`profiles/brands/geoverum/audio_themes.json` + CLI Wiring**:
  - Externalize Geoverum's domain audio themes (`maritime`, `aviation`, `geopolitics`, `weather`, `infrastructure`, `geology`, `time_and_systems`) with curated studio BGM search queries, ambience beds, and recorded foley mappings.
  - *(Architect Call)* Wire `--brand` / `--brand-dir` into `vedit geo auto-audio` (`packages/director-py/src/vedit/cli/geo.py`, defaulting to `profiles/brands/geoverum` when `--brand geoverum` is passed) and validate `audio_themes.json` structure in `validate_brand_tree` when present so the file is live end-to-end.
- **`profiles/brands/geoverum/templates/catalog.json` & `components/*.html`**:
  - *(Architect Call)* Propagate the calibrated `palette_roles` hexes into `templates/catalog.json` defaults and `blueprint_tabletop_frame.html` (`#2059DC` cobalt blueprint default) so catalog defaults never drift from `brand_style_policy.json`.
  - Fix the `font-weight: 400` defect across all 7 affected templates (`metric_callout.html`, `myth_debunk_badge.html`, `archival_stamp_impact.html`, `kinetic_portal_title.html`, `physical_gauge_callout.html`, `historical_parchment_plate.html`, `blueprint_tabletop_frame.html`) -> `font-weight: 900` (including `fitTextFontSize` in `metric_callout.html`).
  - Align `caption_rail.html` default font stack (`'{{CAPTION_FONT}}', 'Inter', sans-serif`) and refined soft-shadow contrast halo.

### 5.5 Renderer & Caption Calibration (`tools/geo-assets/` + `packages/director-py/src/vedit/geo/`)

Scope is strictly calibrated configuration and preset alignment (confirmed Option 1A — no new WebGL layer engines in `runtime_layers.mjs`):

- **`tools/geo-assets/build_tiles.mjs`**:
  - Refine `gradeRgb()` ocean and land calibration so shallow continental shelves retain vivid bathymetric cyan-turquoise separation (`#227282`–`#3A8F9D`) over deep marine-teal ocean (`#093B4B`–`#134F5F`), while landmasses preserve warm natural olive/ochre relief clarity without crushing midtones.
- **`tools/geo-assets/scene/runtime_typography.mjs`**:
  - Sync primary white ink (`#F5F7FA`) and add 5 reference-calibrated editorial typography presets to `CARTO_TYPO_PRESETS`:
    - `dark_on_fill`: `Montserrat 900`, `#140E0E`, subtle light outer lift for bold country labels over vivid crimson/amber fills.
    - `acronym_hero`: `Montserrat 900`, `#F7DC28`, tight tracking `-0.02em`, soft directional shadow for bold acronym/offset heroes.
    - `velocity_cyan`: `Montserrat 800 italic`, `#7CE8FF`, subtle cyan glow (`#38BDF8`) for wind/flow speeds.
    - `underlined_city`: `Inter 700`, `#F5F7FA`, clean shadow for pin-anchored city callouts.
    - `water_subtle`: `Lora 600 italic`, `rgba(110, 198, 224, 0.72)` for understated ocean/sea labels integrated into bathymetry.
- **`tools/geo-assets/scene/html_blueprint.mjs` & `tools/geo-assets/scene/html_map_scene.mjs`**:
  - Add lightweight theme/color config support: cobalt blueprint grid (`#2059DC`) option in `html_blueprint.mjs` (defaulting to cobalt when `theme: "cobalt"` is requested, preserving existing paper theme for backward compatibility), and configurable ocean ground (`#0E4352`) / daylight horizon sky (`#2B7AE4` -> `#A3CEF5`) register options in `html_map_scene.mjs`.
- **`packages/director-py/src/vedit/geo/captions.py` & `tools/geo-assets/render_captions_overlay.mjs`** *(Architect Call: Geoverum-scoped; shared `vedit/mastering/ass_captions.py` and `packages/hf-compiler-ts/src/compiler.ts` cross-brand fallbacks stay untouched)*:
  - Read both portrait (`caption_font_px_9x16`: `46`) and landscape (`type_scale.caption.size_px_16x9`: `42`) caption sizes from `brand_style_policy.json` in `vedit/geo/captions.py` and `vedit/director/planner.py`, falling back to `46 px` (`9:16`) / `42 px` (`16:9`) in Geoverum's caption builder (`MarginV = 525`, `Inter` Bold `#F5F7FA`).
  - Strengthen the multi-layer soft Gaussian shadow stack in `render_captions_overlay.mjs` (tight dark contact halo + wide soft ambient shadow, zero hard black outline) so captions remain legible even over sunlit snow peaks or bright clouds.

### 5.6 Reframing Repository Skills & Docs

- **`.agents/skills/brand-profiling/SKILL.md`**:
  - Explicitly redefine scope: **Offline Reference Calibration Only** — used *solely* when ingesting new reference videos to calibrate Layer 1 (Brand DNA tokens, grading, caption geometry, guardrails) and propose candidate Layer 2 curated recipes or Layer 3 idiom parameter ranges.
  - Explicitly prohibit using `brand-profiling` to bloat `editorial_playbook.json` with unexecuted pseudo-DSL triggers or to hardcode rigid shot sequences; document the **Tight Rails (20% DNA), Open Canvas (80% Creative Sandbox)** contract.
- **`.agents/skills/brand-director/SKILL.md`**:
  - Remove all stale contradictions (`Rubik 56 px`, `MarginV=348`, `flag_pin`).
  - Add **Stage 0: Divergent Concept Pitch (Verbalized Sampling)** ahead of storyboarding, explicitly pairing `brand_style_policy.json` single-source tokens with open-ended custom visual metaphors (`map_sprites`, `cutaway_2d`, `horizon_3d`, bespoke 2D scenes) and referencing `brand_memory.json` for cross-episode variation.
- **`profiles/README.md`**:
  - Document the 3-layer **Tight Rails, Open Canvas** brand directory architecture, including `audio_themes.json` and progressive-disclosure loading order.

---

## 6. Left to the Builder

- Exact wording and selection of the ~20 curated recipes and ~20–24 exemplars in `editorial_playbook.json`, provided they span all 7 schema roles, eliminate duplicate triggers, and reflect the 3-layer design with spread weights (`0.55`–`0.95`).
- Exact bilingual keyword stems in `directing_idioms.json` (`auto_director.device_rules` and `readiness_phrases`), provided every device class in `device_classes` has a matching entry in `device_realization` and zero schema/catalog errors occur.
- Exact RGB polynomial coefficients inside `build_tiles.mjs` `gradeRgb()`, provided ocean bathymetry shelf contrast and natural land warmth pass visual spot-checks and existing unit tests.
- Updating Geoverum-specific unit test assertions that hardcode the previous `52 px` caption default, `120 ms` fade-in, or legacy Geoverum hex values (`test_production_sound_and_wiring.py`, `test_geo_geometry.py`, `test_director_verifier.py`, `render_captions_overlay.test.mjs`) to reflect the new single-source standard while leaving cross-brand/unbranded tests (`test_compiler_mastering_and_cloud.py`) intact.

---

## 7. Verification & Acceptance Criteria

1. **Contract & Brand Validation**:
   - `packages/director-py/.venv/bin/vedit contracts validate --json` -> `"ok": true`.
   - `packages/director-py/.venv/bin/vedit brand validate --brand-dir profiles/brands/geoverum --json` -> `"ok": true`.
2. **Cross-File Consistency & Token Budget Audit**:
   - Zero stale `Rubik` / `56 px` / `MarginV=348` / `flag_pin` / `weight: 400` (on `TITLE_FONT`) regressions across `profiles/brands/geoverum/` and `.agents/skills/`.
   - Total root profile footprint (`README.md`, `CRAFT.md`, `DIRECTING.md`, `brand_style_policy.json`, `directing_idioms.json`, `editorial_playbook.json`) reduced by `>= 55%` (target `< 25K` tokens total; `README.md < 1K`, `CRAFT.md < 3.5K`, `DIRECTING.md < 3.5K`).
   - Zero unmapped devices in `device_classes` and zero high-value orphan overlay templates left unwired.
3. **Repository Hygiene Audit**:
   - Zero chat/session/batch counters, zero third-party consumer/app/platform/channel brand names, zero local absolute paths.
4. **Full Automated Test Suites**:
   - `packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal`
   - `packages/director-py/.venv/bin/pytest -v packages/director-py/tests`
   - `cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test`
   - `node --test tools/geo-assets/serve_tiles.test.mjs tools/geo-assets/render_captions_overlay.test.mjs tools/geo-assets/map_draw_math.test.mjs tools/geo-assets/scene/scene_modules.test.mjs tools/geo-assets/scene/determinism.test.mjs`
