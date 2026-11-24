"""Semi-automated reference editing inversion and low-confidence exception queue."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from vedit.director.storyboard import (
    _device_lead_window,
    scaffold_storyboard,
    validate_storyboard_contract,
)

ConfidenceLevel = Literal["high", "medium", "low"]


@dataclass(slots=True)
class BeatInversionAudit:
    """Per-beat onset snapping confidence and evidence provenance."""

    beat_id: str
    confidence: ConfidenceLevel
    snapped_onset_s: float
    original_onset_s: float
    evidence_sources: list[str]
    needs_review: bool
    review_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReferenceInversionResult:
    """Draft reference storyboard alongside per-beat audits and review queue."""

    storyboard: dict[str, Any]
    beat_audits: list[BeatInversionAudit] = field(default_factory=list)
    exception_review_beats: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "storyboard": self.storyboard,
            "beat_audits": [a.to_dict() for a in self.beat_audits],
            "exception_review_beats": list(self.exception_review_beats),
            "stats": dict(self.stats),
        }


def _nearest_regime(zoom: float, regimes: dict[str, Any]) -> str | None:
    if not regimes:
        return None
    best_name: str | None = None
    best_dist = float("inf")
    for name, spec in regimes.items():
        if not isinstance(spec, dict) or "zoom" not in spec:
            continue
        dist = abs(float(spec["zoom"]) - zoom)
        if dist < best_dist:
            best_dist = dist
            best_name = str(name)
    return best_name


def _collect_telemetry_events(
    breakdown: dict[str, Any] | None,
    probe: dict[str, Any] | None,
    camera_track: list[list[float]] | None,
    regimes: dict[str, Any],
) -> list[tuple[float, str]]:
    events: list[tuple[float, str]] = []

    if breakdown:
        for shot in breakdown.get("shots") or []:
            if "start_s" in shot:
                events.append((float(shot["start_s"]), "breakdown_shot"))
            for bt in shot.get("beats_s") or []:
                events.append((float(bt), "breakdown_beat"))
        packaging = breakdown.get("packaging") or {}
        for key in ("ocr_spans", "subtitles", "text_events", "styled_text_events", "events"):
            items = packaging.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                t_val = item.get("start_s", item.get("t_s"))
                if t_val is not None:
                    events.append((float(t_val), "breakdown_ocr"))

    if probe:
        for shot in probe.get("shots") or []:
            if "start_s" in shot:
                events.append((float(shot["start_s"]), "probe_shot"))

    if camera_track:
        prev_regime: str | None = None
        prev_zoom: float | None = None
        for sample in camera_track:
            if len(sample) < 4:
                continue
            t_val, zoom = float(sample[0]), float(sample[3])
            regime = _nearest_regime(zoom, regimes)
            if prev_zoom is None or regime != prev_regime or abs(zoom - prev_zoom) >= 0.35:
                events.append((t_val, "camera_regime"))
            prev_regime = regime
            prev_zoom = zoom

    events.sort(key=lambda pair: pair[0])
    return events


def _cluster_events(
    events: list[tuple[float, str]], tol_s: float = 0.15
) -> list[tuple[float, list[str]]]:
    if not events:
        return []
    clusters: list[list[tuple[float, str]]] = [[events[0]]]
    for t_val, src in events[1:]:
        if abs(t_val - clusters[-1][-1][0]) <= tol_s:
            clusters[-1].append((t_val, src))
        else:
            clusters.append([(t_val, src)])
    summarized: list[tuple[float, list[str]]] = []
    for group in clusters:
        rep_t = round(statistics.median(t for t, _ in group), 3)
        sources = sorted({src for _, src in group})
        summarized.append((rep_t, sources))
    return summarized


def draft_reference_storyboard(
    transcript: dict[str, Any],
    idioms: dict[str, Any],
    *,
    project_id: str,
    breakdown: dict[str, Any] | None = None,
    probe: dict[str, Any] | None = None,
    camera_track: list[list[float]] | None = None,
    snap_window_s: tuple[float, float] = (-1.5, 0.5),
) -> ReferenceInversionResult:
    """Invert measured breakdown/probe/camera telemetry into a draft reference storyboard."""
    sb = scaffold_storyboard(transcript, idioms, project_id=project_id, pacing="dense")
    sb["directing_source"] = "reference"

    regimes = idioms.get("camera_regimes") or {}
    raw_events = _collect_telemetry_events(breakdown, probe, camera_track, regimes)
    clusters = _cluster_events(raw_events)

    beat_audits: list[BeatInversionAudit] = []
    exception_review_beats: list[dict[str, Any]] = []
    prev_start = -0.05

    for idx, beat in enumerate(sb["beats"]):
        bid = str(beat["beat_id"])
        original_onset = float(beat["start_s"])
        sync_s = float(beat.get("sync_word_s", original_onset))

        lead_info = _device_lead_window(idioms, beat["device"])
        if lead_info is not None:
            mid_lead = (float(lead_info[1][0]) + float(lead_info[1][1])) / 2.0
        else:
            mid_lead = 0.2
        expected_onset = max(0.0, sync_s - mid_lead)

        lo_t = sync_s + float(snap_window_s[0])
        hi_t = sync_s + float(snap_window_s[1])
        in_window = [(t, srcs) for t, srcs in clusters if lo_t <= t <= hi_t]

        if in_window:
            snapped_t, sources = max(
                in_window,
                key=lambda item: (len(item[1]), -abs(item[0] - expected_onset)),
            )
            delta = abs(snapped_t - original_onset)
            if len(sources) >= 2 or delta <= 0.6:
                confidence: ConfidenceLevel = "high"
            elif delta <= 0.8:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            snapped_t = original_onset
            sources = []
            confidence = "low"

        min_start = 0.0 if idx == 0 else round(prev_start + 0.05, 3)
        snapped_t = round(max(min_start, snapped_t), 3)
        prev_start = snapped_t
        beat["start_s"] = snapped_t
        beat["end_s"] = round(max(float(beat["end_s"]), snapped_t + 0.25), 3)

        if camera_track and regimes:
            nearest_cam = min(camera_track, key=lambda row: abs(float(row[0]) - sync_s))
            if abs(float(nearest_cam[0]) - sync_s) <= 0.5 and len(nearest_cam) >= 4:
                zoom = float(nearest_cam[3])
                regime = _nearest_regime(zoom, regimes)
                if regime is not None:
                    beat["camera"] = {"regime": regime, "zoom": round(zoom, 3)}

        review_reason: str | None = None
        if not sources:
            review_reason = "no corroborated telemetry event inside snap window"
        elif confidence == "low":
            review_reason = "single weak source with large onset shift (> 0.8s)"
        elif abs(snapped_t - original_onset) > 0.8:
            delta_s = snapped_t - original_onset
            review_reason = f"large onset delta ({delta_s:+.2f}s); confirm visually"

        needs_review = confidence == "low" or review_reason is not None
        audit = BeatInversionAudit(
            beat_id=bid,
            confidence=confidence,
            snapped_onset_s=snapped_t,
            original_onset_s=original_onset,
            evidence_sources=sources,
            needs_review=needs_review,
            review_reason=review_reason,
        )
        beat_audits.append(audit)
        if needs_review:
            exception_review_beats.append(
                {
                    "beat_id": bid,
                    "confidence": confidence,
                    "snapped_onset_s": snapped_t,
                    "original_onset_s": original_onset,
                    "evidence_sources": sources,
                    "review_reason": review_reason,
                    "clause": beat.get("clause"),
                    "sync_word": beat.get("sync_word"),
                    "sync_word_s": beat.get("sync_word_s"),
                }
            )

    contract_errors = validate_storyboard_contract(sb)
    if contract_errors:
        raise ValueError(f"Inverted reference storyboard failed contract check: {contract_errors}")

    stats = {
        "total_beats": len(beat_audits),
        "high_confidence_beats": sum(1 for a in beat_audits if a.confidence == "high"),
        "medium_confidence_beats": sum(1 for a in beat_audits if a.confidence == "medium"),
        "low_confidence_beats": sum(1 for a in beat_audits if a.confidence == "low"),
        "exception_review_count": len(exception_review_beats),
        "telemetry_events_collected": len(raw_events),
    }
    return ReferenceInversionResult(
        storyboard=sb,
        beat_audits=beat_audits,
        exception_review_beats=exception_review_beats,
        stats=stats,
    )
