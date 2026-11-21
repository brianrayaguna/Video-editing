"""Map camera preset commands: list the library and expand move plans into keyframes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from vedit.cli._app import JsonOption
from vedit.director.camera_moves import (
    CameraMoveError,
    expand_move_plan,
    load_camera_presets,
    to_baker_keyframes,
    to_scene_keys,
)

camera_app = typer.Typer(help="Reusable map camera move presets for basemap bakes.")


@camera_app.command("list")
def camera_list(
    presets_file: Annotated[Path | None, typer.Option(help="Preset library JSON.")] = None,
    json_output: JsonOption = False,
) -> None:
    """List camera presets with their default duration, deltas, and pan mode."""
    presets = load_camera_presets(presets_file)
    rows = [
        {
            "preset_id": pid,
            "default_duration_s": p.get("default_duration_s"),
            "zoom_delta": p.get("zoom_delta", 0.0),
            "bearing_delta": p.get("bearing_delta", 0.0),
            "pan": p.get("pan", "hold"),
            "purpose": p.get("purpose", ""),
        }
        for pid, p in presets.items()
    ]
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
        return
    for r in rows:
        typer.echo(
            f"{r['preset_id']:<24} {r['default_duration_s']:>5}s  zoom {r['zoom_delta']:+.2f}  "
            f"bearing {r['bearing_delta']:+.1f}  pan={r['pan']}\n    {r['purpose']}"
        )


@camera_app.command("expand")
def camera_expand(
    plan_file: Annotated[Path, typer.Option(help="Move plan JSON (start state + chained moves).")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Keyframe JSON destination.")],
    fps: Annotated[float, typer.Option(help="Frames per second.")] = 30.0,
    fmt: Annotated[
        Literal["baker", "scene"],
        typer.Option(
            "--format",
            help="`baker`: baker KEYFRAMES_JSON; `scene`: [t,lng,lat,zoom,bearing] rows.",
        ),
    ] = "baker",
    presets_file: Annotated[Path | None, typer.Option(help="Preset library JSON.")] = None,
) -> None:
    """Expand a move plan into per-frame camera keyframes."""
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    try:
        samples = expand_move_plan(plan, fps=fps, presets=load_camera_presets(presets_file))
    except CameraMoveError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    payload = (
        to_baker_keyframes(samples, frame_offset=samples[0]["frame"])
        if fmt == "baker"
        else to_scene_keys(samples)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"output": str(output), "frames": len(samples), "format": fmt}))
