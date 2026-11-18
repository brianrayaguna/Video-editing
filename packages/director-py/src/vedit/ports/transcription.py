"""Capability port for speech-to-text transcription."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from vedit.models import NormalizedTranscript


@dataclass(slots=True)
class TranscriptionOptions:
    language: str | None = None
    diarize: bool = True
    include_fillers: bool = True
    keyterms: list[str] = field(default_factory=list)
    source_hash: str | None = None


@runtime_checkable
class TranscriptionPort(Protocol):
    """Provider-agnostic speech-to-text interface returning word-level timestamps."""

    @property
    def provider_name(self) -> str: ...

    def transcribe(
        self,
        media_path: Path,
        options: TranscriptionOptions | None = None,
    ) -> NormalizedTranscript: ...
