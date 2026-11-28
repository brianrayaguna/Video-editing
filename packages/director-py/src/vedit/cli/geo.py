"""Thin Typer CLI adapter for geospatial tile prep, scene baking, captions, and audio mixing."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer

from vedit.contracts import find_repo_root
from vedit.director.camera_moves import camera_jitter_report, smooth_scene_keys
from vedit.geo.audio_mix import (
    _resolve_studio_bgm,
    derive_sfx_events_from_scene,
    mix_geo_audio,
    synthesize_documentary_bgm,
)
from vedit.geo.captions import (
    _escape_geo_ass_text,
    _fmt_ass_time,
    _segments_from_words,
    build_brand_ass_captions,
    build_captions_for_brand,
    build_geoverum_ass_captions,
)
from vedit.geo.scene_baker import bake_geo_scene, fetch_geo_fonts, load_fetch_fonts_module
from vedit.geo.scene_validator import (
    _approx_viewport_pct,
    _as_finite_float,
    _haversine_m,
    _load_scene_vectors,
    _resolve_geom_ref,
    _separately_traced_parts,
    validate_map_scene,
)
from vedit.geo.tiles import (
    _TILE_ABSENT_HTTP_CODES,
    _deg2num,
    _enum_bbox_tiles,
    _extract_tile_list,
    _fetch_tile_set,
    _has_image_magic,
    _national_ortho_url,
    _parse_tile_coord_row,
    _s2_cloudless_url,
    fill_coverage_gaps,
    hq_tile_urls,
    parse_tile_list,
    prepare_geo_project,
    split_coverage_gaps,
)
from vedit.geo.vectors import (
    _clip_ring_half_plane,
    _simplify_geom,
    _simplify_ring,
    extract_project_vectors,
    filter_polygons_by_bbox,
    split_polygon_by_longitude,
)

geo_app = typer.Typer(
    help="Prepare offline AOI satellite tiles/GeoJSON vectors and bake declarative map scenes."
)


@geo_app.command("prepare")
def geo_prepare_cmd(
    out_file: Annotated[Path, typer.Option("--out-file", "-o")],
    bbox: Annotated[list[str] | None, typer.Option("--bbox")] = None,
    country: Annotated[list[str] | None, typer.Option("--country")] = None,
    continent: Annotated[list[str] | None, typer.Option("--continent")] = None,
    province: Annotated[list[str] | None, typer.Option("--province")] = None,
    province_lat_min: Annotated[float | None, typer.Option("--province-lat-min")] = None,
    province_lon_max: Annotated[float | None, typer.Option("--province-lon-max")] = None,
    grade_tiles: Annotated[bool, typer.Option("--grade/--no-grade")] = True,
    hq_aerial: Annotated[bool | None, typer.Option("--hq/--no-hq")] = None,
    provider: Annotated[str, typer.Option("--provider")] = "auto",
    max_tiles: Annotated[int | None, typer.Option("--max-tiles")] = None,
    tile_list: Annotated[Path | None, typer.Option("--tile-list")] = None,
) -> None:
    """Fetch project AOI satellite tiles (without dirtying MANIFEST.json) and extract GeoJSON."""
    prepare_geo_project(
        out_file,
        bbox=bbox,
        country=country,
        continent=continent,
        province=province,
        province_lat_min=province_lat_min,
        province_lon_max=province_lon_max,
        grade_tiles=grade_tiles,
        hq_aerial=hq_aerial,
        provider=provider,
        max_tiles=max_tiles,
        tile_list=tile_list,
        repo_root=find_repo_root(),
        fetch_fn=_fetch_tile_set,
        extract_vectors_fn=extract_project_vectors,
    )


@geo_app.command("validate-scene")
def geo_validate_scene_cmd(
    scene_file: Annotated[Path, typer.Option("--scene-file")],
) -> None:
    """Validate map_scene.json against scene craft, sharpness, and clutter guardrails."""
    root = find_repo_root()
    scene_path = scene_file.expanduser().resolve()
    spec = json.loads(scene_path.read_text(encoding="utf-8"))
    report = validate_map_scene(spec, repo_root=root, base_dir=scene_path.parent)
    typer.echo(json.dumps(report, indent=2))
    if not report["ok"]:
        raise typer.Exit(code=1)


@geo_app.command("build-captions")
def geo_build_captions_cmd(
    transcript_file: Annotated[Path, typer.Argument()],
    out_file: Annotated[Path, typer.Option("--out-file", "-o")],
    width: Annotated[int, typer.Option("--width")] = 1080,
    height: Annotated[int, typer.Option("--height")] = 1920,
    speed: Annotated[float, typer.Option("--speed")] = 1.0,
    max_words: Annotated[int | None, typer.Option("--max-words")] = None,
    font_size: Annotated[int | None, typer.Option("--font-size")] = None,
    margin_v: Annotated[int | None, typer.Option("--margin-v")] = None,
    fade_in_ms: Annotated[int | None, typer.Option("--fade-in-ms")] = None,
    fade_out_ms: Annotated[int | None, typer.Option("--fade-out-ms")] = None,
    gap_ms: Annotated[int | None, typer.Option("--gap-ms")] = None,
    brand: Annotated[str | None, typer.Option("--brand")] = None,
    outline_px: Annotated[float | None, typer.Option("--outline-px")] = None,
    shadow_px: Annotated[float | None, typer.Option("--shadow-px")] = None,
    blur_px: Annotated[float | None, typer.Option("--blur-px")] = None,
) -> None:
    """Generate calibrated boxless bottom-band ASS subtitles."""
    build_captions_for_brand(
        transcript_file,
        out_file,
        width=width,
        height=height,
        speed=speed,
        max_words=max_words,
        font_size=font_size,
        margin_v=margin_v,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        gap_ms=gap_ms,
        brand=brand,
        outline_px=outline_px,
        shadow_px=shadow_px,
        blur_px=blur_px,
    )


@geo_app.command("mix-audio")
def geo_mix_audio_cmd(
    scene_file: Annotated[Path, typer.Option("--scene-file")],
    voice_file: Annotated[Path, typer.Option("--voice")],
    out_file: Annotated[Path, typer.Option("--out-file", "-o")],
    bgm_file: Annotated[Path | None, typer.Option("--bgm")] = None,
    bgm_second: Annotated[Path | None, typer.Option("--bgm-second")] = None,
    bgm_switch_s: Annotated[float | None, typer.Option("--bgm-switch-s")] = None,
    bgm_gain_db: Annotated[float, typer.Option("--bgm-gain-db")] = -16.0,
    bgm_second_gain_db: Annotated[float | None, typer.Option("--bgm-second-gain-db")] = None,
    ambience_file: Annotated[Path | None, typer.Option("--ambience")] = None,
    ambience_gain_db: Annotated[float, typer.Option("--ambience-gain-db")] = -26.0,
    extra_sfx_json: Annotated[Path | None, typer.Option("--extra-sfx")] = None,
    storyboard_file: Annotated[Path | None, typer.Option("--storyboard-file")] = None,
    loudness_profile: Annotated[str, typer.Option("--loudness-profile")] = "streaming_web",
    narrative_fx: Annotated[bool, typer.Option("--narrative-fx/--no-narrative-fx")] = True,
    allow_synth_fx: Annotated[bool, typer.Option("--allow-synth-fx/--no-allow-synth-fx")] = False,
    room_tone: Annotated[bool, typer.Option("--room-tone/--no-room-tone")] = True,
    room_tone_db: Annotated[float, typer.Option("--room-tone-db")] = -52.0,
) -> None:
    """Mix voiceover + studio BGM + scene-synced SFX with two-pass loudnorm."""
    mix_geo_audio(
        scene_file,
        voice_file,
        out_file,
        bgm_file=bgm_file,
        bgm_second=bgm_second,
        bgm_switch_s=bgm_switch_s,
        bgm_gain_db=bgm_gain_db,
        bgm_second_gain_db=bgm_second_gain_db,
        ambience_file=ambience_file,
        ambience_gain_db=ambience_gain_db,
        extra_sfx_json=extra_sfx_json,
        storyboard_file=storyboard_file,
        loudness_profile=loudness_profile,
        narrative_fx=narrative_fx,
        allow_synth_fx=allow_synth_fx,
        room_tone=room_tone,
        room_tone_db=room_tone_db,
    )


@geo_app.command("bake-scene")
def geo_bake_scene_cmd(
    scene_file: Annotated[Path, typer.Option("--scene-file")],
    out_dir: Annotated[Path, typer.Option("--out-dir", "-o")],
    skip_validate: Annotated[bool, typer.Option("--skip-validate")] = False,
    fill_tiles: Annotated[bool, typer.Option("--fill-tiles")] = False,
    only_act: Annotated[list[str] | None, typer.Option("--only-act")] = None,
    preview_keyframes: Annotated[int | None, typer.Option("--preview-keyframes")] = None,
) -> None:
    """Expand smooth camera plans and bake declarative world-space map scenes via MapLibre."""
    bake_geo_scene(
        scene_file,
        out_dir,
        skip_validate=skip_validate,
        fill_tiles=fill_tiles,
        only_act=only_act,
        preview_keyframes=preview_keyframes,
        repo_root=find_repo_root(),
        which_fn=shutil.which,
        run_fn=subprocess.run,
        fill_gaps_fn=fill_coverage_gaps,
    )


@geo_app.command("camera-track")
def geo_camera_track_cmd(
    track_file: Annotated[Path, typer.Argument()],
    out: Annotated[Path | None, typer.Option("--out", "-o")] = None,
    window_s: Annotated[float, typer.Option()] = 0.6,
    cut: Annotated[list[float] | None, typer.Option("--cut")] = None,
    anchor: Annotated[list[float] | None, typer.Option("--anchor")] = None,
    max_shift_px: Annotated[float, typer.Option()] = 24.0,
    max_zoom_shift: Annotated[float, typer.Option()] = 0.08,
    fps: Annotated[float, typer.Option()] = 30.0,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Measure camera shake in a measured track and optionally write a denoised copy."""
    keys = json.loads(track_file.expanduser().read_text(encoding="utf-8"))
    cuts = list(cut or [])
    before = camera_jitter_report(keys, fps=fps, cuts=cuts)
    report: dict[str, Any] = {"before": {k: v for k, v in before.items() if k != "flagged"}}
    if out is not None:
        smoothed = smooth_scene_keys(
            keys,
            window_s=window_s,
            cuts=cuts,
            anchors=list(anchor or []),
            max_shift_px=max_shift_px,
            max_zoom_shift=max_zoom_shift,
        )
        out.expanduser().write_text(json.dumps(smoothed), encoding="utf-8")
        after = camera_jitter_report(smoothed, fps=fps, cuts=cuts)
        report["after"] = {k: v for k, v in after.items() if k != "flagged"}
        report["out"] = str(out)
    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return
    for stage in ("before", "after"):
        if stage in report:
            r = report[stage]
            typer.echo(
                f"{stage}: {r['flagged_frames']}/{r['frames']} flagged, "
                f"pan reversals {r['reversals']}, zoom reversals {r['zoom_reversals']}, "
                f"max pan accel {r['max_pan_accel_px']} px/frame^2"
            )


@geo_app.command("list-fonts")
def geo_list_fonts_cmd(
    category: Annotated[list[str] | None, typer.Option("--category")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """List installed open-license font families in assets/geo/fonts/."""
    del as_json
    root = find_repo_root()
    mod = load_fetch_fonts_module(root)
    payload = mod.list_installed_fonts(
        fonts_dir=root / "assets" / "geo" / "fonts", categories=category
    )
    typer.echo(json.dumps(payload, indent=2))


@geo_app.command("fetch-fonts")
def geo_fetch_fonts_cmd(
    category: Annotated[list[str] | None, typer.Option("--category")] = None,
    no_static: Annotated[bool, typer.Option("--no-static")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = True,
) -> None:
    """Download curated open-license fonts into assets/geo/fonts/."""
    del as_json
    fetch_geo_fonts(category=category, no_static=no_static)


@geo_app.command("auto-audio")
def geo_auto_audio_cmd(
    scene_file: Annotated[Path, typer.Option("--scene-file")],
    out_dir: Annotated[Path, typer.Option("--out-dir", "-o")],
    transcript_file: Annotated[Path | None, typer.Option("--transcript")] = None,
    seed: Annotated[str | None, typer.Option("--seed")] = None,
    brand: Annotated[str | None, typer.Option("--brand")] = None,
    brand_dir: Annotated[Path | None, typer.Option("--brand-dir")] = None,
) -> None:
    """Select and cache theme-matched studio BGM (primary + pivot), ambience, and foley."""
    from vedit.geo_production import plan_and_fetch_thematic_audio

    root = find_repo_root()
    resolved_brand_dir: Path | None = None
    if brand_dir is not None:
        resolved_brand_dir = brand_dir.expanduser().resolve()
        if not resolved_brand_dir.is_dir():
            raise typer.BadParameter(f"Brand directory not found: {resolved_brand_dir}")
    elif brand:
        if "/" in brand or "\\" in brand or ".." in brand or not brand.strip():
            raise typer.BadParameter(f"Invalid brand identifier: {brand!r}")
        brands_root = (root / "profiles" / "brands").resolve()
        candidate = (brands_root / brand.strip()).resolve()
        if not candidate.is_relative_to(brands_root) or not candidate.is_dir():
            raise typer.BadParameter(f"Unknown brand: {brand!r}")
        resolved_brand_dir = candidate
    spec = json.loads(scene_file.expanduser().resolve().read_text(encoding="utf-8"))
    tr = (
        json.loads(transcript_file.expanduser().resolve().read_text(encoding="utf-8"))
        if transcript_file is not None
        else None
    )
    plan = plan_and_fetch_thematic_audio(
        spec,
        tr,
        out_dir,
        repo_root=root,
        seed_key=seed,
        brand_dir=resolved_brand_dir,
    )
    typer.echo(json.dumps(plan, indent=2))


@geo_app.command("master")
def geo_master_cmd(
    scene_file: Annotated[Path, typer.Option("--scene-file")],
    acts_dir: Annotated[Path, typer.Option("--acts-dir")],
    audio_file: Annotated[Path, typer.Option("--audio")],
    out_file: Annotated[Path, typer.Option("--out-file", "-o")],
    captions_file: Annotated[Path | None, typer.Option("--captions")] = None,
    caption_renderer: Annotated[str, typer.Option("--caption-renderer")] = "html",
    credit_ass_file: Annotated[Path | None, typer.Option("--credit-ass")] = None,
    contact_sheet: Annotated[Path | None, typer.Option("--contact-sheet")] = None,
    audit_out: Annotated[Path | None, typer.Option("--audit-out")] = None,
    platform: Annotated[str | None, typer.Option("--platform")] = None,
    brand: Annotated[str | None, typer.Option("--brand")] = None,
    crf: Annotated[int, typer.Option("--crf")] = 17,
) -> None:
    """Assemble baked map/cutaway acts with transitions, captions, audio, and BT.709."""
    from vedit.geo_production import master_geo_acts

    kwargs: dict[str, Any] = dict(
        captions_file=captions_file,
        caption_renderer=caption_renderer,
        credit_ass_file=credit_ass_file,
        contact_sheet=contact_sheet,
        audit_out=audit_out,
        platform_id=platform,
        crf=crf,
        repo_root=find_repo_root(),
    )
    if brand is not None:
        kwargs["brand_id"] = brand
    result = master_geo_acts(scene_file, acts_dir, audio_file, out_file, **kwargs)
    typer.echo(json.dumps(result, indent=2))
    if not result["ok"]:
        raise typer.Exit(code=1)


__all__ = [
    "_TILE_ABSENT_HTTP_CODES",
    "_approx_viewport_pct",
    "_as_finite_float",
    "_clip_ring_half_plane",
    "_deg2num",
    "_enum_bbox_tiles",
    "_escape_geo_ass_text",
    "_extract_tile_list",
    "_fetch_tile_set",
    "_fmt_ass_time",
    "_has_image_magic",
    "_haversine_m",
    "_load_scene_vectors",
    "_national_ortho_url",
    "_parse_tile_coord_row",
    "_resolve_geom_ref",
    "_resolve_studio_bgm",
    "_s2_cloudless_url",
    "_segments_from_words",
    "_separately_traced_parts",
    "_simplify_geom",
    "_simplify_ring",
    "build_brand_ass_captions",
    "build_geoverum_ass_captions",
    "derive_sfx_events_from_scene",
    "extract_project_vectors",
    "fill_coverage_gaps",
    "filter_polygons_by_bbox",
    "geo_app",
    "hq_tile_urls",
    "parse_tile_list",
    "split_coverage_gaps",
    "split_polygon_by_longitude",
    "synthesize_documentary_bgm",
    "validate_map_scene",
]
