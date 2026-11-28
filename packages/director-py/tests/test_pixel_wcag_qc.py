"""Tests for post-render pixel-level WCAG contrast and safe-zone intrusion QC."""

from __future__ import annotations

import subprocess
from pathlib import Path

from vedit.contracts import load_platform_targets
from vedit.models import AssetRef, EditPlan, OverlayCompositionOp, PlatformTarget, VideoClipOp


def _make_synthetic_clip(
    out_path: Path,
    *,
    width: int = 360,
    height: int = 640,
    bg_hex: str = "0x03161F",
    box: tuple[int, int, int, int, str] | None = None,
) -> Path:
    vf_parts = [f"color=c={bg_hex}:s={width}x{height}:r=30:d=1.0"]
    if box is not None:
        x, y, bw, bh, fg_hex = box
        vf_parts.append(f"drawbox=x={x}:y={y}:w={bw}:h={bh}:color={fg_hex}@1.0:t=fill")
    vf_parts.append("format=yuv420p")
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            ",".join(vf_parts),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-color_range",
            "tv",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return out_path


def _small_platform() -> PlatformTarget:
    raw = dict(load_platform_targets()["shorts_9x16_1080p"])
    raw["width"] = 360
    raw["height"] = 640
    return PlatformTarget.model_validate(raw)


def _sample_plan(video_path: Path, *, safe_band: str = "lower_third") -> EditPlan:
    return EditPlan(
        schema_version="1.0",
        job_id="qc_pixel_test",
        project_id="qc_proj",
        brand_id="editorial_explainer",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=1.0,
        fps=30,
        width=360,
        height=640,
        assets=[
            AssetRef(
                asset_id="v1",
                sha256="a" * 64,
                kind="video",
                path=str(video_path),
                duration_s=1.0,
            )
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v1",
                timeline_start_s=0.0,
                timeline_duration_s=1.0,
                source_start_s=0.0,
                role="a_roll",
            )
        ],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="cap_1",
                kind="caption_rail",
                timeline_start_s=0.1,
                timeline_duration_s=0.8,
                transparent=True,
                safe_band=safe_band,
                props={"text": "HIGH CONTRAST TEST"},
            )
        ],
        audio_tracks=[],
    )


def test_pixel_wcag_contrast_passes_high_contrast_and_flags_low_contrast(tmp_path: Path) -> None:
    from vedit.mastering.qc_audit import audit_rendered_frame_contrast

    platform = _small_platform()
    # Lower-third band on 360x640 sits around y=420..500; draw a crisp high-contrast ink block.
    good_mp4 = _make_synthetic_clip(
        tmp_path / "good.mp4",
        bg_hex="0x03161F",
        box=(90, 445, 180, 32, "0xF4F1EA"),
    )
    good_plan = _sample_plan(good_mp4)
    errs, warns, metrics = audit_rendered_frame_contrast(good_mp4, platform, plan=good_plan)
    assert errs == []
    assert not any(w.code == "PIXEL_CONTRAST_LOW" for w in warns)
    assert metrics["pixel_contrast_min_ratio"] >= 10.0
    assert metrics["safe_zone_pixel_diff_skipped"] == "no_base_or_alpha_stream"

    # Low-contrast gray-on-gray block (#7A7A7A on #666666 -> ratio ~1.3:1 < 4.5).
    bad_mp4 = _make_synthetic_clip(
        tmp_path / "bad.mp4",
        bg_hex="0x666666",
        box=(90, 445, 180, 32, "0x7A7A7A"),
    )
    bad_plan = _sample_plan(bad_mp4)
    b_errs, b_warns, b_metrics = audit_rendered_frame_contrast(bad_mp4, platform, plan=bad_plan)
    all_issues = [*b_errs, *b_warns]
    assert any(issue.code == "PIXEL_CONTRAST_LOW" for issue in all_issues)
    assert b_metrics["pixel_contrast_min_ratio"] < 4.5


def test_parse_ass_caption_boxes_and_audit_external_ass_pixels(tmp_path: Path) -> None:
    from vedit.mastering.qc_audit import (
        audit_mastered_deliverable,
        parse_ass_caption_boxes,
    )

    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(
        "[Script Info]\n"
        "PlayResX: 360\n"
        "PlayResY: 640\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Inter,28,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,0,0,1,2,0,2,20,20,160,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.10,0:00:00.90,Default,,0,0,0,,{\\fad(60,60)}SAMPLE CAPTION\n",
        encoding="utf-8",
    )

    boxes = parse_ass_caption_boxes(ass_path, 360, 640)
    assert len(boxes) == 1
    assert abs(boxes[0]["t_s"] - 0.5) < 0.05
    assert 0.5 < boxes[0]["rect"].top < boxes[0]["rect"].bottom < 0.9

    bad_mp4 = _make_synthetic_clip(
        tmp_path / "bad_ass.mp4",
        bg_hex="0x5E5E5E",
        box=(90, 440, 180, 34, "0x6E6E6E"),
    )
    platform = _small_platform()
    report = audit_mastered_deliverable(
        bad_mp4,
        platform,
        require_audio=False,
        check_visual=False,
        captions_ass_path=ass_path,
    )
    all_codes = {i.code for i in [*report.errors, *report.warnings]}
    assert "PIXEL_CONTRAST_LOW" in all_codes
    assert report.metrics["safe_zone_pixel_diff_skipped"] == "no_base_or_alpha_stream"


def test_safe_zone_pixel_intrusion_detected_when_base_video_provided(tmp_path: Path) -> None:
    from vedit.mastering.qc_audit import audit_rendered_frame_contrast

    platform = _small_platform()
    base_mp4 = _make_synthetic_clip(tmp_path / "base.mp4", bg_hex="0x08141E")
    # Paint a bright overlay banner directly inside safe_zone.top_pct (top 14% = y 0..89).
    comp_mp4 = _make_synthetic_clip(
        tmp_path / "comp.mp4",
        bg_hex="0x08141E",
        box=(10, 10, 340, 60, "0xF5F5F5"),
    )
    plan = _sample_plan(comp_mp4)
    errs, warns, metrics = audit_rendered_frame_contrast(
        comp_mp4,
        platform,
        plan=plan,
        base_video_path=base_mp4,
    )
    all_codes = {i.code for i in [*errs, *warns]}
    assert "SAFE_ZONE_PIXEL_INTRUSION" in all_codes
    assert metrics["safe_zone_pixel_intrusion_ratio"] > 0.05
