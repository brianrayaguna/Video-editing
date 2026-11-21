"""End-to-end and contract tests for spatial, grid, hierarchy, and typography forensics."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vedit.analyzers.spatial_forensics import (
    SpatialForensicsOptions,
    analyze_video_structure,
    resolve_spatial_python,
)


def _spatial_env_available() -> bool:
    try:
        resolve_spatial_python()
        return shutil.which("ffmpeg") is not None
    except FileNotFoundError:
        return False


def _render_synthetic_video(out_mp4: Path) -> None:
    """Create a 2-second 720x1280 vertical test video with known typography, margins, and card."""
    # Dark navy ground (#101828), bright white centered headline at y=280,
    # centered lower caption at y=860, and a crisp vertical divider at x=360.
    vf = (
        "drawbox=x=72:y=220:w=576:h=160:color=0x1E293B:t=fill,"
        "drawtext=text='STRAIT OF GIBRALTAR':fontcolor=white:fontsize=46:"
        "x=(w-text_w)/2:y=275,"
        "drawtext=text='FOURTEEN KILOMETERS WIDE':fontcolor=0xFACC15:fontsize=30:"
        "x=(w-text_w)/2:y=860"
    )
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x101828:s=720x1280:d=2:r=24",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_mp4),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"ffmpeg drawtext unavailable for synthetic video test: {proc.stderr}")


@pytest.mark.skipif(not _spatial_env_available(), reason="spatial-forensics venv or ffmpeg missing")
def test_spatial_forensics_synthetic_ground_truth(tmp_path: Path) -> None:
    video_path = tmp_path / "synthetic_vertical.mp4"
    out_dir = tmp_path / "spatial_out"
    _render_synthetic_video(video_path)

    result = analyze_video_structure(
        video_path,
        out_dir,
        SpatialForensicsOptions(
            platform_target_id="shorts_9x16_1080p",
            max_frames=3,
            max_motion_windows=1,
            use_subject_mask=False,
            use_face_detection=False,
        ),
    )

    assert result.width == 720
    assert result.height == 1280
    assert result.aspect_ratio == "9:16"
    assert len(result.frames) >= 1
    assert (out_dir / "spatial_forensics.json").is_file()
    assert (out_dir / "STRUCTURE.md").is_file()

    # Check Set-of-Mark blueprint images were rendered.
    for fr in result.frames:
        assert fr.blueprint_path is not None
        assert Path(fr.blueprint_path).is_file()

    # Typography, local WCAG contrast, and grid alignment assertions.
    assert result.summary.typography.text_block_count >= 2
    assert result.summary.typography.median_wcag_contrast is not None
    assert result.summary.typography.median_wcag_contrast >= 4.5
    assert result.summary.grid.dominant_alignment in ("center", "left", "mixed")
    assert result.summary.grid.margin_left_pct >= 0.04
    assert result.summary.grid.margin_right_pct >= 0.04
    assert result.summary.motion.dominant_camera_regime == "static"
