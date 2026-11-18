"""Python bridge invoking the native Rust `vedit-probe` binary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root, validate_against_contract
from vedit.models import MediaProbeResult


@dataclass(slots=True)
class ProbeOptions:
    scene_threshold: float = 12.0
    min_scene_s: float = 0.4
    silence_db: float = -35.0
    silence_min_s: float = 0.30
    analysis_fps: float = 1.0
    analysis_width: int = 320
    true_peak: bool = False
    extract_keyframes_dir: Path | None = None


def resolve_probe_binary(repo_root: Path | None = None) -> Path:
    """Locate the compiled `vedit-probe` executable (env, release, debug, or PATH)."""
    env_bin = os.environ.get("VEDIT_PROBE_BIN")
    if env_bin:
        candidate = Path(env_bin)
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"VEDIT_PROBE_BIN points to missing binary: {candidate}")

    root = repo_root or find_repo_root()
    for profile in ("release", "debug"):
        candidate = root / "packages" / "media-probe-rs" / "target" / profile / "vedit-probe"
        if candidate.is_file():
            return candidate

    on_path = shutil.which("vedit-probe")
    if on_path:
        return Path(on_path)

    raise FileNotFoundError(
        "Compiled `vedit-probe` binary not found. "
        "Run `cargo build --release` in `packages/media-probe-rs`."
    )


def hash_media(media_path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Compute SHA-256 content-addressed hash and byte size using `vedit-probe`."""
    binary = resolve_probe_binary(repo_root=repo_root)
    proc = subprocess.run(
        [str(binary), "hash", str(media_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"vedit-probe hash failed ({proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def probe_media(
    media_path: Path,
    options: ProbeOptions | None = None,
    *,
    repo_root: Path | None = None,
    validate_contract: bool = True,
) -> MediaProbeResult:
    """Run single-pass deterministic audio/video/shot probe via `vedit-probe`."""
    opts = options or ProbeOptions()
    root = repo_root or find_repo_root()
    binary = resolve_probe_binary(repo_root=root)

    cmd = [
        str(binary),
        "analyze",
        str(media_path),
        f"--scene-threshold={opts.scene_threshold}",
        f"--min-scene-s={opts.min_scene_s}",
        f"--silence-db={opts.silence_db}",
        f"--silence-min-s={opts.silence_min_s}",
        f"--analysis-fps={opts.analysis_fps}",
        f"--analysis-width={opts.analysis_width}",
    ]
    if opts.true_peak:
        cmd.append("--true-peak")
    if opts.extract_keyframes_dir is not None:
        cmd.extend(["--extract-keyframes", str(opts.extract_keyframes_dir)])

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"vedit-probe analyze failed ({proc.returncode}): {proc.stderr.strip()}")

    payload = json.loads(proc.stdout)
    if validate_contract:
        errors = validate_against_contract(payload, "media_probe.schema.json", repo_root=root)
        if errors:
            raise ValueError(f"Probe payload failed media_probe.schema.json: {errors}")

    return MediaProbeResult.model_validate(payload)
