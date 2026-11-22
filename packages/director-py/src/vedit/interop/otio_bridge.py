"""OpenTimelineIO export bridge translating EditPlan manifests to `.otio` timelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vedit.models import AudioTrackOp, EditPlan, VideoClipOp
from vedit.project_workspace import resolve_plan_asset_paths


def _require_otio() -> Any:
    try:
        import opentimelineio as otio
    except ImportError as exc:
        raise RuntimeError(
            "OpenTimelineIO is not installed. Install the optional interop extra with "
            "`uv sync --extra interop` in `packages/director-py`."
        ) from exc
    return otio


def _build_external_ref(otio: Any, media_path: str, duration_s: float | None, fps: float) -> Any:
    available_range = None
    if duration_s is not None and duration_s > 0:
        available_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0.0, fps),
            duration=otio.opentime.RationalTime(round(duration_s * fps, 4), fps),
        )
    return otio.schema.ExternalReference(
        target_url=media_path,
        available_range=available_range,
    )


def _append_video_track(
    otio: Any,
    timeline: Any,
    clips: list[VideoClipOp],
    assets_by_id: dict[str, Any],
    fps: float,
) -> None:
    track = otio.schema.Track(name="Video_Main", kind=otio.schema.TrackKind.Video)
    cursor_s = 0.0
    for clip in sorted(clips, key=lambda c: c.timeline_start_s):
        gap_s = round(clip.timeline_start_s - cursor_s, 4)
        if gap_s > 0.01:
            track.append(
                otio.schema.Gap(
                    source_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(0.0, fps),
                        duration=otio.opentime.RationalTime(round(gap_s * fps, 4), fps),
                    )
                )
            )
        asset = assets_by_id.get(clip.asset_id)
        target_url = asset.path if asset is not None else clip.asset_id
        dur_hint = asset.duration_s if asset is not None else None
        media_ref = _build_external_ref(otio, target_url, dur_hint, fps)
        source_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(round(clip.source_start_s * fps, 4), fps),
            duration=otio.opentime.RationalTime(round(clip.timeline_duration_s * fps, 4), fps),
        )
        otio_clip = otio.schema.Clip(
            name=clip.clip_id,
            media_reference=media_ref,
            source_range=source_range,
            metadata={
                "vedit": {
                    "asset_id": clip.asset_id,
                    "role": clip.role,
                    "scale": clip.scale,
                    "transition_in": clip.transition_in,
                }
            },
        )
        track.append(otio_clip)
        cursor_s = clip.timeline_start_s + clip.timeline_duration_s
    timeline.tracks.append(track)


def _append_audio_group_track(
    otio: Any,
    timeline: Any,
    group_name: str,
    tracks_in_group: list[AudioTrackOp],
    assets_by_id: dict[str, Any],
    fps: float,
) -> None:
    if not tracks_in_group:
        return
    # Partition overlapping items within the same group into separate non-overlapping lanes.
    lanes: list[list[AudioTrackOp]] = []
    lane_ends: list[float] = []
    for item in sorted(tracks_in_group, key=lambda t: t.timeline_start_s):
        placed = False
        for lane_idx, end_s in enumerate(lane_ends):
            if item.timeline_start_s >= end_s - 1e-4:
                lanes[lane_idx].append(item)
                lane_ends[lane_idx] = item.timeline_start_s + item.timeline_duration_s
                placed = True
                break
        if not placed:
            lanes.append([item])
            lane_ends.append(item.timeline_start_s + item.timeline_duration_s)

    for lane_idx, lane_items in enumerate(lanes):
        suffix = "" if lane_idx == 0 else f"_{lane_idx + 1}"
        track_name = f"Audio_{group_name}{suffix}"
        track = otio.schema.Track(name=track_name, kind=otio.schema.TrackKind.Audio)
        cursor_s = 0.0
        for item in lane_items:
            gap_s = round(item.timeline_start_s - cursor_s, 4)
            if gap_s > 1e-4:
                track.append(
                    otio.schema.Gap(
                        source_range=otio.opentime.TimeRange(
                            start_time=otio.opentime.RationalTime(0.0, fps),
                            duration=otio.opentime.RationalTime(round(gap_s * fps, 4), fps),
                        )
                    )
                )
                cursor_s += gap_s
            asset = assets_by_id.get(item.asset_id)
            target_url = asset.path if asset is not None else item.asset_id
            dur_hint = asset.duration_s if asset is not None else None
            media_ref = _build_external_ref(otio, target_url, dur_hint, fps)
            source_range = otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(round(item.source_start_s * fps, 4), fps),
                duration=otio.opentime.RationalTime(round(item.timeline_duration_s * fps, 4), fps),
            )
            otio_clip = otio.schema.Clip(
                name=item.track_id,
                media_reference=media_ref,
                source_range=source_range,
                metadata={
                    "vedit": {
                        "asset_id": item.asset_id,
                        "audio_group": item.audio_group,
                        "gain_db": item.gain_db,
                        "carve_against_group": item.carve_against_group,
                        "carve_strength": item.carve_strength,
                    }
                },
            )
            track.append(otio_clip)
            cursor_s += item.timeline_duration_s
        timeline.tracks.append(track)


def export_edit_plan_to_otio(
    plan: EditPlan,
    output_path: Path,
    *,
    base_dir: Path | None = None,
    resolve_paths: bool = False,
) -> Path:
    """Serialize an `EditPlan` into an OpenTimelineIO `.otio` timeline file.

    By default, preserves relative `AssetRef.path` strings for portable NLE interchange;
    set `resolve_paths=True` with `base_dir` to emit resolved absolute paths.
    """
    otio = _require_otio()
    effective_plan = (
        resolve_plan_asset_paths(plan, base_dir=base_dir)
        if resolve_paths and base_dir is not None
        else plan
    )
    fps = float(effective_plan.fps)
    assets_by_id = {asset.asset_id: asset for asset in effective_plan.assets}

    timeline = otio.schema.Timeline(
        name=effective_plan.job_id,
        global_start_time=otio.opentime.RationalTime(0.0, fps),
        metadata={
            "vedit": {
                "schema_version": effective_plan.schema_version,
                "project_id": effective_plan.project_id,
                "brand_id": effective_plan.brand_id,
                "platform_target_id": effective_plan.platform_target_id,
                "render_strategy": effective_plan.render_strategy,
                "width": effective_plan.width,
                "height": effective_plan.height,
                "fps": fps,
                "duration_s": effective_plan.duration_s,
            }
        },
    )

    _append_video_track(otio, timeline, effective_plan.video_tracks, assets_by_id, fps)

    for group in ("voiceover", "music", "sfx", "program_mix"):
        grouped = [t for t in effective_plan.audio_tracks if t.audio_group == group]
        _append_audio_group_track(otio, timeline, group, grouped, assets_by_id, fps)

    for ov in sorted(effective_plan.overlay_compositions, key=lambda o: o.timeline_start_s):
        marker = otio.schema.Marker(
            name=ov.overlay_id,
            marked_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(round(ov.timeline_start_s * fps, 4), fps),
                duration=otio.opentime.RationalTime(round(ov.timeline_duration_s * fps, 4), fps),
            ),
            color=(
                otio.schema.MarkerColor.CYAN
                if ov.kind == "caption_rail"
                else otio.schema.MarkerColor.YELLOW
            ),
            metadata={
                "vedit": {
                    "kind": ov.kind,
                    "safe_band": ov.safe_band,
                    "template_id": ov.template_id,
                    "variables": ov.variables,
                }
            },
        )
        timeline.tracks.markers.append(marker)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(timeline, str(output_path))
    return output_path
