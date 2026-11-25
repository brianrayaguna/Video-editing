"""Tests for narrative frameworks, shot-list export, storyboard propagation, and cinematography."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from vedit.analyzers.editorial_forensics import analyze_cross_cut_continuity
from vedit.cli import app
from vedit.director.critique import build_critique_packet
from vedit.director.planner import build_edit_plan
from vedit.director.script_readiness import audit_script_readiness
from vedit.director.storyboard import (
    check_storyboard,
    export_shot_list,
    idioms_path,
    load_directing_idioms,
    validate_storyboard_contract,
)
from vedit.director.storyboard_plan import storyboard_overlays
from vedit.models import (
    BrandStylePolicy,
    BrandTemplateCatalog,
    MediaProbeResult,
    NormalizedTranscript,
    PlatformTarget,
)


def _sample_words(clauses: list[tuple[str, float, float]]) -> list[dict[str, object]]:
    words: list[dict[str, object]] = []
    for text, start_s, end_s in clauses:
        toks = text.split()
        step = (end_s - start_s) / max(len(toks), 1)
        for idx, tok in enumerate(toks):
            words.append(
                {
                    "text": tok,
                    "start_s": round(start_s + idx * step, 3),
                    "end_s": round(start_s + (idx + 1) * step, 3),
                    "is_filler": False,
                }
            )
    return words


def test_narrative_frameworks_character_arc_blocking_and_shot_list(tmp_path: Path) -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    sb = {
        "schema_version": "1.0",
        "project_id": "proj_sc",
        "brand_id": "geoverum",
        "duration_s": 24.0,
        "directing_source": "user",
        "pacing": "default",
        "story": {
            "shape": "mystery_turn",
            "narrative_framework": "story_circle",
            "story_circle_map": {
                "you": "b1",
                "need": "b2",
                "go": "b3",
                "search": "b4",
                "find": "b4",
                "take": "b3",  # Out of order intentionally
            },
            "character_arc": {
                "kind": "positive",
                "start_state": "uncertain observer",
                "end_state": "uncertain observer",
            },
        },
        "overrides": {"disabled_idioms": ["curiosity_loops_closed"]},
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.0,
                "end_s": 4.0,
                "clause": "A quiet strait hides a flaw.",
                "function": "hook",
                "story_need": "open on key question",
                "device": "fill",
                "blocking": {
                    "subject_zone": "left",
                    "axis_side": "left",
                    "camera_move": "dolly_in",
                },
                "subtext_note": "A quiet strait hides a flaw.",
            },
            {
                "beat_id": "b2",
                "start_s": 4.0,
                "end_s": 10.0,
                "clause": "Engineers surveyed 14 km in 1998.",
                "function": "setup",
                "story_need": "show scale proof",
                "device": "measurement_line",
                "blocking": {"subject_zone": "right", "axis_side": "right", "camera_move": "pan"},
            },
            {
                "beat_id": "b3",
                "start_s": 10.0,
                "end_s": 17.0,
                "clause": "Then winter currents severed the cable.",
                "function": "hinge",
                "story_need": "mark pivot beat",
                "device": "route_trace",
                "blocking": {
                    "subject_zone": "center",
                    "axis_side": "neutral",
                    "camera_move": "orbit",
                },
            },
            {
                "beat_id": "b4",
                "start_s": 17.0,
                "end_s": 24.0,
                "clause": "Recovery took 42 days.",
                "function": "outro",
                "story_need": "land closing datum",
                "device": "numeral",
                "blocking": {
                    "subject_zone": "center",
                    "axis_side": "neutral",
                    "camera_move": "static",
                },
            },
        ],
    }

    rep = check_storyboard(sb, idioms)
    idiom_hits = {i.idiom_id for i in rep.issues}
    assert "narrative_framework_structure" in idiom_hits
    assert "subtext_and_arc_coherence" in idiom_hits
    assert "blocking_axis_continuity" in idiom_hits

    shot_list = export_shot_list(sb)
    assert shot_list["total_shots"] == 4
    assert shot_list["shots"][0]["axis_side"] == "left"
    assert shot_list["shots"][0]["camera_move"] == "dolly_in"

    sb_file = tmp_path / "sb.json"
    sl_out = tmp_path / "shot_list.json"
    sb_file.write_text(json.dumps(sb), encoding="utf-8")
    res = CliRunner().invoke(app, ["storyboard", "shot-list", str(sb_file), "-o", str(sl_out)])
    assert res.exit_code == 0, res.output
    assert sl_out.is_file()


def test_storyboard_propagation_and_script_readiness_checks(tmp_path: Path) -> None:
    idioms = load_directing_idioms(idioms_path("geoverum"))
    policy = BrandStylePolicy.model_validate_json(
        Path("profiles/brands/geoverum/brand_style_policy.json").read_text(encoding="utf-8")
    )
    catalog = BrandTemplateCatalog.model_validate_json(
        Path("profiles/brands/geoverum/templates/catalog.json").read_text(encoding="utf-8")
    )
    platforms = json.loads(
        subprocess.run(
            ["packages/director-py/.venv/bin/vedit", "contracts", "validate", "--json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert platforms["ok"] is True

    from vedit.contracts import load_platform_targets

    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    src_mp4 = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#083847:s=360x640:r=30:d=4.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=48000",
            "-t",
            "4.0",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(src_mp4),
        ],
        check=True,
        capture_output=True,
    )
    probe = MediaProbeResult.model_validate(
        {
            "schema_version": "1.0",
            "path": str(src_mp4),
            "sha256": "c" * 64,
            "file_bytes": src_mp4.stat().st_size,
            "container": {"format_name": "mp4", "duration_s": 4.0},
            "video": {
                "present": True,
                "width": 360,
                "height": 640,
                "fps": 30.0,
                "is_cfr": True,
            },
            "audio": {
                "present": True,
                "sample_rate_hz": 48000,
                "channels": 2,
                "silence_intervals": [],
                "silence_ratio": 0.0,
            },
            "shots": [
                {
                    "shot_index": 0,
                    "start_s": 0.0,
                    "end_s": 2.0,
                    "duration_s": 2.0,
                    "confidence": 0.9,
                },
                {
                    "shot_index": 1,
                    "start_s": 2.0,
                    "end_s": 4.0,
                    "duration_s": 2.0,
                    "confidence": 0.9,
                },
            ],
            "shot_stats": {
                "count": 2,
                "asl_p25_s": 2.0,
                "asl_p50_s": 2.0,
                "asl_p75_s": 2.0,
                "cuts_per_min": 15.0,
            },
            "visual": {
                "sampled_frames": 2,
                "palette": [],
                "palette_entropy": 0.0,
                "mean_luminance": 60.0,
                "band_luminance": {"upper": 60.0, "center": 60.0, "lower_third": 60.0},
                "mean_sharpness": 100.0,
                "black_intervals": [],
                "keyframes": [],
            },
            "timing_ms": {
                "hash_ms": 1,
                "ffprobe_ms": 5,
                "stream_analyze_ms": 5,
                "total_ms": 11,
            },
        }
    )
    transcript = NormalizedTranscript.model_validate(
        {
            "provider": "mock",
            "source_hash": "c" * 64,
            "language": "en",
            "duration_s": 4.0,
            "text": "14 km across the strait.",
            "words": _sample_words(
                [("14 km", 0.1, 1.5), ("across the strait.", 2.1, 3.6)]
            ),
        }
    )
    sb = {
        "schema_version": "1.0",
        "project_id": "proj_prop",
        "brand_id": "geoverum",
        "duration_s": 4.0,
        "directing_source": "user",
        "pacing": "default",
        "story": {"shape": "record_superlative"},
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.0,
                "end_s": 1.8,
                "clause": "14 km",
                "function": "hook",
                "story_need": "open cleanly",
                "device": "numeral",
                "register": "comic",
                "blend_mode": "screen",
                "color_mood": "cool_investigative",
                "shot": {
                    "scale": "ws",
                    "angle": "birds_eye",
                    "lighting": "natural",
                    "motion_direction": "left_to_right",
                },
                "callouts": [{"kind": "numeral", "text": "14 km", "xy": [540, 620]}],
            },
            {
                "beat_id": "b2",
                "start_s": 1.8,
                "end_s": 4.0,
                "clause": "across the strait.",
                "function": "outro",
                "story_need": "close cleanly",
                "device": "numeral",
                "color_mood": "dread_dim_vignette",
                "split_edit": {"kind": "j_cut", "offset_s": 0.5},
                "shot": {"scale": "cu", "angle": "low_angle", "lighting": "chiaroscuro"},
                "callouts": [{"kind": "numeral", "text": "14 km", "xy": [540, 620]}],
            },
        ],
    }

    assert validate_storyboard_contract(sb) == []
    sb_ovs, _ = storyboard_overlays(
        sb, idioms, catalog, policy, frame=(1080, 1920), duration_s=4.0, safe_zone=target.safe_zone
    )
    assert sb_ovs[0].motion_register == "comic"
    assert sb_ovs[0].blend_mode == "screen"

    plan, report = build_edit_plan(
        job_id="job_prop",
        project_id="proj_prop",
        probe=probe,
        policy=policy,
        platform_target=target,
        transcript=transcript,
        template_catalog=catalog,
        extra_overlays=sb_ovs,
        storyboard=sb,
    )
    assert report.passed
    assert plan.video_tracks[0].shot_scale == "ws"
    assert plan.video_tracks[0].lighting_key == "normal_key"
    assert plan.video_tracks[0].color_grade is not None
    assert plan.video_tracks[0].color_grade.preset == "cool_investigative"
    assert plan.video_tracks[1].shot_scale == "cu"
    assert plan.video_tracks[1].lighting_key == "chiaroscuro"
    assert plan.video_tracks[1].color_grade is not None
    assert plan.video_tracks[1].color_grade.preset == "dread_dim_vignette"

    packet = build_critique_packet(idioms=idioms, storyboard=sb, cuts=[2.0])
    assert "tension_curve" in packet["deterministic"]

    # Script readiness flags fast kinetic burst and trailing CTA filler.
    tr_fast = {
        "duration_s": 2.4,
        "words": _sample_words(
            [
                ("Five rapid spoken words here.", 0.0, 0.55),
                ("Thanks for watching and subscribe.", 1.0, 2.3),
            ]
        ),
    }
    sr_rep = audit_script_readiness(tr_fast, idioms)
    sr_codes = {f.code for f in sr_rep.findings}
    assert "kinetic_legibility_risk" in sr_codes
    assert "trailing_bloat_outro" in sr_codes


def test_editorial_forensics_cinematography_metrics(tmp_path: Path) -> None:
    vid = tmp_path / "warm_bright.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#F0D8B8:s=320x180:r=25:d=1.6",
            "-t",
            "1.6",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(vid),
        ],
        check=True,
        capture_output=True,
    )
    rep = analyze_cross_cut_continuity(vid, cuts_s=[0.8])
    assert rep.dominant_lighting_key == "high_key"
    assert rep.mean_symmetry_index > 0.9
    assert rep.mean_warm_cool_balance > 0.1
