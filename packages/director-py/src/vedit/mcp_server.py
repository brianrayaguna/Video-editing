"""Lightweight Model Context Protocol (MCP) server exposing vedit orchestration tools."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import (
    find_repo_root,
    load_brand_template_catalog,
    load_platform_targets,
    load_schema,
    validate_all_brand_trees,
)
from vedit.director.verifier import verify_edit_plan
from vedit.interop.otio_bridge import export_edit_plan_to_otio
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    EditPlan,
    NormalizedTranscript,
    PlatformTarget,
)
from vedit.project_workspace import (
    init_project_workspace,
    inspect_project_status,
    resolve_plan_asset_paths,
    validate_project_workspace,
)


def create_mcp_server() -> Any:
    """Build a FastMCP server exposing thin control-plane project and cloud-render tools."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "FastMCP is not installed. Install the optional mcp extra with "
            "`uv sync --extra mcp` in `packages/director-py`."
        ) from exc

    mcp = FastMCP(
        name="vedit",
        instructions=(
            "Capability-first video directing, external project management, verification, "
            "HyperFrames compilation, OpenTimelineIO export, and Modal cloud rendering."
        ),
    )

    @mcp.tool()
    def project_init(
        project_id: str,
        brand_id: str,
        platform_target_id: str,
        projects_root: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Initialize a structured editing project outside the engine repository."""
        info = init_project_workspace(
            project_id=project_id,
            brand_id=brand_id,
            platform_target_id=platform_target_id,
            projects_root=Path(projects_root) if projects_root else None,
            title=title,
        )
        return info.to_dict()

    @mcp.tool()
    def project_status(project_dir: str) -> dict[str, Any]:
        """Inspect pipeline artifact readiness for a structured project directory."""
        return inspect_project_status(Path(project_dir)).to_dict()

    @mcp.tool()
    def project_validate(project_dir: str) -> dict[str, Any]:
        """Validate project manifest contract, brand/platform refs, and relative path hygiene."""
        return validate_project_workspace(Path(project_dir)).to_dict()

    @mcp.tool()
    def contracts_validate() -> dict[str, Any]:
        """Validate all JSON Schemas, platform mastering presets, and brand trees."""
        root = find_repo_root()
        schemas = [p.name for p in sorted((root / "contracts").glob("*.schema.json"))]
        for name in schemas:
            load_schema(name, repo_root=root)
        platforms = load_platform_targets(repo_root=root)
        brands = validate_all_brand_trees(repo_root=root)
        return {
            "ok": True,
            "schemas": schemas,
            "platforms_validated": sorted(platforms.keys()),
            "brands_validated": [entry["brand_id"] for entry in brands],
        }

    @mcp.tool()
    def director_verify(
        plan_file: str,
        policy_file: str,
        platform_id: str,
        brand_dir: str | None = None,
        transcript_file: str | None = None,
        update_plan: bool = False,
    ) -> dict[str, Any]:
        """Deterministically verify an EditPlan against BrandStylePolicy and PlatformTarget."""
        plan_path = Path(plan_file).expanduser().resolve()
        policy_path = Path(policy_file).expanduser().resolve()
        platforms = load_platform_targets()
        if platform_id not in platforms:
            raise ValueError(f"Unknown platform target: {platform_id}")
        platform_target = PlatformTarget.model_validate(platforms[platform_id])
        plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        policy = BrandStylePolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))
        transcript: NormalizedTranscript | None = (
            NormalizedTranscript.model_validate_json(
                Path(transcript_file).expanduser().read_text(encoding="utf-8")
            )
            if transcript_file
            else None
        )
        catalog: BrandTemplateCatalog | None = None
        if brand_dir is not None:
            resolved_brand = Path(brand_dir).expanduser().resolve()
            if not resolved_brand.is_dir():
                raise FileNotFoundError(f"Brand directory not found: {resolved_brand}")
            cat_path = resolved_brand / "templates" / "catalog.json"
        else:
            sibling = policy_path.parent / "templates" / "catalog.json"
            repo_cat = (
                find_repo_root()
                / "profiles"
                / "brands"
                / policy.brand_id
                / "templates"
                / "catalog.json"
            )
            cat_path = sibling if sibling.is_file() else repo_cat
        if cat_path.is_file():
            catalog = BrandTemplateCatalog.model_validate(load_brand_template_catalog(cat_path))
        report = verify_edit_plan(
            plan,
            policy,
            platform_target,
            transcript=transcript,
            template_catalog=catalog,
        )
        if update_plan:
            updated = plan.model_copy(update={"verifier_passed": report.passed})
            plan_path.write_text(
                updated.model_dump_json(indent=2, exclude_none=True) + "\n",
                encoding="utf-8",
            )
        return report.to_dict()

    @mcp.tool()
    def compile_plan(
        plan_file: str,
        out_dir: str,
        platform_id: str | None = None,
        run_lint: bool = True,
    ) -> dict[str, Any]:
        """Compile an EditPlan (resolving project-relative assets) into a HyperFrames project."""
        plan_path = Path(plan_file).expanduser().resolve()
        raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        resolved_plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
        target_id = platform_id or resolved_plan.platform_target_id
        platforms = load_platform_targets()
        if platform_id is not None and platform_id not in platforms:
            raise ValueError(f"Unknown platform target: {platform_id}")
        platform_target = (
            PlatformTarget.model_validate(platforms[target_id]) if target_id in platforms else None
        )
        compiled = compile_edit_plan(
            resolved_plan,
            Path(out_dir).expanduser().resolve(),
            platform_target=platform_target,
            run_lint=run_lint,
        )
        return json.loads(json.dumps(asdict(compiled), default=str))

    @mcp.tool()
    def audit_deliverable(
        media_file: str,
        platform_id: str,
        require_audio: bool = True,
        check_visual: bool = True,
    ) -> dict[str, Any]:
        """Audit mastered deliverable stream metadata, EBU R128 loudness, and visual anomalies."""
        platforms = load_platform_targets()
        if platform_id not in platforms:
            raise ValueError(f"Unknown platform target: {platform_id}")
        platform_target = PlatformTarget.model_validate(platforms[platform_id])
        report = audit_mastered_deliverable(
            Path(media_file).expanduser().resolve(),
            platform_target,
            require_audio=require_audio,
            check_visual=check_visual,
        )
        return report.to_dict()

    @mcp.tool()
    def export_otio(
        plan_file: str,
        output_path: str,
        resolve_paths: bool = False,
    ) -> dict[str, Any]:
        """Export an EditPlan manifest to an OpenTimelineIO `.otio` timeline file."""
        plan_path = Path(plan_file).expanduser().resolve()
        plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        out = export_edit_plan_to_otio(
            plan,
            Path(output_path).expanduser().resolve(),
            base_dir=plan_path.parent,
            resolve_paths=resolve_paths,
        )
        return {"ok": True, "output_path": str(out)}

    @mcp.tool()
    def cloud_render(
        plan_file: str,
        output_path: str,
        platform_id: str | None = None,
        chunk_frames: int = 180,
        quality: Literal["draft", "standard", "high"] = "high",
        force_hf: bool = False,
    ) -> dict[str, Any]:
        """Submit a verified EditPlan to Modal serverless workers and download the mastered MP4."""
        import modal

        cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
        if cloud_src not in sys.path:
            sys.path.insert(0, cloud_src)

        from vedit_cloud.app import APP_NAME, submit_modal_render

        plan_path = Path(plan_file).expanduser().resolve()
        raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        if not raw_plan.verifier_passed:
            raise ValueError("EditPlan must pass `director_verify` before cloud submission.")
        resolved_plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
        target_id = platform_id or resolved_plan.platform_target_id
        platforms = load_platform_targets()
        if target_id not in platforms:
            raise ValueError(f"Unknown platform target: {target_id}")
        platform_target = PlatformTarget.model_validate(platforms[target_id])

        remote_fn = modal.Function.from_name(APP_NAME, "orchestrate_distributed_render")
        remote_fn.hydrate()
        summary = submit_modal_render(
            resolved_plan,
            platform_target,
            output_path=Path(output_path).expanduser().resolve(),
            chunk_frames=chunk_frames,
            quality=quality,
            force_hf=force_hf,
            remote_fn=remote_fn,
        )
        return json.loads(json.dumps(summary, default=str))

    return mcp


def main() -> None:
    """Run the vedit FastMCP server over stdio."""
    server = create_mcp_server()
    server.run()


if __name__ == "__main__":
    main()
