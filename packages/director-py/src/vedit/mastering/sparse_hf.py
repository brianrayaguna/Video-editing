"""Windowed sparse HyperFrames renderer for selective hero explainer animations.

Instead of rendering an entire 90-600s timeline through headless Chromium ProRes 4444
when only 2-4 hero moments (charts, cross-section diagrams, chapter morphs, outro CTAs)
require DOM/GSAP/Three.js animation, this module groups animated overlays into compact
active time windows, renders only those windows, and returns `(start_s, end_s, mov_path)`
segments for FFmpeg compositing alongside native `libass` captions.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from vedit.compiler.hf_bridge import (
    assemble_v2,
    compile_edit_plan,
    plan_distributed_v2,
    render_chunk_v2,
)
from vedit.models import EditPlan, OverlayCompositionOp, PlatformTarget


@dataclass(slots=True)
class SparseOverlayWindow:
    """One contiguous active time window of animated HyperFrames overlays."""

    window_index: int
    start_s: float
    end_s: float
    overlays: list[OverlayCompositionOp]

    @property
    def duration_s(self) -> float:
        return round(max(0.25, self.end_s - self.start_s), 3)


def group_sparse_hf_windows(
    plan: EditPlan,
    hf_overlays: list[OverlayCompositionOp],
    *,
    merge_gap_s: float = 0.5,
    pad_s: float = 0.05,
) -> list[SparseOverlayWindow]:
    """Group animated overlays into minimal contiguous windows on the timeline."""
    if not hf_overlays:
        return []

    ordered = sorted(hf_overlays, key=lambda o: (o.timeline_start_s, o.timeline_duration_s))
    windows: list[SparseOverlayWindow] = []
    cur_start = max(0.0, ordered[0].timeline_start_s - pad_s)
    cur_end = min(
        plan.duration_s,
        ordered[0].timeline_start_s + ordered[0].timeline_duration_s + pad_s,
    )
    cur_items: list[OverlayCompositionOp] = [ordered[0]]

    for ov in ordered[1:]:
        ov_start = max(0.0, ov.timeline_start_s - pad_s)
        ov_end = min(plan.duration_s, ov.timeline_start_s + ov.timeline_duration_s + pad_s)
        if ov_start <= cur_end + merge_gap_s:
            cur_end = max(cur_end, ov_end)
            cur_items.append(ov)
        else:
            windows.append(
                SparseOverlayWindow(
                    window_index=len(windows),
                    start_s=round(cur_start, 3),
                    end_s=round(cur_end, 3),
                    overlays=cur_items,
                )
            )
            cur_start = ov_start
            cur_end = ov_end
            cur_items = [ov]

    windows.append(
        SparseOverlayWindow(
            window_index=len(windows),
            start_s=round(cur_start, 3),
            end_s=round(cur_end, 3),
            overlays=cur_items,
        )
    )
    return windows


def build_window_local_plan(plan: EditPlan, window: SparseOverlayWindow) -> EditPlan:
    """Create a local-time hybrid EditPlan (`t = 0..window.duration_s`) for one sparse window."""
    shifted: list[OverlayCompositionOp] = []
    for ov in window.overlays:
        local_start = round(max(0.0, ov.timeline_start_s - window.start_s), 3)
        shifted.append(ov.model_copy(update={"timeline_start_s": local_start}))

    # Keep only font/image assets needed for overlay compilation (no heavy video/audio copies).
    overlay_assets = [a for a in plan.assets if a.kind in ("font", "image")]
    return plan.model_copy(
        update={
            "job_id": f"{plan.job_id}_win{window.window_index:02d}",
            "render_strategy": "hybrid",
            "duration_s": window.duration_s,
            "assets": overlay_assets,
            "video_tracks": [],
            "audio_tracks": [],
            "overlay_compositions": shifted,
        }
    )


def render_sparse_hf_windows(
    plan: EditPlan,
    hf_overlays: list[OverlayCompositionOp],
    platform_target: PlatformTarget,
    work_dir: Path,
    *,
    quality: Literal["draft", "standard", "high"] = "high",
    chunk_frames: int = 180,
    max_capture_workers: int = 2,
    repo_root: Path | None = None,
) -> tuple[list[tuple[float, float, Path]], list[dict[str, Any]]]:
    """Compile, lint, and render only active HyperFrames windows into alpha ProRes MOVs."""
    windows = group_sparse_hf_windows(plan, hf_overlays)
    if not windows:
        return [], []

    work_dir.mkdir(parents=True, exist_ok=True)
    segments: list[tuple[float, float, Path]] = []
    metrics: list[dict[str, Any]] = []

    for win in windows:
        t0 = time.perf_counter()
        win_root = work_dir / f"win_{win.window_index:02d}"
        hf_dir = win_root / "hf_project"
        plan_v2_dir = win_root / "plan_v2"
        chunks_dir = win_root / "chunks"
        out_mov = work_dir / f"win_{win.window_index:02d}_{win.start_s:.2f}s.mov"

        shutil.rmtree(win_root, ignore_errors=True)
        chunks_dir.mkdir(parents=True, exist_ok=True)

        local_plan = build_window_local_plan(plan, win)
        compiled = compile_edit_plan(
            local_plan,
            hf_dir,
            platform_target=platform_target,
            run_lint=True,
            copy_assets=True,
            repo_root=repo_root,
        )
        if compiled.lint and not compiled.lint.ok:
            details = compiled.lint.hyperframes_findings or compiled.lint.performance_violations
            raise RuntimeError(
                f"Sparse HyperFrames window {win.window_index} lint failed: {details}"
            )

        planned = plan_distributed_v2(
            hf_dir,
            plan_v2_dir,
            fps=round(platform_target.fps),
            width=platform_target.width,
            height=platform_target.height,
            fmt="mov",
            quality=quality,
            chunk_frames=chunk_frames,
            repo_root=repo_root,
        )
        chunk_count = int(planned["manifest"]["chunkCount"])
        chunk_paths: list[Path] = []
        for idx in range(chunk_count):
            c_out = chunks_dir / f"chunk_{idx:04d}.mov"
            render_chunk_v2(
                plan_v2_dir,
                idx,
                c_out,
                max_capture_workers=max_capture_workers,
                repo_root=repo_root,
            )
            chunk_paths.append(c_out)

        out_mov.unlink(missing_ok=True)
        assemble_v2(plan_v2_dir, chunk_paths, out_mov, repo_root=repo_root)
        elapsed_s = round(time.perf_counter() - t0, 3)

        segments.append((win.start_s, win.end_s, out_mov))
        metrics.append(
            {
                "window_index": win.window_index,
                "start_s": win.start_s,
                "end_s": win.end_s,
                "duration_s": win.duration_s,
                "overlay_ids": [o.overlay_id for o in win.overlays],
                "chunk_count": chunk_count,
                "elapsed_s": elapsed_s,
                "output_mov": str(out_mov),
            }
        )

    return segments, metrics
