"""Python bridge invoking the TypeScript `@vedit/hf-compiler` package."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import find_repo_root
from vedit.models import EditPlan, PlatformTarget


class HyperframesCompileError(RuntimeError):
    """Raised when HyperFrames compilation, linting, or distributed invocation fails."""


@dataclass(slots=True)
class HyperframesLintSummary:
    ok: bool
    total_errors: int
    total_warnings: int
    performance_violations: list[dict[str, Any]] = field(default_factory=list)
    hyperframes_findings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class CompiledHyperframesProject:
    out_dir: Path
    render_strategy: Literal["hybrid", "full_hf"]
    index_html_path: Path
    composition_files: list[Path]
    copied_assets: list[Path]
    recommended_format: Literal["mov", "mp4"]
    lint: HyperframesLintSummary | None = None


def resolve_hf_compiler_cli(repo_root: Path | None = None) -> Path:
    """Locate the built `@vedit/hf-compiler` CLI entrypoint (`dist/cli.js`)."""
    env_cli = os.environ.get("VEDIT_HF_COMPILER_CLI", "").strip()
    if env_cli:
        cand = Path(env_cli)
        if cand.is_file():
            return cand
        raise FileNotFoundError(f"VEDIT_HF_COMPILER_CLI points to missing script: {cand}")

    root = repo_root or find_repo_root()
    cand = root / "packages" / "hf-compiler-ts" / "dist" / "cli.js"
    if cand.is_file():
        return cand
    raise FileNotFoundError(
        "Built HyperFrames compiler CLI not found. "
        "Run `npm run build` in `packages/hf-compiler-ts`."
    )


def _run_node_cli(args: list[str], *, repo_root: Path | None = None) -> dict[str, Any]:
    node_bin = shutil.which("node")
    if not node_bin:
        raise FileNotFoundError("Node.js >= 22 is required to invoke @vedit/hf-compiler.")
    root = (repo_root or find_repo_root()).resolve()
    cli_js = resolve_hf_compiler_cli(repo_root=root)
    env = dict(os.environ)
    env.setdefault("VEDIT_REPO_ROOT", str(root))
    proc = subprocess.run(
        [node_bin, str(cli_js), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise HyperframesCompileError(f"hf-compiler command {args[0]!r} failed: {detail}")
    return json.loads(proc.stdout)


def _parse_lint_summary(raw: dict[str, Any]) -> HyperframesLintSummary:
    return HyperframesLintSummary(
        ok=bool(raw.get("ok")),
        total_errors=int(raw.get("totalErrors", 0)),
        total_warnings=int(raw.get("totalWarnings", 0)),
        performance_violations=list(raw.get("performanceViolations") or []),
        hyperframes_findings=list(raw.get("hyperframesFindings") or []),
    )


def compile_edit_plan(
    plan: EditPlan,
    out_dir: Path,
    *,
    platform_target: PlatformTarget | None = None,
    copy_assets: bool = True,
    run_lint: bool = True,
    repo_root: Path | None = None,
) -> CompiledHyperframesProject:
    """Compile a verified `EditPlan` into a HyperFrames project and run static lint checks."""
    if plan.verifier_passed is False and plan.overlay_compositions:
        # Callers may pass unverified drafts explicitly if desired, or verify beforehand.
        pass

    with tempfile.TemporaryDirectory(prefix="vedit_compile_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        plan_json_path = tmp_path / "edit_plan.json"
        plan_json_path.write_text(plan.model_dump_json(indent=2, exclude_none=True), "utf-8")

        args = [
            "compile",
            "--plan",
            str(plan_json_path),
            "--out-dir",
            str(out_dir),
            "--lint" if run_lint else "--no-lint",
            "--copy-assets" if copy_assets else "--no-copy-assets",
        ]
        if platform_target is not None:
            plat_path = tmp_path / "platform_target.json"
            plat_path.write_text(
                platform_target.model_dump_json(indent=2, exclude_none=True), "utf-8"
            )
            args.extend(["--platform", str(plat_path)])

        payload = _run_node_cli(args, repo_root=repo_root)

    compiled = payload["compiled"]
    lint_raw = payload.get("lint")
    return CompiledHyperframesProject(
        out_dir=Path(compiled["outDir"]),
        render_strategy=compiled["renderStrategy"],
        index_html_path=Path(compiled["indexHtmlPath"]),
        composition_files=[Path(p) for p in compiled.get("compositionFiles", [])],
        copied_assets=[Path(p) for p in compiled.get("copiedAssets", [])],
        recommended_format=compiled["recommendedFormat"],
        lint=_parse_lint_summary(lint_raw) if isinstance(lint_raw, dict) else None,
    )


def lint_hyperframes_project(
    project_dir: Path,
    *,
    entry: str | None = None,
    repo_root: Path | None = None,
) -> HyperframesLintSummary:
    """Run HyperFrames structural lint + CSS blur performance checks on a project folder."""
    args = ["lint", "--project-dir", str(project_dir)]
    if entry:
        args.extend(["--entry", entry])
    payload = _run_node_cli(args, repo_root=repo_root)
    return _parse_lint_summary(payload)


def plan_distributed_v2(
    project_dir: Path,
    plan_v2_dir: Path,
    *,
    fps: int,
    width: int,
    height: int,
    fmt: Literal["mp4", "mov"] = "mp4",
    quality: Literal["draft", "standard", "high"] = "high",
    chunk_frames: int = 180,
    max_parallel_chunks: int | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build a bounded-chunk distributed Plan v2 directory via `@hyperframes/producer`."""
    args = [
        "plan-v2",
        "--project-dir",
        str(project_dir),
        "--plan-v2-dir",
        str(plan_v2_dir),
        "--fps",
        str(int(fps)),
        "--width",
        str(int(width)),
        "--height",
        str(int(height)),
        "--format",
        fmt,
        "--quality",
        quality,
        "--chunk-frames",
        str(int(chunk_frames)),
    ]
    if max_parallel_chunks is not None:
        args.extend(["--max-parallel-chunks", str(int(max_parallel_chunks))])
    return _run_node_cli(args, repo_root=repo_root)


def render_chunk_v2(
    plan_v2_dir: Path,
    chunk_index: int,
    output_chunk_path: Path,
    *,
    max_capture_workers: int | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Render one chunk from a materialized Plan v2 directory."""
    args = [
        "render-chunk-v2",
        "--plan-v2-dir",
        str(plan_v2_dir),
        "--chunk-index",
        str(int(chunk_index)),
        "--out",
        str(output_chunk_path),
    ]
    if max_capture_workers is not None and max_capture_workers > 0:
        args.extend(["--max-capture-workers", str(int(max_capture_workers))])
    return _run_node_cli(args, repo_root=repo_root)


def assemble_v2(
    plan_v2_dir: Path,
    chunk_paths: list[Path],
    output_path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Assemble distributed chunk outputs back into a single video artifact."""
    with tempfile.TemporaryDirectory(prefix="vedit_assemble_") as tmp_dir:
        chunks_json = Path(tmp_dir) / "chunks.json"
        chunks_json.write_text(json.dumps([str(p) for p in chunk_paths]), encoding="utf-8")
        args = [
            "assemble-v2",
            "--plan-v2-dir",
            str(plan_v2_dir),
            "--chunks-json",
            str(chunks_json),
            "--out",
            str(output_path),
        ]
        return _run_node_cli(args, repo_root=repo_root)
