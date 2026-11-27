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


def test_modal_worker_image_spec_and_cas_staging(tmp_path: Path) -> None:
    cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
    if cloud_src not in sys.path:
        sys.path.insert(0, cloud_src)

    from vedit_cloud.app import (
        CAS_VOLUME_NAME,
        download_cas_file,
        estimate_modal_render_cost,
        stage_local_assets_for_cloud,
    )
    from vedit_cloud.image import (
        PINNED_CHROME_HEADLESS_VERSION,
        WORKER_CHROMIUM_FLAGS,
        build_worker_image,
    )

    img = build_worker_image()
    assert img is not None
    assert WORKER_CHROMIUM_FLAGS == "--no-browser-gpu --use-gl=swiftshader"
    assert PINNED_CHROME_HEADLESS_VERSION == "158.0.8127.36"
    assert CAS_VOLUME_NAME == "vedit-cas-cache-v2"
    usd = estimate_modal_render_cost(10_000, cpus=4.0, memory_mb=8192)
    assert usd > 0.0

    from vedit_cloud.app import _chunk_filename

    # Explicit fmt prevents job_id containing "mov" from corrupting chunk extensions.
    assert _chunk_filename(0, "mp4") == "chunk_0000.mp4"
    assert _chunk_filename(3, "mov") == "chunk_0003.mov"

    # Mock Modal Volume CAS upload dedup and download.
    cached_sha = "1" * 64
    new_sha = "2" * 64
    local_cached = tmp_path / "cached.mp4"
    local_new = tmp_path / "fresh.wav"
    local_cached.write_bytes(b"cached")
    local_new.write_bytes(b"fresh")

    class _FakeEntry:
        def __init__(self, path: str) -> None:
            self.path = path

    class _FakeBatch:
        def __init__(self, target_list: list[tuple[str, str]]) -> None:
            self._list = target_list

        def __enter__(self) -> _FakeBatch:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def put_file(self, src: str, dst: str) -> None:
            self._list.append((src, dst))

    class _FakeVolume:
        def __init__(self) -> None:
            self.uploaded: list[tuple[str, str]] = []

        def listdir(self, prefix: str) -> list[_FakeEntry]:
            assert prefix == "/sources"
            return [_FakeEntry(f"sources/{cached_sha}.mp4")]

        def batch_upload(self, force: bool = False) -> _FakeBatch:
            return _FakeBatch(self.uploaded)

        def read_file(self, remote_path: str):
            assert remote_path == "jobs/j_1/out.mp4"
            yield b"hello-"
            yield b"mp4"

    vol = _FakeVolume()
    plan = EditPlan(
        schema_version="1.0",
        job_id="j_1",
        project_id="p_1",
        brand_id="b_1",
        platform_target_id="reels_9x16_1080p",
        render_strategy="hybrid",
        duration_s=2.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(asset_id="a1", sha256=cached_sha, kind="video", path=str(local_cached)),
            AssetRef(asset_id="a2", sha256=new_sha, kind="audio_speech", path=str(local_new)),
            AssetRef(
                asset_id="a3",
                sha256="3" * 64,
                kind="audio_bgm",
                path="https://cdn.example/music.mp3",
            ),
        ],
        video_tracks=[],
        overlay_compositions=[],
        audio_tracks=[],
    )

    staged = stage_local_assets_for_cloud(plan, vol)
    assert len(vol.uploaded) == 1
    assert vol.uploaded[0][1] == f"/sources/{new_sha}.wav"
    assert staged.assets[0].path == f"/vol/cas/sources/{cached_sha}.mp4"
    assert staged.assets[1].path == f"/vol/cas/sources/{new_sha}.wav"
    assert staged.assets[2].path == "https://cdn.example/music.mp3"

    out_dl = tmp_path / "downloaded.mp4"
    download_cas_file(vol, "/jobs/j_1/out.mp4", out_dl)
    assert out_dl.read_bytes() == b"hello-mp4"

    # LUT files referenced on clips must also be staged to Modal CAS and rewritten.
    from vedit_cloud.app import _plan_has_split_audio

    from vedit.models import ColorGradeSpec

    lut_file = tmp_path / "film.cube"
    lut_file.write_text("LUT_3D_SIZE 2\n0 0 0\n1 1 1\n", encoding="utf-8")
    plan_with_lut = plan.model_copy(
        update={
            "video_tracks": [
                VideoClipOp(
                    clip_id="c_lut",
                    asset_id="a1",
                    timeline_start_s=0.0,
                    timeline_duration_s=2.0,
                    source_start_s=0.0,
                    role="a_roll",
                    j_cut_lead_s=0.35,
                    color_grade=ColorGradeSpec(lut_path=str(lut_file)),
                )
            ]
        }
    )
    staged_lut = stage_local_assets_for_cloud(plan_with_lut, vol)
    staged_lut_path = staged_lut.video_tracks[0].color_grade.lut_path
    assert staged_lut_path is not None
    assert staged_lut_path.startswith("/vol/cas/sources/")
    assert staged_lut_path.endswith(".cube")
    assert any(dst.endswith(".cube") for _, dst in vol.uploaded)

    # Split-audio detection must ignore J/L-cut clips whose video asset has_audio=False.
    assert _plan_has_split_audio(plan_with_lut) is False
    plan_with_audio_clip = plan_with_lut.model_copy(
        update={
            "assets": [
                plan_with_lut.assets[0].model_copy(update={"has_audio": True}),
                *plan_with_lut.assets[1:],
            ]
        }
    )
    assert _plan_has_split_audio(plan_with_audio_clip) is True


def test_libass_fastpath_partition_and_e2e_master_9x16_and_16x9(tmp_path: Path) -> None:
    from vedit.mastering.ass_captions import (
        build_sparse_hf_plan,
        partition_overlays_for_hybrid,
        write_ass_overlays_file,
    )

    platforms = load_platform_targets()
    shorts_target = PlatformTarget.model_validate(platforms["shorts_9x16_1080p"])
    yt_target = PlatformTarget.model_validate(platforms["youtube_16x9_1080p"])

    src_video = tmp_path / "base.mp4"
    vo_wav = tmp_path / "vo.wav"
    bgm_wav = tmp_path / "bgm.wav"
    _synth_video(src_video, duration_s=3.0)
    _synth_audio(vo_wav, freq_hz=440, duration_s=3.0, amp=0.35)
    _synth_audio(bgm_wav, freq_hz=220, duration_s=3.0, amp=0.18)

    v_hash = hash_media(src_video)["sha256"]
    vo_hash = hash_media(vo_wav)["sha256"]
    bgm_hash = hash_media(bgm_wav)["sha256"]

    overlays = [
        OverlayCompositionOp(
            overlay_id="cap_1",
            kind="caption_rail",
            template_id="caption_rail",
            timeline_start_s=0.1,
            timeline_duration_s=1.0,
            transparent=True,
            safe_band="lower_third",
            props={"text": "Three tectonic plates", "caption_style": "plain"},
        ),
        OverlayCompositionOp(
            overlay_id="wm_1",
            kind="lower_third",
            template_id="broadcast_bug",
            timeline_start_s=0.0,
            timeline_duration_s=2.0,
            transparent=True,
            safe_band="upper_safe",
            props={"text": "geoverum"},
        ),
        OverlayCompositionOp(
            overlay_id="card_1",
            kind="data_card",
            template_id="amber_fact_card",
            timeline_start_s=1.1,
            timeline_duration_s=0.9,
            transparent=True,
            safe_band="lower_third",
            props={"text": "42 mm/yr"},
        ),
    ]

    plan_base = EditPlan(
        schema_version="1.0",
        job_id="job_fastpath_mov_test",
        project_id="proj_fp",
        brand_id="geoverum",
        platform_target_id=shorts_target.platform_id,
        render_strategy="hybrid",
        duration_s=2.2,
        fps=shorts_target.fps,
        width=shorts_target.width,
        height=shorts_target.height,
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
                clip_id="c1",
                asset_id="vid_1",
                timeline_start_s=0.0,
                timeline_duration_s=1.1,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
                scale=1.08,
                transition_in="clean_fade",
            ),
            VideoClipOp(
                clip_id="c2",
                asset_id="vid_1",
                timeline_start_s=1.1,
                timeline_duration_s=1.1,
                source_start_s=1.0,
                role="a_roll",
                reframed_to_target=True,
            ),
        ],
        overlay_compositions=overlays,
        audio_tracks=[
            AudioTrackOp(
                track_id="vo",
                asset_id="vo_1",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=2.2,
                source_start_s=0.0,
                gain_db=0.0,
                cleaned_speech_stem=True,
            ),
            AudioTrackOp(
                track_id="bgm",
                asset_id="bgm_1",
                audio_group="music",
                timeline_start_s=0.0,
                timeline_duration_s=2.2,
                source_start_s=0.0,
                gain_db=-12.0,
                carve_against_group="voiceover",
                carve_strength=0.45,
            ),
        ],
        verifier_passed=True,
    )

    ass_ov, hf_ov = partition_overlays_for_hybrid(plan_base)
    assert [o.overlay_id for o in ass_ov] == ["cap_1", "wm_1"]
    assert [o.overlay_id for o in hf_ov] == ["card_1"]

    sparse = build_sparse_hf_plan(plan_base, hf_ov)
    assert [o.overlay_id for o in sparse.overlay_compositions] == ["card_1"]

    ass_path = write_ass_overlays_file(ass_ov, shorts_target, tmp_path / "test.ass")
    ass_text = ass_path.read_text(encoding="utf-8")
    assert "Three tectonic plates" in ass_text
    assert "geoverum" in ass_text
    # Symmetric horizontal margin = round(1080 * 0.16) = 173; bottom = round(1920 * 0.285) = 547.
    assert ",2,173,173,547,1" in ass_text

    # Run real FFmpeg libass fast-path end-to-end on 9:16 and 16:9 and verify QC passes!
    plain_only_plan = plan_base.model_copy(update={"overlay_compositions": ass_ov})
    out_9x16 = tmp_path / "fast_9x16.mp4"
    res_9x16 = assemble_hybrid_deliverable(
        plain_only_plan,
        shorts_target,
        out_9x16,
        use_ass_fastpath=True,
        encode_preset="veryfast",
    )
    assert res_9x16.output_path.is_file()
    qc_9x16 = audit_mastered_deliverable(out_9x16, shorts_target, require_audio=True)
    assert qc_9x16.passed is True, f"9:16 QC failed: {qc_9x16.errors}"

    plan_16x9 = plain_only_plan.model_copy(
        update={
            "platform_target_id": yt_target.platform_id,
            "width": yt_target.width,
            "height": yt_target.height,
        }
    )
    out_16x9 = tmp_path / "fast_16x9.mp4"
    res_16x9 = assemble_hybrid_deliverable(
        plan_16x9,
        yt_target,
        out_16x9,
        use_ass_fastpath=True,
        encode_preset="veryfast",
    )
    assert res_16x9.output_path.is_file()
    qc_16x9 = audit_mastered_deliverable(out_16x9, yt_target, require_audio=True)
    assert qc_16x9.passed is True, f"16:9 QC failed: {qc_16x9.errors}"


def test_sparse_hf_window_grouping_and_overlay_segments_master(tmp_path: Path) -> None:
    from vedit.mastering.sparse_hf import build_window_local_plan, group_sparse_hf_windows

    platforms = load_platform_targets()
    shorts_target = PlatformTarget.model_validate(platforms["shorts_9x16_1080p"])

    src_video = tmp_path / "base.mp4"
    seg_video = tmp_path / "seg.mp4"
    _synth_video(src_video, duration_s=3.0, color="0x03161F")
    _synth_video(seg_video, duration_s=0.8, color="0xF5C542")
    v_hash = hash_media(src_video)["sha256"]

    hf_overlays = [
        OverlayCompositionOp(
            overlay_id="hero_a",
            kind="data_card",
            template_id="comparison_bar_chart",
            timeline_start_s=28.75,
            timeline_duration_s=5.0,
            transparent=True,
            safe_band="upper_safe",
            props={"title": "Rivers"},
        ),
        OverlayCompositionOp(
            overlay_id="hero_b",
            kind="full_scene",
            template_id="cross_section_diagram",
            timeline_start_s=48.20,
            timeline_duration_s=5.8,
            transparent=True,
            safe_band="upper_safe",
            props={"title": "Peatland"},
        ),
    ]
    plan = EditPlan(
        schema_version="1.0",
        job_id="job_sparse_win",
        project_id="proj_sw",
        brand_id="geoverum",
        platform_target_id=shorts_target.platform_id,
        render_strategy="hybrid",
        duration_s=96.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(
                asset_id="v1",
                sha256=v_hash,
                kind="video",
                path=str(src_video),
                duration_s=3.0,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v1",
                timeline_start_s=0.0,
                timeline_duration_s=2.4,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
            )
        ],
        overlay_compositions=hf_overlays,
        audio_tracks=[],
        verifier_passed=True,
    )

    windows = group_sparse_hf_windows(plan, hf_overlays)
    assert len(windows) == 2
    assert windows[0].start_s == 28.7
    assert windows[0].end_s == 33.8
    assert windows[1].start_s == 48.15
    assert windows[1].end_s == 54.05

    local_w0 = build_window_local_plan(plan, windows[0])
    assert local_w0.duration_s == 5.1
    assert local_w0.overlay_compositions[0].timeline_start_s == 0.05
    assert local_w0.video_tracks == []

    # Verify FFmpeg composites sparse timed overlay_segments cleanly on short clip.
    short_plan = plan.model_copy(update={"duration_s": 2.4, "overlay_compositions": []})
    out_mp4 = tmp_path / "sparse_comp.mp4"
    res = assemble_hybrid_deliverable(
        short_plan,
        shorts_target,
        out_mp4,
        overlay_segments=[(0.5, 1.2, seg_video)],
        use_ass_fastpath=False,
        encode_preset="veryfast",
    )
    assert res.used_overlay_video is True
    assert res.output_path.is_file()
    qc = audit_mastered_deliverable(out_mp4, shorts_target, require_audio=False)
    assert qc.passed is True, f"Sparse segment QC failed: {qc.errors}"


def test_caption_style_props_override_house_style(tmp_path: Path) -> None:
    from vedit.mastering.ass_captions import write_ass_overlays_file

    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    base = {"text": "has been walking", "caption_style": "plain"}

    default_ass = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="cap_default",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="lower_third",
                props=base,
            )
        ],
        target,
        tmp_path / "default.ass",
    ).read_text(encoding="utf-8")
    assert "Style: CaptionLower,Rubik,56," in default_ass
    assert "\\blur" not in default_ass

    styled_ass = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="cap_styled",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="lower_third",
                props={
                    **base,
                    "caption_font_family": "Inter",
                    "caption_font_px": 72,
                    "caption_bottom_pct": 0.271,
                    "caption_opacity": 0.9,
                    "caption_outline_px": 0,
                    "caption_shadow_px": 4,
                    "caption_shadow_opacity": 0.55,
                    "caption_shadow_blur_px": 6,
                },
            )
        ],
        target,
        tmp_path / "styled.ass",
    ).read_text(encoding="utf-8")
    # 90% opacity -> alpha 0x19; bottom margin round(1920 * 0.271) = 520.
    assert "Style: CaptionLower,Inter,72,&H19EAF1F4," in styled_ass
    assert ",-1,0,0,0,100,100,0.3,0,1,0.0,0,2," in styled_ass
    assert ",520,1" in styled_ass
    shadow_line = next(line for line in styled_ass.splitlines() if line.startswith("Dialogue: 0,"))
    assert "\\blur6" in shadow_line and "\\1a&H73&" in shadow_line
    assert ",516,," in shadow_line
    assert any(
        line.startswith("Dialogue: 1,") and line.endswith("has been walking")
        for line in styled_ass.splitlines()
    )

    glow_ass = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="cap_glow",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="lower_third",
                props={
                    **base,
                    "caption_glow_color": "#F5C542",
                    "caption_glow_px": 12,
                    "caption_transition_ms": 140,
                },
            )
        ],
        target,
        tmp_path / "glow.ass",
    ).read_text(encoding="utf-8")
    glow_layer = next(line for line in glow_ass.splitlines() if line.startswith("Dialogue: 0,"))
    assert "\\blur12" in glow_layer and "\\1c&H42C5F5&" in glow_layer
    assert "\\fad(140,140)" in glow_layer

    asym_ass = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="cap_asym",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="lower_third",
                props={
                    **base,
                    "caption_transition_ms": 140,
                    "caption_fade_in_ms": 130,
                    "caption_fade_out_ms": 0,
                },
            )
        ],
        target,
        tmp_path / "asym.ass",
    ).read_text(encoding="utf-8")
    asym_lines = [ln for ln in asym_ass.splitlines() if ln.startswith("Dialogue:")]
    assert asym_lines and all("\\fad(130,0)" in ln for ln in asym_lines)


def test_ffmpeg_xfade_preserves_timeline_duration_and_ssim_fallback(tmp_path: Path) -> None:
    shorts_target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    src_a = tmp_path / "a.mp4"
    src_b = tmp_path / "b.mp4"
    mix_wav = tmp_path / "mix.wav"
    _synth_video(src_a, duration_s=2.0, color="0x1E293B")
    _synth_video(src_b, duration_s=2.0, color="0x0B3D4E")
    _synth_audio(mix_wav, freq_hz=330, duration_s=4.5)

    plan = EditPlan(
        schema_version="1.0",
        job_id="xfade_test",
        project_id="proj_xf",
        brand_id="geoverum",
        platform_target_id=shorts_target.platform_id,
        render_strategy="hybrid",
        duration_s=4.5,
        fps=shorts_target.fps,
        width=shorts_target.width,
        height=shorts_target.height,
        assets=[
            AssetRef(
                asset_id="va",
                sha256=hash_media(src_a)["sha256"],
                kind="video",
                path=str(src_a),
                duration_s=2.0,
                has_audio=False,
            ),
            AssetRef(
                asset_id="vb",
                sha256=hash_media(src_b)["sha256"],
                kind="video",
                path=str(src_b),
                duration_s=2.0,
                has_audio=False,
            ),
            AssetRef(
                asset_id="am",
                sha256=hash_media(mix_wav)["sha256"],
                kind="audio_speech",
                path=str(mix_wav),
                duration_s=4.5,
                has_audio=True,
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="va",
                timeline_start_s=0.0,
                timeline_duration_s=1.5,
                source_start_s=0.0,
                role="a_roll",
                content_type="map",
                reframed_to_target=True,
            ),
            VideoClipOp(
                clip_id="c2",
                asset_id="vb",
                timeline_start_s=1.5,
                timeline_duration_s=1.5,
                source_start_s=0.0,
                role="b_roll",
                content_type="map",
                reframed_to_target=True,
                transition_in="hard_cut",
            ),
            VideoClipOp(
                clip_id="c3",
                asset_id="va",
                timeline_start_s=3.0,
                timeline_duration_s=1.5,
                source_start_s=0.0,
                role="a_roll",
                content_type="map",
                reframed_to_target=True,
                transition_in="clean_crossfade",
            ),
        ],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="mix",
                asset_id="am",
                audio_group="program_mix",
                timeline_start_s=0.0,
                timeline_duration_s=4.5,
                source_start_s=0.0,
                gain_db=0.0,
                cleaned_speech_stem=True,
            )
        ],
        verifier_passed=True,
    )
    out_mp4 = tmp_path / "master_xfade.mp4"
    res = assemble_hybrid_deliverable(
        plan,
        shorts_target,
        out_mp4,
        encode_preset="veryfast",
    )
    assert res.output_path.is_file()
    audit = audit_mastered_deliverable(out_mp4, shorts_target, reference_path=out_mp4)
    assert audit.passed is True, f"Audit failed: {audit.errors}"
    assert abs(audit.metrics["video_duration_s"] - 4.5) < 0.15
    assert (
        audit.metrics.get("ssim") is not None
        or audit.metrics.get("vmaf_score") is not None
    )


def test_xfade_spec_maps_named_transitions() -> None:
    from vedit.mastering.ffmpeg_master import _xfade_spec

    assert _xfade_spec("hard_cut") is None
    assert _xfade_spec("not_a_transition") is None
    zoom = _xfade_spec("whip_zoom_blur")
    assert zoom is not None and zoom[0] == "zoomin"
    disc = _xfade_spec("disc_sweep")
    assert disc is not None
    assert disc[0].startswith("custom:expr=")
    assert disc[2] == "gbrp"
    assert 0.15 <= disc[1] <= 0.25
    fade = _xfade_spec(" Clean_Crossfade ")
    assert fade is not None and fade[0] == "fade" and fade[2] == ""


def _frame_luma(path: Path, t_s: float) -> tuple[float, int]:
    """Mean and max luma of one frame, nearest-neighbour downscaled to keep thin streaks."""
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", f"{t_s:.4f}", "-i", str(path),
            "-frames:v", "1", "-vf", "scale=270:480:flags=neighbor,format=gray",
            "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=True,
    )
    data = proc.stdout
    return sum(data) / max(1, len(data)), max(data)


def _disc_sweep_frames(
    first: str, size: str, frames: tuple[int, int], threads: int = 8
) -> list[bytes]:
    from vedit.mastering.ffmpeg_master import _xfade_spec

    spec = _xfade_spec("disc_sweep")
    assert spec is not None
    w, h = (int(v) for v in size.split("x"))
    graph = (
        "[0]format=gbrp[a];[1]format=gbrp[b];"
        f"[a][b]xfade=transition={spec[0]}:duration=0.2:offset=0.4,"
        f"select='between(n\\,{frames[0]}\\,{frames[1]})',format=gray"
    )
    count = frames[1] - frames[0] + 1
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-filter_complex_threads", str(threads),
            "-f", "lavfi", "-i", f"{first}{':' if '=' in first else '='}s={size}:r=30:d=1",
            "-f", "lavfi", "-i", f"color=c=white:s={size}:r=30:d=1",
            "-filter_complex", graph, "-fps_mode", "passthrough",
            "-frames:v", str(count), "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=True,
    )
    return [proc.stdout[i * w * h : (i + 1) * w * h] for i in range(count)]


def test_disc_sweep_follows_measured_black_profile() -> None:
    """Six-frame sweep on a 9:16 frame: black fraction per frame as measured on the
    reference register swap, fully black on the middle frame, entering from the right."""
    measured = [0.13, 0.59, 0.99, 0.8, 0.26, 0.0]
    w, h = 108, 192
    frames = _disc_sweep_frames("color=c=white", f"{w}x{h}", (13, 18))
    fractions = [sum(1 for v in f if v < 128) / (w * h) for f in frames]
    for got, want in zip(fractions, measured, strict=True):
        assert abs(got - want) <= 0.15, (fractions, measured)
    assert fractions[2] >= 0.995, fractions
    entering = frames[0]
    right = sum(1 for y in range(h) for x in range(w // 2, w) if entering[y * w + x] < 128)
    left = sum(1 for y in range(h) for x in range(0, w // 2) if entering[y * w + x] < 128)
    assert right > 0 and left == 0, (left, right)


def test_disc_sweep_expression_is_thread_safe() -> None:
    """Slice threads share expression registers, so the expression must not use st()/ld()."""
    (frame,) = _disc_sweep_frames("testsrc2", "540x960", (14, 14))

    def region(xs: range) -> list[int]:
        return [frame[y * 540 + x] for y in range(300, 660) for x in xs]

    # Two frames in, the solid core of the disc covers x >= 160 across this band while
    # the outgoing clip still shows at the left edge.
    covered = region(range(160, 540))
    assert max(covered) <= 8, f"{sum(1 for v in covered if v > 8)} pixels leak through the disc"
    assert sum(region(range(0, 40))) / (40 * 360) > 40


def test_disc_sweep_transition_dips_to_black_mid_cut(tmp_path: Path) -> None:
    shorts_target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    src_a = tmp_path / "a.mp4"
    src_b = tmp_path / "b.mp4"
    mix_wav = tmp_path / "mix.wav"
    _synth_video(src_a, duration_s=2.0, color="0xD8D8D8")
    _synth_video(src_b, duration_s=2.0, color="0x9090C8")
    _synth_audio(mix_wav, freq_hz=330, duration_s=3.0)

    def asset(asset_id: str, path: Path, kind: str, dur: float, audio: bool) -> AssetRef:
        return AssetRef(
            asset_id=asset_id,
            sha256=hash_media(path)["sha256"],
            kind=kind,
            path=str(path),
            duration_s=dur,
            has_audio=audio,
        )

    plan = EditPlan(
        schema_version="1.0",
        job_id="disc_sweep_test",
        project_id="proj_disc",
        brand_id="geoverum",
        platform_target_id=shorts_target.platform_id,
        render_strategy="hybrid",
        duration_s=3.0,
        fps=shorts_target.fps,
        width=shorts_target.width,
        height=shorts_target.height,
        assets=[
            asset("va", src_a, "video", 2.0, False),
            asset("vb", src_b, "video", 2.0, False),
            asset("am", mix_wav, "audio_speech", 3.0, True),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="va",
                timeline_start_s=0.0,
                timeline_duration_s=1.5,
                source_start_s=0.0,
                role="a_roll",
                content_type="map",
                reframed_to_target=True,
            ),
            VideoClipOp(
                clip_id="c2",
                asset_id="vb",
                timeline_start_s=1.5,
                timeline_duration_s=1.5,
                source_start_s=0.0,
                role="b_roll",
                content_type="map",
                reframed_to_target=True,
                transition_in="disc_sweep",
            ),
        ],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="mix",
                asset_id="am",
                audio_group="program_mix",
                timeline_start_s=0.0,
                timeline_duration_s=3.0,
                source_start_s=0.0,
                gain_db=0.0,
                cleaned_speech_stem=True,
            )
        ],
        verifier_passed=True,
    )
    out_mp4 = tmp_path / "master_disc.mp4"
    assemble_hybrid_deliverable(plan, shorts_target, out_mp4, encode_preset="veryfast")
    before, _ = _frame_luma(out_mp4, 1.2)
    middle, middle_max = _frame_luma(out_mp4, 1.6)
    after, _ = _frame_luma(out_mp4, 2.3)
    assert before > 170, before
    assert middle < 40, middle
    assert middle_max < 60, f"streaks inside the disc (max luma {middle_max})"
    assert 100 < after < 170, after
    audit = audit_mastered_deliverable(out_mp4, shorts_target, reference_path=out_mp4)
    assert abs(audit.metrics["video_duration_s"] - 3.0) < 0.15


def test_audio_sidechain_pads_vo_and_qc_fails_on_silent_audio(tmp_path: Path) -> None:
    from vedit.mastering.ffmpeg_master import _build_audio_mix_graph
    from vedit.models import AudioTrackOp

    vo = tmp_path / "vo.wav"
    bgm = tmp_path / "bgm.wav"
    vo.write_bytes(b"")
    bgm.write_bytes(b"")
    plan = EditPlan(
        job_id="sidechain_pad_test",
        project_id="proj",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=10.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(asset_id="vo", sha256="a" * 64, kind="audio_speech", path=str(vo)),
            AssetRef(asset_id="bgm", sha256="b" * 64, kind="audio_bgm", path=str(bgm)),
        ],
        video_tracks=[],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="t_vo",
                asset_id="vo",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=4.0,
                source_start_s=0.0,
                cleaned_speech_stem=True,
            ),
            AudioTrackOp(
                track_id="t_bgm",
                asset_id="bgm",
                audio_group="music",
                timeline_start_s=0.0,
                timeline_duration_s=10.0,
                source_start_s=0.0,
                carve_against_group="voiceover",
                carve_strength=0.75,
            ),
        ],
    )
    _, graph, _ = _build_audio_mix_graph(plan, {"vo": vo, "bgm": bgm})
    assert "[vo_sc_raw]apad,atrim=0:10.0000[vo_sc]" in graph

    # Silent audio deliverable (-inf LUFS) must fail QC audit rather than pass
    silent_mp4 = tmp_path / "silent.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#0A2332:s=1080x1920:r=30:d=1.0",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo:d=1.0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(silent_mp4),
        ],
        check=True,
    )
    shorts_target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    audit = audit_mastered_deliverable(silent_mp4, shorts_target, check_visual=False)
    assert audit.passed is False
    assert audit.metrics.get("true_peak_dbtp") is None
    assert {"SILENT_AUDIO_STREAM", "LOUDNESS_OUT_OF_TOLERANCE"} & {e.code for e in audit.errors}


def test_ass_captions_null_fade_and_variables_override_plus_square_disc_sweep(
    tmp_path: Path,
) -> None:
    from vedit.mastering.ass_captions import is_ass_fastpath_overlay, write_ass_overlays_file

    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    cap_chip = OverlayCompositionOp(
        overlay_id="cap_chip",
        kind="caption_rail",
        template_id="caption_rail",
        timeline_start_s=0.0,
        timeline_duration_s=1.0,
        transparent=True,
        safe_band="lower_third",
        props={"text": "Base", "caption_style": "plain"},
        variables={"caption_style": "chip"},
    )
    assert is_ass_fastpath_overlay(cap_chip) is False

    cap_null = OverlayCompositionOp(
        overlay_id="cap_null",
        kind="caption_rail",
        template_id="caption_rail",
        timeline_start_s=0.0,
        timeline_duration_s=1.0,
        transparent=True,
        safe_band="lower_third",
        props={
            "text": "Hello",
            "caption_style": "plain",
            "caption_transition_ms": None,
            "caption_fade_in_ms": None,
            "caption_fade_out_ms": 0,
        },
        variables={"text": "World", "caption_fade_in_ms": None},
    )
    ass_path = write_ass_overlays_file([cap_null], target, tmp_path / "null_fade.ass")
    ass_text = ass_path.read_text(encoding="utf-8")
    assert "World" in ass_text
    assert "\\fad(120,0)" in ass_text

    # 1:1 square deliverable must reach full black at the middle frame of disc_sweep
    sq_frames = _disc_sweep_frames("color=c=white", "108x108", (15, 15))
    black_frac = sum(1 for v in sq_frames[0] if v < 128) / (108 * 108)
    assert black_frac == pytest.approx(1.0, abs=0.005)


def test_single_pass_mastering_with_external_captions_ass_and_source_credit_style(
    tmp_path: Path,
) -> None:
    from vedit.mastering.ass_captions import write_ass_overlays_file

    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    credit = OverlayCompositionOp(
        overlay_id="ov_credit",
        kind="lower_third",
        template_id="source_credit",
        timeline_start_s=0.0,
        timeline_duration_s=1.5,
        transparent=True,
        safe_band="upper_safe",
        variables={"text": "Imagery: Open Earth Archive", "opacity": 0.8},
        props={},
    )
    ov_ass = write_ass_overlays_file([credit], target, tmp_path / "ov.ass").read_text(
        encoding="utf-8"
    )
    assert "Style: SourceCredit," in ov_ass
    assert ",1,1.6,1.8,7," in ov_ass

    src_video = tmp_path / "clip.mp4"
    _synth_video(src_video, duration_s=1.5)
    v_hash = hash_media(src_video)["sha256"]
    cap_ass = tmp_path / "captions.ass"
    cap_ass.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Rubik,56,&H00FFFFFF,&H0000FFFF,&H90000000,&HA0000000,"
        "-1,0,0,0,100,100,0,0,1,1.6,3.2,2,60,60,348,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.20,Default,,0,0,0,,Single pass caption test\n",
        encoding="utf-8",
    )
    plan = EditPlan(
        schema_version="1.0",
        job_id="job_1pass",
        project_id="proj_1pass",
        brand_id="geoverum",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=1.2,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[
            AssetRef(
                asset_id="vid_1",
                sha256=v_hash,
                kind="video",
                path=str(src_video),
                duration_s=1.5,
                has_audio=False,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="vid_1",
                timeline_start_s=0.0,
                timeline_duration_s=1.2,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
            )
        ],
        overlay_compositions=[credit],
        audio_tracks=[],
        verifier_passed=True,
    )
    out_mp4 = tmp_path / "onepass.mp4"
    res = assemble_hybrid_deliverable(
        plan,
        target,
        out_mp4,
        captions_ass_path=cap_ass,
        encode_preset="ultrafast",
    )
    assert res.output_path.is_file()
    qc = audit_mastered_deliverable(out_mp4, target, require_audio=False, check_visual=False)
    assert qc.passed is True, qc.errors


def test_ass_readability_short_chunks_blend_gbrp_sparse_modes_and_fonts_stage(
    tmp_path: Path,
) -> None:
    from vedit.mastering.ass_captions import (
        build_ass_from_transcript,
        validate_ass_captions_readability,
        write_ass_overlays_file,
    )
    from vedit.mastering.ffmpeg_master import _stage_plan_fonts_dir
    from vedit.mastering.sparse_hf import group_sparse_hf_windows

    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])

    # H3: glow layer 0 duplicate must not trigger false overlap warnings in readability audit.
    glow_path = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="c1",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.0,
                timeline_duration_s=1.8,
                transparent=True,
                safe_band="lower_third",
                props={
                    "text": "Clean glow caption",
                    "caption_glow_color": "#F5C542",
                    "caption_glow_px": 10,
                },
            )
        ],
        target,
        tmp_path / "glow_audit.ass",
    )
    assert validate_ass_captions_readability(glow_path.read_text(encoding="utf-8")) == []

    # H4: short multi-chunk segment must never emit 0.00s cue, and overlapping segments clamp.
    ass_short = build_ass_from_transcript(
        [
            {"start": 0.0, "end": 0.35, "text": "one two three four five six seven eight nine"},
            {"start": 0.25, "end": 1.4, "text": "overlapping follow up"},
        ],
        max_words=3,
    )
    dialogues = [ln for ln in ass_short.splitlines() if ln.startswith("Dialogue:")]
    assert len(dialogues) >= 4
    for ln in dialogues:
        parts = ln.split(",", 9)
        assert parts[1] != parts[2], f"Zero-duration cue emitted: {ln}"
    assert not any("overlaps" in w for w in validate_ass_captions_readability(ass_short))

    # H5: caption_transition_ms=0 (with fade_out_ms unset) must still apply caption_gap_ms.
    gap_path = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="g1",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="lower_third",
                props={"text": "First cue", "caption_transition_ms": 0, "caption_gap_ms": 100},
            ),
            OverlayCompositionOp(
                overlay_id="g2",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=1.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="lower_third",
                props={"text": "Second cue", "caption_transition_ms": 0, "caption_gap_ms": 100},
            ),
        ],
        target,
        tmp_path / "gap.ass",
    )
    gap_lines = [
        ln for ln in gap_path.read_text(encoding="utf-8").splitlines() if ln.startswith("Dialogue:")
    ]
    assert "0:00:00.90" in gap_lines[0]

    # Section 3.4: empty broadcast_bug text must not hardcode a brand name.
    bug_path = write_ass_overlays_file(
        [
            OverlayCompositionOp(
                overlay_id="bug_empty",
                kind="lower_third",
                template_id="broadcast_bug",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="upper_safe",
                props={"text": ""},
            )
        ],
        target,
        tmp_path / "bug_empty.ass",
    )
    assert "geoverum" not in bug_path.read_text(encoding="utf-8").lower()

    # M3: group_sparse_hf_windows must not merge overlays with different blend_mode.
    base_plan = EditPlan(
        job_id="blend_split",
        project_id="p_blend",
        brand_id="geoverum",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=10.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[],
        video_tracks=[],
        overlay_compositions=[],
        audio_tracks=[],
    )
    win_split = group_sparse_hf_windows(
        base_plan,
        [
            OverlayCompositionOp(
                overlay_id="ov_norm",
                kind="data_card",
                timeline_start_s=1.0,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="upper_safe",
                blend_mode="normal",
            ),
            OverlayCompositionOp(
                overlay_id="ov_scr",
                kind="data_card",
                timeline_start_s=2.1,
                timeline_duration_s=1.0,
                transparent=True,
                safe_band="upper_safe",
                blend_mode="screen",
            ),
        ],
    )
    assert len(win_split) == 2

    # H2: extra_fonts_dir must respect variable-font exclusion when static weight exists.
    extra_f = tmp_path / "extra_fonts"
    extra_f.mkdir()
    (extra_f / "TestFam-Bold.ttf").write_bytes(b"static")
    (extra_f / "TestFam-Variable.ttf").write_bytes(b"var")
    staged_dir = _stage_plan_fonts_dir(base_plan, tmp_path / "staged_f", extra_fonts_dir=extra_f)
    assert staged_dir is not None
    assert (staged_dir / "TestFam-Bold.ttf").is_file()
    assert not (staged_dir / "TestFam-Variable.ttf").exists()

    # H1: screen blend mode must run in planar RGB (gbrp), not YUV (yuva420p).
    black_base = tmp_path / "black.mp4"
    green_ov = tmp_path / "green.mov"
    _synth_video(black_base, duration_s=1.0, color="0x000000")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x00FF00:s=1080x1920:r=30:d=1.0",
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            str(green_ov),
        ],
        capture_output=True,
        check=True,
    )
    blend_plan = base_plan.model_copy(
        update={
            "duration_s": 1.0,
            "assets": [
                AssetRef(
                    asset_id="vb",
                    sha256=hash_media(black_base)["sha256"],
                    kind="video",
                    path=str(black_base),
                    duration_s=1.0,
                )
            ],
            "video_tracks": [
                VideoClipOp(
                    clip_id="cb",
                    asset_id="vb",
                    timeline_start_s=0.0,
                    timeline_duration_s=1.0,
                    source_start_s=0.0,
                    role="a_roll",
                    reframed_to_target=True,
                )
            ],
        }
    )
    blended_mp4 = tmp_path / "blended_screen.mp4"
    assemble_hybrid_deliverable(
        blend_plan,
        target,
        blended_mp4,
        overlay_segments=[(0.0, 1.0, green_ov)],
        overlay_blend_modes=["screen"],
        use_ass_fastpath=False,
        encode_preset="ultrafast",
    )
    raw_px = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(blended_mp4),
            "-vf",
            "scale=1:1",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    r, g, b = raw_px[0], raw_px[1], raw_px[2]
    assert g > 200 and r < 20 and b < 20, (
        f"Expected pure green from screen blend, got RGB={(r, g, b)}"
    )
