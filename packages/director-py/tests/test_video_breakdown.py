"""Tests for VideoBreakdownPort, ReaVideoBreakdownProvider parser, and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from vedit.cli import app
from vedit.contracts import validate_against_contract
from vedit.models import (
    MediaProbeResult,
    ProbeAudioInfo,
    ProbeBandLuminance,
    ProbeContainerInfo,
    ProbePaletteColor,
    ProbeShotSegment,
    ProbeShotStats,
    ProbeTimingBreakdown,
    ProbeVideoInfo,
    ProbeVisualInfo,
)
from vedit.ports.video_breakdown import VideoBreakdownPort
from vedit.providers.video_breakdown.rea_video import (
    ReaVideoBreakdownProvider,
    parse_rea_breakdown,
)


def _sample_raw_rea_breakdown(
    *,
    width: int = 1080,
    height: int = 1920,
    rotation: int = 0,
    ai_ratio: float = 0.0,
    reviewed: bool = True,
    no_beat: bool = False,
) -> dict[str, Any]:
    live_ratio = round(max(0.0, 0.55 - ai_ratio), 4)
    mix = [
        {"label": "code_render", "seconds": 27.0, "ratio": 0.45},
        {"label": "live_action", "seconds": round(60.0 * live_ratio, 2), "ratio": live_ratio},
    ]
    if ai_ratio > 0:
        mix.append({"label": "ai_video", "seconds": round(60.0 * ai_ratio, 2), "ratio": ai_ratio})

    decided_by = "fused_agent" if reviewed else "deterministic"
    shots: list[dict[str, Any]] = [
        {
            "id": "shot_001",
            "index": 1,
            "start": 0.0,
            "end": 6.0,
            "duration": 6.0,
            "transition_in": "start",
            "beats": [1.5, 4.2],
            "base": {
                "label": "code_render",
                "confidence": 0.94,
                "decided_by": decided_by,
            },
            "narrative": {"role": "hook", "point": "Open on bold geographic anomaly."},
            "review": {
                "_by": "ai-directing-client",
                "description": "Dark bathymetric globe dive with crimson island fill.",
            }
            if reviewed
            else None,
            "motion": {
                "drawn": {
                    "colours": [
                        {"hex": "#f5c542", "share": 0.48},
                        {"hex": "#c2412d", "share": 0.32},
                    ]
                }
            },
            "material": {"has_real_material": False, "items": []},
            "assets": {"sheet": "shots/shot_001.jpg"},
        },
        {
            "id": "shot_002",
            "index": 2,
            "start": 6.0,
            "end": 18.0,
            "duration": 12.0,
            "transition_in": "dissolve",
            "transition": {"type": "dissolve", "start": 5.8, "end": 6.2, "duration": 0.4},
            "beats": [],
            "base": {
                "label": "ai_video" if ai_ratio >= 0.05 else "live_action",
                "confidence": 0.91,
                "decided_by": decided_by,
            },
            "narrative": {"role": "proof", "point": "Show aerial relief terrain evidence."},
            "review": {"_by": "ai-directing-client", "description": "Aerial mountain ridge."}
            if reviewed
            else None,
            "aspects": {"framing": {"measured": {"area": 0.25}}},
            "material": {"has_real_material": True, "items": [{"real_material": True}]},
            "assets": {"sheet": "shots/shot_002.jpg"},
        },
        {
            "id": "shot_003",
            "index": 3,
            "start": 18.0,
            "end": 26.0,
            "duration": 8.0,
            "transition_in": "fade",
            "transition": {"type": "fade", "start": 17.7, "end": 18.0, "duration": 0.3},
            "beats": [],
            "base": {
                "label": "code_render",
                "confidence": 0.89,
                "decided_by": decided_by,
            },
            "narrative": {"role": "cta", "point": "Close with understated end card."},
            "aspects": {"framing": {"measured": {"area": 0.36}}},
            "material": {"has_real_material": False, "items": []},
            "assets": {"sheet": "shots/shot_003.jpg"},
        },
    ]

    return {
        "schema": "2.0",
        "source": {
            "path": "/tmp/ref_clip.mp4",
            "filename": "ref_clip.mp4",
            "sha256_head": "a" * 64,
            "width": width,
            "height": height,
            "rotation": rotation,
            "fps": 30.0,
            "duration": 26.0,
            "has_audio": True,
        },
        "summary": {
            "duration": 26.0,
            "shots": len(shots),
            "verdict": "Mixed production: code / template render 45% + live action 55%",
            "production_mix": mix,
            "confidence": 0.92,
            "avg_shot_s": 8.67,
        },
        "shots": shots,
        "global_layers": {"frozen_ratio": 0.03, "boxes": [[0.82, 0.04, 0.14, 0.03]]},
        "aspects": {
            "editing": {
                "cuts_per_min": 4.6,
                "avg_shot_s": 8.67,
                "positions": 2,
                "jump_cuts": 0,
                "punch_ins": 1,
                "cuts_in_pauses": 0.78,
                "insert_share": 0.45,
                "beat_synced": True,
            },
            "grade": {
                "result": {"look": "dark and desaturated"},
                "measured": {
                    "sat": 0.24,
                    "contrast": 0.22,
                    "black": 5.2,
                    "white": 92.4,
                    "shadow_b": -6.8,
                    "highlight_b": 7.5,
                    "mean_l": 28.4,
                    "mean_b": -1.2,
                },
                "words": {"tone": "cool"},
            },
        },
        "audio": {
            "has_audio": True,
            "voice": {"present": True, "style": "speech"},
            "music": {
                "present": True,
                "tempo_bpm": None if no_beat else 94.0,
                "beat_strength": 0.12 if no_beat else 0.64,
                "no_beat": no_beat,
                "key": {"tonic": "D", "mode": "minor"},
                "section_changes": [8.5, 18.0],
            },
            "beat_synced_edit": True,
        },
        "audio_plan": {
            "sfx_merged": [
                {
                    "t": 6.0,
                    "type": "whoosh",
                    "in_scene": False,
                    "on": {"type": "cut"},
                    "confidence": "high",
                },
                {
                    "t": 18.0,
                    "type": "impact",
                    "in_scene": False,
                    "on": {"type": "title_in"},
                    "confidence": "high",
                },
            ]
        },
        "packaging": {
            "text_cues": [
                {
                    "id": "t01",
                    "kind": "subtitle",
                    "t0": 0.5,
                    "t1": 2.1,
                    "text": "Tectonic plates collide",
                    "band": "bottom",
                    "bbox": [0.22, 0.78, 0.56, 0.05],
                    "style": {"fill": "#f4f1ea", "stroke": "#03161f", "box": False},
                    "anim_in": {"kind": "cut"},
                },
                {
                    "id": "t02",
                    "kind": "subtitle",
                    "t0": 2.2,
                    "t1": 4.0,
                    "text": "deep beneath Sulawesi",
                    "band": "bottom",
                    "bbox": [0.24, 0.78, 0.52, 0.05],
                    "style": {"fill": "#f4f1ea", "stroke": "#03161f", "box": False},
                    "anim_in": {"kind": "cut"},
                },
                {
                    "id": "t03",
                    "kind": "subtitle",
                    "t0": 6.5,
                    "t1": 8.4,
                    "text": "forming four arms",
                    "band": "bottom",
                    "bbox": [0.26, 0.78, 0.48, 0.05],
                    "style": {"fill": "#f4f1ea", "stroke": "#03161f", "box": False},
                    "anim_in": {"kind": "cut"},
                },
                {
                    "id": "t04",
                    "kind": "title",
                    "t0": 0.2,
                    "t1": 25.8,
                    "text": "geoverum",
                    "band": "top",
                    "bbox": [0.80, 0.04, 0.16, 0.03],
                    "persistent": True,
                },
            ],
            "stickers": [],
            "sfx_alignment": {"sfx_on": {"cut": 1, "title_in": 1}},
        },
    }


def _make_minimal_probe(sha: str = "a" * 64) -> MediaProbeResult:
    return MediaProbeResult(
        path="/tmp/ref_clip.mp4",
        sha256=sha,
        file_bytes=4096000,
        container=ProbeContainerInfo(format_name="mp4", duration_s=26.0, bit_rate=4000000),
        video=ProbeVideoInfo(
            present=True,
            codec="h264",
            width=1080,
            height=1920,
            fps=30.0,
            is_cfr=True,
            pixel_format="yuv420p",
            color_space="bt709",
            color_primaries="bt709",
            color_trc="bt709",
            frame_count_est=780,
        ),
        audio=ProbeAudioInfo(
            present=True,
            codec="aac",
            sample_rate_hz=48000,
            channels=2,
            integrated_lufs=-14.1,
            lra=5.2,
            true_peak_dbtp=-1.2,
            silence_intervals=[],
            silence_ratio=0.12,
        ),
        shots=[
            ProbeShotSegment(
                shot_index=0, start_s=0.0, end_s=13.0, duration_s=13.0, confidence=0.9
            ),
            ProbeShotSegment(
                shot_index=1, start_s=13.0, end_s=26.0, duration_s=13.0, confidence=0.8
            ),
        ],
        shot_stats=ProbeShotStats(
            count=2, asl_p25_s=13.0, asl_p50_s=13.0, asl_p75_s=13.0, cuts_per_min=2.3
        ),
        visual=ProbeVisualInfo(
            sampled_frames=26,
            palette=[
                ProbePaletteColor(hex="#03161F", share=0.68, lab_l=7.0, lab_a=-4.0, lab_b=-8.0),
                ProbePaletteColor(hex="#F4F1EA", share=0.18, lab_l=95.0, lab_a=0.5, lab_b=3.0),
                ProbePaletteColor(hex="#F5C542", share=0.14, lab_l=82.0, lab_a=6.0, lab_b=68.0),
            ],
            palette_entropy=1.1,
            mean_luminance=28.0,
            band_luminance=ProbeBandLuminance(upper=24.0, center=32.0, lower_third=26.0),
            mean_sharpness=48.0,
            black_intervals=[],
            keyframes=[],
        ),
        timing_ms=ProbeTimingBreakdown(hash_ms=2, ffprobe_ms=8, stream_analyze_ms=20, total_ms=30),
    )


def test_video_breakdown_port_excludes_generative_remake_methods() -> None:
    public_methods = {m for m in dir(VideoBreakdownPort) if not m.startswith("_")}
    assert public_methods == {
        "provider_name",
        "survey",
        "analyze",
        "prepare_review",
        "apply_review",
        "load_breakdown",
    }


def test_rea_video_provider_blocks_generative_remake_subcommands() -> None:
    provider = ReaVideoBreakdownProvider()
    for forbidden in ("plan", "remake", "remake-run", "remake-plan", "drive", "capsule"):
        with pytest.raises(ValueError, match="forbidden by forensic-only policy"):
            provider._run_cli(forbidden, [])


def test_parse_rea_breakdown_validates_contract_and_extracts_signals(tmp_path: Path) -> None:
    (tmp_path / "VIDEO.md").write_text("# VIDEO\n", encoding="utf-8")
    (tmp_path / "storyboard.jpg").write_bytes(b"jpg")

    raw = _sample_raw_rea_breakdown(ai_ratio=0.15, reviewed=True)
    result = parse_rea_breakdown(raw, output_dir=tmp_path)

    errors = validate_against_contract(
        result.model_dump(exclude_none=True),
        "video_breakdown.schema.json",
    )
    assert errors == []
    assert result.aspect_ratio == "9:16"
    assert result.generative_reference_warning is True
    assert result.videomd_path == str((tmp_path / "VIDEO.md").resolve())
    assert "ai-directing-client" in result.reviewed_by
    assert result.audio.tempo_bpm == 94.0
    assert result.audio.key_mode == "minor"
    assert result.audio.sfx_aligned_to_visual_count == 2
    assert result.packaging.subtitle_count == 3
    assert result.packaging.caption_style_observed == "plain"
    assert result.packaging.caption_band_observed == "lower_third"
    assert result.packaging.caption_words_p75 == 3.0
    assert result.packaging.caption_fill_hex == "#F4F1EA"
    assert result.packaging.persistent_watermark_detected is True
    assert result.shots[0].narrative_role == "hook"
    assert result.shots[0].drawn_palette_hex == ["#F5C542", "#C2412D"]
    assert result.shots[1].transition_in == "dissolve"
    assert result.editing.cuts_in_pauses_ratio == 0.78
    assert result.editing.beat_synced_edit is True


def test_parse_rea_breakdown_handles_rotated_video_and_no_beat(tmp_path: Path) -> None:
    raw = _sample_raw_rea_breakdown(width=1920, height=1080, rotation=90, no_beat=True)
    result = parse_rea_breakdown(raw, output_dir=tmp_path)

    assert result.width == 1080
    assert result.height == 1920
    assert result.aspect_ratio == "9:16"
    assert result.audio.no_beat is True
    assert result.audio.tempo_bpm is None
    assert result.generative_reference_warning is False


def test_cli_breakdown_import_and_brand_analyze_fusion(tmp_path: Path) -> None:
    bd_dir = tmp_path / "bd_ref"
    bd_dir.mkdir()
    (bd_dir / "VIDEO.md").write_text("# VIDEO\n", encoding="utf-8")
    (bd_dir / "breakdown.json").write_text(
        json.dumps(_sample_raw_rea_breakdown(reviewed=True)),
        encoding="utf-8",
    )

    probe_file = tmp_path / "ref_clip.json"
    probe_file.write_text(_make_minimal_probe().model_dump_json(indent=2), encoding="utf-8")

    norm_out = tmp_path / "normalized_breakdown.json"
    policy_out = tmp_path / "brand_style_policy.json"
    playbook_out = tmp_path / "editorial_playbook.json"

    runner = CliRunner()
    imp = runner.invoke(app, ["breakdown", "import", str(bd_dir), "-o", str(norm_out)])
    assert imp.exit_code == 0, imp.output
    assert norm_out.is_file()

    syn = runner.invoke(
        app,
        [
            "brand",
            "analyze",
            "--brand-id",
            "forensic_brand",
            "--probe-file",
            str(probe_file),
            "--breakdown-file",
            str(bd_dir),
            "-o",
            str(policy_out),
            "--playbook-out",
            str(playbook_out),
        ],
    )
    assert syn.exit_code == 0, syn.output
    policy = json.loads(policy_out.read_text(encoding="utf-8"))
    playbook = json.loads(playbook_out.read_text(encoding="utf-8"))

    typo = policy["soft_priors"]["visual_tokens"]["typography"]
    assert policy["soft_priors"]["audio_style"]["bpm_range"] == [86.0, 102.0]
    assert typo["caption_style"] == "plain"
    assert typo["default_caption_band"] == "lower_third"
    assert typo["max_words_per_caption_group"] == 3
    assert any(t["trigger_id"] == "beat_aligned_cut_anchor" for t in playbook["grammar_triggers"])
