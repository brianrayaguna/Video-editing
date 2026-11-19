"""Modal.com serverless implementation of MediaOpsPort (DeepFilterNet & cloud reframing)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import find_repo_root
from vedit.ports.media_ops import GenerativeVideoProhibitedError, MediaOpResult
from vedit.providers.http import ProviderAPIError


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ModalCloudMediaOpsProvider:
    """Serverless Modal CPU adapter for neural speech enhancement and video reframing.

    Stages local inputs by SHA-256 into the shared Modal CAS Volume, invokes deployed
    Modal worker functions (`clean_audio_cloud`, `reframe_video_cloud`), and downloads
    processed outputs without running ML or heavy transcoding locally.
    """

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        volume: Any | None = None,
        clean_audio_fn: Any | None = None,
        reframe_fn: Any | None = None,
    ) -> None:
        self._options = dict(options or {})
        if self._options.get("allow_generative_video", False):
            raise GenerativeVideoProhibitedError(
                "Generative video synthesis is permanently prohibited by repository policy."
            )
        self._app_name = str(self._options.get("app_name") or "vedit-distributed-renderer")
        self._volume_name = str(self._options.get("volume_name") or "vedit-cas-cache-v2")
        self._volume = volume
        self._clean_audio_fn = clean_audio_fn
        self._reframe_fn = reframe_fn

    @property
    def provider_name(self) -> str:
        return "modal_cloud"

    def _ensure_cloud_src_on_path(self) -> None:
        try:
            cloud_src = str(find_repo_root() / "packages" / "cloud-modal" / "src")
            if cloud_src not in sys.path:
                sys.path.insert(0, cloud_src)
        except FileNotFoundError:
            pass

    def _get_volume(self) -> Any:
        if self._volume is not None:
            return self._volume
        import modal

        return modal.Volume.from_name(self._volume_name, create_if_missing=True, version=2)

    def _stage_file(self, volume: Any, local_path: Path) -> str:
        sha = _sha256_file(local_path)
        ext = local_path.suffix.lower() or ".bin"
        remote_rel = f"sources/{sha}{ext}"

        existing: set[str] = set()
        try:
            for entry in volume.listdir("/sources"):
                existing.add(str(entry.path).lstrip("/"))
        except Exception:
            existing = set()

        if remote_rel not in existing:
            with volume.batch_upload(force=True) as batch:
                batch.put_file(str(local_path), f"/{remote_rel}")
        return remote_rel

    def _download_file(self, volume: Any, remote_relpath: str, local_output: Path) -> Path:
        local_output.parent.mkdir(parents=True, exist_ok=True)
        clean_rel = remote_relpath.lstrip("/")
        with local_output.open("wb") as fp:
            for chunk in volume.read_file(clean_rel):
                fp.write(chunk)
        return local_output

    def _resolve_remote_fn(self, override: Any | None, fn_name: str) -> Any:
        if override is not None:
            return override
        import modal

        self._ensure_cloud_src_on_path()
        try:
            fn = modal.Function.from_name(self._app_name, fn_name)
            fn.hydrate()
            return fn
        except Exception as exc:
            raise ProviderAPIError(
                self.provider_name,
                None,
                f"Modal function `{self._app_name}.{fn_name}` is not deployed or unreachable. "
                "Deploy with `modal deploy packages/cloud-modal/src/vedit_cloud/app.py`. "
                f"Detail: {exc}",
            ) from exc

    def clean_audio(
        self,
        speech_input: Path,
        output_path: Path,
        *,
        strength: float = 0.85,
    ) -> MediaOpResult:
        if not speech_input.is_file():
            raise FileNotFoundError(f"Audio/video file not found: {speech_input}")
        if not 0.0 <= strength <= 1.0:
            raise ValueError(f"clean_audio strength must be within [0.0, 1.0], got {strength}")

        volume = self._get_volume()
        remote_rel = self._stage_file(volume, speech_input)
        remote_fn = self._resolve_remote_fn(self._clean_audio_fn, "clean_audio_cloud")
        summary = remote_fn.remote(remote_rel, strength=strength)
        self._download_file(volume, str(summary["output_subpath"]), output_path)
        return MediaOpResult(
            provider=self.provider_name,
            operation="clean_audio",
            output_path=output_path,
            metadata=dict(summary),
        )

    def reframe(
        self,
        video_input: Path,
        output_path: Path,
        *,
        target_aspect_ratio: Literal["9:16", "1:1", "4:5", "16:9"] = "9:16",
    ) -> MediaOpResult:
        if not video_input.is_file():
            raise FileNotFoundError(f"Video file not found: {video_input}")

        volume = self._get_volume()
        remote_rel = self._stage_file(volume, video_input)
        remote_fn = self._resolve_remote_fn(self._reframe_fn, "reframe_video_cloud")
        summary = remote_fn.remote(remote_rel, target_aspect_ratio=target_aspect_ratio)
        self._download_file(volume, str(summary["output_subpath"]), output_path)
        return MediaOpResult(
            provider=self.provider_name,
            operation="reframe",
            output_path=output_path,
            metadata=dict(summary),
        )

    def remove_background(
        self,
        video_input: Path,
        output_path: Path,
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "Modal CPU media_ops handles `clean_audio` (DeepFilterNet) and `reframe`. "
            "Use `--provider veed` with OpenEdit OAuth for cloud background matting.",
        )
