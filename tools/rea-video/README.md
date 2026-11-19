# `tools/rea-video` — Isolated Forensic Breakdown Toolchain

This directory manages an isolated local installation of [`JuneYaooo/rea-video`](https://github.com/JuneYaooo/rea-video) (Apache-2.0) used by `ReaVideoBreakdownProvider` (`VideoBreakdownPort`) to extract forensic shot, transition, audio, color-grade, and OCR caption telemetry for brand profiling.

## Why Isolated?

1. **Lean Core & Cloud Images**: Keeps `packages/director-py/.venv` and `packages/cloud-modal` container images free of `opencv-python-headless`, `onnxruntime`, and `rapidocr-onnxruntime`.
2. **Python Compatibility**: `onnxruntime` requires Python `3.10–3.14` (incompatible with Python `3.15+`). `setup.sh` selects a compatible interpreter (preferring Python `3.12`) and deduplicates `opencv-python` vs `opencv-python-headless`.
3. **Clean License & Git Separation**: Upstream checkout (`upstream/`) and virtual environment (`.venv/`) are gitignored; `vedit` interacts with the CLI exclusively over a subprocess boundary.

## Strict Forensic-Only Boundary

Per `.agents/rules/editing-system.md`, `vedit` exposes **only** the forensic analysis subcommands (`survey`, `decompose`, `review`, `apply-review`, `summary`, `videomd`, `tiles`). Generative video remake workflows (`plan`, `remake`, `remake-run`, `drive`, `capsule-cinema`) are intentionally excluded and blocked by `ReaVideoBreakdownProvider`.

## Setup

```bash
# Default installation: forensic core + local RapidOCR ([ocr], ~15 MB models)
bash tools/rea-video/setup.sh

# Minimal installation without local OCR
bash tools/rea-video/setup.sh --no-ocr

# Optional: also install local sherpa-onnx ASR (~195 MB models)
bash tools/rea-video/setup.sh --with-asr

# Update existing checkout
bash tools/rea-video/setup.sh --update
```

## Binary Discovery Order

`ReaVideoBreakdownProvider` resolves the executable in this order:
1. `options.binary` in `config/providers.yaml`
2. `VEDIT_REA_VIDEO_BIN` environment variable
3. `tools/rea-video/.venv/bin/rea-video`
4. `rea-video` on `PATH`

## Local Model Caches

On first execution with `--stems` enabled, `rea-video` downloads UVR MDX-Net (~67 MB) and BandIt v2 (~149 MB) ONNX weights to its local cache directory for vocal/music stem separation. RapidOCR models (~15 MB) download on first OCR pass.
