"""Provider-agnostic CLI (`vedit`) for automated pipelines and AI directing clients."""

from __future__ import annotations

import getpass
import json
import os
import sys
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
from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import (
    find_repo_root,
    load_brand_template_catalog,
    load_platform_targets,
    load_schema,
    validate_all_brand_trees,
    validate_brand_tree,
)
from vedit.director.planner import build_edit_plan
from vedit.director.verifier import verify_edit_plan
from vedit.interop.otio_bridge import export_edit_plan_to_otio
from vedit.mastering.ffmpeg_master import assemble_hybrid_deliverable
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    EditorialPlaybook,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    PlatformTarget,
    VideoBreakdownResult,
)
from vedit.ports.audio_catalog import AudioKind, VocalPolicy
from vedit.ports.decision import DecisionQuestion, ImageInput
from vedit.ports.transcription import TranscriptionOptions
from vedit.ports.video_breakdown import BreakdownOptions
from vedit.project_workspace import (
    find_project_root,
    init_project_workspace,
    inspect_project_status,
    resolve_plan_asset_paths,
    validate_project_workspace,
)
from vedit.providers.config import load_providers_config
from vedit.providers.env import upsert_env_var
from vedit.providers.registry import build_default_registry
from vedit.providers.veed_oauth import has_openedit_oauth_login, resolve_openedit_token_path

app = typer.Typer(
    name="vedit",
    help="Capability-first video directing, brand policy, and Modal cloud-render CLI.",
    no_args_is_help=True,
)
contracts_app = typer.Typer(help="Validate JSON Schemas and platform mastering presets.")
project_app = typer.Typer(help="Initialize, inspect, and validate external editing projects.")
providers_app = typer.Typer(help="Inspect and configure capability providers.")
platforms_app = typer.Typer(help="List validated platform mastering targets.")
probe_app = typer.Typer(help="Fast deterministic media hashing, shot & CIELAB analysis.")
breakdown_app = typer.Typer(
    help="Forensic shot, transition, audio, OCR packaging breakdown and visual review."
)
brand_app = typer.Typer(
    help="Synthesize brand policy/playbook, validate brand trees, query exemplars."
)
director_app = typer.Typer(help="Assemble and verify EditPlan specifications.")
cloud_app = typer.Typer(help="Submit distributed renders and mastering jobs to Modal.com.")

app.add_typer(contracts_app, name="contracts")
app.add_typer(project_app, name="project")
app.add_typer(providers_app, name="providers")
app.add_typer(platforms_app, name="platforms")
app.add_typer(probe_app, name="probe")
app.add_typer(breakdown_app, name="breakdown")
app.add_typer(brand_app, name="brand")
app.add_typer(director_app, name="director")
app.add_typer(cloud_app, name="cloud")

JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")]


@contracts_app.command("validate")
def contracts_validate(
    json_output: JsonOption = False,
    repo_root: Annotated[Path | None, typer.Option("--repo-root", hidden=True)] = None,
) -> None:
    """Validate contracts, platform presets, and brand trees under `profiles/`."""
    root = repo_root or find_repo_root()
    schema_files = sorted((root / "contracts").glob("*.schema.json"))
    loaded_schemas: list[str] = []
    for schema_path in schema_files:
        load_schema(schema_path.name, repo_root=root)
        loaded_schemas.append(schema_path.name)

    platforms = load_platform_targets(repo_root=root)
    brands = validate_all_brand_trees(repo_root=root)
    result = {
        "ok": True,
        "schemas": loaded_schemas,
        "platforms_validated": sorted(platforms.keys()),
        "brands_validated": [entry["brand_id"] for entry in brands],
        "brand_trees": brands,
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(
            f"Validated {len(loaded_schemas)} schemas, {len(platforms)} platform targets, "
            f"and {len(brands)} brand tree(s)."
        )


@platforms_app.command("list")
def platforms_list(json_output: JsonOption = False) -> None:
    """List available platform mastering presets."""
    platforms = load_platform_targets()
    if json_output:
        typer.echo(json.dumps(platforms, indent=2))
        return
    for pid, spec in platforms.items():
        typer.echo(
            f"{pid}: {spec['width']}x{spec['height']}@{spec['fps']}fps "
            f"({spec['aspect_ratio']}, {spec['audio']['target_lufs']} LUFS)"
        )


@providers_app.command("list")
def providers_list(json_output: JsonOption = False) -> None:
    """Inspect configured capability providers and credential readiness (no secrets shown)."""
    registry = build_default_registry()
    report = registry.status_report()
    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return
    for capability, info in report.items():
        cred_state = "credentials=SET" if info["credentials_present"] else "credentials=MISSING"
        typer.echo(
            f"{capability}: primary={info['configured_primary']} "
            f"(auth={info['auth_type']}, {cred_state})"
        )


@providers_app.command("auth")
def providers_auth(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", help="Target .env path (defaults to repo root .env)."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Re-prompt even for keys already present."),
    ] = False,
) -> None:
    """Interactively configure missing API keys and report OpenEdit OAuth login state."""
    root = find_repo_root()
    cfg = load_providers_config(repo_root=root)
    target_env = env_file or (root / ".env")

    typer.echo(f"Credential store target: {target_env} (input is hidden; press Enter to skip)")
    seen_envs: set[str] = set()
    for capability, cap_cfg in cfg.defaults.items():
        if cap_cfg.auth_type == "openedit_oauth":
            token_path = resolve_openedit_token_path()
            if has_openedit_oauth_login():
                typer.echo(
                    f"  {capability} ({cap_cfg.primary}): OpenEdit OAuth READY ({token_path})"
                )
            else:
                typer.echo(
                    f"  {capability} ({cap_cfg.primary}): OpenEdit OAuth MISSING. "
                    "Run `npx @veedstudio/openedit-cli login` to authenticate in browser."
                )
            continue

        if cap_cfg.auth_type == "local":
            typer.echo(f"  {capability} ({cap_cfg.primary}): local binary (no credentials needed)")
            continue

        env_name = cap_cfg.options.get("api_key_env")
        if not isinstance(env_name, str) or not env_name or env_name in seen_envs:
            continue
        seen_envs.add(env_name)

        already_set = bool(os.environ.get(env_name))
        if already_set and not overwrite:
            typer.echo(f"  {env_name} ({capability}): already SET (skipped)")
            continue
        entered = getpass.getpass(f"  Enter {env_name} for {capability}: ")
        if entered.strip():
            upsert_env_var(target_env, env_name, entered)
            typer.echo(f"  {env_name}: SAVED (0600)")
        else:
            typer.echo(f"  {env_name}: SKIPPED")


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


@app.command("transcribe")
def transcribe_cmd(
    media_file: Path,
    language: Annotated[
        str | None, typer.Option("--language", help="BCP-47 language hint.")
    ] = None,
    diarize: Annotated[bool, typer.Option("--diarize/--no-diarize")] = True,
    keyterm: Annotated[list[str] | None, typer.Option("--keyterm", help="Bias terms.")] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override STT provider.")
    ] = None,
    json_output: JsonOption = True,
) -> None:
    """Transcribe speech to word-level timestamps using the configured TranscriptionPort."""
    registry = build_default_registry()
    stt = registry.resolve("transcription", provider_name=provider)
    transcript = stt.transcribe(
        media_file,
        TranscriptionOptions(
            language=language,
            diarize=diarize,
            keyterms=keyterm or [],
        ),
    )
    if json_output:
        typer.echo(transcript.model_dump_json(indent=2))
    else:
        typer.echo(transcript.text)


@app.command("decide")
def decide_cmd(
    state_json: Annotated[str, typer.Option("--state", help="JSON object or text state.")],
    questions_json: Annotated[str, typer.Option("--questions", help="JSON array of questions.")],
    image: Annotated[list[Path] | None, typer.Option("--image", help="Image paths.")] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override DecisionPort.")
    ] = None,
) -> None:
    """Evaluate calibrated decision questions using the configured DecisionPort."""
    registry = build_default_registry()
    engine = registry.resolve("decision", provider_name=provider)

    try:
        parsed_state = json.loads(state_json)
    except json.JSONDecodeError:
        parsed_state = state_json

    raw_qs = json.loads(questions_json)
    questions = [
        DecisionQuestion(
            name=q["name"],
            question_type=q["type"],
            instructions=q["instructions"],
            criteria=q.get("criteria"),
            multiple=bool(q.get("multiple", False)),
            value_range=tuple(q["range"]) if "range" in q else None,
            step=q.get("step"),
            unit=q.get("unit"),
            max_items=q.get("max"),
        )
        for q in raw_qs
    ]
    images = [ImageInput(path=p) for p in (image or [])]
    res = engine.evaluate(state=parsed_state, questions=questions, images=images)
    typer.echo(
        json.dumps(
            {
                "provider": res.provider,
                "model": res.model,
                "input_tokens": res.input_tokens,
                "answers": {k: asdict(v) for k, v in res.answers.items()},
            },
            indent=2,
        )
    )


@app.command("search-audio")
def search_audio_cmd(
    query: str,
    kind: Annotated[AudioKind, typer.Option("--kind", help="music or sfx")] = "music",
    vocal_type: Annotated[VocalPolicy, typer.Option("--vocal-type")] = "NONE",
    limit: Annotated[int, typer.Option("--limit")] = 10,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Search licensed music or SFX using the configured AudioCatalogPort."""
    registry = build_default_registry()
    catalog = registry.resolve("audio_catalog", provider_name=provider)
    items = (
        catalog.search_music(query, vocal_type=vocal_type, limit=limit)
        if kind == "music"
        else catalog.search_sfx(query, limit=limit)
    )
    typer.echo(json.dumps([asdict(item) for item in items], indent=2, default=str))


@app.command("clean-audio")
def clean_audio_cmd(
    speech_input: Annotated[Path, typer.Argument(help="Speech audio or video input path.")],
    output_path: Annotated[Path, typer.Argument(help="Denoised audio output path.")],
    strength: Annotated[
        float, typer.Option("--strength", help="Noise reduction strength (0.0 to 1.0).")
    ] = 0.85,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Denoise spoken audio using the configured MediaOpsPort."""
    registry = build_default_registry()
    ops = registry.resolve("media_ops", provider_name=provider)
    result = ops.clean_audio(speech_input, output_path, strength=strength)
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("reframe")
def reframe_cmd(
    video_input: Annotated[Path, typer.Argument(help="Input video path.")],
    output_path: Annotated[Path, typer.Argument(help="Reframed video output path.")],
    aspect_ratio: Annotated[
        Literal["9:16", "1:1", "4:5", "16:9"],
        typer.Option("--aspect-ratio", help="Target aspect ratio."),
    ] = "9:16",
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Reframe video to a target aspect ratio using the configured MediaOpsPort."""
    registry = build_default_registry()
    ops = registry.resolve("media_ops", provider_name=provider)
    result = ops.reframe(video_input, output_path, target_aspect_ratio=aspect_ratio)
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("remove-background")
def remove_background_cmd(
    video_input: Annotated[Path, typer.Argument(help="Input video path.")],
    output_path: Annotated[Path, typer.Argument(help="Matte/transparent video output path.")],
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Remove video background using the configured MediaOpsPort."""
    registry = build_default_registry()
    ops = registry.resolve("media_ops", provider_name=provider)
    result = ops.remove_background(video_input, output_path)
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@breakdown_app.command("survey")
def breakdown_survey_cmd(
    media_file: Annotated[Path, typer.Argument(help="Reference video file to survey.")],
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Breakdown output directory.")
    ],
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
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Breakdown output directory.")
    ],
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
    asr: Annotated[
        bool, typer.Option("--asr/--no-asr", help="Enable optional local ASR.")
    ] = False,
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

    decision_port = (
        build_default_registry().resolve("decision") if use_decision else None
    )
    synthesized = synthesize_brand_artifacts(brand_id, samples, decision_port=decision_port)
    policy_payload = synthesized.policy.model_dump(exclude_none=True)
    playbook_payload = synthesized.playbook.model_dump(exclude_none=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(policy_payload, indent=2) + "\n", encoding="utf-8")
    if playbook_out is not None:
        playbook_out.parent.mkdir(parents=True, exist_ok=True)
        playbook_out.write_text(json.dumps(playbook_payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(
        json.dumps({"policy": policy_payload, "playbook": playbook_payload}, indent=2)
    )


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


def _load_optional_template_catalog(
    template_catalog: Path | None,
    brand_dir: Path | None,
) -> BrandTemplateCatalog | None:
    if template_catalog is not None:
        return BrandTemplateCatalog.model_validate(load_brand_template_catalog(template_catalog))
    if brand_dir is not None:
        catalog_path = brand_dir / "templates" / "catalog.json"
        if catalog_path.is_file():
            return BrandTemplateCatalog.model_validate(load_brand_template_catalog(catalog_path))
    return None


@director_app.command("plan")
def director_plan_cmd(
    probe_file: Annotated[Path, typer.Option("--probe-file", help="Source MediaProbeResult JSON.")],
    policy_file: Annotated[Path, typer.Option("--policy-file", help="BrandStylePolicy JSON.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    job_id: Annotated[str, typer.Option("--job-id")] = "job_local",
    project_id: Annotated[str, typer.Option("--project-id")] = "proj_local",
    transcript_file: Annotated[Path | None, typer.Option("--transcript-file")] = None,
    brand_dir: Annotated[
        Path | None, typer.Option("--brand-dir", help="Brand dir for templates/catalog.json.")
    ] = None,
    template_catalog: Annotated[
        Path | None, typer.Option("--template-catalog", help="Brand template catalog JSON.")
    ] = None,
    render_strategy: Annotated[
        Literal["hybrid", "full_hf"], typer.Option("--strategy")
    ] = "hybrid",
    use_decision: Annotated[
        bool, typer.Option("--use-decision", help="Enable DecisionPort spatial box grounding.")
    ] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Assemble and deterministically verify an EditPlan."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    probe = MediaProbeResult.model_validate_json(probe_file.read_text(encoding="utf-8"))
    policy = BrandStylePolicy.model_validate_json(policy_file.read_text(encoding="utf-8"))
    transcript = (
        NormalizedTranscript.model_validate_json(transcript_file.read_text(encoding="utf-8"))
        if transcript_file is not None
        else None
    )
    catalog = _load_optional_template_catalog(template_catalog, brand_dir)
    decision_port = build_default_registry().resolve("decision") if use_decision else None
    plan, report = build_edit_plan(
        job_id=job_id,
        project_id=project_id,
        probe=probe,
        policy=policy,
        platform_target=platform_target,
        transcript=transcript,
        decision_port=decision_port,
        render_strategy=render_strategy,
        template_catalog=catalog,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(plan.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    typer.echo(
        json.dumps(
            {"plan": plan.model_dump(exclude_none=True), "report": report.to_dict()},
            indent=2,
        )
    )


@director_app.command("verify")
def director_verify_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    policy_file: Annotated[Path, typer.Option("--policy-file", help="BrandStylePolicy JSON path.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    transcript_file: Annotated[Path | None, typer.Option("--transcript-file")] = None,
    brand_dir: Annotated[
        Path | None, typer.Option("--brand-dir", help="Brand dir for templates/catalog.json.")
    ] = None,
    template_catalog: Annotated[
        Path | None, typer.Option("--template-catalog", help="Brand template catalog JSON.")
    ] = None,
) -> None:
    """Verify an EditPlan deterministically against BrandStylePolicy and PlatformTarget."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    plan = EditPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
    policy = BrandStylePolicy.model_validate_json(policy_file.read_text(encoding="utf-8"))
    transcript = (
        NormalizedTranscript.model_validate_json(transcript_file.read_text(encoding="utf-8"))
        if transcript_file is not None
        else None
    )
    catalog = _load_optional_template_catalog(template_catalog, brand_dir)
    report = verify_edit_plan(
        plan,
        policy,
        platform_target,
        transcript=transcript,
        template_catalog=catalog,
    )
    typer.echo(json.dumps(report.to_dict(), indent=2))
    if not report.passed:
        raise typer.Exit(code=1)


@project_app.command("init")
def project_init_cmd(
    project_id: Annotated[str, typer.Argument(help="Unique project identifier (slug).")],
    brand_id: Annotated[str, typer.Option("--brand", help="Brand profile identifier.")],
    platform_id: Annotated[
        str, typer.Option("--platform", help="Target platform mastering preset ID.")
    ],
    projects_root: Annotated[
        Path | None,
        typer.Option(
            "--projects-root",
            help="External projects root directory (defaults to VEDIT_PROJECTS_ROOT or sibling).",
        ),
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Human-readable project title.")] = (
        None
    ),
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing project.json and brief.md.")
    ] = False,
    json_output: JsonOption = False,
) -> None:
    """Initialize a structured editing project outside the engine repository."""
    info = init_project_workspace(
        project_id=project_id,
        brand_id=brand_id,
        platform_target_id=platform_id,
        projects_root=projects_root,
        title=title,
        overwrite=overwrite,
    )
    if json_output:
        typer.echo(json.dumps(info.to_dict(), indent=2))
    else:
        typer.echo(
            f"Initialized project {project_id!r} ({brand_id} / {platform_id}) at {info.project_dir}"
        )


@project_app.command("status")
def project_status_cmd(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Path to a structured project directory containing project.json."),
    ] = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Inspect artifact and stage readiness for an external editing project."""
    report = inspect_project_status(project_dir)
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return
    typer.echo(
        f"Project {report.project_id} ({report.brand_id} / {report.platform_target_id}) "
        f"@ {report.project_dir}"
    )
    for stage_name, info in report.stages.items():
        state = "READY" if info.get("ready") else "PENDING"
        typer.echo(f"  {stage_name:12s} {state:8s} ({info.get('path')})")


@project_app.command("validate")
def project_validate_cmd(
    project_dir: Annotated[
        Path,
        typer.Argument(help="Path to a structured project directory containing project.json."),
    ] = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Validate project manifest contract, relative-path hygiene, and brand/platform refs."""
    report = validate_project_workspace(project_dir)
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        status = "PASSED" if report.passed else "FAILED"
        typer.echo(
            f"Project validation {status} ({len(report.errors)} error(s), "
            f"{len(report.warnings)} warning(s)): {report.project_dir}"
        )
        for err in report.errors:
            typer.echo(f"  [ERROR] {err.code}: {err.message}")
        for warn in report.warnings:
            typer.echo(f"  [WARN]  {warn.code}: {warn.message}")
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("compile")
def compile_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="HyperFrames project output dir.")],
    platform_id: Annotated[str | None, typer.Option("--platform")] = None,
    run_lint: Annotated[bool, typer.Option("--lint/--no-lint")] = True,
) -> None:
    """Compile an EditPlan into HyperFrames HTML/GSAP scenes and run static checks."""
    plan_path = plan_file.expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    platform_target = (
        PlatformTarget.model_validate(platforms[target_id]) if target_id in platforms else None
    )
    compiled = compile_edit_plan(
        plan,
        out_dir,
        platform_target=platform_target,
        run_lint=run_lint,
    )
    typer.echo(json.dumps(asdict(compiled), indent=2, default=str))
    if compiled.lint and not compiled.lint.ok:
        raise typer.Exit(code=1)


@app.command("master")
def master_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Final mastered MP4 output path.")],
    platform_id: Annotated[str | None, typer.Option("--platform")] = None,
    overlay_video: Annotated[
        Path | None, typer.Option("--overlay-video", help="Rendered transparent HyperFrames MOV.")
    ] = None,
    preset: Annotated[
        Literal["ultrafast", "veryfast", "fast", "medium", "slow"],
        typer.Option("--preset", help="x264/x265 encode preset."),
    ] = "fast",
    hw_encode: Annotated[
        bool,
        typer.Option("--hw-encode/--no-hw-encode", help="Use macOS VideoToolbox when available."),
    ] = False,
    ass_fastpath: Annotated[
        bool,
        typer.Option(
            "--ass-fastpath/--no-ass-fastpath",
            help="Burn plain captions and static text overlays via native FFmpeg libass.",
        ),
    ] = True,
) -> None:
    """Assemble hybrid cuts, composite overlays, and master two-pass `-14.0 LUFS` audio."""
    plan_path = plan_file.expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {target_id}")
    platform_target = PlatformTarget.model_validate(platforms[target_id])
    res = assemble_hybrid_deliverable(
        plan,
        platform_target,
        output,
        overlay_video_path=overlay_video,
        use_ass_fastpath=ass_fastpath,
        encode_preset=preset,
        use_hardware_encoder=hw_encode,
    )
    typer.echo(json.dumps(asdict(res), indent=2, default=str))


@app.command("export-otio")
def export_otio_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="EditPlan JSON path.")],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Destination OpenTimelineIO `.otio` file path.")
    ],
    resolve_paths: Annotated[
        bool,
        typer.Option(
            "--resolve-paths/--keep-relative",
            help="Emit resolved absolute asset paths instead of portable relative paths.",
        ),
    ] = False,
) -> None:
    """Export an EditPlan manifest to an OpenTimelineIO `.otio` timeline."""
    plan_path = plan_file.expanduser().resolve()
    plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    out = export_edit_plan_to_otio(
        plan,
        output,
        base_dir=plan_path.parent,
        resolve_paths=resolve_paths,
    )
    typer.echo(json.dumps({"ok": True, "output_path": str(out)}, indent=2))


@app.command("audit")
def audit_cmd(
    media_file: Annotated[Path, typer.Argument(help="Deliverable video file to audit.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    require_audio: Annotated[bool, typer.Option("--require-audio/--allow-silent")] = True,
    check_visual: Annotated[
        bool,
        typer.Option(
            "--check-visual/--no-check-visual",
            help="Scan for unintended black segments and frozen frames.",
        ),
    ] = True,
    reference: Annotated[
        Path | None,
        typer.Option("--reference", help="Optional reference video for perceptual VMAF scoring."),
    ] = None,
) -> None:
    """Run deterministic ffprobe, EBU R128, and visual QC verification on a deliverable video."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    qc = audit_mastered_deliverable(
        media_file,
        platform_target,
        require_audio=require_audio,
        check_visual=check_visual,
        reference_path=reference,
    )
    typer.echo(json.dumps(qc.to_dict(), indent=2, default=str))
    if not qc.passed:
        raise typer.Exit(code=1)


@cloud_app.command("render")
def cloud_render_cmd(
    plan_file: Annotated[Path, typer.Option("--plan-file", help="Verified EditPlan JSON path.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Local output deliverable MP4 path.")
    ] = None,
    platform_id: Annotated[str | None, typer.Option("--platform")] = None,
    chunk_frames: Annotated[
        int, typer.Option("--chunk-frames", help="Chunk frame budget (150-240).")
    ] = 180,
    quality: Annotated[
        Literal["draft", "standard", "high"],
        typer.Option("--quality", help="HyperFrames producer quality tier."),
    ] = "high",
    force_hf: Annotated[
        bool,
        typer.Option(
            "--force-hf",
            help="Force all overlays through HyperFrames Chromium instead of libass fast-path.",
        ),
    ] = False,
    ephemeral: Annotated[
        bool,
        typer.Option(
            "--ephemeral",
            help="Run an ephemeral Modal app instead of calling the deployed app.",
        ),
    ] = False,
    allow_unverified: Annotated[
        bool,
        typer.Option(
            "--allow-unverified",
            help="Allow submitting an EditPlan where verifier_passed is false.",
        ),
    ] = False,
) -> None:
    """Stage local media on Modal CAS, run distributed render & mastering, and download MP4."""
    import modal

    cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
    if cloud_src not in sys.path:
        sys.path.insert(0, cloud_src)

    from vedit_cloud.app import APP_NAME, submit_modal_render
    from vedit_cloud.app import app as modal_app

    plan_path = plan_file.expanduser().resolve()
    raw_plan = EditPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    if not raw_plan.verifier_passed and not allow_unverified:
        raise typer.BadParameter(
            "EditPlan has verifier_passed=false. Run `vedit director verify` first or pass "
            "--allow-unverified to submit anyway."
        )
    plan = resolve_plan_asset_paths(raw_plan, base_dir=plan_path.parent)
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {target_id}")
    platform_target = PlatformTarget.model_validate(platforms[target_id])

    if output is not None:
        out_path = output
    else:
        project_root = find_project_root(plan_path.parent)
        out_path = (
            project_root / "output" / "master.mp4"
            if project_root is not None
            else Path("renders") / f"{plan.job_id}_master.mp4"
        )

    deployed_fn = None
    if not ephemeral:
        try:
            deployed_fn = modal.Function.from_name(APP_NAME, "orchestrate_distributed_render")
            deployed_fn.hydrate()
        except Exception:
            deployed_fn = None

    if deployed_fn is not None:
        summary = submit_modal_render(
            plan,
            platform_target,
            output_path=out_path,
            chunk_frames=chunk_frames,
            quality=quality,
            force_hf=force_hf,
            remote_fn=deployed_fn,
        )
    else:
        with modal.enable_output(), modal_app.run():
            summary = submit_modal_render(
                plan,
                platform_target,
                output_path=out_path,
                chunk_frames=chunk_frames,
                quality=quality,
                force_hf=force_hf,
            )
    typer.echo(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    app()
