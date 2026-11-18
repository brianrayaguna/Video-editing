"""Constraint-aware EditPlan synthesizer backed by BrandStylePolicy and capability ports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from vedit.director.verifier import VerificationReport, verify_and_stamp_plan
from vedit.metrics import NormRect, resolve_overlay_rect
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    BoundingBox,
    BrandStylePolicy,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
    VideoClipOp,
)
from vedit.ports.audio_catalog import AudioCatalogPort
from vedit.ports.decision import DecisionPort, DecisionQuestion, ImageInput, validate_decision_batch

_NUMBER_TOKEN_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|x|k|m|b|\+)?\b", re.I)


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

    # Subdivide any hold exceeding max_uninterrupted_hold_s cleanly between words when possible.
    final_boundaries: list[float] = [raw_boundaries[0]]
    for end_t in raw_boundaries[1:]:
        cur_start = final_boundaries[-1]
        while (end_t - cur_start) > max_hold:
            candidate = cur_start + max_hold * 0.75
            lo = cur_start + min_shot
            hi = end_t - min_shot
            if hi <= lo:
                break
            candidate = min(max(candidate, lo), hi)
            snapped = _snap_cut_to_safe_gap(candidate, lo, hi, transcript, margin_s)
            snapped = min(max(snapped, lo), hi)
            final_boundaries.append(snapped)
            cur_start = snapped
        if end_t - final_boundaries[-1] >= 0.05:
            final_boundaries.append(end_t)

    clips: list[VideoClipOp] = []
    for idx in range(len(final_boundaries) - 1):
        start_s = round(final_boundaries[idx], 3)
        dur_s = round(final_boundaries[idx + 1] - final_boundaries[idx], 3)
        if dur_s <= 0.0:
            continue
        clips.append(
            VideoClipOp(
                clip_id=f"clip_{idx + 1:03d}",
                asset_id=primary_asset_id,
                timeline_start_s=start_s,
                timeline_duration_s=dur_s,
                source_start_s=start_s,
                role="a_roll" if idx % 2 == 0 else "cutaway",
                reframed_to_target=reframed_to_target,
                scale=1.0,
                transition_in=None,
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


def _build_overlays(
    clips: list[VideoClipOp],
    transcript: NormalizedTranscript | None,
    policy: BrandStylePolicy,
    platform_target: PlatformTarget,
) -> list[OverlayCompositionOp]:
    overlays: list[OverlayCompositionOp] = []
    typo = policy.soft_priors.visual_tokens.typography
    palette = policy.soft_priors.visual_tokens.palette_roles
    pref_band_raw = typo.default_caption_band
    pref_band: Literal["lower_third", "upper_safe", "center_safe"] = (
        "upper_safe" if pref_band_raw == "upper_safe" else "lower_third"
    )

    if transcript and transcript.words:
        max_words = typo.max_words_per_caption_group
        spoken = [w for w in transcript.words if not w.is_filler]
        for idx in range(0, len(spoken), max_words):
            chunk = spoken[idx : idx + max_words]
            t_start = round(chunk[0].start_s, 3)
            t_end = round(max(chunk[-1].end_s, t_start + 0.3), 3)
            t_dur = round(t_end - t_start, 3)
            mid_t = t_start + t_dur * 0.5
            active_boxes: list[BoundingBox] = []
            for clip in clips:
                c_end = clip.timeline_start_s + clip.timeline_duration_s
                if clip.timeline_start_s <= mid_t <= c_end:
                    active_boxes.extend(clip.subject_safe_boxes)

            band = _choose_non_overlapping_band(pref_band, active_boxes, platform_target)
            phrase = _apply_case(" ".join(w.text for w in chunk), typo.caption_case)
            overlays.append(
                OverlayCompositionOp(
                    overlay_id=f"cap_{len(overlays) + 1:03d}",
                    kind="caption_rail",
                    timeline_start_s=t_start,
                    timeline_duration_s=t_dur,
                    transparent=True,
                    safe_band=band,
                    props={
                        "text": phrase,
                        "font_family": typo.body_family,
                        "fg_color": palette.ink,
                        "bg_color": palette.ground,
                        "pattern": "clean_caption_rail",
                    },
                )
            )

            if _NUMBER_TOKEN_RE.search(phrase):
                alt_band = "upper_safe" if band == "lower_third" else "lower_third"
                card_band = _choose_non_overlapping_band(
                    alt_band,  # type: ignore[arg-type]
                    active_boxes,
                    platform_target,
                )
                overlays.append(
                    OverlayCompositionOp(
                        overlay_id=f"card_{len(overlays) + 1:03d}",
                        kind="data_card",
                        timeline_start_s=t_start,
                        timeline_duration_s=round(max(t_dur, 1.2), 3),
                        transparent=True,
                        safe_band=card_band,
                        props={
                            "headline": phrase,
                            "accent_color": palette.accent,
                            "fg_color": palette.ink,
                            "bg_color": palette.ground,
                            "pattern": "split_metric_card",
                        },
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
    repo_root: Path | None = None,
) -> tuple[EditPlan, VerificationReport]:
    """Assemble and deterministically verify an `EditPlan` using `BrandStylePolicy`."""
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
        policy,
        transcript,
        primary_asset_id=primary_asset_id,
        reframed_to_target=reframed_to_target,
    )
    _ground_subject_boxes(clips, probe, decision_port)

    overlays = _build_overlays(clips, transcript, policy, platform_target)
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
    bgm_moods = policy.soft_priors.audio_style.bgm_moods
    if chosen_bgm is None and audio_catalog is not None and bgm_moods:
        mood_query = " ".join(bgm_moods[:2])
        hits = audio_catalog.search_music(mood_query, vocal_type="NONE", limit=1)
        if hits and hits[0].preview_url:
            chosen_bgm = AssetRef(
                asset_id="bgm_selected",
                sha256=f"{hits[0].asset_id:0<16}"[:16],
                kind="audio_bgm",
                path=hits[0].preview_url,
                duration_s=max(hits[0].duration_s or total_dur, total_dur),
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
                carve_strength=policy.soft_priors.audio_style.ducking_strength,
                cleaned_speech_stem=False,
            )
        )

    raw_plan = EditPlan(
        job_id=job_id,
        project_id=project_id,
        brand_id=policy.brand_id,
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
        policy,
        platform_target,
        transcript=transcript,
        repo_root=repo_root,
    )
