"""Multi-reference BrandStylePolicy synthesis, editorial playbook aids, and calibration.

Runtime policies carry soft priors, hard guardrails, calibration, and provenance.
Advisory grammar triggers and exemplars are emitted separately as EditorialPlaybook.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import validate_against_contract
from vedit.metrics import (
    compute_quantiles,
    pick_accent_color,
    pick_accessible_ink,
    relative_luminance,
)
from vedit.models import (
    AudioStyleTokens,
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
    VisualTokens,
)
from vedit.ports.decision import DecisionPort, DecisionQuestion, ImageInput, validate_decision_batch

SectionName = Literal["hook", "setup", "body", "escalation", "climax", "outro"]
ExemplarRole = Literal[
    "hook", "setup", "proof", "data_callout", "broll_bridge", "climax", "outro"
]

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

_ROLE_TO_HF_PATTERN: dict[ExemplarRole, str] = {
    "hook": "kinetic_hook_title",
    "proof": "lower_third_proof",
    "data_callout": "split_metric_card",
    "broll_bridge": "clean_broll_cut",
    "climax": "impact_stat_overlay",
    "outro": "clean_end_card",
}


@dataclass(slots=True)
class ReferenceVideoSample:
    """Bundled deterministic telemetry and optional transcript for one reference video."""

    source_video_id: str
    probe: MediaProbeResult
    transcript: NormalizedTranscript | None = None
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


def _weighted_palette(samples: Sequence[ReferenceVideoSample]) -> tuple[PaletteRoles, float]:
    """Derive WCAG-compliant PaletteRoles and mean luminance across reference probes."""
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
    ink = pick_accessible_ink(ground, min_contrast=4.5, candidates=ink_candidates)

    accent_pool = [(hx, meta[1], meta[0] / total_dur) for hx, meta in color_weights.items()]
    accent = pick_accent_color(ground, accent_pool, min_contrast=3.0)
    secondary = pick_accent_color(ground, accent_pool, min_contrast=3.0, exclude_hex=accent)

    return (
        PaletteRoles(ground=ground, ink=ink, accent=accent, secondary_accent=secondary),
        mean_luma,
    )


def _compute_temporal_curve(samples: Sequence[ReferenceVideoSample]) -> list[TemporalSectionPrior]:
    section_durations: dict[SectionName, list[float]] = {name: [] for name, *_ in _SECTION_BOUNDS}
    global_durations: list[float] = []
    mean_cuts_per_min = 0.0

    for sample in samples:
        dur = max(sample.probe.container.duration_s, 0.1)
        mean_cuts_per_min += sample.probe.shot_stats.cuts_per_min
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
        transitions = ["hard_cut"] if p50 < 2.2 else ["hard_cut", "j_cut"]
        if name == "outro":
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
        dur = max(probe.container.duration_s, 0.5)
        kf_by_shot = _collect_keyframe_index(probe)
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
            metrics: dict[str, Any] = {
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
            sum(s.probe.shot_stats.cuts_per_min for s in samples) / max(len(samples), 1), 2
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


def synthesize_brand_artifacts(
    brand_id: str,
    samples: Sequence[ReferenceVideoSample],
    *,
    display_name: str | None = None,
    decision_port: DecisionPort | None = None,
    validate_contract: bool = True,
) -> BrandSynthesisResult:
    """Synthesize runtime policy and advisory playbook from reference probes."""
    if not samples:
        raise ValueError("At least one ReferenceVideoSample is required to build BrandStylePolicy.")

    temporal_curve = _compute_temporal_curve(samples)
    palette_roles, _ = _weighted_palette(samples)

    mean_cpm = sum(s.probe.shot_stats.cuts_per_min for s in samples) / len(samples)
    mean_silence = sum(s.probe.audio.silence_ratio for s in samples) / len(samples)
    wpm = _estimate_speech_wpm(samples)

    if mean_cpm >= 32.0:
        motion_default = "energetic_pop"
        entrance_range = [120, 240]
        sfx_policy: Literal["none", "selective_transitions", "kinetic_accents"] = "kinetic_accents"
        moods = ["energetic", "modern", "electronic"]
        bpm_range = [116.0, 132.0]
    elif mean_cpm >= 14.0:
        motion_default = "snappy_ease_out"
        entrance_range = [180, 340]
        sfx_policy = "selective_transitions"
        moods = ["upbeat", "focused", "minimal"]
        bpm_range = [96.0, 118.0]
    elif mean_cpm >= 6.0:
        motion_default = "smooth_editorial"
        entrance_range = [260, 480]
        sfx_policy = "selective_transitions"
        moods = ["documentary", "warm", "ambient"]
        bpm_range = [80.0, 102.0]
    else:
        motion_default = "minimal_static"
        entrance_range = [340, 620]
        sfx_policy = "none"
        moods = ["ambient", "calm"]
        bpm_range = [65.0, 88.0]

    cap_default = "uppercase" if mean_cpm >= 28.0 else "sentence"
    confidence = min(0.62 + 0.08 * min(len(samples), 3), 0.86)
    editorial_identity: str | None = None

    if decision_port is not None:
        motion_default, cap_default, editorial_identity, dec_conf = _apply_decision_enrichment(
            samples,
            decision_port,
            motion_default=motion_default,
            caption_case_default=cap_default,
        )
        confidence = max(confidence, dec_conf)

    max_words = 4 if wpm >= 165.0 or mean_cpm >= 26.0 else 6
    ducking = round(min(max(0.55 + (1.0 - mean_silence) * 0.35, 0.5), 0.92), 2)

    all_asl = [sec.asl_p50_s for sec in temporal_curve]
    min_shot = max(0.35, round(min(sec.asl_p25_s for sec in temporal_curve) * 0.6, 3))
    max_hold = max(4.0, round(max(sec.asl_p75_s for sec in temporal_curve) * 2.2, 3))

    policy = BrandStylePolicy(
        brand_id=brand_id,
        display_name=display_name or brand_id.replace("_", " ").replace("-", " ").title(),
        editorial_identity=editorial_identity
        or f"Data-driven {motion_default.replace('_', ' ')} style ({mean_cpm:.1f} cuts/min).",
        soft_priors=SoftPriors(
            temporal_curve=temporal_curve,
            visual_tokens=VisualTokens(
                palette_roles=palette_roles,
                typography=TypographyTokens(
                    display_family="Inter, sans-serif",
                    body_family="Inter, sans-serif",
                    caption_case=cap_default,  # type: ignore[arg-type]
                    max_words_per_caption_group=max_words,
                    default_caption_band="dynamic_away_from_subject",
                ),
                motion_style=MotionStyleTokens(
                    easing_feel=motion_default,  # type: ignore[arg-type]
                    entrance_ms_range=entrance_range,
                    punch_in_scale_range=[1.04, 1.12] if min(all_asl) < 3.5 else [1.0, 1.06],
                ),
            ),
            audio_style=AudioStyleTokens(
                bgm_moods=moods,
                bpm_range=bpm_range,
                ducking_strength=ducking,
                sfx_policy=sfx_policy,
            ),
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
        calibration=StyleCalibration(
            accepted_overrides=0,
            rejected_patterns=[],
            last_calibrated_at=datetime.now(UTC).isoformat(),
        ),
        provenance=BrandProvenance(
            reference_video_count=len(samples),
            reference_hashes=[s.probe.sha256 for s in samples],
            confidence=round(confidence, 3),
            created_at=datetime.now(UTC).isoformat(),
        ),
    )

    playbook = EditorialPlaybook(
        brand_id=brand_id,
        schema_note=(
            "Advisory directing playbook only. Not consumed by planner, verifier, "
            "compile, master, or audit."
        ),
        grammar_triggers=_default_grammar_triggers(),
        exemplar_bank=_build_exemplars(samples, motion_default),
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
