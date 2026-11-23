"""Tests for EditPlan synthesis (`build_edit_plan`) and guardrail verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vedit.analyzers.brand_analyzer import ReferenceVideoSample, synthesize_brand_policy
from vedit.contracts import load_platform_targets
from vedit.director.planner import build_edit_plan
from vedit.director.verifier import verify_edit_plan
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    BoundingBox,
    BrandStylePolicy,
    EditPlan,
    MediaProbeResult,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
    ProbeAudioInfo,
    ProbeBandLuminance,
    ProbeContainerInfo,
    ProbeKeyframeInfo,
    ProbePaletteColor,
    ProbeShotSegment,
    ProbeShotStats,
    ProbeTimingBreakdown,
    ProbeVideoInfo,
    ProbeVisualInfo,
    TranscriptWord,
)
from vedit.ports.audio_catalog import AudioAssetResult
from vedit.ports.decision import DecisionAnswer, DecisionBatchResult, DecisionQuestion, ImageInput


def _build_fixture_bundle(tmp_path: Path) -> tuple[
    MediaProbeResult, BrandStylePolicy, PlatformTarget, NormalizedTranscript
]:
    kf = tmp_path / "frame.jpg"
    kf.write_bytes(b"jpeg-placeholder")
    probe = MediaProbeResult(
        path=str(tmp_path / "source.mp4"),
        sha256="d" * 64,
        file_bytes=4096000,
        container=ProbeContainerInfo(format_name="mov,mp4,m4a", duration_s=10.0, bit_rate=5000),
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
            frame_count_est=300,
        ),
        audio=ProbeAudioInfo(
            present=True,
            codec="aac",
            sample_rate_hz=48000,
            channels=2,
            integrated_lufs=-16.0,
            lra=5.0,
            true_peak_dbtp=-1.5,
            silence_intervals=[],
            silence_ratio=0.18,
        ),
        shots=[
            ProbeShotSegment(
                shot_index=0, start_s=0.0, end_s=3.5, duration_s=3.5, confidence=0.95
            ),
            ProbeShotSegment(
                shot_index=1, start_s=3.5, end_s=7.0, duration_s=3.5, confidence=0.95
            ),
            ProbeShotSegment(
                shot_index=2, start_s=7.0, end_s=10.0, duration_s=3.0, confidence=0.95
            ),
        ],
        shot_stats=ProbeShotStats(
            count=3, asl_p25_s=3.0, asl_p50_s=3.5, asl_p75_s=3.5, cuts_per_min=18.0
        ),
        visual=ProbeVisualInfo(
            sampled_frames=3,
            palette=[
                ProbePaletteColor(hex="#0B0F19", share=0.65, lab_l=6.0, lab_a=1.0, lab_b=-10.0),
                ProbePaletteColor(hex="#38BDF8", share=0.20, lab_l=70.0, lab_a=-16.0, lab_b=-34.0),
                ProbePaletteColor(hex="#F8FAFC", share=0.15, lab_l=98.0, lab_a=0.0, lab_b=-1.0),
            ],
            palette_entropy=1.2,
            mean_luminance=42.0,
            band_luminance=ProbeBandLuminance(upper=45.0, center=60.0, lower_third=38.0),
            mean_sharpness=64.0,
            black_intervals=[],
            keyframes=[
                ProbeKeyframeInfo(
                    timestamp_s=1.75,
                    shot_index=0,
                    path=str(kf),
                    luma_lower_third=38.0,
                    sharpness=64.0,
                ),
                ProbeKeyframeInfo(
                    timestamp_s=5.25,
                    shot_index=1,
                    path=str(kf),
                    luma_lower_third=38.0,
                    sharpness=64.0,
                ),
                ProbeKeyframeInfo(
                    timestamp_s=8.50,
                    shot_index=2,
                    path=str(kf),
                    luma_lower_third=38.0,
                    sharpness=64.0,
                ),
            ],
        ),
        timing_ms=ProbeTimingBreakdown(hash_ms=3, ffprobe_ms=8, stream_analyze_ms=20, total_ms=31),
    )

    transcript = NormalizedTranscript(
        source_hash="d" * 64,
        provider="xai",
        language="en",
        duration_s=10.0,
        text="Retention reached 85% across four launches.",
        words=[
            TranscriptWord(text="Retention", start_s=0.2, end_s=1.1),
            TranscriptWord(text="reached", start_s=1.2, end_s=1.9),
            TranscriptWord(text="85%", start_s=3.7, end_s=4.5),
            TranscriptWord(text="across", start_s=4.6, end_s=5.3),
            TranscriptWord(text="four", start_s=7.2, end_s=7.8),
            TranscriptWord(text="launches.", start_s=8.0, end_s=9.2),
        ],
    )

    policy = synthesize_brand_policy(
        "creator_test", [ReferenceVideoSample(source_video_id="ref_a", probe=probe)]
    )
    platforms = load_platform_targets()
    target = PlatformTarget.model_validate(platforms["reels_9x16_1080p"])
    return probe, policy, target, transcript


def test_build_edit_plan_avoids_subject_boxes_and_passes_verifier(tmp_path: Path) -> None:
    class SpatialMockDecision:
        @property
        def provider_name(self) -> str:
            return "mock_decision"

        def evaluate(
            self,
            *,
            state: dict[str, Any] | str,
            questions: list[DecisionQuestion],
            images: list[ImageInput] | None = None,
        ) -> DecisionBatchResult:
            assert len(images or []) == 1
            return DecisionBatchResult(
                provider=self.provider_name,
                model="mock-box",
                input_tokens=150,
                answers={
                    "subject_boxes": DecisionAnswer(
                        "subject_boxes",
                        "boxes",
                        {
                            "boxes": [
                                {
                                    "top": 0.65,
                                    "bottom": 0.90,
                                    "left": 0.15,
                                    "right": 0.85,
                                    "label": "speaker",
                                }
                            ]
                        },
                    )
                },
            )

    class MockCatalog:
        @property
        def provider_name(self) -> str:
            return "mock_catalog"

        def search_music(self, query: str, *, vocal_type: str = "NONE", limit: int = 10):
            return [
                AudioAssetResult(
                    asset_id="track_991122334455",
                    provider="mock_catalog",
                    kind="music",
                    title="Focused Pulse",
                    duration_s=30.0,
                    preview_url="https://cdn.example/bgm.mp3",
                )
            ]

        def search_sfx(self, query: str, *, limit: int = 10):
            return []

        def download_asset(self, asset_id: str, *, kind: str, destination_dir: Path, **kwargs):
            return destination_dir / f"{asset_id}.mp3"

    probe, policy, target, transcript = _build_fixture_bundle(tmp_path)
    plan, report = build_edit_plan(
        job_id="job_01",
        project_id="proj_01",
        probe=probe,
        policy=policy,
        platform_target=target,
        transcript=transcript,
        decision_port=SpatialMockDecision(),
        audio_catalog=MockCatalog(),
    )

    assert report.passed is True, f"Unexpected verification failures: {report.errors}"
    assert plan.verifier_passed is True
    assert any(ov.safe_band == "upper_safe" for ov in plan.overlay_compositions)
    assert any(
        tr.audio_group == "music" and tr.carve_against_group == "voiceover"
        for tr in plan.audio_tracks
    )


def test_verifier_catches_all_hard_guardrails(tmp_path: Path) -> None:
    probe, policy, target, transcript = _build_fixture_bundle(tmp_path)
    plan, report = build_edit_plan(
        job_id="job_02",
        project_id="proj_02",
        probe=probe,
        policy=policy,
        platform_target=target,
        transcript=transcript,
    )
    assert report.passed is True

    # Build a corrupted clone exercising each hard guardrail failure.
    bad_clips = [
        plan.video_tracks[0].model_copy(
            update={
                "timeline_duration_s": 0.25,
                "transition_in": "flash_white_strobe",
                "reframed_to_target": False,
                "subject_safe_boxes": [
                    BoundingBox(top=0.72, bottom=0.90, left=0.15, right=0.85, label="face")
                ],
            }
        ),
        plan.video_tracks[1].model_copy(
            update={"timeline_start_s": 0.25, "timeline_duration_s": 9.5}
        ),
    ]
    # Add clip slicing straight inside word "85%" [3.7, 4.5] to test keyword cut guard.
    split_clips = [
        bad_clips[0].model_copy(update={"timeline_duration_s": 4.1}),
        bad_clips[1].model_copy(
            update={
                "timeline_start_s": 4.1,
                "source_start_s": 4.1,
                "timeline_duration_s": 5.9,
            }
        ),
    ]
    # Trigger all overlay and audio guardrail violations cleanly on the corrupt clone.
    bad_overlays = [
        OverlayCompositionOp(
            overlay_id="ov_bad",
            kind="data_card",
            timeline_start_s=0.1,
            timeline_duration_s=2.0,
            transparent=True,
            safe_band="lower_third",
            props={
                "pattern": "heavy_css_blur_glass",
                "backdropFilter": "blur(16px)",
                "fg_color": "#777777",
                "bg_color": "#666666",
                "box": {"top": 0.02, "bottom": 0.85, "left": 0.1, "right": 0.95},
            },
        )
    ]
    bad_assets = [
        *plan.assets,
        AssetRef(
            asset_id="bgm_bad",
            sha256="f" * 64,
            kind="audio_bgm",
            path="https://cdn.example/bgm.mp3",
            duration_s=30.0,
        ),
    ]
    bad_audio = [
        *plan.audio_tracks,
        AudioTrackOp(
            track_id="bgm_un_carved",
            asset_id="bgm_bad",
            audio_group="music",
            timeline_start_s=0.0,
            timeline_duration_s=5.0,
            source_start_s=0.0,
            gain_db=2.0,
            carve_against_group=None,
            carve_strength=0.0,
        ),
    ]

    corrupt_plan = EditPlan(
        schema_version="1.0",
        job_id="bad_job",
        project_id="proj_02",
        brand_id=policy.brand_id,
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=10.0,
        fps=24.0,  # mismatch against 30 fps target
        width=1920,  # mismatch against 1080x1920 target
        height=1080,
        assets=bad_assets,
        video_tracks=split_clips,
        overlay_compositions=bad_overlays,
        audio_tracks=bad_audio,
    )

    bad_report = verify_edit_plan(corrupt_plan, policy, target, transcript=transcript)
    codes = {issue.code for issue in bad_report.errors}
    expected_codes = {
        "PLATFORM_CANVAS_MISMATCH",
        "PLATFORM_FPS_MISMATCH",
        "BANNED_TRANSITION",
        "UNREFRAMED_SOURCE_CLIP",
        "CUT_WITHIN_KEYWORD_WINDOW",
        "BANNED_PATTERN",
        "HEAVY_CSS_BLUR",
        "LOW_WCAG_CONTRAST",
        "OUTSIDE_PLATFORM_SAFE_ZONE",
        "SUBJECT_BOX_OVERLAP",
        "MUSIC_MISSING_VO_CARVE",
        "MUSIC_GAIN_EXCEEDS_VO",
    }
    assert bad_report.passed is False
    assert expected_codes.issubset(codes)

    # Also explicitly verify BELOW_MIN_SHOT_DURATION and EXCEEDS_MAX_HOLD_DURATION.
    tiny_and_long = corrupt_plan.model_copy(
        update={
            "video_tracks": [
                plan.video_tracks[0].model_copy(update={"timeline_duration_s": 0.22}),
                plan.video_tracks[1].model_copy(
                    update={
                        "timeline_start_s": 0.22,
                        "source_start_s": 0.22,
                        "timeline_duration_s": 9.7,
                    }
                ),
            ]
        }
    )
    pace_codes = {i.code for i in verify_edit_plan(tiny_and_long, policy, target).errors}
    assert "BELOW_MIN_SHOT_DURATION" in pace_codes
    assert "EXCEEDS_MAX_HOLD_DURATION" in pace_codes


def test_planner_hold_cap_and_clause_caption_grouping_and_geoverum_formats(tmp_path: Path) -> None:
    from vedit.contracts import find_repo_root, load_brand_template_catalog
    from vedit.director.templates import resolve_effective_policy
    from vedit.models import BrandTemplateCatalog

    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    gv_policy = BrandStylePolicy.model_validate_json(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8")
    )
    gv_catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(gv_dir / "templates" / "catalog.json", repo_root=root)
    )
    platforms = load_platform_targets()
    shorts_target = PlatformTarget.model_validate(platforms["shorts_9x16_1080p"])
    yt_target = PlatformTarget.model_validate(platforms["youtube_16x9_1080p"])

    eff_9x16 = resolve_effective_policy(gv_policy, shorts_target)
    eff_16x9 = resolve_effective_policy(gv_policy, yt_target)
    assert eff_9x16.hard_guardrails.max_uninterrupted_hold_s == 45.0
    assert eff_16x9.hard_guardrails.max_uninterrupted_hold_s == 20.0

    # Long single 65s shot must be subdivided strictly <= max_uninterrupted_hold_s.
    probe, _, _, _ = _build_fixture_bundle(tmp_path)
    long_probe = probe.model_copy(
        update={
            "container": probe.container.model_copy(update={"duration_s": 65.0}),
            "shots": [
                ProbeShotSegment(
                    shot_index=0,
                    start_s=0.0,
                    end_s=65.0,
                    duration_s=65.0,
                    confidence=0.99,
                )
            ],
        }
    )
    transcript = NormalizedTranscript(
        source_hash="d" * 64,
        provider="xai",
        language="en",
        duration_s=65.0,
        text="Three tectonic plates, colliding slowly, formed 42 percent of Sulawesi.",
        words=[
            TranscriptWord(text="Three", start_s=0.2, end_s=0.5),
            TranscriptWord(text="tectonic", start_s=0.55, end_s=0.95),
            TranscriptWord(text="plates,", start_s=1.0, end_s=1.4),
            TranscriptWord(text="colliding", start_s=2.0, end_s=2.4),
            TranscriptWord(text="slowly,", start_s=2.45, end_s=2.9),
            TranscriptWord(text="formed", start_s=3.4, end_s=3.7),
            TranscriptWord(text="42", start_s=3.75, end_s=4.0),
            TranscriptWord(text="percent", start_s=4.05, end_s=4.4),
            TranscriptWord(text="of", start_s=4.45, end_s=4.6),
            TranscriptWord(text="Sulawesi.", start_s=4.65, end_s=5.1),
        ],
    )

    plan_9x16, report_9x16 = build_edit_plan(
        job_id="job_gv_9x16",
        project_id="proj_gv",
        probe=long_probe,
        policy=gv_policy,
        platform_target=shorts_target,
        transcript=transcript,
        template_catalog=gv_catalog,
    )
    assert report_9x16.passed is True, f"9:16 errors: {report_9x16.errors}"
    assert all(
        c.timeline_duration_s <= eff_9x16.hard_guardrails.max_uninterrupted_hold_s + 0.01
        for c in plan_9x16.video_tracks
    )
    assert all(c.role == "a_roll" for c in plan_9x16.video_tracks)
    # Plain caption style within policy max_words_per_caption_group, no amber_fact_card on 9:16.
    max_words = eff_9x16.soft_priors.visual_tokens.typography.max_words_per_caption_group
    captions = [ov for ov in plan_9x16.overlay_compositions if ov.kind == "caption_rail"]
    assert len(captions) >= 3
    for cap in captions:
        words = str(cap.props.get("text", "")).split()
        assert 1 <= len(words) <= max_words
        assert cap.props.get("caption_style") == "plain"
        # Captions fade in over a few frames and cut out hard.
        assert cap.props.get("caption_fade_in_ms") == 130
        assert cap.props.get("caption_fade_out_ms") == 0
    assert not any(ov.template_id == "amber_fact_card" for ov in plan_9x16.overlay_compositions)

    # On 16:9, amber_fact_card is eligible for numeric phrases and keeps amber ground/ink tokens.
    plan_16x9, report_16x9 = build_edit_plan(
        job_id="job_gv_16x9",
        project_id="proj_gv",
        probe=long_probe,
        policy=gv_policy,
        platform_target=yt_target,
        transcript=transcript,
        template_catalog=gv_catalog,
    )
    assert report_16x9.passed is True, f"16:9 errors: {report_16x9.errors}"
    amber_cards = [
        ov for ov in plan_16x9.overlay_compositions if ov.template_id == "amber_fact_card"
    ]
    assert amber_cards, "Expected amber_fact_card on 16:9 documentary plan"
    assert amber_cards[0].variables is not None
    assert amber_cards[0].variables["bg_color"] == "#F5C542"
    assert amber_cards[0].variables["fg_color"] == "#03161F"


def test_verifier_detects_violet_scale_zero_collision_and_allows_corner_watermark(
    tmp_path: Path,
) -> None:
    from vedit.contracts import find_repo_root, load_brand_template_catalog
    from vedit.models import BrandTemplateCatalog

    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    gv_policy = BrandStylePolicy.model_validate_json(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8")
    )
    gv_catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(gv_dir / "templates" / "catalog.json", repo_root=root)
    )
    probe, _, target, transcript = _build_fixture_bundle(tmp_path)
    plan, report = build_edit_plan(
        job_id="job_v_checks",
        project_id="proj_v",
        probe=probe,
        policy=gv_policy,
        platform_target=target,
        transcript=transcript,
    )
    assert report.passed is True

    # Corner watermark in upper-right slightly down (top=0.16, bottom=0.20, left=0.72, right=0.945)
    # should pass safe-zone validation cleanly.
    wm_plan = plan.model_copy(
        update={
            "overlay_compositions": [
                OverlayCompositionOp(
                    overlay_id="wm_ok",
                    kind="lower_third",
                    template_id="broadcast_bug",
                    timeline_start_s=0.0,
                    timeline_duration_s=5.0,
                    transparent=True,
                    safe_band="upper_safe",
                    variables={"text": "geoverum", "opacity": 0.72, "fg_color": "#F4F1EA"},
                    props={
                        "text": "geoverum",
                        "box": {"top": 0.16, "bottom": 0.20, "left": 0.72, "right": 0.945},
                    },
                )
            ]
        }
    )
    wm_report = verify_edit_plan(wm_plan, gv_policy, target, template_catalog=gv_catalog)
    assert wm_report.passed is True, f"Watermark should pass: {wm_report.errors}"

    # Violet accent, scale_zero_pop_in, and colliding overlays must all be caught.
    bad_plan = plan.model_copy(
        update={
            "overlay_compositions": [
                OverlayCompositionOp(
                    overlay_id="ov_violet",
                    kind="data_card",
                    timeline_start_s=1.0,
                    timeline_duration_s=2.0,
                    transparent=True,
                    safe_band="upper_safe",
                    variables={"accent_color": "#A855F7"},
                    props={"custom_timeline_js": "tl.from('#el', { scale: 0, duration: 0.3 })"},
                ),
                OverlayCompositionOp(
                    overlay_id="ov_collide",
                    kind="data_card",
                    timeline_start_s=1.5,
                    timeline_duration_s=2.0,
                    transparent=True,
                    safe_band="upper_safe",
                    props={"headline": "Overlapping card"},
                ),
            ]
        }
    )
    bad_report = verify_edit_plan(bad_plan, gv_policy, target)
    codes = {i.code for i in bad_report.errors}
    assert "BANNED_PATTERN" in codes
    assert "OVERLAY_COLLISION" in codes


def test_verifier_map_content_type_visual_beats_program_mix_and_caption_glow() -> None:
    from vedit.contracts import find_repo_root, load_brand_template_catalog
    from vedit.models import BrandTemplateCatalog, VideoClipOp

    root = find_repo_root()
    policy = BrandStylePolicy.model_validate_json(
        (root / "profiles" / "brands" / "geoverum" / "brand_style_policy.json").read_text(
            encoding="utf-8"
        )
    )
    catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(
            root / "profiles" / "brands" / "geoverum" / "templates" / "catalog.json",
            repo_root=root,
        )
    )
    target = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])
    transcript = NormalizedTranscript(
        source_hash="a" * 64,
        provider="xai",
        language="en",
        duration_s=12.0,
        text="the isthmus",
        words=[
            TranscriptWord(text="the", start_s=2.95, end_s=3.08, confidence=0.99),
            TranscriptWord(text="isthmus", start_s=3.10, end_s=3.60, confidence=0.99),
        ],
    )
    plan = EditPlan(
        schema_version="1.0",
        job_id="map_doc_job",
        project_id="proj_map",
        brand_id=policy.brand_id,
        platform_target_id=target.platform_id,
        render_strategy="hybrid",
        duration_s=12.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(
                asset_id="map_a",
                sha256="a" * 64,
                kind="video",
                path="media/maps/act1.mp4",
                duration_s=12.0,
                has_audio=False,
            ),
            AssetRef(
                asset_id="mix_a",
                sha256="b" * 64,
                kind="audio_speech",
                path="media/audio/mix.wav",
                duration_s=12.0,
                has_audio=True,
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="m1",
                asset_id="map_a",
                timeline_start_s=0.0,
                timeline_duration_s=3.0,
                source_start_s=0.0,
                role="a_roll",
                content_type="map",
                visual_beat_count=3,
                reframed_to_target=True,
            ),
            VideoClipOp(
                clip_id="m2",
                asset_id="map_a",
                timeline_start_s=3.0,
                timeline_duration_s=9.0,
                source_start_s=3.0,
                role="b_roll",
                content_type="landscape",
                visual_beat_count=5,
                reframed_to_target=True,
            ),
        ],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="cap_glow",
                kind="caption_rail",
                template_id="caption_rail",
                timeline_start_s=0.5,
                timeline_duration_s=2.0,
                transparent=True,
                safe_band="lower_third",
                props={
                    "text": "The isthmus",
                    "caption_shadow_blur_px": 10,
                    "caption_glow_px": 14,
                    "caption_glow_color": "#F5C542",
                },
            )
        ],
        audio_tracks=[
            AudioTrackOp(
                track_id="mix",
                asset_id="mix_a",
                audio_group="program_mix",
                timeline_start_s=0.0,
                timeline_duration_s=12.0,
                source_start_s=0.0,
                gain_db=0.0,
                cleaned_speech_stem=True,
            )
        ],
    )
    report = verify_edit_plan(
        plan,
        policy,
        target,
        transcript=transcript,
        template_catalog=catalog,
    )
    assert report.passed is True, f"Errors: {report.errors}"
    warn_codes = {w.code for w in report.warnings}
    assert "MISSING_SUBJECT_BOX_GROUNDING" not in warn_codes
    assert "HEAVY_CSS_BLUR" not in {e.code for e in report.errors}
    assert "CUT_WITHIN_KEYWORD_WINDOW" not in {e.code for e in report.errors}


def test_verifier_rejects_inverted_overlay_box_and_unsupported_template_aspect(
    tmp_path: Path,
) -> None:
    from vedit.contracts import find_repo_root, load_brand_template_catalog, load_platform_targets
    from vedit.models import BrandTemplateCatalog, VideoClipOp

    root = find_repo_root()
    gv_dir = root / "profiles" / "brands" / "geoverum"
    policy = BrandStylePolicy.model_validate_json(
        (gv_dir / "brand_style_policy.json").read_text(encoding="utf-8")
    )
    catalog = BrandTemplateCatalog.model_validate(
        load_brand_template_catalog(gv_dir / "templates" / "catalog.json", repo_root=root)
    )
    shorts = PlatformTarget.model_validate(load_platform_targets()["shorts_9x16_1080p"])

    plan = EditPlan(
        job_id="verify_aspect_and_box",
        project_id="proj_check",
        brand_id="geoverum",
        platform_target_id=shorts.platform_id,
        render_strategy="hybrid",
        duration_s=6.0,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(asset_id="v1", sha256="a" * 64, kind="video", path="a.mp4", duration_s=6.0),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="c1",
                asset_id="v1",
                timeline_start_s=0.0,
                timeline_duration_s=6.0,
                source_start_s=0.0,
                role="a_roll",
                content_type="map",
                reframed_to_target=True,
            )
        ],
        overlay_compositions=[
            OverlayCompositionOp(
                overlay_id="bad_box",
                kind="kinetic_callout",
                timeline_start_s=0.5,
                timeline_duration_s=2.0,
                transparent=True,
                safe_band="center_safe",
                props={
                    "text": "Inverted",
                    "box": {"top": 0.7, "bottom": 0.2, "left": 0.7, "right": 0.2},
                },
            ),
            OverlayCompositionOp(
                overlay_id="wrong_aspect",
                kind="data_card",
                template_id="amber_fact_card",
                timeline_start_s=3.0,
                timeline_duration_s=2.0,
                transparent=True,
                safe_band="lower_third",
                variables={"number": "1803", "text": "Wrong aspect"},
                props={},
            ),
        ],
        audio_tracks=[],
    )
    report = verify_edit_plan(plan, policy, shorts, template_catalog=catalog)
    err_codes = {e.code for e in report.errors}
    assert report.passed is False
    assert "INVALID_OVERLAY_BOX" in err_codes
    assert "TEMPLATE_VARIABLE_INVALID" in err_codes
