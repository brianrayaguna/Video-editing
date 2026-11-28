"""Decoupled satellite imagery provider helpers and attribution provenance.

Supports:
- High-resolution global 2D satellite tiles via the Google Map Tiles API when
  `GOOGLE_MAPS_API_KEY` is configured in the environment (z0-z18, scaleFactor2x + highDpi,
  14-day disk session caching with expiry renewal, and pooled httpx transport).
- Open-licensed national orthoimagery (U.S. Geological Survey, The National Map,
  public domain, ~1 m, z13-16) where covered.
- Open-licensed global Sentinel-2 cloudless 2024 (EOX IT Services GmbH; modified
  Copernicus Sentinel data 2024, CC BY 4.0, ~10 m native, z0-14).

Every tile fetch records accurate attribution metadata in `attribution.json` so
map scene renderers display compliant on-screen imagery credits automatically.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from vedit.providers.env import load_dotenv_safe
from vedit.providers.http import redact_secret

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
_SESSION_REFRESH_MARGIN_S = 3600.0


def _default_session_cache_path() -> Path:
    cache_root = os.environ.get("VEDIT_CACHE_DIR", "").strip()
    base = Path(cache_root).expanduser() if cache_root else (Path.home() / ".cache" / "vedit")
    return base / "google_tiles_session.json"


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
    """Resolve the active satellite imagery provider (`google` or `open`) and optional API key."""
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


def _atomic_write_json_0600(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, indent=2) + "\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


class GoogleMapTilesClient:
    """Google Map Tiles API client with persistent 14-day session cache and pooled httpx."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 12.0,
        session_cache_path: Path | None = None,
        client: httpx.Client | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._api_key = api_key
        self._key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        self._timeout_s = timeout_s
        self._session_cache_path = session_cache_path or _default_session_cache_path()
        self._client = client
        self._own_client = client is None
        self._now_fn = now_fn or time.time
        self._lock = threading.Lock()
        self._session_token: str | None = None
        self._session_expiry: float = 0.0
        self._session_signature: str | None = None

    @property
    def api_key(self) -> str:
        return self._api_key

    def _http(self) -> httpx.Client:
        if self._client is None:
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=16)
            self._client = httpx.Client(timeout=self._timeout_s, limits=limits)
        return self._client

    def close(self) -> None:
        if self._own_client and self._client is not None:
            self._client.close()
            self._client = None

    def _signature(
        self,
        map_type: str,
        language: str,
        region: str,
        scale: str,
        high_dpi: bool,
        image_format: str,
    ) -> str:
        return (
            f"{self._key_hash}:{map_type}:{language}:{region}:"
            f"{scale}:{int(high_dpi)}:{image_format}"
        )

    def _load_cached_session(self, sig: str) -> tuple[str, float] | None:
        try:
            if not self._session_cache_path.is_file():
                return None
            data = json.loads(self._session_cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        entry = data.get(sig) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            return None
        token = str(entry.get("session") or "").strip()
        try:
            expiry = float(entry.get("expiry") or 0.0)
        except (TypeError, ValueError):
            expiry = 0.0
        if token and expiry > (self._now_fn() + _SESSION_REFRESH_MARGIN_S):
            return token, expiry
        return None

    def _save_cached_session(
        self, sig: str, token: str, expiry: float, meta: dict[str, Any]
    ) -> None:
        store: dict[str, Any] = {}
        try:
            if self._session_cache_path.is_file():
                raw = json.loads(self._session_cache_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    store = raw
        except (OSError, ValueError):
            store = {}
        store[sig] = {
            "session": token,
            "expiry": expiry,
            "tileWidth": meta.get("tileWidth"),
            "tileHeight": meta.get("tileHeight"),
            "imageFormat": meta.get("imageFormat"),
        }
        try:
            _atomic_write_json_0600(self._session_cache_path, store)
        except OSError:
            pass

    def create_session(
        self,
        *,
        map_type: str = "satellite",
        language: str = "en-US",
        region: str = "US",
        scale: str = "scaleFactor2x",
        high_dpi: bool = True,
        image_format: str = "jpeg",
        force_refresh: bool = False,
    ) -> str:
        """Create or reuse a persistent Map Tiles API session token with expiry tracking."""
        sig = self._signature(map_type, language, region, scale, high_dpi, image_format)
        now = self._now_fn()
        with self._lock:
            if (
                not force_refresh
                and self._session_token
                and self._session_signature == sig
                and self._session_expiry > (now + _SESSION_REFRESH_MARGIN_S)
            ):
                return self._session_token

            if not force_refresh:
                cached = self._load_cached_session(sig)
                if cached is not None:
                    self._session_token, self._session_expiry = cached
                    self._session_signature = sig
                    return self._session_token

            body: dict[str, Any] = {
                "mapType": map_type,
                "language": language,
                "region": region,
            }
            if scale and scale != "scaleFactor1x":
                body["scale"] = scale
                if high_dpi:
                    body["highDpi"] = True
            if image_format:
                body["imageFormat"] = image_format

            try:
                resp = self._http().post(
                    GOOGLE_CREATE_SESSION_URL,
                    params={"key": self._api_key},
                    json=body,
                )
            except httpx.HTTPError as exc:
                safe = redact_secret(str(exc), self._api_key)
                raise RuntimeError(f"Google Map Tiles createSession network error: {safe}") from exc

            if resp.status_code >= 400:
                safe = redact_secret(resp.text[:300], self._api_key)
                raise RuntimeError(
                    f"Google Map Tiles createSession failed (HTTP {resp.status_code}): {safe}"
                )

            data: dict[str, Any] = resp.json()
            token = str(data.get("session") or "").strip()
            if not token:
                raise RuntimeError("Google Map Tiles API createSession returned no session token.")
            try:
                expiry = float(data.get("expiry") or (now + 14 * 86400))
            except (TypeError, ValueError):
                expiry = now + 14 * 86400

            self._session_token = token
            self._session_expiry = expiry
            self._session_signature = sig
            self._save_cached_session(sig, token, expiry, data)
            return token

    def fetch_tile_bytes(
        self,
        z: int,
        x: int,
        y: int,
        *,
        map_type: str = "satellite",
        scale: str = "scaleFactor2x",
        high_dpi: bool = True,
        image_format: str = "jpeg",
        max_retries: int = 3,
    ) -> tuple[bytes | None, int]:
        """Fetch raw tile bytes over pooled httpx with session expiry renewal and backoff."""
        refreshed = False
        for attempt in range(max_retries + 1):
            token = self.create_session(
                map_type=map_type,
                scale=scale,
                high_dpi=high_dpi,
                image_format=image_format,
            )
            try:
                resp = self._http().get(
                    f"{GOOGLE_2DTILES_URL}/{z}/{x}/{y}",
                    params={"session": token, "key": self._api_key},
                )
            except httpx.HTTPError:
                if attempt < max_retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
                return None, 0

            if resp.status_code == 200 and len(resp.content) >= 64:
                return resp.content, 200
            if resp.status_code in (400, 401, 403) and not refreshed:
                refreshed = True
                try:
                    self.create_session(
                        map_type=map_type,
                        scale=scale,
                        high_dpi=high_dpi,
                        image_format=image_format,
                        force_refresh=True,
                    )
                    continue
                except RuntimeError:
                    return None, resp.status_code
            if resp.status_code in (404, 410):
                return None, resp.status_code
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(0.35 * (2**attempt))
                continue
            return None, resp.status_code
        return None, 0

    def fetch_viewport_copyright(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> str:
        """Query official Google Map Tiles viewport copyright metadata for `(w, s, e, n)`."""
        token = self.create_session()
        w, s, e, n = bbox
        clamped_z = max(0, min(GOOGLE_TILES_MAX_Z, int(zoom)))
        try:
            resp = self._http().get(
                GOOGLE_VIEWPORT_URL,
                params={
                    "session": token,
                    "key": self._api_key,
                    "zoom": clamped_z,
                    "north": f"{n:.5f}",
                    "south": f"{s:.5f}",
                    "east": f"{e:.5f}",
                    "west": f"{w:.5f}",
                },
            )
            if resp.status_code >= 400:
                return GOOGLE_DEFAULT_ATTRIBUTION
            data: dict[str, Any] = resp.json()
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
