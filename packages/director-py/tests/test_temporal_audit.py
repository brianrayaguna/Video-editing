"""Temporal audio-visual sync audit and surgical critique loop tests."""

from __future__ import annotations

import copy
import json

from vedit.contracts import validate_against_contract
from vedit.director.critique import (
    apply_surgical_fixes,
    build_critique_packet,
    gate_review,
)
from vedit.director.storyboard import check_storyboard, idioms_path, load_directing_idioms
from vedit.director.temporal_audit import audit_temporal_sync


def _sample_storyboard() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "temporal_demo",
        "brand_id": "geoverum",
        "duration_s": 8.0,
        "directing_source": "user",
        "pacing": "calm",
        "story": {"shape": "journey_chain"},
        "overrides": {},
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.0,
                "end_s": 1.6,
                "clause": "Opening claim on the strait.",
                "function": "hook",
                "story_need": "anchor opening geography",
                "device": "pin_and_label",
                "sync_word": "strait",
                "sync_word_s": 0.25,
            },
            {
                "beat_id": "b2",
                "start_s": 1.6,
                "end_s": 3.8,
                "clause": "27 crossings occurred here.",
                "function": "data_callout",
                "story_need": "show crossing count",
                "device": "numeral",
                "sync_word": "27",
                "sync_word_s": 2.2,
                "callouts": [
                    {
                        "kind": "numeral",
                        "text": "27",
                        "anchor": "place",
                        "size_px": 90,
                        "xy": [540.0, 900.0],
                    }
                ],
            },
            {
                "beat_id": "b3",
                "start_s": 3.8,
                "end_s": 8.0,
                "clause": "Rebels closed the corridor.",
                "function": "outro",
                "story_need": "show obstacle closing route",
                "device": "hazard_icons",
                "sync_word": "closed",
                "sync_word_s": 4.1,
            },
        ],
    }


def test_temporal_audit_passes_aligned_sfx_and_active_motion() -> None:
    sb = _sample_storyboard()
    audio_events = [0.04, 1.63, 3.77]
    cuts = [1.62, 3.81]
    motion_series = [(t * 0.5, 0.25) for t in range(16)]

    report = audit_temporal_sync(
        sb,
        audio_events_s=audio_events,
        cuts_s=cuts,
        motion_energy_series=motion_series,
    )
    assert report.passed is True
    assert report.sfx_matched_ratio == 1.0
    assert report.median_av_offset_ms is not None
    assert report.median_av_offset_ms <= 50.0
    assert report.dead_motion_windows == []
    assert len(report.split_cut_offsets_s) == 2


def test_temporal_audit_flags_desynced_sfx_and_dead_motion_zone() -> None:
    sb = _sample_storyboard()
    audio_events = [0.35, 1.95, 4.15]  # 350 ms off every onset
    motion_series = [
        (0.0, 0.2),
        (0.5, 0.15),
        (1.0, 0.0),
        (1.5, 0.0),
        (2.0, 0.0),
        (2.5, 0.0),
        (3.0, 0.0),
        (3.5, 0.0),
        (4.0, 0.0),
        (4.5, 0.0),  # 3.5s zero-motion span (1.0..4.5)
        (5.0, 0.25),
    ]

    report = audit_temporal_sync(
        sb,
        audio_events_s=audio_events,
        motion_energy_series=motion_series,
    )
    assert report.passed is False
    assert report.sfx_matched_ratio == 0.0
    assert len(report.dead_motion_windows) == 1
    assert report.dead_motion_windows[0]["duration_s"] >= 3.0
    assert len(report.issues) >= 2


def test_surgical_fixes_respect_frozen_beats_and_rollback_regressions() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _sample_storyboard()
    # Break b2 sync_lead and caption_band_clear so surgical fixes can repair b2.
    sb["beats"][1]["start_s"] = 2.15  # lead 0.05s; numeral needs 0.3..1.0s
    sb["beats"][1]["callouts"][0]["xy"] = [540.0, 1340.0]  # inside 0.66..0.76 * 1920 = 1267..1459

    before_b1 = copy.deepcopy(sb["beats"][0])

    packet = build_critique_packet(idioms=idioms, storyboard=sb)
    packet["frozen_beat_ids"] = ["b1"]
    packet["review"]["scores"] = {k: 0.9 for k in packet["review"]["scores"]}
    packet["review"]["fixes"] = [
        {"beat_id": "b1", "kind": "device", "device": "stamp"},  # frozen -> skip
        {"beat_id": "b2", "kind": "timing"},  # nudge start_s into reading lead_s window
        {"beat_id": "b2", "kind": "layout"},  # move xy[1] above caption band
        {"beat_id": "b3", "kind": "timing", "start_s": 0.1},  # causes regression -> rollback
    ]

    res = apply_surgical_fixes(sb, packet, idioms)
    assert "b1" in res["skipped_frozen"]
    assert res["storyboard"]["beats"][0] == before_b1
    assert any(f["beat_id"] == "b2" and f["kind"] == "timing" for f in res["applied"])
    assert any(f["beat_id"] == "b2" and f["kind"] == "layout" for f in res["applied"])
    assert any(r["fix"]["beat_id"] == "b3" for r in res["rolled_back"])

    repaired_b2 = res["storyboard"]["beats"][1]
    lead = repaired_b2["sync_word_s"] - repaired_b2["start_s"]
    assert 0.3 <= lead <= 1.0
    assert repaired_b2["callouts"][0]["xy"][1] < 1267.0
    assert check_storyboard(res["storyboard"], idioms).score >= check_storyboard(sb, idioms).score


def test_gate_review_computes_next_frozen_beats_and_enforces_iteration_cap() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _sample_storyboard()
    sb["beats"][1]["callouts"][0]["xy"] = [540.0, 1340.0]  # deterministic issue on b2

    packet = build_critique_packet(idioms=idioms, storyboard=sb, iteration=4, max_iterations=3)
    packet["review"]["scores"] = {k: 0.9 for k in packet["review"]["scores"]}
    packet["review"]["fixes"] = [{"beat_id": "b3", "kind": "camera", "regime": "close"}]

    gate = gate_review(packet)
    assert gate["passed"] is False
    assert gate["iteration_budget_exhausted"] is True
    assert any("iteration budget" in r for r in gate["reasons"])
    assert "b1" in gate["next_frozen_beat_ids"]
    assert "b2" not in gate["next_frozen_beat_ids"]
    assert "b3" not in gate["next_frozen_beat_ids"]


def test_critique_packet_validates_against_contract_schema() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _sample_storyboard()
    packet = build_critique_packet(
        idioms=idioms,
        storyboard=sb,
        camera_track=[[0, 0, 0, 3, 0], [1, 1, 0, 3, 0], [2, 2, 0, 3, 0]],
        audio_events_s=[0.02, 1.61, 3.82],
        cuts=[1.6, 3.8],
        motion_energy_series=[(t * 0.5, 0.3) for t in range(16)],
        iteration=1,
        max_iterations=3,
    )
    errors = validate_against_contract(packet, "critique_packet.schema.json")
    assert errors == [], json.dumps(errors, indent=2)
