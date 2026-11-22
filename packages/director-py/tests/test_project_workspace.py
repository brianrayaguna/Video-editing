"""Tests for external project workspace lifecycle, path hygiene, and relative asset resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vedit.cli import app
from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import find_repo_root, load_platform_targets
from vedit.models import AssetRef, EditPlan, OverlayCompositionOp, PlatformTarget
from vedit.project_workspace import (
    init_project_workspace,
    inspect_project_status,
    resolve_plan_asset_paths,
    resolve_projects_root,
    validate_project_workspace,
)


def test_resolve_projects_root_defaults_outside_engine_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = find_repo_root()
    monkeypatch.delenv("VEDIT_PROJECTS_ROOT", raising=False)
    default_root = resolve_projects_root(repo_root=repo_root)
    assert default_root == (repo_root.parent / f"{repo_root.name}-Projects").resolve()
    assert not default_root.is_relative_to(repo_root)

    with pytest.raises(ValueError, match="outside the engine repository"):
        resolve_projects_root(repo_root / "workspace", repo_root=repo_root)


def test_project_init_status_validate_and_absolute_path_rejection(tmp_path: Path) -> None:
    ext_root = tmp_path / "external_projects"
    info = init_project_workspace(
        project_id="episode_alpha",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        projects_root=ext_root,
        title="Episode Alpha",
    )
    assert info.project_dir == (ext_root / "geoverum" / "episode_alpha").resolve()
    assert info.manifest_path.is_file()
    assert info.brief_path.is_file()
    assert (info.project_dir / "inputs").is_dir()
    assert (info.project_dir / "analysis" / "probes").is_dir()
    assert (info.project_dir / "media" / "maps").is_dir()
    assert (info.project_dir / "plan").is_dir()
    assert (info.project_dir / "build" / "hf_sparse_windows").is_dir()
    assert (info.project_dir / "output").is_dir()

    status = inspect_project_status(info.project_dir)
    assert status.project_id == "episode_alpha"
    assert status.stages["inputs"]["ready"] is False
    assert status.stages["edit_plan"]["ready"] is False

    report = validate_project_workspace(info.project_dir)
    assert report.passed, report.to_dict()
    assert report.errors == []

    # Injecting a leaked local absolute path into plan/edit_plan.json must fail validation.
    leaked_plan = info.project_dir / "plan" / "edit_plan.json"
    leaked_plan.write_text(
        json.dumps({"assets": [{"path": "/Users/example/leaked.mp4"}]}),
        encoding="utf-8",
    )
    failed = validate_project_workspace(info.project_dir)
    assert not failed.passed
    assert any(err.code == "ABSOLUTE_PATH_LEAK" for err in failed.errors)


def test_resolve_plan_asset_paths_and_external_template_compilation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_root = tmp_path / "external_projects"
    info = init_project_workspace(
        project_id="episode_beta",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        projects_root=ext_root,
    )
    media_file = info.project_dir / "media" / "maps" / "shot_01.mp4"
    media_file.write_bytes(b"fake-mp4-bytes")
    font_file = info.project_dir / "media" / "SpaceGrotesk-Variable.ttf"
    font_file.write_bytes(b"fake-ttf-bytes")

    plan = EditPlan(
        job_id="episode_beta_job",
        project_id="episode_beta",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=4.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(
                asset_id="shot_01",
                sha256="a" * 64,
                kind="video",
                path="media/maps/shot_01.mp4",
                duration_s=4.0,
            ),
            AssetRef(
                asset_id="font_space_grotesk",
                sha256="c" * 64,
                kind="font",
                path="media/SpaceGrotesk-Variable.ttf",
            ),
            AssetRef(
                asset_id="remote_ref",
                sha256="b" * 64,
                kind="image",
                path="https://example.com/poster.jpg",
            ),
        ],
        video_tracks=[],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="ov_cap",
                kind="caption_rail",
                timeline_start_s=0.2,
                timeline_duration_s=2.0,
                transparent=True,
                safe_band="lower_third",
                template_id="caption_rail",
                props={
                    "composition_path": (
                        "profiles/brands/geoverum/templates/components/caption_rail.html"
                    ),
                    "text": "Clean external project.",
                    "fg_color": "#F4F1EA",
                    "bg_color": "#03161F",
                    "font_family": "Space Grotesk",
                    "caption_style": "plain",
                },
            )
        ],
        audio_tracks=[],
        verifier_passed=True,
    )

    resolved = resolve_plan_asset_paths(plan, base_dir=info.project_dir / "plan")
    assert resolved.assets[0].path == str(media_file.resolve())
    assert resolved.assets[1].path == str(font_file.resolve())
    assert resolved.assets[2].path == "https://example.com/poster.jpg"

    # Compile from an external cwd with VEDIT_REPO_ROOT unset to confirm template discovery.
    monkeypatch.delenv("VEDIT_REPO_ROOT", raising=False)
    monkeypatch.chdir(info.project_dir)
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    compiled = compile_edit_plan(
        resolved,
        info.project_dir / "build" / "hf_project",
        platform_target=target,
        run_lint=True,
    )
    assert compiled.index_html_path.is_file()
    assert compiled.lint is not None and compiled.lint.ok


def test_cli_project_commands_work_end_to_end(tmp_path: Path) -> None:
    runner = CliRunner()
    ext_root = tmp_path / "cli_projects"
    init_res = runner.invoke(
        app,
        [
            "project",
            "init",
            "cli_smoke",
            "--brand",
            "geoverum",
            "--platform",
            "shorts_9x16_1080p",
            "--projects-root",
            str(ext_root),
            "--json",
        ],
    )
    assert init_res.exit_code == 0, init_res.output
    payload = json.loads(init_res.output)
    proj_dir = Path(payload["project_dir"])
    assert proj_dir.is_dir()

    status_res = runner.invoke(app, ["project", "status", str(proj_dir), "--json"])
    assert status_res.exit_code == 0, status_res.output
    assert json.loads(status_res.output)["project_id"] == "cli_smoke"

    val_res = runner.invoke(app, ["project", "validate", str(proj_dir), "--json"])
    assert val_res.exit_code == 0, val_res.output
    assert json.loads(val_res.output)["passed"] is True


def test_path_containment_blocks_traversal_in_workspace_manifest_and_templates(
    tmp_path: Path,
) -> None:
    from pydantic import ValidationError

    from vedit.contracts import _resolve_template_composition_path, validate_against_contract
    from vedit.models import AssetRef, EditPlan, ProjectDirectories

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("sensitive", encoding="utf-8")
    proj_root = tmp_path / "projects" / "geoverum" / "demo"
    proj_root.mkdir(parents=True)

    # ProjectDirectories and manifest schema must reject '..' and 'plan/..'
    with pytest.raises(ValidationError):
        ProjectDirectories(inputs="..")
    with pytest.raises(ValidationError):
        ProjectDirectories(plan="plan/..")
    manifest_payload = {
        "schema_version": "1.0",
        "project_id": "demo",
        "brand_id": "geoverum",
        "platform_target_id": "shorts_9x16_1080p",
        "created_at": "2026-01-01T00:00:00Z",
        "directories": {
            "inputs": "..",
            "probes": "analysis/probes",
            "breakdowns": "analysis/breakdowns",
            "transcripts": "analysis/transcripts",
            "decisions": "analysis/decisions",
            "maps": "media/maps",
            "broll": "media/broll",
            "audio": "media/audio",
            "plan": "plan/..",
            "build": "build",
            "output": "output",
        },
        "artifacts": {
            "brief": "brief.md",
            "edit_plan": "plan/edit_plan.json",
            "verification": "plan/verification.json",
            "master": "output/master.mp4",
            "audit": "output/audit.json",
            "otio": "output/timeline.otio",
            "benchmark": "output/benchmark.json",
        },
    }
    assert validate_against_contract(manifest_payload, "project_manifest.schema.json")

    # resolve_plan_asset_paths must NOT resolve '..' traversal outside project root
    plan = EditPlan(
        job_id="safe_job",
        project_id="demo",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=2.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(
                asset_id="a1",
                sha256="a" * 64,
                kind="video",
                path="../../../secret.txt",
            )
        ],
        video_tracks=[],
        overlay_compositions=[],
        audio_tracks=[],
    )
    resolved = resolve_plan_asset_paths(plan, base_dir=proj_root)
    assert resolved.assets[0].path == "../../../secret.txt"

    # _resolve_template_composition_path rejects absolute and parent-escaping paths
    brand_dir = tmp_path / "brand"
    brand_dir.mkdir()
    assert (
        _resolve_template_composition_path(
            str(secret_file), brand_dir=brand_dir, repo_root=brand_dir
        )
        is None
    )
    assert (
        _resolve_template_composition_path(
            "../secret.txt", brand_dir=brand_dir, repo_root=brand_dir
        )
        is None
    )

    # EditPlan rejects traversal job_id and non-hex sha256
    with pytest.raises(ValidationError):
        plan.model_copy(update={"job_id": "../escape"})
        EditPlan.model_validate({**plan.model_dump(), "job_id": "../escape"})
    with pytest.raises(ValidationError):
        AssetRef(asset_id="bad", sha256="../../etc/passwd1234", kind="video", path="x.mp4")
