# Geoverum Modal Production Workflow

End-to-end path for Geoverum studies that assemble a verified **`EditPlan`**, compile HyperFrames overlays, and render/master on **Modal** (`vedit cloud render`). Canonical reference: **`pilot-sulawesi`**. Sister production study: **`tectonics-30s`**. Sister local-bake study: **`audio-mix`**. Archived sketch only: **`_archive/ref-tectonics-30s`**.

**MapLibre A-roll is local.** Before baking satellite/fill beds, read [`tools/geo-assets/README.md`](../../tools/geo-assets/README.md). Production-proven knobs live in `render_sulawesi_shots.mjs`. Modal only overlays + masters; it does not bake MapLibre frames.

---

## 1. Canonical study: `pilot-sulawesi`

| Item | Path / value |
| --- | --- |
| Spec | `studies/geoverum/pilot-sulawesi/SPEC.md` |
| Plan builder | `studies/geoverum/pilot-sulawesi/build_pilot.py` |
| Output EditPlan | `studies/geoverum/pilot-sulawesi/edit_plan.json` (written by builder) |
| Platform | `shorts_9x16_1080p` → `profiles/platforms/shorts_9x16_1080p.json` |
| Brand policy | `profiles/brands/geoverum/brand_style_policy.json` |
| Strategy | `render_strategy="hybrid"` (FFmpeg A-roll + transparent HyperFrames overlays) |
| Duration | `70.600s` / `2118` frames @ `30fps` / `1080x1920` |
| Job id | `geoverum_sulawesi_pilot` |

### Minimal artifacts required before Modal

1. **Shot MP4s** (silent cartographic beds), one per shot id in `SHOT_ORDER`:
   - `studies/geoverum/pilot-sulawesi/assets/shots/shot_01_hook_dive.mp4` … `shot_09_outro_cta.mp4`
2. **Subject boxes** (target-canvas, for overlay collision guardrails):
   - `studies/geoverum/pilot-sulawesi/assets/subject_boxes.json`
3. **Repo audio + transcript** (paths hardcoded in `build_pilot.py`):
   - `assets/audio/sulawesi_vo_clean.wav`
   - `assets/audio/sulawesi_transcript.json`
   - Epidemic BGM/SFX WAVs referenced in `build_pilot.py` (`music_c273725d-…`, `sfx_36d506f7-…`, `sfx_bf1e97b7-…`, `sfx_d0ba83c3-…`)
4. **Fonts**:
   - `assets/geo/fonts/SpaceGrotesk-Variable.ttf`
   - `assets/geo/fonts/ArchivoBlack-Regular.ttf`
5. **Brand + platform presets** (already in repo):
   - `profiles/brands/geoverum/brand_style_policy.json`
   - `profiles/platforms/shorts_9x16_1080p.json`
6. **Verified EditPlan JSON** after `build_pilot.py` / `vedit director verify`:
   - `studies/geoverum/pilot-sulawesi/edit_plan.json` with `verifier_passed: true`

Optional but used by the generic director path (not required if you use `build_pilot.py`):

- Probe JSON from `vedit probe analyze`
- Keyframes for `DecisionPort` box grounding

---

## 2. Exact CLI sequence

Use the director venv binary from repo root:

```bash
VEDIT=packages/director-py/.venv/bin/vedit
```

### One-time setup

```bash
# Rust probe
(cd packages/media-probe-rs && cargo test && cargo build --release)

# Python director (+ modal dependency)
(cd packages/director-py && uv venv --python 3.12 && uv sync --extra dev)

# HyperFrames compiler bridge
(cd packages/hf-compiler-ts && npm install && npm run build)

# Providers (DecisionPort / STT / Epidemic) — never commit secrets
cp config/providers.example.yaml config/providers.yaml
# Export env vars named in providers.yaml (LIQUID_API_KEY, XAI_API_KEY, EPIDEMIC_API_KEY, …)
$VEDIT providers auth   # interactive .env upsert where needed

# Modal (cloud only)
modal token set   # or: modal setup
```

### Production sequence (pilot / any EditPlan + Modal study)

```text
probe → (optional brand) → plan|build → verify → compile → [local master|cloud render] → audit
```

Concrete commands for **pilot-sulawesi** (hand-authored plan via `build_pilot.py`):

```bash
# 0) Probe source beds / VO as needed (telemetry + keyframes for DecisionPort)
$VEDIT probe hash studies/geoverum/pilot-sulawesi/assets/shots/shot_01_hook_dive.mp4
$VEDIT probe analyze assets/audio/sulawesi_vo_clean.wav --true-peak \
  > /tmp/sulawesi_vo_probe.json

# Optional DecisionPort spatial grounding on a target-canvas keyframe (exactly 1 image for box/boxes)
$VEDIT decide \
  --state '{"shot":"shot_06_palu_koro","canvas":"9:16"}' \
  --questions '[{"name":"subject","type":"boxes","instructions":"Landmass and labels to avoid"}]' \
  --image studies/geoverum/pilot-sulawesi/assets/shots/keyframes/shot_06.jpg

# Optional brand refresh from reference probes (Geoverum policy already checked in)
$VEDIT brand analyze --brand-id geoverum \
  --probe-file studies/geoverum/reference-calibration/ref-tectonics/probe.json \
  --probe-file studies/geoverum/reference-calibration/ref-ethiopia-toba/probe.json \
  -o profiles/brands/geoverum/brand_style_policy.json
$VEDIT brand exemplars profiles/brands/geoverum/brand_style_policy.json --role hook

# 1) Assemble + verify EditPlan (writes edit_plan.json, runs HF lint dry-check)
packages/director-py/.venv/bin/python studies/geoverum/pilot-sulawesi/build_pilot.py

# Equivalent CLI verify if plan already exists:
$VEDIT director verify \
  --plan-file studies/geoverum/pilot-sulawesi/edit_plan.json \
  --policy-file profiles/brands/geoverum/brand_style_policy.json \
  --platform shorts_9x16_1080p \
  --transcript-file assets/audio/sulawesi_transcript.json

# 2) Local compile + HyperFrames static lint (also done inside Modal; do locally first)
$VEDIT compile \
  --plan-file studies/geoverum/pilot-sulawesi/edit_plan.json \
  --out-dir studies/geoverum/pilot-sulawesi/hf_project \
  --platform shorts_9x16_1080p \
  --lint

# 3a) Preferred production path — Modal does compile → chunk render → hybrid master → QC
$VEDIT cloud render \
  --plan-file studies/geoverum/pilot-sulawesi/edit_plan.json \
  --platform shorts_9x16_1080p \
  --chunk-frames 180 \
  -o studies/geoverum/pilot-sulawesi/renders/geoverum_sulawesi_pilot_master.mp4

# 3b) Local alternative (no Modal) — render overlays yourself, then master
# (see audio-mix/build_audio_mix.py for plan_v2 / render_chunk_v2 / assemble_v2)
$VEDIT master \
  --plan-file studies/geoverum/pilot-sulawesi/edit_plan.json \
  --platform shorts_9x16_1080p \
  --overlay-video studies/geoverum/pilot-sulawesi/renders/overlay.mov \
  -o studies/geoverum/pilot-sulawesi/renders/local_master.mp4

# 4) Audit deliverable (Modal already runs QC; re-run locally after download)
$VEDIT audit \
  studies/geoverum/pilot-sulawesi/renders/geoverum_sulawesi_pilot_master.mp4 \
  --platform shorts_9x16_1080p
```

### Generic auto-plan path (probe-driven, not used by pilot)

When you do **not** hand-author clips in Python:

```bash
$VEDIT probe analyze path/to/source.mp4 --extract-keyframes /tmp/kf > /tmp/probe.json

$VEDIT director plan \
  --probe-file /tmp/probe.json \
  --policy-file profiles/brands/geoverum/brand_style_policy.json \
  --platform shorts_9x16_1080p \
  --transcript-file path/to/transcript.json \
  --strategy hybrid \
  --use-decision \
  --job-id geoverum_job \
  --project-id geoverum \
  -o /tmp/edit_plan.json

$VEDIT director verify \
  --plan-file /tmp/edit_plan.json \
  --policy-file profiles/brands/geoverum/brand_style_policy.json \
  --platform shorts_9x16_1080p \
  --transcript-file path/to/transcript.json

$VEDIT compile --plan-file /tmp/edit_plan.json --out-dir /tmp/hf_project --lint
$VEDIT cloud render --plan-file /tmp/edit_plan.json -o /tmp/master.mp4
$VEDIT audit /tmp/master.mp4 --platform shorts_9x16_1080p
```

Contracts gate (any change to schemas/presets):

```bash
$VEDIT contracts validate --json
$VEDIT platforms list
```

---

## 3. Key Python / TypeScript modules

| Role | Path |
| --- | --- |
| CLI entry | `packages/director-py/src/vedit/cli.py` (`probe`, `brand`, `director`, `compile`, `master`, `audit`, `cloud render`) |
| Pilot assembler | `studies/geoverum/pilot-sulawesi/build_pilot.py` |
| Audio-mix assembler (local bake reference) | `studies/geoverum/audio-mix/build_audio_mix.py` |
| EditPlan models | `packages/director-py/src/vedit/models.py` (`EditPlan`, `OverlayCompositionOp`, `VideoClipOp`, `AudioTrackOp`) |
| Plan synthesis | `packages/director-py/src/vedit/director/planner.py` (`build_edit_plan`) |
| Guardrail verify | `packages/director-py/src/vedit/director/verifier.py` (`verify_edit_plan`) |
| DecisionPort protocol | `packages/director-py/src/vedit/ports/decision.py` |
| Liquid D1 adapter | `packages/director-py/src/vedit/providers/decision/liquid_d1.py` |
| Brand analyzer | `packages/director-py/src/vedit/analyzers/brand_analyzer.py` |
| HF compile bridge | `packages/director-py/src/vedit/compiler/hf_bridge.py` (`compile_edit_plan`, `plan_distributed_v2`, `render_chunk_v2`, `assemble_v2`) |
| TS compiler | `packages/hf-compiler-ts/src/compiler.ts` (`compileEditPlanToHyperframes`) |
| Hybrid master + loudnorm | `packages/director-py/src/vedit/mastering/ffmpeg_master.py` |
| QC audit | `packages/director-py/src/vedit/mastering/qc_audit.py` |
| Modal app / workers | `packages/cloud-modal/src/vedit_cloud/app.py` |
| Modal worker image | `packages/cloud-modal/src/vedit_cloud/image.py` |
| EditPlan schema | `contracts/edit_plan.schema.json` |
| Brand director playbook | `.agents/skills/brand-director/SKILL.md` |

---

## 4. What Modal workers do vs local bake

### Modal (`vedit cloud render` → `submit_modal_render`)

Implemented in `packages/cloud-modal/src/vedit_cloud/app.py`:

1. **CAS stage** — Upload local `AssetRef` files by SHA-256 into Modal Volume `vedit-cas-cache` (`/vol/cas/sources/<sha><ext>`), rewrite plan paths.
2. **Orchestrator** (`orchestrate_distributed_render`, 4 vCPU / 8 GiB, 1200s):
   - `compile_edit_plan` + HyperFrames lint on the worker
   - `plan_distributed_v2` with `--chunk-frames` (default **180**, allowed **150–240**)
   - Fan-out `render_chunk_worker.starmap` — each chunk in a **fresh** Chromium turn with software GL (`--no-browser-gpu --use-gl=swiftshader`)
   - `assemble_v2` → transparent overlay MOV (hybrid) or full MP4 (`full_hf`)
   - `assemble_hybrid_deliverable` — cut A-roll, composite overlay, spectral carve, two-pass `-14.0 LUFS` / `<= -1.0 dBTP`
   - `audit_mastered_deliverable` — ffprobe + ebur128 QC
3. **Download** master MP4 from CAS to local `-o` path.

Worker image (`image.py`) builds Linux `x86_64` `vedit-probe` **inside** the container (never copy macOS ARM binaries), pins `chrome-headless-shell@152.0.7977.30`, and stages `contracts/`, `profiles/`, `packages/director-py`, `packages/hf-compiler-ts`.

### Local bake (no Modal)

| Path | What it does |
| --- | --- |
| `tools/geo-assets/render_sulawesi_shots.mjs` | **Production-proven** MapLibre A-roll bake (JPEG, ~1.5s idle, Darwin GPU). See `tools/geo-assets/README.md`. |
| `tools/geo-assets/bake_vertical_basemap.mjs` | Shared continuous-camera helper; must stay aligned with the sulawesi bake knobs. |
| `audio-mix/build_audio_mix.py` | Same EditPlan → `compile_edit_plan` → `plan_distributed_v2` → local `render_chunk_v2` loop → `assemble_v2` → `vedit master` / `assemble_hybrid_deliverable` → `vedit audit` |
| `vedit compile` + `vedit master --overlay-video` | You supply a pre-rendered overlay MOV; FFmpeg hybrid master only |
| `_archive/ref-tectonics-30s/bake_and_render.mjs` | Archived sketch only — bypasses EditPlan / Modal; do not ship |

Rule of thumb:

- **Ship / QC / cost-attributed cloud** → Modal (overlays + master only; A-roll already baked locally).
- **MapLibre satellite / fill beds** → local geo-assets bakers with the README contract — never assume Modal bakes them.
- **Iterate overlays on a laptop** → local `hf_bridge` chunk render or short sketch scripts.
- **Never** treat `bake_and_render.mjs` as the production mastering path for Geoverum.

---

## 5. Required env / config for Modal

| Requirement | Detail |
| --- | --- |
| Modal auth | `modal token set` (or `modal setup`); account must allow app `vedit-distributed-renderer` |
| Python deps | `modal>=1.6.0` via `packages/director-py` and `packages/cloud-modal` |
| Volume | Auto-created `vedit-cas-cache` (CAS mount `/vol/cas`) |
| Worker env (image) | `VEDIT_REPO_ROOT=/opt/vedit`, `VEDIT_PROBE_BIN=/usr/local/bin/vedit-probe`, `VEDIT_HF_COMPILER_CLI=…/hf-compiler-ts/dist/cli.js`, `HYPERFRAMES_CHROMIUM_FLAGS=--no-browser-gpu --use-gl=swiftshader`, `HYPERFRAMES_CHROME_SANDBOX=0`, `PRODUCER_BROWSER_GPU_MODE=software` |
| Host providers (plan/STT/decide only) | `config/providers.yaml` from `config/providers.example.yaml`; keys via env (`LIQUID_API_KEY`, `XAI_API_KEY`, `EPIDEMIC_API_KEY`, …). **Not** required on Modal workers for pure render/master of an already-verified plan |
| Secrets hygiene | Image build **ignores** `config/providers.yaml`; do not bake API keys into the Modal image |
| Local binaries | Host needs FFmpeg/ffprobe, Node ≥ 22, built `packages/hf-compiler-ts/dist/cli.js`, and release `vedit-probe` for local probe/compile |

---

## 6. Canonical 30s tectonics path — `tectonics-30s`

Production EditPlan study (not the archived PNG sketch under `_archive/ref-tectonics-30s`).

| Item | Path |
| --- | --- |
| Spec | `studies/geoverum/tectonics-30s/SPEC.md` |
| Basemap bake | `studies/geoverum/tectonics-30s/bake_tectonics_basemap.mjs` |
| Plan builder | `studies/geoverum/tectonics-30s/build_tectonics_30s.py` |
| EditPlan | `studies/geoverum/tectonics-30s/edit_plan.json` |
| Brand policy | `profiles/brands/geoverum/brand_style_policy.json` |
| Platform | `shorts_9x16_1080p` |

```bash
node studies/geoverum/tectonics-30s/bake_tectonics_basemap.mjs
packages/director-py/.venv/bin/python studies/geoverum/tectonics-30s/build_tectonics_30s.py

$VEDIT compile \
  --plan-file studies/geoverum/tectonics-30s/edit_plan.json \
  --out-dir studies/geoverum/tectonics-30s/hf_project --lint

$VEDIT cloud render \
  --plan-file studies/geoverum/tectonics-30s/edit_plan.json \
  --platform shorts_9x16_1080p \
  --chunk-frames 180 \
  -o studies/geoverum/tectonics-30s/renders/geoverum_tectonics_30s_master.mp4

$VEDIT audit \
  studies/geoverum/tectonics-30s/renders/geoverum_tectonics_30s_master.mp4 \
  --platform shorts_9x16_1080p
```

With `--chunk-frames 180` on 900 frames → **5** HyperFrames chunks.

---

## 7. Quick decision tree

```text
Need shippable Geoverum MP4 with LUFS QC?
  ├─ Have verified edit_plan.json + local assets?
  │    └─ vedit cloud render → vedit audit
  ├─ Assembling Sulawesi pilot?
  │    └─ build_pilot.py → cloud render
  ├─ Assembling 30s tectonics?
  │    └─ tectonics-30s/build_tectonics_30s.py → compile → cloud render
  └─ Debugging audio only?
       └─ audio-mix/build_audio_mix.py (local chunks OK)
```

---

## Related docs

- `docs/ARCHITECTURE.md` — ports, hybrid vs full_hf, cloud worker constraints
- `profiles/README.md` — brands vs platforms
- `studies/geoverum/pilot-sulawesi/SPEC.md` — 70.6s shot list
- `studies/geoverum/tectonics-30s/SPEC.md` — 30s tectonics production contract
- `studies/geoverum/audio-mix/SPEC.md` — audio DAG + local master reference
- `README.md` — repo quickstart and optional Modal note
