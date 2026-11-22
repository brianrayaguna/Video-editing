"""Unit tests for meridian polygon splitting, bbox filtering, and map scene primitives."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from vedit.cli.geo import filter_polygons_by_bbox, split_polygon_by_longitude
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
