---
name: brand-profiling
description: Offline reference-video calibration playbook for measuring Layer 1 Brand DNA (color grading, typography scale, caption geometry, guardrails), Layer 3 executable idiom thresholds, and curated non-overlapping Layer 2 visual recipes under `profiles/brands/<brand_id>/`. Not for active episode directing or creative architecture redesign.
---

# Brand Profiling & Reference Calibration Playbook

> **Scope Boundary — Offline Reference Calibration Only**
> Use this playbook **only** when ingesting raw reference videos to empirically calibrate a brand's **Quality Floor** under `profiles/brands/<brand_id>/`. Do **not** invoke this skill during episode production (use `brand-director`), and do **not** use reference videos to freeze shot order or dump dozens of pseudo-DSL trigger rules into `editorial_playbook.json`.

## Tight Rails (20%), Open Canvas (80%) Principle

Profiling calibrates **what makes a brand recognizable and broadcast-grade**—never a rigid episode template:

- **Calibrate into Layer 1 (Brand DNA, ~20%)**: Ocean/land color grading ranges, surface register palettes, adaptive ink contrast rules, modular typography scale, caption geometry, audio loudness/ducking targets, and hard guardrails (`brand_style_policy.json` + compact `CRAFT.md`).
- **Curate sparingly into Layer 2 (Creative Sandbox, ~80%)**: Distill only **distinct, reusable visual recipes** (target `16–24` non-overlapping entries with spread weights `0.55–0.95` and plain-English/engine-grounded actions) and `18–26` role-balanced exemplars into `editorial_playbook.json`. Never transcribe every reference frame as a mandatory trigger; episodes must remain free to improvise new concepts and open primitives.
- **Measure into Layer 3 (Quality Floor)**: Calibrate numeric idiom parameters (hook window, event cadence, sync lead windows, camera regimes) in `directing_idioms.json` via `vedit brand calibrate-idioms`.

## Architectural Rules

1. **Forensic Measurement Only**: Never invoke generative video remake commands (`plan`, `remake`, `remake-run`, `drive`, or synthetic video generators). Document non-generative deterministic substitutes (MapLibre cartography, custom SVG `map_sprites`, full-bleed `cutaway_2d`, real archival B-roll) when analyzing references.
2. **Evidence Over Guessing**: Prefer measured telemetry from `vedit-probe` and `VideoBreakdownPort` (`VIDEO.md` + `STRUCTURE.md`) verified by direct visual frame inspection over heuristic guesses.
3. **Layered Reading (`VIDEO.md`)**: Never load raw `breakdown.json` into context. Read `VIDEO.md` and `STRUCTURE.md` first, opening only targeted topic files (`video/packaging.md`, `video/sound.md`, `video/rhythm.md`, `video/look.md`).
4. **Single Source of Truth & Anti-Bloat**: Store numeric tokens and guardrails once in `brand_style_policy.json` (never duplicate hex/px tables across `README.md`, `CRAFT.md`, and `calibration.rejected_patterns`). Keep raw per-video notes, download indices, and calibration reports strictly outside the repository under `$VEDIT_PROJECTS_ROOT/<brand_id>/_calibration/`. Inside the repository, use timeless, neutral technical English, `ref_<topic>` IDs, and zero third-party brand/app/channel names or local paths.

## Calibration Workflow

### Stage 1: Deterministic Telemetry (External Workspace)

```bash
CAL_DIR="${VEDIT_PROJECTS_ROOT:-../Editing-Projects}/<brand_id>/_calibration"
mkdir -p "$CAL_DIR"

packages/director-py/.venv/bin/vedit probe analyze <ref.mp4> \
  --extract-keyframes "$CAL_DIR/kf_<stem>" > "$CAL_DIR/probe_<stem>.json"

packages/director-py/.venv/bin/vedit breakdown analyze <ref.mp4> -o "$CAL_DIR/bd_<stem>"

packages/director-py/.venv/bin/vedit breakdown structure <ref.mp4> \
  -o "$CAL_DIR/bd_<stem>" \
  --shots-from "$CAL_DIR/bd_<stem>/video_breakdown.json" \
  --platform shorts_9x16_1080p
```

*(Install optional local breakdown toolchains via `bash tools/rea-video/setup.sh` or `bash tools/spatial-forensics/setup.sh` only when running full offline forensic batches.)*

### Stage 2: Direct Visual Inspection (What Pixels/OCR Cannot Measure)

Inspect contact sheets (`storyboard.jpg`, `spatial/frame_XXX_blueprint.jpg`, high-priority shot sheets) directly via `read_file` to record:
- Exact **surface registers** (satellite bathymetry/land grade, blueprint backdrop, matte radar, daylight 3D terrain, tactical 2D/parchment).
- **Typography & adaptive ink**: real font families, display/hero weights (never collapsed `400`), caption pixel proportion, soft shadow halo over bright snow/clouds, and dark-on-bright-fill ink inversions.
- **Concept distinctiveness**: how each reference invents a distinct visual anchor and structure rather than repeating a template.
- **Anti-patterns** to block in `brand_style_policy.json` (`hard_guardrails.banned_patterns`).

Fuse verified observations via `vedit breakdown apply-review "$CAL_DIR/bd_<stem>" --by ai-directing-client --lang en`.

### Stage 3: Calibrate Executable Idioms (Optional, When Tuning Numeric Thresholds)

Invert reference narrations into temporary reference storyboards (`vedit brand invert-reference`), verify exception beats visually on grid-anchored contact sheets (`vedit critique packet`), and calibrate numeric thresholds into `directing_idioms.json`:

```bash
packages/director-py/.venv/bin/vedit brand calibrate-idioms \
  --reference-storyboard "$CAL_DIR/ref_storyboard_<stem1>.json" \
  --idioms-file profiles/brands/<brand_id>/directing_idioms.json \
  --report "$CAL_DIR/idiom_calibration.json" --blend 0.5
```

Apply with `--apply` only after verifying each numeric shift in the report.

### Stage 4: Route Every Finding to Exactly One Home

| Finding | Single Home | Rule |
| :--- | :--- | :--- |
| Palette roles, typography scale, caption size/band, temporal priors, hard bans | `brand_style_policy.json` | Single source of truth; zero duplication into `calibration.rejected_patterns` or prose tables. |
| Surface register art direction, adaptive ink/glow, layout stage, camera feel | `CRAFT.md` (`< 3.5K` tokens) | Timeless craft rules; zero repeated JSON tables or internal renderer shader APIs. |
| Story shapes, concept divergence, sync offsets, variation rules | `DIRECTING.md` (`< 3.5K` tokens) | Creative method only; preserves open-canvas improvisation. |
| Executable timing/size/wiring rules & critique rubric | `directing_idioms.json` | Keep `device_classes` 100% mapped in `device_realization`; zero dead keys. |
| Curated visual recipes (`16–24`) & role-balanced exemplars (`18–26`) | `editorial_playbook.json` | Plain-English conditions, engine-grounded actions, spread weights (`0.55–0.95`), zero pseudo-DSL bloat. |
| Domain studio BGM/ambience/foley queries | `audio_themes.json` | Validated by `validate_brand_tree` and loaded via `vedit geo auto-audio --brand <brand_id>`. |
| Parameterized HyperFrames components | `templates/catalog.json` + `components/*.html` | Sync defaults to `palette_roles`; match declared weights (`font-synthesis: none`). |

### Stage 5: Hygiene Audit & Validation Gate

```bash
rg -in "batch|phase |preserved baseline|cumulatively|yt_|/Users/" profiles/brands/<brand_id>/ || true
packages/director-py/.venv/bin/vedit brand validate --brand-dir profiles/brands/<brand_id> --json
packages/director-py/.venv/bin/vedit contracts validate --json
packages/director-py/.venv/bin/pytest -q packages/director-py/tests/test_contracts.py packages/director-py/tests/test_storyboard.py packages/director-py/tests/test_idiom_calibration.py
```
