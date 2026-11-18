# System Architecture Rules

These rules govern all media pipelines, composition compilers, and provider integrations within this repository.

## 1. Capability-First Abstraction (Ports & Adapters)
- Core modules (`analyzers`, `director`, `mastering`, `cli`) and documentation must depend exclusively on capability interfaces in `vedit.ports` (`TranscriptionPort`, `DecisionPort`, `MediaOpsPort`, `AudioCatalogPort`).
- Concrete vendor integrations live under `vedit.providers` and are resolved solely through `ProviderRegistry` and YAML/environment configuration. Never hardcode vendor assumptions in core logic or agent skills.

## 2. Strict Prohibition on Generative Video
- This system processes, indexes, directs, and assembles real source media alongside procedural HTML/GSAP motion graphics rendered with HyperFrames.
- Do not add, expose, or invoke generative AI video, synthetic avatar, or lip-sync synthesis endpoints in any port, provider, or workflow.

## 3. Mandatory Pipeline Ordering Invariants
1. **Audio Processing DAG**: Run optional speech denoising (`MediaOpsPort.clean_audio`) exclusively on isolated speech stems **before** speech-to-text transcription (`TranscriptionPort`), and never after mixing music or sound effects. Apply spectral voiceover carving to background music against the voiceover group, mix, and master via two-pass EBU R128 toward `-14.0 LUFS` integrated and `<= -1.0 dBTP` true peak (`48 kHz` stereo AAC-LC).
2. **Target-Canvas Spatial Grounding**: Run `DecisionPort` bounding-box detection (`box`/`boxes`) on target-aspect-ratio frames **after** reframing or cropping (for example, on `9:16` output frames), never on uncropped source geometry.
3. **Decision Batching**: Extract shot boundaries first via `vedit-probe` / FFmpeg. Request `box`/`boxes` once per shot that carries overlays, and batch classification/scoring queries up to provider request limits (`<= 8` images, `<= 128` questions).

## 4. HyperFrames & Cloud Worker Performance
- Never apply animated CSS `backdrop-filter` or `filter: blur()` in HyperFrames compositions; pre-render static blurred assets instead.
- CPU cloud rendering workers must pass `--no-browser-gpu` with software WebGL (`swiftshader`), partition long timelines into short chunks (`150–240` frames) to bound Chromium memory growth, and recycle browser processes per chunk.
- Compile native Linux `x86_64` binaries (`vedit-probe`) directly inside the cloud container image build; never copy macOS ARM64 binaries into Linux containers.
- Keep `@hyperframes/core` and `@hyperframes/producer` pinned explicitly across `packages/hf-compiler-ts` and cloud container images.

## 5. Brand Style Policy Semantics
- Treat `BrandStylePolicy` as a flexible editorial policy combining section-conditioned pacing priors (`hook`, `setup`, `body`, `escalation`, `climax`, `outro`), conditional trigger grammar, hard negative guardrails, and a multimodal exemplar bank—never as a rigid shot-length template.
