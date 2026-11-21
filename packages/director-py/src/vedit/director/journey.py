"""Compile a route-driven storyboard into head, camera, route-width and callout keys.

A journey storyboard binds named path markers to spoken place names (`beat.head`) and camera
regimes to beats (`beat.camera.regime`). This module turns that into the per-scene data a map
player consumes, so a journey film needs no hand-written timing code:

- `head_keys`: `[t, path_index]` — where the drawn route tip is at each time.
- `camera_keys`: `[t, lng, lat, zoom, bearing]` — regime moves that start before the spoken
  name, then denoised with `camera_moves.smooth_scene_keys`.
- `route_width_keys`: `[t, px]` — screen-constant stroke eased with the camera regime.
- callout positions resolved on the output canvas, trailing the head (see `place_callout`).
"""

from __future__ import annotations

import math
from typing import Any

from vedit.director.camera_moves import TILE_SIZE, smooth_scene_keys

FRAME = (1080.0, 1920.0)


def _merc(lng: float, lat: float) -> tuple[float, float]:
    lat = max(min(lat, 85.0511), -85.0511)
    return math.radians(lng), math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def project(
    lng: float, lat: float, cam: list[float], frame: tuple[float, float] = FRAME
) -> tuple[float, float]:
    """Project a point to canvas pixels for camera `[t, lng, lat, zoom, bearing]` (Web Mercator)."""
    _, clng, clat, zoom, bearing = cam[:5]
    scale = TILE_SIZE * 2.0**zoom / (2.0 * math.pi)
    px, py = _merc(lng, lat)
    cx, cy = _merc(clng, clat)
    dx = (px - cx) * scale
    dy = -(py - cy) * scale
    b = math.radians(-bearing)
    rx = dx * math.cos(b) - dy * math.sin(b)
    ry = dx * math.sin(b) + dy * math.cos(b)
    return frame[0] / 2 + rx, frame[1] / 2 + ry


def head_keys(storyboard: dict[str, Any]) -> list[list[float]]:
    """Route tip schedule: the head reaches each beat's marker at `head.arrive_s`.

    `draw` beats add an arrival key; `hold` and `pause` beats keep the previous index until the
    beat ends, so the tip waits while the narration explains an obstacle.
    """
    route = storyboard.get("route") or {}
    markers = route.get("markers") or {}
    keys: list[list[float]] = [[0.0, 0.0]]
    for beat in sorted(storyboard["beats"], key=lambda b: b["start_s"]):
        head = beat.get("head")
        if not head:
            continue
        idx = float(markers[head["marker"]])
        motion = head.get("motion", "draw")
        if motion == "draw":
            t = head.get("arrive_s", beat.get("sync_word_s", beat["start_s"]))
            keys.append([round(float(t), 3), idx])
        else:
            keys.append([round(beat["start_s"], 3), keys[-1][1]])
            keys.append([round(beat["end_s"], 3), keys[-1][1]])
    keys.sort(key=lambda k: k[0])
    # Monotone in time and never backwards along the path.
    out: list[list[float]] = []
    for t, idx in keys:
        if out and t <= out[-1][0]:
            out[-1][1] = max(out[-1][1], idx)
            continue
        out.append([t, max(idx, out[-1][1]) if out else idx])
    return out


def head_index_at(keys: list[list[float]], t: float) -> float:
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, i0), (t1, i1) in zip(keys, keys[1:], strict=False):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3 - 2 * u)  # smoothstep: the tip eases out of and into each place
            return i0 + (i1 - i0) * u
    return keys[-1][1]


def path_point(path: list[list[float]], index: float) -> tuple[float, float]:
    i = max(0, min(int(math.floor(index)), len(path) - 1))
    j = min(i + 1, len(path) - 1)
    u = index - i
    return path[i][0] + (path[j][0] - path[i][0]) * u, path[i][1] + (path[j][1] - path[i][1]) * u


def camera_keys(
    storyboard: dict[str, Any],
    regimes: dict[str, dict[str, float]],
    *,
    lead_s: float = 0.5,
    smooth_window_s: float = 0.6,
    cuts: list[float] | None = None,
) -> list[list[float]]:
    """Camera keys from beat regimes: each move starts `lead_s` before the sync word.

    A beat's target is `camera.target` when given, else the head position at the sync word.
    `hold` beats repeat the previous framing. Keys are denoised before they are returned.
    """
    path = (storyboard.get("route") or {}).get("path") or []
    hk = head_keys(storyboard) if path else []
    keys: list[list[float]] = []
    prev: list[float] | None = None
    for beat in sorted(storyboard["beats"], key=lambda b: b["start_s"]):
        cam = beat.get("camera") or {}
        regime = cam.get("regime")
        if not regime:
            continue
        arrive = float(beat.get("sync_word_s", beat["start_s"]))
        if regime == "hold" and prev is not None:
            keys.append([round(arrive, 3), *prev[1:]])
            continue
        if "target" in cam:
            lng, lat = cam["target"]
        elif hk:
            lng, lat = path_point(path, head_index_at(hk, arrive))
        elif prev is not None:
            lng, lat = prev[1], prev[2]
        else:
            continue
        zoom = float(cam.get("zoom", regimes.get(regime, {}).get("zoom", 4.0)))
        bearing = float(cam.get("bearing", 0.0))
        start = float(cam.get("move_start_s", arrive - lead_s))
        if prev is not None and start > prev[0] + 1e-3:
            keys.append([round(start, 3), *prev[1:]])
        key = [round(arrive, 3), float(lng), float(lat), zoom, bearing]
        keys.append(key)
        prev = key
    keys.sort(key=lambda k: k[0])
    dedup: list[list[float]] = []
    for k in keys:
        if dedup and abs(k[0] - dedup[-1][0]) < 1e-3:
            dedup[-1] = k
        else:
            dedup.append(k)
    if len(dedup) < 3:
        return dedup
    return smooth_scene_keys(dedup, window_s=smooth_window_s, cuts=cuts or [])


def route_width_keys(
    cam_keys: list[list[float]], regimes: dict[str, dict[str, float]]
) -> list[list[float]]:
    """Stroke width per camera key, interpolated in zoom between the brand's regime widths."""
    table = sorted((r["zoom"], r["route_width_px"]) for r in regimes.values())
    out = []
    for k in cam_keys:
        z = k[3]
        if z <= table[0][0]:
            w = table[0][1]
        elif z >= table[-1][0]:
            w = table[-1][1]
        else:
            for (z0, w0), (z1, w1) in zip(table, table[1:], strict=False):
                if z0 <= z <= z1:
                    w = w0 + (w1 - w0) * (z - z0) / (z1 - z0)
                    break
        out.append([k[0], round(w, 2)])
    return out


def place_callout(
    head_xy: tuple[float, float],
    travel_xy: tuple[float, float],
    size_px: float,
    *,
    occupied: list[tuple[float, float, float]] | None = None,
    frame: tuple[float, float] = FRAME,
    caption_band_pct: tuple[float, float] = (0.66, 0.76),
    distance_px: tuple[float, float] = (200.0, 320.0),
    clear_radius_px: float = 120.0,
    side_margin_px: float = 60.0,
) -> tuple[float, float]:
    """Choose a callout centre that trails the route head.

    Candidates sit `distance_px` from the head on the side the route came from (opposite
    `travel_xy`), biased upward. Each candidate is penalised for leaving the frame margins,
    entering the caption band, covering the head's clear radius or the next stretch of route,
    and overlapping `occupied` callouts given as `(x, y, size)`.
    """
    hx, hy = head_xy
    tx, ty = travel_xy
    norm = math.hypot(tx, ty) or 1.0
    tx, ty = tx / norm, ty / norm
    back = math.atan2(-ty, -tx)
    occupied = occupied or []
    band = (caption_band_pct[0] * frame[1], caption_band_pct[1] * frame[1])
    half = size_px / 2
    best, best_cost = (hx, hy - distance_px[0]), math.inf
    for da in range(-120, 121, 15):
        for dist in (distance_px[0], sum(distance_px) / 2, distance_px[1]):
            a = back + math.radians(da)
            x, y = hx + dist * math.cos(a), hy + dist * math.sin(a)
            cost = abs(da) / 60.0 + (y - hy) / 400.0  # prefer straight behind, then upward
            if x - half < side_margin_px or x + half > frame[0] - side_margin_px:
                cost += 50
            if y - half < side_margin_px or y + half > frame[1] - side_margin_px:
                cost += 50
            if y + half > band[0] and y - half < band[1]:
                cost += 40
            if math.hypot(x - hx, y - hy) - half < clear_radius_px:
                cost += 30
            ahead = (hx + tx * 160.0, hy + ty * 160.0)
            if math.hypot(x - ahead[0], y - ahead[1]) < half + 40:
                cost += 30
            for ox, oy, osize in occupied:
                if math.hypot(x - ox, y - oy) < half + osize / 2:
                    cost += 25
            if cost < best_cost:
                best, best_cost = (x, y), cost
    return round(best[0], 1), round(best[1], 1)


def compile_journey(
    storyboard: dict[str, Any],
    idioms: dict[str, Any],
    *,
    cuts: list[float] | None = None,
) -> dict[str, Any]:
    """Head, camera and route-width keys plus resolved callout positions for a journey storyboard.

    Callouts anchored to `route_head` get `xy` written back into the returned storyboard copy,
    so `check_storyboard` can verify the caption band and concurrency on real positions.
    """
    import copy

    regimes = idioms.get("camera_regimes") or {}
    sb = copy.deepcopy(storyboard)
    path = (sb.get("route") or {}).get("path") or []
    hk = head_keys(sb) if path else []
    cams = camera_keys(sb, regimes, cuts=cuts)
    widths = route_width_keys(cams, regimes) if cams and regimes else []

    def cam_at(t: float) -> list[float] | None:
        if not cams:
            return None
        if t <= cams[0][0]:
            return cams[0]
        for a, b in zip(cams, cams[1:], strict=False):
            if t <= b[0]:
                u = (t - a[0]) / (b[0] - a[0])
                return [t, *(a[i] + (b[i] - a[i]) * u for i in range(1, 5))]
        return cams[-1]

    live: list[tuple[float, float, float, float]] = []  # (end_s, x, y, size)
    for beat in sorted(sb["beats"], key=lambda b: b["start_s"]):
        for c in beat.get("callouts") or []:
            if c.get("anchor", "route_head") != "route_head" or "xy" in c or not hk:
                continue
            t = c.get("start_s", beat["start_s"])
            cam = cam_at(t)
            if cam is None:
                continue
            idx = head_index_at(hk, t)
            here = path_point(path, idx)
            before = path_point(path, max(0.0, idx - 1.0))
            hx, hy = project(*here, cam)
            bx, by = project(*before, cam)
            live = [o for o in live if o[0] > t]
            size = float(c.get("size_px", 200.0))
            xy = place_callout(
                (hx, hy), (hx - bx, hy - by), size, occupied=[(x, y, s) for _, x, y, s in live]
            )
            c["xy"] = list(xy)
            live.append((c.get("end_s", beat["end_s"]), xy[0], xy[1], size))
    return {
        "storyboard": sb,
        "head_keys": hk,
        "camera_keys": cams,
        "route_width_keys": widths,
    }
