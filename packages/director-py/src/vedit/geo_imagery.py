"""Decoupled satellite imagery provider helpers and attribution provenance.

Supports:
- High-resolution global 2D satellite tiles via the Google Map Tiles API when
  `GOOGLE_MAPS_API_KEY` is configured in the environment (up to z18).
- Open-licensed national orthoimagery (U.S. Geological Survey, The National Map,
  public domain, ~1 m, z13-16) where covered.
- Open-licensed global Sentinel-2 cloudless 2024 (EOX IT Services GmbH; modified
  Copernicus Sentinel data 2024, CC BY 4.0, ~10 m native, z0-14).

Every tile fetch records accurate attribution metadata in `attribution.json` so
map scene renderers display compliant on-screen imagery credits automatically.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vedit.providers.env import load_dotenv_safe

S2_CLOUDLESS_YEAR = "2024"
S2_CLOUDLESS_LAYER = "s2cloudless-2024_3857"
S2_CLOUDLESS_MAX_NATIVE_Z = 14
S2_CLOUDLESS_ATTRIBUTION = "Sentinel-2 cloudless 2024 by EOX IT Services GmbH"

NATIONAL_ORTHO_MIN_Z = 13
NATIONAL_ORTHO_MAX_Z = 16
NATIONAL_ORTHO_ATTRIBUTION = "Imagery: U.S. Geological Survey"

GOOGLE_TILES_MAX_Z = 18
GOOGLE_DEFAULT_ATTRIBUTION = "Imagery ©Google"
GOOGLE_CREATE_SESSION_URL = "https://tile.googleapis.com/v1/createSession"
GOOGLE_VIEWPORT_URL = "https://tile.googleapis.com/v1/viewport"
GOOGLE_2DTILES_URL = "https://tile.googleapis.com/v1/2dtiles"


def s2_cloudless_url(z: int, x: int, y: int, subdomain: str = "a") -> str:
    """Return the EOX Sentinel-2 cloudless 2024 WMTS URL for `(z, x, y)`."""
    return (
        f"https://{subdomain}.tiles.maps.eox.at/wmts/1.0.0/{S2_CLOUDLESS_LAYER}/default/g/"
        f"{z}/{y}/{x}.jpg"
    )


def national_ortho_url(z: int, x: int, y: int) -> str:
    """Return the public-domain USGS National Map orthoimagery URL for `(z, x, y)`."""
    return (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/"
        f"{z}/{y}/{x}"
    )


def google_satellite_tile_url(
    z: int, x: int, y: int, *, session_token: str, api_key: str
) -> str:
    """Return the Google Map Tiles API 2D satellite tile URL for `(z, x, y)`."""
    params = urllib.parse.urlencode({"session": session_token, "key": api_key})
    return f"{GOOGLE_2DTILES_URL}/{z}/{x}/{y}?{params}"


def resolve_imagery_provider(
    provider: str = "auto", *, repo_root: Path | None = None
) -> tuple[str, str | None]:
    """Resolve the active HQ imagery provider (`google` or `open`) and optional API key."""
    load_dotenv_safe(repo_root)
    mode = provider.strip().lower()
    if mode not in {"auto", "google", "open"}:
        raise ValueError(
            f"Unsupported imagery provider {provider!r}; expected auto, google, or open."
        )
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip() or None
    if mode == "google":
        if not api_key:
            raise ValueError(
                "GOOGLE_MAPS_API_KEY is not set. Add it to .env or pass --provider open."
            )
        return "google", api_key
    if mode == "auto" and api_key:
        return "google", api_key
    return "open", None


def tiles_to_bbox(coords: set[tuple[int, int, int]]) -> tuple[float, float, float, float] | None:
    """Compute `(west, south, east, north)` degrees bounding box covering XYZ tile coords."""
    if not coords:
        return None
    west, south, east, north = 180.0, 90.0, -180.0, -90.0
    for z, x, y in coords:
        n = 2.0**z
        lon_w = x / n * 360.0 - 180.0
        lon_e = (x + 1) / n * 360.0 - 180.0
        lat_n = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
        lat_s = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / n))))
        west = min(west, lon_w)
        east = max(east, lon_e)
        south = min(south, lat_s)
        north = max(north, lat_n)
    return (
        max(-180.0, west),
        max(-85.0511, south),
        min(180.0, east),
        min(85.0511, north),
    )


class GoogleMapTilesClient:
    """Minimal Google Map Tiles API client for 2D satellite sessions and copyright lookup."""

    def __init__(self, api_key: str, *, timeout_s: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._session_token: str | None = None

    @property
    def api_key(self) -> str:
        return self._api_key

    def create_session(
        self,
        *,
        map_type: str = "satellite",
        language: str = "en-US",
        region: str = "US",
    ) -> str:
        """Create and cache a Map Tiles API session token."""
        if self._session_token:
            return self._session_token
        url = f"{GOOGLE_CREATE_SESSION_URL}?{urllib.parse.urlencode({'key': self._api_key})}"
        payload = json.dumps(
            {
                "mapType": map_type,
                "language": language,
                "region": region,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = str(data.get("session") or "").strip()
        if not token:
            raise RuntimeError("Google Map Tiles API createSession returned no session token.")
        self._session_token = token
        return token

    def fetch_viewport_copyright(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> str:
        """Query official Google Map Tiles viewport copyright metadata for `(w, s, e, n)`."""
        token = self.create_session()
        w, s, e, n = bbox
        clamped_z = max(0, min(GOOGLE_TILES_MAX_Z, int(zoom)))
        params = urllib.parse.urlencode(
            {
                "session": token,
                "key": self._api_key,
                "zoom": clamped_z,
                "north": f"{n:.5f}",
                "south": f"{s:.5f}",
                "east": f"{e:.5f}",
                "west": f"{w:.5f}",
            }
        )
        req = urllib.request.Request(f"{GOOGLE_VIEWPORT_URL}?{params}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            copyright_str = str(data.get("copyright") or "").strip()
            return copyright_str or GOOGLE_DEFAULT_ATTRIBUTION
        except Exception:
            return GOOGLE_DEFAULT_ATTRIBUTION


def format_credit_line(
    sources: list[str], *, google_copyright: str | None = None
) -> str:
    """Format a concise, compliant on-screen attribution line from active source IDs."""
    parts: list[str] = []
    seen: set[str] = set()
    for src in sources:
        if src == "google_map_tiles":
            text = (google_copyright or GOOGLE_DEFAULT_ATTRIBUTION).strip()
        elif src == "usgs_national_map":
            text = NATIONAL_ORTHO_ATTRIBUTION
        elif src == "eox_s2_2024":
            text = S2_CLOUDLESS_ATTRIBUTION
        else:
            continue
        if text and text not in seen:
            seen.add(text)
            parts.append(text)
    if not parts:
        return S2_CLOUDLESS_ATTRIBUTION
    return " · ".join(parts)


def record_imagery_attribution(
    hq_dir: Path,
    *,
    sources: list[str],
    google_copyright: str | None = None,
) -> tuple[Path, str]:
    """Write `attribution.json` inside `hq_dir` and return `(path, credit_line)`."""
    hq_dir.mkdir(parents=True, exist_ok=True)
    attr_path = hq_dir / "attribution.json"
    credit_line = format_credit_line(sources, google_copyright=google_copyright)
    payload = {
        "schema_version": "1.0",
        "updated_at": datetime.now(UTC).isoformat(),
        "sources": sources,
        "google_copyright": google_copyright,
        "credit_line": credit_line,
    }
    attr_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return attr_path, credit_line
