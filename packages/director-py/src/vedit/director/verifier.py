"""Deterministic pre-render EditPlan constraint verifier against BrandStylePolicy and targets."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import validate_against_contract
from vedit.director.templates import validate_overlay_template
from vedit.metrics import (
    NormRect,
    intervals_overlap,
    resolve_overlay_rect,
    wcag_contrast_ratio,
)
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    EditPlan,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
)

_SECTION_SPAN: dict[str, tuple[float, float]] = {
    "hook": (0.00, 0.12),
    "setup": (0.12, 0.28),
    "body": (0.28, 0.68),
    "escalation": (0.68, 0.84),
    "climax": (0.84, 0.94),
    "outro": (0.94, 1.01),
}

_BLUR_CSS_RE = re.compile(r"(backdrop-filter\s*:|filter\s*:[^;]*blur\s*\(|blur\s*\()", re.I)


@dataclass(slots=True)
class VerificationIssue:
    """Single deterministic constraint violation or advisory warning."""

    severity: Literal["error", "warning"]
    code: str
    message: str
    target_id: str | None = None


@dataclass(slots=True)
class VerificationReport:
    """Aggregated outcome from verifying an EditPlan before compilation or cloud render."""

    passed: bool
    errors: list[VerificationIssue] = field(default_factory=list)
    warnings: list[VerificationIssue] = field(default_factory=list)
    checked_guardrails: list[str] = field(default_factory=list)
    summary_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": [asdict(err) for err in self.errors],
            "warnings": [asdict(warn) for warn in self.warnings],
            "checked_guardrails": list(self.checked_guardrails),
            "summary_metrics": dict(self.summary_metrics),
        }


def _contains_css_blur(value: Any, *, key_name: str = "") -> bool:
    if isinstance(value, dict):
        for k, v in value.items():
            kl = str(k).lower()
            if kl in ("backdropfilter", "backdrop_filter") and v:
                return True
            if kl in ("blur_px", "css_blur_px") and isinstance(v, (int, float)) and v > 0:
                return True
            if _contains_css_blur(v, key_name=kl):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_css_blur(item, key_name=key_name) for item in value)
    if isinstance(value, str):
        if key_name in ("filter", "backdropfilter", "backdrop_filter", "css", "style"):
            return bool(_BLUR_CSS_RE.search(value) or "backdrop-filter" in value.lower())
        return bool(_BLUR_CSS_RE.search(value))
    return False


def _first_hex(props: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        val = props.get(key)
        if isinstance(val, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", val.strip()):
            return val.strip().upper()
    return None


def _check_schema_and_canvas(
    plan: EditPlan,
    platform_target: PlatformTarget,
    errors: list[VerificationIssue],
    repo_root: Path | None,
) -> None:
    schema_errs = validate_against_contract(
        plan.model_dump(exclude_none=True),
        "edit_plan.schema.json",
        repo_root=repo_root,
    )
    for err in schema_errs:
        errors.append(
            VerificationIssue(
                severity="error",
                code="EDIT_PLAN_SCHEMA_INVALID",
                message=err,
            )
        )

    if plan.width != platform_target.width or plan.height != platform_target.height:
        errors.append(
            VerificationIssue(
                severity="error",
                code="PLATFORM_CANVAS_MISMATCH",
                message=(
                    f"EditPlan resolution {plan.width}x{plan.height} does not match "
                    f"platform target {platform_target.width}x{platform_target.height}."
                ),
            )
        )
    if abs(plan.fps - platform_target.fps) > 0.05:
        errors.append(
            VerificationIssue(
                severity="error",
                code="PLATFORM_FPS_MISMATCH",
                message=f"EditPlan fps {plan.fps} differs from target {platform_target.fps}.",
            )
        )


def _check_assets_and_video_tracks(
    plan: EditPlan,
    policy: BrandStylePolicy,
    errors: list[VerificationIssue],
    warnings: list[VerificationIssue],
) -> None:
    assets_by_id = {asset.asset_id: asset for asset in plan.assets}
    guard = policy.hard_guardrails
    banned_trans = {t.lower() for t in guard.banned_transitions}

    prev_end = 0.0
    ordered = sorted(plan.video_tracks, key=lambda c: c.timeline_start_s)
    for idx, clip in enumerate(ordered):
        asset = assets_by_id.get(clip.asset_id)
        if asset is None:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="MISSING_ASSET_REF",
                    target_id=clip.clip_id,
                    message=f"Clip references missing asset_id={clip.asset_id!r}.",
                )
            )
        elif asset.duration_s is not None:
            if clip.source_start_s + clip.timeline_duration_s > asset.duration_s + 1e-3:
                errors.append(
                    VerificationIssue(
                        severity="error",
                        code="SOURCE_DURATION_EXCEEDED",
                        target_id=clip.clip_id,
                        message="Clip source window exceeds referenced asset duration.",
                    )
                )

        if clip.timeline_start_s + clip.timeline_duration_s > plan.duration_s + 1e-3:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="TIMELINE_DURATION_EXCEEDED",
                    target_id=clip.clip_id,
                    message="Clip extends beyond EditPlan.duration_s.",
                )
            )

        if idx > 0 and clip.timeline_start_s < prev_end - 1e-3:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="OVERLAPPING_VIDEO_TRACKS",
                    target_id=clip.clip_id,
                    message=f"Clip starts at {clip.timeline_start_s:.3f}s before prior end.",
                )
            )
        prev_end = max(prev_end, clip.timeline_start_s + clip.timeline_duration_s)

        if clip.timeline_duration_s < guard.min_shot_duration_s - 1e-6:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="BELOW_MIN_SHOT_DURATION",
                    target_id=clip.clip_id,
                    message=(
                        f"Clip duration {clip.timeline_duration_s:.3f}s is shorter than "
                        f"hard guardrail {guard.min_shot_duration_s:.3f}s."
                    ),
                )
            )

        if clip.timeline_duration_s > guard.max_uninterrupted_hold_s + 1e-6:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="EXCEEDS_MAX_HOLD_DURATION",
                    target_id=clip.clip_id,
                    message=(
                        f"Clip duration {clip.timeline_duration_s:.3f}s exceeds "
                        f"max_uninterrupted_hold_s={guard.max_uninterrupted_hold_s:.3f}s."
                    ),
                )
            )

        if clip.transition_in and clip.transition_in.lower() in banned_trans:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="BANNED_TRANSITION",
                    target_id=clip.clip_id,
                    message=f"Transition {clip.transition_in!r} is forbidden by brand guardrails.",
                )
            )

        if not clip.reframed_to_target:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="UNREFRAMED_SOURCE_CLIP",
                    target_id=clip.clip_id,
                    message="Clip must be reframed_to_target=True before spatial grounding.",
                )
            )

        if not clip.subject_safe_boxes and any(
            intervals_overlap(
                clip.timeline_start_s,
                clip.timeline_duration_s,
                ov.timeline_start_s,
                ov.timeline_duration_s,
            )
            and (ov.transparent or ov.safe_band != "fullscreen")
            for ov in plan.overlay_compositions
        ):
            warnings.append(
                VerificationIssue(
                    severity="warning",
                    code="MISSING_SUBJECT_BOX_GROUNDING",
                    target_id=clip.clip_id,
                    message="Clip overlaps overlay without DecisionPort subject_safe_boxes.",
                )
            )


def _check_keyword_cut_windows(
    plan: EditPlan,
    policy: BrandStylePolicy,
    transcript: NormalizedTranscript | None,
    errors: list[VerificationIssue],
) -> None:
    if transcript is None or len(plan.video_tracks) < 2:
        return

    ordered = sorted(plan.video_tracks, key=lambda c: c.timeline_start_s)
    cut_boundaries = [
        (ordered[i].clip_id, round(ordered[i].timeline_start_s + ordered[i].timeline_duration_s, 4))
        for i in range(len(ordered) - 1)
    ]
    margin_s = policy.hard_guardrails.no_cut_within_keyword_ms / 1000.0
    boundary_tol = 0.012

    for clip_id, cut_t in cut_boundaries:
        for word in transcript.words:
            if word.is_filler:
                continue
            word_len = max(0.0, word.end_s - word.start_s)
            if word_len <= 0.0:
                continue
            # Strictly interior word cut OR slicing inside keyword boundary margin.
            in_core = (word.start_s + boundary_tol) < cut_t < (word.end_s - boundary_tol)
            if in_core:
                errors.append(
                    VerificationIssue(
                        severity="error",
                        code="CUT_WITHIN_KEYWORD_WINDOW",
                        target_id=clip_id,
                        message=(
                            f"Cut at {cut_t:.3f}s splits spoken word {word.text!r} "
                            f"[{word.start_s:.3f}s, {word.end_s:.3f}s]."
                        ),
                    )
                )
                break

        if margin_s <= 0.0:
            continue
        for ov in plan.overlay_compositions:
            spans = ov.props.get("protected_spans")
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                s_start = float(span.get("start_s", 0.0))
                s_end = float(span.get("end_s", 0.0))
                if (s_start - margin_s) < cut_t < (s_end + margin_s):
                    errors.append(
                        VerificationIssue(
                            severity="error",
                            code="CUT_WITHIN_KEYWORD_WINDOW",
                            target_id=clip_id,
                            message=(
                                f"Cut at {cut_t:.3f}s intrudes on protected keyword span "
                                f"[{s_start:.3f}s, {s_end:.3f}s] (+/- {margin_s:.3f}s)."
                            ),
                        )
                    )
                    break


def _check_overlay_contrast(
    ov: OverlayCompositionOp,
    policy: BrandStylePolicy,
    errors: list[VerificationIssue],
) -> None:
    min_ratio = policy.hard_guardrails.min_wcag_contrast
    fg = _first_hex(ov.props, ("fg_color", "text_color", "ink"))
    bg = _first_hex(ov.props, ("bg_color", "background_color", "ground"))
    palette_bg = policy.soft_priors.visual_tokens.palette_roles.ground

    if fg and bg:
        ratio = wcag_contrast_ratio(fg, bg)
        if ratio < min_ratio:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="LOW_WCAG_CONTRAST",
                    target_id=ov.overlay_id,
                    message=(
                        f"Overlay contrast {ratio:.2f}:1 ({fg} on {bg}) "
                        f"is below minimum {min_ratio:.2f}:1."
                    ),
                )
            )
    elif fg and not ov.transparent:
        ratio = wcag_contrast_ratio(fg, palette_bg)
        if ratio < min_ratio:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="LOW_WCAG_CONTRAST",
                    target_id=ov.overlay_id,
                    message=(
                        f"Overlay foreground {fg} on policy ground {palette_bg} yields "
                        f"{ratio:.2f}:1 (< {min_ratio:.2f}:1)."
                    ),
                )
            )


def _check_overlays_and_spatial_grounding(
    plan: EditPlan,
    policy: BrandStylePolicy,
    platform_target: PlatformTarget,
    errors: list[VerificationIssue],
) -> None:
    guard = policy.hard_guardrails
    banned_patterns = {p.lower() for p in guard.banned_patterns}
    if policy.calibration:
        banned_patterns.update(p.lower() for p in policy.calibration.rejected_patterns)

    palette = policy.soft_priors.visual_tokens.palette_roles
    base_contrast = wcag_contrast_ratio(palette.ink, palette.ground)
    if base_contrast < guard.min_wcag_contrast:
        errors.append(
            VerificationIssue(
                severity="error",
                code="LOW_WCAG_CONTRAST",
                message=(
                    f"Brand policy palette ink/ground contrast {base_contrast:.2f}:1 "
                    f"is below guardrail {guard.min_wcag_contrast:.2f}:1."
                ),
            )
        )

    safe_zone = platform_target.safe_zone
    for ov in plan.overlay_compositions:
        if ov.timeline_start_s + ov.timeline_duration_s > plan.duration_s + 1e-3:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="OVERLAY_EXCEEDS_TIMELINE",
                    target_id=ov.overlay_id,
                    message="Overlay end time exceeds EditPlan.duration_s.",
                )
            )

        pattern_tags = [
            ov.kind.lower(),
            str(ov.props.get("pattern", "")).lower(),
            str(ov.props.get("template", "")).lower(),
        ]
        for tag in pattern_tags:
            if tag and tag in banned_patterns:
                errors.append(
                    VerificationIssue(
                        severity="error",
                        code="BANNED_PATTERN",
                        target_id=ov.overlay_id,
                        message=f"Overlay uses banned or rejected pattern {tag!r}.",
                    )
                )

        if guard.avoid_heavy_css_blur and _contains_css_blur(ov.props):
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="HEAVY_CSS_BLUR",
                    target_id=ov.overlay_id,
                    message="Overlay props include forbidden runtime CSS blur/backdrop-filter.",
                )
            )

        _check_overlay_contrast(ov, policy, errors)

        explicit_box = ov.props.get("box") if isinstance(ov.props.get("box"), dict) else None
        rect = resolve_overlay_rect(ov.safe_band, safe_zone, explicit_box=explicit_box)
        if ov.safe_band != "fullscreen" or explicit_box is not None:
            if (
                rect.top < safe_zone.top_pct - 1e-4
                or rect.bottom > (1.0 - safe_zone.bottom_pct) + 1e-4
                or rect.left < safe_zone.left_pct - 1e-4
                or rect.right > (1.0 - safe_zone.right_pct) + 1e-4
            ):
                errors.append(
                    VerificationIssue(
                        severity="error",
                        code="OUTSIDE_PLATFORM_SAFE_ZONE",
                        target_id=ov.overlay_id,
                        message=(
                            f"Overlay rect ({rect.top:.2f}..{rect.bottom:.2f}, "
                            f"{rect.left:.2f}..{rect.right:.2f}) intrudes on platform safe zone."
                        ),
                    )
                )

        if guard.never_overlap_subject_boxes and (ov.transparent or ov.safe_band != "fullscreen"):
            for clip in plan.video_tracks:
                if not intervals_overlap(
                    ov.timeline_start_s,
                    ov.timeline_duration_s,
                    clip.timeline_start_s,
                    clip.timeline_duration_s,
                ):
                    continue
                for s_box in clip.subject_safe_boxes:
                    s_rect = NormRect(
                        top=s_box.top,
                        bottom=s_box.bottom,
                        left=s_box.left,
                        right=s_box.right,
                    )
                    if rect.overlap_fraction(s_rect) > 0.01:
                        errors.append(
                            VerificationIssue(
                                severity="error",
                                code="SUBJECT_BOX_OVERLAP",
                                target_id=ov.overlay_id,
                                message=(
                                    f"Overlay {ov.overlay_id!r} overlaps subject box "
                                    f"{s_box.label or 'subject'} in clip {clip.clip_id!r}."
                                ),
                            )
                        )


def _check_audio_dag(
    plan: EditPlan,
    errors: list[VerificationIssue],
    warnings: list[VerificationIssue],
) -> None:
    assets_by_id = {asset.asset_id: asset for asset in plan.assets}
    vo_tracks = [t for t in plan.audio_tracks if t.audio_group == "voiceover"]

    for track in plan.audio_tracks:
        if track.asset_id not in assets_by_id:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="MISSING_ASSET_REF",
                    target_id=track.track_id,
                    message=f"Audio track references missing asset_id={track.asset_id!r}.",
                )
            )
        if track.timeline_start_s + track.timeline_duration_s > plan.duration_s + 1e-3:
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="AUDIO_EXCEEDS_TIMELINE",
                    target_id=track.track_id,
                    message="Audio track extends past EditPlan.duration_s.",
                )
            )

        if track.audio_group == "voiceover" and not track.cleaned_speech_stem:
            warnings.append(
                VerificationIssue(
                    severity="warning",
                    code="UNCLEANED_SPEECH_STEM",
                    target_id=track.track_id,
                    message="Voiceover track has cleaned_speech_stem=False.",
                )
            )

        if track.audio_group == "music":
            overlaps_vo = any(
                intervals_overlap(
                    track.timeline_start_s,
                    track.timeline_duration_s,
                    vo.timeline_start_s,
                    vo.timeline_duration_s,
                )
                for vo in vo_tracks
            )
            if overlaps_vo:
                if track.carve_against_group != "voiceover" or track.carve_strength <= 0.0:
                    errors.append(
                        VerificationIssue(
                            severity="error",
                            code="MUSIC_MISSING_VO_CARVE",
                            target_id=track.track_id,
                            message=(
                                "Music track overlapping voiceover must set "
                                "carve_against_group='voiceover' and carve_strength > 0."
                            ),
                        )
                    )
                if track.gain_db > 0.0:
                    errors.append(
                        VerificationIssue(
                            severity="error",
                            code="MUSIC_GAIN_EXCEEDS_VO",
                            target_id=track.track_id,
                            message="Music gain_db must not exceed 0 dB while ducking voiceover.",
                        )
                    )


def _check_soft_temporal_priors(
    plan: EditPlan,
    policy: BrandStylePolicy,
    warnings: list[VerificationIssue],
) -> None:
    """Warn when section cuts/min drift outside soft prior ranges (non-fatal)."""
    if plan.duration_s <= 0:
        return
    curve = {p.section: p for p in policy.soft_priors.temporal_curve}
    for section, (lo, hi) in _SECTION_SPAN.items():
        prior = curve.get(section)  # type: ignore[arg-type]
        if prior is None:
            continue
        sec_start = plan.duration_s * lo
        sec_end = plan.duration_s * min(hi, 1.0)
        sec_dur = max(sec_end - sec_start, 1e-6)
        cuts = sum(
            1
            for clip in plan.video_tracks
            if sec_start <= clip.timeline_start_s < sec_end and clip.timeline_start_s > 0.01
        )
        cpm = (cuts / sec_dur) * 60.0
        lo_cpm, hi_cpm = prior.cuts_per_min_range
        if cpm < lo_cpm * 0.55 or cpm > hi_cpm * 1.45:
            warnings.append(
                VerificationIssue(
                    severity="warning",
                    code="SOFT_TEMPORAL_CURVE_DRIFT",
                    target_id=section,
                    message=(
                        f"Section {section} cuts/min={cpm:.1f} outside soft prior "
                        f"[{lo_cpm:.1f}, {hi_cpm:.1f}] (advisory)."
                    ),
                )
            )


def _check_template_bindings(
    plan: EditPlan,
    template_catalog: BrandTemplateCatalog | None,
    errors: list[VerificationIssue],
) -> None:
    for ov in plan.overlay_compositions:
        for msg in validate_overlay_template(ov, template_catalog):
            errors.append(
                VerificationIssue(
                    severity="error",
                    code="TEMPLATE_VARIABLE_INVALID",
                    target_id=ov.overlay_id,
                    message=msg,
                )
            )


def verify_edit_plan(
    plan: EditPlan,
    policy: BrandStylePolicy,
    platform_target: PlatformTarget,
    transcript: NormalizedTranscript | None = None,
    *,
    template_catalog: BrandTemplateCatalog | None = None,
    repo_root: Path | None = None,
) -> VerificationReport:
    """Run all deterministic schema, pacing, spatial, contrast, and audio DAG checks."""
    errors: list[VerificationIssue] = []
    warnings: list[VerificationIssue] = []

    _check_schema_and_canvas(plan, platform_target, errors, repo_root)
    _check_assets_and_video_tracks(plan, policy, errors, warnings)
    _check_keyword_cut_windows(plan, policy, transcript, errors)
    _check_overlays_and_spatial_grounding(plan, policy, platform_target, errors)
    _check_audio_dag(plan, errors, warnings)
    _check_soft_temporal_priors(plan, policy, warnings)
    _check_template_bindings(plan, template_catalog, errors)

    checked = [
        "edit_plan_schema",
        "platform_canvas",
        "min_shot_duration_s",
        "max_uninterrupted_hold_s",
        "no_cut_within_keyword_ms",
        "banned_transitions_and_patterns",
        "avoid_heavy_css_blur",
        "min_wcag_contrast",
        "platform_safe_zones",
        "never_overlap_subject_boxes",
        "audio_dag_voiceover_carving",
        "soft_temporal_curve",
        "brand_template_bindings",
    ]
    return VerificationReport(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        checked_guardrails=checked,
        summary_metrics={
            "video_clip_count": len(plan.video_tracks),
            "overlay_count": len(plan.overlay_compositions),
            "audio_track_count": len(plan.audio_tracks),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    )


def verify_and_stamp_plan(
    plan: EditPlan,
    policy: BrandStylePolicy,
    platform_target: PlatformTarget,
    transcript: NormalizedTranscript | None = None,
    *,
    template_catalog: BrandTemplateCatalog | None = None,
    repo_root: Path | None = None,
) -> tuple[EditPlan, VerificationReport]:
    """Verify `plan` and return a copy stamped with `verifier_passed` and its report."""
    report = verify_edit_plan(
        plan,
        policy,
        platform_target,
        transcript,
        template_catalog=template_catalog,
        repo_root=repo_root,
    )
    stamped = plan.model_copy(update={"verifier_passed": report.passed})
    return stamped, report
