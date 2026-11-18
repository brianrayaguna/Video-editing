# System Architecture

## 1. Design Principles

1. **Capability-First Ports & Adapters**: Core modules (`analyzers`, `director`, `mastering`, `cli`) depend solely on abstract protocols in `vedit.ports`. External services are isolated in `vedit.providers` and selected via configuration (`config/providers.yaml`).
2. **Deterministic Media Assembly Only**: The system processes real camera/screen footage, licensed audio assets, and HTML/GSAP compositions. Generative video synthesis and synthetic avatars are excluded by contract (`MediaOpsPort`).
3. **Hybrid Rendering Strategy**: Full-frame HTML-to-video rendering via headless Chromium (`BeginFrame`) is reserved for motion graphics, kinetic typography, data cards, and transparent overlays. Base A-roll/B-roll cuts, color tagging, audio mixing, and loudness normalization run natively in FFmpeg/NVENC (`hybrid` mode), while fully motion-driven pieces can route to distributed HyperFrames chunk rendering (`full_hf` mode).
4. **Filesystem-First Durable State**: Policies, transcripts, probe metrics, edit plans, and step checkpoints (`JobCheckpoint`) are stored as human- and agent-inspectable JSON files keyed by content SHA-256 and deterministic `idempotency_key` hashes.

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
  └─► TypeScript / Node >= 22 (`@vedit/hf-compiler`)
        EditPlan → HyperFrames HTML/GSAP scenes, static checks,
        distributed planV2 / renderChunkV2 / assembleV2 bridge (pinned 0.9.65)
```

---

## 3. Pipeline Execution Invariants

### A. Audio Processing DAG
1. Isolate speech stems from raw footage.
2. Apply optional speech noise reduction (`MediaOpsPort.clean_audio`) **before** transcription, and never after music or SFX mixing.
3. Run speech-to-text (`TranscriptionPort`) to produce `NormalizedTranscript` (`word`, `start_s`, `end_s`, `speaker`, `is_filler`).
4. Direct visual cuts, B-roll, and overlay timing against word boundaries.
5. Source music (`vocal_type="NONE"` under speech) and SFX via `AudioCatalogPort`.
6. Apply spectral voiceover carving to music beds, mix stems, and master using two-pass FFmpeg `loudnorm` toward `-14.0 LUFS` integrated and `<= -1.0 dBTP` true peak (`48 kHz` stereo AAC-LC).

### B. Target-Canvas Spatial Grounding
1. If source and target aspect ratios differ (e.g., `16:9` source → `9:16` vertical), perform reframing/cropping first (`MediaOpsPort.reframe` or crop tracks).
2. Run `DecisionPort` bounding-box grounding (`box`/`boxes`) on target-aspect keyframes **once per shot carrying overlays** (max `1` image per spatial-box request; batch non-spatial questions up to `8` images / `128` questions).
3. Place captions and cards exclusively within target platform safe zones and clear of detected subject/text boxes.

### C. HyperFrames Cloud Worker Constraints
- CPU containers run `chrome-headless-shell` with `--no-browser-gpu` and `--use-gl=swiftshader` to avoid GPU probe stalls and guarantee deterministic rendering across workers.
- Long timelines are partitioned into bounded chunks (`150–240` frames) to cap Chromium memory growth and allow chunk-level parallelism.
- Compositions prohibit animated CSS `backdrop-filter` and `filter: blur()` to prevent software-compositor slowdowns.
- Cloud container builds compile `vedit-probe` natively for Linux `x86_64` during image build rather than copying macOS host binaries.

---

## 4. Brand Style Policy Model

`BrandStylePolicy` (`contracts/brand_style_policy.schema.json`) models editing style as a structured policy rather than rigid templates or global averages:

- **`soft_priors.temporal_curve`**: Section-conditioned pacing quantiles (`asl_p25_s`, `asl_p50_s`, `asl_p75_s`, `cuts_per_min_range`, `energy_target`) across `hook`, `setup`, `body`, `escalation`, `climax`, and `outro`.
- **`soft_priors.visual_tokens` & `audio_style`**: Palette roles, typography rules, easing characteristics, music moods, BPM range, and ducking strength.
- **`grammar_triggers`**: Conditional editorial heuristics mapping speech/audio/visual events (such as quantified claims or topic transitions) to weighted actions.
- **`hard_guardrails`**: Deterministic constraints enforced prior to rendering (`min_shot_duration_s`, `max_uninterrupted_hold_s`, `no_cut_within_keyword_ms`, `never_overlap_subject_boxes`, `banned_transitions`, `avoid_heavy_css_blur`).
- **`exemplar_bank`**: Timecoded atomic segments from reference videos preserving concrete composition patterns alongside measured metrics.
- **`calibration` & `provenance`**: Override counts, rejected patterns, multi-video reference hashes, and confidence score.

---

## 5. Platform Mastering Targets

Presets in `profiles/platforms/*.json` encode target mastering configurations:
- **YouTube `16:9` 1080p / 4K**: `H.264 High`, `yuv420p`, explicit `bt709` color space/primaries/transfer tags, 2s closed GOP, `+faststart`, `384 kbps` AAC stereo, `-14.0 LUFS` target, `<= -1.0 dBTP`.
- **Vertical `9:16` (Shorts / Reels / TikTok)**: `1080x1920`, `10–12 Mbps` VBR, `192 kbps` AAC stereo, `-14.0 LUFS` target, `<= -1.0 dBTP`, and platform UI safe-zone margins (`top_pct`, `bottom_pct`, `right_pct`).
