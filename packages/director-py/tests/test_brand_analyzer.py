"""Tests for multi-reference BrandStylePolicy synthesis, exemplars, and calibration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vedit.analyzers.brand_analyzer import (
    ReferenceVideoSample,
    query_exemplars,
    record_calibration_feedback,
    synthesize_brand_artifacts,
    synthesize_brand_policy,
)
from vedit.contracts import validate_against_contract
from vedit.metrics import wcag_contrast_ratio
from vedit.models import (
    MediaProbeResult,
    NormalizedTranscript,
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
from vedit.ports.decision import DecisionAnswer, DecisionBatchResult, DecisionQuestion, ImageInput


def _make_probe(
    *,
    sha: str,
    shot_durations: list[float],
    kf_paths: list[Path],
    mean_luma: float = 38.0,
) -> MediaProbeResult:
    shots: list[ProbeShotSegment] = []
    keyframes: list[ProbeKeyframeInfo] = []
    t = 0.0
    for idx, dur in enumerate(shot_durations):
        end = round(t + dur, 3)
        shots.append(
            ProbeShotSegment(shot_index=idx, start_s=t, end_s=end, duration_s=dur, confidence=0.92)
        )
        if idx < len(kf_paths):
            keyframes.append(
                ProbeKeyframeInfo(
                    timestamp_s=round(t + dur * 0.5, 3),
                    shot_index=idx,
                    path=str(kf_paths[idx]),
                    luma_lower_third=mean_luma,
                    sharpness=45.0 + idx * 5.0,
                )
            )
        t = end

    total_dur = max(t, 1.0)
    cuts_per_min = (max(len(shot_durations) - 1, 1) / total_dur) * 60.0
    ordered = sorted(shot_durations)
    return MediaProbeResult(
        path=f"/tmp/{sha[:8]}.mp4",
        sha256=sha,
        file_bytes=2048000,
        container=ProbeContainerInfo(
            format_name="mov,mp4,m4a", duration_s=total_dur, bit_rate=4000
        ),
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
            frame_count_est=int(total_dur * 30),
        ),
        audio=ProbeAudioInfo(
            present=True,
            codec="aac",
            sample_rate_hz=48000,
            channels=2,
            integrated_lufs=-14.2,
            lra=5.4,
            true_peak_dbtp=-1.3,
            silence_intervals=[],
            silence_ratio=0.14,
        ),
        shots=shots,
        shot_stats=ProbeShotStats(
            count=len(shots),
            asl_p25_s=ordered[0],
            asl_p50_s=ordered[len(ordered) // 2],
            asl_p75_s=ordered[-1],
            cuts_per_min=round(cuts_per_min, 2),
        ),
        visual=ProbeVisualInfo(
            sampled_frames=len(shots),
            palette=[
                ProbePaletteColor(hex="#0F172A", share=0.58, lab_l=9.0, lab_a=2.0, lab_b=-12.0),
                ProbePaletteColor(hex="#38BDF8", share=0.22, lab_l=72.0, lab_a=-18.0, lab_b=-36.0),
                ProbePaletteColor(hex="#F8FAFC", share=0.20, lab_l=98.0, lab_a=0.0, lab_b=-2.0),
            ],
            palette_entropy=1.35,
            mean_luminance=mean_luma,
            band_luminance=ProbeBandLuminance(upper=40.0, center=55.0, lower_third=32.0),
            mean_sharpness=52.0,
            black_intervals=[],
            keyframes=keyframes,
        ),
        timing_ms=ProbeTimingBreakdown(hash_ms=4, ffprobe_ms=12, stream_analyze_ms=34, total_ms=50),
    )


def test_synthesize_multi_reference_policy_and_exemplars(tmp_path: Path) -> None:
    kf1 = tmp_path / "kf1.jpg"
    kf2 = tmp_path / "kf2.jpg"
    kf1.write_bytes(b"jpg-1")
    kf2.write_bytes(b"jpg-2")

    p1 = _make_probe(sha="a" * 64, shot_durations=[1.2, 1.8, 2.4, 2.1, 1.4, 2.0], kf_paths=[kf1])
    p2 = _make_probe(sha="b" * 64, shot_durations=[1.0, 2.2, 3.0, 2.6, 1.8, 2.5], kf_paths=[kf2])
    transcript = NormalizedTranscript(
        source_hash="a" * 64,
        provider="xai",
        language="en",
        duration_s=10.9,
        text="Revenue grew 42% this quarter.",
        words=[
            TranscriptWord(text="Revenue", start_s=0.1, end_s=0.5),
            TranscriptWord(text="grew", start_s=0.6, end_s=0.9),
            TranscriptWord(text="42%", start_s=1.0, end_s=1.5),
            TranscriptWord(text="this", start_s=1.6, end_s=1.9),
            TranscriptWord(text="quarter.", start_s=2.0, end_s=2.6),
        ],
    )

    synthesized = synthesize_brand_artifacts(
        "tech_explainer",
        [
            ReferenceVideoSample(source_video_id="ref_one", probe=p1, transcript=transcript),
            ReferenceVideoSample(source_video_id="ref_two", probe=p2),
        ],
    )
    policy = synthesized.policy
    playbook = synthesized.playbook

    assert validate_against_contract(
        policy.model_dump(exclude_none=True), "brand_style_policy.schema.json"
    ) == []
    assert validate_against_contract(
        playbook.model_dump(exclude_none=True), "editorial_playbook.schema.json"
    ) == []
    assert "grammar_triggers" not in policy.model_dump()
    assert "exemplar_bank" not in policy.model_dump()
    assert policy.provenance.reference_video_count == 2
    assert policy.provenance.reference_hashes == ["a" * 64, "b" * 64]
    assert playbook.grammar_triggers
    assert playbook.exemplar_bank

    palette = policy.soft_priors.visual_tokens.palette_roles
    assert wcag_contrast_ratio(palette.ink, palette.ground) >= 4.5
    for prior in policy.soft_priors.temporal_curve:
        assert 0 < prior.asl_p25_s <= prior.asl_p50_s <= prior.asl_p75_s

    hook_exemplars = query_exemplars(playbook, role="hook")
    assert len(hook_exemplars) >= 1
    assert hook_exemplars[0].hyperframes_pattern == "kinetic_hook_title"
    assert "duration_s" in hook_exemplars[0].measured_metrics


def test_brand_analyzer_decision_enrichment_caps_images_at_eight(tmp_path: Path) -> None:
    class FakeDecisionPort:
        def __init__(self) -> None:
            self.seen_images = 0

        @property
        def provider_name(self) -> str:
            return "fake_decision"

        def evaluate(
            self,
            *,
            state: dict[str, Any] | str,
            questions: list[DecisionQuestion],
            images: list[ImageInput] | None = None,
        ) -> DecisionBatchResult:
            self.seen_images = len(images or [])
            return DecisionBatchResult(
                provider=self.provider_name,
                model="fake-d1",
                input_tokens=200,
                answers={
                    "motion_feel": DecisionAnswer(
                        "motion_feel", "choice", {"choice": "energetic_pop"}
                    ),
                    "caption_case": DecisionAnswer("caption_case", "choice", {"choice": "title"}),
                    "editorial_tone": DecisionAnswer(
                        "editorial_tone", "text", {"text": "High-contrast analytical storytelling"}
                    ),
                },
            )

    samples: list[ReferenceVideoSample] = []
    for idx in range(6):
        kfs: list[Path] = []
        for j in range(2):
            kf = tmp_path / f"ref_{idx}_{j}.jpg"
            kf.write_bytes(b"img")
            kfs.append(kf)
        probe = _make_probe(sha=f"{idx}" * 64, shot_durations=[2.5, 3.0], kf_paths=kfs)
        samples.append(ReferenceVideoSample(source_video_id=f"ref_{idx}", probe=probe))

    fake_port = FakeDecisionPort()
    policy = synthesize_brand_policy("multi_ref_brand", samples, decision_port=fake_port)

    assert fake_port.seen_images == 8
    assert policy.soft_priors.visual_tokens.motion_style.easing_feel == "energetic_pop"
    assert policy.soft_priors.visual_tokens.typography.caption_case == "title"
    assert policy.editorial_identity == "High-contrast analytical storytelling"
    assert policy.provenance.confidence >= 0.85


def test_calibration_feedback_updates_and_validates(tmp_path: Path) -> None:
    kf = tmp_path / "kf.jpg"
    kf.write_bytes(b"img")
    probe = _make_probe(sha="c" * 64, shot_durations=[2.0, 2.5, 3.0], kf_paths=[kf])
    policy = synthesize_brand_policy(
        "calibrated_brand",
        [ReferenceVideoSample(source_video_id="ref_cal", probe=probe)],
    )
    updated = record_calibration_feedback(
        policy, accepted_override=True, rejected_pattern="split_metric_card"
    )
    assert updated.calibration is not None
    assert updated.calibration.accepted_overrides == 1
    assert "split_metric_card" in updated.calibration.rejected_patterns
