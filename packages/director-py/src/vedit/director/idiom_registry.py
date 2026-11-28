"""Extensible directing idiom registry decoupling core checks from domain-specific plugins."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

IdiomChecker = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], list[Any]]


class IdiomRegistry:
    """Registry mapping `idiom_id` strings to deterministic storyboard check callables."""

    def __init__(self, *, parent: IdiomRegistry | None = None) -> None:
        self._parent = parent
        self._checkers: dict[str, IdiomChecker] = {}
        self._domains: dict[str, str] = {}

    def register(
        self,
        idiom_id: str,
        checker: IdiomChecker,
        *,
        domain: str = "core",
    ) -> None:
        self._checkers[idiom_id] = checker
        self._domains[idiom_id] = domain

    def get(self, idiom_id: str) -> IdiomChecker | None:
        if idiom_id in self._checkers:
            return self._checkers[idiom_id]
        if self._parent is not None:
            return self._parent.get(idiom_id)
        return None

    def check(
        self,
        idiom: dict[str, Any],
        storyboard: dict[str, Any],
        idioms: dict[str, Any],
    ) -> list[Any]:
        checker = self.get(str(idiom["idiom_id"]))
        if checker is None:
            return []
        return checker(idiom, storyboard, idioms)

    def list_ids(self, *, domain: str | None = None) -> list[str]:
        merged: dict[str, str] = {}
        if self._parent is not None:
            for iid in self._parent.list_ids():
                merged[iid] = self._parent._domain_of(iid)
        merged.update(self._domains)
        if domain is None:
            return sorted(merged.keys())
        return sorted(iid for iid, dom in merged.items() if dom == domain)

    def _domain_of(self, idiom_id: str) -> str:
        if idiom_id in self._domains:
            return self._domains[idiom_id]
        if self._parent is not None:
            return self._parent._domain_of(idiom_id)
        return "core"


def _issue(idiom: dict[str, Any], msg: str, beat: dict[str, Any] | None = None) -> Any:
    from vedit.director.storyboard import StoryboardIssue

    return StoryboardIssue(
        idiom["idiom_id"],
        idiom["severity"],
        msg,
        beat["beat_id"] if beat else None,
    )


def _sorted_beats(sb: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(sb["beats"], key=lambda b: b["start_s"])


def _device_lead_window(idioms: dict[str, Any], device: str) -> tuple[str, list[float]] | None:
    for name, cls in (idioms.get("device_classes") or {}).items():
        if device in cls["devices"]:
            return name, cls["lead_s"]
    return None


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


def _clean_word(word: str) -> str:
    return re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", word)


def _check_hook_event_early(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    beats = _sorted_beats(sb)
    max_s = idiom["params"]["max_first_event_s"]
    if beats[0]["start_s"] > max_s:
        return [_issue(idiom, f"first visual event at {beats[0]['start_s']:.2f}s (max {max_s}s)")]
    return []


def _check_story_need_stated(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    marks = [m.lower() for m in idiom["params"].get("placeholder_markers", [])]
    out: list[Any] = []
    for b in _sorted_beats(sb):
        need = b["story_need"].strip().lower()
        if not need or any(need == m or need.startswith(m + " ") for m in marks):
            out.append(_issue(idiom, "story need is a placeholder", b))
    return out


def _check_event_cadence(idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]) -> list[Any]:
    p = idiom["params"]
    pacing = sb.get("pacing", "default")
    max_gap = p["max_gap_s"][pacing] if isinstance(p["max_gap_s"], dict) else p["max_gap_s"]
    beats = _sorted_beats(sb)
    out: list[Any] = []
    for a, b in zip(beats, beats[1:], strict=False):
        gap = b["start_s"] - a["start_s"]
        if gap < p["min_gap_s"] - 1e-6:
            out.append(_issue(idiom, f"events {gap:.2f}s apart (min {p['min_gap_s']}s)", b))
        elif gap > max_gap + 1e-6 and not a.get("hold_reason"):
            out.append(
                _issue(
                    idiom, f"{gap:.2f}s without a new event (max {max_gap}s for {pacing} pacing)", a
                )
            )
    return out


def _check_sync_lead(
    idiom: dict[str, Any], sb: dict[str, Any], idioms: dict[str, Any]
) -> list[Any]:
    tol = idiom["params"].get("tolerance_s", 0.0)
    out: list[Any] = []
    for b in _sorted_beats(sb):
        if "sync_word_s" not in b:
            continue
        found = _device_lead_window(idioms, b["device"])
        if not found:
            continue
        cls, (lo, hi) = found
        lead = b["sync_word_s"] - b["start_s"]
        if not lo - tol <= lead <= hi + tol:
            out.append(
                _issue(
                    idiom,
                    f"{cls} device {b['device']!r} leads its word by {lead:.2f}s "
                    f"(window {lo}..{hi}s)",
                    b,
                )
            )
    return out


def _check_max_concurrent_callouts(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    max_c = idiom["params"]["max_concurrent"]
    spans = [
        (c.get("start_s", b["start_s"]), c.get("end_s", b["end_s"]), b)
        for b in _sorted_beats(sb)
        for c in (b.get("callouts") or [])
    ]
    out: list[Any] = []
    for t0, _, b in spans:
        live = sum(1 for s, e, _ in spans if s <= t0 + 1e-6 and e > t0 + 1e-6)
        if live > max_c:
            out.append(_issue(idiom, f"{live} callouts on screen at {t0:.2f}s (max {max_c})", b))
    return out


def _check_caption_band_clear(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    y0, y1 = idiom["params"]["band_y_pct"]
    height = idiom["params"]["frame_px"][1]
    out: list[Any] = []
    for b in _sorted_beats(sb):
        for c in b.get("callouts") or []:
            if c.get("anchor") == "screen" or "xy" not in c:
                continue
            half = c.get("size_px", 0) / 2
            top, bottom = c["xy"][1] - half, c["xy"][1] + half
            if bottom > y0 * height and top < y1 * height:
                out.append(
                    _issue(idiom, f"{c['kind']} at y={c['xy'][1]:.0f}px enters the caption band", b)
                )
    return out


def _check_callout_min_size(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    mins = idiom["params"]["min_size_px"]
    out: list[Any] = []
    for b in _sorted_beats(sb):
        for c in b.get("callouts") or []:
            need = mins.get(c["kind"])
            if need and "size_px" in c and c["size_px"] < need:
                out.append(_issue(idiom, f"{c['kind']} is {c['size_px']:.0f}px (min {need}px)", b))
    return out


def _check_default_device_share(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    p = idiom["params"]
    beats = _sorted_beats(sb)
    default = p["default_device"]
    share = sum(1 for b in beats if b["device"] == default) / len(beats)
    if share > p["max_share"] + 1e-6:
        return [
            _issue(
                idiom,
                f"{share:.0%} of beats use the fallback device {default!r} "
                f"(max {p['max_share']:.0%}); give those clauses a concrete visual answer",
            )
        ]
    return []


def _check_obstacles_differ(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    obstacles = [b for b in _sorted_beats(sb) if b["function"] == "obstacle"]
    out: list[Any] = []
    for a, b in zip(obstacles, obstacles[1:], strict=False):
        if a["device"] == b["device"] and a.get("treatment") == b.get("treatment"):
            out.append(
                _issue(
                    idiom,
                    f"repeats device {b['device']!r} and treatment of the previous obstacle",
                    b,
                )
            )
    return out


def _check_signature_image_persists(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    if sb["story"].get("signature_image"):
        uses = sum(1 for b in _sorted_beats(sb) if b.get("uses_signature_image"))
        min_b = idiom["params"]["min_beats"]
        if uses < min_b:
            return [_issue(idiom, f"signature image used in {uses} beat(s) (min {min_b})")]
    return []


def _check_ending_present(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    beats = _sorted_beats(sb)
    if beats[-1]["function"] not in idiom["params"]["functions"]:
        return [_issue(idiom, f"last beat function is {beats[-1]['function']!r}", beats[-1])]
    return []


def _check_variation_against_recent(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    story = sb["story"]
    lookback = int(idiom["params"].get("lookback", 0))
    recent = (sb.get("recent_episodes") or [])[-lookback:] if lookback > 0 else []
    out: list[Any] = []
    for ep in recent:
        same_hook = (
            story.get("hook_mechanism") and ep.get("hook_mechanism") == story["hook_mechanism"]
        )
        same_end = story.get("ending_type") and ep.get("ending_type") == story["ending_type"]
        if same_hook and same_end:
            out.append(
                _issue(idiom, f"hook and ending both repeat episode {ep.get('project_id', '?')!r}")
            )
        sig = story.get("signature_image")
        if sig and ep.get("signature_image") == sig:
            out.append(
                _issue(idiom, f"signature image repeats episode {ep.get('project_id', '?')!r}")
            )
    return out


def _check_numeric_parity(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    p = idiom["params"]
    ignore_years = bool(p.get("ignore_years", True))
    rel_tol = float(p.get("rel_tolerance", 0.02))
    out: list[Any] = []
    for b in _sorted_beats(sb):
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
            out.append(
                _issue(
                    idiom,
                    f"spoken number {missing[0]:g} does not match callout values {callout_nums}",
                    b,
                )
            )
    return out


def _check_callout_safe_margins(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    p = idiom["params"]
    frame_w, frame_h = p.get("frame_px", [1080, 1920])
    min_x, max_x = float(p.get("min_x_pct", 0.08)), float(p.get("max_x_pct", 0.92))
    min_y, max_y = float(p.get("min_y_pct", 0.12)), float(p.get("max_y_pct", 0.88))
    ruler_min_top = float(p.get("scale_ruler_min_top_pct", 0.12))
    out: list[Any] = []
    for b in _sorted_beats(sb):
        is_ruler = b.get("device") in ("measurement_line", "scale_ruler")
        for c in b.get("callouts") or []:
            xy = c.get("xy")
            if not isinstance(xy, (list, tuple)) or len(xy) != 2:
                continue
            x_pct, y_pct = float(xy[0]) / float(frame_w), float(xy[1]) / float(frame_h)
            if x_pct < min_x or x_pct > max_x:
                out.append(
                    _issue(
                        idiom,
                        f"callout x={xy[0]:.0f}px ({x_pct:.0%}) violates safe margin "
                        f"[{min_x:.0%}, {max_x:.0%}]",
                        b,
                    )
                )
                break
            min_req_y = ruler_min_top if is_ruler else min_y
            if y_pct < min_req_y or y_pct > max_y:
                out.append(
                    _issue(
                        idiom,
                        f"callout y={xy[1]:.0f}px ({y_pct:.0%}) violates safe margin "
                        f"[{min_req_y:.0%}, {max_y:.0%}]",
                        b,
                    )
                )
                break
    return out


def _check_curiosity_loops_closed(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    loops = (sb.get("story") or {}).get("curiosity_loops") or []
    if not loops:
        return []
    beats = _sorted_beats(sb)
    beat_pos = {b["beat_id"]: (idx, b) for idx, b in enumerate(beats)}
    min_deferred = min(
        float(idiom["params"].get("min_deferred_span_s", 15.0)),
        max(3.0, float(sb.get("duration_s", 60.0)) * 0.30),
    )
    has_deferred = False
    out: list[Any] = []
    for lp in loops:
        lid = lp.get("loop_id", "?")
        open_id = lp.get("opened_beat_id")
        payoff_id = lp.get("payoff_beat_id")
        hinge_id = lp.get("promise_hinge_beat_id")
        if open_id not in beat_pos:
            out.append(_issue(idiom, f"curiosity loop {lid!r} opens at unknown beat {open_id!r}"))
            continue
        if hinge_id and hinge_id not in beat_pos:
            out.append(
                _issue(idiom, f"curiosity loop {lid!r} promise hinge {hinge_id!r} does not exist")
            )
        if not payoff_id:
            out.append(
                _issue(idiom, f"curiosity loop {lid!r} has no payoff_beat_id", beat_pos[open_id][1])
            )
            continue
        if payoff_id not in beat_pos:
            out.append(
                _issue(idiom, f"curiosity loop {lid!r} payoff beat {payoff_id!r} does not exist")
            )
            continue
        oi, ob = beat_pos[open_id]
        pi, pb = beat_pos[payoff_id]
        if pi <= oi:
            out.append(
                _issue(idiom, f"curiosity loop {lid!r} pays off before or at its opening beat", pb)
            )
            continue
        if float(pb["start_s"]) - float(ob["start_s"]) >= min_deferred:
            has_deferred = True
    if not has_deferred and float(sb.get("duration_s", 0.0)) >= 12.0:
        out.append(
            _issue(
                idiom,
                f"no curiosity loop outlives {min_deferred:.1f}s "
                "(open at least one deferred payoff loop)",
            )
        )
    return out


def _check_tension_arc_dynamic(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    t_vals = [
        float(b["tension_level"]) for b in _sorted_beats(sb) if b.get("tension_level") is not None
    ]
    if len(t_vals) >= 4:
        min_range = float(idiom["params"].get("min_range", 0.25))
        if max(t_vals) - min(t_vals) < min_range - 1e-6:
            return [
                _issue(
                    idiom,
                    f"tension_level range {max(t_vals) - min(t_vals):.2f} is below "
                    f"minimum {min_range:.2f}; story arc reads flat",
                )
            ]
    return []


def _check_shot_direction_continuity(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    prev_dir: str | None = None
    out: list[Any] = []
    for b in _sorted_beats(sb):
        cur_dir = (b.get("shot") or {}).get("motion_direction")
        if cur_dir in ("left_to_right", "right_to_left") and prev_dir in (
            "left_to_right",
            "right_to_left",
        ):
            if cur_dir != prev_dir:
                out.append(
                    _issue(
                        idiom,
                        f"horizontal motion flips from {prev_dir!r} to {cur_dir!r} "
                        "without a neutral shot",
                        b,
                    )
                )
        if cur_dir:
            prev_dir = cur_dir
    return out


def _check_split_edit_bounds(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    max_off = float(idiom["params"].get("max_offset_s", 2.5))
    out: list[Any] = []
    for b in _sorted_beats(sb):
        se = b.get("split_edit")
        if not isinstance(se, dict):
            continue
        off = float(se.get("offset_s", 0.0))
        if off > max_off + 1e-6:
            out.append(_issue(idiom, f"split_edit offset {off:.2f}s exceeds max {max_off:.2f}s", b))
        elif se.get("kind") == "j_cut" and off > float(b["start_s"]) + 1e-6:
            out.append(_issue(idiom, f"j_cut offset {off:.2f}s pre-laps before timeline t=0", b))
    return out


def _check_narrative_framework_structure(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    beats = _sorted_beats(sb)
    story = sb.get("story") or {}
    fw = str(story.get("narrative_framework") or "")
    total_dur = max(float(sb.get("duration_s") or 0.0), 1e-6)
    beat_idx_map = {b["beat_id"]: (idx, b) for idx, b in enumerate(beats)}
    out: list[Any] = []
    if fw == "story_circle":
        sc_map = story.get("story_circle_map") or {}
        if not isinstance(sc_map, dict) or not sc_map:
            out.append(
                _issue(idiom, "story_circle framework requires a populated story_circle_map")
            )
        else:
            steps = ("you", "need", "go", "search", "find", "take", "return", "change")
            present = [(st, sc_map[st]) for st in steps if st in sc_map]
            if len(present) < 4:
                out.append(
                    _issue(
                        idiom, f"story_circle_map covers only {len(present)} of 8 steps (minimum 4)"
                    )
                )
            prev_pos = -1
            for st, bid in present:
                if bid not in beat_idx_map:
                    out.append(
                        _issue(idiom, f"story_circle step {st!r} references unknown beat {bid!r}")
                    )
                    continue
                pos = beat_idx_map[bid][0]
                if pos < prev_pos:
                    out.append(
                        _issue(
                            idiom,
                            f"story_circle step {st!r} occurs out of narrative order",
                            beat_idx_map[bid][1],
                        )
                    )
                prev_pos = pos
    elif fw == "three_act" and len(beats) >= 6:
        act1_beats = [b for b in beats if b.get("function") in ("hook", "setup")]
        climax_beats = [b for b in beats if b.get("function") in ("climax", "outro")]
        if act1_beats:
            act1_end = max(float(b.get("end_s", 0.0)) for b in act1_beats) / total_dur
            if act1_end < 0.08 or act1_end > 0.45:
                out.append(
                    _issue(idiom, f"three_act setup finishes at {act1_end:.0%} (expected 8%-45%)")
                )
        if climax_beats:
            climax_start = min(float(b.get("start_s", 0.0)) for b in climax_beats) / total_dur
            if climax_start < 0.65:
                out.append(
                    _issue(idiom, f"three_act climax starts early at {climax_start:.0%} (< 65%)")
                )
    elif fw == "frame_narrative" and len(beats) >= 4:
        first, last = beats[0], beats[-1]
        same_dev = first.get("device") == last.get("device")
        same_reg = first.get("register") and first.get("register") == last.get("register")
        toks_a = {
            _clean_word(w).lower()
            for w in str(first.get("clause") or "").split()
            if len(_clean_word(w)) >= 4
        }
        toks_b = {
            _clean_word(w).lower()
            for w in str(last.get("clause") or "").split()
            if len(_clean_word(w)) >= 4
        }
        if not (same_dev or same_reg or (toks_a & toks_b)):
            out.append(
                _issue(
                    idiom,
                    "frame_narrative opening and closing beats share no recurring motif, "
                    "register, or device",
                    last,
                )
            )
    return out


def _check_subtext_and_arc_coherence(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    out: list[Any] = []
    arc = (sb.get("story") or {}).get("character_arc")
    if isinstance(arc, dict) and arc.get("kind") not in (None, "none"):
        start_s = str(arc.get("start_state") or "").strip()
        end_s = str(arc.get("end_state") or "").strip()
        if not start_s or not end_s:
            out.append(_issue(idiom, "character_arc must specify both start_state and end_state"))
        elif arc.get("kind") in ("positive", "negative") and start_s.lower() == end_s.lower():
            out.append(
                _issue(
                    idiom,
                    f"character_arc ({arc['kind']}) shows no state shift "
                    "between start_state and end_state",
                )
            )
    for b in _sorted_beats(sb):
        sub = str(b.get("subtext_note") or "").strip()
        if sub and sub.lower() == str(b.get("clause") or "").strip().lower():
            out.append(
                _issue(
                    idiom,
                    "subtext_note literally repeats the spoken clause rather than implied subtext",
                    b,
                )
            )
    return out


def _check_blocking_axis_continuity(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    prev_axis: str | None = None
    out: list[Any] = []
    for b in _sorted_beats(sb):
        axis = (b.get("blocking") or {}).get("axis_side")
        if axis in ("left", "right") and prev_axis in ("left", "right") and axis != prev_axis:
            out.append(
                _issue(
                    idiom,
                    f"blocking axis_side flips from {prev_axis!r} to {axis!r} across cut "
                    "without neutral beat",
                    b,
                )
            )
        if axis:
            prev_axis = axis
    return out


def core_idiom_registry() -> IdiomRegistry:
    """Return a fresh IdiomRegistry containing strictly brand/domain-agnostic core idioms."""
    reg = IdiomRegistry()
    reg.register("hook_event_early", _check_hook_event_early, domain="core")
    reg.register("story_need_stated", _check_story_need_stated, domain="core")
    reg.register("event_cadence", _check_event_cadence, domain="core")
    reg.register("sync_lead", _check_sync_lead, domain="core")
    reg.register("max_concurrent_callouts", _check_max_concurrent_callouts, domain="core")
    reg.register("caption_band_clear", _check_caption_band_clear, domain="core")
    reg.register("callout_min_size", _check_callout_min_size, domain="core")
    reg.register("default_device_share", _check_default_device_share, domain="core")
    reg.register("obstacles_differ", _check_obstacles_differ, domain="core")
    reg.register("signature_image_persists", _check_signature_image_persists, domain="core")
    reg.register("ending_present", _check_ending_present, domain="core")
    reg.register("variation_against_recent", _check_variation_against_recent, domain="core")
    reg.register("numeric_parity", _check_numeric_parity, domain="core")
    reg.register("callout_safe_margins", _check_callout_safe_margins, domain="core")
    reg.register("curiosity_loops_closed", _check_curiosity_loops_closed, domain="core")
    reg.register("tension_arc_dynamic", _check_tension_arc_dynamic, domain="core")
    reg.register("shot_direction_continuity", _check_shot_direction_continuity, domain="core")
    reg.register("split_edit_bounds", _check_split_edit_bounds, domain="core")
    reg.register(
        "narrative_framework_structure", _check_narrative_framework_structure, domain="core"
    )
    reg.register("subtext_and_arc_coherence", _check_subtext_and_arc_coherence, domain="core")
    reg.register("blocking_axis_continuity", _check_blocking_axis_continuity, domain="core")
    return reg


def _build_default_registry() -> IdiomRegistry:
    reg = core_idiom_registry()
    from vedit.geo.idioms import register_geo_idioms

    register_geo_idioms(reg)
    return reg


DEFAULT_IDIOM_REGISTRY: IdiomRegistry = _build_default_registry()
