"""Integration tests for Python->HyperFrames compiler, FFmpeg mastering, QC, and Modal spec."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from vedit.analyzers.media_probe import hash_media
from vedit.compiler.hf_bridge import HyperframesCompileError, compile_edit_plan
from vedit.contracts import find_repo_root, load_platform_targets
from vedit.mastering.ffmpeg_master import assemble_hybrid_deliverable, master_audio_mix
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    EditPlan,
    OverlayCompositionOp,
    PlatformTarget,
    VideoClipOp,
)


def _synth_video(path: Path, duration_s: float = 2.5, color: str = "0x1E293B") -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1280x720:r=30:d={duration_s}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed generating synthetic video: {proc.stderr}")


def _synth_audio(path: Path, freq_hz: int, duration_s: float = 2.5, amp: float = 0.25) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq_hz}:sample_rate=48000:duration={duration_s}",
        "-af",
        f"volume={amp}",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed generating synthetic audio: {proc.stderr}")


def test_python_bridge_compiles_and_lints_hyperframes_project(tmp_path: Path) -> None:
    platforms = load_platform_targets()
    target = PlatformTarget.model_validate(platforms["reels_9x16_1080p"])
    plan = EditPlan(
        schema_version="1.0",
        job_id="job_bridge_01",
        project_id="proj_bridge_01",
        brand_id="brand_bridge",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=4.0,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[],
        video_tracks=[],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="hook_ov",
                kind="kinetic_callout",
                timeline_start_s=0.1,
                timeline_duration_s=1.8,
                transparent=True,
                safe_band="upper_safe",
                props={
                    "headline": "3.2x Faster Mastering",
                    "fg_color": "#F8FAFC",
                    "bg_color": "#0B0F19",
                    "accent_color": "#38BDF8",
                },
            )
        ],
        audio_tracks=[],
        verifier_passed=True,
    )

    out_dir = tmp_path / "hf_out"
    compiled = compile_edit_plan(plan, out_dir, platform_target=target, run_lint=True)
    assert compiled.index_html_path.is_file()
    assert compiled.recommended_format == "mov"
    assert compiled.lint is not None
    assert compiled.lint.ok is True
    assert compiled.lint.total_errors == 0

    # Reject forbidden runtime CSS blur over the Python->Node boundary.
    bad_plan = plan.model_copy(
        update={
            "overlay_compositions": [
                plan.overlay_compositions[0].model_copy(
                    update={"props": {"headline": "Blur", "backdropFilter": "blur(10px)"}}
                )
            ]
        }
    )
    with pytest.raises(HyperframesCompileError, match="CSS performance gate failed"):
        compile_edit_plan(bad_plan, tmp_path / "hf_bad")


def test_two_pass_mastering_hybrid_assembly_and_qc_audit(tmp_path: Path) -> None:
    src_video = tmp_path / "raw_clip.mp4"
    vo_wav = tmp_path / "voiceover.wav"
    bgm_wav = tmp_path / "bgm.wav"
    _synth_video(src_video, duration_s=3.0)
    _synth_audio(vo_wav, freq_hz=440, duration_s=3.0, amp=0.35)
    _synth_audio(bgm_wav, freq_hz=220, duration_s=3.0, amp=0.20)

    v_hash = hash_media(src_video)["sha256"]
    vo_hash = hash_media(vo_wav)["sha256"]
    bgm_hash = hash_media(bgm_wav)["sha256"]

    platforms = load_platform_targets()
    target = PlatformTarget.model_validate(platforms["reels_9x16_1080p"])

    plan = EditPlan(
        schema_version="1.0",
        job_id="job_master_01",
        project_id="proj_master_01",
        brand_id="brand_master",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=2.4,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[
            AssetRef(
                asset_id="vid_1",
                sha256=v_hash,
                kind="video",
                path=str(src_video),
                duration_s=3.0,
                has_audio=False,
            ),
            AssetRef(
                asset_id="vo_1",
                sha256=vo_hash,
                kind="audio_speech",
                path=str(vo_wav),
                duration_s=3.0,
                has_audio=True,
            ),
            AssetRef(
                asset_id="bgm_1",
                sha256=bgm_hash,
                kind="audio_bgm",
                path=str(bgm_wav),
                duration_s=3.0,
                has_audio=True,
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="clip_1",
                asset_id="vid_1",
                timeline_start_s=0.0,
                timeline_duration_s=1.2,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
            ),
            VideoClipOp(
                clip_id="clip_2",
                asset_id="vid_1",
                timeline_start_s=1.2,
                timeline_duration_s=1.2,
                source_start_s=1.0,
                role="b_roll",
                reframed_to_target=True,
            ),
        ],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="trk_vo",
                asset_id="vo_1",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=2.4,
                source_start_s=0.0,
                gain_db=0.0,
                cleaned_speech_stem=True,
            ),
            AudioTrackOp(
                track_id="trk_bgm",
                asset_id="bgm_1",
                audio_group="music",
                timeline_start_s=0.0,
                timeline_duration_s=2.4,
                source_start_s=0.0,
                gain_db=-10.0,
                carve_against_group="voiceover",
                carve_strength=0.8,
                cleaned_speech_stem=False,
            ),
        ],
        verifier_passed=True,
    )

    audio_out = tmp_path / "master_audio.wav"
    audio_res = master_audio_mix(plan, target, audio_out)
    assert audio_res.two_pass is True
    assert audio_res.measurement is not None
    assert audio_out.is_file()

    final_mp4 = tmp_path / "final_deliverable.mp4"
    assembly_res = assemble_hybrid_deliverable(plan, target, final_mp4)
    assert assembly_res.output_path.is_file()
    assert assembly_res.width == 1080
    assert assembly_res.height == 1920

    qc = audit_mastered_deliverable(final_mp4, target, require_audio=True)
    assert qc.passed is True, f"QC errors: {qc.errors}, metrics: {qc.metrics}"
    assert qc.metrics["is_cfr"] is True
    assert qc.metrics["color_space"] == "bt709"
    assert qc.metrics["color_primaries"] == "bt709"
    assert qc.metrics["color_trc"] == "bt709"
    assert qc.metrics["sample_rate_hz"] == 48000
    assert qc.metrics["channels"] == 2
    assert -14.5 <= qc.metrics["integrated_lufs"] <= -13.5
    assert qc.metrics["true_peak_dbtp"] <= -1.0


def test_modal_worker_image_spec_and_cost_estimator() -> None:
    cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
    if cloud_src not in sys.path:
        sys.path.insert(0, cloud_src)

    from vedit_cloud.app import CAS_VOLUME_NAME, estimate_modal_render_cost
    from vedit_cloud.image import WORKER_CHROMIUM_FLAGS, build_worker_image

    img = build_worker_image()
    assert img is not None
    assert WORKER_CHROMIUM_FLAGS == "--no-browser-gpu --use-gl=swiftshader"
    assert CAS_VOLUME_NAME == "vedit-cas-cache"
    usd = estimate_modal_render_cost(10_000, cpus=4.0, memory_mb=8192)
    assert usd > 0.0
