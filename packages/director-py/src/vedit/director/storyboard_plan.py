"""Realise storyboard beats as EditPlan overlays through the brand's device map.

Each beat's `device` is looked up in `directing_idioms.device_realization`:

- `scene` devices (route draws, fills, camera moves, cutaways) are drawn by the map or footage
  scene; they are listed in the report so the scene builder can confirm coverage.
- `overlay` devices become `OverlayCompositionOp`s bound to a brand template. Variable bindings
  are literals or `$field` references resolved from the beat; numbers are clamped to the
  template's declared range and unknown variables are dropped, so every overlay passes template
  verification.

Overlays share screen bands one in, one out: a new overlay in the same safe band ends the
previous one, keeping a single reading order. Overlays bound to a screen anchor (a pin or ring
centred on a place) carry an explicit `box` around that anchor so collision checks use the real
footprint instead of a whole band.

`fit_overlays` places realised overlays against the overlays the planner already built
(captions): each keeps its anchor box or the first band whose rectangle stays clear of every
time-overlapping overlay; one that fits nowhere is left out, and the caller reports it.
"""

from __future__ import annotations

import re
from typing import Any

from vedit.director.templates import catalog_by_id, resolve_template_variables
from vedit.metrics import NormRect, intervals_overlap, resolve_overlay_rect
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    OverlayCompositionOp,
    SafeZoneMargins,
)

_NUM = re.compile(r"\d[\d.,]*%?")
_YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
_BANDS = {"lower_third", "upper_safe", "left_rail", "right_rail", "center_safe", "fullscreen"}
_FULLSCREEN_KINDS = {"full_scene", "title_scene"}
DEFAULT_ANCHOR_PCT = (50.0, 42.0)
ANCHOR_KEYS = (("anchor_x_pct", "anchor_y_pct"), ("center_x_pct", "center_y_pct"))
ANCHOR_BOX_W, ANCHOR_BOX_H = 0.34, 0.08
MAX_OVERLAP = 0.25
BAND_ORDER = ("upper_safe", "center_safe", "right_rail", "left_rail", "lower_third")


class StoryboardPlanError(ValueError):
    """Raised when a storyboard device has no realisation or references a missing template."""


def _bind(value: Any, beat: dict[str, Any], frame: tuple[int, int]) -> Any:
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    callout = (beat.get("callouts") or [{}])[0]
    clause = beat.get("clause", "")
    sync = beat.get("sync_word", "")
    xy = callout.get("xy")
    x_pct = round(100.0 * xy[0] / frame[0], 1) if xy else DEFAULT_ANCHOR_PCT[0]
    y_pct = round(100.0 * xy[1] / frame[1], 1) if xy else DEFAULT_ANCHOR_PCT[1]
    number = _NUM.search(sync) or _NUM.search(clause)
    year = _YEAR.search(sync) or _YEAR.search(clause)
    fields: dict[str, Any] = {
        "$clause": clause,
        "$sync_word": sync,
        "$sync_word_upper": sync.upper(),
        "$number": number.group(0) if number else sync,
        "$year": year.group(0) if year else sync,
        "$callout_text": callout.get("text", sync),
        "$x_pct": x_pct,
        "$y_pct": y_pct,
        "$size_px": callout.get("size_px"),
        "$story_need": beat.get("story_need", ""),
    }
    if value not in fields:
        raise StoryboardPlanError(f"unknown binding {value!r}")
    return fields[value]


def storyboard_overlays(
    storyboard: dict[str, Any],
    idioms: dict[str, Any],
    catalog: BrandTemplateCatalog,
    policy: BrandStylePolicy,
    *,
    frame: tuple[int, int] = (1080, 1920),
    duration_s: float | None = None,
    safe_zone: SafeZoneMargins | None = None,
) -> tuple[list[OverlayCompositionOp], dict[str, Any]]:
    """Turn storyboard beats into template-bound overlays; report scene-realised beats."""
    realization = idioms.get("device_realization") or {}
    entries = catalog_by_id(catalog)
    overlays: list[OverlayCompositionOp] = []
    scene_beats: list[dict[str, Any]] = []
    unrealised: list[str] = []
    end_limit = duration_s if duration_s is not None else storyboard.get("duration_s", 1e9)
    for beat in sorted(storyboard["beats"], key=lambda b: b["start_s"]):
        rule = realization.get(beat["device"])
        if rule is None:
            unrealised.append(beat["device"])
            continue
        if rule["surface"] == "scene":
            scene_beats.append({"beat_id": beat["beat_id"], "device": beat["device"],
                                "start_s": beat["start_s"], "end_s": beat["end_s"]})
            continue
        entry = entries.get(rule.get("template_id", ""))
        if entry is None:
            raise StoryboardPlanError(
                f"device {beat['device']!r} maps to unknown template {rule.get('template_id')!r}"
            )
        declared = {v.id: v for v in entry.variables}
        bound: dict[str, Any] = {}
        for key, raw in (rule.get("variables") or {}).items():
            var = declared.get(key)
            value = _bind(raw, beat, frame)
            if var is None or value is None:
                continue
            if var.type == "number":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if var.min is not None:
                    value = max(value, var.min)
                if var.max is not None:
                    value = min(value, var.max)
            elif var.type in {"string", "enum"}:
                value = str(value)
                if var.type == "enum" and value not in (var.enum_values or []):
                    continue
            bound[key] = value
        variables = resolve_template_variables(entry, policy, bound)
        start = float(beat["start_s"])
        dur = float(beat["end_s"]) - start
        dur = max(dur, float(rule.get("min_duration_s", 0.6)))
        dur = min(dur, float(rule.get("max_duration_s", 3.0)))
        dur = min(dur, end_limit - start)
        if dur <= 0.05:
            continue
        kind = entry.overlay_kind or "kinetic_callout"
        band = "fullscreen" if kind in _FULLSCREEN_KINDS else (entry.safe_band or "center_safe")
        if band not in _BANDS:
            band = "center_safe"
        props: dict[str, Any] = {"storyboard_beat_id": beat["beat_id"], "device": beat["device"]}
        box = _anchor_box(bound, safe_zone, variables=variables)
        if box is not None:
            props["box"] = box
        overlays.append(
            OverlayCompositionOp(
                overlay_id=f"sb_{beat['beat_id']}",
                kind=kind,
                timeline_start_s=round(start, 3),
                timeline_duration_s=round(dur, 3),
                transparent=kind not in _FULLSCREEN_KINDS or kind == "title_scene",
                safe_band=band,
                template_id=entry.template_id,
                variables=variables,
                props=props,
            )
        )
    # One in, one out per band.
    trimmed: list[OverlayCompositionOp] = []
    last_by_band: dict[str, int] = {}
    for ov in overlays:
        prev_idx = last_by_band.get(ov.safe_band)
        if prev_idx is not None:
            prev = trimmed[prev_idx]
            prev_end = prev.timeline_start_s + prev.timeline_duration_s
            if prev_end > ov.timeline_start_s:
                new_dur = round(max(0.05, ov.timeline_start_s - prev.timeline_start_s), 3)
                trimmed[prev_idx] = prev.model_copy(update={"timeline_duration_s": new_dur})
        last_by_band[ov.safe_band] = len(trimmed)
        trimmed.append(ov)
    report = {
        "overlay_beats": len(trimmed),
        "scene_beats": scene_beats,
        "unrealised_devices": sorted(set(unrealised)),
    }
    return trimmed, report


def _anchor_box(
    bound: dict[str, Any],
    safe_zone: SafeZoneMargins | None,
    *,
    variables: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    matched_keys: tuple[str, str] | None = None
    for kx, ky in ANCHOR_KEYS:
        if kx in bound and ky in bound:
            cx, cy = float(bound[kx]) / 100.0, float(bound[ky]) / 100.0
            matched_keys = (kx, ky)
            break
    else:
        return None
    lo_x = safe_zone.left_pct if safe_zone else 0.0
    hi_x = 1.0 - safe_zone.right_pct if safe_zone else 1.0
    lo_y = safe_zone.top_pct if safe_zone else 0.0
    hi_y = 1.0 - safe_zone.bottom_pct if safe_zone else 1.0
    left = min(max(cx - ANCHOR_BOX_W / 2, lo_x), hi_x - ANCHOR_BOX_W)
    top = min(max(cy - ANCHOR_BOX_H / 2, lo_y), hi_y - ANCHOR_BOX_H)
    if variables is not None and matched_keys is not None:
        kx, ky = matched_keys
        if kx in variables:
            variables[kx] = round((left + ANCHOR_BOX_W / 2) * 100.0, 2)
        if ky in variables:
            variables[ky] = round((top + ANCHOR_BOX_H / 2) * 100.0, 2)
    return {
        "top": round(top, 4),
        "bottom": round(top + ANCHOR_BOX_H, 4),
        "left": round(left, 4),
        "right": round(left + ANCHOR_BOX_W, 4),
    }


def _rect(ov: OverlayCompositionOp, safe_zone: SafeZoneMargins) -> NormRect | None:
    box = ov.props.get("box") if isinstance(ov.props.get("box"), dict) else None
    if ov.safe_band == "fullscreen" and box is None:
        return None
    return resolve_overlay_rect(ov.safe_band, safe_zone, explicit_box=box)


def fit_overlays(
    extra: list[OverlayCompositionOp],
    existing: list[OverlayCompositionOp],
    safe_zone: SafeZoneMargins,
    *,
    max_overlap: float = MAX_OVERLAP,
) -> tuple[list[OverlayCompositionOp], list[str]]:
    """Place `extra` overlays clear of `existing` ones; return (placed, dropped overlay ids)."""
    placed: list[OverlayCompositionOp] = []
    dropped: list[str] = []
    for ov in extra:
        if _rect(ov, safe_zone) is None:
            placed.append(ov)
            continue
        live = [
            (other, r)
            for other in (*existing, *placed)
            if intervals_overlap(
                ov.timeline_start_s,
                ov.timeline_duration_s,
                other.timeline_start_s,
                other.timeline_duration_s,
            )
            and (r := _rect(other, safe_zone)) is not None
        ]
        if isinstance(ov.props.get("box"), dict):
            candidates = [ov]
        else:
            bands = [ov.safe_band, *(b for b in BAND_ORDER if b != ov.safe_band)]
            candidates = [ov.model_copy(update={"safe_band": b}) for b in bands]
        for cand in candidates:
            rect = _rect(cand, safe_zone)
            if rect is not None and all(rect.overlap_fraction(r) <= max_overlap for _, r in live):
                placed.append(cand)
                break
        else:
            dropped.append(ov.overlay_id)
    return placed, dropped


def check_realization_catalog(idioms: dict[str, Any], catalog: BrandTemplateCatalog) -> list[str]:
    """Errors for overlay devices whose template or variables are missing from the catalog."""
    entries = catalog_by_id(catalog)
    errors: list[str] = []
    for device, rule in (idioms.get("device_realization") or {}).items():
        if rule["surface"] != "overlay":
            continue
        entry = entries.get(rule.get("template_id", ""))
        if entry is None:
            errors.append(f"device {device!r}: unknown template {rule.get('template_id')!r}")
            continue
        declared = {v.id for v in entry.variables}
        for key in rule.get("variables") or {}:
            if key not in declared:
                errors.append(f"device {device!r}: template {entry.template_id!r} has no {key!r}")
    known = {d for cls in (idioms.get("device_classes") or {}).values() for d in cls["devices"]}
    missing = sorted(known - set(idioms.get("device_realization") or {}))
    if idioms.get("device_realization") and missing:
        errors.append(f"devices without a realisation: {missing}")
    return errors
