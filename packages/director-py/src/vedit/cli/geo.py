"""Geospatial asset preparation and declarative world-space map scene baking commands."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import time
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

geo_app = typer.Typer(
    help="Prepare offline AOI satellite tiles/GeoJSON vectors and bake declarative map scenes."
)


def _deg2num(lat: float, lon: float, z: int) -> tuple[int, int]:
    lat_rad = math.radians(max(min(lat, 85.0511), -85.0511))
    n = 2.0**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(int(n) - 1, x)), max(0, min(int(n) - 1, y))


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
) -> None:
    """Fetch project AOI satellite tiles (without dirtying MANIFEST.json) and extract GeoJSON."""
    root = find_repo_root()
    fetched_count = 0
    if bbox:
        coords: set[tuple[int, int, int]] = set()
        for spec in bbox:
            if ":" not in spec:
                raise typer.BadParameter(f"Invalid --bbox {spec!r}; expected 'W,S,E,N:Z'.")
            box_part, z_part = spec.rsplit(":", 1)
            w, s, e, n = (float(v) for v in box_part.split(","))
            for z_token in z_part.split(","):
                coords.update(_enum_bbox_tiles(w, s, e, n, int(z_token)))

        raw_dir = root / "assets" / "geo" / "raw" / "tiles_s2_2016"
        ordered = sorted(coords)

        def _download(item: tuple[int, tuple[int, int, int]]) -> bool:
            idx, (z, x, y) = item
            dest = raw_dir / str(z) / str(x) / f"{y}.jpg"
            if dest.is_file() and dest.stat().st_size >= 64:
                return True
            dest.parent.mkdir(parents=True, exist_ok=True)
            sub = ("a", "b", "c", "d")[idx % 4]
            url = f"https://{sub}.tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
            tmp = dest.with_suffix(".jpg.part")
            for attempt in range(4):
                proc = subprocess.run(
                    [
                        "curl",
                        "-sS",
                        "-L",
                        "--fail",
                        "--connect-timeout",
                        "5",
                        "--max-time",
                        "12",
                        "-o",
                        str(tmp),
                        url,
                    ],
                    capture_output=True,
                    check=False,
                )
                if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size >= 64:
                    tmp.replace(dest)
                    return True
                time.sleep(0.3 * (attempt + 1))
            return False

        with ThreadPoolExecutor(max_workers=16) as pool:
            fetched_count = sum(1 for ok in pool.map(_download, enumerate(ordered)) if ok)

        if grade_tiles:
            node_bin = shutil.which("node")
            if not node_bin:
                raise RuntimeError(
                    "Node.js >= 22 is required to run tools/geo-assets/build_tiles.mjs."
                )
            subprocess.run(
                [node_bin, str(root / "tools" / "geo-assets" / "build_tiles.mjs")],
                check=True,
            )

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
                "vectors_path": str(out_file),
                "countries": sorted(vectors["countries"].keys()),
                "continents": sorted(vectors["continents"].keys()),
                "provinces": [p["name"] for p in vectors["provinces"]],
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
) -> None:
    """Expand smooth camera plans and bake declarative world-space map scenes via MapLibre."""
    root = find_repo_root()
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("Node.js >= 22 is required to bake map scenes.")

    scene_path = scene_file.expanduser().resolve()
    spec = json.loads(scene_path.read_text(encoding="utf-8"))
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
                smooth_s=float(act.get("camera_smooth_s", 0.09)),
                shutter_windows=act.get("shutter_windows"),
                auto_shutter=bool(act.get("auto_shutter", True)),
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
