"""Structural and backward-compatibility tests for modular `vedit.geo` domain package."""

from __future__ import annotations

from vedit.contracts import find_repo_root


def test_cli_geo_is_thin_typer_wrapper() -> None:
    cli_path = find_repo_root() / "packages" / "director-py" / "src" / "vedit" / "cli" / "geo.py"
    lines = cli_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 450, f"Expected cli/geo.py <= 450 lines, got {len(lines)}"


def test_vedit_geo_submodules_and_cli_reexports_match() -> None:
    from vedit.cli import geo as cli_geo
    from vedit.geo.audio_mix import (
        derive_sfx_events_from_scene,
        synthesize_documentary_bgm,
    )
    from vedit.geo.captions import build_brand_ass_captions, build_geoverum_ass_captions
    from vedit.geo.scene_validator import validate_map_scene
    from vedit.geo.tiles import (
        _deg2num,
        fill_coverage_gaps,
        hq_tile_urls,
        parse_tile_list,
        split_coverage_gaps,
    )
    from vedit.geo.vectors import (
        extract_project_vectors,
        filter_polygons_by_bbox,
        split_polygon_by_longitude,
    )

    assert cli_geo._deg2num is _deg2num
    assert cli_geo.hq_tile_urls is hq_tile_urls
    assert cli_geo.parse_tile_list is parse_tile_list
    assert cli_geo.split_coverage_gaps is split_coverage_gaps
    assert cli_geo.fill_coverage_gaps is fill_coverage_gaps
    assert cli_geo.extract_project_vectors is extract_project_vectors
    assert cli_geo.filter_polygons_by_bbox is filter_polygons_by_bbox
    assert cli_geo.split_polygon_by_longitude is split_polygon_by_longitude
    assert cli_geo.validate_map_scene is validate_map_scene
    assert cli_geo.build_geoverum_ass_captions is build_geoverum_ass_captions
    assert cli_geo.derive_sfx_events_from_scene is derive_sfx_events_from_scene
    assert cli_geo.synthesize_documentary_bgm is synthesize_documentary_bgm
    assert callable(build_brand_ass_captions)
