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


def test_fly_to_blend_shake_and_shutter_samples() -> None:
    plan = {
        "start": {"center": [-78.0, 8.0], "zoom": 2.0, "bearing": 0.0, "pitch": 0.0},
        "blend_s": 0.2,
        "optical_shutter_blur": True,
        "moves": [
            {
                "preset": "cinema_fly_dive",
                "duration_s": 2.0,
                "target": [-77.5, 8.2],
                "zoom_to": 7.5,
            },
            {
                "preset": "impact_settle_shake",
                "duration_s": 1.0,
                "zoom_delta": 0.6,
            },
            {
                "preset": "orbital_vignette_drift",
                "duration_s": 1.0,
            },
        ],
    }
    samples = expand_move_plan(plan, fps=30)
    assert len(samples) == 121
    assert samples[0]["zoom"] == pytest.approx(2.0, abs=0.05)
    assert samples[-1]["zoom"] > 7.5
    assert any(s.get("shutter_samples", 1) > 1 for s in samples)
    assert "zoom_vel" in samples[30] and "bearing_vel" in samples[30]
    assert samples[60]["center"][0] == pytest.approx(-77.5, abs=0.15)


def _noisy_track() -> list[list[float]]:
    keys = []
    for i in range(41):
        t = i * 0.25
        wobble = 0.004 * (1 if i % 2 else -1)
        zoom = 5.0 + 0.02 * t + 0.03 * (i % 2)
        keys.append([t, 10.0 + 0.05 * t + wobble, 45.0 + wobble, zoom, 0.0])
    return keys


def test_smoothing_removes_shake_and_respects_caps_cuts_and_anchors() -> None:
    from vedit.director.camera_moves import camera_jitter_report, smooth_scene_keys

    keys = _noisy_track()
    before = camera_jitter_report(keys, cuts=[5.0])
    assert before["zoom_reversals"] > 0
    out = smooth_scene_keys(keys, window_s=0.6, cuts=[5.0], anchors=[2.5], max_zoom_shift=0.05)
    after = camera_jitter_report(out, cuts=[5.0])
    assert after["zoom_reversals"] < before["zoom_reversals"]
    by_t = {k[0]: k for k in out}
    assert by_t[2.5] == keys[10]  # anchor kept exactly
    assert by_t[0.0] == keys[0] and by_t[10.0] == keys[-1]  # span ends kept
    assert by_t[4.75] == keys[19] and by_t[5.0] == keys[20]  # cut boundary keys kept
    for a, b in zip(keys, out, strict=True):
        assert abs(a[3] - b[3]) <= 0.05 + 1e-9


def test_smoothing_unwraps_antimeridian() -> None:
    from vedit.director.camera_moves import smooth_scene_keys

    keys = [
        [0.0, 179.0, 60.0, 4.0, 0.0],
        [0.5, -179.5, 60.0, 4.0, 0.0],
        [1.0, -178.0, 60.0, 4.0, 0.0],
    ]
    out = smooth_scene_keys(keys, window_s=0.6)
    assert out[1][1] > 179.0 and out[2][1] == 182.0


def test_camera_track_cli_writes_denoised_track(tmp_path) -> None:
    src = tmp_path / "track.json"
    dst = tmp_path / "smooth.json"
    src.write_text(json.dumps(_noisy_track()), encoding="utf-8")
    result = CliRunner().invoke(
        app, ["geo", "camera-track", str(src), "-o", str(dst), "--cut", "5.0", "--json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["after"]["zoom_reversals"] <= report["before"]["zoom_reversals"]
    assert len(json.loads(dst.read_text(encoding="utf-8"))) == 41


def test_project_world_anchor_to_track_follows_pan_and_zoom() -> None:
    from vedit.director.camera_moves import project_world_anchor_to_track

    # Camera starts centered on Darien (-77.55, 8.18) at z=6, then pans east & zooms in to z=7.
    cam = [
        [0.0, -77.55, 8.18, 6.0, 0.0],
        [0.5, -77.05, 8.18, 6.5, 0.0],
        [1.0, -76.55, 8.18, 7.0, 0.0],
    ]
    kfs = project_world_anchor_to_track(
        cam,
        lng=-77.55,
        lat=8.18,
        width=1080,
        height=1920,
        start_s=0.0,
        duration_s=1.0,
        scale_with_zoom=True,
    )
    assert len(kfs) == 3
    assert kfs[0]["x_pct"] == 50.0 and kfs[0]["y_pct"] == 50.0 and kfs[0]["scale"] == 1.0
    # As camera pans east, the anchor moves left (< 50%) and doubles in scale at +1 zoom.
    assert kfs[-1]["x_pct"] < 50.0
    assert kfs[-1]["scale"] == 2.0


def test_build_cinema_camera_track_is_c2_smooth_and_orbits_3d() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    kfs = [
        [0.0, -100.0, 25.0, 2.2, -20.0, 5.0],
        [2.0, -77.55, 8.18, 7.2, 18.0, 48.0],
        [4.0, -77.55, 8.18, 7.6, 35.0, 52.0],
    ]
    samples = build_cinema_camera_track(kfs, duration_s=4.0, fps=30.0, smooth_s=0.22)
    assert len(samples) == 120
    # Smooth 3D bearing & pitch progression without spikes.
    bearings = [s["bearing"] for s in samples]
    pitches = [s["pitch"] for s in samples]
    assert bearings[0] == -20.0 and abs(bearings[-1] - 35.0) < 0.5
    assert pitches[-1] >= 48.0
    max_bearing_step = max(abs(bearings[i] - bearings[i - 1]) for i in range(1, len(bearings)))
    assert max_bearing_step < 2.0
    assert "roll" in samples[0]


def test_cinema_camera_hyperbolic_fly_roll_micro_drift_and_auto_shutter() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    # Lateral hop between two high-zoom landmarks (Llivia -> Pheasant Island)
    kfs = [
        {
            "t": 0.0,
            "center": [1.98, 42.46],
            "zoom": 12.0,
            "bearing": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
        },
        {
            "t": 2.5,
            "center": [-1.765, 43.343],
            "zoom": 12.0,
            "bearing": 14.0,
            "pitch": 18.0,
            "roll": 3.5,
            "curve": "hyperbolic_fly",
            "rho": 1.42,
        },
        {
            "t": 4.0,
            "center": [-1.765, 43.343],
            "zoom": 12.0,
            "bearing": 14.0,
            "pitch": 18.0,
            "roll": 0.0,
            "curve": "orbit_cruise",
        },
    ]
    samples = build_cinema_camera_track(
        kfs,
        duration_s=4.0,
        fps=30.0,
        auto_shutter=True,
        micro_drift={"enabled": True, "amp_bearing": 0.5, "amp_roll": 0.4},
    )
    assert len(samples) == 120
    # Hyperbolic fly lifts altitude (lowers zoom) mid-flight between two z=12 endpoints
    min_mid_zoom = min(s["zoom"] for s in samples[15:65])
    assert min_mid_zoom < 9.5
    # Roll banks during turn and settles back near 0 at endpoints
    assert max(abs(s["roll"]) for s in samples) > 1.5
    assert samples[0]["roll"] == pytest.approx(0.0, abs=0.05)
    assert samples[-1]["roll"] == pytest.approx(0.0, abs=0.05)
    # Velocity-adaptive shutter engages (>1) during fast hop and drops to 1 during calm hold
    assert max(s["shutter_samples"] for s in samples[10:65]) >= 3
    assert samples[-1]["shutter_samples"] == 1


def test_project_world_anchor_supports_3d_pitch_and_map_plane() -> None:
    from vedit.director.camera_moves import project_world_anchor_to_track

    cam = [
        {
            "t": 0.0,
            "center": [-3.6, 40.2],
            "zoom": 5.0,
            "bearing": 10.0,
            "pitch": 35.0,
            "roll": 2.0,
        },
        {
            "t": 1.0,
            "center": [-3.6, 40.2],
            "zoom": 5.5,
            "bearing": 15.0,
            "pitch": 40.0,
            "roll": 2.5,
        },
    ]
    kfs = project_world_anchor_to_track(
        cam,
        lng=-3.6,
        lat=40.2,
        width=1080,
        height=1920,
        start_s=0.0,
        duration_s=1.0,
        space="map_plane",
    )
    assert len(kfs) == 2
    assert kfs[0]["rotateX_deg"] == pytest.approx(35.0, abs=0.1)
    assert kfs[1]["rotateX_deg"] == pytest.approx(40.0, abs=0.1)
    assert kfs[0]["perspective_px"] > 1000.0


def test_camera_math_handles_extreme_zoom_duplicate_cuts_antimeridian_and_track_chaining() -> None:
    from vedit.director.camera_moves import (
        _van_wijk_fly_to,
        build_cinema_camera_track,
        camera_jitter_report,
        project_world_anchor_to_track,
    )

    # Extreme zoom dive must not hit log(0) math domain error
    x, y, z = _van_wijk_fly_to(0.0, 0.0, 18.0, 1e-4, 0.0, 1.0, 0.5)
    assert z == z  # finite

    # Duplicate-timestamp hard cut must not ZeroDivisionError and must not bleed spline jitter
    static_with_cut = [
        [0.0, 0.0, 0.0, 4.0, 0.0],
        [1.5, 0.0, 0.0, 4.0, 0.0],
        [1.5, 45.0, 20.0, 7.0, 0.0],
        [3.0, 45.0, 20.0, 7.0, 0.0],
    ]
    report = camera_jitter_report(static_with_cut, cuts=[1.5], fps=30.0)
    assert report["flagged_frames"] == 0
    assert report["reversals"] == 0

    # build_cinema_camera_track includes 't'/'frame', wraps antimeridian, and chains into projection
    samples = build_cinema_camera_track(
        [
            {"t": 0.0, "center": [179.5, 10.0], "zoom": 6.0, "bearing": 0.0, "pitch": 10.0},
            {"t": 1.0, "center": [-179.5, 10.0], "zoom": 6.5, "bearing": 0.0, "pitch": 15.0},
        ],
        duration_s=1.0,
        fps=10.0,
        smooth_s=0.0,
    )
    assert "t" in samples[0] and "frame" in samples[0]
    assert samples[-1]["t"] > 0.5
    # Must take shortest 1-degree path across antimeridian rather than zooming out to ~0
    assert min(s["zoom"] for s in samples) >= 5.5

    projected = project_world_anchor_to_track(
        samples, lng=-179.5, lat=10.0, width=1080, height=1920, start_s=0.0, duration_s=1.0
    )
    assert len(projected) == len(samples)
    assert projected[-1]["t_s"] > 0.5
    assert all(0.0 <= kf["x_pct"] <= 100.0 for kf in projected)


def test_project_world_anchor_dedupes_t0_and_clamps_rotate_x_and_smooth_orbit_exit() -> None:
    from vedit.director.camera_moves import (
        build_cinema_camera_track,
        project_world_anchor_to_track,
    )

    cam = [
        {
            "t": round(i / 30.0, 5),
            "center": [0.0 + i * 0.01, 10.0],
            "zoom": 5.0,
            "bearing": 0.0,
            "pitch": 78.0,
        }
        for i in range(60)
    ]
    kfs = project_world_anchor_to_track(
        cam,
        lng=0.3,
        lat=10.0,
        width=1080,
        height=1920,
        start_s=1.0,
        duration_s=0.5,
        space="map_plane",
    )
    t0_rows = [k for k in kfs if k["t_s"] == 0.0]
    assert len(t0_rows) == 1
    assert all(k.get("rotateX_deg", 0.0) <= 72.0 for k in kfs)

    # Exiting an orbiting keyframe to a non-orbiting keyframe must not teleport at the boundary.
    samples = build_cinema_camera_track(
        [
            {
                "t": 0.0,
                "center": [0.0, 0.0],
                "zoom": 5.0,
                "bearing": 0.0,
                "orbit_target": [0.0, 0.0],
                "orbit_radius_deg": 1.0,
            },
            {
                "t": 1.0,
                "center": [0.0, 0.0],
                "zoom": 5.0,
                "bearing": 90.0,
            },
            {
                "t": 2.0,
                "center": [0.0, 0.0],
                "zoom": 5.0,
                "bearing": 90.0,
            },
        ],
        duration_s=2.0,
        fps=30.0,
        smooth_s=0.0,
    )
    max_jump = max(
        abs(samples[i]["center"][0] - samples[i - 1]["center"][0])
        + abs(samples[i]["center"][1] - samples[i - 1]["center"][1])
        for i in range(1, len(samples))
    )
    assert max_jump < 0.25


def _zoom_velocity(samples: list[dict]) -> list[float]:
    """Central-difference zoom velocity (log2 per frame) for every sample."""
    zs = [s["zoom"] for s in samples]
    vel = [0.0] * len(zs)
    for i in range(1, len(zs) - 1):
        vel[i] = (zs[i + 1] - zs[i - 1]) / 2.0
    return vel


def test_rest_keyframes_have_zero_velocity() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    kfs = [
        {"t": 0.0, "center": [10.0, 50.0], "zoom": 4.0},
        {"t": 1.2, "center": [10.0, 50.0], "zoom": 8.0, "curve": "snap_dive"},
        {"t": 2.6, "center": [10.0, 50.0], "zoom": 6.0, "curve": "snap_dive"},
    ]
    samples = build_cinema_camera_track(kfs, duration_s=3.0, fps=30.0)
    vel = _zoom_velocity(samples)
    peak = max(abs(v) for v in vel)
    assert peak > 0.05
    for key_frame in (36, 78):
        assert abs(vel[key_frame]) < 0.02 * peak, (key_frame, vel[key_frame], peak)
    max_jump = max(abs(vel[i] - vel[i - 1]) for i in range(2, len(vel) - 1))
    assert max_jump < 0.25 * peak


def test_profile_peak_positions() -> None:
    from vedit.director.camera_moves import eased_progress

    def peak_fraction(curve: str) -> float:
        steps = 2000
        best_u, best_v = 0.0, -1.0
        for i in range(steps):
            u0, u1 = i / steps, (i + 1) / steps
            v = eased_progress(u1, curve) - eased_progress(u0, curve)
            if v > best_v:
                best_u, best_v = (u0 + u1) / 2.0, v
        return best_u

    for curve in ("glide", "snap_dive", "whip_snap", "hyperbolic_fly", "orbit_cruise", "auto"):
        assert eased_progress(0.0, curve) == pytest.approx(0.0, abs=1e-9)
        assert eased_progress(1.0, curve) == pytest.approx(1.0, abs=1e-9)
        values = [eased_progress(i / 200, curve) for i in range(201)]
        assert all(b >= a for a, b in zip(values, values[1:], strict=False))
        # Zero slope at both ends (rest points).
        assert eased_progress(0.01, curve) < 0.01 * 0.2
        assert 1.0 - eased_progress(0.99, curve) < 0.01 * 0.2
    assert 0.28 <= peak_fraction("snap_dive") <= 0.42
    assert 0.45 <= peak_fraction("glide") <= 0.55


def test_through_keyframe_keeps_moving() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    kfs = [
        {"t": 0.0, "center": [10.0, 50.0], "zoom": 4.0},
        {"t": 1.0, "center": [10.0, 50.0], "zoom": 6.0, "through": True},
        {"t": 2.0, "center": [10.0, 50.0], "zoom": 8.0},
    ]
    samples = build_cinema_camera_track(kfs, duration_s=2.0, fps=30.0)
    vel = _zoom_velocity(samples)
    peak = max(abs(v) for v in vel)
    assert abs(vel[30]) > 0.5 * peak
    assert samples[30]["zoom"] == pytest.approx(6.0, abs=0.35)


def test_single_and_duplicate_keyframes() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    single = build_cinema_camera_track(
        [{"t": 0.5, "center": [3.0, 4.0], "zoom": 7.0}], duration_s=1.0, fps=10.0
    )
    assert len(single) == 10
    assert {s["zoom"] for s in single} == {7.0}
    assert {tuple(s["center"]) for s in single} == {(3.0, 4.0)}

    dup = build_cinema_camera_track(
        [
            {"t": 1.0, "center": [3.0, 4.0], "zoom": 7.0},
            {"t": 1.0, "center": [3.0, 4.0], "zoom": 7.0, "through": True},
            {"t": 1.0, "center": [3.0, 4.0], "zoom": 7.0},
        ],
        duration_s=2.0,
        fps=10.0,
    )
    assert {s["zoom"] for s in dup} == {7.0}

    cut = build_cinema_camera_track(
        [
            {"t": 0.0, "center": [0.0, 0.0], "zoom": 3.0},
            {"t": 1.0, "center": [0.0, 0.0], "zoom": 5.0},
            {"t": 1.0, "center": [20.0, 10.0], "zoom": 7.0},
            {"t": 2.0, "center": [20.0, 10.0], "zoom": 7.0},
        ],
        duration_s=2.0,
        fps=10.0,
    )
    assert cut[5]["zoom"] < 5.0
    assert cut[15]["zoom"] == pytest.approx(7.0)


def test_auto_shutter_adaptive() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    kfs = [
        {"t": 0.0, "center": [10.0, 50.0], "zoom": 4.0},
        {"t": 1.0, "center": [10.0, 50.0], "zoom": 9.0},
        {"t": 2.0, "center": [10.0, 50.0], "zoom": 9.0},
    ]
    samples = build_cinema_camera_track(kfs, duration_s=2.0, fps=30.0, auto_shutter=True)
    assert max(s["shutter_samples"] for s in samples[5:26]) >= 6
    assert all(s["shutter_samples"] == 1 for s in samples[40:60])
    assert max(s["shutter_samples"] for s in samples) <= 16
    off = build_cinema_camera_track(kfs, duration_s=2.0, fps=30.0)
    assert {s["shutter_samples"] for s in off} == {1}


def test_cuts_with_through_keyframes_start_cuts_auto_shutter_and_none_curve() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    cut_after_through = build_cinema_camera_track(
        [
            {"t": 0.0, "center": [0.0, 0.0], "zoom": 3.0},
            {"t": 1.0, "center": [0.0, 0.0], "zoom": 5.0, "through": True},
            {"t": 1.0, "center": [20.0, 10.0], "zoom": 8.0},
            {"t": 2.0, "center": [20.0, 10.0], "zoom": 9.0},
        ],
        duration_s=2.0,
        fps=10.0,
        auto_shutter=True,
    )
    assert cut_after_through[5]["zoom"] == pytest.approx(4.0, abs=0.05)
    assert cut_after_through[10]["shutter_samples"] == 1

    cut_at_start = build_cinema_camera_track(
        [
            {"t": 0.0, "center": [0.0, 0.0], "zoom": 3.0},
            {"t": 0.0, "center": [10.0, 10.0], "zoom": 7.0},
            {"t": 1.0, "center": [20.0, 20.0], "zoom": 9.0},
        ],
        duration_s=1.0,
        fps=10.0,
    )
    assert cut_at_start[0]["zoom"] == pytest.approx(7.0, abs=1e-3)

    cut_only = build_cinema_camera_track(
        [
            {"t": 1.0, "center": [0.0, 0.0], "zoom": 3.0},
            {"t": 1.0, "center": [10.0, 10.0], "zoom": 7.0},
        ],
        duration_s=2.0,
        fps=10.0,
    )
    assert cut_only[9]["zoom"] == pytest.approx(3.0)
    assert cut_only[10]["zoom"] == pytest.approx(7.0)

    none_curve = build_cinema_camera_track(
        [
            {"t": 0.0, "center": [-74.0, 40.7], "zoom": 10.0, "curve": "hyperbolic_fly"},
            {"t": 1.0, "center": [139.7, 35.7], "zoom": 10.0, "curve": None},
        ],
        duration_s=1.0,
        fps=10.0,
    )
    assert min(s["zoom"] for s in none_curve) < 6.0


def test_high_zoom_slow_drift_preserves_subpixel_precision() -> None:
    from vedit.director.camera_moves import build_cinema_camera_track

    # Slow 1.0s drift across ~30 meters at z=16.5 (~0.00027 deg total, ~9e-6 deg/frame).
    # With 5-decimal quantization (1e-5 deg) adjacent frames stall identically; 7-decimal precision
    # preserves smooth sub-pixel increments on every interior frame.
    kfs = [
        {
            "t": 0.0,
            "center": [106.8270000, -6.1750000],
            "zoom": 16.5,
            "pitch": 45.0,
            "bearing": 12.0,
        },
        {
            "t": 1.0,
            "center": [106.8272700, -6.1751800],
            "zoom": 16.504,
            "pitch": 45.12,
            "bearing": 12.15,
        },
    ]
    samples = build_cinema_camera_track(kfs, duration_s=1.0, fps=30.0)
    assert len(samples) == 30
    interior = samples[4:26]
    # Every consecutive interior frame must advance strictly in longitude and pitch.
    stalled_lng = sum(
        1 for a, b in zip(interior, interior[1:], strict=False) if a["center"][0] == b["center"][0]
    )
    stalled_pitch = sum(
        1 for a, b in zip(interior, interior[1:], strict=False) if a["pitch"] == b["pitch"]
    )
    assert stalled_lng == 0, f"Detected {stalled_lng} quantized longitude stalls at z=16.5"
    assert stalled_pitch == 0, f"Detected {stalled_pitch} quantized pitch stalls"
