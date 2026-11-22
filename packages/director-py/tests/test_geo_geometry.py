"""Unit tests for meridian polygon splitting, bbox filtering, and map scene primitives."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

from vedit.cli.geo import (
    build_geoverum_ass_captions,
    derive_sfx_events_from_scene,
    filter_polygons_by_bbox,
    split_polygon_by_longitude,
    synthesize_documentary_bgm,
    validate_map_scene,
)
from vedit.contracts import find_repo_root


def test_split_polygon_by_longitude_partitions_box_cleanly() -> None:
    square = {
        "type": "Polygon",
        "coordinates": [
            [
                [-120.0, 30.0],
                [-80.0, 30.0],
                [-80.0, 48.0],
                [-120.0, 48.0],
                [-120.0, 30.0],
            ]
        ],
    }
    halves = split_polygon_by_longitude(square, -100.0)
    west_ring = halves["west"]["coordinates"][0][0]
    east_ring = halves["east"]["coordinates"][0][0]

    assert west_ring[0] == west_ring[-1]
    assert east_ring[0] == east_ring[-1]
    assert all(pt[0] <= -100.0 for pt in west_ring)
    assert all(pt[0] >= -100.0 for pt in east_ring)
    assert any(pt[0] == -100.0 for pt in west_ring)
    assert any(pt[0] == -100.0 for pt in east_ring)


def test_filter_polygons_by_bbox_isolates_contiguous_mainland() -> None:
    multi = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-124.0, 32.0], [-70.0, 32.0], [-70.0, 48.0], [-124.0, 48.0], [-124.0, 32.0]]],
            [[[-160.0, 60.0], [-140.0, 60.0], [-140.0, 70.0], [-160.0, 70.0], [-160.0, 60.0]]],
            [[[-158.0, 19.0], [-155.0, 19.0], [-155.0, 22.0], [-158.0, 22.0], [-158.0, 19.0]]],
        ],
    }
    mainland = filter_polygons_by_bbox(
        multi, min_lon=-126.0, max_lon=-65.0, min_lat=24.0, max_lat=50.0
    )
    assert mainland["type"] == "MultiPolygon"
    assert len(mainland["coordinates"]) == 1


def test_render_map_scene_contains_atmospheric_and_demographic_primitives() -> None:
    repo = find_repo_root()
    src = Path(repo / "tools" / "geo-assets" / "render_map_scene.mjs").read_text(encoding="utf-8")
    for token in (
        'layer.type === "human_silhouette_row"',
        'layer.type === "landmark_silhouette"',
        'layer.type === "cloud_system"',
        'layer.type === "wind_streamlines"',
        'layer.type === "prohibition_pins"',
        "applyWorldDirectionalClip",
        "drawProgressiveGeomPerimeter",
    ):
        assert token in src

    node_bin = shutil.which("node")
    if node_bin:
        mjs_path = str(repo / "tools" / "geo-assets" / "render_map_scene.mjs")
        check_js = (
            'const fs = require("fs");'
            f'const src = fs.readFileSync({mjs_path!r}, "utf8");'
            r"const m = src.match(/function buildMapSceneHtml[\s\S]*?\n\}\n/);"
            'const fn = new Function(m[0] + "\\nreturn buildMapSceneHtml('
            '\\"http://x\\", 1080, 1920, \\"{}\\", {});");'
            r"const script = fn().match(/<script>([\s\S]*?)<\/script>/)[1];"
            "new Function(script);"
        )
        proc = subprocess.run(
            [node_bin, "-e", check_js], capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stderr


def test_validate_map_scene_rejects_slop_microtext_and_blurry_closeups(tmp_path: Path) -> None:
    bad_scene = {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "acts": [
            {
                "act_id": "bad_act",
                "type": "map",
                "duration_s": 20.0,
                "tile_source": "graded",
                "camera_keyframes": [
                    {"t": 0.0, "center": [109.322, 0.0], "zoom": 16.0, "pitch": 0.0},
                    {"t": 20.0, "center": [109.322, 0.0], "zoom": 16.0, "pitch": 0.0},
                ],
                "layers": [
                    {"type": "coord_plaque", "start_s": 0.0, "end_s": 5.0},
                    {"type": "scale_comparison", "start_s": 5.0, "end_s": 10.0},
                    {
                        "type": "glow_label",
                        "text": "Tiny",
                        "font_px": 22,
                        "start_s": 0.0,
                        "end_s": 5.0,
                    },
                ],
            }
        ],
    }
    report = validate_map_scene(bad_scene, repo_root=tmp_path)
    assert report["ok"] is False
    joined = "\n".join(report["errors"])
    assert "coord_plaque" in joined
    assert "scale_comparison" in joined
    assert "font_px=22" in joined
    assert "Sentinel-2 'graded'" in joined
    assert "camera_keyframes" in joined


def test_validate_map_scene_accepts_clean_3d_scene() -> None:
    good_scene = {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "acts": [
            {
                "act_id": "clean_act",
                "type": "map",
                "duration_s": 15.0,
                "tile_source": "hybrid",
                "camera_keyframes": [
                    {"t": 0.0, "center": [109.32, 0.0], "zoom": 5.0, "pitch": 12.0},
                    {"t": 7.5, "center": [109.32, 0.0], "zoom": 9.0, "pitch": 24.0},
                    {"t": 15.0, "center": [109.32, 0.0], "zoom": 7.0, "pitch": 16.0},
                ],
                "layers": [
                    {
                        "type": "glow_label",
                        "text": "Pontianak",
                        "font_px": 56,
                        "start_s": 1.0,
                        "end_s": 6.0,
                    }
                ],
            }
        ],
    }
    report = validate_map_scene(good_scene)
    assert report["ok"] is True
    assert report["errors"] == []


def test_build_geoverum_ass_captions_locks_bottom_band_and_speed() -> None:
    transcript = {
        "segments": [
            {
                "start": 0.0,
                "end": 2.6,
                "text": "Tahun 1928 para pengukur menandai garis khatulistiwa.",
            },
            {"start": 2.6, "end": 5.2, "text": "Hasilnya selisih 117 meter?"},
        ]
    }
    ass = build_geoverum_ass_captions(transcript, speed=1.3, max_words=4)
    assert "Style: Default,Rubik,56," in ass
    assert ",1,1.6,3.2,2,60,60,348,1" in ass
    # 2.6s / 1.3 == 2.00s, 5.2s / 1.3 == 4.00s
    assert "0:00:02.00,0:00:04.00" in ass
    assert "Hasilnya selisih 117 meter?" in ass

    # Centisecond rollover near 60s must format 0:01:00.00 (never 0:00:60.00) and escape ASS tags
    edge_ass = build_geoverum_ass_captions(
        {"segments": [{"start": 59.999, "end": 61.0, "text": r"Test {tag} \N word"}]}
    )
    assert "0:00:60.00" not in edge_ass
    assert "0:01:00.00,0:01:01.00" in edge_ass
    assert r"\{tag\}" in edge_ass
    assert r"\N" not in edge_ass.split("{\\fad(80,80)}", 1)[1]


def test_map_plane_jacobian_has_near_plane_determinant_guard() -> None:
    repo = find_repo_root()
    src = Path(repo / "tools" / "geo-assets" / "render_map_scene.mjs").read_text(encoding="utf-8")
    assert "const stepZoom = Math.max(refZoom, curZoom);" in src
    assert "const det = a * d - b * c;" in src


def test_derive_sfx_events_and_synthesize_bgm(tmp_path: Path) -> None:
    scene = {
        "acts": [
            {
                "act_id": "a1",
                "duration_s": 20.0,
                "camera_keyframes": [
                    {"t": 0.0, "center": [109.32, 0.0], "zoom": 5.0, "curve": "glide"},
                    {"t": 3.0, "center": [109.32, 0.0], "zoom": 15.0, "curve": "snap_dive"},
                ],
                "layers": [
                    {"type": "pin_label", "start_s": 4.0, "end_s": 8.0},
                    {"type": "crimson_x", "start_s": 9.0, "end_s": 11.0},
                    {"type": "void_wipe", "start_s": 12.0, "end_s": 16.0},
                    {"type": "glow_label", "count_to": 117, "start_s": 15.0, "end_s": 18.0},
                ],
            }
        ]
    }
    events = derive_sfx_events_from_scene(scene)
    sfx_names = [e["sfx"] for e in events]
    assert "swoosh_zoom.wav" in sfx_names
    assert "pin_drop.wav" in sfx_names
    assert "stamp_impact.wav" in sfx_names
    assert "flash_swish.wav" in sfx_names
    assert "ding_glass.wav" in sfx_names

    bgm_path = synthesize_documentary_bgm(1.0, tmp_path / "bgm.wav")
    assert bgm_path.is_file()
    with wave.open(str(bgm_path), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 48000
        assert wf.getnframes() == 48000
