"""Built-in provider registration manifest."""

from __future__ import annotations

from vedit.providers.audio_catalog.epidemic import EpidemicAudioCatalogProvider
from vedit.providers.decision.liquid_d1 import LiquidDecisionProvider
from vedit.providers.media_ops.ffmpeg_local import FfmpegMediaOpsProvider
from vedit.providers.media_ops.veed import VeedMediaOpsProvider
from vedit.providers.registry import ProviderRegistry, ProviderSpec
from vedit.providers.transcription.veed import VeedTranscriptionProvider
from vedit.providers.transcription.xai import XaiTranscriptionProvider


def register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register capability provider descriptors without coupling core modules to vendors."""
    specs = [
        ProviderSpec(
            capability="transcription",
            name="xai",
            factory=lambda opts: XaiTranscriptionProvider(opts),
            implemented=True,
            description=(
                "REST speech-to-text adapter with word timestamps, diarization, and keyterms."
            ),
        ),
        ProviderSpec(
            capability="transcription",
            name="veed",
            factory=lambda opts: VeedTranscriptionProvider(opts),
            implemented=True,
            description="VEED hosted transcription adapter using OpenEdit OAuth credentials.",
        ),
        ProviderSpec(
            capability="decision",
            name="liquid_d1",
            factory=lambda opts: LiquidDecisionProvider(opts),
            implemented=True,
            description="Omnimodal calibrated decision, span extraction, and spatial box adapter.",
        ),
        ProviderSpec(
            capability="media_ops",
            name="veed",
            factory=lambda opts: VeedMediaOpsProvider(opts),
            implemented=True,
            description=(
                "VEED OpenEdit OAuth background-removal adapter (non-generative)."
            ),
        ),
        ProviderSpec(
            capability="media_ops",
            name="ffmpeg",
            factory=lambda opts: FfmpegMediaOpsProvider(opts),
            implemented=True,
            description="Local deterministic FFmpeg speech denoising and aspect-ratio reframing.",
        ),
        ProviderSpec(
            capability="audio_catalog",
            name="epidemic",
            factory=lambda opts: EpidemicAudioCatalogProvider(opts),
            implemented=True,
            description="Semantic music and sound-effect catalog search/download adapter.",
        ),
    ]
    for spec in specs:
        registry.register(spec)
