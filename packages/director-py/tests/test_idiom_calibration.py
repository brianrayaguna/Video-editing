"""Calibrating directing idioms from annotated reference storyboards."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from vedit.analyzers.idiom_calibration import calibrate_idioms
from vedit.cli import app
from vedit.director.storyboard import idioms_path, load_directing_idioms


def _reference() -> dict:
    beats = []
    for i in range(20):
        t = i * 1.1
        kind = ["pin_and_label", "numeral", "hazard_icons", "route_draw"][i % 4]
        lead = {"pin_and_label": 0.15, "numeral": 0.7, "hazard_icons": 0.3, "route_draw": 0.5}[kind]
        lead += 0.05 * (i % 3)
        beat = {
            "beat_id": f"r{i:02d}",
            "start_s": round(t, 3),
            "end_s": round(t + 1.0, 3),
            "clause": f"clause {i}",
            "function": "proof",
            "story_need": "measured on reference",
            "device": kind,
            "sync_word": "w",
            "sync_word_s": round(t + lead, 3),
            "camera": {
                "regime": ["wide", "regional", "close"][i % 3],
                "zoom": [3.6, 5.2, 7.6][i % 3],
                "route_width_px": [5.0, 12.0, 30.0][i % 3],
            },
        }
        if kind == "hazard_icons":
            beat["callouts"] = [{"kind": "icon_cluster", "size_px": 130.0 + i}]
        beats.append(beat)
    beats[-1]["function"] = "outro"
    return {
        "schema_version": "1.0",
        "project_id": "ref_demo",
        "brand_id": "geoverum",
        "duration_s": 23.0,
        "directing_source": "reference",
        "pacing": "dense",
        "story": {"shape": "journey_chain"},
        "beats": beats,
    }


def test_calibration_measures_and_blends() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    result = calibrate_idioms(idioms, [_reference()], blend=1.0)
    paths = {c["path"]: c for c in result["changes"]}
    assert paths["camera_regimes.close.zoom"]["new"] == 7.6
    assert paths["camera_regimes.close.route_width_px"]["new"] == 30.0
    reading = result["proposed_idioms"]["device_classes"]["reading"]["lead_s"]
    assert reading[1] - reading[0] >= 0.2 - 1e-9
    assert "callout_min_size.min_size_px.icon_cluster" in paths
    # The original idioms are untouched; proposals live in the result.
    assert idioms["camera_regimes"]["close"]["zoom"] == 7.0
    half = calibrate_idioms(idioms, [_reference()], blend=0.5)
    zoom = {c["path"]: c["new"] for c in half["changes"]}["camera_regimes.close.zoom"]
    assert 7.0 < zoom < 7.6


def test_unannotated_leads_are_skipped() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    ref = _reference()
    for b in ref["beats"]:
        b["sync_word_s"] = round(b["start_s"] + 0.2, 3)
    result = calibrate_idioms(idioms, [ref])
    assert not any(c["path"].startswith("device_classes") for c in result["changes"])
    assert any(s.get("reason", "").startswith("no variance") for s in result["skipped"])


def test_unclassified_devices_reported() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    ref = _reference()
    ref["beats"][0]["device"] = "split_screen_compare"
    result = calibrate_idioms(idioms, [ref])
    assert result["follow_up"] and "split_screen_compare" in result["follow_up"][0]


def test_calibrate_cli_applies_to_copy(tmp_path) -> None:
    idioms_copy = tmp_path / "directing_idioms.json"
    idioms_copy.write_text(idioms_path("geoverum").read_text(encoding="utf-8"), encoding="utf-8")
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps(_reference()), encoding="utf-8")
    res = CliRunner().invoke(
        app,
        [
            "brand",
            "calibrate-idioms",
            "--reference-storyboard",
            str(ref),
            "--idioms-file",
            str(idioms_copy),
            "--report",
            str(tmp_path / "report.json"),
            "--blend",
            "1.0",
            "--apply",
        ],
    )
    assert res.exit_code == 0, res.output
    updated = load_directing_idioms(idioms_copy)
    assert updated["camera_regimes"]["close"]["zoom"] == 7.6
