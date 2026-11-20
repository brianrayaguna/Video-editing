---
name: brand-profiling
description: Forensic reference-video profiling playbook for synthesizing high-accuracy BrandStylePolicy, EditorialPlaybook, and CRAFT.md files via `vedit probe`, `vedit breakdown` (`VideoBreakdownPort`), layered `VIDEO.md` reading, and automatic multimodal visual review.
---

# Brand Profiling Playbook

Use this workflow whenever analyzing reference videos to create, calibrate, or audit a brand profile under `profiles/brands/<brand_id>/`.

## Architectural Rules

1. **Forensic Analysis Only**: Never invoke generative video remake commands (`plan`, `remake`, `remake-run`, `drive`, or external synthetic video generators). If a reference video contains `ai_video` or `avatar` shots (`generative_reference_warning: true`), document non-generative substitutes (real footage, cartographic beds, or procedural HyperFrames HTML/GSAP) in `CRAFT.md` and `editorial_playbook.json`.
2. **Evidence Over Guessing**: Prefer measured telemetry from `vedit-probe` and `VideoBreakdownPort` (`VIDEO.md` + `video_breakdown.json`) verified by direct visual inspection over heuristic defaults.
3. **Layered Reading (`VIDEO.md`)**: Never load raw `breakdown.json` into context. Read `VIDEO.md` first, then open only the specific topic files needed (`video/timeline.md`, `video/packaging.md`, `video/sound.md`, `video/rhythm.md`, `video/look.md`).
4. **Timeless & Neutral Repository Output**: Follow `.agents/rules/engineering-standards.md` and `AGENTS.md` strictly when writing into `profiles/brands/<brand_id>/`. Keep batch trackers, download numbers (`yt_01`), and raw per-video notes strictly inside the external `$VEDIT_PROJECTS_ROOT/<brand_id>/_calibration/` workspace. Inside the repository, use only content-based `ref_<topic>` IDs in `exemplar_bank`, write standalone objective technical English with zero batch/session counters, and strip all third-party product, app, platform, software, and channel brand names.

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
```

If `tools/rea-video/.venv/bin/rea-video` is not yet installed, instruct the operator or run `bash tools/rea-video/setup.sh`.

### Stage 2: Layered `VIDEO.md` Inspection

Inspect the generated `VIDEO.md` package layer by layer:
1. `$CAL_DIR/bd_<stem>/VIDEO.md` — production mix, confidence, overall verdict, file map.
2. `video/packaging.md` — measured subtitle lane, casing, box/stroke colors, words per line, entrance animations, persistent watermarks.
3. `video/sound.md` — measured BPM, beat-sync ratio, key/mode, vocal style, visual-aligned SFX.
4. `video/rhythm.md` & `video/timeline.md` — cut cadence, transition types, per-shot durations, internal motion beats.
5. `video/look.md` — color grade metrics, lighting, framing, camera setups (when live-action shots exist).

### Stage 3: Automatic Multimodal Visual Review (Agent-as-VLM)

A multimodal AI directing client **must** perform visual review automatically (no separate external VLM API key is required):

1. Open `review_tasks.json`, `storyboard.jpg`, and every `priority: "high"` contact sheet (`shots/shot_XXX.jpg`), plus any flagged `packaging/sticker_*.jpg`.
2. Inspect the frames directly to determine facts pixels/OCR cannot measure:
   - Exact **production label** on platform-recompressed shots (`live_action`, `code_render`, `screen_capture`, `cg_3d`, `still_motion`, `static_hold`, `anim_2d`, `film_footage`, etc.).
   - Semantic **narrative role** per shot (`hook`, `context`, `info`, `proof`, `turn`, `payoff`, `cta`, `mood`) and concise one-sentence `point`.
   - Exact **font families** (display, body, title), caption styling (`plain` / `chip` / `bar`), and watermark/chrome presence.
   - Recurring **anti-patterns** to record under `hard_guardrails.banned_patterns` and `calibration.rejected_patterns`.
3. Write the verified answers into `$CAL_DIR/bd_<stem>/review_answers.json`.
4. Fuse the visual review back into the breakdown artifacts:

```bash
packages/director-py/.venv/bin/vedit breakdown apply-review \
  "$CAL_DIR/bd_<stem>" \
  --by ai-directing-client \
  --lang en
```

### Stage 4: Synthesize Policy, Playbook & `CRAFT.md`

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
packages/director-py/.venv/bin/vedit contracts validate --json
```
