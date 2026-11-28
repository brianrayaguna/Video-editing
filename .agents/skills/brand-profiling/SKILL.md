---
name: brand-profiling
description: Forensic reference-video profiling playbook for synthesizing and calibrating BrandStylePolicy, EditorialPlaybook, executable directing idioms, DIRECTING.md, and CRAFT.md via `vedit probe`, `vedit breakdown` (`VideoBreakdownPort`), layered `VIDEO.md` reading, reference storyboard annotation, and automatic multimodal visual review.
---

# Brand Profiling Playbook

Use this workflow whenever analyzing reference videos to create, calibrate, or audit a brand profile under `profiles/brands/<brand_id>/`.

## Architectural Rules

1. **Forensic Analysis Only**: Never invoke generative video remake commands (`plan`, `remake`, `remake-run`, `drive`, or external synthetic video generators). If a reference video contains `ai_video` or `avatar` shots (`generative_reference_warning: true`), document non-generative substitutes (real footage, cartographic beds, or procedural HyperFrames HTML/GSAP) in `CRAFT.md` and `editorial_playbook.json`.
2. **Evidence Over Guessing**: Prefer measured telemetry from `vedit-probe` and `VideoBreakdownPort` (`VIDEO.md` + `video_breakdown.json`) verified by direct visual inspection over heuristic defaults.
3. **Layered Reading (`VIDEO.md`)**: Never load raw `breakdown.json` into context. Read `VIDEO.md` first, then open only the specific topic files needed (`video/timeline.md`, `video/packaging.md`, `video/sound.md`, `video/rhythm.md`, `video/look.md`).
4. **Timeless & Neutral Repository Output**: Follow `AGENTS.md` strictly when writing into `profiles/brands/<brand_id>/`. Keep batch trackers, download numbers (`yt_01`), and raw per-video notes strictly inside the external `$VEDIT_PROJECTS_ROOT/<brand_id>/_calibration/` workspace. Inside the repository, use only content-based `ref_<topic>` IDs in `exemplar_bank`, write standalone objective technical English with zero batch/session counters, and strip all third-party product, app, platform, software, and channel brand names.

## Workflow

### Stage 1: Dual Deterministic Telemetry

For each reference video `<ref.mp4>`, run both deterministic analyzers into an external project analysis directory under `$VEDIT_PROJECTS_ROOT/<brand_id>/_calibration/`:

```bash
CAL_DIR="${VEDIT_PROJECTS_ROOT:-../Editing-Projects}/<brand_id>/_calibration"
mkdir -p "$CAL_DIR"

# 1. Fast Rust telemetry: SHA-256, BT.709 color tags, EBU R128 LUFS, CIELAB palette, silence intervals
packages/director-py/.venv/bin/vedit probe analyze <ref.mp4> \
  --extract-keyframes "$CAL_DIR/kf_<stem>" \
  > "$CAL_DIR/probe_<stem>.json"

# 2. Optional (recommended for motion-graphics or complex-transition documentaries):
#    Run visual-first contact-sheet survey before decompose so dissolves, morphs, and whip-zooms
#    are captured accurately. Repeat until status == "done".
packages/director-py/.venv/bin/vedit breakdown survey <ref.mp4> -o "$CAL_DIR/bd_<stem>"

# 3. Forensic breakdown (offline shots/transitions, audio BPM/key/SFX, 2-10fps OCR packaging,
#    color grade, VIDEO.md, storyboard.jpg, shots/shot_XXX.jpg, and review_tasks.json)
packages/director-py/.venv/bin/vedit breakdown analyze <ref.mp4> -o "$CAL_DIR/bd_<stem>"

# 4. Spatial, grid, visual hierarchy, micro-typography/WCAG, and motion easing forensics
#    (emits spatial_forensics.json, STRUCTURE.md, and Set-of-Mark spatial/frame_XXX_blueprint.jpg)
packages/director-py/.venv/bin/vedit breakdown structure <ref.mp4> \
  -o "$CAL_DIR/bd_<stem>" \
  --shots-from "$CAL_DIR/bd_<stem>/video_breakdown.json" \
  --platform shorts_9x16_1080p

# 5. Native-FPS full-frame forensics across every frame: continuous camera kinematics,
#    surface/map register segmentation, color/glow/vignette telemetry, dense OCR caption &
#    in-world typography tracking, localized graphic events, audio transient sync, and
#    full-coverage timeline sheets + full-FPS cut burst strips (emits FULLFRAME.md)
packages/director-py/.venv/bin/vedit breakdown fullframe <ref.mp4> \
  -o "$CAL_DIR/ff_<stem>" \
  --platform shorts_9x16_1080p \
  --ocr-fps 3.0 \
  --sheet-fps 1.0
```

If `tools/rea-video/.venv/bin/rea-video` is not yet installed, instruct the operator or run `bash tools/rea-video/setup.sh`.
If `tools/spatial-forensics/.venv/bin/python` is not yet installed, run `bash tools/spatial-forensics/setup.sh`.

### Stage 2: Layered `VIDEO.md` & `STRUCTURE.md` Inspection

Inspect the generated `VIDEO.md` and `STRUCTURE.md` packages layer by layer:
1. `$CAL_DIR/bd_<stem>/VIDEO.md` — production mix, confidence, overall verdict, file map.
2. `$CAL_DIR/bd_<stem>/STRUCTURE.md` — inferred grid columns, margins (`L/R/T/B`), alignment snap score, competing Tier-1 signals, whitespace/calm ratio, display-to-caption type scale ratio, WCAG contrast, safe-zone violation rate, and motion easing class.
3. `video/packaging.md` — measured subtitle lane, casing, box/stroke colors, words per line, entrance animations, persistent watermarks.
4. `video/sound.md` — measured BPM, beat-sync ratio, key/mode, vocal style, visual-aligned SFX.
5. `video/rhythm.md` & `video/timeline.md` — cut cadence, transition types, per-shot durations, internal motion beats.
6. `video/look.md` — color grade metrics, lighting, framing, camera setups (when live-action shots exist).

### Stage 3: Automatic Multimodal Visual Review (Agent-as-VLM)

A multimodal AI directing client **must** perform visual review automatically (no separate external VLM API key is required):

1. Open `review_tasks.json`, `storyboard.jpg`, Set-of-Mark blueprint frames (`spatial/frame_XXX_blueprint.jpg`) for exact grid/hierarchy/safe-zone grounding, and every `priority: "high"` contact sheet (`shots/shot_XXX.jpg`), plus any flagged `packaging/sticker_*.jpg`.
2. Inspect the frames directly to determine facts pixels/OCR cannot measure:
   - Exact **production label** on platform-recompressed shots (`live_action`, `code_render`, `screen_capture`, `cg_3d`, `still_motion`, `static_hold`, `anim_2d`, `film_footage`, etc.).
   - Semantic **narrative role** per shot (`hook`, `context`, `info`, `proof`, `turn`, `payoff`, `cta`, `mood`) and concise one-sentence `point`.
   - Exact **font families** (display, body, title), caption styling (`plain` / `chip` / `bar`), and watermark/chrome presence.
   - Recurring **anti-patterns** to record under `hard_guardrails.banned_patterns` and `calibration.rejected_patterns`.
   - Whenever a reference uses whip-zooms, rack-focus register swaps, rapid counters, or curved tool actions, inspect a full-FPS transition window (`±15` frames around the cut or action peak) so easing curves, directional blur duration, and velocity carry-over are measured directly rather than estimated from `1–2 fps` keyframe samples.
3. Write the verified answers into `$CAL_DIR/bd_<stem>/review_answers.json`.
4. Fuse the visual review back into the breakdown artifacts:

```bash
packages/director-py/.venv/bin/vedit breakdown apply-review \
  "$CAL_DIR/bd_<stem>" \
  --by ai-directing-client \
  --lang en
```

### Stage 4: Reference Storyboard Annotation (directing evidence)

Telemetry measures cuts, colour and loudness; it cannot measure *directing*. Capture that by annotating each reference in the engine's own storyboard format so its measurements can calibrate the executable idioms.

1. Transcribe the reference narration through the configured cloud `TranscriptionPort` (`vedit transcribe`) into `$CAL_DIR/transcript_<stem>.json`. When no speech track can be separated, build word timings from the on-screen captions read in Stage 2 and note this in the annotation's `overrides.notes`.
2. Draft the reference storyboard automatically by snapping beat onsets to corroborated breakdown, probe, and camera-regime telemetry via `vedit brand invert-reference`:

```bash
packages/director-py/.venv/bin/vedit brand invert-reference "$CAL_DIR/transcript_<stem>.json" \
  --brand <brand_id> --project-id <ref_topic> \
  --breakdown-file "$CAL_DIR/bd_<stem>/video_breakdown.json" \
  --probe-file "$CAL_DIR/probe_<stem>.json" \
  [--camera-track "$CAL_DIR/camera_<stem>.json"] \
  -o "$CAL_DIR/ref_storyboard_<stem>.json" \
  --review-queue-out "$CAL_DIR/review_queue_<stem>.json"
packages/director-py/.venv/bin/vedit critique packet -o "$CAL_DIR/ref_sheets_<stem>/packet.json" \
  --storyboard "$CAL_DIR/ref_storyboard_<stem>.json" --video <ref.mp4> --brand <brand_id>
```

3. Inspect the grid-anchored sheets (columns A–F, rows 1–10 on a `1080x1920` frame: one column = `180 px`, one row = `192 px`; scale proportionally for other canvases) and prioritize verifying and correcting the flagged `exception_review_beats` in `review_queue_<stem>.json` (plus any devices, treatments, or callouts the automated inversion could not confirm):
   - `start_s`: the frame where the visual event begins (step through frames around the sync word; do not keep the automatic onset).
   - `device` and `treatment`: the on-screen answer, using existing device names where they fit; a new device name is reported by calibration as unclassified.
   - `function`, `story_need`: why the reference shows it.
   - `callouts`: `kind`, `size_px` (measured width or diameter), `xy` (centre), `start_s` / `end_s`.
   - `camera.regime`, plus `camera.zoom` when a calibrated camera track exists and `camera.route_width_px` when a route is drawn.
   - `head` markers and `route` for journey films; `hold_reason` where the voice pauses.
   - `story`: shape, hook mechanism, ending type, signature image, colour cast.
4. For map-driven references, solve a camera track (`[t, lng, lat, zoom, bearing]`) against rendered basemaps and check it with `vedit geo camera-track` so regime zooms come from measurement.

### Stage 5: Calibrate Executable Directing Idioms

```bash
packages/director-py/.venv/bin/vedit brand calibrate-idioms \
  --reference-storyboard "$CAL_DIR/ref_storyboard_<stem1>.json" \
  --reference-storyboard "$CAL_DIR/ref_storyboard_<stem2>.json" \
  [--camera-track "$CAL_DIR/camera_<stem1>.json" --camera-track "$CAL_DIR/camera_<stem2>.json"] \
  --idioms-file profiles/brands/<brand_id>/directing_idioms.json \
  --report "$CAL_DIR/idiom_calibration.json" --blend 0.5
```

1. Read the report: `changes` (old → new with evidence), `skipped` (too few samples, or onsets that were never re-timed), and `follow_up` (unclassified devices to add to a device class with a lead window).
2. Re-run with `--apply` when every change is supported by the evidence. Use `--blend 1.0` only when the references are the brand's defining examples; the default `0.5` moves existing values halfway so one reference refines rather than overwrites the profile.
3. Add new devices to `device_classes` and new keyword rules to `auto_director.device_rules` by hand when the references show a recurring pattern the automatic director misses.
4. Re-check the annotated references against the updated idioms (`vedit storyboard check "$CAL_DIR/ref_storyboard_<stem>.json"`). A reference that fails its own brand's idioms means a parameter is still wrong or the reference departs from the brand; record which in the calibration workspace.

### Stage 6: Route Every Finding to Its Home

Each finding from the analysis goes to exactly one place. Prefer the most executable home that can express it.

| Finding | Home | Form |
| :--- | :--- | :--- |
| A measurable threshold (timing, size, count, zoom, width, lead) | `directing_idioms.json` | Idiom parameter via calibration, or a new idiom with rationale |
| A pattern the automatic director should pick by itself (keyword → device) | `directing_idioms.json` → `auto_director.device_rules` | Keyword stems, device, function, story need |
| How to choose or order story beats (shape, hook, ending, storyboard method) | `DIRECTING.md` | Timeless method prose; add the shape signal words to `auto_director.shape_signals` |
| How a device looks or moves (colour, stroke, typography, layout, camera feel) | `CRAFT.md` | Measured ranges in neutral technical terms |
| A rule worth checking on rendered frames that cannot be measured from the plan | `directing_idioms.json` → `critique_rubric` | Criterion question, weight, fail signs |
| A timecoded moment worth imitating | `editorial_playbook.json` → `exemplar_bank` | `ref_<topic>` exemplar with role and pattern |
| A narration-triggered heuristic for human or AI directors | `editorial_playbook.json` → `grammar_triggers` | Advisory trigger with rationale |
| Pacing priors, palette, typography tokens, hard guardrails | `brand_style_policy.json` | Via `vedit brand analyze`, then refined |
| A reusable visual component | `templates/` | Parameterised component plus catalog entry |
| An engine capability gap (a device the renderer cannot produce) | Engine code and tests | New layer type, CLI option, or module |

Never store per-reference notes, timings, download numbers, or the calibration report itself inside the repository; they stay in `$CAL_DIR`.

### Stage 7: Synthesize Policy, Playbook & `CRAFT.md`

Combine all reference probes and reviewed breakdowns (including both `9:16` and `16:9` references when the brand spans multiple formats):

```bash
packages/director-py/.venv/bin/vedit brand analyze \
  --brand-id <brand_id> \
  --probe-file "$CAL_DIR/probe_<ref1>.json" \
  --breakdown-file "$CAL_DIR/bd_<ref1>" \
  --probe-file "$CAL_DIR/probe_<ref2>.json" \
  --breakdown-file "$CAL_DIR/bd_<ref2>" \
  --output profiles/brands/<brand_id>/brand_style_policy.json \
  --playbook-out profiles/brands/<brand_id>/editorial_playbook.json
```

Then refine the brand directory:
1. Update `typography.display_family`, `body_family`, and `title_family` in `brand_style_policy.json` with the visually identified font families (OCR cannot read font names).
2. Refine `hard_guardrails.banned_patterns` and `editorial_identity` using the reviewed visual craft notes.
3. Author or update `profiles/brands/<brand_id>/CRAFT.md` documenting layout hierarchy, motion choreography, color roles, audio/SFX rules, and non-generative asset sourcing in standalone technical English (zero batch/corpus counters, zero video-ID citation lists, zero third-party brand names).
4. Run a repository hygiene audit (checking for leaked batch/session counters, sequential platform prefixes, local paths, and any third-party brand/product/platform names) and validate the complete brand tree before finishing:

```bash
rg -in "batch|phase |preserved baseline|cumulatively|yt_|/Users/" profiles/brands/<brand_id>/ || true
packages/director-py/.venv/bin/vedit brand validate --brand-dir profiles/brands/<brand_id> --json
packages/director-py/.venv/bin/pytest -q packages/director-py/tests/test_storyboard.py packages/director-py/tests/test_idiom_calibration.py
packages/director-py/.venv/bin/vedit contracts validate --json
```
