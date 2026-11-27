"""VEED OpenEdit OAuth implementation of MediaOpsPort (`www.veed.io/api/v1`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import httpx

from vedit.ports.media_ops import GenerativeVideoProhibitedError, MediaOpResult
from vedit.providers.http import ProviderAPIError, poll_until_complete
from vedit.providers.veed_oauth import VeedEdgeClient, VeedOAuthTokenStore


class VeedMediaOpsProvider:
    """VEED MediaOpsPort using OpenEdit OAuth credentials (`www.veed.io/api/v1`).

    Supports VEED's free authenticated `remove_background` workflow with automatic
    resumable local asset upload. Generative video endpoints are permanently blocked.
    """

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
        token_store: VeedOAuthTokenStore | None = None,
    ) -> None:
        self._options = dict(options or {})
        if self._options.get("allow_generative_video", False):
            raise GenerativeVideoProhibitedError(
                "Generative video synthesis is permanently prohibited by repository policy."
            )
        self._workspace_id: str | None = self._options.get("workspace_id")
        self._poll_interval_s = float(self._options.get("poll_interval_s") or 3.0)
        self._timeout_s = float(self._options.get("timeout_s") or 900.0)
        self._edge = VeedEdgeClient(
            token_store=token_store,
            api_base=self._options.get("api_base"),
            client=client,
        )

    @property
    def provider_name(self) -> str:
        return "veed"

    def clean_audio(
        self,
        speech_input: Path,
        output_path: Path,
        *,
        strength: float = 0.85,
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "OpenEdit OAuth (`www.veed.io/api/v1`) does not expose a clean-audio endpoint. "
            "Use the `ffmpeg` media_ops provider (`vedit clean-audio --provider ffmpeg`) "
            "for deterministic local speech denoising.",
        )

    def reframe(
        self,
        video_input: Path,
        output_path: Path,
        *,
        target_aspect_ratio: Literal["9:16", "1:1", "4:5", "16:9"] = "9:16",
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "OpenEdit OAuth (`www.veed.io/api/v1`) performs reframing locally rather than via "
            "a hosted endpoint. Use the `ffmpeg` media_ops provider for deterministic reframing.",
        )

    def remove_background(
        self,
        video_input: Path,
        output_path: Path,
    ) -> MediaOpResult:
        if not video_input.is_file():
            raise FileNotFoundError(f"Video file not found for background removal: {video_input}")

        workspace_id = self._edge.resolve_workspace_id(self._workspace_id)
        space = self._edge.get_json(f"/workspace/{workspace_id}/space/default") or {}
        space_id = str(space["id"])

        project = (
            self._edge.post_json(
                "/project",
                {
                    "name": f"vedit-bg-{video_input.stem}",
                    "workspaceId": workspace_id,
                    "spaceId": space_id,
                    "folderId": space_id,
                    "privacy": "private",
                },
            )
            or {}
        )
        project_id = str(project["id"])

        _asset_id, cdn_url = self._edge.upload_local_asset(
            video_input,
            asset_type="VIDEO",
            group="srcVideo",
            workspace_id=workspace_id,
            project_id=project_id,
            poll_interval_s=min(self._poll_interval_s, 1.0),
        )

        started = (
            self._edge.post_json(
                "/remove-background",
                {
                    "videoUrl": cdn_url,
                    "projectId": project_id,
                    "workspaceId": workspace_id,
                },
            )
            or {}
        )
        workflow_id = str(started["workflowId"])

        def _poll() -> tuple[str, dict[str, Any]]:
            status_resp = (
                self._edge.get_json(
                    f"/remove-background/status?workflowId={workflow_id}&projectId={project_id}"
                )
                or {}
            )
            entries = status_resp.get("statuses") or []
            match = next(
                (e for e in entries if e.get("workflowId") == workflow_id),
                entries[0] if entries else None,
            )
            if not match:
                return "PENDING", {}
            status = str(match.get("status") or "PENDING").upper()
            if status == "COMPLETED":
                return "COMPLETED", match
            if status in ("FAILED", "CANCELED"):
                return "FAILED", match
            return status, match

        completed = poll_until_complete(
            _poll,
            provider=self.provider_name,
            poll_interval_s=self._poll_interval_s,
            timeout_s=self._timeout_s,
        )

        result_url = (completed.get("result") or {}).get("url")
        if not isinstance(result_url, str) or not result_url.startswith("http"):
            raise ProviderAPIError(
                self.provider_name,
                None,
                f"Background removal completed without a downloadable result URL: {completed}",
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._edge.download_bytes(result_url))

        return MediaOpResult(
            provider=self.provider_name,
            operation="remove_background",
            output_path=output_path,
            metadata={
                "workflow_id": workflow_id,
                "project_id": project_id,
                "workspace_id": workspace_id,
            },
        )

    def trim(
        self,
        video_input: Path,
        output_path: Path,
        *,
        start_s: float,
        end_s: float,
        accurate: bool = False,
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "Hosted media_ops handles `remove_background`. "
            "Use `--provider ffmpeg` for deterministic local clipping (`trim`).",
        )

    def remove_silence(
        self,
        speech_input: Path,
        output_path: Path,
        *,
        threshold_db: float = -40.0,
        min_silence_s: float = 0.45,
        padding_s: float = 0.12,
        crossfade_ms: int = 12,
        room_tone_db: float | None = None,
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "Hosted media_ops handles `remove_background`. "
            "Use `--provider ffmpeg` for deterministic local silence removal.",
        )

    def restore_footage(
        self,
        video_input: Path,
        output_path: Path,
        *,
        stabilize: bool = True,
        denoise: bool = True,
        deinterlace: bool = False,
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "Hosted media_ops handles `remove_background`. "
            "Use `--provider ffmpeg` for deterministic local footage restoration.",
        )
