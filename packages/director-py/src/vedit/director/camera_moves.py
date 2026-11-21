"""Expand chained map camera presets into per-frame MapLibre camera keyframes.

A move plan starts from an explicit camera state and chains presets from
`tools/geo-assets/camera_presets.json`; every move begins where the previous one ended,
so a whole shot is described by a handful of preset names instead of hand-tuned keys.
`cut` entries replace the state instantly (hard cuts between shots).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root

TILE_SIZE = 512.0
PAN_MODES = {"hold", "drift", "to_target", "path"}


class CameraMoveError(ValueError):
    """Raised when a move plan references unknown presets or lacks required inputs."""


@dataclass(frozen=True)
class CameraState:
    lng: float
    lat: float
    zoom: float
    bearing: float = 0.0
    pitch: float = 0.0


def presets_path(repo_root: Path | None = None) -> Path:
    return (repo_root or find_repo_root()) / "tools" / "geo-assets" / "camera_presets.json"


def load_camera_presets(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the preset library keyed by `preset_id`."""
    data = json.loads((path or presets_path()).read_text(encoding="utf-8"))
    presets = {p["preset_id"]: p for p in data["presets"]}
    for pid, preset in presets.items():
        if preset.get("pan", "hold") not in PAN_MODES:
            raise CameraMoveError(f"Preset {pid!r} has unknown pan mode {preset.get('pan')!r}.")
    return presets


def _merc_x(lng: float) -> float:
    return math.radians(lng)


def _merc_y(lat: float) -> float:
    lat = max(min(lat, 85.0511), -85.0511)
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def _inv_merc_y(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


def monotone_curve(points: list[list[float]] | None, u: float) -> float:
    """Evaluate a monotone cubic (Fritsch-Carlson) through `[u, value]` points at `u`."""
    if not points:
        return min(max(u, 0.0), 1.0)
    pts = sorted((float(a), float(b)) for a, b in points)
    if u <= pts[0][0]:
        return pts[0][1]
    if u >= pts[-1][0]:
        return pts[-1][1]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = (
        [d[0]]
        + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)]
        + [d[-1]]
    )
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            t = 3 / math.sqrt(s)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    i = max(k for k in range(n - 1) if xs[k] <= u)
    h = xs[i + 1] - xs[i]
    t = (u - xs[i]) / h
    h00 = 2 * t**3 - 3 * t**2 + 1
    h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2
    h11 = t**3 - t**2
    return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]


def _path_point(path: list[list[float]], frac: float) -> tuple[float, float]:
    pts = [(_merc_x(p[0]), _merc_y(p[1])) for p in path]
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg)
    if total == 0:
        return path[0][0], path[0][1]
    target = min(max(frac, 0.0), 1.0) * total
    for i, length in enumerate(seg):
        if target <= length or i == len(seg) - 1:
            k = 0.0 if length == 0 else min(target / length, 1.0)
            x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k
            y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k
            return math.degrees(x), _inv_merc_y(y)
        target -= length
    return path[-1][0], path[-1][1]


def _state_at(
    preset: dict[str, Any], move: dict[str, Any], start: CameraState, u: float, t_s: float
) -> CameraState:
    zoom_delta = float(move.get("zoom_delta", preset.get("zoom_delta", 0.0)))
    if "zoom_to" in move:
        zoom_delta = float(move["zoom_to"]) - start.zoom
    bearing_delta = float(move.get("bearing_delta", preset.get("bearing_delta", 0.0)))
    if "bearing_to" in move:
        bearing_delta = float(move["bearing_to"]) - start.bearing
    zoom = start.zoom + zoom_delta * monotone_curve(preset.get("zoom_curve"), u)
    bearing = start.bearing + bearing_delta * monotone_curve(preset.get("bearing_curve"), u)
    pitch_delta = float(move.get("pitch_delta", preset.get("pitch_delta", 0.0)))
    pitch = start.pitch + pitch_delta * monotone_curve(preset.get("pitch_curve"), u)
    pan = move.get("pan", preset.get("pan", "hold"))
    lng, lat = start.lng, start.lat
    if pan == "drift":
        dx, dy = move.get("drift_px_per_s", preset.get("drift_px_per_s", [0.0, 0.0]))
        world_px = TILE_SIZE * 2**zoom
        br = math.radians(bearing)
        mx = (dx * math.cos(br) - dy * math.sin(br)) * t_s
        my = (dx * math.sin(br) + dy * math.cos(br)) * t_s
        lng = start.lng + math.degrees(mx / world_px * 2 * math.pi)
        lat = _inv_merc_y(_merc_y(start.lat) - my / world_px * 2 * math.pi)
    elif pan == "to_target":
        target = move.get("target")
        if not target:
            raise CameraMoveError(
                f"Move using {preset['preset_id']!r} needs a `target` [lng, lat]."
            )
        k = monotone_curve(move.get("pan_curve", preset.get("pan_curve")), u)
        lng = start.lng + (float(target[0]) - start.lng) * k
        lat = _inv_merc_y(_merc_y(start.lat) + (_merc_y(float(target[1])) - _merc_y(start.lat)) * k)
    elif pan == "path":
        path = move.get("path")
        if not path or len(path) < 2:
            raise CameraMoveError(
                f"Move using {preset['preset_id']!r} needs a `path` of 2+ points."
            )
        k = monotone_curve(move.get("pan_curve", preset.get("pan_curve")), u)
        lng, lat = _path_point([[start.lng, start.lat], *path], k)
    return CameraState(lng=lng, lat=lat, zoom=zoom, bearing=bearing, pitch=pitch)


def expand_move_plan(
    plan: dict[str, Any], *, fps: float = 30.0, presets: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Expand a move plan into one camera sample per frame.

    Plan shape: `{"start": {"center": [lng, lat], "zoom": z, "bearing": b, "pitch": p},
    "moves": [{"preset": id, "duration_s": s, ...overrides} | {"cut": {...state, "at_s": t}}]}`.
    A `cut` replaces the camera state instantly; its optional `at_s` advances the timeline
    cursor first, leaving a gap for footage between map shots.
    Returns `[{"frame", "t", "center", "zoom", "bearing", "pitch"}]`.
    """
    library = presets if presets is not None else load_camera_presets()
    state = _parse_state(plan.get("start"), None)
    t0 = float(plan.get("start_s", 0.0))
    samples: list[dict[str, Any]] = []

    def emit(frame: int, cam: CameraState) -> None:
        sample = {
            "frame": frame,
            "t": round(frame / fps, 4),
            "center": [round(cam.lng, 5), round(cam.lat, 5)],
            "zoom": round(cam.zoom, 4),
            "bearing": round(cam.bearing, 3),
            "pitch": round(cam.pitch, 3),
        }
        if samples and samples[-1]["frame"] == frame:
            samples[-1] = sample
        else:
            samples.append(sample)

    cursor = t0
    emit(round(cursor * fps), state)
    for move in plan.get("moves", []):
        if "cut" in move:
            state = _parse_state(move["cut"], state)
            if "at_s" in move["cut"]:
                cursor = max(cursor, float(move["cut"]["at_s"]))
            emit(round(cursor * fps), state)
            continue
        pid = move.get("preset")
        if pid not in library:
            raise CameraMoveError(f"Unknown camera preset {pid!r}. Known: {sorted(library)}")
        preset = library[pid]
        duration = float(move.get("duration_s", preset.get("default_duration_s", 1.0)))
        if duration <= 0:
            raise CameraMoveError(f"Move {pid!r} needs a positive duration.")
        f0, f1 = round(cursor * fps), round((cursor + duration) * fps)
        for frame in range(f0 + 1, f1 + 1):
            u = (frame - f0) / max(f1 - f0, 1)
            emit(frame, _state_at(preset, move, state, u, u * duration))
        state = _state_at(preset, move, state, 1.0, duration)
        cursor += duration
    return samples


def _parse_state(raw: dict[str, Any] | None, base: CameraState | None) -> CameraState:
    if not raw:
        if base is None:
            raise CameraMoveError("Move plan needs a `start` camera state.")
        return base
    center = raw.get("center") or ([base.lng, base.lat] if base else None)
    if center is None or "zoom" not in raw and base is None:
        raise CameraMoveError("Camera state needs `center` and `zoom`.")
    seed = base or CameraState(lng=0.0, lat=0.0, zoom=0.0)
    return replace(
        seed,
        lng=float(center[0]),
        lat=float(center[1]),
        zoom=float(raw.get("zoom", seed.zoom)),
        bearing=float(raw.get("bearing", seed.bearing)),
        pitch=float(raw.get("pitch", seed.pitch)),
    )


def to_baker_keyframes(
    samples: list[dict[str, Any]], *, frame_offset: int = 0
) -> list[dict[str, Any]]:
    """Format samples for `bake_vertical_basemap.mjs` `KEYFRAMES_JSON` (linear between frames)."""
    return [
        {
            "frame": s["frame"] - frame_offset,
            "center": s["center"],
            "zoom": s["zoom"],
            "bearing": s["bearing"],
            "pitch": s["pitch"],
            "ease": "linear",
        }
        for s in samples
    ]


def to_scene_keys(samples: list[dict[str, Any]]) -> list[list[float]]:
    """Format samples as compact `[t, lng, lat, zoom, bearing]` rows for custom scene players."""
    return [[s["t"], s["center"][0], s["center"][1], s["zoom"], s["bearing"]] for s in samples]
