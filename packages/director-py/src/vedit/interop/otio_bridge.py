"""OpenTimelineIO export bridge translating EditPlan manifests to `.otio` timelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vedit.models import AudioTrackOp, EditPlan, VideoClipOp
from vedit.project_workspace import resolve_plan_asset_paths
from vedit.timebase import RationalTime, Timebase


def _require_otio() -> Any:
    try:
        import opentimelineio as otio
    except ImportError as exc:
        raise RuntimeError(
            "OpenTimelineIO is not installed. Install the optional interop extra with "
            "`uv sync --extra interop` in `packages/director-py`."
        ) from exc
    return otio


def _resolve_plan_timebase(plan: EditPlan) -> Timebase:
    if plan.timebase is not None:
        return Timebase(plan.timebase.num, plan.timebase.den)
    return Timebase.from_fps(plan.fps)


def _frames_or_seconds(frame_val: int | None, seconds: float, tb: Timebase) -> int:
    if frame_val is not None:
        return int(frame_val)
    return RationalTime.from_seconds(seconds, tb).value


def _otio_rt(otio: Any, frames: int, tb: Timebase) -> Any:
    return otio.opentime.RationalTime(float(frames), tb.fps_float)


def _build_external_ref(otio: Any, media_path: str, duration_s: float | None, tb: Timebase) -> Any:
    available_range = None
    if duration_s is not None and duration_s > 0:
        available_range = otio.opentime.TimeRange(
            start_time=_otio_rt(otio, 0, tb),
            duration=_otio_rt(otio, RationalTime.from_seconds(duration_s, tb).value, tb),
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
    tb: Timebase,
) -> None:
    track = otio.schema.Track(name="Video_Main", kind=otio.schema.TrackKind.Video)
    cursor_frames = 0
    for clip in sorted(
        clips,
        key=lambda c: _frames_or_seconds(c.start_frame, c.timeline_start_s, tb),
    ):
        clip_start = _frames_or_seconds(clip.start_frame, clip.timeline_start_s, tb)
        clip_dur = max(1, _frames_or_seconds(clip.duration_frames, clip.timeline_duration_s, tb))
        clip_src = _frames_or_seconds(clip.source_start_frame, clip.source_start_s, tb)
        gap_frames = clip_start - cursor_frames
        if gap_frames > 0:
            track.append(
                otio.schema.Gap(
                    source_range=otio.opentime.TimeRange(
                        start_time=_otio_rt(otio, 0, tb),
                        duration=_otio_rt(otio, gap_frames, tb),
                    )
                )
            )
        asset = assets_by_id.get(clip.asset_id)
        target_url = asset.path if asset is not None else clip.asset_id
        dur_hint = asset.duration_s if asset is not None else None
        media_ref = _build_external_ref(otio, target_url, dur_hint, tb)
        source_range = otio.opentime.TimeRange(
            start_time=_otio_rt(otio, clip_src, tb),
            duration=_otio_rt(otio, clip_dur, tb),
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
        cursor_frames = clip_start + clip_dur
    timeline.tracks.append(track)


def _append_audio_group_track(
    otio: Any,
    timeline: Any,
    group_name: str,
    tracks_in_group: list[AudioTrackOp],
    assets_by_id: dict[str, Any],
    tb: Timebase,
) -> None:
    if not tracks_in_group:
        return
    # Partition overlapping items within the same group into separate non-overlapping lanes.
    lanes: list[list[AudioTrackOp]] = []
    lane_ends: list[int] = []
    for item in sorted(
        tracks_in_group,
        key=lambda t: _frames_or_seconds(t.start_frame, t.timeline_start_s, tb),
    ):
        item_start = _frames_or_seconds(item.start_frame, item.timeline_start_s, tb)
        item_dur = max(1, _frames_or_seconds(item.duration_frames, item.timeline_duration_s, tb))
        placed = False
        for lane_idx, end_frames in enumerate(lane_ends):
            if item_start >= end_frames:
                lanes[lane_idx].append(item)
                lane_ends[lane_idx] = item_start + item_dur
                placed = True
                break
        if not placed:
            lanes.append([item])
            lane_ends.append(item_start + item_dur)

    for lane_idx, lane_items in enumerate(lanes):
        suffix = "" if lane_idx == 0 else f"_{lane_idx + 1}"
        track_name = f"Audio_{group_name}{suffix}"
        track = otio.schema.Track(name=track_name, kind=otio.schema.TrackKind.Audio)
        cursor_frames = 0
        for item in lane_items:
            item_start = _frames_or_seconds(item.start_frame, item.timeline_start_s, tb)
            item_dur = max(
                1, _frames_or_seconds(item.duration_frames, item.timeline_duration_s, tb)
            )
            item_src = _frames_or_seconds(item.source_start_frame, item.source_start_s, tb)
            gap_frames = item_start - cursor_frames
            if gap_frames > 0:
                track.append(
                    otio.schema.Gap(
                        source_range=otio.opentime.TimeRange(
                            start_time=_otio_rt(otio, 0, tb),
                            duration=_otio_rt(otio, gap_frames, tb),
                        )
                    )
                )
                cursor_frames += gap_frames
            asset = assets_by_id.get(item.asset_id)
            target_url = asset.path if asset is not None else item.asset_id
            dur_hint = asset.duration_s if asset is not None else None
            media_ref = _build_external_ref(otio, target_url, dur_hint, tb)
            source_range = otio.opentime.TimeRange(
                start_time=_otio_rt(otio, item_src, tb),
                duration=_otio_rt(otio, item_dur, tb),
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
            cursor_frames += item_dur
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
    tb = _resolve_plan_timebase(effective_plan)
    assets_by_id = {asset.asset_id: asset for asset in effective_plan.assets}

    timeline = otio.schema.Timeline(
        name=effective_plan.job_id,
        global_start_time=_otio_rt(otio, 0, tb),
        metadata={
            "vedit": {
                "schema_version": effective_plan.schema_version,
                "project_id": effective_plan.project_id,
                "brand_id": effective_plan.brand_id,
                "platform_target_id": effective_plan.platform_target_id,
                "render_strategy": effective_plan.render_strategy,
                "width": effective_plan.width,
                "height": effective_plan.height,
                "fps": tb.fps_float,
                "timebase": {"num": tb.num, "den": tb.den},
                "duration_s": effective_plan.duration_s,
            }
        },
    )

    _append_video_track(otio, timeline, effective_plan.video_tracks, assets_by_id, tb)

    for group in ("voiceover", "music", "ambience", "room_tone", "sfx", "program_mix"):
        grouped = [t for t in effective_plan.audio_tracks if t.audio_group == group]
        _append_audio_group_track(otio, timeline, group, grouped, assets_by_id, tb)

    for ov in sorted(
        effective_plan.overlay_compositions,
        key=lambda o: _frames_or_seconds(o.start_frame, o.timeline_start_s, tb),
    ):
        ov_start = _frames_or_seconds(ov.start_frame, ov.timeline_start_s, tb)
        ov_dur = max(1, _frames_or_seconds(ov.duration_frames, ov.timeline_duration_s, tb))
        marker = otio.schema.Marker(
            name=ov.overlay_id,
            marked_range=otio.opentime.TimeRange(
                start_time=_otio_rt(otio, ov_start, tb),
                duration=_otio_rt(otio, ov_dur, tb),
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
