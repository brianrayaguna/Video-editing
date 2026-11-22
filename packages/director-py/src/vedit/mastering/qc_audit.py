"""Post-render technical and visual QC auditor (ffprobe, EBU R128, black/freeze, optional VMAF)."""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.models import PlatformTarget

_EBUR128_I_RE = re.compile(
    r"Integrated loudness:\s*\n\s*I:\s*([-+]?(?:\d+(?:\.\d+)?|inf))\s*LUFS", re.I
)
_EBUR128_TP_RE = re.compile(
    r"True peak:\s*\n\s*Peak:\s*([-+]?(?:\d+(?:\.\d+)?|inf))\s*dBFS", re.I
)
_BLACK_RE = re.compile(
    r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)",
    re.I,
)
_FREEZE_START_RE = re.compile(r"freeze_start:\s*([\d.]+)", re.I)
_FREEZE_DUR_RE = re.compile(r"freeze_duration:\s*([\d.]+)", re.I)
_VMAF_SCORE_RE = re.compile(r"VMAF score:\s*([\d.]+)", re.I)
_SSIM_ALL_RE = re.compile(r"All:([\d.]+)", re.I)
_PSNR_AVG_RE = re.compile(r"average:(\d+(?:\.\d+)?|inf)", re.I)


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


def _run_visual_anomaly_scan(
    media_path: Path,
    *,
    black_min_s: float = 0.4,
    freeze_min_s: float = 3.0,
) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    """Detect unintended black segments and frozen frames in a single FFmpeg decode pass."""
    vf = f"blackdetect=d={black_min_s:.2f}:pix_th=0.10,freezedetect=n=-60dB:d={freeze_min_s:.2f}"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(media_path),
            "-vf",
            vf,
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if proc.returncode != 0:
        err_tail = (proc.stderr or "")[-400:]
        raise RuntimeError(
            f"FFmpeg visual anomaly scan failed (exit {proc.returncode}): {err_tail}"
        )
    stderr = proc.stderr or ""
    blacks = [
        {
            "start_s": round(float(m.group(1)), 3),
            "end_s": round(float(m.group(2)), 3),
            "duration_s": round(float(m.group(3)), 3),
        }
        for m in _BLACK_RE.finditer(stderr)
    ]

    freezes: list[dict[str, float]] = []
    pending_start: float | None = None
    for line in stderr.splitlines():
        s_match = _FREEZE_START_RE.search(line)
        if s_match:
            pending_start = float(s_match.group(1))
            continue
        d_match = _FREEZE_DUR_RE.search(line)
        if d_match and pending_start is not None:
            dur = float(d_match.group(1))
            freezes.append(
                {
                    "start_s": round(pending_start, 3),
                    "duration_s": round(dur, 3),
                }
            )
            pending_start = None
    return blacks, freezes


def compute_vmaf_score(
    distorted_path: Path,
    reference_path: Path,
) -> float | None:
    """Compute perceptual VMAF score via FFmpeg `libvmaf` when supported by the FFmpeg build."""
    if not distorted_path.is_file() or not reference_path.is_file():
        return None
    filters = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    )
    if filters.returncode != 0 or "libvmaf" not in (filters.stdout or ""):
        return None

    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(distorted_path),
            "-i",
            str(reference_path),
            "-lavfi",
            "[0:v]setpts=PTS-STARTPTS[dist];[1:v]setpts=PTS-STARTPTS[ref];[dist][ref]libvmaf",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    match = _VMAF_SCORE_RE.search(proc.stderr or "")
    return round(float(match.group(1)), 3) if match else None


def compute_ssim_psnr_scores(
    distorted_path: Path,
    reference_path: Path,
) -> dict[str, float] | None:
    """Compute FFmpeg SSIM and PSNR metrics as a portable fallback when libvmaf is absent."""
    if not distorted_path.is_file() or not reference_path.is_file():
        return None
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(distorted_path),
            "-i",
            str(reference_path),
            "-lavfi",
            "[0:v]setpts=PTS-STARTPTS,split[d1][d2];"
            "[1:v]setpts=PTS-STARTPTS,split[r1][r2];"
            "[d1][r1]ssim;[d2][r2]psnr",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if proc.returncode != 0:
        return {}
    stderr = proc.stderr or ""
    ssim_m = _SSIM_ALL_RE.search(stderr)
    psnr_m = _PSNR_AVG_RE.search(stderr)
    out: dict[str, float] = {}
    if ssim_m:
        out["ssim"] = round(float(ssim_m.group(1)), 4)
    if psnr_m:
        raw_psnr = psnr_m.group(1).lower()
        out["psnr_db"] = 99.0 if raw_psnr == "inf" else round(float(raw_psnr), 2)
    return out or None


def generate_diff_contact_sheet(
    deliverable_path: Path,
    reference_path: Path,
    output_jpg: Path,
    *,
    samples: int = 12,
) -> Path | None:
    """Render a side-by-side contact sheet (REF left vs DELIVERABLE right) across the timeline."""
    if not deliverable_path.is_file() or not reference_path.is_file():
        return None
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(deliverable_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        dur = max(0.5, float((probe.stdout or "0").strip()))
    except ValueError:
        return None

    import tempfile

    n = max(2, min(samples, 24))
    cols = 3
    stamps = [round((dur * (i + 0.5)) / n, 3) for i in range(n)]
    cell_w, cell_h = 240, 426
    output_jpg.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vedit_diff_sheet_") as tmp_dir:
        tmp = Path(tmp_dir)
        cells: list[Path] = []
        for idx, t in enumerate(stamps):
            cell = tmp / f"cell_{idx:02d}.jpg"
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-ss",
                    f"{t:.3f}",
                    "-i",
                    str(reference_path),
                    "-ss",
                    f"{t:.3f}",
                    "-i",
                    str(deliverable_path),
                    "-filter_complex",
                    f"[0:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                    f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2,drawtext=text='REF {t:.1f}s':"
                    "x=6:y=6:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.75[a];"
                    f"[1:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                    f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2,drawtext=text='OUT {t:.1f}s':"
                    "x=6:y=6:fontsize=16:fontcolor=cyan:box=1:boxcolor=black@0.75[b];"
                    "[a][b]hstack=inputs=2",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "3",
                    str(cell),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and cell.is_file():
                cells.append(cell)
        if not cells:
            return None
        inputs: list[str] = []
        for c in cells:
            inputs.extend(["-i", str(c)])
        pair_w = cell_w * 2
        layout = "|".join(
            f"{(i % cols) * pair_w}_{(i // cols) * cell_h}" for i in range(len(cells))
        )
        fc = "".join(f"[{i}:v]" for i in range(len(cells))) + (
            f"xstack=inputs={len(cells)}:layout={layout}"
        )
        grid = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                *inputs,
                "-filter_complex",
                fc,
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(output_jpg),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return output_jpg if grid.returncode == 0 and output_jpg.is_file() else None


def audit_mastered_deliverable(
    media_path: Path,
    platform_target: PlatformTarget,
    *,
    require_audio: bool = True,
    check_visual: bool = True,
    reference_path: Path | None = None,
    min_vmaf: float = 85.0,
) -> QCAuditReport:
    """Verify resolution, CFR frame rate, bt709 tags, AAC audio, loudness, and visual anomalies."""
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
        dur_raw = (
            info.get("format", {}).get("duration")
            or v_stream.get("duration")
            or 0.0
        )
        metrics.update(
            {
                "width": w,
                "height": h,
                "duration_s": round(float(dur_raw), 3),
                "video_duration_s": round(float(v_stream.get("duration") or dur_raw), 3),
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

        if check_visual:
            try:
                blacks, freezes = _run_visual_anomaly_scan(media_path)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                errors.append(
                    QCIssue(
                        severity="error",
                        code="VISUAL_SCAN_FAILED",
                        message=str(exc),
                    )
                )
                blacks, freezes = [], []
            metrics["black_segments"] = blacks
            metrics["freeze_segments"] = freezes
            if blacks:
                warnings.append(
                    QCIssue(
                        severity="warning",
                        code="BLACK_FRAMES_DETECTED",
                        message=(
                            f"Detected {len(blacks)} black segment(s) >= 0.4s "
                            f"(first at {blacks[0]['start_s']:.2f}s)."
                        ),
                    )
                )
            if freezes:
                warnings.append(
                    QCIssue(
                        severity="warning",
                        code="FROZEN_FRAMES_DETECTED",
                        message=(
                            f"Detected {len(freezes)} frozen segment(s) >= 3.0s "
                            f"(first at {freezes[0]['start_s']:.2f}s)."
                        ),
                    )
                )

        if reference_path is not None:
            vmaf = compute_vmaf_score(media_path, reference_path)
            if vmaf is not None:
                metrics["vmaf_score"] = vmaf
                if vmaf < min_vmaf:
                    warnings.append(
                        QCIssue(
                            severity="warning",
                            code="LOW_VMAF_SCORE",
                            message=f"VMAF score {vmaf:.2f} is below threshold {min_vmaf:.1f}.",
                        )
                    )
            else:
                fallback_scores = compute_ssim_psnr_scores(media_path, reference_path)
                if fallback_scores:
                    metrics.update(fallback_scores)
                else:
                    warnings.append(
                        QCIssue(
                            severity="warning",
                            code="VMAF_UNAVAILABLE",
                            message="FFmpeg libvmaf filter not available on this host.",
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
            timeout=300,
        )
        i_match = _EBUR128_I_RE.search(ebur.stderr)
        tp_match = _EBUR128_TP_RE.search(ebur.stderr)
        if ebur.returncode != 0:
            errors.append(
                QCIssue(
                    severity="error",
                    code="LOUDNESS_MEASUREMENT_FAILED",
                    message=(
                        f"FFmpeg ebur128 measurement failed (exit {ebur.returncode}): "
                        f"{(ebur.stderr or '').strip()[-240:]}"
                    ),
                )
            )
        elif i_match:
            lufs = float(i_match.group(1))
            if not math.isfinite(lufs):
                metrics["integrated_lufs"] = None
                errors.append(
                    QCIssue(
                        severity="error",
                        code="SILENT_AUDIO_STREAM",
                        message=(
                            f"Integrated loudness is non-finite ({i_match.group(1)} LUFS); "
                            "audio stream appears silent."
                        ),
                    )
                )
            else:
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
            errors.append(
                QCIssue(
                    severity="error",
                    code="LOUDNESS_PARSE_UNAVAILABLE",
                    message="Could not parse integrated LUFS from ebur128 summary.",
                )
            )

        if a_stream is not None and v_stream is not None:
            v_dur = float(v_stream.get("duration") or 0.0)
            a_dur = float(a_stream.get("duration") or 0.0)
            if v_dur > 0 and a_dur > 0 and abs(v_dur - a_dur) > 0.5:
                errors.append(
                    QCIssue(
                        severity="error",
                        code="VIDEO_AUDIO_DURATION_MISMATCH",
                        message=(
                            f"Video stream ({v_dur:.2f}s) and audio stream ({a_dur:.2f}s) "
                            "differ by more than 0.5s."
                        ),
                    )
                )
        if ebur.returncode == 0 and tp_match:
            tp = float(tp_match.group(1))
            metrics["true_peak_dbtp"] = tp if math.isfinite(tp) else None
            if math.isfinite(tp) and tp > platform_target.audio.max_true_peak_dbtp:
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
