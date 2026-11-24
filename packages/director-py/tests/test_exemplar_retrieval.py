"""Advisory exemplar, grammar-trigger, and brand-memory retrieval tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from typer.testing import CliRunner

from vedit.cli import app
from vedit.director.exemplar_retrieval import (
    load_editorial_playbook,
    playbook_path,
    retrieve_directing_context,
)
from vedit.director.storyboard import validate_storyboard_contract


def _sample_storyboard() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "distance_demo",
        "brand_id": "geoverum",
        "duration_s": 8.0,
        "directing_source": "auto",
        "pacing": "dense",
        "story": {"shape": "paradox_mechanism_consequence"},
        "overrides": {},
        "beats": [
            {
                "beat_id": "b001",
                "start_s": 0.0,
                "end_s": 2.4,
                "clause": "Why does Chile look so narrow across the map?",
                "function": "hook",
                "story_need": "open curiosity with scale comparison",
                "device": "title_card",
                "sync_word": "Chile",
                "sync_word_s": 0.4,
            },
            {
                "beat_id": "b002",
                "start_s": 2.4,
                "end_s": 5.5,
                "clause": "The distance spans 4300 kilometers compared to Europe.",
                "function": "data_callout",
                "story_need": "show dual unit distance bracket and comparison",
                "device": "numeral",
                "sync_word": "4300",
                "sync_word_s": 3.0,
            },
            {
                "beat_id": "b003",
                "start_s": 5.5,
                "end_s": 8.0,
                "clause": "Santiago sits pinned between ocean and peaks.",
                "function": "outro",
                "story_need": "locate the capital before closing",
                "device": "pin_and_label",
                "sync_word": "Santiago",
                "sync_word_s": 6.0,
            },
        ],
    }


def test_retrieve_ranks_role_and_keyword_matching_exemplars() -> None:
    pb = load_editorial_playbook(playbook_path("geoverum"))
    sb = _sample_storyboard()
    ctx = retrieve_directing_context(sb, pb, top_k_per_beat=2, top_k_triggers=5)

    assert ctx.brand_id == "geoverum"
    assert ctx.story_shape == "paradox_mechanism_consequence"
    assert 1 <= len(ctx.global_triggers) <= 5
    trigger_ids = [h.item_id for h in ctx.global_triggers]
    assert any(
        "distance" in tid or "compare" in tid or "scale" in tid
        for tid in trigger_ids
    )

    b2_hints = ctx.beat_hints["b002"]
    assert 1 <= len(b2_hints) <= 2
    assert any(
        h.kind == "exemplar" and h.payload.get("role") == "data_callout"
        for h in b2_hints
    )


def test_retrieve_surfaces_memory_failure_patterns_and_winning_beats() -> None:
    pb = load_editorial_playbook(playbook_path("geoverum"))
    sb = _sample_storyboard()
    memory = {
        "schema_version": "1.0",
        "brand_id": "geoverum",
        "updated_at": "2026-11-24T00:00:00+00:00",
        "recent_episodes": [],
        "winning_beats": [
            {
                "project_id": "ep1",
                "beat_id": "b002",
                "function": "data_callout",
                "device": "numeral",
                "clause": "4300 kilometers distance comparison",
                "story_need": "distance bracket comparison",
                "rubric_score": 0.94,
            }
        ],
        "failure_patterns": [
            {
                "pattern_id": "fp_pin_overlap",
                "device": "pin_and_label",
                "kind": "layout",
                "description": "pin_and_label overlapped the bottom caption band",
                "occurrences": 3,
                "last_project_id": "ep1",
                "project_ids": ["ep0", "ep1", "ep2"],
            }
        ],
    }

    ctx = retrieve_directing_context(sb, pb, memory=memory, top_k_per_beat=2, top_k_triggers=5)
    assert any(
        w.kind == "failure_pattern" and w.payload.get("device") == "pin_and_label"
        for w in ctx.failure_warnings
    )
    b2_kinds = {h.kind for h in ctx.beat_hints["b002"]}
    b3_kinds = {h.kind for h in ctx.beat_hints["b003"]}
    assert "winning_beat" in b2_kinds
    assert "failure_pattern" in b3_kinds


def test_retrieve_never_mutates_storyboard_or_breaks_contract() -> None:
    pb = load_editorial_playbook(playbook_path("geoverum"))
    sb = _sample_storyboard()
    before = copy.deepcopy(sb)
    _ = retrieve_directing_context(sb, pb)
    assert sb == before
    assert validate_storyboard_contract(sb) == []


def test_cli_storyboard_context_writes_sidecar_json(tmp_path: Path) -> None:
    sb_path = tmp_path / "sb.json"
    ctx_path = tmp_path / "ctx.json"
    sb_path.write_text(json.dumps(_sample_storyboard()), encoding="utf-8")

    res = CliRunner().invoke(
        app,
        ["storyboard", "context", str(sb_path), "--brand", "geoverum", "-o", str(ctx_path)],
    )
    assert res.exit_code == 0, res.output
    assert ctx_path.is_file()
    payload = json.loads(ctx_path.read_text(encoding="utf-8"))
    assert payload["brand_id"] == "geoverum"
    assert "beat_hints" in payload and "global_triggers" in payload
    assert "b001" in payload["beat_hints"]
