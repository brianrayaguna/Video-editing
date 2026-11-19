"""JSON Schema contract and Pydantic model round-trip tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from vedit.contracts import (
    find_repo_root,
    load_platform_targets,
    validate_against_contract,
    validate_all_brand_trees,
    validate_brand_tree,
)
from vedit.models import (
    BrandStylePolicy,
    EditorialPlaybook,
    EditPlan,
    NormalizedTranscript,
    PlatformTarget,
)


def test_all_platform_presets_validate_against_schema_and_model() -> None:
    presets = load_platform_targets()
    expected = {
        "youtube_16x9_1080p",
        "youtube_16x9_4k",
        "shorts_9x16_1080p",
        "reels_9x16_1080p",
        "tiktok_9x16_1080p",
    }
    assert expected.issubset(presets.keys())
    for pid, payload in presets.items():
        model = PlatformTarget.model_validate(payload)
        assert model.platform_id == pid
        assert model.audio.target_lufs == -14.0
        assert model.audio.max_true_peak_dbtp <= -1.0
        assert model.video.color_space == "bt709"


def test_geoverum_brand_template_catalog_validates() -> None:
    path = find_repo_root() / "profiles" / "brands" / "geoverum" / "templates" / "catalog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_against_contract(
        payload,
        "brand_template.schema.json",
        repo_root=find_repo_root(),
    )
    assert errors == []
    assert payload["brand_id"] == "geoverum"
    assert len(payload["templates"]) >= 1


def test_geoverum_runtime_policy_omits_advisory_fields() -> None:
    """Checked-in Geoverum policy is runtime-only; playbook holds advisory fields."""
    path = find_repo_root() / "profiles" / "brands" / "geoverum" / "brand_style_policy.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "grammar_triggers" not in payload
    assert "exemplar_bank" not in payload
    model = BrandStylePolicy.model_validate(payload)
    assert "grammar_triggers" not in BrandStylePolicy.model_fields
    assert "exemplar_bank" not in BrandStylePolicy.model_fields
    errors = validate_against_contract(
        model.model_dump(exclude_none=True),
        "brand_style_policy.schema.json",
        repo_root=find_repo_root(),
    )
    assert errors == []


def test_geoverum_editorial_playbook_validates() -> None:
    path = find_repo_root() / "profiles" / "brands" / "geoverum" / "editorial_playbook.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_against_contract(
        payload,
        "editorial_playbook.schema.json",
        repo_root=find_repo_root(),
    )
    assert errors == []
    playbook = EditorialPlaybook.model_validate(payload)
    assert playbook.brand_id == "geoverum"
    assert len(playbook.grammar_triggers) >= 1
    assert len(playbook.exemplar_bank) >= 1


def test_geoverum_brand_tree_validates() -> None:
    root = find_repo_root()
    result = validate_brand_tree(root / "profiles" / "brands" / "geoverum", repo_root=root)
    assert result["brand_id"] == "geoverum"
    assert result["playbook"] is not None
    assert result["templates"] is not None
    assert validate_all_brand_trees(repo_root=root)


def test_brand_style_policy_rejects_advisory_fields() -> None:
    sample = {
        "schema_version": "1.0",
        "brand_id": "sample-creator",
        "display_name": "Sample Creator",
        "editorial_identity": (
            "Analytical tech storytelling with brisk hooks and breathing body shots."
        ),
        "soft_priors": {
            "temporal_curve": [
                {
                    "section": "hook",
                    "asl_p25_s": 0.9,
                    "asl_p50_s": 1.4,
                    "asl_p75_s": 1.9,
                    "cuts_per_min_range": [28, 45],
                    "energy_target": 0.85,
                    "preferred_transitions": ["hard_cut", "j_cut"],
                },
                {
                    "section": "body",
                    "asl_p25_s": 2.1,
                    "asl_p50_s": 3.2,
                    "asl_p75_s": 4.8,
                    "cuts_per_min_range": [12, 22],
                    "energy_target": 0.55,
                    "preferred_transitions": ["hard_cut", "l_cut"],
                },
            ],
            "visual_tokens": {
                "palette_roles": {
                    "ground": "#0D1117",
                    "ink": "#F0F6FC",
                    "accent": "#2F81F7",
                },
                "typography": {
                    "display_family": "Space Grotesk",
                    "body_family": "Inter",
                    "caption_case": "sentence",
                    "max_words_per_caption_group": 5,
                    "default_caption_band": "dynamic_away_from_subject",
                },
                "motion_style": {
                    "easing_feel": "snappy_ease_out",
                    "entrance_ms_range": [160, 280],
                    "punch_in_scale_range": [1.06, 1.12],
                },
            },
            "audio_style": {
                "bgm_moods": ["minimal_pulse", "focused_electronic"],
                "bpm_range": [105, 128],
                "ducking_strength": 0.8,
                "sfx_policy": "selective_transitions",
            },
        },
        "grammar_triggers": [
            {
                "trigger_id": "numeric_claim_callout",
                "condition": "spoken sentence states a quantified metric or percentage",
                "action": "insert data_card overlay in safe band without cutting speech",
                "weight": 0.85,
            }
        ],
        "hard_guardrails": {
            "min_shot_duration_s": 0.7,
            "max_uninterrupted_hold_s": 9.0,
            "no_cut_within_keyword_ms": 180,
            "never_overlap_subject_boxes": True,
            "min_wcag_contrast": 4.5,
            "banned_transitions": ["spin_3d", "star_wipe"],
            "banned_patterns": ["bouncy_emoji_captions"],
            "avoid_heavy_css_blur": True,
        },
        "calibration": {
            "accepted_overrides": 0,
            "rejected_patterns": [],
        },
        "provenance": {
            "reference_video_count": 3,
            "reference_hashes": ["deadbeef12345678"],
            "confidence": 0.86,
        },
    }
    with pytest.raises(ValidationError):
        BrandStylePolicy.model_validate(sample)
    errors = validate_against_contract(
        sample,
        "brand_style_policy.schema.json",
        repo_root=find_repo_root(),
    )
    assert errors


def test_brand_style_policy_round_trip() -> None:
    sample = {
        "schema_version": "1.0",
        "brand_id": "sample-creator",
        "display_name": "Sample Creator",
        "editorial_identity": (
            "Analytical tech storytelling with brisk hooks and breathing body shots."
        ),
        "soft_priors": {
            "temporal_curve": [
                {
                    "section": "hook",
                    "asl_p25_s": 0.9,
                    "asl_p50_s": 1.4,
                    "asl_p75_s": 1.9,
                    "cuts_per_min_range": [28, 45],
                    "energy_target": 0.85,
                    "preferred_transitions": ["hard_cut", "j_cut"],
                },
                {
                    "section": "body",
                    "asl_p25_s": 2.1,
                    "asl_p50_s": 3.2,
                    "asl_p75_s": 4.8,
                    "cuts_per_min_range": [12, 22],
                    "energy_target": 0.55,
                    "preferred_transitions": ["hard_cut", "l_cut"],
                },
            ],
            "visual_tokens": {
                "palette_roles": {
                    "ground": "#0D1117",
                    "ink": "#F0F6FC",
                    "accent": "#2F81F7",
                },
                "typography": {
                    "display_family": "Space Grotesk",
                    "body_family": "Inter",
                    "caption_case": "sentence",
                    "max_words_per_caption_group": 5,
                    "default_caption_band": "dynamic_away_from_subject",
                },
                "motion_style": {
                    "easing_feel": "snappy_ease_out",
                    "entrance_ms_range": [160, 280],
                    "punch_in_scale_range": [1.06, 1.12],
                },
            },
            "audio_style": {
                "bgm_moods": ["minimal_pulse", "focused_electronic"],
                "bpm_range": [105, 128],
                "ducking_strength": 0.8,
                "sfx_policy": "selective_transitions",
            },
        },
        "hard_guardrails": {
            "min_shot_duration_s": 0.7,
            "max_uninterrupted_hold_s": 9.0,
            "no_cut_within_keyword_ms": 180,
            "never_overlap_subject_boxes": True,
            "min_wcag_contrast": 4.5,
            "banned_transitions": ["spin_3d", "star_wipe"],
            "banned_patterns": ["bouncy_emoji_captions"],
            "avoid_heavy_css_blur": True,
        },
        "calibration": {
            "accepted_overrides": 0,
            "rejected_patterns": [],
        },
        "provenance": {
            "reference_video_count": 3,
            "reference_hashes": ["deadbeef12345678"],
            "confidence": 0.86,
        },
    }
    model = BrandStylePolicy.model_validate(sample)
    errors = validate_against_contract(
        model.model_dump(exclude_none=True),
        "brand_style_policy.schema.json",
        repo_root=find_repo_root(),
    )
    assert errors == []


def test_transcript_and_edit_plan_contracts() -> None:
    transcript_data = {
        "source_hash": "a1b2c3d4e5f67890",
        "provider": "mock-stt",
        "language": "id",
        "duration_s": 4.0,
        "text": "Halo semua.",
        "words": [
            {"text": "Halo", "start_s": 0.1, "end_s": 0.4, "speaker": 0, "is_filler": False},
            {"text": "semua.", "start_s": 0.45, "end_s": 0.9, "speaker": 0, "is_filler": False},
        ],
    }
    t_model = NormalizedTranscript.model_validate(transcript_data)
    t_errors = validate_against_contract(
        t_model.model_dump(exclude_none=True),
        "transcript.schema.json",
    )
    assert t_errors == []

    plan_data = {
        "schema_version": "1.0",
        "job_id": "job-001",
        "project_id": "proj-001",
        "brand_id": "sample-creator",
        "platform_target_id": "youtube_16x9_1080p",
        "render_strategy": "hybrid",
        "duration_s": 4.0,
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "assets": [
            {
                "asset_id": "aroll-1",
                "sha256": "0123456789abcdef0123456789abcdef",
                "kind": "video",
                "path": "assets/aroll.mp4",
                "duration_s": 4.0,
                "has_audio": True,
            }
        ],
        "video_tracks": [
            {
                "clip_id": "v1",
                "asset_id": "aroll-1",
                "timeline_start_s": 0.0,
                "timeline_duration_s": 4.0,
                "source_start_s": 0.0,
                "role": "a_roll",
                "reframed_to_target": True,
                "scale": 1.0,
                "transition_in": None,
                "subject_safe_boxes": [
                    {"top": 0.1, "bottom": 0.85, "left": 0.35, "right": 0.65, "label": "speaker"}
                ],
            }
        ],
        "overlay_compositions": [
            {
                "overlay_id": "cap-1",
                "kind": "caption_rail",
                "timeline_start_s": 0.1,
                "timeline_duration_s": 0.85,
                "transparent": True,
                "safe_band": "lower_third",
                "template_id": "caption_rail",
                "variables": {"text": "Halo semua.", "fg_color": "#F0F6FC", "bg_color": "#0D1117"},
                "props": {"text": "Halo semua."},
            }
        ],
        "audio_tracks": [
            {
                "track_id": "vo-1",
                "asset_id": "aroll-1",
                "audio_group": "voiceover",
                "timeline_start_s": 0.0,
                "timeline_duration_s": 4.0,
                "source_start_s": 0.0,
                "gain_db": 0.0,
                "carve_against_group": None,
                "carve_strength": 0.8,
                "cleaned_speech_stem": True,
            }
        ],
        "verifier_passed": True,
    }
    p_model = EditPlan.model_validate(plan_data)
    assert p_model.overlay_compositions[0].template_id == "caption_rail"
    p_errors = validate_against_contract(
        p_model.model_dump(exclude_none=True),
        "edit_plan.schema.json",
    )
    assert p_errors == []


def test_geoverum_two_documentary_formats_and_brand_tree_integrity(tmp_path) -> None:
    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    policy = BrandStylePolicy.model_validate_json(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8")
    )
    assert policy.soft_priors.visual_tokens.typography.caption_style == "plain"
    assert policy.soft_priors.visual_tokens.typography.max_words_per_caption_group == 3
    assert policy.format_overrides is not None
    assert "9:16" in policy.format_overrides
    assert "16:9" in policy.format_overrides
    assert policy.format_overrides["9:16"].watermark_default is False
    assert policy.format_overrides["16:9"].watermark_default is False

    # Copy geoverum brand tree to tmp and break composition_path -> validate_brand_tree must fail.
    broken_dir = tmp_path / "broken_brand"
    (broken_dir / "templates").mkdir(parents=True)
    (broken_dir / "brand_style_policy.json").write_text(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    bad_catalog = json.loads(
        (gv_dir / "templates" / "catalog.json").read_text(encoding="utf-8")
    )
    bad_catalog["templates"][0]["composition_path"] = (
        "profiles/brands/geoverum/templates/components/nonexistent_tpl.html"
    )
    (broken_dir / "templates" / "catalog.json").write_text(
        json.dumps(bad_catalog),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing composition_path"):
        validate_brand_tree(broken_dir, repo_root=root)

    # Break token_ref -> validate_brand_tree must fail.
    bad_token_catalog = json.loads(
        (gv_dir / "templates" / "catalog.json").read_text(encoding="utf-8")
    )
    bad_token_catalog["templates"][0]["variables"][1]["token_ref"] = "palette_roles.nonexistent"
    (broken_dir / "templates" / "catalog.json").write_text(
        json.dumps(bad_token_catalog),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unresolved policy token_ref"):
        validate_brand_tree(broken_dir, repo_root=root)
