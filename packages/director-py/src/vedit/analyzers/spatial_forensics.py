"""Subprocess wrapper for the isolated spatial, structural, and hierarchy forensics worker."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vedit.contracts import find_repo_root, load_platform_targets, validate_against_contract
from vedit.models import SpatialForensicsResult


@dataclass(slots=True)
class SpatialForensicsOptions:
    """Configuration options for `vedit breakdown structure`."""

    shots_json: Path | None = None
    platform_target_id: str | None = None
    max_frames: int = 12
    max_motion_windows: int = 4
    use_subject_mask: bool = True
    use_face_detection: bool = True
    python_bin: Path | None = None


def resolve_spatial_python(
    explicit: Path | None = None, repo_root: Path | None = None
) -> Path:
    """Locate the isolated spatial-forensics Python interpreter."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(os.path.abspath(str(explicit.expanduser()))))
    env_py = os.environ.get("VEDIT_SPATIAL_FORENSICS_PYTHON", "").strip()
    if env_py:
        candidates.append(Path(os.path.abspath(str(Path(env_py).expanduser()))))
    root = repo_root or find_repo_root()
    candidates.append(root / "tools" / "spatial-forensics" / ".venv" / "bin" / "python")
    for cand in candidates:
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        "Spatial forensics virtualenv not found. "
        "Run `bash tools/spatial-forensics/setup.sh` to install it."
    )


def analyze_video_structure(
    media_path: Path,
    output_dir: Path,
    options: SpatialForensicsOptions | None = None,
    *,
    repo_root: Path | None = None,
) -> SpatialForensicsResult:
    """Run isolated spatial/grid/hierarchy/typography/motion forensics and validate contract."""
    opts = options or SpatialForensicsOptions()
    root = repo_root or find_repo_root()
    media = media_path.expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(f"Video file not found: {media}")

    out_dir = output_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    py_bin = resolve_spatial_python(opts.python_bin, repo_root=root)
    worker = root / "tools" / "spatial-forensics" / "analyze_video.py"
    if not worker.is_file():
        raise FileNotFoundError(f"Spatial forensics worker not found: {worker}")

    cmd = [
        str(py_bin),
        str(worker),
        "--video",
        str(media),
        "--out-dir",
        str(out_dir),
        "--max-frames",
        str(opts.max_frames),
        "--max-motion-windows",
        str(opts.max_motion_windows),
    ]
    if opts.shots_json is not None:
        cmd.extend(["--shots-json", str(opts.shots_json.expanduser().resolve())])
    if opts.platform_target_id:
        platforms = load_platform_targets(repo_root=root)
        target = platforms.get(opts.platform_target_id)
        if target is None:
            raise ValueError(f"Unknown platform_target_id: {opts.platform_target_id}")
        cmd.extend(["--platform-target-id", opts.platform_target_id])
        safe_zone = target.get("safe_zone")
        if safe_zone:
            cmd.extend(["--safe-zone-json", json.dumps(safe_zone)])
    if not opts.use_subject_mask:
        cmd.append("--no-subject-mask")
    if not opts.use_face_detection:
        cmd.append("--no-face-detection")

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Spatial forensics worker failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )

    json_path = out_dir / "spatial_forensics.json"
    if not json_path.is_file():
        raise RuntimeError(f"Spatial forensics worker did not write {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    errors = validate_against_contract(payload, "spatial_forensics.schema.json", repo_root=root)
    if errors:
        raise ValueError(f"spatial_forensics.json failed contract validation: {errors}")

    return SpatialForensicsResult.model_validate(payload)
