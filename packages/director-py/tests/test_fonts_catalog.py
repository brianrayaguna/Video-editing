"""Tests for curated font catalog, CLI discovery commands, and local binary integrity."""

from __future__ import annotations

import importlib.util
import json

from typer.testing import CliRunner

from vedit.cli import app
from vedit.contracts import find_repo_root


def _load_fetch_fonts():
    root = find_repo_root()
    script = root / "tools" / "geo-assets" / "fetch_fonts.py"
    spec = importlib.util.spec_from_file_location("test_fetch_fonts", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_font_catalog_structure_categories_and_licenses() -> None:
    mod = _load_fetch_fonts()
    catalog = mod.FONT_CATALOG
    assert len(catalog) >= 38
    families = [e["family"] for e in catalog]
    assert len(families) == len(set(families))
    categories = {e["category"] for e in catalog}
    assert categories == {"display", "sans", "serif", "mono", "handwriting"}
    for fam in (
        "Archivo Black",
        "Rubik",
        "Space Grotesk",
        "Inter",
        "Plus Jakarta Sans",
        "Bebas Neue",
        "Barlow Condensed",
        "Cinzel",
        "Lora",
        "Merriweather",
        "Libre Baskerville",
        "Courier Prime",
        "Caveat",
        "Permanent Marker",
    ):
        assert fam in families
    for entry in catalog:
        assert entry["license"] in {"SIL OFL 1.1", "Apache-2.0"}
        assert entry["files"]


def test_cli_geo_list_fonts_and_installed_font_binaries() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["geo", "list-fonts", "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["total_catalog_families"] >= 38

    root = find_repo_root()
    fonts_dir = root / "assets" / "geo" / "fonts"
    mod = _load_fetch_fonts()
    if fonts_dir.is_dir():
        font_files = [
            p for p in fonts_dir.iterdir() if p.is_file() and p.suffix.lower() in {".ttf", ".otf"}
        ]
        for fp in font_files:
            assert mod.is_valid_font_file(fp), f"Invalid font binary header: {fp.name}"

    cat_res = runner.invoke(app, ["geo", "list-fonts", "--category", "mono", "--json"])
    assert cat_res.exit_code == 0, cat_res.output
    cat_data = json.loads(cat_res.stdout)
    assert all(f["category"] == "mono" for f in cat_data["families"])
    assert len(cat_data["families"]) == 5
