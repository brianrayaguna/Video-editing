"""Brand template catalog helpers: token resolution, kind mapping, variable checks."""

from __future__ import annotations

import re
from typing import Any, Literal

from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    BrandTemplateEntry,
    BrandTemplateVariable,
    OverlayCompositionOp,
)

OverlayKind = Literal[
    "caption_rail", "kinetic_callout", "lower_third", "data_card", "title_scene", "full_scene"
]

TEMPLATE_KIND_MAP: dict[str, OverlayKind] = {
    "caption_rail": "caption_rail",
    "amber_fact_card": "data_card",
    "broadcast_bug": "lower_third",
    "distance_metric": "kinetic_callout",
    "tabular_metric": "kinetic_callout",
    "region_highlight": "full_scene",
}

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def catalog_by_id(catalog: BrandTemplateCatalog) -> dict[str, BrandTemplateEntry]:
    return {entry.template_id: entry for entry in catalog.templates}


def resolve_token_ref(policy: BrandStylePolicy, token_ref: str | None) -> Any | None:
    """Resolve a dotted soft-prior token path such as `palette_roles.accent`."""
    if not token_ref:
        return None
    parts = [p for p in token_ref.split(".") if p]
    if not parts:
        return None
    visual = policy.soft_priors.visual_tokens
    roots: dict[str, Any] = {
        "palette_roles": visual.palette_roles.model_dump(exclude_none=True),
        "typography": visual.typography.model_dump(exclude_none=True),
        "motion_style": visual.motion_style.model_dump(exclude_none=True),
        "audio_style": policy.soft_priors.audio_style.model_dump(exclude_none=True),
    }
    cursor: Any = roots
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def resolve_template_variables(
    entry: BrandTemplateEntry,
    policy: BrandStylePolicy,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill typed template variables from defaults, token_ref, then overrides."""
    resolved: dict[str, Any] = {}
    overrides = overrides or {}
    for var in entry.variables:
        value: Any | None = None
        if var.id in overrides:
            value = overrides[var.id]
        elif var.token_ref:
            value = resolve_token_ref(policy, var.token_ref)
        if value is None and var.default is not None:
            value = var.default
        if value is not None:
            resolved[var.id] = value
    return resolved


def overlay_kind_for_template(template_id: str, fallback: OverlayKind) -> OverlayKind:
    return TEMPLATE_KIND_MAP.get(template_id, fallback)


def motion_props_from_policy(policy: BrandStylePolicy) -> dict[str, Any]:
    motion = policy.soft_priors.visual_tokens.motion_style
    lo, hi = motion.entrance_ms_range
    entrance_ms = int(round((lo + hi) / 2))
    props: dict[str, Any] = {
        "easing_feel": motion.easing_feel,
        "entrance_ms": entrance_ms,
    }
    if motion.punch_in_scale_range:
        props["punch_in_scale"] = round(
            (motion.punch_in_scale_range[0] + motion.punch_in_scale_range[1]) / 2.0, 3
        )
    return props


def _type_ok(var: BrandTemplateVariable, value: Any) -> bool:
    if var.type == "string":
        return isinstance(value, str)
    if var.type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if var.min is not None and float(value) < var.min:
            return False
        if var.max is not None and float(value) > var.max:
            return False
        return True
    if var.type == "boolean":
        return isinstance(value, bool)
    if var.type == "color":
        return isinstance(value, str) and bool(_HEX_RE.fullmatch(value.strip()))
    if var.type == "image":
        return isinstance(value, str) and len(value) > 0
    if var.type == "enum":
        return isinstance(value, str) and value in (var.enum_values or [])
    return False


def validate_overlay_template(
    overlay: OverlayCompositionOp,
    catalog: BrandTemplateCatalog | None,
) -> list[str]:
    """Return human-readable errors for template_id / variables on one overlay."""
    if not overlay.template_id:
        return []
    if catalog is None:
        return [f"{overlay.overlay_id}: template_id set but no brand template catalog provided"]

    entry = catalog_by_id(catalog).get(overlay.template_id)
    if entry is None:
        return [f"{overlay.overlay_id}: unknown template_id {overlay.template_id!r}"]

    declared = {var.id: var for var in entry.variables}
    values = dict(overlay.variables or {})
    # Allow props to carry declared variables when variables dict is sparse.
    for key, val in (overlay.props or {}).items():
        if key in declared and key not in values:
            values[key] = val

    errors: list[str] = []
    for key in values:
        if key not in declared:
            errors.append(
                f"{overlay.overlay_id}: unknown template variable {key!r} for {overlay.template_id}"
            )
    for var_id, var in declared.items():
        if var_id not in values:
            continue
        if not _type_ok(var, values[var_id]):
            errors.append(
                f"{overlay.overlay_id}: variable {var_id!r} failed type/range check "
                f"({var.type}) for {overlay.template_id}"
            )
    expected_kind = TEMPLATE_KIND_MAP.get(overlay.template_id)
    if expected_kind is not None and overlay.kind != expected_kind:
        errors.append(
            f"{overlay.overlay_id}: kind {overlay.kind!r} incompatible with "
            f"template_id {overlay.template_id!r} (expected {expected_kind!r})"
        )
    return errors
