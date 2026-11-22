#!/usr/bin/env bash
# Install JuneYaooo/rea-video into an isolated Python 3.10-3.14 virtualenv under tools/rea-video/.
# Usage:
#   bash tools/rea-video/setup.sh              # default: [ocr] extra (recommended)
#   bash tools/rea-video/setup.sh --no-ocr     # minimal base install without RapidOCR
#   bash tools/rea-video/setup.sh --with-asr   # include local sherpa-onnx ASR (~195 MB)
#   bash tools/rea-video/setup.sh --update     # pull latest upstream main instead of pinned ref
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM_DIR="$TOOL_DIR/upstream"
VENV_DIR="$TOOL_DIR/.venv"
REPO_URL="https://github.com/JuneYaooo/rea-video.git"
PINNED_REF="${REA_VIDEO_REF:-ac470773188574833b839be17abee6162201ddf9}"

WITH_OCR=1
WITH_ASR=0
DO_UPDATE=0

for arg in "$@"; do
  case "$arg" in
    --no-ocr) WITH_OCR=0 ;;
    --with-asr) WITH_ASR=1 ;;
    --update) DO_UPDATE=1 ;;
    -h|--help)
      sed -n '2,7p' "$0"
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
  "$1" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)' 2>/dev/null
}

PY="${PYTHON_BIN:-}"
if [ -z "$PY" ]; then
  for cand in /opt/homebrew/bin/python3.12 python3.12 /opt/homebrew/bin/python3.13 python3.13 /opt/homebrew/bin/python3.14 python3.14 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1 && py_supported "$cand"; then
      PY="$(command -v "$cand")"
      break
    fi
  done
fi

if [ -z "$PY" ] || ! py_supported "$PY"; then
  echo "Error: Python 3.10-3.14 is required (onnxruntime does not support Python 3.15+)." >&2
  echo "Set PYTHON_BIN=/path/to/python3.12 and re-run." >&2
  exit 1
fi
echo "Using Python interpreter: $PY ($("$PY" --version 2>&1))"

if [ ! -d "$UPSTREAM_DIR/.git" ]; then
  echo "Cloning $REPO_URL into $UPSTREAM_DIR..."
  git clone --depth 1 "$REPO_URL" "$UPSTREAM_DIR"
  if [ "$PINNED_REF" != "main" ]; then
    git -C "$UPSTREAM_DIR" fetch --depth 1 origin "$PINNED_REF"
    git -C "$UPSTREAM_DIR" checkout --detach "$PINNED_REF"
  fi
elif [ "$DO_UPDATE" -eq 1 ]; then
  echo "Updating $UPSTREAM_DIR..."
  git -C "$UPSTREAM_DIR" fetch --depth 1 origin "$PINNED_REF"
  git -C "$UPSTREAM_DIR" checkout --detach FETCH_HEAD
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating isolated virtualenv at $VENV_DIR..."
  "$PY" -m venv "$VENV_DIR"
fi

EXTRAS=()
[ "$WITH_OCR" -eq 1 ] && EXTRAS+=("ocr")
[ "$WITH_ASR" -eq 1 ] && EXTRAS+=("asr")

INSTALL_TARGET="$UPSTREAM_DIR"
if [ "${#EXTRAS[@]}" -gt 0 ]; then
  IFS=,
  INSTALL_TARGET="${UPSTREAM_DIR}[${EXTRAS[*]}]"
  unset IFS
fi

echo "Installing $INSTALL_TARGET..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install -e "$INSTALL_TARGET"

# On Python <= 3.12, rapidocr-onnxruntime pulls GUI opencv-python which collides with
# opencv-python-headless inside cv2/. Deduplicate to keep headless OpenCV only.
if "$VENV_DIR/bin/python" -m pip show opencv-python >/dev/null 2>&1; then
  echo "Deduplicating opencv-python -> opencv-python-headless..."
  "$VENV_DIR/bin/python" -m pip uninstall -y opencv-python >/dev/null
  "$VENV_DIR/bin/python" -m pip install --force-reinstall --no-deps "opencv-python-headless>=4.8,<5" >/dev/null
fi

COMMIT_SHA="$(git -C "$UPSTREAM_DIR" rev-parse HEAD)"
echo "Installed rea-video commit: $COMMIT_SHA"
"$VENV_DIR/bin/rea-video" --help >/dev/null
echo "Verified: $VENV_DIR/bin/rea-video"
