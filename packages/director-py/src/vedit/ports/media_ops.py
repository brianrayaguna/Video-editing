"""Capability port for deterministic/non-generative media preprocessing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable


class GenerativeVideoProhibitedError(RuntimeError):
    """Raised if any caller or provider attempts AI video generation."""


@dataclass(slots=True)
class MediaOpResult:
    provider: str
    operation: Literal[
        "clean_audio",
        "reframe",
        "remove_background",
        "trim",
        "remove_silence",
        "restore_footage",
    ]
    output_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MediaOpsPort(Protocol):
    """Non-generative media preprocessing interface.

    By design, AI video generation and synthetic avatar synthesis are excluded.
    """

    @property
    def provider_name(self) -> str: ...

    def clean_audio(
        self,
        speech_input: Path,
        output_path: Path,
        *,
        strength: float = 0.85,
    ) -> MediaOpResult: ...

    def reframe(
        self,
        video_input: Path,
        output_path: Path,
        *,
        target_aspect_ratio: Literal["9:16", "1:1", "4:5", "16:9"] = "9:16",
    ) -> MediaOpResult: ...

    def remove_background(
        self,
        video_input: Path,
        output_path: Path,
    ) -> MediaOpResult: ...

    def trim(
        self,
        video_input: Path,
        output_path: Path,
        *,
        start_s: float,
        end_s: float,
        accurate: bool = False,
    ) -> MediaOpResult: ...

    def remove_silence(
        self,
        speech_input: Path,
        output_path: Path,
        *,
        threshold_db: float = -40.0,
        min_silence_s: float = 0.45,
        padding_s: float = 0.12,
        crossfade_ms: int = 12,
        room_tone_db: float | None = None,
    ) -> MediaOpResult: ...

    def restore_footage(
        self,
        video_input: Path,
        output_path: Path,
        *,
        stabilize: bool = True,
        denoise: bool = True,
        deinterlace: bool = False,
    ) -> MediaOpResult: ...
