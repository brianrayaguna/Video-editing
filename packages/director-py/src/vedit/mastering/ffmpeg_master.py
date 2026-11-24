"""Deterministic FFmpeg hybrid video assembly and two-pass EBU R128 audio mastering."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import find_repo_root
from vedit.mastering.ass_captions import (
    escape_ffmpeg_filter_path,
    partition_overlays_for_hybrid,
    write_ass_overlays_file,
)
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
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return LoudnormMeasurement(
        input_i=str(data.get("input_i", "-inf")),
        input_tp=str(data.get("input_tp", "-inf")),
        input_lra=str(data.get("input_lra", "0.0")),
        input_thresh=str(data.get("input_thresh", "-70.0")),
        target_offset=str(data.get("target_offset", "0.0")),
        raw=data,
    )


def _is_finite_loudnorm_val(raw: str) -> bool:
    try:
        return math.isfinite(float(raw))
    except (TypeError, ValueError):
        return False


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
    carve_strength: float | None = None

    for idx, track in enumerate(plan.audio_tracks):
        src_path = assets_by_id.get(track.asset_id)
        if src_path is None or not src_path.is_file():
            raise MasteringError(
                f"Missing audio asset on disk for track {track.track_id}: {src_path}"
            )
        input_args.extend(["-i", str(src_path)])
        label = f"trk_{idx}"
        chains.append(_build_track_chain(idx, track, label))
        if track.audio_group in ("voiceover", "program_mix"):
            vo_labels.append(f"[{label}]")
        elif track.audio_group == "music":
            bgm_labels.append(f"[{label}]")
            if track.carve_against_group == "voiceover":
                carve_strength = (
                    track.carve_strength
                    if carve_strength is None
                    else max(carve_strength, track.carve_strength)
                )
        else:
            sfx_labels.append(f"[{label}]")

    should_carve = bool(
        vo_labels and bgm_labels and carve_strength is not None and carve_strength > 0
    )
    effective_carve = carve_strength if carve_strength is not None else 0.0

    mix_inputs: list[str] = []
    if vo_labels:
        if len(vo_labels) == 1:
            chains.append(f"{vo_labels[0]}acopy[vo_bus]")
        else:
            chains.append(
                f"{''.join(vo_labels)}amix=inputs={len(vo_labels)}:duration=longest:normalize=0[vo_bus]"
            )
        # Split VO into dry branch + padded sidechain trigger so BGM never cuts at VO EOF.
        if should_carve:
            chains.append(
                f"[vo_bus]asplit=2[vo_mix][vo_sc_raw];"
                f"[vo_sc_raw]apad,atrim=0:{plan.duration_s:.4f}[vo_sc]"
            )
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
        if should_carve:
            ratio = round(2.0 + effective_carve * 6.0, 2)
            eq_cut = round(-2.5 * effective_carve, 2)
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
        chains.append(f"{mix_inputs[0]}apad,atrim=0:{plan.duration_s:.4f}[mixed_a]")
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
        can_two_pass = measurement is not None and all(
            _is_finite_loudnorm_val(val)
            for val in (
                measurement.input_i,
                measurement.input_tp,
                measurement.input_lra,
                measurement.input_thresh,
                measurement.target_offset,
            )
        )
        if not can_two_pass:
            print(
                "Warning: loudnorm pass-1 measurements non-finite or unavailable; "
                "falling back to single-pass dynamic loudnorm.",
                file=sys.stderr,
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


def _video_codec_args(
    platform_target: PlatformTarget,
    *,
    preset: str = "fast",
    use_hardware_encoder: bool = False,
) -> list[str]:
    vspec = platform_target.video
    fps = platform_target.fps
    gop_frames = max(1, round(fps * vspec.gop_seconds))
    target_mbps = (
        vspec.high_fps_target_bitrate_mbps
        if fps >= 48.0 and vspec.high_fps_target_bitrate_mbps is not None
        else vspec.target_bitrate_mbps
    )
    target_bps = f"{target_mbps}M"
    max_bps = f"{vspec.max_bitrate_mbps}M"
    buf_bps = f"{round(vspec.max_bitrate_mbps * 2.0, 2)}M"

    if vspec.codec == "prores":
        args = [
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4" if vspec.pixel_format == "yuva444p10le" else "3",
            "-pix_fmt",
            vspec.pixel_format,
        ]
    elif vspec.codec == "hevc":
        args = [
            "-c:v",
            "libx265",
            "-preset",
            preset,
            "-pix_fmt",
            vspec.pixel_format,
            "-b:v",
            target_bps,
            "-maxrate",
            max_bps,
            "-bufsize",
            buf_bps,
        ]
    elif use_hardware_encoder and sys.platform == "darwin":
        args = [
            "-c:v",
            "h264_videotoolbox",
            "-profile:v",
            vspec.profile,
            "-pix_fmt",
            vspec.pixel_format,
            "-b:v",
            target_bps,
            "-maxrate",
            max_bps,
            "-bufsize",
            buf_bps,
        ]
    else:
        args = [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-profile:v",
            vspec.profile,
            "-pix_fmt",
            vspec.pixel_format,
            "-b:v",
            target_bps,
            "-maxrate",
            max_bps,
            "-bufsize",
            buf_bps,
            "-sc_threshold",
            "0",
        ]

    args.extend(
        [
            "-r",
            str(fps),
            "-fps_mode",
            "cfr",
            "-g",
            str(gop_frames),
            "-keyint_min",
            str(gop_frames),
            "-colorspace",
            vspec.color_space,
            "-color_primaries",
            vspec.color_primaries,
            "-color_trc",
            vspec.color_trc,
            "-color_range",
            "tv",
        ]
    )
    if vspec.faststart and vspec.container == "mp4":
        args.extend(["-movflags", "+faststart"])
    return args


def _stage_plan_fonts_dir(plan: EditPlan, dest_dir: Path) -> Path | None:
    """Copy plan font assets plus the engine font library into one directory for libass.

    Plan fonts win on filename collisions; the engine library (`assets/geo/fonts`) makes
    brand typefaces resolvable even when a plan declares no font assets.
    """
    copied = 0
    sources: list[Path] = [Path(a.path) for a in plan.assets if a.kind == "font"]
    try:
        library = find_repo_root() / "assets" / "geo" / "fonts"
    except FileNotFoundError:
        library = None
    if library is not None and library.is_dir():
        sources.extend(sorted(p for p in library.iterdir() if p.suffix.lower() in {".ttf", ".otf"}))
    for src in sources:
        if not src.is_file() or (dest_dir / src.name).exists():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_dir / src.name)
        copied += 1
    return dest_dir if copied > 0 else None


# Feathered black disc that crosses the frame right to left at mid-height: ahead of its
# centre the outgoing clip shows, behind it the incoming clip. Radius 0.69 x the long
# side (about 1320 px on a 1920 px frame), feather 12% of the radius; the centre travels
# from W + 1.4 R to -1.25 R, so over six frames the black fraction runs about
# 0.06, 0.72, 1.0, 0.9, 0.21, 0 and the middle frame is fully black. Evaluated in planar
# RGB so black is 0 on every plane. xfade progress P runs from 1 to 0. The expression
# is written without st()/ld() registers: xfade evaluates it from several slice threads
# that share one register set.
_DISC_R = "(max(0.69*max(W,H),1.20*hypot(W/2,H/2)))"
_DISC_CX = f"(P*W+(2.65*P-1.25)*{_DISC_R})"
_DISC_SWEEP_EXPR = (
    f"if(gt(X,{_DISC_CX}),B,A)"
    f"*(1-clip(({_DISC_R}-hypot(X-{_DISC_CX},Y-H/2))/(0.12*{_DISC_R}),0,1))"
)

_XFADE_MAP: dict[str, tuple[str, float, str]] = {
    "clean_crossfade": ("fade", 0.30, ""),
    "clean_fade": ("fade", 0.28, ""),
    "wipe": ("wipeleft", 0.32, ""),
    "wipe_left": ("wipeleft", 0.32, ""),
    "wipe_right": ("wiperight", 0.32, ""),
    "whip_zoom_blur": ("zoomin", 0.20, ""),
    "color_flash": ("fadewhite", 0.18, ""),
    "disc_sweep": (f"custom:expr='{_DISC_SWEEP_EXPR}'", 0.20, "gbrp"),
}


def _xfade_spec(transition: str | None) -> tuple[str, float, str] | None:
    """Return (xfade transition argument, default duration s, input pixel format) or None.

    An empty pixel format leaves format negotiation to FFmpeg; ``None`` means the
    transition is a hard cut.
    """
    return _XFADE_MAP.get((transition or "").lower().strip())


def assemble_hybrid_deliverable(
    plan: EditPlan,
    platform_target: PlatformTarget,
    output_path: Path,
    *,
    overlay_video_path: Path | None = None,
    overlay_segments: list[tuple[float, float, Path]] | None = None,
    mastered_audio_path: Path | None = None,
    use_ass_fastpath: bool = True,
    encode_preset: Literal["ultrafast", "veryfast", "fast", "medium", "slow"] = "fast",
    use_hardware_encoder: bool = False,
) -> HybridDeliverableResult:
    """Assemble base cuts, optional transparent overlay, native libass text, and mastered audio."""
    if not plan.video_tracks:
        raise MasteringError("EditPlan requires at least one video clip in video_tracks.")

    assets_by_id = {asset.asset_id: Path(asset.path) for asset in plan.assets}
    width = platform_target.width
    height = platform_target.height
    fps = platform_target.fps

    input_args: list[str] = []
    chains: list[str] = []
    clip_nodes: list[tuple[str, float, str]] = []
    ordered_clips = sorted(plan.video_tracks, key=lambda c: c.timeline_start_s)
    cursor_s = 0.0
    gap_idx = 0
    for idx, clip in enumerate(ordered_clips):
        src = assets_by_id.get(clip.asset_id)
        if src is None or not src.is_file():
            raise MasteringError(f"Missing video asset for clip {clip.clip_id}: {src}")

        # Preserve timeline alignment when a gap exists before this clip.
        gap_s = round(clip.timeline_start_s - cursor_s, 4)
        if gap_s > 0.02:
            gap_lbl = f"vgap_{gap_idx}"
            gap_idx += 1
            chains.append(
                f"color=c=black:s={width}x{height}:r={fps}:d={gap_s:.4f},format=yuv420p[{gap_lbl}]"
            )
            clip_nodes.append((f"[{gap_lbl}]", gap_s, "hard_cut"))

        input_args.extend(["-i", str(src)])
        lbl = f"vclip_{idx}"
        scale_val = max(1.0, float(clip.scale or 1.0))
        scaled_w = max(width, round(width * scale_val / 2) * 2)
        scaled_h = max(height, round(height * scale_val / 2) * 2)
        vf_parts = [
            f"trim=start={clip.source_start_s:.4f}:duration={clip.timeline_duration_s:.4f}",
            "setpts=PTS-STARTPTS",
            f"fps={fps}",
            f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={width}:{height}",
            "setsar=1",
            "format=yuv420p",
        ]
        trans = (clip.transition_in or "hard_cut").lower().strip()
        if (
            idx == 0
            and trans in ("clean_fade", "clean_crossfade")
            and clip.timeline_duration_s >= 0.4
        ):
            fade_d = min(0.28, round(clip.timeline_duration_s * 0.15, 3))
            vf_parts.append(f"fade=t=in:st=0:d={fade_d:.3f}")
        chains.append(f"[{idx}:v]{','.join(vf_parts)}[{lbl}]")
        clip_nodes.append((f"[{lbl}]", clip.timeline_duration_s, trans))
        cursor_s = clip.timeline_start_s + clip.timeline_duration_s

    if len(clip_nodes) == 1:
        chains.append(f"{clip_nodes[0][0]}copy[v_base]")
    elif any(_xfade_spec(trans) for _, _, trans in clip_nodes[1:]):
        fps_int = max(1, round(fps))
        cur_lbl, cur_dur, _ = clip_nodes[0]
        cur_frames = max(1, round(cur_dur * fps_int))
        for step_idx, (nxt_lbl, nxt_dur, trans) in enumerate(clip_nodes[1:], start=1):
            nxt_frames = max(1, round(nxt_dur * fps_int))
            out_lbl = "[v_base]" if step_idx == len(clip_nodes) - 1 else f"[vx_{step_idx}]"
            spec = _xfade_spec(trans)
            if spec is not None and cur_dur >= 0.35 and nxt_dur >= 0.35:
                xf_name, default_d, xf_fmt = spec
                pre_fmt = f",format={xf_fmt}" if xf_fmt else ""
                d_frames = max(
                    2,
                    min(
                        round(default_d * fps_int),
                        cur_frames // 4,
                        nxt_frames // 4,
                    ),
                )
                d = round(d_frames / fps_int, 4)
                offset_s = round(cur_frames / fps_int, 4)
                # Pad outgoing tail by d_frames (+1 guard frame) with uniform CFR timebase
                # so xfade always overlaps cleanly and preserves exact timeline duration.
                pad_lbl = f"[vpad_{step_idx}]"
                chains.append(
                    f"{cur_lbl}fps={fps_int},setpts=PTS-STARTPTS,"
                    f"tpad=stop_mode=clone:stop={d_frames + 1},"
                    f"settb=1/{fps_int}{pre_fmt}{pad_lbl};"
                    f"{nxt_lbl}fps={fps_int},setpts=PTS-STARTPTS,"
                    f"settb=1/{fps_int}{pre_fmt}[vnxt_{step_idx}];"
                    f"{pad_lbl}[vnxt_{step_idx}]xfade=transition={xf_name}:"
                    f"duration={d:.4f}:offset={offset_s:.4f},"
                    f"fps={fps_int},setpts=PTS-STARTPTS,format=yuv420p{out_lbl}"
                )
            else:
                chains.append(
                    f"{cur_lbl}fps={fps_int},setpts=PTS-STARTPTS[vca_{step_idx}];"
                    f"{nxt_lbl}fps={fps_int},setpts=PTS-STARTPTS[vcb_{step_idx}];"
                    f"[vca_{step_idx}][vcb_{step_idx}]concat=n=2:v=1:a=0,"
                    f"fps={fps_int},setpts=PTS-STARTPTS,format=yuv420p{out_lbl}"
                )
            cur_lbl = out_lbl
            cur_frames += nxt_frames
            cur_dur = round(cur_frames / fps_int, 4)
    else:
        concat_tags = "".join(lbl for lbl, _, _ in clip_nodes)
        chains.append(f"{concat_tags}concat=n={len(clip_nodes)}:v=1:a=0[v_base]")

    final_v_label = "[v_base]"
    used_overlay = False
    next_input_idx = len(ordered_clips)
    if overlay_video_path is not None:
        if not overlay_video_path.is_file():
            raise MasteringError(f"Overlay video not found: {overlay_video_path}")
        ov_idx = next_input_idx
        next_input_idx += 1
        input_args.extend(["-i", str(overlay_video_path)])
        chains.append(
            f"[{ov_idx}:v]fps={fps},scale={width}:{height}[v_ov];"
            f"{final_v_label}[v_ov]overlay=0:0:shortest=0:eof_action=pass,format=yuv420p[v_comp]"
        )
        final_v_label = "[v_comp]"
        used_overlay = True

    for seg_k, (seg_start, seg_end, seg_path) in enumerate(overlay_segments or []):
        if not seg_path.is_file():
            raise MasteringError(f"Sparse overlay segment not found: {seg_path}")
        seg_idx = next_input_idx
        next_input_idx += 1
        input_args.extend(["-i", str(seg_path)])
        ov_lbl = f"v_seg_{seg_k}"
        comp_lbl = f"v_scomp_{seg_k}"
        chains.append(
            f"[{seg_idx}:v]fps={fps},scale={width}:{height},"
            f"setpts=PTS-STARTPTS+{seg_start:.4f}/TB[{ov_lbl}];"
            f"{final_v_label}[{ov_lbl}]overlay=0:0:"
            f"enable='between(t,{seg_start:.4f},{seg_end:.4f})':"
            f"shortest=0:eof_action=pass,format=yuv420p[{comp_lbl}]"
        )
        final_v_label = f"[{comp_lbl}]"
        used_overlay = True

    ass_overlays, _ = partition_overlays_for_hybrid(plan) if use_ass_fastpath else ([], [])

    audio_result: MasteredAudioResult | None = None
    with tempfile.TemporaryDirectory(prefix="vedit_master_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        if ass_overlays:
            ass_file = write_ass_overlays_file(
                ass_overlays,
                platform_target,
                tmp_path / "overlays.ass",
            )
            fonts_dir = _stage_plan_fonts_dir(plan, tmp_path / "fonts")
            escaped_ass = escape_ffmpeg_filter_path(ass_file)
            if fonts_dir is not None:
                escaped_fonts = escape_ffmpeg_filter_path(fonts_dir)
                sub_filter = f"ass='{escaped_ass}':fontsdir='{escaped_fonts}'"
            else:
                sub_filter = f"ass='{escaped_ass}'"
            chains.append(f"{final_v_label}{sub_filter},format=yuv420p[v_ass]")
            final_v_label = "[v_ass]"

        vspec = platform_target.video
        chains.append(
            f"{final_v_label}setparams=colorspace={vspec.color_space}:"
            f"color_primaries={vspec.color_primaries}:color_trc={vspec.color_trc}:"
            "range=tv[v_tagged]"
        )
        final_v_label = "[v_tagged]"

        resolved_audio: Path | None = mastered_audio_path
        if resolved_audio is None and plan.audio_tracks:
            resolved_audio = tmp_path / "master_audio.wav"
            audio_result = master_audio_mix(plan, platform_target, resolved_audio)

        map_args = ["-map", final_v_label]
        audio_encode_args: list[str] = ["-an"]
        if resolved_audio is not None:
            audio_idx = next_input_idx
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

        video_encode_args = _video_codec_args(
            platform_target,
            preset=encode_preset,
            use_hardware_encoder=use_hardware_encoder,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *input_args,
            "-filter_complex",
            ";".join(chains),
            *map_args,
            *video_encode_args,
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


def master_full_hf_deliverable(
    hf_video_path: Path,
    plan: EditPlan,
    platform_target: PlatformTarget,
    output_path: Path,
    *,
    encode_preset: Literal["ultrafast", "veryfast", "fast", "medium", "slow"] = "fast",
) -> HybridDeliverableResult:
    """Apply explicit color metadata tagging and two-pass EBU R128 mastering to a full_hf render."""
    if not hf_video_path.is_file():
        raise MasteringError(f"HyperFrames assembled video not found: {hf_video_path}")

    vspec = platform_target.video
    audio_result: MasteredAudioResult | None = None
    with tempfile.TemporaryDirectory(prefix="vedit_full_hf_master_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_args = ["-i", str(hf_video_path)]
        map_args = ["-map", "[v_tagged]"]
        audio_encode_args: list[str] = ["-an"]

        if plan.audio_tracks:
            master_wav = tmp_path / "master_audio.wav"
            audio_result = master_audio_mix(plan, platform_target, master_wav)
            input_args.extend(["-i", str(master_wav)])
            map_args.extend(["-map", "1:a"])
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

        vf = (
            f"[0:v]fps={platform_target.fps},format=yuv420p,"
            f"setparams=colorspace={vspec.color_space}:"
            f"color_primaries={vspec.color_primaries}:color_trc={vspec.color_trc}:range=tv[v_tagged]"
        )
        video_encode_args = _video_codec_args(platform_target, preset=encode_preset)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *input_args,
            "-filter_complex",
            vf,
            *map_args,
            *video_encode_args,
            *audio_encode_args,
            "-t",
            f"{plan.duration_s:.4f}",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise MasteringError(f"Full HyperFrames master pass failed: {proc.stderr}")

    return HybridDeliverableResult(
        output_path=output_path,
        audio_master=audio_result,
        used_overlay_video=False,
        width=platform_target.width,
        height=platform_target.height,
        fps=platform_target.fps,
    )
