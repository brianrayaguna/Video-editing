"""Local deterministic FFmpeg implementation of MediaOpsPort."""

from __future__ import annotations

import json
import re
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


_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[0-9.]+)")


def parse_silencedetect(stderr_text: str, duration_s: float) -> list[tuple[float, float]]:
    """Parse `silencedetect` stderr into `(start, end)` intervals clamped to `[0, duration_s]`.

    A trailing `silence_start` without a matching `silence_end` runs to the end of the media.
    """
    intervals: list[tuple[float, float]] = []
    open_start: float | None = None
    for line in stderr_text.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            open_start = max(0.0, float(start_match.group(1)))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and open_start is not None:
            end = min(duration_s, float(end_match.group(1)))
            if end > open_start:
                intervals.append((open_start, end))
            open_start = None
    if open_start is not None and duration_s > open_start:
        intervals.append((open_start, duration_s))
    return intervals


def compute_keep_segments(
    silences: list[tuple[float, float]],
    duration_s: float,
    *,
    padding_s: float,
) -> list[tuple[float, float]]:
    """Return speech segments to keep after removing `silences`.

    Each silence is shrunk by `padding_s` on both sides so word onsets and decays survive;
    silences shorter than twice the padding are left untouched. Silences touching the media
    start or end are trimmed fully up to the padding.
    """
    if duration_s <= 0:
        return []
    cuts: list[tuple[float, float]] = []
    for start, end in sorted(silences):
        cut_start = start + padding_s if start > 0 else 0.0
        cut_end = end - padding_s if end < duration_s else duration_s
        if cut_end - cut_start > 1e-3:
            cuts.append((cut_start, cut_end))

    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for cut_start, cut_end in cuts:
        if cut_start > cursor + 1e-3:
            keep.append((round(cursor, 3), round(cut_start, 3)))
        cursor = max(cursor, cut_end)
    if duration_s > cursor + 1e-3:
        keep.append((round(cursor, 3), round(duration_s, 3)))
    return keep


class FfmpegMediaOpsProvider:
    """Deterministic FFmpeg preprocessing adapter for local audio and footage preparation.

    `trim`, `remove_silence`, and `restore_footage` are local-only operations: they are
    I/O-bound or lightweight enough that staging media to a remote worker costs more than
    running them in place.
    """

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
            "Background matting is not supported by the local ffmpeg provider.",
        )

    def _run(self, cmd: list[str], operation: str) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ProviderAPIError(
                self.provider_name, None, f"ffmpeg {operation} failed: {proc.stderr}"
            )
        return proc

    def _probe_duration(self, media_input: Path) -> float:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(media_input),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            raise ProviderAPIError(self.provider_name, None, f"ffprobe failed: {probe.stderr}")
        try:
            return float(json.loads(probe.stdout)["format"]["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderAPIError(
                self.provider_name, None, f"Could not read media duration: {media_input}"
            ) from exc

    def trim(
        self,
        video_input: Path,
        output_path: Path,
        *,
        start_s: float,
        end_s: float,
        accurate: bool = False,
    ) -> MediaOpResult:
        """Cut `[start_s, end_s)` from a clip.

        The default stream-copy mode is lossless and near-instant but snaps the start to the
        preceding keyframe. `accurate=True` re-encodes for a frame-exact cut point.
        """
        if not video_input.is_file():
            raise FileNotFoundError(f"Video file not found: {video_input}")
        if start_s < 0 or end_s <= start_s:
            raise ValueError(f"trim requires 0 <= start_s < end_s, got [{start_s}, {end_s}]")
        duration = round(end_s - start_s, 3)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-hide_banner", "-y", "-ss", f"{start_s:.3f}", "-i", str(video_input)]
        cmd += ["-t", f"{duration:.3f}"]
        if accurate:
            cmd += [
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        else:
            cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        cmd.append(str(output_path))
        self._run(cmd, "trim")
        return MediaOpResult(
            provider=self.provider_name,
            operation="trim",
            output_path=output_path,
            metadata={
                "start_s": start_s,
                "end_s": end_s,
                "duration_s": duration,
                "mode": "accurate" if accurate else "stream_copy",
            },
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
        """Tighten a voiceover by cutting pauses longer than `min_silence_s`.

        Output is 48 kHz PCM WAV. Timestamps shift, so run this before transcription; the
        returned `kept_segments` map output time back to source time.
        """
        if not speech_input.is_file():
            raise FileNotFoundError(f"Audio/video file not found: {speech_input}")
        if min_silence_s <= 0 or padding_s < 0 or 2 * padding_s >= min_silence_s:
            raise ValueError(
                "remove_silence requires min_silence_s > 0 and 0 <= 2 * padding_s < min_silence_s"
            )
        duration_s = self._probe_duration(speech_input)
        detect = self._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(speech_input),
                "-vn",
                "-af",
                f"silencedetect=n={threshold_db}dB:d={min_silence_s}",
                "-f",
                "null",
                "-",
            ],
            "silencedetect",
        )
        silences = parse_silencedetect(detect.stderr, duration_s)
        keep = compute_keep_segments(silences, duration_s, padding_s=padding_s)
        if not keep:
            raise ProviderAPIError(
                self.provider_name, None, "remove_silence found no audible segments to keep."
            )
        # Sample-accurate cuts joined with short edge fades to suppress splice clicks.
        fade_s = max(0.002, min(0.05, crossfade_ms / 1000.0))
        kept_s = round(sum(b - a for a, b in keep), 3)
        graph_parts: list[str] = []
        for idx, (a, b) in enumerate(keep):
            seg_len = max(0.01, b - a)
            eff_fade = min(fade_s, seg_len * 0.25)
            fade_out_start = max(0.0, seg_len - eff_fade)
            graph_parts.append(
                f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={eff_fade:.4f},afade=t=out:st={fade_out_start:.3f}:d={eff_fade:.4f}[s{idx}]"
            )
        joined = "".join(f"[s{idx}]" for idx in range(len(keep)))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if room_tone_db is not None:
            import tempfile

            from vedit.mastering.sound_design import synthesize_room_tone_bed

            with tempfile.TemporaryDirectory(prefix="vedit_room_tone_") as tmp_dir:
                room_wav = synthesize_room_tone_bed(
                    max(0.25, kept_s),
                    Path(tmp_dir) / "room.wav",
                    level_db=float(room_tone_db),
                )
                graph_parts.append(
                    f"{joined}concat=n={len(keep)}:v=0:a=1,"
                    "aresample=48000,aformat=channel_layouts=stereo[joined]"
                )
                graph_parts.append(
                    f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{kept_s:.3f}[room];"
                    "[joined][room]amix=inputs=2:duration=first:normalize=0[out]"
                )
                self._run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-y",
                        "-i",
                        str(speech_input),
                        "-i",
                        str(room_wav),
                        "-filter_complex",
                        ";".join(graph_parts),
                        "-map",
                        "[out]",
                        "-ar",
                        "48000",
                        "-ac",
                        "2",
                        "-c:a",
                        "pcm_s16le",
                        str(output_path),
                    ],
                    "remove_silence",
                )
        else:
            graph_parts.append(f"{joined}concat=n={len(keep)}:v=0:a=1[out]")
            self._run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(speech_input),
                    "-filter_complex",
                    ";".join(graph_parts),
                    "-map",
                    "[out]",
                    "-ar",
                    "48000",
                    "-c:a",
                    "pcm_s16le",
                    str(output_path),
                ],
                "remove_silence",
            )
        return MediaOpResult(
            provider=self.provider_name,
            operation="remove_silence",
            output_path=output_path,
            metadata={
                "source_duration_s": round(duration_s, 3),
                "output_duration_s": kept_s,
                "removed_s": round(duration_s - kept_s, 3),
                "room_tone_db": room_tone_db,
                "kept_segments": [[a, b] for a, b in keep],
            },
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
        """Clean raw footage: optional deinterlace, single-pass stabilization, light denoise."""
        if not video_input.is_file():
            raise FileNotFoundError(f"Video file not found: {video_input}")
        filters: list[str] = []
        if deinterlace:
            filters.append("bwdif=mode=send_frame")
        if stabilize:
            filters.append("deshake")
        if denoise:
            filters.append("hqdn3d=1.5:1.5:6:6")
        if not filters:
            raise ValueError(
                "restore_footage requires at least one of stabilize/denoise/deinterlace"
            )
        filters.append("format=yuv420p")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(video_input),
                "-vf",
                ",".join(filters),
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-preset",
                "fast",
                "-c:a",
                "copy",
                str(output_path),
            ],
            "restore_footage",
        )
        return MediaOpResult(
            provider=self.provider_name,
            operation="restore_footage",
            output_path=output_path,
            metadata={"filters": filters[:-1]},
        )
