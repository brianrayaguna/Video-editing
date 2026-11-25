"""Critique loop: deterministic checks plus a rubric-driven visual review of rendered output.

The loop runs after a low-resolution preview (or the final master) exists:

1. `build_critique_packet` runs the storyboard idiom check and the camera shake report, renders
   grid-anchored contact sheets at each beat's sync word, and emits the brand rubric as an empty
   review form. Grid anchors (columns A-F left to right, rows 1-10 top to bottom) let a vision
   reviewer name positions precisely ("callout at C7 overlaps the caption band").
2. A vision-capable reviewer fills `review.scores` (0-1 per criterion) and `review.fixes`.
3. `gate_review` combines the deterministic results with the filled review into one pass/fail
   decision. Failing items go back to the storyboard or scene, and the preview is re-rendered.
"""

from __future__ import annotations

import copy
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vedit.analyzers.editorial_forensics import (
    analyze_cross_cut_continuity,
    compute_multimodal_tension_curve,
)
from vedit.director.camera_moves import camera_jitter_report
from vedit.director.storyboard import (
    _device_lead_window,
    check_storyboard,
    validate_storyboard_contract,
)
from vedit.director.temporal_audit import audit_temporal_sync

GRID_COLS = "ABCDEF"
GRID_ROWS = 10
CELL_W, CELL_H = 270, 480


def _render_cell(video: Path, t: float, label: str, out: Path) -> bool:
    grid = (
        f"scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=decrease,"
        f"pad={CELL_W}:{CELL_H}:(ow-iw)/2:(oh-ih)/2:black,"
        f"drawgrid=w=iw/{len(GRID_COLS)}:h=ih/{GRID_ROWS}:t=1:c=yellow@0.45"
    )
    text = (
        label.replace("\\", "")
        .replace("'", "")
        .replace(":", "-")
        .replace(",", " ")
        .replace(";", " ")
        .replace("[", "(")
        .replace("]", ")")
        .replace("%", "pct")
    )
    with_text = (
        grid
        + f",drawtext=text='{text}':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6"
    )
    for vf in (with_text, grid):
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                vf,
                "-q:v",
                "3",
                str(out),
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0 and out.is_file():
            return True
    return False


def grid_contact_sheets(
    video: Path,
    out_dir: Path,
    samples: list[tuple[float, str]],
    *,
    per_row: int = 6,
    rows_per_sheet: int = 2,
) -> list[dict[str, Any]]:
    """Render labelled, grid-anchored frames at `samples` and tile them into sheets."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to render contact sheets.")
    out_dir.mkdir(parents=True, exist_ok=True)
    per_sheet = per_row * rows_per_sheet
    sheets: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="vedit_critique_") as tmp_dir:
        tmp = Path(tmp_dir)
        for s0 in range(0, len(samples), per_sheet):
            chunk = samples[s0 : s0 + per_sheet]
            cells = []
            for k, (t, label) in enumerate(chunk):
                cell = tmp / f"cell_{s0 + k:04d}.jpg"
                if _render_cell(video, t, label, cell):
                    cells.append(cell)
            if not cells:
                continue
            # Pad the last sheet so the tile filter always receives a full grid.
            while len(cells) < per_sheet:
                pad = tmp / f"pad_{s0}_{len(cells):02d}.jpg"
                shutil.copy(cells[-1], pad)
                cells.append(pad)
            listing = tmp / f"list_{s0}.txt"
            listing.write_text("".join(f"file '{c}'\n" for c in cells), encoding="utf-8")
            sheet = out_dir / f"sheet_{s0 // per_sheet + 1:02d}.jpg"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(listing),
                    "-vf",
                    f"tile={per_row}x{rows_per_sheet}",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(sheet),
                ],
                check=True,
            )
            sheets.append(
                {
                    "path": str(sheet),
                    "frames": [{"t": round(t, 3), "label": label} for t, label in chunk],
                }
            )
    return sheets


def beat_samples(storyboard: dict[str, Any], max_samples: int = 48) -> list[tuple[float, str]]:
    """One frame per beat at its sync word (or onset + 0.3 s), thinned evenly to `max_samples`."""
    beats = sorted(storyboard["beats"], key=lambda b: b["start_s"])
    picks = [
        (
            float(b.get("sync_word_s", b["start_s"] + 0.3)) + 0.1,
            f"{b['beat_id']} {b.get('sync_word', '')}",
        )
        for b in beats
    ]
    if len(picks) <= max_samples:
        return picks
    step = len(picks) / max_samples
    return [picks[int(i * step)] for i in range(max_samples)]


def _beat_issue_ids(packet: dict[str, Any]) -> set[str]:
    det_sb = (packet.get("deterministic") or {}).get("storyboard") or {}
    issue_beats = {
        str(issue["beat_id"])
        for issue in (det_sb.get("issues") or [])
        if issue.get("beat_id")
    }
    fix_beats = {
        str(fix["beat_id"])
        for fix in ((packet.get("review") or {}).get("fixes") or [])
        if isinstance(fix, dict) and fix.get("beat_id")
    }
    return issue_beats | fix_beats


def _compute_next_frozen_beats(packet: dict[str, Any]) -> list[str]:
    existing = [str(bid) for bid in (packet.get("frozen_beat_ids") or [])]
    det_sb = (packet.get("deterministic") or {}).get("storyboard") or {}
    all_beats = [str(bid) for bid in (det_sb.get("beat_ids") or [])]
    dirty = _beat_issue_ids(packet)
    ordered = list(existing)
    seen = set(ordered)
    for bid in all_beats:
        if bid not in dirty and bid not in seen:
            ordered.append(bid)
            seen.add(bid)
    return ordered


def build_critique_packet(
    *,
    idioms: dict[str, Any],
    storyboard: dict[str, Any] | None = None,
    camera_track: list[list[float]] | None = None,
    cuts: list[float] | None = None,
    video: Path | None = None,
    sheets_dir: Path | None = None,
    every_s: float = 1.0,
    audio_events_s: list[float] | None = None,
    motion_energy_series: list[tuple[float, float]] | None = None,
    previous_packet: dict[str, Any] | None = None,
    iteration: int = 1,
    max_iterations: int = 3,
) -> dict[str, Any]:
    """Collect deterministic results, contact sheets and an empty rubric review form."""
    frozen_beat_ids: list[str] = []
    if previous_packet is not None:
        frozen_beat_ids = _compute_next_frozen_beats(previous_packet)

    packet: dict[str, Any] = {
        "schema_version": "1.0",
        "iteration": int(iteration),
        "max_iterations": int(max_iterations),
        "frozen_beat_ids": frozen_beat_ids,
        "deterministic": {},
        "sheets": [],
        "review": {},
    }
    if storyboard is not None:
        sb_dict = check_storyboard(storyboard, idioms).to_dict()
        sb_dict["beat_ids"] = [str(b["beat_id"]) for b in storyboard.get("beats") or []]
        packet["deterministic"]["storyboard"] = sb_dict
        if (
            audio_events_s is not None
            or cuts is not None
            or motion_energy_series is not None
        ):
            packet["deterministic"]["temporal"] = audit_temporal_sync(
                storyboard,
                audio_events_s=audio_events_s,
                cuts_s=cuts,
                motion_energy_series=motion_energy_series,
            ).to_dict()
    if camera_track:
        shake = camera_jitter_report(camera_track, cuts=cuts or [])
        shake.pop("flagged", None)
        span_s = max(camera_track[-1][0] - camera_track[0][0], 1e-6)
        shake["pan_flips_per_15s"] = round(shake["reversals"] * 15.0 / span_s, 2)
        shake["zoom_flips_per_30s"] = round(shake["zoom_reversals"] * 30.0 / span_s, 2)
        shake["passed"] = shake["pan_flips_per_15s"] <= 1.0 and shake["zoom_flips_per_30s"] <= 1.0
        packet["deterministic"]["camera"] = shake
    if video is not None and cuts:
        cont = analyze_cross_cut_continuity(video, [float(c) for c in cuts]).to_dict()
        packet["deterministic"]["editorial_continuity"] = cont
    if storyboard is not None or (video is not None and cuts):
        est_dur = (
            float(storyboard.get("duration_s") or 0.0)
            if storyboard is not None
            else (_duration(video) if video is not None else 0.0)
        )
        if est_dur > 0.0:
            packet["deterministic"]["tension_curve"] = compute_multimodal_tension_curve(
                est_dur,
                storyboard=storyboard,
                cuts_s=[float(c) for c in (cuts or [])],
            ).to_dict()
    if video is not None and sheets_dir is not None:
        if storyboard is not None:
            samples = beat_samples(storyboard)
        else:
            dur = _duration(video)
            samples = [(t, f"t={t:.1f}s") for t in _frange(0.1, dur, every_s)]
        packet["sheets"] = grid_contact_sheets(video, sheets_dir, samples)
        packet["grid_legend"] = (
            f"Each frame carries a {len(GRID_COLS)}x{GRID_ROWS} grid: columns "
            f"{GRID_COLS[0]}-{GRID_COLS[-1]} left to right, rows 1-{GRID_ROWS} top to bottom. "
            "Name positions by cell (for example C7)."
        )
    packet["review"] = {
        "instructions": (
            "Score each criterion from 0 (fails) to 1 (fully meets) using the sheets, citing frame "
            "labels and grid cells. List each concrete fix with the beat_id it belongs to."
        ),
        "scores": {c["criterion_id"]: None for c in idioms["critique_rubric"]},
        "fixes": [],
        "rubric": idioms["critique_rubric"],
    }
    return packet


def _caption_band_params(idioms: dict[str, Any]) -> tuple[float, float, float]:
    for idiom in idioms.get("idioms") or []:
        if idiom.get("idiom_id") == "caption_band_clear":
            p = idiom.get("params") or {}
            band = p.get("band_y_pct") or [0.66, 0.76]
            frame = p.get("frame_px") or [1080, 1920]
            return float(band[0]), float(band[1]), float(frame[1])
    return 0.66, 0.76, 1920.0


def _known_devices(idioms: dict[str, Any]) -> set[str]:
    return {
        str(dev)
        for cls in (idioms.get("device_classes") or {}).values()
        for dev in (cls.get("devices") or [])
    }


def _apply_one_fix(
    beat: dict[str, Any],
    fix: dict[str, Any],
    idioms: dict[str, Any],
    *,
    banned_devices: set[str],
    known_devices: set[str],
) -> bool:
    kind = str(fix.get("kind") or "")
    params = fix.get("params") if isinstance(fix.get("params"), dict) else {}

    if kind == "timing":
        explicit_start = fix.get("start_s", params.get("start_s"))
        explicit_end = fix.get("end_s", params.get("end_s"))
        if explicit_start is not None:
            beat["start_s"] = round(max(0.0, float(explicit_start)), 3)
        elif "sync_word_s" in beat:
            lead_info = _device_lead_window(idioms, beat["device"])
            if lead_info is not None:
                lo, hi = float(lead_info[1][0]), float(lead_info[1][1])
                mid = (lo + hi) / 2.0
                beat["start_s"] = round(max(0.0, float(beat["sync_word_s"]) - mid), 3)
        if explicit_end is not None:
            beat["end_s"] = round(max(float(explicit_end), float(beat["start_s"]) + 0.25), 3)
        else:
            beat["end_s"] = round(max(float(beat["end_s"]), float(beat["start_s"]) + 0.25), 3)
        return True

    if kind == "layout":
        y0_pct, y1_pct, frame_h = _caption_band_params(idioms)
        band_top = y0_pct * frame_h
        band_bottom = y1_pct * frame_h
        explicit_xy = fix.get("xy", params.get("xy"))
        explicit_size = fix.get("size_px", params.get("size_px"))
        callouts = beat.get("callouts") or []
        if not callouts:
            return False
        for callout in callouts:
            if explicit_size is not None:
                callout["size_px"] = float(explicit_size)
            if explicit_xy is not None:
                callout["xy"] = [float(explicit_xy[0]), float(explicit_xy[1])]
            elif "xy" in callout:
                half = float(callout.get("size_px", 0.0)) / 2.0
                cy = float(callout["xy"][1])
                if cy + half > band_top and cy - half < band_bottom:
                    callout["xy"] = [
                        float(callout["xy"][0]),
                        round(max(half + 20.0, band_top - half - 20.0), 1),
                    ]
        return True

    if kind == "device":
        new_dev = str(fix.get("device") or params.get("device") or "").strip()
        if not new_dev or new_dev in banned_devices or new_dev not in known_devices:
            return False
        beat["device"] = new_dev
        new_treat = fix.get("treatment", params.get("treatment"))
        if isinstance(new_treat, str) and new_treat.strip():
            beat["treatment"] = new_treat.strip()
        new_need = fix.get("story_need", params.get("story_need"))
        if isinstance(new_need, str) and len(new_need.strip()) >= 3:
            beat["story_need"] = new_need.strip()
        if "sync_word_s" in beat:
            lead_info = _device_lead_window(idioms, new_dev)
            if lead_info is not None:
                lo, hi = float(lead_info[1][0]), float(lead_info[1][1])
                beat["start_s"] = round(max(0.0, float(beat["sync_word_s"]) - (lo + hi) / 2.0), 3)
                beat["end_s"] = round(max(float(beat["end_s"]), float(beat["start_s"]) + 0.25), 3)
        return True

    if kind == "camera":
        regime = fix.get("regime", params.get("regime"))
        move_start_s = fix.get("move_start_s", params.get("move_start_s"))
        cam = dict(beat.get("camera") or {})
        if regime is not None:
            cam["regime"] = str(regime)
        if move_start_s is not None:
            cam["move_start_s"] = round(max(0.0, float(move_start_s)), 3)
        if cam:
            beat["camera"] = cam
            return True
        return False

    return False


def apply_surgical_fixes(
    storyboard: dict[str, Any],
    packet: dict[str, Any],
    idioms: dict[str, Any],
) -> dict[str, Any]:
    """Apply typed review fixes to unfrozen beats, rolling back any regression."""
    working = copy.deepcopy(storyboard)
    overrides = working.get("overrides") or {}
    frozen = {str(b) for b in (packet.get("frozen_beat_ids") or [])} | {
        str(b) for b in (overrides.get("locked_beat_ids") or [])
    }
    banned_devices = {str(d) for d in (overrides.get("banned_devices") or [])}
    known_devices = _known_devices(idioms)

    applied: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    skipped_frozen: list[str] = []
    rolled_back: list[dict[str, Any]] = []

    raw_fixes = ((packet.get("review") or {}).get("fixes")) or []
    for raw_fix in raw_fixes:
        if not isinstance(raw_fix, dict):
            deferred.append({"fix": raw_fix, "reason": "untyped_string_fix"})
            continue
        beat_id = str(raw_fix.get("beat_id") or "")
        kind = str(raw_fix.get("kind") or "")
        if not beat_id or not kind:
            deferred.append({"fix": raw_fix, "reason": "missing_beat_id_or_kind"})
            continue
        if beat_id in frozen:
            if beat_id not in skipped_frozen:
                skipped_frozen.append(beat_id)
            continue
        if kind in ("audio_sync", "script"):
            deferred.append({"fix": raw_fix, "reason": f"requires_{kind}_intervention"})
            continue

        before_report = check_storyboard(working, idioms).to_dict()
        candidate = copy.deepcopy(working)
        target_beat = next(
            (b for b in candidate.get("beats") or [] if b.get("beat_id") == beat_id),
            None,
        )
        if target_beat is None:
            deferred.append({"fix": raw_fix, "reason": "unknown_beat_id"})
            continue

        mutated = _apply_one_fix(
            target_beat,
            raw_fix,
            idioms,
            banned_devices=banned_devices,
            known_devices=known_devices,
        )
        if not mutated:
            deferred.append({"fix": raw_fix, "reason": "no_applicable_mutation"})
            continue

        contract_errs = validate_storyboard_contract(candidate)
        if contract_errs:
            rolled_back.append(
                {"fix": raw_fix, "reason": f"contract_violation: {contract_errs[0]}"}
            )
            continue

        after_report = check_storyboard(candidate, idioms).to_dict()
        if (
            after_report["error_count"] > before_report["error_count"]
            or after_report["score"] < before_report["score"]
        ):
            rolled_back.append(
                {
                    "fix": raw_fix,
                    "reason": (
                        f"regression (errors {before_report['error_count']}->"
                        f"{after_report['error_count']}, score {before_report['score']}->"
                        f"{after_report['score']})"
                    ),
                }
            )
            continue

        working = candidate
        applied.append(copy.deepcopy(raw_fix))

    return {
        "storyboard": working,
        "applied": applied,
        "deferred": deferred,
        "skipped_frozen": skipped_frozen,
        "rolled_back": rolled_back,
    }


def gate_review(packet: dict[str, Any], *, threshold: float = 0.8) -> dict[str, Any]:
    """Weighted rubric score plus deterministic results -> single pass/fail with reasons."""
    rubric = {c["criterion_id"]: c for c in packet["review"]["rubric"]}
    scores = packet["review"]["scores"]
    missing = [cid for cid in rubric if scores.get(cid) is None]
    unknown = [cid for cid in scores if cid not in rubric]
    reasons: list[str] = []
    if missing:
        reasons.append(f"unscored criteria: {missing}")
    if unknown:
        reasons.append(f"unknown rubric criteria: {unknown}")

    valid_scores: dict[str, float] = {}
    out_of_range: list[str] = []
    for cid in rubric:
        raw_v = scores.get(cid)
        if raw_v is None:
            continue
        try:
            fv = float(raw_v)
        except (TypeError, ValueError):
            out_of_range.append(cid)
            continue
        if not math.isfinite(fv) or fv < 0.0 or fv > 1.0:
            out_of_range.append(cid)
            continue
        valid_scores[cid] = fv
    if out_of_range:
        reasons.append(f"scores outside [0, 1]: {out_of_range}")

    total_w = sum(rubric[c]["weight"] for c in rubric) or 1.0
    weighted = sum(rubric[c]["weight"] * v for c, v in valid_scores.items()) / total_w
    if weighted < threshold:
        reasons.append(f"rubric score {weighted:.2f} below {threshold}")
    low = [c for c, v in valid_scores.items() if v < 0.5]
    if low:
        reasons.append(f"criteria below 0.5: {low}")
    det = packet.get("deterministic", {})
    if det.get("storyboard") and not det["storyboard"]["passed"]:
        reasons.append("storyboard has idiom errors")
    if det.get("camera") and not det["camera"]["passed"]:
        reasons.append("camera exceeds the shake budget")
    if det.get("temporal") and not det["temporal"]["passed"]:
        reasons.append("temporal audio-visual sync failed")

    iteration = int(packet.get("iteration", 1))
    max_iterations = int(packet.get("max_iterations", 3))
    iteration_budget_exhausted = iteration > max_iterations
    if iteration_budget_exhausted and reasons:
        reasons.append(f"iteration budget exhausted ({iteration} > {max_iterations})")

    return {
        "passed": not reasons,
        "rubric_score": round(weighted, 3),
        "reasons": reasons,
        "fixes": packet["review"].get("fixes", []),
        "next_frozen_beat_ids": _compute_next_frozen_beats(packet),
        "iteration_budget_exhausted": iteration_budget_exhausted,
    }


def _duration(video: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _frange(start: float, stop: float, step: float) -> list[float]:
    out, t = [], start
    while t < stop:
        out.append(round(t, 3))
        t += step
    return out
