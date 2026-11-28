"""Tests for exact RationalTime arithmetic, NTSC dual schema fields, OTIO, and FFmpeg timebases."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from vedit.contracts import load_platform_targets, validate_against_contract
from vedit.models import AssetRef, EditPlan, PlatformTarget, VideoClipOp


def test_rational_time_ntsc_exact_arithmetic_has_zero_drift() -> None:
    from vedit.timebase import RationalTime, Timebase

    tb_ntsc = Timebase.from_fps(29.97)
    assert (tb_ntsc.num, tb_ntsc.den) == (30000, 1001)
    assert tb_ntsc.ffmpeg_rate_str == "30000/1001"
    assert tb_ntsc.ffmpeg_timebase_str == "1001/30000"

    tb_film = Timebase.from_fps(23.976)
    assert (tb_film.num, tb_film.den) == (24000, 1001)

    tb_60 = Timebase.from_fps(59.94)
    assert (tb_60.num, tb_60.den) == (60000, 1001)

    tb_30 = Timebase.from_fps(30)
    assert (tb_30.num, tb_30.den) == (30, 1)
    assert tb_30.ffmpeg_rate_str == "30/1"
    assert tb_30.ffmpeg_timebase_str == "1/30"

    # 10,000 sequential 1-frame additions at 30000/1001 stay exact with zero float drift.
    cursor = RationalTime(0, tb_ntsc)
    step = RationalTime(1, tb_ntsc)
    for _ in range(10_000):
        cursor = cursor + step
    assert cursor.value == 10_000
    assert cursor.to_fraction() == Fraction(10_000 * 1001, 30_000)


def test_edit_plan_dual_rational_frame_fields_validate_and_reject_conflicts() -> None:
    base_kwargs = dict(
        schema_version="1.0",
        job_id="ntsc_job_01",
        project_id="ntsc_proj",
        brand_id="editorial_explainer",
        platform_target_id="youtube_16x9_1080p",
        render_strategy="hybrid",
        duration_s=10.01,
        fps=29.97,
        timebase={"num": 30000, "den": 1001},
        width=1920,
        height=1080,
        assets=[
            AssetRef(
                asset_id="v1",
                sha256="a" * 64,
                kind="video",
                path="media/a.mp4",
                duration_s=10.01,
            )
        ],
        overlay_compositions=[],
        audio_tracks=[],
    )

    # Consistent frame & float timestamps pass both Pydantic and JSON Schema.
    good = EditPlan(
        **base_kwargs,
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v1",
                timeline_start_s=0.0,
                timeline_duration_s=10.01,
                source_start_s=0.0,
                start_frame=0,
                duration_frames=300,
                source_start_frame=0,
                role="a_roll",
            )
        ],
    )
    errs = validate_against_contract(good.model_dump(exclude_none=True), "edit_plan.schema.json")
    assert errs == [], errs

    # Conflicting float (10.01s = 300 frames) vs frame (duration_frames=250) must fail loudly.
    with pytest.raises(ValueError, match="duration_frames"):
        EditPlan(
            **base_kwargs,
            video_tracks=[
                VideoClipOp(
                    clip_id="c1",
                    asset_id="v1",
                    timeline_start_s=0.0,
                    timeline_duration_s=10.01,
                    source_start_s=0.0,
                    start_frame=0,
                    duration_frames=250,
                    role="a_roll",
                )
            ],
        )


def test_platform_target_accepts_ntsc_fractional_fps_and_ffmpeg_uses_rational_rate() -> None:
    targets = load_platform_targets()
    ntsc_payload = dict(targets["youtube_16x9_1080p"])
    ntsc_payload["platform_id"] = "broadcast_ntsc_1080p"
    ntsc_payload["fps"] = 29.97
    ntsc_payload["timebase"] = {"num": 30000, "den": 1001}

    errs = validate_against_contract(ntsc_payload, "platform_target.schema.json")
    assert errs == [], errs
    pt = PlatformTarget.model_validate(ntsc_payload)
    assert pt.fps == 29.97

    from vedit.mastering.ffmpeg_master import _video_codec_args

    args = _video_codec_args(pt)
    r_idx = args.index("-r")
    assert args[r_idx + 1] == "30000/1001"


def test_otio_bridge_uses_exact_rational_frames(tmp_path: Path) -> None:
    otio = pytest.importorskip("opentimelineio")
    from vedit.interop.otio_bridge import export_edit_plan_to_otio

    plan = EditPlan(
        schema_version="1.0",
        job_id="otio_ntsc",
        project_id="p1",
        brand_id="editorial_explainer",
        platform_target_id="youtube_16x9_1080p",
        render_strategy="hybrid",
        duration_s=10.01,
        fps=29.97,
        timebase={"num": 30000, "den": 1001},
        width=1920,
        height=1080,
        assets=[
            AssetRef(
                asset_id="v1",
                sha256="b" * 64,
                kind="video",
                path="media/a.mp4",
                duration_s=10.01,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v1",
                timeline_start_s=0.0,
                timeline_duration_s=10.01,
                source_start_s=0.0,
                start_frame=0,
                duration_frames=300,
                source_start_frame=0,
                role="a_roll",
            )
        ],
        overlay_compositions=[],
        audio_tracks=[],
    )
    out_otio = export_edit_plan_to_otio(plan, tmp_path / "timeline.otio")
    tl = otio.adapters.read_from_file(str(out_otio))
    clip = tl.find_clips()[0]
    assert clip.source_range.duration.value == 300.0
    assert abs(clip.source_range.duration.rate - (30000.0 / 1001.0)) < 1e-6
