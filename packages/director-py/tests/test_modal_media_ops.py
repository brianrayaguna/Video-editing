"""Tests for ModalCloudMediaOpsProvider (DeepFilterNet cloud cleanup and cloud reframing)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from vedit.ports.media_ops import GenerativeVideoProhibitedError, MediaOpsPort
from vedit.providers.http import ProviderAPIError
from vedit.providers.media_ops.modal_cloud import ModalCloudMediaOpsProvider
from vedit.providers.registry import build_default_registry


@dataclass
class _FakeEntry:
    path: str


class _FakeBatchUpload:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store
        self.uploaded: list[str] = []

    def __enter__(self) -> _FakeBatchUpload:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def put_file(self, local_path: str, remote_dst: str) -> None:
        clean = remote_dst.lstrip("/")
        self._store[clean] = Path(local_path).read_bytes()
        self.uploaded.append(clean)


class _FakeModalVolume:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.upload_calls: int = 0

    def listdir(self, prefix: str) -> list[_FakeEntry]:
        clean = prefix.lstrip("/")
        return [
            _FakeEntry(path=k)
            for k in self.store
            if k.startswith(f"{clean}/")
        ]

    def batch_upload(self, *, force: bool = True) -> _FakeBatchUpload:
        self.upload_calls += 1
        return _FakeBatchUpload(self.store)

    def read_file(self, relpath: str) -> list[bytes]:
        return [self.store[relpath.lstrip("/")]]


class _FakeRemoteFn:
    def __init__(self, volume: _FakeModalVolume, out_subpath: str, payload: bytes) -> None:
        self._volume = volume
        self._out_subpath = out_subpath
        self._payload = payload
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def remote(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((args, kwargs))
        self._volume.store[self._out_subpath] = self._payload
        return {
            "output_subpath": self._out_subpath,
            "engine": "deepfilternet",
            "wall_ms": 420,
            "estimated_usd": 0.0001,
        }


def test_modal_cloud_media_ops_clean_audio_and_cas_dedup(tmp_path: Path) -> None:
    src_wav = tmp_path / "vo_raw.wav"
    src_wav.write_bytes(b"RIFF-fake-speech-input")
    out_wav = tmp_path / "vo_clean.wav"

    vol = _FakeModalVolume()
    fn = _FakeRemoteFn(vol, "media_ops/clean_audio/clean.wav", b"RIFF-deepfiltered")
    provider = ModalCloudMediaOpsProvider(volume=vol, clean_audio_fn=fn)
    assert isinstance(provider, MediaOpsPort)

    res1 = provider.clean_audio(src_wav, out_wav, strength=0.8)
    assert res1.provider == "modal_cloud"
    assert res1.operation == "clean_audio"
    assert out_wav.read_bytes() == b"RIFF-deepfiltered"
    assert vol.upload_calls == 1
    assert fn.calls[0][1] == {"strength": 0.8}

    # Re-running with identical content reuses CAS without re-uploading.
    out_wav_2 = tmp_path / "vo_clean_2.wav"
    provider.clean_audio(src_wav, out_wav_2, strength=0.8)
    assert vol.upload_calls == 1


def test_modal_cloud_media_ops_reframe_and_guardrails(tmp_path: Path) -> None:
    with pytest.raises(GenerativeVideoProhibitedError):
        ModalCloudMediaOpsProvider({"allow_generative_video": True})

    src_mp4 = tmp_path / "clip.mp4"
    src_mp4.write_bytes(b"fake-video-bytes")
    out_mp4 = tmp_path / "clip_9x16.mp4"

    vol = _FakeModalVolume()
    fn = _FakeRemoteFn(vol, "media_ops/reframe/out.mp4", b"reframed-mp4-bytes")
    provider = ModalCloudMediaOpsProvider(volume=vol, reframe_fn=fn)

    res = provider.reframe(src_mp4, out_mp4, target_aspect_ratio="9:16")
    assert res.operation == "reframe"
    assert out_mp4.read_bytes() == b"reframed-mp4-bytes"
    assert fn.calls[0][1] == {"target_aspect_ratio": "9:16"}

    with pytest.raises(ProviderAPIError, match="not supported"):
        provider.remove_background(src_mp4, tmp_path / "matte.mov")


def test_modal_cloud_registered_in_default_registry() -> None:
    registry = build_default_registry()
    names = {spec.name for spec in registry.list_specs("media_ops")}
    assert {"modal_cloud", "ffmpeg"}.issubset(names)
