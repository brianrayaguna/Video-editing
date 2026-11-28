"""Tests for upgraded Liquid AI d1.2-ultra DecisionPort, auto mode, Gate 2 critique, and spans."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from vedit.ports.decision import DecisionAnswer, DecisionBatchResult, DecisionQuestion, ImageInput


def test_liquid_d1_score_sends_ordered_criteria_list_and_parses_confidence_and_cost() -> None:
    from vedit.providers.decision.liquid_d1 import LiquidDecisionProvider

    seen_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        seen_payload = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "d1.2-ultra",
                "usage": {"input_tokens": 410, "output_tokens": 0, "cost": 0.0000172},
                "answers": {
                    "hook_quality": {
                        "type": "score",
                        "score": 3.4,
                        "legend": {
                            "0": "Poor",
                            "1": "Weak",
                            "2": "Acceptable",
                            "3": "Strong",
                            "4": "Broadcast-grade",
                        },
                        "confidence": 0.88,
                    },
                    "has_clutter": {
                        "type": "noul",
                        "noul": 0.12,
                        "confidence": 0.91,
                    },
                },
            },
        )

    engine = LiquidDecisionProvider(
        {"api_key": "liq-key", "model": "d1.2-ultra"},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    levels = ["Poor", "Weak", "Acceptable", "Strong", "Broadcast-grade"]
    res = engine.evaluate(
        state={"beat": "Opening hook"},
        questions=[
            DecisionQuestion(
                name="hook_quality",
                question_type="score",
                instructions="Rate visual specificity of the opening hook.",
                criteria=levels,
            ),
            DecisionQuestion(
                name="has_clutter",
                question_type="noul",
                instructions="Is the frame visually cluttered?",
            ),
        ],
    )

    assert seen_payload["model"] == "d1.2-ultra"
    assert seen_payload["questions"]["hook_quality"]["criteria"] == levels
    assert "range" not in seen_payload["questions"]["hook_quality"]
    assert res.cost_usd == pytest.approx(0.0000172)
    assert res.answers["hook_quality"].confidence == pytest.approx(0.88)
    assert res.answers["hook_quality"].score_value == pytest.approx(3.4)
    assert res.answers["has_clutter"].noul_prob == pytest.approx(0.12)


def test_liquid_d1_auto_downscales_oversized_images_within_patch_budget(tmp_path: Path) -> None:
    from vedit.providers.decision.liquid_d1 import LiquidDecisionProvider, _image_dimensions

    big_jpg = tmp_path / "huge_4k.jpg"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#0A2233:s=2400x1600:d=0.1",
            "-frames:v",
            "1",
            str(big_jpg),
        ],
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert _image_dimensions(big_jpg.read_bytes()) == (2400, 1600)

    seen_dims: list[tuple[int, int] | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import base64

        body = json.loads(request.read().decode("utf-8"))
        for img in body.get("images") or []:
            raw = base64.b64decode(img["base64"])
            seen_dims.append(_image_dimensions(raw))
        return httpx.Response(
            200,
            json={
                "model": "d1.2-ultra",
                "usage": {"input_tokens": 200, "output_tokens": 0},
                "answers": {"ok": {"type": "noul", "noul": 0.9}},
            },
        )

    engine = LiquidDecisionProvider(
        {"api_key": "liq-key", "max_image_dim": 640},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    engine.evaluate(
        state="check frame",
        questions=[
            DecisionQuestion(name="ok", question_type="noul", instructions="Is frame clear?")
        ],
        images=[ImageInput(path=big_jpg)],
    )
    assert seen_dims and seen_dims[0] is not None
    w, h = seen_dims[0]
    assert max(w, h) <= 640


def test_extract_narrative_signals_uses_liquid_spans() -> None:
    from vedit.director.semantic_director import extract_narrative_signals

    class _StubDecision:
        provider_name = "liquid_d1"

        def evaluate(self, *, state, questions, images=None) -> DecisionBatchResult:
            q_types = {q.name: q.question_type for q in questions}
            assert q_types["places"] == "spans"
            assert q_types["numeric_claims"] == "spans"
            assert q_types["narrative_pivots"] == "spans"
            return DecisionBatchResult(
                provider="liquid_d1",
                model="d1.2-ultra",
                input_tokens=150,
                answers={
                    "places": DecisionAnswer(
                        name="places",
                        question_type="spans",
                        raw={"spans": [{"text": "Selat Malaka", "found": 0.94}]},
                    ),
                    "numeric_claims": DecisionAnswer(
                        name="numeric_claims",
                        question_type="spans",
                        raw={"spans": [{"text": "90.000 kapal per tahun", "found": 0.91}]},
                    ),
                    "narrative_pivots": DecisionAnswer(
                        name="narrative_pivots",
                        question_type="spans",
                        raw={
                            "spans": [
                                {"text": "Namun di balik ramainya jalur ini", "found": 0.88}
                            ]
                        },
                    ),
                },
            )

    signals = extract_narrative_signals(
        {
            "text": (
                "Selat Malaka dilalui 90.000 kapal per tahun. "
                "Namun di balik ramainya jalur ini..."
            )
        },
        _StubDecision(),
    )
    assert signals["places"] == ["Selat Malaka"]
    assert signals["numeric_claims"] == ["90.000 kapal per tahun"]
    assert signals["narrative_pivots"] == ["Namun di balik ramainya jalur ini"]


def test_critique_packet_auto_scores_with_liquid_confidence_gating(tmp_path: Path) -> None:
    from vedit.director.critique import score_critique_packet_with_decision

    sheet_jpg = tmp_path / "sheet_01.jpg"
    sheet_jpg.write_bytes(b"\xff\xd8\xff\xe0dummy")

    packet: dict[str, Any] = {
        "schema_version": "1.0",
        "sheets": [{"path": str(sheet_jpg), "frames": [{"t": 0.5, "label": "b1"}]}],
        "review": {
            "instructions": "Score each criterion.",
            "scores": {"hierarchy": None, "legibility": None},
            "fixes": [],
            "rubric": [
                {
                    "criterion_id": "hierarchy",
                    "question": "Is there one clear focal hierarchy?",
                    "weight": 0.5,
                },
                {
                    "criterion_id": "legibility",
                    "question": "Is all text crisp and legible?",
                    "weight": 0.5,
                },
            ],
        },
    }

    legend5 = {"0": "a", "1": "b", "2": "c", "3": "d", "4": "e"}

    class _StubDecision:
        provider_name = "liquid_d1"

        def evaluate(self, *, state, questions, images=None) -> DecisionBatchResult:
            assert images and len(images) == 1
            return DecisionBatchResult(
                provider="liquid_d1",
                model="d1.2-ultra",
                input_tokens=300,
                answers={
                    "rubric__hierarchy": DecisionAnswer(
                        name="rubric__hierarchy",
                        question_type="score",
                        raw={"score": 3.6, "legend": legend5, "confidence": 0.89},
                    ),
                    "rubric__legibility": DecisionAnswer(
                        name="rubric__legibility",
                        question_type="score",
                        raw={"score": 2.0, "legend": legend5, "confidence": 0.52},
                    ),
                    "defect__text_clipped": DecisionAnswer(
                        name="defect__text_clipped",
                        question_type="noul",
                        raw={"noul": 0.82, "confidence": 0.86},
                    ),
                    "defect__caption_overlap": DecisionAnswer(
                        name="defect__caption_overlap",
                        question_type="noul",
                        raw={"noul": 0.05, "confidence": 0.92},
                    ),
                    "defect__blurry_map_tiles": DecisionAnswer(
                        name="defect__blurry_map_tiles",
                        question_type="noul",
                        raw={"noul": 0.1, "confidence": 0.90},
                    ),
                    "defect__cluttered_frame": DecisionAnswer(
                        name="defect__cluttered_frame",
                        question_type="noul",
                        raw={"noul": 0.15, "confidence": 0.88},
                    ),
                },
            )

    scored = score_critique_packet_with_decision(packet, _StubDecision(), confidence_threshold=0.75)
    # High-confidence score (3.6 / 4.0 = 0.9) is auto-filled.
    assert scored["review"]["scores"]["hierarchy"] == pytest.approx(0.9)
    # Low-confidence score (0.52 < 0.75) stays None and is flagged for human review.
    assert scored["review"]["scores"]["legibility"] is None
    assert "legibility" in scored["review"]["needs_human_review"]
    # High-probability noul defect (text_clipped = 0.82) is reported.
    assert any(d["code"] == "text_clipped" for d in scored["review"]["detected_defects"])


def test_resolve_decision_port_auto_mode(monkeypatch) -> None:
    from vedit.providers.decision_mode import resolve_decision_port

    monkeypatch.delenv("LIQUID_API_KEY", raising=False)
    # Prevent .env reload from re-injecting LIQUID_API_KEY during this test.
    monkeypatch.setattr("vedit.providers.config.load_dotenv_safe", lambda repo_root=None: [])
    assert resolve_decision_port("off") is None
    assert resolve_decision_port("auto") is None

    monkeypatch.setenv("LIQUID_API_KEY", "test-liquid-token")
    port = resolve_decision_port("auto")
    assert port is not None
    assert port.provider_name == "liquid_d1"


def test_geo_imagery_registered_in_provider_registry() -> None:
    from vedit.providers.registry import build_default_registry

    registry = build_default_registry()
    report = registry.status_report()
    assert "geo_imagery" in report
    names = {s["name"] for s in report["geo_imagery"]["registered"]}
    assert {"google_tiles", "open_imagery"}.issubset(names)
    assert report["geo_imagery"]["configured_primary"] == "google_tiles"


def test_google_map_tiles_client_persists_session_high_dpi_and_renews_on_expiry(
    tmp_path: Path,
) -> None:
    from vedit.geo_imagery import GoogleMapTilesClient

    cache_file = tmp_path / "google_session.json"
    calls: list[dict[str, Any]] = []
    now_holder = [1_700_000_000.0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/createSession":
            body = json.loads(request.read().decode("utf-8"))
            calls.append(body)
            sess_idx = len(calls)
            return httpx.Response(
                200,
                json={
                    "session": f"sess-token-{sess_idx}",
                    "expiry": str(int(now_holder[0] + 14 * 86400)),
                    "tileWidth": 512,
                    "tileHeight": 512,
                    "imageFormat": "jpeg",
                },
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    c1 = GoogleMapTilesClient(
        "AIza-test-key-secret",
        session_cache_path=cache_file,
        client=http_client,
        now_fn=lambda: now_holder[0],
    )
    tok1 = c1.create_session(
        map_type="satellite", scale="scaleFactor2x", high_dpi=True, image_format="jpeg"
    )
    assert tok1 == "sess-token-1"
    assert calls[0]["scale"] == "scaleFactor2x"
    assert calls[0]["highDpi"] is True
    assert calls[0]["imageFormat"] == "jpeg"
    assert (cache_file.stat().st_mode & 0o777) == 0o600

    # A brand-new client instance reuses the persisted disk session without a new HTTP call.
    c2 = GoogleMapTilesClient(
        "AIza-test-key-secret",
        session_cache_path=cache_file,
        client=http_client,
        now_fn=lambda: now_holder[0] + 3600.0,
    )
    tok2 = c2.create_session(
        map_type="satellite", scale="scaleFactor2x", high_dpi=True, image_format="jpeg"
    )
    assert tok2 == "sess-token-1"
    assert len(calls) == 1

    # Once within 1 hour of expiry, the client proactively renews the session token.
    now_holder[0] += 14 * 86400 - 1800
    tok3 = c2.create_session(
        map_type="satellite", scale="scaleFactor2x", high_dpi=True, image_format="jpeg"
    )
    assert tok3 == "sess-token-2"
    assert len(calls) == 2


def test_fetch_tile_set_enforces_max_tiles_guardrail_and_uses_httpx_without_curl(
    tmp_path: Path, monkeypatch
) -> None:
    from vedit.geo.tiles import _fetch_tile_set

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "AIza-guard-test")
    too_many = {(15, x, 100) for x in range(10)}
    with pytest.raises(ValueError, match="max_tiles_per_run"):
        _fetch_tile_set(
            tmp_path,
            too_many,
            hq_aerial=None,
            grade_tiles=False,
            provider="google",
            max_tiles_per_run=5,
        )
