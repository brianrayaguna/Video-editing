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
    hq_tile_urls,
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
        math_path = str(repo / "tools" / "geo-assets" / "map_draw_math.mjs")
        # The page builder reads two module-level constants: the inlined draw-math source
        # (export keywords stripped, as the module does) and the flag raster width.
        check_js = (
            'const fs = require("fs");'
            f'const src = fs.readFileSync({mjs_path!r}, "utf8");'
            f'const mathSrc = fs.readFileSync({math_path!r}, "utf8")'
            r'.replace(/^export\s+/gm, "");'
            r"const flagWidth = Number(src.match(/const FLAG_RASTER_WIDTH = (\d+)/)[1]);"
            r"const m = src.match(/function buildMapSceneHtml[\s\S]*?\n\}\n/);"
            'const fn = new Function("DRAW_MATH_SRC", "FLAG_RASTER_WIDTH", '
            'm[0] + "\\nreturn buildMapSceneHtml('
            '\\"http://x\\", 1080, 1920, \\"{}\\", {});");'
            r"const script = fn(mathSrc, flagWidth).match(/<script>([\s\S]*?)<\/script>/)[1];"
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


def test_hq_tile_urls_prefer_open_orthoimagery_then_sentinel2() -> None:
    mid = hq_tile_urls(14, 3090, 6428)
    assert len(mid) == 2
    assert "nationalmap.gov" in mid[0]
    assert "s2cloudless" in mid[1]
    assert mid[1].endswith("/14/6428/3090.jpg")
    deep = hq_tile_urls(16, 12360, 25712)
    assert len(deep) == 1 and "nationalmap.gov" in deep[0]
    assert hq_tile_urls(17, 24721, 51425) == []
    low = hq_tile_urls(8, 97, 43)
    assert len(low) == 1 and "s2cloudless" in low[0]


def _closeup_scene(zoom: float) -> dict:
    return {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "acts": [
            {
                "act_id": "closeup",
                "type": "map",
                "duration_s": 4.0,
                "tile_source": "hybrid",
                "camera_keyframes": [
                    {"t": 0.0, "center": [-5.35, 36.14], "zoom": zoom, "pitch": 20.0},
                    {"t": 4.0, "center": [-5.35, 36.14], "zoom": zoom, "pitch": 24.0},
                ],
                "layers": [],
            }
        ],
    }


def _touch_hq_tile(root: Path, lng: float, lat: float, z: int) -> None:
    from vedit.cli.geo import _deg2num

    x, y = _deg2num(lat, lng, z)
    tile = root / "assets" / "geo" / "tiles_hq" / str(z) / str(x) / f"{y}.jpg"
    tile.parent.mkdir(parents=True, exist_ok=True)
    tile.write_bytes(b"\xff" * 128)


def test_validate_map_scene_warns_when_closeup_exceeds_sentinel2_native_zoom(
    tmp_path: Path,
) -> None:
    _touch_hq_tile(tmp_path, -5.35, 36.14, 14)
    report = validate_map_scene(_closeup_scene(16.0), repo_root=tmp_path)
    assert report["ok"] is True
    assert any("native zoom" in w for w in report["warnings"])

    _touch_hq_tile(tmp_path, -5.35, 36.14, 15)
    sharp = validate_map_scene(_closeup_scene(16.0), repo_root=tmp_path)
    assert not any("native zoom" in w for w in sharp["warnings"])


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
    assert r"\N" not in edge_ass.split("{\\fad(130,0)}", 1)[1]


def test_build_geoverum_ass_captions_fades_in_and_cuts_out() -> None:
    seg = {"segments": [{"start": 0.0, "end": 1.0, "text": "Garis batas"}]}
    assert "{\\fad(130,0)}Garis batas" in build_geoverum_ass_captions(seg)
    custom = build_geoverum_ass_captions(seg, fade_in_ms=100, fade_out_ms=60)
    assert "{\\fad(100,60)}Garis batas" in custom
    clamped = build_geoverum_ass_captions(seg, fade_in_ms=900, fade_out_ms=-5)
    assert "{\\fad(200,0)}Garis batas" in clamped
    plain = build_geoverum_ass_captions(seg, fade_in_ms=0, fade_out_ms=0)
    assert "\\fad" not in plain and ",,Garis batas" in plain


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


def test_tile_list_parsing(tmp_path: Path) -> None:
    import json

    import pytest

    from vedit.cli.geo import parse_tile_list

    good = tmp_path / "coverage.json"
    good.write_text(json.dumps({"tiles": [[13, 1, 2], [5, 3, 4], [13, 1, 2]]}), encoding="utf-8")
    assert parse_tile_list(good) == {(13, 1, 2), (5, 3, 4)}

    for bad_rows in ([[13, 1]], [["a", 1, 2]], [[3, 9, 0]], [[-1, 0, 0]], [[23, 0, 0]], "x"):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"tiles": bad_rows}), encoding="utf-8")
        with pytest.raises(ValueError):
            parse_tile_list(bad)
    missing_key = tmp_path / "nokey.json"
    missing_key.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_tile_list(missing_key)


def test_validate_scene_flag_fill_and_trace(tmp_path: Path) -> None:
    flags = tmp_path / "assets" / "geo" / "flags"
    flags.mkdir(parents=True)
    (flags / "se.svg").write_text("<svg/>", encoding="utf-8")

    def scene(*layers: dict) -> dict:
        return {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "acts": [
                {
                    "act_id": "trace_act",
                    "type": "map",
                    "duration_s": 4.0,
                    "tile_source": "hybrid",
                    "camera_keyframes": [
                        {"t": 0.0, "center": [18.0, 60.0], "zoom": 5.0},
                        {"t": 4.0, "center": [18.0, 60.0], "zoom": 5.4},
                    ],
                    "layers": list(layers),
                }
            ],
        }

    good = validate_map_scene(
        scene(
            {"type": "polygon", "geom_ref": "se", "flag_fill": "SE", "flag_reveal": "radial"},
            {
                "type": "polygon",
                "geom_ref": "fi",
                "border_trace_s": 1.5,
                "border_trace_delay_s": 1.0,
            },
        ),
        repo_root=tmp_path,
    )
    assert good["ok"] is True, good["errors"]
    assert not any("border_trace" in w for w in good["warnings"])

    missing = validate_map_scene(
        scene({"type": "polygon", "geom_ref": "x", "flag_fill": "qq"}), repo_root=tmp_path
    )
    assert missing["ok"] is False
    assert any("flag_fill 'qq'" in e for e in missing["errors"])

    traversal = validate_map_scene(
        scene({"type": "polygon", "geom_ref": "x", "flag_fill": "../se"}), repo_root=tmp_path
    )
    assert traversal["ok"] is False

    long_trace = validate_map_scene(
        scene(
            {
                "type": "polygon",
                "geom_ref": "x",
                "border_trace_s": 3.5,
                "border_trace_delay_s": 1.0,
            }
        ),
        repo_root=tmp_path,
    )
    assert long_trace["ok"] is True
    assert any("border_trace" in w and "4.50" in w for w in long_trace["warnings"])

    bad_enums = validate_map_scene(
        scene(
            {
                "type": "polygon",
                "geom_ref": "se",
                "flag_fill": "se",
                "flag_reveal": "spiral",
                "flag_blend": "darken",
                "flag_fit": "contain",
                "border_trace_s": 1.0,
                "border_trace_ease": "bounce",
                "border_trace_dir": "left",
                "border_trace_heads": 3,
            }
        ),
        repo_root=tmp_path,
    )
    joined = "\n".join(bad_enums["errors"])
    for key in (
        "flag_reveal",
        "flag_blend",
        "flag_fit",
        "border_trace_ease",
        "border_trace_dir",
        "border_trace_heads",
    ):
        assert key in joined, key


def test_validate_scene_cut_blur_keys() -> None:
    def scene(**act_keys: object) -> dict:
        act = {
            "act_id": "cut_act",
            "type": "map",
            "duration_s": 4.0,
            "tile_source": "hybrid",
            "camera_keyframes": [
                {"t": 0.0, "center": [18.0, 60.0], "zoom": 5.0},
                {"t": 4.0, "center": [18.0, 60.0], "zoom": 5.4},
            ],
            "layers": [],
        }
        act.update(act_keys)
        return {"width": 1080, "height": 1920, "fps": 30, "acts": [act]}

    good = validate_map_scene(
        scene(cut_blur_in_s=0.4, cut_blur_out_s=0.3, cut_blur_strength=0.15)
    )
    assert good["ok"], good["errors"]
    assert not [w for w in good["warnings"] if "cut_blur" in w]

    strong = validate_map_scene(scene(cut_blur_in_s=0.4, cut_blur_strength=0.6))
    assert not strong["ok"]
    assert any("cut_blur_strength" in e for e in strong["errors"])

    negative = validate_map_scene(scene(cut_blur_in_s=-0.1))
    assert any("cut_blur_in_s" in e for e in negative["errors"])

    text = validate_map_scene(scene(cut_blur_out_s="abc"))
    assert any("cut_blur_out_s" in e for e in text["errors"])

    overlap = validate_map_scene(scene(cut_blur_in_s=3.0, cut_blur_out_s=2.0))
    assert overlap["ok"], overlap["errors"]
    assert any("cut_blur" in w and "4.00" in w for w in overlap["warnings"])


def test_validate_scene_flag_wave_and_organic_reveal(tmp_path: Path) -> None:
    flags = tmp_path / "assets" / "geo" / "flags"
    flags.mkdir(parents=True)
    (flags / "se.svg").write_text("<svg/>", encoding="utf-8")

    def scene(**layer_keys: object) -> dict:
        layer = {"type": "polygon", "geom_ref": "se", "flag_fill": "se"}
        layer.update(layer_keys)
        return {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "acts": [
                {
                    "act_id": "wave_act",
                    "type": "map",
                    "duration_s": 3.0,
                    "tile_source": "hybrid",
                    "camera_keyframes": [
                        {"t": 0.0, "center": [18.0, 60.0], "zoom": 5.0},
                        {"t": 3.0, "center": [18.0, 60.0], "zoom": 5.2},
                    ],
                    "layers": [layer],
                }
            ],
        }

    good = validate_map_scene(
        scene(
            flag_reveal="organic",
            flag_wave=0.2,
            flag_wave_speed=0.6,
            flag_wave_cycles=3,
            flag_wave_angle_deg=15,
            fill_reveal_roughness=0.3,
            fill_reveal_seed=4,
        ),
        repo_root=tmp_path,
    )
    assert good["ok"], good["errors"]
    assert validate_map_scene(scene(flag_wave=True), repo_root=tmp_path)["ok"]
    assert validate_map_scene(scene(fill_reveal_mode="organic"), repo_root=tmp_path)["ok"]

    for key, value in (
        ("flag_wave", 0.9),
        ("flag_wave", "strong"),
        ("flag_wave_speed", "fast"),
        ("flag_wave_cycles", -1),
        ("fill_reveal_roughness", 0.8),
    ):
        bad = validate_map_scene(scene(**{key: value}), repo_root=tmp_path)
        assert not bad["ok"], (key, value)
        assert any(key in e for e in bad["errors"]), (key, bad["errors"])


def test_coverage_gaps_split_by_route(tmp_path: Path) -> None:
    import json

    from vedit.cli.geo import split_coverage_gaps

    routed = tmp_path / "routed.json"
    routed.write_text(
        json.dumps(
            {
                "tiles": [[13, 1, 2], [14, 5, 6], [9, 0, 0]],
                "by_route": {
                    "tiles": [[13, 1, 2]],
                    "tiles_hq": [[9, 0, 0]],
                    "tiles_hybrid": [[14, 5, 6], [13, 1, 2]],
                },
            }
        ),
        encoding="utf-8",
    )
    assert split_coverage_gaps(routed) == (
        {(13, 1, 2)},
        {(9, 0, 0), (14, 5, 6), (13, 1, 2)},
    )
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"tiles": [[13, 1, 2]]}), encoding="utf-8")
    assert split_coverage_gaps(legacy) == (set(), {(13, 1, 2)})


def test_fill_coverage_gaps_routes_fetches_and_counts_unfillable(tmp_path: Path) -> None:
    from vedit.cli.geo import fill_coverage_gaps

    calls: list[tuple[set, object]] = []
    absent = {(15, 7, 7), (14, 2, 2)}

    def fake_fetch(root, coords, *, hq_aerial, grade_tiles, missing):
        calls.append((set(coords), hq_aerial))
        missing.update(c for c in coords if c in absent)
        ok = [c for c in coords if c not in absent]
        if hq_aerial is False:
            return len(ok), 0
        return sum(1 for c in ok if c[0] <= 12), sum(1 for c in ok if c[0] >= 13)

    regular = {(13, 1, 1), (14, 2, 2), (16, 9, 9)}
    hq = {(15, 7, 7), (16, 8, 8), (12, 3, 3)}
    summary = fill_coverage_gaps(tmp_path, regular, hq, fetch=fake_fetch)
    assert calls == [({(13, 1, 1), (14, 2, 2)}, False), (hq, None)]
    assert summary == {
        "coverage_gaps": 6,
        "tiles_verified": 2,
        "hq_tiles_verified": 1,
        "coverage_unfillable": 3,
    }
    assert fill_coverage_gaps(tmp_path, set(), set(), fetch=fake_fetch)["coverage_gaps"] == 0


def test_validate_scene_warns_on_border_trace_over_multipart_geometry(tmp_path: Path) -> None:
    import json

    from vedit.cli.geo import validate_map_scene

    square = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
    neighbour = [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]
    vectors = {
        "countries": {"AA": {"type": "Polygon", "coordinates": square}},
        "provinces_by_country": {
            "AA": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": square}},
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": neighbour}},
            ]
        },
        "dissolved_region": {
            "type": "MultiPolygon",
            "coordinates": [square, neighbour],
            "dissolve_seams": True,
        },
    }
    (tmp_path / "vectors.json").write_text(json.dumps(vectors), encoding="utf-8")

    def scene(geom_ref: str, trace_s: float = 1.2) -> dict:
        return {
            "vectors_file": "vectors.json",
            "acts": [
                {
                    "act_id": "reveal",
                    "duration_s": 3.0,
                    "layers": [
                        {"type": "polygon", "geom_ref": geom_ref, "border_trace_s": trace_s}
                    ],
                }
            ],
        }

    def trace_warnings(spec: dict) -> list[str]:
        report = validate_map_scene(spec, base_dir=tmp_path)
        return [w for w in report["warnings"] if "border_trace_s" in w]

    assert trace_warnings(scene("countries.AA")) == []
    assert len(trace_warnings(scene("provinces_by_country.AA"))) == 1
    assert "2 separate parts" in trace_warnings(scene("provinces_by_country.AA"))[0]
    assert len(trace_warnings(scene("dissolved_region"))) == 1
    assert trace_warnings(scene("provinces_by_country.AA", trace_s=0)) == []
    assert trace_warnings(scene("missing.ref")) == []
    no_vectors = scene("provinces_by_country.AA")
    no_vectors.pop("vectors_file")
    assert trace_warnings(no_vectors) == []


def test_coverage_validation_fill_dedup_and_prepare_routing(tmp_path: Path, monkeypatch) -> None:
    import json
    import subprocess

    import pytest
    from typer.testing import CliRunner

    from vedit.cli import geo as geo_mod

    # 1. split_coverage_gaps rejects bools/floats and preserves unrouted tiles
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"tiles": [[1, 0, 1]], "by_route": {"tiles": [[True, False, True]]}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed tile row"):
        geo_mod.split_coverage_gaps(bad)

    unrouted = tmp_path / "unrouted.json"
    unrouted.write_text(json.dumps({"tiles": [[10, 1, 2]], "by_route": {}}), encoding="utf-8")
    assert geo_mod.split_coverage_gaps(unrouted) == (set(), {(10, 1, 2)})

    # 2. fill_coverage_gaps deduplicates overlapping z<=12 tiles across regular and HQ routes
    calls: list[tuple[set, object, bool]] = []

    def fake_fetch(root, coords, *, hq_aerial, grade_tiles, missing):
        calls.append((set(coords), hq_aerial, grade_tiles))
        return len(coords), 0

    summary = geo_mod.fill_coverage_gaps(tmp_path, {(10, 1, 2)}, {(10, 1, 2)}, fetch=fake_fetch)
    assert summary["coverage_gaps"] == 1
    assert summary["tiles_verified"] == 1
    assert calls == [({(10, 1, 2)}, False, True)]

    # 3. _fetch_tile_set with hq_aerial=True does not download z<=12 into Sentinel-2
    fake_root = tmp_path / "repo"
    (fake_root / "assets" / "geo" / "tiles_hq" / "10" / "1").mkdir(parents=True)
    (fake_root / "assets" / "geo" / "tiles_hq" / "10" / "1" / "2.jpg").write_bytes(b"x" * 128)
    s2_n, hq_n = geo_mod._fetch_tile_set(
        fake_root, {(10, 1, 2)}, hq_aerial=True, grade_tiles=False
    )
    assert (s2_n, hq_n) == (0, 1)
    assert not (fake_root / "assets" / "geo" / "raw" / "tiles_s2_2016" / "10").exists()

    # 4. validate_map_scene handles z=16-only HQ tiles cleanly and rejects bools/bad types
    z16_dir = fake_root / "assets" / "geo" / "tiles_hq" / "16" / "10485"
    z16_dir.mkdir(parents=True)
    tx, ty = geo_mod._deg2num(37.78, -122.4, 16)
    (fake_root / "assets" / "geo" / "tiles_hq" / "16" / str(tx)).mkdir(parents=True, exist_ok=True)
    (
        fake_root / "assets" / "geo" / "tiles_hq" / "16" / str(tx) / f"{ty}.jpg"
    ).write_bytes(b"x" * 128)
    ok_z16 = geo_mod.validate_map_scene(
        {
            "acts": [
                {
                    "act_id": "z16",
                    "duration_s": 3.0,
                    "camera_keyframes": [
                        {"t": 0.0, "center": [-122.4, 37.78], "zoom": 16.0},
                        {"t": 3.0, "center": [-122.4, 37.78], "zoom": 16.0},
                    ],
                }
            ]
        },
        repo_root=fake_root,
    )
    assert ok_z16["ok"] and ok_z16["warnings"] == []

    bad_types = geo_mod.validate_map_scene(
        {
            "acts": [
                {
                    "act_id": "bad",
                    "duration_s": 3.0,
                    "cut_blur_in_s": True,
                    "layers": [
                        {
                            "type": "polygon",
                            "geom_ref": "x",
                            "border_trace_heads": True,
                            "border_trace_s": "fast",
                            "end_s": None,
                        }
                    ],
                }
            ]
        }
    )
    assert not bad_types["ok"]
    assert any("cut_blur_in_s" in e for e in bad_types["errors"])
    assert any("border_trace_heads" in e for e in bad_types["errors"])
    assert any("border_trace_s" in e for e in bad_types["errors"])

    # 5. geo prepare --tile-list respects by_route for regular z13-14 gaps
    cov_json = tmp_path / "cov.json"
    cov_json.write_text(
        json.dumps(
            {
                "tiles": [[13, 1, 2]],
                "by_route": {"tiles": [[13, 1, 2]], "tiles_hq": [], "tiles_hybrid": []},
            }
        ),
        encoding="utf-8",
    )
    fetch_calls: list[tuple[set, object]] = []
    monkeypatch.setattr(geo_mod, "find_repo_root", lambda: fake_root)
    monkeypatch.setattr(
        geo_mod,
        "_fetch_tile_set",
        lambda root, coords, *, hq_aerial, grade_tiles, missing=None: (
            fetch_calls.append((set(coords), hq_aerial)) or (len(coords), 0)
        ),
    )
    monkeypatch.setattr(
        geo_mod,
        "extract_project_vectors",
        lambda **kw: {"countries": {}, "continents": {}, "provinces": []},
    )
    runner = CliRunner()
    res = runner.invoke(
        geo_mod.geo_app,
        ["prepare", "--tile-list", str(cov_json), "-o", str(tmp_path / "vec.json")],
    )
    assert res.exit_code == 0, res.output
    assert fetch_calls == [({(13, 1, 2)}, False)]

    # 6. geo bake-scene --fill-tiles defers HQ tile presence check until after filling
    scene_file = tmp_path / "scene.json"
    scene_file.write_text(
        json.dumps(
            {
                "acts": [
                    {
                        "act_id": "closeup",
                        "duration_s": 2.0,
                        "camera_keyframes": [
                            {"t": 0.0, "center": [10.0, 10.0], "zoom": 14.0},
                            {"t": 2.0, "center": [10.0, 10.0], "zoom": 14.0},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(geo_mod.shutil, "which", lambda name: "/usr/bin/node")

    def fake_run(cmd, check=False, **kw):
        if "--coverage-out" in cmd:
            cov_out = Path(cmd[cmd.index("--coverage-out") + 1])
            tx14, ty14 = geo_mod._deg2num(10.0, 10.0, 14)
            cov_out.write_text(
                json.dumps(
                    {
                        "tiles": [[14, tx14, ty14]],
                        "by_route": {
                            "tiles": [],
                            "tiles_hq": [],
                            "tiles_hybrid": [[14, tx14, ty14]],
                        },
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(geo_mod.subprocess, "run", fake_run)

    def fake_fill(root, reg, hq):
        for z, tx, ty in hq:
            p = root / "assets" / "geo" / "tiles_hq" / str(z) / str(tx) / f"{ty}.jpg"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x" * 128)
        return {
            "coverage_gaps": len(reg | hq),
            "tiles_verified": 0,
            "hq_tiles_verified": len(hq),
            "coverage_unfillable": 0,
        }

    monkeypatch.setattr(geo_mod, "fill_coverage_gaps", fake_fill)
    bake_res = runner.invoke(
        geo_mod.geo_app,
        [
            "bake-scene",
            "--scene-file",
            str(scene_file),
            "-o",
            str(tmp_path / "out"),
            "--fill-tiles",
        ],
    )
    assert bake_res.exit_code == 0, bake_res.output


def test_validate_scene_supports_3d_layers_and_gloss_warp_flags(tmp_path: Path) -> None:
    flags = tmp_path / "assets" / "geo" / "flags"
    flags.mkdir(parents=True)
    (flags / "id.svg").write_text("<svg/>", encoding="utf-8")

    good = validate_map_scene(
        {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "acts": [
                {
                    "act_id": "three_d",
                    "type": "map",
                    "duration_s": 5.0,
                    "camera_keyframes": [
                        {"t": 0.0, "center": [106.8, -6.2], "zoom": 6.0, "pitch": 45.0},
                        {"t": 5.0, "center": [103.8, 1.3], "zoom": 9.0, "pitch": 55.0},
                    ],
                    "layers": [
                        {
                            "type": "polygon",
                            "geom_ref": "countries.Indonesia",
                            "flag_fill": "id",
                            "flag_wave": 0.3,
                            "flag_wave_warp": 0.04,
                            "flag_gloss": True,
                        },
                        {
                            "type": "cable_3d",
                            "coords": [[106.8, -6.2], [103.8, 1.3]],
                            "radius_px": 6.0,
                        },
                        {
                            "type": "model_3d",
                            "model": "transmission_tower",
                            "coord": [106.8, -6.2],
                        },
                        {
                            "type": "volume_3d",
                            "coord": [103.8, 1.3],
                            "width_m": 10954,
                            "length_m": 10954,
                            "height_m": 1400,
                        },
                    ],
                }
            ],
        },
        repo_root=tmp_path,
    )
    assert good["ok"], good["errors"]

    bad = validate_map_scene(
        {
            "acts": [
                {
                    "act_id": "bad_3d",
                    "duration_s": 3.0,
                    "layers": [
                        {"type": "polygon", "geom_ref": "x", "flag_gloss": 1.8},
                        {"type": "cable_3d", "coords": [[0, 0]]},
                        {"type": "model_3d", "model": "unknown_mesh", "coord": [0, 0]},
                        {"type": "volume_3d", "coord": [0, 0], "width_m": -10, "length_m": 5},
                    ],
                }
            ]
        },
        repo_root=tmp_path,
    )
    assert not bad["ok"]
    joined = "\n".join(bad["errors"])
    assert "flag_gloss" in joined
    assert "cable_3d" in joined
    assert "model_3d" in joined
    assert "volume_3d" in joined

    # Verify buildMapSceneHtml produces valid JS even when has_3d=True
    repo = find_repo_root()
    node_bin = shutil.which("node")
    if node_bin:
        mjs_path = str(repo / "tools" / "geo-assets" / "render_map_scene.mjs")
        math_path = str(repo / "tools" / "geo-assets" / "map_draw_math.mjs")
        check_js = (
            'const fs = require("fs");'
            f'const src = fs.readFileSync({mjs_path!r}, "utf8");'
            f'const mathSrc = fs.readFileSync({math_path!r}, "utf8")'
            r'.replace(/^export\s+/gm, "");'
            r"const flagWidth = Number(src.match(/const FLAG_RASTER_WIDTH = (\d+)/)[1]);"
            r"const m = src.match(/function buildMapSceneHtml[\s\S]*?\n\}\n/);"
            'const fn = new Function("DRAW_MATH_SRC", "FLAG_RASTER_WIDTH", '
            'm[0] + "\\nreturn buildMapSceneHtml('
            '\\"http://x\\", 1080, 1920, \\"{}\\", {has_3d: true, origin_coord: [106, -6]});");'
            r"const html = fn(mathSrc, flagWidth);"
            r"const scripts = [...html.matchAll(/<script(?:[^>]*)>([\s\S]*?)<\/script>/g)];"
            r"new Function(scripts[scripts.length - 1][1]);"
        )
        proc = subprocess.run(
            [node_bin, "-e", check_js], capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stderr


def test_build_geoverum_ass_captions_supports_word_only_transcript() -> None:
    word_only = {
        "source_hash": "a" * 64,
        "provider": "mock",
        "language": "id",
        "duration_s": 3.0,
        "text": "Kabel listrik melintas di dasar laut.",
        "words": [
            {"text": "Kabel", "start_s": 0.0, "end_s": 0.4},
            {"text": "listrik", "start_s": 0.42, "end_s": 0.8},
            {"text": "melintas.", "start_s": 0.82, "end_s": 1.3},
            {"text": "Di", "start_s": 1.8, "end_s": 2.0},
            {"text": "dasar", "start_s": 2.05, "end_s": 2.4},
            {"text": "laut.", "start_s": 2.42, "end_s": 2.9},
        ],
    }
    ass = build_geoverum_ass_captions(word_only, speed=1.0, max_words=4)
    assert "Dialogue: 0," in ass
    assert "Kabel listrik melintas" in ass
    assert "Di dasar laut" in ass


def test_validate_map_scene_gltf_taper_viewport_edge_and_substation_clearance(
    tmp_path: Path,
) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "tower.glb").write_bytes(b"glTF")

    report = validate_map_scene(
        {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "acts": [
                {
                    "act_id": "preflight_checks",
                    "type": "map",
                    "duration_s": 10.0,
                    "tile_source": "hybrid",
                    "camera_keyframes": [
                        {"t": 0.0, "center": [106.8, -6.2], "zoom": 8.0, "pitch": 30.0},
                        {"t": 5.0, "center": [106.8, -6.2], "zoom": 8.0, "pitch": 30.0},
                        {"t": 10.0, "center": [106.8, -6.2], "zoom": 8.0, "pitch": 30.0},
                    ],
                    "layers": [
                        {
                            "type": "model_3d",
                            "gltf_url": "project_models/tower.glb",
                            "coord": [106.8, -6.2],
                            "start_s": 0.0,
                            "end_s": 8.0,
                        },
                        {
                            "type": "model_3d",
                            "model": "substation",
                            "coord": [106.8, -6.2],
                            "start_s": 0.0,
                            "end_s": 8.0,
                        },
                        {
                            "type": "cable_3d",
                            "coords": [[106.5, -6.2], [106.8005, -6.2], [107.1, -6.2]],
                            "end_taper_m": 250,
                            "min_screen_radius_px": 2.0,
                            "start_s": 0.0,
                            "end_s": 8.0,
                        },
                        {
                            "type": "pin_label",
                            "text": "Edge Pin",
                            "coord": [105.0, -6.2],
                            "font_px": 42,
                            "start_s": 0.0,
                            "end_s": 6.0,
                        },
                    ],
                }
            ],
        },
        repo_root=tmp_path,
        base_dir=tmp_path,
    )
    assert report["ok"] is True, report["errors"]
    warn_text = "\n".join(report["warnings"])
    assert "viewport side margin" in warn_text
    assert "substation center" in warn_text

    missing_glb = validate_map_scene(
        {
            "acts": [
                {
                    "act_id": "bad_glb",
                    "duration_s": 4.0,
                    "layers": [
                        {
                            "type": "model_3d",
                            "gltf_url": "project_models/missing.glb",
                            "coord": [0, 0],
                        },
                        {"type": "cable_3d", "coords": [[0, 0], [1, 1]], "end_taper_m": -5},
                    ],
                }
            ]
        },
        repo_root=tmp_path,
        base_dir=tmp_path,
    )
    assert missing_glb["ok"] is False
    err_text = "\n".join(missing_glb["errors"])
    assert "missing.glb" in err_text
    assert "end_taper_m" in err_text


def test_validate_scene_smooth_hatch_lighting_country_block_3d_and_sfx(tmp_path: Path) -> None:
    good = validate_map_scene(
        {
            "width": 1080,
            "height": 1920,
            "fps": 60,
            "ov_scale": 1.5,
            "capture_format": "png",
            "acts": [
                {
                    "act_id": "smooth_2d_and_3d",
                    "type": "map",
                    "duration_s": 6.0,
                    "ov_scale": 2.0,
                    "capture_format": "jpeg",
                    "camera_keyframes": [
                        {"t": 0.0, "center": [106.8, -6.2], "zoom": 5.0, "pitch": 30.0},
                        {"t": 6.0, "center": [110.0, -7.0], "zoom": 6.0, "pitch": 45.0},
                    ],
                    "layers": [
                        {
                            "type": "polygon",
                            "geom_ref": "countries.Indonesia",
                            "border_trace_s": 0.9,
                            "border_trace_ease": "editorial_out",
                            "fill_bloom_overshoot": 1.18,
                            "hatch": True,
                            "hatch_space": "world",
                            "hatch_reveal_mode": "staggered_draw",
                            "hatch_direction": "center_out",
                            "hatch_ease": "spring_crisp",
                            "hatch_draw_s": 0.75,
                            "hatch_delay_s": 0.08,
                            "hatch_stagger": 0.62,
                            "hatch_angle_deg": 45,
                            "hatch_spacing": 16,
                            "hatch_width": 3.0,
                            "lift_px": 14,
                            "bevel_light": True,
                            "cast_shadow": True,
                            "light_sweep": {"duration_s": 0.65, "intensity": 0.55},
                            "rim_glint": True,
                            "start_s": 0.0,
                            "end_s": 3.0,
                        },
                        {
                            "type": "focus_spotlight",
                            "geom_refs": ["countries.Indonesia"],
                            "dim_alpha": 0.55,
                            "feather_px": 36,
                            "start_s": 0.2,
                            "end_s": 3.0,
                        },
                        {
                            "type": "country_block_3d",
                            "geom_ref": "countries.Indonesia",
                            "extrude_height_m": 65000,
                            "bevel_px": 12,
                            "rise_ease": "spring_tactile",
                            "hatch": True,
                            "light_sweep": True,
                            "start_s": 3.0,
                            "end_s": 6.0,
                        },
                    ],
                }
            ],
        },
        repo_root=tmp_path,
    )
    assert good["ok"], good["errors"]

    sfx = derive_sfx_events_from_scene(
        {
            "acts": [
                {
                    "act_id": "three_d_block",
                    "duration_s": 4.0,
                    "layers": [
                        {
                            "type": "country_block_3d",
                            "geom_ref": "countries.Indonesia",
                            "start_s": 1.0,
                            "end_s": 4.0,
                        }
                    ],
                }
            ]
        }
    )
    assert any(ev["sfx"] == "sub_thud.wav" and ev["gain_db"] == -10.5 for ev in sfx), sfx

    bad = validate_map_scene(
        {
            "ov_scale": 99,
            "capture_format": "gif",
            "acts": [
                {
                    "act_id": "hostile_smooth",
                    "duration_s": 4.0,
                    "layers": [
                        {
                            "type": "polygon",
                            "geom_ref": "x",
                            "hatch_space": "invalid_space",
                            "hatch_reveal_mode": "bogus_mode",
                            "hatch_direction": "sideways",
                            "hatch_draw_s": -1,
                            "hatch_spacing": 0,
                            "hatch_stagger": 1.5,
                            "lift_px": 500,
                            "bevel_light": 2.5,
                            "fill_bloom_overshoot": 0.5,
                            "light_sweep": 123,
                            "rim_glint": "nope",
                        },
                        {
                            "type": "country_block_3d",
                            "extrude_height_m": float("nan"),
                            "bevel_px": -4,
                        },
                        {
                            "type": "focus_spotlight",
                            "dim_alpha": 1.8,
                        },
                    ],
                }
            ],
        },
        repo_root=tmp_path,
    )
    assert not bad["ok"]
    joined = "\n".join(bad["errors"])
    for token in (
        "ov_scale",
        "capture_format",
        "hatch_space",
        "hatch_reveal_mode",
        "hatch_direction",
        "hatch_draw_s",
        "hatch_spacing",
        "hatch_stagger",
        "lift_px",
        "bevel_light",
        "fill_bloom_overshoot",
        "light_sweep",
        "rim_glint",
        "country_block_3d",
        "focus_spotlight",
    ):
        assert token in joined, f"Expected error mentioning {token!r}, got:\n{joined}"
