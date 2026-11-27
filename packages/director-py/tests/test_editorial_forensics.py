"""Tests for editorial forensics: eye-trace jump, exposure shock, split edits, and tension curve."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from vedit.analyzers.editorial_forensics import (
    analyze_cross_cut_continuity,
    analyze_editorial_forensics,
    compute_multimodal_tension_curve,
    detect_split_edits,
)
from vedit.cli import app


def _synth_two_shot_jump_video(path: Path) -> None:
    """Create a 2s 2-shot video: bright top-left box -> bright bottom-right box."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x050505:s=320x180:r=30:d=1.0",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x888888:s=320x180:r=30:d=1.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=400:sample_rate=48000:duration=2.0",
            "-filter_complex",
            "[0:v]drawbox=x=10:y=10:w=60:h=50:color=white:t=fill[v0];"
            "[1:v]drawbox=x=240:y=120:w=60:h=50:color=white:t=fill[v1];"
            "[v0][v1]concat=n=2:v=1:a=0,format=yuv420p[v]",
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
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


def test_cross_cut_continuity_detects_eye_trace_and_exposure_jump(tmp_path: Path) -> None:
    vid = tmp_path / "jump.mp4"
    _synth_two_shot_jump_video(vid)
    rep = analyze_cross_cut_continuity(vid, cuts_s=[1.0])
    assert rep.cuts_analyzed == 1
    assert rep.mean_eye_trace_jump > 0.35
    assert rep.exposure_shocks == 1
    assert "large_eye_jump" in rep.per_cut[0].flags
    assert "exposure_shock" in rep.per_cut[0].flags


def test_detect_split_edits_classifies_j_l_and_straight_cuts() -> None:
    rep = detect_split_edits(
        cuts_s=[2.0, 5.0, 8.0],
        speech_intervals_s=[(1.5, 3.0), (3.6, 5.45), (8.02, 9.5)],
    )
    assert rep.total_cuts == 3
    assert rep.j_cut_count == 1
    assert rep.l_cut_count == 1
    assert rep.straight_cut_count == 1
    assert rep.median_j_lead_s == 0.5
    assert rep.median_l_trail_s == 0.45

    post_silence = detect_split_edits(cuts_s=[5.0], speech_intervals_s=[(5.45, 7.0)])
    assert post_silence.events[0].kind == "straight_cut"
    assert post_silence.events[0].audio_offset_s == 0.0


def test_multimodal_tension_curve_and_editorial_cli(tmp_path: Path) -> None:
    vid = tmp_path / "jump.mp4"
    _synth_two_shot_jump_video(vid)
    transcript = {
        "words": [
            {"text": "Start", "start_s": 0.1, "end_s": 0.4},
            {"text": "slowly", "start_s": 0.5, "end_s": 0.9},
            {"text": "then", "start_s": 1.1, "end_s": 1.2},
            {"text": "escalate", "start_s": 1.25, "end_s": 1.4},
            {"text": "fast", "start_s": 1.45, "end_s": 1.6},
            {"text": "now", "start_s": 1.65, "end_s": 1.85},
        ]
    }
    storyboard = {
        "beats": [
            {"beat_id": "b1", "start_s": 0.0, "end_s": 1.0, "tension_level": 0.3},
            {"beat_id": "b2", "start_s": 1.0, "end_s": 2.0, "tension_level": 0.9},
        ]
    }
    curve = compute_multimodal_tension_curve(
        2.0, transcript=transcript, storyboard=storyboard, cuts_s=[1.0], bins=4
    )
    assert curve.escalation_slope > 0.2
    assert curve.pacing_variance > 0.05

    full = analyze_editorial_forensics(
        vid, cuts_s=[1.0], transcript=transcript, storyboard=storyboard
    )
    assert full.continuity.cuts_analyzed == 1
    assert full.mono_phase_correlation is not None

    probe_json = tmp_path / "shots.json"
    probe_json.write_text(
        json.dumps({"shots": [{"start_s": 0.0}, {"start_s": 1.0}]}),
        encoding="utf-8",
    )
    res = CliRunner().invoke(
        app,
        ["breakdown", "editorial", str(vid), "--shots-from", str(probe_json)],
    )
    assert res.exit_code == 0, res.output
    parsed = json.loads(res.output)
    assert parsed["continuity"]["cuts_analyzed"] == 1


def test_classify_color_harmony_reaches_split_complementary() -> None:
    from vedit.analyzers.editorial_forensics import _classify_color_harmony

    # Bin centers at 15, 165 (diff=150), and 225 (d02=150) form a split-complementary triad.
    hues = [15.0] * 10 + [165.0] * 6 + [225.0] * 6
    assert _classify_color_harmony(hues) == "split_complementary"
