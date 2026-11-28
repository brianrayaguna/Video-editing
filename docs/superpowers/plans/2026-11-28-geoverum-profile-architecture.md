# Geoverum Profile Architecture & Production Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect `profiles/brands/geoverum/` around a three-layer "Tight Rails, Open Canvas" model (~65% token reduction), fix active typography/palette/wiring defects across templates and CLI, calibrate Geoverum map grading, typography presets, and captions in `tools/geo-assets/` + `vedit/geo/`, and reframe `.agents/skills/brand-director/` and `brand-profiling/`.

**Architecture:** Preserve v1.0 Draft 2020-12 JSON contracts while eliminating multi-source-of-truth drift across three layers: (1) locked Brand DNA in `brand_style_policy.json` + compact `CRAFT.md` + calibrated geo/caption defaults, (2) open Creative Sandbox in compact `DIRECTING.md` (Stage 0 Verbalized Sampling across 3 decoupled axes) + pruned `editorial_playbook.json` (~20 curated recipes, ~22 exemplars), and (3) live executable quality gates in `directing_idioms.json` + `audio_themes.json` + fixed HTML templates.

**Tech Stack:** Python 3.11+ (Pydantic v2, Typer, pytest, ruff), Node.js ESM (`node --test`, sharp, Puppeteer), TypeScript (`packages/hf-compiler-ts`), Draft 2020-12 JSON Schema, HTML/SVG/GSAP HyperFrames templates.

**Spec:** `docs/superpowers/specs/2026-11-28-geoverum-profile-architecture-design.md`

## Global Constraints

- Every file in `profiles/brands/geoverum/` must pass `vedit contracts validate --json` and `vedit brand validate --brand-dir profiles/brands/geoverum --json` (`additionalProperties: false` on all 4 brand schemas).
- All repository text, JSON, code, and tests must use timeless, neutral technical English with domain-based naming (`ref_<topic>`), zero third-party consumer/app/platform/channel brand names, zero local absolute paths, and zero session/batch/phase counters.
- Preserve all 32 existing HTML files under `profiles/brands/geoverum/templates/components/` for compiler test compatibility; zero runtime CSS `filter: blur()` or `backdrop-filter`.
- Keep `46 px` (`9:16`) / `42 px` (`16:9`) caption calibration strictly Geoverum-scoped; do NOT modify cross-brand fallbacks in `vedit/mastering/ass_captions.py` or `packages/hf-compiler-ts/src/compiler.ts` or alter `profiles/brands/editorial_explainer/`.
- No new WebGL/Canvas layer engines inside `tools/geo-assets/scene/runtime_layers.mjs`; bespoke visual metaphors are storyboard vocabulary realized through existing open primitives (`cutaway_2d`, `map_sprites`, `polygon`/`route`, pitched terrain).

## Review Focus

1. **Landscape `16:9` policy caption size ignored by planner & geo caption builder**: When a Geoverum `16:9` episode runs through `build_captions_for_brand` or `planner.py`, omitting landscape `type_scale.caption.size_px_16x9` lookup would silently fall back to `48 px` instead of `42 px`. (Pinned by test in Task 4.)
2. **Invalid or malformed `audio_themes.json` silently breaking `vedit geo auto-audio`**: `validate_brand_tree` does not currently check `audio_themes.json`, and `geo auto-audio` currently passes `brand_dir=None`, leaving brand audio themes unwired or unvalidated. (Pinned by tests in Task 2.)
3. **Hero templates collapsing to `Montserrat Regular 400` under `font-synthesis: none`**: Any remaining `font-weight: 400` on `{{TITLE_FONT}}` in `templates/components/*.html` or `type_scale.hero` causes thin hero typography in compiled HyperFrames output. (Pinned by test in Task 1.)
4. **Uncalibrated `build_tiles.mjs` crushing shallow marine shelves or clipping RGB channels**: Changing `gradeRgb()` polynomials must keep pure ocean pixels in the deep marine-teal range, preserve cyan-turquoise shallow shelf contrast above deep ocean, keep outputs strictly within `[0, 255]`, and stay deterministic. (Pinned by test in Task 5.)
5. **Backward compatibility of `html_blueprint.mjs` and `html_map_scene.mjs` when new register options are omitted**: Existing callers that pass no `theme` to `buildBlueprintHtml` or no `atmosphere`/`background_color` to `buildMapSceneHtml` must continue rendering cleanly without undefined CSS/JS tokens. (Pinned by tests in Task 5.)

---

### Task 1: Layer 1 Brand DNA (`brand_style_policy.json`) & Template Weight/Palette Sync

**Files:**
- Modify: `profiles/brands/geoverum/brand_style_policy.json`
- Modify: `profiles/brands/geoverum/templates/catalog.json`
- Modify: `profiles/brands/geoverum/templates/components/metric_callout.html`
- Modify: `profiles/brands/geoverum/templates/components/myth_debunk_badge.html`
- Modify: `profiles/brands/geoverum/templates/components/archival_stamp_impact.html`
- Modify: `profiles/brands/geoverum/templates/components/kinetic_portal_title.html`
- Modify: `profiles/brands/geoverum/templates/components/physical_gauge_callout.html`
- Modify: `profiles/brands/geoverum/templates/components/historical_parchment_plate.html`
- Modify: `profiles/brands/geoverum/templates/components/blueprint_tabletop_frame.html`
- Modify: `profiles/brands/geoverum/templates/components/caption_rail.html`
- Test: `packages/director-py/tests/test_contracts.py`
- Test: `packages/director-py/tests/test_director_verifier.py`
- Test: `packages/hf-compiler-ts/src/compiler.test.ts`

**Interfaces:**
- Consumes: `contracts/brand_style_policy.schema.json`, `contracts/brand_template.schema.json`
- Produces: Single-source Geoverum `palette_roles` (`ground: #071D26`, `surface_elevated: #0E4352`, `ink: #F5F7FA`, `accent: #F7DC28`, `secondary_accent: #D62828`, `hydro_accent: #5EE2FF`, `comparison_accent: #2563EB`, `muted_ink: #9BB3C0`), unified typography tokens (`display_family` & `title_family`: `"Montserrat, sans-serif"`, `caption_font_family`: `"Inter, sans-serif"`, `caption_font_px_9x16: 46`, `type_scale.caption.size_px_16x9: 42`, `caption_fade_in_ms: 110`, `type_scale.hero.weight: 900`), deduplicated `hard_guardrails.banned_patterns` vs `calibration.rejected_patterns`, and `font-weight: 900` across all 7 hero HTML templates.

- [ ] **Step 1: Add failing contract/regression tests for Geoverum single-source typography, palette, and non-400 hero template weights**

In `packages/director-py/tests/test_contracts.py`, add:
```python
def test_geoverum_policy_and_templates_single_source_invariants() -> None:
    root = find_repo_root()
    gv = root / "profiles" / "brands" / "geoverum"
    policy = json.loads((gv / "brand_style_policy.json").read_text(encoding="utf-8"))
    typo = policy["soft_priors"]["visual_tokens"]["typography"]
    pal = policy["soft_priors"]["visual_tokens"]["palette_roles"]

    assert typo["display_family"] == "Montserrat, sans-serif"
    assert typo["title_family"] == "Montserrat, sans-serif"
    assert typo["caption_font_family"] == "Inter, sans-serif"
    assert typo["caption_font_px_9x16"] == 46
    assert typo["caption_fade_in_ms"] == 110
    assert typo["type_scale"]["hero"]["weight"] == 900
    assert typo["type_scale"]["caption"]["size_px_9x16"] == 46
    assert typo["type_scale"]["caption"]["size_px_16x9"] == 42
    assert pal["ground"] == "#071D26"
    assert pal["surface_elevated"] == "#0E4352"
    assert pal["ink"] == "#F5F7FA"
    assert pal["accent"] == "#F7DC28"

    # No verbatim duplication between hard_guardrails.banned_patterns and calibration.rejected_patterns.
    banned = set(policy["hard_guardrails"]["banned_patterns"])
    rejected = set(policy["calibration"]["rejected_patterns"])
    assert banned.isdisjoint(rejected)

    # Zero TITLE_FONT templates declaring font-weight: 400 (which collapses Montserrat to Regular).
    for html_path in sorted((gv / "templates" / "components").glob("*.html")):
        txt = html_path.read_text(encoding="utf-8")
        if "{{TITLE_FONT}}" in txt:
            assert "font-weight: 400" not in txt, f"{html_path.name} uses font-weight: 400 with TITLE_FONT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_contracts.py::test_geoverum_policy_and_templates_single_source_invariants`
Expected: FAIL on `display_family`, `caption_font_px_9x16`, `type_scale.hero.weight`, `banned.isdisjoint(rejected)`, and `font-weight: 400`.

- [ ] **Step 3: Update `profiles/brands/geoverum/brand_style_policy.json`**

Apply the exact spec Section 5.2 tokens:
- `editorial_identity`: concise single-paragraph statement matching the Tight Rails, Open Canvas identity (no stale `52 px` or legacy prose).
- `palette_roles`: `#071D26`, `#0E4352`, `#F5F7FA`, `#F7DC28`, `#D62828`, `#5EE2FF`, `#2563EB`, `#9BB3C0`.
- `typography`: `display_family`, `title_family` -> `"Montserrat, sans-serif"`; `body_family`, `caption_font_family` -> `"Inter, sans-serif"`; `serif_family` -> `"Lora, Georgia, serif"`; `mono_family` -> `"IBM Plex Mono, monospace"`; `caption_font_px_9x16: 46`, `caption_margin_v_px_9x16: 525`, `caption_fade_in_ms: 110`, `caption_fade_out_ms: 0`, `caption_gap_ms: 67`, `caption_letter_spacing_em: -0.01`, and the exact 7-step `type_scale` from Spec Section 5.2.
- `hard_guardrails.banned_patterns`: concise deduplicated list (~20 canonical identifiers); `calibration.rejected_patterns`: `[]` (no overlap).

- [ ] **Step 4: Sync `profiles/brands/geoverum/templates/catalog.json` and fix the 8 HTML templates**

- Update all `token_ref` defaults in `templates/catalog.json` to match the new `palette_roles` hexes (`#F5F7FA`, `#071D26`, `#F7DC28`, `#9BB3C0`).
- Replace `font-weight: 400` with `font-weight: 900` (and `fontWeight: 400` -> `fontWeight: 900` in `metric_callout.html` `fitTextFontSize`) across `metric_callout.html`, `myth_debunk_badge.html`, `archival_stamp_impact.html`, `kinetic_portal_title.html`, `physical_gauge_callout.html`, `historical_parchment_plate.html`, and `blueprint_tabletop_frame.html`.
- Update `blueprint_tabletop_frame.html` grid background default to cobalt `#2059DC` (from `#14427A`) and `caption_rail.html` default font stack to `'{{CAPTION_FONT}}', 'Inter', sans-serif` (removing stale `'Rubik'` fallback) with strengthened multi-layer soft shadow (`0 1px 2px rgba(0, 0, 0, 0.92), 0 3px 10px rgba(0, 0, 0, 0.78), 0 8px 24px rgba(0, 0, 0, 0.48)`).

- [ ] **Step 5: Update Geoverum-specific policy assertions in `packages/director-py/tests/test_director_verifier.py`**

Update the 3 assertions in `test_director_verifier.py` (around lines 450, 470–471) that hardcode Geoverum's previous `caption_fade_in_ms == 120`, `#F5C542`, and `#03161F` to assert the new single-source values (`110`, `#F7DC28`, `#071D26`).

- [ ] **Step 6: Verify tests and compiler build pass**

Run:
```bash
packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_contracts.py packages/director-py/tests/test_director_verifier.py
cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test
```
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add profiles/brands/geoverum/brand_style_policy.json profiles/brands/geoverum/templates/ packages/director-py/tests/test_contracts.py packages/director-py/tests/test_director_verifier.py
git commit -m "feat(geoverum): calibrate brand DNA tokens and fix hero template weights"
```

---

### Task 2: Layer 3 Executable Wiring (`directing_idioms.json`, `audio_themes.json`, CLI & Contract Validation)

**Files:**
- Modify: `profiles/brands/geoverum/directing_idioms.json`
- Create: `profiles/brands/geoverum/audio_themes.json`
- Modify: `packages/director-py/src/vedit/cli/geo.py:291-311`
- Modify: `packages/director-py/src/vedit/contracts.py:176-266`
- Test: `packages/director-py/tests/test_contracts.py`
- Test: `packages/director-py/tests/test_storyboard.py`
- Test: `packages/director-py/tests/test_storyboard_plan.py`
- Test: `packages/director-py/tests/test_idiom_registry_and_themes.py`

**Interfaces:**
- Consumes: `profiles/brands/geoverum/brand_style_policy.json`, `profiles/brands/geoverum/templates/catalog.json`, `vedit.geo.themes.load_audio_themes(brand_dir: Path | None = None) -> dict[str, dict[str, Any]]`, `vedit.geo_production.plan_and_fetch_thematic_audio(..., brand_dir: Path | None = None)`
- Produces:
  - `profiles/brands/geoverum/audio_themes.json` validated by `validate_brand_tree()` (adds `"audio_themes": str | None` to the returned dict; raises `ValueError` if JSON is malformed or any theme lacks non-empty `keywords`, `curious_query`, `tension_query`, `ambience_query`).
  - `vedit geo auto-audio` CLI options `--brand: str | None = None` and `--brand-dir: Path | None = None` resolving `brand_dir` cleanly into `plan_and_fetch_thematic_audio(..., brand_dir=resolved_brand_dir)`.
  - Wired `profiles/brands/geoverum/directing_idioms.json` with bilingual `readiness_phrases`, expanded `device_classes` + `device_realization` (wiring all high-value overlay templates + 7 scene vocabulary devices), expanded bilingual `auto_director.device_rules`, and updated `critique_rubric` (zero dead `auto_director` keys).

- [ ] **Step 1: Write failing tests for `audio_themes.json` validation, CLI `--brand` wiring, and `directing_idioms.json` wiring**

In `packages/director-py/tests/test_idiom_registry_and_themes.py`, add tests:
```python
def test_geoverum_audio_themes_override_loads_and_validates() -> None:
    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    themes = load_audio_themes(brand_dir=gv_dir)
    assert "time_and_systems" in themes
    assert "aviation" in themes
    validated = validate_brand_tree(gv_dir, repo_root=root)
    assert validated["audio_themes"] == "profiles/brands/geoverum/audio_themes.json"


def test_validate_brand_tree_rejects_malformed_audio_themes(tmp_path: Path) -> None:
    root = find_repo_root()
    gv = root / "profiles" / "brands" / "geoverum"
    broken = tmp_path / "broken_brand"
    broken.mkdir()
    (broken / "brand_style_policy.json").write_text(
        (gv / "brand_style_policy.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (broken / "audio_themes.json").write_text('{"bad_theme": {"keywords": []}}', encoding="utf-8")
    with pytest.raises(ValueError, match="audio_themes.json"):
        validate_brand_tree(broken, repo_root=root)
```
In `packages/director-py/tests/test_storyboard_plan.py`, add a test verifying:
- `directing_idioms.json` has bilingual `readiness_phrases` (`throat_clearing`, `trailing_bloat`, `telling_exposition`),
- all 11 previously-orphan high-value overlay templates (`coordinate_pin_callout`, `organic_focus_lasso`, `blueprint_tabletop_frame`, `split_wipe_divider`, `multi_panel_split`, `cross_section_diagram`, `demographic_icon_grid`, `dual_metric_compare`, `physical_gauge_callout`, `scale_ladder_and_bands`, `soft_curtain_transition`) are realized in `device_realization`,
- all 7 new scene vocabulary devices (`silhouette_tile`, `radar_traffic`, `horizon_3d_flight`, `loupe_zoom`, `acronym_reveal`, `sector_polygons`, `tactical_2d_canvas`) exist in `device_classes` and `device_realization`,
- zero unread keys (`default_device`, `default_story_shape`, `default_pacing`) exist in `auto_director`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_idiom_registry_and_themes.py packages/director-py/tests/test_storyboard_plan.py`
Expected: FAIL on missing `audio_themes.json`, missing validation, and unwired devices/templates.

- [ ] **Step 3: Create `profiles/brands/geoverum/audio_themes.json` and wire `contracts.py` + `cli/geo.py`**

- Create `profiles/brands/geoverum/audio_themes.json` defining 7 Geoverum documentary audio themes (`maritime`, `aviation`, `geopolitics`, `weather`, `infrastructure`, `geology`, `time_and_systems`) with bilingual `keywords`, `curious_query`, `tension_query`, `ambience_query`, `ambience_gain_db`, and `foley`.
- In `packages/director-py/src/vedit/contracts.py:validate_brand_tree`: add `"audio_themes": None` to `validated`; when `(brand_dir / "audio_themes.json").is_file()`, parse and verify it is a non-empty dict whose entries are dicts containing non-empty list `keywords` and non-empty strings `curious_query`, `tension_query`, `ambience_query`, raising `ValueError("audio_themes.json ...")` on failure.
- In `packages/director-py/src/vedit/cli/geo.py:geo_auto_audio_cmd`: add optional `brand: Annotated[str | None, typer.Option("--brand")] = None` and `brand_dir: Annotated[Path | None, typer.Option("--brand-dir")] = None`; resolve `resolved_brand_dir = brand_dir.expanduser().resolve() if brand_dir is not None else (find_repo_root() / "profiles" / "brands" / brand if brand else None)` and pass `brand_dir=resolved_brand_dir` to `plan_and_fetch_thematic_audio(...)`.

- [ ] **Step 4: Update `profiles/brands/geoverum/directing_idioms.json`**

- Wire all 11 previously orphan overlay templates into `device_classes` + `device_realization` (with exact declared variable names from `templates/catalog.json` so `check_realization_catalog` passes with zero errors).
- Add the 7 scene vocabulary devices (`silhouette_tile`, `radar_traffic`, `horizon_3d_flight`, `loupe_zoom`, `acronym_reveal`, `sector_polygons`, `tactical_2d_canvas`) to `device_classes` and `device_realization` (`{"surface": "scene"}`).
- Add bilingual `readiness_phrases` (`throat_clearing`, `trailing_bloat`, `telling_exposition`) covering EN + ID filler phrases.
- Expand `auto_director.device_rules` with bilingual EN + ID stems covering core documentary visual devices (`flag_fill`, `silhouette_tile`, `radar_traffic`, `horizon_3d_flight`, `cross_section`, `focus_lasso`, `split_compare`, `demographic_split`, `dual_metric`, `physical_gauge`, `scale_ladder`, `acronym_reveal`, `count_up`, etc.) while keeping existing tested rules intact and omitting unread `auto_director` keys.
- Refine `critique_rubric` to explicitly audit concept distinctiveness, adaptive ink legibility (including dark ink on bright fills and caption contrast over snow), bathymetric/surface register contrast, and non-collapsed display font weights.

- [ ] **Step 5: Run tests and brand validation**

Run:
```bash
packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_idiom_registry_and_themes.py packages/director-py/tests/test_storyboard.py packages/director-py/tests/test_storyboard_plan.py packages/director-py/tests/test_script_readiness.py packages/director-py/tests/test_idiom_calibration.py
packages/director-py/.venv/bin/vedit brand validate --brand-dir profiles/brands/geoverum --json
```
Expected: All PASS, `vedit brand validate` returns `"ok": true`.

- [ ] **Step 6: Commit**

```bash
git add profiles/brands/geoverum/directing_idioms.json profiles/brands/geoverum/audio_themes.json packages/director-py/src/vedit/cli/geo.py packages/director-py/src/vedit/contracts.py packages/director-py/tests/test_idiom_registry_and_themes.py packages/director-py/tests/test_storyboard_plan.py
git commit -m "feat(geoverum): wire idioms, overlay devices, readiness phrases, and brand audio themes"
```

---

### Task 3: Layer 2 Creative Sandbox (`editorial_playbook.json`, `README.md`, `DIRECTING.md`, `CRAFT.md`)

**Files:**
- Modify: `profiles/brands/geoverum/editorial_playbook.json`
- Modify: `profiles/brands/geoverum/README.md`
- Modify: `profiles/brands/geoverum/DIRECTING.md`
- Modify: `profiles/brands/geoverum/CRAFT.md`
- Test: `packages/director-py/tests/test_contracts.py`
- Test: `packages/director-py/tests/test_exemplar_retrieval.py`

**Interfaces:**
- Consumes: `contracts/editorial_playbook.schema.json`, Layer 1 tokens in `brand_style_policy.json`, Layer 3 devices in `directing_idioms.json`
- Produces:
  - Pruned `editorial_playbook.json` (18–22 curated non-overlapping `grammar_triggers` with spread weights in `[0.55, 0.95]` and plain-English/engine-grounded actions; 20–24 refreshed `exemplar_bank` entries covering all 7 schema roles).
  - Compact progressive-disclosure `README.md` (`< 1,000` tokens), `DIRECTING.md` (`< 3,500` tokens, Stage 0 Divergent Concept Pitch via Verbalized Sampling + 3 decoupled axes + Open Primitives authorization), and `CRAFT.md` (`< 3,500` tokens, 5 surface registers, adaptive ink/glow rules, upper-center layout stage, zero raw JSON token table duplication or shader API internals). Total root profile footprint `< 25,000` tokens (`>= 55%` reduction from ~57K).

- [ ] **Step 1: Add failing tests for playbook curation quality, role coverage, and profile token budget**

In `packages/director-py/tests/test_contracts.py`, add:
```python
def test_geoverum_profile_token_budget_and_playbook_curation() -> None:
    root = find_repo_root()
    gv = root / "profiles" / "brands" / "geoverum"
    pb = json.loads((gv / "editorial_playbook.json").read_text(encoding="utf-8"))

    triggers = pb["grammar_triggers"]
    exemplars = pb["exemplar_bank"]
    assert 16 <= len(triggers) <= 24
    assert 18 <= len(exemplars) <= 26
    weights = [float(t["weight"]) for t in triggers]
    assert max(weights) - min(weights) >= 0.30
    roles = {e["role"] for e in exemplars}
    assert roles == {"hook", "setup", "proof", "data_callout", "broll_bridge", "climax", "outro"}

    # Progressive disclosure token budgets (~4 chars/token).
    readme_tok = len((gv / "README.md").read_text(encoding="utf-8")) // 4
    directing_tok = len((gv / "DIRECTING.md").read_text(encoding="utf-8")) // 4
    craft_tok = len((gv / "CRAFT.md").read_text(encoding="utf-8")) // 4
    total_tok = sum(
        len((gv / name).read_text(encoding="utf-8")) // 4
        for name in (
            "README.md",
            "DIRECTING.md",
            "CRAFT.md",
            "brand_style_policy.json",
            "directing_idioms.json",
            "editorial_playbook.json",
        )
    )
    assert readme_tok < 1000
    assert directing_tok < 3500
    assert craft_tok < 3500
    assert total_tok < 25000

    # Zero stale legacy caption/font contradictions across markdown docs.
    for md in ("README.md", "DIRECTING.md", "CRAFT.md"):
        txt = (gv / md).read_text(encoding="utf-8")
        assert "Rubik" not in txt, f"stale Rubik reference in {md}"
        assert "56 px" not in txt and "56px" not in txt, f"stale 56px reference in {md}"
        assert "MarginV=348" not in txt and "MarginV = 348" not in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_contracts.py::test_geoverum_profile_token_budget_and_playbook_curation`
Expected: FAIL (`len(triggers) == 74`, `total_tok ~ 57000`, stale `Rubik`/`56 px`).

- [ ] **Step 3: Author pruned `profiles/brands/geoverum/editorial_playbook.json`**

Replace the 74 overlapping pseudo-DSL triggers and 83 legacy exemplars with:
- **20 curated, non-overlapping Visual Recipes** covering core concept archetypes & staging devices (bathymetric map spine, molten rim-glow territory, silhouette tiling, radar traffic + circular zoom loupe, daylight 3D horizon altitude ladder, chevron jet stream + velocity callout, split-street comic dialogue, acronym hero + colored control sectors, tactical 2D closer, full-territory waving flag fill, perimeter trace-then-fill, dual-unit axis brackets, 2D subsurface cutaway, historical parchment + timeline, demographic icon split, vertical wipe-to-void counter, radial whip-zoom B-roll triplet, 3D in-map infrastructure, feathered black-disc register swap, story-driven ending note), using clean plain-English `condition` + concrete engine-grounded `action` and spread weights `0.55`–`0.95`.
- **22 curated `exemplar_bank` entries** spanning all 7 roles (`hook`, `setup`, `proof`, `data_callout`, `broll_bridge`, `climax`, `outro`), zero tilted-badge or banned-chrome descriptions, domain-named `ref_<topic>` IDs only.

- [ ] **Step 4: Rewrite `README.md`, `DIRECTING.md`, and `CRAFT.md` for progressive disclosure and zero drift**

- `README.md` (`< 800` tokens): 3-layer **Tight Rails, Open Canvas** overview, file index map (what to read at each stage), and open-data geospatial provenance. Zero duplicated token tables.
- `DIRECTING.md` (`< 3,000` tokens): Stage 0 **Divergent Concept Pitch (Verbalized Sampling: 4–5 concepts with `p` scores including `>= 2` tail concepts `p < 0.15` -> 1 unique Visual Anchor)**, 3 independent creative axes (`Narrative Strategy x Tone/Register x Surface & Metaphor Mix`), compact story shapes & hook/ending tables, clause-level `story_need -> visual_answer` method, Open Primitives authorization (custom SVG sprites / custom `cutaway_2d` HTML / bespoke 2D diagrams), sync timing offsets, and cross-episode variation contract (`brand_memory.json`).
- `CRAFT.md` (`< 3,000` tokens): Single-source reference to `brand_style_policy.json` (no duplicated hex/px tables), the 5 Surface Registers (Satellite Relief Spine, Cobalt Blueprint Backdrop, Matte Slate Radar, Daylight 3D Horizon Terrain, Deep Tactical 2D / Parchment), Adaptive Ink & Glow Rules (white / dark-on-fill / yellow / cyan / semantic green-vs-red / subdued water), Upper-Center Action Stage (`y = 22%–62%`) + lower-band `46 px` soft-shadow caption separation, motion continuity & camera feel, studio audio/foley rules (`audio_themes.json`), and concise Rejected Chrome list.

- [ ] **Step 5: Run tests and validation**

Run:
```bash
packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_contracts.py packages/director-py/tests/test_exemplar_retrieval.py
packages/director-py/.venv/bin/vedit contracts validate --json
```
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add profiles/brands/geoverum/editorial_playbook.json profiles/brands/geoverum/README.md profiles/brands/geoverum/DIRECTING.md profiles/brands/geoverum/CRAFT.md packages/director-py/tests/test_contracts.py
git commit -m "feat(geoverum): restructure playbook and craft/directing docs into tight-rails open-canvas architecture"
```

---

### Task 4: Geoverum-Scoped Caption Policy Propagation (`captions.py`, `planner.py`, `render_captions_overlay.mjs`)

**Files:**
- Modify: `packages/director-py/src/vedit/geo/captions.py:76-255`
- Modify: `packages/director-py/src/vedit/director/planner.py:485-505`
- Modify: `tools/geo-assets/render_captions_overlay.mjs:299-396`
- Test: `packages/director-py/tests/test_production_sound_and_wiring.py`
- Test: `packages/director-py/tests/test_geo_geometry.py`
- Test: `tools/geo-assets/render_captions_overlay.test.mjs`

**Interfaces:**
- Consumes: `brand_style_policy.json` (`caption_font_px_9x16`, `caption_margin_v_px_9x16`, `type_scale.caption.size_px_16x9`, `palette_roles.ink`, `palette_roles.ground`)
- Produces:
  - `build_captions_for_brand(...)` reads `caption_font_px_9x16` (`46`) on portrait AND `type_scale.caption.size_px_16x9` (`42`) on landscape from the brand policy, falling back to `46` / `42` for Geoverum (`MarginV = 525`, `#F5F7FA` ink, `#071D26` ground).
  - `planner.py` propagates both portrait `caption_font_px_9x16` and landscape `type_scale.caption.size_px_16x9` into `caption_props["caption_font_px"]` when defined by the active `BrandStylePolicy` (leaving `editorial_explainer` and unbranded fallbacks in `ass_captions.py` unchanged).
  - `render_captions_overlay.mjs` defaults fallback size to `46 * scale` (portrait) / `42 * scale` (landscape) when ASS omits fontSize, and applies an enhanced multi-layer soft Gaussian shadow stack (`0 1px 2px rgba(0, 0, 0, 0.94), 0 2px 6px rgba(0, 0, 0, 0.82), 0 6px 18px rgba(0, 0, 0, 0.56), 0 0 24px rgba(0, 0, 0, 0.32)`) for snow/cloud legibility without hard outlines.

- [ ] **Step 1: Write failing tests for Geoverum portrait (`46 px`) AND landscape (`42 px`) caption sizing**

- In `packages/director-py/tests/test_production_sound_and_wiring.py`: update existing Geoverum portrait assertion (`52` -> `46`) and add a landscape `16:9` test asserting `caption_font_px == 42` for Geoverum while confirming `editorial_explainer` (`46` from its `type_scale.caption.size_px_16x9`) resolves from its own policy without breaking.
- In `packages/director-py/tests/test_geo_geometry.py`: add/update Geoverum `build_captions_for_brand(..., brand="geoverum")` tests asserting `Style: Default,Inter,46,` (`9:16`, `#F5F7FA`, `#071D26`, `MarginV=525`) and `Style: Default,Inter,42,` (`16:9`), keeping unbranded `build_ass_from_transcript` tests untouched.
- In `tools/geo-assets/render_captions_overlay.test.mjs`: update the Geoverum ASS fixture test for `46 px` and add a check verifying fallback defaults (`46` / `42`) and soft multi-layer shadow CSS.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_production_sound_and_wiring.py packages/director-py/tests/test_geo_geometry.py
node --test tools/geo-assets/render_captions_overlay.test.mjs
```
Expected: FAIL on `46` / `42` caption size expectations.

- [ ] **Step 3: Update `vedit/geo/captions.py`, `vedit/director/planner.py`, and `tools/geo-assets/render_captions_overlay.mjs`**

- In `vedit/geo/captions.py:build_captions_for_brand`:
  - Update Geoverum defaults (`eff_font_size = round(46 * scale) if is_portrait else round(42 * scale)`, `eff_fg = "#F5F7FA"`, `eff_outline = "#071D26"`).
  - When `brand` policy is loaded: read `caption_font_px_9x16` on portrait (`is_portrait`), and on landscape read `(typo.get("type_scale") or {}).get("caption", {}).get("size_px_16x9")` scaled by `scale`.
  - Update `build_brand_ass_captions` / `build_geoverum_ass_captions` default `fg_color="#F5F7FA"`, `outline_color="#071D26"`, `fade_in_ms=110`.
- In `vedit/director/planner.py` (around line 493):
  - When `is_portrait` and `typo.caption_font_px_9x16 is not None`, set `caption_font_px` scaled to height (existing behavior).
  - Else when `not is_portrait` and `typo.type_scale is not None` and `typo.type_scale.caption is not None`, set `caption_props["caption_font_px"] = max(16, round(typo.type_scale.caption.size_px_16x9 * (platform_target.height / 1080.0)))`.
- In `tools/geo-assets/render_captions_overlay.mjs`:
  - Update fallback font size expression to `isPortrait ? 46 * scale : 42 * scale`, default `colorHex` to `"#F5F7FA"`, and strengthen the 4-layer soft Gaussian `text-shadow` stack in `#cap`.

- [ ] **Step 4: Run Python & Node tests to verify everything passes (including unbranded `test_compiler_mastering_and_cloud.py`)**

Run:
```bash
packages/director-py/.venv/bin/pytest -v packages/director-py/tests/test_production_sound_and_wiring.py packages/director-py/tests/test_geo_geometry.py packages/director-py/tests/test_compiler_mastering_and_cloud.py
node --test tools/geo-assets/render_captions_overlay.test.mjs
```
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/director-py/src/vedit/geo/captions.py packages/director-py/src/vedit/director/planner.py tools/geo-assets/render_captions_overlay.mjs packages/director-py/tests/test_production_sound_and_wiring.py packages/director-py/tests/test_geo_geometry.py tools/geo-assets/render_captions_overlay.test.mjs
git commit -m "feat(geoverum): sync policy-driven 46px/42px captions and snow-safe soft shadow"
```

---

### Task 5: Renderer Color Grading, Surface Register Options & Adaptive Typography Presets (`tools/geo-assets/`)

**Files:**
- Modify: `tools/geo-assets/build_tiles.mjs:58-115`
- Modify: `tools/geo-assets/scene/runtime_typography.mjs:46-62`
- Modify: `tools/geo-assets/scene/html_blueprint.mjs:4-155`
- Modify: `tools/geo-assets/scene/html_map_scene.mjs:100-220`
- Test: `tools/geo-assets/scene/scene_modules.test.mjs`
- Test: `tools/geo-assets/serve_tiles.test.mjs`

**Interfaces:**
- Consumes: Layer 1 palette tokens (`#0E4352` ocean ground, `#F5F7FA` primary ink, `#F7DC28` acronym hero, `#7CE8FF` velocity cyan, `#2059DC` cobalt blueprint, `#2B7AE4` -> `#A3CEF5` daylight sky).
- Produces:
  - Calibrated `gradeRgb(data, z, bmngData = null)` preserving deep marine-teal ocean (`#093B4B`–`#134F5F`), vibrant shallow cyan-turquoise bathymetric shelves, and warm natural land relief.
  - 5 new presets in `CARTO_TYPO_PRESETS`: `dark_on_fill`, `acronym_hero`, `velocity_cyan`, `underlined_city`, `water_subtle` (plus `#F5F7FA` synced white ink on core presets).
  - `buildBlueprintHtml(..., actSpec)` supporting `actSpec.theme === "cobalt"` (`#2059DC` blueprint drafting canvas with crisp white grid) while preserving existing paper theme when omitted.
  - `buildMapSceneHtml(..., mapOpts)` supporting `mapOpts.surface_register === "daylight_terrain"` (natural daylight sky `#2B7AE4` -> `#A3CEF5`) and configurable `mapOpts.background_color` (default `#0E4352`), preserving full backward compatibility when omitted.

- [ ] **Step 1: Write failing Node tests for `gradeRgb`, 5 new typography presets, cobalt blueprint theme, and daylight sky register**

In `tools/geo-assets/scene/scene_modules.test.mjs`, add tests asserting:
- `buildTypographyRuntime()` defines all 5 new presets (`dark_on_fill`, `acronym_hero`, `velocity_cyan`, `underlined_city`, `water_subtle`) with expected colors (`#140E0E`, `#F7DC28`, `#7CE8FF`, `#F5F7FA`) and zero `strokeMult > 0` on matte presets.
- `buildBlueprintHtml(..., { theme: "cobalt" })` emits `#2059DC` cobalt blueprint rendering, while default `{}` preserves `#D9D2C3` paper rendering with zero `undefined` literals.
- `buildMapSceneHtml(..., { surface_register: "daylight_terrain", terrain_3d: true })` emits `#2B7AE4` sky color and `#A3CEF5` horizon color, while default `{}` emits `#0E4352` background with zero `undefined` literals.

In `tools/geo-assets/serve_tiles.test.mjs` (or `scene_modules.test.mjs`), import `gradeRgb` from `../build_tiles.mjs` and assert:
- Deep ocean pixel `[10, 28, 48]` stays marine-teal (`b > g > r`, `g >= 48`, `b >= 68`, not crushed black),
- Shallow coastal shelf pixel `[38, 128, 148]` stays visibly brighter/more cyan than deep ocean (`shelfG > deepG + 20`, `shelfB > deepB + 20`),
- Warm landmass pixel `[160, 145, 110]` preserves natural warmth (`r > b`, no negative/overflow values), and `gradeRgb` is deterministic across repeated calls.

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tools/geo-assets/scene/scene_modules.test.mjs tools/geo-assets/serve_tiles.test.mjs`
Expected: FAIL on missing presets, theme/register support, and shelf luminance checks.

- [ ] **Step 3: Implement `build_tiles.mjs`, `runtime_typography.mjs`, `html_blueprint.mjs`, and `html_map_scene.mjs` updates**

- `tools/geo-assets/build_tiles.mjs:gradeRgb`: adjust ocean grading so shallow turquoise/cyan shelves (`luma > 75 && g > r + 15`) preserve shelf brightness (`#227282`–`#3A8F9D`) while deep ocean grades smoothly to `#093B4B`–`#134F5F`, and warm landmass contrast preserves olive/ochre relief (`c = 1.09`, warm slight red/green lift without clipping).
- `tools/geo-assets/scene/runtime_typography.mjs`: sync `#F4F1EA` -> `#F5F7FA` on primary white presets and add `dark_on_fill`, `acronym_hero`, `velocity_cyan`, `underlined_city`, and `water_subtle` to `CARTO_TYPO_PRESETS`.
- `tools/geo-assets/scene/html_blueprint.mjs`: branch cleanly on `SPEC.theme === "cobalt"` to draw a vivid `#2059DC` full-frame blueprint drafting canvas with translucent white coordinate grid (`rgba(255,255,255,0.16)`), keeping the existing paper theme untouched when `theme` is unset or `"paper"`.
- `tools/geo-assets/scene/html_map_scene.mjs`: derive `bgColor = mapOpts.background_color || "#0E4352"` (updating HTML body background and MapLibre `bg` layer), and when `mapOpts.surface_register === "daylight_terrain"` (and `mapOpts.atmosphere` is not a custom object), emit daylight sky (`sky-color: "#2B7AE4"`, `horizon-color: "#A3CEF5"`, `fog-color: "#CBE4F9"`, `fog-ground-blend: 0.22`).

- [ ] **Step 4: Run all Node geo-assets tests**

Run: `node --test tools/geo-assets/serve_tiles.test.mjs tools/geo-assets/render_captions_overlay.test.mjs tools/geo-assets/map_draw_math.test.mjs tools/geo-assets/scene/scene_modules.test.mjs tools/geo-assets/scene/determinism.test.mjs`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/geo-assets/build_tiles.mjs tools/geo-assets/scene/runtime_typography.mjs tools/geo-assets/scene/html_blueprint.mjs tools/geo-assets/scene/html_map_scene.mjs tools/geo-assets/scene/scene_modules.test.mjs
git commit -m "feat(geo-assets): calibrate bathymetric grading, surface registers, and adaptive typography presets"
```

---

### Task 6: Reframe Repository Skills & Docs + Full Verification & Hygiene Audit

**Files:**
- Modify: `.agents/skills/brand-director/SKILL.md`
- Modify: `.agents/skills/brand-profiling/SKILL.md`
- Modify: `profiles/README.md`

**Interfaces:**
- Consumes: Finalized 3-layer Geoverum profile, calibrated `46 px` / `MarginV=525` / `Inter` caption contract, `audio_themes.json` CLI flag, Stage 0 Divergent Concept Pitch workflow.
- Produces: Synchronized, non-misleading operator playbooks and profile architecture docs with zero contradictions and zero hygiene leaks.

- [ ] **Step 1: Update `.agents/skills/brand-director/SKILL.md`**

- Remove all stale contradictions (`Rubik Bold 56 px`, `MarginV=348`, `y ≈ 80%`, `flag_pin`).
- Insert **Stage 0: Divergent Concept Pitch (Verbalized Sampling)** ahead of storyboarding (generate 4–5 distinct episode concepts including `>= 2` tail concepts `p < 0.15` across `Narrative Strategy x Tone/Register x Surface/Metaphor Mix`, pick 1 unique Visual Anchor, check `brand_memory.json`, authorize custom episode SVG `map_sprites` / `cutaway_2d` HTML open primitives bound by Layer 1 Brand DNA).
- Document single-source policy-driven `vedit geo build-captions --brand geoverum` (`Inter` Bold `46 px`, `MarginV=525`, `y ≈ 72.7%`, HTML soft-shadow renderer) and `vedit geo auto-audio --brand geoverum` (`audio_themes.json`).

- [ ] **Step 2: Reframe `.agents/skills/brand-profiling/SKILL.md`**

- Explicitly clarify scope in frontmatter and top warning: **Offline Reference Calibration Only** — invoked strictly when analyzing raw reference videos to calibrate Layer 1 Brand DNA (color grading, typography scale, caption geometry, hard guardrails), Layer 3 executable idiom parameters, and a small set of curated non-overlapping Layer 2 recipes.
- Explicitly prohibit using `brand-profiling` for active brand redesigns, creative directing, dumping unexecuted pseudo-DSL trigger lists into `editorial_playbook.json`, or locking episodes into fixed shot sequences; codify the **Tight Rails (20% Brand DNA), Open Canvas (80% Creative Sandbox)** contract.

- [ ] **Step 3: Update `profiles/README.md`**

- Document the 3-layer **Tight Rails, Open Canvas** brand directory structure, progressive-disclosure reading order, and optional `audio_themes.json` override.

- [ ] **Step 4: Run repository hygiene audit + complete automated verification suite**

Run:
```bash
# Hygiene audit across all modified permanent repo files
rg -in "batch|phase |preserved baseline|cumulatively|yt_|/Users/|youtube|tiktok|google earth|flightradar|rubik|56 px|56px|marginv=348|flag_pin" \
  profiles/brands/geoverum/README.md \
  profiles/brands/geoverum/CRAFT.md \
  profiles/brands/geoverum/DIRECTING.md \
  profiles/brands/geoverum/brand_style_policy.json \
  profiles/brands/geoverum/directing_idioms.json \
  profiles/brands/geoverum/editorial_playbook.json \
  profiles/brands/geoverum/audio_themes.json \
  .agents/skills/brand-director/SKILL.md \
  .agents/skills/brand-profiling/SKILL.md \
  profiles/README.md || echo "HYGIENE_CLEAN"

# Full engine & contract verification
packages/director-py/.venv/bin/vedit contracts validate --json
packages/director-py/.venv/bin/vedit brand validate --brand-dir profiles/brands/geoverum --json
packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal
packages/director-py/.venv/bin/pytest -v packages/director-py/tests
cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test && cd ../..
node --test tools/geo-assets/serve_tiles.test.mjs tools/geo-assets/render_captions_overlay.test.mjs tools/geo-assets/map_draw_math.test.mjs tools/geo-assets/scene/scene_modules.test.mjs tools/geo-assets/scene/determinism.test.mjs
```
Expected: Zero hygiene leaks (other than explicit negative prohibition statements if any) and 100% green across contracts, ruff, pytest, TypeScript compiler tests, and Node geo tests.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/brand-director/SKILL.md .agents/skills/brand-profiling/SKILL.md profiles/README.md
git commit -m "docs(skills): sync brand-director and reframe brand-profiling around tight-rails open-canvas"
```
