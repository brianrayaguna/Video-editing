# System Architecture Rules

These rules govern all media pipelines, composition compilers, and provider integrations within this repository.

## 1. Capability-First Abstraction (Ports & Adapters)
- Core modules (`analyzers`, `director`, `mastering`, `cli`) and documentation must depend exclusively on capability interfaces in `vedit.ports` (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`, `VideoBreakdownPort`).
- Concrete vendor integrations live under `vedit.providers` and are resolved solely through `ProviderRegistry` and YAML/environment configuration. Never hardcode vendor assumptions in core logic or agent skills.

## 2. Strict Prohibition on Generative Video
- This system processes, indexes, directs, and assembles real source media alongside procedural HTML/GSAP motion graphics rendered with HyperFrames.
- Do not add, expose, or invoke generative AI video, synthetic avatar, or lip-sync synthesis endpoints in any port, provider, or workflow.
- Forensic breakdown providers (`VideoBreakdownPort`) must strictly whitelist non-generative analysis subcommands only; never expose or invoke generative remake commands from external breakdown tools.

## 3. Mandatory Pipeline Ordering Invariants
1. **Audio Processing DAG**: Run optional pause removal (`vedit remove-silence`) and speech denoising (`MediaOpsPort.clean_audio`) exclusively on isolated speech stems **before** speech-to-text transcription (`TranscriptionPort`), and never after mixing music or sound effects. Apply spectral voiceover carving to background music against the voiceover group, mix, and master via two-pass EBU R128 toward `-14.0 LUFS` integrated and `<= -1.0 dBTP` true peak (`48 kHz` stereo AAC-LC).
2. **Target-Canvas Spatial Grounding**: Run `DecisionPort` bounding-box detection (`box`/`boxes`) on target-aspect-ratio frames **after** reframing or cropping (for example, on `9:16` output frames), never on uncropped source geometry.
3. **Decision Batching**: Extract shot boundaries first via `vedit-probe` / FFmpeg. Request `box`/`boxes` once per shot that carries overlays, and batch classification/scoring queries up to provider request limits (`<= 8` images, `<= 128` questions).

## 4. HyperFrames & Cloud Worker Performance
- Never apply animated CSS `backdrop-filter` or `filter: blur()` in HyperFrames compositions; pre-render static blurred assets instead.
- CPU cloud rendering workers must pass `--no-browser-gpu` with software WebGL (`swiftshader`), partition long timelines into short chunks (`150–240` frames) to bound Chromium memory growth, and recycle browser processes per chunk.
- Compile native Linux `x86_64` binaries (`vedit-probe`) directly inside the cloud container image build; never copy macOS ARM64 binaries into Linux containers.
- Keep `@hyperframes/core`, `@hyperframes/lint`, and `@hyperframes/producer` pinned explicitly (`0.9.68`) across `packages/hf-compiler-ts` and cloud container images.
- Keep heavy ML and video rendering off the local host: route STT through cloud `TranscriptionPort` (`xai` / `veed`), neural speech denoising and heavy aspect reframing through `MediaOpsPort` (`--provider modal_cloud` on deployed Modal app `vedit-distributed-renderer`), background matting through cloud `veed`, and distributed HyperFrames rendering + EBU R128 mastering through `vedit cloud render`.
- Redeploy Modal workers with `packages/director-py/.venv/bin/modal deploy packages/cloud-modal/src/vedit_cloud/app.py` whenever container dependencies or worker functions change.

## 5. MapLibre A-Roll Bake (Cartography Tooling)
- Basemap / shot A-roll baking uses MapLibre + Puppeteer + offline tiles via [`tools/geo-assets/README.md`](../../tools/geo-assets/README.md) (`bake_vertical_basemap.mjs` + `fast_capture.mjs` + `serve_tiles.mjs`). Modal distributed renderers composite HyperFrames overlays onto finished A-roll and master audio.
- **Required knobs for continuous or multi-shot MapLibre bakes:**
  - Intermediate frames: **JPEG** (quality ≈ 92) piped via `image2pipe` MJPEG, not full-resolution PNG sequences
  - Tile idle: poll ≈ **20 ms**, timeout ≈ **1500 ms**
  - Chromium GL on **Darwin**: `--use-gl=angle --use-angle=metal` without forced SwiftShader; reserve SwiftShader for Linux/CI/cloud CPU workers only
  - Resume/skip existing valid frames unless `REBAKE=1`
  - Pre-warm tiles at each camera keyframe before the full frame loop when using multi-beat `KEYFRAMES_JSON`
- All shippable masters must follow the deterministic production spine: verified `EditPlan` -> `vedit compile --lint` -> `vedit cloud render` (or `vedit master`) -> `vedit audit`.

## 6. Engine vs. External Project Boundary
- Never create active editing projects, episode voiceovers, or render outputs inside the engine repository.
- Initialize and execute all active editing projects outside the repository under `VEDIT_PROJECTS_ROOT/<brand_id>/<project_id>/` using `vedit project init`, storing strictly project-relative paths in `project.json` and `plan/edit_plan.json`.
- AI directing clients run project initialization and every downstream pipeline stage on the user's behalf; see the Autonomous Production Protocol in [`AGENTS.md`](../../AGENTS.md).

## 7. Brand Style Policy Semantics
- Runtime `BrandStylePolicy` (`profiles/brands/<brand_id>/brand_style_policy.json`) carries section-conditioned pacing priors, visual/audio soft tokens, hard guardrails, and calibration/provenance. Planner and verifier consume those fields only—never treat the policy as a rigid shot-length template.
- Advisory `grammar_triggers` / `exemplar_bank` live only in `editorial_playbook.json` (`contracts/editorial_playbook.schema.json`). Do not put them on runtime policy. Do not imply the engine executes trigger DSLs.
- Optional `templates/catalog.json` binds approved compositions via typed variables (`template_id` on EditPlan overlays). Unknown variables fail verification.
- Brand craft documents (`CRAFT.md`) stay under `profiles/brands/<brand_id>/`. Engine-wide composition rules stay in `DESIGN.md`.
- Validate with `vedit contracts validate` (platforms + brand trees) or `vedit brand validate`.
