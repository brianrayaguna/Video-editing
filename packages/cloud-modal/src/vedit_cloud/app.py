"""Modal.com distributed worker fan-out, CAS staging, and benchmark cost attribution."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

_CLOUD_SRC = str(Path(__file__).resolve().parents[1])
if _CLOUD_SRC not in sys.path:
    sys.path.insert(0, _CLOUD_SRC)

import modal
from vedit.compiler.hf_bridge import (
    assemble_v2,
    compile_edit_plan,
    plan_distributed_v2,
    render_chunk_v2,
)
from vedit.mastering.ass_captions import (
    build_sparse_hf_plan,
    partition_overlays_for_hybrid,
)
from vedit.mastering.ffmpeg_master import (
    assemble_hybrid_deliverable,
    master_full_hf_deliverable,
)
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.mastering.sparse_hf import build_window_local_plan, group_sparse_hf_windows
from vedit.models import AssetRef, EditPlan, PlatformTarget
from vedit.telemetry import JobCheckpoint, StageMetric

from vedit_cloud.image import WORKER_CHROMIUM_FLAGS, build_worker_image
from vedit_cloud.media_ops_worker import (
    MEDIA_OPS_CPU_COUNT,
    MEDIA_OPS_MEMORY_MB,
    build_media_ops_image,
    run_clean_audio_cloud,
    run_reframe_video_cloud,
)

APP_NAME = "vedit-distributed-renderer"
CAS_VOLUME_NAME = "vedit-cas-cache-v2"
CAS_MOUNT_PATH = Path("/vol/cas")
CPU_WORKER_COUNT = 4.0
ORCHESTRATOR_CPU_COUNT = 8.0
MEMORY_MB_WORKER = 8192
SCALEDOWN_WINDOW_S = 180

# Baseline Modal serverless compute unit rates (USD per second).
MODAL_VCPU_PER_SEC_USD = 0.0000131
MODAL_GIB_PER_SEC_USD = 0.00000222

app = modal.App(APP_NAME)
cas_volume = modal.Volume.from_name(CAS_VOLUME_NAME, create_if_missing=True, version=2)
worker_image = (
    build_worker_image()
    if modal.is_local()
    else modal.Image.debian_slim(python_version="3.12")
)
media_ops_image = (
    build_media_ops_image()
    if modal.is_local()
    else modal.Image.debian_slim(python_version="3.12")
)


def estimate_modal_render_cost(
    wall_ms: int,
    *,
    cpus: float = CPU_WORKER_COUNT,
    memory_mb: int = MEMORY_MB_WORKER,
) -> float:
    """Compute transparent Modal worker compute cost in USD from wall time and resource shape."""
    secs = max(wall_ms, 0) / 1000.0
    gib = memory_mb / 1024.0
    usd = secs * (cpus * MODAL_VCPU_PER_SEC_USD + gib * MODAL_GIB_PER_SEC_USD)
    return round(usd, 6)


def _stage_key(prefix: str, payload: str) -> str:
    return hashlib.sha256(f"{prefix}:{payload}".encode()).hexdigest()


def _chunk_filename(chunk_index: int, fmt: Literal["mov", "mp4"]) -> str:
    ext = ".mov" if fmt == "mov" else ".mp4"
    return f"chunk_{chunk_index:04d}{ext}"


def _stage_artifacts_exist(checkpoint: JobCheckpoint, stage: str) -> bool:
    metric = checkpoint.completed_stages.get(stage)
    if metric is None or not metric.output_artifacts:
        return False
    return all(Path(p).exists() for p in metric.output_artifacts)


def stage_local_assets_for_cloud(plan: EditPlan, volume: Any) -> EditPlan:
    """Upload missing local media files by SHA-256 to Modal CAS Volume and rewrite paths."""
    existing_paths: set[str] = set()
    try:
        for entry in volume.listdir("/sources"):
            existing_paths.add(str(entry.path).lstrip("/"))
    except (FileNotFoundError, modal.exception.NotFoundError, modal.exception.InvalidError):
        existing_paths = set()

    uploads: dict[str, tuple[Path, str]] = {}
    rewritten_assets: list[AssetRef] = []

    for asset in plan.assets:
        local_src = Path(asset.path)
        if local_src.is_file():
            ext = local_src.suffix.lower() or ".bin"
            remote_rel = f"sources/{asset.sha256}{ext}"
            if remote_rel not in existing_paths and remote_rel not in uploads:
                uploads[remote_rel] = (local_src, f"/{remote_rel}")
            rewritten_assets.append(
                asset.model_copy(update={"path": str(CAS_MOUNT_PATH / remote_rel)})
            )
        else:
            rewritten_assets.append(asset)

    if uploads:
        with volume.batch_upload(force=True) as batch:
            for local_src, remote_dst in uploads.values():
                batch.put_file(str(local_src), remote_dst)

    return plan.model_copy(update={"assets": rewritten_assets})


def download_cas_file(volume: Any, remote_relpath: str, local_output_path: Path) -> Path:
    """Download a completed deliverable from the Modal CAS Volume to a local path."""
    local_output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_rel = remote_relpath.lstrip("/")
    with local_output_path.open("wb") as fp:
        for chunk in volume.read_file(clean_rel):
            fp.write(chunk)
    return local_output_path


def _resolve_headless_shell_path() -> str | None:
    """Locate the pre-installed chrome-headless-shell executable inside the worker image."""
    configured = os.environ.get("PRODUCER_HEADLESS_SHELL_PATH")
    if configured and Path(configured).is_file():
        return configured
    cache_root = Path("/root/.cache/puppeteer/chrome-headless-shell")
    if cache_root.is_dir():
        matches = sorted(cache_root.rglob("chrome-headless-shell"), reverse=True)
        for candidate in matches:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


@app.function(
    image=worker_image,
    volumes={str(CAS_MOUNT_PATH): cas_volume},
    cpu=CPU_WORKER_COUNT,
    memory=MEMORY_MB_WORKER,
    timeout=900,
    enable_memory_snapshot=True,
    scaledown_window=SCALEDOWN_WINDOW_S,
)
def render_chunk_worker(
    plan_v2_subpath: str,
    chunk_index: int,
    job_subpath: str,
    fmt: Literal["mov", "mp4"] = "mov",
    max_capture_workers: int = 2,
) -> dict[str, Any]:
    """Render one bounded HyperFrames chunk (`150-240` frames) inside a fresh worker turn."""
    os.environ["HYPERFRAMES_CHROMIUM_FLAGS"] = WORKER_CHROMIUM_FLAGS
    os.environ["HYPERFRAMES_CHROME_SANDBOX"] = "0"
    os.environ["PRODUCER_BROWSER_GPU_MODE"] = "software"
    shell_path = _resolve_headless_shell_path()
    if shell_path:
        os.environ["PRODUCER_HEADLESS_SHELL_PATH"] = shell_path
    cas_volume.reload()

    plan_v2_dir = CAS_MOUNT_PATH / plan_v2_subpath
    chunk_name = _chunk_filename(chunk_index, fmt)
    out_chunk = CAS_MOUNT_PATH / job_subpath / "chunks" / chunk_name
    out_chunk.parent.mkdir(parents=True, exist_ok=True)
    out_chunk.unlink(missing_ok=True)

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"vedit_chunk_{chunk_index:04d}_") as local_tmp:
        local_chunk = Path(local_tmp) / chunk_name
        chunk_result = render_chunk_v2(
            plan_v2_dir,
            chunk_index,
            local_chunk,
            max_capture_workers=max_capture_workers,
            repo_root=Path("/opt/vedit"),
        )
        shutil.move(str(local_chunk), str(out_chunk))
    wall_ms = int((time.perf_counter() - t0) * 1000)
    cas_volume.commit()

    return {
        "chunk_index": chunk_index,
        "output_subpath": str(out_chunk.relative_to(CAS_MOUNT_PATH)),
        "wall_ms": wall_ms,
        "estimated_usd": estimate_modal_render_cost(wall_ms),
        "result": chunk_result,
    }


@app.function(
    image=worker_image,
    volumes={str(CAS_MOUNT_PATH): cas_volume},
    cpu=ORCHESTRATOR_CPU_COUNT,
    memory=MEMORY_MB_WORKER,
    timeout=1200,
    enable_memory_snapshot=True,
    scaledown_window=SCALEDOWN_WINDOW_S,
)
def orchestrate_distributed_render(
    edit_plan_json: str,
    platform_target_json: str,
    *,
    chunk_frames: int = 180,
    quality: Literal["draft", "standard", "high"] = "high",
    force_hf: bool = False,
) -> dict[str, Any]:
    """Coordinate compile -> Plan v2 -> chunk fan-out -> assemble -> hybrid master -> QC."""
    cas_volume.reload()
    plan = EditPlan.model_validate_json(edit_plan_json)
    target = PlatformTarget.model_validate_json(platform_target_json)

    repo_root = Path("/opt/vedit")
    job_subpath = f"jobs/{plan.job_id}"
    job_root = CAS_MOUNT_PATH / job_subpath
    job_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = job_root / "checkpoint.json"
    checkpoint = JobCheckpoint.load_or_create(
        checkpoint_path,
        job_id=plan.job_id,
        project_id=plan.project_id,
        brand_id=plan.brand_id,
        platform_target_id=plan.platform_target_id,
    )

    encode_preset: Literal["veryfast", "fast"] = "veryfast" if quality == "draft" else "fast"

    if plan.render_strategy == "hybrid":
        ass_overlays, hf_overlays = partition_overlays_for_hybrid(
            plan,
            force_hyperframes=force_hf,
        )
        needs_hf = bool(hf_overlays)
        hf_plan = build_sparse_hf_plan(plan, hf_overlays) if needs_hf else None
        use_ass_fastpath = bool(ass_overlays) and not force_hf
    else:
        ass_overlays = []
        hf_overlays = list(plan.overlay_compositions)
        needs_hf = True
        hf_plan = plan
        use_ass_fastpath = False

    overlay_render_path: Path | None = None
    overlay_segments: list[tuple[float, float, Path]] = []
    hf_dir = job_root / "hf_project"
    plan_v2_dir = job_root / "plan_v2"
    fmt: Literal["mov", "mp4"] = "mov" if plan.render_strategy == "hybrid" else "mp4"
    chunk_tag = f"{job_subpath}/{fmt}"

    sparse_windows = (
        group_sparse_hf_windows(plan, hf_overlays)
        if plan.render_strategy == "hybrid" and needs_hf and hf_plan is not None
        else []
    )
    use_sparse_windows = (
        bool(sparse_windows)
        and hf_plan is not None
        and sum(w.duration_s for w in sparse_windows) < (hf_plan.duration_s * 0.65)
    )

    with tempfile.TemporaryDirectory(prefix=f"vedit_orch_{plan.job_id}_") as local_scratch:
        scratch_root = Path(local_scratch)

        if needs_hf and use_sparse_windows:
            # Fan out ONLY active animated HyperFrames windows in one parallel Modal starmap!
            win_jobs: list[tuple[str, int, str, Literal["mov", "mp4"], int]] = []
            win_meta: list[tuple[Any, Path, int]] = []
            for win in sparse_windows:
                local_plan = build_window_local_plan(plan, win)
                local_w_hf = scratch_root / f"win_{win.window_index:02d}_hf"
                local_w_p2 = scratch_root / f"win_{win.window_index:02d}_plan_v2"
                cas_w_p2 = job_root / f"win_{win.window_index:02d}" / "plan_v2"
                compiled = compile_edit_plan(
                    local_plan,
                    local_w_hf,
                    platform_target=target,
                    run_lint=True,
                    repo_root=repo_root,
                )
                if compiled.lint and not compiled.lint.ok:
                    raise RuntimeError(
                        f"HyperFrames sparse window {win.window_index} lint failed: "
                        f"{compiled.lint.hyperframes_findings}"
                    )
                planned = plan_distributed_v2(
                    local_w_hf,
                    local_w_p2,
                    fps=round(local_plan.fps),
                    width=local_plan.width,
                    height=local_plan.height,
                    fmt="mov",
                    quality=quality,
                    chunk_frames=chunk_frames,
                    repo_root=repo_root,
                )
                shutil.rmtree(cas_w_p2, ignore_errors=True)
                shutil.copytree(local_w_p2, cas_w_p2)
                c_count = int(planned["manifest"]["chunkCount"])
                win_tag = f"{job_subpath}/win_{win.window_index:02d}"
                for idx in range(c_count):
                    win_jobs.append(
                        (str(cas_w_p2.relative_to(CAS_MOUNT_PATH)), idx, win_tag, "mov", 2)
                    )
                win_meta.append((win, cas_w_p2, c_count))
            cas_volume.commit()

            t_chunks = time.perf_counter()
            all_chunk_outputs = list(render_chunk_worker.starmap(win_jobs))
            cas_volume.reload()
            chunks_wall_ms = int((time.perf_counter() - t_chunks) * 1000)
            chunks_usd = round(
                sum(float(c["estimated_usd"]) for c in all_chunk_outputs),
                6,
            )
            cursor = 0
            for win, cas_w_p2, c_count in win_meta:
                w_outs = all_chunk_outputs[cursor : cursor + c_count]
                cursor += c_count
                w_chunk_paths = [CAS_MOUNT_PATH / str(c["output_subpath"]) for c in w_outs]
                local_mov = scratch_root / f"win_{win.window_index:02d}.mov"
                assemble_v2(cas_w_p2, w_chunk_paths, local_mov, repo_root=repo_root)
                overlay_segments.append((win.start_s, win.end_s, local_mov))
            checkpoint.record(
                StageMetric(
                    stage="render_sparse_windows",
                    status="completed",
                    idempotency_key=_stage_key("sparse_win", f"{plan.job_id}:{len(win_jobs)}"),
                    wall_ms=chunks_wall_ms,
                    provider="modal_hyperframes_workers",
                    estimated_usd=chunks_usd,
                    output_artifacts=[str(p) for _, _, p in overlay_segments],
                )
            )
            checkpoint.save(checkpoint_path)

        elif needs_hf and hf_plan is not None:
            hf_plan_json = hf_plan.model_dump_json(exclude_none=True)
            compile_key = _stage_key("compile", f"{hf_plan_json}:{quality}")
            plan_v2_key = _stage_key("plan_v2", f"{hf_plan_json}:{chunk_frames}:{quality}:{fmt}")
            assemble_key = _stage_key("assemble", f"{plan_v2_key}:{fmt}")
            assembled_hf_path = job_root / f"hf_assembled.{fmt}"

            if (
                checkpoint.is_stage_done("assemble_v2", assemble_key)
                and _stage_artifacts_exist(checkpoint, "assemble_v2")
                and assembled_hf_path.is_file()
            ):
                overlay_render_path = assembled_hf_path
            else:
                local_hf_dir = scratch_root / "hf_project"
                if (
                    not checkpoint.is_stage_done("plan_v2", plan_v2_key)
                    or not (plan_v2_dir / "manifest.json").is_file()
                ):
                    with checkpoint.track_stage(
                        "compile_and_lint",
                        compile_key,
                        state_path=checkpoint_path,
                        provider="hyperframes",
                    ) as meta:
                        compiled = compile_edit_plan(
                            hf_plan,
                            local_hf_dir,
                            platform_target=target,
                            run_lint=True,
                            repo_root=repo_root,
                        )
                        if compiled.lint and not compiled.lint.ok:
                            raise RuntimeError(
                                f"HyperFrames lint failed: {compiled.lint.hyperframes_findings}"
                            )
                        meta["output_artifacts"] = [str(compiled.index_html_path)]

                    with checkpoint.track_stage(
                        "plan_v2",
                        plan_v2_key,
                        state_path=checkpoint_path,
                        provider="hyperframes_producer",
                    ) as meta:
                        local_plan_v2 = scratch_root / "plan_v2"
                        planned = plan_distributed_v2(
                            local_hf_dir,
                            local_plan_v2,
                            fps=round(hf_plan.fps),
                            width=hf_plan.width,
                            height=hf_plan.height,
                            fmt=fmt,
                            quality=quality,
                            chunk_frames=chunk_frames,
                            repo_root=repo_root,
                        )
                        shutil.rmtree(plan_v2_dir, ignore_errors=True)
                        shutil.copytree(local_plan_v2, plan_v2_dir)
                        manifest = planned["manifest"]
                        chunk_count = int(manifest["chunkCount"])
                        meta["output_artifacts"] = [str(plan_v2_dir / "manifest.json")]
                    cas_volume.commit()
                else:
                    import json as _json

                    manifest = _json.loads((plan_v2_dir / "manifest.json").read_text("utf-8"))
                    chunk_count = int(manifest["chunkCount"])

                chunks_key = _stage_key("chunks", f"{plan_v2_key}:{chunk_count}")
                expected_chunks = [
                    CAS_MOUNT_PATH / chunk_tag / "chunks" / _chunk_filename(idx, fmt)
                    for idx in range(chunk_count)
                ]
                if (
                    checkpoint.is_stage_done("render_chunks", chunks_key)
                    and all(p.is_file() for p in expected_chunks)
                ):
                    chunk_paths = expected_chunks
                else:
                    t_chunks = time.perf_counter()
                    chunk_outputs = list(
                        render_chunk_worker.starmap(
                            [
                                (
                                    str(plan_v2_dir.relative_to(CAS_MOUNT_PATH)),
                                    idx,
                                    chunk_tag,
                                    fmt,
                                    2,
                                )
                                for idx in range(chunk_count)
                            ]
                        )
                    )
                    cas_volume.reload()
                    chunks_wall_ms = int((time.perf_counter() - t_chunks) * 1000)
                    chunks_usd = round(
                        sum(float(c["estimated_usd"]) for c in chunk_outputs),
                        6,
                    )
                    chunk_paths = [
                        CAS_MOUNT_PATH / str(c["output_subpath"]) for c in chunk_outputs
                    ]
                    checkpoint.record(
                        StageMetric(
                            stage="render_chunks",
                            status="completed",
                            idempotency_key=chunks_key,
                            wall_ms=chunks_wall_ms,
                            provider="modal_hyperframes_workers",
                            estimated_usd=chunks_usd,
                            output_artifacts=[str(p) for p in chunk_paths],
                        )
                    )
                    checkpoint.save(checkpoint_path)

                with checkpoint.track_stage(
                    "assemble_v2",
                    assemble_key,
                    state_path=checkpoint_path,
                    provider="hyperframes_producer",
                ) as meta:
                    local_assembled = scratch_root / f"hf_assembled.{fmt}"
                    assemble_v2(plan_v2_dir, chunk_paths, local_assembled, repo_root=repo_root)
                    assembled_hf_path.unlink(missing_ok=True)
                    shutil.move(str(local_assembled), str(assembled_hf_path))
                    meta["output_artifacts"] = [str(assembled_hf_path)]
                overlay_render_path = assembled_hf_path

        final_deliverable = job_root / f"{plan.job_id}_master.mp4"
        master_key = _stage_key(
            "master",
            f"{edit_plan_json}:{encode_preset}:{use_ass_fastpath}:{overlay_render_path}",
        )
        if not (
            checkpoint.is_stage_done("hybrid_master", master_key)
            and final_deliverable.is_file()
        ):
            with checkpoint.track_stage(
                "hybrid_master",
                master_key,
                state_path=checkpoint_path,
                provider="ffmpeg_libass" if use_ass_fastpath else "ffmpeg",
            ) as meta:
                t_m = time.perf_counter()
                local_master = scratch_root / f"{plan.job_id}_master.mp4"
                if plan.render_strategy == "full_hf" and overlay_render_path is not None:
                    master_full_hf_deliverable(
                        overlay_render_path,
                        plan,
                        target,
                        local_master,
                        encode_preset=encode_preset,
                    )
                else:
                    assemble_hybrid_deliverable(
                        plan,
                        target,
                        local_master,
                        overlay_video_path=overlay_render_path,
                        overlay_segments=overlay_segments or None,
                        use_ass_fastpath=use_ass_fastpath,
                        encode_preset=encode_preset,
                    )
                final_deliverable.unlink(missing_ok=True)
                shutil.move(str(local_master), str(final_deliverable))
                m_ms = int((time.perf_counter() - t_m) * 1000)
                meta["estimated_usd"] = estimate_modal_render_cost(
                    m_ms,
                    cpus=ORCHESTRATOR_CPU_COUNT,
                )
                meta["output_artifacts"] = [str(final_deliverable)]

        with checkpoint.track_stage(
            "qc_audit",
            _stage_key("qc", str(final_deliverable)),
            state_path=checkpoint_path,
            provider="ffprobe_ebur128",
        ) as meta:
            qc = audit_mastered_deliverable(
                final_deliverable,
                target,
                require_audio=bool(plan.audio_tracks),
            )
            meta["output_artifacts"] = [str(final_deliverable)]

    # Clean intermediate scratch dirs on Volume after QC passes to keep Volume inode counts low.
    if qc.passed:
        shutil.rmtree(hf_dir, ignore_errors=True)
        shutil.rmtree(plan_v2_dir, ignore_errors=True)
        shutil.rmtree(CAS_MOUNT_PATH / chunk_tag, ignore_errors=True)
        for win in sparse_windows:
            shutil.rmtree(job_root / f"win_{win.window_index:02d}", ignore_errors=True)

    cas_volume.commit()
    return {
        "job_id": plan.job_id,
        "deliverable_path": str(final_deliverable),
        "deliverable_subpath": str(final_deliverable.relative_to(CAS_MOUNT_PATH)),
        "used_hyperframes": needs_hf,
        "used_ass_fastpath": use_ass_fastpath,
        "ass_overlay_count": len(ass_overlays),
        "hf_overlay_count": len(hf_overlays),
        "qc": qc.to_dict(),
        "telemetry": checkpoint.model_dump(),
    }


def submit_modal_render(
    plan: EditPlan,
    platform_target: PlatformTarget,
    *,
    output_path: Path | None = None,
    chunk_frames: int = 180,
    quality: Literal["draft", "standard", "high"] = "high",
    force_hf: bool = False,
    remote_fn: Any | None = None,
) -> dict[str, Any]:
    """Upload local source assets to Modal CAS, run cloud render, and optionally download output."""
    cloud_plan = stage_local_assets_for_cloud(plan, cas_volume)
    orchestrator = remote_fn or orchestrate_distributed_render
    summary = orchestrator.remote(
        cloud_plan.model_dump_json(exclude_none=True),
        platform_target.model_dump_json(exclude_none=True),
        chunk_frames=chunk_frames,
        quality=quality,
        force_hf=force_hf,
    )
    if output_path is not None and "deliverable_subpath" in summary:
        downloaded = download_cas_file(
            cas_volume,
            str(summary["deliverable_subpath"]),
            output_path,
        )
        summary["local_output_path"] = str(downloaded)
    return summary


@app.local_entrypoint()
def main(
    plan_file: str,
    platform_id: str = "",
    chunk_frames: int = 180,
    quality: str = "high",
    force_hf: bool = False,
    output: str = "",
) -> None:
    """Stage local media on Modal CAS, run distributed render, and download master MP4."""
    import json

    from vedit.contracts import load_platform_targets
    from vedit.project_workspace import resolve_plan_asset_paths

    plan_path = Path(plan_file).expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise ValueError(f"Unknown platform target: {target_id}")
    target = PlatformTarget.model_validate(platforms[target_id])
    out_path = Path(output) if output else Path("renders") / f"{plan.job_id}_master.mp4"
    typed_quality: Literal["draft", "standard", "high"] = (
        quality if quality in ("draft", "standard", "high") else "high"
    )
    summary = submit_modal_render(
        plan,
        target,
        output_path=out_path,
        chunk_frames=chunk_frames,
        quality=typed_quality,
        force_hf=force_hf,
    )
    print(json.dumps(summary, indent=2))


@app.function(
    image=media_ops_image,
    volumes={str(CAS_MOUNT_PATH): cas_volume},
    cpu=MEDIA_OPS_CPU_COUNT,
    memory=MEDIA_OPS_MEMORY_MB,
    timeout=600,
    enable_memory_snapshot=True,
    scaledown_window=SCALEDOWN_WINDOW_S,
)
def clean_audio_cloud(
    source_relpath: str,
    *,
    strength: float = 0.85,
) -> dict[str, Any]:
    """Run 48 kHz neural speech enhancement via DeepFilterNet inside a Modal CPU container."""
    return run_clean_audio_cloud(
        source_relpath,
        cas_mount_path=CAS_MOUNT_PATH,
        cas_volume=cas_volume,
        estimate_cost_fn=estimate_modal_render_cost,
        strength=strength,
    )


@app.function(
    image=media_ops_image,
    volumes={str(CAS_MOUNT_PATH): cas_volume},
    cpu=MEDIA_OPS_CPU_COUNT,
    memory=MEDIA_OPS_MEMORY_MB,
    timeout=900,
    enable_memory_snapshot=True,
    scaledown_window=SCALEDOWN_WINDOW_S,
)
def reframe_video_cloud(
    source_relpath: str,
    *,
    target_aspect_ratio: Literal["9:16", "1:1", "4:5", "16:9"] = "9:16",
) -> dict[str, Any]:
    """Run deterministic Lanczos + bt709 aspect-ratio reframing inside a Modal CPU container."""
    return run_reframe_video_cloud(
        source_relpath,
        cas_mount_path=CAS_MOUNT_PATH,
        cas_volume=cas_volume,
        estimate_cost_fn=estimate_modal_render_cost,
        target_aspect_ratio=target_aspect_ratio,
    )
