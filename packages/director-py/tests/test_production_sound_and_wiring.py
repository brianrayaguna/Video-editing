"""Tests for production sound QC, extended synthesis/psychoacoustics, and pipeline wiring."""

from __future__ import annotations

import array
import json
import math
import subprocess
import wave
from pathlib import Path

from typer.testing import CliRunner

from vedit.cli import app
from vedit.contracts import find_repo_root, load_brand_template_catalog, load_platform_targets
from vedit.director.planner import build_edit_plan
from vedit.mastering.ass_captions import write_ass_overlays_file
from vedit.mastering.ffmpeg_master import (
    _derive_split_edit_audio_tracks,
    assemble_hybrid_deliverable,
    auto_shot_match_plan,
    resolve_segment_blend_modes,
)
from vedit.mastering.qc_audit import audit_mastered_deliverable, audit_production_sound
from vedit.mastering.sound_design import (
    LOUDNESS_PROFILES,
    build_layer_band_filter,
    haas_delay_to_ffmpeg_filter,
    plan_narrative_audio_cues,
    reverb_return_to_ffmpeg_filter,
    synthesize_ambience_layers,
    synthesize_four_layer_impact,
    synthesize_granular_pad,
    synthesize_stinger,
    synthesize_whoosh,
)
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    BrandStylePolicy,
    BrandTemplateCatalog,
    ColorCorrectionSpec,
    ColorGradeSpec,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
    VideoClipOp,
)
from vedit.providers.media_ops.ffmpeg_local import FfmpegMediaOpsProvider


def _make_speech_like_wav(
    path: Path, *, amplitude: float = 0.25, clip: bool = False, rumble: bool = False
) -> Path:
    sr = 48000
    dur = 2.0
    n = int(sr * dur)
    buf = array.array("h", [0] * n)
    for i in range(n):
        t = i / sr
        active = 1.0 if (0.25 <= t <= 0.9 or 1.2 <= t <= 1.8) else 0.015
        sig = amplitude * active * math.sin(2.0 * math.pi * 240.0 * t)
        if rumble:
            sig += 0.45 * math.sin(2.0 * math.pi * 40.0 * t)
        if clip and active > 0.5:
            sig = 1.25 if math.sin(2.0 * math.pi * 240.0 * t) >= 0 else -1.25
        val = max(-1.0, min(1.0, sig))
        buf[i] = int(val * 32767.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf.tobytes())
    return path


def _make_test_video(path: Path, *, color: str = "#183040", dur_s: float = 1.6) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=360x640:r=30:d={dur_s}",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=48000",
            "-t",
            str(dur_s),
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _test_target() -> PlatformTarget:
    base = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    return base.model_copy(update={"width": 360, "height": 640})


def test_worldwide_loudness_profiles_and_synthesizers(tmp_path: Path) -> None:
    assert "broadcast_atsc_a85" in LOUDNESS_PROFILES
    assert LOUDNESS_PROFILES["broadcast_atsc_a85"].target_lufs == -24.0
    assert "cinema_streaming_dialogue" in LOUDNESS_PROFILES
    assert LOUDNESS_PROFILES["cinema_streaming_dialogue"].target_lufs == -27.0

    whoosh = synthesize_whoosh(0.4, tmp_path / "whoosh.wav", direction="in")
    stinger = synthesize_stinger(tmp_path / "stinger.wav", style="twist")
    gran = synthesize_granular_pad(0.8, tmp_path / "gran.wav")
    amb = synthesize_ambience_layers(1.2, tmp_path / "amb.wav", layers=3)
    impact = synthesize_four_layer_impact(tmp_path / "impact.wav")
    for wav_p in (whoosh, stinger, gran, amb, impact):
        assert wav_p.is_file() and wav_p.stat().st_size > 1000

    assert haas_delay_to_ffmpeg_filter(14.0) == "adelay=0|14.0"
    assert haas_delay_to_ffmpeg_filter(None) is None
    rev_panned = reverb_return_to_ffmpeg_filter("close", reverb_pan=-0.5)
    assert rev_panned is not None and "aecho=" in rev_panned and "pan=stereo" in rev_panned

    sfx_track = AudioTrackOp(
        track_id="sfx_1",
        asset_id="a1",
        audio_group="sfx",
        timeline_start_s=0.0,
        timeline_duration_s=1.0,
        source_start_s=0.0,
        layer_role="detail",
        reverb_preset="close",
        reverb_pan=0.4,
        haas_delay_ms=12.0,
    )
    filters = build_layer_band_filter(sfx_track)
    assert any("adelay=0|12.0" in f for f in filters)
    assert any("aecho=" in f for f in filters)


def test_audit_production_sound_and_room_tone_silence_cut(tmp_path: Path) -> None:
    clean_wav = _make_speech_like_wav(tmp_path / "clean.wav", amplitude=0.35)
    clean_rep = audit_production_sound(clean_wav)
    assert clean_rep.estimated_snr_db >= 20.0
    assert not any(w.code == "CLIPPING_DETECTED" for w in clean_rep.warnings)

    clip_wav = _make_speech_like_wav(tmp_path / "clip.wav", amplitude=0.5, clip=True)
    clip_rep = audit_production_sound(clip_wav)
    assert "CLIPPING_DETECTED" in {w.code for w in clip_rep.warnings}

    rumble_wav = _make_speech_like_wav(tmp_path / "rumble.wav", amplitude=0.15, rumble=True)
    rumble_rep = audit_production_sound(rumble_wav)
    assert "WIND_RUMBLE_DETECTED" in {w.code for w in rumble_rep.warnings}

    tight_wav = tmp_path / "tight_room.wav"
    res = FfmpegMediaOpsProvider().remove_silence(
        clean_wav,
        tight_wav,
        threshold_db=-38.0,
        min_silence_s=0.25,
        padding_s=0.05,
        room_tone_db=-48.0,
    )
    assert tight_wav.is_file()
    assert res.metadata["room_tone_db"] == -48.0


def test_geo_mix_audio_wires_impacts_stingers_whooshes_and_room_tone(tmp_path: Path) -> None:
    vo = _make_speech_like_wav(tmp_path / "vo.wav", amplitude=0.35)
    scene = {
        "acts": [
            {
                "duration_s": 2.0,
                "camera_keyframes": [{"t": 1.0, "curve": "snap_dive"}],
                "layers": [{"type": "crimson_x", "start_s": 1.2}],
            }
        ]
    }
    storyboard = {
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.4,
                "end_s": 1.0,
                "function": "hinge",
                "sound_cue": {"function": "stinger"},
            },
            {
                "beat_id": "b2",
                "start_s": 1.2,
                "end_s": 1.8,
                "function": "climax",
                "blocking": {"camera_move": "whip_pan"},
            },
        ]
    }
    cues = plan_narrative_audio_cues(scene, storyboard=storyboard)
    assert cues["impacts"] and cues["stingers"] and cues["whooshes"]

    scene_path = tmp_path / "scene.json"
    sb_path = tmp_path / "sb.json"
    out_wav = tmp_path / "mixed.wav"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    sb_path.write_text(json.dumps(storyboard), encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "geo",
            "mix-audio",
            "--scene-file",
            str(scene_path),
            "--voice",
            str(vo),
            "--storyboard-file",
            str(sb_path),
            "--room-tone",
            "-o",
            str(out_wav),
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["impact_count"] >= 1
    assert data["stinger_count"] >= 1
    assert data["whoosh_count"] >= 1
    assert data["room_tone_enabled"] is True
    assert "cue_clustering_warnings" in data


def test_vo_center_guard_qc_rumble_stereo_clip_dedup_and_alpha_multiply(tmp_path: Path) -> None:
    vo_track = AudioTrackOp(
        track_id="vo_guarded",
        asset_id="a1",
        audio_group="voiceover",
        timeline_start_s=0.0,
        timeline_duration_s=1.0,
        source_start_s=0.0,
        pan=-0.6,
        reverb_preset="medium",
        reverb_pan=0.5,
        haas_delay_ms=14.0,
    )
    vo_filters = build_layer_band_filter(vo_track)
    assert not any("pan=stereo" in f for f in vo_filters)
    assert not any("adelay=" in f for f in vo_filters)

    # Clean 140 Hz voice fundamentals must not falsely trigger WIND_RUMBLE_DETECTED.
    sr = 48000
    n = sr
    voice_140 = tmp_path / "voice_140.wav"
    buf_140 = array.array(
        "h",
        [int(0.3 * math.sin(2.0 * math.pi * 140.0 * i / sr) * 32767.0) for i in range(n)],
    )
    with wave.open(str(voice_140), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf_140.tobytes())
    rep_140 = audit_production_sound(voice_140)
    assert "WIND_RUMBLE_DETECTED" not in {w.code for w in rep_140.warnings}

    # Single-channel stereo clipping (R clips while L is silent) must be caught.
    stereo_clip = tmp_path / "stereo_clip.wav"
    st_buf = array.array("h", [0] * (n * 2))
    for i in range(n):
        st_buf[2 * i] = 0
        st_buf[2 * i + 1] = 32767 if (i // 10) % 2 == 0 else -32767
    with wave.open(str(stereo_clip), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(st_buf.tobytes())
    rep_st = audit_production_sound(stereo_clip)
    assert "CLIPPING_DETECTED" in {w.code for w in rep_st.warnings}

    # Split-edit audio derivation skips clips already covered by vo_main on same asset_id.
    base_vid = _make_test_video(tmp_path / "base_bright.mp4", color="#80B0E0", dur_s=1.0)
    dedup_plan = EditPlan(
        job_id="job_dedup",
        project_id="proj_dedup",
        brand_id="geoverum",
        platform_target_id="test_9x16",
        render_strategy="hybrid",
        duration_s=1.0,
        fps=30,
        width=360,
        height=640,
        assets=[
            AssetRef(
                asset_id="vo_a",
                sha256="d" * 32,
                kind="video",
                path=str(base_vid),
                has_audio=True,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="vo_a",
                timeline_start_s=0.3,
                timeline_duration_s=0.7,
                source_start_s=0.3,
                role="a_roll",
                j_cut_lead_s=0.25,
            )
        ],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="vo_main",
                asset_id="vo_a",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                source_start_s=0.0,
            )
        ],
    )
    assets_map = {a.asset_id: Path(a.path) for a in dedup_plan.assets}
    assert _derive_split_edit_audio_tracks(dedup_plan, assets_map) == []

    # blend_mode="multiply" with transparent alpha preserves bright background border.
    alpha_ov = tmp_path / "ov_alpha.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x00000000:s=360x640:r=30:d=0.6,format=rgba,geq=r=255:g=255:b=255:a='if(gt(X,150)*lt(X,210)*gt(Y,280)*lt(Y,340),255,0)'",
            "-c:v",
            "qtrle",
            str(alpha_ov),
        ],
        check=True,
        capture_output=True,
    )
    mul_plan = dedup_plan.model_copy(
        update={
            "video_tracks": [
                VideoClipOp(
                    clip_id="c1",
                    asset_id="vo_a",
                    timeline_start_s=0.0,
                    timeline_duration_s=1.0,
                    source_start_s=0.0,
                    role="a_roll",
                )
            ],
            "overlay_compositions": [
                OverlayCompositionOp(
                    overlay_id="ov_mul",
                    kind="kinetic_callout",
                    timeline_start_s=0.2,
                    timeline_duration_s=0.6,
                    transparent=True,
                    blend_mode="multiply",
                    props={"headline": "Mul"},
                )
            ],
        }
    )
    mul_out = tmp_path / "mul_master.mp4"
    assemble_hybrid_deliverable(
        mul_plan,
        _test_target(),
        mul_out,
        overlay_segments=[(0.2, 0.8, alpha_ov)],
        auto_shot_match=False,
    )
    # Sample corner pixel (10, 10) at t=0.4s: must remain bright blue (#80B0E0), not darkened black.
    px_res = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            "0.4",
            "-i",
            str(mul_out),
            "-vframes",
            "1",
            "-vf",
            "format=rgb24,crop=2:2:10:10",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    r_px, g_px, b_px = px_res.stdout[:3]
    assert b_px > 180 and g_px > 140 and r_px > 95


def test_blend_mode_auto_resolve_shot_match_and_spectral_qc(tmp_path: Path) -> None:
    clip_a = _make_test_video(tmp_path / "a.mp4", color="#183040", dur_s=1.2)
    clip_b = _make_test_video(tmp_path / "b.mp4", color="#908878", dur_s=1.2)
    seg_vid = _make_test_video(tmp_path / "seg.mp4", color="#FFFFFF", dur_s=0.8)

    plan = EditPlan(
        job_id="job_wire",
        project_id="proj_wire",
        brand_id="geoverum",
        platform_target_id="test_9x16",
        render_strategy="hybrid",
        duration_s=2.4,
        fps=30,
        width=360,
        height=640,
        assets=[
            AssetRef(
                asset_id="va", sha256="a" * 32, kind="video", path=str(clip_a), has_audio=True
            ),
            AssetRef(
                asset_id="vb", sha256="b" * 32, kind="video", path=str(clip_b), has_audio=True
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="va",
                timeline_start_s=0.0,
                timeline_duration_s=1.2,
                source_start_s=0.0,
                role="a_roll",
                color_correction=ColorCorrectionSpec(lift=0.02, gain=-0.02),
            ),
            VideoClipOp(
                clip_id="c2",
                asset_id="vb",
                timeline_start_s=1.2,
                timeline_duration_s=1.2,
                source_start_s=0.0,
                role="b_roll",
            ),
        ],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="ov1",
                kind="kinetic_callout",
                timeline_start_s=0.2,
                timeline_duration_s=0.8,
                transparent=True,
                blend_mode="screen",
                props={"headline": "Test"},
            )
        ],
        audio_tracks=[
            AudioTrackOp(
                track_id="vo",
                asset_id="va",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=2.4,
                source_start_s=0.0,
            )
        ],
    )
    matched = auto_shot_match_plan(plan, {"va": clip_a, "vb": clip_b})
    assert matched.video_tracks[1].color_correction is not None
    assert matched.video_tracks[1].color_correction.exposure_ev < 0.0

    modes = resolve_segment_blend_modes(plan, [(0.2, 1.0, seg_vid)])
    assert modes == ["screen"]

    out_mp4 = tmp_path / "master.mp4"
    assemble_hybrid_deliverable(
        plan,
        _test_target(),
        out_mp4,
        overlay_segments=[(0.2, 1.0, seg_vid)],
        auto_shot_match=True,
    )
    qc = audit_mastered_deliverable(out_mp4, _test_target(), check_visual=False)
    assert qc.passed
    assert "low_to_mid_db" in qc.metrics


def test_cross_commit_caption_ssot_3d_audio_cues_and_single_pass_grade(tmp_path: Path) -> None:
    vid = _make_test_video(tmp_path / "src.mp4", color="#183040", dur_s=2.0)
    repo = find_repo_root()
    policy = BrandStylePolicy.model_validate(
        json.loads(
            (repo / "profiles" / "brands" / "geoverum" / "brand_style_policy.json").read_text(
                encoding="utf-8"
            )
        )
    )
    catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(
            repo / "profiles" / "brands" / "geoverum" / "templates" / "catalog.json"
        )
    )
    shorts = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    probe = MediaProbeResult.model_validate(
        {
            "schema_version": "1.0",
            "path": str(vid),
            "sha256": "e" * 64,
            "file_bytes": vid.stat().st_size,
            "container": {"format_name": "mp4", "duration_s": 2.0},
            "video": {
                "present": True,
                "width": 360,
                "height": 640,
                "fps": 30.0,
                "is_cfr": True,
            },
            "audio": {
                "present": True,
                "sample_rate_hz": 48000,
                "channels": 2,
                "silence_intervals": [],
                "silence_ratio": 0.0,
            },
            "shots": [
                {
                    "shot_index": 0,
                    "start_s": 0.0,
                    "end_s": 2.0,
                    "duration_s": 2.0,
                    "confidence": 0.9,
                }
            ],
            "shot_stats": {
                "count": 1,
                "asl_p25_s": 2.0,
                "asl_p50_s": 2.0,
                "asl_p75_s": 2.0,
                "cuts_per_min": 0.0,
            },
            "visual": {
                "sampled_frames": 2,
                "palette": [],
                "palette_entropy": 0.0,
                "mean_luminance": 60.0,
                "band_luminance": {"upper": 60.0, "center": 60.0, "lower_third": 60.0},
                "mean_sharpness": 100.0,
                "black_intervals": [],
                "keyframes": [],
            },
            "timing_ms": {
                "hash_ms": 1,
                "ffprobe_ms": 5,
                "stream_analyze_ms": 5,
                "total_ms": 11,
            },
        }
    )
    transcript = NormalizedTranscript.model_validate(
        {
            "provider": "mock",
            "source_hash": "f" * 64,
            "language": "en",
            "duration_s": 2.0,
            "text": "Deep cable corridor",
            "words": [
                {"text": "Deep", "start_s": 0.1, "end_s": 0.5, "confidence": 0.99},
                {"text": "cable", "start_s": 0.5, "end_s": 0.9, "confidence": 0.99},
                {"text": "corridor", "start_s": 0.9, "end_s": 1.4, "confidence": 0.99},
            ],
        }
    )
    plan, report = build_edit_plan(
        job_id="job_ssot",
        project_id="proj_ssot",
        probe=probe,
        policy=policy,
        platform_target=shorts,
        transcript=transcript,
        template_catalog=catalog,
    )
    assert report.passed
    cap_ovs = [o for o in plan.overlay_compositions if o.kind == "caption_rail"]
    assert cap_ovs
    assert str(cap_ovs[0].props["caption_font_family"]).startswith("Inter")
    assert cap_ovs[0].props["caption_font_px"] == 46
    assert cap_ovs[0].props["caption_bottom_pct"] == round(525 / 1920.0, 5)

    ass_out = write_ass_overlays_file(cap_ovs, shorts, tmp_path / "ssot_caps.ass")
    ass_txt = ass_out.read_text(encoding="utf-8")
    assert "Style: CaptionLower,Inter,46," in ass_txt
    assert ",525,1\n" in ass_txt

    # Landscape 16:9 Geoverum plan propagates type_scale.caption.size_px_16x9 (42 px).
    yt_16x9 = PlatformTarget.model_validate(load_platform_targets()["youtube_16x9_1080p"])
    plan_16x9, report_16x9 = build_edit_plan(
        job_id="job_ssot_16x9",
        project_id="proj_ssot",
        probe=probe,
        policy=policy,
        platform_target=yt_16x9,
        transcript=transcript,
        template_catalog=catalog,
    )
    assert report_16x9.passed
    cap_16x9 = [o for o in plan_16x9.overlay_compositions if o.kind == "caption_rail"]
    assert cap_16x9
    assert cap_16x9[0].props["caption_font_px"] == 42

    # 3D map layers trigger procedural audio cues cleanly.
    cues_3d = plan_narrative_audio_cues(
        {
            "acts": [
                {
                    "duration_s": 3.0,
                    "layers": [
                        {"type": "cable_3d", "start_s": 0.4},
                        {"type": "model_3d", "start_s": 1.2},
                        {"type": "volume_3d", "start_s": 2.1},
                    ],
                }
            ]
        }
    )
    assert len(cues_3d["impacts"]) == 1
    assert len(cues_3d["whooshes"]) == 2

    # Combined single-pass captions_ass_path + Stage-2 color_grade + podcast_video loudness profile.
    ext_ass = tmp_path / "ext_caps.ass"
    write_ass_overlays_file(cap_ovs, _test_target(), ext_ass)
    graded_plan = EditPlan(
        job_id="job_combo",
        project_id="proj_combo",
        brand_id="geoverum",
        platform_target_id="test_9x16",
        render_strategy="hybrid",
        duration_s=2.0,
        fps=30,
        width=360,
        height=640,
        assets=[
            AssetRef(
                asset_id="v1",
                sha256="a" * 32,
                kind="video",
                path=str(vid),
                has_audio=True,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v1",
                timeline_start_s=0.0,
                timeline_duration_s=2.0,
                source_start_s=0.0,
                role="a_roll",
                color_grade=ColorGradeSpec(preset="cool_investigative", intensity=0.8),
            )
        ],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="vo",
                asset_id="v1",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=2.0,
                source_start_s=0.0,
            )
        ],
    )
    combo_mp4 = tmp_path / "combo.mp4"
    assemble_hybrid_deliverable(
        graded_plan,
        _test_target(),
        combo_mp4,
        captions_ass_path=ext_ass,
        loudness_profile="podcast_video",
        use_ass_fastpath=False,
    )
    combo_qc = audit_mastered_deliverable(
        combo_mp4, _test_target(), check_visual=False, loudness_profile="podcast_video"
    )
    assert combo_qc.passed
