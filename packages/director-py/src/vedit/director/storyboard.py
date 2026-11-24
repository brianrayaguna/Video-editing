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
    idiom: dict[str, Any], sb: dict[str, Any], idioms: dict[str, Any]
) -> list[StoryboardIssue]:
    iid, sev, p = idiom["idiom_id"], idiom["severity"], idiom["params"]
    beats = sorted(sb["beats"], key=lambda b: b["start_s"])
    issues: list[StoryboardIssue] = []

    def add(msg: str, beat: dict[str, Any] | None = None) -> None:
        issues.append(StoryboardIssue(iid, sev, msg, beat["beat_id"] if beat else None))

    if iid == "hook_event_early":
        if beats[0]["start_s"] > p["max_first_event_s"]:
            add(f"first visual event at {beats[0]['start_s']:.2f}s (max {p['max_first_event_s']}s)")
    elif iid == "story_need_stated":
        marks = [m.lower() for m in p.get("placeholder_markers", [])]
        for b in beats:
            need = b["story_need"].strip().lower()
            if not need or any(need == m or need.startswith(m + " ") for m in marks):
                add("story need is a placeholder", b)
    elif iid == "event_cadence":
        pacing = sb.get("pacing", "default")
        max_gap = p["max_gap_s"][pacing] if isinstance(p["max_gap_s"], dict) else p["max_gap_s"]
        for a, b in zip(beats, beats[1:], strict=False):
            gap = b["start_s"] - a["start_s"]
            if gap < p["min_gap_s"] - 1e-6:
                add(f"events {gap:.2f}s apart (min {p['min_gap_s']}s)", b)
            elif gap > max_gap + 1e-6 and not a.get("hold_reason"):
                add(f"{gap:.2f}s without a new event (max {max_gap}s for {pacing} pacing)", a)
    elif iid == "sync_lead":
        tol = p.get("tolerance_s", 0.0)
        for b in beats:
            if "sync_word_s" not in b:
                continue
            found = _device_lead_window(idioms, b["device"])
            if not found:
                continue
            cls, (lo, hi) = found
            lead = b["sync_word_s"] - b["start_s"]
            if not lo - tol <= lead <= hi + tol:
                add(
                    f"{cls} device {b['device']!r} leads its word by {lead:.2f}s "
                    f"(window {lo}..{hi}s)",
                    b,
                )
    elif iid == "head_on_place_name":
        for b in beats:
            head = b.get("head")
            if not head or head.get("motion", "draw") != "draw" or "sync_word_s" not in b:
                continue
            arrive = head.get("arrive_s")
            if arrive is None:
                add("drawing beat has no head arrival time", b)
                continue
            delta = b["sync_word_s"] - arrive
            if delta > p["max_early_s"] + 1e-6 or delta < -p["max_late_s"] - 1e-6:
                add(
                    f"head arrives {delta:+.2f}s relative to the place name "
                    f"(allowed -{p['max_late_s']}..+{p['max_early_s']}s early)",
                    b,
                )
    elif iid == "regime_change_lead":
        lo, hi = p["lead_s"]
        prev = None
        for b in beats:
            regime = (b.get("camera") or {}).get("regime")
            if not regime or regime == "hold":
                continue
            if prev is not None and regime != prev and "sync_word_s" in b:
                start = b["camera"].get("move_start_s", b["start_s"])
                lead = b["sync_word_s"] - start
                if not lo - 1e-6 <= lead <= hi + 1e-6:
                    add(
                        f"camera {prev}->{regime} starts {lead:.2f}s before the word "
                        f"(window {lo}..{hi}s)",
                        b,
                    )
            prev = regime
    elif iid == "max_concurrent_callouts":
        spans = []
        for b in beats:
            for c in b.get("callouts") or []:
                spans.append((c.get("start_s", b["start_s"]), c.get("end_s", b["end_s"]), b))
        for t0, _, b in spans:
            live = sum(1 for s, e, _ in spans if s <= t0 + 1e-6 and e > t0 + 1e-6)
            if live > p["max_concurrent"]:
                add(f"{live} callouts on screen at {t0:.2f}s (max {p['max_concurrent']})", b)
    elif iid == "caption_band_clear":
        y0, y1 = p["band_y_pct"]
        height = p["frame_px"][1]
        for b in beats:
            for c in b.get("callouts") or []:
                if c.get("anchor") == "screen" or "xy" not in c:
                    continue
                half = c.get("size_px", 0) / 2
                top, bottom = c["xy"][1] - half, c["xy"][1] + half
                if bottom > y0 * height and top < y1 * height:
                    add(f"{c['kind']} at y={c['xy'][1]:.0f}px enters the caption band", b)
    elif iid == "callout_min_size":
        mins = p["min_size_px"]
        for b in beats:
            for c in b.get("callouts") or []:
                need = mins.get(c["kind"])
                if need and "size_px" in c and c["size_px"] < need:
                    add(f"{c['kind']} is {c['size_px']:.0f}px (min {need}px)", b)
    elif iid == "default_device_share":
        default = p["default_device"]
        share = sum(1 for b in beats if b["device"] == default) / len(beats)
        if share > p["max_share"] + 1e-6:
            add(
                f"{share:.0%} of beats use the fallback device {default!r} "
                f"(max {p['max_share']:.0%}); give those clauses a concrete visual answer"
            )
    elif iid == "obstacles_differ":
        obstacles = [b for b in beats if b["function"] == "obstacle"]
        for a, b in zip(obstacles, obstacles[1:], strict=False):
            if a["device"] == b["device"] and a.get("treatment") == b.get("treatment"):
                add(f"repeats device {b['device']!r} and treatment of the previous obstacle", b)
    elif iid == "signature_image_persists":
        if sb["story"].get("signature_image"):
            uses = sum(1 for b in beats if b.get("uses_signature_image"))
            if uses < p["min_beats"]:
                add(f"signature image used in {uses} beat(s) (min {p['min_beats']})")
    elif iid == "ending_present":
        if beats[-1]["function"] not in p["functions"]:
            add(f"last beat function is {beats[-1]['function']!r}", beats[-1])
    elif iid == "variation_against_recent":
        story = sb["story"]
        for ep in (sb.get("recent_episodes") or [])[-p["lookback"] :]:
            same_hook = (
                story.get("hook_mechanism") and ep.get("hook_mechanism") == story["hook_mechanism"]
            )
            same_end = story.get("ending_type") and ep.get("ending_type") == story["ending_type"]
            if same_hook and same_end:
                add(f"hook and ending both repeat episode {ep.get('project_id', '?')!r}")
            sig = story.get("signature_image")
            if sig and ep.get("signature_image") == sig:
                add(f"signature image repeats episode {ep.get('project_id', '?')!r}")
    elif iid == "numeric_parity":
        ignore_years = bool(p.get("ignore_years", True))
        rel_tol = float(p.get("rel_tolerance", 0.02))
        for b in beats:
            callouts = b.get("callouts") or []
            if not callouts:
                continue
            skip_yr = ignore_years and b.get("device") != "era_marker"
            clause_nums = _extract_numeric_values(str(b.get("clause", "")), skip_years=skip_yr)
            if not clause_nums:
                continue
            callout_nums: list[float] = []
            for c in callouts:
                text = str(c.get("text") or "")
                if text:
                    callout_nums.extend(_extract_numeric_values(text, skip_years=skip_yr))
            if not callout_nums:
                continue
            missing = [
                cn
                for cn in clause_nums
                if not any(abs(cn - vn) <= max(1e-6, abs(cn) * rel_tol) for vn in callout_nums)
            ]
            if missing:
                add(
                    f"spoken number {missing[0]:g} does not match callout values {callout_nums}",
                    b,
                )
    elif iid == "callout_safe_margins":
        frame_w, frame_h = p.get("frame_px", [1080, 1920])
        min_x = float(p.get("min_x_pct", 0.08))
        max_x = float(p.get("max_x_pct", 0.92))
        min_y = float(p.get("min_y_pct", 0.12))
        max_y = float(p.get("max_y_pct", 0.88))
        ruler_min_top = float(p.get("scale_ruler_min_top_pct", 0.12))
        for b in beats:
            is_ruler_beat = b.get("device") in ("measurement_line", "scale_ruler")
            for c in b.get("callouts") or []:
                xy = c.get("xy")
                if not isinstance(xy, (list, tuple)) or len(xy) != 2:
                    continue
                x_pct = float(xy[0]) / float(frame_w)
                y_pct = float(xy[1]) / float(frame_h)
                if x_pct < min_x or x_pct > max_x:
                    add(
                        f"callout x={xy[0]:.0f}px ({x_pct:.0%}) violates safe margin [{min_x:.0%}, {max_x:.0%}]",
                        b,
                    )
                    break
                min_required_y = ruler_min_top if is_ruler_beat else min_y
                if y_pct < min_required_y or y_pct > max_y:
                    add(
                        f"callout y={xy[1]:.0f}px ({y_pct:.0%}) violates safe margin [{min_required_y:.0%}, {max_y:.0%}]",
                        b,
                    )
                    break
    return issues


def _extract_numeric_values(text: str, *, skip_years: bool = False) -> list[float]:
    values: list[float] = []
    for m in re.finditer(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", text):
        tok = m.group(0)
        if (
            skip_years
            and "," not in tok
            and "." not in tok
            and tok.isdigit()
            and 1500 <= int(tok) <= 2099
        ):
            continue
        values.append(float(tok.replace(",", "")))
    return values


def check_storyboard(storyboard: dict[str, Any], idioms: dict[str, Any]) -> StoryboardReport:
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
        found = _check(idiom, storyboard, idioms)
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
    clauses: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for i, w in enumerate(kept):
        cur.append(w)
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        ends_punct = any(w["text"].rstrip().endswith(p) for p in rules["punctuation"])
        pause = nxt is not None and nxt["start_s"] - w["end_s"] >= rules["pause_s"]
        if ends_punct or pause or len(cur) >= rules["max_words"] or nxt is None:
            clauses.append(cur)
            cur = []
    return clauses


def _classify(
    clause: list[dict[str, Any]], auto: dict[str, Any], sentence_start: bool
) -> tuple[str, dict[str, Any]]:
    stop = {s.lower() for s in auto["stopwords"]}
    questions = {q.lower() for q in auto["question_words"]}
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
        for shape, signals in auto["shape_signals"].items()
    }
    best = max(scores, key=scores.get) if scores else ""
    return best if best and scores[best] > 0 else "free_form"


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
    for n, clause in enumerate(_split_clauses(words, auto["clause_split"])):
        match, sync = _classify(clause, auto, sentence_start=prev_end_punct)
        stressed = [w for w in clause if _clean(w["text"]).lower() in emphasis]
        if stressed:
            sync = stressed[0]
        prev_end_punct = clause[-1]["text"].rstrip().endswith((".", "?", "!"))
        rule = rules[match]
        found = _device_lead_window(idioms, rule["device"])
        lo, hi = found[1] if found else (0.0, auto["default_lead_s"])
        lead = min(max(auto["default_lead_s"], lo), hi)
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
        hook_until = auto["hook_window_s"]
        for b in beats[1:]:
            if b["start_s"] < hook_until and b["function"] == "proof":
                b["function"] = "hook"
        outro_from = duration * (1.0 - auto["outro_fraction"])
        for b in beats:
            if b["start_s"] >= outro_from:
                b["function"] = "outro"
        beats[-1]["function"] = "outro"
    text = transcript.get("text") or " ".join(w["text"] for w in words)
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "brand_id": idioms["brand_id"],
        "duration_s": round(duration, 3),
        "directing_source": "auto",
        "pacing": pacing,
        "story": {"shape": detect_story_shape(text, auto)},
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
    for b in out["beats"]:
        if b["device"] in banned and b["beat_id"] not in locked:
            b["device"] = "camera_drift"
            b["story_need"] = b["story_need"] or "keep the subject alive while the clause lands"
    out["directing_source"] = "mixed" if out["beats"] != directed.get("beats") else "user"
    return out
