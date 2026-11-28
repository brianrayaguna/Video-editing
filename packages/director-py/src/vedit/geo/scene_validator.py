"""Declarative map_scene.json craft, sharpness, geometry, and clutter validation."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from vedit.geo.tiles import _deg2num
from vedit.geo_imagery import NATIONAL_ORTHO_MAX_Z, S2_CLOUDLESS_MAX_NATIVE_Z

_TEXT_LAYER_TYPES = frozenset(
    {"glow_label", "pin_label", "curved_pointer_label", "year_badge", "curved_label"}
)
_THREE_D_MODELS = frozenset(
    {"aircraft", "transmission_tower", "solar_farm", "substation", "survey_vessel"}
)

_REVEAL_MODES = frozenset(
    {"fade", "radial", "organic", "wipe_left", "wipe_right", "wipe_down", "wipe_up"}
)
_EASE_MODES = frozenset(
    {
        "linear",
        "out",
        "in_out",
        "expo_out",
        "quint_out",
        "quart_in_out",
        "in_quad",
        "in_cubic",
        "editorial_out",
        "spring_crisp",
        "spring_tactile",
        "spring_playful",
    }
)
_CAPTURE_FORMATS = frozenset({"jpeg", "png"})
# Numeric polygon keys: (lower bound, upper bound or None).
_POLYGON_NUMERIC_KEYS: dict[str, tuple[float, float | None]] = {
    "flag_wave_speed": (0.0, None),
    "flag_wave_cycles": (0.0, None),
    "flag_wave_angle_deg": (-360.0, 360.0),
    "fill_reveal_roughness": (0.0, 0.6),
    "hatch_draw_s": (0.0, None),
    "hatch_delay_s": (0.0, None),
    "hatch_stagger": (0.0, 0.95),
    "hatch_angle_deg": (-360.0, 360.0),
    "hatch_spacing": (2.0, None),
    "hatch_width": (0.2, 64.0),
    "lift_px": (0.0, 120.0),
    "fill_bloom_overshoot": (1.0, 1.6),
}
_POLYGON_OPT_BOOL_FLOAT_KEYS: dict[str, tuple[float, float]] = {
    "flag_gloss": (0.0, 1.0),
    "flag_wave_warp": (0.0, 0.15),
    "bevel_light": (0.0, 1.0),
}
# Polygon keys whose unknown values the renderer would silently replace with a default.
_POLYGON_ENUM_KEYS: dict[str, frozenset[Any]] = {
    "flag_reveal": _REVEAL_MODES,
    "fill_reveal_mode": _REVEAL_MODES,
    "flag_blend": frozenset({"normal", "multiply", "overlay", "soft-light", "screen"}),
    "flag_fit": frozenset({"stretch", "cover"}),
    "border_trace_ease": _EASE_MODES,
    "border_trace_dir": frozenset({"cw", "ccw"}),
    "border_trace_heads": frozenset({1, 2}),
    "hatch_space": frozenset({"world", "screen"}),
    "hatch_reveal_mode": frozenset({"staggered_draw", "venetian_grow", "contour_ripple", "fade"}),
    "hatch_direction": frozenset({"ltr", "rtl", "center_out", "alternate"}),
    "hatch_ease": _EASE_MODES,
    "lift_ease": _EASE_MODES,
}
_FLAG_CODE_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")




REJECTED_SCENE_LAYER_TYPES = frozenset(
    {
        "coord_plaque",
        "scale_comparison",
        "survey_pin",
        "orbital_sightlines",
        "culmination_sun",
        "callout_badge",
    }
)


def _haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def _approx_viewport_pct(
    lng: float,
    lat: float,
    center: list[float],
    zoom: float,
    bearing_deg: float,
    width: int,
    height: int,
    *,
    dx: float = 0.0,
    dy: float = 0.0,
) -> tuple[float, float]:
    scale = 512.0 * (2.0**zoom)

    def _merc(lon_v: float, lat_v: float) -> tuple[float, float]:
        s = math.sin(math.radians(max(-85.0, min(85.0, lat_v))))
        mx = ((lon_v + 180.0) / 360.0) * scale
        my = (0.5 - math.log((1.0 + s) / (1.0 - s)) / (4.0 * math.pi)) * scale
        return mx, my

    px, py = _merc(lng, lat)
    cx, cy = _merc(center[0], center[1])
    vx, vy = px - cx, py - cy
    rad = math.radians(-bearing_deg)
    rx = vx * math.cos(rad) - vy * math.sin(rad)
    ry = vx * math.sin(rad) + vy * math.cos(rad)
    sx = width * 0.5 + rx + dx
    sy = height * 0.5 + ry + dy
    return sx / max(1, width), sy / max(1, height)



def _load_scene_vectors(spec: dict[str, Any], base_dir: Path | None) -> dict[str, Any] | None:
    """Load the scene's `vectors_file`; None when absent, unreadable, or relative without a base."""
    ref = spec.get("vectors_file") or spec.get("vectors_path")
    if not ref:
        return None
    path = Path(str(ref)).expanduser()
    if not path.is_absolute():
        if base_dir is None:
            return None
        path = base_dir / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_geom_ref(vectors: dict[str, Any] | None, ref: Any) -> Any:
    """Resolve a layer `geom_ref` (inline geometry or dotted path into the vectors) or None."""
    if isinstance(ref, dict) and ref.get("type"):
        return ref
    if not isinstance(ref, str) or vectors is None:
        return None
    cur: Any = vectors
    for part in ref.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _separately_traced_parts(geom: Any) -> int:
    """Count parts a border trace walks independently with seams between them.

    Feature lists, FeatureCollections and seam-dissolved MultiPolygons trace every part from its
    own start; a single Polygon or a plain MultiPolygon (islands of one outline) counts as 1.
    """
    if isinstance(geom, list):
        return sum(1 for g in geom if g)
    if isinstance(geom, dict):
        if geom.get("type") == "FeatureCollection":
            return sum(1 for g in geom.get("features") or [] if g)
        if geom.get("type") == "MultiPolygon" and geom.get("dissolve_seams"):
            return len(geom.get("coordinates") or [])
    return 1


def _as_finite_float(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


def validate_map_scene(
    spec: dict[str, Any],
    *,
    repo_root: Path | None = None,
    base_dir: Path | None = None,
    check_hq_tiles: bool = True,
) -> dict[str, Any]:
    """Validate declarative map_scene.json against Geoverum craft and sharpness guardrails.

    `base_dir` resolves a relative `vectors_file` so geometry-dependent checks can run.
    """
    errors: list[str] = []
    warnings: list[str] = []
    vectors = _load_scene_vectors(spec, base_dir)
    width = int(spec.get("width", 1080))
    height = int(spec.get("height", 1920))
    min_font_px = 36 if height >= 1600 else 28
    hq_dir = (repo_root / "assets" / "geo" / "tiles_hq") if repo_root else None

    def _check_render_opts(container: dict[str, Any], scope: str) -> None:
        if "ov_scale" in container and container["ov_scale"] is not None:
            ov = _as_finite_float(container["ov_scale"])
            if ov is None or not (1.0 <= ov <= 2.0):
                errors.append(
                    f"[{scope}] ov_scale must be a number between 1 and 2, "
                    f"got {container['ov_scale']!r}."
                )
        if "capture_format" in container and container["capture_format"] is not None:
            cf = container["capture_format"]
            if isinstance(cf, bool) or cf not in _CAPTURE_FORMATS:
                errors.append(
                    f"[{scope}] capture_format={cf!r} is not one of "
                    f"{sorted(_CAPTURE_FORMATS)}."
                )

    _check_render_opts(spec, "scene")

    for act in spec.get("acts") or []:
        act_id = str(act.get("act_id") or "unknown")
        act_kind = str(act.get("kind") or act.get("mode") or act.get("type") or "map")
        if act_kind == "cutaway_2d":
            preset = act.get("preset")
            html_file = act.get("html_file")
            custom_html = act.get("custom_html")
            known_cutaways = {"soil_root_cutaway", "dust_wall_horizon", "port_depth_cutaway"}
            if html_file:
                hp = Path(str(html_file))
                if not hp.is_absolute() and base_dir is not None:
                    hp = base_dir / hp
                if not hp.is_file():
                    errors.append(
                        f"[{act_id}] cutaway_2d html_file {html_file!r} not found at {hp}."
                    )
            elif not (isinstance(custom_html, str) and custom_html.strip()):
                if preset is not None and str(preset) not in known_cutaways:
                    errors.append(
                        f"[{act_id}] cutaway_2d preset {preset!r} is unknown; expected one of "
                        f"{sorted(known_cutaways)} or pass html_file/custom_html."
                    )
            continue
        if act_kind != "map":
            continue
        _check_render_opts(act, act_id)
        dur = float(act.get("duration_s", 0.0))
        tile_source = str(act.get("tile_source") or "hybrid")
        layers = list(act.get("layers") or [])

        # 0. Cut-accent radial zoom blur windows and strength
        cut_windows: list[float] = []
        for key, upper in (
            ("cut_blur_in_s", None),
            ("cut_blur_out_s", None),
            ("cut_blur_strength", 0.4),
        ):
            if key not in act:
                continue
            value = _as_finite_float(act[key])
            if value is None:
                errors.append(f"[{act_id}] {key} must be a number, got {act[key]!r}.")
                continue
            if value < 0 or (upper is not None and value > upper):
                bound = f"between 0 and {upper}" if upper is not None else "a finite value >= 0"
                errors.append(f"[{act_id}] {key} must be {bound}, got {value}.")
                continue
            if key != "cut_blur_strength":
                cut_windows.append(value)
        if dur > 0 and sum(cut_windows) > dur + 1e-6:
            warnings.append(
                f"[{act_id}] cut_blur_in_s + cut_blur_out_s = {sum(cut_windows):.2f}s exceeds the "
                f"act duration {dur:.2f}s; the blur never clears mid-act."
            )

        # 0b. Enforce Google Map Tiles attribution visibility when Google tiles are active
        act_kind = str(act.get("kind") or "map")
        tile_src = str(act.get("tile_source") or "hybrid")
        effective_show_credit = (
            act["show_credit"] if "show_credit" in act else spec.get("show_credit", True)
        )
        if (
            act_kind == "map"
            and tile_src in {"hybrid", "realistic", "realistic_graded"}
            and effective_show_credit is False
            and repo_root is not None
        ):
            hq_attr_path = repo_root / "assets" / "geo" / "tiles_hq" / "attribution.json"
            if hq_attr_path.is_file():
                try:
                    hq_attr = json.loads(hq_attr_path.read_text(encoding="utf-8"))
                    if "google_map_tiles" in (hq_attr.get("sources") or []):
                        warnings.append(
                            f"[{act_id}] show_credit=false ignored for Google Map Tiles "
                            f"(tile_source={tile_src!r}); official imagery attribution will be "
                            "rendered on screen to comply with tile terms."
                        )
                except (OSError, json.JSONDecodeError):
                    pass

        # 1. Reject legacy/chrome slop layers and micro-typography
        text_intervals: list[tuple[float, float, str]] = []
        for idx, layer in enumerate(layers):
            ltype = str(layer.get("type") or "")
            if ltype in REJECTED_SCENE_LAYER_TYPES:
                errors.append(
                    f"[{act_id}] layer #{idx} uses rejected chrome type '{ltype}'. "
                    "Use calibrated boxless primitives (glow_label, pin_label, "
                    "curved_pointer_label, dashed_distance, void_wipe, counter_odometer, "
                    "prohibition_pins)."
                )
            if ltype in _TEXT_LAYER_TYPES:
                raw_fpx = layer.get("font_px")
                fpx = float(56 if raw_fpx is None else raw_fpx)
                if fpx < min_font_px:
                    errors.append(
                        f"[{act_id}] layer #{idx} ({ltype}) font_px={fpx} is below minimum "
                        f"{min_font_px}px for {width}x{height} legibility."
                    )
                if ltype == "curved_label":
                    coords = layer.get("coords")
                    if not isinstance(coords, list) or len(coords) < 2:
                        errors.append(
                            f"[{act_id}] layer #{idx} (curved_label) requires at least 2 "
                            "[lng, lat] points in 'coords'."
                        )
                raw_t0 = layer.get("start_s")
                raw_t1 = layer.get("end_s")
                t0 = float(0.0 if raw_t0 is None else raw_t0)
                t1 = float(dur if raw_t1 is None else raw_t1)
                text_intervals.append((t0, t1, str(layer.get("text") or ltype)))

        # 2. Enforce calm hierarchy: error above 4 concurrent text overlays, warn at 4
        if text_intervals and dur > 0:
            step = 0.25
            t_cur = 0.0
            warned_crowd = False
            while t_cur < dur - 1e-6:
                active = [lbl for (a, b, lbl) in text_intervals if a <= t_cur < b]
                if len(active) > 4:
                    errors.append(
                        f"[{act_id}] {len(active)} concurrent text overlays at t={t_cur:.2f}s "
                        f"({', '.join(active[:5])}); max allowed is 4 to prevent visual clutter."
                    )
                    break
                if len(active) == 4 and not warned_crowd:
                    warnings.append(
                        f"[{act_id}] 4 concurrent map text overlays at t={t_cur:.2f}s "
                        f"({', '.join(active)}); prefer <= 3 labels when captions are active."
                    )
                    warned_crowd = True
                t_cur += step

        # 3. Close-up sharpness check: zoom >= 13.5 requires HQ aerial tiles (never Sentinel-2)
        kfs = list(act.get("camera_keyframes") or [])
        max_zoom = 0.0
        closeup_centers: list[tuple[float, float, float]] = []
        for kf in kfs:
            if isinstance(kf, dict):
                z = float(kf.get("zoom", 0.0))
                ctr = kf.get("center") or [kf.get("lng", 0.0), kf.get("lat", 0.0)]
            else:
                z = float(kf[3]) if len(kf) > 3 else 0.0
                ctr = [float(kf[1]), float(kf[2])] if len(kf) > 2 else [0.0, 0.0]
            if z > max_zoom:
                max_zoom = z
            if z >= 13.5:
                closeup_centers.append((float(ctr[0]), float(ctr[1]), z))

        if max_zoom >= 13.5 and tile_source == "graded":
            errors.append(
                f"[{act_id}] max zoom {max_zoom:.1f} uses Sentinel-2 'graded' tiles "
                "which blur below ~2 km. Use tile_source 'hybrid' or 'realistic' and fetch "
                "high-resolution tiles with `vedit geo prepare --hq`."
            )
        use_project_tiles = tile_source in {"project", "project_graded"}
        project_tiles_spec = spec.get("project_tiles_dir")
        if use_project_tiles and not project_tiles_spec:
            errors.append(
                f"[{act_id}] tile_source '{tile_source}' requires top-level 'project_tiles_dir'."
            )
        if check_hq_tiles and closeup_centers and (hq_dir is not None or use_project_tiles):
            probe_root = hq_dir
            if use_project_tiles and project_tiles_spec:
                p_dir = Path(str(project_tiles_spec))
                probe_root = p_dir if p_dir.is_absolute() else ((base_dir or Path.cwd()) / p_dir)
            for lng, lat, z in closeup_centers:
                check_z = min(16, max(13, round(z)))
                found_z: int | None = None
                if probe_root is not None:
                    for probe_z in range(check_z, 12, -1):
                        tx, ty = _deg2num(lat, lng, probe_z)
                        if (probe_root / str(probe_z) / str(tx) / f"{ty}.jpg").is_file():
                            found_z = probe_z
                            break
                has_hq = found_z is not None
                if (
                    not use_project_tiles
                    and has_hq
                    and z >= 14.5
                    and (found_z is None or found_z <= S2_CLOUDLESS_MAX_NATIVE_Z)
                    and probe_root is not None
                ):
                    has_ortho = any(
                        (
                            probe_root
                            / str(oz)
                            / str(_deg2num(lat, lng, oz)[0])
                            / f"{_deg2num(lat, lng, oz)[1]}.jpg"
                        ).is_file()
                        for oz in range(S2_CLOUDLESS_MAX_NATIVE_Z + 1, NATIONAL_ORTHO_MAX_Z + 1)
                    )
                    if not has_ortho:
                        warnings.append(
                            f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} exceeds "
                            f"the ~10 m Sentinel-2 native zoom (z{S2_CLOUDLESS_MAX_NATIVE_Z}) "
                            "and no sharper orthoimagery covers it; cap the zoom near 14.5 or "
                            "supply a project-scoped aerial plate."
                        )
                if not has_hq:
                    if use_project_tiles:
                        errors.append(
                            f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} has no "
                            f"project tiles in {probe_root} covering z13-16."
                        )
                    else:
                        errors.append(
                            f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} has no "
                            "high-resolution aerial tiles in assets/geo/tiles_hq/. Run "
                            f"`vedit geo prepare --bbox \"{lng-0.06:.3f},{lat-0.06:.3f},"
                            f"{lng+0.06:.3f},{lat+0.06:.3f}:13,14,15,16\" --hq "
                            "-o media/maps/vectors.json` first."
                        )
                    break

        # 4. Camera dynamism check (reject flat/static maps)
        if dur >= 8.0 and kfs:
            if len(kfs) < 3:
                errors.append(
                    f"[{act_id}] duration {dur:.1f}s has only {len(kfs)} camera_keyframes; "
                    "use >= 3 3D cinema keyframes with zoom/bearing/pitch progression."
                )
            pitches = [
                float(kf.get("pitch", 0.0))
                if isinstance(kf, dict)
                else (float(kf[5]) if len(kf) > 5 else 0.0)
                for kf in kfs
            ]
            if max(pitches, default=0.0) < 4.0:
                warnings.append(
                    f"[{act_id}] peak camera pitch is {max(pitches, default=0.0):.1f} deg; "
                    "consider 10-35 deg 3D pitch on approach and corridor beats."
                )

        # 5. Polygon border-trace timing, flag-fill assets, and enumerated keys
        flags_dir = (repo_root / "assets" / "geo" / "flags") if repo_root else None
        for idx, layer in enumerate(layers):
            if str(layer.get("type") or "") != "polygon":
                continue
            for key, allowed in _POLYGON_ENUM_KEYS.items():
                if key in layer:
                    val = layer[key]
                    if isinstance(val, bool) or val not in allowed:
                        errors.append(
                            f"[{act_id}] layer #{idx} {key}={val!r} is not one of "
                            f"{sorted(str(v) for v in allowed)}."
                        )
            wave = layer.get("flag_wave")
            if wave is not None and not isinstance(wave, bool):
                wave_f = _as_finite_float(wave)
                if wave_f is None or not (0.0 <= wave_f <= 0.6):
                    errors.append(
                        f"[{act_id}] layer #{idx} flag_wave must be true/false or a shading "
                        f"amplitude between 0 and 0.6, got {wave!r}."
                    )
            for key, (lo, hi) in _POLYGON_NUMERIC_KEYS.items():
                if key not in layer:
                    continue
                val = _as_finite_float(layer[key])
                if val is None or val < lo or (hi is not None and val > hi):
                    bound = f"between {lo:g} and {hi:g}" if hi is not None else f">= {lo:g}"
                    errors.append(
                        f"[{act_id}] layer #{idx} {key} must be a number {bound}, "
                        f"got {layer[key]!r}."
                    )
            for key, (lo, hi) in _POLYGON_OPT_BOOL_FLOAT_KEYS.items():
                if key not in layer:
                    continue
                raw_val = layer[key]
                if isinstance(raw_val, bool):
                    continue
                val = _as_finite_float(raw_val)
                if val is None or val < lo or val > hi:
                    errors.append(
                        f"[{act_id}] layer #{idx} {key} must be true/false or between "
                        f"{lo:g} and {hi:g}, got {raw_val!r}."
                    )
            for opt_obj_key in ("light_sweep", "rim_glint", "cast_shadow"):
                if opt_obj_key in layer and layer[opt_obj_key] is not None:
                    raw_obj = layer[opt_obj_key]
                    if not isinstance(raw_obj, (bool, dict)):
                        errors.append(
                            f"[{act_id}] layer #{idx} {opt_obj_key} must be a boolean or object, "
                            f"got {raw_obj!r}."
                        )
            code = layer.get("flag_fill")
            if code:
                code_s = str(code).lower()
                if not _FLAG_CODE_RE.fullmatch(code_s):
                    errors.append(
                        f"[{act_id}] layer #{idx} flag_fill {code!r} is not a flag code "
                        "(lowercase letters, digits and hyphens, e.g. 'se' or 'gb-sct')."
                    )
                elif flags_dir is not None and not (flags_dir / f"{code_s}.svg").is_file():
                    errors.append(
                        f"[{act_id}] layer #{idx} flag_fill '{code_s}' has no "
                        f"assets/geo/flags/{code_s}.svg; the bake would fall back to the "
                        "colour fill."
                    )
            trace_s = 0.0
            if "border_trace_s" in layer and layer["border_trace_s"] is not None:
                parsed_trace = _as_finite_float(layer["border_trace_s"])
                if parsed_trace is None or parsed_trace < 0:
                    errors.append(
                        f"[{act_id}] layer #{idx} border_trace_s must be a number >= 0, "
                        f"got {layer['border_trace_s']!r}."
                    )
                else:
                    trace_s = parsed_trace
            delay_s = 0.0
            if "border_trace_delay_s" in layer and layer["border_trace_delay_s"] is not None:
                parsed_delay = _as_finite_float(layer["border_trace_delay_s"])
                if parsed_delay is None or parsed_delay < 0:
                    errors.append(
                        f"[{act_id}] layer #{idx} border_trace_delay_s must be a number >= 0, "
                        f"got {layer['border_trace_delay_s']!r}."
                    )
                else:
                    delay_s = parsed_delay
            if trace_s > 0:
                raw_start = 0.0 if layer.get("start_s") is None else layer.get("start_s")
                raw_end = dur if layer.get("end_s") is None else layer.get("end_s")
                start_s = _as_finite_float(raw_start)
                visible_end = _as_finite_float(raw_end)
                if start_s is None or visible_end is None:
                    errors.append(
                        f"[{act_id}] layer #{idx} start_s/end_s must be finite numbers."
                    )
                else:
                    trace_end = start_s + delay_s + trace_s
                    if dur > 0:
                        visible_end = min(visible_end, dur)
                    if trace_end > visible_end + 1e-6:
                        warnings.append(
                            f"[{act_id}] layer #{idx} border_trace ends at {trace_end:.2f}s, "
                            f"after the layer/act ends at {visible_end:.2f}s; the outline never "
                            "closes on screen."
                        )
                parts = _separately_traced_parts(_resolve_geom_ref(vectors, layer.get("geom_ref")))
                if parts > 1:
                    warnings.append(
                        f"[{act_id}] layer #{idx} border_trace_s runs over {parts} separate parts "
                        f"of {layer.get('geom_ref')!r}; each part traces its own outline from its "
                        "own start, so the border grows in fragments. Trace one country outline "
                        "(countries.<ISO>) or reveal multi-part regions with border_draw_s."
                    )

        # 6. 3D scene layers, contextual crimson_x, and disallowed small flag_pin checks
        for idx, layer in enumerate(layers):
            ltype = str(layer.get("type") or "")
            if ltype == "flag_pin":
                errors.append(
                    f"[{act_id}] layer #{idx} flag_pin is disallowed for national territories; "
                    "cover the full coastline with country_block_3d or polygon using "
                    "flag_fill, flag_wave, and flag_glow."
                )
            elif ltype == "crimson_x":
                if "slash_duration_s" in layer and layer["slash_duration_s"] is not None:
                    sd = _as_finite_float(layer["slash_duration_s"])
                    if sd is None or sd <= 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} crimson_x slash_duration_s must be > 0, "
                            f"got {layer['slash_duration_s']!r}."
                        )
                if "gap_s" in layer and layer["gap_s"] is not None:
                    gs = _as_finite_float(layer["gap_s"])
                    if gs is None or gs < 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} crimson_x gap_s must be >= 0, "
                            f"got {layer['gap_s']!r}."
                        )
                if "shockwave" in layer and layer["shockwave"] is not None:
                    if not isinstance(layer["shockwave"], bool):
                        errors.append(
                            f"[{act_id}] layer #{idx} crimson_x shockwave must be boolean, "
                            f"got {layer['shockwave']!r}."
                        )
            elif ltype == "cable_3d":
                coords = layer.get("coords")
                coords_ref = layer.get("coords_ref")
                if not coords_ref and (not isinstance(coords, list) or len(coords) < 2):
                    errors.append(
                        f"[{act_id}] layer #{idx} cable_3d requires coords (len >= 2) or "
                        "coords_ref."
                    )
                if "end_taper_m" in layer and layer["end_taper_m"] is not None:
                    et = _as_finite_float(layer["end_taper_m"])
                    if et is None or et < 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} cable_3d end_taper_m must be >= 0, "
                            f"got {layer['end_taper_m']!r}."
                        )
                if "min_screen_radius_px" in layer and layer["min_screen_radius_px"] is not None:
                    mr = _as_finite_float(layer["min_screen_radius_px"])
                    if mr is None or mr <= 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} cable_3d min_screen_radius_px must be > 0, "
                            f"got {layer['min_screen_radius_px']!r}."
                        )
            elif ltype == "model_3d":
                mtype = str(layer.get("model") or "")
                gltf_url = layer.get("gltf_url")
                if not gltf_url and mtype not in _THREE_D_MODELS:
                    errors.append(
                        f"[{act_id}] layer #{idx} model_3d has unknown model {mtype!r}; "
                        f"expected one of {sorted(_THREE_D_MODELS)} or gltf_url."
                    )
                if gltf_url:
                    g_raw = str(gltf_url).strip()
                    if not g_raw.startswith(("http://", "https://")):
                        g_rel = g_raw.lstrip("/")
                        candidates = []
                        if base_dir is not None:
                            candidates.append(base_dir / g_rel)
                            if g_rel.startswith("project_models/"):
                                candidates.append(
                                    base_dir / "models" / g_rel[len("project_models/"):]
                                )
                        if repo_root is not None:
                            candidates.append(repo_root / "assets" / "geo" / g_rel)
                            candidates.append(repo_root / "assets" / "geo" / "models" / g_rel)
                        if candidates and not any(c.is_file() for c in candidates):
                            errors.append(
                                f"[{act_id}] layer #{idx} model_3d gltf_url {gltf_url!r} "
                                "not found in project models/ or assets/geo/models/."
                            )
                coord = layer.get("coord")
                path = layer.get("path")
                has_coord = isinstance(coord, list) and len(coord) >= 2
                has_path = isinstance(path, list) and len(path) >= 2
                if not has_coord and not has_path:
                    errors.append(
                        f"[{act_id}] layer #{idx} model_3d requires coord [lng, lat] or path."
                    )
                if "altitude_arc_m" in layer and layer["altitude_arc_m"] is not None:
                    aa = _as_finite_float(layer["altitude_arc_m"])
                    if aa is None or aa < 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} model_3d altitude_arc_m must be >= 0, "
                            f"got {layer['altitude_arc_m']!r}."
                        )
                if "bank_deg" in layer and layer["bank_deg"] is not None:
                    bd = _as_finite_float(layer["bank_deg"])
                    if bd is None or not (-60.0 <= bd <= 60.0):
                        errors.append(
                            f"[{act_id}] layer #{idx} model_3d bank_deg must be "
                            f"between -60 and 60, got {layer['bank_deg']!r}."
                        )
                if "spin_rps" in layer and layer["spin_rps"] is not None:
                    sr = _as_finite_float(layer["spin_rps"])
                    if sr is None or not (-10.0 <= sr <= 10.0):
                        errors.append(
                            f"[{act_id}] layer #{idx} model_3d spin_rps must be "
                            f"between -10 and 10, got {layer['spin_rps']!r}."
                        )
                if "contrail" in layer and layer["contrail"] is not None:
                    if not isinstance(layer["contrail"], bool):
                        errors.append(
                            f"[{act_id}] layer #{idx} model_3d contrail must be boolean, "
                            f"got {layer['contrail']!r}."
                        )
            elif ltype == "volume_3d":
                coord = layer.get("coord")
                if not (isinstance(coord, list) and len(coord) >= 2):
                    errors.append(
                        f"[{act_id}] layer #{idx} volume_3d requires coord [lng, lat]."
                    )
                for dim in ("width_m", "length_m", "height_m"):
                    dval = _as_finite_float(layer.get(dim))
                    if dval is None or dval <= 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} volume_3d {dim} must be > 0, "
                            f"got {layer.get(dim)!r}."
                        )
            elif ltype == "country_block_3d":
                if not layer.get("geom_ref"):
                    errors.append(
                        f"[{act_id}] layer #{idx} country_block_3d requires geom_ref."
                    )
                if "extrude_height_m" in layer and layer["extrude_height_m"] is not None:
                    eh = _as_finite_float(layer["extrude_height_m"])
                    if eh is None or eh <= 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d extrude_height_m "
                            f"must be > 0, got {layer['extrude_height_m']!r}."
                        )
                if "bevel_px" in layer and layer["bevel_px"] is not None:
                    bp = _as_finite_float(layer["bevel_px"])
                    if bp is None or bp < 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d bevel_px must be >= 0, "
                            f"got {layer['bevel_px']!r}."
                        )
                if "rise_ease" in layer and layer["rise_ease"] is not None:
                    re_val = layer["rise_ease"]
                    if isinstance(re_val, bool) or re_val not in _EASE_MODES:
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d rise_ease={re_val!r} "
                            f"is not one of {sorted(_EASE_MODES)}."
                        )
                if "light_sweep" in layer and layer["light_sweep"] is not None:
                    if not isinstance(layer["light_sweep"], (bool, dict)):
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d light_sweep must be "
                            f"boolean or object, got {layer['light_sweep']!r}."
                        )
                cb_flag = layer.get("flag_fill")
                if cb_flag:
                    cb_code = str(cb_flag).lower()
                    if not _FLAG_CODE_RE.fullmatch(cb_code):
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d flag_fill {cb_flag!r} "
                            "is not a valid flag code."
                        )
                    elif flags_dir is not None and not (flags_dir / f"{cb_code}.svg").is_file():
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d flag_fill '{cb_code}' "
                            f"has no assets/geo/flags/{cb_code}.svg."
                        )
                if "flag_wave" in layer and layer["flag_wave"] is not None:
                    cb_wave = layer["flag_wave"]
                    if not isinstance(cb_wave, bool):
                        cb_wf = _as_finite_float(cb_wave)
                        if cb_wf is None or not (0.0 <= cb_wf <= 0.6):
                            errors.append(
                                f"[{act_id}] layer #{idx} country_block_3d flag_wave must be "
                                f"boolean or between 0 and 0.6, got {cb_wave!r}."
                            )
                for fkey, (lo, hi) in (
                    ("flag_wave_speed", (0.0, None)),
                    ("flag_wave_cycles", (0.0, None)),
                    ("flag_wave_angle_deg", (-360.0, 360.0)),
                    ("flag_glow_intensity", (0.0, 3.0)),
                ):
                    if fkey in layer and layer[fkey] is not None:
                        fval = _as_finite_float(layer[fkey])
                        if fval is None or fval < lo or (hi is not None and fval > hi):
                            bound = f"between {lo:g} and {hi:g}" if hi is not None else f">= {lo:g}"
                            errors.append(
                                f"[{act_id}] layer #{idx} country_block_3d {fkey} must be "
                                f"a number {bound}, got {layer[fkey]!r}."
                            )
                if "flag_glow" in layer and layer["flag_glow"] is not None:
                    if not isinstance(layer["flag_glow"], bool):
                        errors.append(
                            f"[{act_id}] layer #{idx} country_block_3d flag_glow must be "
                            f"boolean, got {layer['flag_glow']!r}."
                        )
            elif ltype == "focus_spotlight":
                gref = layer.get("geom_ref")
                grefs = layer.get("geom_refs")
                has_refs = bool(gref) or (isinstance(grefs, list) and len(grefs) > 0)
                if not has_refs:
                    errors.append(
                        f"[{act_id}] layer #{idx} focus_spotlight requires geom_ref or geom_refs."
                    )
                if "dim_alpha" in layer and layer["dim_alpha"] is not None:
                    da = _as_finite_float(layer["dim_alpha"])
                    if da is None or not (0.0 <= da <= 1.0):
                        errors.append(
                            f"[{act_id}] layer #{idx} focus_spotlight dim_alpha must be "
                            f"between 0 and 1, got {layer['dim_alpha']!r}."
                        )
                if "feather_px" in layer and layer["feather_px"] is not None:
                    fp = _as_finite_float(layer["feather_px"])
                    if fp is None or fp < 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} focus_spotlight feather_px must be >= 0, "
                            f"got {layer['feather_px']!r}."
                        )
            elif ltype == "parchment_sheet":
                bbox = layer.get("bbox")
                if not (isinstance(bbox, list) and len(bbox) == 4):
                    errors.append(
                        f"[{act_id}] layer #{idx} parchment_sheet requires bbox "
                        "[west_lon, south_lat, east_lon, north_lat]."
                    )
                else:
                    nums = [_as_finite_float(v) for v in bbox]
                    if any(v is None for v in nums) or nums[0] >= nums[2] or nums[1] >= nums[3]:  # type: ignore[operator]
                        errors.append(
                            f"[{act_id}] layer #{idx} parchment_sheet bbox must satisfy "
                            f"west < east and south < north, got {bbox!r}."
                        )
            elif ltype == "map_sprites":
                sprites = layer.get("sprites")
                if sprites is None:
                    sprites = layer.get("items")
                if not isinstance(sprites, list) or len(sprites) == 0:
                    errors.append(
                        f"[{act_id}] layer #{idx} map_sprites requires a non-empty 'sprites' list."
                    )
                else:
                    for s_i, sp in enumerate(sprites):
                        if not isinstance(sp, dict):
                            errors.append(
                                f"[{act_id}] layer #{idx} map_sprites[{s_i}] must be an object."
                            )
                            continue
                        sc = sp.get("coord")
                        sp_path = sp.get("path")
                        has_sc = isinstance(sc, list) and len(sc) >= 2
                        has_sp = isinstance(sp_path, list) and len(sp_path) >= 2
                        if not has_sc and not has_sp:
                            errors.append(
                                f"[{act_id}] layer #{idx} map_sprites[{s_i}] "
                                "requires coord or path."
                            )
                        raw_svg = sp.get("svg_url") or sp.get("image_url")
                        if raw_svg and not str(raw_svg).startswith(("http://", "https://")):
                            s_rel = str(raw_svg).lstrip("/")
                            cands: list[Path] = []
                            if base_dir is not None:
                                cands.append(base_dir / s_rel)
                                if s_rel.startswith("project_graphics/"):
                                    sub = s_rel[len("project_graphics/") :]
                                    cands.append(base_dir.parent / "media" / "graphics" / sub)
                                    cands.append(base_dir / "graphics" / sub)
                            if repo_root is not None:
                                cands.append(repo_root / "assets" / "geo" / s_rel)
                            if cands and not any(c.is_file() for c in cands):
                                errors.append(
                                    f"[{act_id}] layer #{idx} map_sprites[{s_i}] asset "
                                    f"{raw_svg!r} not found in project graphics or assets/geo/."
                                )

        # 7. Preflight viewport edge-clipping, caption-band, and cable/substation clearance checks
        cam_points: list[tuple[float, list[float], float, float]] = []
        for kf in kfs:
            if isinstance(kf, dict):
                tk = float(kf.get("t", kf.get("t_s", 0.0)))
                ctr = kf.get("center") or [kf.get("lng", 0.0), kf.get("lat", 0.0)]
                zk = float(kf.get("zoom", 5.0))
                bk = float(kf.get("bearing", 0.0))
            elif len(kf) >= 4:
                tk, ctr, zk = float(kf[0]), [float(kf[1]), float(kf[2])], float(kf[3])
                bk = float(kf[4]) if len(kf) > 4 else 0.0
            else:
                continue
            cam_points.append((tk, [float(ctr[0]), float(ctr[1])], zk, bk))
        cam_points.sort(key=lambda item: item[0])

        substations = [
            layer.get("coord")
            for layer in layers
            if str(layer.get("type") or "") == "model_3d"
            and str(layer.get("model") or "") == "substation"
            and isinstance(layer.get("coord"), list)
            and len(layer["coord"]) >= 2
        ]
        for idx, layer in enumerate(layers):
            ltype = str(layer.get("type") or "")
            if (
                ltype in {"pin_label", "glow_label"}
                and cam_points
                and isinstance(layer.get("coord"), list)
                and len(layer["coord"]) >= 2
            ):
                raw_t0 = layer.get("start_s")
                raw_t1 = layer.get("end_s")
                t0 = float(0.0 if raw_t0 is None else raw_t0)
                t1 = float((dur if dur > 0 else t0 + 1.0) if raw_t1 is None else raw_t1)
                t_mid = 0.5 * (t0 + t1)
                nearest_cam = min(cam_points, key=lambda item: abs(item[0] - t_mid))
                xp, yp = _approx_viewport_pct(
                    float(layer["coord"][0]),
                    float(layer["coord"][1]),
                    nearest_cam[1],
                    nearest_cam[2],
                    nearest_cam[3],
                    width,
                    height,
                    dx=float(layer.get("dx") or 0.0),
                    dy=float(layer.get("dy") or 0.0),
                )
                if -0.25 <= xp <= 1.25 and -0.25 <= yp <= 1.25:
                    if xp < 0.06 or xp > 0.94:
                        warnings.append(
                            f"[{act_id}] layer #{idx} ({ltype}) projected x={xp:.2f} nears "
                            "viewport side margin (<0.06 or >0.94); adjust dx or x_pct."
                        )
                    if height > width and 0.66 <= yp <= 0.84:
                        warnings.append(
                            f"[{act_id}] layer #{idx} ({ltype}) projected y={yp:.2f} enters "
                            "protected caption band [0.66, 0.84]."
                        )
            elif ltype == "cable_3d" and substations:
                raw_coords = (
                    _resolve_geom_ref(vectors, layer.get("coords_ref"))
                    or layer.get("coords")
                    or []
                )
                if isinstance(raw_coords, list) and len(raw_coords) >= 3:
                    for wi in range(1, len(raw_coords) - 1):
                        wp = raw_coords[wi]
                        if not isinstance(wp, list) or len(wp) < 2:
                            continue
                        for sc in substations:
                            dist_m = _haversine_m(
                                float(wp[0]), float(wp[1]), float(sc[0]), float(sc[1])
                            )
                            if dist_m < 250.0:
                                warnings.append(
                                    f"[{act_id}] layer #{idx} cable_3d intermediate waypoint "
                                    f"#{wi} passes within {dist_m:.0f}m of substation center; "
                                    "route clear of structure roof."
                                )
                                break

        # Static 3D model anti-stacking check: warn when time-overlapping models collide on screen
        static_models: list[tuple[int, list[float], float, float]] = []
        for idx, layer in enumerate(layers):
            if str(layer.get("type") or "") != "model_3d":
                continue
            coord = layer.get("coord")
            if layer.get("path") or not (isinstance(coord, list) and len(coord) >= 2):
                continue
            t0 = float(0.0 if layer.get("start_s") is None else layer["start_s"])
            raw_end = layer.get("end_s")
            t1 = float((dur if dur > 0 else t0 + 1.0) if raw_end is None else raw_end)
            static_models.append((idx, [float(coord[0]), float(coord[1])], t0, t1))
        for i in range(len(static_models)):
            idx_a, coord_a, a0, a1 = static_models[i]
            for j in range(i + 1, len(static_models)):
                idx_b, coord_b, b0, b1 = static_models[j]
                ov_start = max(a0, b0)
                ov_end = min(a1, b1)
                if ov_end <= ov_start + 1e-6:
                    continue
                if cam_points:
                    t_mid = 0.5 * (ov_start + ov_end)
                    nearest_cam = min(cam_points, key=lambda item: abs(item[0] - t_mid))
                    xa, ya = _approx_viewport_pct(
                        coord_a[0],
                        coord_a[1],
                        nearest_cam[1],
                        nearest_cam[2],
                        nearest_cam[3],
                        width,
                        height,
                    )
                    xb, yb = _approx_viewport_pct(
                        coord_b[0],
                        coord_b[1],
                        nearest_cam[1],
                        nearest_cam[2],
                        nearest_cam[3],
                        width,
                        height,
                    )
                    dist_px = math.hypot((xa - xb) * width, (ya - yb) * height)
                    if dist_px < 52.0:
                        warnings.append(
                            f"[{act_id}] model_3d layers #{idx_a} and #{idx_b} stack/overlap "
                            f"spatially ({dist_px:.0f} px apart at t={t_mid:.2f}s); separate "
                            "coordinates or stagger timing."
                        )
                elif _haversine_m(coord_a[0], coord_a[1], coord_b[0], coord_b[1]) < 100.0:
                    warnings.append(
                        f"[{act_id}] model_3d layers #{idx_a} and #{idx_b} stack/overlap at "
                        "nearly identical coordinates; separate coordinates or stagger timing."
                    )

        # Label overlap detection: warn when two concurrent labels project onto the same spot
        placed_labels: list[tuple[int, str, float, float, float, float]] = []
        if cam_points:
            for idx, layer in enumerate(layers):
                ltype = str(layer.get("type") or "")
                if ltype not in {"glow_label", "pin_label"}:
                    continue
                t0 = float(0.0 if layer.get("start_s") is None else layer["start_s"])
                raw_end = layer.get("end_s")
                t1 = float((dur if dur > 0 else t0 + 1.0) if raw_end is None else raw_end)
                t_mid = 0.5 * (t0 + t1)
                if isinstance(layer.get("coord"), list) and len(layer["coord"]) >= 2:
                    nearest_cam = min(cam_points, key=lambda item: abs(item[0] - t_mid))
                    xp, yp = _approx_viewport_pct(
                        float(layer["coord"][0]),
                        float(layer["coord"][1]),
                        nearest_cam[1],
                        nearest_cam[2],
                        nearest_cam[3],
                        width,
                        height,
                        dx=float(layer.get("dx") or 0.0),
                        dy=float(layer.get("dy") or 0.0),
                    )
                elif layer.get("x_pct") is not None or layer.get("y_pct") is not None:
                    xp = float(layer.get("x_pct", 0.5))
                    yp = float(layer.get("y_pct", 0.25))
                else:
                    continue
                lbl = str(layer.get("text") or ltype).replace("\n", " ")[:24]
                placed_labels.append((idx, lbl, xp * width, yp * height, t0, t1))
        for i in range(len(placed_labels)):
            ia, la, xa, ya, a0, a1 = placed_labels[i]
            for j in range(i + 1, len(placed_labels)):
                ib, lb, xb, yb, b0, b1 = placed_labels[j]
                if min(a1, b1) <= max(a0, b0) + 0.15:
                    continue
                if abs(xa - xb) < 95.0 and abs(ya - yb) < 48.0:
                    dx_px = abs(xa - xb)
                    dy_px = abs(ya - yb)
                    warnings.append(
                        f"[{act_id}] labels #{ia} ({la!r}) and #{ib} ({lb!r}) overlap closely "
                        f"({dx_px:.0f}x{dy_px:.0f} px); separate positions or stagger."
                    )

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


