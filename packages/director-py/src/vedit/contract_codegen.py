"""Deterministic JSON Schema (Draft 2020-12) to TypeScript contract generator.

`contracts/*.schema.json` is the single source of truth for cross-runtime types.
This module compiles `contracts/platform_target.schema.json` and
`contracts/edit_plan.schema.json` into `packages/hf-compiler-ts/src/contracts.ts`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root, load_schema

_HEADER = """\
/**
 * AUTO-GENERATED FILE — DO NOT EDIT MANUALLY.
 *
 * Generated from `contracts/platform_target.schema.json` and
 * `contracts/edit_plan.schema.json` via `vedit contracts generate-ts`.
 */
"""


def _ts_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value)


def _ts_type_from_schema(
    prop: dict[str, Any],
    *,
    named_refs: dict[int, str],
) -> str:
    ref_name = named_refs.get(id(prop))
    if ref_name is not None:
        raw_type = prop.get("type")
        if isinstance(raw_type, list) and "null" in raw_type:
            return f"{ref_name} | null"
        return ref_name

    if "const" in prop:
        return _ts_literal(prop["const"])

    if "enum" in prop:
        members = [_ts_literal(v) for v in prop["enum"]]
        return " | ".join(members)

    raw_type = prop.get("type")
    nullable = False
    base_type: str | None = None
    if isinstance(raw_type, list):
        nullable = "null" in raw_type
        non_null = [t for t in raw_type if t != "null"]
        base_type = non_null[0] if non_null else None
    elif isinstance(raw_type, str):
        base_type = raw_type

    if base_type == "string":
        ts = "string"
    elif base_type in ("number", "integer"):
        ts = "number"
    elif base_type == "boolean":
        ts = "boolean"
    elif base_type == "array":
        items = prop.get("items")
        if isinstance(items, dict):
            item_ts = _ts_type_from_schema(items, named_refs=named_refs)
            ts = f"({item_ts})[]" if " | " in item_ts else f"{item_ts}[]"
        else:
            ts = "unknown[]"
    elif base_type == "object":
        if "properties" in prop:
            ts = _inline_object_ts(prop, named_refs=named_refs)
        else:
            ts = "Record<string, unknown>"
    else:
        ts = "unknown"

    return f"{ts} | null" if nullable else ts


def _inline_object_ts(schema: dict[str, Any], *, named_refs: dict[int, str]) -> str:
    required = set(schema.get("required") or [])
    props = schema.get("properties") or {}
    fields: list[str] = []
    for key, prop in props.items():
        opt = "" if key in required else "?"
        ts_t = _ts_type_from_schema(prop, named_refs=named_refs)
        fields.append(f"{key}{opt}: {ts_t}")
    return "{ " + "; ".join(fields) + " }"


def _emit_type_alias(name: str, values: list[Any]) -> str:
    literals = [_ts_literal(v) for v in values]
    one_line = f"export type {name} = {' | '.join(literals)};"
    if len(one_line) <= 96:
        return one_line
    body = "\n".join(f"  | {lit}" for lit in literals)
    return f"export type {name} =\n{body};"


def _emit_interface(
    name: str,
    schema: dict[str, Any],
    *,
    named_refs: dict[int, str],
) -> str:
    required = set(schema.get("required") or [])
    props = schema.get("properties") or {}
    lines = [f"export interface {name} {{"]
    for key, prop in props.items():
        opt = "" if key in required else "?"
        ts_t = _ts_type_from_schema(prop, named_refs=named_refs)
        lines.append(f"  {key}{opt}: {ts_t};")
    lines.append("}")
    return "\n".join(lines)


def generate_ts_contracts(repo_root: Path | None = None) -> str:
    """Compile `platform_target.schema.json` and `edit_plan.schema.json` into TypeScript."""
    root = repo_root or find_repo_root()
    platform_schema = load_schema("platform_target.schema.json", repo_root=root)
    edit_plan_schema = load_schema("edit_plan.schema.json", repo_root=root)

    pt_props = platform_schema["properties"]
    ep_props = edit_plan_schema["properties"]

    timebase_schema = pt_props["timebase"]
    video_master_schema = pt_props["video"]
    audio_master_schema = pt_props["audio"]
    safe_zone_schema = pt_props["safe_zone"]

    asset_item = ep_props["assets"]["items"]
    video_clip_item = ep_props["video_tracks"]["items"]
    overlay_item = ep_props["overlay_compositions"]["items"]
    audio_track_item = ep_props["audio_tracks"]["items"]

    bbox_item = video_clip_item["properties"]["subject_safe_boxes"]["items"]
    cc_schema = video_clip_item["properties"]["color_correction"]
    cg_schema = video_clip_item["properties"]["color_grade"]
    kf_item = overlay_item["properties"]["track_keyframes"]["items"]

    render_strategy_prop = ep_props["render_strategy"]
    asset_kind_prop = asset_item["properties"]["kind"]
    clip_role_prop = video_clip_item["properties"]["role"]
    overlay_kind_prop = overlay_item["properties"]["kind"]
    safe_band_prop = overlay_item["properties"]["safe_band"]

    named_refs: dict[int, str] = {
        id(render_strategy_prop): "RenderStrategy",
        id(asset_kind_prop): "AssetKind",
        id(clip_role_prop): "ClipRole",
        id(overlay_kind_prop): "OverlayKind",
        id(safe_band_prop): "SafeBand",
        id(timebase_schema): "TimebaseSpec",
        id(ep_props["timebase"]): "TimebaseSpec",
        id(video_master_schema): "VideoMasteringSpec",
        id(audio_master_schema): "AudioMasteringSpec",
        id(safe_zone_schema): "SafeZoneMargins",
        id(bbox_item): "BoundingBox",
        id(asset_item): "AssetRef",
        id(cc_schema): "ColorCorrectionSpec",
        id(cg_schema): "ColorGradeSpec",
        id(video_clip_item): "VideoClipOp",
        id(kf_item): "OverlayTrackKeyframe",
        id(overlay_item): "OverlayCompositionOp",
        id(audio_track_item): "AudioTrackOp",
    }

    sections: list[str] = [
        _HEADER.rstrip(),
        "\n".join(
            [
                _emit_type_alias("RenderStrategy", render_strategy_prop["enum"]),
                _emit_type_alias("AssetKind", asset_kind_prop["enum"]),
                _emit_type_alias("ClipRole", clip_role_prop["enum"]),
                _emit_type_alias("OverlayKind", overlay_kind_prop["enum"]),
                _emit_type_alias("SafeBand", safe_band_prop["enum"]),
            ]
        ),
        _emit_interface("TimebaseSpec", timebase_schema, named_refs=named_refs),
        _emit_interface("SafeZoneMargins", safe_zone_schema, named_refs=named_refs),
        _emit_interface("VideoMasteringSpec", video_master_schema, named_refs=named_refs),
        _emit_interface("AudioMasteringSpec", audio_master_schema, named_refs=named_refs),
        _emit_interface("PlatformTarget", platform_schema, named_refs=named_refs),
        (
            'export type PlatformCanvasTarget = Omit<PlatformTarget, "video" | "audio"> &\n'
            '  Partial<Pick<PlatformTarget, "video" | "audio">>;'
        ),
        _emit_interface("BoundingBox", bbox_item, named_refs=named_refs),
        _emit_interface("AssetRef", asset_item, named_refs=named_refs),
        _emit_interface("ColorCorrectionSpec", cc_schema, named_refs=named_refs),
        _emit_interface("ColorGradeSpec", cg_schema, named_refs=named_refs),
        _emit_interface("VideoClipOp", video_clip_item, named_refs=named_refs),
        _emit_interface("OverlayTrackKeyframe", kf_item, named_refs=named_refs),
        _emit_interface("OverlayCompositionOp", overlay_item, named_refs=named_refs),
        _emit_interface("AudioTrackOp", audio_track_item, named_refs=named_refs),
        _emit_interface("EditPlan", edit_plan_schema, named_refs=named_refs),
    ]
    return "\n\n".join(sections) + "\n"
