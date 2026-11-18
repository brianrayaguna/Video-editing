"""Deterministic FFmpeg hybrid video assembly and two-pass EBU R128 audio mastering."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vedit.models import AudioTrackOp, EditPlan, PlatformTarget

_LOUDNORM_JSON_RE = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


class MasteringError(RuntimeError):
    """Raised when FFmpeg mastering or deliverable assembly fails."""


@dataclass(slots=True)
class LoudnormMeasurement:
    input_i: str
    input_tp: str
    input_lra: str
    input_thresh: str
    target_offset: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MasteredAudioResult:
    output_path: Path
    two_pass: bool
    measurement: LoudnormMeasurement | None
    target_lufs: float
    target_tp_dbtp: float


@dataclass(slots=True)
class HybridDeliverableResult:
    output_path: Path
    audio_master: MasteredAudioResult | None
    used_overlay_video: bool
    width: int
    height: int
    fps: float


def _parse_loudnorm_json(stderr_text: str) -> LoudnormMeasurement | None:
    match = _LOUDNORM_JSON_RE.search(stderr_text)
    if not match:
        return None
    data = json.loads(match.group(0))
    return LoudnormMeasurement(
        input_i=str(data.get("input_i", "-inf")),
        input_tp=str(data.get("input_tp", "-inf")),
        input_lra=str(data.get("input_lra", "0.0")),
        input_thresh=str(data.get("input_thresh", "-70.0")),
        target_offset=str(data.get("target_offset", "0.0")),
        raw=data,
    )


def _build_track_chain(
    input_index: int,
    track: AudioTrackOp,
    label: str,
) -> str:
    delay_ms = max(0, round(track.timeline_start_s * 1000))
    parts = [
        f"atrim=start={track.source_start_s:.4f}:duration={track.timeline_duration_s:.4f}",
        "asetpts=PTS-STARTPTS",
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
        f"volume={track.gain_db:.2f}dB",
    ]
    if delay_ms > 0:
        parts.append(f"adelay={delay_ms}|{delay_ms}")
    return f"[{input_index}:a]{','.join(parts)}[{label}]"


def _build_audio_mix_graph(
    plan: EditPlan,
    assets_by_id: dict[str, Path],
) -> tuple[list[str], str, str]:
    """Build FFmpeg inputs and filter_complex producing `[mixed_a]` at 48 kHz stereo."""
    input_args: list[str] = []
    chains: list[str] = []
    vo_labels: list[str] = []
    bgm_labels: list[str] = []
    sfx_labels: list[str] = []
    carve_strength = 0.75

    for idx, track in enumerate(plan.audio_tracks):
        src_path = assets_by_id.get(track.asset_id)
        if src_path is None or not src_path.is_file():
            raise MasteringError(
                f"Missing audio asset on disk for track {track.track_id}: {src_path}"
            )
        input_args.extend(["-i", str(src_path)])
        label = f"trk_{idx}"
        chains.append(_build_track_chain(idx, track, label))
        if track.audio_group == "voiceover":
            vo_labels.append(f"[{label}]")
        elif track.audio_group == "music":
            bgm_labels.append(f"[{label}]")
            if track.carve_against_group == "voiceover":
                carve_strength = max(carve_strength, track.carve_strength)
        else:
            sfx_labels.append(f"[{label}]")

    mix_inputs: list[str] = []
    if vo_labels:
        if len(vo_labels) == 1:
            chains.append(f"{vo_labels[0]}acopy[vo_bus]")
        else:
            chains.append(
                f"{''.join(vo_labels)}amix=inputs={len(vo_labels)}:duration=longest:normalize=0[vo_bus]"
            )
        # Split voiceover into dry mix branch + sidechain trigger when ducking music.
        if bgm_labels:
            chains.append("[vo_bus]asplit=2[vo_mix][vo_sc]")
            mix_inputs.append("[vo_mix]")
        else:
            mix_inputs.append("[vo_bus]")

    if bgm_labels:
        if len(bgm_labels) == 1:
            chains.append(f"{bgm_labels[0]}acopy[bgm_raw]")
        else:
            chains.append(
                f"{''.join(bgm_labels)}amix=inputs={len(bgm_labels)}:duration=longest:normalize=0[bgm_raw]"
            )
        if vo_labels:
            ratio = round(2.0 + carve_strength * 6.0, 2)
            eq_cut = round(-2.5 * carve_strength, 2)
            chains.append(
                f"[bgm_raw]equalizer=f=2200:t=o:w=1.2:g={eq_cut}[bgm_eq];"
                f"[bgm_eq][vo_sc]sidechaincompress=threshold=0.025:ratio={ratio}"
                ":attack=20:release=260:makeup=1[bgm_bus]"
            )
        else:
            chains.append("[bgm_raw]acopy[bgm_bus]")
        mix_inputs.append("[bgm_bus]")

    if sfx_labels:
        if len(sfx_labels) == 1:
            mix_inputs.append(sfx_labels[0])
        else:
            chains.append(
                f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:duration=longest:normalize=0[sfx_bus]"
            )
            mix_inputs.append("[sfx_bus]")

    if len(mix_inputs) == 1:
        chains.append(
            f"{mix_inputs[0]}apad,atrim=0:{plan.duration_s:.4f}[mixed_a]"
        )
    else:
        chains.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:normalize=0,"
            f"apad,atrim=0:{plan.duration_s:.4f}[mixed_a]"
        )
    return input_args, ";".join(chains), "[mixed_a]"


def master_audio_mix(
    plan: EditPlan,
    platform_target: PlatformTarget,
    output_audio_path: Path,
) -> MasteredAudioResult:
    """Mix voiceover, carved music, and SFX, then run two-pass FFmpeg `loudnorm`."""
    if not plan.audio_tracks:
        raise MasteringError("Cannot master audio: EditPlan has no audio_tracks.")

    assets_by_id = {asset.asset_id: Path(asset.path) for asset in plan.assets}
    input_args, graph, mixed_label = _build_audio_mix_graph(plan, assets_by_id)
    audio_spec = platform_target.audio
    target_i = audio_spec.target_lufs
    # Leave a small 0.15 dBTP headroom guard for lossy AAC encoding overshoot.
    target_tp = round(min(audio_spec.max_true_peak_dbtp - 0.15, -1.05), 2)
    target_lra = audio_spec.target_lra

    with tempfile.TemporaryDirectory(prefix="vedit_audio_mix_") as tmp_dir:
        pre_wav = Path(tmp_dir) / "pre_norm.wav"
        mix_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *input_args,
            "-filter_complex",
            graph,
            "-map",
            mixed_label,
            "-ar",
            str(audio_spec.sample_rate_hz),
            "-ac",
            str(audio_spec.channels),
            "-c:a",
            "pcm_f32le",
            str(pre_wav),
        ]
        mix_proc = subprocess.run(mix_cmd, capture_output=True, text=True, check=False)
        if mix_proc.returncode != 0:
            raise MasteringError(f"Audio stem mix failed: {mix_proc.stderr}")

        pass1_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(pre_wav),
            "-af",
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
            "-f",
            "null",
            "-",
        ]
        p1_proc = subprocess.run(pass1_cmd, capture_output=True, text=True, check=False)
        if p1_proc.returncode != 0:
            raise MasteringError(f"Audio loudnorm pass 1 failed: {p1_proc.stderr}")

        measurement = _parse_loudnorm_json(p1_proc.stderr)
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        can_two_pass = (
            measurement is not None
            and measurement.input_i != "-inf"
            and measurement.input_tp != "-inf"
        )
        af_pass2 = (
            (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                f"measured_I={measurement.input_i}:measured_TP={measurement.input_tp}:"
                f"measured_LRA={measurement.input_lra}:measured_thresh={measurement.input_thresh}:"
                f"offset={measurement.target_offset}:linear=true:print_format=summary"
            )
            if can_two_pass and measurement is not None
            else f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        )

        ext = output_audio_path.suffix.lower()
        codec_args = (
            ["-c:a", "pcm_s24le"]
            if ext == ".wav"
            else ["-c:a", "aac", "-b:a", f"{audio_spec.bitrate_kbps}k"]
        )
        pass2_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(pre_wav),
            "-af",
            af_pass2,
            "-ar",
            str(audio_spec.sample_rate_hz),
            "-ac",
            str(audio_spec.channels),
            *codec_args,
            str(output_audio_path),
        ]
        p2_proc = subprocess.run(pass2_cmd, capture_output=True, text=True, check=False)
        if p2_proc.returncode != 0:
            raise MasteringError(f"Audio loudnorm pass 2 failed: {p2_proc.stderr}")

    return MasteredAudioResult(
        output_path=output_audio_path,
        two_pass=can_two_pass,
        measurement=measurement,
        target_lufs=target_i,
        target_tp_dbtp=target_tp,
    )


def assemble_hybrid_deliverable(
    plan: EditPlan,
    platform_target: PlatformTarget,
    output_path: Path,
    *,
    overlay_video_path: Path | None = None,
    mastered_audio_path: Path | None = None,
) -> HybridDeliverableResult:
    """Assemble base cuts, optional transparent overlay, and two-pass mastered audio."""
    if not plan.video_tracks:
        raise MasteringError("EditPlan requires at least one video clip in video_tracks.")

    assets_by_id = {asset.asset_id: Path(asset.path) for asset in plan.assets}
    width = platform_target.width
    height = platform_target.height
    fps = platform_target.fps
    gop_frames = max(1, round(fps * platform_target.video.gop_seconds))

    input_args: list[str] = []
    chains: list[str] = []
    concat_inputs: list[str] = []

    ordered_clips = sorted(plan.video_tracks, key=lambda c: c.timeline_start_s)
    for idx, clip in enumerate(ordered_clips):
        src = assets_by_id.get(clip.asset_id)
        if src is None or not src.is_file():
            raise MasteringError(f"Missing video asset for clip {clip.clip_id}: {src}")
        input_args.extend(["-i", str(src)])
        lbl = f"vclip_{idx}"
        vf = (
            f"trim=start={clip.source_start_s:.4f}:duration={clip.timeline_duration_s:.4f},"
            "setpts=PTS-STARTPTS,"
            f"fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height},"
            "setsar=1,format=yuv420p"
        )
        chains.append(f"[{idx}:v]{vf}[{lbl}]")
        concat_inputs.append(f"[{lbl}]")

    if len(concat_inputs) == 1:
        chains.append(f"{concat_inputs[0]}copy[v_base]")
    else:
        chains.append(f"{''.join(concat_inputs)}concat=n={len(concat_inputs)}:v=1:a=0[v_base]")

    final_v_label = "[v_base]"
    used_overlay = False
    if overlay_video_path is not None:
        if not overlay_video_path.is_file():
            raise MasteringError(f"Overlay video not found: {overlay_video_path}")
        ov_idx = len(ordered_clips)
        input_args.extend(["-i", str(overlay_video_path)])
        chains.append(
            f"[{ov_idx}:v]fps={fps},scale={width}:{height}[v_ov];"
            "[v_base][v_ov]overlay=0:0:shortest=1:eof_action=pass,format=yuv420p[v_comp]"
        )
        final_v_label = "[v_comp]"
        used_overlay = True

    vspec = platform_target.video
    chains.append(
        f"{final_v_label}setparams=colorspace={vspec.color_space}:"
        f"color_primaries={vspec.color_primaries}:color_trc={vspec.color_trc}:"
        "range=tv[v_tagged]"
    )
    final_v_label = "[v_tagged]"

    audio_result: MasteredAudioResult | None = None
    with tempfile.TemporaryDirectory(prefix="vedit_master_") as tmp_dir:
        resolved_audio: Path | None = mastered_audio_path
        if resolved_audio is None and plan.audio_tracks:
            resolved_audio = Path(tmp_dir) / "master_audio.wav"
            audio_result = master_audio_mix(plan, platform_target, resolved_audio)

        map_args = ["-map", final_v_label]
        audio_encode_args: list[str] = ["-an"]
        if resolved_audio is not None:
            audio_idx = len(ordered_clips) + (1 if used_overlay else 0)
            input_args.extend(["-i", str(resolved_audio)])
            map_args.extend(["-map", f"{audio_idx}:a"])
            audio_encode_args = [
                "-c:a",
                "aac",
                "-b:a",
                f"{platform_target.audio.bitrate_kbps}k",
                "-ar",
                str(platform_target.audio.sample_rate_hz),
                "-ac",
                str(platform_target.audio.channels),
            ]

        target_bps = f"{vspec.target_bitrate_mbps}M"
        max_bps = f"{vspec.max_bitrate_mbps}M"
        buf_bps = f"{round(vspec.max_bitrate_mbps * 2.0, 2)}M"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *input_args,
            "-filter_complex",
            ";".join(chains),
            *map_args,
            "-c:v",
            "libx264",
            "-profile:v",
            vspec.profile,
            "-pix_fmt",
            vspec.pixel_format,
            "-r",
            str(fps),
            "-fps_mode",
            "cfr",
            "-g",
            str(gop_frames),
            "-keyint_min",
            str(gop_frames),
            "-sc_threshold",
            "0",
            "-b:v",
            target_bps,
            "-maxrate",
            max_bps,
            "-bufsize",
            buf_bps,
            "-colorspace",
            vspec.color_space,
            "-color_primaries",
            vspec.color_primaries,
            "-color_trc",
            vspec.color_trc,
            "-color_range",
            "tv",
            "-movflags",
            "+faststart",
            *audio_encode_args,
            "-t",
            f"{plan.duration_s:.4f}",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise MasteringError(f"Hybrid deliverable encode failed: {proc.stderr}")

    return HybridDeliverableResult(
        output_path=output_path,
        audio_master=audio_result,
        used_overlay_video=used_overlay,
        width=width,
        height=height,
        fps=fps,
    )
