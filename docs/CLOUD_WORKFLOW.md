# Cloud Production Workflow (Modal Serverless)

End-to-end production spine for executing verified `EditPlan` manifests on **Modal** (`vedit-distributed-renderer`) from external project folders under `VEDIT_PROJECTS_ROOT`.

## Pipeline Sequence

```text
project init -> clean-audio (cloud) -> transcribe (cloud) -> probe -> plan -> verify -> compile --lint -> cloud render -> audit
```

## One-Time Cloud Setup

```bash
# Authenticate Modal CLI
modal token set

# Deploy the warm serverless app (enables memory snapshots and scaledown windows)
modal deploy packages/cloud-modal/src/vedit_cloud/app.py
```

The deployed Modal app (`vedit-distributed-renderer`) exposes:
- `orchestrate_distributed_render` — compiles HyperFrames scenes, partitions plain text/captions onto the native FFmpeg `libass` fast-path, fans out sparse animated windows via `render_chunk_worker.starmap`, masters two-pass `-14.0 LUFS` / `<= -1.0 dBTP` audio, runs technical + visual QC (`audit_mastered_deliverable`), and cleans intermediate volume scratch directories after QC passes.
- `render_chunk_worker` — renders bounded HyperFrames chunks (`150–240` frames) inside isolated software-GL Chromium containers (`--no-browser-gpu --use-gl=swiftshader`).
- `clean_audio_cloud` — runs 48 kHz neural speech enhancement via `DeepFilterNet` on Modal CPU (`vedit clean-audio --provider modal_cloud`).
- `reframe_video_cloud` — runs deterministic Lanczos + `bt709` aspect-ratio reframing on Modal CPU (`vedit reframe --provider modal_cloud`).

## Content-Addressed Storage (CAS)

- All local project media files referenced by `EditPlan.assets` or `modal_cloud` media operations are hashed with SHA-256 and deduplicated into Modal Volume v2 (`vedit-cas-cache-v2`) under `/vol/cas/sources/<sha256><ext>`.
- Relative asset paths inside external `EditPlan` manifests are resolved automatically before upload.
- Container images exclude `config/providers.yaml` and `.env`; credentials stay on the directing host or in explicit Modal Secrets.

## Execution Commands

```bash
PROJECT="$VEDIT_PROJECTS_ROOT/<brand_id>/<project_id>"
VEDIT="packages/director-py/.venv/bin/vedit"

# 1. Cloud speech denoising before transcription (Audio Processing DAG)
$VEDIT clean-audio "$PROJECT/inputs/vo_raw.wav" "$PROJECT/media/audio/vo_clean.wav" \
  --provider modal_cloud

# 2. Cloud speech-to-text transcription (configured TranscriptionPort)
$VEDIT transcribe "$PROJECT/media/audio/vo_clean.wav" \
  > "$PROJECT/analysis/transcripts/vo.json"

# 3. Verify EditPlan against brand policy and platform guardrails
$VEDIT director verify \
  --plan-file "$PROJECT/plan/edit_plan.json" \
  --policy-file profiles/brands/<brand_id>/brand_style_policy.json \
  --brand-dir profiles/brands/<brand_id> \
  --platform shorts_9x16_1080p \
  --transcript-file "$PROJECT/analysis/transcripts/vo.json" \
  --update-plan

# 4. Dry-check HyperFrames compilation and static lint
$VEDIT compile \
  --plan-file "$PROJECT/plan/edit_plan.json" \
  --out-dir "$PROJECT/build/hf_project" \
  --platform shorts_9x16_1080p \
  --lint

# 5. Distributed cloud render, hybrid mastering, and QC
$VEDIT cloud render \
  --plan-file "$PROJECT/plan/edit_plan.json" \
  --platform shorts_9x16_1080p \
  --chunk-frames 180 \
  -o "$PROJECT/output/master.mp4"

# 6. Local post-download audit
$VEDIT audit "$PROJECT/output/master.mp4" --platform shorts_9x16_1080p
```
