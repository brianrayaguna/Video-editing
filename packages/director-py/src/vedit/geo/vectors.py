"""GeoJSON vector extraction, simplification, meridian clipping, and bbox filtering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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

    if want_countries or want_continents:
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


