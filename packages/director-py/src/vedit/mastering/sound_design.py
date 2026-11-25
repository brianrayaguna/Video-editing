"""Procedural sound design, 4-layer SFX filtering, psychoacoustic mix, and loudness profiles."""

from __future__ import annotations

import array
import math
import random
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from vedit.models import AudioTrackOp, PlatformTarget


@dataclass(frozen=True, slots=True)
class LoudnessProfile:
    """Target loudness envelope for a delivery destination."""

    name: str
    target_lufs: float
    max_true_peak_dbtp: float
    target_lra: float
    tolerance: float


LOUDNESS_PROFILES: dict[str, LoudnessProfile] = {
    "streaming_web": LoudnessProfile(
        name="streaming_web",
        target_lufs=-14.0,
        max_true_peak_dbtp=-1.0,
        target_lra=7.0,
        tolerance=0.5,
    ),
    "podcast_video": LoudnessProfile(
        name="podcast_video",
        target_lufs=-16.0,
        max_true_peak_dbtp=-1.0,
        target_lra=7.0,
        tolerance=0.5,
    ),
    "broadcast_ebu_r128": LoudnessProfile(
        name="broadcast_ebu_r128",
        target_lufs=-23.0,
        max_true_peak_dbtp=-1.0,
        target_lra=10.0,
        tolerance=0.5,
    ),
    "cinema_trailer": LoudnessProfile(
        name="cinema_trailer",
        target_lufs=-18.0,
        max_true_peak_dbtp=-1.0,
        target_lra=12.0,
        tolerance=1.0,
    ),
    "broadcast_atsc_a85": LoudnessProfile(
        name="broadcast_atsc_a85",
        target_lufs=-24.0,
        max_true_peak_dbtp=-2.0,
        target_lra=10.0,
        tolerance=0.5,
    ),
    "cinema_streaming_dialogue": LoudnessProfile(
        name="cinema_streaming_dialogue",
        target_lufs=-27.0,
        max_true_peak_dbtp=-2.0,
        target_lra=14.0,
        tolerance=1.0,
    ),
}


def resolve_loudness_profile(
    name: str | None,
    fallback: PlatformTarget,
) -> tuple[float, float, float, float]:
    """Return `(target_lufs, max_true_peak_dbtp, target_lra, lufs_tolerance)`."""
    if name is None or not name.strip():
        a = fallback.audio
        return (a.target_lufs, a.max_true_peak_dbtp, a.target_lra, a.lufs_tolerance)
    key = name.strip().lower()
    if key not in LOUDNESS_PROFILES:
        valid = ", ".join(sorted(LOUDNESS_PROFILES))
        raise ValueError(f"Unknown loudness profile {name!r}; expected one of: {valid}")
    p = LOUDNESS_PROFILES[key]
    return (p.target_lufs, p.max_true_peak_dbtp, p.target_lra, p.tolerance)


def _write_stereo_wav(
    out_wav: Path,
    samples_lr: list[tuple[float, float]],
    *,
    sample_rate: int = 48000,
) -> Path:
    buf = array.array("h", [0] * (len(samples_lr) * 2))
    for i, (left, right) in enumerate(samples_lr):
        cl = max(-0.98, min(0.98, left))
        cr = max(-0.98, min(0.98, right))
        buf[i * 2] = int(cl * 32767.0)
        buf[i * 2 + 1] = int(cr * 32767.0)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(buf.tobytes())
    return out_wav


def synthesize_shepard_riser(
    duration_s: float,
    out_wav: Path,
    *,
    sample_rate: int = 48000,
    base_hz: float = 110.0,
    octaves: int = 5,
    rise_octaves_per_s: float = 0.55,
) -> Path:
    """Synthesize an endlessly ascending octave-layered riser for tension transitions."""
    dur = max(0.25, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    two_pi = 2.0 * math.pi
    center_oct = (octaves - 1) * 0.5
    sigma_oct = max(0.7, octaves * 0.28)
    phases = [0.0] * max(1, octaves)
    samples: list[tuple[float, float]] = []

    for i in range(n):
        t = i / sample_rate
        u = min(1.0, t / max(dur, 1e-6))
        swell = (u**1.6) * (0.35 + 0.65 * u)
        # Short 12 ms tail ramp to prevent a click at cut boundary.
        tail_ramp = min(1.0, (n - i) / max(1, int(0.012 * sample_rate)))
        head_ramp = min(1.0, i / max(1, int(0.04 * sample_rate)))
        env = swell * tail_ramp * head_ramp

        val_l = 0.0
        val_r = 0.0
        for k in range(max(1, octaves)):
            oct_pos = (k + t * rise_octaves_per_s) % octaves
            freq = base_hz * (2.0**oct_pos)
            weight = math.exp(-0.5 * ((oct_pos - center_oct) / sigma_oct) ** 2)
            phases[k] += two_pi * freq / sample_rate
            # Subtle stereo detune across octave harmonics while keeping strong mono sum.
            val_l += weight * math.sin(phases[k])
            val_r += weight * math.sin(phases[k] + 0.08 * (k % 2))

        norm = 0.22 / max(1.0, math.sqrt(octaves))
        samples.append((val_l * norm * env, val_r * norm * env))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_tension_drone(
    duration_s: float,
    out_wav: Path,
    *,
    sample_rate: int = 48000,
    fundamental_hz: float = 55.0,
    dissonance: float = 0.25,
) -> Path:
    """Synthesize a low-end sub foundation + beating harmonic drone for mood dips."""
    dur = max(0.3, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    two_pi = 2.0 * math.pi
    fade_n = max(1, int(min(0.25, dur * 0.2) * sample_rate))
    detune = 1.0 + 0.008 * max(0.0, min(1.0, dissonance))
    tritone_ratio = 1.4142  # Subtle dissonant interval above octave
    samples: list[tuple[float, float]] = []

    for i in range(n):
        t = i / sample_rate
        env = min(1.0, i / fade_n) * min(1.0, (n - i) / fade_n)
        breath = 0.78 + 0.22 * math.sin(two_pi * 0.35 * t)
        sub = 0.36 * math.sin(two_pi * fundamental_hz * t)
        # Warm 2nd harmonic ensures mobile speakers perceive bass depth via missing fundamental.
        warm = 0.16 * math.sin(two_pi * (fundamental_hz * 2.0) * t)
        beat_l = 0.10 * math.sin(two_pi * (fundamental_hz * 3.0) * t)
        beat_r = 0.10 * math.sin(two_pi * (fundamental_hz * 3.0 * detune) * t + 0.2)
        tens = (
            0.05
            * dissonance
            * math.sin(two_pi * (fundamental_hz * 2.0 * tritone_ratio) * t)
        )
        left = (sub + warm + beat_l + tens) * breath * env
        right = (sub + warm + beat_r + tens) * breath * env
        samples.append((left, right))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_four_layer_impact(
    out_wav: Path,
    *,
    sample_rate: int = 48000,
    character: Literal["verdict", "reveal", "transition"] = "verdict",
    seed: int = 17,
) -> Path:
    """Synthesize a transient-aligned 4-layer impact (sub, body, detail, tail)."""
    dur = 0.95 if character == "verdict" else 0.75 if character == "reveal" else 0.55
    n = max(1, math.ceil(dur * sample_rate))
    rng = random.Random(seed)
    two_pi = 2.0 * math.pi

    sub_f0 = 105.0 if character == "verdict" else 130.0
    sub_f1 = 46.0 if character == "verdict" else 58.0
    body_f = 290.0 if character == "verdict" else 420.0 if character == "reveal" else 340.0
    tail_decay = 4.2 if character == "verdict" else 5.8

    phase_sub = 0.0
    phase_harm = 0.0
    prev_noise = 0.0
    samples: list[tuple[float, float]] = []

    for i in range(n):
        t = i / sample_rate
        # Frame-0 transient alignment across all 4 roles (attack <= 2 ms).
        attack = min(1.0, i / max(1, int(0.002 * sample_rate)))

        # 1. Sub: pitch-drop sine + soft 2nd-harmonic warmth for equal-loudness mobile audibility.
        f_sub = sub_f1 + (sub_f0 - sub_f1) * math.exp(-t * 28.0)
        phase_sub += two_pi * f_sub / sample_rate
        phase_harm += two_pi * (f_sub * 2.0) / sample_rate
        sub_env = attack * math.exp(-t * 6.2)
        sub_sig = (0.42 * math.sin(phase_sub) + 0.14 * math.sin(phase_harm)) * sub_env

        # 2. Body: midrange punch (220-900 Hz)
        body_env = attack * math.exp(-t * 14.0)
        body_sig = 0.24 * math.sin(two_pi * body_f * t) * body_env

        # 3. Detail: high-frequency crisp click/snap (differentiated white noise HPF).
        white = rng.uniform(-1.0, 1.0)
        hp_noise = white - prev_noise
        prev_noise = white
        detail_env = attack * math.exp(-t * 36.0)
        detail_sig = 0.14 * hp_noise * detail_env

        # 4. Tail: subtle stereo-decorrelated room decay.
        tail_env = min(1.0, t / 0.018) * math.exp(-t * tail_decay)
        tail_l = 0.09 * math.sin(two_pi * (body_f * 0.68) * t + 0.1) * tail_env
        tail_r = 0.09 * math.sin(two_pi * (body_f * 0.69) * t + 0.55) * tail_env

        out_fade = min(1.0, (n - i) / max(1, int(0.025 * sample_rate)))
        left = (sub_sig + body_sig + detail_sig + tail_l) * out_fade
        right = (sub_sig + body_sig + detail_sig + tail_r) * out_fade
        samples.append((left, right))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_room_tone_bed(
    duration_s: float,
    out_wav: Path,
    *,
    sample_rate: int = 48000,
    level_db: float = -48.0,
    seed: int = 42,
) -> Path:
    """Synthesize a continuous filtered room-tone floor to bridge speech edits naturally."""
    dur = max(0.25, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    rng = random.Random(seed)
    gain = 10.0 ** (level_db / 20.0)
    lp_l = 0.0
    lp_r = 0.0
    fade_n = max(1, int(min(0.15, dur * 0.2) * sample_rate))
    samples: list[tuple[float, float]] = []

    for i in range(n):
        env = min(1.0, i / fade_n) * min(1.0, (n - i) / fade_n)
        w = rng.uniform(-1.0, 1.0)
        lp_l = 0.92 * lp_l + 0.08 * w
        lp_r = 0.92 * lp_r + 0.08 * (w * 0.85 + rng.uniform(-0.15, 0.15))
        samples.append((lp_l * gain * env, lp_r * gain * env))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_whoosh(
    duration_s: float,
    out_wav: Path,
    *,
    direction: Literal["in", "out"] = "in",
    pitch_start_hz: float = 280.0,
    pitch_end_hz: float = 1150.0,
    sample_rate: int = 48000,
    seed: int = 23,
) -> Path:
    """Synthesize a Doppler bandpass-swept whoosh transition (inward or outward)."""
    dur = max(0.18, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    rng = random.Random(seed)
    two_pi = 2.0 * math.pi
    f0 = pitch_start_hz if direction == "in" else pitch_end_hz
    f1 = pitch_end_hz if direction == "in" else pitch_start_hz
    phase = 0.0
    lp = 0.0
    prev_lp = 0.0
    samples: list[tuple[float, float]] = []

    for i in range(n):
        t = i / sample_rate
        u = min(1.0, t / max(dur, 1e-6))
        bell = math.sin(math.pi * u) ** 1.35
        freq = f0 + (f1 - f0) * (u if direction == "in" else u**0.8)
        phase += two_pi * freq / sample_rate
        alpha = min(0.85, max(0.05, (two_pi * freq) / (sample_rate + two_pi * freq)))
        noise = rng.uniform(-1.0, 1.0)
        lp = (1.0 - alpha) * lp + alpha * noise
        bp = lp - prev_lp
        prev_lp = lp
        pan_shift = (u - 0.5) * 0.35 * (1.0 if direction == "in" else -1.0)
        gl = math.sqrt(max(0.05, 0.5 - pan_shift))
        gr = math.sqrt(max(0.05, 0.5 + pan_shift))
        core = (0.34 * bp + 0.16 * math.sin(phase)) * bell
        samples.append((core * gl, core * gr))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_stinger(
    out_wav: Path,
    *,
    style: Literal["reveal", "twist", "accent"] = "reveal",
    duration_s: float = 0.65,
    sample_rate: int = 48000,
) -> Path:
    """Synthesize a sharp harmonic accent/pivot stinger synchronized to narrative hinges."""
    dur = max(0.25, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    two_pi = 2.0 * math.pi
    ratios = (
        (220.0, 277.18, 329.63)
        if style == "reveal"
        else (196.0, 277.18, 392.0)
        if style == "twist"
        else (293.66, 440.0, 587.33)
    )
    decay = 5.2 if style == "accent" else 3.8
    samples: list[tuple[float, float]] = []

    for i in range(n):
        t = i / sample_rate
        attack = min(1.0, i / max(1, int(0.004 * sample_rate)))
        env = attack * math.exp(-t * decay)
        out_fade = min(1.0, (n - i) / max(1, int(0.02 * sample_rate)))
        s_l = 0.0
        s_r = 0.0
        for idx, hz in enumerate(ratios):
            det = 1.0 + 0.003 * (idx - 1)
            s_l += 0.18 * math.sin(two_pi * hz * t)
            s_r += 0.18 * math.sin(two_pi * hz * det * t + 0.12 * idx)
        samples.append((s_l * env * out_fade, s_r * env * out_fade))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_granular_pad(
    duration_s: float,
    out_wav: Path,
    *,
    base_hz: float = 110.0,
    grain_ms: float = 45.0,
    density_hz: float = 24.0,
    seed: int = 31,
    sample_rate: int = 48000,
) -> Path:
    """Synthesize a Hann-windowed overlapping micro-grain atmospheric pad."""
    dur = max(0.3, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    rng = random.Random(seed)
    two_pi = 2.0 * math.pi
    grain_n = max(16, int((max(15.0, grain_ms) / 1000.0) * sample_rate))
    hop_n = max(8, int(sample_rate / max(4.0, density_hz)))
    partials = (1.0, 1.5, 2.0, 2.5)
    buf_l = [0.0] * n
    buf_r = [0.0] * n

    for start in range(0, n, hop_n):
        ratio = rng.choice(partials)
        freq = base_hz * ratio * (1.0 + rng.uniform(-0.006, 0.006))
        phase0 = rng.uniform(0.0, two_pi)
        pan_pos = rng.uniform(-0.35, 0.35)
        gl = 0.22 * math.sqrt(max(0.1, 0.5 - pan_pos * 0.5))
        gr = 0.22 * math.sqrt(max(0.1, 0.5 + pan_pos * 0.5))
        end_idx = min(n, start + grain_n)
        for j in range(start, end_idx):
            local = (j - start) / max(1, grain_n - 1)
            win = 0.5 * (1.0 - math.cos(two_pi * local))
            sig = math.sin(phase0 + two_pi * freq * (j / sample_rate)) * win
            buf_l[j] += sig * gl
            buf_r[j] += sig * gr

    fade_n = max(1, int(min(0.25, dur * 0.2) * sample_rate))
    samples: list[tuple[float, float]] = []
    for i in range(n):
        env = min(1.0, i / fade_n) * min(1.0, (n - i) / fade_n)
        samples.append((buf_l[i] * env, buf_r[i] * env))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def synthesize_ambience_layers(
    duration_s: float,
    out_wav: Path,
    *,
    layers: int = 3,
    crossfade_s: float = 0.35,
    level_db: float = -34.0,
    seed: int = 53,
    sample_rate: int = 48000,
) -> Path:
    """Synthesize 2-4 frequency-separated background ambience layers with smooth loop crossfade."""
    dur = max(0.5, float(duration_s))
    n = max(1, math.ceil(dur * sample_rate))
    layer_cnt = max(2, min(4, int(layers)))
    rng = random.Random(seed)
    gain = 10.0 ** (level_db / 20.0)
    xfade_n = max(1, min(n // 3, int(max(0.05, crossfade_s) * sample_rate)))

    raw_l = [0.0] * n
    raw_r = [0.0] * n
    band_alphas = (0.04, 0.16, 0.42, 0.72)[:layer_cnt]
    for idx, alpha in enumerate(band_alphas):
        lp_l = 0.0
        lp_r = 0.0
        prev_l = 0.0
        prev_r = 0.0
        weight = 1.0 / math.sqrt(layer_cnt)
        for i in range(n):
            wl = rng.uniform(-1.0, 1.0)
            wr = 0.65 * wl + 0.35 * rng.uniform(-1.0, 1.0)
            lp_l = (1.0 - alpha) * lp_l + alpha * wl
            lp_r = (1.0 - alpha) * lp_r + alpha * wr
            if idx == 0:
                sig_l, sig_r = lp_l, lp_r
            else:
                sig_l = lp_l - prev_l * 0.5
                sig_r = lp_r - prev_r * 0.5
            prev_l, prev_r = lp_l, lp_r
            raw_l[i] += sig_l * weight * gain
            raw_r[i] += sig_r * weight * gain

    # Equal-power seam blend across start/end overlap window so looped playback stays continuous.
    samples: list[tuple[float, float]] = []
    for i in range(n):
        if i < xfade_n and n > xfade_n * 2:
            tail_idx = n - xfade_n + i
            u = i / max(1, xfade_n)
            a_in = math.sin(u * math.pi * 0.5)
            a_out = math.cos(u * math.pi * 0.5)
            samples.append(
                (
                    raw_l[i] * a_in + raw_l[tail_idx] * a_out,
                    raw_r[i] * a_in + raw_r[tail_idx] * a_out,
                )
            )
        elif i >= n - xfade_n and n > xfade_n * 2:
            fade = max(0.0, (n - i) / max(1, xfade_n))
            samples.append((raw_l[i] * fade, raw_r[i] * fade))
        else:
            samples.append((raw_l[i], raw_r[i]))

    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def _section_intensity_at(
    t: float,
    duration_s: float,
    section_timeline: list[dict[str, Any]] | None,
) -> tuple[float, float]:
    """Return `(pad_intensity, ostinato_drive)` in `[0.3, 1.3]` for timestamp `t`."""
    if section_timeline:
        for sec in section_timeline:
            s0 = float(sec.get("start_s", 0.0))
            s1 = float(sec.get("end_s", duration_s))
            if s0 <= t <= s1:
                kind = str(sec.get("section", "body")).lower()
                if kind == "hook":
                    return (0.90, 0.85)
                if kind == "setup":
                    return (0.72, 0.45)
                if kind == "escalation":
                    frac = (t - s0) / max(s1 - s0, 1e-6)
                    return (0.85 + 0.25 * frac, 0.70 + 0.45 * frac)
                if kind == "climax":
                    return (1.15, 1.20)
                if kind == "outro":
                    return (0.65, 0.35)
                return (0.82, 0.62)

    ratio = t / max(duration_s, 1e-6)
    if ratio < 0.14:
        return (0.90, 0.80)
    if ratio < 0.65:
        return (0.78, 0.55)
    if ratio < 0.88:
        frac = (ratio - 0.65) / 0.23
        return (0.85 + 0.30 * frac, 0.70 + 0.48 * frac)
    return (0.70, 0.40)


def synthesize_narrative_bgm(
    duration_s: float,
    out_wav: Path,
    *,
    sample_rate: int = 48000,
    bpm: float = 96.0,
    section_timeline: list[dict[str, Any]] | None = None,
    silence_dropouts: list[tuple[float, float]] | None = None,
) -> Path:
    """Synthesize a section-adaptive documentary BGM bed with ostinato pulse and silence cutouts."""
    dur = max(0.5, float(duration_s))
    n_samples = max(1, math.ceil(dur * sample_rate))
    # D minor documentary progression: Dm -> Bb -> F -> C
    chords = [
        (73.42, 146.83, 174.61, 220.00),
        (58.27, 116.54, 174.61, 233.08),
        (87.31, 130.81, 174.61, 220.00),
        (65.41, 130.81, 164.81, 196.00),
    ]
    beat_s = 60.0 / max(40.0, bpm)
    half_beat_s = beat_s * 0.5
    bar_s = beat_s * 4.0
    two_pi = 2.0 * math.pi
    fade_in_n = max(1, int(min(1.2, dur * 0.08) * sample_rate))
    fade_out_n = max(1, int(min(1.6, dur * 0.12) * sample_rate))
    dropouts = [(float(a), float(b)) for a, b in (silence_dropouts or []) if b > a]
    ramp_s = 0.020

    buf = array.array("h", [0] * (n_samples * 2))
    for i in range(n_samples):
        t = i / sample_rate
        pad_scale, ost_scale = _section_intensity_at(t, dur, section_timeline)

        bar_idx = int(t / bar_s) % len(chords)
        bar_pos = (t % bar_s) / bar_s
        beat_pos = (t % beat_s) / beat_s
        sub_pos = (t % half_beat_s) / half_beat_s
        bass_f, f1, f2, f3 = chords[bar_idx]

        chord_env = min(1.0, bar_pos * 8.0) * min(1.0, (1.0 - bar_pos) * 10.0 + 0.15)
        pulse = 0.62 + 0.38 * math.exp(-beat_pos * 4.5)
        sub = 0.25 * math.sin(two_pi * bass_f * t) * pulse * pad_scale
        # 8th-note rhythmic ostinato intensifies during escalation & climax sections.
        ost_env = math.exp(-sub_pos * 8.5)
        ostinato = 0.06 * ost_scale * math.sin(two_pi * f3 * 2.0 * t) * ost_env

        pad_l = (
            0.13 * math.sin(two_pi * f1 * t)
            + 0.10 * math.sin(two_pi * f2 * t + 0.3)
            + 0.07 * math.sin(two_pi * f3 * t + 0.8)
        ) * chord_env * pad_scale
        pad_r = (
            0.13 * math.sin(two_pi * f1 * t + 0.15)
            + 0.10 * math.sin(two_pi * f2 * t + 0.6)
            + 0.07 * math.sin(two_pi * f3 * t + 1.1)
        ) * chord_env * pad_scale

        env = 1.0
        if i < fade_in_n:
            env *= i / fade_in_n
        if i > n_samples - fade_out_n:
            env *= max(0.0, (n_samples - i) / fade_out_n)

        # Strategic silence drop-outs right before climax/reveal impacts.
        for d0, d1 in dropouts:
            if d0 <= t <= d1:
                if t < d0 + ramp_s:
                    env *= max(0.0, 1.0 - (t - d0) / ramp_s)
                elif t > d1 - ramp_s:
                    env *= max(0.0, 1.0 - (d1 - t) / ramp_s)
                else:
                    env = 0.0
                break

        val_l = max(-0.92, min(0.92, (sub + pad_l + ostinato) * env))
        val_r = max(-0.92, min(0.92, (sub + pad_r + ostinato) * env))
        buf[i * 2] = int(val_l * 32767.0)
        buf[i * 2 + 1] = int(val_r * 32767.0)

    samples = [
        (
            max(-0.92, min(0.92, (buf[i * 2] / 32767.0))),
            max(-0.92, min(0.92, (buf[i * 2 + 1] / 32767.0))),
        )
        for i in range(n_samples)
    ]
    return _write_stereo_wav(out_wav, samples, sample_rate=sample_rate)


def pan_to_ffmpeg_filter(pan: float) -> str:
    """Return constant-power stereo panning FFmpeg filter (`pan` in `[-1.0, 1.0]`)."""
    p = max(-1.0, min(1.0, float(pan)))
    # Map [-1, 1] -> [0, pi/2] for constant-power law.
    angle = (p + 1.0) * 0.25 * math.pi
    g_l = round(math.cos(angle) * 1.4142, 4)
    g_r = round(math.sin(angle) * 1.4142, 4)
    return f"pan=stereo|c0={g_l}*c0|c1={g_r}*c1"


def reverb_preset_to_ffmpeg_filter(preset: str | None) -> str | None:
    """Map spatial depth preset (`dry|close|medium|wide`) to a deterministic `aecho` chain."""
    if not preset or preset == "dry":
        return None
    if preset == "close":
        return "aecho=0.8:0.75:22|38:0.18|0.12"
    if preset == "medium":
        return "aecho=0.8:0.82:45|78|115:0.24|0.18|0.11"
    if preset == "wide":
        return "aecho=0.8:0.86:65|110|165|220:0.28|0.22|0.15|0.09"
    return None


def haas_delay_to_ffmpeg_filter(
    delay_ms: float | None,
    *,
    side: Literal["left", "right"] = "right",
) -> str | None:
    """Return subtle stereo precedence-effect delay (`[5, 25] ms`) preserving mono summation."""
    if delay_ms is None or float(delay_ms) < 4.0:
        return None
    ms = round(max(5.0, min(25.0, float(delay_ms))), 2)
    return f"adelay=0|{ms}" if side == "right" else f"adelay={ms}|0"


def reverb_return_to_ffmpeg_filter(
    preset: str | None,
    *,
    reverb_pan: float | None = None,
) -> str | None:
    """Apply `aecho` reverb with optional directional stereo return balance."""
    base = reverb_preset_to_ffmpeg_filter(preset)
    if base is None:
        return None
    if reverb_pan is None or abs(float(reverb_pan)) <= 0.01:
        return base
    # Keep stereo balance moderate so dialogue clarity and mono fold-down remain intact.
    p = max(-0.65, min(0.65, float(reverb_pan) * 0.65))
    return f"{base},{pan_to_ffmpeg_filter(p)}"


def build_layer_band_filter(track: AudioTrackOp) -> list[str]:
    """Build frequency-separation, fade, panning, Haas, and spatial reverb filters."""
    filters: list[str] = []
    role = track.layer_role
    if track.highpass_hz is not None:
        filters.append(f"highpass=f={track.highpass_hz:.1f}")
    elif role == "body":
        filters.append("highpass=f=130")
    elif role == "detail":
        filters.append("highpass=f=2400")
    elif role == "tail":
        filters.append("highpass=f=180")

    if track.lowpass_hz is not None:
        filters.append(f"lowpass=f={track.lowpass_hz:.1f}")
    elif role == "sub":
        filters.append("lowpass=f=140")
    elif role == "body":
        filters.append("lowpass=f=2800")

    fade_in = float(track.fade_in_s or 0.0)
    fade_out = float(track.fade_out_s or 0.0)
    if fade_in > 0.002:
        dur_in = min(fade_in, track.timeline_duration_s * 0.45)
        filters.append(f"afade=t=in:st=0:d={dur_in:.4f}")
    if fade_out > 0.002:
        dur_out = min(fade_out, track.timeline_duration_s * 0.45)
        st_out = max(0.0, track.timeline_duration_s - dur_out)
        filters.append(f"afade=t=out:st={st_out:.4f}:d={dur_out:.4f}")

    if track.audio_group != "voiceover":
        if track.reverb_preset:
            rev = reverb_preset_to_ffmpeg_filter(track.reverb_preset)
            if rev:
                filters.append(rev)
        if track.haas_delay_ms is not None and track.layer_role != "sub":
            haas = haas_delay_to_ffmpeg_filter(track.haas_delay_ms)
            if haas:
                filters.append(haas)
        # Apply a single stereo placement filter so direct pan and reverb bias never stack twice.
        eff_pan = (
            track.pan
            if (track.pan is not None and abs(track.pan) > 0.01)
            else (
                max(-0.65, min(0.65, float(track.reverb_pan) * 0.65))
                if (
                    track.reverb_preset
                    and track.reverb_pan is not None
                    and abs(track.reverb_pan) > 0.01
                )
                else None
            )
        )
        if eff_pan is not None:
            filters.append(pan_to_ffmpeg_filter(eff_pan))
    elif track.reverb_preset:
        rev = reverb_preset_to_ffmpeg_filter(track.reverb_preset)
        if rev:
            filters.append(rev)

    return filters


def build_psychoacoustic_bgm_chain(
    in_label: str,
    vo_sc_label: str,
    out_label: str,
    *,
    carve_strength: float,
    speech_wpm: float | None = None,
) -> str:
    """Build multi-band voice-pocket EQ + WPM-adaptive sidechain ducking filter chain."""
    strength = max(0.0, min(1.0, float(carve_strength)))
    ratio = round(2.0 + strength * 6.0, 2)
    presence_cut = round(-2.8 * strength, 2)
    mud_cut = round(-1.8 * strength, 2)
    # Longer release on rapid narration avoids pumping between tightly spaced words.
    release_ms = 400 if (speech_wpm is not None and speech_wpm >= 170.0) else 260
    return (
        f"{in_label}highpass=f=35,"
        f"equalizer=f=380:t=o:w=1.0:g={mud_cut},"
        f"equalizer=f=2400:t=o:w=1.3:g={presence_cut}[bgm_eq];"
        f"[bgm_eq]{vo_sc_label}sidechaincompress=threshold=0.025:ratio={ratio}"
        f":attack=12:release={release_ms}:makeup=1{out_label}"
    )


def plan_narrative_audio_cues(
    spec: dict[str, Any],
    *,
    storyboard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive risers, drones, impacts, stingers, whooshes, ambience, and clustering warnings."""
    risers: list[dict[str, Any]] = []
    drones: list[dict[str, Any]] = []
    impacts: list[dict[str, Any]] = []
    stingers: list[dict[str, Any]] = []
    whooshes: list[dict[str, Any]] = []
    ambience: list[dict[str, Any]] = []
    silence_dropouts: list[tuple[float, float]] = []
    section_timeline: list[dict[str, Any]] = []

    time_offset = 0.0
    for act in spec.get("acts") or []:
        dur = float(act.get("duration_s", 0.0))
        for kf in act.get("camera_keyframes") or []:
            if not isinstance(kf, dict):
                continue
            curve = str(kf.get("curve") or "")
            tk = float(kf.get("t", kf.get("t_s", 0.0)))
            abs_t = time_offset + tk
            if curve in ("snap_dive", "hyperbolic_fly") and abs_t >= 0.85:
                r_dur = 0.85 if curve == "snap_dive" else 1.05
                risers.append(
                    {
                        "start_s": round(max(0.0, abs_t - r_dur), 3),
                        "duration_s": r_dur,
                        "gain_db": -16.5,
                    }
                )
                whooshes.append(
                    {
                        "start_s": round(max(0.0, abs_t - 0.12), 3),
                        "duration_s": 0.42,
                        "direction": "in" if curve == "snap_dive" else "out",
                        "gain_db": -15.0,
                    }
                )
        for layer in act.get("layers") or []:
            ltype = str(layer.get("type") or "")
            t0 = time_offset + float(layer.get("start_s", 0.0))
            if ltype in ("crimson_x", "void_wipe") and t0 >= 0.35:
                silence_dropouts.append((round(t0 - 0.22, 3), round(t0 - 0.02, 3)))
                impacts.append(
                    {
                        "start_s": round(t0, 3),
                        "character": "verdict" if ltype == "crimson_x" else "transition",
                        "gain_db": -13.5,
                        "pan": 0.0,
                    }
                )
            elif ltype == "model_3d":
                impacts.append(
                    {
                        "start_s": round(t0, 3),
                        "character": "reveal",
                        "gain_db": -14.5,
                        "pan": 0.0,
                    }
                )
            elif ltype in ("cable_3d", "volume_3d"):
                whooshes.append(
                    {
                        "start_s": round(t0, 3),
                        "duration_s": 0.38,
                        "direction": "in",
                        "gain_db": -15.5,
                    }
                )
        time_offset += dur

    if storyboard:
        for beat in storyboard.get("beats") or []:
            b_start = float(beat.get("start_s", 0.0))
            b_end = float(beat.get("end_s", b_start + 0.5))
            func = str(beat.get("function") or "body")
            section_timeline.append(
                {"start_s": b_start, "end_s": b_end, "section": func}
            )
            cue = beat.get("sound_cue") or {}
            cue_fn = str(cue.get("function") or "")
            pan_pct = cue.get("pan_x_pct")
            pan_val = (
                round(max(-1.0, min(1.0, (float(pan_pct) - 50.0) / 50.0)), 3)
                if pan_pct is not None
                else 0.0
            )
            blocking = beat.get("blocking") or {}
            cam_move = str(blocking.get("camera_move") or "")
            if cam_move == "whip_pan" and b_start >= 0.15:
                whooshes.append(
                    {
                        "start_s": round(max(0.0, b_start - 0.08), 3),
                        "duration_s": 0.35,
                        "direction": "in",
                        "gain_db": -14.5,
                    }
                )
            if cue_fn == "riser" and b_start >= 0.5:
                r_dur = min(1.0, max(0.5, b_end - b_start))
                risers.append(
                    {
                        "start_s": round(max(0.0, b_start - 0.1), 3),
                        "duration_s": round(r_dur, 3),
                        "gain_db": -15.5,
                    }
                )
            elif cue_fn == "drone" and b_end - b_start >= 0.6:
                cmood = str(beat.get("color_mood") or "")
                drones.append(
                    {
                        "start_s": round(b_start, 3),
                        "duration_s": round(b_end - b_start, 3),
                        "gain_db": -22.0,
                        "texture": "granular" if cmood == "dread_dim_vignette" else "harmonic",
                    }
                )
            elif cue_fn == "ambience" and b_end - b_start >= 0.6:
                ambience.append(
                    {
                        "start_s": round(b_start, 3),
                        "duration_s": round(b_end - b_start, 3),
                        "gain_db": -26.0,
                        "pan": pan_val,
                    }
                )
            elif cue_fn == "stinger" or func == "hinge":
                stingers.append(
                    {
                        "start_s": round(b_start, 3),
                        "style": "twist" if func == "hinge" else "reveal",
                        "gain_db": -15.5,
                    }
                )
            elif cue_fn == "impact" or cue_fn == "hit" or func == "climax":
                impacts.append(
                    {
                        "start_s": round(b_start, 3),
                        "character": "verdict" if func == "climax" else "reveal",
                        "gain_db": -13.0,
                        "pan": pan_val,
                    }
                )
            if cue_fn == "silence_dropout" or (func == "climax" and b_start >= 0.4):
                drop_ms = float(cue.get("silence_dropout_ms") or 220.0)
                drop_s = min(0.5, max(0.12, drop_ms / 1000.0))
                if b_start >= drop_s + 0.05:
                    silence_dropouts.append(
                        (round(b_start - drop_s, 3), round(b_start - 0.02, 3))
                    )

    # Deduplicate overlapping silence dropouts cleanly.
    silence_dropouts.sort()
    merged_drops: list[tuple[float, float]] = []
    for a, b in silence_dropouts:
        if not merged_drops or a > merged_drops[-1][1] + 0.35:
            merged_drops.append((a, b))

    # Flag excessive beat-for-beat cue clustering (>6 discrete cues inside 4.0 s window).
    cue_times = sorted(
        [c["start_s"] for c in risers]
        + [c["start_s"] for c in impacts]
        + [c["start_s"] for c in stingers]
        + [c["start_s"] for c in whooshes]
    )
    clustering_warnings: list[str] = []
    for idx, t0 in enumerate(cue_times):
        end_idx = idx
        while end_idx < len(cue_times) and cue_times[end_idx] - t0 <= 4.0:
            end_idx += 1
        count_in_win = end_idx - idx
        if count_in_win > 6:
            clustering_warnings.append(
                f"excessive SFX clustering ({count_in_win} cues in 4.0s starting at t={t0:.2f}s)"
            )
            break

    return {
        "risers": risers[:8],
        "drones": drones[:6],
        "impacts": impacts[:8],
        "stingers": stingers[:6],
        "whooshes": whooshes[:8],
        "ambience": ambience[:4],
        "silence_dropouts": merged_drops[:6],
        "section_timeline": section_timeline,
        "cue_clustering_warnings": clustering_warnings,
    }
