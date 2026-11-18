"""Brand template binding and soft-prior helper tests."""

from __future__ import annotations

import json

from vedit.contracts import find_repo_root, load_brand_template_catalog
from vedit.director.templates import (
    motion_props_from_policy,
    resolve_template_variables,
    validate_overlay_template,
)
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    OverlayCompositionOp,
)


def test_geoverum_token_ref_resolution_and_invalid_variable() -> None:
    root = find_repo_root()
    policy = BrandStylePolicy.model_validate_json(
        (root / "profiles" / "brands" / "geoverum" / "brand_style_policy.json").read_text(
            encoding="utf-8"
        )
    )
    catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(
            root / "profiles" / "brands" / "geoverum" / "templates" / "catalog.json",
            repo_root=root,
        )
    )
    entry = next(e for e in catalog.templates if e.template_id == "caption_rail")
    resolved = resolve_template_variables(entry, policy, {"text": "Hello"})
    assert resolved["text"] == "Hello"
    assert resolved["fg_color"] == policy.soft_priors.visual_tokens.palette_roles.ink
    assert resolved["bg_color"] == policy.soft_priors.visual_tokens.palette_roles.ground

    ok_overlay = OverlayCompositionOp(
        overlay_id="cap_ok",
        kind="caption_rail",
        timeline_start_s=0.0,
        timeline_duration_s=1.0,
        transparent=True,
        template_id="caption_rail",
        variables=resolved,
        props=resolved,
    )
    assert validate_overlay_template(ok_overlay, catalog) == []

    bad_overlay = OverlayCompositionOp(
        overlay_id="cap_bad",
        kind="caption_rail",
        timeline_start_s=0.0,
        timeline_duration_s=1.0,
        transparent=True,
        template_id="caption_rail",
        variables={**resolved, "extra_slot": "nope"},
        props={},
    )
    errors = validate_overlay_template(bad_overlay, catalog)
    assert errors
    assert any("unknown template variable" in msg for msg in errors)

    motion = motion_props_from_policy(policy)
    assert "entrance_ms" in motion
    assert "easing_feel" in motion


def test_geoverum_playbook_exemplar_count() -> None:
    root = find_repo_root()
    payload = json.loads(
        (root / "profiles" / "brands" / "geoverum" / "editorial_playbook.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(payload["exemplar_bank"]) == 16
    assert len(payload["grammar_triggers"]) == 19
