"""Constraint-aware EditPlan synthesizer backed by BrandStylePolicy and capability ports."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal

from vedit.director.storyboard_plan import apply_storyboard_to_clips, fit_overlays
from vedit.director.templates import (
    catalog_by_id,
    motion_props_from_policy,
    overlay_kind_for_template,
    resolve_effective_policy,
    resolve_template_variables,
)
from vedit.director.verifier import VerificationReport, verify_and_stamp_plan
from vedit.metrics import NormRect, resolve_overlay_rect
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    BoundingBox,
    BrandStylePolicy,
    BrandTemplateCatalog,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
    TemporalSectionPrior,
    TranscriptWord,
    VideoClipOp,
)
from vedit.ports.audio_catalog import AudioCatalogPort
from vedit.ports.decision import DecisionPort, DecisionQuestion, ImageInput, validate_decision_batch

_NUMBER_TOKEN_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|x|k|m|b|\+)?\b", re.I)

_SECTION_ORDER: tuple[str, ...] = ("hook", "setup", "body", "escalation", "climax", "outro")
_SECTION_SPAN: dict[str, tuple[float, float]] = {
    "hook": (0.00, 0.12),
    "setup": (0.12, 0.28),
    "body": (0.28, 0.68),
    "escalation": (0.68, 0.84),
    "climax": (0.84, 0.94),
    "outro": (0.94, 1.01),
}


def _section_prior_at(
    policy: BrandStylePolicy,
    mid_ratio: float,
) -> TemporalSectionPrior | None:
    curve = {p.section: p for p in policy.soft_priors.temporal_curve}
    for name in _SECTION_ORDER:
        lo, hi = _SECTION_SPAN[name]
        if lo <= mid_ratio < hi and name in curve:
            return curve[name]
    if "outro" in curve:
        return curve["outro"]
    if policy.soft_priors.temporal_curve:
        return policy.soft_priors.temporal_curve[-1]
    return None


def _apply_case(text: str, case_mode: str) -> str:
    if case_mode == "uppercase":
        return text.upper()
    if case_mode == "lowercase":
        return text.lower()
    if case_mode == "title":
        return text.title()
    return text


def _snap_cut_to_safe_gap(
    target_t: float,
    min_t: float,
    max_t: float,
    transcript: NormalizedTranscript | None,
    margin_s: float,
) -> float:
    """Snap a candidate cut timestamp away from spoken words when inter-word gaps exist."""
    if transcript is None or not transcript.words:
        return round(target_t, 3)

    best_t = target_t
    best_dist = float("inf")
    words = [w for w in transcript.words if not w.is_filler]
    if not words:
        return round(target_t, 3)

    candidates: list[float] = []
    for idx in range(len(words) - 1):
        gap_start = words[idx].end_s
        gap_end = words[idx + 1].start_s
        if gap_end > gap_start:
            mid = (gap_start + gap_end) * 0.5
            if min_t <= mid <= max_t:
                candidates.append(mid)

    for cand in candidates:
        pad = margin_s * 0.1
        blocked = any((w.start_s - pad) < cand < (w.end_s + pad) for w in words)
        if blocked:
            continue
        dist = abs(cand - target_t)
        if dist < best_dist:
            best_dist = dist
            best_t = cand
    return round(best_t, 3)


def _plan_video_cuts(
    probe: MediaProbeResult,
    policy: BrandStylePolicy,
    transcript: NormalizedTranscript | None,
    *,
    primary_asset_id: str,
    reframed_to_target: bool,
) -> list[VideoClipOp]:
    total_dur = max(probe.container.duration_s, 0.5)
    min_shot = policy.hard_guardrails.min_shot_duration_s
    max_hold = policy.hard_guardrails.max_uninterrupted_hold_s
    margin_s = policy.hard_guardrails.no_cut_within_keyword_ms / 1000.0

    raw_boundaries: list[float] = [0.0]
    for shot in probe.shots:
        if shot.start_s - raw_boundaries[-1] >= min_shot and total_dur - shot.start_s >= min_shot:
            snapped = _snap_cut_to_safe_gap(
                shot.start_s,
                raw_boundaries[-1] + min_shot,
                total_dur - min_shot,
                transcript,
                margin_s,
            )
            if snapped - raw_boundaries[-1] >= min_shot and total_dur - snapped >= min_shot:
                raw_boundaries.append(snapped)
    raw_boundaries.append(total_dur)

    # Subdivide holds using section soft prior (asl_p50) with non-metronomic rhythm contours.
    final_boundaries: list[float] = [raw_boundaries[0]]
    for end_t in raw_boundaries[1:]:
        cur_start = final_boundaries[-1]
        sub_step_idx = 0
        while True:
            hold = end_t - cur_start
            mid_ratio = min(max(((cur_start + end_t) * 0.5) / total_dur, 0.0), 0.999)
            prior = _section_prior_at(policy, mid_ratio)
            if prior is not None:
                base_asl = prior.asl_p50_s
                if prior.section == "escalation":
                    # Accelerando across escalation: step narrows from p75 toward p25.
                    esc_lo, esc_hi = _SECTION_SPAN["escalation"]
                    sec_span = max(esc_hi - esc_lo, 1e-6)
                    sec_prog = min(1.0, max(0.0, (mid_ratio - esc_lo) / sec_span))
                    soft_target = (
                        prior.asl_p75_s + (prior.asl_p25_s - prior.asl_p75_s) * sec_prog
                    )
                elif prior.section == "climax":
                    soft_target = prior.asl_p75_s if sub_step_idx == 0 else prior.asl_p25_s
                else:
                    # Subtle alternating cadence prevents flat metronomic pacing.
                    rhythm_mult = 1.12 if (sub_step_idx % 2 == 0) else 0.88
                    soft_target = min(max(base_asl * rhythm_mult, prior.asl_p25_s), prior.asl_p75_s)
            else:
                soft_target = max_hold * 0.75
            soft_target = min(max(soft_target, min_shot), max_hold)
            split_threshold = min(soft_target * 1.35, max_hold)
            if hold <= split_threshold + 1e-6:
                break
            lo = cur_start + min_shot
            hi = end_t - min_shot
            if hi <= lo:
                break
            # Ensure even remainder when a hold strictly exceeds max_hold.
            if hold > max_hold:
                ideal_step = min(soft_target, max_hold * 0.85, hold * 0.5)
                candidate = cur_start + max(ideal_step, min_shot)
            else:
                candidate = cur_start + soft_target
            candidate = min(max(candidate, lo), hi)
            snapped = _snap_cut_to_safe_gap(candidate, lo, hi, transcript, margin_s)
            snapped = min(max(snapped, lo), hi)
            if snapped - cur_start > max_hold:
                snapped = round(min(cur_start + max_hold, hi), 3)
            if snapped <= cur_start + 1e-3:
                break
            final_boundaries.append(snapped)
            cur_start = snapped
            sub_step_idx += 1
        if end_t - final_boundaries[-1] >= 0.05:
            final_boundaries.append(end_t)

    clips: list[VideoClipOp] = []
    for idx in range(len(final_boundaries) - 1):
        start_s = round(final_boundaries[idx], 3)
        dur_s = round(final_boundaries[idx + 1] - final_boundaries[idx], 3)
        if dur_s <= 0.0:
            continue
        mid_ratio = min(max(((start_s + dur_s * 0.5) / total_dur), 0.0), 0.999)
        sec_prior = _section_prior_at(policy, mid_ratio)
        pref_tr = [t.lower() for t in (sec_prior.preferred_transitions if sec_prior else [])]
        j_lead: float | None = None
        if (
            idx > 0
            and probe.audio.present
            and "j_cut" in pref_tr
            and start_s >= 0.35
            and dur_s >= 1.2
        ):
            j_lead = round(min(0.35, start_s * 0.5), 3)
        clips.append(
            VideoClipOp(
                clip_id=f"clip_{idx + 1:03d}",
                asset_id=primary_asset_id,
                timeline_start_s=start_s,
                timeline_duration_s=dur_s,
                source_start_s=start_s,
                role="a_roll",
                reframed_to_target=reframed_to_target,
                scale=1.0,
                transition_in="hard_cut" if j_lead else None,
                j_cut_lead_s=j_lead,
                subject_safe_boxes=[],
            )
        )
    return clips


def _ground_subject_boxes(
    clips: list[VideoClipOp],
    probe: MediaProbeResult,
    decision_port: DecisionPort | None,
) -> None:
    if decision_port is None or not probe.visual.keyframes:
        return

    kf_list = probe.visual.keyframes
    for clip in clips:
        mid_t = clip.timeline_start_s + clip.timeline_duration_s * 0.5
        nearest = min(kf_list, key=lambda k: abs(k.timestamp_s - mid_t))
        kf_path = Path(nearest.path)
        if not kf_path.is_file():
            continue
        question = DecisionQuestion(
            name="subject_boxes",
            question_type="boxes",
            instructions="Locate primary speaker faces, hands, and focal UI elements.",
            max_items=4,
        )
        images = [ImageInput(path=kf_path, content_type="image/jpeg")]
        validate_decision_batch([question], images)
        res = decision_port.evaluate(
            state={"clip_id": clip.clip_id, "time_s": mid_t},
            questions=[question],
            images=images,
        )
        ans = res.answers.get("subject_boxes")
        if not ans:
            continue
        raw_boxes = ans.raw.get("boxes") or []
        parsed: list[BoundingBox] = []
        for idx, b in enumerate(raw_boxes):
            if not isinstance(b, dict):
                continue
            parsed.append(
                BoundingBox(
                    top=min(max(float(b["top"]), 0.0), 1.0),
                    bottom=min(max(float(b["bottom"]), 0.0), 1.0),
                    left=min(max(float(b["left"]), 0.0), 1.0),
                    right=min(max(float(b["right"]), 0.0), 1.0),
                    label=str(b.get("label") or f"subject_{idx}"),
                )
            )
        clip.subject_safe_boxes = parsed


def _choose_non_overlapping_band(
    preferred: Literal["lower_third", "upper_safe", "center_safe", "left_rail", "right_rail"],
    subject_boxes: list[BoundingBox],
    platform_target: PlatformTarget,
) -> Literal["lower_third", "upper_safe", "center_safe", "left_rail", "right_rail"]:
    order: list[Literal["lower_third", "upper_safe", "center_safe", "left_rail", "right_rail"]] = [
        preferred,
        "upper_safe",
        "lower_third",
        "right_rail",
        "left_rail",
        "center_safe",
    ]
    seen: set[str] = set()
    for band in order:
        if band in seen:
            continue
        seen.add(band)
        rect = resolve_overlay_rect(band, platform_target.safe_zone)
        collides = any(
            rect.overlap_fraction(
                NormRect(top=b.top, bottom=b.bottom, left=b.left, right=b.right)
            )
            > 0.01
            for b in subject_boxes
        )
        if not collides:
            return band
    return preferred


_CLAUSE_END_RE = re.compile(r"[.,!?;:]$")


def _group_caption_words(
    spoken: list[TranscriptWord],
    max_words: int,
    *,
    pause_gap_s: float = 0.15,
) -> list[list[TranscriptWord]]:
    """Partition spoken words into balanced 2-to-max_words phrases aligned to pauses and clauses."""
    if not spoken:
        return []

    clauses: list[list[TranscriptWord]] = []
    current: list[TranscriptWord] = []
    for idx, word in enumerate(spoken):
        current.append(word)
        is_last = idx == len(spoken) - 1
        next_gap = (spoken[idx + 1].start_s - word.end_s) if not is_last else 0.0
        ends_clause = bool(_CLAUSE_END_RE.search(word.text.strip()))
        if is_last or next_gap >= pause_gap_s or ends_clause:
            clauses.append(current)
            current = []

    groups: list[list[TranscriptWord]] = []
    cap = max(1, max_words)
    for clause in clauses:
        n = len(clause)
        if n <= cap:
            groups.append(clause)
            continue
        # Balance chunks to avoid awkward single-word orphans when cap >= 3 (e.g. 4 words -> 2+2).
        pos = 0
        while pos < n:
            rem = n - pos
            if rem <= cap:
                groups.append(clause[pos:])
                break
            if cap >= 3 and rem == cap + 1:
                take = cap - 1
            else:
                take = cap
            groups.append(clause[pos : pos + take])
            pos += take
    return groups


def _build_overlays(
    clips: list[VideoClipOp],
    transcript: NormalizedTranscript | None,
    policy: BrandStylePolicy,
    platform_target: PlatformTarget,
    template_catalog: BrandTemplateCatalog | None = None,
    auto_data_cards: bool = True,
) -> list[OverlayCompositionOp]:
    overlays: list[OverlayCompositionOp] = []
    typo = policy.soft_priors.visual_tokens.typography
    palette = policy.soft_priors.visual_tokens.palette_roles
    motion = motion_props_from_policy(policy)
    catalog_map = catalog_by_id(template_catalog) if template_catalog else {}
    catalog_ids = set(catalog_map.keys())
    pref_band_raw = typo.default_caption_band
    if pref_band_raw == "upper_safe":
        pref_band: Literal["lower_third", "upper_safe", "center_safe"] = "upper_safe"
    elif pref_band_raw == "center_safe":
        pref_band = "center_safe"
    else:
        pref_band = "lower_third"

    caption_style = typo.caption_style or "plain"
    caption_transition_ms = (
        typo.caption_transition_ms if typo.caption_transition_ms is not None else 50
    )

    if transcript and transcript.words:
        max_words = typo.max_words_per_caption_group
        spoken = [w for w in transcript.words if not w.is_filler]
        chunks = _group_caption_words(spoken, max_words)
        for idx, chunk in enumerate(chunks):
            t_start = round(chunk[0].start_s, 3)
            raw_end = max(chunk[-1].end_s, t_start + 0.3)
            if idx + 1 < len(chunks):
                next_start = round(chunks[idx + 1][0].start_s, 3)
                if next_start > t_start:
                    raw_end = min(raw_end, next_start)
            t_end = round(max(raw_end, t_start + 0.05), 3)
            t_dur = round(t_end - t_start, 3)
            active_boxes: list[BoundingBox] = []
            for clip in clips:
                c_end = clip.timeline_start_s + clip.timeline_duration_s
                if clip.timeline_start_s < t_end and c_end > t_start:
                    active_boxes.extend(clip.subject_safe_boxes)

            band = _choose_non_overlapping_band(pref_band, active_boxes, platform_target)
            phrase = _apply_case(" ".join(w.text for w in chunk), typo.caption_case)
            caption_template = "caption_rail" if "caption_rail" in catalog_ids else None
            caption_vars: dict[str, object] = {"text": phrase}
            caption_path = None
            if template_catalog is not None and caption_template:
                entry = catalog_map[caption_template]
                caption_vars = resolve_template_variables(entry, policy, caption_vars)
                caption_path = entry.composition_path
            caption_props: dict[str, object] = {
                "text": phrase,
                "font_family": typo.body_family,
                "display_family": typo.display_family,
                "fg_color": caption_vars.get("fg_color", palette.ink),
                "bg_color": caption_vars.get("bg_color", palette.ground),
                "caption_style": caption_vars.get("caption_style", caption_style),
                "caption_transition_ms": caption_transition_ms,
                "pattern": "clean_caption_rail",
                **motion,
            }
            is_portrait = platform_target.height > platform_target.width
            if typo.caption_font_family:
                caption_props["caption_font_family"] = typo.caption_font_family
            if is_portrait and typo.caption_font_px_9x16 is not None:
                caption_props["caption_font_px"] = max(
                    16, round(typo.caption_font_px_9x16 * (platform_target.height / 1920.0))
                )
            if is_portrait and typo.caption_margin_v_px_9x16 is not None:
                caption_props["caption_bottom_pct"] = round(
                    typo.caption_margin_v_px_9x16 / 1920.0, 5
                )
            if typo.caption_fade_in_ms is not None:
                caption_props["caption_fade_in_ms"] = typo.caption_fade_in_ms
            if typo.caption_fade_out_ms is not None:
                caption_props["caption_fade_out_ms"] = typo.caption_fade_out_ms
            if caption_path:
                caption_props["composition_path"] = caption_path
            overlays.append(
                OverlayCompositionOp(
                    overlay_id=f"cap_{len(overlays) + 1:03d}",
                    kind=overlay_kind_for_template(
                        caption_template or "caption_rail",
                        "caption_rail",
                        catalog=template_catalog,
                    ),
                    timeline_start_s=t_start,
                    timeline_duration_s=t_dur,
                    transparent=True,
                    safe_band=band,
                    template_id=caption_template,
                    variables=caption_vars if caption_template else {},
                    props=caption_props,
                )
            )

            if auto_data_cards and _NUMBER_TOKEN_RE.search(phrase):
                alt_band: Literal[
                    "lower_third", "upper_safe", "center_safe", "left_rail", "right_rail"
                ] = "upper_safe" if band == "lower_third" else "lower_third"
                card_band = _choose_non_overlapping_band(alt_band, active_boxes, platform_target)
                if card_band == band:
                    # Try center_safe if opposite band was blocked by subject boxes.
                    fallback_band = _choose_non_overlapping_band(
                        "center_safe",
                        active_boxes,
                        platform_target,
                    )
                    card_band = fallback_band if fallback_band != band else band
                if card_band == band:
                    continue
                is_landscape = platform_target.aspect_ratio == "16:9"
                if is_landscape and "amber_fact_card" in catalog_ids:
                    card_template: str | None = "amber_fact_card"
                elif "tabular_metric" in catalog_ids:
                    card_template = "tabular_metric"
                else:
                    card_template = None

                # Pass only content overrides so template token_ref defaults (e.g. amber_fact_card
                # amber surface + dark ink) are preserved rather than overwritten.
                card_vars: dict[str, object] = {"text": phrase, "label": phrase}
                card_path = None
                if template_catalog is not None and card_template:
                    entry = catalog_map[card_template]
                    card_vars = resolve_template_variables(entry, policy, card_vars)
                    card_path = entry.composition_path
                card_props: dict[str, object] = {
                    "headline": phrase,
                    "text": phrase,
                    "font_family": typo.body_family,
                    "display_family": typo.display_family,
                    "accent_color": card_vars.get("accent_color", palette.accent),
                    "fg_color": card_vars.get("fg_color", palette.ink),
                    "bg_color": card_vars.get("bg_color", palette.ground),
                    "pattern": "split_metric_card",
                    **motion,
                }
                if card_path:
                    card_props["composition_path"] = card_path
                overlays.append(
                    OverlayCompositionOp(
                        overlay_id=f"card_{len(overlays) + 1:03d}",
                        kind=overlay_kind_for_template(
                            card_template or "data_card",
                            "data_card",
                            catalog=template_catalog,
                        ),
                        timeline_start_s=t_start,
                        timeline_duration_s=round(t_dur, 3),
                        transparent=True,
                        safe_band=card_band,
                        template_id=card_template,
                        variables=card_vars if card_template else {},
                        props=card_props,
                    )
                )
    return overlays


def build_edit_plan(
    *,
    job_id: str,
    project_id: str,
    probe: MediaProbeResult,
    policy: BrandStylePolicy,
    platform_target: PlatformTarget,
    transcript: NormalizedTranscript | None = None,
    decision_port: DecisionPort | None = None,
    audio_catalog: AudioCatalogPort | None = None,
    bgm_asset: AssetRef | None = None,
    render_strategy: Literal["hybrid", "full_hf"] = "hybrid",
    reframed_to_target: bool = True,
    cleaned_speech_stem: bool = True,
    template_catalog: BrandTemplateCatalog | None = None,
    repo_root: Path | None = None,
    extra_overlays: list[OverlayCompositionOp] | None = None,
    storyboard: dict[str, Any] | None = None,
) -> tuple[EditPlan, VerificationReport]:
    """Assemble and deterministically verify an `EditPlan` using `BrandStylePolicy`.

    `extra_overlays` carries overlays realised from a checked storyboard
    (`storyboard_plan.storyboard_overlays`). When present, the storyboard owns number cards, so
    the caption-driven automatic data cards are skipped; the extra overlays are placed clear of
    the captions (`storyboard_plan.fit_overlays`), then clamped and verified with the rest.
    Overlays that fit nowhere are left out of the plan.
    """
    effective_policy = resolve_effective_policy(policy, platform_target)
    total_dur = round(max(probe.container.duration_s, 0.5), 3)
    primary_asset_id = "src_primary"
    assets: list[AssetRef] = [
        AssetRef(
            asset_id=primary_asset_id,
            sha256=probe.sha256,
            kind="video" if probe.video.present else "audio_speech",
            path=probe.path,
            duration_s=total_dur,
            has_audio=probe.audio.present,
        )
    ]

    clips = _plan_video_cuts(
        probe,
        effective_policy,
        transcript,
        primary_asset_id=primary_asset_id,
        reframed_to_target=reframed_to_target,
    )
    if storyboard is not None:
        clips = apply_storyboard_to_clips(clips, storyboard)
    _ground_subject_boxes(clips, probe, decision_port)

    overlays = _build_overlays(
        clips,
        transcript,
        effective_policy,
        platform_target,
        template_catalog=template_catalog,
        auto_data_cards=not extra_overlays,
    )
    if extra_overlays:
        fitted, _dropped = fit_overlays(extra_overlays, overlays, platform_target.safe_zone)
        overlays = [*overlays, *fitted]
    # Clamp overlays cleanly within total timeline duration.
    clamped_overlays: list[OverlayCompositionOp] = []
    for ov in overlays:
        if ov.timeline_start_s >= total_dur:
            continue
        max_dur = round(total_dur - ov.timeline_start_s, 3)
        if max_dur <= 0.05:
            continue
        if ov.timeline_duration_s > max_dur:
            ov = ov.model_copy(update={"timeline_duration_s": max_dur})
        clamped_overlays.append(ov)

    audio_tracks: list[AudioTrackOp] = []
    if probe.audio.present:
        audio_tracks.append(
            AudioTrackOp(
                track_id="vo_main",
                asset_id=primary_asset_id,
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=total_dur,
                source_start_s=0.0,
                gain_db=0.0,
                cleaned_speech_stem=cleaned_speech_stem,
            )
        )

    chosen_bgm = bgm_asset
    bgm_moods = effective_policy.soft_priors.audio_style.bgm_moods
    if chosen_bgm is None and audio_catalog is not None and bgm_moods:
        mood_query = " ".join(bgm_moods[:2])
        hits = audio_catalog.search_music(mood_query, vocal_type="NONE", limit=1)
        if hits:
            hit = hits[0]
            bgm_path_str = hit.preview_url or ""
            if bgm_path_str:
                bgm_sha = hashlib.sha256(
                    f"{hit.provider}:{hit.asset_id}:{bgm_path_str}".encode()
                ).hexdigest()
                chosen_bgm = AssetRef(
                    asset_id="bgm_selected",
                    sha256=bgm_sha,
                    kind="audio_bgm",
                    path=bgm_path_str,
                    duration_s=max(hit.duration_s or total_dur, total_dur),
                    has_audio=True,
                )

    if chosen_bgm is not None:
        assets.append(chosen_bgm)
        audio_tracks.append(
            AudioTrackOp(
                track_id="bgm_main",
                asset_id=chosen_bgm.asset_id,
                audio_group="music",
                timeline_start_s=0.0,
                timeline_duration_s=total_dur,
                source_start_s=0.0,
                gain_db=-14.0,
                carve_against_group="voiceover" if probe.audio.present else None,
                carve_strength=effective_policy.soft_priors.audio_style.ducking_strength,
                cleaned_speech_stem=False,
            )
        )

    raw_plan = EditPlan(
        job_id=job_id,
        project_id=project_id,
        brand_id=effective_policy.brand_id,
        platform_target_id=platform_target.platform_id,
        render_strategy=render_strategy,
        duration_s=total_dur,
        fps=platform_target.fps,
        width=platform_target.width,
        height=platform_target.height,
        assets=assets,
        video_tracks=clips,
        overlay_compositions=clamped_overlays,
        audio_tracks=audio_tracks,
        verifier_passed=False,
    )
    return verify_and_stamp_plan(
        raw_plan,
        effective_policy,
        platform_target,
        transcript=transcript,
        template_catalog=template_catalog,
        repo_root=repo_root,
    )
