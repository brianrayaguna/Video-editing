"""Expand chained map camera presets into per-frame MapLibre camera keyframes.

A move plan starts from an explicit camera state and chains presets from
`tools/geo-assets/camera_presets.json`; every move begins where the previous one ended,
so a whole shot is described by a handful of preset names instead of hand-tuned keys.
`cut` entries replace the state instantly (hard cuts between shots).
"""

from __future__ import annotations

import functools
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
    dedup: list[tuple[float, float]] = []
    for px, py in pts:
        if dedup and abs(px - dedup[-1][0]) < 1e-12:
            dedup[-1] = (px, py)
        else:
            dedup.append((px, py))
    pts = dedup
    if len(pts) == 1 or u <= pts[0][0]:
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
    if dist < 1e-9 or rho <= 0.0:
        zoom = z0 + (z1 - z0) * u
        return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, zoom

    rho2 = rho * rho
    rho4 = rho2 * rho2

    def _r(idx: int) -> float:
        sign = 1.0 if idx == 0 else -1.0
        w_i = w0 if idx == 0 else w1
        num = (w1 * w1 - w0 * w0) + sign * rho4 * dist * dist
        den = 2.0 * w_i * rho2 * dist
        b = num / max(den, 1e-12)
        return -math.asinh(b)

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
        dedup_x: list[float] = []
        dedup_y: list[float] = []
        for x_val, y_val in zip(xs, ys, strict=True):
            if dedup_x and abs(x_val - dedup_x[-1]) < 1e-12:
                dedup_y[-1] = y_val
            else:
                dedup_x.append(x_val)
                dedup_y.append(y_val)
        self.xs, self.ys = dedup_x, dedup_y
        n = len(self.xs)
        if n < 2:
            self.m = [0.0] * n
            return
        d = [(self.ys[i + 1] - self.ys[i]) / (self.xs[i + 1] - self.xs[i]) for i in range(n - 1)]
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
    spans = _spans(times, list(cuts))
    cut_frames = {round(c * fps) for c in cuts}

    def blocked(f: int) -> bool:
        return any(c - 1 <= f <= c + 1 for c in cut_frames)

    flagged: list[dict[str, Any]] = []
    reversals = zoom_reversals = 0
    max_pan = max_zoom = max_bear = 0.0
    total_frames = 0
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

    for lo, hi in spans:
        sub = rows[lo:hi]
        if len(sub) < 2:
            continue
        sub_times = [r[0] for r in sub]
        fx = _Monotone(sub_times, [_merc_x(r[1]) for r in sub])
        fy = _Monotone(sub_times, [_merc_y(r[2]) for r in sub])
        fz = _Monotone(sub_times, [r[3] for r in sub])
        fb = _Monotone(sub_times, [r[4] for r in sub])
        f0, f1 = math.ceil(sub_times[0] * fps), math.floor(sub_times[-1] * fps)
        hint = 0
        samples: list[tuple[int, float, float, float, float]] = []
        for f in range(f0, f1 + 1):
            t = f / fps
            x, hint = fx(t, hint)
            y, _ = fy(t, hint)
            z, _ = fz(t, hint)
            b, _ = fb(t, hint)
            samples.append((f, x, y, z, b))
        total_frames += len(samples)

        last_sign.clear()
        last_flip.clear()

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
            max_pan = max(max_pan, pan)
            max_zoom = max(max_zoom, zac)
            max_bear = max(max_bear, bac)
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
        "frames": total_frames,
        "flagged_frames": len(flagged),
        "flagged": flagged,
        "reversals": reversals,
        "zoom_reversals": zoom_reversals,
        "max_pan_accel_px": round(max_pan, 2),
        "max_zoom_accel": round(max_zoom, 5),
        "max_bearing_accel_deg": round(max_bear, 3),
    }


def _mercator_norm(lng: float, lat: float) -> tuple[float, float]:
    """Convert WGS84 (lng, lat) to normalized Web Mercator [0..1, 0..1]."""
    clamped_lat = max(-85.051129, min(85.051129, lat))
    x = (lng + 180.0) / 360.0
    sin_lat = math.sin(math.radians(clamped_lat))
    y = 0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)
    return (x, y)


def _inv_mercator_norm(x: float, y: float) -> tuple[float, float]:
    """Convert normalized Web Mercator [0..1, 0..1] back to WGS84 (lng, lat)."""
    lng = x * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * max(1e-6, min(1.0 - 1e-6, y))
    lat = math.degrees(math.atan(0.5 * (math.exp(n) - math.exp(-n))))
    return (lng, lat)


# Velocity shape per curve name: Beta(a, b) profile u^(a-1) (1-u)^(b-1). Both exponents
# exceed 2, so velocity and acceleration are zero at both ends of a move (C2 rest points),
# and the velocity peak sits at (a-1)/(a+b-2) of the move.
_PROFILE_SHAPES: dict[str, tuple[float, float]] = {
    "glide": (2.6, 2.6),
    "snap_dive": (2.2, 3.4),
    "whip_snap": (3.2, 3.2),
    "hyperbolic_fly": (2.6, 3.0),
    "orbit_cruise": (2.2, 2.2),
}
_PROFILE_STEPS = 512


@functools.lru_cache(maxsize=32)
def _profile_cdf(a: float, b: float) -> tuple[float, ...]:
    """Normalised cumulative Beta(a, b) velocity profile on a uniform grid (midpoint rule)."""
    acc = [0.0]
    total = 0.0
    for i in range(_PROFILE_STEPS):
        u = (i + 0.5) / _PROFILE_STEPS
        total += u ** (a - 1.0) * (1.0 - u) ** (b - 1.0)
        acc.append(total)
    return tuple(v / total for v in acc)


def eased_progress(u: float, curve: str) -> float:
    """Map linear move time `u` in [0, 1] to eased progress for a named camera curve.

    Monotone, 0 -> 0 and 1 -> 1, with zero slope and zero curvature at both ends. Unknown
    names and `auto` use the symmetric `glide` profile.
    """
    a, b = _PROFILE_SHAPES.get(curve, _PROFILE_SHAPES["glide"])
    cdf = _profile_cdf(a, b)
    x = max(0.0, min(1.0, u)) * _PROFILE_STEPS
    i = min(_PROFILE_STEPS - 1, int(x))
    return cdf[i] + (cdf[i + 1] - cdf[i]) * (x - i)


def _monotone_tangents(times: list[float], values: list[float]) -> list[float]:
    """Finite-difference Hermite tangents limited so the curve never overshoots its keys."""
    n = len(values)
    slopes = [
        (values[i + 1] - values[i]) / max(1e-6, times[i + 1] - times[i]) for i in range(n - 1)
    ]
    tangents = [0.0] * n
    tangents[0] = slopes[0]
    tangents[-1] = slopes[-1]
    for i in range(1, n - 1):
        s0, s1 = slopes[i - 1], slopes[i]
        tangents[i] = 0.0 if s0 * s1 <= 0.0 else 0.5 * (s0 + s1)
    for i, s in enumerate(slopes):
        if s == 0.0:
            tangents[i] = tangents[i + 1] = 0.0
            continue
        alpha, beta = tangents[i] / s, tangents[i + 1] / s
        mag = math.hypot(alpha, beta)
        if mag > 3.0:
            tangents[i] = 3.0 * alpha / mag * s
            tangents[i + 1] = 3.0 * beta / mag * s
    return tangents


def _hermite(times: list[float], values: list[float], tangents: list[float], tau: float) -> float:
    """Evaluate a non-uniform cubic Hermite spline through `(times, values)` at `tau`."""
    j = 0
    while j < len(times) - 2 and tau > times[j + 1]:
        j += 1
    h = times[j + 1] - times[j]
    if h <= 1e-9:
        return values[j + 1]
    x = max(0.0, min(1.0, (tau - times[j]) / h))
    x2, x3 = x * x, x * x * x
    return (
        (2.0 * x3 - 3.0 * x2 + 1.0) * values[j]
        + (x3 - 2.0 * x2 + x) * h * tangents[j]
        + (-2.0 * x3 + 3.0 * x2) * values[j + 1]
        + (x3 - x2) * h * tangents[j + 1]
    )


def _zero_phase_smooth(values: list[float], sigma_frames: float) -> list[float]:
    """Zero-phase Gaussian smoothing preserving exact endpoints (C2 stabilized-rig feel)."""
    n = len(values)
    if n < 5 or sigma_frames <= 0.25:
        return list(values)
    radius = max(1, int(math.ceil(sigma_frames * 2.5)))
    weights = [math.exp(-0.5 * (k / sigma_frames) ** 2) for k in range(-radius, radius + 1)]
    w_sum = sum(weights)
    weights = [w / w_sum for w in weights]
    out = [0.0] * n
    for i in range(n):
        acc = 0.0
        for k, w in zip(range(-radius, radius + 1), weights, strict=True):
            idx = max(0, min(n - 1, i + k))
            acc += values[idx] * w
        out[i] = acc
    out[0] = values[0]
    out[-1] = values[-1]
    return out


def build_cinema_camera_track(
    keyframes: list[list[float]] | list[dict[str, Any]],
    duration_s: float,
    fps: float = 30.0,
    *,
    smooth_s: float = 0.0,
    shutter_windows: list[list[float]] | None = None,
    auto_shutter: bool = False,
    micro_drift: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a C2-continuous 3D cinema camera track from declarative waypoints.

    Each keyframe may be `[t_s, lng, lat, zoom, bearing, pitch, roll]` or a dict with
    `t`, `center`, `zoom`, `bearing`, `pitch`, `roll`, `curve` (`glide`, `snap_dive`,
    `whip_snap`, `orbit_cruise`, `hyperbolic_fly`, `auto`), `rho`, `through`, and optional
    `orbit_target` / `orbit_radius_deg`.

    Every keyframe is a rest point (zero velocity and acceleration) unless it sets
    `"through": true`; the first and last keyframes always rest. Each move between rest
    points follows the velocity profile of its curve name (taken from the arriving key,
    else the departing key). A run of `through` keyframes forms one eased multi-waypoint
    move: eased run time is mapped back to the authored key times and every channel is
    evaluated on a monotone cubic Hermite spline, so the camera keeps moving through them.
    Long rest-to-rest hops (`hyperbolic_fly`, or `auto` beyond ~0.35 viewport widths) follow
    the van Wijk & Nuij (2003) zoom-pan path; other moves couple pan to the zoom scale.
    Optional zero-phase smoothing, organic micro-drift and an adaptive optical shutter
    (`ceil(v_px / 2.5)` sub-frames, 1-16) are applied on top.
    """
    if not keyframes:
        return []

    parsed: list[dict[str, Any]] = []
    for row in keyframes:
        if isinstance(row, dict):
            t_k = float(row.get("t", row.get("t_s", 0.0)))
            ctr = row.get("center", [row.get("lng", 0.0), row.get("lat", 0.0)])
            lng_k, lat_k = float(ctr[0]), float(ctr[1])
            z_k = float(row.get("zoom", 2.0))
            b_k = float(row.get("bearing", 0.0))
            p_k = float(row.get("pitch", 0.0))
            r_k = float(row.get("roll", 0.0))
            curve_k = str(row.get("curve", "auto"))
            rho_k = float(row.get("rho", 1.42))
            orbit_t = row.get("orbit_target")
            orbit_r = float(row.get("orbit_radius_deg", 0.0))
            through_k = bool(row.get("through", False))
        else:
            t_k = float(row[0])
            lng_k, lat_k = float(row[1]), float(row[2])
            z_k = float(row[3])
            b_k = float(row[4]) if len(row) > 4 else 0.0
            p_k = float(row[5]) if len(row) > 5 else 0.0
            r_k = float(row[6]) if len(row) > 6 else 0.0
            curve_k = "auto"
            rho_k = 1.42
            orbit_t = None
            orbit_r = 0.0
            through_k = False
        mx, my = _mercator_norm(lng_k, lat_k)
        parsed.append(
            {
                "t": t_k,
                "lng": lng_k,
                "lat": lat_k,
                "mx": mx,
                "my": my,
                "z": z_k,
                "b": b_k,
                "p": p_k,
                "r": r_k,
                "curve": curve_k,
                "rho": rho_k,
                "orbit_target": orbit_t,
                "orbit_radius_deg": orbit_r,
                "through": through_k,
            }
        )
    parsed.sort(key=lambda item: item["t"])
    for idx in range(1, len(parsed)):
        lng_cur = parsed[idx]["lng"]
        lng_prev = parsed[idx - 1]["lng"]
        while lng_cur - lng_prev > 180.0:
            lng_cur -= 360.0
        while lng_cur - lng_prev < -180.0:
            lng_cur += 360.0
        if lng_cur != parsed[idx]["lng"]:
            parsed[idx]["lng"] = lng_cur
            parsed[idx]["mx"], parsed[idx]["my"] = _mercator_norm(lng_cur, parsed[idx]["lat"])

    total = max(1, round(duration_s * fps))
    raw_mx: list[float] = []
    raw_my: list[float] = []
    raw_z: list[float] = []
    raw_b: list[float] = []
    raw_p: list[float] = []
    raw_r: list[float] = []

    m = len(parsed)
    rest_idx = [i for i, k in enumerate(parsed) if i in (0, m - 1) or not k["through"]]
    runs = [
        (r0, r1)
        for r0, r1 in zip(rest_idx, rest_idx[1:], strict=False)
        if parsed[r1]["t"] - parsed[r0]["t"] > 1e-9
    ]
    channels = ("mx", "my", "z", "b", "p", "r")
    run_splines: dict[tuple[int, int], tuple[list[float], dict[str, tuple[list, list]]]] = {}
    for r0, r1 in runs:
        if r1 - r0 > 1:
            keys = parsed[r0 : r1 + 1]
            times = [k["t"] for k in keys]
            splines = {}
            for ch in channels:
                vals = [k[ch] for k in keys]
                splines[ch] = (vals, _monotone_tangents(times, vals))
            run_splines[(r0, r1)] = (times, splines)

    for f in range(total):
        t = f / fps
        orbit_t = None
        orbit_r = 0.0
        run = None
        if m > 1 and parsed[0]["t"] < t < parsed[-1]["t"]:
            for r0, r1 in runs:
                if parsed[r0]["t"] <= t < parsed[r1]["t"]:
                    run = (r0, r1)
                    break
        if run is None:
            k = parsed[0] if (m == 1 or t <= parsed[0]["t"]) else parsed[-1]
            mx, my, z, b, p, r = k["mx"], k["my"], k["z"], k["b"], k["p"], k["r"]
            orbit_t = k["orbit_target"]
            orbit_r = k["orbit_radius_deg"]
        else:
            r0, r1 = run
            k1, k2 = parsed[r0], parsed[r1]
            seg_curve = k2["curve"] if k2["curve"] != "auto" else k1["curve"]
            span = k2["t"] - k1["t"]
            u = eased_progress((t - k1["t"]) / span, seg_curve)
            if run in run_splines:
                times, splines = run_splines[run]
                tau = k1["t"] + u * span
                mx, my, z, b, p, r = (
                    _hermite(times, splines[ch][0], splines[ch][1], tau) for ch in channels
                )
                j = r0
                while j < r1 - 1 and tau > parsed[j + 1]["t"]:
                    j += 1
                k1, k2 = parsed[j], parsed[j + 1]
            else:
                b = k1["b"] + (k2["b"] - k1["b"]) * u
                p = k1["p"] + (k2["p"] - k1["p"]) * u
                r = k1["r"] + (k2["r"] - k1["r"]) * u

                dist_norm = math.hypot(k2["mx"] - k1["mx"], k2["my"] - k1["my"])
                max_w = max(2.0 ** (-k1["z"]), 2.0 ** (-k2["z"]))
                use_hyperbolic = seg_curve == "hyperbolic_fly" or (
                    seg_curve == "auto" and dist_norm > 0.35 * max_w and dist_norm > 1e-4
                )
                if use_hyperbolic:
                    # van Wijk & Nuij (2003) zoom-pan path in Web Mercator radians
                    x0_rad, y0_rad = _merc_x(k1["lng"]), _merc_y(k1["lat"])
                    x1_rad, y1_rad = _merc_x(k2["lng"]), _merc_y(k2["lat"])
                    xr, yr, z = _van_wijk_fly_to(
                        x0_rad, y0_rad, k1["z"], x1_rad, y1_rad, k2["z"], u, rho=k2["rho"]
                    )
                    mx, my = _mercator_norm(math.degrees(xr), _inv_merc_y(yr))
                else:
                    z = k1["z"] + (k2["z"] - k1["z"]) * u
                    if abs(k2["z"] - k1["z"]) > 0.25:
                        # Couple pan to the zoom scale so the target stays put on screen.
                        s0 = 2.0 ** (-k1["z"])
                        s1 = 2.0 ** (-k2["z"])
                        sc = 2.0 ** (-z)
                        u_pan = max(0.0, min(1.0, (sc - s0) / (s1 - s0)))
                    else:
                        u_pan = u
                    mx = k1["mx"] + (k2["mx"] - k1["mx"]) * u_pan
                    my = k1["my"] + (k2["my"] - k1["my"]) * u_pan

            orbit_t = k2["orbit_target"] or k1["orbit_target"]
            orbit_r = max(k1["orbit_radius_deg"], k2["orbit_radius_deg"])

        # Optional circular orbit trucking offset around an explicit landmark
        if orbit_t and orbit_r > 0.0:
            ang = math.radians(b)
            olng = float(orbit_t[0]) + math.sin(ang) * orbit_r
            olat = float(orbit_t[1]) + math.cos(ang) * orbit_r * 0.65
            mx, my = _mercator_norm(olng, olat)

        raw_mx.append(mx)
        raw_my.append(my)
        raw_z.append(z)
        raw_b.append(b)
        raw_p.append(p)
        raw_r.append(r)

    sigma = smooth_s * fps
    sm_mx = _zero_phase_smooth(raw_mx, sigma)
    sm_my = _zero_phase_smooth(raw_my, sigma)
    sm_z = _zero_phase_smooth(raw_z, sigma)
    sm_b = _zero_phase_smooth(raw_b, sigma * 1.15)
    sm_p = _zero_phase_smooth(raw_p, sigma * 1.15)
    sm_r = _zero_phase_smooth(raw_r, sigma * 1.2)

    # Optional organic stabilized-rig micro-drift (tapered to 0 at endpoints)
    drift_cfg = (
        micro_drift if isinstance(micro_drift, dict) and micro_drift.get("enabled") else None
    )
    if drift_cfg and total > 6:
        freq = float(drift_cfg.get("freq_hz", 0.22))
        amp_b = float(drift_cfg.get("amp_bearing", 0.55))
        amp_p = float(drift_cfg.get("amp_pitch", 0.35))
        amp_r = float(drift_cfg.get("amp_roll", 0.35))
        amp_pan_px = float(drift_cfg.get("amp_pan_px", 4.5))
        for f in range(total):
            t = f / fps
            env = math.sin(math.pi * (f / max(1, total - 1))) ** 0.5
            sm_b[f] += env * amp_b * math.sin(2.0 * math.pi * freq * t + 0.4)
            sm_p[f] += env * amp_p * math.sin(2.0 * math.pi * freq * 0.73 * t + 1.7)
            sm_r[f] += env * amp_r * math.cos(2.0 * math.pi * freq * 0.58 * t + 0.9)
            w_px = TILE_SIZE * (2.0 ** sm_z[f])
            pan_step = env * (amp_pan_px / max(w_px, 1.0))
            sm_mx[f] += pan_step * math.sin(2.0 * math.pi * freq * 0.65 * t)
            sm_my[f] += pan_step * math.cos(2.0 * math.pi * freq * 0.51 * t)

    samples: list[dict[str, Any]] = []
    for f in range(total):
        t = f / fps
        lng, lat = _inv_mercator_norm(sm_mx[f], sm_my[f])
        shutter = 1
        if auto_shutter and f > 0:
            world_px = TILE_SIZE * (2.0 ** sm_z[f])
            d_pan_px = math.hypot(sm_mx[f] - sm_mx[f - 1], sm_my[f] - sm_my[f - 1]) * world_px
            d_zoom_px = abs(sm_z[f] - sm_z[f - 1]) * 380.0
            d_rot_px = abs(sm_b[f] - sm_b[f - 1]) * 8.0
            v_px = d_pan_px + d_zoom_px + d_rot_px
            shutter = max(1, min(16, math.ceil(v_px / 2.5 - 1e-6)))
        for sw in shutter_windows or []:
            if sw[0] <= t <= sw[1]:
                shutter = int(sw[2])
                break
        samples.append(
            {
                "frame": f,
                "t": round(t, 4),
                "center": [round(lng, 5), round(lat, 5)],
                "zoom": round(sm_z[f], 4),
                "bearing": round(sm_b[f], 3),
                "pitch": round(max(0.0, min(72.0, sm_p[f])), 2),
                "roll": round(max(-12.0, min(12.0, sm_r[f])), 3),
                "shutter_samples": shutter,
            }
        )
    return samples


def _unpack_camera_row(
    row: list[float] | dict[str, Any],
) -> tuple[float, float, float, float, float, float, float]:
    if isinstance(row, dict):
        t_abs = float(row.get("t", row.get("t_s", 0.0)))
        center = row.get("center") or [row.get("lng", 0.0), row.get("lat", 0.0)]
        return (
            t_abs,
            float(center[0]),
            float(center[1]),
            float(row.get("zoom", 2.0)),
            float(row.get("bearing", 0.0)),
            float(row.get("pitch", 0.0)),
            float(row.get("roll", 0.0)),
        )
    bearing = float(row[4]) if len(row) > 4 else 0.0
    pitch = float(row[5]) if len(row) > 5 else 0.0
    roll = float(row[6]) if len(row) > 6 else 0.0
    return (float(row[0]), float(row[1]), float(row[2]), float(row[3]), bearing, pitch, roll)


def project_world_anchor_to_track(
    camera_keys: list[list[float]] | list[dict[str, Any]],
    lng: float,
    lat: float,
    width: int,
    height: int,
    *,
    start_s: float,
    duration_s: float,
    reference_zoom: float | None = None,
    scale_with_zoom: bool = True,
    scale_coupling: float = 1.0,
    space: str = "world_billboard",
    tile_size: float = 512.0,
) -> list[dict[str, float]]:
    """Project a geographic [lng, lat] anchor through 3D camera track rows.

    Accepts `[t, lng, lat, zoom, bearing, pitch, roll]` lists or camera dicts exported
    by `render_map_scene.mjs`. Applies 3D perspective foreshortening along camera pitch
    and roll, returning `track_keyframes` dicts relative to `start_s`.
    """
    end_s = start_s + duration_s
    ax, ay = _mercator_norm(lng, lat)
    unpacked = [_unpack_camera_row(row) for row in camera_keys]
    window = [r for r in unpacked if start_s - 0.05 <= r[0] <= end_s + 0.05]
    if not window:
        return []
    ref_z = reference_zoom if reference_zoom is not None else window[0][3]
    focal_px = 1.5 * max(height, 1)  # Matches MapLibre default 36.87 deg vertical FOV
    out: list[dict[str, float]] = []
    for t_abs, c_lng, c_lat, zoom, bearing, pitch, roll in window:
        cx, cy = _mercator_norm(c_lng, c_lat)
        world_px = tile_size * (2.0**zoom)
        dx_norm = ((ax - cx + 0.5) % 1.0) - 0.5
        dx_px = dx_norm * world_px
        dy_px = (ay - cy) * world_px
        rad = math.radians(-bearing)
        cos_b, sin_b = math.cos(rad), math.sin(rad)
        rx = dx_px * cos_b - dy_px * sin_b
        ry = dx_px * sin_b + dy_px * cos_b

        # Apply 3D pinhole perspective foreshortening along camera pitch
        pitch_rad = math.radians(max(0.0, min(72.0, pitch)))
        cos_p, sin_p = math.cos(pitch_rad), math.sin(pitch_rad)
        raw_depth = focal_px - ry * sin_p
        behind_camera = raw_depth <= 0.1 * focal_px
        depth = max(0.2 * focal_px, raw_depth)
        persp = focal_px / depth
        px = rx * persp
        py = ry * cos_p * persp

        # Apply optical Z-axis roll + overscan matching render_map_scene.mjs
        overscan = 1.0
        if abs(roll) > 1e-4:
            rr = math.radians(roll)
            cr, sr = math.cos(rr), math.sin(rr)
            aspect = max(width / max(height, 1), height / max(width, 1))
            overscan = abs(cr) + abs(sr) * aspect
            px, py = (px * cr - py * sr) * overscan, (px * sr + py * cr) * overscan

        x_pct = round(50.0 + (px / max(width, 1)) * 100.0, 2)
        y_pct = round(50.0 + (py / max(height, 1)) * 100.0, 2)
        raw_scale = (
            (2.0 ** ((zoom - ref_z) * scale_coupling)) * persp * overscan
            if scale_with_zoom
            else overscan
        )
        scale = max(0.05, min(8.0, round(raw_scale, 4)))
        kf: dict[str, float] = {
            "t_s": round(max(0.0, t_abs - start_s), 3),
            "x_pct": x_pct,
            "y_pct": y_pct,
            "scale": scale,
            "rotation_deg": round((-bearing if space == "map_plane" else 0.0) + roll, 2),
        }
        if behind_camera:
            kf["opacity"] = 0.0
        if space == "map_plane" and pitch > 0.1:
            kf["rotateX_deg"] = round(pitch, 2)
            kf["perspective_px"] = round(focal_px, 1)
        out.append(kf)
    return out
