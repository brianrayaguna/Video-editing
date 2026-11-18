"""Local deterministic FFmpeg implementation of MediaOpsPort."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from vedit.ports.media_ops import MediaOpResult
from vedit.providers.http import ProviderAPIError

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


class FfmpegMediaOpsProvider:
    """Deterministic FFmpeg preprocessing adapter for local audio cleanup and reframing."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._options = dict(options or {})

    @property
    def provider_name(self) -> str:
        return "ffmpeg"

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

        noise_reduction_db = round(4.0 + strength * 18.0, 1)
        af_chain = (
            f"highpass=f=80,afftdn=nr={noise_reduction_db}:nf=-30,"
            "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=120"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(speech_input),
            "-vn",
            "-af",
            af_chain,
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ProviderAPIError(
                self.provider_name, None, f"ffmpeg clean_audio failed: {proc.stderr}"
            )

        return MediaOpResult(
            provider=self.provider_name,
            operation="clean_audio",
            output_path=output_path,
            metadata={"noise_reduction_db": noise_reduction_db},
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
        target_w, target_h = ASPECT_DIMENSIONS[target_aspect_ratio]

        # Probe source dimensions so crop cleanly preserves aspect without stretching.
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(video_input),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            raise ProviderAPIError(self.provider_name, None, f"ffprobe failed: {probe.stderr}")
        streams = json.loads(probe.stdout).get("streams") or []
        if not streams:
            raise ProviderAPIError(self.provider_name, None, "Input media has no video stream.")

        vf = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={target_w}:{target_h},format=yuv420p"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(video_input),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "16",
            "-preset",
            "fast",
            "-c:a",
            "copy",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ProviderAPIError(
                self.provider_name, None, f"ffmpeg reframe failed: {proc.stderr}"
            )

        return MediaOpResult(
            provider=self.provider_name,
            operation="reframe",
            output_path=output_path,
            metadata={"width": target_w, "height": target_h, "aspect_ratio": target_aspect_ratio},
        )

    def remove_background(
        self,
        video_input: Path,
        output_path: Path,
    ) -> MediaOpResult:
        raise ProviderAPIError(
            self.provider_name,
            None,
            "Local FFmpeg does not perform neural background matting; "
            "use `--provider veed` with OpenEdit OAuth.",
        )
