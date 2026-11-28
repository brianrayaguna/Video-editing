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
from vedit.analyzers.fullframe_forensics import (
    FullFrameForensicsOptions,
    analyze_video_fullframe,
)
from vedit.analyzers.media_probe import ProbeOptions, hash_media, probe_media
from vedit.analyzers.spatial_forensics import (
    SpatialForensicsOptions,
    analyze_video_structure,
)
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
memory_app = typer.Typer(help="Inspect and record external per-brand episodic memory.")
brand_app.add_typer(memory_app, name="memory")


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
        bool | None,
        typer.Option(
            "--prepare-review/--no-prepare-review",
            help="Generate review_tasks.json and review_answers.json for visual review.",
        ),
    ] = None,
    ocr: Annotated[
        bool | None,
        typer.Option("--ocr/--no-ocr", help="Enable local OCR caption/text extraction."),
    ] = None,
    stems: Annotated[
        bool | None,
        typer.Option("--stems/--no-stems", help="Enable local vocal/music stem separation."),
    ] = None,
    packaging: Annotated[
        bool | None,
        typer.Option(
            "--packaging/--no-packaging",
            help="Extract subtitle lanes, styled text, and stickers.",
        ),
    ] = None,
    asr: Annotated[
        bool | None, typer.Option("--asr/--no-asr", help="Enable optional local ASR.")
    ] = None,
    use_vlm: Annotated[
        bool | None,
        typer.Option(
            "--vlm/--no-vlm",
            help="Use external VLM API (disabled by default; prefer interactive visual review).",
        ),
    ] = None,
    lang: Annotated[Literal["en", "zh"] | None, typer.Option("--lang")] = None,
    ocr_lang: Annotated[str | None, typer.Option("--ocr-lang")] = None,
    env_file: Annotated[Path | None, typer.Option("--env-file")] = None,
    workers: Annotated[int | None, typer.Option("--workers")] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Override VideoBreakdownPort provider.")
    ] = None,
) -> None:
    """Run forensic video breakdown and emit VIDEO.md + normalized video_breakdown.json."""
    registry = build_default_registry()
    engine = registry.resolve("video_breakdown", provider_name=provider)
    cfg_opts = getattr(engine, "_options", None)
    defaults = cfg_opts if isinstance(cfg_opts, dict) else {}
    resolved_lang = lang if lang is not None else str(defaults.get("lang", "en"))
    result = engine.analyze(
        media_file,
        out_dir,
        BreakdownOptions(
            use_vlm=use_vlm if use_vlm is not None else bool(defaults.get("use_vlm", False)),
            prepare_review=(
                prepare_review
                if prepare_review is not None
                else bool(defaults.get("prepare_review", True))
            ),
            ocr=ocr if ocr is not None else bool(defaults.get("ocr", True)),
            stems=stems if stems is not None else bool(defaults.get("stems", True)),
            packaging=(
                packaging if packaging is not None else bool(defaults.get("packaging", True))
            ),
            asr=asr if asr is not None else bool(defaults.get("asr", False)),
            lang="zh" if resolved_lang == "zh" else "en",
            ocr_lang=ocr_lang if ocr_lang is not None else defaults.get("ocr_lang"),
            env_file=env_file,
            workers=workers if workers is not None else int(defaults.get("workers", 3)),
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


@breakdown_app.command("structure")
def breakdown_structure_cmd(
    media_file: Annotated[Path, typer.Argument(help="Reference video file to analyze.")],
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Spatial forensics output directory.")
    ],
    shots_from: Annotated[
        Path | None,
        typer.Option(
            "--shots-from",
            help="Optional probe.json or video_breakdown.json to align sampling to shot midpoints.",
        ),
    ] = None,
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            help="Optional platform_target_id (e.g. shorts_9x16_1080p) for safe-zone checks.",
        ),
    ] = None,
    max_frames: Annotated[
        int, typer.Option("--max-frames", min=1, max=48, help="Maximum frames to analyze.")
    ] = 12,
    max_motion_windows: Annotated[
        int,
        typer.Option(
            "--max-motion-windows", min=0, max=12, help="Shot-onset motion burst windows."
        ),
    ] = 4,
    subject_mask: Annotated[
        bool,
        typer.Option(
            "--subject-mask/--no-subject-mask",
            help="Enable u2netp ONNX foreground subject mask for whitespace/calm ratio.",
        ),
    ] = True,
    face_detection: Annotated[
        bool,
        typer.Option(
            "--face-detection/--no-face-detection",
            help="Enable MediaPipe face & eye-line detection.",
        ),
    ] = True,
) -> None:
    """Extract latent grid, visual hierarchy, typography/WCAG, motion easing, and SoM blueprints."""
    result = analyze_video_structure(
        media_file,
        out_dir,
        SpatialForensicsOptions(
            shots_json=shots_from,
            platform_target_id=platform,
            max_frames=max_frames,
            max_motion_windows=max_motion_windows,
            use_subject_mask=subject_mask,
            use_face_detection=face_detection,
        ),
    )
    out_resolved = out_dir.expanduser().resolve()
    payload = {
        "spatial_forensics_path": str(out_resolved / "spatial_forensics.json"),
        "structure_md_path": result.structure_md_path,
        "frames_analyzed": len(result.frames),
        "motion_windows": len(result.motion_windows),
        "summary": result.summary.model_dump(exclude_none=True),
    }
    typer.echo(json.dumps(payload, indent=2))


@breakdown_app.command("fullframe")
def breakdown_fullframe_cmd(
    media_file: Annotated[Path, typer.Argument(help="Reference video file to analyze.")],
    out_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Full-frame forensics output directory.")
    ],
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            help="Optional platform_target_id (e.g. shorts_9x16_1080p) recorded in report.",
        ),
    ] = None,
    ocr_fps: Annotated[
        float,
        typer.Option("--ocr-fps", min=0.5, max=15.0, help="Dense OCR sampling rate in fps."),
    ] = 3.0,
    sheet_fps: Annotated[
        float,
        typer.Option("--sheet-fps", min=0.2, max=5.0, help="Timeline contact-sheet sampling fps."),
    ] = 1.0,
    max_event_strips: Annotated[
        int,
        typer.Option("--max-event-strips", min=0, max=64, help="Max full-FPS cut burst strips."),
    ] = 16,
) -> None:
    """Run native-FPS full-frame video forensics across camera, surfaces, layout, and audio."""
    result = analyze_video_fullframe(
        media_file,
        out_dir,
        FullFrameForensicsOptions(
            platform_target_id=platform,
            ocr_fps=ocr_fps,
            sheet_fps=sheet_fps,
            max_event_strips=max_event_strips,
        ),
    )
    out_resolved = out_dir.expanduser().resolve()
    payload = {
        "fullframe_forensics_path": str(out_resolved / "fullframe_forensics.json"),
        "report_md_path": result["report_md_path"],
        "frame_telemetry_path": result["frame_telemetry_path"],
        "frame_count": result["frame_count"],
        "surface_segments": len(result["surface_segments"]),
        "camera_segments": len(result["camera_segments"]),
        "cuts": len(result["cuts"]),
        "graphic_events": len(result["graphic_events"]),
        "captions": len(result["captions"]),
        "in_world_text": len(result["in_world_text"]),
        "timeline_sheets": len(result["sheets"]["timeline_sheets"]),
        "summary": result["summary"],
    }
    typer.echo(json.dumps(payload, indent=2))


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


@breakdown_app.command("editorial")
def breakdown_editorial_cmd(
    media_file: Annotated[
        Path, typer.Argument(help="Video file to analyze for editorial continuity.")
    ],
    shots_from: Annotated[
        Path | None,
        typer.Option(
            "--shots-from", help="Optional probe.json or video_breakdown.json supplying shot cuts."
        ),
    ] = None,
    transcript_file: Annotated[
        Path | None,
        typer.Option(
            "--transcript", help="Optional NormalizedTranscript JSON for J/L-cut & WPM tension."
        ),
    ] = None,
    storyboard_file: Annotated[
        Path | None,
        typer.Option("--storyboard", help="Optional Storyboard JSON for tension-curve comparison."),
    ] = None,
    out_file: Annotated[
        Path | None, typer.Option("--out", "--out-file", "-o", help="Optional JSON output path.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON output (always JSON, for CLI parity).")
    ] = True,
) -> None:
    """Analyze cross-cut eye-trace, luma/Lab shock, J/L edits, mono phase, and tension."""
    del as_json
    from vedit.analyzers.editorial_forensics import analyze_editorial_forensics

    cuts_s: list[float] = []
    if shots_from is not None:
        sdata = json.loads(shots_from.expanduser().resolve().read_text(encoding="utf-8"))
        for sh in sdata.get("shots") or []:
            st = float(sh.get("start_s", 0.0))
            if st > 0.05:
                cuts_s.append(st)
    tr = (
        json.loads(transcript_file.expanduser().resolve().read_text(encoding="utf-8"))
        if transcript_file is not None
        else None
    )
    sb = (
        json.loads(storyboard_file.expanduser().resolve().read_text(encoding="utf-8"))
        if storyboard_file is not None
        else None
    )
    report = analyze_editorial_forensics(
        media_file,
        cuts_s=cuts_s or None,
        transcript=tr,
        storyboard=sb,
    ).to_dict()
    payload = json.dumps(report, indent=2)
    if out_file is not None:
        out_p = out_file.expanduser().resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


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


@brand_app.command("calibrate-idioms")
def brand_calibrate_idioms_cmd(
    reference_storyboards: Annotated[
        list[Path],
        typer.Option(
            "--reference-storyboard",
            help="Annotated reference storyboard JSON (directing_source: reference). Repeatable.",
        ),
    ],
    idioms_file: Annotated[
        Path, typer.Option("--idioms-file", help="Brand directing_idioms.json to calibrate.")
    ],
    report: Annotated[
        Path, typer.Option("--report", help="Calibration report JSON (keep outside the repo).")
    ],
    camera_tracks: Annotated[
        list[Path] | None,
        typer.Option(
            "--camera-track",
            help="Measured [t,lng,lat,zoom,bearing] track per reference, in the same order.",
        ),
    ] = None,
    blend: Annotated[
        float, typer.Option(help="Move existing values toward measurements by this fraction.")
    ] = 0.5,
    apply: Annotated[
        bool, typer.Option("--apply", help="Write the proposed parameters into --idioms-file.")
    ] = False,
) -> None:
    """Measure annotated references and propose (or apply) directing idiom parameters."""
    from vedit.analyzers.idiom_calibration import calibrate_idioms
    from vedit.director.storyboard import load_directing_idioms

    idioms = load_directing_idioms(idioms_file)
    refs = [json.loads(p.read_text(encoding="utf-8")) for p in reference_storyboards]
    tracks = [json.loads(p.read_text(encoding="utf-8")) for p in camera_tracks or []]
    if tracks and len(tracks) != len(refs):
        raise typer.BadParameter("Pass one --camera-track per --reference-storyboard, or none.")
    result = calibrate_idioms(idioms, refs, camera_tracks=tracks or None, blend=blend)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if apply:
        idioms_file.write_text(
            json.dumps(result["proposed_idioms"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    typer.echo(
        json.dumps(
            {
                "report": str(report),
                "applied": apply,
                "changes": result["changes"],
                "skipped": len(result["skipped"]),
                "follow_up": result["follow_up"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@memory_app.command("show")
def brand_memory_show_cmd(
    brand_id: Annotated[str, typer.Option("--brand-id", help="Target brand identifier.")],
    projects_root: Annotated[
        Path | None,
        typer.Option("--projects-root", help="External VEDIT_PROJECTS_ROOT override."),
    ] = None,
) -> None:
    """Display the external brand_memory.json for a brand (or empty summary if absent)."""
    from vedit.director.brand_memory import (
        empty_brand_memory,
        load_brand_memory,
        resolve_brand_memory_path,
    )

    mem_path = resolve_brand_memory_path(brand_id, projects_root=projects_root)
    memory = load_brand_memory(mem_path) if mem_path.is_file() else empty_brand_memory(brand_id)
    typer.echo(json.dumps({"path": str(mem_path), "memory": memory}, indent=2, ensure_ascii=False))


@memory_app.command("record")
def brand_memory_record_cmd(
    brand_id: Annotated[str, typer.Option("--brand-id", help="Target brand identifier.")],
    storyboard_file: Annotated[
        Path, typer.Option("--storyboard", help="Completed Storyboard JSON.")
    ],
    critique_packet_file: Annotated[
        Path | None, typer.Option("--packet", help="Optional CritiquePacket JSON.")
    ] = None,
    gate_result_file: Annotated[
        Path | None, typer.Option("--gate-result", help="Optional gate_review output JSON.")
    ] = None,
    projects_root: Annotated[
        Path | None,
        typer.Option("--projects-root", help="External VEDIT_PROJECTS_ROOT override."),
    ] = None,
) -> None:
    """Record an episode outcome into external VEDIT_PROJECTS_ROOT/<brand_id>/brand_memory.json."""
    from vedit.director.brand_memory import (
        empty_brand_memory,
        load_brand_memory,
        record_episode_outcome,
        resolve_brand_memory_path,
        save_brand_memory,
    )

    mem_path = resolve_brand_memory_path(brand_id, projects_root=projects_root)
    memory = load_brand_memory(mem_path) if mem_path.is_file() else empty_brand_memory(brand_id)
    sb = json.loads(storyboard_file.expanduser().read_text(encoding="utf-8"))
    packet = (
        json.loads(critique_packet_file.expanduser().read_text(encoding="utf-8"))
        if critique_packet_file is not None
        else None
    )
    gate = (
        json.loads(gate_result_file.expanduser().read_text(encoding="utf-8"))
        if gate_result_file is not None
        else None
    )
    updated = record_episode_outcome(memory, sb, critique_packet=packet, gate_result=gate)
    saved = save_brand_memory(mem_path, updated)
    typer.echo(
        json.dumps(
            {
                "path": str(saved),
                "recent_episodes": len(updated["recent_episodes"]),
                "winning_beats": len(updated["winning_beats"]),
                "failure_patterns": len(updated["failure_patterns"]),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@brand_app.command("invert-reference")
def brand_invert_reference_cmd(
    transcript_file: Annotated[Path, typer.Argument(help="NormalizedTranscript JSON.")],
    project_id: Annotated[str, typer.Option("--project-id", help="Reference topic id.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Draft reference storyboard JSON path.")],
    brand: Annotated[
        str | None, typer.Option("--brand", help="Brand id (loads its directing idioms).")
    ] = None,
    idioms_file: Annotated[
        Path | None, typer.Option("--idioms-file", help="Explicit directing_idioms.json path.")
    ] = None,
    review_queue_out: Annotated[
        Path | None,
        typer.Option("--review-queue-out", help="Optional exception review queue JSON path."),
    ] = None,
    breakdown_file: Annotated[
        Path | None, typer.Option("--breakdown-file", help="Optional VideoBreakdownResult JSON.")
    ] = None,
    probe_file: Annotated[
        Path | None, typer.Option("--probe-file", help="Optional MediaProbeResult JSON.")
    ] = None,
    camera_track: Annotated[
        Path | None, typer.Option("--camera-track", help="Optional [t,lng,lat,zoom,bearing] JSON.")
    ] = None,
) -> None:
    """Draft a reference storyboard from telemetry and emit an exception review queue."""
    from vedit.analyzers.reference_inversion import draft_reference_storyboard
    from vedit.director.storyboard import idioms_path, load_directing_idioms

    if idioms_file is not None:
        idioms = load_directing_idioms(idioms_file.expanduser())
    elif brand:
        idioms = load_directing_idioms(idioms_path(brand))
    else:
        raise typer.BadParameter("Pass --brand or --idioms-file.")

    tr = json.loads(transcript_file.expanduser().read_text(encoding="utf-8"))
    bd = (
        json.loads(breakdown_file.expanduser().read_text(encoding="utf-8"))
        if breakdown_file is not None
        else None
    )
    pr = (
        json.loads(probe_file.expanduser().read_text(encoding="utf-8"))
        if probe_file is not None
        else None
    )
    cam = (
        json.loads(camera_track.expanduser().read_text(encoding="utf-8"))
        if camera_track is not None
        else None
    )
    result = draft_reference_storyboard(
        tr,
        idioms,
        project_id=project_id,
        breakdown=bd,
        probe=pr,
        camera_track=cam,
    )
    out.expanduser().parent.mkdir(parents=True, exist_ok=True)
    out.expanduser().write_text(
        json.dumps(result.storyboard, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if review_queue_out is not None:
        q_payload = {
            "project_id": project_id,
            "stats": result.stats,
            "exception_review_beats": result.exception_review_beats,
            "beat_audits": [a.to_dict() for a in result.beat_audits],
        }
        review_queue_out.expanduser().parent.mkdir(parents=True, exist_ok=True)
        review_queue_out.expanduser().write_text(
            json.dumps(q_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    typer.echo(
        json.dumps(
            {
                "out": str(out),
                "review_queue_out": str(review_queue_out) if review_queue_out else None,
                "stats": result.stats,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
