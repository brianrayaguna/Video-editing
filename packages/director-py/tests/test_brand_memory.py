"""External per-brand episodic memory and repository isolation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vedit.cli import app
from vedit.contracts import find_repo_root, validate_against_contract
from vedit.director.brand_memory import (
    empty_brand_memory,
    export_recent_episodes,
    load_brand_memory,
    record_episode_outcome,
    resolve_brand_memory_path,
    save_brand_memory,
)
from vedit.director.storyboard import validate_storyboard_contract


def _sample_storyboard(project_id: str = "ep1") -> dict:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "brand_id": "geoverum",
        "duration_s": 6.0,
        "directing_source": "mixed",
        "pacing": "dense",
        "story": {
            "shape": "paradox_mechanism_consequence",
            "hook_mechanism": "scale_paradox",
            "ending_type": "return_to_question",
            "signature_image": "border_split",
        },
        "overrides": {},
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.0,
                "end_s": 2.0,
                "clause": "Opening paradox on the border.",
                "function": "hook",
                "story_need": "show scale paradox on frame one",
                "device": "title_card",
                "sync_word": "border",
                "sync_word_s": 0.3,
            },
            {
                "beat_id": "b2",
                "start_s": 2.0,
                "end_s": 4.0,
                "clause": "Wait for the crossing.",
                "function": "proof",
                "story_need": "keep frame alive",
                "device": "camera_drift",
                "sync_word": "crossing",
                "sync_word_s": 2.2,
            },
            {
                "beat_id": "b3",
                "start_s": 4.0,
                "end_s": 6.0,
                "clause": "4200 km from north to south.",
                "function": "outro",
                "story_need": "display full span",
                "device": "measurement_line",
                "treatment": "amber_dashed",
                "sync_word": "4200",
                "sync_word_s": 4.5,
            },
        ],
    }


def test_resolve_and_save_reject_paths_inside_engine_repo() -> None:
    repo_root = find_repo_root()
    with pytest.raises(ValueError, match="external workspace isolation"):
        resolve_brand_memory_path("geoverum", projects_root=repo_root, repo_root=repo_root)

    mem = empty_brand_memory("geoverum")
    inside_path = repo_root / "profiles" / "brands" / "geoverum" / "brand_memory.json"
    with pytest.raises(ValueError, match="external workspace isolation"):
        save_brand_memory(inside_path, mem, repo_root=repo_root)


def test_record_episode_outcome_is_idempotent_and_deduplicates_failures() -> None:
    mem = empty_brand_memory("geoverum")
    sb1 = _sample_storyboard("ep1")
    packet1 = {
        "deterministic": {
            "storyboard": {
                "passed": True,
                "issues": [],
            }
        },
        "review": {
            "fixes": [
                {
                    "beat_id": "b1",
                    "kind": "layout",
                    "message": "callout entered bottom caption band",
                }
            ]
        },
    }
    gate1 = {"passed": False, "rubric_score": 0.72}

    mem = record_episode_outcome(mem, sb1, critique_packet=packet1, gate_result=gate1)
    assert len(mem["recent_episodes"]) == 1
    assert len(mem["failure_patterns"]) == 1
    assert mem["failure_patterns"][0]["occurrences"] == 1

    # Re-recording the same project_id must be idempotent.
    mem = record_episode_outcome(mem, sb1, critique_packet=packet1, gate_result=gate1)
    assert len(mem["recent_episodes"]) == 1
    assert mem["failure_patterns"][0]["occurrences"] == 1

    # Recording a second episode with the same failure increments occurrences to 2.
    sb2 = _sample_storyboard("ep2")
    mem = record_episode_outcome(mem, sb2, critique_packet=packet1, gate_result=gate1)
    assert len(mem["recent_episodes"]) == 2
    assert mem["failure_patterns"][0]["occurrences"] == 2
    assert mem["failure_patterns"][0]["project_ids"] == ["ep1", "ep2"]


def test_winning_beats_capture_only_high_scoring_non_fallback_beats(tmp_path: Path) -> None:
    mem = empty_brand_memory("geoverum")
    sb = _sample_storyboard("ep_win")
    packet = {
        "deterministic": {
            "storyboard": {
                "passed": True,
                "issues": [],
            }
        },
        "review": {
            "fixes": [
                {
                    "beat_id": "b1",
                    "kind": "timing",
                    "message": "shift onset 150ms earlier",
                }
            ]
        },
    }
    # Below 0.85 or failed -> zero winning beats captured.
    low_gate = {"passed": True, "rubric_score": 0.82}
    mem_low = record_episode_outcome(mem, sb, critique_packet=packet, gate_result=low_gate)
    assert mem_low["winning_beats"] == []

    # >= 0.85 and passed -> capture only concrete beats without fixes/issues
    # (b3 only; b1 had fix, b2 is fallback).
    high_gate = {"passed": True, "rubric_score": 0.91}
    mem_high = record_episode_outcome(mem, sb, critique_packet=packet, gate_result=high_gate)
    assert [wb["beat_id"] for wb in mem_high["winning_beats"]] == ["b3"]
    assert validate_against_contract(mem_high, "brand_memory.schema.json") == []

    out_path = save_brand_memory(tmp_path / "geoverum" / "brand_memory.json", mem_high)
    loaded = load_brand_memory(out_path)
    assert loaded["brand_id"] == "geoverum"
    assert len(loaded["winning_beats"]) == 1


def test_storyboard_auto_with_memory_file_populates_recent_episodes(tmp_path: Path) -> None:
    mem = empty_brand_memory("geoverum")
    mem = record_episode_outcome(
        mem,
        _sample_storyboard("ep_prior"),
        gate_result={"passed": True, "rubric_score": 0.9},
    )
    assert len(export_recent_episodes(mem)) == 1
    mem_path = tmp_path / "brand_memory.json"
    save_brand_memory(mem_path, mem)

    transcript = {
        "source_hash": "abcdef12",
        "provider": "test",
        "language": "en",
        "duration_s": 4.8,
        "text": "In 1998 Chile counted 27 crossings, then walked north to Alaska.",
        "words": [
            {"text": "In", "start_s": 0.0, "end_s": 0.25},
            {"text": "1998", "start_s": 0.3, "end_s": 0.7},
            {"text": "Chile", "start_s": 0.75, "end_s": 1.1},
            {"text": "counted", "start_s": 1.15, "end_s": 1.5},
            {"text": "27", "start_s": 1.55, "end_s": 1.9},
            {"text": "crossings,", "start_s": 1.95, "end_s": 2.4},
            {"text": "then", "start_s": 2.75, "end_s": 3.0},
            {"text": "walked", "start_s": 3.05, "end_s": 3.4},
            {"text": "north", "start_s": 3.45, "end_s": 3.8},
            {"text": "to", "start_s": 3.85, "end_s": 4.05},
            {"text": "Alaska.", "start_s": 4.1, "end_s": 4.6},
        ],
    }
    tr_path = tmp_path / "tr.json"
    sb_path = tmp_path / "sb.json"
    tr_path.write_text(json.dumps(transcript), encoding="utf-8")

    res = CliRunner().invoke(
        app,
        [
            "storyboard",
            "auto",
            str(tr_path),
            "--brand",
            "geoverum",
            "--project-id",
            "ep2",
            "--memory-file",
            str(mem_path),
            "-o",
            str(sb_path),
        ],
    )
    assert res.exit_code == 0, res.output
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    assert sb["recent_episodes"] == [
        {
            "project_id": "ep_prior",
            "hook_mechanism": "scale_paradox",
            "ending_type": "return_to_question",
            "signature_image": "border_split",
        }
    ]
    assert validate_storyboard_contract(sb) == []

    # Verify `vedit brand memory record` and `vedit brand memory show` CLI roundtrip.
    ext_root = tmp_path / "projects_root"
    rec_res = CliRunner().invoke(
        app,
        [
            "brand",
            "memory",
            "record",
            "--brand-id",
            "geoverum",
            "--storyboard",
            str(sb_path),
            "--projects-root",
            str(ext_root),
        ],
    )
    assert rec_res.exit_code == 0, rec_res.output
    show_res = CliRunner().invoke(
        app,
        [
            "brand",
            "memory",
            "show",
            "--brand-id",
            "geoverum",
            "--projects-root",
            str(ext_root),
        ],
    )
    assert show_res.exit_code == 0, show_res.output
    shown = json.loads(show_res.output)
    assert shown["memory"]["recent_episodes"][0]["project_id"] == "ep2"
