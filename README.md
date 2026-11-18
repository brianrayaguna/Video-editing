# vedit — Brand-Adaptive Video Directing & Distributed Render Engine

**vedit** is a modular, provider-agnostic video directing and assembly engine combining deterministic media analysis (`Rust` + `FFmpeg`), calibrated omnimodal decision models, HTML/GSAP motion rendering (`HyperFrames`), and distributed serverless execution (`Modal`).

It is built for automated pipelines and AI directing clients to edit real footage and procedural motion graphics in the style of an analyzed brand—without generative video synthesis.

## Architecture Overview

| Package | Runtime | Responsibility |
| :--- | :--- | :--- |
| [`packages/media-probe-rs`](packages/media-probe-rs) | Rust (`vedit-probe`) | Single-pass `ffprobe` + `ffmpeg` pipe for SHA-256 CAS hashing, `scdet` shot cuts, `ebur128` loudness, `silencedetect`, Sobel sharpness, BT.709 band luminance, and CIELAB palette clustering. |
| [`packages/director-py`](packages/director-py) | Python 3.12 (`vedit`) | Capability ports (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`), YAML-configured provider registry, schema validation, durable job checkpoints, brand profiling, and CLI. |
| [`packages/hf-compiler-ts`](packages/hf-compiler-ts) | Node >= 22 / TypeScript | Contracts and compilation bridge targeting pinned `@hyperframes/core` and `@hyperframes/producer` (`0.9.65`). |
| [`contracts`](contracts) | JSON Schema (Draft 2020-12) | Shared cross-runtime contracts (`brand_style_policy`, `edit_plan`, `media_probe`, `platform_target`, `transcript`). |
| [`profiles/platforms`](profiles/platforms) | JSON | Delivery mastering presets for YouTube (`16:9` 1080p/4K), Shorts, Reels, and TikTok (`9:16` 1080p). |

For detailed pipeline invariants and design rationale, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Prerequisites

- **FFmpeg & FFprobe** (tested with FFmpeg 9.x; `scdet`, `blackdetect`, `silencedetect`, `ebur128` enabled)
- **Rust & Cargo** (`rustc >= 1.85` / Edition 2024)
- **Python 3.12** managed via `uv`
- **Node.js >= 22** & `npm`

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

### 3. Install the TypeScript HyperFrames Bridge
```bash
cd packages/hf-compiler-ts
npm install
npm run typecheck && npm run build
```

### 4. Configure Providers (Optional for Local Probe/Contract Checks)
Copy `config/providers.example.yaml` to `config/providers.yaml` and export the referenced environment variables (never commit secrets).

### 5. Run Verification & CLI Checks
```bash
# Python lint + unit & integration tests
packages/director-py/.venv/bin/ruff check packages/director-py
packages/director-py/.venv/bin/pytest -v packages/director-py/tests

# Validate JSON schemas and platform presets
packages/director-py/.venv/bin/vedit contracts validate --json
packages/director-py/.venv/bin/vedit platforms list
packages/director-py/.venv/bin/vedit providers list --json

# Probe a media file in a single pass
packages/director-py/.venv/bin/vedit probe analyze path/to/video.mp4 --json
```
