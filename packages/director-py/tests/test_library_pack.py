"""Unit tests for tools/geo-assets/fetch_library_pack.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[3] / "tools" / "geo-assets" / "fetch_library_pack.py"
    spec = importlib.util.spec_from_file_location("fetch_library_pack", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fetch_library_pack"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_build_country_svgs_keeps_sovereign_over_dependency(tmp_path: Path, monkeypatch) -> None:
    mod = _load_module()
    raw_vec = tmp_path / "raw" / "vector"
    raw_vec.mkdir(parents=True)
    svg_dir = tmp_path / "svg"
    monkeypatch.setattr(mod, "GEO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "RAW_VECTOR_DIR", raw_vec)
    monkeypatch.setattr(mod, "SVG_DIR", svg_dir)

    france = {
        "type": "Feature",
        "properties": {
            "ISO_A2_EH": "FR",
            "NAME_EN": "France",
            "TYPE": "Sovereign country",
            "POP_EST": 67000000,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-4.0, 42.0], [8.0, 42.0], [8.0, 51.0], [-4.0, 51.0], [-4.0, 42.0]]],
        },
    }
    clipperton = {
        "type": "Feature",
        "properties": {
            "ISO_A2_EH": "FR",
            "NAME_EN": "Clipperton Island",
            "TYPE": "Dependency",
            "POP_EST": 0,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-109.2, 10.2], [-109.1, 10.2], [-109.1, 10.3], [-109.2, 10.3], [-109.2, 10.2]]
            ],
        },
    }
    (raw_vec / "ne_10m_admin_0_countries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [france, clipperton]}),
        encoding="utf-8",
    )

    assert mod.build_country_svgs() == 1
    fr_svg = (svg_dir / "countries" / "fr.svg").read_text(encoding="utf-8")
    assert 'data-name="france"' in fr_svg
    assert "<title>France</title>" in fr_svg


def test_build_subdivision_svgs_disambiguates_collisions_and_rejects_invalid_iso2(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _load_module()
    raw_vec = tmp_path / "raw" / "vector"
    raw_vec.mkdir(parents=True)
    svg_dir = tmp_path / "svg"
    monkeypatch.setattr(mod, "GEO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "RAW_VECTOR_DIR", raw_vec)
    monkeypatch.setattr(mod, "SVG_DIR", svg_dir)

    sq1 = [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]
    sq2 = [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]]
    features = [
        {
            "type": "Feature",
            "properties": {"iso_a2": "US", "name_en": "Washington", "name": "Washington"},
            "geometry": {"type": "Polygon", "coordinates": sq1},
        },
        {
            "type": "Feature",
            "properties": {
                "iso_a2": "US",
                "name_en": "Washington",
                "name": "District of Columbia",
            },
            "geometry": {"type": "Polygon", "coordinates": sq2},
        },
        {
            "type": "Feature",
            "properties": {"iso_a2": "-1", "name_en": "Invalid", "name": "Invalid"},
            "geometry": {"type": "Polygon", "coordinates": sq1},
        },
        {
            "type": "Feature",
            "properties": {"iso_a2": "../escape", "name_en": "Bad", "name": "Bad"},
            "geometry": {"type": "Polygon", "coordinates": sq1},
        },
    ]
    (raw_vec / "ne_10m_admin_1_states_provinces.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )

    counts = mod.build_subdivision_svgs(["us", "-1", "../escape"])
    assert counts == {"us": 2}
    assert (svg_dir / "subdivisions" / "us" / "washington.svg").is_file()
    assert (svg_dir / "subdivisions" / "us" / "district_of_columbia.svg").is_file()
    assert not (svg_dir / "subdivisions" / "-1").exists()


def test_unwrap_antimeridian_preserves_prime_meridian_and_unwraps_dateline() -> None:
    mod = _load_module()
    antarctica = [[[[ -1.0, -70.0], [1.0, -70.0], [179.0, -75.0], [-179.0, -75.0], [-1.0, -70.0]]]]
    # Crosses 0 deg prime meridian: must NOT shift negative longitudes by +360
    assert mod._unwrap_antimeridian(antarctica) == antarctica

    fiji = [[[[177.0, -18.0], [180.0, -18.0], [-179.0, -17.0], [-178.0, -18.0], [177.0, -18.0]]]]
    unwrapped = mod._unwrap_antimeridian(fiji)
    lons = [pt[0] for pt in unwrapped[0][0]]
    assert min(lons) >= 177.0 and max(lons) <= 182.0


def test_polygons_to_svg_keeps_microstates_escapes_xml_and_handles_3d_coords() -> None:
    import xml.etree.ElementTree as ET

    mod = _load_module()
    tiny_archipelago = [
        [[[-176.0, 0.2, 5.0], [-175.99, 0.2, 5.0], [-175.99, 0.21, 5.0], [-176.0, 0.2, 5.0]]],
        [[[-160.0, 5.8, 2.0], [-159.99, 5.8, 2.0], [-159.99, 5.81, 2.0], [-160.0, 5.8, 2.0]]],
    ]
    svg = mod.polygons_to_svg(
        tiny_archipelago,
        title='Islands <"A&B">',
        meta={"iso2": "um", "name": 'a"b'},
    )
    assert svg is not None
    root = ET.fromstring(svg)
    assert root.attrib["data-iso2"] == "um"
    assert root.attrib["data-name"] == 'a"b'
    title_el = root.find("{http://www.w3.org/2000/svg}title")
    assert title_el is not None and title_el.text == 'Islands <"A&B">'


def test_build_world_svg_deduplicates_ids_and_handles_empty_rings(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _load_module()
    raw_vec = tmp_path / "raw" / "vector"
    raw_vec.mkdir(parents=True)
    svg_dir = tmp_path / "svg"
    monkeypatch.setattr(mod, "GEO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "RAW_VECTOR_DIR", raw_vec)
    monkeypatch.setattr(mod, "SVG_DIR", svg_dir)

    features = [
        {
            "type": "Feature",
            "properties": {"ISO_A2_EH": "AU", "NAME_EN": "Australia"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [113.0, -35.0, 0.0],
                        [153.0, -35.0, 0.0],
                        [153.0, -11.0, 0.0],
                        [113.0, -35.0, 0.0],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {"ISO_A2_EH": "AU", "NAME_EN": "Ashmore"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [],
                    [[123.0, -12.0], [123.5, -12.0], [123.5, -12.5], [123.0, -12.0]],
                ],
            },
        },
    ]
    (raw_vec / "ne_10m_admin_0_countries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )

    assert mod.build_world_svg() is True
    world_svg = (svg_dir / "world.svg").read_text(encoding="utf-8")
    assert world_svg.count('id="au"') == 1


def test_write_catalog_preserves_disk_subdivisions_and_multi_source_licenses(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _load_module()
    raw_vec = tmp_path / "raw" / "vector"
    raw_vec.mkdir(parents=True)
    svg_dir = tmp_path / "svg"
    (svg_dir / "subdivisions" / "id").mkdir(parents=True)
    (svg_dir / "subdivisions" / "id" / "aceh.svg").write_text("<svg/>", encoding="utf-8")
    (svg_dir / "subdivisions" / "us").mkdir(parents=True)
    (svg_dir / "subdivisions" / "us" / "texas.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "vector").mkdir(parents=True)
    (tmp_path / "vector" / ".DS_Store").write_text("junk", encoding="utf-8")
    (tmp_path / "flags").mkdir(parents=True)
    (tmp_path / "icons").mkdir(parents=True)
    monkeypatch.setattr(mod, "GEO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "RAW_VECTOR_DIR", raw_vec)
    monkeypatch.setattr(mod, "SVG_DIR", svg_dir)
    monkeypatch.setattr(mod, "FLAGS_DIR", tmp_path / "flags")
    monkeypatch.setattr(mod, "ICONS_DIR", tmp_path / "icons")
    monkeypatch.setattr(mod, "CATALOG_PATH", tmp_path / "LIBRARY.json")

    mod.write_catalog({}, {"id": 1})
    cat = json.loads((tmp_path / "LIBRARY.json").read_text(encoding="utf-8"))
    assert cat["sections"]["svg"]["subdivisions"]["per_country"] == {"id": 1, "us": 1}
    assert cat["sections"]["svg"]["world"] is None
    assert cat["sections"]["vector"]["curated"] == []
    assert "gem_active_faults_*" in cat["sections"]["vector"]["licenses"]
    assert "material_symbols" in cat["sections"]["icons"]["licenses"]
