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
from vedit.mastering.sound_design import (
    build_layer_band_filter,
    build_psychoacoustic_bgm_chain,
    resolve_loudness_profile,
)
from vedit.models import (
    AudioTrackOp,
    ColorCorrectionSpec,
    ColorGradeSpec,
    EditPlan,
    PlatformTarget,
    VideoClipOp,
)

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
    ]
    if track.audio_group == "voiceover" and track.highpass_hz is None:
        parts.append("highpass=f=75")
    parts.extend(build_layer_band_filter(track))
    parts.append(f"volume={track.gain_db:.2f}dB")
    if delay_ms > 0:
        parts.append(f"adelay={delay_ms}|{delay_ms}")
    return f"[{input_index}:a]{','.join(parts)}[{label}]"


def _derive_split_edit_audio_tracks(
    plan: EditPlan,
    assets_by_id: dict[str, Path],
) -> list[AudioTrackOp]:
    """Derive J-cut/L-cut audio pre-lap and post-lap tracks from clip split-edit metadata."""
    assets_meta = {a.asset_id: a for a in plan.assets}
    derived: list[AudioTrackOp] = []
    for clip in sorted(plan.video_tracks, key=lambda c: c.timeline_start_s):
        j_lead = float(clip.j_cut_lead_s or 0.0)
        l_trail = float(clip.l_cut_trail_s or 0.0)
        if j_lead <= 0.01 and l_trail <= 0.01:
            continue
        asset_ref = assets_meta.get(clip.asset_id)
        src_path = assets_by_id.get(clip.asset_id)
        if (
            asset_ref is None
            or not asset_ref.has_audio
            or src_path is None
            or not src_path.is_file()
        ):
            continue
        clip_end = clip.timeline_start_s + clip.timeline_duration_s
        covered_by_track = any(
            t.asset_id == clip.asset_id
            and (
                t.split_edit_role in ("j_cut", "l_cut")
                or (
                    t.timeline_start_s <= clip.timeline_start_s + 0.05
                    and (t.timeline_start_s + t.timeline_duration_s) >= clip_end - 0.05
                )
            )
            for t in plan.audio_tracks
        )
        if covered_by_track:
            continue

        # Clamp lead/trail against timeline and source media boundaries.
        max_lead = min(j_lead, clip.timeline_start_s, clip.source_start_s)
        max_end = plan.duration_s
        if asset_ref.duration_s is not None:
            clip_src_end = clip.source_start_s + clip.timeline_duration_s
            avail_after = max(0.0, asset_ref.duration_s - clip_src_end)
            l_trail = min(l_trail, avail_after)
        tl_start = round(max(0.0, clip.timeline_start_s - max_lead), 4)
        src_start = round(max(0.0, clip.source_start_s - max_lead), 4)
        tl_end = round(min(max_end, clip.timeline_start_s + clip.timeline_duration_s + l_trail), 4)
        dur = round(tl_end - tl_start, 4)
        if dur <= 0.05:
            continue
        role_tag: Literal["j_cut", "l_cut"] = "j_cut" if max_lead >= l_trail else "l_cut"
        derived.append(
            AudioTrackOp(
                track_id=f"split_{clip.clip_id}",
                asset_id=clip.asset_id,
                audio_group="voiceover" if clip.role == "a_roll" else "ambience",
                timeline_start_s=tl_start,
                timeline_duration_s=dur,
                source_start_s=src_start,
                gain_db=0.0 if clip.role == "a_roll" else -8.0,
                carve_against_group="voiceover" if clip.role != "a_roll" else None,
                carve_strength=0.45 if clip.role != "a_roll" else 0.0,
                fade_in_s=round(min(0.25, max(0.04, max_lead * 0.6)), 3),
                fade_out_s=round(min(0.25, max(0.04, l_trail * 0.6)), 3),
                split_edit_role=role_tag,
                split_edit_offset_s=round(-max_lead if role_tag == "j_cut" else l_trail, 3),
            )
        )
    return derived


def _build_audio_mix_graph(
    plan: EditPlan,
    assets_by_id: dict[str, Path],
    *,
    speech_wpm: float | None = None,
) -> tuple[list[str], str, str]:
    """Build FFmpeg inputs and filter_complex producing `[mixed_a]` at 48 kHz stereo."""
    input_args: list[str] = []
    chains: list[str] = []
    vo_labels: list[str] = []
    bgm_labels: list[str] = []
    amb_labels: list[str] = []
    room_labels: list[str] = []
    sfx_labels: list[str] = []
    carve_strength: float | None = None
    amb_carve_strength: float | None = None

    effective_tracks = list(plan.audio_tracks) + _derive_split_edit_audio_tracks(plan, assets_by_id)
    for idx, track in enumerate(effective_tracks):
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
        elif track.audio_group == "ambience":
            amb_labels.append(f"[{label}]")
            if track.carve_against_group == "voiceover":
                amb_carve_strength = (
                    track.carve_strength
                    if amb_carve_strength is None
                    else max(amb_carve_strength, track.carve_strength)
                )
        elif track.audio_group == "room_tone":
            room_labels.append(f"[{label}]")
        else:
            sfx_labels.append(f"[{label}]")

    should_carve = bool(
        vo_labels and bgm_labels and carve_strength is not None and carve_strength > 0
    )
    should_carve_amb = bool(
        vo_labels and amb_labels and amb_carve_strength is not None and amb_carve_strength > 0
    )
    need_vo_sc = should_carve or should_carve_amb
    effective_carve = carve_strength if carve_strength is not None else 0.0

    mix_inputs: list[str] = []
    if vo_labels:
        if len(vo_labels) == 1:
            chains.append(f"{vo_labels[0]}acopy[vo_bus]")
        else:
            chains.append(
                f"{''.join(vo_labels)}amix=inputs={len(vo_labels)}:duration=longest:normalize=0[vo_bus]"
            )
        # Split VO into dry branch + padded sidechain triggers so BGM/ambience never cut at VO EOF.
        if should_carve and should_carve_amb:
            chains.append(
                f"[vo_bus]asplit=3[vo_mix][vo_sc_raw][vo_amb_raw];"
                f"[vo_sc_raw]apad,atrim=0:{plan.duration_s:.4f}[vo_sc];"
                f"[vo_amb_raw]apad,atrim=0:{plan.duration_s:.4f}[vo_sc_amb]"
            )
            mix_inputs.append("[vo_mix]")
        elif need_vo_sc:
            sc_lbl = "[vo_sc]" if should_carve else "[vo_sc_amb]"
            chains.append(
                f"[vo_bus]asplit=2[vo_mix][vo_sc_raw];"
                f"[vo_sc_raw]apad,atrim=0:{plan.duration_s:.4f}{sc_lbl}"
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
            chains.append(
                build_psychoacoustic_bgm_chain(
                    "[bgm_raw]",
                    "[vo_sc]",
                    "[bgm_bus]",
                    carve_strength=effective_carve,
                    speech_wpm=speech_wpm,
                )
            )
        else:
            chains.append("[bgm_raw]acopy[bgm_bus]")
        mix_inputs.append("[bgm_bus]")

    if amb_labels:
        if len(amb_labels) == 1:
            chains.append(f"{amb_labels[0]}acopy[amb_raw]")
        else:
            chains.append(
                f"{''.join(amb_labels)}amix=inputs={len(amb_labels)}:duration=longest:normalize=0[amb_raw]"
            )
        if should_carve_amb and amb_carve_strength is not None:
            amb_ratio = round(1.5 + amb_carve_strength * 2.5, 2)
            amb_cut = round(-1.8 * amb_carve_strength, 2)
            chains.append(
                f"[amb_raw]equalizer=f=2400:t=o:w=1.2:g={amb_cut}[amb_eq];"
                f"[amb_eq][vo_sc_amb]sidechaincompress=threshold=0.03:ratio={amb_ratio}"
                ":attack=25:release=320:makeup=1[amb_bus]"
            )
        else:
            chains.append("[amb_raw]acopy[amb_bus]")
        mix_inputs.append("[amb_bus]")

    if room_labels:
        if len(room_labels) == 1:
            mix_inputs.append(room_labels[0])
        else:
            chains.append(
                f"{''.join(room_labels)}amix=inputs={len(room_labels)}:duration=longest:normalize=0[room_bus]"
            )
            mix_inputs.append("[room_bus]")

    if sfx_labels:
        if len(sfx_labels) == 1:
            mix_inputs.append(sfx_labels[0])
        else:
            chains.append(
                f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:duration=longest:normalize=0[sfx_bus]"
            )
            mix_inputs.append("[sfx_bus]")

    # Anchor final mix onto a full-duration silent bed so delayed tracks keep exact 0..duration_s.
    chains.append(
        f"anullsrc=r=48000:cl=stereo,atrim=0:{plan.duration_s:.4f}[sil_bed]"
    )
    all_mix = ["[sil_bed]", *mix_inputs]
    chains.append(
        f"{''.join(all_mix)}amix=inputs={len(all_mix)}:duration=first:normalize=0,"
        f"atrim=0:{plan.duration_s:.4f}[mixed_a]"
    )
    return input_args, ";".join(chains), "[mixed_a]"


def master_audio_mix(
    plan: EditPlan,
    platform_target: PlatformTarget,
    output_audio_path: Path,
    *,
    loudness_profile: str | None = None,
    speech_wpm: float | None = None,
) -> MasteredAudioResult:
    """Mix voiceover, carved music, ambience, room tone, and SFX, then run two-pass `loudnorm`."""
    assets_by_id = {asset.asset_id: Path(asset.path) for asset in plan.assets}
    has_split_audio = bool(_derive_split_edit_audio_tracks(plan, assets_by_id))
    if not plan.audio_tracks and not has_split_audio:
        raise MasteringError("Cannot master audio: EditPlan has no audio_tracks.")

    input_args, graph, mixed_label = _build_audio_mix_graph(
        plan, assets_by_id, speech_wpm=speech_wpm
    )
    audio_spec = platform_target.audio
    target_i, max_tp, target_lra, _tol = resolve_loudness_profile(
        loudness_profile, platform_target
    )
    # Leave a small 0.15 dBTP headroom guard for lossy AAC encoding overshoot.
    target_tp = round(min(max_tp - 0.15, -1.05), 2)

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

    Plan fonts win on filename collisions. For the shared engine font library
    (`assets/geo/fonts`), families that bundle both static weight files and variable masters
    stage static faces only so FreeType/libass deterministically resolves bold/regular weights
    without falling back to light default variable instances.
    """
    copied = 0
    plan_sources: list[Path] = [Path(a.path) for a in plan.assets if a.kind == "font"]
    for src in plan_sources:
        if not src.is_file() or (dest_dir / src.name).exists():
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_dir / src.name)
        copied += 1

    try:
        library = find_repo_root() / "assets" / "geo" / "fonts"
    except FileNotFoundError:
        library = None
    if library is not None and library.is_dir():
        lib_fonts = sorted(p for p in library.iterdir() if p.suffix.lower() in {".ttf", ".otf"})
        families_with_static: set[str] = set()
        for fp in lib_fonts:
            if "variable" not in fp.stem.lower():
                families_with_static.add(fp.stem.split("-")[0].lower())
        for src in lib_fonts:
            if not src.is_file() or (dest_dir / src.name).exists():
                continue
            stem_key = src.stem.split("-")[0].lower()
            if "variable" in src.stem.lower() and stem_key in families_with_static:
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


def _build_color_correction_filters(cc: ColorCorrectionSpec) -> list[str]:
    """Stage 1 technical normalization (exposure, contrast, saturation, white balance)."""
    filters: list[str] = []
    # Map exposure_ev [-2..2] gently into eq brightness [-0.35..0.35] and gamma compensation.
    brightness = max(-0.4, min(0.4, cc.exposure_ev * 0.14))
    if (
        abs(brightness) > 1e-4
        or abs(cc.contrast - 1.0) > 1e-4
        or abs(cc.saturation - 1.0) > 1e-4
        or abs(cc.gamma - 1.0) > 1e-4
    ):
        filters.append(
            f"eq=brightness={brightness:.3f}:contrast={cc.contrast:.3f}:"
            f"saturation={cc.saturation:.3f}:gamma={cc.gamma:.3f}"
        )
    has_wb = abs(cc.temperature) > 1e-4 or abs(cc.tint) > 1e-4
    has_lg = (
        (cc.lift is not None and abs(cc.lift) > 1e-4)
        or (cc.gain is not None and abs(cc.gain) > 1e-4)
    )
    if has_wb or has_lg:
        lv = max(-0.5, min(0.5, float(cc.lift or 0.0)))
        gv = max(-0.5, min(0.5, float(cc.gain or 0.0)))
        wb_r = max(-0.4, min(0.4, cc.temperature * 0.18))
        wb_b = max(-0.4, min(0.4, -cc.temperature * 0.18))
        wb_g = max(-0.4, min(0.4, -cc.tint * 0.16))
        rs = max(-0.5, min(0.5, lv + wb_r * 0.5))
        gs = max(-0.5, min(0.5, lv + wb_g * 0.5))
        bs = max(-0.5, min(0.5, lv + wb_b * 0.5))
        rm = max(-0.5, min(0.5, wb_r))
        gm = max(-0.5, min(0.5, wb_g))
        bm = max(-0.5, min(0.5, wb_b))
        filters.append(
            f"colorbalance=rs={rs:.3f}:gs={gs:.3f}:bs={bs:.3f}:"
            f"rm={rm:.3f}:gm={gm:.3f}:bm={bm:.3f}:"
            f"rh={gv:.3f}:gh={gv:.3f}:bh={gv:.3f}"
        )
    return filters


def _build_color_grade_filters(cg: ColorGradeSpec) -> list[str]:
    """Stage 2 creative/emotional color grading applied strictly after correction."""
    filters: list[str] = []
    intensity = max(0.0, min(1.0, float(cg.intensity)))
    preset = cg.preset or "neutral"
    if intensity > 1e-4:
        if preset == "catastrophe_warm":
            rs = round(0.14 * intensity, 3)
            bs = round(-0.16 * intensity, 3)
            sat = round(1.0 - 0.18 * intensity, 3)
            filters.append(f"colorbalance=rs={rs}:bs={bs}:rm={rs * 0.7:.3f}:bm={bs * 0.7:.3f}")
            filters.append(f"eq=saturation={sat}:contrast={1.0 + 0.08 * intensity:.3f}")
        elif preset == "dread_dim_vignette":
            bri = round(-0.08 * intensity, 3)
            sat = round(1.0 - 0.35 * intensity, 3)
            con = round(1.0 + 0.12 * intensity, 3)
            filters.append(f"eq=brightness={bri}:saturation={sat}:contrast={con}")
            if cg.vignette_strength is None:
                filters.append(f"vignette=angle={0.45 + 0.35 * intensity:.3f}")
        elif preset == "anomaly_desat":
            sat = round(max(0.05, 1.0 - 0.78 * intensity), 3)
            filters.append(f"eq=saturation={sat}:contrast={1.0 + 0.14 * intensity:.3f}")
        elif preset == "archival_sepia":
            rs = round(0.18 * intensity, 3)
            gs = round(0.05 * intensity, 3)
            bs = round(-0.22 * intensity, 3)
            sat = round(max(0.25, 1.0 - 0.55 * intensity), 3)
            filters.append(f"eq=saturation={sat}:contrast={1.0 - 0.06 * intensity:.3f}")
            filters.append(f"colorbalance=rs={rs}:gs={gs}:bs={bs}")
        elif preset == "cool_investigative":
            rs = round(-0.08 * intensity, 3)
            bs = round(0.12 * intensity, 3)
            filters.append(f"colorbalance=rs={rs}:bs={bs}")
            filters.append(f"eq=contrast={1.0 + 0.08 * intensity:.3f}")

    if cg.lut_path:
        lut_p = Path(cg.lut_path).expanduser().resolve()
        if not lut_p.is_file():
            raise MasteringError(f"Missing 3D LUT file: {cg.lut_path}")
        escaped_lut = escape_ffmpeg_filter_path(lut_p)
        filters.append(f"lut3d=file='{escaped_lut}'")

    if cg.vignette_strength is not None and cg.vignette_strength > 0.01:
        angle = round(0.25 + min(1.0, cg.vignette_strength) * 0.65, 3)
        filters.append(f"vignette=angle={angle}")

    return filters


def compute_shot_match_correction(
    source_luma: float,
    target_luma: float,
    *,
    source_ab: tuple[float, float] | None = None,
    target_ab: tuple[float, float] | None = None,
) -> ColorCorrectionSpec:
    """Compute bounded Stage 1 exposure/white-balance correction to match B-roll to spine."""
    luma_diff = (target_luma - source_luma) / 128.0
    exposure_ev = round(max(-1.5, min(1.5, luma_diff * 1.15)), 3)
    temp = 0.0
    tint = 0.0
    if source_ab is not None and target_ab is not None:
        da = target_ab[0] - source_ab[0]
        db = target_ab[1] - source_ab[1]
        temp = round(max(-0.8, min(0.8, db / 64.0)), 3)
        tint = round(max(-0.8, min(0.8, da / 64.0)), 3)
    return ColorCorrectionSpec(exposure_ev=exposure_ev, temperature=temp, tint=tint)


def resolve_segment_blend_modes(
    plan: EditPlan,
    overlay_segments: list[tuple[float, float, Path]],
) -> list[str | None]:
    """Map each sparse overlay window to its strongest non-normal overlay `blend_mode`."""
    modes: list[str | None] = []
    for seg_start, seg_end, _ in overlay_segments:
        found: str | None = None
        for ov in plan.overlay_compositions:
            ov_start = float(ov.timeline_start_s)
            ov_end = ov_start + float(ov.timeline_duration_s)
            if (
                ov_start < seg_end
                and ov_end > seg_start
                and ov.blend_mode
                and ov.blend_mode != "normal"
            ):
                found = ov.blend_mode
                break
        modes.append(found)
    return modes


def _probe_clip_luma_ab(
    media_path: Path,
    t_s: float,
) -> tuple[float, tuple[float, float]] | None:
    """Sample mean BT.601 luma and approximate Lab a*/b* from a frame at `t_s`."""
    w, h = 64, 36
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, float(t_s)):.3f}",
            "-i",
            str(media_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={w}:{h}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    expected = w * h * 3
    if proc.returncode != 0 or len(proc.stdout) < expected:
        return None
    raw = proc.stdout[:expected]
    n_px = w * h
    sum_y = 0.0
    sum_rg = 0.0
    sum_by = 0.0
    for idx in range(0, expected, 3):
        r, g, b = raw[idx], raw[idx + 1], raw[idx + 2]
        sum_y += 0.299 * r + 0.587 * g + 0.114 * b
        sum_rg += (r - g) * 0.5
        sum_by += (0.5 * (r + g) - b) * 0.5
    return (round(sum_y / n_px, 2), (round(sum_rg / n_px, 2), round(sum_by / n_px, 2)))


def auto_shot_match_plan(
    plan: EditPlan,
    assets_by_id: dict[str, Path],
) -> EditPlan:
    """Populate Stage-1 `color_correction` on B-roll/secondary clips to match the opening spine."""
    ordered = sorted(plan.video_tracks, key=lambda c: c.timeline_start_s)
    if len(ordered) < 2:
        return plan
    spine = ordered[0]
    spine_path = assets_by_id.get(spine.asset_id)
    if spine_path is None or not spine_path.is_file():
        return plan
    ref = _probe_clip_luma_ab(spine_path, spine.source_start_s + spine.timeline_duration_s * 0.5)
    if ref is None:
        return plan
    target_luma, target_ab = ref

    updated_clips: list[VideoClipOp] = []
    changed = False
    for clip in plan.video_tracks:
        if clip.asset_id != spine.asset_id and clip.color_correction is None:
            cpath = assets_by_id.get(clip.asset_id)
            if cpath is not None and cpath.is_file():
                sample = _probe_clip_luma_ab(
                    cpath, clip.source_start_s + clip.timeline_duration_s * 0.5
                )
                if sample is not None:
                    src_luma, src_ab = sample
                    cc = compute_shot_match_correction(
                        src_luma,
                        target_luma,
                        source_ab=src_ab,
                        target_ab=target_ab,
                    )
                    clip = clip.model_copy(update={"color_correction": cc})
                    changed = True
        updated_clips.append(clip)
    return plan.model_copy(update={"video_tracks": updated_clips}) if changed else plan


def assemble_hybrid_deliverable(
    plan: EditPlan,
    platform_target: PlatformTarget,
    output_path: Path,
    *,
    overlay_video_path: Path | None = None,
    overlay_segments: list[tuple[float, float, Path]] | None = None,
    overlay_blend_modes: list[str | None] | None = None,
    mastered_audio_path: Path | None = None,
    captions_ass_path: Path | None = None,
    fonts_dir: Path | None = None,
    use_ass_fastpath: bool = True,
    encode_preset: Literal["ultrafast", "veryfast", "fast", "medium", "slow"] = "fast",
    use_hardware_encoder: bool = False,
    loudness_profile: str | None = None,
    auto_shot_match: bool = False,
) -> HybridDeliverableResult:
    """Assemble base cuts, optional transparent overlay, native libass text, and mastered audio."""
    if not plan.video_tracks:
        raise MasteringError("EditPlan requires at least one video clip in video_tracks.")

    assets_by_id = {asset.asset_id: Path(asset.path) for asset in plan.assets}
    if auto_shot_match:
        plan = auto_shot_match_plan(plan, assets_by_id)
    if overlay_segments and overlay_blend_modes is None:
        overlay_blend_modes = resolve_segment_blend_modes(plan, overlay_segments)
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
        if clip.color_correction is not None:
            vf_parts.extend(_build_color_correction_filters(clip.color_correction))
        if clip.color_grade is not None:
            vf_parts.extend(_build_color_grade_filters(clip.color_grade))
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
        bmode = (
            overlay_blend_modes[seg_k]
            if overlay_blend_modes and seg_k < len(overlay_blend_modes)
            else None
        )
        if bmode and bmode in ("screen", "multiply", "overlay", "lighten"):
            base_rgba = f"v_b_rgba_{seg_k}"
            blend_rgb = f"v_bl_rgb_{seg_k}"
            blend_rgba = f"v_bl_rgba_{seg_k}"
            chains.append(
                f"{final_v_label}format=yuv420p,split[{base_rgba}_orig][{base_rgba}_prep];"
                f"[{base_rgba}_prep]format=rgba[{base_rgba}];"
                f"[{seg_idx}:v]fps={fps},scale={width}:{height},"
                f"setpts=PTS-STARTPTS+{seg_start:.4f}/TB,format=rgba,"
                f"split[{ov_lbl}_rgb][{ov_lbl}_a];"
                f"[{ov_lbl}_a]alphaextract[{ov_lbl}_mask];"
                f"[{base_rgba}][{ov_lbl}_rgb]blend=all_mode={bmode}:"
                f"all_opacity=1:eof_action=pass[{blend_rgb}];"
                f"[{blend_rgb}][{ov_lbl}_mask]alphamerge[{blend_rgba}];"
                f"[{base_rgba}_orig][{blend_rgba}]overlay=0:0:"
                f"enable='between(t,{seg_start:.4f},{seg_end:.4f})':"
                f"shortest=0:eof_action=pass,format=yuv420p[{comp_lbl}]"
            )
        else:
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
    ext_captions_ass: Path | None = None
    if captions_ass_path is not None:
        ext_captions_ass = captions_ass_path.expanduser().resolve()
        if not ext_captions_ass.is_file():
            raise MasteringError(f"Captions ASS file not found: {ext_captions_ass}")

    audio_result: MasteredAudioResult | None = None
    with tempfile.TemporaryDirectory(prefix="vedit_master_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        staged_fonts = _stage_plan_fonts_dir(plan, tmp_path / "fonts")
        if fonts_dir is not None:
            extra_fonts_dir = fonts_dir.expanduser().resolve()
            if extra_fonts_dir.is_dir():
                fonts_dest = tmp_path / "fonts"
                fonts_dest.mkdir(parents=True, exist_ok=True)
                for src_f in sorted(extra_fonts_dir.iterdir()):
                    if src_f.is_file() and src_f.suffix.lower() in {".ttf", ".otf"}:
                        if not (fonts_dest / src_f.name).exists():
                            shutil.copy2(src_f, fonts_dest / src_f.name)
                        staged_fonts = fonts_dest

        if ass_overlays:
            ass_file = write_ass_overlays_file(
                ass_overlays,
                platform_target,
                tmp_path / "overlays.ass",
            )
            escaped_ass = escape_ffmpeg_filter_path(ass_file)
            if staged_fonts is not None:
                escaped_fonts = escape_ffmpeg_filter_path(staged_fonts)
                sub_filter = f"ass='{escaped_ass}':fontsdir='{escaped_fonts}'"
            else:
                sub_filter = f"ass='{escaped_ass}'"
            chains.append(f"{final_v_label}{sub_filter},format=yuv420p[v_ass]")
            final_v_label = "[v_ass]"

        if ext_captions_ass is not None:
            escaped_cap = escape_ffmpeg_filter_path(ext_captions_ass)
            if staged_fonts is not None:
                escaped_fonts = escape_ffmpeg_filter_path(staged_fonts)
                cap_filter = f"ass='{escaped_cap}':fontsdir='{escaped_fonts}'"
            else:
                cap_filter = f"ass='{escaped_cap}'"
            chains.append(f"{final_v_label}{cap_filter},format=yuv420p[v_cap]")
            final_v_label = "[v_cap]"

        vspec = platform_target.video
        chains.append(
            f"{final_v_label}setparams=colorspace={vspec.color_space}:"
            f"color_primaries={vspec.color_primaries}:color_trc={vspec.color_trc}:"
            "range=tv[v_tagged]"
        )
        final_v_label = "[v_tagged]"

        resolved_audio: Path | None = mastered_audio_path
        has_split_audio = bool(_derive_split_edit_audio_tracks(plan, assets_by_id))
        if resolved_audio is None and (plan.audio_tracks or has_split_audio):
            resolved_audio = tmp_path / "master_audio.wav"
            audio_result = master_audio_mix(
                plan,
                platform_target,
                resolved_audio,
                loudness_profile=loudness_profile,
            )

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
    loudness_profile: str | None = None,
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

        assets_by_id = {asset.asset_id: Path(asset.path) for asset in plan.assets}
        has_split_audio = bool(_derive_split_edit_audio_tracks(plan, assets_by_id))
        if plan.audio_tracks or has_split_audio:
            master_wav = tmp_path / "master_audio.wav"
            audio_result = master_audio_mix(
                plan,
                platform_target,
                master_wav,
                loudness_profile=loudness_profile,
            )
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
