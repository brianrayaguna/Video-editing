"""Epidemic Sound REST (`/v0`) and MCP Streamable HTTP (`AudioCatalogPort`) adapter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import httpx

from vedit.ports.audio_catalog import AudioAssetResult, AudioKind, VocalPolicy
from vedit.providers.http import ProviderAPIError, request_with_retry, require_api_key

_DEFAULT_REST_BASE_URL = "https://api.epidemicsound.com/v0"
_DEFAULT_MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _parse_mcp_sse_json(response: httpx.Response, provider: str) -> dict[str, Any]:
    """Extract the JSON-RPC response payload from either JSON or SSE `data:` framing."""
    content_type = response.headers.get("content-type", "").lower()
    raw = response.text
    if "text/event-stream" in content_type or raw.lstrip().startswith(("event:", "data:", "id:")):
        last_payload: dict[str, Any] | None = None
        for line in raw.splitlines():
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body:
                continue
            last_payload = json.loads(body)
        if last_payload is not None:
            return last_payload
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderAPIError(
            provider, response.status_code, f"Malformed MCP response: {raw[:300]}"
        ) from exc


class EpidemicAudioCatalogProvider:
    """Semantic music and SFX catalog adapter targeting Epidemic Sound REST and MCP."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._options = dict(options or {})
        self._base_url = str(self._options.get("base_url") or _DEFAULT_REST_BASE_URL).rstrip("/")
        self._mcp_url = str(self._options.get("mcp_url") or _DEFAULT_MCP_URL).strip()
        self._transport = str(self._options.get("transport") or "auto").lower()
        self._partner_user_id = str(self._options.get("partner_user_id") or "vedit-cli-user")
        self._timeout_s = float(self._options.get("timeout_s") or 60.0)
        self._client = client
        self._mcp_session_id: str | None = None
        self._prefer_mcp = self._transport == "mcp" or "/mcp" in self._base_url.lower()

    @property
    def provider_name(self) -> str:
        return "epidemic"

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "x-partner-user-id": self._partner_user_id,
        }

    def _mcp_call_tool(
        self,
        client: httpx.Client,
        api_key: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Initialize an MCP Streamable HTTP session when needed and invoke a tool."""
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if not self._mcp_session_id:
            init_resp = request_with_retry(
                client,
                "POST",
                self._mcp_url,
                provider=self.provider_name,
                secret_to_redact=api_key,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "vedit", "version": "1.0"},
                    },
                },
            )
            self._mcp_session_id = init_resp.headers.get("mcp-session-id")
            if self._mcp_session_id:
                session_hdrs = {**headers, "Mcp-Session-Id": self._mcp_session_id}
                request_with_retry(
                    client,
                    "POST",
                    self._mcp_url,
                    provider=self.provider_name,
                    secret_to_redact=api_key,
                    headers=session_hdrs,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                )

        call_headers = dict(headers)
        if self._mcp_session_id:
            call_headers["Mcp-Session-Id"] = self._mcp_session_id

        try:
            resp = request_with_retry(
                client,
                "POST",
                self._mcp_url,
                provider=self.provider_name,
                secret_to_redact=api_key,
                headers=call_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
            )
        except ProviderAPIError as exc:
            if exc.status_code in (400, 404) and self._mcp_session_id:
                self._mcp_session_id = None
                return self._call_mcp_tool(client, api_key, tool_name, arguments)
            raise
        rpc_payload = _parse_mcp_sse_json(resp, self.provider_name)
        if "error" in rpc_payload:
            raise ProviderAPIError(
                self.provider_name,
                resp.status_code,
                f"MCP JSON-RPC error in {tool_name}: {rpc_payload['error']}",
            )
        result = rpc_payload.get("result") or {}
        if result.get("isError"):
            raise ProviderAPIError(
                self.provider_name,
                resp.status_code,
                f"MCP tool '{tool_name}' failed: {result.get('content')}",
            )
        content_items = result.get("content") or []
        for item in content_items:
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                return json.loads(item["text"])
        return result

    def _search_music_mcp(
        self,
        client: httpx.Client,
        api_key: str,
        clean_term: str,
        *,
        vocal_type: VocalPolicy | None,
        bpm_range: tuple[int, int] | None,
        moods: list[str] | None,
        limit: int,
    ) -> list[AudioAssetResult]:
        filters: dict[str, Any] = {}
        if vocal_type == "NONE":
            filters["vocals"] = False
        elif vocal_type in {"PRESENCE", "LEAD"}:
            filters["vocals"] = True
        if bpm_range is not None:
            filters["bpm"] = {"min": bpm_range[0], "max": bpm_range[1]}
        if moods:
            filters["moodSlugs"] = {"matchType": "ANY", "values": [m.lower() for m in moods]}

        args: dict[str, Any] = {
            "query": {"term": clean_term},
            "first": max(1, min(limit, 50)),
            "sort": {"by": "RELEVANCE", "order": "DESCENDING"},
        }
        if filters:
            args["filter"] = filters

        data = self._mcp_call_tool(client, api_key, "SearchRecordings", args)
        nodes = ((data.get("data") or {}).get("recordings") or {}).get("nodes") or []
        results: list[AudioAssetResult] = []
        for node in nodes:
            rec = node.get("recording") or node
            tags = rec.get("tags") or []
            node_moods = [
                str(t.get("displayName"))
                for t in tags
                if (t.get("dimension") or {}).get("name") == "mood" and t.get("displayName")
            ]
            node_genres = [
                str(t.get("displayName"))
                for t in tags
                if (t.get("dimension") or {}).get("name") == "genre" and t.get("displayName")
            ]
            audio_file = rec.get("audioFile") or {}
            dur_ms = float(audio_file.get("durationInMilliseconds") or 0.0)
            has_no_vocals = any(
                (t.get("displayName") or "").lower() == "no vocals" for t in tags
            )
            resolved_vocal: str | None = None
            if has_no_vocals or vocal_type == "NONE":
                resolved_vocal = "NONE"
            results.append(
                AudioAssetResult(
                    asset_id=str(rec["id"]),
                    provider=self.provider_name,
                    kind="music",
                    title=str(rec.get("title") or ""),
                    duration_s=round(dur_ms / 1000.0, 3),
                    bpm=float(rec["bpm"]) if rec.get("bpm") is not None else None,
                    moods=node_moods,
                    genres=node_genres,
                    vocal_type=resolved_vocal,
                    preview_url=audio_file.get("lqmp3Url"),
                )
            )
        return results

    def _search_sfx_mcp(
        self,
        client: httpx.Client,
        api_key: str,
        clean_term: str,
        *,
        limit: int,
    ) -> list[AudioAssetResult]:
        args: dict[str, Any] = {
            "query": {"term": clean_term},
            "first": max(1, min(limit, 50)),
            "sort": {"by": "RELEVANCE", "order": "DESCENDING"},
        }
        data = self._mcp_call_tool(client, api_key, "SearchSoundEffects", args)
        nodes = ((data.get("data") or {}).get("soundEffects") or {}).get("nodes") or []
        results: list[AudioAssetResult] = []
        for node in nodes:
            sfx = node.get("soundEffect") or node
            audio_file = sfx.get("audioFile") or {}
            dur_ms = float(audio_file.get("durationInMilliseconds") or 0.0)
            results.append(
                AudioAssetResult(
                    asset_id=str(sfx["id"]),
                    provider=self.provider_name,
                    kind="sfx",
                    title=str(sfx.get("title") or ""),
                    duration_s=round(dur_ms / 1000.0, 3),
                    preview_url=audio_file.get("lqmp3Url"),
                )
            )
        return results

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
        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            if self._prefer_mcp:
                return self._search_music_mcp(
                    client,
                    api_key,
                    clean_term,
                    vocal_type=vocal_type,
                    bpm_range=bpm_range,
                    moods=moods,
                    limit=limit,
                )

            # Epidemic Sound REST `/v0` requires repeated query keys for array filters.
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
            except ProviderAPIError as exc:
                if exc.status_code == 401 and self._transport == "auto":
                    self._prefer_mcp = True
                    return self._search_music_mcp(
                        client,
                        api_key,
                        clean_term,
                        vocal_type=vocal_type,
                        bpm_range=bpm_range,
                        moods=moods,
                        limit=limit,
                    )
                raise
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
            if self._prefer_mcp:
                return self._search_sfx_mcp(client, api_key, clean_term, limit=limit)
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
            except ProviderAPIError as exc:
                if exc.status_code == 401 and self._transport == "auto":
                    self._prefer_mcp = True
                    return self._search_sfx_mcp(client, api_key, clean_term, limit=limit)
                raise
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

    def _resolve_mcp_download_url(
        self,
        client: httpx.Client,
        api_key: str,
        asset_id: str,
        *,
        kind: AudioKind,
        file_type: Literal["MP3", "WAV"],
        stem_type: Literal["FULL", "BASS", "DRUMS", "INSTRUMENTS"] = "FULL",
    ) -> str:
        if kind == "music":
            data = self._mcp_call_tool(
                client,
                api_key,
                "DownloadRecording",
                {
                    "id": asset_id,
                    "options": {"fileType": file_type, "stemType": stem_type},
                },
            )
            payload = (data.get("data") or {}).get("recordingDownload") or data
        else:
            data = self._mcp_call_tool(
                client,
                api_key,
                "DownloadSoundEffect",
                {"id": asset_id, "options": {"fileType": file_type}},
            )
            payload = (data.get("data") or {}).get("soundEffectDownload") or data

        url = payload.get("assetUrl") or payload.get("url")
        if not isinstance(url, str) or not url.startswith("http"):
            raise ProviderAPIError(
                self.provider_name, None, f"Missing signed download URL in MCP response: {data}"
            )
        return url

    def download_asset(
        self,
        asset_id: str,
        *,
        kind: AudioKind,
        destination_dir: Path,
        quality: Literal["normal", "high"] = "high",
        file_format: Literal["mp3", "wav"] | None = None,
        stem_type: Literal["FULL", "BASS", "DRUMS", "INSTRUMENTS"] = "FULL",
    ) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        use_mcp = self._prefer_mcp or (self._transport == "auto" and bool(_UUID_RE.match(asset_id)))
        chosen_fmt: Literal["mp3", "wav"] = file_format or (
            "wav" if (use_mcp and quality == "high") else "mp3"
        )
        stem_suffix = f"_{stem_type.lower()}" if (kind == "music" and stem_type != "FULL") else ""
        cached_path = destination_dir / f"{kind}_{asset_id}_{quality}{stem_suffix}.{chosen_fmt}"
        if cached_path.is_file() and cached_path.stat().st_size > 0:
            return cached_path

        api_key = require_api_key(self._options, "EPIDEMIC_API_KEY", self.provider_name)
        resource = "tracks" if kind == "music" else "sound-effects"

        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            signed_url: str | None = None
            if not use_mcp:
                try:
                    meta = request_with_retry(
                        client,
                        "GET",
                        f"{self._base_url}/{resource}/{asset_id}/download",
                        provider=self.provider_name,
                        secret_to_redact=api_key,
                        headers=self._auth_headers(api_key),
                        params={"format": chosen_fmt, "quality": quality},
                    ).json()
                    raw_url = meta.get("url")
                    if not isinstance(raw_url, str) or not raw_url.startswith("http"):
                        raise ProviderAPIError(
                            self.provider_name,
                            None,
                            f"Missing signed download URL in response: {meta}",
                        )
                    signed_url = raw_url
                except ProviderAPIError as exc:
                    if exc.status_code == 401 and self._transport == "auto":
                        self._prefer_mcp = True
                        use_mcp = True
                    else:
                        raise

            if use_mcp:
                mcp_fmt: Literal["MP3", "WAV"] = "WAV" if chosen_fmt == "wav" else "MP3"
                signed_url = self._resolve_mcp_download_url(
                    client,
                    api_key,
                    asset_id,
                    kind=kind,
                    file_type=mcp_fmt,
                    stem_type=stem_type,
                )

            if signed_url is None:
                raise ProviderAPIError(
                    self.provider_name, None, f"Failed to resolve download URL for {asset_id}"
                )
            # Signed CDN URLs must be fetched unmodified without Bearer headers.
            audio_resp = request_with_retry(
                client,
                "GET",
                signed_url,
                provider=self.provider_name,
                secret_to_redact=signed_url,
            )
            tmp_path = cached_path.with_suffix(cached_path.suffix + ".part")
            try:
                tmp_path.write_bytes(audio_resp.content)
                tmp_path.replace(cached_path)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        finally:
            if own_client:
                client.close()

        return cached_path
