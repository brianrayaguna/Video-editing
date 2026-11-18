"""Tests for capability ports, provider registry, decision bounds, and checkpointing."""

from __future__ import annotations

from pathlib import Path

import pytest

from vedit.ports.decision import DecisionQuestion, ImageInput, validate_decision_batch
from vedit.ports.media_ops import MediaOpsPort
from vedit.providers.registry import ProviderNotFoundError, ProviderSpec, build_default_registry
from vedit.telemetry import JobCheckpoint, compute_idempotency_key


def test_registry_resolves_custom_capability_provider_without_core_changes() -> None:
    registry = build_default_registry()
    report = registry.status_report()
    assert set(report.keys()) == {"transcription", "decision", "media_ops", "audio_catalog"}

    class FakeSTT:
        @property
        def provider_name(self) -> str:
            return "fake_stt"

        def transcribe(self, media_path: Path, options=None):  # pragma: no cover - signature check
            raise AssertionError("Not called")

    registry.register(
        ProviderSpec(capability="transcription", name="fake_stt", factory=lambda _opts: FakeSTT())
    )
    resolved = registry.resolve("transcription", provider_name="fake_stt")
    assert resolved.provider_name == "fake_stt"

    with pytest.raises(ProviderNotFoundError):
        registry.resolve("transcription", provider_name="nonexistent")


def test_media_ops_port_excludes_generative_video_methods() -> None:
    public_methods = {m for m in dir(MediaOpsPort) if not m.startswith("_")}
    assert public_methods == {"provider_name", "clean_audio", "reframe", "remove_background"}


def test_decision_batch_bounds_enforce_one_image_for_box_questions() -> None:
    box_q = DecisionQuestion(name="face", question_type="box", instructions="Find speaker face")
    with pytest.raises(ValueError, match="exactly 1 image"):
        validate_decision_batch([box_q], [ImageInput(), ImageInput()])

    validate_decision_batch([box_q], [ImageInput()])

    many_qs = [
        DecisionQuestion(name=f"q{i}", question_type="noul", instructions="ok?")
        for i in range(129)
    ]
    with pytest.raises(ValueError, match="Too many questions"):
        validate_decision_batch(many_qs, [])


def test_job_checkpoint_records_telemetry_and_idempotency(tmp_path: Path) -> None:
    state_file = tmp_path / "job_state.json"
    ckpt = JobCheckpoint.load_or_create(
        state_file,
        job_id="job-1",
        project_id="proj-1",
        brand_id="brand-1",
        platform_target_id="shorts_9x16_1080p",
    )
    key = compute_idempotency_key(asset="abc", stage="probe")
    with ckpt.track_stage("probe", key, state_path=state_file, provider="rust_probe") as meta:
        meta["estimated_usd"] = 0.0012
        meta["output_artifacts"] = ["probe.json"]

    reloaded = JobCheckpoint.load_or_create(
        state_file,
        job_id="job-1",
        project_id="proj-1",
        brand_id="brand-1",
        platform_target_id="shorts_9x16_1080p",
    )
    assert reloaded.is_stage_done("probe", key) is True
    assert reloaded.total_estimated_usd == pytest.approx(0.0012)
