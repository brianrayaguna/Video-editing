# vedit — Brand-Adaptive Video Directing & Mastering Engine

**vedit** is a modular, provider-agnostic video directing and mastering engine that combines deterministic media analysis (`Rust` + `FFmpeg`), calibrated omnimodal decision models, HTML/GSAP motion rendering (`HyperFrames`), and deterministic `FFmpeg` delivery mastering—with **optional** serverless cloud rendering via `Modal`.

It is designed for automated pipelines and AI directing clients to edit real footage and procedural motion graphics in the visual style of an analyzed brand, without generative video synthesis.

## Architecture Overview

| Package / Directory | Runtime | Responsibility |
| :--- | :--- | :--- |
| [`packages/media-probe-rs`](packages/media-probe-rs) | Rust (`vedit-probe`) | Single-pass `ffprobe` + `ffmpeg` pipe for SHA-256 CAS hashing, `scdet` shot cuts, `ebur128` loudness, `silencedetect`, Sobel sharpness, BT.709 band luminance, and CIELAB palette clustering. |
| [`packages/director-py`](packages/director-py) | Python 3.12 (`vedit`) | Capability ports (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`), YAML-configured provider registry, schema validation, durable job checkpoints, brand profiling (`brand_analyzer`), planning/verification (`director`), HyperFrames compilation, `FFmpeg` mastering, audit, and CLI. |
| [`packages/hf-compiler-ts`](packages/hf-compiler-ts) | Node >= 22 / TypeScript | Contracts and compilation bridge targeting pinned `@hyperframes/core` and `@hyperframes/producer` (`0.9.65`). |
| [`packages/cloud-modal`](packages/cloud-modal) | Python / Modal (Optional) | Optional serverless worker image and entrypoint for offloading headless Chromium / HyperFrames `BeginFrame` renders to Modal. |
| [`contracts`](contracts) | JSON Schema (Draft 2020-12) | Shared cross-runtime contracts (`brand_style_policy`, `edit_plan`, `media_probe`, `platform_target`, `transcript`). |
| [`profiles/platforms`](profiles/platforms) | JSON | Delivery mastering presets for YouTube (`16:9` 1080p/4K), Shorts, Reels, and TikTok (`9:16` 1080p). |
| [`profiles/<brand_id>`](profiles) | JSON / Markdown | Brand-specific editing policies (`brand_style_policy.json`), visual tokens, and exemplar references (decoupled from core engine code). |
| [`tools/geo-assets`](tools/geo-assets) | Python / Node.js | Deterministic open-licensed geospatial asset fetcher, SHA-256 manifest verifier (`assets/geo/MANIFEST.json`), build-time tile grader, and local offline XYZ tile server. |
| [`studies/<brand_id>`](DESIGN.md) | HyperFrames HTML/GSAP | Isolated component studies and production compositions governed by [`DESIGN.md`](DESIGN.md). |

For detailed pipeline invariants, visual craft standards, and design rationale, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`DESIGN.md`](DESIGN.md), and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Execution & Rendering Modes

Rendering and mastering run **locally by default**. Cloud execution is strictly optional:

- **Local Rendering & Mastering (Default):** Compile motion projects with `vedit compile`, render locally via HyperFrames and `FFmpeg`, assemble hybrid deliverables with `vedit master` (including two-pass `-14.0 LUFS` loudness normalization), and verify output compliance with `vedit audit`. No cloud account is required.
- **Optional Cloud Offload (`Modal`):** Use `vedit cloud render` (`packages/cloud-modal`) when you want to offload heavy headless Chromium renders to serverless workers (for example, on memory-constrained hosts or for parallel batch rendering).

## End-to-End Pipeline & CLI Reference

All CLI commands are exposed through `vedit` (installed in `packages/director-py/.venv/bin/vedit`):

- **Media Analysis & Brand Profiling**
  - `vedit probe hash` / `vedit probe analyze` — Compute content-addressed hashes and extract deterministic visual/audio telemetry.
  - `vedit brand analyze` / `vedit brand exemplars` — Extract `BrandStylePolicy` profiles from reference videos and inspect exemplar palettes/typography.
- **Directing & Media Operations**
  - `vedit transcribe` — Generate word-level transcripts via the configured `TranscriptionPort`.
  - `vedit decide` — Run omnimodal edit decisioning against probe telemetry, transcripts, and brand policy.
  - `vedit director plan` / `vedit director verify` — Generate and validate structured `EditPlan` manifests.
  - `vedit search-audio` / `vedit clean-audio` — Query licensed audio catalogs and denoise/process stems.
  - `vedit reframe` / `vedit remove-background` — Apply subject-aware reframing and background matting.
- **Compilation, Rendering & Mastering**
  - `vedit compile` — Compile an `EditPlan` into a HyperFrames project bundle.
  - `vedit cloud render` — *(Optional)* Submit a compiled bundle to Modal for remote headless Chromium rendering.
  - `vedit master` — Assemble final deliverables against a target platform preset (`youtube_16x9_1080p`, `youtube_16x9_4k`, `shorts_9x16_1080p`, `reels_9x16_1080p`, `tiktok_9x16_1080p`) with two-pass `ebur128` loudnorm.
  - `vedit audit` — Verify output streams, frame rate, resolution, and loudness compliance.
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
packages/director-py/.venv/bin/ruff check packages/director-py
packages/director-py/.venv/bin/pytest -v packages/director-py/tests
packages/director-py/.venv/bin/vedit contracts validate --json
packages/director-py/.venv/bin/vedit platforms list
packages/director-py/.venv/bin/vedit providers list --json
```
