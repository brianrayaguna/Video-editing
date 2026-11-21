#!/usr/bin/env bash
# Install the isolated spatial, layout, hierarchy, typography, and motion forensics
# Python toolchain under tools/spatial-forensics/.venv.
# Usage:
#   bash tools/spatial-forensics/setup.sh            # install core stack + u2netp ONNX (~4.7 MB)
#   bash tools/spatial-forensics/setup.sh --no-model # skip pre-downloading u2netp ONNX weights
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$TOOL_DIR/.venv"
MODELS_DIR="$TOOL_DIR/models"
PREFETCH_MODEL=1

for arg in "$@"; do
  case "$arg" in
    --no-model) PREFETCH_MODEL=0 ;;
    -h|--help)
      sed -n '2,6p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "Error: ffmpeg and ffprobe are required on PATH." >&2
  exit 1
fi

py_supported() {
  "$1" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)' 2>/dev/null
}

PY="${PYTHON_BIN:-}"
if [ -z "$PY" ]; then
  for cand in /opt/homebrew/bin/python3.12 python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1 && py_supported "$cand"; then
      PY="$(command -v "$cand")"
      break
    fi
  done
fi

if [ -z "$PY" ] || ! py_supported "$PY"; then
  echo "Error: Python 3.10-3.12 is required for mediapipe + onnxruntime compatibility." >&2
  echo "Set PYTHON_BIN=/path/to/python3.12 and re-run." >&2
  exit 1
fi
echo "Using Python interpreter: $PY ($("$PY" --version 2>&1))"

PACKAGES=(
  "numpy>=1.26,<2.3"
  "pillow>=10.0"
  "opencv-python-headless>=4.9,<5"
  "onnxruntime>=1.18"
  "rapidocr-onnxruntime>=1.4"
  "shapely>=2.0"
  "pyclipper>=1.3"
  "scipy>=1.13"
  "scikit-learn>=1.5"
  "scikit-image>=0.24"
  "rembg>=2.0.59"
  "mediapipe>=0.10.14"
  "supervision>=0.25"
  "fonttools>=4.53"
)

if command -v uv >/dev/null 2>&1; then
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating isolated virtualenv with uv at $VENV_DIR..."
    uv venv --python "$PY" "$VENV_DIR"
  fi
  echo "Installing spatial forensics packages via uv..."
  uv pip install --python "$VENV_DIR/bin/python" "${PACKAGES[@]}"
  # Ensure headless OpenCV only (some dependencies pull GUI opencv-python).
  if uv pip show --python "$VENV_DIR/bin/python" opencv-python >/dev/null 2>&1; then
    echo "Deduplicating opencv-python -> opencv-python-headless..."
    uv pip uninstall --python "$VENV_DIR/bin/python" opencv-python
    uv pip install --python "$VENV_DIR/bin/python" --reinstall-package opencv-python-headless "opencv-python-headless>=4.9,<5"
  fi
else
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating isolated virtualenv at $VENV_DIR..."
    "$PY" -m venv "$VENV_DIR"
  fi
  "$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV_DIR/bin/python" -m pip install "${PACKAGES[@]}"
  if "$VENV_DIR/bin/python" -m pip show opencv-python >/dev/null 2>&1; then
    "$VENV_DIR/bin/python" -m pip uninstall -y opencv-python >/dev/null
    "$VENV_DIR/bin/python" -m pip install --force-reinstall --no-deps "opencv-python-headless>=4.9,<5" >/dev/null
  fi
fi

mkdir -p "$MODELS_DIR"
if [ "$PREFETCH_MODEL" -eq 1 ]; then
  echo "Pre-fetching lightweight u2netp ONNX subject-segmentation model into $MODELS_DIR..."
  U2NET_HOME="$MODELS_DIR" "$VENV_DIR/bin/python" -c "from rembg import new_session; new_session('u2netp'); print('u2netp ready')"
fi

"$VENV_DIR/bin/python" -c "import cv2, onnxruntime, rapidocr_onnxruntime, shapely, scipy, sklearn, skimage, rembg, mediapipe, supervision, fontTools; print('Verified spatial-forensics environment: ALL OK')"
