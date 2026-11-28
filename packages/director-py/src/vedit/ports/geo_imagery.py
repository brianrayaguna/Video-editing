"""Capability port for satellite and orthophoto map tile imagery providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ImagerySessionInfo:
    """Resolved imagery provider configuration and session metadata."""

    provider: str
    map_type: str
    scale: str
    high_dpi: bool
    image_format: str
    google_min_zoom: int
    max_tiles_per_run: int


@runtime_checkable
class GeoImageryPort(Protocol):
    """Provider-agnostic interface for satellite tile imagery sessions and attribution."""

    @property
    def provider_name(self) -> str: ...

    def session_info(self) -> ImagerySessionInfo: ...
