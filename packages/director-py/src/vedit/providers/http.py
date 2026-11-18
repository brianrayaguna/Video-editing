"""Shared HTTP retry, credential redaction, and polling helpers for API providers."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from collections.abc import Set as AbstractSet
from typing import Any

import httpx


class ProviderAPIError(RuntimeError):
    """Raised when an upstream capability API fails after retries or returns 4xx."""

    def __init__(self, provider: str, status_code: int | None, message: str) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


def redact_secret(text: str, secret: str | None) -> str:
    """Scrub a secret token out of any diagnostic string."""
    if not secret:
        return text
    return text.replace(secret, "***REDACTED***")


def require_api_key(options: dict[str, Any], default_env: str, provider: str) -> str:
    """Resolve an API key from options or environment without logging its value."""
    direct = options.get("api_key")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    env_name = str(options.get("api_key_env") or default_env)
    val = os.environ.get(env_name, "").strip()
    if not val:
        raise ProviderAPIError(
            provider,
            None,
            f"Missing credential environment variable '{env_name}'. "
            "Run `vedit providers auth` or export it before invoking this capability.",
        )
    return val


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    provider: str,
    secret_to_redact: str | None = None,
    max_attempts: int = 4,
    base_backoff_s: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with exponential backoff on 429, 5xx, and transport errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                msg = redact_secret(str(exc), secret_to_redact)
                raise ProviderAPIError(provider, None, f"Network error: {msg}") from exc
            sleep_fn(base_backoff_s * (2**attempt))
            continue

        if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < max_attempts:
            retry_after = response.headers.get("Retry-After")
            delay = (
                float(retry_after)
                if retry_after and retry_after.replace(".", "", 1).isdigit()
                else base_backoff_s * (2**attempt)
            )
            sleep_fn(min(delay, 30.0))
            continue

        if response.status_code >= 400:
            body = redact_secret(response.text[:600], secret_to_redact)
            raise ProviderAPIError(
                provider,
                response.status_code,
                f"HTTP {response.status_code}: {body}",
            )

        return response

    raise ProviderAPIError(provider, None, f"Exhausted retries: {last_exc}")


def poll_until_complete(
    check_fn: Callable[[], tuple[str, dict[str, Any]]],
    *,
    provider: str,
    done_states: AbstractSet[str] = frozenset({"COMPLETED", "SUCCEEDED", "DONE"}),
    fail_states: AbstractSet[str] = frozenset({"FAILED", "ERROR", "CANCELLED"}),
    poll_interval_s: float = 2.0,
    timeout_s: float = 600.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Poll an asynchronous media-processing job until terminal status or timeout."""
    deadline = monotonic_fn() + timeout_s
    while True:
        status, payload = check_fn()
        upper = status.upper()
        if upper in done_states:
            return payload
        if upper in fail_states:
            raise ProviderAPIError(
                provider, None, f"Remote job failed with status '{status}': {payload}"
            )
        if monotonic_fn() >= deadline:
            raise ProviderAPIError(
                provider,
                None,
                f"Remote job timed out after {timeout_s:.0f}s (last status={status})",
            )
        sleep_fn(poll_interval_s)
