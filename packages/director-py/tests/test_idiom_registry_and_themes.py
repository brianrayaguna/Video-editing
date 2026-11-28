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


def test_geoverum_audio_themes_override_loads_and_validates(tmp_path: Path) -> None:
    import pytest
    from typer.testing import CliRunner

    from vedit.cli import app
    from vedit.contracts import find_repo_root, validate_brand_tree
    from vedit.geo_production import plan_and_fetch_thematic_audio

    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    themes = load_audio_themes(brand_dir=gv_dir)
    assert "time_and_systems" in themes
    assert "aviation" in themes
    validated = validate_brand_tree(gv_dir, repo_root=root)
    assert validated["audio_themes"] == "profiles/brands/geoverum/audio_themes.json"

    # Malformed audio_themes.json fails validate_brand_tree loudly.
    broken = tmp_path / "broken_brand"
    broken.mkdir()
    (broken / "brand_style_policy.json").write_text(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (broken / "audio_themes.json").write_text('{"bad_theme": {"keywords": []}}', encoding="utf-8")
    with pytest.raises(ValueError, match="audio_themes.json"):
        validate_brand_tree(broken, repo_root=root)

    # Invalid JSON and invalid foley/ambience_gain_db also fail validate_brand_tree cleanly.
    (broken / "audio_themes.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="audio_themes.json"):
        validate_brand_tree(broken, repo_root=root)

    (broken / "audio_themes.json").write_text(
        json.dumps(
            {
                "bad_types": {
                    "keywords": ["orbit"],
                    "curious_query": "synth",
                    "tension_query": "pulse",
                    "ambience_query": "hum",
                    "ambience_gain_db": "loud",
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ambience_gain_db"):
        validate_brand_tree(broken, repo_root=root)

    (broken / "audio_themes.json").write_text(
        json.dumps(
            {
                "bad_foley": {
                    "keywords": ["orbit"],
                    "curious_query": "synth",
                    "tension_query": "pulse",
                    "ambience_query": "hum",
                    "foley": {"ping": ["only_one_item"]},
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="foley"):
        validate_brand_tree(broken, repo_root=root)

    # Minimal valid audio_themes.json (omitting optional foley/ambience_gain_db) must validate
    # AND succeed at runtime in plan_and_fetch_thematic_audio without KeyError.
    minimal = tmp_path / "minimal_brand"
    minimal.mkdir()
    (minimal / "brand_style_policy.json").write_text(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (minimal / "audio_themes.json").write_text(
        json.dumps(
            {
                "maritime": {
                    "keywords": ["harbor", "vessel", "port", "ship"],
                    "curious_query": "maritime curiosity",
                    "tension_query": "maritime tension",
                    "ambience_query": "ocean wind",
                }
            }
        ),
        encoding="utf-8",
    )
    assert validate_brand_tree(minimal, repo_root=root)["audio_themes"] is not None

    class _EmptyCatalog:
        def search(self, **_kwargs):  # type: ignore[no-untyped-def]
            return []

    min_scene = {
        "acts": [
            {
                "act_id": "a1",
                "duration_s": 4.0,
                "kind": "cutaway_2d",
                "preset": "port_cutaway",
                "layers": [
                    {
                        "type": "map_sprites",
                        "start_s": 0.5,
                        "sprites": [{"kind": "cargo_ship"}] * 3,
                    }
                ],
            }
        ]
    }
    min_plan = plan_and_fetch_thematic_audio(
        min_scene,
        {"text": "The vessel entered the harbor."},
        tmp_path / "min_out",
        brand_dir=minimal,
        catalog=_EmptyCatalog(),
    )
    assert min_plan["ok"] is True
    assert min_plan["theme"] == "maritime"
    assert min_plan["ambience_gain_db"] == -28.0

    # CLI execution: invalid --brand / traversal / missing --brand-dir fail loudly; valid
    # --brand geoverum resolves Geoverum's time_and_systems theme end-to-end.
    runner = CliRunner()
    scene_file = tmp_path / "scene.json"
    tr_file = tmp_path / "tr.json"
    scene_file.write_text(
        json.dumps({"acts": [{"act_id": "a1", "duration_s": 5.0}]}),
        encoding="utf-8",
    )
    tr_file.write_text(
        json.dumps({"text": "Why do UTC time zone meridian offsets look so jagged?"}),
        encoding="utf-8",
    )

    bad_brand = runner.invoke(
        app,
        [
            "geo",
            "auto-audio",
            "--scene-file",
            str(scene_file),
            "--out-dir",
            str(tmp_path / "bad_out"),
            "--brand",
            "nonexistent_brand_xyz",
        ],
    )
    assert bad_brand.exit_code != 0

    trav_brand = runner.invoke(
        app,
        [
            "geo",
            "auto-audio",
            "--scene-file",
            str(scene_file),
            "--out-dir",
            str(tmp_path / "trav_out"),
            "--brand",
            "../platforms",
        ],
    )
    assert trav_brand.exit_code != 0

    bad_dir = runner.invoke(
        app,
        [
            "geo",
            "auto-audio",
            "--scene-file",
            str(scene_file),
            "--out-dir",
            str(tmp_path / "baddir_out"),
            "--brand-dir",
            str(tmp_path / "does_not_exist"),
        ],
    )
    assert bad_dir.exit_code != 0

    ok_res = runner.invoke(
        app,
        [
            "geo",
            "auto-audio",
            "--scene-file",
            str(scene_file),
            "--transcript",
            str(tr_file),
            "--out-dir",
            str(tmp_path / "gv_out"),
            "--brand",
            "geoverum",
        ],
    )
    assert ok_res.exit_code == 0, ok_res.output
    cli_payload = json.loads(ok_res.output)
    assert cli_payload["ok"] is True
    assert cli_payload["theme"] == "time_and_systems"
