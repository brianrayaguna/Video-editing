"""Post-render technical and visual QC auditor (ffprobe, EBU R128, black/freeze, optional VMAF)."""

from __future__ import annotations

import array
import json
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.mastering.sound_design import resolve_loudness_profile
from vedit.models import PlatformTarget

_EBUR128_I_RE = re.compile(
    r"Integrated loudness:\s*\n\s*I:\s*([-+]?(?:\d+(?:\.\d+)?|inf))\s*LUFS", re.I
)
_EBUR128_LRA_RE = re.compile(
    r"Loudness range:\s*\n\s*LRA:\s*([-+]?(?:\d+(?:\.\d+)?|inf))\s*LU", re.I
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
        if len(cells) == 1:
            shutil.copy2(cells[0], output_jpg)
            return output_jpg
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


def measure_mono_phase_correlation(media_path: Path) -> float | None:
    """Measure stereo L/R Pearson correlation (`-1.0..+1.0`) to detect mono phase cancellation."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "2",
            "-f",
            "s16le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0 or len(proc.stdout) < 8:
        return None
    pcm = array.array("h")
    usable = len(proc.stdout) - (len(proc.stdout) % 4)
    pcm.frombytes(proc.stdout[:usable])
    n_frames = len(pcm) // 2
    if n_frames < 16:
        return None
    sum_l2 = 0.0
    sum_r2 = 0.0
    sum_lr = 0.0
    for idx in range(0, n_frames * 2, 2):
        left = float(pcm[idx])
        right = float(pcm[idx + 1])
        sum_l2 += left * left
        sum_r2 += right * right
        sum_lr += left * right
    denom = math.sqrt(sum_l2 * sum_r2)
    if denom <= 1e-6:
        return 1.0
    return round(max(-1.0, min(1.0, sum_lr / denom)), 4)


@dataclass(slots=True)
class ProductionSoundReport:
    """Pre-ingest field/voiceover production sound diagnostics."""

    source_path: Path
    duration_s: float
    sample_rate: int
    channels: int
    peak_dbfs: float
    speech_rms_dbfs: float
    noise_floor_dbfs: float
    estimated_snr_db: float
    clipped_sample_ratio: float
    rumble_ratio_below_80hz: float
    plosive_burst_count: int
    recommended_clean_strength: float
    recommended_highpass_hz: int
    warnings: list[QCIssue] = field(default_factory=list)
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "duration_s": self.duration_s,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "peak_dbfs": self.peak_dbfs,
            "speech_rms_dbfs": self.speech_rms_dbfs,
            "noise_floor_dbfs": self.noise_floor_dbfs,
            "estimated_snr_db": self.estimated_snr_db,
            "clipped_sample_ratio": self.clipped_sample_ratio,
            "rumble_ratio_below_80hz": self.rumble_ratio_below_80hz,
            "plosive_burst_count": self.plosive_burst_count,
            "recommended_clean_strength": self.recommended_clean_strength,
            "recommended_highpass_hz": self.recommended_highpass_hz,
            "warnings": [asdict(w) for w in self.warnings],
            "passed": self.passed,
        }


def audit_production_sound(media_path: Path) -> ProductionSoundReport:
    """Inspect raw field/VO audio for clipping, SNR, sub-80 Hz rumble, and plosive bursts."""
    src = media_path.expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Audio/media file not found: {src}")

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(src),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    info = json.loads(probe.stdout) if probe.returncode == 0 and probe.stdout.strip() else {}
    sr = 48000
    ch = 1
    dur = float((info.get("format") or {}).get("duration") or 0.0)
    for st in info.get("streams") or []:
        if st.get("codec_type") == "audio":
            sr = int(st.get("sample_rate") or 48000)
            ch = int(st.get("channels") or 1)
            dur = float(st.get("duration") or dur or 0.0)
            break

    dec_ch = 2 if ch >= 2 else 1
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vn",
            "-t",
            "120",
            "-ar",
            "48000",
            "-ac",
            str(dec_ch),
            "-f",
            "s16le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0 or len(proc.stdout) < 4:
        raise RuntimeError(f"Could not decode audio stream from {src}")

    pcm = array.array("h")
    usable = len(proc.stdout) - (len(proc.stdout) % (2 * dec_ch))
    pcm.frombytes(proc.stdout[:usable])
    n_samples = len(pcm)
    if dec_ch == 2:
        mono_pcm = [
            0.5 * (pcm[idx] + pcm[idx + 1]) for idx in range(0, n_samples - 1, 2)
        ]
    else:
        mono_pcm = [float(s) for s in pcm]
    n = len(mono_pcm)
    if dur <= 0.0:
        dur = round(n / 48000.0, 3)

    peak = 0
    clipped = 0
    for s in pcm:
        av = abs(s)
        if av > peak:
            peak = av
        if av >= 32700:
            clipped += 1
    peak_dbfs = round(20.0 * math.log10(max(peak, 1) / 32768.0), 2)
    clipped_ratio = round(clipped / max(1, n_samples), 6)

    # 2nd-order low-pass at 80 Hz prevents 120-240 Hz speech from tripping rumble.
    alpha_80 = (2.0 * math.pi * 80.0) / (48000.0 + 2.0 * math.pi * 80.0)
    alpha_120 = (2.0 * math.pi * 120.0) / (48000.0 + 2.0 * math.pi * 120.0)
    lp80_a = 0.0
    lp80_b = 0.0
    lp120_a = 0.0
    lp120_b = 0.0
    total_e = 0.0
    rumble_e = 0.0
    frame_n = 2400  # 50 ms @ 48 kHz
    frame_rms_dbs: list[float] = []
    sub_frame_rms_dbs: list[float] = []

    idx = 0
    while idx + frame_n <= n:
        f_sq = 0.0
        sub_sq = 0.0
        for k in range(idx, idx + frame_n):
            x = mono_pcm[k] / 32768.0
            lp80_a = (1.0 - alpha_80) * lp80_a + alpha_80 * x
            lp80_b = (1.0 - alpha_80) * lp80_b + alpha_80 * lp80_a
            lp120_a = (1.0 - alpha_120) * lp120_a + alpha_120 * x
            lp120_b = (1.0 - alpha_120) * lp120_b + alpha_120 * lp120_a
            total_e += x * x
            rumble_e += lp80_b * lp80_b
            f_sq += x * x
            sub_sq += lp120_b * lp120_b
        rms = math.sqrt(f_sq / frame_n)
        sub_rms = math.sqrt(sub_sq / frame_n)
        frame_rms_dbs.append(20.0 * math.log10(max(rms, 1e-6)))
        sub_frame_rms_dbs.append(20.0 * math.log10(max(sub_rms, 1e-6)))
        idx += frame_n

    if not frame_rms_dbs:
        frame_rms_dbs = [peak_dbfs]
        sub_frame_rms_dbs = [-60.0]

    sorted_rms = sorted(frame_rms_dbs)
    p05_idx = min(len(sorted_rms) - 1, max(0, int(0.05 * len(sorted_rms))))
    p95_idx = min(len(sorted_rms) - 1, max(0, int(0.95 * len(sorted_rms))))
    noise_floor_db = round(sorted_rms[p05_idx], 2)
    speech_rms_db = round(sorted_rms[p95_idx], 2)
    snr_db = round(max(0.0, speech_rms_db - noise_floor_db), 2)
    rumble_ratio = round(min(1.0, rumble_e / max(total_e, 1e-9)), 4)
    has_silence_floor = not (snr_db < 6.0 and noise_floor_db > -24.0)

    sorted_sub = sorted(sub_frame_rms_dbs)
    sub_med = sorted_sub[len(sorted_sub) // 2]
    plosive_thresh = max(-24.0, sub_med + 12.0)
    plosive_bursts = 0
    in_burst = False
    for val in sub_frame_rms_dbs:
        if val > plosive_thresh:
            if not in_burst:
                plosive_bursts += 1
                in_burst = True
        else:
            in_burst = False

    warnings: list[QCIssue] = []
    if clipped_ratio > 0.0005:
        warnings.append(
            QCIssue(
                severity="warning",
                code="CLIPPING_DETECTED",
                message=(
                    f"Digital clipping on {clipped_ratio:.4%} of samples "
                    f"(peak {peak_dbfs:.1f} dBFS)."
                ),
            )
        )
    if snr_db < 18.0 and has_silence_floor:
        warnings.append(
            QCIssue(
                severity="warning",
                code="LOW_PRODUCTION_SNR",
                message=(
                    f"Estimated SNR is {snr_db:.1f} dB (noise floor {noise_floor_db:.1f} dBFS); "
                    "increase noise reduction strength."
                ),
            )
        )
    if rumble_ratio > 0.28:
        warnings.append(
            QCIssue(
                severity="warning",
                code="WIND_RUMBLE_DETECTED",
                message=(
                    f"Sub-80 Hz energy ratio is {rumble_ratio:.2f} (> 0.28); "
                    "apply steep high-pass filtering before dialogue cleanup."
                ),
            )
        )
    if plosive_bursts >= 3:
        warnings.append(
            QCIssue(
                severity="warning",
                code="PLOSIVES_DETECTED",
                message=(
                    f"Detected {plosive_bursts} low-frequency plosive bursts; "
                    "raise high-pass cutoff above 100 Hz."
                ),
            )
        )

    rec_strength = 0.95 if snr_db < 18.0 else 0.78 if snr_db < 26.0 else 0.55
    rec_hpf = (
        120
        if (plosive_bursts >= 3 or rumble_ratio > 0.35)
        else (100 if rumble_ratio > 0.2 else 80)
    )

    return ProductionSoundReport(
        source_path=src,
        duration_s=round(dur, 3),
        sample_rate=sr,
        channels=ch,
        peak_dbfs=peak_dbfs,
        speech_rms_dbfs=speech_rms_db,
        noise_floor_dbfs=noise_floor_db,
        estimated_snr_db=snr_db,
        clipped_sample_ratio=clipped_ratio,
        rumble_ratio_below_80hz=rumble_ratio,
        plosive_burst_count=plosive_bursts,
        recommended_clean_strength=rec_strength,
        recommended_highpass_hz=rec_hpf,
        warnings=warnings,
        passed=True,
    )


def measure_spectral_translation(media_path: Path) -> dict[str, float] | None:
    """Measure sub-120 Hz vs speech-mid (500-4000 Hz) energy ratio for small-speaker translation."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-vn",
            "-t",
            "60",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0 or len(proc.stdout) < 32:
        return None
    pcm = array.array("h")
    usable = len(proc.stdout) - (len(proc.stdout) % 2)
    pcm.frombytes(proc.stdout[:usable])
    if len(pcm) < 64:
        return None

    sr = 16000.0
    a_low = (2.0 * math.pi * 120.0) / (sr + 2.0 * math.pi * 120.0)
    a_m_lo = (2.0 * math.pi * 500.0) / (sr + 2.0 * math.pi * 500.0)
    a_m_hi = (2.0 * math.pi * 4000.0) / (sr + 2.0 * math.pi * 4000.0)
    lp120 = 0.0
    lp500 = 0.0
    lp4000 = 0.0
    e_low = 0.0
    e_mid = 0.0
    for s in pcm:
        x = s / 32768.0
        lp120 = (1.0 - a_low) * lp120 + a_low * x
        lp500 = (1.0 - a_m_lo) * lp500 + a_m_lo * x
        lp4000 = (1.0 - a_m_hi) * lp4000 + a_m_hi * x
        mid = lp4000 - lp500
        e_low += lp120 * lp120
        e_mid += mid * mid
    if e_low < 1e-12 and e_mid < 1e-12:
        return None
    low_to_mid_db = round(10.0 * math.log10(max(e_low, 1e-12) / max(e_mid, 1e-12)), 2)
    return {"low_to_mid_db": low_to_mid_db}


def audit_mastered_deliverable(
    media_path: Path,
    platform_target: PlatformTarget,
    *,
    require_audio: bool = True,
    check_visual: bool = True,
    reference_path: Path | None = None,
    min_vmaf: float = 85.0,
    loudness_profile: str | None = None,
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

        target_lufs, max_tp_limit, target_lra, lufs_tol = resolve_loudness_profile(
            loudness_profile, platform_target
        )
        metrics["loudness_profile"] = loudness_profile or "platform_default"
        ebur = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(media_path),
                "-vn",
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
        spec_trans = measure_spectral_translation(media_path)
        if spec_trans is not None:
            metrics["low_to_mid_db"] = spec_trans["low_to_mid_db"]
            if spec_trans["low_to_mid_db"] > 12.0:
                warnings.append(
                    QCIssue(
                        severity="warning",
                        code="BASS_HEAVY_LOW_VOLUME_RISK",
                        message=(
                            f"Sub-120 Hz energy exceeds midrange by "
                            f"{spec_trans['low_to_mid_db']:.1f} dB; "
                            "bass detail may drop out on 58-65 dB SPL consumer playback."
                        ),
                    )
                )
        i_match = _EBUR128_I_RE.search(ebur.stderr)
        lra_match = _EBUR128_LRA_RE.search(ebur.stderr)
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
                diff = abs(lufs - target_lufs)
                if diff > lufs_tol:
                    errors.append(
                        QCIssue(
                            severity="error",
                            code="LOUDNESS_OUT_OF_TOLERANCE",
                            message=(
                                f"Integrated loudness {lufs:.2f} LUFS misses target "
                                f"{target_lufs:.1f} +/- {lufs_tol:.1f} LUFS."
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

        if ebur.returncode == 0 and lra_match:
            lra_val = float(lra_match.group(1))
            if math.isfinite(lra_val):
                metrics["loudness_range_lu"] = round(lra_val, 2)
                if lra_val > target_lra + 6.0:
                    warnings.append(
                        QCIssue(
                            severity="warning",
                            code="LRA_OUT_OF_RANGE",
                            message=(
                                f"Loudness range {lra_val:.2f} LU exceeds comfortable target "
                                f"{target_lra:.1f} LU (+6 LU allowance) for mobile playback."
                            ),
                        )
                    )

        if ch == 2:
            phase_corr = measure_mono_phase_correlation(media_path)
            if phase_corr is not None:
                metrics["mono_phase_correlation"] = phase_corr
                if phase_corr < 0.15:
                    warnings.append(
                        QCIssue(
                            severity="warning",
                            code="LOW_MONO_PHASE_CORRELATION",
                            message=(
                                f"Stereo phase correlation {phase_corr:.2f} (< 0.15) risks "
                                "phase cancellation when summed to mono."
                            ),
                        )
                    )

        if a_stream is not None and v_stream is not None:
            try:
                v_dur = float(v_stream.get("duration") or 0.0)
            except (TypeError, ValueError):
                v_dur = 0.0
            try:
                a_dur = float(a_stream.get("duration") or 0.0)
            except (TypeError, ValueError):
                a_dur = 0.0
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
            if math.isfinite(tp) and tp > max_tp_limit:
                errors.append(
                    QCIssue(
                        severity="error",
                        code="TRUE_PEAK_EXCEEDED",
                        message=(
                            f"True peak {tp:.2f} dBTP exceeds limit "
                            f"{max_tp_limit:.2f} dBTP."
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
