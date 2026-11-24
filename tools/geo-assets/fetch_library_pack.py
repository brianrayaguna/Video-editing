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
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from xml.sax.saxutils import quoteattr

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
    "pb2002": "ODC-By 1.0 (Peter Bird PB2002 tectonic plates).",
    "gem_active_faults": "CC BY-SA 4.0 (GEM Global Active Faults Database).",
    "lucide": "ISC License (Lucide Contributors).",
    "material_symbols": "Apache-2.0 License (Material Symbols).",
    "flags": "MIT License (flag-icons contributors).",
}


def _download(url: str, dest: Path, min_bytes: int = 64, *, validate_json: bool = False) -> str:
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
            if tmp.stat().st_size < min_bytes:
                raise RuntimeError(f"download too small: {url}")
            if validate_json:
                json.loads(tmp.read_text(encoding="utf-8"))
            tmp.replace(dest)
            return "downloaded"
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            tmp.unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def fetch_natural_earth_layers() -> dict[str, list[str]]:
    jobs = [(group, name) for group, names in NE_LAYERS.items() for name in names]

    def _one(job: tuple[str, str]) -> tuple[str, str, str]:
        group, name = job
        dest = RAW_VECTOR_DIR / f"{name}.geojson"
        try:
            return group, name, _download(
                f"{NE_BASE}/{name}.geojson", dest, min_bytes=512, validate_json=True
            )
        except Exception as exc:  # noqa: BLE001
            return group, name, f"failed: {exc}"

    installed: dict[str, list[str]] = {group: [] for group in NE_LAYERS}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for group, name, status in pool.map(_one, jobs):
            print(f"  [vector] {name}: {status}")
            if status.startswith("failed"):
                failed.append(f"{name}: {status}")
            else:
                installed[group].append(f"raw/vector/{name}.geojson")
    if failed:
        raise RuntimeError(f"Failed downloading Natural Earth layers: {'; '.join(failed)}")
    return installed


def fetch_lucide_icons() -> int:
    tgz = GEO_ROOT / "raw" / f"lucide-static-{LUCIDE_VERSION}.tgz"
    _download(LUCIDE_TARBALL, tgz, min_bytes=10_000)
    count = 0
    max_icon_bytes = 256_000
    with tarfile.open(tgz, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if not (member.isfile() and re.fullmatch(r"package/icons/[a-z0-9-]+\.svg", name)):
                continue
            if member.size > max_icon_bytes:
                continue
            dest = ICONS_DIR / Path(name).name
            if dest.is_file():
                count += 1
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            data = src.read(max_icon_bytes + 1)
            if len(data) > max_icon_bytes or b"<svg" not in data[:512]:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part")
            try:
                tmp.write_bytes(data)
                tmp.replace(dest)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
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
    for poly in polys:
        for ring in poly:
            for i in range(len(ring) - 1):
                lon1, lon2 = ring[i][0], ring[i + 1][0]
                if abs(lon2 - lon1) < 180 and ((lon1 < 0 < lon2) or (lon2 < 0 < lon1)):
                    return polys
    wrapped_lons = [lon + 360 if lon < 0 else lon for lon in lons]
    if max(wrapped_lons) - min(wrapped_lons) >= max(lons) - min(lons):
        return polys
    return [
        [[[pt[0] + 360 if pt[0] < 0 else pt[0], pt[1]] for pt in ring] for ring in poly]
        for poly in polys
    ]


def _encode_svg_rings(
    polys: list[list[list[list[float]]]],
    *,
    kx: float,
    scale: float,
    off_x: float,
    off_y: float,
    tolerance: float,
    drop_small: bool,
) -> list[str]:
    parts: list[str] = []
    for poly in polys:
        for ring in poly:
            proj = [(pt[0] * kx * scale + off_x, -pt[1] * scale + off_y) for pt in ring]
            if len(proj) < 4:
                continue
            if drop_small:
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
                if drop_small:
                    continue
                kept = proj[:-1]
            parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in kept) + "Z")
    return parts


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
    pts = [(pt[0], pt[1]) for poly in polys for ring in poly for pt in ring]
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

    parts = _encode_svg_rings(
        polys,
        kx=kx,
        scale=scale,
        off_x=off_x,
        off_y=off_y,
        tolerance=tolerance,
        drop_small=True,
    )
    if not parts:
        parts = _encode_svg_rings(
            polys,
            kx=kx,
            scale=scale,
            off_x=off_x,
            off_y=off_y,
            tolerance=0.1,
            drop_small=False,
        )
    if not parts:
        return None
    data_attrs = "".join(
        f" data-{re.sub(r'[^a-z0-9_-]', '', k.lower())}={quoteattr(str(v))}"
        for k, v in (meta or {}).items()
    )
    safe_title = xml_escape(title)
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


def _geometry_area_score(geometry: dict[str, Any] | None) -> float:
    area = 0.0
    for poly in _polygons(geometry):
        if not poly:
            continue
        ring = poly[0]
        if len(ring) < 3:
            continue
        ring_area = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[(i + 1) % len(ring)][0], ring[(i + 1) % len(ring)][1]
            ring_area += x1 * y2 - x2 * y1
        area += abs(ring_area) / 2.0
    return area


def _country_feature_rank(feature: dict[str, Any]) -> tuple[int, float, float]:
    props = feature.get("properties") or {}
    is_sovereign = 1 if props.get("TYPE") in {"Sovereign country", "Country"} else 0
    try:
        pop = float(props.get("POP_EST") or 0.0)
    except (TypeError, ValueError):
        pop = 0.0
    return (is_sovereign, pop, _geometry_area_score(feature.get("geometry")))


def build_country_svgs() -> int:
    src = RAW_VECTOR_DIR / "ne_10m_admin_0_countries.geojson"
    if not src.is_file():
        print("  [svg] missing ne_10m_admin_0_countries.geojson; run fetch_assets.py first")
        return 0
    out_dir = SVG_DIR / "countries"
    out_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for feature in json.loads(src.read_text(encoding="utf-8"))["features"]:
        props = feature.get("properties") or {}
        code = _iso2(props)
        if not code:
            continue
        grouped.setdefault(code, []).append(feature)

    count = 0
    for code, features in grouped.items():
        primary = max(features, key=_country_feature_rank)
        props = primary.get("properties") or {}
        name = str(props.get("NAME_EN") or props.get("NAME") or code)
        svg = polygons_to_svg(
            _polygons(primary.get("geometry")),
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
    wanted = {c.lower() for c in iso2_codes if re.fullmatch(r"[a-z]{2}", c.lower())}
    if not wanted:
        return {}

    by_country: dict[str, list[dict[str, Any]]] = {}
    for feature in json.loads(src.read_text(encoding="utf-8"))["features"]:
        props = feature.get("properties") or {}
        code = str(props.get("iso_a2") or "").lower()
        if code in wanted and re.fullmatch(r"[a-z]{2}", code):
            by_country.setdefault(code, []).append(feature)

    counts: dict[str, int] = {}
    for code, features in by_country.items():
        base_slugs = [
            _slug(str((f.get("properties") or {}).get("name_en") or (f.get("properties") or {}).get("name") or "unnamed"))
            for f in features
        ]
        slug_freq: dict[str, int] = {}
        for s in base_slugs:
            slug_freq[s] = slug_freq.get(s, 0) + 1

        used_slugs: set[str] = set()
        for feature, base_slug in zip(features, base_slugs, strict=True):
            props = feature.get("properties") or {}
            name = str(props.get("name_en") or props.get("name") or "unnamed")
            slug = base_slug
            if slug_freq[base_slug] > 1:
                alt_name = str(props.get("name") or "")
                alt_slug = _slug(alt_name) if alt_name else ""
                if alt_slug and alt_slug != base_slug and alt_slug not in used_slugs:
                    slug = alt_slug
                else:
                    qualifier = _slug(str(props.get("type_en") or props.get("iso_3166_2") or ""))
                    if qualifier and qualifier != "unnamed":
                        slug = f"{base_slug}_{qualifier}"
            if slug in used_slugs:
                n = 2
                while f"{slug}_{n}" in used_slugs:
                    n += 1
                slug = f"{slug}_{n}"
            used_slugs.add(slug)

            svg = polygons_to_svg(
                _polygons(feature.get("geometry")),
                title=name,
                meta={"iso2": code, "name": slug},
            )
            if svg:
                out = SVG_DIR / "subdivisions" / code / f"{slug}.svg"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(svg, encoding="utf-8")
                counts[code] = counts.get(code, 0) + 1
    return counts


def build_world_svg() -> bool:
    src = RAW_VECTOR_DIR / "ne_10m_admin_0_countries.geojson"
    if not src.is_file():
        return False
    width, height, tol = 3600.0, 1800.0, 0.8
    segs_by_code: dict[str, list[str]] = {}
    for feature in json.loads(src.read_text(encoding="utf-8"))["features"]:
        props = feature.get("properties") or {}
        code = _iso2(props) or _slug(str(props.get("ADM0_A3") or "xx"))
        segs = segs_by_code.setdefault(code, [])
        for poly in _polygons(feature.get("geometry")):
            for ring in poly:
                proj = [((pt[0] + 180) * 10, (90 - pt[1]) * 10) for pt in ring]
                if len(proj) < 4:
                    continue
                kept = [proj[0]]
                for x, y in proj[1:-1]:
                    if abs(x - kept[-1][0]) >= tol or abs(y - kept[-1][1]) >= tol:
                        kept.append((x, y))
                if len(kept) >= 3:
                    segs.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in kept) + "Z")
    paths = [
        f'<path id={quoteattr(code)} fill-rule="evenodd" d="{"".join(segs)}"/>'
        for code, segs in segs_by_code.items()
        if segs
    ]
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


def _subdivision_counts_on_disk() -> dict[str, int]:
    sub_root = SVG_DIR / "subdivisions"
    if not sub_root.is_dir():
        return {}
    return {
        d.name: len(list(d.glob("*.svg")))
        for d in sorted(sub_root.iterdir())
        if d.is_dir() and re.fullmatch(r"[a-z]{2}", d.name)
    }


def write_catalog(vector_groups: dict[str, list[str]], subdivisions: dict[str, int]) -> None:
    on_disk_subdivisions = _subdivision_counts_on_disk()
    merged_subdivisions = {**on_disk_subdivisions, **subdivisions} if on_disk_subdivisions else subdivisions
    curated_dir = GEO_ROOT / "vector"
    curated = (
        sorted(
            f"vector/{p.name}"
            for p in curated_dir.glob("*")
            if p.is_file() and not p.name.startswith(".")
        )
        if curated_dir.is_dir()
        else []
    )
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
                "curated": curated,
                "licenses": {
                    "ne_*": LICENSES["natural_earth"],
                    "PB2002_*": LICENSES["pb2002"],
                    "gem_active_faults_*": LICENSES["gem_active_faults"],
                },
            },
            "svg": {
                "countries": {"path": "svg/countries/<iso2>.svg", **_dir_stats(SVG_DIR / "countries")},
                "subdivisions": {
                    "path": "svg/subdivisions/<iso2>/<slug>.svg",
                    "per_country": merged_subdivisions,
                },
                "world": "svg/world.svg" if (SVG_DIR / "world.svg").is_file() else None,
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
                "licenses": {
                    "lucide": LICENSES["lucide"],
                    "material_symbols": LICENSES["material_symbols"],
                },
            },
            "fonts": {"path": "fonts/", **_dir_stats(GEO_ROOT / "fonts")},
            "textures": {"path": "textures/", **_dir_stats(GEO_ROOT / "textures")},
        },
    }
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CATALOG_PATH.with_name(CATALOG_PATH.name + ".part")
    try:
        tmp.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CATALOG_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


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
