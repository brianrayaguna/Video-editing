"""Geospatial asset preparation and declarative world-space map scene baking commands."""

from __future__ import annotations

import array
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

import typer

from vedit.contracts import find_repo_root
from vedit.director.camera_moves import (
    camera_jitter_report,
    expand_move_plan,
    smooth_scene_keys,
)
from vedit.mastering.ffmpeg_master import _is_finite_loudnorm_val, _parse_loudnorm_json
from vedit.mastering.sound_design import (
    LOUDNESS_PROFILES,
    build_psychoacoustic_bgm_chain,
    pan_to_ffmpeg_filter,
    plan_narrative_audio_cues,
    synthesize_ambience_layers,
    synthesize_four_layer_impact,
    synthesize_granular_pad,
    synthesize_narrative_bgm,
    synthesize_room_tone_bed,
    synthesize_shepard_riser,
    synthesize_stinger,
    synthesize_tension_drone,
    synthesize_whoosh,
)

geo_app = typer.Typer(
    help="Prepare offline AOI satellite tiles/GeoJSON vectors and bake declarative map scenes."
)


def _deg2num(lat: float, lon: float, z: int) -> tuple[int, int]:
    lat_rad = math.radians(max(min(lat, 85.0511), -85.0511))
    n = 2.0**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(int(n) - 1, x)), max(0, min(int(n) - 1, y))


# Open-licensed imagery sources used by `geo prepare`.
# - Sentinel-2 cloudless 2016: CC BY 4.0 (EOX IT Services GmbH; contains modified Copernicus
#   Sentinel data 2016). Global coverage at ~10 m native resolution (z14).
# - National orthoimagery: public domain (U.S. Geological Survey, The National Map). Covers the
#   United States at ~1 m (served to z16) and answers HTTP 404 outside its coverage at z13+;
#   lower zooms return generic placeholder imagery, so it is requested only from z13.
# High-resolution (`--hq`) tiles try the national orthoimagery first and fall back to Sentinel-2
# up to its native zoom. Deeper tiles are not stored when only Sentinel-2 covers the area;
# `serve_tiles.mjs` upsamples the nearest stored ancestor instead.
S2_CLOUDLESS_MAX_NATIVE_Z = 14
NATIONAL_ORTHO_MIN_Z = 13
NATIONAL_ORTHO_MAX_Z = 16
_TILE_ABSENT_HTTP_CODES = frozenset({"204", "400", "404"})


def _s2_cloudless_url(z: int, x: int, y: int, subdomain: str = "a") -> str:
    return (
        f"https://{subdomain}.tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/"
        f"{z}/{y}/{x}.jpg"
    )


def _national_ortho_url(z: int, x: int, y: int) -> str:
    return (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/"
        f"{z}/{y}/{x}"
    )


def hq_tile_urls(z: int, x: int, y: int, subdomain: str = "a") -> list[str]:
    """Return open high-resolution tile URLs for `(z, x, y)` in fallback order."""
    urls: list[str] = []
    if NATIONAL_ORTHO_MIN_Z <= z <= NATIONAL_ORTHO_MAX_Z:
        urls.append(_national_ortho_url(z, x, y))
    if z <= S2_CLOUDLESS_MAX_NATIVE_Z:
        urls.append(_s2_cloudless_url(z, x, y, subdomain))
    return urls


def _enum_bbox_tiles(w: float, s: float, e: float, n: float, z: int) -> list[tuple[int, int, int]]:
    x0, y1 = _deg2num(s, w, z)
    x1, y0 = _deg2num(n, e, z)
    return [
        (z, x, y)
        for x in range(min(x0, x1), max(x0, x1) + 1)
        for y in range(min(y0, y1), max(y0, y1) + 1)
    ]


def _simplify_ring(ring: list[list[float]], step: int = 1) -> list[list[float]]:
    if step <= 1 or len(ring) <= 12:
        return [[round(c[0], 4), round(c[1], 4)] for c in ring]
    pts = ring[::step]
    if pts[-1] != ring[-1]:
        pts.append(ring[-1])
    return [[round(c[0], 4), round(c[1], 4)] for c in pts]


def _simplify_geom(geom: dict[str, Any], step: int = 1, min_pts: int = 0) -> dict[str, Any]:
    gtype = geom.get("type")
    if gtype == "Polygon":
        return {
            "type": gtype,
            "coordinates": [_simplify_ring(r, step) for r in geom["coordinates"]],
        }
    if gtype == "MultiPolygon":
        kept = []
        for poly in geom["coordinates"]:
            if len(poly[0]) >= min_pts:
                kept.append([_simplify_ring(r, step) for r in poly])
        if not kept and geom["coordinates"]:
            largest = max(geom["coordinates"], key=lambda p: len(p[0]))
            kept = [[_simplify_ring(r, step) for r in largest]]
        return {"type": gtype, "coordinates": kept}
    return geom


def _clip_ring_half_plane(
    ring: list[list[float]], split_lon: float, keep_east: bool
) -> list[list[float]]:
    """Clip a closed lon/lat ring against the vertical meridian x = split_lon."""
    if len(ring) < 3:
        return []
    pts = ring[:-1] if ring[0] == ring[-1] else list(ring)
    if len(pts) < 3:
        return []

    def _inside(p: list[float]) -> bool:
        return p[0] >= split_lon if keep_east else p[0] <= split_lon

    def _intersect(a: list[float], b: list[float]) -> list[float]:
        dx = b[0] - a[0]
        if abs(dx) < 1e-12:
            return [round(split_lon, 4), round(a[1], 4)]
        t = (split_lon - a[0]) / dx
        return [round(split_lon, 4), round(a[1] + t * (b[1] - a[1]), 4)]

    out: list[list[float]] = []
    prev = pts[-1]
    prev_in = _inside(prev)
    for curr in pts:
        curr_in = _inside(curr)
        if curr_in:
            if not prev_in:
                out.append(_intersect(prev, curr))
            out.append([round(curr[0], 4), round(curr[1], 4)])
        elif prev_in:
            out.append(_intersect(prev, curr))
        prev = curr
        prev_in = curr_in

    if len(out) < 3:
        return []
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def split_polygon_by_longitude(geom: dict[str, Any], split_lon: float) -> dict[str, dict[str, Any]]:
    """Split a GeoJSON Polygon/MultiPolygon along a meridian into west and east MultiPolygons."""
    polys = (
        [geom["coordinates"]]
        if geom.get("type") == "Polygon"
        else list(geom.get("coordinates") or [])
    )
    west_polys: list[list[list[list[float]]]] = []
    east_polys: list[list[list[list[float]]]] = []
    for poly in polys:
        if not poly:
            continue
        w_outer = _clip_ring_half_plane(poly[0], split_lon, keep_east=False)
        if len(w_outer) >= 4:
            west_polys.append([w_outer])
        e_outer = _clip_ring_half_plane(poly[0], split_lon, keep_east=True)
        if len(e_outer) >= 4:
            east_polys.append([e_outer])
    return {
        "west": {"type": "MultiPolygon", "coordinates": west_polys, "dissolve_seams": True},
        "east": {"type": "MultiPolygon", "coordinates": east_polys, "dissolve_seams": True},
    }


def filter_polygons_by_bbox(
    geom: dict[str, Any],
    *,
    min_lon: float,
    max_lon: float,
    min_lat: float,
    max_lat: float,
) -> dict[str, Any]:
    """Retain only polygon rings whose centroid lies within the specified lon/lat bounding box."""
    polys = (
        [geom["coordinates"]]
        if geom.get("type") == "Polygon"
        else list(geom.get("coordinates") or [])
    )
    kept: list[list[list[list[float]]]] = []
    for poly in polys:
        if not poly or not poly[0]:
            continue
        ring = poly[0]
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        if min_lon <= cx <= max_lon and min_lat <= cy <= max_lat:
            kept.append(poly)
    return {"type": "MultiPolygon", "coordinates": kept, "dissolve_seams": True}


def extract_project_vectors(
    *,
    repo_root: Path,
    countries: list[str] | None = None,
    continents: list[str] | None = None,
    provinces: list[str] | None = None,
    province_lat_min: float | None = None,
    province_lon_max: float | None = None,
) -> dict[str, Any]:
    """Extract clean Natural Earth country, continent, and dissolved-region GeoJSON bundles."""
    raw_vec = repo_root / "assets" / "geo" / "raw" / "vector"
    countries_file = raw_vec / "ne_10m_admin_0_countries.geojson"
    provinces_file = raw_vec / "ne_10m_admin_1_states_provinces.geojson"
    if not countries_file.is_file():
        raise FileNotFoundError(
            f"Missing Natural Earth countries dataset: {countries_file}. "
            "Run `python3 tools/geo-assets/fetch_assets.py` first."
        )

    want_countries = {c.strip().lower(): c.strip() for c in (countries or []) if c.strip()}
    want_continents = {c.strip().lower(): c.strip() for c in (continents or []) if c.strip()}
    want_provinces = [p.strip().lower() for p in (provinces or []) if p.strip()]

    result: dict[str, Any] = {
        "countries": {},
        "continents": {},
        "provinces": [],
        "provinces_by_name": {},
        "dissolved_region": None,
    }

    c_data = json.loads(countries_file.read_text(encoding="utf-8"))
    for feat in c_data.get("features") or []:
        props = feat.get("properties") or {}
        name = str(props.get("ADMIN") or props.get("NAME") or "")
        cont = str(props.get("CONTINENT") or "")
        nl = name.lower()
        cl = cont.lower()
        if nl in want_countries:
            key = want_countries[nl]
            result["countries"][key] = _simplify_geom(feat["geometry"], step=2, min_pts=20)
        if cl in want_continents:
            key = want_continents[cl]
            result["continents"].setdefault(key, []).append(
                {
                    "name": name,
                    "geometry": _simplify_geom(feat["geometry"], step=6, min_pts=18),
                }
            )

    if want_provinces and provinces_file.is_file():
        p_data = json.loads(provinces_file.read_text(encoding="utf-8"))
        region_polys: list[list[list[list[float]]]] = []
        for feat in p_data.get("features") or []:
            props = feat.get("properties") or {}
            pname = str(props.get("name") or "")
            admin = str(props.get("admin") or "")
            pnl = pname.lower()
            if not any(tok in pnl for tok in want_provinces):
                continue
            geom = _simplify_geom(feat["geometry"], step=1)
            result["provinces"].append({"admin": admin, "name": pname, "geometry": geom})
            if pname:
                result["provinces_by_name"][pname] = geom
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            for poly in polys:
                outer = poly[0]
                if province_lat_min is not None or province_lon_max is not None:
                    clipped = []
                    for pt in outer:
                        lon, lat = pt[0], pt[1]
                        if province_lat_min is not None and lat < province_lat_min - 0.25:
                            continue
                        if province_lon_max is not None and lon > province_lon_max + 0.2:
                            continue
                        clipped.append(
                            [
                                min(lon, province_lon_max) if province_lon_max is not None else lon,
                                max(lat, province_lat_min) if province_lat_min is not None else lat,
                            ]
                        )
                    if len(clipped) >= 6:
                        if clipped[0] != clipped[-1]:
                            clipped.append(clipped[0])
                        region_polys.append([clipped])
                elif len(outer) >= 6:
                    region_polys.append([outer])

        if region_polys:
            result["dissolved_region"] = {
                "type": "MultiPolygon",
                "coordinates": region_polys,
                "dissolve_seams": True,
            }
    return result


def _parse_tile_coord_row(row: Any, path: Path) -> tuple[int, int, int]:
    if not (
        isinstance(row, list)
        and len(row) == 3
        and all(isinstance(v, int) and not isinstance(v, bool) for v in row)
    ):
        raise ValueError(f"{path}: malformed tile row {row!r}; expected [z, x, y] integers")
    z, x, y = row
    if not (0 <= z <= 22 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError(f"{path}: tile {row!r} is outside the web-mercator grid")
    return (z, x, y)


def _extract_tile_list(data: Any, path: Path) -> set[tuple[int, int, int]]:
    rows = data.get("tiles") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected an object with a 'tiles' list")
    return {_parse_tile_coord_row(row, path) for row in rows}


def parse_tile_list(path: Path) -> set[tuple[int, int, int]]:
    """Read a coverage tile list `{"tiles": [[z, x, y], ...]}` into a set of tile coordinates.

    Raises `ValueError` for a missing `tiles` list, rows that are not three integers, or tiles
    outside the web-mercator grid (z 0-22).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _extract_tile_list(data, path)


_REGULAR_COVERAGE_ROUTES = ("tiles",)
_HQ_COVERAGE_ROUTES = ("tiles_hq", "tiles_hybrid")


def split_coverage_gaps(
    path: Path,
) -> tuple[set[tuple[int, int, int]], set[tuple[int, int, int]]]:
    """Split a coverage report into (regular-route gaps, HQ-route gaps).

    Regular-route gaps are served from the graded Sentinel-2 set; HQ-route gaps from the
    high-resolution set. A report without `by_route` (or tiles not listed under known routes)
    routes those tiles as HQ-route gaps.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tiles = _extract_tile_list(data, path)
    by_route = data.get("by_route")
    if not isinstance(by_route, dict):
        return set(), tiles

    def _rows(routes: tuple[str, ...]) -> set[tuple[int, int, int]]:
        out: set[tuple[int, int, int]] = set()
        for route in routes:
            route_rows = by_route.get(route)
            if route_rows is None:
                continue
            if not isinstance(route_rows, list):
                raise ValueError(f"{path}: route {route!r} must be a list of [z, x, y] rows")
            for row in route_rows:
                coord = _parse_tile_coord_row(row, path)
                if coord not in tiles:
                    raise ValueError(f"{path}: route {route!r} lists {row!r}, absent from 'tiles'")
                out.add(coord)
        return out

    reg = _rows(_REGULAR_COVERAGE_ROUTES)
    hq = _rows(_HQ_COVERAGE_ROUTES)
    unrouted = tiles - reg - hq
    if unrouted:
        hq = hq | unrouted
    return reg, hq


def _has_image_magic(path: Path) -> bool:
    with path.open("rb") as fh:
        head = fh.read(8)
    return head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG\r\n\x1a\n")


def _fetch_tile_set(
    root: Path,
    coords: set[tuple[int, int, int]],
    *,
    hq_aerial: bool | None,
    grade_tiles: bool,
    missing: set[tuple[int, int, int]] | None = None,
) -> tuple[int, int]:
    """Fetch satellite tiles: z<=12 from Sentinel-2 2016 (graded), z>=13 high-resolution.

    `hq_aerial` True sends every tile to the high-resolution fetcher, False sends every tile to
    Sentinel-2; None splits at z=13. Returns (Sentinel-2 tiles present, HQ tiles present).
    Tiles no source could supply are added to `missing` when it is given.
    """
    fetched_count = 0
    hq_fetched_count = 0
    raw_dir = root / "assets" / "geo" / "raw" / "tiles_s2_2016"
    hq_dir = root / "assets" / "geo" / "tiles_hq"
    if hq_aerial is True:
        s2_coords = []
        hq_coords = sorted(coords)
    elif hq_aerial is False:
        s2_coords = sorted(coords)
        hq_coords = []
    else:
        s2_coords = sorted(c for c in coords if c[0] <= 12)
        hq_coords = sorted(c for c in coords if c[0] >= 13)

    def _fetch_url(dest: Path, url: str) -> bool:
        if dest.is_file() and dest.stat().st_size >= 64:
            return True
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".jpg.part")
        for attempt in range(4):
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-L",
                    "--connect-timeout",
                    "5",
                    "--max-time",
                    "12",
                    "-w",
                    "%{http_code}",
                    "-o",
                    str(tmp),
                    url,
                ],
                capture_output=True,
                check=False,
                text=True,
            )
            status = proc.stdout.strip()
            if (
                proc.returncode == 0
                and status.startswith("2")
                and status not in _TILE_ABSENT_HTTP_CODES
                and tmp.is_file()
                and tmp.stat().st_size >= 64
                and _has_image_magic(tmp)
            ):
                tmp.replace(dest)
                return True
            tmp.unlink(missing_ok=True)
            if status in _TILE_ABSENT_HTTP_CODES:
                return False
            time.sleep(0.3 * (attempt + 1))
        return False

    def _download_s2(item: tuple[int, tuple[int, int, int]]) -> bool:
        idx, (z, x, y) = item
        dest = raw_dir / str(z) / str(x) / f"{y}.jpg"
        sub = ("a", "b", "c", "d")[idx % 4]
        return _fetch_url(dest, _s2_cloudless_url(z, x, y, sub))

    def _download_hq(item: tuple[int, tuple[int, int, int]]) -> bool:
        idx, (z, x, y) = item
        dest = hq_dir / str(z) / str(x) / f"{y}.jpg"
        sub = ("a", "b", "c", "d")[idx % 4]
        return any(_fetch_url(dest, url) for url in hq_tile_urls(z, x, y, sub))

    if s2_coords:
        with ThreadPoolExecutor(max_workers=16) as pool:
            s2_ok = list(pool.map(_download_s2, enumerate(s2_coords)))
        fetched_count = sum(s2_ok)
        if missing is not None:
            missing.update(c for c, ok in zip(s2_coords, s2_ok, strict=True) if not ok)

    if hq_coords:
        with ThreadPoolExecutor(max_workers=16) as pool:
            hq_ok = list(pool.map(_download_hq, enumerate(hq_coords)))
        hq_fetched_count = sum(hq_ok)
        if missing is not None:
            missing.update(c for c, ok in zip(hq_coords, hq_ok, strict=True) if not ok)

    if grade_tiles and s2_coords:
        node_bin = shutil.which("node")
        if not node_bin:
            raise RuntimeError("Node.js >= 22 is required to run tools/geo-assets/build_tiles.mjs.")
        subprocess.run(
            [node_bin, str(root / "tools" / "geo-assets" / "build_tiles.mjs")],
            check=True,
        )
    return fetched_count, hq_fetched_count


def fill_coverage_gaps(
    root: Path,
    regular_gaps: set[tuple[int, int, int]],
    hq_gaps: set[tuple[int, int, int]],
    *,
    fetch: Callable[..., tuple[int, int]] | None = None,
) -> dict[str, int]:
    """Fetch coverage gaps through the source each route serves and summarise the result.

    Regular-route gaps go to Sentinel-2 only (graded), up to its native zoom; deeper ones are
    unfillable by construction. HQ-route gaps use the default z=13 split. `coverage_unfillable`
    counts distinct tiles that still upscale an ancestor on at least one route.
    """
    fetch = fetch or _fetch_tile_set
    unfillable = {c for c in regular_gaps if c[0] > S2_CLOUDLESS_MAX_NATIVE_Z}
    regular_fetch = regular_gaps - unfillable
    shared_s2 = {c for c in regular_fetch if c[0] <= 12}
    hq_fetch = hq_gaps - shared_s2
    hq_has_s2 = any(c[0] <= 12 for c in hq_fetch)
    missing: set[tuple[int, int, int]] = set()
    s2_count = hq_count = 0
    if regular_fetch:
        s2_count, _ = fetch(
            root,
            regular_fetch,
            hq_aerial=False,
            grade_tiles=not hq_has_s2,
            missing=missing,
        )
    if hq_fetch:
        s2_more, hq_count = fetch(root, hq_fetch, hq_aerial=None, grade_tiles=True, missing=missing)
        s2_count += s2_more
    return {
        "coverage_gaps": len(regular_gaps | hq_gaps),
        "tiles_verified": s2_count,
        "hq_tiles_verified": hq_count,
        "coverage_unfillable": len(unfillable | missing),
    }


@geo_app.command("prepare")
def geo_prepare_cmd(
    out_file: Annotated[
        Path, typer.Option("--out-file", "-o", help="Destination project vectors JSON path.")
    ],
    bbox: Annotated[
        list[str] | None,
        typer.Option("--bbox", help="AOI tile box as 'W,S,E,N:Z' (repeatable)."),
    ] = None,
    country: Annotated[
        list[str] | None, typer.Option("--country", help="Country name to extract (repeatable).")
    ] = None,
    continent: Annotated[
        list[str] | None,
        typer.Option("--continent", help="Continent name to extract (repeatable)."),
    ] = None,
    province: Annotated[
        list[str] | None,
        typer.Option("--province", help="Province name substring for dissolved region."),
    ] = None,
    province_lat_min: Annotated[
        float | None, typer.Option("--province-lat-min", help="Optional south clip latitude.")
    ] = None,
    province_lon_max: Annotated[
        float | None, typer.Option("--province-lon-max", help="Optional east clip longitude.")
    ] = None,
    grade_tiles: Annotated[
        bool, typer.Option("--grade/--no-grade", help="Run build_tiles.mjs after fetching AOI.")
    ] = True,
    hq_aerial: Annotated[
        bool | None,
        typer.Option(
            "--hq/--no-hq",
            help="Fetch open high-resolution tiles into assets/geo/tiles_hq/: public-domain "
            "national orthoimagery where covered (~1 m, z<=16), otherwise Sentinel-2 2016 "
            "(~10 m, z<=14) (default: auto-enabled for z >= 13).",
        ),
    ] = None,
    tile_list: Annotated[
        Path | None,
        typer.Option(
            "--tile-list",
            help="Coverage JSON with a 'tiles' list of [z, x, y] rows (from a bake coverage "
            "pass), merged into the fetch set.",
        ),
    ] = None,
) -> None:
    """Fetch project AOI satellite tiles (without dirtying MANIFEST.json) and extract GeoJSON."""
    root = find_repo_root()
    fetched_count = 0
    hq_fetched_count = 0
    if bbox or tile_list:
        bbox_coords: set[tuple[int, int, int]] = set()
        for spec in bbox or []:
            if ":" not in spec:
                raise typer.BadParameter(f"Invalid --bbox {spec!r}; expected 'W,S,E,N:Z'.")
            box_part, z_part = spec.rsplit(":", 1)
            w, s, e, n = (float(v) for v in box_part.split(","))
            for z_token in z_part.split(","):
                bbox_coords.update(_enum_bbox_tiles(w, s, e, n, int(z_token)))
        regular_tile_coords: set[tuple[int, int, int]] = set()
        hq_tile_coords: set[tuple[int, int, int]] = set()
        if tile_list:
            try:
                if hq_aerial is None:
                    regular_tile_coords, hq_tile_coords = split_coverage_gaps(tile_list)
                else:
                    hq_tile_coords = parse_tile_list(tile_list)
            except (OSError, ValueError) as exc:
                raise typer.BadParameter(str(exc)) from exc
        regular_fetch = {c for c in regular_tile_coords if c[0] <= S2_CLOUDLESS_MAX_NATIVE_Z}
        if regular_fetch:
            s2_more, _ = _fetch_tile_set(
                root, regular_fetch, hq_aerial=False, grade_tiles=grade_tiles
            )
            fetched_count += s2_more
        merged_coords = bbox_coords | hq_tile_coords
        if merged_coords:
            s2_more, hq_more = _fetch_tile_set(
                root, merged_coords, hq_aerial=hq_aerial, grade_tiles=grade_tiles
            )
            fetched_count += s2_more
            hq_fetched_count += hq_more

    vectors = extract_project_vectors(
        repo_root=root,
        countries=country,
        continents=continent,
        provinces=province,
        province_lat_min=province_lat_min,
        province_lon_max=province_lon_max,
    )
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(vectors), encoding="utf-8")
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "tiles_verified": fetched_count,
                "hq_tiles_verified": hq_fetched_count,
                "vectors_path": str(out_file),
                "countries": sorted(vectors["countries"].keys()),
                "continents": sorted(vectors["continents"].keys()),
                "provinces": [p["name"] for p in vectors["provinces"]],
            },
            indent=2,
        )
    )


REJECTED_SCENE_LAYER_TYPES = frozenset(
    {
        "coord_plaque",
        "scale_comparison",
        "survey_pin",
        "orbital_sightlines",
        "culmination_sun",
        "callout_badge",
    }
)

_TEXT_LAYER_TYPES = frozenset({"glow_label", "pin_label", "curved_pointer_label", "year_badge"})
_THREE_D_MODELS = frozenset({"transmission_tower", "solar_farm", "substation", "survey_vessel"})

_REVEAL_MODES = frozenset(
    {"fade", "radial", "organic", "wipe_left", "wipe_right", "wipe_down", "wipe_up"}
)
# Numeric polygon keys: (lower bound, upper bound or None).
_POLYGON_NUMERIC_KEYS: dict[str, tuple[float, float | None]] = {
    "flag_wave_speed": (0.0, None),
    "flag_wave_cycles": (0.0, None),
    "flag_wave_angle_deg": (-360.0, 360.0),
    "fill_reveal_roughness": (0.0, 0.6),
}
_POLYGON_OPT_BOOL_FLOAT_KEYS: dict[str, tuple[float, float]] = {
    "flag_gloss": (0.0, 1.0),
    "flag_wave_warp": (0.0, 0.15),
}
# Polygon keys whose unknown values the renderer would silently replace with a default.
_POLYGON_ENUM_KEYS: dict[str, frozenset[Any]] = {
    "flag_reveal": _REVEAL_MODES,
    "fill_reveal_mode": _REVEAL_MODES,
    "flag_blend": frozenset({"normal", "multiply", "overlay", "soft-light", "screen"}),
    "flag_fit": frozenset({"stretch", "cover"}),
    "border_trace_ease": frozenset({"linear", "in_out", "out"}),
    "border_trace_dir": frozenset({"cw", "ccw"}),
    "border_trace_heads": frozenset({1, 2}),
}
_FLAG_CODE_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _load_scene_vectors(spec: dict[str, Any], base_dir: Path | None) -> dict[str, Any] | None:
    """Load the scene's `vectors_file`; None when absent, unreadable, or relative without a base."""
    ref = spec.get("vectors_file") or spec.get("vectors_path")
    if not ref:
        return None
    path = Path(str(ref)).expanduser()
    if not path.is_absolute():
        if base_dir is None:
            return None
        path = base_dir / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_geom_ref(vectors: dict[str, Any] | None, ref: Any) -> Any:
    """Resolve a layer `geom_ref` (inline geometry or dotted path into the vectors) or None."""
    if isinstance(ref, dict) and ref.get("type"):
        return ref
    if not isinstance(ref, str) or vectors is None:
        return None
    cur: Any = vectors
    for part in ref.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _separately_traced_parts(geom: Any) -> int:
    """Count parts a border trace walks independently with seams between them.

    Feature lists, FeatureCollections and seam-dissolved MultiPolygons trace every part from its
    own start; a single Polygon or a plain MultiPolygon (islands of one outline) counts as 1.
    """
    if isinstance(geom, list):
        return sum(1 for g in geom if g)
    if isinstance(geom, dict):
        if geom.get("type") == "FeatureCollection":
            return sum(1 for g in geom.get("features") or [] if g)
        if geom.get("type") == "MultiPolygon" and geom.get("dissolve_seams"):
            return len(geom.get("coordinates") or [])
    return 1


def _as_finite_float(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


def validate_map_scene(
    spec: dict[str, Any],
    *,
    repo_root: Path | None = None,
    base_dir: Path | None = None,
    check_hq_tiles: bool = True,
) -> dict[str, Any]:
    """Validate declarative map_scene.json against Geoverum craft and sharpness guardrails.

    `base_dir` resolves a relative `vectors_file` so geometry-dependent checks can run.
    """
    errors: list[str] = []
    warnings: list[str] = []
    vectors = _load_scene_vectors(spec, base_dir)
    width = int(spec.get("width", 1080))
    height = int(spec.get("height", 1920))
    min_font_px = 36 if height >= 1600 else 28
    hq_dir = (repo_root / "assets" / "geo" / "tiles_hq") if repo_root else None

    for act in spec.get("acts") or []:
        act_id = str(act.get("act_id") or "unknown")
        act_kind = str(act.get("kind") or act.get("mode") or act.get("type") or "map")
        if act_kind != "map":
            continue
        dur = float(act.get("duration_s", 0.0))
        tile_source = str(act.get("tile_source") or "hybrid")
        layers = list(act.get("layers") or [])

        # 0. Cut-accent radial zoom blur windows and strength
        cut_windows: list[float] = []
        for key, upper in (
            ("cut_blur_in_s", None),
            ("cut_blur_out_s", None),
            ("cut_blur_strength", 0.4),
        ):
            if key not in act:
                continue
            value = _as_finite_float(act[key])
            if value is None:
                errors.append(f"[{act_id}] {key} must be a number, got {act[key]!r}.")
                continue
            if value < 0 or (upper is not None and value > upper):
                bound = f"between 0 and {upper}" if upper is not None else "a finite value >= 0"
                errors.append(f"[{act_id}] {key} must be {bound}, got {value}.")
                continue
            if key != "cut_blur_strength":
                cut_windows.append(value)
        if dur > 0 and sum(cut_windows) > dur + 1e-6:
            warnings.append(
                f"[{act_id}] cut_blur_in_s + cut_blur_out_s = {sum(cut_windows):.2f}s exceeds the "
                f"act duration {dur:.2f}s; the blur never clears mid-act."
            )

        # 1. Reject legacy/chrome slop layers and micro-typography
        text_intervals: list[tuple[float, float, str]] = []
        for idx, layer in enumerate(layers):
            ltype = str(layer.get("type") or "")
            if ltype in REJECTED_SCENE_LAYER_TYPES:
                errors.append(
                    f"[{act_id}] layer #{idx} uses rejected chrome type '{ltype}'. "
                    "Use calibrated boxless primitives (glow_label, pin_label, "
                    "curved_pointer_label, dashed_distance, void_wipe, counter_odometer, "
                    "prohibition_pins)."
                )
            if ltype in _TEXT_LAYER_TYPES:
                fpx = float(layer.get("font_px", 56))
                if fpx < min_font_px:
                    errors.append(
                        f"[{act_id}] layer #{idx} ({ltype}) font_px={fpx} is below minimum "
                        f"{min_font_px}px for {width}x{height} legibility."
                    )
                t0 = float(layer.get("start_s", 0.0))
                t1 = float(layer.get("end_s", dur))
                text_intervals.append((t0, t1, str(layer.get("text") or ltype)))

        # 2. Enforce calm hierarchy: at most 4 concurrent text overlays at any sampled timestamp
        if text_intervals and dur > 0:
            step = 0.25
            t_cur = 0.0
            while t_cur <= dur:
                active = [lbl for (a, b, lbl) in text_intervals if a <= t_cur <= b]
                if len(active) > 4:
                    errors.append(
                        f"[{act_id}] {len(active)} concurrent text overlays at t={t_cur:.2f}s "
                        f"({', '.join(active[:5])}); max allowed is 4 to prevent visual clutter."
                    )
                    break
                t_cur += step

        # 3. Close-up sharpness check: zoom >= 13.5 requires HQ aerial tiles (never Sentinel-2)
        kfs = list(act.get("camera_keyframes") or [])
        max_zoom = 0.0
        closeup_centers: list[tuple[float, float, float]] = []
        for kf in kfs:
            if isinstance(kf, dict):
                z = float(kf.get("zoom", 0.0))
                ctr = kf.get("center") or [kf.get("lng", 0.0), kf.get("lat", 0.0)]
            else:
                z = float(kf[3]) if len(kf) > 3 else 0.0
                ctr = [float(kf[1]), float(kf[2])] if len(kf) > 2 else [0.0, 0.0]
            if z > max_zoom:
                max_zoom = z
            if z >= 13.5:
                closeup_centers.append((float(ctr[0]), float(ctr[1]), z))

        if max_zoom >= 13.5 and tile_source == "graded":
            errors.append(
                f"[{act_id}] max zoom {max_zoom:.1f} uses Sentinel-2 'graded' tiles "
                "which blur below ~2 km. Use tile_source 'hybrid' or 'realistic' and fetch "
                "high-resolution tiles with `vedit geo prepare --hq`."
            )
        use_project_tiles = tile_source in {"project", "project_graded"}
        project_tiles_spec = spec.get("project_tiles_dir")
        if use_project_tiles and not project_tiles_spec:
            errors.append(
                f"[{act_id}] tile_source '{tile_source}' requires top-level 'project_tiles_dir'."
            )
        if check_hq_tiles and closeup_centers and (hq_dir is not None or use_project_tiles):
            probe_root = hq_dir
            if use_project_tiles and project_tiles_spec:
                p_dir = Path(str(project_tiles_spec))
                probe_root = p_dir if p_dir.is_absolute() else ((base_dir or Path.cwd()) / p_dir)
            for lng, lat, z in closeup_centers:
                check_z = min(16, max(13, round(z)))
                found_z: int | None = None
                if probe_root is not None:
                    for probe_z in range(check_z, 12, -1):
                        tx, ty = _deg2num(lat, lng, probe_z)
                        if (probe_root / str(probe_z) / str(tx) / f"{ty}.jpg").is_file():
                            found_z = probe_z
                            break
                has_hq = found_z is not None
                if (
                    not use_project_tiles
                    and has_hq
                    and z >= 14.5
                    and (found_z is None or found_z <= S2_CLOUDLESS_MAX_NATIVE_Z)
                    and probe_root is not None
                ):
                    has_ortho = any(
                        (
                            probe_root
                            / str(oz)
                            / str(_deg2num(lat, lng, oz)[0])
                            / f"{_deg2num(lat, lng, oz)[1]}.jpg"
                        ).is_file()
                        for oz in range(S2_CLOUDLESS_MAX_NATIVE_Z + 1, NATIONAL_ORTHO_MAX_Z + 1)
                    )
                    if not has_ortho:
                        warnings.append(
                            f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} exceeds "
                            f"the ~10 m Sentinel-2 native zoom (z{S2_CLOUDLESS_MAX_NATIVE_Z}) "
                            "and no sharper orthoimagery covers it; cap the zoom near 14.5 or "
                            "supply a project-scoped aerial plate."
                        )
                if not has_hq:
                    if use_project_tiles:
                        errors.append(
                            f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} has no "
                            f"project tiles in {probe_root} covering z13-16."
                        )
                    else:
                        errors.append(
                            f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} has no "
                            "high-resolution aerial tiles in assets/geo/tiles_hq/. Run "
                            f"`vedit geo prepare --bbox \"{lng-0.06:.3f},{lat-0.06:.3f},"
                            f"{lng+0.06:.3f},{lat+0.06:.3f}:13,14,15,16\" --hq "
                            "-o media/maps/vectors.json` first."
                        )
                    break

        # 4. Camera dynamism check (reject flat/static maps)
        if dur >= 8.0 and kfs:
            if len(kfs) < 3:
                errors.append(
                    f"[{act_id}] duration {dur:.1f}s has only {len(kfs)} camera_keyframes; "
                    "use >= 3 3D cinema keyframes with zoom/bearing/pitch progression."
                )
            pitches = [
                float(kf.get("pitch", 0.0))
                if isinstance(kf, dict)
                else (float(kf[5]) if len(kf) > 5 else 0.0)
                for kf in kfs
            ]
            if max(pitches, default=0.0) < 4.0:
                warnings.append(
                    f"[{act_id}] peak camera pitch is {max(pitches, default=0.0):.1f} deg; "
                    "consider 10-35 deg 3D pitch on approach and corridor beats."
                )

        # 5. Polygon border-trace timing, flag-fill assets, and enumerated keys
        flags_dir = (repo_root / "assets" / "geo" / "flags") if repo_root else None
        for idx, layer in enumerate(layers):
            if str(layer.get("type") or "") != "polygon":
                continue
            for key, allowed in _POLYGON_ENUM_KEYS.items():
                if key in layer:
                    val = layer[key]
                    if isinstance(val, bool) or val not in allowed:
                        errors.append(
                            f"[{act_id}] layer #{idx} {key}={val!r} is not one of "
                            f"{sorted(str(v) for v in allowed)}."
                        )
            wave = layer.get("flag_wave")
            if wave is not None and not isinstance(wave, bool):
                wave_f = _as_finite_float(wave)
                if wave_f is None or not (0.0 <= wave_f <= 0.6):
                    errors.append(
                        f"[{act_id}] layer #{idx} flag_wave must be true/false or a shading "
                        f"amplitude between 0 and 0.6, got {wave!r}."
                    )
            for key, (lo, hi) in _POLYGON_NUMERIC_KEYS.items():
                if key not in layer:
                    continue
                val = _as_finite_float(layer[key])
                if val is None or val < lo or (hi is not None and val > hi):
                    bound = f"between {lo:g} and {hi:g}" if hi is not None else f">= {lo:g}"
                    errors.append(
                        f"[{act_id}] layer #{idx} {key} must be a number {bound}, "
                        f"got {layer[key]!r}."
                    )
            for key, (lo, hi) in _POLYGON_OPT_BOOL_FLOAT_KEYS.items():
                if key not in layer:
                    continue
                raw_val = layer[key]
                if isinstance(raw_val, bool):
                    continue
                val = _as_finite_float(raw_val)
                if val is None or val < lo or val > hi:
                    errors.append(
                        f"[{act_id}] layer #{idx} {key} must be true/false or between "
                        f"{lo:g} and {hi:g}, got {raw_val!r}."
                    )
            code = layer.get("flag_fill")
            if code:
                code_s = str(code).lower()
                if not _FLAG_CODE_RE.fullmatch(code_s):
                    errors.append(
                        f"[{act_id}] layer #{idx} flag_fill {code!r} is not a flag code "
                        "(lowercase letters, digits and hyphens, e.g. 'se' or 'gb-sct')."
                    )
                elif flags_dir is not None and not (flags_dir / f"{code_s}.svg").is_file():
                    errors.append(
                        f"[{act_id}] layer #{idx} flag_fill '{code_s}' has no "
                        f"assets/geo/flags/{code_s}.svg; the bake would fall back to the "
                        "colour fill."
                    )
            trace_s = 0.0
            if "border_trace_s" in layer and layer["border_trace_s"] is not None:
                parsed_trace = _as_finite_float(layer["border_trace_s"])
                if parsed_trace is None or parsed_trace < 0:
                    errors.append(
                        f"[{act_id}] layer #{idx} border_trace_s must be a number >= 0, "
                        f"got {layer['border_trace_s']!r}."
                    )
                else:
                    trace_s = parsed_trace
            delay_s = 0.0
            if "border_trace_delay_s" in layer and layer["border_trace_delay_s"] is not None:
                parsed_delay = _as_finite_float(layer["border_trace_delay_s"])
                if parsed_delay is None or parsed_delay < 0:
                    errors.append(
                        f"[{act_id}] layer #{idx} border_trace_delay_s must be a number >= 0, "
                        f"got {layer['border_trace_delay_s']!r}."
                    )
                else:
                    delay_s = parsed_delay
            if trace_s > 0:
                raw_start = 0.0 if layer.get("start_s") is None else layer.get("start_s")
                raw_end = dur if layer.get("end_s") is None else layer.get("end_s")
                start_s = _as_finite_float(raw_start)
                visible_end = _as_finite_float(raw_end)
                if start_s is None or visible_end is None:
                    errors.append(
                        f"[{act_id}] layer #{idx} start_s/end_s must be finite numbers."
                    )
                else:
                    trace_end = start_s + delay_s + trace_s
                    if dur > 0:
                        visible_end = min(visible_end, dur)
                    if trace_end > visible_end + 1e-6:
                        warnings.append(
                            f"[{act_id}] layer #{idx} border_trace ends at {trace_end:.2f}s, "
                            f"after the layer/act ends at {visible_end:.2f}s; the outline never "
                            "closes on screen."
                        )
                parts = _separately_traced_parts(_resolve_geom_ref(vectors, layer.get("geom_ref")))
                if parts > 1:
                    warnings.append(
                        f"[{act_id}] layer #{idx} border_trace_s runs over {parts} separate parts "
                        f"of {layer.get('geom_ref')!r}; each part traces its own outline from its "
                        "own start, so the border grows in fragments. Trace one country outline "
                        "(countries.<ISO>) or reveal multi-part regions with border_draw_s."
                    )

        # 6. 3D scene layers (cable_3d, model_3d, volume_3d)
        for idx, layer in enumerate(layers):
            ltype = str(layer.get("type") or "")
            if ltype == "cable_3d":
                coords = layer.get("coords")
                coords_ref = layer.get("coords_ref")
                if not coords_ref and (not isinstance(coords, list) or len(coords) < 2):
                    errors.append(
                        f"[{act_id}] layer #{idx} cable_3d requires coords (len >= 2) or "
                        "coords_ref."
                    )
                if "end_taper_m" in layer and layer["end_taper_m"] is not None:
                    et = _as_finite_float(layer["end_taper_m"])
                    if et is None or et < 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} cable_3d end_taper_m must be >= 0, "
                            f"got {layer['end_taper_m']!r}."
                        )
                if "min_screen_radius_px" in layer and layer["min_screen_radius_px"] is not None:
                    mr = _as_finite_float(layer["min_screen_radius_px"])
                    if mr is None or mr <= 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} cable_3d min_screen_radius_px must be > 0, "
                            f"got {layer['min_screen_radius_px']!r}."
                        )
            elif ltype == "model_3d":
                mtype = str(layer.get("model") or "")
                gltf_url = layer.get("gltf_url")
                if not gltf_url and mtype not in _THREE_D_MODELS:
                    errors.append(
                        f"[{act_id}] layer #{idx} model_3d has unknown model {mtype!r}; "
                        f"expected one of {sorted(_THREE_D_MODELS)} or gltf_url."
                    )
                if gltf_url:
                    g_raw = str(gltf_url).strip()
                    if not g_raw.startswith(("http://", "https://")):
                        g_rel = g_raw.lstrip("/")
                        candidates = []
                        if base_dir is not None:
                            candidates.append(base_dir / g_rel)
                            if g_rel.startswith("project_models/"):
                                candidates.append(
                                    base_dir / "models" / g_rel[len("project_models/"):]
                                )
                        if repo_root is not None:
                            candidates.append(repo_root / "assets" / "geo" / g_rel)
                            candidates.append(repo_root / "assets" / "geo" / "models" / g_rel)
                        if candidates and not any(c.is_file() for c in candidates):
                            errors.append(
                                f"[{act_id}] layer #{idx} model_3d gltf_url {gltf_url!r} "
                                "not found in project models/ or assets/geo/models/."
                            )
                coord = layer.get("coord")
                path = layer.get("path")
                has_coord = isinstance(coord, list) and len(coord) >= 2
                has_path = isinstance(path, list) and len(path) >= 2
                if not has_coord and not has_path:
                    errors.append(
                        f"[{act_id}] layer #{idx} model_3d requires coord [lng, lat] or path."
                    )
            elif ltype == "volume_3d":
                coord = layer.get("coord")
                if not (isinstance(coord, list) and len(coord) >= 2):
                    errors.append(
                        f"[{act_id}] layer #{idx} volume_3d requires coord [lng, lat]."
                    )
                for dim in ("width_m", "length_m", "height_m"):
                    dval = _as_finite_float(layer.get(dim))
                    if dval is None or dval <= 0:
                        errors.append(
                            f"[{act_id}] layer #{idx} volume_3d {dim} must be > 0, "
                            f"got {layer.get(dim)!r}."
                        )

        # 7. Preflight viewport edge-clipping, caption-band, and cable/substation clearance checks
        cam_points: list[tuple[float, list[float], float, float]] = []
        for kf in kfs:
            if isinstance(kf, dict):
                tk = float(kf.get("t", kf.get("t_s", 0.0)))
                ctr = kf.get("center") or [kf.get("lng", 0.0), kf.get("lat", 0.0)]
                zk = float(kf.get("zoom", 5.0))
                bk = float(kf.get("bearing", 0.0))
            elif len(kf) >= 4:
                tk, ctr, zk = float(kf[0]), [float(kf[1]), float(kf[2])], float(kf[3])
                bk = float(kf[4]) if len(kf) > 4 else 0.0
            else:
                continue
            cam_points.append((tk, [float(ctr[0]), float(ctr[1])], zk, bk))
        cam_points.sort(key=lambda item: item[0])

        substations = [
            layer.get("coord")
            for layer in layers
            if str(layer.get("type") or "") == "model_3d"
            and str(layer.get("model") or "") == "substation"
            and isinstance(layer.get("coord"), list)
            and len(layer["coord"]) >= 2
        ]
        for idx, layer in enumerate(layers):
            ltype = str(layer.get("type") or "")
            if (
                ltype in {"pin_label", "glow_label"}
                and cam_points
                and isinstance(layer.get("coord"), list)
                and len(layer["coord"]) >= 2
            ):
                t0 = float(layer.get("start_s", 0.0))
                t1 = float(layer.get("end_s", dur if dur > 0 else t0 + 1.0))
                t_mid = 0.5 * (t0 + t1)
                nearest_cam = min(cam_points, key=lambda item: abs(item[0] - t_mid))
                xp, yp = _approx_viewport_pct(
                    float(layer["coord"][0]),
                    float(layer["coord"][1]),
                    nearest_cam[1],
                    nearest_cam[2],
                    nearest_cam[3],
                    width,
                    height,
                    dx=float(layer.get("dx") or 0.0),
                    dy=float(layer.get("dy") or 0.0),
                )
                if -0.25 <= xp <= 1.25 and -0.25 <= yp <= 1.25:
                    if xp < 0.06 or xp > 0.94:
                        warnings.append(
                            f"[{act_id}] layer #{idx} ({ltype}) projected x={xp:.2f} nears "
                            "viewport side margin (<0.06 or >0.94); adjust dx or x_pct."
                        )
                    if height > width and 0.66 <= yp <= 0.84:
                        warnings.append(
                            f"[{act_id}] layer #{idx} ({ltype}) projected y={yp:.2f} enters "
                            "protected caption band [0.66, 0.84]."
                        )
            elif ltype == "cable_3d" and substations:
                raw_coords = (
                    _resolve_geom_ref(vectors, layer.get("coords_ref"))
                    or layer.get("coords")
                    or []
                )
                if isinstance(raw_coords, list) and len(raw_coords) >= 3:
                    for wi in range(1, len(raw_coords) - 1):
                        wp = raw_coords[wi]
                        if not isinstance(wp, list) or len(wp) < 2:
                            continue
                        for sc in substations:
                            dist_m = _haversine_m(
                                float(wp[0]), float(wp[1]), float(sc[0]), float(sc[1])
                            )
                            if dist_m < 250.0:
                                warnings.append(
                                    f"[{act_id}] layer #{idx} cable_3d intermediate waypoint "
                                    f"#{wi} passes within {dist_m:.0f}m of substation center; "
                                    "route clear of structure roof."
                                )
                                break

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _fmt_ass_time(sec: float) -> str:
    total_cs = max(0, round(sec * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_geo_ass_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\\", "\\\u2060").replace("{", r"\{").replace("}", r"\}")
    return cleaned.replace("\n", r"\N")


def _haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def _approx_viewport_pct(
    lng: float,
    lat: float,
    center: list[float],
    zoom: float,
    bearing_deg: float,
    width: int,
    height: int,
    *,
    dx: float = 0.0,
    dy: float = 0.0,
) -> tuple[float, float]:
    scale = 512.0 * (2.0**zoom)

    def _merc(lon_v: float, lat_v: float) -> tuple[float, float]:
        s = math.sin(math.radians(max(-85.0, min(85.0, lat_v))))
        mx = ((lon_v + 180.0) / 360.0) * scale
        my = (0.5 - math.log((1.0 + s) / (1.0 - s)) / (4.0 * math.pi)) * scale
        return mx, my

    px, py = _merc(lng, lat)
    cx, cy = _merc(center[0], center[1])
    vx, vy = px - cx, py - cy
    rad = math.radians(-bearing_deg)
    rx = vx * math.cos(rad) - vy * math.sin(rad)
    ry = vx * math.sin(rad) + vy * math.cos(rad)
    sx = width * 0.5 + rx + dx
    sy = height * 0.5 + ry + dy
    return sx / max(1, width), sy / max(1, height)


def _segments_from_words(words: list[dict[str, Any]], max_words: int = 8) -> list[dict[str, Any]]:
    if not words:
        return []
    out: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []
    group_limit = max(4, min(10, max_words * 2))
    for w in words:
        txt = str(w.get("text") or "").strip()
        if not txt:
            continue
        t0 = float(w.get("start_s", w.get("start", 0.0)))
        if bucket:
            prev_end = float(bucket[-1].get("end_s", bucket[-1].get("end", t0)))
            if t0 - prev_end >= 0.35 or len(bucket) >= group_limit:
                out.append(
                    {
                        "start": float(bucket[0].get("start_s", bucket[0].get("start", 0.0))),
                        "end": prev_end,
                        "text": " ".join(str(x.get("text") or "").strip() for x in bucket),
                    }
                )
                bucket = []
        bucket.append(w)
        if txt.endswith((".", "?", "!", ",")) and len(bucket) >= max(2, max_words):
            out.append(
                {
                    "start": float(bucket[0].get("start_s", bucket[0].get("start", 0.0))),
                    "end": float(w.get("end_s", w.get("end", t0 + 0.2))),
                    "text": " ".join(str(x.get("text") or "").strip() for x in bucket),
                }
            )
            bucket = []
    if bucket:
        out.append(
            {
                "start": float(bucket[0].get("start_s", bucket[0].get("start", 0.0))),
                "end": float(bucket[-1].get("end_s", bucket[-1].get("end", 0.0))),
                "text": " ".join(str(x.get("text") or "").strip() for x in bucket),
            }
        )
    return out


def build_geoverum_ass_captions(
    transcript_data: dict[str, Any] | list[dict[str, Any]],
    *,
    speed: float = 1.0,
    max_words: int = 4,
    font_size: int = 56,
    margin_v: int = 348,
    fade_in_ms: int = 130,
    fade_out_ms: int = 0,
    font_name: str = "Rubik",
) -> str:
    """Build locked Geoverum boxless bottom-band ASS subtitles from segments or words.

    Each caption group fades in over ``fade_in_ms`` and leaves over ``fade_out_ms``
    (default 0: a hard cut to the next group). Both are clamped to 0-200 ms.
    """
    if speed <= 0:
        raise ValueError("speed must be > 0")
    fade_in = max(0, min(200, int(fade_in_ms)))
    fade_out = max(0, min(200, int(fade_out_ms)))
    fade_tag = f"{{\\fad({fade_in},{fade_out})}}" if (fade_in or fade_out) else ""
    if isinstance(transcript_data, list):
        segments = transcript_data
    else:
        segments = list(transcript_data.get("segments") or [])
        if not segments and isinstance(transcript_data.get("words"), list):
            segments = _segments_from_words(list(transcript_data["words"]), max_words=max_words)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,&H90000000,&HA0000000,"
        f"-1,0,0,0,100,100,0,0,1,1.6,3.2,2,60,60,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for seg in segments:
        t0 = float(seg.get("start", seg.get("start_s", 0.0))) / speed
        t1 = float(seg.get("end", seg.get("end_s", t0 + 0.5))) / speed
        raw_text = " ".join(str(seg.get("text") or "").split())
        if not raw_text or t1 <= t0:
            continue
        words = raw_text.split()
        if len(words) <= max_words:
            chunks = [words]
        else:
            n_chunks = math.ceil(len(words) / max_words)
            base = len(words) // n_chunks
            rem = len(words) % n_chunks
            chunks = []
            pos = 0
            for ci in range(n_chunks):
                take = base + (1 if ci < rem else 0)
                chunks.append(words[pos : pos + take])
                pos += take
        total_chars = max(1, sum(len(" ".join(c)) for c in chunks))
        cur_t = t0
        for ci, chunk in enumerate(chunks):
            txt = " ".join(chunk)
            # Strip trailing comma/period mid-narration while preserving question marks
            if txt.endswith((",", ".")):
                txt = txt[:-1]
            dur_c = (t1 - t0) * (len(txt) / total_chars)
            end_t = t1 if ci == len(chunks) - 1 else min(t1, cur_t + max(0.18, dur_c))
            lines.append(
                f"Dialogue: 0,{_fmt_ass_time(cur_t)},{_fmt_ass_time(end_t)},"
                f"Default,,0,0,0,,{fade_tag}{_escape_geo_ass_text(txt)}"
            )
            cur_t = end_t
    return "\n".join(lines) + "\n"


@geo_app.command("validate-scene")
def geo_validate_scene_cmd(
    scene_file: Annotated[
        Path, typer.Option("--scene-file", help="Declarative map_scene.json specification.")
    ],
) -> None:
    """Validate map_scene.json against Geoverum craft, sharpness, and clutter guardrails."""
    root = find_repo_root()
    scene_path = scene_file.expanduser().resolve()
    spec = json.loads(scene_path.read_text(encoding="utf-8"))
    report = validate_map_scene(spec, repo_root=root, base_dir=scene_path.parent)
    typer.echo(json.dumps(report, indent=2))
    if not report["ok"]:
        raise typer.Exit(code=1)


@geo_app.command("build-captions")
def geo_build_captions_cmd(
    transcript_file: Annotated[
        Path, typer.Argument(help="Transcript JSON with `segments` or word-level `words`.")
    ],
    out_file: Annotated[
        Path, typer.Option("--out-file", "-o", help="Destination ASS subtitle path.")
    ],
    speed: Annotated[
        float, typer.Option("--speed", help="Audio playback speed multiplier (e.g. 1.3).")
    ] = 1.0,
    max_words: Annotated[
        int | None, typer.Option("--max-words", help="Maximum words per caption group.")
    ] = None,
    font_size: Annotated[
        int | None, typer.Option("--font-size", help="ASS font size on 1080x1920 canvas.")
    ] = None,
    margin_v: Annotated[
        int | None, typer.Option("--margin-v", help="Bottom safe margin in px.")
    ] = None,
    fade_in_ms: Annotated[
        int | None, typer.Option("--fade-in-ms", help="Caption fade-in in ms (0-200).")
    ] = None,
    fade_out_ms: Annotated[
        int | None,
        typer.Option("--fade-out-ms", help="Caption fade-out in ms (0 = hard cut out)."),
    ] = None,
    brand: Annotated[
        str | None,
        typer.Option("--brand", help="Brand profile ID to load caption defaults from."),
    ] = "geoverum",
) -> None:
    """Generate locked Geoverum boxless bottom-band ASS subtitles."""
    eff_max_words = 4
    eff_font_size = 56
    eff_margin_v = 348
    eff_fade_in = 130
    eff_fade_out = 0
    eff_font = "Rubik"
    if brand:
        try:
            policy_path = (
                find_repo_root() / "profiles" / "brands" / brand / "brand_style_policy.json"
            )
            if policy_path.is_file():
                pol = json.loads(policy_path.read_text(encoding="utf-8"))
                typo = ((pol.get("soft_priors") or {}).get("visual_tokens") or {}).get(
                    "typography"
                ) or {}
                eff_max_words = int(typo.get("max_words_per_caption_group", eff_max_words))
                eff_font_size = int(typo.get("caption_font_px_9x16", eff_font_size))
                eff_margin_v = int(typo.get("caption_margin_v_px_9x16", eff_margin_v))
                if typo.get("caption_fade_in_ms") is not None:
                    eff_fade_in = int(typo["caption_fade_in_ms"])
                if typo.get("caption_fade_out_ms") is not None:
                    eff_fade_out = int(typo["caption_fade_out_ms"])
                raw_fam = typo.get("caption_font_family")
                if isinstance(raw_fam, str) and raw_fam.strip():
                    eff_font = raw_fam.split(",")[0].strip().strip("'\"") or eff_font
        except FileNotFoundError:
            pass

    data = json.loads(transcript_file.expanduser().resolve().read_text(encoding="utf-8"))
    ass_text = build_geoverum_ass_captions(
        data,
        speed=speed,
        max_words=max_words if max_words is not None else eff_max_words,
        font_size=font_size if font_size is not None else eff_font_size,
        margin_v=margin_v if margin_v is not None else eff_margin_v,
        fade_in_ms=fade_in_ms if fade_in_ms is not None else eff_fade_in,
        fade_out_ms=fade_out_ms if fade_out_ms is not None else eff_fade_out,
        font_name=eff_font,
    )
    out = out_file.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ass_text, encoding="utf-8")
    typer.echo(json.dumps({"ok": True, "ass_path": str(out), "speed": speed}, indent=2))


_SFX_LAYER_MAP: dict[str, tuple[str, float]] = {
    "void_wipe": ("flash_swish.wav", -9.0),
    "crimson_x": ("stamp_impact.wav", -6.5),
    "pin_label": ("pin_drop.wav", -10.5),
    "curved_pointer_label": ("pop_soft.wav", -11.0),
    "dashed_distance": ("whoosh_fast.wav", -11.5),
    "curved_arc_arrow": ("whoosh_fast.wav", -11.5),
    "route": ("whoosh_deep.wav", -12.0),
    "cable_3d": ("whoosh_deep.wav", -12.0),
    "model_3d": ("sub_thud.wav", -10.0),
    "volume_3d": ("flash_swish.wav", -10.5),
    "radar_rings": ("radar_ping.wav", -13.0),
    "counter_odometer": ("counter_tick.wav", -11.0),
    "human_silhouette_row": ("pop_bright.wav", -11.0),
    "landmark_silhouette": ("sub_thud.wav", -9.5),
    "wind_streamlines": ("whoosh_fast.wav", -13.0),
    "flag_pin": ("pop_soft.wav", -11.5),
    "ghost_overlay": ("flash_swish.wav", -11.0),
}


def derive_sfx_events_from_scene(
    spec: dict[str, Any], *, min_gap_s: float = 0.35, max_events: int = 44
) -> list[dict[str, Any]]:
    """Derive 0ms-aligned kinetic SFX hits from declarative map_scene.json beats."""
    raw: list[tuple[float, int, str, float]] = []
    time_offset = 0.0
    for act in spec.get("acts") or []:
        dur = float(act.get("duration_s", 0.0))
        # Camera dive / fly moves -> subtle swoosh accent
        for kf in act.get("camera_keyframes") or []:
            if isinstance(kf, dict):
                curve = str(kf.get("curve") or "")
                tk = float(kf.get("t", kf.get("t_s", 0.0)))
                if curve == "snap_dive" and tk > 0.2:
                    raw.append((time_offset + max(0.0, tk - 0.55), 1, "swoosh_zoom.wav", -12.5))
                elif curve == "hyperbolic_fly" and tk > 0.2:
                    raw.append((time_offset + max(0.0, tk - 0.65), 1, "whoosh_deep.wav", -12.0))

        for layer in act.get("layers") or []:
            ltype = str(layer.get("type") or "")
            t0 = time_offset + float(layer.get("start_s", 0.0))
            if ltype in _SFX_LAYER_MAP:
                sfx_name, gain_db = _SFX_LAYER_MAP[ltype]
                prio = 3 if ltype in {"crimson_x", "void_wipe", "landmark_silhouette"} else 2
                raw.append((t0, prio, sfx_name, gain_db))
            elif ltype == "glow_label":
                if layer.get("count_to") is not None:
                    raw.append((t0, 3, "ding_glass.wav", -10.0))
                elif float(layer.get("font_px", 48)) >= 64:
                    raw.append((t0, 2, "pop_bright.wav", -11.5))
            elif ltype == "prohibition_pins":
                for pin in (layer.get("pins") or [])[:8]:
                    pt = time_offset + float(pin.get("pop_s", layer.get("start_s", 0.0)))
                    raw.append((pt, 2, "pop_bright.wav", -12.0))
                    sd = float(pin.get("slash_delay_s", 0.36))
                    raw.append((pt + sd, 2, "warning_pulse.wav", -13.0))
        time_offset += dur

    raw.sort(key=lambda item: (item[0], -item[1]))
    selected: list[dict[str, Any]] = []
    last_t = -10.0
    for t_ev, _prio, fname, gain_db in raw:
        if t_ev < 0.0 or t_ev - last_t < min_gap_s:
            continue
        selected.append({"t_s": round(t_ev, 3), "sfx": fname, "gain_db": gain_db})
        last_t = t_ev
        if len(selected) >= max_events:
            break
    return selected


def synthesize_documentary_bgm(
    duration_s: float, out_wav: Path, *, sample_rate: int = 48000, bpm: float = 92.0
) -> Path:
    """Synthesize a clean ambient cartographic-documentary BGM bed (48 kHz stereo PCM)."""
    n_samples = max(1, math.ceil(duration_s * sample_rate))
    # D minor documentary progression: Dm -> Bb -> F -> C (each 4 beats)
    chords = [
        (73.42, 146.83, 174.61, 220.00),  # Dm
        (58.27, 116.54, 174.61, 233.08),  # Bb
        (87.31, 130.81, 174.61, 220.00),  # F
        (65.41, 130.81, 164.81, 196.00),  # C
    ]
    beat_s = 60.0 / bpm
    bar_s = beat_s * 4.0
    buf = array.array("h", [0] * (n_samples * 2))
    two_pi = 2.0 * math.pi
    fade_in_n = int(min(1.5, duration_s * 0.1) * sample_rate)
    fade_out_n = int(min(2.0, duration_s * 0.15) * sample_rate)

    for i in range(n_samples):
        t = i / sample_rate
        bar_idx = int(t / bar_s) % len(chords)
        bar_pos = (t % bar_s) / bar_s
        beat_pos = (t % beat_s) / beat_s
        bass_f, f1, f2, f3 = chords[bar_idx]

        # Smooth chord crossfade envelope within bar
        chord_env = min(1.0, bar_pos * 8.0) * min(1.0, (1.0 - bar_pos) * 10.0 + 0.15)
        # Gentle documentary pulse on each beat
        pulse = 0.65 + 0.35 * math.exp(-beat_pos * 4.5)
        # Warm sub-bass + soft filtered triad pads
        sub = 0.28 * math.sin(two_pi * bass_f * t) * pulse
        pad_l = (
            0.14 * math.sin(two_pi * f1 * t)
            + 0.11 * math.sin(two_pi * f2 * t + 0.3)
            + 0.08 * math.sin(two_pi * f3 * t + 0.8)
            + 0.03 * math.sin(two_pi * f3 * 2.0 * t) * math.exp(-beat_pos * 7.0)
        ) * chord_env
        pad_r = (
            0.14 * math.sin(two_pi * f1 * t + 0.15)
            + 0.11 * math.sin(two_pi * f2 * t + 0.6)
            + 0.08 * math.sin(two_pi * f3 * t + 1.1)
            + 0.03 * math.sin(two_pi * f2 * 2.0 * t) * math.exp(-beat_pos * 7.0)
        ) * chord_env

        env = 1.0
        if i < fade_in_n:
            env *= i / max(1, fade_in_n)
        if i > n_samples - fade_out_n:
            env *= max(0.0, (n_samples - i) / max(1, fade_out_n))

        val_l = max(-0.92, min(0.92, (sub + pad_l) * env))
        val_r = max(-0.92, min(0.92, (sub + pad_r) * env))
        buf[i * 2] = int(val_l * 32767)
        buf[i * 2 + 1] = int(val_r * 32767)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(buf.tobytes())
    return out_wav


@geo_app.command("mix-audio")
def geo_mix_audio_cmd(
    scene_file: Annotated[
        Path, typer.Option("--scene-file", help="Declarative map_scene.json specification.")
    ],
    voice_file: Annotated[
        Path, typer.Option("--voice", help="Voiceover WAV/MP3 audio file (post-speedup).")
    ],
    out_file: Annotated[
        Path, typer.Option("--out-file", "-o", help="Destination mixed 48 kHz WAV file.")
    ],
    bgm_file: Annotated[
        Path | None,
        typer.Option("--bgm", help="Optional custom BGM track; synthesizes bed if omitted."),
    ] = None,
    bgm_gain_db: Annotated[
        float, typer.Option("--bgm-gain-db", help="Base BGM attenuation before sidechain ducking.")
    ] = -16.0,
    storyboard_file: Annotated[
        Path | None,
        typer.Option("--storyboard-file", help="Optional storyboard JSON for adaptive cues."),
    ] = None,
    loudness_profile: Annotated[
        str,
        typer.Option(
            "--loudness-profile",
            help=(
                "Target loudness profile: streaming_web, podcast_video, broadcast_ebu_r128, "
                "broadcast_atsc_a85, cinema_streaming_dialogue, cinema_trailer."
            ),
        ),
    ] = "streaming_web",
    narrative_fx: Annotated[
        bool,
        typer.Option(
            "--narrative-fx/--no-narrative-fx",
            help=(
                "Layer Shepard risers, tension drones, impacts, stingers, whooshes, "
                "and silence drop-outs."
            ),
        ),
    ] = True,
    room_tone: Annotated[
        bool,
        typer.Option(
            "--room-tone/--no-room-tone",
            help="Layer a subtle continuous room-tone floor under speech breaks.",
        ),
    ] = True,
    room_tone_db: Annotated[
        float,
        typer.Option("--room-tone-db", help="Level of synthesized room-tone floor in dBFS."),
    ] = -48.0,
) -> None:
    """Mix voiceover + ducked documentary BGM + scene-synced kinetic SFX with two-pass loudnorm."""
    root = find_repo_root()
    sfx_dir = root / "assets" / "audio" / "sfx"
    spec = json.loads(scene_file.expanduser().resolve().read_text(encoding="utf-8"))
    sb_data = (
        json.loads(storyboard_file.expanduser().resolve().read_text(encoding="utf-8"))
        if storyboard_file is not None
        else None
    )
    vo_path = voice_file.expanduser().resolve()
    out_path = out_file.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lp_key = loudness_profile.strip().lower()
    if lp_key not in LOUDNESS_PROFILES:
        raise typer.BadParameter(
            f"Unknown --loudness-profile {loudness_profile!r}; "
            f"expected one of: {', '.join(sorted(LOUDNESS_PROFILES))}"
        )
    prof = LOUDNESS_PROFILES[lp_key]
    target_i = prof.target_lufs
    target_tp = round(min(prof.max_true_peak_dbtp - 0.15, -1.05), 2)
    target_lra = prof.target_lra

    # Probe exact voiceover duration
    dur_proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vo_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    duration_s = float(dur_proc.stdout.strip())

    cues = (
        plan_narrative_audio_cues(spec, storyboard=sb_data)
        if narrative_fx
        else {
            "risers": [],
            "drones": [],
            "impacts": [],
            "stingers": [],
            "whooshes": [],
            "ambience": [],
            "silence_dropouts": [],
            "section_timeline": [],
            "cue_clustering_warnings": [],
        }
    )

    with tempfile.TemporaryDirectory(prefix="vedit_geo_mix_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        if bgm_file is not None:
            bgm_path = bgm_file.expanduser().resolve()
        else:
            bgm_path = tmp_path / "narrative_bgm.wav"
            synthesize_narrative_bgm(
                duration_s + 0.5,
                bgm_path,
                section_timeline=cues["section_timeline"] or None,
                silence_dropouts=cues["silence_dropouts"] or None,
            )

        events = [
            ev
            for ev in derive_sfx_events_from_scene(spec)
            if ev["t_s"] < duration_s - 0.15 and (sfx_dir / ev["sfx"]).is_file()
        ]
        extra_fx: list[dict[str, Any]] = []
        for idx, r_ev in enumerate(cues["risers"]):
            if r_ev["start_s"] + r_ev["duration_s"] <= duration_s:
                r_wav = tmp_path / f"riser_{idx}.wav"
                synthesize_shepard_riser(r_ev["duration_s"], r_wav)
                extra_fx.append(
                    {
                        "t_s": r_ev["start_s"],
                        "path": r_wav,
                        "gain_db": r_ev["gain_db"],
                        "pan": 0.0,
                    }
                )
        for idx, d_ev in enumerate(cues["drones"]):
            if d_ev["start_s"] < duration_s - 0.2:
                d_wav = tmp_path / f"drone_{idx}.wav"
                d_len = min(d_ev["duration_s"], duration_s - d_ev["start_s"])
                if d_ev.get("texture") == "granular":
                    synthesize_granular_pad(d_len, d_wav)
                else:
                    synthesize_tension_drone(d_len, d_wav)
                extra_fx.append(
                    {
                        "t_s": d_ev["start_s"],
                        "path": d_wav,
                        "gain_db": d_ev["gain_db"],
                        "pan": 0.0,
                    }
                )
        for idx, a_ev in enumerate(cues.get("ambience") or []):
            if a_ev["start_s"] < duration_s - 0.2:
                a_wav = tmp_path / f"amb_{idx}.wav"
                a_len = min(a_ev["duration_s"], duration_s - a_ev["start_s"])
                synthesize_ambience_layers(a_len, a_wav, level_db=-24.0)
                extra_fx.append(
                    {
                        "t_s": a_ev["start_s"],
                        "path": a_wav,
                        "gain_db": a_ev.get("gain_db", -20.0),
                        "pan": float(a_ev.get("pan") or 0.0),
                    }
                )
        for idx, imp_ev in enumerate(cues.get("impacts") or []):
            if imp_ev["start_s"] < duration_s - 0.2:
                i_wav = tmp_path / f"impact_{idx}.wav"
                synthesize_four_layer_impact(
                    i_wav,
                    character=str(imp_ev.get("character") or "verdict"),  # type: ignore[arg-type]
                )
                extra_fx.append(
                    {
                        "t_s": imp_ev["start_s"],
                        "path": i_wav,
                        "gain_db": imp_ev.get("gain_db", -13.0),
                        "pan": float(imp_ev.get("pan") or 0.0),
                    }
                )
        for idx, st_ev in enumerate(cues.get("stingers") or []):
            if st_ev["start_s"] < duration_s - 0.2:
                st_wav = tmp_path / f"stinger_{idx}.wav"
                synthesize_stinger(
                    st_wav,
                    style=str(st_ev.get("style") or "reveal"),  # type: ignore[arg-type]
                )
                extra_fx.append(
                    {
                        "t_s": st_ev["start_s"],
                        "path": st_wav,
                        "gain_db": st_ev.get("gain_db", -15.5),
                        "pan": 0.0,
                    }
                )
        for idx, wh_ev in enumerate(cues.get("whooshes") or []):
            if wh_ev["start_s"] < duration_s - 0.15:
                w_wav = tmp_path / f"whoosh_{idx}.wav"
                synthesize_whoosh(
                    float(wh_ev.get("duration_s") or 0.4),
                    w_wav,
                    direction=str(wh_ev.get("direction") or "in"),  # type: ignore[arg-type]
                )
                extra_fx.append(
                    {
                        "t_s": wh_ev["start_s"],
                        "path": w_wav,
                        "gain_db": wh_ev.get("gain_db", -15.0),
                        "pan": 0.0,
                    }
                )
        if room_tone:
            room_wav = tmp_path / "room_tone.wav"
            synthesize_room_tone_bed(duration_s, room_wav, level_db=room_tone_db)
            extra_fx.append(
                {
                    "t_s": 0.0,
                    "path": room_wav,
                    "gain_db": 0.0,
                    "pan": 0.0,
                }
            )

        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-i",
            str(vo_path),
            "-stream_loop",
            "-1",
            "-i",
            str(bgm_path),
        ]
        synth_transient_times = [
            float(fx["t_s"])
            for fx in extra_fx
            if Path(str(fx["path"])).stem.startswith(("impact_", "whoosh_", "stinger_"))
        ]
        all_sfx = [
            {"t_s": ev["t_s"], "path": sfx_dir / ev["sfx"], "gain_db": ev["gain_db"], "pan": 0.0}
            for ev in events
            if not any(abs(float(ev["t_s"]) - st) <= 0.18 for st in synth_transient_times)
        ] + extra_fx
        for ev in all_sfx:
            cmd.extend(["-i", str(ev["path"])])

        chains = [
            "[0:a]aresample=48000,aformat=channel_layouts=stereo,highpass=f=75,asplit=2[vo_dry][vo_sc_raw]",
            f"[vo_sc_raw]apad,atrim=0:{duration_s:.3f}[vo_sc]",
            f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{duration_s:.3f},"
            f"volume={bgm_gain_db:.1f}dB[bgm_raw]",
            build_psychoacoustic_bgm_chain("[bgm_raw]", "[vo_sc]", "[bgm_bus]", carve_strength=0.9),
        ]
        mix_inputs = ["[vo_dry]", "[bgm_bus]"]
        if all_sfx:
            sfx_tags: list[str] = []
            for idx, ev in enumerate(all_sfx):
                inp = idx + 2
                ms = round(ev["t_s"] * 1000)
                tag = f"[s{idx}]"
                pan_part = (
                    f",{pan_to_ffmpeg_filter(float(ev['pan']))}"
                    if abs(float(ev.get("pan") or 0.0)) > 0.01
                    else ""
                )
                chains.append(
                    f"[{inp}:a]aresample=48000,aformat=channel_layouts=stereo"
                    f"{pan_part},volume={ev['gain_db']:.1f}dB,adelay={ms}|{ms}{tag}"
                )
                sfx_tags.append(tag)
            if len(sfx_tags) == 1:
                mix_inputs.append(sfx_tags[0])
            else:
                chains.append(
                    f"{''.join(sfx_tags)}amix=inputs={len(sfx_tags)}:duration=longest:normalize=0[sfx_bus]"
                )
                mix_inputs.append("[sfx_bus]")

        chains.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:normalize=0,"
            f"apad,atrim=0:{duration_s:.3f}[mixed_a]"
        )
        pre_wav = tmp_path / "pre_norm.wav"
        cmd.extend(
            [
                "-filter_complex",
                ";".join(chains),
                "-map",
                "[mixed_a]",
                "-t",
                f"{duration_s:.3f}",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_f32le",
                str(pre_wav),
            ]
        )
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            err_tail = (proc.stderr or "").strip().splitlines()[-12:]
            raise RuntimeError(
                f"ffmpeg mix-audio failed (exit {proc.returncode}): " + " | ".join(err_tail)
            )

        # Two-pass linear loudnorm (Pass 1 measure -> Pass 2 linear scale + limiter).
        pass1 = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(pre_wav),
                "-af",
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        meas = _parse_loudnorm_json(pass1.stderr) if pass1.returncode == 0 else None
        can_two_pass = meas is not None and all(
            _is_finite_loudnorm_val(v)
            for v in (
                meas.input_i,
                meas.input_tp,
                meas.input_lra,
                meas.input_thresh,
                meas.target_offset,
            )
        )
        lim_db = prof.max_true_peak_dbtp
        af_pass2 = (
            (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
                f"measured_I={meas.input_i}:measured_TP={meas.input_tp}:"
                f"measured_LRA={meas.input_lra}:measured_thresh={meas.input_thresh}:"
                f"offset={meas.target_offset}:linear=true:print_format=summary,"
                f"alimiter=limit={lim_db:.1f}dB:level=disabled"
            )
            if can_two_pass and meas is not None
            else (
                f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra},"
                f"alimiter=limit={lim_db:.1f}dB:level=disabled"
            )
        )
        pass2 = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(pre_wav),
                "-af",
                af_pass2,
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if pass2.returncode != 0:
            err_tail = (pass2.stderr or "").strip().splitlines()[-12:]
            raise RuntimeError(
                f"ffmpeg mix-audio loudnorm pass 2 failed (exit {pass2.returncode}): "
                + " | ".join(err_tail)
            )

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "out_file": str(out_path),
                "duration_s": round(duration_s, 3),
                "sfx_count": len(events),
                "riser_count": len(cues["risers"]),
                "drone_count": len(cues["drones"]),
                "impact_count": len(cues.get("impacts") or []),
                "stinger_count": len(cues.get("stingers") or []),
                "whoosh_count": len(cues.get("whooshes") or []),
                "silence_dropouts": len(cues["silence_dropouts"]),
                "room_tone_enabled": room_tone,
                "cue_clustering_warnings": cues.get("cue_clustering_warnings") or [],
                "two_pass_loudnorm": can_two_pass,
                "loudness_profile": lp_key,
                "bgm_source": str(bgm_file) if bgm_file else "synthesized_narrative_bed",
            },
            indent=2,
        )
    )


@geo_app.command("bake-scene")
def geo_bake_scene_cmd(
    scene_file: Annotated[
        Path, typer.Option("--scene-file", help="Declarative map_scene.json specification.")
    ],
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Output directory for baked MP4 acts.")
    ],
    skip_validate: Annotated[
        bool,
        typer.Option("--skip-validate", help="Bypass preflight craft/sharpness validation."),
    ] = False,
    fill_tiles: Annotated[
        bool,
        typer.Option(
            "--fill-tiles",
            help="Before baking, run a tile coverage pass over every camera track and fetch "
            "tiles that would otherwise be upscaled from an ancestor, through the source each "
            "tile route serves (Sentinel-2 to z14, orthoimagery to z16); tiles no source covers "
            "are reported as coverage_unfillable.",
        ),
    ] = False,
    only_act: Annotated[
        list[str] | None,
        typer.Option("--only-act", help="Bake only specific act_id(s) (repeatable)."),
    ] = None,
    preview_keyframes: Annotated[
        int | None,
        typer.Option(
            "--preview-keyframes",
            help="Fast visual check: render N evenly sampled keyframe JPEGs + contact sheet.",
        ),
    ] = None,
) -> None:
    """Expand smooth camera plans and bake declarative world-space map scenes via MapLibre."""
    root = find_repo_root()
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("Node.js >= 22 is required to bake map scenes.")

    scene_path = scene_file.expanduser().resolve()
    spec = json.loads(scene_path.read_text(encoding="utf-8"))
    if not skip_validate:
        report = validate_map_scene(
            spec,
            repo_root=root,
            base_dir=scene_path.parent,
            check_hq_tiles=not fill_tiles,
        )
        if not report["ok"]:
            typer.echo(json.dumps(report, indent=2), err=True)
            raise typer.Exit(code=1)
    fps = float(spec.get("fps", 30.0))

    # Expand declarative `camera_plan` or `camera_keyframes` for smooth C2 cinema physics.
    from vedit.director.camera_moves import build_cinema_camera_track

    for act in spec.get("acts") or []:
        if "camera_plan" in act and "camera_samples" not in act:
            act["camera_samples"] = expand_move_plan(act["camera_plan"], fps=fps)
        elif "camera_keyframes" in act and "camera_samples" not in act:
            act["camera_samples"] = build_cinema_camera_track(
                act["camera_keyframes"],
                duration_s=float(act.get("duration_s", 1.0)),
                fps=fps,
                smooth_s=float(act.get("camera_smooth_s", 0.0)),
                shutter_windows=act.get("shutter_windows"),
                auto_shutter=bool(act.get("auto_shutter", False)),
                micro_drift=act.get("micro_drift"),
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="vedit_map_scene_", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(spec, tmp)
        expanded_path = Path(tmp.name)

    try:
        runner = root / "tools" / "geo-assets" / "render_map_scene.mjs"
        extra_args: list[str] = []
        for aid in only_act or []:
            extra_args.extend(["--only-act", aid])
        if preview_keyframes is not None and preview_keyframes > 0:
            extra_args.extend(["--preview-keyframes", str(preview_keyframes)])

        if fill_tiles:
            coverage_path = expanded_path.with_suffix(".coverage.json")
            try:
                cov = subprocess.run(
                    [
                        node_bin,
                        str(runner),
                        "--scene-file",
                        str(expanded_path),
                        "--base-dir",
                        str(scene_path.parent),
                        "--out-dir",
                        str(out_dir.expanduser().resolve()),
                        "--coverage-only",
                        "--coverage-out",
                        str(coverage_path),
                        *[a for aid in (only_act or []) for a in ("--only-act", aid)],
                    ],
                    check=False,
                )
                if cov.returncode != 0:
                    raise typer.Exit(code=cov.returncode)
                regular_gaps, hq_gaps = split_coverage_gaps(coverage_path)
            finally:
                coverage_path.unlink(missing_ok=True)
            typer.echo(json.dumps(fill_coverage_gaps(root, regular_gaps, hq_gaps)))
            if not skip_validate:
                post_report = validate_map_scene(
                    spec, repo_root=root, base_dir=scene_path.parent, check_hq_tiles=True
                )
                if not post_report["ok"]:
                    typer.echo(json.dumps(post_report, indent=2), err=True)
                    raise typer.Exit(code=1)
        proc = subprocess.run(
            [
                node_bin,
                str(runner),
                "--scene-file",
                str(expanded_path),
                "--base-dir",
                str(scene_path.parent),
                "--out-dir",
                str(out_dir.expanduser().resolve()),
                *extra_args,
            ],
            check=False,
        )
        if proc.returncode != 0:
            raise typer.Exit(code=proc.returncode)
    finally:
        expanded_path.unlink(missing_ok=True)


@geo_app.command("camera-track")
def geo_camera_track_cmd(
    track_file: Annotated[
        Path, typer.Argument(help="JSON list of `[t, lng, lat, zoom, bearing]` camera keys.")
    ],
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Write the denoised track here (omit to only measure)."),
    ] = None,
    window_s: Annotated[float, typer.Option(help="Gaussian smoothing window in seconds.")] = 0.6,
    cut: Annotated[
        list[float] | None, typer.Option("--cut", help="Hard-cut time in seconds (repeatable).")
    ] = None,
    anchor: Annotated[
        list[float] | None,
        typer.Option("--anchor", help="Key time kept exactly, e.g. a story-beat hold."),
    ] = None,
    max_shift_px: Annotated[float, typer.Option(help="Per-key centre correction cap.")] = 24.0,
    max_zoom_shift: Annotated[float, typer.Option(help="Per-key zoom correction cap.")] = 0.08,
    fps: Annotated[float, typer.Option(help="Sampling rate for the shake report.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
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


def _load_fetch_fonts_module(repo_root: Path) -> Any:
    import importlib.util

    script = repo_root / "tools" / "geo-assets" / "fetch_fonts.py"
    if not script.is_file():
        raise typer.BadParameter(f"Missing font catalog script: {script}")
    spec = importlib.util.spec_from_file_location("vedit_fetch_fonts", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load font catalog script: {script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@geo_app.command("list-fonts")
def geo_list_fonts_cmd(
    category: Annotated[
        list[str] | None,
        typer.Option(
            "--category",
            help="Filter by category (display, sans, serif, mono, handwriting). Repeatable.",
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON output (always JSON, for CLI parity).")
    ] = True,
) -> None:
    """List installed open-license font families and static/variable files in assets/geo/fonts/."""
    del as_json
    root = find_repo_root()
    mod = _load_fetch_fonts_module(root)
    payload = mod.list_installed_fonts(
        fonts_dir=root / "assets" / "geo" / "fonts",
        categories=category,
    )
    typer.echo(json.dumps(payload, indent=2))


@geo_app.command("fetch-fonts")
def geo_fetch_fonts_cmd(
    category: Annotated[
        list[str] | None,
        typer.Option(
            "--category",
            help="Filter by category (display, sans, serif, mono, handwriting). Repeatable.",
        ),
    ] = None,
    no_static: Annotated[
        bool,
        typer.Option("--no-static", help="Skip variable-to-static TTF derivation for libass."),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON output (always JSON, for CLI parity).")
    ] = True,
) -> None:
    """Download curated open-license fonts into assets/geo/fonts/ and build static weights."""
    del as_json
    import shutil
    import sys

    root = find_repo_root()
    script = root / "tools" / "geo-assets" / "fetch_fonts.py"
    if not script.is_file():
        raise typer.BadParameter(f"Missing font catalog script: {script}")

    args = [str(script), "--json"]
    for cat in category or []:
        args.extend(["--category", cat])
    if no_static:
        args.append("--no-static")

    has_fonttools = False
    try:
        import fontTools  # type: ignore[import-not-found] # noqa: F401

        has_fonttools = True
    except ImportError:
        has_fonttools = False

    uv_bin = shutil.which("uv")
    if not has_fonttools and not no_static and uv_bin:
        cmd = [uv_bin, "run", "--with", "fonttools", "python", *args]
    else:
        cmd = [sys.executable, *args]

    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise typer.Exit(code=proc.returncode)
