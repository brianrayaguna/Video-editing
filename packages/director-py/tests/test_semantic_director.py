"""Semantic directing, tiered execution modes, and Gate 1 pre-render critique tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from vedit.cli import app
from vedit.director.semantic_director import (
    critique_storyboard_prerender,
    enrich_storyboard_semantically,
)
from vedit.director.storyboard import (
    idioms_path,
    load_directing_idioms,
    validate_storyboard_contract,
)
from vedit.ports.decision import (
    DecisionAnswer,
    DecisionBatchResult,
    DecisionQuestion,
    ImageInput,
    validate_decision_batch,
)


class FakeDecisionPort:
    """In-memory DecisionPort test double recording batch sizes and returning canned answers."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "fake_decision"

    def evaluate(
        self,
        *,
        state: dict[str, Any] | str,
        questions: list[DecisionQuestion],
        images: list[ImageInput] | None = None,
    ) -> DecisionBatchResult:
        validate_decision_batch(questions, images or [])
        self.calls.append({"state": state, "question_count": len(questions)})
        answers: dict[str, DecisionAnswer] = {}
        for q in questions:
            if q.name in self.responses:
                raw = dict(self.responses[q.name])
            elif q.question_type == "choice" and q.criteria:
                first_choice = next(iter(q.criteria))
                raw = {"choice": first_choice}
            elif q.question_type == "score":
                raw = {"score": 88.0}
            else:
                raw = {"text": "visualize the key geographic claim clearly"}
            answers[q.name] = DecisionAnswer(name=q.name, question_type=q.question_type, raw=raw)
        return DecisionBatchResult(
            provider=self.provider_name,
            model="fake-v1",
            input_tokens=len(questions) * 10,
            answers=answers,
        )


def _base_storyboard(n_beats: int = 3) -> dict[str, Any]:
    beats = []
    for idx in range(n_beats):
        start = round(idx * 1.5, 3)
        sync = round(start + 0.2, 3)
        beats.append(
            {
                "beat_id": f"b{idx + 1:03d}",
                "start_s": start,
                "end_s": round(start + 1.4, 3),
                "clause": f"clause {idx + 1} explains the border shift",
                "function": "hook" if idx == 0 else ("outro" if idx == n_beats - 1 else "proof"),
                "story_need": "keep the subject alive while the clause lands",
                "device": "camera_drift",
                "sync_word": "border",
                "sync_word_s": sync,
            }
        )
    return {
        "schema_version": "1.0",
        "project_id": "semantic_demo",
        "brand_id": "geoverum",
        "duration_s": round(max(n_beats * 1.5, 2.0), 3),
        "directing_source": "auto",
        "pacing": "dense",
        "story": {
            "shape": "paradox_mechanism_consequence",
            "hook_mechanism": "scale_paradox",
            "ending_type": "return_to_question",
            "signature_image": "border_line",
        },
        "overrides": {},
        "beats": beats,
    }


def test_draft_tier_or_none_port_is_deterministic_noop() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _base_storyboard(4)
    port = FakeDecisionPort()

    res_draft = enrich_storyboard_semantically(sb, idioms, decision_port=port, tier="draft")
    assert res_draft.batches_sent == 0
    assert port.calls == []
    assert res_draft.storyboard == sb
    assert validate_storyboard_contract(res_draft.storyboard) == []

    res_none = enrich_storyboard_semantically(sb, idioms, decision_port=None, tier="standard")
    assert res_none.batches_sent == 0
    assert res_none.storyboard == sb
    assert validate_storyboard_contract(res_none.storyboard) == []


def test_standard_tier_upgrades_fallback_beats_and_recomputes_sync_lead() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _base_storyboard(3)
    sb["beats"][1]["sync_word_s"] = 2.0
    sb["beats"][1]["start_s"] = 1.8
    sb["beats"][1]["end_s"] = 3.0
    sb["beats"][0]["device"] = "title_card"  # non-fallback hook, should stay untouched in standard

    port = FakeDecisionPort(
        responses={
            "b002__device": {"choice": "measurement_line"},
            "b002__story_need": {"text": "measure the border width directly on the map"},
            "b003__device": {"choice": "fill"},
            "b003__story_need": {"text": "highlight the enclosed territory"},
        }
    )
    res = enrich_storyboard_semantically(sb, idioms, decision_port=port, tier="standard")
    assert res.batches_sent == 1
    assert "b002" in res.updated_beat_ids
    assert "b001" not in res.updated_beat_ids
    b2 = next(b for b in res.storyboard["beats"] if b["beat_id"] == "b002")
    assert b2["device"] == "measurement_line"
    assert b2["story_need"] == "measure the border width directly on the map"
    # measurement_line is in reading class (lead_s: [0.3, 1.0])
    lead = round(b2["sync_word_s"] - b2["start_s"], 3)
    assert 0.3 <= lead <= 1.0
    assert validate_storyboard_contract(res.storyboard) == []


def test_hallucinated_device_banned_device_and_locked_beats_are_protected() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _base_storyboard(4)
    sb["overrides"] = {
        "banned_devices": ["stamp"],
        "locked_beat_ids": ["b001"],
    }
    before = copy.deepcopy(sb)

    port = FakeDecisionPort(
        responses={
            "b001__device": {"choice": "fill"},  # locked beat must stay untouched
            "b002__device": {"choice": "hologram_3d"},  # hallucinated unknown device
            "b003__device": {"choice": "stamp"},  # banned device
            "b004__device": {"choice": "fill"},  # valid upgrade
            "b004__story_need": {"text": "fill the closing region"},
        }
    )
    res = enrich_storyboard_semantically(sb, idioms, decision_port=port, tier="standard")
    by_id = {b["beat_id"]: b for b in res.storyboard["beats"]}
    assert by_id["b001"] == before["beats"][0]
    assert by_id["b002"]["device"] == "camera_drift"
    assert by_id["b003"]["device"] == "camera_drift"
    assert by_id["b004"]["device"] == "fill"

    rejected_reasons = {r["beat_id"]: r["reason"] for r in res.rejected_suggestions}
    assert rejected_reasons.get("b001") == "locked_beat"
    assert rejected_reasons.get("b002") == "unknown_device"
    assert rejected_reasons.get("b003") == "banned_device"
    assert validate_storyboard_contract(res.storyboard) == []


def test_large_storyboard_respects_128_question_batch_limit() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _base_storyboard(90)
    port = FakeDecisionPort()
    res = enrich_storyboard_semantically(sb, idioms, decision_port=port, tier="flagship")
    assert res.batches_sent >= 2
    assert len(port.calls) == res.batches_sent
    assert all(call["question_count"] <= 128 for call in port.calls)
    assert validate_storyboard_contract(res.storyboard) == []


def test_flagship_prerender_gate_selects_best_of_n_hook_respecting_recent_episodes() -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = _base_storyboard(4)
    sb["beats"][0]["device"] = "title_card"
    sb["beats"][0]["story_need"] = "pose the border paradox in frame one"
    sb["beats"][1]["device"] = "pin_and_label"
    sb["beats"][2]["device"] = "numeral"
    sb["beats"][3]["device"] = "fill"
    sb["recent_episodes"] = [
        {
            "project_id": "ep_prev",
            "hook_mechanism": "blueprint_comparison",
            "ending_type": "zoom_out",
            "signature_image": "split_line",
        }
    ]

    candidate_hooks = [
        {
            "hook_mechanism": "blueprint_comparison",  # duplicates recent_episodes
            "signature_image": "split_line",
            "device": "title_card",
            "story_need": "compare the sizes on blueprint",
        },
        {
            "hook_mechanism": "map_paradox_zoom",
            "signature_image": "coastline_trace",
            "device": "dive_zoom",
            "story_need": "dive directly into the anomalous border bend",
        },
        {
            "hook_mechanism": "vague_intro",
            "device": "camera_drift",
            "story_need": "drift",
        },
    ]

    port = FakeDecisionPort(
        responses={
            "prerender_coherence": {"score": 90.0},
            "hook_0__score": {"score": 92.0},
            "hook_1__score": {"score": 88.0},
            "hook_2__score": {"score": 60.0},
        }
    )
    gate = critique_storyboard_prerender(
        sb,
        idioms,
        decision_port=port,
        tier="flagship",
        candidate_hooks=candidate_hooks,
        min_score=75.0,
    )
    assert gate.passed is True
    assert gate.semantic_score == 90.0
    assert gate.selected_hook_index == 1
    assert len(gate.hook_scores) == 3


def test_cli_storyboard_auto_tier_and_gate_prerender(tmp_path: Path) -> None:
    runner = CliRunner()
    transcript = {
        "source_hash": "abcdef12",
        "provider": "test",
        "language": "en",
        "duration_s": 5.0,
        "text": "In 1998 Chile counted 27 crossings before walking north to Alaska.",
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

    res_auto = runner.invoke(
        app,
        [
            "storyboard",
            "auto",
            str(tr_path),
            "-o",
            str(sb_path),
            "--project-id",
            "cli_tier_demo",
            "--brand",
            "geoverum",
            "--tier",
            "draft",
        ],
    )
    assert res_auto.exit_code == 0, res_auto.output
    assert sb_path.is_file()

    res_gate = runner.invoke(
        app,
        [
            "storyboard",
            "gate-prerender",
            str(sb_path),
            "--brand",
            "geoverum",
            "--tier",
            "draft",
            "--min-score",
            "70",
        ],
    )
    assert res_gate.exit_code == 0, res_gate.output
    gate_payload = json.loads(res_gate.output)
    assert gate_payload["passed"] is True
