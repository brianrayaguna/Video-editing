"""Epidemic Sound REST API implementation of AudioCatalogPort."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import httpx

from vedit.ports.audio_catalog import AudioAssetResult, AudioKind, VocalPolicy
from vedit.providers.http import ProviderAPIError, request_with_retry, require_api_key


class EpidemicAudioCatalogProvider:
    """Semantic music and SFX catalog adapter targeting Epidemic Sound `/v0` endpoints."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._options = dict(options or {})
        self._base_url = str(
            self._options.get("base_url") or "https://api.epidemicsound.com/v0"
        ).rstrip("/")
        self._partner_user_id = str(self._options.get("partner_user_id") or "vedit-cli-user")
        self._timeout_s = float(self._options.get("timeout_s") or 60.0)
        self._client = client

    @property
    def provider_name(self) -> str:
        return "epidemic"

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "x-partner-user-id": self._partner_user_id,
        }

    def search_music(
        self,
        query: str,
        *,
        vocal_type: VocalPolicy | None = "NONE",
        bpm_range: tuple[int, int] | None = None,
        moods: list[str] | None = None,
        limit: int = 10,
    ) -> list[AudioAssetResult]:
        clean_term = query.strip()[:500]
        if not clean_term:
            raise ValueError("Music search query must be non-empty.")

        api_key = require_api_key(self._options, "EPIDEMIC_API_KEY", self.provider_name)
        # Epidemic Sound requires repeated query keys for array filters (no bracket syntax).
        params: list[tuple[str, str]] = [
            ("term", clean_term),
            ("limit", str(max(1, min(limit, 60)))),
            ("sort", "Relevance"),
            ("order", "desc"),
        ]
        if vocal_type is not None:
            params.append(("vocalType", vocal_type))
        if bpm_range is not None:
            params.append(("minBpm", str(bpm_range[0])))
            params.append(("maxBpm", str(bpm_range[1])))
        for mood in moods or []:
            params.append(("mood", mood))

        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            resp = request_with_retry(
                client,
                "GET",
                f"{self._base_url}/tracks/search",
                provider=self.provider_name,
                secret_to_redact=api_key,
                headers=self._auth_headers(api_key),
                params=params,
            ).json()
        finally:
            if own_client:
                client.close()

        items = resp.get("tracks") or resp.get("data") or resp.get("items") or []
        results: list[AudioAssetResult] = []
        for item in items:
            raw_moods = item.get("moods") or []
            raw_genres = item.get("genres") or []
            results.append(
                AudioAssetResult(
                    asset_id=str(item["id"]),
                    provider=self.provider_name,
                    kind="music",
                    title=str(item.get("title") or ""),
                    duration_s=float(item.get("length") or item.get("duration") or 0.0),
                    bpm=float(item["bpm"]) if item.get("bpm") is not None else None,
                    moods=[
                        str(m.get("tag") or m) if isinstance(m, dict) else str(m)
                        for m in raw_moods
                    ],
                    genres=[
                        str(g.get("tag") or g) if isinstance(g, dict) else str(g)
                        for g in raw_genres
                    ],
                    vocal_type=item.get("vocalType"),
                    preview_url=item.get("previewUrl"),
                )
            )
        return results

    def search_sfx(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[AudioAssetResult]:
        clean_term = query.strip()[:500]
        if not clean_term:
            raise ValueError("SFX search query must be non-empty.")

        api_key = require_api_key(self._options, "EPIDEMIC_API_KEY", self.provider_name)
        params: list[tuple[str, str]] = [
            ("term", clean_term),
            ("limit", str(max(1, min(limit, 60)))),
            ("sort", "best-match"),
            ("order", "desc"),
        ]

        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            resp = request_with_retry(
                client,
                "GET",
                f"{self._base_url}/sound-effects/search",
                provider=self.provider_name,
                secret_to_redact=api_key,
                headers=self._auth_headers(api_key),
                params=params,
            ).json()
        finally:
            if own_client:
                client.close()

        items = resp.get("soundEffects") or resp.get("data") or resp.get("items") or []
        results: list[AudioAssetResult] = []
        for item in items:
            results.append(
                AudioAssetResult(
                    asset_id=str(item["id"]),
                    provider=self.provider_name,
                    kind="sfx",
                    title=str(item.get("title") or ""),
                    duration_s=float(item.get("length") or item.get("duration") or 0.0),
                    preview_url=item.get("previewUrl"),
                )
            )
        return results

    def download_asset(
        self,
        asset_id: str,
        *,
        kind: AudioKind,
        destination_dir: Path,
        quality: Literal["normal", "high"] = "high",
    ) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        cached_path = destination_dir / f"{kind}_{asset_id}_{quality}.mp3"
        if cached_path.is_file() and cached_path.stat().st_size > 0:
            return cached_path

        api_key = require_api_key(self._options, "EPIDEMIC_API_KEY", self.provider_name)
        resource = "tracks" if kind == "music" else "sound-effects"

        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            meta = request_with_retry(
                client,
                "GET",
                f"{self._base_url}/{resource}/{asset_id}/download",
                provider=self.provider_name,
                secret_to_redact=api_key,
                headers=self._auth_headers(api_key),
                params={"format": "mp3", "quality": quality},
            ).json()

            signed_url = meta.get("url")
            if not isinstance(signed_url, str) or not signed_url.startswith("http"):
                raise ProviderAPIError(
                    self.provider_name, None, f"Missing signed download URL in response: {meta}"
                )

            # Signed CDN URLs must be fetched unmodified without Bearer headers.
            audio_resp = request_with_retry(client, "GET", signed_url, provider=self.provider_name)
            cached_path.write_bytes(audio_resp.content)
        finally:
            if own_client:
                client.close()

        return cached_path
