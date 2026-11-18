"""VEED OpenEdit OAuth implementation of TranscriptionPort (`www.veed.io/api/v1`)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx

from vedit.models import NormalizedTranscript, TranscriptWord
from vedit.ports.transcription import TranscriptionOptions
from vedit.providers.http import ProviderAPIError, poll_until_complete
from vedit.providers.veed_oauth import VeedEdgeClient, VeedOAuthTokenStore

DEFAULT_FILLERS = frozenset({"uh", "um", "er", "ah", "eh", "emm", "hmm", "uhh", "umm"})


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class VeedTranscriptionProvider:
    """Hosted speech-to-text adapter backed by OpenEdit VEED OAuth credentials."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
        token_store: VeedOAuthTokenStore | None = None,
    ) -> None:
        self._options = dict(options or {})
        self._workspace_id: str | None = self._options.get("workspace_id")
        self._poll_interval_s = float(self._options.get("poll_interval_s") or 2.0)
        self._timeout_s = float(self._options.get("timeout_s") or 600.0)
        self._edge = VeedEdgeClient(
            token_store=token_store,
            api_base=self._options.get("api_base"),
            client=client,
        )

    @property
    def provider_name(self) -> str:
        return "veed"

    def transcribe(
        self,
        media_path: Path,
        options: TranscriptionOptions | None = None,
    ) -> NormalizedTranscript:
        if not media_path.is_file():
            raise FileNotFoundError(f"Media file not found for transcription: {media_path}")

        opts = options or TranscriptionOptions()
        source_hash = opts.source_hash or _sha256_file(media_path)
        workspace_id = self._edge.resolve_workspace_id(self._workspace_id)

        asset_id, cdn_url = self._edge.upload_local_asset(
            media_path,
            asset_type="VIDEO",
            group="srcVideo",
            poll_interval_s=min(self._poll_interval_s, 1.0),
        )

        started = self._edge.post_json(
            f"/subtitles/assets/{asset_id}/transcribe",
            {
                "projectId": None,
                "workspaceId": workspace_id,
                "videoUrl": cdn_url,
                "language": opts.language,
            },
        )
        subtitle_id = str(started["id"])

        def _poll() -> tuple[str, dict[str, Any]]:
            sub = self._edge.get_json(f"/subtitles/{subtitle_id}") or {}
            status = str(sub.get("status") or "pending").lower()
            if status == "active":
                return "COMPLETED", sub
            if status == "error":
                return "FAILED", sub
            return "PENDING", sub

        done = poll_until_complete(
            _poll,
            provider=self.provider_name,
            poll_interval_s=self._poll_interval_s,
            timeout_s=self._timeout_s,
        )

        subtitles_map = done.get("subtitles") or {}
        items = sorted(subtitles_map.values(), key=lambda x: float(x.get("from", 0.0)))
        if not items:
            raise ProviderAPIError(
                self.provider_name, None, "VEED transcription returned no usable caption items."
            )

        words: list[TranscriptWord] = []
        chunk_texts: list[str] = []
        max_end = 0.0
        for item in items:
            item_from = float(item.get("from", 0.0))
            item_to = float(item.get("to", item_from))
            max_end = max(max_end, item_to)
            raw_words = item.get("words") or []
            item_tokens: list[str] = []
            for w in raw_words:
                val = str(w.get("value", "")).strip()
                if not val:
                    continue
                w_start = float(w.get("from", item_from))
                w_end = float(w.get("to", item_to))
                max_end = max(max_end, w_end)
                item_tokens.append(val)
                words.append(
                    TranscriptWord(
                        text=val,
                        start_s=w_start,
                        end_s=w_end,
                        speaker=None,
                        confidence=None,
                        is_filler=(val.strip(".,!?").lower() in DEFAULT_FILLERS),
                    )
                )
            if item_tokens:
                chunk_texts.append(" ".join(item_tokens))

        return NormalizedTranscript(
            source_hash=source_hash,
            provider=self.provider_name,
            model="veed-hosted",
            language=opts.language or "und",
            duration_s=max_end,
            text=" ".join(chunk_texts),
            words=words,
        )
