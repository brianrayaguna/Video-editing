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


@pytest.mark.skipif(not _spatial_env_available(), reason="spatial-forensics venv missing")
def test_spatial_forensics_linear_contrast_and_motion_track_exclusivity() -> None:
    """Verify linearized sRGB foreground selection, 1D centroid math, and track exclusivity."""
    import json

    py = resolve_spatial_python()
    probe_script = r"""
import importlib.util, json, sys
from pathlib import Path
import numpy as np

sf_path = Path("tools/spatial-forensics/analyze_video.py")
spec = importlib.util.spec_from_file_location("sf_mod", sf_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# 1. Mid-gray bg (#808080, linear luma ~0.216) with dark ink (#080808) and mild highlight (#969696).
# Gamma crop_luma vs linear bg_luma wrongly selects #969696; linearized selects #080808.
img = np.full((120, 200, 3), 128, dtype=np.uint8)
img[40:80, 40:160] = 128
img[45:75, 50:90] = 8     # dark ink (20%+ of crop)
img[45:75, 100:140] = 150 # subtle bright halo
contrast, fg_hex, bg_hex, _ = mod._sample_text_contrast_and_style(img, (40, 40, 160, 80))

# 2. Saliency centroid on impulse at (x=75, y=25) in 100x100 map.
sal = np.zeros((100, 100), dtype=np.float32)
sal[25, 75] = 1.0
cx, cy = mod._saliency_centroid(sal)

# 3. Motion window tracker must never assign two nearby detections in the same frame to one track.
class _DummyCap:
    def __init__(self, frames):
        self.frames = frames
        self.idx = 0
    def set(self, *_args):
        self.idx = 0
    def read(self):
        if self.idx >= len(self.frames):
            return False, None
        f = self.frames[self.idx]
        self.idx += 1
        return True, f

def _dummy_ocr(_frame):
    # Two nearby labels 30px apart in every frame
    p1 = [[100, 100], [160, 100], [160, 120], [100, 120]]
    p2 = [[100, 130], [160, 130], [160, 150], [100, 150]]
    return ([(p1, "ALPHA", 0.95), (p2, "BETA", 0.95)], None)

dummy_frames = [np.zeros((200, 200, 3), dtype=np.uint8) for _ in range(8)]
mw = mod._analyze_motion_window(_DummyCap(dummy_frames), 10.0, 0.0, 0.8, 0, 0, _dummy_ocr)

print(json.dumps({
    "contrast": contrast,
    "fg_hex": fg_hex,
    "bg_hex": bg_hex,
    "cx": cx,
    "cy": cy,
    "entrance_count": len(mw["entrances"]),
    "entrance_texts": sorted(e["text"] for e in mw["entrances"]),
}))
"""
    proc = subprocess.run(
        [str(py), "-c", probe_script],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["fg_hex"] == "#080808", f"Expected dark ink #080808, got {data}"
    assert data["contrast"] >= 4.5, f"Expected WCAG contrast >= 4.5, got {data}"
    assert data["cx"] == pytest.approx(0.75, abs=0.01)
    assert data["cy"] == pytest.approx(0.25, abs=0.01)
    assert data["entrance_count"] == 2, f"Expected 2 separate tracks, got {data}"
    assert data["entrance_texts"] == ["ALPHA", "BETA"]
