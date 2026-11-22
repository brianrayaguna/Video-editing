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

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vedit.director.camera_moves import camera_jitter_report
from vedit.director.storyboard import check_storyboard

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


def build_critique_packet(
    *,
    idioms: dict[str, Any],
    storyboard: dict[str, Any] | None = None,
    camera_track: list[list[float]] | None = None,
    cuts: list[float] | None = None,
    video: Path | None = None,
    sheets_dir: Path | None = None,
    every_s: float = 1.0,
) -> dict[str, Any]:
    """Collect deterministic results, contact sheets and an empty rubric review form."""
    packet: dict[str, Any] = {"deterministic": {}, "sheets": [], "review": {}}
    if storyboard is not None:
        packet["deterministic"]["storyboard"] = check_storyboard(storyboard, idioms).to_dict()
    if camera_track:
        shake = camera_jitter_report(camera_track, cuts=cuts or [])
        shake.pop("flagged", None)
        span_s = max(camera_track[-1][0] - camera_track[0][0], 1e-6)
        shake["pan_flips_per_15s"] = round(shake["reversals"] * 15.0 / span_s, 2)
        shake["zoom_flips_per_30s"] = round(shake["zoom_reversals"] * 30.0 / span_s, 2)
        shake["passed"] = shake["pan_flips_per_15s"] <= 1.0 and shake["zoom_flips_per_30s"] <= 1.0
        packet["deterministic"]["camera"] = shake
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


def gate_review(packet: dict[str, Any], *, threshold: float = 0.8) -> dict[str, Any]:
    """Weighted rubric score plus deterministic results → single pass/fail with reasons."""
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
    return {
        "passed": not reasons,
        "rubric_score": round(weighted, 3),
        "reasons": reasons,
        "fixes": packet["review"].get("fixes", []),
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
