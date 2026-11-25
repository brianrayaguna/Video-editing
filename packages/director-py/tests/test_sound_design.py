"""Tests for procedural sound design, 6-bus mixing, two-pass geo mix-audio, and audio QC."""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

from typer.testing import CliRunner

from vedit.analyzers.media_probe import hash_media
from vedit.cli import app
from vedit.contracts import load_platform_targets
from vedit.mastering.ffmpeg_master import master_audio_mix
from vedit.mastering.qc_audit import audit_mastered_deliverable, measure_mono_phase_correlation
from vedit.mastering.sound_design import (
    LOUDNESS_PROFILES,
    plan_narrative_audio_cues,
    resolve_loudness_profile,
    synthesize_four_layer_impact,
    synthesize_narrative_bgm,
    synthesize_room_tone_bed,
    synthesize_shepard_riser,
    synthesize_tension_drone,
)
from vedit.models import AssetRef, AudioTrackOp, EditPlan, PlatformTarget, VideoClipOp


def _synth_tone(path: Path, freq_hz: int, duration_s: float = 2.0, amp: float = 0.25) -> None:
    proc = subprocess.run(
        [
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
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)


def _synth_video_with_audio(
    path: Path, duration_s: float = 2.0, invert_right: bool = False
) -> None:
    af = "pan=stereo|c0=c0|c1=-1*c0" if invert_right else "anull"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x102030:s=1080x1920:r=30:d={duration_s}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration_s}",
            "-af",
            f"volume=0.25,{af}",
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
            "-color_range",
            "tv",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
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


def test_procedural_synthesis_and_silence_dropout(tmp_path: Path) -> None:
    riser = synthesize_shepard_riser(1.0, tmp_path / "riser.wav")
    drone = synthesize_tension_drone(1.0, tmp_path / "drone.wav")
    impact = synthesize_four_layer_impact(tmp_path / "impact.wav", character="verdict")
    room = synthesize_room_tone_bed(1.0, tmp_path / "room.wav")
    bgm = synthesize_narrative_bgm(
        3.0,
        tmp_path / "bgm.wav",
        section_timeline=[
            {"start_s": 0.0, "end_s": 1.2, "section": "setup"},
            {"start_s": 1.2, "end_s": 2.2, "section": "escalation"},
            {"start_s": 2.2, "end_s": 3.0, "section": "climax"},
        ],
        silence_dropouts=[(1.95, 2.2)],
    )
    for wav_p in (riser, drone, impact, room, bgm):
        assert wav_p.is_file() and wav_p.stat().st_size > 1000
        with wave.open(str(wav_p), "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getframerate() == 48000

    # Verify silence dropout window [2.00s..2.15s] is near-zero inside bgm.wav.
    with wave.open(str(bgm), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    import array

    pcm = array.array("h")
    pcm.frombytes(frames)
    s0 = int(2.00 * 48000) * 2
    s1 = int(2.15 * 48000) * 2
    peak_in_drop = max(abs(x) for x in pcm[s0:s1])
    assert peak_in_drop <= 5


def test_loudness_profiles_and_narrative_cue_planning() -> None:
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    assert set(LOUDNESS_PROFILES) == {
        "streaming_web",
        "podcast_video",
        "broadcast_ebu_r128",
        "broadcast_atsc_a85",
        "cinema_streaming_dialogue",
        "cinema_trailer",
    }
    lufs, tp, lra, tol = resolve_loudness_profile("broadcast_ebu_r128", target)
    assert lufs == -23.0 and tp == -1.0 and lra == 10.0 and tol == 0.5

    cues = plan_narrative_audio_cues(
        {
            "acts": [
                {
                    "duration_s": 4.0,
                    "camera_keyframes": [{"t": 2.0, "curve": "snap_dive"}],
                    "layers": [{"type": "void_wipe", "start_s": 2.8}],
                }
            ]
        },
        storyboard={
            "beats": [
                {"beat_id": "b1", "start_s": 0.0, "end_s": 1.5, "function": "hook"},
                {
                    "beat_id": "b2",
                    "start_s": 2.0,
                    "end_s": 3.5,
                    "function": "climax",
                    "sound_cue": {"function": "drone"},
                },
            ]
        },
    )
    assert len(cues["risers"]) >= 1
    assert len(cues["drones"]) == 1
    assert len(cues["silence_dropouts"]) >= 1


def test_six_bus_audio_mastering_and_mono_phase_qc(tmp_path: Path) -> None:
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    vo_wav = tmp_path / "vo.wav"
    bgm_wav = tmp_path / "bgm.wav"
    amb_wav = tmp_path / "amb.wav"
    room_wav = tmp_path / "room.wav"
    sfx_wav = tmp_path / "sfx.wav"
    _synth_tone(vo_wav, 320, duration_s=2.5, amp=0.35)
    synthesize_narrative_bgm(2.5, bgm_wav)
    _synth_tone(amb_wav, 180, duration_s=2.5, amp=0.10)
    synthesize_room_tone_bed(2.5, room_wav)
    synthesize_four_layer_impact(sfx_wav)

    def _asset(aid: str, p: Path, kind: str) -> AssetRef:
        return AssetRef(
            asset_id=aid,
            sha256=hash_media(p)["sha256"],
            kind=kind,  # type: ignore[arg-type]
            path=str(p),
            duration_s=2.5,
            has_audio=True,
        )

    plan = EditPlan(
        schema_version="1.0",
        job_id="job_sound_01",
        project_id="proj_sound",
        brand_id="geoverum",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=2.5,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[
            _asset("a_vo", vo_wav, "audio_speech"),
            _asset("a_bgm", bgm_wav, "audio_bgm"),
            _asset("a_amb", amb_wav, "audio_ambience"),
            _asset("a_room", room_wav, "audio_ambience"),
            _asset("a_sfx", sfx_wav, "audio_sfx"),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="a_vo",
                timeline_start_s=0.0,
                timeline_duration_s=2.5,
                source_start_s=0.0,
                role="a_roll",
            )
        ],
        overlay_compositions=[],
        audio_tracks=[
            AudioTrackOp(
                track_id="t_vo",
                asset_id="a_vo",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=2.5,
                source_start_s=0.0,
                cleaned_speech_stem=True,
            ),
            AudioTrackOp(
                track_id="t_bgm",
                asset_id="a_bgm",
                audio_group="music",
                timeline_start_s=0.0,
                timeline_duration_s=2.5,
                source_start_s=0.0,
                gain_db=-14.0,
                carve_against_group="voiceover",
                carve_strength=0.9,
            ),
            AudioTrackOp(
                track_id="t_amb",
                asset_id="a_amb",
                audio_group="ambience",
                timeline_start_s=0.0,
                timeline_duration_s=2.5,
                source_start_s=0.0,
                gain_db=-18.0,
                carve_against_group="voiceover",
                carve_strength=0.5,
                pan=0.25,
                reverb_preset="close",
            ),
            AudioTrackOp(
                track_id="t_room",
                asset_id="a_room",
                audio_group="room_tone",
                timeline_start_s=0.0,
                timeline_duration_s=2.5,
                source_start_s=0.0,
                gain_db=-6.0,
            ),
            AudioTrackOp(
                track_id="t_sfx",
                asset_id="a_sfx",
                audio_group="sfx",
                timeline_start_s=0.8,
                timeline_duration_s=0.9,
                source_start_s=0.0,
                gain_db=-8.0,
                layer_role="body",
                diegetic=False,
                pan=-0.2,
                reverb_preset="medium",
                fade_in_s=0.01,
                fade_out_s=0.1,
            ),
        ],
        verifier_passed=True,
    )
    out_wav = tmp_path / "mastered.wav"
    res = master_audio_mix(
        plan, target, out_wav, loudness_profile="streaming_web", speech_wpm=185.0
    )
    assert res.output_path.is_file()
    assert res.two_pass is True
    assert measure_mono_phase_correlation(out_wav) >= 0.5

    # Out-of-phase stereo video should be caught by QC audit.
    bad_mp4 = tmp_path / "inverted_phase.mp4"
    _synth_video_with_audio(bad_mp4, duration_s=1.5, invert_right=True)
    qc = audit_mastered_deliverable(bad_mp4, target, check_visual=False)
    warn_codes = {w.code for w in qc.warnings}
    assert "LOW_MONO_PHASE_CORRELATION" in warn_codes
    assert qc.metrics["mono_phase_correlation"] < 0.0


def test_cli_geo_mix_audio_two_pass(tmp_path: Path) -> None:
    vo = tmp_path / "vo.wav"
    _synth_tone(vo, 260, duration_s=2.4, amp=0.35)
    scene = tmp_path / "scene.json"
    scene.write_text(
        json.dumps(
            {
                "acts": [
                    {
                        "duration_s": 2.4,
                        "camera_keyframes": [{"t": 1.2, "curve": "snap_dive"}],
                        "layers": [{"type": "void_wipe", "start_s": 1.4}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out_wav = tmp_path / "mix.wav"
    res = CliRunner().invoke(
        app,
        [
            "geo",
            "mix-audio",
            "--scene-file",
            str(scene),
            "--voice",
            str(vo),
            "-o",
            str(out_wav),
        ],
    )
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["ok"] is True
    assert payload["two_pass_loudnorm"] is True
    assert payload["riser_count"] >= 1
    assert out_wav.is_file()
