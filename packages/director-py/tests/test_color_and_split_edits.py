"""Tests for two-stage color pipeline, blend modes, J/L-cut execution, and dynamic rhythm."""

from __future__ import annotations

import subprocess
from pathlib import Path

from vedit.analyzers.media_probe import hash_media
from vedit.contracts import load_platform_targets
from vedit.director.planner import _plan_video_cuts
from vedit.director.verifier import verify_edit_plan
from vedit.mastering.ffmpeg_master import (
    _derive_split_edit_audio_tracks,
    assemble_hybrid_deliverable,
    compute_shot_match_correction,
)
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import (
    AssetRef,
    BrandStylePolicy,
    ColorCorrectionSpec,
    ColorGradeSpec,
    EditPlan,
    MediaProbeResult,
    PlatformTarget,
    VideoClipOp,
)


def _synth_av(path: Path, duration_s: float = 2.0, color: str = "0x243444") -> None:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=720x1280:r=30:d={duration_s}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:sample_rate=48000:duration={duration_s}",
            "-af",
            "volume=0.25",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


def test_color_pipeline_shot_match_and_j_cut_assembly(tmp_path: Path) -> None:
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    ov_seg = tmp_path / "ov.mp4"
    _synth_av(clip_a, duration_s=2.0, color="0x122232")
    _synth_av(clip_b, duration_s=2.0, color="0x223242")
    _synth_av(ov_seg, duration_s=1.0, color="0x303030")

    matched = compute_shot_match_correction(
        60.0, 100.0, source_ab=(2.0, -4.0), target_ab=(0.0, 4.0)
    )
    assert matched.exposure_ev > 0.0
    assert matched.temperature > 0.0

    plan = EditPlan(
        schema_version="1.0",
        job_id="job_color_split",
        project_id="proj_color",
        brand_id="geoverum",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=3.0,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[
            AssetRef(
                asset_id="src_a",
                sha256=hash_media(clip_a)["sha256"],
                kind="video",
                path=str(clip_a),
                duration_s=2.0,
                has_audio=True,
            ),
            AssetRef(
                asset_id="src_b",
                sha256=hash_media(clip_b)["sha256"],
                kind="video",
                path=str(clip_b),
                duration_s=2.0,
                has_audio=True,
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="v1",
                asset_id="src_a",
                timeline_start_s=0.0,
                timeline_duration_s=1.5,
                source_start_s=0.0,
                role="a_roll",
                motion_direction="left_to_right",
                color_correction=ColorCorrectionSpec(
                    exposure_ev=0.1, contrast=1.05, saturation=1.05
                ),
                color_grade=ColorGradeSpec(preset="cool_investigative", intensity=0.8),
            ),
            VideoClipOp(
                clip_id="v2",
                asset_id="src_b",
                timeline_start_s=1.5,
                timeline_duration_s=1.5,
                source_start_s=0.5,
                role="b_roll",
                j_cut_lead_s=0.4,
                motion_direction="left_to_right",
                color_correction=matched,
                color_grade=ColorGradeSpec(preset="dread_dim_vignette", intensity=0.7),
            ),
        ],
        overlay_compositions=[],
        audio_tracks=[],
        verifier_passed=True,
    )

    derived = _derive_split_edit_audio_tracks(
        plan, {"src_a": clip_a, "src_b": clip_b}
    )
    assert len(derived) == 1
    assert derived[0].split_edit_role == "j_cut"
    assert derived[0].timeline_start_s == 1.1

    out_mp4 = tmp_path / "out.mp4"
    res = assemble_hybrid_deliverable(
        plan,
        target,
        out_mp4,
        overlay_segments=[(0.5, 1.5, ov_seg)],
        overlay_blend_modes=["screen"],
        encode_preset="ultrafast",
    )
    assert res.output_path.is_file()
    assert res.audio_master is not None
    qc = audit_mastered_deliverable(out_mp4, target, check_visual=False)
    assert qc.passed, qc.to_dict()


def test_verifier_flags_screen_direction_reversal_and_planner_varies_rhythm() -> None:
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    policy_path = (
        Path(__file__).resolve().parents[3]
        / "profiles"
        / "brands"
        / "geoverum"
        / "brand_style_policy.json"
    )
    policy = BrandStylePolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    plan = EditPlan(
        schema_version="1.0",
        job_id="job_dir_rev",
        project_id="proj_dir",
        brand_id="geoverum",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=4.0,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[
            AssetRef(
                asset_id="v",
                sha256="a" * 64,
                kind="video",
                path="inputs/a.mp4",
                duration_s=4.0,
                has_audio=True,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v",
                timeline_start_s=0.0,
                timeline_duration_s=2.0,
                source_start_s=0.0,
                role="b_roll",
                motion_direction="left_to_right",
            ),
            VideoClipOp(
                clip_id="c2",
                asset_id="v",
                timeline_start_s=2.0,
                timeline_duration_s=2.0,
                source_start_s=2.0,
                role="b_roll",
                motion_direction="right_to_left",
            ),
        ],
        overlay_compositions=[],
        audio_tracks=[],
    )
    report = verify_edit_plan(plan, policy, target)
    assert any(w.code == "SCREEN_DIRECTION_REVERSAL" for w in report.warnings)

    probe = MediaProbeResult.model_validate(
        {
            "path": "inputs/long.mp4",
            "sha256": "b" * 64,
            "file_bytes": 1000,
            "container": {"format_name": "mp4", "duration_s": 30.0},
            "video": {"present": True, "width": 1080, "height": 1920, "fps": 30.0, "is_cfr": True},
            "audio": {"present": True, "silence_intervals": [], "silence_ratio": 0.0},
            "shots": [],
            "shot_stats": {
                "count": 1,
                "asl_p25_s": 30.0,
                "asl_p50_s": 30.0,
                "asl_p75_s": 30.0,
                "cuts_per_min": 2.0,
            },
            "visual": {
                "sampled_frames": 0,
                "palette": [],
                "palette_entropy": 0.0,
                "mean_luminance": 100.0,
                "band_luminance": {"upper": 100.0, "center": 100.0, "lower_third": 100.0},
                "mean_sharpness": 50.0,
                "black_intervals": [],
                "keyframes": [],
            },
            "timing_ms": {"hash_ms": 1, "ffprobe_ms": 1, "stream_analyze_ms": 1, "total_ms": 3},
        }
    )
    clips = _plan_video_cuts(probe, policy, None, primary_asset_id="v", reframed_to_target=True)
    durations = [round(c.timeline_duration_s, 2) for c in clips]
    assert len(set(durations)) >= 2
