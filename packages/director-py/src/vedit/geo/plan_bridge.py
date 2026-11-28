"""Canonical EditPlan bridge translating baked geospatial acts into the unified mastering spine."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root, load_platform_targets
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    EditPlan,
    PlatformTarget,
    TimebaseSpec,
    VideoClipOp,
)
from vedit.timebase import RationalTime, Timebase

_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_RGBA_OVERLAY_TRANSITIONS = frozenset({"disc_sweep", "feathered_dark_wipe"})


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe_duration_s(media_path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0.0, float(proc.stdout.strip()))


def _sanitize_slug(raw: str, fallback: str = "geo_scene") -> str:
    cleaned = _SAFE_ID_RE.sub("_", raw.strip()).strip("._-")
    if not cleaned or not cleaned[0].isalnum():
        return fallback
    return cleaned


def resolve_geo_brand_id(
    scene_spec: dict[str, Any],
    scene_file: Path,
    *,
    explicit_brand_id: str | None = None,
) -> str | None:
    """Resolve brand_id neutrally without hardcoding a default brand in core."""
    if explicit_brand_id and explicit_brand_id.strip():
        return explicit_brand_id.strip()
    spec_brand = scene_spec.get("brand_id")
    if isinstance(spec_brand, str) and spec_brand.strip():
        return spec_brand.strip()

    cursor = scene_file.expanduser().resolve().parent
    for parent in (cursor, *cursor.parents[:3]):
        manifest = parent / "project.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                bid = data.get("brand_id")
                if isinstance(bid, str) and bid.strip():
                    return bid.strip()
            except (OSError, ValueError):
                continue
    return None


def build_edit_plan_from_geo_acts(
    scene_file: Path,
    acts_dir: Path,
    audio_file: Path,
    *,
    platform_id: str | None = None,
    brand_id: str | None = None,
    repo_root: Path | None = None,
) -> tuple[EditPlan, PlatformTarget, list[float]]:
    """Build a schema-valid canonical EditPlan from baked map_scene acts and mixed audio."""
    root = repo_root or find_repo_root()
    scene_p = scene_file.expanduser().resolve()
    spec = json.loads(scene_p.read_text(encoding="utf-8"))
    acts = spec.get("acts") or []
    if not acts:
        raise ValueError("map_scene.json contains no acts to master.")

    width = int(spec.get("width", 1080))
    height = int(spec.get("height", 1920))
    fps = float(spec.get("fps", 30))
    acts_dir_p = acts_dir.expanduser().resolve()
    audio_p = audio_file.expanduser().resolve()
    if not audio_p.is_file():
        raise FileNotFoundError(f"Missing audio file: {audio_p}")

    resolved_plat_id = platform_id or (
        "shorts_9x16_1080p" if height > width else "youtube_16x9_1080p"
    )
    targets = load_platform_targets(repo_root=root)
    if resolved_plat_id not in targets:
        raise ValueError(f"Unknown platform target: {resolved_plat_id!r}")
    target_data = dict(targets[resolved_plat_id])
    tb = Timebase.from_fps(fps)
    tb_spec = TimebaseSpec(num=tb.num, den=tb.den)
    target_data["width"] = width
    target_data["height"] = height
    target_data["fps"] = fps
    target_data["timebase"] = {"num": tb.num, "den": tb.den}
    target = PlatformTarget.model_validate(target_data)

    audio_dur = _probe_duration_s(audio_p)
    assets: list[AssetRef] = []
    video_tracks: list[VideoClipOp] = []
    disc_cuts: list[float] = []
    acc_s = 0.0

    for idx, act in enumerate(acts):
        act_id = str(act.get("act_id") or f"act_{idx:02d}")
        out_name = str(act.get("output_file") or f"{act_id}.mp4")
        clip_path = acts_dir_p / out_name
        if not clip_path.is_file():
            raise FileNotFoundError(f"Missing baked act video: {clip_path}")

        act_dur = float(act.get("duration_s") or 0.0)
        if act_dur <= 0.0:
            act_dur = _probe_duration_s(clip_path)
        if act_dur <= 0.0:
            raise ValueError(f"Act {act_id!r} has non-positive duration.")

        asset_id = f"geo_act_{idx:02d}"
        assets.append(
            AssetRef(
                asset_id=asset_id,
                sha256=_sha256_file(clip_path),
                kind="video",
                path=str(clip_path),
                duration_s=round(act_dur, 4),
                has_audio=False,
            )
        )

        raw_trans = str(act.get("transition_in") or "").strip().lower()
        clip_trans: str | None = None
        if idx > 0 and raw_trans in _RGBA_OVERLAY_TRANSITIONS:
            disc_cuts.append(round(acc_s, 3))
            # Omit xfade transition_in here so timed RGBA transition_overlays do not double-apply.
            clip_trans = None
        elif idx > 0 and raw_trans:
            clip_trans = raw_trans

        act_kind = str(act.get("kind") or act.get("mode") or act.get("type") or "map").lower()
        content_type = "diagram" if act_kind in {"cutaway_2d", "blueprint_paper"} else "map"
        start_f = RationalTime.from_seconds(acc_s, tb).value
        dur_f = max(1, RationalTime.from_seconds(act_dur, tb).value)
        video_tracks.append(
            VideoClipOp(
                clip_id=f"clip_{idx:02d}_{_sanitize_slug(act_id, f'act_{idx:02d}')}",
                asset_id=asset_id,
                timeline_start_s=round(acc_s, 4),
                timeline_duration_s=round(act_dur, 4),
                source_start_s=0.0,
                start_frame=start_f,
                duration_frames=dur_f,
                source_start_frame=0,
                role="a_roll",
                content_type=content_type,  # type: ignore[arg-type]
                reframed_to_target=True,
                transition_in=clip_trans,
            )
        )
        acc_s += act_dur

    target_dur = min(acc_s, audio_dur) if acc_s > 0 and audio_dur > 0 else max(acc_s, audio_dur)
    audio_asset_id = "geo_program_mix"
    assets.append(
        AssetRef(
            asset_id=audio_asset_id,
            sha256=_sha256_file(audio_p),
            kind="audio_speech",
            path=str(audio_p),
            duration_s=round(audio_dur, 4),
            has_audio=True,
        )
    )
    audio_tracks = [
        AudioTrackOp(
            track_id="program_mix_01",
            asset_id=audio_asset_id,
            audio_group="program_mix",
            timeline_start_s=0.0,
            timeline_duration_s=round(target_dur, 4),
            source_start_s=0.0,
            gain_db=0.0,
        )
    ]

    resolved_brand = resolve_geo_brand_id(spec, scene_p, explicit_brand_id=brand_id)
    project_id = _sanitize_slug(str(spec.get("project_id") or scene_p.parent.name), "geo_project")
    job_hash = hashlib.sha256(f"{scene_p}:{target_dur:.3f}".encode()).hexdigest()[:12]

    plan = EditPlan(
        schema_version="1.0",
        job_id=f"geo_master_{job_hash}",
        project_id=project_id,
        brand_id=resolved_brand or "unbranded",
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=round(target_dur, 4),
        fps=fps,
        timebase=tb_spec,
        width=width,
        height=height,
        assets=assets,
        video_tracks=video_tracks,
        overlay_compositions=[],
        audio_tracks=audio_tracks,
    )
    return plan, target, disc_cuts
