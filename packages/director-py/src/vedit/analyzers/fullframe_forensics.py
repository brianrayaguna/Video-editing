"""Subprocess wrapper for the native-FPS full-frame video forensics worker."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vedit.analyzers.spatial_forensics import resolve_spatial_python
from vedit.contracts import find_repo_root, validate_against_contract


@dataclass(slots=True)
class FullFrameForensicsOptions:
    """Configuration options for `vedit breakdown fullframe`."""

    platform_target_id: str | None = None
    ocr_fps: float = 3.0
    sheet_fps: float = 1.0
    max_event_strips: int = 16
    python_bin: Path | None = None


def analyze_video_fullframe(
    media_path: Path,
    output_dir: Path,
    options: FullFrameForensicsOptions | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run native-FPS full-frame forensics and validate output against contract schema."""
    opts = options or FullFrameForensicsOptions()
    root = repo_root or find_repo_root()
    media = media_path.expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(f"Video file not found: {media}")

    out_dir = output_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    py_bin = resolve_spatial_python(opts.python_bin, repo_root=root)
    worker = root / "tools" / "spatial-forensics" / "analyze_fullframe.py"
    if not worker.is_file():
        raise FileNotFoundError(f"Full-frame forensics worker not found: {worker}")

    cmd = [
        str(py_bin),
        str(worker),
        "--video",
        str(media),
        "--out-dir",
        str(out_dir),
        "--ocr-fps",
        str(opts.ocr_fps),
        "--sheet-fps",
        str(opts.sheet_fps),
        "--max-event-strips",
        str(opts.max_event_strips),
    ]
    if opts.platform_target_id:
        cmd.extend(["--platform-target-id", opts.platform_target_id])

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Full-frame forensics worker failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )

    json_path = out_dir / "fullframe_forensics.json"
    if not json_path.is_file():
        raise RuntimeError(f"Full-frame forensics worker did not write {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    errors = validate_against_contract(payload, "fullframe_forensics.schema.json", repo_root=root)
    if errors:
        raise ValueError(f"fullframe_forensics.json failed contract validation: {errors}")

    return payload
