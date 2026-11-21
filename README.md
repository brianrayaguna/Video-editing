# vedit — Brand-Adaptive Video Directing & Mastering Engine

**vedit** is a modular, provider-agnostic video directing and mastering engine that combines deterministic media analysis (`Rust` + `FFmpeg`), calibrated omnimodal decision models, HTML/GSAP motion rendering (`HyperFrames`), and deterministic `FFmpeg` delivery mastering—with **optional** serverless cloud rendering via `Modal`.

It is designed for automated pipelines and AI directing clients to edit real footage and procedural motion graphics in the visual style of an analyzed brand, without generative video synthesis.

## Architecture Overview

| Package / Directory | Runtime | Responsibility |
| :--- | :--- | :--- |
| [`packages/media-probe-rs`](packages/media-probe-rs) | Rust (`vedit-probe`) | Single-pass `ffprobe` + `ffmpeg` pipe for SHA-256 CAS hashing, `scdet` shot cuts, `ebur128` loudness, `silencedetect`, Sobel sharpness, BT.709 band luminance, and CIELAB palette clustering. |
| [`packages/director-py`](packages/director-py) | Python 3.12 (`vedit`, `vedit-mcp`) | Capability ports (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`, `VideoBreakdownPort`), YAML-configured provider registry, schema validation, external project workspace lifecycle (`vedit project`), durable job checkpoints, brand profiling (`brand_analyzer`), planning/verification (`director`), HyperFrames compilation, `FFmpeg` mastering, visual/technical QC audit, OpenTimelineIO export, FastMCP server, and CLI. |
| [`packages/hf-compiler-ts`](packages/hf-compiler-ts) | Node >= 22 / TypeScript | Contracts and compilation bridge targeting pinned `@hyperframes/core` and `@hyperframes/producer` (`0.9.68`). |
| [`packages/cloud-modal`](packages/cloud-modal) | Python / Modal (Optional) | Serverless worker images and entrypoints for offloading headless Chromium / HyperFrames `BeginFrame` renders, DeepFilterNet speech denoising, and deterministic cloud reframing to Modal. |
| [`contracts`](contracts) | JSON Schema (Draft 2020-12) | Shared cross-runtime contracts (`brand_style_policy`, `editorial_playbook`, `brand_template`, `edit_plan`, `media_probe`, `platform_target`, `project_manifest`, `transcript`, `video_breakdown`). |
| [`profiles/platforms`](profiles/platforms) | JSON | Delivery mastering presets for YouTube (`16:9` 1080p/4K), Shorts, Reels, and TikTok (`9:16` 1080p). |
| [`profiles/brands/<brand_id>`](profiles/brands) | JSON / Markdown | Brand runtime policies, optional advisory playbooks, parameterized brand templates, and craft docs (decoupled from core engine code). See [`profiles/README.md`](profiles/README.md). |
| [`tools/geo-assets`](tools/geo-assets) | Python / Node.js | Deterministic open-licensed geospatial asset fetcher, SHA-256 manifest verifier (`assets/geo/MANIFEST.json`), build-time tile grader, offline XYZ tile server, and MapLibre basemap baker. |
| [`tools/rea-video`](tools/rea-video) | Python 3.12 (Isolated) | Isolated local forensic video breakdown toolchain (`rea-video[ocr]`) powering `VideoBreakdownPort` for high-accuracy brand profiling without polluting core or cloud dependencies. |
| External Projects (`VEDIT_PROJECTS_ROOT`) | Outside Engine Git Repo | Self-contained active editing projects managed by `vedit project init|status|validate`. See [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md). |

For detailed pipeline invariants, visual craft standards, cloud workflows, and external workspace rules, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`DESIGN.md`](DESIGN.md), [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md), [`docs/CLOUD_WORKFLOW.md`](docs/CLOUD_WORKFLOW.md), and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Execution & Rendering Modes

The local host operates cleanly as a thin control plane while heavy compute runs in the cloud:

- **Cloud Offload (`Modal` & Cloud APIs — Recommended for Constrained Hosts):** Run cloud STT (`xai` / `veed`), cloud neural speech denoising and reframing (`vedit clean-audio --provider modal_cloud`, `vedit reframe --provider modal_cloud`), cloud background matting (`veed`), and distributed HyperFrames rendering + EBU R128 mastering (`vedit cloud render`). Runbook: [`docs/CLOUD_WORKFLOW.md`](docs/CLOUD_WORKFLOW.md).
- **Local Deterministic Mode:** Compile motion projects with `vedit compile`, assemble hybrid deliverables locally with `vedit master`, export NLE timelines with `vedit export-otio`, and verify stream/loudness/visual compliance with `vedit audit`.

## End-to-End Pipeline & CLI Reference

All CLI commands are exposed through `vedit` (installed in `packages/director-py/.venv/bin/vedit`; command modules live in `packages/director-py/src/vedit/cli/`) and optionally over MCP via `vedit-mcp`:

- **External Project Workspace**
  - `vedit project init` / `vedit project status` / `vedit project validate` — Scaffold, inspect, and validate self-contained projects outside the engine repository under `VEDIT_PROJECTS_ROOT`.
- **Media Analysis & Brand Profiling**
  - `vedit probe hash` / `vedit probe analyze` — Compute content-addressed hashes and extract deterministic visual/audio telemetry.
  - `vedit breakdown survey` / `vedit breakdown analyze` / `vedit breakdown review` / `vedit breakdown apply-review` / `vedit breakdown import` — Run forensic shot/transition/audio/OCR breakdown, emit layered `VIDEO.md` + `video_breakdown.json`, and fuse multimodal visual reviews.
  - `vedit brand analyze` / `vedit brand exemplars` / `vedit brand validate` — Synthesize runtime policy + advisory playbook (fusing `--probe-file`, `--breakdown-file`, and `--transcript-file`), query playbook exemplars, validate brand trees.
- **Directing & Media Operations**
  - `vedit transcribe` — Generate word-level transcripts via the configured `TranscriptionPort`.
  - `vedit decide` — Run omnimodal edit decisioning against probe telemetry, transcripts, and brand policy.
  - `vedit director plan` / `vedit director verify` — Generate and validate structured `EditPlan` manifests.
  - `vedit search-audio` / `vedit clean-audio` — Query licensed audio catalogs and denoise speech stems (cloud `modal_cloud` DeepFilterNet or local `ffmpeg`).
  - `vedit reframe` / `vedit remove-background` — Apply aspect-ratio reframing (`modal_cloud` or `ffmpeg`) and cloud background matting (`veed`).
  - `vedit trim` / `vedit remove-silence` / `vedit restore-footage` — Local FFmpeg preprocessing: lossless or frame-accurate clip trims, voiceover pause removal (run before `transcribe`), and stabilization/denoise/deinterlace for raw footage.
- **Compilation, Rendering, Interop & Mastering**
  - `vedit compile` — Compile an `EditPlan` (resolving project-relative assets) into a HyperFrames project bundle.
  - `vedit export-otio` — Export an `EditPlan` into an OpenTimelineIO `.otio` timeline for external NLE review.
  - `vedit cloud render` — Submit a verified `EditPlan` to Modal for remote distributed rendering, hybrid mastering, and QC.
  - `vedit master` — Assemble final deliverables against a target platform preset (`youtube_16x9_1080p`, `youtube_16x9_4k`, `shorts_9x16_1080p`, `reels_9x16_1080p`, `tiktok_9x16_1080p`) with two-pass `ebur128` loudnorm.
  - `vedit audit` — Verify output streams, frame rate, resolution, loudness compliance, black/freeze visual anomalies, and optional VMAF.
- **System & Registry Inspection**
  - `vedit contracts validate` — Validate JSON Schemas and platform mastering profiles.
  - `vedit platforms list` — List available delivery presets.
  - `vedit providers list` / `vedit providers auth` — Inspect configured capability providers and credential status.

## Prerequisites

- **FFmpeg & FFprobe** (tested with FFmpeg 9.x; `scdet`, `blackdetect`, `silencedetect`, and `ebur128` filters enabled)
- **Rust & Cargo** (`rustc >= 1.85`, Edition 2024)
- **Python 3.12** managed via `uv`
- **Node.js >= 22** and `npm`
- **Modal CLI** *(optional, only required for `vedit cloud render`)*

## Quickstart

### 1. Build the Native Media Probe

```bash
cd packages/media-probe-rs
cargo test && cargo build --release
```

### 2. Set Up the Python Directing Environment

```bash
cd packages/director-py
uv venv --python 3.12
uv sync --extra dev
```

### 3. Install & Test the TypeScript HyperFrames Bridge

```bash
cd packages/hf-compiler-ts
npm install
npm run typecheck && npm run build && npm test
```

### 4. Configure Providers (Optional for Local Probe/Contract Checks)

Copy `config/providers.example.yaml` to `config/providers.yaml` and export the referenced environment variables (never commit credentials or tokens).

If you plan to use optional Modal cloud rendering, authenticate your Modal profile (`modal token set`) and ensure `packages/director-py` is synced with the Modal dependency.

## Verification

Run the full verification suite across all runtimes from the repository root:

```bash
# Rust probe tests and release build
(cd packages/media-probe-rs && cargo test && cargo build --release)

# TypeScript compiler bridge typecheck, build, and tests
(cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test)

# Python linting, unit/integration tests, and contract validation
packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal
packages/director-py/.venv/bin/pytest -v packages/director-py/tests
packages/director-py/.venv/bin/vedit contracts validate --json
packages/director-py/.venv/bin/vedit platforms list
packages/director-py/.venv/bin/vedit providers list --json
```
