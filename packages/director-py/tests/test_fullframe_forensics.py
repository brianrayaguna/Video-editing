"""Tests for native-FPS full-frame video forensics contract and worker execution."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vedit.analyzers.fullframe_forensics import (
    FullFrameForensicsOptions,
    analyze_video_fullframe,
)
from vedit.analyzers.spatial_forensics import resolve_spatial_python
from vedit.contracts import find_repo_root, load_schema


def test_fullframe_schema_is_valid_draft_2020_12() -> None:
    schema = load_schema("fullframe_forensics.schema.json")
    assert schema["title"] == "FullFrameForensicsResult"
    assert "surface_segments" in schema["required"]
    assert "camera_segments" in schema["required"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_analyze_video_fullframe_on_synthetic_clip(tmp_path: Path) -> None:
    repo_root = find_repo_root()
    try:
        py_bin = resolve_spatial_python(repo_root=repo_root)
    except FileNotFoundError:
        pytest.skip("spatial-forensics virtualenv not installed")

    video_path = tmp_path / "synthetic_map.mp4"
    # 2-second 360x640 15fps clip: deep marine-teal ocean first second, warm parchment second.
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=#083847:s=360x640:r=15:d=1.0",
        "-f",
        "lavfi",
        "-i",
        "color=c=#B9A386:s=360x640:r=15:d=1.0",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2.0",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "2:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(video_path),
    ]
    subprocess.run(cmd, check=True)

    out_dir = tmp_path / "ff_out"
    res = analyze_video_fullframe(
        video_path,
        out_dir,
        FullFrameForensicsOptions(
            platform_target_id="shorts_9x16_1080p",
            ocr_fps=2.0,
            sheet_fps=1.0,
            max_event_strips=4,
            python_bin=py_bin,
        ),
        repo_root=repo_root,
    )

    assert res["width"] == 360
    assert res["height"] == 640
    assert res["frame_count"] >= 28
    assert Path(res["report_md_path"]).is_file()
    assert Path(res["frame_telemetry_path"]).is_file()
    assert len(res["surface_segments"]) >= 2
    assert len(res["cuts"]) >= 1
    assert len(res["sheets"]["timeline_sheets"]) >= 1
