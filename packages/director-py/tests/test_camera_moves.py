"""Camera preset library and move-plan expansion."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from vedit.cli import app
from vedit.director.camera_moves import (
    CameraMoveError,
    expand_move_plan,
    load_camera_presets,
    monotone_curve,
    to_baker_keyframes,
    to_scene_keys,
)


def test_preset_library_loads_and_curves_are_anchored() -> None:
    presets = load_camera_presets()
    assert {"snap_zoom_out_reveal", "route_chase_pullback", "world_card_pullback"} <= set(presets)
    for pid, preset in presets.items():
        assert preset["default_duration_s"] > 0, pid
        for key in ("zoom_curve", "bearing_curve", "pan_curve"):
            curve = preset.get(key)
            if curve:
                assert curve[0] == [0.0, 0.0], (pid, key)
                assert curve[-1][0] == 1.0 and curve[-1][1] == 1.0, (pid, key)


def test_monotone_curve_interpolates_without_overshoot() -> None:
    pts = [[0.0, 0.0], [0.5, 0.9], [0.6, 0.95], [1.0, 1.0]]
    values = [monotone_curve(pts, u / 100) for u in range(101)]
    assert values[0] == 0.0 and values[-1] == 1.0
    assert all(b >= a - 1e-9 for a, b in zip(values, values[1:], strict=False))
    assert max(values) <= 1.0 + 1e-9


def test_chained_moves_start_where_previous_ended() -> None:
    plan = {
        "start": {"center": [25.0, 42.0], "zoom": 7.0, "bearing": 7.0},
        "moves": [
            {"preset": "snap_zoom_out_reveal", "duration_s": 1.5},
            {"preset": "settle_pullback_roll", "duration_s": 1.0},
        ],
    }
    samples = expand_move_plan(plan, fps=30)
    assert len(samples) == 76
    by_frame = {s["frame"]: s for s in samples}
    assert by_frame[45]["zoom"] == pytest.approx(4.0, abs=1e-3)
    assert by_frame[45]["bearing"] == pytest.approx(3.0, abs=1e-3)
    assert by_frame[75]["zoom"] == pytest.approx(4.0 - 0.63, abs=1e-3)
    assert by_frame[75]["center"] == [25.0, 42.0]


def test_target_path_and_absolute_overrides() -> None:
    plan = {
        "start": {"center": [10.0, 0.0], "zoom": 3.0, "bearing": 12.0},
        "moves": [
            {
                "preset": "world_card_pullback",
                "target": [40.0, 10.0],
                "zoom_to": 0.5,
                "bearing_to": 0.0,
            },
            {"preset": "route_chase_pullback", "path": [[60.0, 10.0], [80.0, 0.0]]},
        ],
    }
    samples = expand_move_plan(plan, fps=30)
    card_end = next(s for s in samples if s["frame"] == round(0.75 * 30))
    assert card_end["center"] == pytest.approx([40.0, 10.0], abs=1e-4)
    assert card_end["zoom"] == pytest.approx(0.5, abs=1e-4)
    assert card_end["bearing"] == pytest.approx(0.0, abs=1e-4)
    assert samples[-1]["center"] == pytest.approx([80.0, 0.0], abs=1e-4)


def test_cut_jumps_state_and_timeline() -> None:
    plan = {
        "start": {"center": [0.0, 0.0], "zoom": 2.0},
        "moves": [
            {"preset": "card_hold_drift", "duration_s": 1.0},
            {"cut": {"center": [-70.0, -53.0], "zoom": 5.0, "bearing": 0.0, "at_s": 2.0}},
            {"preset": "nudge_toward", "target": [-64.0, -52.0]},
        ],
    }
    samples = expand_move_plan(plan, fps=30)
    cut = next(s for s in samples if s["frame"] == 60)
    assert cut["center"] == [-70.0, -53.0] and cut["zoom"] == 5.0
    assert samples[-1]["frame"] == 78
    drift = next(s for s in samples if s["frame"] == 30)
    assert drift["center"][0] < 0.0  # westward drift


def test_missing_inputs_raise() -> None:
    with pytest.raises(CameraMoveError):
        expand_move_plan({"start": {"center": [0, 0], "zoom": 1}, "moves": [{"preset": "nope"}]})
    with pytest.raises(CameraMoveError):
        expand_move_plan(
            {"start": {"center": [0, 0], "zoom": 1}, "moves": [{"preset": "nudge_toward"}]}
        )


def test_output_formats() -> None:
    samples = expand_move_plan(
        {
            "start": {"center": [5.0, 5.0], "zoom": 4.0},
            "moves": [{"preset": "nudge_toward", "target": [6, 5]}],
        },
        fps=10,
    )
    baker = to_baker_keyframes(samples)
    assert baker[0]["frame"] == 0 and baker[0]["ease"] == "linear"
    scene = to_scene_keys(samples)
    assert scene[-1][0] == pytest.approx(0.6) and len(scene[-1]) == 5


def test_cli_list_and_expand(tmp_path) -> None:
    runner = CliRunner()
    listed = runner.invoke(app, ["camera", "list", "--json"])
    assert listed.exit_code == 0
    assert any(r["preset_id"] == "slow_roll_hold" for r in json.loads(listed.stdout))

    plan_file = tmp_path / "moves.json"
    plan_file.write_text(
        json.dumps(
            {
                "start": {"center": [0, 0], "zoom": 3},
                "moves": [{"preset": "slow_roll_hold", "duration_s": 1}],
            }
        )
    )
    out = tmp_path / "keys.json"
    res = runner.invoke(
        app, ["camera", "expand", "--plan-file", str(plan_file), "-o", str(out), "--fps", "30"]
    )
    assert res.exit_code == 0, res.stdout
    keys = json.loads(out.read_text())
    assert len(keys) == 31 and keys[-1]["frame"] == 30
