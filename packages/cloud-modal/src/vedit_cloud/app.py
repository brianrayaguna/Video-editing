"""Modal.com distributed worker fan-out, CAS staging, and benchmark cost attribution."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Any

import modal
from vedit.compiler.hf_bridge import (
    assemble_v2,
    compile_edit_plan,
    plan_distributed_v2,
    render_chunk_v2,
)
from vedit.mastering.ffmpeg_master import assemble_hybrid_deliverable
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import AssetRef, EditPlan, PlatformTarget
from vedit.telemetry import JobCheckpoint, StageMetric

from vedit_cloud.image import WORKER_CHROMIUM_FLAGS, build_worker_image

CAS_VOLUME_NAME = "vedit-cas-cache"
CAS_MOUNT_PATH = Path("/vol/cas")
CPU_WORKER_COUNT = 4.0
MEMORY_MB_WORKER = 8192

# Baseline Modal serverless compute unit rates (USD per second).
MODAL_VCPU_PER_SEC_USD = 0.0000131
MODAL_GIB_PER_SEC_USD = 0.00000222

app = modal.App("vedit-distributed-renderer")
cas_volume = modal.Volume.from_name(CAS_VOLUME_NAME, create_if_missing=True)
worker_image = (
    build_worker_image()
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


@app.function(
    image=worker_image,
    volumes={str(CAS_MOUNT_PATH): cas_volume},
    cpu=CPU_WORKER_COUNT,
    memory=MEMORY_MB_WORKER,
    timeout=900,
)
def render_chunk_worker(plan_v2_subpath: str, chunk_index: int, job_subpath: str) -> dict[str, Any]:
    """Render one bounded HyperFrames chunk (`150-240` frames) inside a fresh worker turn."""
    os.environ["HYPERFRAMES_CHROMIUM_FLAGS"] = WORKER_CHROMIUM_FLAGS
    os.environ["HYPERFRAMES_CHROME_SANDBOX"] = "0"
    cas_volume.reload()

    plan_v2_dir = CAS_MOUNT_PATH / plan_v2_subpath
    chunk_ext = ".mov" if "mov" in job_subpath else ".mp4"
    out_chunk = CAS_MOUNT_PATH / job_subpath / "chunks" / f"chunk_{chunk_index:04d}{chunk_ext}"
    out_chunk.parent.mkdir(parents=True, exist_ok=True)
    out_chunk.unlink(missing_ok=True)

    t0 = time.perf_counter()
    chunk_result = render_chunk_v2(
        plan_v2_dir,
        chunk_index,
        out_chunk,
        repo_root=Path("/opt/vedit"),
    )
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
    cpu=CPU_WORKER_COUNT,
    memory=MEMORY_MB_WORKER,
    timeout=1200,
)
def orchestrate_distributed_render(
    edit_plan_json: str,
    platform_target_json: str,
    *,
    chunk_frames: int = 180,
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

    overlay_render_path: Path | None = None
    needs_hf = plan.render_strategy == "full_hf" or bool(plan.overlay_compositions)

    if needs_hf:
        hf_dir = job_root / "hf_project"
        plan_v2_dir = job_root / "plan_v2"
        fmt = "mov" if plan.render_strategy == "hybrid" else "mp4"

        with checkpoint.track_stage(
            "compile_and_lint",
            _stage_key("compile", edit_plan_json),
            state_path=checkpoint_path,
            provider="hyperframes",
        ) as meta:
            shutil.rmtree(hf_dir, ignore_errors=True)
            compiled = compile_edit_plan(
                plan,
                hf_dir,
                platform_target=target,
                run_lint=True,
                repo_root=repo_root,
            )
            if compiled.lint and not compiled.lint.ok:
                raise RuntimeError(f"HyperFrames lint failed: {compiled.lint.hyperframes_findings}")
            meta["output_artifacts"] = [str(compiled.index_html_path)]

        with checkpoint.track_stage(
            "plan_v2",
            _stage_key("plan_v2", edit_plan_json),
            state_path=checkpoint_path,
            provider="hyperframes_producer",
        ) as meta:
            shutil.rmtree(plan_v2_dir, ignore_errors=True)
            planned = plan_distributed_v2(
                hf_dir,
                plan_v2_dir,
                fps=round(plan.fps),
                width=plan.width,
                height=plan.height,
                fmt=fmt,
                chunk_frames=chunk_frames,
                repo_root=repo_root,
            )
            manifest = planned["manifest"]
            chunk_count = int(manifest["chunkCount"])
            meta["output_artifacts"] = [str(plan_v2_dir)]
        cas_volume.commit()

        chunk_tag = f"{job_subpath}/{fmt}"
        t_chunks = time.perf_counter()
        chunk_outputs = list(
            render_chunk_worker.starmap(
                [
                    (str(plan_v2_dir.relative_to(CAS_MOUNT_PATH)), idx, chunk_tag)
                    for idx in range(chunk_count)
                ]
            )
        )
        cas_volume.reload()
        chunks_wall_ms = int((time.perf_counter() - t_chunks) * 1000)
        chunks_usd = round(sum(float(c["estimated_usd"]) for c in chunk_outputs), 6)
        chunk_paths = [CAS_MOUNT_PATH / str(c["output_subpath"]) for c in chunk_outputs]
        checkpoint.record(
            StageMetric(
                stage="render_chunks",
                status="completed",
                idempotency_key=_stage_key("chunks", f"{plan.job_id}:{chunk_count}"),
                wall_ms=chunks_wall_ms,
                provider="modal_hyperframes_workers",
                estimated_usd=chunks_usd,
                output_artifacts=[str(p) for p in chunk_paths],
            )
        )
        checkpoint.save(checkpoint_path)

        assembled_hf_path = job_root / f"hf_assembled.{fmt}"
        with checkpoint.track_stage(
            "assemble_v2",
            _stage_key("assemble", f"{plan.job_id}:{chunk_count}"),
            state_path=checkpoint_path,
            provider="hyperframes_producer",
        ) as meta:
            assembled_hf_path.unlink(missing_ok=True)
            assemble_v2(plan_v2_dir, chunk_paths, assembled_hf_path, repo_root=repo_root)
            meta["output_artifacts"] = [str(assembled_hf_path)]
        overlay_render_path = assembled_hf_path

    final_deliverable = job_root / f"{plan.job_id}_master.mp4"
    if plan.render_strategy == "full_hf" and overlay_render_path is not None:
        final_deliverable = overlay_render_path
    else:
        with checkpoint.track_stage(
            "hybrid_master",
            _stage_key("master", edit_plan_json),
            state_path=checkpoint_path,
            provider="ffmpeg",
        ) as meta:
            t_m = time.perf_counter()
            assemble_hybrid_deliverable(
                plan,
                target,
                final_deliverable,
                overlay_video_path=overlay_render_path,
            )
            m_ms = int((time.perf_counter() - t_m) * 1000)
            meta["estimated_usd"] = estimate_modal_render_cost(m_ms)
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

    cas_volume.commit()
    return {
        "job_id": plan.job_id,
        "deliverable_path": str(final_deliverable),
        "deliverable_subpath": str(final_deliverable.relative_to(CAS_MOUNT_PATH)),
        "qc": qc.to_dict(),
        "telemetry": checkpoint.model_dump(),
    }


def submit_modal_render(
    plan: EditPlan,
    platform_target: PlatformTarget,
    *,
    output_path: Path | None = None,
    chunk_frames: int = 180,
) -> dict[str, Any]:
    """Upload local source assets to Modal CAS, run cloud render, and optionally download output."""
    cloud_plan = stage_local_assets_for_cloud(plan, cas_volume)
    summary = orchestrate_distributed_render.remote(
        cloud_plan.model_dump_json(exclude_none=True),
        platform_target.model_dump_json(exclude_none=True),
        chunk_frames=chunk_frames,
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
    output: str = "",
) -> None:
    """Stage local media on Modal CAS, run distributed render, and download master MP4."""
    import json

    from vedit.contracts import load_platform_targets

    plan = EditPlan.model_validate_json(Path(plan_file).read_text(encoding="utf-8"))
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise ValueError(f"Unknown platform target: {target_id}")
    target = PlatformTarget.model_validate(platforms[target_id])
    out_path = Path(output) if output else Path("renders") / f"{plan.job_id}_master.mp4"
    summary = submit_modal_render(
        plan,
        target,
        output_path=out_path,
        chunk_frames=chunk_frames,
    )
    print(json.dumps(summary, indent=2))
