"""Deterministic audio-visual temporal sync, cut offset, and dead-motion audit."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FixKind = Literal["timing", "layout", "device", "camera", "audio_sync", "script"]

_MOTION_ENERGY_FLOOR = 0.02


@dataclass(slots=True)
class TemporalSyncReport:
    """Measured audio-visual sync, cut offsets, and dead-motion windows."""

    passed: bool
    sfx_matched_ratio: float | None
    median_av_offset_ms: float | None
    dead_motion_windows: list[dict[str, float]] = field(default_factory=list)
    split_cut_offsets_s: list[float] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _nearest_beat_start(t: float, beat_starts: list[float]) -> float:
    return min(beat_starts, key=lambda bs: abs(t - bs))


def _span_covered_by_hold(start_s: float, end_s: float, beats: list[dict[str, Any]]) -> bool:
    for beat in beats:
        if not beat.get("hold_reason"):
            continue
        b_start = float(beat.get("start_s", 0.0))
        b_end = float(beat.get("end_s", b_start))
        if b_start <= end_s and b_end >= start_s:
            return True
    return False


def audit_temporal_sync(
    storyboard: dict[str, Any],
    *,
    audio_events_s: list[float] | None = None,
    cuts_s: list[float] | None = None,
    motion_energy_series: list[tuple[float, float]] | None = None,
    max_av_offset_ms: float = 120.0,
    max_dead_window_s: float = 2.5,
) -> TemporalSyncReport:
    """Audit audio event sync, J/L cut offsets, and zero-motion dead zones against a storyboard."""
    beats = sorted(storyboard.get("beats") or [], key=lambda b: float(b.get("start_s", 0.0)))
    beat_starts = [float(b["start_s"]) for b in beats]
    issues: list[str] = []

    sfx_matched_ratio: float | None = None
    median_av_offset_ms: float | None = None
    if audio_events_s is not None and beat_starts:
        if audio_events_s:
            offsets_ms = [
                abs(float(ev) - _nearest_beat_start(float(ev), beat_starts)) * 1000.0
                for ev in audio_events_s
            ]
            matched = sum(1 for off in offsets_ms if off <= max_av_offset_ms)
            sfx_matched_ratio = round(matched / len(offsets_ms), 4)
            median_av_offset_ms = round(statistics.median(offsets_ms), 2)
            if median_av_offset_ms > max_av_offset_ms:
                issues.append(
                    f"median AV offset {median_av_offset_ms:.1f} ms exceeds "
                    f"limit {max_av_offset_ms:.1f} ms"
                )
            if sfx_matched_ratio < 0.75:
                issues.append(
                    f"only {sfx_matched_ratio:.0%} of audio events align within "
                    f"+/-{max_av_offset_ms:.0f} ms of a beat onset"
                )
        else:
            sfx_matched_ratio = 1.0
            median_av_offset_ms = 0.0

    split_cut_offsets_s: list[float] = []
    if cuts_s and beat_starts:
        for cut in cuts_s:
            c_val = float(cut)
            nearest = _nearest_beat_start(c_val, beat_starts)
            split_cut_offsets_s.append(round(c_val - nearest, 3))

    dead_motion_windows: list[dict[str, float]] = []
    if motion_energy_series:
        ordered = sorted((float(t), float(e)) for t, e in motion_energy_series)
        span_start: float | None = None
        last_low_t: float | None = None

        def _flush_low(end_t: float) -> None:
            nonlocal span_start, last_low_t
            if span_start is not None:
                dur = round(end_t - span_start, 3)
                if dur > max_dead_window_s and not _span_covered_by_hold(span_start, end_t, beats):
                    dead_motion_windows.append(
                        {
                            "start_s": round(span_start, 3),
                            "end_s": round(end_t, 3),
                            "duration_s": dur,
                        }
                    )
            span_start = None
            last_low_t = None

        for t_val, energy in ordered:
            if energy <= _MOTION_ENERGY_FLOOR:
                if span_start is None:
                    span_start = t_val
                last_low_t = t_val
            elif span_start is not None:
                _flush_low(t_val)
        if span_start is not None and last_low_t is not None:
            _flush_low(last_low_t)

        if dead_motion_windows:
            issues.append(
                f"{len(dead_motion_windows)} dead-motion window(s) exceed {max_dead_window_s:.1f}s "
                "without hold_reason"
            )

    return TemporalSyncReport(
        passed=len(issues) == 0,
        sfx_matched_ratio=sfx_matched_ratio,
        median_av_offset_ms=median_av_offset_ms,
        dead_motion_windows=dead_motion_windows,
        split_cut_offsets_s=split_cut_offsets_s,
        issues=issues,
    )
