"""Storyboard commands: automatic directing, idiom checks, journey compilation, and critique."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from vedit.director.brand_memory import export_recent_episodes, load_brand_memory
from vedit.director.critique import apply_surgical_fixes, build_critique_packet, gate_review
from vedit.director.exemplar_retrieval import (
    load_editorial_playbook,
    playbook_path,
    retrieve_directing_context,
)
from vedit.director.journey import compile_journey
from vedit.director.script_readiness import audit_script_readiness
from vedit.director.semantic_director import (
    DirectingTier,
    critique_storyboard_prerender,
    enrich_storyboard_semantically,
)
from vedit.director.storyboard import (
    apply_director_storyboard,
    check_storyboard,
    idioms_path,
    load_directing_idioms,
    scaffold_storyboard,
)
from vedit.providers.registry import build_default_registry

storyboard_app = typer.Typer(
    help="Typed storyboards: auto-direct from a transcript, merge director input, check idioms."
)
critique_app = typer.Typer(
    help="Critique loop: deterministic checks, grid contact sheets, rubric review gate."
)


def _read(path: Path) -> Any:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.expanduser().parent.mkdir(parents=True, exist_ok=True)
    path.expanduser().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _idioms(
    brand: str | None, idioms_file: Path | None, storyboard: dict[str, Any] | None = None
) -> dict[str, Any]:
    if idioms_file is not None:
        return load_directing_idioms(idioms_file.expanduser())
    brand_id = brand or (storyboard or {}).get("brand_id")
    if not brand_id:
        raise typer.BadParameter("Pass --brand or --idioms-file.")
    return load_directing_idioms(idioms_path(brand_id))


BrandOpt = Annotated[
    str | None, typer.Option("--brand", help="Brand id (loads its directing idioms).")
]
IdiomsOpt = Annotated[
    Path | None, typer.Option("--idioms-file", help="Explicit directing idioms JSON.")
]


@storyboard_app.command("readiness")
def storyboard_readiness_cmd(
    transcript_file: Annotated[Path, typer.Argument(help="NormalizedTranscript JSON.")],
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
    pacing: Annotated[str, typer.Option(help="calm, default, or dense.")] = "default",
    max_dry_streak: Annotated[
        int, typer.Option("--max-dry-streak", min=2, help="Max consecutive fallback clauses.")
    ] = 3,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with code 1 when script is not ready.")
    ] = False,
) -> None:
    """Audit a transcript for visualizability and breath-pause readiness before VO lock."""
    idioms = _idioms(brand, idioms_file)
    report = audit_script_readiness(
        _read(transcript_file),
        idioms,
        pacing=pacing,
        max_dry_streak=max_dry_streak,
    )
    typer.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if strict and not report.ready:
        raise typer.Exit(code=1)


@storyboard_app.command("context")
def storyboard_context_cmd(
    storyboard_file: Annotated[Path, typer.Argument(help="Storyboard JSON.")],
    brand: BrandOpt = None,
    playbook_file: Annotated[
        Path | None, typer.Option("--playbook-file", help="Explicit editorial_playbook.json.")
    ] = None,
    memory_file: Annotated[
        Path | None, typer.Option("--memory-file", help="Optional external brand_memory.json.")
    ] = None,
    top_k: Annotated[int, typer.Option("--top-k", min=1, help="Hints per beat.")] = 2,
    top_k_triggers: Annotated[
        int, typer.Option("--top-k-triggers", min=1, help="Global triggers to return.")
    ] = 5,
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Sidecar directing context JSON to write.")
    ] = None,
) -> None:
    """Retrieve advisory playbook exemplars, triggers, and memory warnings for a storyboard."""
    sb = _read(storyboard_file)
    brand_id = brand or sb.get("brand_id")
    if not brand_id and playbook_file is None:
        raise typer.BadParameter("Pass --brand or --playbook-file.")
    pb_path = playbook_file.expanduser() if playbook_file else playbook_path(str(brand_id))
    playbook = load_editorial_playbook(pb_path)
    memory = _read(memory_file) if memory_file is not None else None
    ctx = retrieve_directing_context(
        sb,
        playbook,
        memory=memory,
        top_k_per_beat=top_k,
        top_k_triggers=top_k_triggers,
    ).to_dict()
    if out is not None:
        _write(out, ctx)
    typer.echo(json.dumps(ctx, indent=2, ensure_ascii=False))


@storyboard_app.command("auto")
def storyboard_auto_cmd(
    transcript_file: Annotated[Path, typer.Argument(help="NormalizedTranscript JSON.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Storyboard JSON to write.")],
    project_id: Annotated[
        str, typer.Option("--project-id", help="Project id recorded in the storyboard.")
    ],
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
    pacing: Annotated[str, typer.Option(help="calm, default, or dense.")] = "default",
    reference: Annotated[
        bool,
        typer.Option("--reference", help="Start a reference annotation instead of a film plan."),
    ] = False,
    director_file: Annotated[
        Path | None,
        typer.Option(
            "--director-file", help="Partial director storyboard merged over the automatic one."
        ),
    ] = None,
    tier: Annotated[
        DirectingTier,
        typer.Option("--tier", help="Directing tier: draft, standard, or flagship."),
    ] = "draft",
    use_decision: Annotated[
        bool,
        typer.Option("--use-decision", help="Enable DecisionPort semantic enrichment."),
    ] = False,
    playbook_file: Annotated[
        Path | None,
        typer.Option("--playbook-file", help="Optional editorial_playbook.json for retrieval."),
    ] = None,
    memory_file: Annotated[
        Path | None,
        typer.Option("--memory-file", help="Optional external brand_memory.json."),
    ] = None,
) -> None:
    """Direct automatically from narration, then layer optional director input on top.

    With `--reference`, the result is the starting point for annotating a reference video:
    replace each beat's device, onset, callouts and camera with what the reference shows.
    """
    idioms = _idioms(brand, idioms_file)
    sb = scaffold_storyboard(_read(transcript_file), idioms, project_id=project_id, pacing=pacing)
    memory = load_brand_memory(memory_file) if memory_file is not None else None
    if memory is not None:
        recent = export_recent_episodes(memory)
        if recent:
            sb["recent_episodes"] = recent
    if director_file is not None:
        sb = apply_director_storyboard(sb, _read(director_file))
    if reference:
        sb["directing_source"] = "reference"
    elif tier != "draft" and use_decision:
        brand_id = brand or idioms.get("brand_id")
        pb_path = playbook_file.expanduser() if playbook_file else playbook_path(str(brand_id))
        ctx = None
        if pb_path.is_file():
            ctx = retrieve_directing_context(sb, load_editorial_playbook(pb_path), memory=memory)
        decision_port = build_default_registry().resolve("decision")
        sb = enrich_storyboard_semantically(
            sb,
            idioms,
            decision_port=decision_port,
            context=ctx,
            tier=tier,
        ).storyboard
    _write(out, sb)
    report = check_storyboard(sb, idioms).to_dict()
    typer.echo(
        json.dumps(
            {
                "out": str(out),
                "beats": len(sb["beats"]),
                "shape": sb["story"]["shape"],
                "tier": tier,
                "score": report["score"],
                "passed": report["passed"],
            },
            indent=2,
        )
    )


@storyboard_app.command("gate-prerender")
def storyboard_gate_prerender_cmd(
    storyboard_file: Annotated[Path, typer.Argument(help="Storyboard JSON.")],
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
    tier: Annotated[
        DirectingTier, typer.Option("--tier", help="Critique tier: draft, standard, or flagship.")
    ] = "standard",
    min_score: Annotated[float, typer.Option("--min-score", help="Fail below score.")] = 75.0,
    use_decision: Annotated[
        bool, typer.Option("--use-decision", help="Enable DecisionPort semantic gate scoring.")
    ] = False,
    candidates_file: Annotated[
        Path | None,
        typer.Option("--candidates-file", help="Optional JSON array of candidate hook dicts."),
    ] = None,
) -> None:
    """Run Gate 1 pre-render deterministic and optional semantic storyboard critique."""
    sb = _read(storyboard_file)
    idioms = _idioms(brand, idioms_file, sb)
    brand_id = brand or sb.get("brand_id")
    ctx = None
    if brand_id:
        pb_path = playbook_path(str(brand_id))
        if pb_path.is_file():
            ctx = retrieve_directing_context(sb, load_editorial_playbook(pb_path))
    decision_port = build_default_registry().resolve("decision") if use_decision else None
    candidates = _read(candidates_file) if candidates_file is not None else None
    result = critique_storyboard_prerender(
        sb,
        idioms,
        decision_port=decision_port,
        context=ctx,
        tier=tier,
        candidate_hooks=candidates,
        min_score=min_score,
    ).to_dict()
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["passed"]:
        raise typer.Exit(code=1)


@storyboard_app.command("check")
def storyboard_check_cmd(
    storyboard_file: Annotated[Path, typer.Argument(help="Storyboard JSON.")],
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
    min_score: Annotated[float, typer.Option(help="Fail below this score.")] = 70.0,
) -> None:
    """Check a storyboard against the brand's executable directing idioms."""
    sb = _read(storyboard_file)
    report = check_storyboard(sb, _idioms(brand, idioms_file, sb)).to_dict()
    report["min_score"] = min_score
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["passed"] or report["score"] < min_score:
        raise typer.Exit(code=1)


@storyboard_app.command("journey")
def storyboard_journey_cmd(
    storyboard_file: Annotated[
        Path, typer.Argument(help="Storyboard JSON with `route` and beat heads.")
    ],
    out: Annotated[Path, typer.Option("--out", "-o", help="Journey keys JSON to write.")],
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
    cut: Annotated[
        list[float] | None, typer.Option("--cut", help="Hard-cut time (repeatable).")
    ] = None,
    resolved_storyboard: Annotated[
        Path | None,
        typer.Option(
            "--resolved-storyboard", help="Also write the storyboard with callout positions."
        ),
    ] = None,
) -> None:
    """Compile route head, camera, route width and callout positions from a journey storyboard."""
    sb = _read(storyboard_file)
    idioms = _idioms(brand, idioms_file, sb)
    result = compile_journey(sb, idioms, cuts=list(cut or []))
    _write(out, {k: v for k, v in result.items() if k != "storyboard"})
    if resolved_storyboard is not None:
        _write(resolved_storyboard, result["storyboard"])
    report = check_storyboard(result["storyboard"], idioms).to_dict()
    typer.echo(
        json.dumps(
            {
                "out": str(out),
                "camera_keys": len(result["camera_keys"]),
                "head_keys": len(result["head_keys"]),
                "score": report["score"],
                "passed": report["passed"],
            },
            indent=2,
        )
    )


@critique_app.command("packet")
def critique_packet_cmd(
    out: Annotated[Path, typer.Option("--out", "-o", help="Critique packet JSON to write.")],
    storyboard_file: Annotated[
        Path | None, typer.Option("--storyboard", help="Storyboard JSON.")
    ] = None,
    camera_track: Annotated[
        Path | None, typer.Option("--camera-track", help="[t,lng,lat,zoom,bearing] JSON.")
    ] = None,
    video: Annotated[
        Path | None, typer.Option("--video", help="Preview or master to sample.")
    ] = None,
    sheets_dir: Annotated[
        Path | None, typer.Option("--sheets-dir", help="Where contact sheets go.")
    ] = None,
    cut: Annotated[
        list[float] | None, typer.Option("--cut", help="Hard-cut time (repeatable).")
    ] = None,
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
    audio_events: Annotated[
        Path | None, typer.Option("--audio-events", help="JSON list of audio event timestamps (s).")
    ] = None,
    motion_energy: Annotated[
        Path | None,
        typer.Option("--motion-energy", help="JSON list of [t_s, energy] pairs."),
    ] = None,
    previous_packet: Annotated[
        Path | None,
        typer.Option("--previous-packet", help="Prior critique packet for frozen beats."),
    ] = None,
    iteration: Annotated[int, typer.Option("--iteration", min=1)] = 1,
    max_iterations: Annotated[int, typer.Option("--max-iterations", min=1)] = 3,
) -> None:
    """Run deterministic checks, render grid contact sheets, and emit the rubric review form."""
    sb = _read(storyboard_file) if storyboard_file else None
    idioms = _idioms(brand, idioms_file, sb)
    if video is not None and sheets_dir is None:
        sheets_dir = out.expanduser().parent / "critique_sheets"
    raw_energy = _read(motion_energy) if motion_energy else None
    energy_series = (
        [(float(pair[0]), float(pair[1])) for pair in raw_energy]
        if raw_energy is not None
        else None
    )
    packet = build_critique_packet(
        idioms=idioms,
        storyboard=sb,
        camera_track=_read(camera_track) if camera_track else None,
        cuts=list(cut or []),
        video=video.expanduser() if video else None,
        sheets_dir=sheets_dir.expanduser() if sheets_dir else None,
        audio_events_s=_read(audio_events) if audio_events else None,
        motion_energy_series=energy_series,
        previous_packet=_read(previous_packet) if previous_packet else None,
        iteration=iteration,
        max_iterations=max_iterations,
    )
    _write(out, packet)
    typer.echo(
        json.dumps(
            {
                "out": str(out),
                "sheets": [s["path"] for s in packet["sheets"]],
                "deterministic": packet["deterministic"],
                "frozen_beat_ids": packet["frozen_beat_ids"],
                "iteration": packet["iteration"],
                "max_iterations": packet["max_iterations"],
            },
            indent=2,
        )
    )


@critique_app.command("apply-fixes")
def critique_apply_fixes_cmd(
    storyboard_file: Annotated[Path, typer.Argument(help="Storyboard JSON to repair.")],
    packet_file: Annotated[Path, typer.Argument(help="Critique packet with `review.fixes`.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Repaired storyboard JSON path.")],
    brand: BrandOpt = None,
    idioms_file: IdiomsOpt = None,
) -> None:
    """Apply typed surgical critique fixes onto unfrozen beats with regression rollback."""
    sb = _read(storyboard_file)
    packet = _read(packet_file)
    idioms = _idioms(brand, idioms_file, sb)
    result = apply_surgical_fixes(sb, packet, idioms)
    _write(out, result["storyboard"])
    typer.echo(
        json.dumps(
            {
                "out": str(out),
                "applied": result["applied"],
                "deferred": result["deferred"],
                "skipped_frozen": result["skipped_frozen"],
                "rolled_back": result["rolled_back"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@critique_app.command("gate")
def critique_gate_cmd(
    packet_file: Annotated[
        Path, typer.Argument(help="Critique packet with `review.scores` filled.")
    ],
    threshold: Annotated[float, typer.Option(help="Minimum weighted rubric score.")] = 0.8,
) -> None:
    """Decide pass/fail from a filled critique packet; exit 1 lists what to fix."""
    result = gate_review(_read(packet_file), threshold=threshold)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["passed"]:
        raise typer.Exit(code=1)
