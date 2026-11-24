"""Semi-automated reference editing inversion and exception review queue tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vedit.analyzers.idiom_calibration import calibrate_idioms
from vedit.analyzers.reference_inversion import draft_reference_storyboard
from vedit.cli import app
from vedit.director.storyboard import (
    idioms_path,
    load_directing_idioms,
    validate_storyboard_contract,
)


def _multi_clause_transcript() -> dict:
    clauses = [
        ("In Chile.", 0.2),
        ("At Peru.", 2.2),
        ("In Ecuador.", 4.2),
        ("Near Colombia.", 6.2),
        ("To Panama.", 8.2),
        ("In Mexico.", 10.2),
        ("Across Alaska.", 12.2),
    ]
    words = []
    for text, t0 in clauses:
        parts = text.split()
        for idx, tok in enumerate(parts):
            ws = round(t0 + idx * 0.45, 3)
            words.append({"text": tok, "start_s": ws, "end_s": round(ws + 0.35, 3)})
    return {
        "source_hash": "refhash1234",
        "provider": "test",
        "language": "en",
        "duration_s": 14.0,
        "text": " ".join(c[0] for c in clauses),
        "words": words,
    }


def test_snaps_onsets_from_breakdown_ocr_shots_and_camera_regimes() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    tr = _multi_clause_transcript()

    # Sync words fall at: 0.65 (Chile), 2.65 (Peru), 4.65 (Ecuador), 6.65 (Colombia),
    # 8.65 (Panama), 10.65 (Mexico), 12.65 (Alaska).
    # Provide corroborated shot/OCR/camera events with varying non-zero lead offsets.
    breakdown = {
        "shots": [
            {"shot_index": 0, "start_s": 0.15, "beats_s": [0.15]},
            {"shot_index": 1, "start_s": 2.40, "beats_s": [2.40]},
            {"shot_index": 2, "start_s": 4.20, "beats_s": [4.20]},
            {"shot_index": 3, "start_s": 6.50, "beats_s": [6.50]},
            {"shot_index": 4, "start_s": 8.25, "beats_s": [8.25]},
            {"shot_index": 5, "start_s": 10.55, "beats_s": [10.55]},
            {"shot_index": 6, "start_s": 12.15, "beats_s": [12.15]},
        ],
        "packaging": {
            "ocr_spans": [
                {"start_s": 0.16, "text": "CHILE"},
                {"start_s": 2.41, "text": "PERU"},
                {"start_s": 4.22, "text": "ECUADOR"},
                {"start_s": 6.49, "text": "COLOMBIA"},
                {"start_s": 8.26, "text": "PANAMA"},
                {"start_s": 10.56, "text": "MEXICO"},
                {"start_s": 12.16, "text": "ALASKA"},
            ]
        },
    }
    probe = {
        "shots": [
            {"shot_index": 0, "start_s": 0.15},
            {"shot_index": 1, "start_s": 2.40},
            {"shot_index": 2, "start_s": 4.20},
        ]
    }
    camera_track = [
        [0.0, -70.0, -33.0, 3.3, 0.0],
        [2.40, -75.0, -10.0, 5.1, 0.0],
        [4.20, -78.0, -1.0, 7.1, 0.0],
        [6.50, -74.0, 4.0, 3.3, 0.0],
        [8.25, -79.0, 8.5, 5.0, 0.0],
        [10.55, -99.0, 19.4, 7.0, 0.0],
        [12.15, -150.0, 64.0, 3.2, 0.0],
    ]

    result = draft_reference_storyboard(
        tr,
        idioms,
        project_id="ref_andes",
        breakdown=breakdown,
        probe=probe,
        camera_track=camera_track,
    )
    sb = result.storyboard
    assert sb["directing_source"] == "reference"
    assert validate_storyboard_contract(sb) == []
    assert all(a.confidence == "high" for a in result.beat_audits)
    assert any(b.get("camera", {}).get("regime") == "close" for b in sb["beats"])

    cal = calibrate_idioms(idioms, [sb], camera_tracks=[camera_track], blend=0.5)
    assert not any(
        s.get("reason", "").startswith("no variance") for s in cal["skipped"]
    )
    assert any(c["path"].startswith("device_classes.") for c in cal["changes"])


def test_sparse_telemetry_degrades_to_low_confidence_exception_queue() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    tr = _multi_clause_transcript()
    result = draft_reference_storyboard(
        tr,
        idioms,
        project_id="ref_sparse",
        breakdown=None,
        probe=None,
        camera_track=None,
    )
    assert validate_storyboard_contract(result.storyboard) == []
    assert result.storyboard["directing_source"] == "reference"
    assert all(a.confidence == "low" for a in result.beat_audits)
    assert len(result.exception_review_beats) == len(result.storyboard["beats"])
    assert result.stats["low_confidence_beats"] == len(result.storyboard["beats"])


def test_cli_brand_invert_reference_writes_storyboard_and_queue(tmp_path: Path) -> None:
    tr_path = tmp_path / "tr.json"
    sb_out = tmp_path / "ref_sb.json"
    q_out = tmp_path / "review_queue.json"
    tr_path.write_text(json.dumps(_multi_clause_transcript()), encoding="utf-8")

    res = CliRunner().invoke(
        app,
        [
            "brand",
            "invert-reference",
            str(tr_path),
            "--brand",
            "geoverum",
            "--project-id",
            "ref_demo",
            "-o",
            str(sb_out),
            "--review-queue-out",
            str(q_out),
        ],
    )
    assert res.exit_code == 0, res.output
    assert sb_out.is_file()
    assert q_out.is_file()
    sb = json.loads(sb_out.read_text(encoding="utf-8"))
    queue = json.loads(q_out.read_text(encoding="utf-8"))
    assert sb["directing_source"] == "reference"
    assert validate_storyboard_contract(sb) == []
    assert "exception_review_beats" in queue
    assert "stats" in queue
