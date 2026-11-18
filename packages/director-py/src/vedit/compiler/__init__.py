"""Bridge between EditPlan models and the Node HyperFrames composition compiler."""

from vedit.compiler.hf_bridge import (
    CompiledHyperframesProject,
    HyperframesCompileError,
    HyperframesLintSummary,
    assemble_v2,
    compile_edit_plan,
    lint_hyperframes_project,
    plan_distributed_v2,
    render_chunk_v2,
    resolve_hf_compiler_cli,
)

__all__ = [
    "CompiledHyperframesProject",
    "HyperframesCompileError",
    "HyperframesLintSummary",
    "assemble_v2",
    "compile_edit_plan",
    "lint_hyperframes_project",
    "plan_distributed_v2",
    "render_chunk_v2",
    "resolve_hf_compiler_cli",
]
