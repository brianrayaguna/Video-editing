# `tools/spatial-forensics` — Isolated Spatial, Structural & Hierarchy Forensics Toolchain

This directory manages an isolated local Python computer-vision environment used by `vedit breakdown structure` to extract deterministic frame-level spatial geometry, latent grid alignment, visual hierarchy, micro-typography metrics, local WCAG contrast, subject/eye-line framing, motion/easing curves, and Set-of-Mark diagnostic blueprints.

## Architectural Boundary

1. **Lean Core & Cloud Workers**: Keeps `packages/director-py/.venv` and `packages/cloud-modal` free of heavy CV/ML dependencies (`opencv-python-headless`, `onnxruntime`, `scipy`, `scikit-learn`, `scikit-image`, `rembg`, `mediapipe`, `supervision`).
2. **Subprocess JSON Contract**: `vedit` invokes `analyze_video.py` over a subprocess boundary and validates emitted JSON against `contracts/spatial_forensics.schema.json`.
3. **Git Separation**: Virtual environments (`.venv/`) and downloaded ONNX weights (`models/`) are gitignored.

## Setup

```bash
# Install isolated toolchain and prefetch u2netp (~4.7 MB) ONNX weights
bash tools/spatial-forensics/setup.sh

# Skip ONNX model prefetch (spectral-residual saliency only)
bash tools/spatial-forensics/setup.sh --no-model
```

## Outputs

Running `analyze_video.py` produces:
- `spatial_forensics.json` — contract-validated per-frame and video-level spatial telemetry.
- `STRUCTURE.md` — concise layered Markdown summary for multimodal review without loading raw JSON.
- `spatial/frame_XXX_blueprint.jpg` — Set-of-Mark annotated diagnostic frames with numbered element boxes (`[T1]`, `[G1]`, `[S1]`), detected grid/margin lines, platform safe-zone bands, saliency focal crosshairs, and percentage rulers.
