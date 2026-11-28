"""Offline geospatial tile coordinates, coverage-gap filling, and AOI preparation."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import typer

from vedit.contracts import find_repo_root
from vedit.geo.vectors import extract_project_vectors
from vedit.geo_imagery import (
    GOOGLE_TILES_MAX_Z,
    NATIONAL_ORTHO_MAX_Z,
    NATIONAL_ORTHO_MIN_Z,
    S2_CLOUDLESS_MAX_NATIVE_Z,
    GoogleMapTilesClient,
    format_credit_line,
    google_satellite_tile_url,
    national_ortho_url,
    record_imagery_attribution,
    resolve_imagery_provider,
    s2_cloudless_url,
    tiles_to_bbox,
)


def _deg2num(lat: float, lon: float, z: int) -> tuple[int, int]:
    lat_rad = math.radians(max(min(lat, 85.0511), -85.0511))
    n = 2.0**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(int(n) - 1, x)), max(0, min(int(n) - 1, y))


# Satellite imagery sources used by `geo prepare`:
# - Google Map Tiles API (2D satellite, up to z18) when `GOOGLE_MAPS_API_KEY` is configured.
# - National orthoimagery: public domain (U.S. Geological Survey, The National Map, ~1 m, z13-16).
# - Sentinel-2 cloudless 2024: CC BY 4.0 (EOX IT Services GmbH; modified Copernicus Sentinel data
#   2024, ~10 m native, z0-14).
_TILE_ABSENT_HTTP_CODES = frozenset({"204", "400", "404"})


def _s2_cloudless_url(z: int, x: int, y: int, subdomain: str = "a") -> str:
    return s2_cloudless_url(z, x, y, subdomain)


def _national_ortho_url(z: int, x: int, y: int) -> str:
    return national_ortho_url(z, x, y)


def hq_tile_urls(
    z: int,
    x: int,
    y: int,
    subdomain: str = "a",
    *,
    google_session: str | None = None,
    google_api_key: str | None = None,
) -> list[str]:
    """Return high-resolution tile URLs for `(z, x, y)` in fallback order."""
    urls: list[str] = []
    if google_session and google_api_key and 0 <= z <= GOOGLE_TILES_MAX_Z:
        urls.append(
            google_satellite_tile_url(
                z, x, y, session_token=google_session, api_key=google_api_key
            )
        )
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
    provider: str = "auto",
) -> tuple[int, int]:
    """Fetch satellite tiles: z<=12 from Sentinel-2 2024 (graded), z>=13 high-resolution.

    When `provider` resolves to `google` (auto when `GOOGLE_MAPS_API_KEY` is configured),
    high-resolution tiles use the Google Map Tiles API (2D satellite up to z18) with
    automatic fallback to USGS National Map and Sentinel-2 cloudless 2024, and record
    official copyright attribution in `assets/geo/tiles_hq/attribution.json`.
    """
    fetched_count = 0
    hq_fetched_count = 0
    raw_dir = root / "assets" / "geo" / "raw" / "tiles_s2_2016"
    hq_dir = root / "assets" / "geo" / "tiles_hq"
    resolved_provider, google_api_key = resolve_imagery_provider(provider, repo_root=root)
    if hq_aerial is True or (hq_aerial is None and resolved_provider == "google"):
        s2_coords = []
        hq_coords = sorted(coords)
    elif hq_aerial is False:
        s2_coords = sorted(coords)
        hq_coords = []
    else:
        s2_coords = sorted(c for c in coords if c[0] <= 12)
        hq_coords = sorted(c for c in coords if c[0] >= 13)

    google_session: str | None = None
    google_client: GoogleMapTilesClient | None = None
    if hq_coords and resolved_provider == "google" and google_api_key:
        try:
            google_client = GoogleMapTilesClient(google_api_key)
            google_session = google_client.create_session(map_type="satellite")
        except Exception as exc:
            if provider.strip().lower() == "google":
                raise RuntimeError(
                    "Google Map Tiles API session failed (verify Map Tiles API & Billing are "
                    f"enabled in Google Cloud Console): {exc}"
                ) from exc
            google_client = None
            google_session = None

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
        return any(
            _fetch_url(dest, url)
            for url in hq_tile_urls(
                z,
                x,
                y,
                sub,
                google_session=google_session,
                google_api_key=google_api_key,
            )
        )

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
        if hq_fetched_count > 0:
            active_sources: list[str] = []
            google_copyright: str | None = None
            if google_client and google_session:
                active_sources.append("google_map_tiles")
                bbox_val = tiles_to_bbox(set(hq_coords))
                if bbox_val is not None:
                    max_z = max(c[0] for c in hq_coords)
                    google_copyright = google_client.fetch_viewport_copyright(bbox_val, max_z)
            else:
                active_sources.append("usgs_national_map")
            if s2_coords or not google_client:
                active_sources.append("eox_s2_2024")
            record_imagery_attribution(
                hq_dir, sources=active_sources, google_copyright=google_copyright
            )

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




def prepare_geo_project(
    out_file: Path,
    *,
    bbox: list[str] | None = None,
    country: list[str] | None = None,
    continent: list[str] | None = None,
    province: list[str] | None = None,
    province_lat_min: float | None = None,
    province_lon_max: float | None = None,
    grade_tiles: bool = True,
    hq_aerial: bool | None = None,
    provider: str = "auto",
    tile_list: Path | None = None,
    repo_root: Path | None = None,
    fetch_fn: Callable[..., tuple[int, int]] | None = None,
    extract_vectors_fn: Callable[..., dict[str, Any]] | None = None,
) -> None:
    """Fetch project AOI satellite tiles and extract GeoJSON vectors."""
    root = repo_root or find_repo_root()
    _fetch = fetch_fn or _fetch_tile_set
    _extract = extract_vectors_fn or extract_project_vectors
    fetched_count = 0
    hq_fetched_count = 0
    if bbox or tile_list:
        bbox_coords: set[tuple[int, int, int]] = set()
        for spec in bbox or []:
            if ":" not in spec:
                raise typer.BadParameter(f"Invalid --bbox {spec!r}; expected 'W,S,E,N:Z'.")
            box_part, z_part = spec.rsplit(":", 1)
            coords_parts = box_part.split(",")
            if len(coords_parts) != 4:
                raise typer.BadParameter(f"Invalid --bbox {spec!r}; expected 4 W,S,E,N floats.")
            try:
                w, s, e, n = (float(v) for v in coords_parts)
                z_vals = [int(z_token) for z_token in z_part.split(",")]
            except ValueError as exc:
                raise typer.BadParameter(
                    f"Invalid --bbox numeric value in {spec!r}: {exc}"
                ) from exc
            for z_val in z_vals:
                if not 0 <= z_val <= 22:
                    raise typer.BadParameter(
                        f"Invalid --bbox zoom {z_val} in {spec!r}; expected 0..22."
                    )
                bbox_coords.update(_enum_bbox_tiles(w, s, e, n, z_val))
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
        merged_coords = bbox_coords | hq_tile_coords
        defer_grade = bool(
            grade_tiles
            and regular_fetch
            and merged_coords
            and any(c[0] <= S2_CLOUDLESS_MAX_NATIVE_Z for c in merged_coords)
        )
        if regular_fetch:
            s2_more, _ = _fetch(
                root,
                regular_fetch,
                hq_aerial=False,
                grade_tiles=(grade_tiles and not defer_grade),
            )
            fetched_count += s2_more
        if merged_coords:
            extra_kwargs: dict[str, Any] = {}
            if provider != "auto":
                extra_kwargs["provider"] = provider
            s2_more, hq_more = _fetch(
                root,
                merged_coords,
                hq_aerial=hq_aerial,
                grade_tiles=grade_tiles,
                **extra_kwargs,
            )
            fetched_count += s2_more
            hq_fetched_count += hq_more

    resolved_provider, _ = resolve_imagery_provider(provider, repo_root=root)
    attr_path = root / "assets" / "geo" / "tiles_hq" / "attribution.json"
    imagery_credit = format_credit_line(["eox_s2_2024"])
    if attr_path.is_file():
        try:
            attr_data = json.loads(attr_path.read_text(encoding="utf-8"))
            if isinstance(attr_data.get("credit_line"), str) and attr_data["credit_line"].strip():
                imagery_credit = attr_data["credit_line"].strip()
        except (OSError, ValueError):
            pass

    vectors = _extract(
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
                "imagery_provider": resolved_provider,
                "imagery_credit": imagery_credit,
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
