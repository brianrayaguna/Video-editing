"""xAI speech-to-text implementation of TranscriptionPort."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from vedit.models import NormalizedTranscript, TranscriptWord
from vedit.ports.transcription import TranscriptionOptions
from vedit.providers.http import ProviderAPIError, request_with_retry, require_api_key

MAX_FILE_BYTES = 500 * 1024 * 1024
ITN_SUPPORTED_LANGUAGES = frozenset(
    {"ar", "de", "en", "es", "fr", "ja", "pt", "ru", "sv", "vi", "zh"}
)
DEFAULT_FILLERS = frozenset({"uh", "um", "er", "ah", "eh", "emm", "hmm", "uhh", "umm"})


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class XaiTranscriptionProvider:
    """REST `/v1/stt` client implementing `TranscriptionPort`."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._options = dict(options or {})
        self._endpoint = str(self._options.get("endpoint") or "https://api.x.ai/v1/stt")
        self._model = str(self._options.get("model") or "grok-voice-transcribe-2.0")
        self._timeout_s = float(self._options.get("timeout_s") or 180.0)
        self._client = client

    @property
    def provider_name(self) -> str:
        return "xai"

    def transcribe(
        self,
        media_path: Path,
        options: TranscriptionOptions | None = None,
    ) -> NormalizedTranscript:
        if not media_path.is_file():
            raise FileNotFoundError(f"Media file not found for transcription: {media_path}")

        size_bytes = media_path.stat().st_size
        if size_bytes > MAX_FILE_BYTES:
            raise ProviderAPIError(
                self.provider_name,
                None,
                f"Input file exceeds 500 MB REST limit ({size_bytes} bytes). "
                "Extract an audio-only stem (e.g. MP3/FLAC/WAV) before transcribing.",
            )

        opts = options or TranscriptionOptions()
        api_key = require_api_key(self._options, "XAI_API_KEY", self.provider_name)
        source_hash = opts.source_hash or _sha256_file(media_path)

        # Multipart option fields MUST precede `file` for streamable parsing.
        parts: list[tuple[str, tuple[str | None, Any, str | None] | tuple[None, str]]] = [
            ("model", (None, self._model)),
            ("diarize", (None, "true" if opts.diarize else "false")),
            ("filler_words", (None, "true" if opts.include_fillers else "false")),
        ]
        if opts.language:
            lang = opts.language.strip()
            parts.append(("language", (None, lang)))
            if lang.lower() in ITN_SUPPORTED_LANGUAGES:
                parts.append(("format", (None, "true")))

        for term in opts.keyterms[:100]:
            cleaned = term.strip()[:50]
            if cleaned:
                parts.append(("keyterm", (None, cleaned)))

        mime_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"

        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            with media_path.open("rb") as fp:
                parts.append(("file", (media_path.name, fp, mime_type)))
                response = request_with_retry(
                    client,
                    "POST",
                    self._endpoint,
                    provider=self.provider_name,
                    secret_to_redact=api_key,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files=parts,
                )
        finally:
            if own_client:
                client.close()

        raw = response.json()
        words = [
            TranscriptWord(
                text=str(w.get("text", "")),
                start_s=float(w.get("start", 0.0)),
                end_s=float(w.get("end", w.get("start", 0.0))),
                speaker=w.get("speaker"),
                confidence=w.get("confidence"),
                is_filler=(str(w.get("text", "")).strip(".,!?").lower() in DEFAULT_FILLERS),
            )
            for w in raw.get("words", [])
        ]

        return NormalizedTranscript(
            source_hash=source_hash,
            provider=self.provider_name,
            model=self._model,
            language=str(raw.get("language") or opts.language or "und"),
            duration_s=float(raw.get("duration") or 0.0),
            text=str(raw.get("text") or ""),
            words=words,
        )
