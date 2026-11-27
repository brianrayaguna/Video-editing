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
    assert len(payload["exemplar_bank"]) >= 25
    assert len(payload["grammar_triggers"]) >= 20


def test_geoverum_catalog_editorial_templates_resolve_and_validate() -> None:
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
    ids = {t.template_id for t in catalog.templates}
    assert len(catalog.templates) == 32
    expected_new = {
        "coordinate_pin_callout",
        "chevron_flow_band",
        "cutaway_height_gauge",
        "dual_unit_distance_bracket",
        "blueprint_tabletop_frame",
        "split_wipe_divider",
        "historical_parchment_plate",
        "myth_debunk_badge",
        "organic_focus_lasso",
        "dual_metric_compare",
        "physical_gauge_callout",
        "multi_panel_split",
        "scale_ladder_and_bands",
        "kinetic_portal_title",
        "soft_curtain_transition",
        "demographic_icon_grid",
        "vignette_mood_dip",
        "map_pin_badge",
        "radar_pulse_rings",
        "migrant_dot_flow",
        "weather_cloud_rain",
        "archival_stamp_impact",
    }
    assert expected_new.issubset(ids)

    bp_entry = next(e for e in catalog.templates if e.template_id == "blueprint_tabletop_frame")
    bp_resolved = resolve_template_variables(bp_entry, policy, {})
    assert bp_resolved["tilt_deg"] == 0
    assert bp_resolved["variant"] == "editorial_grid"

    parch_entry = next(
        e for e in catalog.templates if e.template_id == "historical_parchment_plate"
    )
    parch_resolved = resolve_template_variables(parch_entry, policy, {})
    assert parch_resolved["tilt_deg"] == 0
    assert parch_resolved["variant"] == "era_stamp"

    kicker_banned_ids = {
        "chapter_morph_card",
        "kinetic_portal_title",
        "blueprint_tabletop_frame",
        "cross_section_diagram",
        "comparison_bar_chart",
    }
    for tid in kicker_banned_ids:
        entry = next(e for e in catalog.templates if e.template_id == tid)
        var_ids = {v.id for v in entry.variables}
        assert "kicker" not in var_ids, f"Eyebrow kicker variable must not exist in {tid}"

    for entry in catalog.templates:
        resolved = resolve_template_variables(entry, policy, {})
        ov = OverlayCompositionOp(
            overlay_id=f"ov_{entry.template_id}",
            kind=entry.overlay_kind,
            timeline_start_s=0.0,
            timeline_duration_s=3.0,
            transparent=True,
            template_id=entry.template_id,
            variables=resolved,
            props=resolved,
        )
        assert validate_overlay_template(ov, catalog) == []


def test_geoverum_type_scale_and_template_typography_hygiene() -> None:
    import re

    root = find_repo_root()
    policy = BrandStylePolicy.model_validate_json(
        (root / "profiles" / "brands" / "geoverum" / "brand_style_policy.json").read_text(
            encoding="utf-8"
        )
    )
    typo = policy.soft_priors.visual_tokens.typography
    assert typo.type_scale is not None
    assert typo.base_rem_px == 16
    assert typo.caption_letter_spacing_em is not None and typo.caption_letter_spacing_em > 0
    assert policy.hard_guardrails.min_wcag_contrast_small_text == 7.0

    scale = typo.type_scale
    assert scale.hero is not None and scale.body is not None and scale.micro is not None
    assert scale.hero.line_height < scale.body.line_height <= scale.micro.line_height
    assert (
        scale.hero.letter_spacing_em
        < scale.body.letter_spacing_em
        < scale.micro.letter_spacing_em
    )

    comp_dir = root / "profiles" / "brands" / "geoverum" / "templates" / "components"
    for html_path in sorted(comp_dir.glob("*.html")):
        text = html_path.read_text(encoding="utf-8")
        style_blocks = re.findall(r"<style[^>]*>([\s\S]*?)</style>", text, re.IGNORECASE)
        css = "\n".join(style_blocks)
        if "font-family" not in css:
            continue
        assert "font-kerning: normal" in css, f"{html_path.name} missing font-kerning: normal"
        # Check CSS blocks with template placeholders preserved via sentinel replacement.
        sentinel = re.sub(r"\{\{([A-Z0-9_|.-]+)\}\}", r"__TOK_\1__", css)
        for sel, body in re.findall(r"([^{}@]+)\{([^{}]+)\}", sentinel):
            sel_clean = sel.strip()
            if sel_clean.startswith("#root"):
                continue
            size_m = re.search(r"font-size\s*:\s*(?:calc\(\s*)?(\d+(?:\.\d+)?)px", body)
            size_px = float(size_m.group(1)) if size_m else None
            wt_m = re.search(r"font-weight\s*:\s*(\d{3})\b", body)
            wt = int(wt_m.group(1)) if wt_m else None
            ls_m = re.search(r"letter-spacing\s*:\s*(-?\d+(?:\.\d+)?)(em|px)", body)
            if "__TOK_DISPLAY_FONT__" in body:
                assert wt is not None, (
                    f"{html_path.name} selector {sel_clean!r} uses DISPLAY_FONT without font-weight"
                )
                assert wt <= 800, (
                    f"{html_path.name} selector {sel_clean!r} requests weight {wt} > 800"
                )
            if size_px is not None and size_px <= 34 and ls_m is not None:
                assert float(ls_m.group(1)) >= 0, (
                    f"{html_path.name} selector {sel_clean!r} ({size_px}px) has negative tracking"
                )
