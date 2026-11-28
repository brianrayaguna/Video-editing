# System Architecture

## 1. Design Principles

1. **Capability-First Ports & Adapters**: Core modules (`analyzers`, `director`, `mastering`, `cli`) depend solely on abstract protocols in `vedit.ports`. External services are isolated in `vedit.providers` and selected via configuration (`config/providers.yaml`).
2. **Deterministic Media Assembly Only**: The system processes real camera/screen footage, licensed audio assets, and HTML/GSAP compositions. Generative video synthesis and synthetic avatars are excluded by contract (`MediaOpsPort`).
3. **Canonical `EditPlan` Spine & Single-Source Contracts**: JSON Schemas under `contracts/*.schema.json` are the single source of truth for cross-runtime types (`vedit contracts generate-ts --check` keeps `packages/hf-compiler-ts/src/contracts.ts` synchronized with Python Pydantic models). Every mastering workflow—including geospatial act assembly via `vedit.geo.plan_bridge`—converges onto `EditPlan` → `assemble_hybrid_deliverable()` → `audit_mastered_deliverable()`, carrying exact rational timebases (`vedit.timebase.Timebase` / `RationalTime`) for both integer and broadcast NTSC (`23.976`, `29.97`, `59.94`) frame rates.
4. **Hybrid Rendering Strategy**: Full-frame HTML-to-video rendering via headless Chromium (`BeginFrame`) is reserved for motion graphics, kinetic typography, data cards, and transparent overlays. Base A-roll/B-roll cuts, color tagging, audio mixing, and loudness normalization run natively in FFmpeg with `libx264` or hardware `h264_videotoolbox` encoding (`hybrid` mode), while fully motion-driven pieces can route to distributed HyperFrames chunk rendering (`full_hf` mode).
5. **Extensible Domain Idiom Registry & Brand Neutrality**: Storyboard idiom checks register through `vedit.director.idiom_registry.IdiomRegistry` (separating core cross-brand idioms from domain plugins such as `vedit.geo.idioms`), and core modules remain brand-agnostic—verified continuously against multiple independent brand trees under `profiles/brands/` (`geoverum`, `editorial_explainer`).
6. **Filesystem-First Durable State**: Policies, transcripts, probe metrics, edit plans, and step checkpoints (`JobCheckpoint`) are stored as human- and agent-inspectable JSON files keyed by content SHA-256 and deterministic `idempotency_key` hashes.

---

## 2. Polyglot Runtime Boundaries

```text
Storage / Raw Media
  │
  ├─► Rust (`vedit-probe`) + FFmpeg C
  │     Single-pass decode → stdout RGB24 + stderr filter events
  │     Outputs: SHA-256, shots (scdet), LUFS (ebur128), CIELAB palette, Sobel sharpness
  │
  ├─► Python 3.12 (`vedit-director`)
  │     Capability ports, BrandStylePolicy synthesis, constraint verifier,
  │     Modal serverless orchestration, mastering QC
  │
  ├─► Isolated Local Forensic Toolchain (`tools/rea-video/.venv`)
  │     Optional `VideoBreakdownPort` adapter (`rea_video`): shot/transition
  │     forensics, BPM/beat/SFX extraction, 2-10fps OCR caption packaging,
  │     layered `VIDEO.md` output, and Agent-as-VLM visual review loop
  │
  └─► TypeScript / Node >= 22 (`@vedit/hf-compiler`)
        EditPlan → HyperFrames HTML/GSAP scenes, static checks,
        distributed planV2 / renderChunkV2 / assembleV2 bridge (pinned 0.9.68)
```

---

## 3. Pipeline Execution Invariants

### A. Audio Processing DAG
1. Isolate speech stems from raw footage.
2. Apply optional speech noise reduction (`MediaOpsPort.clean_audio`) **before** transcription, and never after music or SFX mixing.
3. Optionally tighten long pauses (`vedit remove-silence`) and run speech-to-text (`TranscriptionPort`) to produce `NormalizedTranscript` (`word`, `start_s`, `end_s`, `speaker`, `is_filler`).
4. Direct visual cuts, B-roll, and overlay timing against word boundaries.
5. Source music (`vocal_type="NONE"` under speech) and SFX via `AudioCatalogPort`.
6. Apply spectral voiceover carving to music beds, mix stems, and master using two-pass FFmpeg `loudnorm` toward `-14.0 LUFS` integrated and `<= -1.0 dBTP` true peak (`48 kHz` stereo AAC-LC).

### B. Target-Canvas Spatial Grounding & Visual Critique
1. If source and target aspect ratios differ (e.g., `16:9` source → `9:16` vertical), perform reframing/cropping first (`MediaOpsPort.reframe` or crop tracks).
2. Run `DecisionPort` bounding-box grounding (`box`/`boxes`) on target-aspect keyframes **once per shot carrying overlays** (max `1` image per spatial-box request; batch non-spatial rubric scoring, `noul` defect detection, and `spans` extraction up to `8` images / `128` questions within the provider image patch budget).
3. Place captions and cards exclusively within target platform safe zones and clear of detected subject/text boxes.
4. Route satellite tile acquisition for cartographic bakes through `GeoImageryPort` (`google_tiles` with persistent session caching and `scaleFactor2x` high-DPI tiles, falling back automatically to `open_imagery`).

### C. HyperFrames Cloud Worker Constraints
- CPU containers run `chrome-headless-shell` with `--no-browser-gpu` and `--use-gl=swiftshader` to avoid GPU probe stalls and guarantee deterministic rendering across workers.
- Long timelines are partitioned into bounded chunks (`150–240` frames) to cap Chromium memory growth and allow chunk-level parallelism.
- Compositions prohibit animated CSS `backdrop-filter` and `filter: blur()` to prevent software-compositor slowdowns.
- Cloud container builds compile `vedit-probe` natively for Linux `x86_64` during image build rather than copying macOS host binaries.

---

## 4. Brand Style Policy Model

`BrandStylePolicy` (`contracts/brand_style_policy.schema.json`) models editing style as a structured **runtime** policy. Brand files live under `profiles/brands/<brand_id>/`. Advisory directing aids live in a separate `editorial_playbook.json` (`contracts/editorial_playbook.schema.json`).

**Consumed by planner / verifier:**

- **`soft_priors.temporal_curve`**: Section-conditioned ASL targets used while subdividing holds; verifier emits soft warnings when cuts/min drift far outside section ranges.
- **`soft_priors.visual_tokens`**: Palette roles, typography, and `motion_style` (`easing_feel`, `entrance_ms`) emitted onto overlays / HF scenes.
- **`soft_priors.audio_style`**: Music moods and ducking strength for BGM selection/carving.
- **`hard_guardrails`**: Deterministic constraints (`min_shot_duration_s`, `max_uninterrupted_hold_s`, `no_cut_within_keyword_ms`, `never_overlap_subject_boxes`, banned patterns/transitions, CSS blur avoidance, WCAG contrast).
- **`calibration` & `provenance`**: Override counts, rejected patterns, reference hashes, confidence.
- **`templates/catalog.json`** (optional): typed brand templates bound via `OverlayCompositionOp.template_id` + `variables`; verifier rejects unknown slots; compile may copy `composition_path`.

**Executable directing (`directing_idioms.json`, `contracts/directing_idioms.schema.json`):**

- **`idioms`**: parameterised storyboard checks with severity and weight, run by `vedit storyboard check` / `vedit critique packet` against `plan/storyboard.json` (`contracts/storyboard.schema.json`). Storyboard `overrides` retune or disable idioms per film.
- **`auto_director`**, **`device_classes`**, **`camera_regimes`**: defaults for `vedit storyboard auto` (transcript → contract-valid storyboard) and `vedit storyboard journey` (route head, camera, route width, callout placement).
- **`critique_rubric`**: criteria a vision reviewer scores on grid-anchored contact sheets; `vedit critique gate` combines them with the deterministic checks.

Idiom parameters are calibrated from reference videos annotated in the storyboard format (`directing_source: reference`) with `vedit brand calibrate-idioms`, which reports measured distributions and blends existing values toward them.

Directing layers resolve in order: brand idiom defaults → automatic storyboard → director storyboard and overrides. A film with no director input is held to the same idioms as a directed one.

**Advisory only (`editorial_playbook.json`, not on runtime policy):**

- **`grammar_triggers`**: Human/AI directing heuristics. Not executed by planner, verifier, compile, master, or audit.
- **`exemplar_bank`**: Timecoded reference notes. Queried by `vedit brand exemplars <playbook.json>`.

---

## 5. Platform Mastering Targets

Presets in `profiles/platforms/*.json` encode target mastering configurations:
- **YouTube `16:9` 1080p / 4K**: `H.264 High`, `yuv420p`, explicit `bt709` color space/primaries/transfer tags, 2s closed GOP, `+faststart`, `384 kbps` AAC stereo, `-14.0 LUFS` target, `<= -1.0 dBTP`.
- **Vertical `9:16` (Shorts / Reels / TikTok)**: `1080x1920`, `10–12 Mbps` VBR, `192 kbps` AAC stereo, `-14.0 LUFS` target, `<= -1.0 dBTP`, and platform UI safe-zone margins (`top_pct`, `bottom_pct`, `right_pct`).
