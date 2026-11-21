"""Media probing, forensic breakdown, and brand profiling commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import typer

from vedit.analyzers.brand_analyzer import (
    ExemplarRole,
    ReferenceVideoSample,
    query_exemplars,
    synthesize_brand_artifacts,
)
from vedit.analyzers.media_probe import ProbeOptions, hash_media, probe_media
from vedit.cli._app import JsonOption
from vedit.contracts import (
    find_repo_root,
    validate_all_brand_trees,
    validate_brand_tree,
)
from vedit.models import (
    EditorialPlaybook,
    MediaProbeResult,
    NormalizedTranscript,
    VideoBreakdownResult,
)
from vedit.ports.video_breakdown import BreakdownOptions
from vedit.providers.registry import build_default_registry

probe_app = typer.Typer(help="Fast deterministic media hashing, shot & CIELAB analysis.")
breakdown_app = typer.Typer(
    help="Forensic shot, transition, audio, OCR packaging breakdown and visual review."
)
brand_app = typer.Typer(
    help="Synthesize brand policy/playbook, validate brand trees, query exemplars."
)


@probe_app.command("hash")
def probe_hash_cmd(
    media_file: Path,
    json_output: JsonOption = True,
) -> None:
    """Compute SHA-256 content hash for a media file."""
    res = hash_media(media_file)
    if json_output:
        typer.echo(json.dumps(res, indent=2))
    else:
        typer.echo(f"{res['sha256']}  {res['file_bytes']} bytes")


@probe_app.command("analyze")
def probe_analyze_cmd(
    media_file: Path,
    extract_keyframes: Annotated[
        Path | None,
        typer.Option("--extract-keyframes", help="Directory to write shot midpoint JPEG frames."),
    ] = None,
    true_peak: Annotated[
        bool,
        typer.Option("--true-peak", help="Include oversampled true-peak loudness measurement."),
    ] = False,
    json_output: JsonOption = True,
) -> None:
    """Run deterministic single-pass ffprobe + FFmpeg + Rust CIELAB analysis."""
    opts = ProbeOptions(true_peak=true_peak, extract_keyframes_dir=extract_keyframes)
    result = probe_media(media_file, opts)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(
            f"{result.video.width}x{result.video.height}@{result.video.fps}fps | "
            f"{result.shot_stats.count} shots (p50={result.shot_stats.asl_p50_s}s) | "
            f"LUFS={result.audio.integrated_lufs}"
        )


@breakdown_app.command("survey")
def breakdown_survey_cmd(
    media_file: Annotated[Path, typer.Argument(help="Reference video file to survey.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", "-o", help="Breakdown output directory.")],
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override VideoBreakdownPort provider.")
    ] = None,
) -> None:
    """Run one step of the visual-first contact-sheet survey pass."""
    registry = build_default_registry()
    engine = registry.resolve("video_breakdown", provider_name=provider)
    step = engine.survey(media_file, out_dir)
    typer.echo(json.dumps(asdict(step), indent=2, default=str))


@breakdown_app.command("analyze")
def breakdown_analyze_cmd(
    media_file: Annotated[Path, typer.Argument(help="Reference video file to analyze.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", "-o", help="Breakdown output directory.")],
    prepare_review: Annotated[
        bool,
        typer.Option(
            "--prepare-review/--no-prepare-review",
            help="Generate review_tasks.json and review_answers.json for visual review.",
        ),
    ] = True,
    ocr: Annotated[
        bool, typer.Option("--ocr/--no-ocr", help="Enable local OCR caption/text extraction.")
    ] = True,
    stems: Annotated[
        bool, typer.Option("--stems/--no-stems", help="Enable local vocal/music stem separation.")
    ] = True,
    packaging: Annotated[
        bool,
        typer.Option(
            "--packaging/--no-packaging",
            help="Extract subtitle lanes, styled text, and stickers.",
        ),
    ] = True,
    asr: Annotated[bool, typer.Option("--asr/--no-asr", help="Enable optional local ASR.")] = False,
    use_vlm: Annotated[
        bool,
        typer.Option(
            "--vlm/--no-vlm",
            help="Use external VLM API (disabled by default; prefer interactive visual review).",
        ),
    ] = False,
    lang: Annotated[Literal["en", "zh"], typer.Option("--lang")] = "en",
    ocr_lang: Annotated[str | None, typer.Option("--ocr-lang")] = None,
    env_file: Annotated[Path | None, typer.Option("--env-file")] = None,
    workers: Annotated[int, typer.Option("--workers")] = 3,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override VideoBreakdownPort provider.")
    ] = None,
) -> None:
    """Run forensic video breakdown and emit VIDEO.md + normalized video_breakdown.json."""
    registry = build_default_registry()
    engine = registry.resolve("video_breakdown", provider_name=provider)
    result = engine.analyze(
        media_file,
        out_dir,
        BreakdownOptions(
            use_vlm=use_vlm,
            prepare_review=prepare_review,
            ocr=ocr,
            stems=stems,
            packaging=packaging,
            asr=asr,
            lang=lang,
            ocr_lang=ocr_lang,
            env_file=env_file,
            workers=workers,
        ),
    )
    out_resolved = out_dir.expanduser().resolve()
    summary_payload = {
        "provider": result.provider,
        "output_dir": result.output_dir,
        "video_breakdown_path": str(out_resolved / "video_breakdown.json"),
        "videomd_path": result.videomd_path,
        "storyboard_path": result.storyboard_path,
        "review_tasks_path": (
            str(out_resolved / "review_tasks.json")
            if (out_resolved / "review_tasks.json").is_file()
            else None
        ),
        "review_answers_path": (
            str(out_resolved / "review_answers.json")
            if (out_resolved / "review_answers.json").is_file()
            else None
        ),
        "shots": len(result.shots),
        "low_confidence_shots": sum(1 for s in result.shots if s.low_confidence_flag),
        "confidence": result.confidence,
        "reviewed_by": result.reviewed_by,
        "generative_reference_warning": result.generative_reference_warning,
        "verdict": result.verdict,
    }
    typer.echo(json.dumps(summary_payload, indent=2))


@breakdown_app.command("review")
def breakdown_review_cmd(
    out_dir: Annotated[Path, typer.Argument(help="Breakdown output directory.")],
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing review_answers.json.")
    ] = False,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Prepare review_tasks.json and review_answers.json for visual verification."""
    registry = build_default_registry()
    engine = registry.resolve("video_breakdown", provider_name=provider)
    bundle = engine.prepare_review(out_dir, force=force)
    typer.echo(json.dumps(asdict(bundle), indent=2, default=str))


@breakdown_app.command("apply-review")
def breakdown_apply_review_cmd(
    out_dir: Annotated[Path, typer.Argument(help="Breakdown output directory.")],
    by: Annotated[
        str, typer.Option("--by", help="Reviewer identifier recorded in provenance.")
    ] = "ai-directing-client",
    lang: Annotated[Literal["en", "zh"], typer.Option("--lang")] = "en",
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Fuse visual review answers back into breakdown.json, VIDEO.md, and video_breakdown.json."""
    registry = build_default_registry()
    engine = registry.resolve("video_breakdown", provider_name=provider)
    result = engine.apply_review(out_dir, reviewer=by, lang=lang)
    typer.echo(json.dumps(result.model_dump(exclude_none=True), indent=2))


@breakdown_app.command("import")
def breakdown_import_cmd(
    path: Annotated[
        Path,
        typer.Argument(help="Existing breakdown output directory or breakdown.json file."),
    ],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Normalized video_breakdown.json path.")
    ] = None,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Normalize an existing forensic breakdown directory into VideoBreakdownResult JSON."""
    registry = build_default_registry()
    engine = registry.resolve("video_breakdown", provider_name=provider)
    result = engine.load_breakdown(path)
    payload = result.model_dump(exclude_none=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2))


def _match_breakdown_for_probe(
    probe: MediaProbeResult,
    probe_path: Path,
    probe_index: int,
    loaded_breakdowns: list[tuple[Path, VideoBreakdownResult]],
    used_indices: set[int],
) -> VideoBreakdownResult | None:
    """Match a VideoBreakdownResult to a probe by SHA-256, stem, or positional order."""
    probe_stem = probe_path.stem.lower()
    source_stem = Path(probe.path).stem.lower()
    for idx, (_path, bd) in enumerate(loaded_breakdowns):
        if idx in used_indices:
            continue
        if bd.source_sha256 and (
            probe.sha256.startswith(bd.source_sha256) or bd.source_sha256.startswith(probe.sha256)
        ):
            used_indices.add(idx)
            return bd
    for idx, (bd_path, bd) in enumerate(loaded_breakdowns):
        if idx in used_indices:
            continue
        bd_stems = {bd_path.stem.lower(), bd_path.name.lower(), Path(bd.source_path).stem.lower()}
        if probe_stem in bd_stems or source_stem in bd_stems:
            used_indices.add(idx)
            return bd
    if probe_index < len(loaded_breakdowns) and probe_index not in used_indices:
        used_indices.add(probe_index)
        return loaded_breakdowns[probe_index][1]
    return None


def _match_transcript_for_probe(
    probe: MediaProbeResult,
    probe_path: Path,
    probe_index: int,
    loaded_transcripts: list[tuple[Path, NormalizedTranscript]],
    used_indices: set[int],
) -> NormalizedTranscript | None:
    """Match a NormalizedTranscript to a probe by source_hash, stem, or positional order."""
    probe_stem = probe_path.stem.lower()
    for idx, (_path, tr) in enumerate(loaded_transcripts):
        if idx in used_indices:
            continue
        if tr.source_hash and (
            probe.sha256.startswith(tr.source_hash) or tr.source_hash.startswith(probe.sha256)
        ):
            used_indices.add(idx)
            return tr
    for idx, (tr_path, tr) in enumerate(loaded_transcripts):
        if idx in used_indices:
            continue
        if tr_path.stem.lower() == probe_stem:
            used_indices.add(idx)
            return tr
    if probe_index < len(loaded_transcripts) and probe_index not in used_indices:
        used_indices.add(probe_index)
        return loaded_transcripts[probe_index][1]
    return None


@brand_app.command("analyze")
def brand_analyze_cmd(
    brand_id: Annotated[str, typer.Option("--brand-id", help="Target brand policy identifier.")],
    probe_files: Annotated[
        list[Path], typer.Option("--probe-file", help="MediaProbeResult JSON path(s).")
    ],
    breakdown_files: Annotated[
        list[Path] | None,
        typer.Option(
            "--breakdown-file",
            help="Optional VideoBreakdownResult JSON file(s) or breakdown output directory(ies).",
        ),
    ] = None,
    transcript_files: Annotated[
        list[Path] | None,
        typer.Option("--transcript-file", help="Optional NormalizedTranscript JSON path(s)."),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Runtime BrandStylePolicy JSON path.")
    ] = None,
    playbook_out: Annotated[
        Path | None,
        typer.Option("--playbook-out", help="Advisory EditorialPlaybook JSON path."),
    ] = None,
    use_decision: Annotated[
        bool, typer.Option("--use-decision", help="Enrich with configured DecisionPort.")
    ] = False,
) -> None:
    """Synthesize runtime BrandStylePolicy and advisory EditorialPlaybook from probes."""
    loaded_breakdowns: list[tuple[Path, VideoBreakdownResult]] = []
    if breakdown_files:
        breakdown_engine = build_default_registry().resolve("video_breakdown")
        for b_path in breakdown_files:
            loaded_breakdowns.append((b_path, breakdown_engine.load_breakdown(b_path)))

    loaded_transcripts: list[tuple[Path, NormalizedTranscript]] = []
    for t_path in transcript_files or []:
        loaded_transcripts.append(
            (t_path, NormalizedTranscript.model_validate_json(t_path.read_text(encoding="utf-8")))
        )

    used_bd: set[int] = set()
    used_tr: set[int] = set()
    samples: list[ReferenceVideoSample] = []
    for idx, p_path in enumerate(probe_files):
        probe = MediaProbeResult.model_validate_json(p_path.read_text(encoding="utf-8"))
        matched_bd = _match_breakdown_for_probe(probe, p_path, idx, loaded_breakdowns, used_bd)
        matched_tr = _match_transcript_for_probe(probe, p_path, idx, loaded_transcripts, used_tr)
        samples.append(
            ReferenceVideoSample(
                source_video_id=p_path.stem,
                probe=probe,
                transcript=matched_tr,
                breakdown=matched_bd,
            )
        )

    decision_port = build_default_registry().resolve("decision") if use_decision else None
    synthesized = synthesize_brand_artifacts(brand_id, samples, decision_port=decision_port)
    policy_payload = synthesized.policy.model_dump(exclude_none=True)
    playbook_payload = synthesized.playbook.model_dump(exclude_none=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(policy_payload, indent=2) + "\n", encoding="utf-8")
    if playbook_out is not None:
        playbook_out.parent.mkdir(parents=True, exist_ok=True)
        playbook_out.write_text(json.dumps(playbook_payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"policy": policy_payload, "playbook": playbook_payload}, indent=2))


@brand_app.command("validate")
def brand_validate_cmd(
    brand_dir: Annotated[
        Path | None,
        typer.Option("--brand-dir", help="Brand directory under profiles/brands/<id>."),
    ] = None,
    json_output: JsonOption = False,
    repo_root: Annotated[Path | None, typer.Option("--repo-root", hidden=True)] = None,
) -> None:
    """Validate one brand tree or all trees under profiles/brands/."""
    root = repo_root or find_repo_root()
    if brand_dir is not None:
        results = [validate_brand_tree(brand_dir, repo_root=root)]
    else:
        results = validate_all_brand_trees(repo_root=root)
    payload = {"ok": True, "brands": results}
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        for entry in results:
            typer.echo(
                f"{entry['brand_id']}: policy={entry['policy']} "
                f"playbook={entry['playbook']} templates={entry['templates']}"
            )


@brand_app.command("exemplars")
def brand_exemplars_cmd(
    playbook_file: Annotated[Path, typer.Argument(help="Path to editorial_playbook.json.")],
    role: Annotated[ExemplarRole | None, typer.Option("--role")] = None,
    min_duration_s: Annotated[float | None, typer.Option("--min-duration-s")] = None,
    max_duration_s: Annotated[float | None, typer.Option("--max-duration-s")] = None,
) -> None:
    """Query matching exemplars from an EditorialPlaybook exemplar_bank."""
    playbook = EditorialPlaybook.model_validate_json(playbook_file.read_text(encoding="utf-8"))
    items = query_exemplars(
        playbook,
        role=role,
        min_duration_s=min_duration_s,
        max_duration_s=max_duration_s,
    )
    typer.echo(json.dumps([item.model_dump(exclude_none=True) for item in items], indent=2))
