"""Multi-reference BrandStylePolicy synthesis, editorial playbook aids, and calibration.

Runtime policies carry soft priors, hard guardrails, calibration, and provenance.
Advisory grammar triggers and exemplars are emitted separately as EditorialPlaybook.
When `VideoBreakdownResult` telemetry is supplied alongside `MediaProbeResult`,
pacing, transitions, audio tempo/SFX, caption packaging, and multi-aspect overrides
are derived from measured forensic evidence rather than coarse heuristics.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import validate_against_contract
from vedit.metrics import (
    compute_quantiles,
    parse_hex_rgb,
    pick_accent_color,
    pick_accessible_ink,
    relative_luminance,
)
from vedit.models import (
    AudioStyleTokens,
    BrandFormatOverride,
    BrandProvenance,
    BrandStylePolicy,
    EditorialPlaybook,
    GrammarTrigger,
    HardGuardrails,
    MediaProbeResult,
    MotionStyleTokens,
    NormalizedTranscript,
    PaletteRoles,
    ProbeKeyframeInfo,
    SoftPriors,
    StyleCalibration,
    StyleExemplar,
    TemporalSectionPrior,
    TypographyTokens,
    VideoBreakdownResult,
    VisualTokens,
)
from vedit.ports.decision import DecisionPort, DecisionQuestion, ImageInput, validate_decision_batch

SectionName = Literal["hook", "setup", "body", "escalation", "climax", "outro"]
ExemplarRole = Literal[
    "hook", "setup", "proof", "data_callout", "broll_bridge", "climax", "outro"
]
CanonicalAspect = Literal["16:9", "9:16", "1:1", "4:5"]

_SECTION_BOUNDS: tuple[tuple[SectionName, float, float, float], ...] = (
    ("hook", 0.00, 0.12, 0.72),
    ("setup", 0.12, 0.28, 0.96),
    ("body", 0.28, 0.68, 1.00),
    ("escalation", 0.68, 0.84, 0.84),
    ("climax", 0.84, 0.94, 0.78),
    ("outro", 0.94, 1.01, 1.08),
)

_SECTION_TO_EXEMPLAR_ROLE: dict[SectionName, ExemplarRole] = {
    "hook": "hook",
    "setup": "proof",
    "body": "broll_bridge",
    "escalation": "data_callout",
    "climax": "climax",
    "outro": "outro",
}

_NARRATIVE_TO_SECTION: dict[str, SectionName] = {
    "hook": "hook",
    "context": "setup",
    "info": "body",
    "proof": "body",
    "turn": "escalation",
    "payoff": "climax",
    "cta": "outro",
}

_NARRATIVE_TO_EXEMPLAR_ROLE: dict[str, ExemplarRole] = {
    "hook": "hook",
    "context": "setup",
    "info": "broll_bridge",
    "proof": "proof",
    "turn": "data_callout",
    "payoff": "climax",
    "cta": "outro",
}

_ROLE_TO_HF_PATTERN: dict[ExemplarRole, str] = {
    "hook": "kinetic_hook_title",
    "setup": "context_establishing_card",
    "proof": "lower_third_proof",
    "data_callout": "split_metric_card",
    "broll_bridge": "clean_broll_cut",
    "climax": "impact_stat_overlay",
    "outro": "clean_end_card",
}

_BREAKDOWN_TRANSITION_MAP: dict[str, str] = {
    "cut": "hard_cut",
    "jump": "hard_cut",
    "dissolve": "clean_crossfade",
    "fade": "clean_fade",
    "wipe": "wipe",
}

_ASPECT_FORMAT_NAMES: dict[CanonicalAspect, str] = {
    "9:16": "short_vertical",
    "16:9": "long_landscape",
    "1:1": "square_social",
    "4:5": "portrait_feed",
}


@dataclass(slots=True)
class ReferenceVideoSample:
    """Bundled deterministic telemetry, optional transcript, and optional forensic breakdown."""

    source_video_id: str
    probe: MediaProbeResult
    transcript: NormalizedTranscript | None = None
    breakdown: VideoBreakdownResult | None = None
    notes: str | None = None


@dataclass(slots=True)
class BrandSynthesisResult:
    """Runtime policy plus optional advisory playbook from one synthesis pass."""

    policy: BrandStylePolicy
    playbook: EditorialPlaybook


def _classify_section(mid_ratio: float) -> SectionName:
    for name, lo, hi, _ in _SECTION_BOUNDS:
        if lo <= mid_ratio < hi:
            return name
    return "outro"


def _sample_aspect(sample: ReferenceVideoSample) -> CanonicalAspect | None:
    if sample.breakdown and sample.breakdown.aspect_ratio in ("16:9", "9:16", "1:1", "4:5"):
        return sample.breakdown.aspect_ratio  # type: ignore[return-value]
    w, h = sample.probe.video.width, sample.probe.video.height
    if w <= 0 or h <= 0:
        return None
    ratio = w / h
    candidates: list[tuple[float, CanonicalAspect]] = [
        (16.0 / 9.0, "16:9"),
        (9.0 / 16.0, "9:16"),
        (1.0, "1:1"),
        (4.0 / 5.0, "4:5"),
    ]
    dist, label = min((abs(ratio - target), lbl) for target, lbl in candidates)
    return label if dist <= 0.12 else None


def _rgb_approx_chroma(hex_color: str) -> float:
    """Estimate perceptual chroma in `[0, 120]` from sRGB hex when Lab values are absent."""
    r, g, b = parse_hex_rgb(hex_color)
    mean = (r + g + b) / 3.0
    spread = math.sqrt(((r - mean) ** 2 + (g - mean) ** 2 + (b - mean) ** 2) / 3.0)
    return min(120.0, spread * 0.95)


def _weighted_palette(samples: Sequence[ReferenceVideoSample]) -> tuple[PaletteRoles, float]:
    """Derive WCAG-compliant PaletteRoles and mean luminance across probes and breakdowns."""
    color_weights: dict[str, list[float]] = {}
    weighted_lumas: list[tuple[float, float]] = []

    for sample in samples:
        dur = max(sample.probe.container.duration_s, 1.0)
        weighted_lumas.append((sample.probe.visual.mean_luminance, dur))
        for swatch in sample.probe.visual.palette:
            chroma = math.hypot(swatch.lab_a, swatch.lab_b)
            entry = color_weights.setdefault(swatch.hex.upper(), [0.0, chroma])
            entry[0] += swatch.share * dur
            entry[1] = max(entry[1], chroma)

        # Incorporate clean graphic/overlay colors measured on rendered layers without letting
        # sparse strokes overpower the true background ground.
        if sample.breakdown is not None:
            drawn_hexes: list[str] = []
            for shot in sample.breakdown.shots:
                drawn_hexes.extend(shot.drawn_palette_hex)
            if sample.breakdown.packaging.caption_fill_hex:
                drawn_hexes.append(sample.breakdown.packaging.caption_fill_hex)
            for hx in drawn_hexes:
                norm = hx.upper()
                chroma = _rgb_approx_chroma(norm)
                entry = color_weights.setdefault(norm, [0.0, chroma])
                entry[0] += 0.06 * dur
                entry[1] = max(entry[1], chroma)

    total_dur = sum(w for _, w in weighted_lumas) or 1.0
    mean_luma = sum(lum * w for lum, w in weighted_lumas) / total_dur
    dark_brand = mean_luma <= 132.0

    candidates_sorted = sorted(
        color_weights.items(),
        key=lambda kv: (
            kv[1][1],
            relative_luminance(kv[0]) if dark_brand else -relative_luminance(kv[0]),
        ),
    )
    ground = "#0B0F19" if dark_brand else "#F8FAFC"
    for hex_val, (weight, chroma) in candidates_sorted:
        lum = relative_luminance(hex_val)
        if weight > 0 and chroma <= 28.0:
            if (dark_brand and lum < 0.25) or (not dark_brand and lum > 0.55):
                ground = hex_val
                break

    ink_candidates = sorted(color_weights.keys(), key=relative_luminance, reverse=dark_brand)
    # Prefer observed caption fill color as ink candidate when it meets WCAG contrast.
    caption_fills = [
        s.breakdown.packaging.caption_fill_hex.upper()
        for s in samples
        if s.breakdown and s.breakdown.packaging.caption_fill_hex
    ]
    ink = pick_accessible_ink(
        ground,
        min_contrast=4.5,
        candidates=[*caption_fills, *ink_candidates],
    )

    accent_pool = [(hx, meta[1], meta[0] / total_dur) for hx, meta in color_weights.items()]
    accent = pick_accent_color(ground, accent_pool, min_contrast=3.0)
    secondary = pick_accent_color(ground, accent_pool, min_contrast=3.0, exclude_hex=accent)

    return (
        PaletteRoles(ground=ground, ink=ink, accent=accent, secondary_accent=secondary),
        mean_luma,
    )


def _sample_cuts_per_min(sample: ReferenceVideoSample) -> float:
    if sample.breakdown is not None and sample.breakdown.editing.cuts_per_min > 0:
        return sample.breakdown.editing.cuts_per_min
    return sample.probe.shot_stats.cuts_per_min


def _compute_temporal_curve(samples: Sequence[ReferenceVideoSample]) -> list[TemporalSectionPrior]:
    section_durations: dict[SectionName, list[float]] = {name: [] for name, *_ in _SECTION_BOUNDS}
    section_transitions: dict[SectionName, Counter[str]] = {
        name: Counter() for name, *_ in _SECTION_BOUNDS
    }
    global_durations: list[float] = []
    mean_cuts_per_min = 0.0
    pause_cut_ratios: list[float] = []

    for sample in samples:
        bd_dur = (
            sample.breakdown.duration_s
            if sample.breakdown and sample.breakdown.duration_s > 0
            else sample.probe.container.duration_s
        )
        dur = max(bd_dur, 0.1)
        mean_cuts_per_min += _sample_cuts_per_min(sample)

        if sample.breakdown is not None and sample.breakdown.shots:
            if sample.breakdown.editing.cuts_in_pauses_ratio is not None:
                pause_cut_ratios.append(sample.breakdown.editing.cuts_in_pauses_ratio)
            for bshot in sample.breakdown.shots:
                shot_dur = max(bshot.duration_s, 0.25)
                global_durations.append(shot_dur)
                mid_ratio = min(max(((bshot.start_s + bshot.end_s) * 0.5) / dur, 0.0), 0.999)
                if bshot.narrative_role and bshot.narrative_role in _NARRATIVE_TO_SECTION:
                    sec = _NARRATIVE_TO_SECTION[bshot.narrative_role]
                    if bshot.narrative_role == "proof" and mid_ratio >= 0.60:
                        sec = "escalation"
                else:
                    sec = _classify_section(mid_ratio)
                section_durations[sec].append(shot_dur)
                mapped_tr = _BREAKDOWN_TRANSITION_MAP.get(bshot.transition_in)
                if mapped_tr:
                    section_transitions[sec][mapped_tr] += 1
            continue

        if not sample.probe.shots:
            global_durations.append(dur)
            section_durations["body"].append(dur)
            continue
        for shot in sample.probe.shots:
            shot_dur = max(shot.duration_s, 0.25)
            global_durations.append(shot_dur)
            mid_ratio = min(max(((shot.start_s + shot.end_s) * 0.5) / dur, 0.0), 0.999)
            section_durations[_classify_section(mid_ratio)].append(shot_dur)

    mean_cuts_per_min /= max(len(samples), 1)
    g_p25, g_p50, g_p75 = compute_quantiles(global_durations or [2.5])
    base_energy = min(max(mean_cuts_per_min / 36.0, 0.25), 0.95)
    uses_j_cut = bool(
        pause_cut_ratios and (sum(pause_cut_ratios) / len(pause_cut_ratios)) >= 0.45
    )

    curve: list[TemporalSectionPrior] = []
    for name, _, _, scale in _SECTION_BOUNDS:
        bucket = section_durations[name]
        if len(bucket) >= 2:
            p25, p50, p75 = compute_quantiles(bucket)
        elif len(bucket) == 1:
            val = bucket[0]
            p25, p50, p75 = max(0.25, val * 0.8), val, max(val * 1.25, val + 0.1)
        else:
            p25 = max(0.25, g_p25 * scale)
            p50 = max(p25, g_p50 * scale)
            p75 = max(p50, g_p75 * scale)

        low_cpm = round(60.0 / max(p75, 0.25), 2)
        high_cpm = round(60.0 / max(p25, 0.25), 2)
        sec_energy = round(min(max(base_energy / max(scale, 0.5), 0.15), 1.0), 3)

        measured_tr = [t for t, _ in section_transitions[name].most_common(3)]
        if measured_tr:
            transitions = list(measured_tr)
            if uses_j_cut and "j_cut" not in transitions:
                transitions.append("j_cut")
        else:
            transitions = ["hard_cut"] if p50 < 2.2 else ["hard_cut", "j_cut"]
            if name == "outro" and "clean_fade" not in transitions:
                transitions.append("clean_fade")

        curve.append(
            TemporalSectionPrior(
                section=name,
                asl_p25_s=round(p25, 3),
                asl_p50_s=round(p50, 3),
                asl_p75_s=round(p75, 3),
                cuts_per_min_range=[min(low_cpm, high_cpm), max(low_cpm, high_cpm)],
                energy_target=sec_energy,
                preferred_transitions=transitions,
            )
        )
    return curve


def _estimate_speech_wpm(samples: Sequence[ReferenceVideoSample]) -> float:
    words = 0
    spoken_s = 0.0
    for sample in samples:
        if sample.transcript and sample.transcript.words:
            words += sum(1 for w in sample.transcript.words if not w.is_filler)
            spoken_s += max(sample.transcript.duration_s, 1.0)
    if spoken_s > 0.0 and words > 0:
        return (words / spoken_s) * 60.0
    return 145.0


def _synthesize_audio_style(
    samples: Sequence[ReferenceVideoSample],
    *,
    mean_cpm: float,
    mean_silence: float,
) -> AudioStyleTokens:
    """Derive AudioStyleTokens from forensic audio telemetry when available."""
    ducking = round(min(max(0.55 + (1.0 - mean_silence) * 0.35, 0.5), 0.92), 2)
    breakdowns = [s.breakdown for s in samples if s.breakdown is not None]

    if not breakdowns:
        if mean_cpm >= 32.0:
            sfx_policy: Literal["none", "selective_transitions", "kinetic_accents"] = (
                "kinetic_accents"
            )
            moods = ["energetic", "modern", "electronic"]
            bpm_range: list[float] | None = [116.0, 132.0]
        elif mean_cpm >= 14.0:
            sfx_policy = "selective_transitions"
            moods = ["upbeat", "focused", "minimal"]
            bpm_range = [96.0, 118.0]
        elif mean_cpm >= 6.0:
            sfx_policy = "selective_transitions"
            moods = ["documentary", "warm", "ambient"]
            bpm_range = [80.0, 102.0]
        else:
            sfx_policy = "none"
            moods = ["ambient", "calm"]
            bpm_range = [65.0, 88.0]
        return AudioStyleTokens(
            bgm_moods=moods,
            bpm_range=bpm_range,
            ducking_strength=ducking,
            sfx_policy=sfx_policy,
        )

    bpms = [
        b.audio.tempo_bpm
        for b in breakdowns
        if b.audio.has_music and not b.audio.no_beat and b.audio.tempo_bpm is not None
    ]
    if bpms:
        lo_bpm = round(max(40.0, min(bpms) - 8.0), 1)
        hi_bpm = round(min(220.0, max(bpms) + 8.0), 1)
        bpm_range = [lo_bpm, max(lo_bpm, hi_bpm)]
    else:
        bpm_range = None

    total_min = sum(max(b.duration_s, 1.0) for b in breakdowns) / 60.0
    total_aligned_sfx = sum(b.audio.sfx_aligned_to_visual_count for b in breakdowns)
    total_sfx = sum(b.audio.sfx_count for b in breakdowns)
    sfx_rate = total_aligned_sfx / max(total_min, 0.1)
    if sfx_rate >= 4.0:
        sfx_policy = "kinetic_accents"
    elif sfx_rate >= 0.5 or total_aligned_sfx >= 1 or (total_sfx / max(total_min, 0.1)) >= 1.5:
        sfx_policy = "selective_transitions"
    else:
        sfx_policy = "none"

    modes = Counter(b.audio.key_mode for b in breakdowns if b.audio.key_mode)
    dominant_mode = modes.most_common(1)[0][0] if modes else None
    any_beat_sync = any(b.editing.beat_synced_edit for b in breakdowns)
    mean_bpm = (sum(bpms) / len(bpms)) if bpms else None

    if mean_bpm is None:
        moods = (
            ["mysterious", "ambient", "documentary"]
            if dominant_mode == "minor"
            else ["ambient", "documentary", "warm"]
        )
    elif dominant_mode == "minor":
        moods = (
            ["dramatic", "focused", "electronic"]
            if mean_bpm >= 105.0
            else ["mysterious", "suspense", "ambient"]
        )
    elif any_beat_sync or mean_bpm >= 115.0:
        moods = ["energetic", "upbeat", "modern"]
    elif mean_bpm >= 92.0:
        moods = ["upbeat", "focused", "minimal"]
    else:
        moods = ["documentary", "warm", "ambient"]

    return AudioStyleTokens(
        bgm_moods=moods,
        bpm_range=bpm_range,
        ducking_strength=ducking,
        sfx_policy=sfx_policy,
    )


def _synthesize_typography(
    samples: Sequence[ReferenceVideoSample],
    *,
    mean_cpm: float,
    wpm: float,
    decision_caption_case: str | None = None,
) -> TypographyTokens:
    """Derive TypographyTokens from OCR packaging telemetry when available."""
    breakdowns = [s.breakdown for s in samples if s.breakdown is not None]

    case_votes: Counter[Literal["sentence", "uppercase", "title", "lowercase"]] = Counter()
    style_votes: Counter[Literal["plain", "chip", "bar"]] = Counter()
    band_votes: Counter[Literal["lower_third", "center_safe", "upper_safe"]] = Counter()
    words_p75_vals: list[float] = []
    trans_ms_vals: list[float] = []

    for bd in breakdowns:
        pk = bd.packaging
        if pk.caption_case_observed:
            case_votes[pk.caption_case_observed] += max(1, pk.subtitle_count)
        if pk.caption_style_observed:
            style_votes[pk.caption_style_observed] += max(1, pk.subtitle_count)
        if pk.caption_band_observed:
            band_votes[pk.caption_band_observed] += max(1, pk.subtitle_count)
        if pk.caption_words_p75 is not None and pk.caption_words_p75 > 0:
            words_p75_vals.append(pk.caption_words_p75)
        if pk.caption_entrance_ms_median is not None:
            trans_ms_vals.append(float(pk.caption_entrance_ms_median))

    if case_votes:
        cap_case: Literal["sentence", "uppercase", "title", "lowercase"] = case_votes.most_common(
            1
        )[0][0]
    elif decision_caption_case in ("sentence", "uppercase", "title", "lowercase"):
        cap_case = decision_caption_case  # type: ignore[assignment]
    else:
        cap_case = "uppercase" if mean_cpm >= 28.0 else "sentence"

    cap_style: Literal["plain", "chip", "bar"] | None = (
        style_votes.most_common(1)[0][0] if style_votes else None
    )
    cap_band: Literal["lower_third", "center_safe", "upper_safe", "dynamic_away_from_subject"] = (
        band_votes.most_common(1)[0][0] if band_votes else "dynamic_away_from_subject"
    )
    if words_p75_vals:
        max_words = int(min(max(round(compute_quantiles(words_p75_vals)[1]), 1), 12))
    else:
        max_words = 4 if wpm >= 165.0 or mean_cpm >= 26.0 else 6

    cap_trans_ms: int | None = (
        int(min(max(round(compute_quantiles(trans_ms_vals)[1]), 0), 200))
        if trans_ms_vals
        else None
    )

    return TypographyTokens(
        display_family="Inter, sans-serif",
        body_family="Inter, sans-serif",
        caption_case=cap_case,
        caption_style=cap_style,
        caption_transition_ms=cap_trans_ms,
        max_words_per_caption_group=max_words,
        default_caption_band=cap_band,
    )


def _synthesize_motion_style(
    samples: Sequence[ReferenceVideoSample],
    *,
    temporal_curve: Sequence[TemporalSectionPrior],
    mean_cpm: float,
    decision_motion: str | None = None,
) -> MotionStyleTokens:
    """Derive MotionStyleTokens from measured animations, punch-ins, and cut cadence."""
    breakdowns = [s.breakdown for s in samples if s.breakdown is not None]
    anim_counter: Counter[str] = Counter()
    punch_ratios: list[float] = []
    total_punch_ins = 0
    any_beat_sync = False

    for bd in breakdowns:
        anim_counter.update(bd.packaging.caption_entrance_animations)
        punch_ratios.extend(bd.editing.punch_in_scale_ratios)
        total_punch_ins += bd.editing.punch_ins
        any_beat_sync = any_beat_sync or bd.editing.beat_synced_edit

    if mean_cpm >= 32.0 or (any_beat_sync and anim_counter.get("pop", 0) > 0):
        motion_default: Literal[
            "snappy_ease_out", "smooth_editorial", "energetic_pop", "minimal_static"
        ] = "energetic_pop"
        entrance_range = [120, 240]
    elif mean_cpm >= 14.0 or anim_counter.get("pop", 0) > anim_counter.get("fade", 0):
        motion_default = "snappy_ease_out"
        entrance_range = [180, 340]
    elif mean_cpm >= 6.0 or anim_counter.get("fade", 0) > 0:
        motion_default = "smooth_editorial"
        entrance_range = [220, 420]
    else:
        motion_default = "minimal_static"
        entrance_range = [340, 620]

    if decision_motion in (
        "snappy_ease_out",
        "smooth_editorial",
        "energetic_pop",
        "minimal_static",
    ):
        motion_default = decision_motion  # type: ignore[assignment]

    all_asl = [sec.asl_p50_s for sec in temporal_curve]
    if punch_ratios:
        p25, _, p75 = compute_quantiles(punch_ratios)
        punch_range = [
            round(min(max(p25, 1.0), 1.45), 2),
            round(min(max(p75, p25), 1.5), 2),
        ]
    elif breakdowns and total_punch_ins == 0:
        punch_range = [1.0, 1.06]
    else:
        punch_range = [1.04, 1.12] if min(all_asl) < 3.5 else [1.0, 1.06]

    return MotionStyleTokens(
        easing_feel=motion_default,
        entrance_ms_range=entrance_range,
        punch_in_scale_range=punch_range,
    )


def _build_format_overrides(
    samples: Sequence[ReferenceVideoSample],
) -> dict[str, BrandFormatOverride] | None:
    """Emit aspect-conditioned format overrides when references span 2+ aspect ratios."""
    grouped: dict[CanonicalAspect, list[ReferenceVideoSample]] = {}
    for sample in samples:
        aspect = _sample_aspect(sample)
        if aspect is not None:
            grouped.setdefault(aspect, []).append(sample)

    if len(grouped) < 2:
        return None

    overrides: dict[str, BrandFormatOverride] = {}
    for aspect, bucket in sorted(grouped.items()):
        curve = _compute_temporal_curve(bucket)
        min_shot = max(0.35, round(min(sec.asl_p25_s for sec in curve) * 0.6, 3))
        max_hold = max(4.0, round(max(sec.asl_p75_s for sec in curve) * 2.2, 3))

        band_votes: Counter[Literal["lower_third", "center_safe", "upper_safe"]] = Counter()
        wm_votes = [
            s.breakdown.packaging.persistent_watermark_detected
            for s in bucket
            if s.breakdown is not None
        ]
        for s in bucket:
            if s.breakdown and s.breakdown.packaging.caption_band_observed:
                band_votes[s.breakdown.packaging.caption_band_observed] += 1

        overrides[aspect] = BrandFormatOverride(
            format_name=_ASPECT_FORMAT_NAMES[aspect],
            min_shot_duration_s=min_shot,
            max_uninterrupted_hold_s=max_hold,
            default_caption_band=band_votes.most_common(1)[0][0] if band_votes else None,
            watermark_default=(sum(wm_votes) > len(wm_votes) / 2) if wm_votes else None,
            temporal_curve=curve,
        )
    return overrides


def _collect_keyframe_index(probe: MediaProbeResult) -> dict[int, ProbeKeyframeInfo]:
    by_shot: dict[int, ProbeKeyframeInfo] = {}
    for kf in probe.visual.keyframes:
        existing = by_shot.get(kf.shot_index)
        if existing is None or kf.sharpness > existing.sharpness:
            by_shot[kf.shot_index] = kf
    return by_shot


def _build_exemplars(
    samples: Sequence[ReferenceVideoSample],
    easing_feel: str,
) -> list[StyleExemplar]:
    exemplars: list[StyleExemplar] = []
    seen_roles: set[tuple[str, ExemplarRole]] = set()

    for sample in samples:
        probe = sample.probe
        kf_by_shot = _collect_keyframe_index(probe)

        if sample.breakdown is not None and sample.breakdown.shots:
            bd = sample.breakdown
            dur = max(bd.duration_s, probe.container.duration_s, 0.5)
            ranked = sorted(
                bd.shots,
                key=lambda s: (
                    1 if s.narrative_role else 0,
                    s.production_confidence,
                    s.duration_s,
                ),
                reverse=True,
            )
            for bshot in ranked:
                mid_ratio = min(max(((bshot.start_s + bshot.end_s) * 0.5) / dur, 0.0), 0.999)
                if bshot.narrative_role and bshot.narrative_role in _NARRATIVE_TO_EXEMPLAR_ROLE:
                    role = _NARRATIVE_TO_EXEMPLAR_ROLE[bshot.narrative_role]
                    if bshot.narrative_role == "info" and bshot.production_label == "code_render":
                        role = "data_callout"
                else:
                    role = _SECTION_TO_EXEMPLAR_ROLE[_classify_section(mid_ratio)]

                key = (sample.source_video_id, role)
                if key in seen_roles:
                    continue
                seen_roles.add(key)

                metrics: dict[str, Any] = {
                    "shot_index": bshot.shot_index,
                    "duration_s": round(bshot.duration_s, 3),
                    "confidence": round(bshot.production_confidence, 3),
                    "cuts_per_min_ref": round(bd.editing.cuts_per_min, 2),
                    "easing_feel": easing_feel,
                    "production_label": bshot.production_label,
                    "transition_in": bshot.transition_in,
                    "beat_synced": bd.editing.beat_synced_edit,
                }
                if bd.grade.look:
                    metrics["grade_look"] = bd.grade.look
                if bd.videomd_path:
                    metrics["videomd_path"] = bd.videomd_path
                if bd.generative_reference_warning:
                    metrics["generative_reference_warning"] = True

                note_parts = [
                    f"Empirical {role} exemplar ({bshot.duration_s:.2f}s, "
                    f"{bshot.production_label}, transition={bshot.transition_in}) "
                    f"from {sample.source_video_id}."
                ]
                if bshot.narrative_point:
                    note_parts.append(bshot.narrative_point)
                elif bshot.description:
                    note_parts.append(bshot.description[:140])
                if bshot.production_label in ("ai_video", "avatar"):
                    note_parts.append(
                        "Reference uses synthetic footage; substitute real media or procedural "
                        "HyperFrames during production."
                    )

                kf = kf_by_shot.get(bshot.shot_index)
                exemplars.append(
                    StyleExemplar(
                        exemplar_id=f"{sample.source_video_id}_{role}_s{bshot.shot_index}",
                        source_video_id=sample.source_video_id,
                        role=role,
                        start_s=round(bshot.start_s, 3),
                        end_s=round(bshot.end_s, 3),
                        keyframe_path=bshot.sheet_path or (kf.path if kf else None),
                        hyperframes_pattern=_ROLE_TO_HF_PATTERN[role],
                        measured_metrics=metrics,
                        notes=" ".join(note_parts),
                    )
                )
            continue

        dur = max(probe.container.duration_s, 0.5)
        scored_shots = sorted(
            probe.shots,
            key=lambda s: (
                kf_by_shot[s.shot_index].sharpness if s.shot_index in kf_by_shot else 0.0,
                s.confidence,
            ),
            reverse=True,
        )
        for shot in scored_shots:
            mid_ratio = min(max(((shot.start_s + shot.end_s) * 0.5) / dur, 0.0), 0.999)
            section = _classify_section(mid_ratio)
            role = _SECTION_TO_EXEMPLAR_ROLE[section]
            key = (sample.source_video_id, role)
            if key in seen_roles:
                continue
            seen_roles.add(key)

            kf = kf_by_shot.get(shot.shot_index)
            metrics = {
                "shot_index": shot.shot_index,
                "duration_s": round(shot.duration_s, 3),
                "confidence": round(shot.confidence, 3),
                "cuts_per_min_ref": round(probe.shot_stats.cuts_per_min, 2),
                "easing_feel": easing_feel,
            }
            if kf is not None:
                metrics["sharpness"] = round(kf.sharpness, 3)
                metrics["luma_lower_third"] = round(kf.luma_lower_third, 2)

            exemplars.append(
                StyleExemplar(
                    exemplar_id=f"{sample.source_video_id}_{role}_s{shot.shot_index}",
                    source_video_id=sample.source_video_id,
                    role=role,
                    start_s=round(shot.start_s, 3),
                    end_s=round(shot.end_s, 3),
                    keyframe_path=kf.path if kf else None,
                    hyperframes_pattern=_ROLE_TO_HF_PATTERN[role],
                    measured_metrics=metrics,
                    notes=(
                        f"Empirical {section} exemplar ({shot.duration_s:.2f}s) from "
                        f"{sample.source_video_id} using {_ROLE_TO_HF_PATTERN[role]}."
                    ),
                )
            )
    return exemplars


def _default_grammar_triggers() -> list[GrammarTrigger]:
    return [
        GrammarTrigger(
            trigger_id="quantified_claim_data_card",
            condition="speech.contains_number_or_metric and speech.duration_s >= 1.5",
            action="overlay.spawn(kind='data_card', band='dynamic_away_from_subject')",
            weight=0.88,
            rationale="Anchor spoken statistics with a legible, contrasting metric card.",
        ),
        GrammarTrigger(
            trigger_id="hook_opening_callout",
            condition="timeline.section == 'hook' and timeline.t_s <= 2.5",
            action="overlay.spawn(kind='kinetic_callout', band='upper_safe')",
            weight=0.84,
            rationale="Establish subject context early inside platform-safe top band.",
        ),
        GrammarTrigger(
            trigger_id="long_hold_visual_refresh",
            condition="shot.hold_s >= 0.75 * hard_guardrails.max_uninterrupted_hold_s",
            action="video.insert_broll_or_punch_in(scale=1.08)",
            weight=0.76,
            rationale="Prevent visual fatigue on extended spoken segments.",
        ),
        GrammarTrigger(
            trigger_id="clause_pause_cut_anchor",
            condition="audio.silence_gap_s >= 0.30",
            action="timeline.prefer_cut_boundary()",
            weight=0.92,
            rationale="Align visual transitions cleanly between speech phrases.",
        ),
    ]


def _build_grammar_triggers(samples: Sequence[ReferenceVideoSample]) -> list[GrammarTrigger]:
    breakdowns = [s.breakdown for s in samples if s.breakdown is not None]
    if not breakdowns:
        return _default_grammar_triggers()

    triggers: list[GrammarTrigger] = [
        GrammarTrigger(
            trigger_id="quantified_claim_data_card",
            condition="speech.contains_number_or_metric and speech.duration_s >= 1.5",
            action="overlay.spawn(kind='data_card', band='dynamic_away_from_subject')",
            weight=0.88,
            rationale="Anchor spoken statistics with a legible, contrasting metric card.",
        ),
        GrammarTrigger(
            trigger_id="hook_opening_callout",
            condition="timeline.section == 'hook' and timeline.t_s <= 2.5",
            action="overlay.spawn(kind='kinetic_callout', band='upper_safe')",
            weight=0.85,
            rationale="Establish subject context early inside platform-safe top band.",
        ),
    ]

    pause_ratios = [
        b.editing.cuts_in_pauses_ratio
        for b in breakdowns
        if b.editing.cuts_in_pauses_ratio is not None
    ]
    if not pause_ratios or (sum(pause_ratios) / len(pause_ratios)) >= 0.35:
        weight = (
            round(min(max(0.65 + 0.30 * (sum(pause_ratios) / len(pause_ratios)), 0.7), 0.96), 2)
            if pause_ratios
            else 0.9
        )
        triggers.append(
            GrammarTrigger(
                trigger_id="clause_pause_cut_anchor",
                condition="audio.silence_gap_s >= 0.25",
                action="timeline.prefer_cut_boundary()",
                weight=weight,
                rationale=(
                    "Measured reference cuts frequently land inside inter-word speech pauses."
                ),
            )
        )

    if any(b.editing.beat_synced_edit for b in breakdowns):
        triggers.append(
            GrammarTrigger(
                trigger_id="beat_aligned_cut_anchor",
                condition="audio.beat_grid_available and timeline.near_beat_ms <= 70",
                action="timeline.snap_cut_to_music_beat()",
                weight=0.91,
                rationale="Reference edits exhibit statistically significant beat-aligned cutting.",
            )
        )

    if sum(b.audio.sfx_aligned_to_visual_count for b in breakdowns) > 0:
        triggers.append(
            GrammarTrigger(
                trigger_id="sfx_transition_anchor",
                condition="transition.or_overlay_entrance",
                action="audio.sync_sfx_peak_to_visual_event()",
                weight=0.87,
                rationale=(
                    "Reference uses sound effects anchored directly to visual entrances or cuts."
                ),
            )
        )

    if sum(b.editing.punch_ins for b in breakdowns) > 0:
        triggers.append(
            GrammarTrigger(
                trigger_id="punch_in_rhythm_refresh",
                condition="shot.hold_s >= 0.70 * hard_guardrails.max_uninterrupted_hold_s",
                action="video.insert_punch_in(scale_range='motion_style.punch_in_scale_range')",
                weight=0.82,
                rationale=(
                    "Reference sustains energy on single-camera takes via deliberate "
                    "punch-in crops."
                ),
            )
        )
    else:
        triggers.append(
            GrammarTrigger(
                trigger_id="long_hold_visual_refresh",
                condition="shot.hold_s >= 0.75 * hard_guardrails.max_uninterrupted_hold_s",
                action="video.insert_broll_or_graphic_cutaway()",
                weight=0.78,
                rationale=(
                    "Refresh visual framing on extended spoken segments with B-roll or graphics."
                ),
            )
        )

    if any(b.generative_reference_warning for b in breakdowns):
        triggers.append(
            GrammarTrigger(
                trigger_id="non_generative_substitution_guard",
                condition="reference_shot.production_label in {'ai_video', 'avatar'}",
                action="director.substitute_real_footage_or_hyperframes()",
                weight=1.0,
                rationale=(
                    "Reference contained synthetic shots; enforce non-generative real media "
                    "or procedural HTML/GSAP motion graphics during production."
                ),
            )
        )

    return triggers


def _apply_decision_enrichment(
    samples: Sequence[ReferenceVideoSample],
    decision_port: DecisionPort,
    *,
    motion_default: str,
    caption_case_default: str,
) -> tuple[str, str, str | None, float]:
    """Query `DecisionPort` with `<= 8` representative keyframes for qualitative traits."""
    images: list[ImageInput] = []
    for sample in samples:
        for kf in sample.probe.visual.keyframes[:2]:
            p = Path(kf.path)
            if p.is_file() and len(images) < 8:
                images.append(ImageInput(path=p, content_type="image/jpeg"))

    if not images:
        return motion_default, caption_case_default, None, 0.72

    questions = [
        DecisionQuestion(
            name="motion_feel",
            question_type="choice",
            instructions="Classify dominant editing motion cadence.",
            criteria={
                "snappy_ease_out": "Fast crisp cuts and tight kinetic entrances.",
                "smooth_editorial": "Measured transitions and calm pacing.",
                "energetic_pop": "High-frequency rhythmic edits and punchy cards.",
                "minimal_static": "Long sustained holds with minimal overlay motion.",
            },
        ),
        DecisionQuestion(
            name="caption_case",
            question_type="choice",
            instructions="Classify dominant caption casing visible across frames.",
            criteria={
                "sentence": "Standard sentence capitalization.",
                "uppercase": "All-uppercase display captions.",
                "title": "Title-cased phrase captions.",
                "lowercase": "Minimalist lowercase captions.",
            },
        ),
        DecisionQuestion(
            name="editorial_tone",
            question_type="text",
            instructions="Summarize the visual editorial aesthetic in one concise phrase.",
        ),
    ]
    validate_decision_batch(questions, images)
    summary_state = {
        "reference_count": len(samples),
        "mean_cuts_per_min": round(
            sum(_sample_cuts_per_min(s) for s in samples) / max(len(samples), 1), 2
        ),
    }
    res = decision_port.evaluate(state=summary_state, questions=questions, images=images)

    motion_ans = (
        str(res.answers["motion_feel"].raw.get("choice", ""))
        if "motion_feel" in res.answers
        else ""
    )
    valid_motions = {"snappy_ease_out", "smooth_editorial", "energetic_pop", "minimal_static"}
    motion = motion_ans if motion_ans in valid_motions else motion_default

    cap_ans = (
        str(res.answers["caption_case"].raw.get("choice", ""))
        if "caption_case" in res.answers
        else ""
    )
    valid_cases = {"sentence", "uppercase", "title", "lowercase"}
    cap_case = cap_ans if cap_ans in valid_cases else caption_case_default

    tone_val = res.answers.get("editorial_tone")
    tone = str(tone_val.raw.get("text", "")).strip() or None if tone_val else None
    return motion, cap_case, tone, 0.88


def _derive_editorial_identity(
    samples: Sequence[ReferenceVideoSample],
    motion_feel: str,
    mean_cpm: float,
    audio_style: AudioStyleTokens,
) -> str:
    breakdowns = [s.breakdown for s in samples if s.breakdown is not None]
    if not breakdowns:
        return f"Data-driven {motion_feel.replace('_', ' ')} style ({mean_cpm:.1f} cuts/min)."

    mix_totals: Counter[str] = Counter()
    for bd in breakdowns:
        for lbl, ratio in bd.production_mix.items():
            mix_totals[lbl] += ratio
    top_prod = [f"{lbl} ({val / len(breakdowns):.0%})" for lbl, val in mix_totals.most_common(2)]
    grade_looks = [bd.grade.look for bd in breakdowns if bd.grade.look]

    parts = [f"Forensic {motion_feel.replace('_', ' ')} style ({mean_cpm:.1f} cuts/min)"]
    if top_prod:
        parts.append("mix: " + ", ".join(top_prod))
    if grade_looks:
        parts.append(f"grade: {grade_looks[0]}")
    if audio_style.bpm_range:
        parts.append(f"BGM {audio_style.bpm_range[0]:.0f}-{audio_style.bpm_range[1]:.0f} BPM")
    if any(bd.generative_reference_warning for bd in breakdowns):
        parts.append("non-generative substitution active for synthetic reference shots")
    return "; ".join(parts) + "."


def synthesize_brand_artifacts(
    brand_id: str,
    samples: Sequence[ReferenceVideoSample],
    *,
    display_name: str | None = None,
    decision_port: DecisionPort | None = None,
    validate_contract: bool = True,
) -> BrandSynthesisResult:
    """Synthesize runtime policy and advisory playbook from probes and optional breakdowns."""
    if not samples:
        raise ValueError("At least one ReferenceVideoSample is required to build BrandStylePolicy.")

    temporal_curve = _compute_temporal_curve(samples)
    palette_roles, _ = _weighted_palette(samples)

    mean_cpm = sum(_sample_cuts_per_min(s) for s in samples) / len(samples)
    mean_silence = sum(s.probe.audio.silence_ratio for s in samples) / len(samples)
    wpm = _estimate_speech_wpm(samples)

    audio_style = _synthesize_audio_style(
        samples,
        mean_cpm=mean_cpm,
        mean_silence=mean_silence,
    )
    motion_style = _synthesize_motion_style(
        samples,
        temporal_curve=temporal_curve,
        mean_cpm=mean_cpm,
    )
    typography = _synthesize_typography(samples, mean_cpm=mean_cpm, wpm=wpm)

    confidence = min(0.62 + 0.08 * min(len(samples), 3), 0.86)
    breakdowns = [s.breakdown for s in samples if s.breakdown is not None]
    if breakdowns:
        confidence += 0.06
        has_visual_review = any(
            any(r != "tool" for r in bd.reviewed_by) for bd in breakdowns
        )
        if has_visual_review:
            confidence += 0.06
        confidence = min(confidence, 0.98)

    editorial_identity: str | None = None
    if decision_port is not None:
        dec_motion, dec_case, editorial_identity, dec_conf = _apply_decision_enrichment(
            samples,
            decision_port,
            motion_default=motion_style.easing_feel,
            caption_case_default=typography.caption_case,
        )
        motion_style = _synthesize_motion_style(
            samples,
            temporal_curve=temporal_curve,
            mean_cpm=mean_cpm,
            decision_motion=dec_motion,
        )
        # Preserve OCR-observed caption casing when breakdown measured subtitles directly.
        if not any(bd.packaging.caption_case_observed for bd in breakdowns):
            typography = _synthesize_typography(
                samples,
                mean_cpm=mean_cpm,
                wpm=wpm,
                decision_caption_case=dec_case,
            )
        confidence = max(confidence, dec_conf)

    min_shot = max(0.35, round(min(sec.asl_p25_s for sec in temporal_curve) * 0.6, 3))
    max_hold = max(4.0, round(max(sec.asl_p75_s for sec in temporal_curve) * 2.2, 3))
    format_overrides = _build_format_overrides(samples)

    policy = BrandStylePolicy(
        brand_id=brand_id,
        display_name=display_name or brand_id.replace("_", " ").replace("-", " ").title(),
        editorial_identity=editorial_identity
        or _derive_editorial_identity(samples, motion_style.easing_feel, mean_cpm, audio_style),
        soft_priors=SoftPriors(
            temporal_curve=temporal_curve,
            visual_tokens=VisualTokens(
                palette_roles=palette_roles,
                typography=typography,
                motion_style=motion_style,
            ),
            audio_style=audio_style,
        ),
        hard_guardrails=HardGuardrails(
            min_shot_duration_s=min_shot,
            max_uninterrupted_hold_s=max_hold,
            no_cut_within_keyword_ms=180,
            never_overlap_subject_boxes=True,
            min_wcag_contrast=4.5,
            banned_transitions=["flash_white_strobe", "glitch_rgb_tear"],
            banned_patterns=["heavy_css_blur_glass"],
            avoid_heavy_css_blur=True,
        ),
        format_overrides=format_overrides,
        calibration=StyleCalibration(
            accepted_overrides=0,
            rejected_patterns=[],
            last_calibrated_at=datetime.now(UTC).isoformat(),
        ),
        provenance=BrandProvenance(
            reference_video_count=len(samples),
            reference_hashes=[s.probe.sha256 for s in samples],
            confidence=round(min(confidence, 0.98), 3),
            created_at=datetime.now(UTC).isoformat(),
        ),
    )

    playbook = EditorialPlaybook(
        brand_id=brand_id,
        schema_note=(
            "Advisory directing playbook only. Not consumed by planner, verifier, "
            "compile, master, or audit."
        ),
        grammar_triggers=_build_grammar_triggers(samples),
        exemplar_bank=_build_exemplars(samples, motion_style.easing_feel),
    )

    if validate_contract:
        policy_errors = validate_against_contract(
            policy.model_dump(exclude_none=True),
            "brand_style_policy.schema.json",
        )
        if policy_errors:
            raise ValueError(
                f"Synthesized BrandStylePolicy failed schema contract: {policy_errors}"
            )
        playbook_errors = validate_against_contract(
            playbook.model_dump(exclude_none=True),
            "editorial_playbook.schema.json",
        )
        if playbook_errors:
            raise ValueError(
                f"Synthesized EditorialPlaybook failed schema contract: {playbook_errors}"
            )

    return BrandSynthesisResult(policy=policy, playbook=playbook)


def synthesize_brand_policy(
    brand_id: str,
    samples: Sequence[ReferenceVideoSample],
    *,
    display_name: str | None = None,
    decision_port: DecisionPort | None = None,
    validate_contract: bool = True,
) -> BrandStylePolicy:
    """Synthesize a schema-valid runtime `BrandStylePolicy` from reference probes."""
    return synthesize_brand_artifacts(
        brand_id,
        samples,
        display_name=display_name,
        decision_port=decision_port,
        validate_contract=validate_contract,
    ).policy


def query_exemplars(
    playbook: EditorialPlaybook,
    *,
    role: ExemplarRole | None = None,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
) -> list[StyleExemplar]:
    """Retrieve matching reference exemplars from an editorial playbook."""
    matches: list[StyleExemplar] = []
    for ex in playbook.exemplar_bank:
        if role is not None and ex.role != role:
            continue
        dur = max(0.0, ex.end_s - ex.start_s)
        if min_duration_s is not None and dur < min_duration_s:
            continue
        if max_duration_s is not None and dur > max_duration_s:
            continue
        matches.append(ex)
    return matches


def record_calibration_feedback(
    policy: BrandStylePolicy,
    *,
    accepted_override: bool = False,
    rejected_pattern: str | None = None,
) -> BrandStylePolicy:
    """Return an updated `BrandStylePolicy` capturing human or automated override feedback."""
    cal = (policy.calibration or StyleCalibration()).model_copy(deep=True)
    if accepted_override:
        cal.accepted_overrides += 1
    if rejected_pattern and rejected_pattern not in cal.rejected_patterns:
        cal.rejected_patterns.append(rejected_pattern)
    cal.last_calibrated_at = datetime.now(UTC).isoformat()

    updated = policy.model_copy(update={"calibration": cal})
    errors = validate_against_contract(
        updated.model_dump(exclude_none=True),
        "brand_style_policy.schema.json",
    )
    if errors:
        raise ValueError(f"Calibrated BrandStylePolicy failed schema contract: {errors}")
    return updated
