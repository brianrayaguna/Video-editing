#!/usr/bin/env python3
"""Idempotent builder for the reusable cartographic asset library under `assets/geo/`.

Installs open-licensed map layers and SVG artwork that any episode can reuse, then writes a
machine-readable catalog at `assets/geo/LIBRARY.json`:

- Natural Earth 1:10m cultural and physical layers (rivers, lakes, coastline, land, ocean,
  populated places, urban areas, boundaries, disputed areas, time zones, transport, reefs,
  glaciers, bathymetry depth bands) into `raw/vector/` (Public Domain).
- Lucide icon set (ISC License) into `icons/` (flat `<name>.svg`).
- Country flags completed at `flags/<iso2>.svg` from the 4:3 flag set (MIT License).
- Country silhouettes `svg/countries/<iso2>.svg`, first-level subdivision silhouettes
  `svg/subdivisions/<iso2>/<slug>.svg`, and an equirectangular `svg/world.svg`, all generated
  from Natural Earth geometry with `fill="currentColor"` so templates can recolor them.

Usage:
    python tools/geo-assets/fetch_library_pack.py [--subdivisions id,my,ph] [--skip-icons]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tarfile
import tempfile
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
GEO_ROOT = REPO_ROOT / "assets" / "geo"
RAW_VECTOR_DIR = GEO_ROOT / "raw" / "vector"
ICONS_DIR = GEO_ROOT / "icons"
FLAGS_DIR = GEO_ROOT / "flags"
SVG_DIR = GEO_ROOT / "svg"
CATALOG_PATH = GEO_ROOT / "LIBRARY.json"

USER_AGENT = "vedit-library-pack/1.0"
NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
LUCIDE_VERSION = "1.77.0"
LUCIDE_TARBALL = f"https://registry.npmjs.org/lucide-static/-/lucide-static-{LUCIDE_VERSION}.tgz"

NE_LAYERS: dict[str, list[str]] = {
    "hydrography": [
        "ne_10m_rivers_lake_centerlines",
        "ne_10m_lakes",
        "ne_10m_coastline",
        "ne_10m_reefs",
    ],
    "land_and_ocean": [
        "ne_10m_land",
        "ne_10m_ocean",
        "ne_10m_glaciated_areas",
        "ne_10m_playas",
        "ne_10m_geography_regions_points",
        "ne_10m_geography_regions_elevation_points",
        "ne_10m_geographic_lines",
    ],
    "bathymetry": [
        f"ne_10m_bathymetry_{band}"
        for band in (
            "L_0",
            "K_200",
            "J_1000",
            "I_2000",
            "H_3000",
            "G_4000",
            "F_5000",
            "E_6000",
            "D_7000",
            "C_8000",
            "B_9000",
            "A_10000",
        )
    ],
    "boundaries": [
        "ne_10m_admin_0_boundary_lines_land",
        "ne_10m_admin_0_boundary_lines_maritime_indicator",
        "ne_10m_admin_0_disputed_areas",
        "ne_10m_admin_0_map_subunits",
        "ne_10m_time_zones",
    ],
    "settlements": [
        "ne_10m_populated_places_simple",
        "ne_10m_urban_areas",
    ],
    "transport": [
        "ne_10m_roads",
        "ne_10m_railroads",
        "ne_10m_ports",
        "ne_10m_airports",
    ],
}

LICENSES = {
    "natural_earth": "Public Domain (Natural Earth). Attribution: Made with Natural Earth.",
    "lucide": "ISC License (Lucide Contributors).",
    "flags": "MIT License (flag-icons contributors).",
}


def _download(url: str, dest: Path, min_bytes: int = 64) -> str:
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    if tmp.stat().st_size < min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download too small: {url}")
    tmp.replace(dest)
    return "downloaded"


def fetch_natural_earth_layers() -> dict[str, list[str]]:
    jobs = [(group, name) for group, names in NE_LAYERS.items() for name in names]

    def _one(job: tuple[str, str]) -> tuple[str, str, str]:
        group, name = job
        dest = RAW_VECTOR_DIR / f"{name}.geojson"
        try:
            return group, name, _download(f"{NE_BASE}/{name}.geojson", dest, min_bytes=512)
        except Exception as exc:  # noqa: BLE001
            return group, name, f"failed: {exc}"

    installed: dict[str, list[str]] = {group: [] for group in NE_LAYERS}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for group, name, status in pool.map(_one, jobs):
            print(f"  [vector] {name}: {status}")
            if not status.startswith("failed"):
                installed[group].append(f"raw/vector/{name}.geojson")
    return installed


def fetch_lucide_icons() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tgz = Path(tmp_dir) / "lucide.tgz"
        _download(LUCIDE_TARBALL, tgz, min_bytes=10_000)
        count = 0
        with tarfile.open(tgz, "r:gz") as tar:
            for member in tar.getmembers():
                name = member.name
                if not (member.isfile() and re.fullmatch(r"package/icons/[a-z0-9-]+\.svg", name)):
                    continue
                dest = ICONS_DIR / Path(name).name
                if dest.is_file():
                    count += 1
                    continue
                src = tar.extractfile(member)
                if src is None:
                    continue
                data = src.read()
                if b"<svg" not in data[:512]:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                count += 1
    return count


def complete_flags() -> int:
    src_dir = FLAGS_DIR / "4x3"
    if not src_dir.is_dir():
        return len(list(FLAGS_DIR.glob("*.svg")))
    for src in sorted(src_dir.glob("*.svg")):
        dest = FLAGS_DIR / src.name
        if not dest.is_file():
            shutil.copyfile(src, dest)
    return len(list(FLAGS_DIR.glob("*.svg")))


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_") or "unnamed"


def _polygons(geometry: dict[str, Any] | None) -> list[list[list[list[float]]]]:
    if not geometry:
        return []
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return list(geometry["coordinates"])
    return []


def _unwrap_antimeridian(polys: list[list[list[list[float]]]]) -> list[list[list[list[float]]]]:
    lons = [pt[0] for poly in polys for ring in poly for pt in ring]
    if not lons or max(lons) - min(lons) <= 180:
        return polys
    return [
        [[[lon + 360 if lon < 0 else lon, lat] for lon, lat in ring] for ring in poly]
        for poly in polys
    ]


def polygons_to_svg(
    polys: list[list[list[list[float]]]],
    *,
    size_px: int = 1024,
    pad_ratio: float = 0.04,
    title: str = "",
    meta: dict[str, str] | None = None,
) -> str | None:
    """Project lon/lat polygons (cos-latitude equirectangular) into a recolorable SVG."""
    polys = _unwrap_antimeridian(polys)
    pts = [pt for poly in polys for ring in poly for pt in ring]
    if not pts:
        return None
    lat0 = math.radians((max(p[1] for p in pts) + min(p[1] for p in pts)) / 2)
    kx = max(math.cos(lat0), 0.2)
    xs = [p[0] * kx for p in pts]
    ys = [-p[1] for p in pts]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1e-9)
    scale = size_px * (1 - 2 * pad_ratio) / span
    width = (max_x - min_x) * scale + 2 * size_px * pad_ratio
    height = (max_y - min_y) * scale + 2 * size_px * pad_ratio
    off_x = size_px * pad_ratio - min_x * scale
    off_y = size_px * pad_ratio - min_y * scale
    tolerance = 0.6

    parts: list[str] = []
    for poly in polys:
        for ring in poly:
            proj = [(lon * kx * scale + off_x, -lat * scale + off_y) for lon, lat in ring]
            if len(proj) < 4:
                continue
            rx = [p[0] for p in proj]
            ry = [p[1] for p in proj]
            if max(rx) - min(rx) < tolerance * 2 and max(ry) - min(ry) < tolerance * 2:
                continue
            kept = [proj[0]]
            for x, y in proj[1:-1]:
                lx, ly = kept[-1]
                if abs(x - lx) >= tolerance or abs(y - ly) >= tolerance:
                    kept.append((x, y))
            if len(kept) < 3:
                continue
            parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in kept) + "Z")
    if not parts:
        return None
    data_attrs = "".join(f' data-{k}="{v}"' for k, v in (meta or {}).items())
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}"'
        f' width="{width:.0f}" height="{height:.0f}"{data_attrs}>'
        f"<title>{safe_title}</title>"
        f'<path fill="currentColor" fill-rule="evenodd" d="{"".join(parts)}"/></svg>\n'
    )


def _iso2(props: dict[str, Any]) -> str | None:
    for key in ("ISO_A2_EH", "ISO_A2", "iso_a2"):
        value = str(props.get(key) or "")
        if re.fullmatch(r"[A-Z]{2}", value):
            return value.lower()
    return None


def build_country_svgs() -> int:
    src = RAW_VECTOR_DIR / "ne_10m_admin_0_countries.geojson"
    if not src.is_file():
        print("  [svg] missing ne_10m_admin_0_countries.geojson; run fetch_assets.py first")
        return 0
    out_dir = SVG_DIR / "countries"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for feature in json.loads(src.read_text(encoding="utf-8"))["features"]:
        props = feature.get("properties") or {}
        code = _iso2(props)
        if not code:
            continue
        name = str(props.get("NAME_EN") or props.get("NAME") or code)
        svg = polygons_to_svg(
            _polygons(feature.get("geometry")),
            title=name,
            meta={"iso2": code, "name": _slug(name)},
        )
        if svg:
            (out_dir / f"{code}.svg").write_text(svg, encoding="utf-8")
            count += 1
    return count


def build_subdivision_svgs(iso2_codes: list[str]) -> dict[str, int]:
    src = RAW_VECTOR_DIR / "ne_10m_admin_1_states_provinces.geojson"
    if not src.is_file() or not iso2_codes:
        return {}
    wanted = {c.lower() for c in iso2_codes}
    counts: dict[str, int] = {}
    for feature in json.loads(src.read_text(encoding="utf-8"))["features"]:
        props = feature.get("properties") or {}
        code = str(props.get("iso_a2") or "").lower()
        if code not in wanted:
            continue
        name = str(props.get("name_en") or props.get("name") or "unnamed")
        svg = polygons_to_svg(
            _polygons(feature.get("geometry")),
            title=name,
            meta={"iso2": code, "name": _slug(name)},
        )
        if svg:
            out = SVG_DIR / "subdivisions" / code / f"{_slug(name)}.svg"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(svg, encoding="utf-8")
            counts[code] = counts.get(code, 0) + 1
    return counts


def build_world_svg() -> bool:
    src = RAW_VECTOR_DIR / "ne_10m_admin_0_countries.geojson"
    if not src.is_file():
        return False
    width, height, tol = 3600.0, 1800.0, 0.8
    paths: list[str] = []
    for feature in json.loads(src.read_text(encoding="utf-8"))["features"]:
        props = feature.get("properties") or {}
        code = _iso2(props) or _slug(str(props.get("ADM0_A3") or "xx"))
        segs: list[str] = []
        for poly in _polygons(feature.get("geometry")):
            for ring in poly:
                proj = [((lon + 180) * 10, (90 - lat) * 10) for lon, lat in ring]
                kept = [proj[0]]
                for x, y in proj[1:-1]:
                    if abs(x - kept[-1][0]) >= tol or abs(y - kept[-1][1]) >= tol:
                        kept.append((x, y))
                if len(kept) >= 3:
                    segs.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in kept) + "Z")
        if segs:
            paths.append(f'<path id="{code}" fill-rule="evenodd" d="{"".join(segs)}"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}"'
        f' width="{width:.0f}" height="{height:.0f}"><title>World countries</title>'
        f'<g fill="currentColor">{"".join(paths)}</g></svg>\n'
    )
    (SVG_DIR / "world.svg").parent.mkdir(parents=True, exist_ok=True)
    (SVG_DIR / "world.svg").write_text(svg, encoding="utf-8")
    return True


def _dir_stats(path: Path, pattern: str = "*") -> dict[str, int]:
    files = [p for p in path.rglob(pattern) if p.is_file()] if path.is_dir() else []
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}


def write_catalog(vector_groups: dict[str, list[str]], subdivisions: dict[str, int]) -> None:
    catalog = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "serve_root": "assets/geo (served by tools/geo-assets/serve_tiles.mjs at /<path>)",
        "sections": {
            "imagery": {
                "tiles": {"path": "tiles/{z}/{x}/{y}.jpg", **_dir_stats(GEO_ROOT / "tiles")},
                "tiles_hq": {
                    "path": "tiles_hq/{z}/{x}/{y}.jpg",
                    **_dir_stats(GEO_ROOT / "tiles_hq"),
                },
                "dem": {"path": "dem/{z}/{x}/{y}.png", **_dir_stats(GEO_ROOT / "dem")},
            },
            "vector": {
                "base_layers": sorted(
                    f"raw/vector/{p.name}" for p in RAW_VECTOR_DIR.glob("*.geojson")
                )
                + sorted(f"raw/vector/{p.name}" for p in RAW_VECTOR_DIR.glob("*.json")),
                "groups": vector_groups,
                "curated": sorted(f"vector/{p.name}" for p in (GEO_ROOT / "vector").glob("*")),
                "license": LICENSES["natural_earth"],
            },
            "svg": {
                "countries": {"path": "svg/countries/<iso2>.svg", **_dir_stats(SVG_DIR / "countries")},
                "subdivisions": {
                    "path": "svg/subdivisions/<iso2>/<slug>.svg",
                    "per_country": subdivisions,
                },
                "world": "svg/world.svg",
                "styling": "Single path with fill=currentColor; recolor via CSS color.",
                "license": LICENSES["natural_earth"],
            },
            "flags": {
                "path": "flags/<iso2>.svg (also flags/4x3/, flags/1x1/)",
                **_dir_stats(FLAGS_DIR, "*.svg"),
                "license": LICENSES["flags"],
            },
            "icons": {
                "path": "icons/<name>.svg",
                **_dir_stats(ICONS_DIR, "*.svg"),
                "license": LICENSES["lucide"],
            },
            "fonts": {"path": "fonts/", **_dir_stats(GEO_ROOT / "fonts")},
            "textures": {"path": "textures/", **_dir_stats(GEO_ROOT / "textures")},
        },
    }
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--subdivisions",
        default="id",
        help="Comma-separated ISO2 codes for first-level subdivision silhouettes.",
    )
    parser.add_argument("--skip-icons", action="store_true", help="Do not fetch the icon set.")
    args = parser.parse_args()

    print("[library] Natural Earth layers")
    groups = fetch_natural_earth_layers()
    if not args.skip_icons:
        print(f"[library] icons: {fetch_lucide_icons()} SVG files")
    print(f"[library] flags: {complete_flags()} top-level SVG files")
    print(f"[library] country silhouettes: {build_country_svgs()}")
    codes = [c.strip() for c in args.subdivisions.split(",") if c.strip()]
    subdivisions = build_subdivision_svgs(codes)
    print(f"[library] subdivision silhouettes: {subdivisions}")
    print(f"[library] world.svg: {build_world_svg()}")
    write_catalog(groups, subdivisions)
    print(f"[library] catalog -> {CATALOG_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
