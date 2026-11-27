"""Storyboard contract, executable directing idioms, auto-director, journey compile, critique."""

from __future__ import annotations

import copy
import json

import pytest
from typer.testing import CliRunner

from vedit.cli import app
from vedit.director.critique import build_critique_packet, gate_review
from vedit.director.journey import compile_journey, head_keys, place_callout
from vedit.director.storyboard import (
    apply_director_storyboard,
    check_storyboard,
    idioms_path,
    load_directing_idioms,
    scaffold_storyboard,
)


@pytest.fixture(scope="module")
def idioms() -> dict:
    return load_directing_idioms(idioms_path("geoverum"))


def _transcript() -> dict:
    text = (
        "This man has been walking for 27 years, the only person in history. "
        "In 1998 he left Chile. Why did he never stop? Rebels arrested him in Panama, "
        "then he walked north to Alaska."
    )
    words, t = [], 0.0
    for tok in text.split():
        words.append({"text": tok, "start_s": round(t, 3), "end_s": round(t + 0.3, 3)})
        t += 0.38
    return {
        "source_hash": "abcdef12",
        "provider": "test",
        "language": "en",
        "duration_s": round(t, 3),
        "text": text,
        "words": words,
    }


def _journey() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "demo",
        "brand_id": "geoverum",
        "duration_s": 8.0,
        "directing_source": "user",
        "pacing": "dense",
        "story": {"shape": "journey_chain", "signature_image": "route"},
        "route": {
            "path": [[-70.8, -53.6], [-70.3, -18.6], [-77.0, 7.76], [-99.2, 19.4]],
            "markers": {"start": 0, "north": 1, "jungle": 2, "mexico": 3},
        },
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.0,
                "end_s": 1.4,
                "clause": "it starts here",
                "function": "hook",
                "story_need": "locate the start",
                "device": "pin_and_label",
                "sync_word": "here",
                "sync_word_s": 0.2,
                "camera": {"regime": "wide"},
                "head": {"marker": "start", "arrive_s": 0.2},
                "uses_signature_image": True,
            },
            {
                "beat_id": "b2",
                "start_s": 1.3,
                "end_s": 2.8,
                "clause": "north",
                "function": "proof",
                "story_need": "show the first leg",
                "device": "route_draw",
                "sync_word": "north",
                "sync_word_s": 1.9,
                "camera": {"regime": "regional", "move_start_s": 1.3},
                "head": {"marker": "north", "arrive_s": 1.8},
                "callouts": [{"kind": "avatar", "size_px": 200, "start_s": 1.5, "end_s": 2.8}],
            },
            {
                "beat_id": "b3",
                "start_s": 2.7,
                "end_s": 4.0,
                "clause": "the jungle",
                "function": "obstacle",
                "story_need": "make the jungle a wall",
                "device": "hazard_icons",
                "treatment": "green",
                "sync_word": "jungle",
                "sync_word_s": 3.0,
                "camera": {"regime": "close", "move_start_s": 2.5},
                "head": {"marker": "jungle", "arrive_s": 2.9},
            },
            {
                "beat_id": "b4",
                "start_s": 3.9,
                "end_s": 5.2,
                "clause": "arrested",
                "function": "obstacle",
                "story_need": "detention as a cage",
                "device": "cage_drop",
                "treatment": "red",
                "sync_word": "arrested",
                "sync_word_s": 3.95,
                "head": {"marker": "jungle", "motion": "hold"},
            },
            {
                "beat_id": "b5",
                "start_s": 5.1,
                "end_s": 8.0,
                "clause": "then to Mexico",
                "function": "outro",
                "story_need": "land the leg",
                "device": "route_draw",
                "sync_word": "Mexico",
                "sync_word_s": 5.7,
                "camera": {"regime": "wide", "move_start_s": 5.1},
                "head": {"marker": "mexico", "arrive_s": 5.6},
                "uses_signature_image": True,
            },
        ],
    }


def test_brand_idioms_validate(idioms: dict) -> None:
    assert idioms["brand_id"] == "geoverum"
    assert {"hook_event_early", "event_cadence", "caption_band_clear"} <= {
        i["idiom_id"] for i in idioms["idioms"]
    }


def test_auto_director_produces_valid_scored_storyboard(idioms: dict) -> None:
    sb = scaffold_storyboard(_transcript(), idioms, project_id="demo", pacing="dense")
    report = check_storyboard(sb, idioms)
    assert report.passed, report.to_dict()
    assert sb["directing_source"] == "auto"
    assert sb["story"]["shape"] == "journey_chain"
    assert sb["beats"][0]["start_s"] == 0.0 and sb["beats"][0]["function"] == "hook"
    assert sb["beats"][-1]["function"] == "outro"
    devices = {b["sync_word"]: b["device"] for b in sb["beats"]}
    assert devices.get("27") == "numeral"
    assert devices.get("1998") == "era_marker"
    assert "hazard_icons" in devices.values()


def test_emphasis_word_becomes_sync_word(idioms: dict) -> None:
    sb = scaffold_storyboard(_transcript(), idioms, project_id="demo", emphasis_words=["history"])
    assert any(b["sync_word"] == "history" for b in sb["beats"])


def test_idioms_flag_problems_and_overrides_retune(idioms: dict) -> None:
    sb = _journey()
    assert check_storyboard(sb, idioms).passed
    bad = copy.deepcopy(sb)
    bad["beats"][0]["start_s"] = 1.2
    bad["beats"][0]["story_need"] = "todo"
    bad["beats"][3]["device"], bad["beats"][3]["treatment"] = "hazard_icons", "green"
    report = check_storyboard(bad, idioms)
    found = {i.idiom_id for i in report.issues}
    assert {"hook_event_early", "story_need_stated", "obstacles_differ"} <= found
    assert not report.passed and report.score < check_storyboard(sb, idioms).score
    bad["overrides"] = {
        "disabled_idioms": ["obstacles_differ"],
        "idiom_params": {"hook_event_early": {"max_first_event_s": 2.0}},
    }
    found = {i.idiom_id for i in check_storyboard(bad, idioms).issues}
    assert "obstacles_differ" not in found and "hook_event_early" not in found


def test_contract_rejects_unknown_marker(idioms: dict) -> None:
    sb = _journey()
    sb["beats"][1]["head"]["marker"] = "nowhere"
    report = check_storyboard(sb, idioms)
    assert not report.passed and report.issues[0].idiom_id == "contract"


def test_director_layer_overrides_auto(idioms: dict) -> None:
    auto = scaffold_storyboard(_transcript(), idioms, project_id="demo")
    directed_beat = dict(auto["beats"][1], device="title_card", story_need="state the record")
    directed = {
        "story": {"hook_mechanism": "record_claim"},
        "overrides": {"locked_beat_ids": [directed_beat["beat_id"]], "banned_devices": ["numeral"]},
        "beats": [directed_beat],
    }
    merged = apply_director_storyboard(auto, directed)
    by_id = {b["beat_id"]: b for b in merged["beats"]}
    assert by_id[directed_beat["beat_id"]]["device"] == "title_card"
    assert merged["story"]["hook_mechanism"] == "record_claim"
    assert "numeral" not in {b["device"] for b in merged["beats"]}
    assert merged["directing_source"] == "mixed"
    with pytest.raises(ValueError):
        apply_director_storyboard(auto, {"overrides": {"locked_beat_ids": ["b999"]}, "beats": []})


def test_head_schedule_holds_and_never_reverses() -> None:
    keys = head_keys(_journey())
    idx = [k[1] for k in keys]
    assert idx == sorted(idx)
    assert [3.9, 2.0] in keys and [5.2, 2.0] in keys  # held during the arrest beat


def test_compile_journey_resolves_callouts_outside_caption_band(idioms: dict) -> None:
    result = compile_journey(_journey(), idioms)
    assert result["camera_keys"] and result["route_width_keys"]
    widths = [w for _, w in result["route_width_keys"]]
    assert min(widths) >= 6 and max(widths) <= 26
    avatar = result["storyboard"]["beats"][1]["callouts"][0]
    assert "xy" in avatar
    assert check_storyboard(result["storyboard"], idioms).passed


def test_place_callout_trails_head_and_avoids_band() -> None:
    x, y = place_callout((540.0, 900.0), (1.0, 0.0), 200.0)
    assert x < 540.0  # behind a rightward-moving head
    assert not (1267 < y + 100 and y - 100 < 1459)
    low = place_callout((540.0, 1300.0), (0.0, -1.0), 200.0)
    assert not (1267 < low[1] + 100 and low[1] - 100 < 1459)


def test_critique_gate(idioms: dict) -> None:
    packet = build_critique_packet(
        idioms=idioms,
        storyboard=_journey(),
        camera_track=[[0, 0, 0, 3, 0], [1, 1, 0, 3, 0], [2, 2, 0, 3, 0]],
    )
    assert packet["deterministic"]["storyboard"]["passed"]
    assert packet["deterministic"]["camera"]["passed"]
    gate = gate_review(packet)
    assert not gate["passed"] and "unscored" in gate["reasons"][0]
    packet["review"]["scores"] = {k: 0.9 for k in packet["review"]["scores"]}
    assert gate_review(packet)["passed"]
    packet["review"]["scores"]["layout_tidiness"] = 0.3
    assert not gate_review(packet)["passed"]

    # Deleting a criterion or inflating scores > 1.0 must fail closed.
    tampered = json.loads(json.dumps(packet))
    tampered["review"]["scores"] = {k: 0.9 for k in tampered["review"]["scores"]}
    first_key = next(iter(tampered["review"]["scores"]))
    del tampered["review"]["scores"][first_key]
    tampered_gate = gate_review(tampered)
    assert not tampered_gate["passed"]
    assert any("unscored" in r for r in tampered_gate["reasons"])

    inflated = json.loads(json.dumps(packet))
    inflated["review"]["scores"] = {k: 1.5 for k in inflated["review"]["scores"]}
    inflated_gate = gate_review(inflated)
    assert not inflated_gate["passed"]
    assert any("outside [0, 1]" in r for r in inflated_gate["reasons"])


def test_split_clauses_preserves_trailing_clause_before_filler(idioms: dict) -> None:
    transcript = {
        "duration_s": 2.4,
        "text": "Border without government control um",
        "words": [
            {"text": "Border", "start_s": 0.0, "end_s": 0.4},
            {"text": "without", "start_s": 0.4, "end_s": 0.8},
            {"text": "government", "start_s": 0.8, "end_s": 1.3},
            {"text": "control", "start_s": 1.3, "end_s": 1.8},
            {"text": "um", "start_s": 1.9, "end_s": 2.2, "is_filler": True},
        ],
    }
    sb = scaffold_storyboard(transcript, idioms, project_id="filler_test")
    assert len(sb["beats"]) == 1
    assert sb["beats"][0]["device"] == "prohibition_badge"


def test_storyboard_cli_roundtrip(tmp_path) -> None:
    tr = tmp_path / "t.json"
    out = tmp_path / "sb.json"
    tr.write_text(json.dumps(_transcript()), encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "storyboard",
            "auto",
            str(tr),
            "-o",
            str(out),
            "--project-id",
            "demo",
            "--brand",
            "geoverum",
        ],
    )
    assert res.exit_code == 0, res.output
    res = runner.invoke(app, ["storyboard", "check", str(out), "--min-score", "0"])
    assert res.exit_code == 0, res.output
    jr = tmp_path / "j.json"
    jr.write_text(json.dumps(_journey()), encoding="utf-8")
    res = runner.invoke(app, ["storyboard", "journey", str(jr), "-o", str(tmp_path / "keys.json")])
    assert res.exit_code == 0, res.output
    packet = tmp_path / "packet.json"
    res = runner.invoke(app, ["critique", "packet", "-o", str(packet), "--storyboard", str(jr)])
    assert res.exit_code == 0, res.output
    res = runner.invoke(app, ["critique", "gate", str(packet)])
    assert res.exit_code == 1

    # Typed surgical fix apply-fixes CLI roundtrip.
    loaded_packet = json.loads(packet.read_text(encoding="utf-8"))
    loaded_packet["review"]["fixes"] = [{"beat_id": "b2", "kind": "timing"}]
    packet.write_text(json.dumps(loaded_packet), encoding="utf-8")
    fixed_sb = tmp_path / "fixed_sb.json"
    res = runner.invoke(
        app,
        ["critique", "apply-fixes", str(jr), str(packet), "-o", str(fixed_sb)],
    )
    assert res.exit_code == 0, res.output
    assert fixed_sb.is_file()


def test_numeric_parity_flags_mismatched_callout_and_accepts_dual_unit_match(idioms: dict) -> None:
    sb = copy.deepcopy(_journey())
    sb["beats"][0]["clause"] = "Chile stretches 4,200 kilometers north to south."
    sb["beats"][0]["device"] = "numeral"
    sb["beats"][0]["callouts"] = [
        {"kind": "numeral", "text": "2,700 km", "xy": [540, 800]}
    ]
    issues = check_storyboard(sb, idioms).issues
    assert any(i.idiom_id == "numeric_parity" and i.beat_id == "b1" for i in issues)

    sb["beats"][0]["callouts"][0]["text"] = "4,200 km / 2,610 mi"
    issues_after = check_storyboard(sb, idioms).issues
    assert not any(i.idiom_id == "numeric_parity" for i in issues_after)

    sb["beats"][0]["clause"] = "The plateau averages 4,500 meters high."
    sb["beats"][0]["callouts"][0]["text"] = "4,500 m / 14,760 ft"
    issues_dual = check_storyboard(sb, idioms).issues
    assert not any(i.idiom_id == "numeric_parity" for i in issues_dual)


def test_callout_safe_margins_flags_clipped_edges_and_top_ruler(idioms: dict) -> None:
    sb = copy.deepcopy(_journey())
    sb["beats"][1]["callouts"] = [
        {"kind": "label", "text": "WEST", "xy": [50, 900]}
    ]
    issues = check_storyboard(sb, idioms).issues
    assert any(i.idiom_id == "callout_safe_margins" and i.beat_id == "b2" for i in issues)

    sb2 = copy.deepcopy(_journey())
    sb2["beats"][1]["device"] = "measurement_line"
    sb2["beats"][1]["callouts"] = [
        {"kind": "label", "text": "500 KM", "xy": [540, 110]}
    ]
    issues_ruler = check_storyboard(sb2, idioms).issues
    assert any(
        i.idiom_id == "callout_safe_margins" and i.beat_id == "b2" for i in issues_ruler
    )

    sb3 = copy.deepcopy(_journey())
    sb3["beats"][1]["device"] = "measurement_line"
    sb3["beats"][1]["callouts"] = [
        {"kind": "label", "text": "500 KM", "xy": [540, 1280]}
    ]
    issues_clean = check_storyboard(sb3, idioms).issues
    assert not any(i.idiom_id == "callout_safe_margins" for i in issues_clean)


def test_auto_director_routes_wind_and_altitude_clauses_to_new_devices(idioms: dict) -> None:
    def _tr(text: str) -> dict:
        words, t = [], 0.0
        for tok in text.split():
            words.append({"text": tok, "start_s": round(t, 3), "end_s": round(t + 0.25, 3)})
            t += 0.3
        return {
            "source_hash": "synth1",
            "provider": "test",
            "language": "en",
            "duration_s": round(t, 3),
            "text": text,
            "words": words,
        }

    sb_wind = scaffold_storyboard(
        _tr("The jet stream pushes winter flights east"), idioms, project_id="wind"
    )
    assert sb_wind["beats"][0]["device"] == "chevron_flow_band"

    sb_alt = scaffold_storyboard(
        _tr("The high plateau elevation blocks planes"), idioms, project_id="alt"
    )
    assert sb_alt["beats"][0]["device"] == "cutaway_gauge"

    sb_dim = scaffold_storyboard(
        _tr("The narrow coastline stretches miles long"), idioms, project_id="dim"
    )
    assert sb_dim["beats"][0]["device"] == "measurement_line"

    sb_era = scaffold_storyboard(
        _tr("During the ancient Roman empire era"), idioms, project_id="era"
    )
    assert sb_era["beats"][0]["device"] == "era_marker"


def test_scale_dimension_scaffold_critique_wcag_and_journey_invariants(idioms: dict) -> None:
    from vedit.contracts import validate_against_contract
    from vedit.director.critique import _frange, build_critique_packet, gate_review
    from vedit.director.journey import compile_journey, path_point, route_width_keys

    # H1: scale_dimension clause in middle beat must produce a valid storyboard function.
    words = [
        {"text": "Intro.", "start_s": 0.0, "end_s": 0.6},
        {"text": "The", "start_s": 1.0, "end_s": 1.2},
        {"text": "strait", "start_s": 1.25, "end_s": 1.6},
        {"text": "is", "start_s": 1.65, "end_s": 1.8},
        {"text": "wide.", "start_s": 1.85, "end_s": 2.3},
        {"text": "End.", "start_s": 3.0, "end_s": 3.5},
    ]
    sb = scaffold_storyboard(
        {
            "source_hash": "h1",
            "provider": "test",
            "language": "en",
            "duration_s": 3.5,
            "text": "Intro. The strait is wide. End.",
            "words": words,
        },
        idioms,
        project_id="scale_check",
    )
    rep = check_storyboard(sb, idioms)
    assert rep.passed is True, rep.issues

    # H2 + M1: typography_contrast validates against schema, gates WCAG failures, rejects bools.
    packet = build_critique_packet(
        idioms=idioms,
        storyboard=sb,
        spatial_forensics={"summary": {"typography": {"min_wcag_contrast": 2.1}}},
    )
    assert validate_against_contract(packet, "critique_packet.schema.json") == []
    packet["review"]["scores"] = {k: 0.95 for k in packet["review"]["scores"]}
    gate = gate_review(packet)
    assert gate["passed"] is False
    assert any("contrast" in r.lower() for r in gate["reasons"])

    packet_bool = copy.deepcopy(packet)
    packet_bool["deterministic"]["typography_contrast"]["passed"] = True
    first_key = next(iter(packet_bool["review"]["scores"]))
    packet_bool["review"]["scores"][first_key] = True
    gate_bool = gate_review(packet_bool)
    assert gate_bool["passed"] is False

    # M7: _frange must reject non-positive steps.
    with pytest.raises(ValueError):
        _frange(0.0, 2.0, 0.0)

    # H8 + M8: route_width_keys and path_point boundary safety + journey idiom margins.
    assert route_width_keys([[0.0, 0.0, 0.0, 5.0, 0.0]], {}) == []
    assert route_width_keys(
        [[0.0, 0.0, 0.0, 5.0, 0.0]],
        {"a": {"zoom": 5.0, "route_width_px": 4.0}, "b": {"zoom": 5.0, "route_width_px": 6.0}},
    ) == [[0.0, 4.0]]
    assert path_point([[10.0, 20.0], [30.0, 40.0]], -2.0) == (10.0, 20.0)
    compiled = compile_journey(_journey(), idioms)
    assert check_storyboard(compiled["storyboard"], idioms).passed is True

    # M8: all-filler transcript raises ValueError; banning camera_drift does not keep camera_drift.
    with pytest.raises(ValueError):
        scaffold_storyboard(
            {
                "source_hash": "h2",
                "provider": "test",
                "language": "en",
                "duration_s": 1.0,
                "text": "um",
                "words": [{"text": "um", "start_s": 0.0, "end_s": 0.5, "is_filler": True}],
            },
            idioms,
            project_id="fillers",
        )
    directed = {
        "overrides": {"banned_devices": ["camera_drift"]},
        "beats": [],
    }
    sb_drift = copy.deepcopy(sb)
    sb_drift["beats"][0]["device"] = "camera_drift"
    merged = apply_director_storyboard(sb_drift, directed)
    assert merged["beats"][0]["device"] != "camera_drift"

