"""Geospatial asset preparation and declarative world-space map scene baking commands."""

from __future__ import annotations

import array
import json
import math
import shutil
import subprocess
import tempfile
import time
import wave
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
            help="Fetch high-resolution aerial ortho tiles into assets/geo/tiles_hq/ "
            "(default: auto-enabled for z >= 13).",
        ),
    ] = None,
) -> None:
    """Fetch project AOI satellite tiles (without dirtying MANIFEST.json) and extract GeoJSON."""
    root = find_repo_root()
    fetched_count = 0
    hq_fetched_count = 0
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
        hq_dir = root / "assets" / "geo" / "tiles_hq"
        s2_coords = sorted(c for c in coords if c[0] <= 12)
        if hq_aerial is True:
            hq_coords = sorted(coords)
        elif hq_aerial is False:
            hq_coords = []
            s2_coords = sorted(coords)
        else:
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

        def _download_s2(item: tuple[int, tuple[int, int, int]]) -> bool:
            idx, (z, x, y) = item
            dest = raw_dir / str(z) / str(x) / f"{y}.jpg"
            sub = ("a", "b", "c", "d")[idx % 4]
            url = f"https://{sub}.tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
            return _fetch_url(dest, url)

        def _download_hq(item: tuple[int, tuple[int, int, int]]) -> bool:
            _idx, (z, x, y) = item
            dest = hq_dir / str(z) / str(x) / f"{y}.jpg"
            url = (
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                f"World_Imagery/MapServer/tile/{z}/{y}/{x}"
            )
            return _fetch_url(dest, url)

        if s2_coords:
            with ThreadPoolExecutor(max_workers=16) as pool:
                fetched_count = sum(1 for ok in pool.map(_download_s2, enumerate(s2_coords)) if ok)

        if hq_coords:
            with ThreadPoolExecutor(max_workers=16) as pool:
                hq_fetched_count = sum(
                    1 for ok in pool.map(_download_hq, enumerate(hq_coords)) if ok
                )

        if grade_tiles and s2_coords:
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


def validate_map_scene(
    spec: dict[str, Any], *, repo_root: Path | None = None
) -> dict[str, Any]:
    """Validate declarative map_scene.json against Geoverum craft and sharpness guardrails."""
    errors: list[str] = []
    warnings: list[str] = []
    width = int(spec.get("width", 1080))
    height = int(spec.get("height", 1920))
    min_font_px = 36 if height >= 1600 else 28
    hq_dir = (repo_root / "assets" / "geo" / "tiles_hq") if repo_root else None

    for act in spec.get("acts") or []:
        act_id = str(act.get("act_id") or "unknown")
        if act.get("type", "map") != "map":
            continue
        dur = float(act.get("duration_s", 0.0))
        tile_source = str(act.get("tile_source") or "hybrid")
        layers = list(act.get("layers") or [])

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
        if closeup_centers and hq_dir is not None:
            for lng, lat, z in closeup_centers:
                check_z = min(16, max(13, round(z)))
                has_hq = False
                for probe_z in range(check_z, 12, -1):
                    tx, ty = _deg2num(lat, lng, probe_z)
                    if (hq_dir / str(probe_z) / str(tx) / f"{ty}.jpg").is_file():
                        has_hq = True
                        break
                if not has_hq:
                    errors.append(
                        f"[{act_id}] close-up at [{lng:.4f}, {lat:.4f}] z={z:.1f} has no "
                        "high-resolution aerial tiles in assets/geo/tiles_hq/. Run "
                        f"`vedit geo prepare --bbox \"{lng-0.06:.3f},{lat-0.06:.3f},"
                        f"{lng+0.06:.3f},{lat+0.06:.3f}:13,14,15,16\" --hq` first."
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

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _fmt_ass_time(sec: float) -> str:
    s = max(0.0, sec)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    rem = s % 60
    return f"{h}:{m:02d}:{rem:05.2f}"


def build_geoverum_ass_captions(
    transcript_data: dict[str, Any] | list[dict[str, Any]],
    *,
    speed: float = 1.0,
    max_words: int = 4,
    font_size: int = 56,
    margin_v: int = 348,
) -> str:
    """Build locked Geoverum boxless bottom-band Rubik ASS subtitles from transcript segments."""
    if speed <= 0:
        raise ValueError("speed must be > 0")
    segments = (
        transcript_data
        if isinstance(transcript_data, list)
        else list(transcript_data.get("segments") or [])
    )
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
        f"Style: Default,Rubik,{font_size},&H00FFFFFF,&H0000FFFF,&H90000000,&HA0000000,"
        f"-1,0,0,0,100,100,0,0,1,1.6,3.2,2,60,60,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for seg in segments:
        t0 = float(seg.get("start", 0.0)) / speed
        t1 = float(seg.get("end", t0 + 0.5)) / speed
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
                f"Default,,0,0,0,,{{\\fad(80,80)}}{txt}"
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
    spec = json.loads(scene_file.expanduser().resolve().read_text(encoding="utf-8"))
    report = validate_map_scene(spec, repo_root=root)
    typer.echo(json.dumps(report, indent=2))
    if not report["ok"]:
        raise typer.Exit(code=1)


@geo_app.command("build-captions")
def geo_build_captions_cmd(
    transcript_file: Annotated[
        Path, typer.Argument(help="Transcript JSON with `segments: [{start, end, text}]`.")
    ],
    out_file: Annotated[
        Path, typer.Option("--out-file", "-o", help="Destination ASS subtitle path.")
    ],
    speed: Annotated[
        float, typer.Option("--speed", help="Audio playback speed multiplier (e.g. 1.3).")
    ] = 1.0,
    max_words: Annotated[
        int, typer.Option("--max-words", help="Maximum words per caption group.")
    ] = 4,
    font_size: Annotated[
        int, typer.Option("--font-size", help="ASS font size on 1080x1920 canvas.")
    ] = 56,
    margin_v: Annotated[
        int, typer.Option("--margin-v", help="Bottom safe margin in px (default 348 -> y~80%).")
    ] = 348,
) -> None:
    """Generate locked Geoverum boxless bottom-band Rubik ASS subtitles."""
    data = json.loads(transcript_file.expanduser().resolve().read_text(encoding="utf-8"))
    ass_text = build_geoverum_ass_captions(
        data, speed=speed, max_words=max_words, font_size=font_size, margin_v=margin_v
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
) -> None:
    """Mix voiceover + ducked documentary BGM + scene-synced kinetic SFX to -14 LUFS."""
    root = find_repo_root()
    sfx_dir = root / "assets" / "audio" / "sfx"
    spec = json.loads(scene_file.expanduser().resolve().read_text(encoding="utf-8"))
    vo_path = voice_file.expanduser().resolve()
    out_path = out_file.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

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

    tmp_bgm: Path | None = None
    if bgm_file is not None:
        bgm_path = bgm_file.expanduser().resolve()
    else:
        tmp_bgm = out_path.with_suffix(".bgm_bed.wav")
        bgm_path = synthesize_documentary_bgm(duration_s + 0.5, tmp_bgm)

    events = [
        ev
        for ev in derive_sfx_events_from_scene(spec)
        if ev["t_s"] < duration_s - 0.15 and (sfx_dir / ev["sfx"]).is_file()
    ]

    cmd: list[str] = ["ffmpeg", "-y", "-i", str(vo_path), "-stream_loop", "-1", "-i", str(bgm_path)]
    for ev in events:
        cmd.extend(["-i", str(sfx_dir / ev["sfx"])])

    chains = [
        "[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[vo_dry][vo_sc]",
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{duration_s:.3f},"
        f"volume={bgm_gain_db:.1f}dB,equalizer=f=2200:t=o:w=1.2:g=-4.5[bgm_eq]",
        "[bgm_eq][vo_sc]sidechaincompress=threshold=0.025:ratio=6:attack=20:release=260:makeup=1[bgm_bus]",
    ]
    mix_inputs = ["[vo_dry]", "[bgm_bus]"]
    if events:
        sfx_tags: list[str] = []
        for idx, ev in enumerate(events):
            inp = idx + 2
            ms = round(ev["t_s"] * 1000)
            tag = f"[s{idx}]"
            chains.append(
                f"[{inp}:a]aresample=48000,aformat=channel_layouts=stereo,"
                f"volume={ev['gain_db']:.1f}dB,adelay={ms}|{ms}{tag}"
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
        "loudnorm=I=-14.0:TP=-1.5:LRA=7[out_a]"
    )
    cmd.extend(
        [
            "-filter_complex",
            ";".join(chains),
            "-map",
            "[out_a]",
            "-t",
            f"{duration_s:.3f}",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ]
    )
    try:
        proc = subprocess.run(
            cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        )
        if proc.returncode != 0:
            err_tail = (proc.stderr or "").strip().splitlines()[-12:]
            raise RuntimeError(
                f"ffmpeg mix-audio failed (exit {proc.returncode}): " + " | ".join(err_tail)
            )
    finally:
        if tmp_bgm is not None:
            tmp_bgm.unlink(missing_ok=True)

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "out_file": str(out_path),
                "duration_s": round(duration_s, 3),
                "sfx_count": len(events),
                "bgm_source": str(bgm_file) if bgm_file else "synthesized_ambient_bed",
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
) -> None:
    """Expand smooth camera plans and bake declarative world-space map scenes via MapLibre."""
    root = find_repo_root()
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("Node.js >= 22 is required to bake map scenes.")

    scene_path = scene_file.expanduser().resolve()
    spec = json.loads(scene_path.read_text(encoding="utf-8"))
    if not skip_validate:
        report = validate_map_scene(spec, repo_root=root)
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
