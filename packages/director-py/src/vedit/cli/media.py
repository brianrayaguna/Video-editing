"""Transcription, decisioning, audio catalog, and media preprocessing commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import typer

from vedit.cli._app import JsonOption, app
from vedit.mastering.qc_audit import audit_production_sound
from vedit.ports.audio_catalog import AudioKind, VocalPolicy
from vedit.ports.decision import DecisionQuestion, ImageInput
from vedit.ports.transcription import TranscriptionOptions
from vedit.providers.registry import build_default_registry


@app.command("transcribe", rich_help_panel="Media & decisioning")
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
    opts = TranscriptionOptions(
        language=language,
        diarize=diarize,
        keyterms=keyterm or [],
    )
    transcript = registry.call_with_fallback(
        "transcription",
        lambda stt: stt.transcribe(media_file, opts),
        provider_name=provider,
    )
    if json_output:
        typer.echo(transcript.model_dump_json(indent=2))
    else:
        typer.echo(transcript.text)


@app.command("decide", rich_help_panel="Media & decisioning")
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
            value_range=tuple(q["range"]) if q.get("range") is not None else None,
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


@app.command("search-audio", rich_help_panel="Media & decisioning")
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


@app.command("clean-audio", rich_help_panel="Media & decisioning")
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
    result = registry.call_with_fallback(
        "media_ops",
        lambda ops: ops.clean_audio(speech_input, output_path, strength=strength),
        provider_name=provider,
    )
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("reframe", rich_help_panel="Media & decisioning")
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
    result = registry.call_with_fallback(
        "media_ops",
        lambda ops: ops.reframe(video_input, output_path, target_aspect_ratio=aspect_ratio),
        provider_name=provider,
    )
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("remove-background", rich_help_panel="Media & decisioning")
def remove_background_cmd(
    video_input: Annotated[Path, typer.Argument(help="Input video path.")],
    output_path: Annotated[Path, typer.Argument(help="Matte/transparent video output path.")],
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """Remove video background using the configured MediaOpsPort."""
    registry = build_default_registry()
    result = registry.call_with_fallback(
        "media_ops",
        lambda ops: ops.remove_background(video_input, output_path),
        provider_name=provider,
    )
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("trim", rich_help_panel="Media & decisioning")
def trim_cmd(
    video_input: Annotated[Path, typer.Argument(help="Input clip path.")],
    output_path: Annotated[Path, typer.Argument(help="Trimmed clip output path.")],
    start: Annotated[float, typer.Option("--start", help="Cut start in seconds.")],
    end: Annotated[float, typer.Option("--end", help="Cut end in seconds.")],
    accurate: Annotated[
        bool,
        typer.Option("--accurate", help="Re-encode for a frame-exact start instead of copy."),
    ] = False,
    provider: Annotated[
        str, typer.Option("--provider", help="MediaOpsPort provider.")
    ] = "ffmpeg",
) -> None:
    """Trim a clip using the configured MediaOpsPort (lossless stream copy by default)."""
    ops = build_default_registry().resolve("media_ops", provider_name=provider)
    result = ops.trim(
        video_input, output_path, start_s=start, end_s=end, accurate=accurate
    )
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("remove-silence", rich_help_panel="Media & decisioning")
def remove_silence_cmd(
    speech_input: Annotated[Path, typer.Argument(help="Voiceover audio or video input path.")],
    output_path: Annotated[Path, typer.Argument(help="Tightened WAV output path.")],
    threshold_db: Annotated[
        float, typer.Option("--threshold-db", help="Silence level in dBFS.")
    ] = -40.0,
    min_silence: Annotated[
        float, typer.Option("--min-silence", help="Shortest pause to cut, in seconds.")
    ] = 0.45,
    padding: Annotated[
        float, typer.Option("--padding", help="Breath kept on each side of a cut, in seconds.")
    ] = 0.12,
    room_tone_db: Annotated[
        float | None,
        typer.Option("--room-tone-db", help="Optional room-tone floor level in dBFS (e.g. -48)."),
    ] = None,
    provider: Annotated[
        str, typer.Option("--provider", help="MediaOpsPort provider.")
    ] = "ffmpeg",
) -> None:
    """Cut long pauses from a voiceover via MediaOpsPort; run before `transcribe`."""
    ops = build_default_registry().resolve("media_ops", provider_name=provider)
    result = ops.remove_silence(
        speech_input,
        output_path,
        threshold_db=threshold_db,
        min_silence_s=min_silence,
        padding_s=padding,
        room_tone_db=room_tone_db,
    )
    typer.echo(json.dumps(asdict(result), indent=2, default=str))


@app.command("inspect-audio", rich_help_panel="Media & decisioning")
def inspect_audio_cmd(
    media_file: Annotated[Path, typer.Argument(help="Raw voiceover or field recording path.")],
    out_file: Annotated[
        Path | None, typer.Option("--out", "--out-file", "-o", help="Optional JSON report path.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON output (always JSON, for CLI parity).")
    ] = True,
) -> None:
    """Inspect production sound health (clipping, SNR, sub-80 Hz rumble, plosives)."""
    del as_json
    report = audit_production_sound(media_file).to_dict()
    payload = json.dumps(report, indent=2)
    if out_file is not None:
        out_p = out_file.expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@app.command("restore-footage", rich_help_panel="Media & decisioning")
def restore_footage_cmd(
    video_input: Annotated[Path, typer.Argument(help="Raw footage input path.")],
    output_path: Annotated[Path, typer.Argument(help="Restored footage output path.")],
    stabilize: Annotated[bool, typer.Option("--stabilize/--no-stabilize")] = True,
    denoise: Annotated[bool, typer.Option("--denoise/--no-denoise")] = True,
    deinterlace: Annotated[bool, typer.Option("--deinterlace/--no-deinterlace")] = False,
    provider: Annotated[
        str, typer.Option("--provider", help="MediaOpsPort provider.")
    ] = "ffmpeg",
) -> None:
    """Stabilize, denoise, and optionally deinterlace raw footage via MediaOpsPort."""
    ops = build_default_registry().resolve("media_ops", provider_name=provider)
    result = ops.restore_footage(
        video_input,
        output_path,
        stabilize=stabilize,
        denoise=denoise,
        deinterlace=deinterlace,
    )
    typer.echo(json.dumps(asdict(result), indent=2, default=str))
