"""Local FFmpeg trim, silence-removal, and footage-restoration operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vedit.providers.media_ops.ffmpeg_local import (
    FfmpegMediaOpsProvider,
    compute_keep_segments,
    parse_silencedetect,
)


def _ffmpeg(*args: str) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-y", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


@pytest.fixture()
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    )  # fmt: skip
    return path


def test_parse_silencedetect_closes_trailing_silence() -> None:
    stderr = (
        "[silencedetect @ 0x1] silence_start: 1.0\n"
        "[silencedetect @ 0x1] silence_end: 2.0 | silence_duration: 1.0\n"
        "[silencedetect @ 0x1] silence_start: 4.5\n"
    )
    assert parse_silencedetect(stderr, 5.0) == [(1.0, 2.0), (4.5, 5.0)]


def test_compute_keep_segments_pads_inner_and_trims_edges() -> None:
    silences = [(0.0, 0.5), (1.0, 2.0), (3.0, 3.1), (4.5, 5.0)]
    keep = compute_keep_segments(silences, 5.0, padding_s=0.1)
    assert keep == [(0.4, 1.1), (1.9, 4.6)]


def test_compute_keep_segments_without_silence_keeps_everything() -> None:
    assert compute_keep_segments([], 2.5, padding_s=0.1) == [(0.0, 2.5)]


def test_remove_silence_cuts_inner_pause(tmp_path: Path) -> None:
    speech = tmp_path / "speech.wav"
    _ffmpeg(
        "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=1.5",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
        "-filter_complex", "[0:a]aresample=48000,aformat=channel_layouts=mono[a];"
        "[2:a]aresample=48000,aformat=channel_layouts=mono[c];[a][1:a][c]concat=n=3:v=0:a=1",
        str(speech),
    )  # fmt: skip
    out = tmp_path / "tight.wav"
    result = FfmpegMediaOpsProvider().remove_silence(speech, out, padding_s=0.1)
    assert result.operation == "remove_silence"
    assert result.metadata["removed_s"] == pytest.approx(1.3, abs=0.1)
    assert _duration(out) == pytest.approx(result.metadata["output_duration_s"], abs=0.05)


def test_trim_stream_copy_and_accurate(clip: Path, tmp_path: Path) -> None:
    ops = FfmpegMediaOpsProvider()
    fast = ops.trim(clip, tmp_path / "fast.mp4", start_s=1.0, end_s=2.0)
    exact = ops.trim(clip, tmp_path / "exact.mp4", start_s=0.5, end_s=1.5, accurate=True)
    assert fast.metadata["mode"] == "stream_copy"
    assert exact.metadata["mode"] == "accurate"
    assert _duration(exact.output_path) == pytest.approx(1.0, abs=0.1)
    assert fast.output_path.stat().st_size > 1000
    with pytest.raises(ValueError):
        ops.trim(clip, tmp_path / "bad.mp4", start_s=2.0, end_s=1.0)


def test_restore_footage_applies_requested_filters(clip: Path, tmp_path: Path) -> None:
    ops = FfmpegMediaOpsProvider()
    result = ops.restore_footage(clip, tmp_path / "restored.mp4", deinterlace=True)
    assert result.metadata["filters"] == ["bwdif=mode=send_frame", "deshake", "hqdn3d=1.5:1.5:6:6"]
    assert result.output_path.stat().st_size > 1000
    with pytest.raises(ValueError):
        ops.restore_footage(clip, tmp_path / "noop.mp4", stabilize=False, denoise=False)
