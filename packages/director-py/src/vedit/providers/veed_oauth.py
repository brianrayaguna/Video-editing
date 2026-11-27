"""OpenEdit OAuth 2.1 + PKCE token store and VEED REST edge client (`www.veed.io/api/v1`)."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from vedit.providers.http import (
    ProviderAPIError,
    poll_until_complete,
    request_with_retry,
)

EXPIRY_SKEW_MS = 60_000
DEFAULT_VEED_ORIGIN = "https://www.veed.io"


def resolve_openedit_state_dir() -> Path:
    """Resolve OpenEdit's cross-platform per-user OAuth state directory."""
    override = os.environ.get("OPENEDIT_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "veed-openedit"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "veed-openedit"
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "veed-openedit"


def resolve_openedit_token_path(token_path: Path | None = None) -> Path:
    return token_path or (resolve_openedit_state_dir() / "token.json")


def has_openedit_oauth_login(token_path: Path | None = None) -> bool:
    """Check whether an OpenEdit VEED access token or refreshable token store exists."""
    if os.environ.get("VEED_ACCESS_TOKEN", "").strip():
        return True
    path = resolve_openedit_token_path(token_path)
    import json

    try:
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        return isinstance(data, dict) and bool(data.get("accessToken") or data.get("refreshToken"))
    except (OSError, json.JSONDecodeError, ValueError):
        return False


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    import json
    import secrets

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


class VeedOAuthTokenStore:
    """Reads and automatically refreshes VEED OpenEdit OAuth tokens."""

    def __init__(
        self,
        *,
        token_path: Path | None = None,
        expected_origin: str | None = None,
        client: httpx.Client | None = None,
        now_ms_fn: Callable[[], int] | None = None,
    ) -> None:
        self._token_path = resolve_openedit_token_path(token_path)
        self._expected_origin = (
            expected_origin
            or os.environ.get("VEED_ORIGIN")
            or DEFAULT_VEED_ORIGIN
        ).rstrip("/")
        self._client = client
        self._now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))

    def resolve_token(self) -> str:
        env_token = os.environ.get("VEED_ACCESS_TOKEN", "").strip()
        if env_token:
            return env_token

        if not self._token_path.is_file():
            raise ProviderAPIError(
                "veed",
                None,
                f"No OpenEdit VEED OAuth login found at {self._token_path}. "
                "Run `npx @veedstudio/openedit-cli login` to authenticate via browser OAuth.",
            )

        import json

        try:
            stored: dict[str, Any] = json.loads(self._token_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderAPIError(
                "veed",
                None,
                f"Failed to parse OpenEdit VEED OAuth token at {self._token_path}: {exc}. "
                "Re-run `npx @veedstudio/openedit-cli login`.",
            ) from exc
        stored_origin = str(stored.get("origin") or "").rstrip("/")
        if stored_origin and stored_origin != self._expected_origin:
            raise ProviderAPIError(
                "veed",
                None,
                f"Stored OpenEdit login is for {stored_origin}, expected {self._expected_origin}. "
                "Re-run `npx @veedstudio/openedit-cli login`.",
            )

        expires_at = int(stored.get("expiresAt") or 0)
        if expires_at > self._now_ms_fn() + EXPIRY_SKEW_MS and stored.get("accessToken"):
            return str(stored["accessToken"])

        refresh_token = stored.get("refreshToken")
        client_id = stored.get("clientId")
        if not refresh_token or not client_id:
            raise ProviderAPIError(
                "veed",
                None,
                "Stored OpenEdit OAuth token expired and lacks a refreshToken/clientId. "
                "Re-run `npx @veedstudio/openedit-cli login`.",
            )

        token_endpoint = str(
            stored.get("tokenEndpoint")
            or f"{stored_origin or self._expected_origin}/api/v1/oauth2/token"
        )
        own_client = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            resp = request_with_retry(
                client,
                "POST",
                token_endpoint,
                provider="veed",
                secret_to_redact=str(refresh_token),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": str(refresh_token),
                    "client_id": str(client_id),
                },
            )
            refreshed = resp.json()
        except ProviderAPIError as exc:
            raise ProviderAPIError(
                "veed",
                exc.status_code,
                f"OpenEdit OAuth token refresh failed ({exc}). "
                "Re-run `npx @veedstudio/openedit-cli login`.",
            ) from exc
        except ValueError as exc:
            raise ProviderAPIError(
                "veed",
                None,
                f"OpenEdit OAuth token refresh returned invalid JSON: {exc}.",
            ) from exc
        finally:
            if own_client:
                client.close()

        if not isinstance(refreshed, dict) or not refreshed.get("access_token"):
            raise ProviderAPIError(
                "veed",
                None,
                "OpenEdit OAuth token refresh response lacked `access_token`.",
            )
        new_access = str(refreshed["access_token"])
        updated = {
            **stored,
            "accessToken": new_access,
            "refreshToken": refreshed.get("refresh_token") or refresh_token,
            "expiresAt": self._now_ms_fn() + int(refreshed.get("expires_in", 3600)) * 1000,
        }
        _write_json_atomically(self._token_path, updated)
        return new_access


def unwrap_veed_data(payload: Any) -> Any:
    """Normalize both bare payloads and `{ 'data': ... }` envelopes from VEED's REST edge."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


class VeedEdgeClient:
    """Thin authenticated client for VEED's OAuth-backed REST edge (`www.veed.io/api/v1`)."""

    def __init__(
        self,
        *,
        token_store: VeedOAuthTokenStore | None = None,
        api_base: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        origin = (os.environ.get("VEED_ORIGIN") or DEFAULT_VEED_ORIGIN).rstrip("/")
        self.api_base = (api_base or os.environ.get("VEED_API_BASE") or f"{origin}/api/v1").rstrip(
            "/"
        )
        self.origin = origin
        self._token_store = token_store or VeedOAuthTokenStore(
            expected_origin=origin, client=client
        )
        self._external_client = client

    def _client_ctx(self) -> tuple[httpx.Client, bool]:
        if self._external_client is not None:
            return self._external_client, False
        return httpx.Client(timeout=120.0), True

    def _edge_headers(self, token: str) -> dict[str, str]:
        # The REST edge rejects authenticated calls without an Origin header (HTTP 400).
        return {"Authorization": f"Bearer {token}", "Origin": self.origin}

    def get_json(self, path: str, *, allow_404: bool = False) -> Any | None:
        token = self._token_store.resolve_token()
        client, own = self._client_ctx()
        try:
            url = f"{self.api_base}{path}"
            if allow_404:
                try:
                    resp = request_with_retry(
                        client,
                        "GET",
                        url,
                        provider="veed",
                        secret_to_redact=token,
                        headers=self._edge_headers(token),
                    )
                except ProviderAPIError as exc:
                    if exc.status_code == 404:
                        return None
                    raise
                try:
                    return unwrap_veed_data(resp.json())
                except ValueError as exc:
                    raise ProviderAPIError(
                        "veed", resp.status_code, f"Invalid JSON: {exc}"
                    ) from exc

            resp = request_with_retry(
                client,
                "GET",
                url,
                provider="veed",
                secret_to_redact=token,
                headers=self._edge_headers(token),
            )
            try:
                return unwrap_veed_data(resp.json())
            except ValueError as exc:
                raise ProviderAPIError("veed", resp.status_code, f"Invalid JSON: {exc}") from exc
        finally:
            if own:
                client.close()

    def post_json(self, path: str, body: dict[str, Any]) -> Any:
        token = self._token_store.resolve_token()
        client, own = self._client_ctx()
        try:
            resp = request_with_retry(
                client,
                "POST",
                f"{self.api_base}{path}",
                provider="veed",
                secret_to_redact=token,
                headers={
                    **self._edge_headers(token),
                    "Content-Type": "application/json",
                },
                json=body,
            )
            return unwrap_veed_data(resp.json())
        finally:
            if own:
                client.close()

    def put_bytes(self, absolute_url: str, raw_bytes: bytes, content_type: str) -> None:
        client, own = self._client_ctx()
        try:
            request_with_retry(
                client,
                "PUT",
                absolute_url,
                provider="veed",
                headers={"Content-Type": content_type},
                content=raw_bytes,
            )
        finally:
            if own:
                client.close()

    def download_bytes(self, absolute_url: str) -> bytes:
        client, own = self._client_ctx()
        try:
            resp = request_with_retry(client, "GET", absolute_url, provider="veed")
            return resp.content
        finally:
            if own:
                client.close()

    def list_workspaces(self) -> list[dict[str, Any]]:
        res = self.get_json("/workspace")
        return list(res or [])

    def resolve_workspace_id(self, preferred_workspace_id: str | None = None) -> str:
        if preferred_workspace_id:
            return preferred_workspace_id
        workspaces = self.list_workspaces()
        if not workspaces:
            raise ProviderAPIError("veed", None, "No VEED workspace found for this OAuth account.")
        return str(workspaces[0]["id"])

    def upload_local_asset(
        self,
        file_path: Path,
        *,
        asset_type: str = "VIDEO",
        group: str = "srcVideo",
        workspace_id: str | None = None,
        project_id: str | None = None,
        poll_interval_s: float = 1.0,
    ) -> tuple[str, str]:
        """Upload a local media file via resumable GCS URL and return `(asset_id, cdn_url)`."""
        ext = file_path.suffix.lstrip(".").lower() or "mp4"
        mime_map = {
            "mp4": "video/mp4",
            "mov": "video/quicktime",
            "webm": "video/webm",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")
        payload: dict[str, Any] = {
            "assetType": asset_type,
            "mimeType": mime_type,
            "extension": ext,
            "group": group,
        }
        if workspace_id and project_id:
            payload["workspaceId"] = workspace_id
            payload["projectId"] = project_id

        created = self.post_json("/asset", payload)
        asset_id = str(created["asset"]["id"])
        upload_url = str(created["url"])

        self.put_bytes(upload_url, file_path.read_bytes(), mime_type)

        def _check() -> tuple[str, dict[str, Any]]:
            asset = self.get_json(f"/asset/{asset_id}", allow_404=True)
            if asset is None:
                return "PENDING", {}
            state = str(asset.get("uploadState") or "UPLOADING")
            if state == "UPLOADED" and asset.get("cdnUrl"):
                return "COMPLETED", asset
            if state == "FAILED":
                return "FAILED", asset
            return "UPLOADING", asset

        final_asset = poll_until_complete(
            _check,
            provider="veed",
            poll_interval_s=poll_interval_s,
            timeout_s=120.0,
        )
        return asset_id, str(final_asset["cdnUrl"])
