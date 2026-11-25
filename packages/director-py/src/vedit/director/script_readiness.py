"""Pre-voiceover script visualizability and breath-pause readiness audit."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from vedit.director.storyboard import (
    _device_lead_window,
    _split_clauses,
    check_storyboard,
    scaffold_storyboard,
)

FindingCode = Literal[
    "dry_clause_streak",
    "high_fallback_share",
    "compressed_beat",
    "weak_hook_window",
    "needs_breath_pause",
    "throat_clearing_opening",
    "flat_pacing_variance",
    "low_show_dont_tell_ratio",
    "trailing_bloat_outro",
    "kinetic_legibility_risk",
]

_TRAILING_BLOAT_PHRASES: tuple[str, ...] = (
    "thanks for watching",
    "don't forget to",
    "subscribe",
    "like and comment",
)

_THROAT_CLEARING_PHRASES: tuple[str, ...] = (
    "hey guys",
    "welcome back",
    "in this video",
    "today we are going to",
    "today we're going to",
    "before we begin",
)

_TELLING_EXPOSITION_PHRASES: tuple[str, ...] = (
    "basically",
    "actually means",
    "simply put",
    "in other words",
    "to put it simply",
    "the reason is simple",
)


@dataclass(slots=True)
class ReadinessFinding:
    """Single script readiness diagnostic tied to one or more beat IDs."""

    code: FindingCode
    severity: Literal["warning", "error"]
    beat_ids: list[str]
    message: str
    recommended_pause_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScriptReadinessReport:
    """Summary of pre-VO script visualizability and narration pacing."""

    ready: bool
    fallback_share: float
    dry_streak_max: int
    findings: list[ReadinessFinding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "fallback_share": self.fallback_share,
            "dry_streak_max": self.dry_streak_max,
            "findings": [f.to_dict() for f in self.findings],
            "summary": dict(self.summary),
        }


def _idiom_params(idioms: dict[str, Any], idiom_id: str) -> dict[str, Any]:
    for item in idioms.get("idioms") or []:
        if item.get("idiom_id") == idiom_id:
            return dict(item.get("params") or {})
    return {}


def audit_script_readiness(
    transcript: dict[str, Any],
    idioms: dict[str, Any],
    *,
    pacing: str = "default",
    max_dry_streak: int = 3,
) -> ScriptReadinessReport:
    """Audit a word-level transcript for visualizable concreteness and breath-pause spacing."""
    storyboard = scaffold_storyboard(
        transcript,
        idioms,
        project_id="readiness_probe",
        pacing=pacing,
    )
    sb_report = check_storyboard(storyboard, idioms)
    beats = storyboard["beats"]

    default_params = _idiom_params(idioms, "default_device_share")
    default_device = str(default_params.get("default_device") or "camera_drift")
    max_share = float(default_params.get("max_share", 0.35))

    cadence_params = _idiom_params(idioms, "event_cadence")
    min_gap_s = float(cadence_params.get("min_gap_s", 0.25))

    auto_cfg = idioms.get("auto_director") or {}
    hook_window_s = float(auto_cfg.get("hook_window_s", 3.0))
    extra_phrases = idioms.get("readiness_phrases") or {}
    throat_phrases = _THROAT_CLEARING_PHRASES + tuple(
        str(p).lower() for p in extra_phrases.get("throat_clearing", ())
    )
    trailing_phrases = _TRAILING_BLOAT_PHRASES + tuple(
        str(p).lower() for p in extra_phrases.get("trailing_bloat", ())
    )
    telling_phrases = _TELLING_EXPOSITION_PHRASES + tuple(
        str(p).lower() for p in extra_phrases.get("telling_exposition", ())
    )

    findings: list[ReadinessFinding] = []
    fallback_ids = [b["beat_id"] for b in beats if b["device"] == default_device]
    fallback_share = round(len(fallback_ids) / max(len(beats), 1), 4)

    if fallback_share > max_share + 1e-6:
        findings.append(
            ReadinessFinding(
                code="high_fallback_share",
                severity="error",
                beat_ids=fallback_ids,
                message=(
                    f"{fallback_share:.0%} of clauses fall back to {default_device!r} "
                    f"(max {max_share:.0%}); add concrete places, numbers, or action verbs."
                ),
            )
        )

    def _flush_streak(streak: list[str]) -> None:
        if len(streak) >= max_dry_streak:
            findings.append(
                ReadinessFinding(
                    code="dry_clause_streak",
                    severity="error",
                    beat_ids=list(streak),
                    message=(
                        f"{len(streak)} consecutive abstract clauses "
                        f"({streak[0]}..{streak[-1]}) lack concrete visual cues."
                    ),
                )
            )

    dry_streak_max = 0
    current_streak: list[str] = []
    for beat in beats:
        if beat["device"] == default_device:
            current_streak.append(beat["beat_id"])
            dry_streak_max = max(dry_streak_max, len(current_streak))
        else:
            _flush_streak(current_streak)
            current_streak = []
    _flush_streak(current_streak)

    hook_concrete = any(
        b["device"] != default_device and b["start_s"] <= hook_window_s for b in beats
    )
    if beats and (beats[0]["device"] == default_device or not hook_concrete):
        findings.append(
            ReadinessFinding(
                code="weak_hook_window",
                severity="warning",
                beat_ids=[beats[0]["beat_id"]],
                message=(
                    f"Opening hook window ({hook_window_s:.1f}s) lacks a strong concrete "
                    "anchor on the opening beat."
                ),
            )
        )

    words = [w for w in transcript.get("words", []) if w.get("text", "").strip()]
    clauses = _split_clauses(words, auto_cfg["clause_split"])
    clause_durs: list[float] = []
    telling_ids: list[str] = []
    max_clause_wpm = 0.0
    fast_burst_ids: list[str] = []
    for idx, (beat, clause) in enumerate(zip(beats, clauses, strict=False)):
        spoken_dur = max(0.0, float(clause[-1]["end_s"]) - float(clause[0]["start_s"]))
        clause_durs.append(spoken_dur)
        if len(clause) >= 4 and spoken_dur > 0.05:
            wpm = round((len(clause) / spoken_dur) * 60.0, 1)
            max_clause_wpm = max(max_clause_wpm, wpm)
            if wpm > 260.0:
                fast_burst_ids.append(beat["beat_id"])
        clause_low = str(beat.get("clause") or "").lower()
        if idx == 0 and any(p in clause_low for p in throat_phrases):
            findings.append(
                ReadinessFinding(
                    code="throat_clearing_opening",
                    severity="warning",
                    beat_ids=[beat["beat_id"]],
                    message=(
                        "Opening clause uses preamble/greeting phrasing; enter late directly "
                        "inside the story tension or anomaly."
                    ),
                )
            )
        if idx == len(beats) - 1 and any(p in clause_low for p in trailing_phrases):
            findings.append(
                ReadinessFinding(
                    code="trailing_bloat_outro",
                    severity="warning",
                    beat_ids=[beat["beat_id"]],
                    message=(
                        "Final clause contains generic sign-off/CTA filler; leave early on "
                        "the narrative resolution or resonant image."
                    ),
                )
            )
        if (
            any(p in clause_low for p in telling_phrases)
            and beat["device"] == default_device
        ):
            telling_ids.append(beat["beat_id"])

        lead_info = _device_lead_window(idioms, beat["device"])
        lo = float(lead_info[1][0]) if lead_info else 0.0
        min_needed = max(min_gap_s, lo + 0.15)
        if lo >= 0.25 and spoken_dur < min_needed:
            pause_ms = max(250, int(round((min_needed - spoken_dur + 0.25) * 1000)))
            findings.append(
                ReadinessFinding(
                    code="needs_breath_pause",
                    severity="warning",
                    beat_ids=[beat["beat_id"]],
                    message=(
                        f"Clause {beat['beat_id']} ({spoken_dur:.2f}s) is too compressed for "
                        f"device {beat['device']!r} (needs >= {min_needed:.2f}s); "
                        "insert a breath pause."
                    ),
                    recommended_pause_ms=pause_ms,
                )
            )
        elif spoken_dur < min_gap_s:
            findings.append(
                ReadinessFinding(
                    code="compressed_beat",
                    severity="warning",
                    beat_ids=[beat["beat_id"]],
                    message=(
                        f"Clause {beat['beat_id']} spoken span {spoken_dur:.2f}s is below "
                        f"minimum event spacing ({min_gap_s:.2f}s)."
                    ),
                )
            )

    pacing_std_s = round(float(statistics.pstdev(clause_durs)), 3) if len(clause_durs) >= 2 else 0.0
    if len(clause_durs) >= 8 and pacing_std_s < 0.22:
        findings.append(
            ReadinessFinding(
                code="flat_pacing_variance",
                severity="warning",
                beat_ids=[b["beat_id"] for b in beats[:3]],
                message=(
                    f"Clause duration std dev is {pacing_std_s:.2f}s (< 0.22s); "
                    "vary short punchy clauses with breathing holds."
                ),
            )
        )

    show_dont_tell_score = round(
        max(0.0, 1.0 - fallback_share - (len(telling_ids) / max(len(beats), 1)) * 0.25), 3
    )
    if len(beats) >= 4 and (
        len(telling_ids) / len(beats) > 0.25 or show_dont_tell_score < 0.55
    ):
        findings.append(
            ReadinessFinding(
                code="low_show_dont_tell_ratio",
                severity="warning",
                beat_ids=telling_ids or fallback_ids[:4],
                message=(
                    f"Show-don't-tell score is {show_dont_tell_score:.2f}; replace abstract "
                    "exposition clauses with visible nouns, actions, or measurements."
                ),
            )
        )

    if fast_burst_ids:
        findings.append(
            ReadinessFinding(
                code="kinetic_legibility_risk",
                severity="warning",
                beat_ids=fast_burst_ids,
                message=(
                    f"{len(fast_burst_ids)} dense spoken burst(s) exceed kinetic typography "
                    f"reading speed (peak {max_clause_wpm:.0f} WPM); keep overlays punchy."
                ),
            )
        )

    error_count = sum(1 for f in findings if f.severity == "error")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    ready = error_count == 0
    return ScriptReadinessReport(
        ready=ready,
        fallback_share=fallback_share,
        dry_streak_max=dry_streak_max,
        findings=findings,
        summary={
            "beat_count": len(beats),
            "fallback_count": len(fallback_ids),
            "storyboard_score": sb_report.score,
            "show_dont_tell_score": show_dont_tell_score,
            "pacing_std_s": pacing_std_s,
            "max_clause_wpm": max_clause_wpm,
            "error_count": error_count,
            "warning_count": warning_count,
            "pacing": pacing,
        },
    )
