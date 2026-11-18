"""End-to-end tests for native `vedit-probe` binary and Python probe bridge."""

from __future__ import annotations

import subprocess
from pathlib import Path

from vedit.analyzers.media_probe import ProbeOptions, hash_media, probe_media


def _make_synthetic_video(out_path: Path) -> None:
    """Generate a 3s 640x360@30fps H.264/AAC clip with 1 hard scene cut at 1.5s and 1.5s silence."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=640x360:rate=30:duration=1.5",
        "-f",
        "lavfi",
        "-i",
        "mandelbrot=size=640x360:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1.5",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo:d=1.5",
        "-t",
        "3",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def _make_audio_only(out_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=523.25:duration=2",
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_probe_detects_hard_cut_lufs_palette_and_extracts_keyframes(tmp_path: Path) -> None:
    clip = tmp_path / "sample.mp4"
    kf_dir = tmp_path / "keyframes"
    _make_synthetic_video(clip)

    h = hash_media(clip)
    assert len(h["sha256"]) == 64
    assert h["file_bytes"] == clip.stat().st_size

    res = probe_media(
        clip,
        ProbeOptions(
            true_peak=True,
            extract_keyframes_dir=kf_dir,
        ),
    )
    assert res.sha256 == h["sha256"]
    assert res.video.present is True
    assert res.video.width == 640
    assert res.video.height == 360
    assert res.video.is_cfr is True
    assert res.shot_stats.count == 2
    assert 1.3 <= res.shots[0].end_s <= 1.7
    assert res.audio.present is True
    assert res.audio.integrated_lufs is not None
    assert res.audio.true_peak_dbtp is not None
    assert len(res.audio.silence_intervals) >= 1
    assert res.visual.sampled_frames >= 4
    assert len(res.visual.palette) >= 1
    assert len(res.visual.keyframes) == 2
    for kf in res.visual.keyframes:
        assert Path(kf.path).is_file()


def test_probe_handles_audio_only_file(tmp_path: Path) -> None:
    wav = tmp_path / "tone.wav"
    _make_audio_only(wav)

    res = probe_media(wav)
    assert res.video.present is False
    assert res.audio.present is True
    assert res.audio.integrated_lufs is not None
    assert res.shots == []
    assert res.visual.sampled_frames == 0
