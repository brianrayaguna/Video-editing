"""End-to-end brand neutrality tests proving core spine works with zero geospatial coupling."""

from __future__ import annotations

import json
from pathlib import Path

from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import (
    find_repo_root,
    load_brand_template_catalog,
    load_platform_targets,
    validate_brand_tree,
)
from vedit.director.idiom_registry import core_idiom_registry
from vedit.director.storyboard import check_storyboard, load_directing_idioms, scaffold_storyboard
from vedit.director.storyboard_plan import storyboard_overlays
from vedit.director.verifier import verify_edit_plan
from vedit.models import (
    AssetRef,
    BrandStylePolicy,
    BrandTemplateCatalog,
    EditPlan,
    PlatformTarget,
    VideoClipOp,
)


def test_editorial_explainer_brand_tree_and_core_spine_without_geo(tmp_path: Path) -> None:
    root = find_repo_root()
    brand_dir = root / "profiles" / "brands" / "editorial_explainer"
    validated = validate_brand_tree(brand_dir, repo_root=root)
    assert validated["brand_id"] == "editorial_explainer"
    assert validated["directing_idioms"] is not None
    assert validated["templates"] is not None

    policy = BrandStylePolicy.model_validate(
        json.loads((brand_dir / "brand_style_policy.json").read_text(encoding="utf-8"))
    )
    idioms = load_directing_idioms(brand_dir / "directing_idioms.json")
    catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(brand_dir / "templates" / "catalog.json", repo_root=root)
    )
    target = PlatformTarget.model_validate(
        load_platform_targets(repo_root=root)["youtube_16x9_1080p"]
    )

    transcript = {
        "duration_s": 12.0,
        "words": [
            {"text": "Battery", "start_s": 0.1, "end_s": 0.6},
            {"text": "costs", "start_s": 0.65, "end_s": 1.1},
            {"text": "dropped", "start_s": 1.15, "end_s": 1.6},
            {"text": "89%", "start_s": 1.65, "end_s": 2.3},
            {"text": "in", "start_s": 2.35, "end_s": 2.6},
            {"text": "ten", "start_s": 2.65, "end_s": 3.0},
            {"text": "years.", "start_s": 3.05, "end_s": 3.6},
            {"text": "Factories", "start_s": 4.2, "end_s": 4.9},
            {"text": "scaled", "start_s": 4.95, "end_s": 5.5},
            {"text": "output", "start_s": 5.55, "end_s": 6.1},
            {"text": "by", "start_s": 6.15, "end_s": 6.4},
            {"text": "4x.", "start_s": 6.45, "end_s": 7.1},
            {"text": "Grid", "start_s": 8.0, "end_s": 8.4},
            {"text": "storage", "start_s": 8.45, "end_s": 9.1},
            {"text": "now", "start_s": 9.15, "end_s": 9.5},
            {"text": "leads", "start_s": 9.55, "end_s": 10.1},
            {"text": "growth.", "start_s": 10.15, "end_s": 11.2},
        ],
    }

    sb = scaffold_storyboard(
        transcript,
        idioms,
        project_id="battery_economics",
    )
    # Verify strictly against core_idiom_registry() — zero geo idioms loaded.
    report = check_storyboard(sb, idioms, registry=core_idiom_registry())
    assert report.passed is True, report.to_dict()

    overlays, meta = storyboard_overlays(
        sb,
        idioms,
        catalog,
        policy,
        frame=(target.width, target.height),
        duration_s=12.0,
        safe_zone=target.safe_zone,
    )
    assert len(overlays) >= 1, meta

    plan = EditPlan(
        schema_version="1.0",
        job_id="explainer_neutrality_test",
        project_id="battery_economics",
        brand_id="editorial_explainer",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=12.0,
        fps=target.fps,
        width=target.width,
        height=target.height,
        assets=[
            AssetRef(
                asset_id="cam_a",
                sha256="a" * 64,
                kind="video",
                path="media/a_roll.mp4",
                duration_s=12.0,
                has_audio=False,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="clip_01",
                asset_id="cam_a",
                timeline_start_s=0.0,
                timeline_duration_s=12.0,
                source_start_s=0.0,
                role="a_roll",
                content_type="diagram",
                reframed_to_target=True,
            )
        ],
        overlay_compositions=overlays,
        audio_tracks=[],
    )

    ver = verify_edit_plan(
        plan,
        policy,
        target,
        template_catalog=catalog,
        repo_root=root,
    )
    assert ver.passed is True, ver.to_dict()

    compiled = compile_edit_plan(
        plan,
        tmp_path / "hf_out",
        platform_target=target,
        run_lint=True,
        repo_root=root,
    )
    assert compiled.lint is not None and compiled.lint.ok is True, compiled.lint
    assert compiled.index_html_path.is_file()
