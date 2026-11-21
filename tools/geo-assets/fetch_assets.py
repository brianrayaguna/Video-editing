#!/usr/bin/env python3
"""Idempotent downloader and SHA-256 manifest verifier for Geoverum geospatial assets.

Downloads commercially safe, open-licensed satellite imagery tiles, vector datasets,
fonts, flags, icons, and the pinned MapLibre GL runtime into `assets/geo/raw/`,
and writes a deterministic provenance manifest at `assets/geo/MANIFEST.json`.

Sources and Licenses:
- NASA Blue Marble: Next Generation (GIBS WMTS, z0-z4): Public Domain (NASA Earth Observatory)
- EOX Sentinel-2 cloudless 2016 (`s2cloudless_3857`, z0-z11 AOI): CC BY 4.0
  (EOX IT Services GmbH; contains modified Copernicus Sentinel data 2016)
- Natural Earth 1:10m cultural & physical vectors: Public Domain (CC0)
- PB2002 Tectonic Plate Boundaries (Peter Bird 2003 / fraxen): ODC-By 1.0
- GEM Global Active Faults Database: CC BY-SA 4.0
- Google Fonts (Space Grotesk, Archivo Black, Unbounded, Inter): SIL Open Font License 1.1
- Flag Icons (`lipis/flag-icons`): MIT License
- Material Design Symbols (`google/material-design-icons`): Apache License 2.0
- MapLibre GL JS `5.24.0`: BSD-3-Clause License
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GEO_ROOT = REPO_ROOT / "assets" / "geo"
RAW_DIR = GEO_ROOT / "raw"
FONTS_DIR = GEO_ROOT / "fonts"
FLAGS_DIR = GEO_ROOT / "flags"
ICONS_DIR = GEO_ROOT / "icons"
VENDOR_DIR = GEO_ROOT / "vendor"
MANIFEST_PATH = GEO_ROOT / "MANIFEST.json"

USER_AGENT = "vedit-geo-asset-fetcher/1.0 (https://github.com/geoverum)"

STATIC_ASSETS: list[dict[str, str]] = [
    {
        "id": "ne_10m_admin_0_countries",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson",
        "dest": "raw/vector/ne_10m_admin_0_countries.geojson",
        "license": "Public Domain (Natural Earth)",
        "attribution": "Made with Natural Earth.",
    },
    {
        "id": "ne_10m_admin_1_states_provinces",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson",
        "dest": "raw/vector/ne_10m_admin_1_states_provinces.geojson",
        "license": "Public Domain (Natural Earth)",
        "attribution": "Made with Natural Earth.",
    },
    {
        "id": "ne_10m_geography_marine_polys",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_geography_marine_polys.geojson",
        "dest": "raw/vector/ne_10m_geography_marine_polys.geojson",
        "license": "Public Domain (Natural Earth)",
        "attribution": "Made with Natural Earth.",
    },
    {
        "id": "ne_10m_geography_regions_polys",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_geography_regions_polys.geojson",
        "dest": "raw/vector/ne_10m_geography_regions_polys.geojson",
        "license": "Public Domain (Natural Earth)",
        "attribution": "Made with Natural Earth.",
    },
    {
        "id": "pb2002_tectonic_boundaries",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/PB2002_boundaries.json",
        "dest": "raw/vector/PB2002_boundaries.json",
        "license": "ODC-By 1.0",
        "attribution": "Peter Bird (2003) PB2002 / Hugo Ahlenius (fraxen/tectonicplates).",
    },
    {
        "id": "pb2002_tectonic_plates",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/PB2002_plates.json",
        "dest": "raw/vector/PB2002_plates.json",
        "license": "ODC-By 1.0",
        "attribution": "Peter Bird (2003) PB2002 / Hugo Ahlenius (fraxen/tectonicplates).",
    },
    {
        "id": "gem_active_faults",
        "category": "vector",
        "url": "https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/master/geojson/gem_active_faults_harmonized.geojson",
        "dest": "raw/vector/gem_active_faults_harmonized.geojson",
        "license": "CC BY-SA 4.0",
        "attribution": "Styron & Pagani (2020) GEM Global Active Faults Database.",
    },
    {
        "id": "font_space_grotesk",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf",
        "dest": "fonts/SpaceGrotesk-Variable.ttf",
        "license": "SIL Open Font License 1.1",
        "attribution": "Space Grotesk by Florian Karsten.",
    },
    {
        "id": "font_space_grotesk_license",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/OFL.txt",
        "dest": "fonts/SpaceGrotesk-OFL.txt",
        "license": "SIL Open Font License 1.1",
        "attribution": "Space Grotesk by Florian Karsten.",
    },
    {
        "id": "font_archivo_black",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/archivoblack/ArchivoBlack-Regular.ttf",
        "dest": "fonts/ArchivoBlack-Regular.ttf",
        "license": "SIL Open Font License 1.1",
        "attribution": "Archivo Black by Omnibus-Type.",
    },
    {
        "id": "font_archivo_black_license",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/archivoblack/OFL.txt",
        "dest": "fonts/ArchivoBlack-OFL.txt",
        "license": "SIL Open Font License 1.1",
        "attribution": "Archivo Black by Omnibus-Type.",
    },
    {
        "id": "font_unbounded",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/unbounded/Unbounded%5Bwght%5D.ttf",
        "dest": "fonts/Unbounded-Variable.ttf",
        "license": "SIL Open Font License 1.1",
        "attribution": "Unbounded by NaN, Studio Feixen, and Polkadot.",
    },
    {
        "id": "font_unbounded_license",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/unbounded/OFL.txt",
        "dest": "fonts/Unbounded-OFL.txt",
        "license": "SIL Open Font License 1.1",
        "attribution": "Unbounded by NaN, Studio Feixen, and Polkadot.",
    },
    {
        "id": "font_inter",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
        "dest": "fonts/Inter-Variable.ttf",
        "license": "SIL Open Font License 1.1",
        "attribution": "Inter by The Inter Project Authors.",
    },
    {
        "id": "font_inter_license",
        "category": "font",
        "url": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/OFL.txt",
        "dest": "fonts/Inter-OFL.txt",
        "license": "SIL Open Font License 1.1",
        "attribution": "Inter by The Inter Project Authors.",
    },
    {
        "id": "flag_icons_tarball",
        "category": "flags",
        "url": "https://registry.npmjs.org/flag-icons/-/flag-icons-7.2.3.tgz",
        "dest": "raw/flag-icons-7.2.3.tgz",
        "license": "MIT",
        "attribution": "flag-icons by Panayiotis Lipiridis (lipis).",
    },
    {
        "id": "icon_location_on",
        "category": "icon",
        "url": "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/location_on/materialsymbolsrounded/location_on_24px.svg",
        "dest": "icons/location_on.svg",
        "license": "Apache-2.0",
        "attribution": "Google Material Symbols.",
    },
    {
        "id": "icon_explore",
        "category": "icon",
        "url": "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/explore/materialsymbolsrounded/explore_24px.svg",
        "dest": "icons/explore.svg",
        "license": "Apache-2.0",
        "attribution": "Google Material Symbols.",
    },
    {
        "id": "icon_warning",
        "category": "icon",
        "url": "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/warning/materialsymbolsrounded/warning_24px.svg",
        "dest": "icons/warning.svg",
        "license": "Apache-2.0",
        "attribution": "Google Material Symbols.",
    },
    {
        "id": "icon_tsunami",
        "category": "icon",
        "url": "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/tsunami/materialsymbolsrounded/tsunami_24px.svg",
        "dest": "icons/tsunami.svg",
        "license": "Apache-2.0",
        "attribution": "Google Material Symbols.",
    },
    {
        "id": "icon_public",
        "category": "icon",
        "url": "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/public/materialsymbolsrounded/public_24px.svg",
        "dest": "icons/public.svg",
        "license": "Apache-2.0",
        "attribution": "Google Material Symbols.",
    },
    {
        "id": "vendor_maplibre_js",
        "category": "vendor",
        "url": "https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js",
        "dest": "vendor/maplibre-gl.js",
        "license": "BSD-3-Clause",
        "attribution": "MapLibre GL JS contributors.",
    },
    {
        "id": "vendor_maplibre_css",
        "category": "vendor",
        "url": "https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css",
        "dest": "vendor/maplibre-gl.css",
        "license": "BSD-3-Clause",
        "attribution": "MapLibre GL JS contributors.",
    },
]


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """Convert WGS84 latitude/longitude to Web Mercator XYZ slippy tile indices."""
    lat_rad = math.radians(max(min(lat_deg, 85.0511), -85.0511))
    n = 2.0**zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    max_idx = int(n) - 1
    return max(0, min(xtile, max_idx)), max(0, min(ytile, max_idx))


def enumerate_bbox_tiles(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, zoom: int
) -> list[tuple[int, int, int]]:
    """Return all `(z, x, y)` tile coordinates covering a geographic bounding box."""
    x0, y1 = deg2num(min_lat, min_lon, zoom)
    x1, y0 = deg2num(max_lat, max_lon, zoom)
    return [
        (zoom, x, y)
        for x in range(min(x0, x1), max(x0, x1) + 1)
        for y in range(min(y0, y1), max(y0, y1) + 1)
    ]


def build_tile_plan(
    aoi_bboxes: list[tuple[int, tuple[float, float, float, float]]] | None = None,
) -> list[tuple[str, int, int, int, str, Path]]:
    """Build the list of `(provider, z, x, y, url, dest)` tiles to fetch.

    Always includes global z0-z4 base coverage. Pass project-specific `(zoom, (w, s, e, n))`
    entries via `--aoi-config` for higher-zoom regional or close-up tiles.
    """
    tasks: list[tuple[str, int, int, int, str, Path]] = []

    # 1. NASA GIBS Blue Marble Shaded Relief & Bathymetry (z0-z4 global)
    for z in range(5):
        n = 2**z
        for x in range(n):
            for y in range(n):
                url = (
                    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
                    f"BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"
                )
                dest = RAW_DIR / "tiles_bmng" / str(z) / str(x) / f"{y}.jpg"
                tasks.append(("nasa_bmng", z, x, y, url, dest))

    # 2. EOX Sentinel-2 cloudless 2016 (CC BY 4.0)
    # Note: WMTS KVP/REST path on tiles.maps.eox.at uses /{z}/{y}/{x}.jpg (TileMatrix/TileRow/TileCol)
    eox_coords: set[tuple[int, int, int]] = set()
    # Global z0-z4
    for z in range(5):
        n = 2**z
        for x in range(n):
            for y in range(n):
                eox_coords.add((z, x, y))

    for z, bbox in aoi_bboxes or []:
        for coord in enumerate_bbox_tiles(*bbox, z):
            eox_coords.add(coord)

    for idx, (z, x, y) in enumerate(sorted(eox_coords)):
        sub = ("a", "b", "c", "d")[idx % 4]
        url = f"https://{sub}.tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
        dest = RAW_DIR / "tiles_s2_2016" / str(z) / str(x) / f"{y}.jpg"
        tasks.append(("eox_s2_2016", z, x, y, url, dest))

    return tasks


def sha256_file(path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(url: str, dest: Path, retries: int = 4) -> tuple[Path, int]:
    """Download `url` to `dest` atomically using curl with strict timeouts if not already present."""
    if dest.exists() and dest.stat().st_size >= 64:
        return dest, dest.stat().st_size
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    last_err: str = ""
    for attempt in range(retries):
        res = subprocess.run(
            [
                "curl",
                "-sS",
                "-L",
                "--fail",
                "--connect-timeout",
                "5",
                "--max-time",
                "12",
                "-A",
                USER_AGENT,
                "-o",
                str(tmp),
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and tmp.exists() and tmp.stat().st_size >= 64:
            sz = tmp.stat().st_size
            tmp.replace(dest)
            return dest, sz
        last_err = res.stderr.strip() or f"exit {res.returncode}"
        time.sleep(0.3 * (attempt + 1))
    raise RuntimeError(f"Failed to download {url} after {retries} attempts: {last_err}")


def extract_flag_icons(tarball_path: Path) -> int:
    """Extract 4x3 and 1x1 SVG flags from the flag-icons npm tarball."""
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)
    extracted = 0
    with tarfile.open(tarball_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # package/flags/4x3/id.svg or package/flags/1x1/id.svg or package/LICENSE
            parts = Path(member.name).parts
            if len(parts) >= 3 and parts[1] == "flags" and parts[2] in ("4x3", "1x1"):
                rel = Path(*parts[2:])
                out_path = FLAGS_DIR / rel
                out_path.parent.mkdir(parents=True, exist_ok=True)
                fobj = tar.extractfile(member)
                if fobj is not None:
                    out_path.write_bytes(fobj.read())
                    extracted += 1
            elif parts[-1] == "LICENSE":
                fobj = tar.extractfile(member)
                if fobj is not None:
                    (FLAGS_DIR / "LICENSE").write_bytes(fobj.read())
    return extracted


def derive_static_bold_instances() -> list[Path]:
    """Pin static Bold instances of variable fonts so libass captions render a true bold.

    libass renders only the default (Regular) instance of a variable font, so caption
    styles that need a heavy weight read the derived `<Family>-Bold.ttf`. Requires the
    optional `fonttools` package; skipped with a notice when it is unavailable.
    """
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError:
        print("  [skip] fonttools not installed; static bold caption fonts not derived")
        return []
    derived: list[Path] = []
    for family, src_name, axes in (
        ("Inter", "Inter-Variable.ttf", {"wght": 700, "opsz": 32}),
    ):
        src = FONTS_DIR / src_name
        if not src.is_file():
            continue
        font = instantiateVariableFont(TTFont(src), axes, updateFontNames=False)
        names = font["name"]
        for name_id in (2, 4, 6, 16, 17, 21, 22, 25):
            names.removeNames(nameID=name_id)
        names.setName(family, 1, 3, 1, 0x409)
        names.setName("Bold", 2, 3, 1, 0x409)
        names.setName(f"{family} Bold", 4, 3, 1, 0x409)
        names.setName(f"{family}-Bold", 6, 3, 1, 0x409)
        font["OS/2"].usWeightClass = 700
        font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0b1000001) | 0b100000
        font["head"].macStyle |= 1
        dest = FONTS_DIR / f"{family}-Bold.ttf"
        font.save(dest)
        derived.append(dest)
    return derived


def write_manifest(tile_tasks: list[tuple[str, int, int, int, str, Path]]) -> dict:
    """Compute SHA-256 digests and write `assets/geo/MANIFEST.json`."""
    static_entries = []
    for item in STATIC_ASSETS:
        p = GEO_ROOT / item["dest"]
        static_entries.append(
            {
                "id": item["id"],
                "category": item["category"],
                "path": f"assets/geo/{item['dest']}",
                "source_url": item["url"],
                "license": item["license"],
                "attribution": item["attribution"],
                "bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            }
        )

    # Summarize tile collections with aggregate root hashes to keep MANIFEST.json compact and git-friendly
    tile_collections: dict[str, dict] = {}
    for provider, z, _x, _y, _url, dest in tile_tasks:
        grp = tile_collections.setdefault(
            provider,
            {
                "provider": provider,
                "tile_count": 0,
                "total_bytes": 0,
                "zoom_levels": set(),
                "tree_hasher": hashlib.sha256(),
            },
        )
        size = dest.stat().st_size
        digest = sha256_file(dest)
        rel = dest.relative_to(GEO_ROOT).as_posix()
        grp["tile_count"] += 1
        grp["total_bytes"] += size
        grp["zoom_levels"].add(z)
        grp["tree_hasher"].update(f"{rel}:{size}:{digest}\n".encode())

    tile_collection_entries = [
        {
            "id": "nasa_bmng",
            "title": "NASA Blue Marble: Next Generation (Shaded Relief & Bathymetry)",
            "source_url_template": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
            "license": "Public Domain",
            "attribution": "NASA Earth Observatory / Goddard Space Flight Center",
            "directory": "assets/geo/raw/tiles_bmng",
            "zoom_levels": sorted(tile_collections["nasa_bmng"]["zoom_levels"]),
            "tile_count": tile_collections["nasa_bmng"]["tile_count"],
            "total_bytes": tile_collections["nasa_bmng"]["total_bytes"],
            "tree_sha256": tile_collections["nasa_bmng"]["tree_hasher"].hexdigest(),
        },
        {
            "id": "eox_s2_2016",
            "title": "EOX Sentinel-2 cloudless 2016 (EPSG:3857)",
            "source_url_template": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg",
            "license": "CC BY 4.0",
            "attribution": "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016)",
            "directory": "assets/geo/raw/tiles_s2_2016",
            "zoom_levels": sorted(tile_collections["eox_s2_2016"]["zoom_levels"]),
            "tile_count": tile_collections["eox_s2_2016"]["tile_count"],
            "total_bytes": tile_collections["eox_s2_2016"]["total_bytes"],
            "tree_sha256": tile_collections["eox_s2_2016"]["tree_hasher"].hexdigest(),
        },
    ]

    manifest = {
        "schema_version": "1.0",
        "profile": "geoverum",
        "generated_at": datetime.now(UTC).isoformat(),
        "on_screen_credit": "Imagery: NASA Blue Marble, EOX Sentinel-2 cloudless 2016 (Copernicus) · Map data: Natural Earth, PB2002, GEM",
        "static_assets": static_entries,
        "tile_collections": tile_collection_entries,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest() -> bool:
    """Verify all static assets and tile trees against `assets/geo/MANIFEST.json`."""
    if not MANIFEST_PATH.exists():
        print(f"ERROR: Manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        return False
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ok = True
    for item in manifest.get("static_assets", []):
        p = REPO_ROOT / item["path"]
        if not p.exists():
            print(f"MISSING: {item['path']}", file=sys.stderr)
            ok = False
            continue
        actual_sha = sha256_file(p)
        if actual_sha != item["sha256"]:
            print(
                f"HASH MISMATCH: {item['path']} expected {item['sha256']} got {actual_sha}",
                file=sys.stderr,
            )
            ok = False

    tile_tasks = build_tile_plan()
    by_provider: dict[str, list[tuple[str, int, int, int, str, Path]]] = {}
    for t in tile_tasks:
        by_provider.setdefault(t[0], []).append(t)

    for col in manifest.get("tile_collections", []):
        pid = col["id"]
        tasks = by_provider.get(pid, [])
        hasher = hashlib.sha256()
        total_bytes = 0
        for _prov, _z, _x, _y, _url, dest in tasks:
            if not dest.exists():
                print(f"MISSING TILE: {dest}", file=sys.stderr)
                ok = False
                break
            sz = dest.stat().st_size
            total_bytes += sz
            rel = dest.relative_to(GEO_ROOT).as_posix()
            hasher.update(f"{rel}:{sz}:{sha256_file(dest)}\n".encode())
        if (
            hasher.hexdigest() != col["tree_sha256"]
            or total_bytes != col["total_bytes"]
        ):
            print(f"TILE TREE MISMATCH for {pid}", file=sys.stderr)
            ok = False

    if ok:
        print(
            f"VERIFIED: {len(manifest['static_assets'])} static assets and "
            f"{sum(c['tile_count'] for c in manifest['tile_collections'])} satellite tiles match MANIFEST.json."
        )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify downloaded files against assets/geo/MANIFEST.json without downloading.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Maximum concurrent HTTP downloads (default: 12).",
    )
    parser.add_argument(
        "--aoi-config",
        type=Path,
        default=None,
        help=(
            "Optional JSON file defining project AOI bounding boxes as "
            '[{"zoom": 8, "bbox": [west, south, east, north]}].'
        ),
    )
    args = parser.parse_args()

    if args.verify:
        return 0 if verify_manifest() else 1

    print(
        f"Fetching {len(STATIC_ASSETS)} static geospatial, font, flag, icon, and runtime assets..."
    )
    for item in STATIC_ASSETS:
        dest = GEO_ROOT / item["dest"]
        _, sz = download_one(item["url"], dest)
        print(f"  [ok] {item['id']} ({sz / 1024:.1f} KB)")

    for derived in derive_static_bold_instances():
        print(f"  [ok] derived {derived.relative_to(REPO_ROOT)}")

    tarball = GEO_ROOT / "raw/flag-icons-7.2.3.tgz"
    n_flags = extract_flag_icons(tarball)
    print(f"  [ok] extracted {n_flags} SVG flags into assets/geo/flags/")

    aoi_bboxes: list[tuple[int, tuple[float, float, float, float]]] = []
    if args.aoi_config is not None:
        raw_aoi = json.loads(args.aoi_config.read_text(encoding="utf-8"))
        for entry in raw_aoi:
            z = int(entry["zoom"])
            w, s, e, n = (float(v) for v in entry["bbox"])
            aoi_bboxes.append((z, (w, s, e, n)))

    tile_tasks = build_tile_plan(aoi_bboxes=aoi_bboxes)
    print(
        f"Fetching {len(tile_tasks)} satellite raster tiles (NASA BMNG + EOX Sentinel-2 2016)..."
    )
    t0 = time.time()
    completed = 0
    total_bytes = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {
            pool.submit(download_one, url, dest): (prov, z, x, y)
            for prov, z, x, y, url, dest in tile_tasks
        }
        for fut in as_completed(future_map):
            _dest, sz = fut.result()
            completed += 1
            total_bytes += sz
            if completed % 200 == 0 or completed == len(tile_tasks):
                elapsed = max(0.001, time.time() - t0)
                print(
                    f"  [{completed}/{len(tile_tasks)}] "
                    f"{total_bytes / (1024 * 1024):.1f} MB ({completed / elapsed:.1f} tiles/s)"
                )

    manifest = write_manifest(tile_tasks)
    print(
        f"Manifest written to {MANIFEST_PATH.relative_to(REPO_ROOT)} "
        f"({len(manifest['static_assets'])} static assets, "
        f"{sum(c['tile_count'] for c in manifest['tile_collections'])} tiles)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
