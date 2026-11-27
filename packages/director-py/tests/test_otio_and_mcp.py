"""Tests for OpenTimelineIO `.otio` export and FastMCP server tool registration."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

from vedit.interop.otio_bridge import export_edit_plan_to_otio
from vedit.mcp_server import create_mcp_server
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    EditPlan,
    OverlayCompositionOp,
    VideoClipOp,
)


def _sample_edit_plan() -> EditPlan:
    return EditPlan(
        job_id="otio_unit_job",
        project_id="otio_unit_proj",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=8.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(
                asset_id="shot_01",
                sha256="1" * 64,
                kind="video",
                path="media/maps/shot_01.mp4",
                duration_s=5.0,
            ),
            AssetRef(
                asset_id="shot_02",
                sha256="2" * 64,
                kind="video",
                path="media/broll/shot_02.mp4",
                duration_s=4.0,
            ),
            AssetRef(
                asset_id="vo_01",
                sha256="3" * 64,
                kind="audio_speech",
                path="media/audio/vo_clean.wav",
                duration_s=8.0,
                has_audio=True,
            ),
            AssetRef(
                asset_id="bgm_01",
                sha256="4" * 64,
                kind="audio_bgm",
                path="media/audio/bgm.wav",
                duration_s=8.0,
                has_audio=True,
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="clip_01",
                asset_id="shot_01",
                timeline_start_s=0.0,
                timeline_duration_s=4.0,
                source_start_s=0.5,
                role="a_roll",
            ),
            VideoClipOp(
                clip_id="clip_02",
                asset_id="shot_02",
                timeline_start_s=4.0,
                timeline_duration_s=4.0,
                source_start_s=0.0,
                role="b_roll",
                transition_in="clean_crossfade",
            ),
        ],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="cap_01",
                kind="caption_rail",
                timeline_start_s=0.5,
                timeline_duration_s=2.0,
                props={"text": "First caption line"},
            ),
            OverlayCompositionOp(
                overlay_id="metric_01",
                kind="data_card",
                timeline_start_s=4.2,
                timeline_duration_s=2.5,
                template_id="tabular_metric",
                variables={"value": "1,143 km"},
            ),
        ],
        audio_tracks=[
            AudioTrackOp(
                track_id="trk_vo",
                asset_id="vo_01",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=8.0,
                source_start_s=0.0,
                cleaned_speech_stem=True,
            ),
            AudioTrackOp(
                track_id="trk_bgm",
                asset_id="bgm_01",
                audio_group="music",
                timeline_start_s=0.0,
                timeline_duration_s=8.0,
                source_start_s=0.0,
                gain_db=-12.0,
                carve_against_group="voiceover",
                carve_strength=0.75,
            ),
        ],
        verifier_passed=True,
    )


@pytest.mark.skipif(
    importlib.util.find_spec("opentimelineio") is None,
    reason="Optional opentimelineio extra not installed.",
)
def test_export_edit_plan_to_otio_round_trip(tmp_path: Path) -> None:
    import opentimelineio as otio

    plan = _sample_edit_plan()
    out_otio = tmp_path / "output" / "timeline.otio"
    written = export_edit_plan_to_otio(plan, out_otio)
    assert written.is_file()

    loaded = otio.adapters.read_from_file(str(written))
    assert loaded.name == "otio_unit_job"
    assert loaded.metadata["vedit"]["brand_id"] == "geoverum"

    track_names = [t.name for t in loaded.tracks]
    assert track_names == ["Video_Main", "Audio_voiceover", "Audio_music"]
    assert len(loaded.video_tracks()[0]) == 2
    assert len(loaded.tracks.markers) == 2
    assert loaded.tracks.markers[0].name == "cap_01"
    assert loaded.tracks.markers[1].name == "metric_01"


@pytest.mark.skipif(
    importlib.util.find_spec("opentimelineio") is None,
    reason="Optional opentimelineio extra not installed.",
)
def test_export_otio_preserves_program_mix_and_splits_overlapping_sfx(tmp_path: Path) -> None:
    import opentimelineio as otio

    plan = _sample_edit_plan().model_copy(
        update={
            "audio_tracks": [
                AudioTrackOp(
                    track_id="mix_main",
                    asset_id="a_vo",
                    audio_group="program_mix",
                    timeline_start_s=0.0,
                    timeline_duration_s=8.0,
                    source_start_s=0.0,
                    gain_db=0.0,
                    cleaned_speech_stem=True,
                ),
                AudioTrackOp(
                    track_id="sfx_1",
                    asset_id="a_bgm",
                    audio_group="sfx",
                    timeline_start_s=1.0,
                    timeline_duration_s=2.0,
                    source_start_s=0.0,
                    gain_db=-6.0,
                ),
                AudioTrackOp(
                    track_id="sfx_2",
                    asset_id="a_bgm",
                    audio_group="sfx",
                    timeline_start_s=1.5,
                    timeline_duration_s=1.5,
                    source_start_s=0.0,
                    gain_db=-6.0,
                ),
            ]
        }
    )
    out_otio = tmp_path / "program_mix.otio"
    export_edit_plan_to_otio(plan, out_otio)
    loaded = otio.adapters.read_from_file(str(out_otio))
    track_names = [t.name for t in loaded.tracks]
    assert "Audio_program_mix" in track_names
    assert "Audio_sfx" in track_names
    assert "Audio_sfx_2" in track_names


@pytest.mark.skipif(
    importlib.util.find_spec("opentimelineio") is None,
    reason="Optional opentimelineio extra not installed.",
)
def test_export_otio_preserves_ambience_and_room_tone(tmp_path: Path) -> None:
    import opentimelineio as otio

    plan = _sample_edit_plan().model_copy(
        update={
            "audio_tracks": [
                AudioTrackOp(
                    track_id="amb_1",
                    asset_id="a_bgm",
                    audio_group="ambience",
                    timeline_start_s=0.0,
                    timeline_duration_s=4.0,
                    source_start_s=0.0,
                    gain_db=-24.0,
                ),
                AudioTrackOp(
                    track_id="rt_1",
                    asset_id="a_bgm",
                    audio_group="room_tone",
                    timeline_start_s=0.0,
                    timeline_duration_s=8.0,
                    source_start_s=0.0,
                    gain_db=-45.0,
                ),
            ]
        }
    )
    out_otio = tmp_path / "ambience_room_tone.otio"
    export_edit_plan_to_otio(plan, out_otio)
    loaded = otio.adapters.read_from_file(str(out_otio))
    track_names = [t.name for t in loaded.tracks]
    assert "Audio_ambience" in track_names
    assert "Audio_room_tone" in track_names


@pytest.mark.skipif(
    importlib.util.find_spec("fastmcp") is None,
    reason="Optional fastmcp extra not installed.",
)
def test_fastmcp_server_registers_thin_control_plane_tools() -> None:
    server = create_mcp_server()
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "project_init",
        "project_status",
        "project_validate",
        "contracts_validate",
        "director_verify",
        "compile_plan",
        "audit_deliverable",
        "export_otio",
        "cloud_render",
        "storyboard_readiness",
        "storyboard_context",
        "storyboard_gate_prerender",
        "critique_apply_fixes",
        "brand_memory_record",
    }
    assert expected.issubset(tool_names)


@pytest.mark.skipif(
    importlib.util.find_spec("fastmcp") is None,
    reason="Optional fastmcp extra not installed.",
)
def test_fastmcp_new_directing_tools_and_memory_isolation(tmp_path: Path) -> None:
    import json

    from vedit.contracts import find_repo_root

    server = create_mcp_server()
    tools_by_name = {t.name: t for t in asyncio.run(server.list_tools())}

    sb_path = tmp_path / "sb.json"
    sb_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": "mcp_demo",
                "brand_id": "geoverum",
                "duration_s": 4.0,
                "directing_source": "auto",
                "pacing": "dense",
                "story": {"shape": "journey_chain"},
                "overrides": {},
                "beats": [
                    {
                        "beat_id": "b1",
                        "start_s": 0.0,
                        "end_s": 2.0,
                        "clause": "In 1998 Chile counted 27 crossings.",
                        "function": "hook",
                        "story_need": "show year and numeral",
                        "device": "numeral",
                        "sync_word": "27",
                        "sync_word_s": 0.5,
                    },
                    {
                        "beat_id": "b2",
                        "start_s": 2.0,
                        "end_s": 4.0,
                        "clause": "Then walked north to Alaska.",
                        "function": "outro",
                        "story_need": "draw closing route",
                        "device": "route_draw",
                        "sync_word": "Alaska",
                        "sync_word_s": 2.5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="external workspace isolation"):
        tools_by_name["brand_memory_record"].fn(
            brand_id="geoverum",
            storyboard_file=str(sb_path),
            projects_root=str(find_repo_root()),
        )

    ext_root = tmp_path / "projects_root"
    res = tools_by_name["brand_memory_record"].fn(
        brand_id="geoverum",
        storyboard_file=str(sb_path),
        projects_root=str(ext_root),
    )
    assert res["recent_episodes"] == 1
    assert Path(res["path"]).is_file()

    tr_path = tmp_path / "tr.json"
    tr_path.write_text(
        json.dumps(
            {
                "source_hash": "mcp1234",
                "provider": "test",
                "language": "en",
                "duration_s": 4.0,
                "text": "In 1998 Chile counted 27 crossings.",
                "words": [
                    {"text": "In", "start_s": 0.0, "end_s": 0.3},
                    {"text": "1998", "start_s": 0.35, "end_s": 0.8},
                    {"text": "Chile", "start_s": 0.85, "end_s": 1.3},
                    {"text": "counted", "start_s": 1.35, "end_s": 1.8},
                    {"text": "27", "start_s": 1.85, "end_s": 2.3},
                    {"text": "crossings.", "start_s": 2.35, "end_s": 2.9},
                ],
            }
        ),
        encoding="utf-8",
    )
    readiness = tools_by_name["storyboard_readiness"].fn(
        transcript_file=str(tr_path),
        brand_id="geoverum",
    )
    assert readiness["ready"] is True

    ctx = tools_by_name["storyboard_context"].fn(
        storyboard_file=str(sb_path),
        brand_id="geoverum",
        memory_file=res["path"],
    )
    assert ctx["brand_id"] == "geoverum"

    gate = tools_by_name["storyboard_gate_prerender"].fn(
        storyboard_file=str(sb_path),
        brand_id="geoverum",
        min_score=70.0,
    )
    assert gate["passed"] is True

    packet_path = tmp_path / "packet.json"
    packet_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "iteration": 1,
                "max_iterations": 3,
                "frozen_beat_ids": [],
                "deterministic": {},
                "sheets": [],
                "review": {
                    "instructions": "score",
                    "scores": {},
                    "fixes": [{"beat_id": "b1", "kind": "timing"}],
                    "rubric": [],
                },
            }
        ),
        encoding="utf-8",
    )
    fixed_out = tmp_path / "fixed_sb.json"
    applied = tools_by_name["critique_apply_fixes"].fn(
        storyboard_file=str(sb_path),
        packet_file=str(packet_path),
        out_file=str(fixed_out),
    )
    assert fixed_out.is_file()
    assert len(applied["applied"]) == 1
