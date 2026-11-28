"""Geospatial satellite imagery provider adapters (`google_tiles` and `open_imagery`)."""

from __future__ import annotations

from typing import Any

from vedit.geo_imagery import GoogleMapTilesClient
from vedit.ports.geo_imagery import ImagerySessionInfo
from vedit.providers.http import require_api_key


class GoogleTilesImageryProvider:
    """Google Map Tiles API 2D satellite imagery provider (`GOOGLE_MAPS_API_KEY`)."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._options = dict(options or {})

    @property
    def provider_name(self) -> str:
        return "google_tiles"

    def session_info(self) -> ImagerySessionInfo:
        return ImagerySessionInfo(
            provider=self.provider_name,
            map_type=str(self._options.get("map_type") or "satellite"),
            scale=str(self._options.get("scale") or "scaleFactor2x"),
            high_dpi=bool(self._options.get("high_dpi", True)),
            image_format=str(self._options.get("image_format") or "jpeg"),
            google_min_zoom=int(self._options.get("google_min_zoom", 0)),
            max_tiles_per_run=int(self._options.get("max_tiles_per_run", 500)),
        )

    def create_client(self) -> GoogleMapTilesClient:
        api_key = require_api_key(self._options, "GOOGLE_MAPS_API_KEY", self.provider_name)
        return GoogleMapTilesClient(api_key)


class OpenImageryProvider:
    """Open-licensed fallback satellite imagery provider (USGS National Map + EOX Sentinel-2)."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._options = dict(options or {})

    @property
    def provider_name(self) -> str:
        return "open_imagery"

    def session_info(self) -> ImagerySessionInfo:
        return ImagerySessionInfo(
            provider=self.provider_name,
            map_type="satellite",
            scale="scaleFactor1x",
            high_dpi=False,
            image_format="jpeg",
            google_min_zoom=13,
            max_tiles_per_run=int(self._options.get("max_tiles_per_run", 500)),
        )


__all__ = ["GoogleTilesImageryProvider", "OpenImageryProvider"]
