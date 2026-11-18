"""Capability port for licensed music and sound-effect catalog search/retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

VocalPolicy = Literal["NONE", "PRESENCE", "LEAD"]
AudioKind = Literal["music", "sfx"]


@dataclass(slots=True)
class AudioAssetResult:
    asset_id: str
    provider: str
    kind: AudioKind
    title: str
    duration_s: float
    bpm: float | None = None
    moods: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    vocal_type: VocalPolicy | None = None
    preview_url: str | None = None
    local_path: Path | None = None


@runtime_checkable
class AudioCatalogPort(Protocol):
    """Provider-agnostic semantic search and download interface for BGM and SFX."""

    @property
    def provider_name(self) -> str: ...

    def search_music(
        self,
        query: str,
        *,
        vocal_type: VocalPolicy | None = "NONE",
        bpm_range: tuple[int, int] | None = None,
        moods: list[str] | None = None,
        limit: int = 10,
    ) -> list[AudioAssetResult]: ...

    def search_sfx(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[AudioAssetResult]: ...

    def download_asset(
        self,
        asset_id: str,
        *,
        kind: AudioKind,
        destination_dir: Path,
        quality: Literal["normal", "high"] = "high",
    ) -> Path: ...
