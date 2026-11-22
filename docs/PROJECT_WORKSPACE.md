# External Project Workspaces

Active video editing projects live **outside** the `vedit` engine repository under a dedicated projects directory configured by `VEDIT_PROJECTS_ROOT`. Keeping projects separate ensures the engine repository stays clean, brand-agnostic, and free of historical episode artifacts while every project still invokes the full `vedit` CLI, contract validators, brand profiles, and Modal cloud workers.

## Root Resolution Order

`vedit project init` resolves the external projects root in the following order:

1. Explicit `--projects-root <path>` flag
2. `VEDIT_PROJECTS_ROOT` environment variable
3. Default sibling directory outside the engine repository (`<engine_parent>/<engine_name>-Projects`)

Project creation inside the engine repository is rejected by default.

## Standard Project Layout

```text
<VEDIT_PROJECTS_ROOT>/
  <brand_id>/
    <project_id>/
      project.json              # Validated ProjectManifest (contracts/project_manifest.schema.json)
      brief.md                  # Editorial brief, narration script, and beat outline
      inputs/                   # Raw project-scoped inputs (voiceover, camera footage, references)
      analysis/
        probes/                 # MediaProbeResult JSON and extracted shot keyframes
        breakdowns/             # VideoBreakdownPort output (VIDEO.md, review_tasks.json)
        transcripts/            # NormalizedTranscript JSON (word-level timestamps)
        decisions/              # DecisionPort spatial bounding boxes and scoring JSON
      media/
        maps/                   # Baked cartographic A-roll shots
        broll/                  # Normalized target-aspect B-roll clips
        audio/                  # Cleaned voiceover stems, music cuts, and SFX
      plan/
        storyboard.json         # Storyboard (contracts/storyboard.schema.json): auto-directed, then refined
        director.json           # Optional partial director storyboard layered over the automatic one
        journey.json            # Route head, camera, route-width keys from `vedit storyboard journey`
        edit_plan.json          # Verified EditPlan (strictly relative asset paths)
        verification.json       # Deterministic guardrail verification report
      build/
        hf_project/             # Compiled HyperFrames HTML/GSAP scenes
        hf_sparse_windows/      # Sparse animated overlay MOV segments
        subtitles/              # Generated libass .ass subtitle scripts
      output/
        master.mp4              # Final mastered deliverable
        audit.json              # Technical and visual QC audit report
        critique/               # Critique packet, filled rubric review, grid contact sheets
        timeline.otio           # Optional OpenTimelineIO NLE handoff
        benchmark.json          # Per-stage latency and cloud cost telemetry (relative paths)
```

## Relative Path Hygiene

- Store strictly **project-relative paths** inside `project.json`, `plan/edit_plan.json`, and `output/benchmark.json` (for example, `media/maps/strait_approach.mp4` or `media/audio/vo_clean.wav`).
- Never embed user-specific absolute paths in project manifests or edit plans.
- At runtime, `vedit` automatically resolves relative `AssetRef.path` values against the enclosing project directory, then the plan directory, and finally the engine repository root (for shared assets such as fonts).
- `vedit compile` automatically propagates `VEDIT_REPO_ROOT` to `@vedit/hf-compiler` so brand template paths (`profiles/brands/<brand_id>/templates/components/*.html`) resolve reliably from any external project directory.

## Standard Commands

```bash
export VEDIT_PROJECTS_ROOT="../Editing-Projects"
VEDIT="/path/to/engine/packages/director-py/.venv/bin/vedit"

# 1. Initialize a new external project
$VEDIT project init gibraltar_strait --brand geoverum --platform shorts_9x16_1080p

# 2. Inspect stage readiness
$VEDIT project status "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait"

# 3. Validate manifest schema, brand/platform references, and relative path hygiene
$VEDIT project validate "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait" --json

# 4. Run end-to-end directing, cloud rendering, mastering, and audit against the external project
$VEDIT director verify \
  --plan-file "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait/plan/edit_plan.json" \
  --policy-file profiles/brands/geoverum/brand_style_policy.json \
  --brand-dir profiles/brands/geoverum \
  --platform shorts_9x16_1080p \
  --update-plan

$VEDIT cloud render \
  --plan-file "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait/plan/edit_plan.json" \
  --platform shorts_9x16_1080p \
  -o "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait/output/master.mp4"

$VEDIT audit \
  "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait/output/master.mp4" \
  --platform shorts_9x16_1080p

# Optional: export timeline for NLE review
$VEDIT export-otio \
  --plan-file "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait/plan/edit_plan.json" \
  -o "$VEDIT_PROJECTS_ROOT/geoverum/gibraltar_strait/output/timeline.otio"
```
