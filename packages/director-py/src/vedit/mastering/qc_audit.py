"""Post-render technical QC auditor using ffprobe and EBU R128 loudness analysis."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.models import PlatformTarget

_EBUR128_I_RE = re.compile(r"Integrated loudness:\s*\n\s*I:\s*([-\d.]+)\s*LUFS", re.I)
_EBUR128_TP_RE = re.compile(r"True peak:\s*\n\s*Peak:\s*([-\d.]+)\s*dBFS", re.I)


@dataclass(slots=True)
class QCIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str


@dataclass(slots=True)
class QCAuditReport:
    passed: bool
    file_path: Path
    errors: list[QCIssue] = field(default_factory=list)
    warnings: list[QCIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "file_path": str(self.file_path),
            "errors": [asdict(e) for e in self.errors],
            "warnings": [asdict(w) for w in self.warnings],
            "metrics": dict(self.metrics),
        }


def _parse_rate(rate_str: str | None) -> float:
    if not rate_str or "/" not in rate_str:
        return float(rate_str) if rate_str else 0.0
    num_s, den_s = rate_str.split("/", 1)
    den = float(den_s)
    return float(num_s) / den if den > 0 else 0.0


def audit_mastered_deliverable(
    media_path: Path,
    platform_target: PlatformTarget,
    *,
    require_audio: bool = True,
) -> QCAuditReport:
    """Verify resolution, CFR frame rate, bt709 tags, AAC audio, and EBU R128 loudness."""
    errors: list[QCIssue] = []
    warnings: list[QCIssue] = []
    metrics: dict[str, Any] = {}

    if not media_path.is_file() or media_path.stat().st_size == 0:
        errors.append(
            QCIssue(
                severity="error",
                code="MISSING_OR_EMPTY_FILE",
                message=f"Deliverable missing or empty: {media_path}",
            )
        )
        return QCAuditReport(passed=False, file_path=media_path, errors=errors)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        errors.append(
            QCIssue(severity="error", code="FFPROBE_FAILED", message=probe.stderr.strip())
        )
        return QCAuditReport(passed=False, file_path=media_path, errors=errors)

    info = json.loads(probe.stdout)
    streams = info.get("streams") or []
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if v_stream is None:
        errors.append(
            QCIssue(severity="error", code="NO_VIDEO_STREAM", message="Missing video stream.")
        )
    else:
        w = int(v_stream.get("width", 0))
        h = int(v_stream.get("height", 0))
        r_fps = _parse_rate(v_stream.get("r_frame_rate"))
        avg_fps = _parse_rate(v_stream.get("avg_frame_rate"))
        is_cfr = abs(r_fps - avg_fps) <= 0.15 and r_fps > 0
        metrics.update(
            {
                "width": w,
                "height": h,
                "r_fps": round(r_fps, 3),
                "avg_fps": round(avg_fps, 3),
                "is_cfr": is_cfr,
                "pixel_format": v_stream.get("pix_fmt"),
                "color_space": v_stream.get("color_space"),
                "color_primaries": v_stream.get("color_primaries"),
                "color_trc": v_stream.get("color_transfer") or v_stream.get("color_trc"),
            }
        )

        if w != platform_target.width or h != platform_target.height:
            errors.append(
                QCIssue(
                    severity="error",
                    code="RESOLUTION_MISMATCH",
                    message=(
                        f"Got {w}x{h}, expected "
                        f"{platform_target.width}x{platform_target.height}."
                    ),
                )
            )
        if not is_cfr or abs(r_fps - platform_target.fps) > 0.15:
            errors.append(
                QCIssue(
                    severity="error",
                    code="FPS_OR_VFR_MISMATCH",
                    message=(
                        f"Expected CFR {platform_target.fps}fps, "
                        f"got r={r_fps:.3f}/avg={avg_fps:.3f}."
                    ),
                )
            )
        for field_name, expected, actual in (
            ("color_space", platform_target.video.color_space, v_stream.get("color_space")),
            (
                "color_primaries",
                platform_target.video.color_primaries,
                v_stream.get("color_primaries"),
            ),
            (
                "color_trc",
                platform_target.video.color_trc,
                v_stream.get("color_transfer") or v_stream.get("color_trc"),
            ),
        ):
            if actual != expected:
                errors.append(
                    QCIssue(
                        severity="error",
                        code="COLOR_METADATA_MISMATCH",
                        message=f"{field_name}={actual!r}, expected {expected!r}.",
                    )
                )

    if a_stream is None:
        if require_audio:
            errors.append(
                QCIssue(severity="error", code="NO_AUDIO_STREAM", message="Missing audio stream.")
            )
    else:
        sr = int(a_stream.get("sample_rate", 0))
        ch = int(a_stream.get("channels", 0))
        metrics.update(
            {
                "audio_codec": a_stream.get("codec_name"),
                "sample_rate_hz": sr,
                "channels": ch,
            }
        )
        if sr != platform_target.audio.sample_rate_hz:
            errors.append(
                QCIssue(
                    severity="error",
                    code="SAMPLE_RATE_MISMATCH",
                    message=f"Expected {platform_target.audio.sample_rate_hz}Hz, got {sr}Hz.",
                )
            )
        if ch != platform_target.audio.channels:
            errors.append(
                QCIssue(
                    severity="error",
                    code="CHANNEL_COUNT_MISMATCH",
                    message=f"Expected {platform_target.audio.channels}ch, got {ch}ch.",
                )
            )

        ebur = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(media_path),
                "-af",
                "ebur128=peak=true",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        i_match = _EBUR128_I_RE.search(ebur.stderr)
        tp_match = _EBUR128_TP_RE.search(ebur.stderr)
        if i_match:
            lufs = float(i_match.group(1))
            metrics["integrated_lufs"] = lufs
            diff = abs(lufs - platform_target.audio.target_lufs)
            if diff > platform_target.audio.lufs_tolerance:
                errors.append(
                    QCIssue(
                        severity="error",
                        code="LOUDNESS_OUT_OF_TOLERANCE",
                        message=(
                            f"Integrated loudness {lufs:.2f} LUFS misses target "
                            f"{platform_target.audio.target_lufs:.1f} "
                            f"+/- {platform_target.audio.lufs_tolerance:.1f} LUFS."
                        ),
                    )
                )
        else:
            warnings.append(
                QCIssue(
                    severity="warning",
                    code="LOUDNESS_PARSE_UNAVAILABLE",
                    message="Could not parse integrated LUFS from ebur128 summary.",
                )
            )

        if tp_match:
            tp = float(tp_match.group(1))
            metrics["true_peak_dbtp"] = tp
            if tp > platform_target.audio.max_true_peak_dbtp:
                errors.append(
                    QCIssue(
                        severity="error",
                        code="TRUE_PEAK_EXCEEDED",
                        message=(
                            f"True peak {tp:.2f} dBTP exceeds limit "
                            f"{platform_target.audio.max_true_peak_dbtp:.2f} dBTP."
                        ),
                    )
                )

    return QCAuditReport(
        passed=len(errors) == 0,
        file_path=media_path,
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )
