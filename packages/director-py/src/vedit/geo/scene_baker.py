"""Declarative map scene expansion, coverage preflight, and MapLibre baking orchestration."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from vedit.contracts import find_repo_root
from vedit.director.camera_moves import expand_move_plan
from vedit.geo.scene_validator import validate_map_scene
from vedit.geo.tiles import fill_coverage_gaps, split_coverage_gaps


def bake_geo_scene(
    scene_file: Path,
    out_dir: Path,
    *,
    skip_validate: bool = False,
    fill_tiles: bool = False,
    only_act: list[str] | None = None,
    preview_keyframes: int | None = None,
    repo_root: Path | None = None,
    which_fn: Callable[[str], str | None] | None = None,
    run_fn: Callable[..., Any] | None = None,
    fill_gaps_fn: Callable[..., dict[str, Any]] | None = None,
) -> None:
    """Expand smooth camera plans and bake declarative world-space map scenes via MapLibre."""
    root = repo_root or find_repo_root()
    _which = which_fn or shutil.which
    _run = run_fn or subprocess.run
    _fill_gaps = fill_gaps_fn or fill_coverage_gaps
    node_bin = _which("node")
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
                cov = _run(
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
            typer.echo(json.dumps(_fill_gaps(root, regular_gaps, hq_gaps)))
            if not skip_validate:
                post_report = validate_map_scene(
                    spec, repo_root=root, base_dir=scene_path.parent, check_hq_tiles=True
                )
                if not post_report["ok"]:
                    typer.echo(json.dumps(post_report, indent=2), err=True)
                    raise typer.Exit(code=1)
        proc = _run(
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



def load_fetch_fonts_module(repo_root: Path) -> Any:
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


def fetch_geo_fonts(*, category: list[str] | None = None, no_static: bool = False) -> None:
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
    cmd = (
        [uv_bin, "run", "--with", "fonttools", "python", *args]
        if (not has_fonttools and not no_static and uv_bin)
        else [sys.executable, *args]
    )
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise typer.Exit(code=proc.returncode)
