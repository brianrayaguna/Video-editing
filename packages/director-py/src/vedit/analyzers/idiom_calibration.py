"""Calibrate a brand's executable directing idioms from annotated reference storyboards.

Reference videos are annotated in the same storyboard format the engine produces
(`directing_source: "reference"`): one beat per narration clause with the device seen on
screen, its visual onset and sync word, callout sizes and positions read from the
grid-anchored contact sheets, camera regimes, and measured route widths. Pooling those
annotations gives measured distributions for every idiom parameter.

`calibrate_idioms` returns the measurements, a proposed idioms file, and a change list with
evidence. Proposals move each existing value toward the measured value by `blend` (1.0 adopts
the measurement), so a single reference refines rather than overwrites the profile. Parameters
with too few samples are reported but left unchanged.
"""

from __future__ import annotations

import copy
import math
import statistics
from typing import Any

from vedit.director.storyboard import validate_storyboard_contract

MIN_SAMPLES = {"gap": 8, "lead": 5, "size": 3, "zoom": 3, "width": 3}
MIN_LEAD_WINDOW_S = 0.2


def _pct(values: list[float], q: float) -> float:
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def _round(x: float, step: float) -> float:
    return round(round(x / step) * step, 4)


def _blend(old: float | None, new: float, blend: float, step: float) -> float:
    if old is None:
        return _round(new, step)
    return _round(old + (new - old) * blend, step)


def _concurrency(beats: list[dict[str, Any]]) -> int:
    spans = [
        (c.get("start_s", b["start_s"]), c.get("end_s", b["end_s"]))
        for b in beats
        for c in b.get("callouts") or []
    ]
    return max((sum(1 for s, e in spans if s <= t0 < e) for t0, _ in spans), default=0)


def measure_references(
    references: list[dict[str, Any]],
    idioms: dict[str, Any],
    camera_tracks: list[list[list[float]] | None] | None = None,
) -> dict[str, Any]:
    """Pool measurable quantities across annotated reference storyboards."""
    class_of = {
        dev: name
        for name, cls in (idioms.get("device_classes") or {}).items()
        for dev in cls["devices"]
    }
    gaps: dict[str, list[float]] = {}
    first_events: list[float] = []
    leads: dict[str, list[float]] = {}
    sizes: dict[str, list[float]] = {}
    widths: dict[str, list[float]] = {}
    zooms: dict[str, list[float]] = {}
    devices: dict[str, int] = {}
    functions: dict[str, int] = {}
    concurrency: list[int] = []
    unclassified: set[str] = set()
    total_beats = 0
    tracks = camera_tracks or [None] * len(references)
    for sb, track in zip(references, tracks, strict=False):
        beats = sorted(sb["beats"], key=lambda b: b["start_s"])
        total_beats += len(beats)
        pacing = sb.get("pacing", "default")
        first_events.append(beats[0]["start_s"])
        for a, b in zip(beats, beats[1:], strict=False):
            if not a.get("hold_reason"):
                gaps.setdefault(pacing, []).append(b["start_s"] - a["start_s"])
        concurrency.append(_concurrency(beats))
        for b in beats:
            devices[b["device"]] = devices.get(b["device"], 0) + 1
            functions[b["function"]] = functions.get(b["function"], 0) + 1
            cls = class_of.get(b["device"])
            if cls is None:
                unclassified.add(b["device"])
            elif "sync_word_s" in b:
                leads.setdefault(cls, []).append(b["sync_word_s"] - b["start_s"])
            for c in b.get("callouts") or []:
                if "size_px" in c:
                    sizes.setdefault(c["kind"], []).append(float(c["size_px"]))
            cam = b.get("camera") or {}
            regime = cam.get("regime")
            if regime and regime != "hold":
                if "route_width_px" in cam:
                    widths.setdefault(regime, []).append(float(cam["route_width_px"]))
                if "zoom" in cam:
                    zooms.setdefault(regime, []).append(float(cam["zoom"]))
                elif track:
                    t = float(b.get("sync_word_s", b["start_s"]))
                    nearest = min(track, key=lambda k: abs(k[0] - t))
                    if abs(nearest[0] - t) <= 0.5:
                        zooms.setdefault(regime, []).append(float(nearest[3]))
    return {
        "references": len(references),
        "beats": total_beats,
        "gaps_s": gaps,
        "first_event_s": first_events,
        "lead_s_by_class": leads,
        "callout_size_px": sizes,
        "route_width_px_by_regime": widths,
        "zoom_by_regime": zooms,
        "max_concurrent_callouts": concurrency,
        "device_counts": dict(sorted(devices.items(), key=lambda kv: -kv[1])),
        "function_counts": dict(sorted(functions.items(), key=lambda kv: -kv[1])),
        "unclassified_devices": sorted(unclassified),
    }


def calibrate_idioms(
    idioms: dict[str, Any],
    references: list[dict[str, Any]],
    *,
    camera_tracks: list[list[list[float]] | None] | None = None,
    blend: float = 0.5,
) -> dict[str, Any]:
    """Measure references and propose idiom parameter updates with evidence."""
    for sb in references:
        errors = validate_storyboard_contract(sb)
        if errors:
            raise ValueError(f"reference {sb.get('project_id')!r} failed contract check: {errors}")
    m = measure_references(references, idioms, camera_tracks)
    proposed = copy.deepcopy(idioms)
    by_id = {i["idiom_id"]: i for i in proposed["idioms"]}
    changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    def change(path: str, old: Any, new: Any, evidence: str) -> None:
        if old != new:
            changes.append({"path": path, "old": old, "new": new, "evidence": evidence})

    if "event_cadence" in by_id:
        params = by_id["event_cadence"]["params"]
        for pacing, vals in m["gaps_s"].items():
            if len(vals) < MIN_SAMPLES["gap"]:
                skipped.append({"path": f"event_cadence.max_gap_s.{pacing}", "samples": len(vals)})
                continue
            p90 = _pct(vals, 0.9)
            if isinstance(params["max_gap_s"], dict):
                old = params["max_gap_s"].get(pacing)
                new = _blend(old, p90, blend, 0.1)
                change(
                    f"event_cadence.max_gap_s.{pacing}",
                    old,
                    new,
                    f"p90 gap {p90:.2f}s over {len(vals)} gaps",
                )
                params["max_gap_s"][pacing] = new
        pooled = [g for vals in m["gaps_s"].values() for g in vals]
        if len(pooled) >= MIN_SAMPLES["gap"]:
            p5 = max(0.1, _pct(pooled, 0.05))
            old = params["min_gap_s"]
            new = min(old, _round(p5, 0.05))
            change("event_cadence.min_gap_s", old, new, f"p5 gap {p5:.2f}s")
            params["min_gap_s"] = new

    if "hook_event_early" in by_id and m["first_event_s"]:
        params = by_id["hook_event_early"]["params"]
        worst = max(m["first_event_s"])
        if worst > params["max_first_event_s"]:
            new = _round(worst + 0.1, 0.1)
            change(
                "hook_event_early.max_first_event_s",
                params["max_first_event_s"],
                new,
                f"latest first event {worst:.2f}s",
            )
            params["max_first_event_s"] = new

    for cls, vals in m["lead_s_by_class"].items():
        if len(vals) < MIN_SAMPLES["lead"]:
            skipped.append({"path": f"device_classes.{cls}.lead_s", "samples": len(vals)})
            continue
        if statistics.pstdev(vals) < 0.01:
            # Identical leads mean the onsets were never re-timed against the reference.
            skipped.append(
                {
                    "path": f"device_classes.{cls}.lead_s",
                    "samples": len(vals),
                    "reason": "no variance; onsets look unannotated",
                }
            )
            continue
        lo, hi = _pct(vals, 0.1), _pct(vals, 0.9)
        old = proposed["device_classes"][cls]["lead_s"]
        new = [_blend(old[0], lo, blend, 0.05), _blend(old[1], hi, blend, 0.05)]
        if new[0] > new[1]:
            new = [new[1], new[0]]
        if new[1] - new[0] < MIN_LEAD_WINDOW_S:
            mid = (new[0] + new[1]) / 2
            new = [
                _round(mid - MIN_LEAD_WINDOW_S / 2, 0.05),
                _round(mid + MIN_LEAD_WINDOW_S / 2, 0.05),
            ]
        change(
            f"device_classes.{cls}.lead_s",
            old,
            new,
            f"p10..p90 lead {lo:.2f}..{hi:.2f}s over {len(vals)} beats",
        )
        proposed["device_classes"][cls]["lead_s"] = new

    if "callout_min_size" in by_id:
        mins = by_id["callout_min_size"]["params"]["min_size_px"]
        for kind, vals in m["callout_size_px"].items():
            if len(vals) < MIN_SAMPLES["size"]:
                skipped.append({"path": f"callout_min_size.{kind}", "samples": len(vals)})
                continue
            p10 = _pct(vals, 0.1)
            old = mins.get(kind)
            new = _blend(old, p10 * 0.9, blend, 10)
            change(
                f"callout_min_size.min_size_px.{kind}",
                old,
                new,
                f"p10 size {p10:.0f}px over {len(vals)} callouts",
            )
            mins[kind] = new

    if "max_concurrent_callouts" in by_id and m["max_concurrent_callouts"]:
        params = by_id["max_concurrent_callouts"]["params"]
        seen = max(m["max_concurrent_callouts"])
        if seen > params["max_concurrent"]:
            change(
                "max_concurrent_callouts.max_concurrent",
                params["max_concurrent"],
                seen,
                f"references show {seen} concurrent callouts",
            )
            params["max_concurrent"] = seen

    if "default_device_share" in by_id and m["beats"]:
        params = by_id["default_device_share"]["params"]
        share = m["device_counts"].get(params["default_device"], 0) / m["beats"]
        if share + 0.1 > params["max_share"]:
            new = _round(min(0.9, share + 0.1), 0.05)
            change(
                "default_device_share.max_share",
                params["max_share"],
                new,
                f"references use the fallback device on {share:.0%} of beats",
            )
            params["max_share"] = new

    regimes = proposed.get("camera_regimes") or {}
    for regime, vals in m["zoom_by_regime"].items():
        if regime not in regimes:
            skipped.append({"path": f"camera_regimes.{regime}", "reason": "unknown regime"})
            continue
        if len(vals) < MIN_SAMPLES["zoom"]:
            skipped.append({"path": f"camera_regimes.{regime}.zoom", "samples": len(vals)})
            continue
        med = statistics.median(vals)
        old = regimes[regime]["zoom"]
        new = _blend(old, med, blend, 0.05)
        change(f"camera_regimes.{regime}.zoom", old, new, f"median zoom {med:.2f} over {len(vals)}")
        regimes[regime]["zoom"] = new
    for regime, vals in m["route_width_px_by_regime"].items():
        if regime not in regimes:
            continue
        if len(vals) < MIN_SAMPLES["width"]:
            skipped.append(
                {"path": f"camera_regimes.{regime}.route_width_px", "samples": len(vals)}
            )
            continue
        med = statistics.median(vals)
        old = regimes[regime]["route_width_px"]
        new = _blend(old, med, blend, 0.5)
        change(
            f"camera_regimes.{regime}.route_width_px",
            old,
            new,
            f"median width {med:.1f}px over {len(vals)}",
        )
        regimes[regime]["route_width_px"] = new

    actions = []
    if m["unclassified_devices"]:
        actions.append(
            "Add these devices to a device class (with a lead window) or rename them to an "
            f"existing device: {m['unclassified_devices']}"
        )
    return {
        "measurements": m,
        "changes": changes,
        "skipped": skipped,
        "follow_up": actions,
        "proposed_idioms": proposed,
    }
