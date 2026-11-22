"""Modal CPU worker logic for cloud speech denoising (DeepFilterNet) and deterministic reframing."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

import modal
from vedit.contracts import find_repo_root

MEDIA_OPS_CPU_COUNT = 4.0
MEDIA_OPS_MEMORY_MB = 8192
DEEPFILTER_VERSION = "0.5.6"
DEEPFILTER_BIN_URL = (
    "https://github.com/Rikorose/DeepFilterNet/releases/download/"
    f"v{DEEPFILTER_VERSION}/deep-filter-{DEEPFILTER_VERSION}-x86_64-unknown-linux-musl"
)

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


def build_media_ops_image(repo_root: Path | None = None) -> modal.Image:
    """Build a lean CPU Linux image with FFmpeg, static Rust deep-filter, and vedit runtime."""
    root = repo_root or find_repo_root()
    ignore_build_dirs = [
        "target",
        "node_modules",
        "dist",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "*.egg-info",
    ]
    return (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("ffmpeg", "curl", "ca-certificates")
        .run_commands(
            f"curl -fsSL '{DEEPFILTER_BIN_URL}' -o /usr/local/bin/deep-filter "
            "&& chmod 0755 /usr/local/bin/deep-filter "
            "&& /usr/local/bin/deep-filter --version"
        )
        .pip_install(
            "hatchling>=1.25.0",
            "pydantic>=2.9.0",
            "jsonschema>=4.23.0",
            "pyyaml>=6.0.2",
            "httpx>=0.27.2",
            "typer>=0.12.5",
        )
        .add_local_dir(root / "contracts", "/opt/vedit/contracts", copy=True)
        .add_local_dir(root / "profiles", "/opt/vedit/profiles", copy=True)
        .add_local_dir(
            root / "config",
            "/opt/vedit/config",
            copy=True,
            ignore=["providers.yaml"],
        )
        .add_local_dir(
            root / "packages" / "director-py",
            "/opt/vedit/packages/director-py",
            copy=True,
            ignore=ignore_build_dirs,
        )
        .add_local_dir(
            root / "packages" / "cloud-modal",
            "/opt/vedit/packages/cloud-modal",
            copy=True,
            ignore=ignore_build_dirs,
        )
        .run_commands(
            "pip install --no-deps --no-build-isolation /opt/vedit/packages/director-py",
            "pip install --no-deps --no-build-isolation /opt/vedit/packages/cloud-modal",
        )
        .env({"VEDIT_REPO_ROOT": "/opt/vedit"})
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_cas_path(cas_mount_path: Path, relpath: str) -> Path:
    """Resolve a CAS-relative path and reject absolute or parent-traversal escapes."""
    raw = Path(relpath)
    if raw.is_absolute():
        raise ValueError(f"CAS path must be relative, got absolute path: {relpath!r}")
    root = cas_mount_path.resolve()
    resolved = (root / raw).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"CAS path escapes mount root ({root}): {relpath!r}")
    return resolved


def run_clean_audio_cloud(
    source_relpath: str,
    *,
    cas_mount_path: Path,
    cas_volume: Any,
    estimate_cost_fn: Any,
    strength: float = 0.85,
) -> dict[str, Any]:
    """Run 48 kHz neural speech enhancement via Rust deep-filter inside a Modal CPU container."""
    if not 0.0 <= strength <= 1.0:
        raise ValueError(f"strength must be within [0.0, 1.0], got {strength}")

    cas_volume.reload()
    src_path = _resolve_cas_path(cas_mount_path, source_relpath.lstrip("/"))
    if not src_path.is_file():
        raise FileNotFoundError(f"Missing staged source audio on Modal CAS: {src_path}")

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vedit_df_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        mono_48k = tmp_root / "input_48k.wav"
        df_out_dir = tmp_root / "df_out"
        df_out_dir.mkdir(parents=True, exist_ok=True)

        extract_proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(src_path),
                "-vn",
                "-af",
                "highpass=f=70",
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(mono_48k),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        if extract_proc.returncode != 0:
            raise RuntimeError(f"FFmpeg speech extraction failed: {extract_proc.stderr}")

        engine_used = "deepfilternet_rust"
        if strength <= 0.0:
            engine_used = "ffmpeg_passthrough"
            enhanced_wav = mono_48k
        else:
            atten_lim_db = round(6.0 + strength * 24.0, 1)
            df_proc = subprocess.run(
                [
                    "/usr/local/bin/deep-filter",
                    "--compensate-delay",
                    "--pf",
                    "--atten-lim-db",
                    str(atten_lim_db),
                    "--output-dir",
                    str(df_out_dir),
                    str(mono_48k),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=600,
            )
            if df_proc.returncode != 0:
                raise RuntimeError(
                    f"deep-filter failed ({df_proc.returncode}): {df_proc.stderr.strip()}"
                )
            candidates = sorted(df_out_dir.glob("*.wav"))
            if not candidates:
                raise RuntimeError("deep-filter completed without emitting an output WAV file.")
            enhanced_wav = candidates[0]

        out_sha = _sha256_file(enhanced_wav)
        out_rel = f"media_ops/clean_audio/{out_sha}.wav"
        out_cas = cas_mount_path / out_rel
        out_cas.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(enhanced_wav, out_cas)

    cas_volume.commit()
    wall_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "output_subpath": out_rel,
        "sha256": out_sha,
        "engine": engine_used,
        "strength": strength,
        "sample_rate_hz": 48000,
        "wall_ms": wall_ms,
        "estimated_usd": estimate_cost_fn(
            wall_ms,
            cpus=MEDIA_OPS_CPU_COUNT,
            memory_mb=MEDIA_OPS_MEMORY_MB,
        ),
    }


def run_reframe_video_cloud(
    source_relpath: str,
    *,
    cas_mount_path: Path,
    cas_volume: Any,
    estimate_cost_fn: Any,
    target_aspect_ratio: Literal["9:16", "1:1", "4:5", "16:9"] = "9:16",
) -> dict[str, Any]:
    """Run deterministic Lanczos + bt709 aspect-ratio reframing inside a Modal CPU container."""
    if target_aspect_ratio not in ASPECT_DIMENSIONS:
        raise ValueError(f"Unsupported target_aspect_ratio: {target_aspect_ratio!r}")

    cas_volume.reload()
    src_path = _resolve_cas_path(cas_mount_path, source_relpath.lstrip("/"))
    if not src_path.is_file():
        raise FileNotFoundError(f"Missing staged source video on Modal CAS: {src_path}")

    target_w, target_h = ASPECT_DIMENSIONS[target_aspect_ratio]
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vedit_reframe_") as tmp_dir:
        out_local = Path(tmp_dir) / "reframed.mp4"
        vf = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={target_w}:{target_h},setsar=1,format=yuv420p"
        )
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(src_path),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-preset",
                "fast",
                "-colorspace",
                "bt709",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-color_range",
                "tv",
                "-movflags",
                "+faststart",
                "-c:a",
                "copy",
                str(out_local),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Cloud FFmpeg reframe failed: {proc.stderr}")

        out_sha = _sha256_file(out_local)
        out_rel = f"media_ops/reframe/{out_sha}_{target_w}x{target_h}.mp4"
        out_cas = cas_mount_path / out_rel
        out_cas.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out_local, out_cas)

    cas_volume.commit()
    wall_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "output_subpath": out_rel,
        "sha256": out_sha,
        "width": target_w,
        "height": target_h,
        "aspect_ratio": target_aspect_ratio,
        "wall_ms": wall_ms,
        "estimated_usd": estimate_cost_fn(
            wall_ms,
            cpus=MEDIA_OPS_CPU_COUNT,
            memory_mb=MEDIA_OPS_MEMORY_MB,
        ),
    }
