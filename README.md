# vedit: Brand-Adaptive Video Directing & Mastering Engine

**vedit** is a modular, provider-agnostic video directing and mastering engine that combines deterministic media analysis (`Rust` and `FFmpeg`), calibrated omnimodal decisioning, procedural HTML/GSAP motion rendering (`HyperFrames`), and deterministic `FFmpeg` delivery mastering, with optional serverless cloud rendering via `Modal`.

It is designed for automated pipelines and AI directing clients to edit real footage and procedural motion graphics in the visual style of an analyzed brand, without generative video synthesis.

## Core Capabilities

- **Deterministic Media Telemetry:** Single-pass media probing extracts content-addressed SHA-256 hashes, shot cut boundaries, integrated loudness, silence intervals, Sobel sharpness, BT.709 luminance bands, and CIELAB color palettes.
- **Decoupled Brand Profiling:** Forensic reference breakdown and spatial analysis synthesize runtime brand policies, executable directing idioms, advisory editorial playbooks, parameterized templates, and external per-brand episodic memory independent of core engine code.
- **Dual-Gate Directing & Critique Loop:** Transcript readiness audits, typed storyboards, pre-render idiom gating, grid-anchored visual contact sheets, and surgical beat-level fixes enforce visual and editorial standards before final delivery.
- **Procedural Motion & Geospatial Tooling:** A TypeScript compilation bridge translates `EditPlan` manifests into `HyperFrames` compositions, paired with open-licensed tile grading, offline XYZ serving, declarative `MapLibre` scene baking, bottom-band caption generation, and ducked documentary audio mixing.
- **Hybrid Local/Cloud Execution & QC Mastering:** The local host acts as a thin control plane while heavy speech denoising, reframing, and distributed rendering can offload to `Modal`, concluding with `OpenTimelineIO` export, two-pass EBU R128 mastering, and automated deliverable audits.

## Repository Structure

| Package / Directory | Runtime | Responsibility |
| :--- | :--- | :--- |
| [`packages/media-probe-rs`](packages/media-probe-rs) | Rust (`vedit-probe`) | Single-pass `ffprobe` and `ffmpeg` pipe for SHA-256 CAS hashing, `scdet` shot cuts, `ebur128` loudness, `silencedetect`, Sobel sharpness, BT.709 band luminance, and CIELAB palette clustering. |
| [`packages/director-py`](packages/director-py) | Python `>=3.12,<3.14` (`vedit`, `vedit-mcp`) | Capability ports (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`, `VideoBreakdownPort`, `GeoImageryPort`), YAML-configured provider registry, schema validation, external project workspace lifecycle (`vedit project`), durable job checkpoints, brand profiling, planning and verification, `HyperFrames` compilation, `FFmpeg` mastering, visual/technical QC audit, `OpenTimelineIO` export, FastMCP server, and CLI. |
| [`packages/hf-compiler-ts`](packages/hf-compiler-ts) | Node.js `>=22` / TypeScript | Contracts and compilation bridge targeting pinned `@hyperframes/core`, `@hyperframes/lint`, and `@hyperframes/producer` (`0.9.68`). |
| [`packages/cloud-modal`](packages/cloud-modal) | Python / Modal (Optional) | Serverless worker images and entrypoints for offloading headless Chromium / `HyperFrames` `BeginFrame` renders, `DeepFilterNet` speech denoising, and deterministic cloud reframing to `Modal`. |
| [`contracts`](contracts) | JSON Schema (Draft 2020-12) | Shared cross-runtime contracts (`brand_memory`, `brand_style_policy`, `brand_template`, `critique_packet`, `directing_idioms`, `edit_plan`, `editorial_playbook`, `media_probe`, `platform_target`, `project_manifest`, `spatial_forensics`, `storyboard`, `transcript`, `video_breakdown`). |
| [`profiles/platforms`](profiles/platforms) | JSON | Delivery mastering presets for landscape (`16:9` 1080p and 4K) and vertical (`9:16` 1080p) targets, inspectable via `vedit platforms list`. |
| [`profiles/brands`](profiles/brands) | JSON / Markdown | Brand runtime policies, executable directing idioms, optional advisory playbooks, parameterized brand templates, and craft/directing guides decoupled from core engine code. See [`profiles/README.md`](profiles/README.md). |
| [`tools/geo-assets`](tools/geo-assets) | Python / Node.js | Deterministic open-licensed geospatial asset fetcher, SHA-256 manifest verifier (`assets/geo/MANIFEST.json`), build-time tile grader, offline XYZ tile server, and `MapLibre` basemap/scene bakers. |
| [`tools/rea-video`](tools/rea-video) | Python 3.12 (Isolated) | Isolated local forensic video breakdown toolchain powering `VideoBreakdownPort` for brand profiling without polluting core or cloud dependencies. |
| [`tools/spatial-forensics`](tools/spatial-forensics) | Python 3.12 (Isolated) | Isolated local spatial, grid, hierarchy, typography, and motion forensics analyzer producing `spatial_forensics.json` and visual blueprints (`vedit breakdown structure`). |
| External Projects (`VEDIT_PROJECTS_ROOT`) | Outside Engine Git Repo | Self-contained active editing projects managed via `vedit project init`, `status`, and `validate`. See [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md). |

## Execution Modes

- **Local Deterministic Mode:** Compile motion projects with `vedit compile`, assemble hybrid deliverables locally with `vedit master`, export NLE timelines with `vedit export-otio`, and verify stream, loudness, and visual compliance with `vedit audit`.
- **Cloud Offload Mode (Optional):** Keep the local host as a thin control plane while offloading speech-to-text and decisioning through configured capability ports (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`), neural speech denoising and reframing (`vedit clean-audio --provider modal_cloud`, `vedit reframe --provider modal_cloud`), and distributed `HyperFrames` rendering with EBU R128 mastering (`vedit cloud render`). See [`docs/CLOUD_WORKFLOW.md`](docs/CLOUD_WORKFLOW.md).

## CLI & MCP Reference

All CLI commands are exposed through `vedit` (installed at `packages/director-py/.venv/bin/vedit`, with command modules in `packages/director-py/src/vedit/cli/`) and optionally over MCP via `vedit-mcp`.

### External Project Workspace

| Command | Purpose |
| :--- | :--- |
| `vedit project init` | Scaffold a self-contained project directory outside the engine repository under `VEDIT_PROJECTS_ROOT`. |
| `vedit project status` | Inspect project manifest state, staged inputs, checkpoints, and render artifacts. |
| `vedit project validate` | Validate project structure, manifest schemas, and asset path containment. |

### Media Analysis & Brand Profiling

| Command | Purpose |
| :--- | :--- |
| `vedit probe hash` | Compute content-addressed SHA-256 hashes for media files. |
| `vedit probe analyze` | Extract deterministic visual and audio telemetry (`media_probe.json`). |
| `vedit breakdown survey` | Run one step of the visual-first contact-sheet survey pass. |
| `vedit breakdown analyze` | Run forensic shot, transition, audio, and OCR breakdown (`VIDEO.md` and `video_breakdown.json`). |
| `vedit breakdown structure` | Extract latent grid, visual hierarchy, typography/WCAG, motion easing, and SoM blueprints (`spatial_forensics.json`). |
| `vedit breakdown review` | Prepare `review_tasks.json` and `review_answers.json` for visual verification. |
| `vedit breakdown apply-review` | Fuse visual review answers back into breakdown outputs. |
| `vedit breakdown import` | Normalize an existing forensic breakdown directory into `VideoBreakdownResult` JSON. |
| `vedit brand analyze` | Synthesize runtime `BrandStylePolicy` and advisory `EditorialPlaybook` from probes and breakdowns. |
| `vedit brand calibrate-idioms` | Measure annotated reference storyboards and propose or apply directing idiom parameters. |
| `vedit brand invert-reference` | Draft a reference storyboard from telemetry and emit an exception review queue. |
| `vedit brand exemplars` | Query matching exemplars from an `EditorialPlaybook` `exemplar_bank`. |
| `vedit brand memory` | Inspect and record external per-brand episodic memory. |
| `vedit brand validate` | Validate a specific brand tree or all trees under `profiles/brands/`. |

### Directing, Storyboarding & Visual Critique

| Command | Purpose |
| :--- | :--- |
| `vedit transcribe` | Generate word-level transcripts via the configured `TranscriptionPort`. |
| `vedit decide` | Evaluate calibrated edit decisions against probe telemetry, transcripts, and brand policy via `DecisionPort`. |
| `vedit storyboard readiness` | Audit a transcript for visualizability and breath-pause readiness prior to voiceover lock. |
| `vedit storyboard context` | Retrieve advisory playbook exemplars, triggers, and brand memory warnings for a storyboard. |
| `vedit storyboard auto` | Build a typed storyboard from narration (with `--decision auto\|on\|off` semantic enrichment) and optionally layer director instructions on top. |
| `vedit storyboard gate-prerender` | Run pre-render deterministic and `DecisionPort` semantic storyboard critique (`--decision auto\|on\|off`). |
| `vedit storyboard check` | Validate a storyboard against the brand's executable directing idioms. |
| `vedit storyboard journey` | Compile route head, camera, route width, and callout positions from a journey storyboard. |
| `vedit critique packet` | Run deterministic checks, render grid-anchored contact sheets, score visual rubrics via `DecisionPort` when enabled (`--decision auto\|on\|off`), and emit the review form. |
| `vedit critique apply-fixes` | Apply typed surgical critique fixes onto unfrozen beats with regression rollback. |
| `vedit critique gate` | Decide pass/fail from a completed critique packet and report remaining issues. |
| `vedit director plan` | Generate structured `EditPlan` manifests. |
| `vedit director verify` | Validate `EditPlan` specifications against contracts and brand constraints. |

### Geospatial & Camera Tooling

| Command | Purpose |
| :--- | :--- |
| `vedit camera list` | List reusable map camera move presets for basemap bakes. |
| `vedit camera expand` | Expand camera move plans into smooth per-frame camera tracks. |
| `vedit geo prepare` | Fetch project AOI satellite tiles via `GeoImageryPort` (`google_tiles` primary with `open_imagery` fallback, without dirtying `MANIFEST.json`) and extract GeoJSON vectors. |
| `vedit geo validate-scene` | Validate `map_scene.json` against brand craft, sharpness, and clutter guardrails. |
| `vedit geo build-captions` | Generate locked boxless bottom-band ASS subtitles. |
| `vedit geo mix-audio` | Mix voiceover, ducked documentary background music, and scene-synced kinetic SFX to `-14.0 LUFS`. |
| `vedit geo bake-scene` | Expand smooth camera plans and bake declarative world-space map scenes via `MapLibre`. |
| `vedit geo camera-track` | Measure camera shake in a measured track and optionally write a denoised copy. |

### Media Operations & Preprocessing

| Command | Purpose |
| :--- | :--- |
| `vedit search-audio` | Search licensed music or SFX catalogs via `AudioCatalogPort`. |
| `vedit clean-audio` | Denoise spoken audio stems via `MediaOpsPort` (cloud `DeepFilterNet` or local `FFmpeg`). |
| `vedit reframe` | Apply target aspect-ratio reframing via `MediaOpsPort` (`modal_cloud` or `ffmpeg`). |
| `vedit remove-background` | Apply cloud background matting via `MediaOpsPort`. |
| `vedit trim` | Trim clips locally (lossless stream copy by default or frame-accurate). |
| `vedit remove-silence` | Cut long pauses from a voiceover locally prior to `vedit transcribe`. |
| `vedit restore-footage` | Stabilize, denoise, and optionally deinterlace raw footage locally with `FFmpeg`. |

### Compilation, Rendering, Interop & Mastering

| Command | Purpose |
| :--- | :--- |
| `vedit compile` | Compile an `EditPlan` (resolving project-relative assets) into a `HyperFrames` project bundle and run static checks. |
| `vedit export-otio` | Export an `EditPlan` into an `OpenTimelineIO` (`.otio`) timeline for external NLE review. |
| `vedit cloud render` | Submit a verified `EditPlan` to `Modal` for distributed rendering, hybrid mastering, and QC. |
| `vedit master` | Assemble hybrid cuts, composite overlays, and master deliverables against a platform preset with two-pass `-14.0 LUFS` loudnorm. |
| `vedit audit` | Verify output streams, frame rate, resolution, EBU R128 loudness compliance, black/freeze anomalies, and optional VMAF. |

### System & Registry Inspection

| Command | Purpose |
| :--- | :--- |
| `vedit doctor` | Verify local toolchain readiness (`ffmpeg`, `ffprobe`, `vedit-probe`, Node.js, isolated tool venvs, and providers). |
| `vedit contracts validate` | Validate JSON Schemas, platform mastering presets, and brand trees. |
| `vedit contracts generate-ts` | Generate TypeScript contract types from JSON Schemas (`--check` guards against schema drift). |
| `vedit platforms list` | List available delivery mastering targets. |
| `vedit providers list` | Inspect configured capability providers and active bindings. |
| `vedit providers auth` | Inspect credential and authentication readiness for configured providers. |

## Prerequisites

- **FFmpeg & FFprobe:** Tested with FFmpeg 9.x (`scdet`, `blackdetect`, `silencedetect`, and `ebur128` filters enabled).
- **Rust & Cargo:** `rustc >= 1.85` (Edition 2024).
- **Python:** `>=3.12,<3.14` managed via `uv`.
- **Node.js & npm:** Node.js `>=22`.
- **Modal CLI (Optional):** Required only for `vedit cloud render` and `modal_cloud` media operations.

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

Include optional extras as needed: `--extra mcp` for the `vedit-mcp` FastMCP server and `--extra interop` for `OpenTimelineIO` export.

### 3. Install & Test the TypeScript HyperFrames Bridge

```bash
cd packages/hf-compiler-ts
npm install
npm run typecheck && npm run build && npm test
```

### 4. Configure Providers (Optional for Local Probe/Contract Checks)

Copy `config/providers.example.yaml` to `config/providers.yaml` and export the referenced environment variables (never commit credentials or tokens).

If using optional `Modal` cloud rendering, authenticate your `Modal` profile (`modal token set`) and ensure `packages/director-py` is synced with the `modal` dependency.

## Verification

Run the full verification suite across all runtimes from the repository root:

```bash
# Rust probe tests and release build
(cd packages/media-probe-rs && cargo test && cargo build --release)

# TypeScript compiler bridge typecheck, build, and tests
(cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test)

# Geo asset tooling tests (tile server, TTF metadata parity, scene modules, determinism)
node --test tools/geo-assets/*.test.mjs tools/geo-assets/scene/*.test.mjs

# Python linting, unit/integration tests, and contract sync/validation
packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal
packages/director-py/.venv/bin/pytest -v packages/director-py/tests
packages/director-py/.venv/bin/vedit contracts validate --json
packages/director-py/.venv/bin/vedit contracts generate-ts --check
packages/director-py/.venv/bin/vedit platforms list
packages/director-py/.venv/bin/vedit providers list --json
```

## Documentation

| Document | Scope |
| :--- | :--- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture, capability ports, and pipeline invariants. |
| [`DESIGN.md`](DESIGN.md) | Engine-wide composition, motion, and repository boundary rules. |
| [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md) | External project directory contract (`VEDIT_PROJECTS_ROOT`). |
| [`docs/CLOUD_WORKFLOW.md`](docs/CLOUD_WORKFLOW.md) | End-to-end `EditPlan`, compilation, `Modal` render, and audit workflow. |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Architecture milestones and planned capabilities. |
| [`profiles/README.md`](profiles/README.md) | Separation between platform mastering targets and brand profiles. |
| [`tools/geo-assets/README.md`](tools/geo-assets/README.md) | Offline geospatial tile grading and `MapLibre` basemap capture contract. |
| [`tools/rea-video/README.md`](tools/rea-video/README.md) | Isolated forensic video breakdown toolchain setup and usage. |
| [`tools/spatial-forensics/README.md`](tools/spatial-forensics/README.md) | Isolated spatial, typography, and motion forensics analyzer setup. |
