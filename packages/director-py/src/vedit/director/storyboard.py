"""Storyboards: the typed directing plan between narration and the EditPlan / map scene.

Layers, lowest to highest priority:

1. Brand directing idioms (`profiles/brands/<brand_id>/directing_idioms.json`): executable
   checks with default parameters, plus the defaults the automatic director uses.
2. The storyboard itself, produced by `scaffold_storyboard` from a transcript when no director
   input exists (`directing_source: auto`), or authored by a director (`user` / `mixed`).
3. `storyboard.overrides`: per-film idiom parameters, disabled idioms, locked beats, emphasis
   words, and banned devices.

`check_storyboard` scores a storyboard against the merged idioms so an automatic plan is held
to the same standard as a directed one.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root, validate_against_contract

STORYBOARD_SCHEMA = "storyboard.schema.json"
IDIOMS_SCHEMA = "directing_idioms.schema.json"


@dataclass
class StoryboardIssue:
    idiom_id: str
    severity: str
    message: str
    beat_id: str | None = None


@dataclass
class StoryboardReport:
    score: float
    passed: bool
    issues: list[StoryboardIssue] = field(default_factory=list)
    idioms_checked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "error_count": sum(1 for i in self.issues if i.severity == "error"),
            "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
            "idioms_checked": self.idioms_checked,
            "issues": [asdict(i) for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Loading and merging
# ---------------------------------------------------------------------------


def idioms_path(brand_id: str, repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    return root / "profiles" / "brands" / brand_id / "directing_idioms.json"


def load_directing_idioms(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_against_contract(data, IDIOMS_SCHEMA)
    if errors:
        raise ValueError(f"{path.name} failed contract check: {errors}")
    return data


def validate_storyboard_contract(storyboard: dict[str, Any]) -> list[str]:
    errors = validate_against_contract(storyboard, STORYBOARD_SCHEMA)
    if errors:
        return errors
    ids = [b.get("beat_id") for b in storyboard.get("beats", [])]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate beat_id values: {dupes}")
    for beat in storyboard.get("beats", []):
        if beat.get("end_s", 0) < beat.get("start_s", 0):
            errors.append(f"beat {beat.get('beat_id')!r} ends before it starts")
    markers = (storyboard.get("route") or {}).get("markers") or {}
    path_len = len((storyboard.get("route") or {}).get("path") or [])
    for name, idx in markers.items():
        if idx >= path_len:
            errors.append(f"route marker {name!r} index {idx} is outside the path")
    for beat in storyboard.get("beats", []):
        head = beat.get("head")
        if head and head["marker"] not in markers:
            errors.append(f"beat {beat['beat_id']!r} head marker {head['marker']!r} is undefined")
    return errors


def merged_idioms(idioms: dict[str, Any], storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    """Brand idioms with storyboard overrides applied (params merged, disabled ones dropped)."""
    overrides = storyboard.get("overrides") or {}
    disabled = set(overrides.get("disabled_idioms") or [])
    params = overrides.get("idiom_params") or {}
    out = []
    for idiom in idioms["idioms"]:
        if idiom["idiom_id"] in disabled:
            continue
        merged = copy.deepcopy(idiom)
        merged["params"].update(params.get(idiom["idiom_id"], {}))
        out.append(merged)
    return out


# ---------------------------------------------------------------------------
# Idiom checks
# ---------------------------------------------------------------------------


def _device_lead_window(idioms: dict[str, Any], device: str) -> tuple[str, list[float]] | None:
    for name, cls in (idioms.get("device_classes") or {}).items():
        if device in cls["devices"]:
            return name, cls["lead_s"]
    return None


def _check(
    idiom: dict[str, Any],
    sb: dict[str, Any],
    idioms: dict[str, Any],
    *,
    registry: Any | None = None,
) -> list[StoryboardIssue]:
    from vedit.director.idiom_registry import DEFAULT_IDIOM_REGISTRY

    active_reg = registry if registry is not None else DEFAULT_IDIOM_REGISTRY
    return active_reg.check(idiom, sb, idioms)


def _extract_numeric_values(text: str, *, skip_years: bool = False) -> list[float]:
    from vedit.director.idiom_registry import _extract_numeric_values as _extract

    return _extract(text, skip_years=skip_years)


def check_storyboard(
    storyboard: dict[str, Any],
    idioms: dict[str, Any],
    *,
    registry: Any | None = None,
) -> StoryboardReport:
    """Run contract validation plus every enabled idiom; score is 100 minus weighted penalties."""
    contract_errors = validate_storyboard_contract(storyboard)
    if contract_errors:
        return StoryboardReport(
            score=0.0,
            passed=False,
            issues=[StoryboardIssue("contract", "error", e) for e in contract_errors],
        )
    active = merged_idioms(idioms, storyboard)
    issues: list[StoryboardIssue] = []
    penalty = 0.0
    n_beats = max(len(storyboard["beats"]), 1)
    for idiom in active:
        found = _check(idiom, storyboard, idioms, registry=registry)
        issues.extend(found)
        if found:
            # Per-beat idioms scale with the share of beats affected; global ones count fully.
            share = min(1.0, len(found) / n_beats) if any(i.beat_id for i in found) else 1.0
            penalty += idiom["weight"] * (0.4 + 0.6 * share) * 10.0
    score = round(max(0.0, 100.0 - penalty), 1)
    passed = not any(i.severity == "error" for i in issues)
    return StoryboardReport(score, passed, issues, [i["idiom_id"] for i in active])


# ---------------------------------------------------------------------------
# Automatic director
# ---------------------------------------------------------------------------

_YEAR = re.compile(r"^(1[5-9]\d\d|20\d\d)$")
_NUMBER = re.compile(r"^\d[\d.,]*%?$")
_NUMBER_WORDS = {
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "hundred",
    "thousand",
    "million",
    "billion",
    "dua",
    "tiga",
    "empat",
    "lima",
    "enam",
    "tujuh",
    "delapan",
    "sembilan",
    "sepuluh",
    "ratus",
    "ribu",
    "juta",
    "miliar",
}


def _clean(word: str) -> str:
    return re.sub(r"[^\w%.,-]", "", word).strip(".,")


def _split_clauses(
    words: list[dict[str, Any]], rules: dict[str, Any]
) -> list[list[dict[str, Any]]]:
    kept = [w for w in words if not w.get("is_filler")]
    puncts = rules.get("punctuation") or [".", "!", "?", ";"]
    pause_s = float(rules.get("pause_s", 0.35))
    max_words = int(rules.get("max_words", 10))
    clauses: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for i, w in enumerate(kept):
        cur.append(w)
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        ends_punct = any(w["text"].rstrip().endswith(p) for p in puncts)
        pause = nxt is not None and nxt["start_s"] - w["end_s"] >= pause_s
        if ends_punct or pause or len(cur) >= max_words or nxt is None:
            clauses.append(cur)
            cur = []
    return clauses


def _classify(
    clause: list[dict[str, Any]], auto: dict[str, Any], sentence_start: bool
) -> tuple[str, dict[str, Any]]:
    stop = {s.lower() for s in auto.get("stopwords") or []}
    questions = {q.lower() for q in auto.get("question_words") or []}
    clause_tokens = [_clean(w["text"]).lower() for w in clause]
    clause_text = " ".join(t for t in clause_tokens if t)
    found: dict[str, dict[str, Any]] = {}
    for k, w in enumerate(clause):
        token = _clean(w["text"])
        low = token.lower()
        if not token:
            continue
        if _YEAR.match(token):
            found.setdefault("year", w)
        elif _NUMBER.match(token) or low in _NUMBER_WORDS:
            found.setdefault("number", w)
        if low in questions:
            found.setdefault("question", w)
        if token[0].isupper() and low not in stop and not (sentence_start and k == 0):
            found.setdefault("proper_noun", w)
        for rule in auto["device_rules"]:
            stems = rule.get("words")
            if not stems:
                continue
            # Single tokens match by stem (>=4 chars) or exact; phrases match clause text.
            matched = False
            for st in stems:
                st_low = st.lower()
                if " " in st_low:
                    if st_low in clause_text and low == st_low.split()[0]:
                        matched = True
                        break
                elif (len(st_low) >= 4 and low.startswith(st_low)) or low == st_low:
                    matched = True
                    break
            if matched:
                found.setdefault(rule["match"], w)
    for rule in auto["device_rules"]:
        if rule["match"] in found:
            return rule["match"], found[rule["match"]]
    content = [w for w in clause if _clean(w["text"]).lower() not in stop] or clause
    return "default", max(content, key=lambda w: len(_clean(w["text"])))


def detect_story_shape(text: str, auto: dict[str, Any]) -> str:
    low = f" {text.lower()} "
    scores = {
        shape: sum(low.count(f" {sig} ") for sig in signals)
        for shape, signals in (auto.get("shape_signals") or {}).items()
    }
    best = max(scores, key=scores.get) if scores else ""
    return best if best and scores[best] > 0 else "free_form"


_FUNCTION_TENSION: dict[str, float] = {
    "hook": 0.72,
    "setup": 0.40,
    "proof": 0.52,
    "data_callout": 0.56,
    "broll_bridge": 0.48,
    "obstacle": 0.68,
    "hinge": 0.76,
    "climax": 0.92,
    "recap": 0.58,
    "outro": 0.45,
}


def scaffold_storyboard(
    transcript: dict[str, Any],
    idioms: dict[str, Any],
    *,
    project_id: str,
    pacing: str = "default",
    emphasis_words: list[str] | None = None,
) -> dict[str, Any]:
    """Build an automatic storyboard from a word-level transcript using brand defaults.

    One beat per clause; the clause's strongest token (year, number, question word, proper
    noun, else longest content word) chooses the device, function and story need from the
    brand's `device_rules`, and the visual onset leads that word by the device class lead.
    The result passes the contract and is meant to be refined, not replaced, by a director.
    """
    auto = idioms["auto_director"]
    words = [w for w in transcript.get("words", []) if w.get("text", "").strip()]
    if not words:
        raise ValueError("Transcript has no words to storyboard.")
    duration = float(transcript.get("duration_s") or words[-1]["end_s"])
    rules = {r["match"]: r for r in auto["device_rules"]}
    emphasis = {w.lower() for w in emphasis_words or []}
    beats: list[dict[str, Any]] = []
    prev_end_punct = True
    for n, clause in enumerate(_split_clauses(words, auto.get("clause_split") or {})):
        match, sync = _classify(clause, auto, sentence_start=prev_end_punct)
        stressed = [w for w in clause if _clean(w["text"]).lower() in emphasis]
        if stressed:
            sync = stressed[0]
        prev_end_punct = clause[-1]["text"].rstrip().endswith((".", "?", "!"))
        default_lead = float(auto.get("default_lead_s", 0.2))
        rule = rules.get(match) or rules["default"]
        found = _device_lead_window(idioms, rule["device"])
        lo, hi = found[1] if found else (0.0, default_lead)
        lead = min(max(default_lead, lo), hi)
        start = max(0.0, sync["start_s"] - lead)
        beats.append(
            {
                "beat_id": f"b{n + 1:03d}",
                "start_s": round(start, 3),
                "end_s": round(max(clause[-1]["end_s"], start + 0.25), 3),
                "clause": " ".join(w["text"].strip() for w in clause),
                "function": rule["function"],
                "story_need": rule["need"],
                "device": rule["device"],
                "sync_word": _clean(sync["text"]),
                "sync_word_s": round(sync["start_s"], 3),
            }
        )
    if not beats:
        raise ValueError("Transcript has no non-filler words to storyboard.")
    # Enforce the minimum event spacing by letting a crowded beat start a little later.
    min_gap = next(
        (i["params"]["min_gap_s"] for i in idioms["idioms"] if i["idiom_id"] == "event_cadence"),
        0.25,
    )
    for a, b in zip(beats, beats[1:], strict=False):
        if b["start_s"] - a["start_s"] < min_gap:
            b["start_s"] = round(a["start_s"] + min_gap, 3)
            b["end_s"] = max(b["end_s"], b["start_s"] + 0.25)
    if beats:
        beats[0]["start_s"] = 0.0
        beats[0]["function"] = "hook"
        hook_until = float(auto.get("hook_window_s", 3.0))
        setup_until = duration * 0.25 if duration >= 180.0 and len(beats) >= 6 else 0.0
        outro_from = duration * (1.0 - float(auto.get("outro_fraction", 0.12)))
        for b in beats[1:]:
            if b["start_s"] < hook_until and b["function"] == "proof":
                b["function"] = "hook"
            elif setup_until > 0.0 and b["end_s"] <= setup_until and b["function"] != "hook":
                b["function"] = "setup"
        for b in beats:
            if b["start_s"] >= outro_from:
                b["function"] = "outro"
        beats[-1]["function"] = "outro"
        for b in beats:
            b.setdefault("tension_level", _FUNCTION_TENSION.get(str(b["function"]), 0.5))
    text = transcript.get("text") or " ".join(w["text"] for w in words)
    story_obj: dict[str, Any] = {"shape": detect_story_shape(text, auto)}
    if duration >= 180.0 and len(beats) >= 6:
        story_obj["narrative_framework"] = "three_act"
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "brand_id": idioms["brand_id"],
        "duration_s": round(duration, 3),
        "directing_source": "auto",
        "pacing": pacing,
        "story": story_obj,
        "overrides": {},
        "beats": beats,
    }


def apply_director_storyboard(auto_sb: dict[str, Any], directed: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial director storyboard over an automatic one.

    Director beats replace automatic beats with the same `beat_id`; `story`, `pacing`,
    `route` and `overrides` fields from the director win. Beats listed in
    `overrides.locked_beat_ids` must come from the director file.
    """
    out = copy.deepcopy(auto_sb)
    for key in ("pacing", "route", "recent_episodes"):
        if key in directed:
            out[key] = copy.deepcopy(directed[key])
    out["story"].update(directed.get("story") or {})
    out["overrides"] = copy.deepcopy(directed.get("overrides") or out.get("overrides") or {})
    by_id = {b["beat_id"]: b for b in directed.get("beats") or []}
    beats = [copy.deepcopy(by_id.pop(b["beat_id"], b)) for b in out["beats"]]
    beats.extend(copy.deepcopy(b) for b in by_id.values())
    out["beats"] = sorted(beats, key=lambda b: b["start_s"])
    locked = set(out["overrides"].get("locked_beat_ids") or [])
    directed_ids = {b["beat_id"] for b in directed.get("beats") or []}
    missing = sorted(locked - directed_ids)
    if missing:
        raise ValueError(f"locked beats missing from the director storyboard: {missing}")
    banned = set(out["overrides"].get("banned_devices") or [])
    fallback_candidates = [
        "camera_drift",
        "static_hold",
        "region_fill",
        *(
            str(b["device"])
            for b in out["beats"]
            if b.get("device") and str(b["device"]) not in banned
        ),
    ]
    fallback_device = next((d for d in fallback_candidates if d not in banned), "static_hold")
    for b in out["beats"]:
        if b["device"] in banned and b["beat_id"] not in locked:
            b["device"] = fallback_device
            b["story_need"] = b["story_need"] or "keep the subject alive while the clause lands"
    out["directing_source"] = "mixed" if out["beats"] != directed.get("beats") else "user"
    return out


def export_shot_list(storyboard: dict[str, Any]) -> dict[str, Any]:
    """Generate a structured production shot list derived from storyboard beats."""
    shots: list[dict[str, Any]] = []
    ordered = sorted(
        storyboard.get("beats") or [],
        key=lambda x: float(x.get("start_s", 0.0)),
    )
    for idx, b in enumerate(ordered, start=1):
        start_s = round(float(b.get("start_s", 0.0)), 3)
        end_s = round(float(b.get("end_s", start_s + 0.5)), 3)
        shot_meta = b.get("shot") or {}
        blocking = b.get("blocking") or {}
        shots.append(
            {
                "shot_number": idx,
                "beat_id": b.get("beat_id"),
                "start_s": start_s,
                "end_s": end_s,
                "duration_s": round(max(0.05, end_s - start_s), 3),
                "function": b.get("function"),
                "device": b.get("device"),
                "register": b.get("register") or "documentary",
                "shot_scale": shot_meta.get("scale"),
                "camera_angle": shot_meta.get("angle"),
                "motion_direction": shot_meta.get("motion_direction"),
                "camera_move": blocking.get("camera_move") or shot_meta.get("movement"),
                "subject_zone": blocking.get("subject_zone"),
                "axis_side": blocking.get("axis_side"),
                "color_mood": b.get("color_mood"),
                "split_edit": b.get("split_edit"),
                "sound_cue": b.get("sound_cue"),
                "clause": b.get("clause"),
            }
        )
    return {
        "schema_version": "1.0",
        "project_id": storyboard.get("project_id", ""),
        "brand_id": storyboard.get("brand_id", ""),
        "duration_s": storyboard.get("duration_s", 0.0),
        "total_shots": len(shots),
        "shots": shots,
    }
