"""Tests for extensible IdiomRegistry, domain idiom separation, and externalized audio themes."""

from __future__ import annotations

import json
from pathlib import Path

from vedit.director.idiom_registry import (
    DEFAULT_IDIOM_REGISTRY,
    IdiomRegistry,
    core_idiom_registry,
)
from vedit.director.storyboard import StoryboardIssue, check_storyboard
from vedit.geo.themes import load_audio_themes


def _minimal_storyboard() -> dict:
    return {
        "schema_version": "1.0",
        "project_id": "test_proj",
        "brand_id": "custom_brand",
        "duration_s": 6.0,
        "directing_source": "user",
        "story": {"shape": "question -> answer"},
        "beats": [
            {
                "beat_id": "b1",
                "start_s": 0.2,
                "end_s": 3.0,
                "clause": "Opening claim.",
                "function": "hook",
                "story_need": "Establish topic.",
                "device": "title_card",
            },
            {
                "beat_id": "b2",
                "start_s": 3.0,
                "end_s": 6.0,
                "clause": "Closing takeaway.",
                "function": "outro",
                "story_need": "Resolve claim.",
                "device": "stat_callout",
            },
        ],
    }


def test_custom_brand_idiom_runs_via_registry_without_editing_core() -> None:
    reg = core_idiom_registry()
    assert "hook_event_early" in reg.list_ids(domain="core")
    assert "head_on_place_name" not in reg.list_ids(domain="core")
    assert "head_on_place_name" in DEFAULT_IDIOM_REGISTRY.list_ids(domain="geo")

    def check_min_beats(idiom: dict, sb: dict, all_idioms: dict) -> list[StoryboardIssue]:
        del all_idioms
        need = int(idiom["params"]["min_beats"])
        if len(sb["beats"]) < need:
            return [StoryboardIssue(idiom["idiom_id"], idiom["severity"], f"need >= {need} beats")]
        return []

    custom_reg = IdiomRegistry(parent=reg)
    custom_reg.register("min_beat_count", check_min_beats, domain="custom")

    idioms = {
        "schema_version": "1.0",
        "brand_id": "custom_brand",
        "idioms": [
            {
                "idiom_id": "min_beat_count",
                "severity": "error",
                "weight": 0.9,
                "params": {"min_beats": 4},
            }
        ],
    }
    report = check_storyboard(_minimal_storyboard(), idioms, registry=custom_reg)
    assert report.passed is False
    assert any(i.idiom_id == "min_beat_count" for i in report.issues)


def test_load_audio_themes_supports_brand_override_file(tmp_path: Path) -> None:
    defaults = load_audio_themes()
    assert "maritime" in defaults and "geopolitics" in defaults

    brand_dir = tmp_path / "custom_brand"
    brand_dir.mkdir()
    (brand_dir / "audio_themes.json").write_text(
        json.dumps(
            {
                "finance": {
                    "keywords": ["inflation", "yield", "bond"],
                    "curious_query": "minimal piano investigative",
                    "tension_query": "tense pulse strings",
                    "ambience_query": "quiet room tone",
                    "ambience_gain_db": -30.0,
                    "foley": {},
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = load_audio_themes(brand_dir=brand_dir)
    assert "finance" in loaded
    assert loaded["finance"]["keywords"] == ("inflation", "yield", "bond")


def test_plan_and_fetch_thematic_audio_applies_brand_dir_override(tmp_path: Path) -> None:
    from vedit.geo_production import plan_and_fetch_thematic_audio

    brand_dir = tmp_path / "custom_brand"
    brand_dir.mkdir()
    (brand_dir / "audio_themes.json").write_text(
        json.dumps(
            {
                "orbital_doc": {
                    "keywords": ["perihelion", "lagrange"],
                    "curious_query": "deep space synth drone",
                    "tension_query": "dark orchestral pulse",
                    "ambience_query": "low frequency hum",
                    "ambience_gain_db": -26.0,
                    "foley": {},
                }
            }
        ),
        encoding="utf-8",
    )

    class _EmptyCatalog:
        def search(self, **_kwargs):  # type: ignore[no-untyped-def]
            return []

    scene = {"acts": [{"act_id": "a1", "duration_s": 5.0}]}
    transcript = {"text": "The spacecraft reached perihelion near the lagrange point."}
    out_dir = tmp_path / "audio_out"
    res = plan_and_fetch_thematic_audio(
        scene,
        transcript,
        out_dir,
        brand_dir=brand_dir,
        catalog=_EmptyCatalog(),
    )
    assert res["theme"] == "orbital_doc"
    assert res["ambience_gain_db"] == -26.0
