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
    synthesize_brand_policy,
)
from vedit.analyzers.media_probe import ProbeOptions, hash_media, probe_media
from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import find_repo_root, load_platform_targets, load_schema
from vedit.director.planner import build_edit_plan
from vedit.director.verifier import verify_edit_plan
from vedit.mastering.ffmpeg_master import assemble_hybrid_deliverable
from vedit.mastering.qc_audit import audit_mastered_deliverable
from vedit.models import (
    BrandStylePolicy,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    PlatformTarget,
)
from vedit.ports.audio_catalog import AudioKind, VocalPolicy
from vedit.ports.decision import DecisionQuestion, ImageInput
from vedit.ports.transcription import TranscriptionOptions
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
providers_app = typer.Typer(help="Inspect and configure capability providers.")
platforms_app = typer.Typer(help="List validated platform mastering targets.")
probe_app = typer.Typer(help="Fast deterministic media hashing, shot & CIELAB analysis.")
brand_app = typer.Typer(help="Synthesize BrandStylePolicy and query style exemplars.")
director_app = typer.Typer(help="Assemble and verify EditPlan specifications.")
cloud_app = typer.Typer(help="Submit distributed renders and mastering jobs to Modal.com.")

app.add_typer(contracts_app, name="contracts")
app.add_typer(providers_app, name="providers")
app.add_typer(platforms_app, name="platforms")
app.add_typer(probe_app, name="probe")
app.add_typer(brand_app, name="brand")
app.add_typer(director_app, name="director")
app.add_typer(cloud_app, name="cloud")

JsonOption = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")]


@contracts_app.command("validate")
def contracts_validate(
    json_output: JsonOption = False,
    repo_root: Annotated[Path | None, typer.Option("--repo-root", hidden=True)] = None,
) -> None:
    """Validate all JSON Schemas in `contracts/` and presets in `profiles/platforms/`."""
    root = repo_root or find_repo_root()
    schema_files = sorted((root / "contracts").glob("*.schema.json"))
    loaded_schemas: list[str] = []
    for schema_path in schema_files:
        load_schema(schema_path.name, repo_root=root)
        loaded_schemas.append(schema_path.name)

    platforms = load_platform_targets(repo_root=root)
    result = {
        "ok": True,
        "schemas": loaded_schemas,
        "platforms_validated": sorted(platforms.keys()),
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(
            f"Validated {len(loaded_schemas)} schemas and {len(platforms)} platform targets."
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


@brand_app.command("analyze")
def brand_analyze_cmd(
    brand_id: Annotated[str, typer.Option("--brand-id", help="Target brand policy identifier.")],
    probe_files: Annotated[
        list[Path], typer.Option("--probe-file", help="MediaProbeResult JSON path(s).")
    ],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Optional output JSON path.")
    ] = None,
    use_decision: Annotated[
        bool, typer.Option("--use-decision", help="Enrich with configured DecisionPort.")
    ] = False,
) -> None:
    """Synthesize a validated BrandStylePolicy from one or more reference MediaProbeResult JSONs."""
    samples: list[ReferenceVideoSample] = []
    for p_path in probe_files:
        probe = MediaProbeResult.model_validate_json(p_path.read_text(encoding="utf-8"))
        samples.append(ReferenceVideoSample(source_video_id=p_path.stem, probe=probe))

    decision_port = (
        build_default_registry().resolve("decision") if use_decision else None
    )
    policy = synthesize_brand_policy(brand_id, samples, decision_port=decision_port)
    payload = policy.model_dump_json(indent=2, exclude_none=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    typer.echo(payload)


@brand_app.command("exemplars")
def brand_exemplars_cmd(
    policy_file: Annotated[Path, typer.Argument(help="Path to BrandStylePolicy JSON.")],
    role: Annotated[ExemplarRole | None, typer.Option("--role")] = None,
    min_duration_s: Annotated[float | None, typer.Option("--min-duration-s")] = None,
    max_duration_s: Annotated[float | None, typer.Option("--max-duration-s")] = None,
) -> None:
    """Query matching exemplars from a BrandStylePolicy exemplar_bank."""
    policy = BrandStylePolicy.model_validate_json(policy_file.read_text(encoding="utf-8"))
    items = query_exemplars(
        policy,
        role=role,
        min_duration_s=min_duration_s,
        max_duration_s=max_duration_s,
    )
    typer.echo(json.dumps([item.model_dump(exclude_none=True) for item in items], indent=2))


@director_app.command("plan")
def director_plan_cmd(
    probe_file: Annotated[Path, typer.Option("--probe-file", help="Source MediaProbeResult JSON.")],
    policy_file: Annotated[Path, typer.Option("--policy-file", help="BrandStylePolicy JSON.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    job_id: Annotated[str, typer.Option("--job-id")] = "job_local",
    project_id: Annotated[str, typer.Option("--project-id")] = "proj_local",
    transcript_file: Annotated[Path | None, typer.Option("--transcript-file")] = None,
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
    report = verify_edit_plan(plan, policy, platform_target, transcript=transcript)
    typer.echo(json.dumps(report.to_dict(), indent=2))
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
    plan = EditPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
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
) -> None:
    """Assemble hybrid cuts, composite overlays, and master two-pass `-14.0 LUFS` audio."""
    plan = EditPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
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
    )
    typer.echo(json.dumps(asdict(res), indent=2, default=str))


@app.command("audit")
def audit_cmd(
    media_file: Annotated[Path, typer.Argument(help="Deliverable video file to audit.")],
    platform_id: Annotated[str, typer.Option("--platform", help="Target platform preset ID.")],
    require_audio: Annotated[bool, typer.Option("--require-audio/--allow-silent")] = True,
) -> None:
    """Run deterministic ffprobe and EBU R128 QC verification on a deliverable video."""
    platforms = load_platform_targets()
    if platform_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {platform_id}")
    platform_target = PlatformTarget.model_validate(platforms[platform_id])
    qc = audit_mastered_deliverable(
        media_file,
        platform_target,
        require_audio=require_audio,
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
) -> None:
    """Stage local media on Modal CAS, run distributed render & mastering, and download MP4."""
    import modal

    cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
    if cloud_src not in sys.path:
        sys.path.insert(0, cloud_src)

    from vedit_cloud.app import app as modal_app
    from vedit_cloud.app import submit_modal_render

    plan = EditPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
    target_id = platform_id or plan.platform_target_id
    platforms = load_platform_targets()
    if target_id not in platforms:
        raise typer.BadParameter(f"Unknown platform target: {target_id}")
    platform_target = PlatformTarget.model_validate(platforms[target_id])
    out_path = output or (Path("renders") / f"{plan.job_id}_master.mp4")

    with modal.enable_output(), modal_app.run():
        summary = submit_modal_render(
            plan,
            platform_target,
            output_path=out_path,
            chunk_frames=chunk_frames,
        )
    typer.echo(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    app()
