"""Scene-synced SFX derivation, documentary BGM synthesis, and multi-bus audio mixing."""

from __future__ import annotations

import array
import json
import math
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import typer

from vedit.contracts import find_repo_root
from vedit.mastering.ffmpeg_master import _is_finite_loudnorm_val, _parse_loudnorm_json
from vedit.mastering.sound_design import (
    LOUDNESS_PROFILES,
    build_psychoacoustic_bgm_chain,
    pan_to_ffmpeg_filter,
    plan_narrative_audio_cues,
    synthesize_ambience_layers,
    synthesize_four_layer_impact,
    synthesize_granular_pad,
    synthesize_narrative_bgm,
    synthesize_room_tone_bed,
    synthesize_shepard_riser,
    synthesize_stinger,
    synthesize_tension_drone,
    synthesize_whoosh,
)

_SFX_LAYER_MAP: dict[str, tuple[str, float]] = {
    "void_wipe": ("flash_swish.wav", -9.0),
    "crimson_x": ("stamp_impact.wav", -6.5),
    "pin_label": ("pin_drop.wav", -10.5),
    "curved_pointer_label": ("pop_soft.wav", -11.0),
    "dashed_distance": ("whoosh_fast.wav", -11.5),
    "curved_arc_arrow": ("whoosh_fast.wav", -11.5),
    "route": ("whoosh_deep.wav", -12.0),
    "cable_3d": ("whoosh_deep.wav", -12.0),
    "model_3d": ("sub_thud.wav", -10.0),
    "volume_3d": ("flash_swish.wav", -10.5),
    "country_block_3d": ("sub_thud.wav", -10.5),
    "radar_rings": ("radar_ping.wav", -13.0),
    "counter_odometer": ("counter_tick.wav", -11.0),
    "human_silhouette_row": ("pop_bright.wav", -11.0),
    "landmark_silhouette": ("sub_thud.wav", -9.5),
    "wind_streamlines": ("whoosh_fast.wav", -13.0),
    "flag_pin": ("pop_soft.wav", -11.5),
    "ghost_overlay": ("flash_swish.wav", -11.0),
    "tree_belt": ("whoosh_deep.wav", -12.0),
    "dust_storm_plume": ("whoosh_deep.wav", -11.5),
    "parchment_sheet": ("paper_unfold.wav", -9.5),
    "map_sprites": ("pop_soft.wav", -11.5),
}




def derive_sfx_events_from_scene(
    spec: dict[str, Any], *, min_gap_s: float = 0.35, max_events: int = 44
) -> list[dict[str, Any]]:
    """Derive 0ms-aligned kinetic SFX hits from declarative map_scene.json beats."""
    raw: list[tuple[float, int, str, float]] = []
    time_offset = 0.0
    for act in spec.get("acts") or []:
        dur = float(act.get("duration_s", 0.0))
        # Camera dive / fly moves -> subtle swoosh accent
        for kf in act.get("camera_keyframes") or []:
            if isinstance(kf, dict):
                curve = str(kf.get("curve") or "")
                tk = float(kf.get("t", kf.get("t_s", 0.0)))
                if curve == "snap_dive" and tk > 0.2:
                    raw.append((time_offset + max(0.0, tk - 0.55), 1, "swoosh_zoom.wav", -12.5))
                elif curve == "hyperbolic_fly" and tk > 0.2:
                    raw.append((time_offset + max(0.0, tk - 0.65), 1, "whoosh_deep.wav", -12.0))

        for layer in act.get("layers") or []:
            ltype = str(layer.get("type") or "")
            t0 = time_offset + float(layer.get("start_s", 0.0))
            if ltype in _SFX_LAYER_MAP:
                sfx_name, gain_db = _SFX_LAYER_MAP[ltype]
                prio = 3 if ltype in {"crimson_x", "void_wipe", "landmark_silhouette"} else 2
                raw.append((t0, prio, sfx_name, gain_db))
            elif ltype == "glow_label":
                if layer.get("count_to") is not None:
                    raw.append((t0, 3, "ding_glass.wav", -10.0))
                elif float(layer.get("font_px", 48)) >= 64:
                    raw.append((t0, 2, "pop_bright.wav", -11.5))
            elif ltype == "prohibition_pins":
                for pin in (layer.get("pins") or [])[:8]:
                    pt = time_offset + float(pin.get("pop_s", layer.get("start_s", 0.0)))
                    raw.append((pt, 2, "pop_bright.wav", -12.0))
                    sd = float(pin.get("slash_delay_s", 0.36))
                    raw.append((pt + sd, 2, "warning_pulse.wav", -13.0))
        time_offset += dur

    raw.sort(key=lambda item: (item[0], -item[1]))
    selected: list[dict[str, Any]] = []
    last_t = -10.0
    for t_ev, _prio, fname, gain_db in raw:
        if t_ev < 0.0 or t_ev - last_t < min_gap_s:
            continue
        selected.append({"t_s": round(t_ev, 3), "sfx": fname, "gain_db": gain_db})
        last_t = t_ev
        if len(selected) >= max_events:
            break
    return selected


def synthesize_documentary_bgm(
    duration_s: float, out_wav: Path, *, sample_rate: int = 48000, bpm: float = 92.0
) -> Path:
    """Synthesize a clean ambient cartographic-documentary BGM bed (48 kHz stereo PCM)."""
    n_samples = max(1, math.ceil(duration_s * sample_rate))
    # D minor documentary progression: Dm -> Bb -> F -> C (each 4 beats)
    chords = [
        (73.42, 146.83, 174.61, 220.00),  # Dm
        (58.27, 116.54, 174.61, 233.08),  # Bb
        (87.31, 130.81, 174.61, 220.00),  # F
        (65.41, 130.81, 164.81, 196.00),  # C
    ]
    beat_s = 60.0 / bpm
    bar_s = beat_s * 4.0
    buf = array.array("h", [0] * (n_samples * 2))
    two_pi = 2.0 * math.pi
    fade_in_n = int(min(1.5, duration_s * 0.1) * sample_rate)
    fade_out_n = int(min(2.0, duration_s * 0.15) * sample_rate)

    for i in range(n_samples):
        t = i / sample_rate
        bar_idx = int(t / bar_s) % len(chords)
        bar_pos = (t % bar_s) / bar_s
        beat_pos = (t % beat_s) / beat_s
        bass_f, f1, f2, f3 = chords[bar_idx]

        # Smooth chord crossfade envelope within bar
        chord_env = min(1.0, bar_pos * 8.0) * min(1.0, (1.0 - bar_pos) * 10.0 + 0.15)
        # Gentle documentary pulse on each beat
        pulse = 0.65 + 0.35 * math.exp(-beat_pos * 4.5)
        # Warm sub-bass + soft filtered triad pads
        sub = 0.28 * math.sin(two_pi * bass_f * t) * pulse
        pad_l = (
            0.14 * math.sin(two_pi * f1 * t)
            + 0.11 * math.sin(two_pi * f2 * t + 0.3)
            + 0.08 * math.sin(two_pi * f3 * t + 0.8)
            + 0.03 * math.sin(two_pi * f3 * 2.0 * t) * math.exp(-beat_pos * 7.0)
        ) * chord_env
        pad_r = (
            0.14 * math.sin(two_pi * f1 * t + 0.15)
            + 0.11 * math.sin(two_pi * f2 * t + 0.6)
            + 0.08 * math.sin(two_pi * f3 * t + 1.1)
            + 0.03 * math.sin(two_pi * f2 * 2.0 * t) * math.exp(-beat_pos * 7.0)
        ) * chord_env

        env = 1.0
        if i < fade_in_n:
            env *= i / max(1, fade_in_n)
        if i > n_samples - fade_out_n:
            env *= max(0.0, (n_samples - i) / max(1, fade_out_n))

        val_l = max(-0.92, min(0.92, (sub + pad_l) * env))
        val_r = max(-0.92, min(0.92, (sub + pad_r) * env))
        buf[i * 2] = int(val_l * 32767)
        buf[i * 2 + 1] = int(val_r * 32767)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(buf.tobytes())
    return out_wav


def _resolve_studio_bgm(
    root: Path, query: str = "mysterious documentary minimal"
) -> tuple[Path | None, str]:
    """Resolve a real studio instrumental BGM track from local cache or AudioCatalogPort."""
    bgm_dir = root / "assets" / "audio" / "bgm"
    for preferred in ("documentary_curious.wav", "documentary_default.wav"):
        cand = bgm_dir / preferred
        if cand.is_file() and cand.stat().st_size > 16384:
            return cand, f"studio_library:{cand.name}"
    if bgm_dir.is_dir():
        for ext in ("*.wav", "*.mp3", "*.m4a", "*.flac"):
            matches = sorted(p for p in bgm_dir.glob(ext) if p.stat().st_size > 16384)
            if matches:
                return matches[0], f"studio_library:{matches[0].name}"
    try:
        from vedit.providers.builtins import build_default_registry

        registry = build_default_registry()
        catalog = registry.resolve("audio_catalog")
        tracks = catalog.search_music(query=query, vocal_type="NONE", limit=3)
        if tracks:
            bgm_dir.mkdir(parents=True, exist_ok=True)
            asset_id = tracks[0].asset_id
            dl = catalog.download_asset(
                asset_id, kind="music", destination_dir=bgm_dir, quality="high"
            )
            if dl.is_file() and dl.stat().st_size > 16384:
                return dl, f"audio_catalog:{asset_id}"
    except Exception:
        pass
    return None, ""




def mix_geo_audio(
    scene_file: Path,
    voice_file: Path,
    out_file: Path,
    *,
    bgm_file: Path | None = None,
    bgm_second: Path | None = None,
    bgm_switch_s: float | None = None,
    bgm_gain_db: float = -16.0,
    bgm_second_gain_db: float | None = None,
    ambience_file: Path | None = None,
    ambience_gain_db: float = -26.0,
    extra_sfx_json: Path | None = None,
    storyboard_file: Path | None = None,
    loudness_profile: str = "streaming_web",
    narrative_fx: bool = True,
    allow_synth_fx: bool = False,
    room_tone: bool = True,
    room_tone_db: float = -52.0,
) -> None:
    """Mix voiceover, studio BGM, and scene-synced SFX with two-pass loudnorm."""
    root = find_repo_root()
    sfx_dir = root / "assets" / "audio" / "sfx"
    spec = json.loads(scene_file.expanduser().resolve().read_text(encoding="utf-8"))
    sb_data = (
        json.loads(storyboard_file.expanduser().resolve().read_text(encoding="utf-8"))
        if storyboard_file is not None
        else None
    )
    vo_path = voice_file.expanduser().resolve()
    out_path = out_file.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lp_key = loudness_profile.strip().lower()
    if lp_key not in LOUDNESS_PROFILES:
        raise typer.BadParameter(
            f"Unknown --loudness-profile {loudness_profile!r}; "
            f"expected one of: {', '.join(sorted(LOUDNESS_PROFILES))}"
        )
    prof = LOUDNESS_PROFILES[lp_key]
    target_i = prof.target_lufs
    target_tp = round(min(prof.max_true_peak_dbtp - 0.35, -1.45), 2)
    target_lra = prof.target_lra

    # Probe exact voiceover duration
    dur_proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vo_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration_s = float(dur_proc.stdout.strip())

    cues = (
        plan_narrative_audio_cues(spec, storyboard=sb_data)
        if narrative_fx
        else {
            "risers": [],
            "drones": [],
            "impacts": [],
            "stingers": [],
            "whooshes": [],
            "ambience": [],
            "silence_dropouts": [],
            "section_timeline": [],
            "cue_clustering_warnings": [],
        }
    )

    with tempfile.TemporaryDirectory(prefix="vedit_geo_mix_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        synthetic_fallback_used = False
        if bgm_file is not None:
            bgm_path = bgm_file.expanduser().resolve()
            bgm_source_label = str(bgm_path)
        else:
            studio_bgm, studio_label = _resolve_studio_bgm(root)
            if studio_bgm is not None:
                bgm_path = studio_bgm
                bgm_source_label = studio_label
            else:
                synthetic_fallback_used = True
                bgm_path = tmp_path / "narrative_bgm.wav"
                bgm_source_label = "synthesized_fallback_bed"
                synthesize_narrative_bgm(
                    duration_s + 0.5,
                    bgm_path,
                    section_timeline=cues["section_timeline"] or None,
                    silence_dropouts=cues["silence_dropouts"] or None,
                )

        # Optional two-track narrative BGM bed with crisp 280ms silence breath at chapter pivot
        if (
            bgm_second is not None
            and bgm_switch_s is not None
            and 0.5 < bgm_switch_s < duration_s - 0.5
        ):
            bgm2_path = bgm_second.expanduser().resolve()
            sw_s = float(bgm_switch_s)
            breath_s = 0.28
            bgm1_end = max(0.2, sw_s - breath_s)
            bgm2_len = max(0.2, duration_s - sw_s + 0.5)
            bgm2_gain_offset = (
                (bgm_second_gain_db - bgm_gain_db) if bgm_second_gain_db is not None else 0.0
            )
            stitched_bgm = tmp_path / "bgm_stitched.wav"
            b1_out = max(0.0, bgm1_end - 0.35)
            b2_out = max(0.0, bgm2_len - 1.2)
            stitch_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(bgm_path),
                "-stream_loop",
                "-1",
                "-i",
                str(bgm2_path),
                "-filter_complex",
                (
                    f"[0:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{bgm1_end:.3f},"
                    f"afade=t=in:st=0:d=0.4,afade=t=out:st={b1_out:.3f}:d=0.35,"
                    f"apad=pad_dur={breath_s:.3f},atrim=0:{sw_s:.3f}[b1];"
                    f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{bgm2_len:.3f},"
                    f"volume={bgm2_gain_offset:.1f}dB,"
                    f"afade=t=in:st=0:d=0.35,afade=t=out:st={b2_out:.3f}:d=1.2[b2];"
                    "[b1][b2]concat=n=2:v=0:a=1[bgm_all]"
                ),
                "-map",
                "[bgm_all]",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_f32le",
                str(stitched_bgm),
            ]
            stitch_proc = subprocess.run(stitch_cmd, capture_output=True, text=True, check=False)
            if stitch_proc.returncode != 0:
                raise RuntimeError(f"ffmpeg BGM stitch failed: {stitch_proc.stderr[-400:]}")
            bgm_path = stitched_bgm
            bgm_source_label = f"{bgm_source_label} -> {bgm2_path.name}@{sw_s:.2f}s"

        events = [
            ev
            for ev in derive_sfx_events_from_scene(spec)
            if ev["t_s"] < duration_s - 0.15 and (sfx_dir / ev["sfx"]).is_file()
        ]
        extra_fx: list[dict[str, Any]] = []
        used_risers = 0
        used_drones = 0
        used_impacts = 0
        used_stingers = 0
        used_whooshes = 0

        # Prefer real recorded studio WAVs from assets/audio/sfx/ over procedural oscillators.
        studio_riser = sfx_dir / "cinematic_riser.wav"
        studio_impact = sfx_dir / "stamp_impact.wav"
        studio_sub = sfx_dir / "sub_thud.wav"
        studio_stinger = sfx_dir / "ding_glass.wav"
        studio_warning = sfx_dir / "warning_pulse.wav"
        studio_whoosh_deep = sfx_dir / "whoosh_deep.wav"
        studio_whoosh_fast = sfx_dir / "whoosh_fast.wav"

        for idx, r_ev in enumerate(cues["risers"]):
            if r_ev["start_s"] + r_ev["duration_s"] <= duration_s:
                if studio_riser.is_file():
                    r_wav = studio_riser
                elif allow_synth_fx:
                    r_wav = tmp_path / f"riser_{idx}.wav"
                    synthesize_shepard_riser(r_ev["duration_s"], r_wav)
                else:
                    continue
                used_risers += 1
                extra_fx.append(
                    {
                        "t_s": r_ev["start_s"],
                        "path": r_wav,
                        "gain_db": r_ev["gain_db"],
                        "pan": 0.0,
                    }
                )
        if allow_synth_fx:
            for idx, d_ev in enumerate(cues["drones"]):
                if d_ev["start_s"] < duration_s - 0.2:
                    d_wav = tmp_path / f"drone_{idx}.wav"
                    d_len = min(d_ev["duration_s"], duration_s - d_ev["start_s"])
                    if d_ev.get("texture") == "granular":
                        synthesize_granular_pad(d_len, d_wav)
                    else:
                        synthesize_tension_drone(d_len, d_wav)
                    used_drones += 1
                    extra_fx.append(
                        {
                            "t_s": d_ev["start_s"],
                            "path": d_wav,
                            "gain_db": d_ev["gain_db"],
                            "pan": 0.0,
                        }
                    )
            for idx, a_ev in enumerate(cues.get("ambience") or []):
                if a_ev["start_s"] < duration_s - 0.2:
                    a_wav = tmp_path / f"amb_{idx}.wav"
                    a_len = min(a_ev["duration_s"], duration_s - a_ev["start_s"])
                    synthesize_ambience_layers(a_len, a_wav, level_db=0.0)
                    extra_fx.append(
                        {
                            "t_s": a_ev["start_s"],
                            "path": a_wav,
                            "gain_db": a_ev.get("gain_db", -20.0),
                            "pan": float(a_ev.get("pan") or 0.0),
                        }
                    )
        for idx, imp_ev in enumerate(cues.get("impacts") or []):
            if imp_ev["start_s"] < duration_s - 0.2:
                char = str(imp_ev.get("character") or "verdict")
                if studio_impact.is_file() or studio_sub.is_file():
                    use_imp = char == "verdict" and studio_impact.is_file()
                    i_wav = studio_impact if use_imp else studio_sub
                elif allow_synth_fx:
                    i_wav = tmp_path / f"impact_{idx}.wav"
                    synthesize_four_layer_impact(
                        i_wav,
                        character=char,  # type: ignore[arg-type]
                    )
                else:
                    continue
                used_impacts += 1
                extra_fx.append(
                    {
                        "t_s": imp_ev["start_s"],
                        "path": i_wav,
                        "gain_db": imp_ev.get("gain_db", -12.0),
                        "pan": float(imp_ev.get("pan") or 0.0),
                    }
                )
        for idx, st_ev in enumerate(cues.get("stingers") or []):
            if st_ev["start_s"] < duration_s - 0.2:
                style = str(st_ev.get("style") or "reveal")
                if studio_stinger.is_file() or studio_warning.is_file():
                    use_warn = style == "twist" and studio_warning.is_file()
                    st_wav = studio_warning if use_warn else studio_stinger
                elif allow_synth_fx:
                    st_wav = tmp_path / f"stinger_{idx}.wav"
                    synthesize_stinger(
                        st_wav,
                        style=style,  # type: ignore[arg-type]
                    )
                else:
                    continue
                used_stingers += 1
                extra_fx.append(
                    {
                        "t_s": st_ev["start_s"],
                        "path": st_wav,
                        "gain_db": st_ev.get("gain_db", -13.5),
                        "pan": 0.0,
                    }
                )
        for idx, wh_ev in enumerate(cues.get("whooshes") or []):
            if wh_ev["start_s"] < duration_s - 0.15:
                direction = str(wh_ev.get("direction") or "in")
                if studio_whoosh_deep.is_file() or studio_whoosh_fast.is_file():
                    use_fast = direction == "out" and studio_whoosh_fast.is_file()
                    w_wav = studio_whoosh_fast if use_fast else studio_whoosh_deep
                elif allow_synth_fx:
                    w_wav = tmp_path / f"whoosh_{idx}.wav"
                    synthesize_whoosh(
                        float(wh_ev.get("duration_s") or 0.4),
                        w_wav,
                        direction=direction,  # type: ignore[arg-type]
                    )
                else:
                    continue
                used_whooshes += 1
                extra_fx.append(
                    {
                        "t_s": wh_ev["start_s"],
                        "path": w_wav,
                        "gain_db": wh_ev.get("gain_db", -13.0),
                        "pan": 0.0,
                    }
                )
        if extra_sfx_json is not None:
            sfx_json_text = extra_sfx_json.expanduser().resolve().read_text(encoding="utf-8")
            custom_list = json.loads(sfx_json_text)
            for item in custom_list:
                p = Path(str(item["path"])).expanduser().resolve()
                if p.is_file() and float(item.get("t_s", 0.0)) < duration_s - 0.05:
                    extra_fx.append(
                        {
                            "t_s": float(item.get("t_s", 0.0)),
                            "path": p,
                            "gain_db": float(item.get("gain_db", -12.0)),
                            "pan": float(item.get("pan", 0.0)),
                            "trim_s": item.get("trim_s"),
                            "fade_out_s": item.get("fade_out_s"),
                        }
                    )
        if ambience_file is not None:
            amb_p = ambience_file.expanduser().resolve()
            if amb_p.is_file():
                extra_fx.append(
                    {
                        "t_s": 0.0,
                        "path": amb_p,
                        "gain_db": ambience_gain_db,
                        "pan": 0.0,
                        "loop_bed": True,
                    }
                )
        if room_tone:
            room_wav = tmp_path / "room_tone.wav"
            synthesize_room_tone_bed(duration_s, room_wav, level_db=room_tone_db)
            extra_fx.append(
                {
                    "t_s": 0.0,
                    "path": room_wav,
                    "gain_db": 0.0,
                    "pan": 0.0,
                }
            )

        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-i",
            str(vo_path),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm_path),
        ]
        synth_transient_times = [
            float(fx["t_s"])
            for fx in extra_fx
            if not fx.get("loop_bed") and Path(str(fx["path"])).stem != "room_tone"
        ]
        all_sfx = [
            {"t_s": ev["t_s"], "path": sfx_dir / ev["sfx"], "gain_db": ev["gain_db"], "pan": 0.0}
            for ev in events
            if not any(abs(float(ev["t_s"]) - st) <= 0.18 for st in synth_transient_times)
        ] + extra_fx
        for ev in all_sfx:
            if ev.get("loop_bed"):
                cmd.extend(["-stream_loop", "-1", "-i", str(ev["path"])])
            else:
                cmd.extend(["-i", str(ev["path"])])

        chains = [
            "[0:a]aresample=48000,aformat=channel_layouts=stereo,highpass=f=75,asplit=2[vo_dry][vo_sc_raw]",
            f"[vo_sc_raw]apad,atrim=0:{duration_s:.3f}[vo_sc]",
            f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{duration_s:.3f},"
            f"volume={bgm_gain_db:.1f}dB[bgm_raw]",
            build_psychoacoustic_bgm_chain("[bgm_raw]", "[vo_sc]", "[bgm_bus]", carve_strength=0.9),
        ]
        mix_inputs = ["[vo_dry]", "[bgm_bus]"]
        if all_sfx:
            sfx_tags: list[str] = []
            for idx, ev in enumerate(all_sfx):
                inp = idx + 2
                ms = round(ev["t_s"] * 1000)
                tag = f"[s{idx}]"
                pan_part = (
                    f",{pan_to_ffmpeg_filter(float(ev['pan']))}"
                    if abs(float(ev.get("pan") or 0.0)) > 0.01
                    else ""
                )
                extra_f = ""
                if ev.get("loop_bed"):
                    amb_out = max(0.0, duration_s - 1.0)
                    extra_f = (
                        f",atrim=0:{duration_s:.3f},highpass=f=90,lowpass=f=4500,"
                        f"afade=t=in:st=0:d=0.6,afade=t=out:st={amb_out:.3f}:d=1.0"
                    )
                else:
                    if ev.get("trim_s") is not None:
                        tr = float(ev["trim_s"])
                        extra_f += f",atrim=0:{tr:.3f}"
                        if ev.get("fade_out_s") is not None:
                            fo = float(ev["fade_out_s"])
                            extra_f += f",afade=t=out:st={max(0.0, tr - fo):.3f}:d={fo:.3f}"
                chains.append(
                    f"[{inp}:a]aresample=48000,aformat=channel_layouts=stereo"
                    f"{extra_f}{pan_part},volume={ev['gain_db']:.1f}dB,adelay={ms}|{ms}{tag}"
                )
                sfx_tags.append(tag)
            if len(sfx_tags) == 1:
                mix_inputs.append(sfx_tags[0])
            else:
                chains.append(
                    f"{''.join(sfx_tags)}amix=inputs={len(sfx_tags)}:duration=longest:normalize=0[sfx_bus]"
                )
                mix_inputs.append("[sfx_bus]")

        chains.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:normalize=0,"
            f"apad,atrim=0:{duration_s:.3f}[mixed_a]"
        )
        pre_wav = tmp_path / "pre_norm.wav"
        cmd.extend(
            [
                "-filter_complex",
                ";".join(chains),
                "-map",
                "[mixed_a]",
                "-t",
                f"{duration_s:.3f}",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_f32le",
                str(pre_wav),
            ]
        )
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            err_tail = (proc.stderr or "").strip().splitlines()[-12:]
            raise RuntimeError(
                f"ffmpeg mix-audio failed (exit {proc.returncode}): " + " | ".join(err_tail)
            )

        # Two-pass linear loudnorm (measure -> linear scale + true-peak limiter).
        pass1 = subprocess.run(
            [
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
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if pass1.returncode != 0:
            err_tail = (pass1.stderr or "").strip().splitlines()[-8:]
            raise RuntimeError(
                f"ffmpeg loudnorm pass 1 failed (exit {pass1.returncode}): " + " | ".join(err_tail)
            )
        meas = _parse_loudnorm_json(pass1.stderr)
        can_two_pass = meas is not None and all(
            _is_finite_loudnorm_val(v)
            for v in (
                meas.input_i,
                meas.input_tp,
                meas.input_lra,
                meas.input_thresh,
                meas.target_offset,
            )
        )
        lim_db = round(min(prof.max_true_peak_dbtp - 0.35, -1.35), 2)
        af_pass2 = (
            (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                f"measured_I={meas.input_i}:measured_TP={meas.input_tp}:"
                f"measured_LRA={meas.input_lra}:measured_thresh={meas.input_thresh}:"
                f"offset={meas.target_offset}:linear=true:print_format=summary,"
                f"alimiter=limit={lim_db:.2f}dB:level=disabled"
            )
            if can_two_pass and meas is not None
            else (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra},"
                f"alimiter=limit={lim_db:.2f}dB:level=disabled"
            )
        )
        pass2 = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(pre_wav),
                "-af",
                af_pass2,
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if pass2.returncode != 0:
            err_tail = (pass2.stderr or "").strip().splitlines()[-12:]
            raise RuntimeError(
                f"ffmpeg mix-audio loudnorm pass 2 failed (exit {pass2.returncode}): "
                + " | ".join(err_tail)
            )

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "out_file": str(out_path),
                "duration_s": round(duration_s, 3),
                "sfx_count": len(events),
                "riser_count": used_risers,
                "drone_count": used_drones,
                "impact_count": used_impacts,
                "stinger_count": used_stingers,
                "whoosh_count": used_whooshes,
                "silence_dropouts": len(cues["silence_dropouts"]),
                "room_tone_enabled": room_tone,
                "synthetic_bgm_fallback": synthetic_fallback_used,
                "cue_clustering_warnings": cues.get("cue_clustering_warnings") or [],
                "two_pass_loudnorm": can_two_pass,
                "loudness_profile": lp_key,
                "bgm_source": bgm_source_label,
            },
            indent=2,
        )
    )


