"""Built-in provider registration manifest."""

from __future__ import annotations

from vedit.providers.audio_catalog.epidemic import EpidemicAudioCatalogProvider
from vedit.providers.decision.liquid_d1 import LiquidDecisionProvider
from vedit.providers.geo_imagery import GoogleTilesImageryProvider, OpenImageryProvider
from vedit.providers.media_ops.ffmpeg_local import FfmpegMediaOpsProvider
from vedit.providers.media_ops.modal_cloud import ModalCloudMediaOpsProvider
from vedit.providers.registry import ProviderRegistry, ProviderSpec
from vedit.providers.video_breakdown.rea_video import ReaVideoBreakdownProvider


def register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register capability provider descriptors without coupling core modules to vendors."""
    specs = [
        ProviderSpec(
            capability="decision",
            name="liquid_d1",
            factory=lambda opts: LiquidDecisionProvider(opts),
            implemented=True,
            description="Omnimodal calibrated decision, span extraction, and spatial box adapter.",
        ),
        ProviderSpec(
            capability="media_ops",
            name="modal_cloud",
            factory=lambda opts: ModalCloudMediaOpsProvider(opts),
            implemented=True,
            description=(
                "Modal serverless CPU speech denoising (DeepFilterNet) and aspect-ratio reframing."
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
        ProviderSpec(
            capability="geo_imagery",
            name="google_tiles",
            factory=lambda opts: GoogleTilesImageryProvider(opts),
            implemented=True,
            description=(
                "Google Map Tiles API 2D satellite imagery (z0-z18, highDpi, cached sessions)."
            ),
        ),
        ProviderSpec(
            capability="geo_imagery",
            name="open_imagery",
            factory=lambda opts: OpenImageryProvider(opts),
            implemented=True,
            description=(
                "Open-licensed USGS National Map orthoimagery and Sentinel-2 cloudless fallback."
            ),
        ),
        ProviderSpec(
            capability="video_breakdown",
            name="rea_video",
            factory=lambda opts: ReaVideoBreakdownProvider(opts),
            implemented=True,
            description=(
                "Local forensic video breakdown adapter (non-generative analysis, OCR packaging, "
                "audio BPM/SFX, and visual review)."
            ),
        ),
    ]
    for spec in specs:
        registry.register(spec)
