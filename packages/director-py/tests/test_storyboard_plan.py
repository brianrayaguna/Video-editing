"""Storyboard realisation: beats become template-bound overlays placed clear of captions."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_director_verifier import _build_fixture_bundle

from vedit.contracts import find_repo_root, load_brand_template_catalog, load_platform_targets
from vedit.director.planner import build_edit_plan
from vedit.director.storyboard import idioms_path, load_directing_idioms, scaffold_storyboard
from vedit.director.storyboard_plan import (
    check_realization_catalog,
    fit_overlays,
    storyboard_overlays,
)
from vedit.metrics import resolve_overlay_rect
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
)


@pytest.fixture(scope="module")
def brand() -> tuple[dict, BrandTemplateCatalog, BrandStylePolicy, PlatformTarget]:
    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(gv_dir / "templates" / "catalog.json", repo_root=root)
    )
    policy = BrandStylePolicy.model_validate_json(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8")
    )
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    return load_directing_idioms(idioms_path("geoverum")), catalog, policy, target


def _transcript() -> dict:
    text = (
        "This man has been walking for 27 years, the only person in history. "
        "In 1998 he left Chile. Why did he never stop? Rebels arrested him in Panama, "
        "then he walked north to Alaska."
    )
    words, t = [], 0.0
    for tok in text.split():
        words.append({"text": tok, "start_s": round(t, 3), "end_s": round(t + 0.3, 3)})
        t += 0.38
    return {
        "source_hash": "abcdef12",
        "provider": "test",
        "language": "en",
        "duration_s": round(t, 3),
        "text": text,
        "words": words,
    }


def _overlay(oid: str, band: str, start: float, dur: float, **props) -> OverlayCompositionOp:
    return OverlayCompositionOp(
        overlay_id=oid,
        kind="kinetic_callout",
        timeline_start_s=start,
        timeline_duration_s=dur,
        transparent=True,
        safe_band=band,
        props=props,
    )


def test_geoverum_realisation_map_matches_catalog(brand) -> None:
    idioms, catalog, _, _ = brand
    assert check_realization_catalog(idioms, catalog) == []


def test_storyboard_overlays_bind_templates_and_report_scene_beats(brand) -> None:
    idioms, catalog, policy, target = brand
    sb = scaffold_storyboard(_transcript(), idioms, project_id="demo", pacing="dense")
    overlays, report = storyboard_overlays(
        sb, idioms, catalog, policy, frame=(target.width, target.height), safe_zone=target.safe_zone
    )
    assert overlays and report["unrealised_devices"] == []
    assert report["overlay_beats"] + len(report["scene_beats"]) <= len(sb["beats"])
    entries = {e.template_id: e for e in catalog.templates}
    for ov in overlays:
        assert ov.overlay_id.startswith("sb_")
        assert ov.template_id in entries
        declared = {v.id: v for v in entries[ov.template_id].variables}
        for key, value in ov.variables.items():
            var = declared[key]
            if var.type == "number" and isinstance(value, int | float):
                assert var.min is None or value >= var.min
                assert var.max is None or value <= var.max
        box = ov.props.get("box")
        if box:
            sz = target.safe_zone
            assert box["top"] >= sz.top_pct - 1e-6
            assert box["bottom"] <= 1.0 - sz.bottom_pct + 1e-6
    # One in, one out: overlays sharing a band never overlap in time.
    by_band: dict[str, list[OverlayCompositionOp]] = {}
    for ov in overlays:
        by_band.setdefault(ov.safe_band, []).append(ov)
    for group in by_band.values():
        for a, b in zip(group, group[1:], strict=False):
            assert a.timeline_start_s + a.timeline_duration_s <= b.timeline_start_s + 1e-6


def test_fit_overlays_moves_band_overlays_and_drops_blocked_anchors(brand) -> None:
    _, _, _, target = brand
    sz = target.safe_zone
    caption = _overlay("cap_001", "lower_third", 0.0, 4.0)
    band_card = _overlay("sb_b001", "lower_third", 1.0, 2.0)
    cap_rect = resolve_overlay_rect("lower_third", sz)
    box = {"top": cap_rect.top, "bottom": cap_rect.bottom, "left": 0.3, "right": 0.6}
    pin = _overlay("sb_b002", "center_safe", 1.5, 1.0, box=box)
    clear_pin = _overlay(
        "sb_b003",
        "center_safe",
        1.5,
        1.0,
        box={"top": 0.3, "bottom": 0.38, "left": 0.3, "right": 0.6},
    )
    placed, dropped = fit_overlays([band_card, pin, clear_pin], [caption], sz)
    ids = {ov.overlay_id: ov for ov in placed}
    assert ids["sb_b001"].safe_band != "lower_third"
    assert dropped == ["sb_b002"]
    assert "sb_b003" in ids


def test_build_edit_plan_realises_storyboard_without_collisions(brand, tmp_path: Path) -> None:
    idioms, catalog, policy, target = brand
    probe, _, _, _ = _build_fixture_bundle(tmp_path)
    transcript_raw = _transcript()
    transcript = NormalizedTranscript.model_validate(transcript_raw)
    sb = scaffold_storyboard(transcript_raw, idioms, project_id="demo", pacing="dense")
    extra, _ = storyboard_overlays(
        sb,
        idioms,
        catalog,
        policy,
        frame=(target.width, target.height),
        duration_s=probe.container.duration_s,
        safe_zone=target.safe_zone,
    )
    plan, report = build_edit_plan(
        job_id="job_sb",
        project_id="demo",
        probe=probe,
        policy=policy,
        platform_target=target,
        transcript=transcript,
        template_catalog=catalog,
        extra_overlays=extra,
    )
    ids = [ov.overlay_id for ov in plan.overlay_compositions]
    assert any(i.startswith("sb_") for i in ids)
    assert not any(i.startswith("card_") for i in ids), "storyboard owns number cards"
    sb_issues = [
        e
        for e in report.errors
        if e.target_id.startswith("sb_")
        or (e.code == "OVERLAY_COLLISION" and "sb_" in e.message)
    ]
    assert sb_issues == []
