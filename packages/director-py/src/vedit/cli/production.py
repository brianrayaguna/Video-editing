"""Directing, external project, compile, mastering, audit, and cloud render commands."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import typer

from vedit.cli._app import JsonOption, app
from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import (
    find_repo_root,
    load_brand_template_catalog,
    load_platform_targets,
)
from vedit.director.planner import build_edit_plan
from vedit.director.verifier import verify_edit_plan
from vedit.interop.otio_bridge import export_edit_plan_to_otio
from vedit.mastering.ffmpeg_master import assemble_hybrid_deliverable
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    PlatformTarget,
)
from vedit.project_workspace import (
    find_project_root,
    init_project_workspace,
    inspect_project_status,
    resolve_plan_asset_paths,
    validate_project_workspace,
)
from vedit.providers.registry import build_default_registry

director_app = typer.Typer(help="Assemble and verify EditPlan specifications.")
project_app = typer.Typer(help="Initialize, inspect, and validate external editing projects.")
cloud_app = typer.Typer(help="Submit distributed renders and mastering jobs to Modal.com.")


def _load_optional_template_catalog(
    template_catalog: Path | None,
    brand_dir: Path | None,
) -> BrandTemplateCatalog | None:
    if template_catalog is not None:
        return BrandTemplateCatalog.model_validate(load_brand_template_catalog(template_catalog))
    if brand_dir is not None:
        catalog_path = brand_dir / "templates" / "catalog.json"
        if catalog_path.is_file():
            return BrandTemplateCatalog.model_validate(load_brand_template_catalog(catalog_path))
    return None


@director_app.command("plan")
def director_plan_cmd(
    probe_file: Annotated[Path, typer.Option("--probe-file", help="Source MediaProbeResult JSON.")],
    policy_file: Annotated[Path, typer.Option("--policy-file", help="BrandStylePolicy JSON.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    job_id: Annotated[str, typer.Option("--job-id")] = "job_local",
    project_id: Annotated[str, typer.Option("--project-id")] = "proj_local",
    transcript_file: Annotated[Path | None, typer.Option("--transcript-file")] = None,
    brand_dir: Annotated[
        Path | None, typer.Option("--brand-dir", help="Brand dir for templates/catalog.json.")
    ] = None,
    template_catalog: Annotated[
        Path | None, typer.Option("--template-catalog", help="Brand template catalog JSON.")
    ] = None,
    render_strategy: Annotated[Literal["hybrid", "full_hf"], typer.Option("--strategy")] = "hybrid",
    use_decision: Annotated[
        bool, typer.Option("--use-decision", help="Enable DecisionPort spatial box grounding.")
    ] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Assemble and deterministically verify an EditPlan."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    probe = MediaProbeResult.model_validate_json(probe_file.read_text(encoding="utf-8"))
    policy = BrandStylePolicy.model_validate_json(policy_file.read_text(encoding="utf-8"))
    transcript = (
        NormalizedTranscript.model_validate_json(transcript_file.read_text(encoding="utf-8"))
        if transcript_file is not None
        else None
    )
    catalog = _load_optional_template_catalog(template_catalog, brand_dir)
    decision_port = build_default_registry().resolve("decision") if use_decision else None
    plan, report = build_edit_plan(
        job_id=job_id,
        project_id=project_id,
        probe=probe,
        policy=policy,
        platform_target=platform_target,
        transcript=transcript,
        decision_port=decision_port,
        render_strategy=render_strategy,
        template_catalog=catalog,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(plan.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    typer.echo(
        json.dumps(
            {"plan": plan.model_dump(exclude_none=True), "report": report.to_dict()},
            indent=2,
        )
    )


@director_app.command("verify")
def director_verify_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    policy_file: Annotated[Path, typer.Option("--policy-file", help="BrandStylePolicy JSON path.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    transcript_file: Annotated[Path | None, typer.Option("--transcript-file")] = None,
    brand_dir: Annotated[
        Path | None, typer.Option("--brand-dir", help="Brand dir for templates/catalog.json.")
    ] = None,
    template_catalog: Annotated[
        Path | None, typer.Option("--template-catalog", help="Brand template catalog JSON.")
    ] = None,
) -> None:
    """Verify an EditPlan deterministically against BrandStylePolicy and PlatformTarget."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    plan = EditPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
    policy = BrandStylePolicy.model_validate_json(policy_file.read_text(encoding="utf-8"))
    transcript = (
        NormalizedTranscript.model_validate_json(transcript_file.read_text(encoding="utf-8"))
        if transcript_file is not None
        else None
    )
    catalog = _load_optional_template_catalog(template_catalog, brand_dir)
    report = verify_edit_plan(
        plan,
        policy,
        platform_target,
        transcript=transcript,
        template_catalog=catalog,
    )
    typer.echo(json.dumps(report.to_dict(), indent=2))
    if not report.passed:
        raise typer.Exit(code=1)


@project_app.command("init")
def project_init_cmd(
    project_id: Annotated[str, typer.Argument(help="Unique project identifier (slug).")],
    brand_id: Annotated[str, typer.Option("--brand", help="Brand profile identifier.")],
    platform_id: Annotated[
        str, typer.Option("--platform", help="Target platform mastering preset ID.")
    ],
    projects_root: Annotated[
        Path | None,
        typer.Option(
            "--projects-root",
            help="External projects root directory (defaults to VEDIT_PROJECTS_ROOT or sibling).",
        ),
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Human-readable project title.")] = (
        None
    ),
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing project.json and brief.md.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Initialize a structured editing project outside the engine repository."""
    info = init_project_workspace(
        project_id=project_id,
        brand_id=brand_id,
        platform_target_id=platform_id,
        projects_root=projects_root,
        title=title,
        overwrite=overwrite,
    )
    if json_output:
        typer.echo(json.dumps(info.to_dict(), indent=2))
    else:
        typer.echo(
            f"Initialized project {project_id!r} ({brand_id} / {platform_id}) at {info.project_dir}"
        )


@project_app.command("status")
def project_status_cmd(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Path to a structured project directory containing project.json."),
    ] = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Inspect artifact and stage readiness for an external editing project."""
    report = inspect_project_status(project_dir)
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return
    typer.echo(
        f"Project {report.project_id} ({report.brand_id} / {report.platform_target_id}) "
        f"@ {report.project_dir}"
    )
    for stage_name, info in report.stages.items():
        state = "READY" if info.get("ready") else "PENDING"
        typer.echo(f"  {stage_name:12s} {state:8s} ({info.get('path')})")


@project_app.command("validate")
def project_validate_cmd(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Path to a structured project directory containing project.json."),
    ] = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Validate project manifest contract, relative-path hygiene, and brand/platform refs."""
    report = validate_project_workspace(project_dir)
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        status = "PASSED" if report.passed else "FAILED"
        typer.echo(
            f"Project validation {status} ({len(report.errors)} error(s), "
            f"{len(report.warnings)} warning(s)): {report.project_dir}"
        )
        for err in report.errors:
            typer.echo(f"  [ERROR] {err.code}: {err.message}")
        for warn in report.warnings:
            typer.echo(f"  [WARN]  {warn.code}: {warn.message}")
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("compile", rich_help_panel="Production")
def compile_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="HyperFrames project output dir.")],
    platform_id: Annotated[str | None, typer.Option("--platform")] = None,
    run_lint: Annotated[bool, typer.Option("--lint/--no-lint")] = True,
) -> None:
    """Compile an EditPlan into HyperFrames HTML/GSAP scenes and run static checks."""
    plan_path = plan_file.expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    platform_target = (
        PlatformTarget.model_validate(platforms[target_id]) if target_id in platforms else None
    )
    compiled = compile_edit_plan(
        plan,
        out_dir,
        platform_target=platform_target,
        run_lint=run_lint,
    )
    typer.echo(json.dumps(asdict(compiled), indent=2, default=str))
    if compiled.lint and not compiled.lint.ok:
        raise typer.Exit(code=1)


@app.command("master", rich_help_panel="Production")
def master_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Final mastered MP4 output path.")],
    platform_id: Annotated[str | None, typer.Option("--platform")] = None,
    overlay_video: Annotated[
        Path | None, typer.Option("--overlay-video", help="Rendered transparent HyperFrames MOV.")
    ] = None,
    preset: Annotated[
        Literal["ultrafast", "veryfast", "fast", "medium", "slow"],
        typer.Option("--preset", help="x264/x265 encode preset."),
    ] = "fast",
    hw_encode: Annotated[
        bool,
        typer.Option("--hw-encode/--no-hw-encode", help="Use macOS VideoToolbox when available."),
    ] = False,
    ass_fastpath: Annotated[
        bool,
        typer.Option(
            "--ass-fastpath/--no-ass-fastpath",
            help="Burn plain captions and static text overlays via native FFmpeg libass.",
        ),
    ] = True,
) -> None:
    """Assemble hybrid cuts, composite overlays, and master two-pass `-14.0 LUFS` audio."""
    plan_path = plan_file.expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {target_id}")
    platform_target = PlatformTarget.model_validate(platforms[target_id])
    res = assemble_hybrid_deliverable(
        plan,
        platform_target,
        output,
        overlay_video_path=overlay_video,
        use_ass_fastpath=ass_fastpath,
        encode_preset=preset,
        use_hardware_encoder=hw_encode,
    )
    typer.echo(json.dumps(asdict(res), indent=2, default=str))


@app.command("export-otio", rich_help_panel="Production")
def export_otio_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Destination OpenTimelineIO `.otio` file path.")
    ],
    resolve_paths: Annotated[
        bool,
        typer.Option(
            "--resolve-paths/--keep-relative",
            help="Emit resolved absolute asset paths instead of portable relative paths.",
        ),
    ] = False,
) -> None:
    """Export an EditPlan manifest to an OpenTimelineIO `.otio` timeline."""
    plan_path = plan_file.expanduser().resolve()
    plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    out = export_edit_plan_to_otio(
        plan,
        output,
        base_dir=plan_path.parent,
        resolve_paths=resolve_paths,
    )
    typer.echo(json.dumps({"ok": True, "output_path": str(out)}, indent=2))


@app.command("audit", rich_help_panel="Production")
def audit_cmd(
    media_file: Annotated[Path, typer.Argument(help="Deliverable video file to audit.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    require_audio: Annotated[bool, typer.Option("--require-audio/--allow-silent")] = True,
    check_visual: Annotated[
        bool,
        typer.Option(
            "--check-visual/--no-check-visual",
            help="Scan for unintended black segments and frozen frames.",
        ),
    ] = True,
    reference: Annotated[
        Path | None,
        typer.Option("--reference", help="Optional reference video for perceptual VMAF scoring."),
    ] = None,
) -> None:
    """Run deterministic ffprobe, EBU R128, and visual QC verification on a deliverable video."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    qc = audit_mastered_deliverable(
        media_file,
        platform_target,
        require_audio=require_audio,
        check_visual=check_visual,
        reference_path=reference,
    )
    typer.echo(json.dumps(qc.to_dict(), indent=2, default=str))
    if not qc.passed:
        raise typer.Exit(code=1)


@cloud_app.command("render")
def cloud_render_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="Verified EditPlan JSON path.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Local output deliverable MP4 path.")
    ] = None,
    platform_id: Annotated[str | None, typer.Option("--platform")] = None,
    chunk_frames: Annotated[
        int, typer.Option("--chunk-frames", help="Chunk frame budget (150-240).")
    ] = 180,
    quality: Annotated[
        Literal["draft", "standard", "high"],
        typer.Option("--quality", help="HyperFrames producer quality tier."),
    ] = "high",
    force_hf: Annotated[
        bool,
        typer.Option(
            "--force-hf",
            help="Force all overlays through HyperFrames Chromium instead of libass fast-path.",
        ),
    ] = False,
    ephemeral: Annotated[
        bool,
        typer.Option(
            "--ephemeral",
            help="Run an ephemeral Modal app instead of calling the deployed app.",
        ),
    ] = False,
    allow_unverified: Annotated[
        bool,
        typer.Option(
            "--allow-unverified",
            help="Allow submitting an EditPlan where verifier_passed is false.",
        ),
    ] = False,
) -> None:
    """Stage local media on Modal CAS, run distributed render & mastering, and download MP4."""
    import modal

    cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
    if cloud_src not in sys.path:
        sys.path.insert(0, cloud_src)

    from vedit_cloud.app import APP_NAME, submit_modal_render
    from vedit_cloud.app import app as modal_app

    plan_path = plan_file.expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    if not raw_plan.verifier_passed and not allow_unverified:
        raise typer.BadParameter(
            "EditPlan has verifier_passed=false. Run `vedit director verify` first or pass "
            "--allow-unverified to submit anyway."
        )
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {target_id}")
    platform_target = PlatformTarget.model_validate(platforms[target_id])

    if output is not None:
        out_path = output
    else:
        project_root = find_project_root(plan_path.parent)
        out_path = (
            project_root / "output" / "master.mp4"
            if project_root is not None
            else Path("renders") / f"{plan.job_id}_master.mp4"
        )

    deployed_fn = None
    if not ephemeral:
        try:
            deployed_fn = modal.Function.from_name(APP_NAME, "orchestrate_distributed_render")
            deployed_fn.hydrate()
        except Exception:
            deployed_fn = None

    if deployed_fn is not None:
        summary = submit_modal_render(
            plan,
            platform_target,
            output_path=out_path,
            chunk_frames=chunk_frames,
            quality=quality,
            force_hf=force_hf,
            remote_fn=deployed_fn,
        )
    else:
        with modal.enable_output(), modal_app.run():
            summary = submit_modal_render(
                plan,
                platform_target,
                output_path=out_path,
                chunk_frames=chunk_frames,
                quality=quality,
                force_hf=force_hf,
            )
    typer.echo(json.dumps(summary, indent=2, default=str))
