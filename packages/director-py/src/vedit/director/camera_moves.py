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
PAN_MODES = {"hold", "drift", "to_target", "path", "fly_to"}


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


def _van_wijk_fly_to(
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    u: float,
    rho: float = 1.42,
) -> tuple[float, float, float]:
    """Evaluate Van Wijk & Nuij (2003) optimal smooth zoom-pan path in Web Mercator space."""
    w0 = 2.0 ** (-z0)
    w1 = 2.0 ** (-z1)
    # Convert Mercator radians (full world = 2*pi) into normalized world units matching w = 2^-z.
    dist = math.hypot(x1 - x0, y1 - y0) / (2.0 * math.pi)
    if dist < 1e-9:
        zoom = z0 + (z1 - z0) * u
        return x0, y0, zoom

    rho2 = rho * rho
    rho4 = rho2 * rho2

    def _r(idx: int) -> float:
        sign = 1.0 if idx == 0 else -1.0
        w_i = w0 if idx == 0 else w1
        num = (w1 * w1 - w0 * w0) + sign * rho4 * dist * dist
        den = 2.0 * w_i * rho2 * dist
        b = num / max(den, 1e-12)
        return math.log(math.sqrt(b * b + 1.0) - b)

    r0 = _r(0)
    r1 = _r(1)
    s_tot = (r1 - r0) / rho
    if abs(s_tot) < 1e-7:
        return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u

    s = u * s_tot
    cosh_r0 = math.cosh(r0)
    w_s = w0 * cosh_r0 / math.cosh(rho * s + r0)
    u_s = (w0 / rho2) * (cosh_r0 * math.tanh(rho * s + r0) - math.sinh(r0))
    frac = min(max(u_s / dist, 0.0), 1.0)
    x = x0 + (x1 - x0) * frac
    y = y0 + (y1 - y0) * frac
    zoom = -math.log2(max(w_s, 1e-12))
    return x, y, zoom


def _scale_coupled_pan_frac(z0: float, z1: float, z_cur: float, fallback_k: float) -> float:
    """Weight pan fraction by inverse map scale (2^-z) during deep zoom dives."""
    if abs(z1 - z0) <= 0.25:
        return fallback_k
    s0 = 2.0 ** (-z0)
    s1 = 2.0 ** (-z1)
    sc = 2.0 ** (-z_cur)
    denom = s0 - s1
    if abs(denom) < 1e-12:
        return fallback_k
    return min(max((s0 - sc) / denom, 0.0), 1.0)


def _state_at(
    preset: dict[str, Any], move: dict[str, Any], start: CameraState, u: float, t_s: float
) -> CameraState:
    zoom_delta = float(move.get("zoom_delta", preset.get("zoom_delta", 0.0)))
    if "zoom_to" in move:
        zoom_delta = float(move["zoom_to"]) - start.zoom
    bearing_delta = float(move.get("bearing_delta", preset.get("bearing_delta", 0.0)))
    if "bearing_to" in move:
        bearing_delta = float(move["bearing_to"]) - start.bearing
    zoom_u = monotone_curve(move.get("zoom_curve", preset.get("zoom_curve")), u)
    zoom = start.zoom + zoom_delta * zoom_u
    bearing = start.bearing + bearing_delta * monotone_curve(
        move.get("bearing_curve", preset.get("bearing_curve")), u
    )
    pitch_delta = float(move.get("pitch_delta", preset.get("pitch_delta", 0.0)))
    if "pitch_to" in move:
        pitch_delta = float(move["pitch_to"]) - start.pitch
    pitch = start.pitch + pitch_delta * monotone_curve(
        move.get("pitch_curve", preset.get("pitch_curve")), u
    )
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
    elif pan == "fly_to":
        target = move.get("target")
        if not target:
            raise CameraMoveError(
                f"Move using {preset['preset_id']!r} needs a `target` [lng, lat]."
            )
        rho = float(move.get("rho", preset.get("rho", 1.42)))
        eased_u = monotone_curve(move.get("pan_curve", preset.get("pan_curve")), u)
        mx, my, fly_z = _van_wijk_fly_to(
            _merc_x(start.lng),
            _merc_y(start.lat),
            start.zoom,
            _merc_x(float(target[0])),
            _merc_y(float(target[1])),
            start.zoom + zoom_delta,
            eased_u,
            rho=rho,
        )
        lng = math.degrees(mx)
        lat = _inv_merc_y(my)
        zoom = fly_z
    elif pan == "to_target":
        target = move.get("target")
        if not target:
            raise CameraMoveError(
                f"Move using {preset['preset_id']!r} needs a `target` [lng, lat]."
            )
        k = monotone_curve(move.get("pan_curve", preset.get("pan_curve")), u)
        scale_coupled = bool(move.get("scale_coupled", preset.get("scale_coupled", True)))
        if scale_coupled and abs(zoom_delta) > 0.25:
            k = _scale_coupled_pan_frac(start.zoom, start.zoom + zoom_delta, zoom, k)
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

    # Optional subtle continuous ambient drift so holds remain visually alive.
    ambient = move.get("ambient_drift") or preset.get("ambient_drift")
    if isinstance(ambient, dict):
        zoom += float(ambient.get("zoom_per_s", 0.0)) * t_s
        bearing += float(ambient.get("bearing_per_s", 0.0)) * t_s

    # Optional damped sinusoidal impulse shake for impact beats (stamps, slams).
    shake = move.get("shake") or preset.get("shake")
    if isinstance(shake, dict):
        start_u = float(shake.get("start_u", 0.0))
        decay_s = max(0.05, float(shake.get("decay_s", 0.32)))
        amp_px = float(shake.get("amplitude_px", 10.0))
        freq_hz = float(shake.get("freq_hz", 16.0))
        if u >= start_u and amp_px > 0:
            dt = max(0.0, t_s - start_u * max(t_s / max(u, 1e-6), 0.01))
            if dt <= decay_s * 1.6:
                env = math.exp(-3.2 * dt / decay_s)
                dx_px = math.sin(2.0 * math.pi * freq_hz * dt) * amp_px * env
                dy_px = math.cos(2.0 * math.pi * freq_hz * 0.87 * dt) * amp_px * 0.85 * env
                world_px = TILE_SIZE * 2**zoom
                lng += math.degrees(dx_px / world_px * 2.0 * math.pi)
                lat = _inv_merc_y(_merc_y(lat) - dy_px / world_px * 2.0 * math.pi)

    return CameraState(lng=lng, lat=lat, zoom=zoom, bearing=bearing, pitch=pitch)


def _apply_velocity_blending(
    samples: list[dict[str, Any]],
    cut_frames: set[int],
    blend_frames: int,
) -> None:
    """Apply C1-continuous smoothing across move boundaries (never across cuts)."""
    if blend_frames <= 0 or len(samples) < 5:
        return
    # Gaussian-weighted local smoothing kernel over continuous spans between cuts.
    spans: list[tuple[int, int]] = []
    start_idx = 0
    for idx in range(1, len(samples)):
        is_gap = samples[idx]["frame"] != samples[idx - 1]["frame"] + 1
        if samples[idx]["frame"] in cut_frames or is_gap:
            spans.append((start_idx, idx))
            start_idx = idx
    spans.append((start_idx, len(samples)))

    radius = min(blend_frames, 12)
    sigma = max(1.0, radius * 0.5)
    weights = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-radius, radius + 1)]

    for lo, hi in spans:
        if hi - lo < 5:
            continue
        orig = [
            (
                _merc_x(s["center"][0]),
                _merc_y(s["center"][1]),
                float(s["zoom"]),
                float(s["bearing"]),
                float(s["pitch"]),
            )
            for s in samples[lo:hi]
        ]
        n = len(orig)
        for i in range(1, n - 1):
            w_sum = 0.0
            ax = ay = az = ab = ap = 0.0
            for k in range(-radius, radius + 1):
                j = min(max(i + k, 0), n - 1)
                w = weights[k + radius]
                ax += orig[j][0] * w
                ay += orig[j][1] * w
                az += orig[j][2] * w
                ab += orig[j][3] * w
                ap += orig[j][4] * w
                w_sum += w
            s = samples[lo + i]
            s["center"] = [round(math.degrees(ax / w_sum), 5), round(_inv_merc_y(ay / w_sum), 5)]
            s["zoom"] = round(az / w_sum, 4)
            s["bearing"] = round(ab / w_sum, 3)
            s["pitch"] = round(ap / w_sum, 3)


def _annotate_motion_and_shutter(
    samples: list[dict[str, Any]],
    cut_frames: set[int],
    fps: float,
) -> None:
    """Attach per-frame camera velocities and optical shutter sub-sample recommendations."""
    for idx, cur in enumerate(samples):
        if idx == 0 or cur["frame"] in cut_frames or cur["frame"] != samples[idx - 1]["frame"] + 1:
            cur["zoom_vel"] = 0.0
            cur["bearing_vel"] = 0.0
            cur["shutter_samples"] = 1
            continue
        prev = samples[idx - 1]
        z_vel = abs(float(cur["zoom"]) - float(prev["zoom"])) * fps
        b_vel = abs(float(cur["bearing"]) - float(prev["bearing"])) * fps
        cur["zoom_vel"] = round(z_vel, 3)
        cur["bearing_vel"] = round(b_vel, 3)
        if z_vel >= 3.2 or b_vel >= 55.0:
            cur["shutter_samples"] = 5
        elif z_vel >= 1.5 or b_vel >= 25.0:
            cur["shutter_samples"] = 3
        else:
            cur["shutter_samples"] = 1


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
    cut_frames: set[int] = set()
    emit(round(cursor * fps), state)
    for move in plan.get("moves", []):
        if "cut" in move:
            state = _parse_state(move["cut"], state)
            if "at_s" in move["cut"]:
                cursor = max(cursor, float(move["cut"]["at_s"]))
            cut_f = round(cursor * fps)
            cut_frames.add(cut_f)
            emit(cut_f, state)
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

    blend_s = float(plan.get("blend_s", 0.0))
    if blend_s > 0.0:
        _apply_velocity_blending(samples, cut_frames, round(blend_s * fps))
    _annotate_motion_and_shutter(samples, cut_frames, fps)
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


# ---------------------------------------------------------------------------
# Measured camera tracks: smoothing and jitter measurement.
#
# A measured track (solved from reference frames, hand-placed, or exported from a
# scene player) is a sparse list of `[t, lng, lat, zoom, bearing]` rows. Frame-to-frame
# solver noise survives monotone interpolation as visible shake, so measured tracks are
# low-pass filtered in Mercator / zoom space before baking. Cuts split the track into
# independent spans; anchor keys (deliberate holds and story beats) are kept exactly.
# ---------------------------------------------------------------------------


class _Monotone:
    """Prebuilt monotone cubic (Fritsch-Carlson) interpolant over strictly increasing xs."""

    def __init__(self, xs: list[float], ys: list[float]) -> None:
        self.xs, self.ys = xs, ys
        n = len(xs)
        if n < 2:
            self.m = [0.0] * n
            return
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
                k = 3 / math.sqrt(s)
                m[i], m[i + 1] = k * a * d[i], k * b * d[i]
        self.m = m

    def __call__(self, x: float, hint: int = 0) -> tuple[float, int]:
        xs, ys, m = self.xs, self.ys, self.m
        if x <= xs[0] or len(xs) < 2:
            return ys[0], 0
        if x >= xs[-1]:
            return ys[-1], len(xs) - 2
        i = min(max(hint, 0), len(xs) - 2)
        while i > 0 and xs[i] > x:
            i -= 1
        while i < len(xs) - 2 and xs[i + 1] <= x:
            i += 1
        h = xs[i + 1] - xs[i]
        t = (x - xs[i]) / h
        h00 = 2 * t**3 - 3 * t**2 + 1
        h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2
        h11 = t**3 - t**2
        return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1], i


def _unwrap_keys(keys: list[list[float]]) -> list[list[float]]:
    rows = sorted(
        ([float(v) for v in k[:5]] + [0.0] * (5 - len(k[:5])) for k in keys), key=lambda r: r[0]
    )
    for i in range(1, len(rows)):
        while rows[i][1] - rows[i - 1][1] > 180:
            rows[i][1] -= 360
        while rows[i][1] - rows[i - 1][1] < -180:
            rows[i][1] += 360
    return rows


def _spans(times: list[float], cuts: list[float]) -> list[tuple[int, int]]:
    """Index ranges `[lo, hi)` of keys between consecutive cuts (a key at a cut opens a span)."""
    bounds = sorted(set(cuts))
    spans: list[tuple[int, int]] = []
    lo = 0
    for i in range(1, len(times)):
        if any(times[i - 1] < c <= times[i] for c in bounds):
            spans.append((lo, i))
            lo = i
    spans.append((lo, len(times)))
    return spans


def smooth_scene_keys(
    keys: list[list[float]],
    *,
    window_s: float = 0.6,
    cuts: list[float] | tuple[float, ...] = (),
    anchors: list[float] | tuple[float, ...] = (),
    anchor_tolerance_s: float = 1e-3,
    max_shift_px: float = 24.0,
    max_zoom_shift: float = 0.08,
) -> list[list[float]]:
    """Denoise a measured `[t, lng, lat, zoom, bearing]` track without re-directing it.

    Each key is replaced by a Gaussian-weighted average (sigma = `window_s / 2`) of the keys
    in its span, computed on Mercator x/y, zoom (already logarithmic in scale) and bearing.
    Span endpoints and keys within `anchor_tolerance_s` of an `anchors` time are kept exactly,
    so cut frames and deliberate story-beat framings do not drift. Each smoothed key may move
    at most `max_shift_px` output pixels (centre) and `max_zoom_shift` zoom levels from its
    measured value, so fast deliberate moves (snap zooms, whip pans) keep their timing while
    small solver noise is removed. Longitudes are unwrapped first and returned unwrapped
    (continuous across the antimeridian).
    """
    if window_s <= 0 or len(keys) < 3:
        return _unwrap_keys(keys)
    rows = _unwrap_keys(keys)
    times = [r[0] for r in rows]
    sigma = window_s / 2.0
    reach = 3.0 * sigma
    feats = [(_merc_x(r[1]), _merc_y(r[2]), r[3], r[4]) for r in rows]
    out = [list(r) for r in rows]
    for lo, hi in _spans(times, list(cuts)):
        for i in range(lo + 1, hi - 1):
            if any(abs(times[i] - a) <= anchor_tolerance_s for a in anchors):
                continue
            acc = [0.0, 0.0, 0.0, 0.0]
            w_sum = 0.0
            for j in range(lo, hi):
                dt = times[j] - times[i]
                if abs(dt) > reach:
                    continue
                w = math.exp(-0.5 * (dt / sigma) ** 2)
                for c in range(4):
                    acc[c] += feats[j][c] * w
                w_sum += w
            x, y, z, b = (v / w_sum for v in acc)
            ox, oy, oz, _ = feats[i]
            z = oz + max(-max_zoom_shift, min(max_zoom_shift, z - oz))
            scale = TILE_SIZE * 2.0**z / (2.0 * math.pi)
            shift = math.hypot(x - ox, y - oy) * scale
            if shift > max_shift_px:
                k = max_shift_px / shift
                x, y = ox + (x - ox) * k, oy + (y - oy) * k
            out[i][1:5] = [
                round(math.degrees(x), 5),
                round(_inv_merc_y(y), 5),
                round(z, 4),
                round(b, 3),
            ]
    return out


def camera_jitter_report(
    keys: list[list[float]],
    *,
    fps: float = 30.0,
    cuts: list[float] | tuple[float, ...] = (),
    pan_accel_px: float = 4.0,
    zoom_accel: float = 0.006,
    bearing_accel_deg: float = 0.6,
    shake_window_s: float = 0.6,
) -> dict[str, Any]:
    """Sample a `[t, lng, lat, zoom, bearing]` track at `fps` and measure per-frame shake.

    Pan acceleration is measured in output pixels per frame squared (world motion under the
    frame centre at the current zoom), zoom acceleration in zoom levels per frame squared and
    bearing acceleration in degrees per frame squared. Frames on either side of a cut are
    excluded. A frame is flagged when any acceleration exceeds its threshold. Shake shows up
    as direction flips rather than as large accelerations (a deliberate snap zoom is large but
    one-directional): `reversals` counts pan direction flips (per screen axis, ignoring motion
    under 0.05 px/frame) and `zoom_reversals` zoom direction flips (ignoring motion under
    0.0005 levels/frame) that follow the previous flip within `shake_window_s`.
    """
    rows = _unwrap_keys(keys)
    if len(rows) < 2:
        return {
            "frames": 0,
            "flagged_frames": 0,
            "flagged": [],
            "reversals": 0,
            "zoom_reversals": 0,
            "max_pan_accel_px": 0.0,
            "max_zoom_accel": 0.0,
            "max_bearing_accel_deg": 0.0,
        }
    times = [r[0] for r in rows]
    fx = _Monotone(times, [_merc_x(r[1]) for r in rows])
    fy = _Monotone(times, [_merc_y(r[2]) for r in rows])
    fz = _Monotone(times, [r[3] for r in rows])
    fb = _Monotone(times, [r[4] for r in rows])
    f0, f1 = math.ceil(times[0] * fps), math.floor(times[-1] * fps)
    cut_frames = {round(c * fps) for c in cuts}
    hint = 0
    samples: list[tuple[int, float, float, float, float]] = []
    for f in range(f0, f1 + 1):
        t = f / fps
        x, hint = fx(t, hint)
        y, _ = fy(t, hint)
        z, _ = fz(t, hint)
        b, _ = fb(t, hint)
        samples.append((f, x, y, z, b))

    def blocked(f: int) -> bool:
        return any(c - 1 <= f <= c + 1 for c in cut_frames)

    flagged: list[dict[str, Any]] = []
    reversals = zoom_reversals = 0
    last_sign: dict[str, int] = {}
    last_flip: dict[str, float] = {}

    def flip(axis: str, value: float, dead: float, t: float) -> bool:
        if abs(value) < dead:
            return False
        sign = 1 if value > 0 else -1
        prev = last_sign.get(axis)
        last_sign[axis] = sign
        if prev is None or prev == sign:
            return False
        recent = t - last_flip.get(axis, -1e9) <= shake_window_s
        last_flip[axis] = t
        return recent

    max_pan = max_zoom = max_bear = 0.0
    for k in range(2, len(samples)):
        f = samples[k][0]
        if blocked(f) or blocked(f - 1) or blocked(f - 2):
            continue
        a, b, c = samples[k - 2], samples[k - 1], samples[k]
        scale = TILE_SIZE * 2.0 ** b[3] / (2.0 * math.pi)
        vel_prev = ((b[1] - a[1]) * scale, (b[2] - a[2]) * scale)
        vel_cur = ((c[1] - b[1]) * scale, (c[2] - b[2]) * scale)
        pan = math.hypot(vel_cur[0] - vel_prev[0], vel_cur[1] - vel_prev[1])
        zac = abs(c[3] - 2 * b[3] + a[3])
        bac = abs(c[4] - 2 * b[4] + a[4])
        t = f / fps
        if flip("x", vel_cur[0], 0.05, t) or flip("y", vel_cur[1], 0.05, t):
            reversals += 1
        if flip("z", c[3] - b[3], 0.0005, t):
            zoom_reversals += 1
        max_pan, max_zoom, max_bear = max(max_pan, pan), max(max_zoom, zac), max(max_bear, bac)
        if pan > pan_accel_px or zac > zoom_accel or bac > bearing_accel_deg:
            flagged.append(
                {
                    "frame": f,
                    "t": round(f / fps, 3),
                    "pan_accel_px": round(pan, 2),
                    "zoom_accel": round(zac, 5),
                    "bearing_accel_deg": round(bac, 3),
                }
            )
    return {
        "frames": len(samples),
        "flagged_frames": len(flagged),
        "flagged": flagged,
        "reversals": reversals,
        "zoom_reversals": zoom_reversals,
        "max_pan_accel_px": round(max_pan, 2),
        "max_zoom_accel": round(max_zoom, 5),
        "max_bearing_accel_deg": round(max_bear, 3),
    }
