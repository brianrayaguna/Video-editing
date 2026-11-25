"""Deterministic editorial forensics: eye-trace, color harmony, split edits, and tension curve."""

from __future__ import annotations

import array
import colorsys
import json
import math
import statistics
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from vedit.mastering.qc_audit import measure_mono_phase_correlation

HarmonyClass = Literal[
    "monochromatic",
    "analogous",
    "complementary",
    "split_complementary",
    "triadic",
    "neutral",
]


@dataclass(slots=True)
class CutContinuityMetrics:
    """Measured visual continuity across a single edit boundary."""

    cut_s: float
    eye_trace_jump_norm: float
    delta_luma: float
    delta_lab_ab: float
    pre_motion_dir: str
    post_motion_dir: str
    direction_reversal: bool
    flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CutContinuityReport:
    """Aggregated cross-cut eye-trace, exposure, color-temperature, and motion continuity."""

    cuts_analyzed: int
    mean_eye_trace_jump: float
    max_eye_trace_jump: float
    mean_delta_luma: float
    mean_delta_lab_ab: float
    direction_reversals: int
    exposure_shocks: int
    color_harmony_class: HarmonyClass
    dominant_lighting_key: Literal[
        "high_key", "normal_key", "low_key", "chiaroscuro"
    ] = "normal_key"
    mean_rule_of_thirds_score: float = 0.0
    mean_symmetry_index: float = 0.0
    mean_warm_cool_balance: float = 0.0
    per_cut: list[CutContinuityMetrics] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SplitEditEvent:
    """Classification of one video cut against nearby audio/speech onset."""

    cut_s: float
    kind: Literal["j_cut", "l_cut", "straight_cut"]
    audio_offset_s: float


@dataclass(slots=True)
class SplitEditReport:
    """Measured J-cut / L-cut / straight-cut breakdown across a timeline."""

    total_cuts: int
    j_cut_count: int
    l_cut_count: int
    straight_cut_count: int
    j_cut_ratio: float
    l_cut_ratio: float
    median_j_lead_s: float | None
    median_l_trail_s: float | None
    events: list[SplitEditEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TensionCurveBin:
    """Single normalized timeline bin on the multi-modal tension curve."""

    bin_index: int
    start_s: float
    end_s: float
    wpm: float
    cut_rate_per_min: float
    audio_rms_norm: float
    storyboard_tension: float | None
    tension_0_1: float


@dataclass(slots=True)
class TensionCurveReport:
    """Multi-modal narrative tension curve and pacing-variety diagnostics."""

    bins: list[TensionCurveBin]
    pacing_variance: float
    escalation_slope: float
    peak_bin_ratio: float
    flat_pacing_warning: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EditorialForensicsReport:
    """Combined continuity, split-edit, audio-health, and tension-curve forensic report."""

    source_path: str
    duration_s: float
    fps: float
    continuity: CutContinuityReport
    split_edits: SplitEditReport
    tension_curve: TensionCurveReport
    mono_phase_correlation: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "duration_s": self.duration_s,
            "fps": self.fps,
            "continuity": self.continuity.to_dict(),
            "split_edits": self.split_edits.to_dict(),
            "tension_curve": self.tension_curve.to_dict(),
            "mono_phase_correlation": self.mono_phase_correlation,
        }


def _probe_video_meta(media_path: Path) -> tuple[float, float]:
    proc = subprocess.run(
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
    if proc.returncode != 0:
        return (0.0, 30.0)
    info = json.loads(proc.stdout)
    dur = float(info.get("format", {}).get("duration") or 0.0)
    fps = 30.0
    for st in info.get("streams") or []:
        if st.get("codec_type") == "video":
            rate = str(st.get("r_frame_rate") or "30/1")
            if "/" in rate:
                a, b = rate.split("/", 1)
                if float(b) > 0:
                    fps = float(a) / float(b)
            else:
                fps = float(rate)
            if dur <= 0:
                dur = float(st.get("duration") or 0.0)
            break
    return (max(0.0, dur), max(1.0, fps))


def _extract_rgb_frame(
    media_path: Path, timestamp_s: float, width: int, height: int
) -> bytes | None:
    expected = width * height * 3
    t_val = max(0.0, float(timestamp_s))
    coarse = max(0.0, t_val - 0.5)
    fine = max(0.0, t_val - coarse)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{coarse:.4f}",
            "-i",
            str(media_path),
            "-ss",
            f"{fine:.4f}",
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:{height}:flags=area,format=rgb24",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0 or len(proc.stdout) < expected:
        return None
    return proc.stdout[:expected]


def _rgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert sRGB `[0..255]` to approximate CIELAB `(L*, a*, b*)`."""
    def _lin(c: float) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    rl, gl, bl = _lin(r), _lin(g), _lin(b)
    x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / 0.95047
    y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
    z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) / 1.08883

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else (7.787 * t + 16.0 / 116.0)

    fx, fy, fz = _f(x), _f(y), _f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _frame_stats(
    buf: bytes, width: int, height: int
) -> tuple[tuple[float, float], float, tuple[float, float], list[float]]:
    """Return `(saliency_centroid_xy, mean_luma, (lab_a, lab_b), saturated_hue_degs)`."""
    n_px = width * height
    lumas = [0.0] * n_px
    sum_r = sum_g = sum_b = 0.0
    hues: list[float] = []

    for i in range(n_px):
        off = i * 3
        r, g, b = buf[off], buf[off + 1], buf[off + 2]
        sum_r += r
        sum_g += g
        sum_b += b
        lumas[i] = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if i % 4 == 0:
            h, l_val, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            if s >= 0.25 and 0.12 <= l_val <= 0.88:
                hues.append(h * 360.0)

    mean_luma = sum(lumas) / max(1, n_px)
    _, lab_a, lab_b = _rgb_to_lab(sum_r / n_px, sum_g / n_px, sum_b / n_px)

    # Spatial saliency combines local edge gradient + luminance deviation from frame mean.
    wx = wy = w_sum = 0.0
    for y in range(1, height - 1):
        row = y * width
        for x in range(1, width - 1):
            idx = row + x
            gx = abs(lumas[idx + 1] - lumas[idx - 1])
            gy = abs(lumas[idx + width] - lumas[idx - width])
            dev = abs(lumas[idx] - mean_luma)
            sal = gx + gy + 0.5 * dev
            if sal > 18.0:
                wx += (x / max(width - 1, 1)) * sal
                wy += (y / max(height - 1, 1)) * sal
                w_sum += sal

    if w_sum > 1e-3:
        centroid = (round(wx / w_sum, 4), round(wy / w_sum, 4))
    else:
        centroid = (0.5, 0.5)
    return centroid, mean_luma, (lab_a, lab_b), hues


def _estimate_motion_dir(
    c_prev: tuple[float, float], c_curr: tuple[float, float], thresh: float = 0.015
) -> str:
    dx = c_curr[0] - c_prev[0]
    dy = c_curr[1] - c_prev[1]
    if abs(dx) < thresh and abs(dy) < thresh:
        return "static"
    if abs(dx) >= abs(dy):
        return "left_to_right" if dx > 0 else "right_to_left"
    return "down" if dy > 0 else "up"


def _classify_color_harmony(hue_samples: list[float]) -> HarmonyClass:
    if len(hue_samples) < 8:
        return "neutral"
    # Bin hues into 12 x 30-degree wheel sectors and take top 3 peaks.
    bins = [0] * 12
    for deg in hue_samples:
        bins[int(deg // 30) % 12] += 1
    ranked = sorted(
        ((cnt, idx * 30.0 + 15.0) for idx, cnt in enumerate(bins) if cnt > 0),
        reverse=True,
    )
    if not ranked:
        return "neutral"
    if len(ranked) == 1 or ranked[0][0] >= sum(c for c, _ in ranked) * 0.72:
        return "monochromatic"

    h0 = ranked[0][1]
    h1 = ranked[1][1]
    diff = abs(h1 - h0)
    diff = min(diff, 360.0 - diff)
    if diff <= 45.0:
        return "analogous"
    if 150.0 <= diff <= 180.0:
        return "complementary"
    if len(ranked) >= 3:
        h2 = ranked[2][1]
        d02 = min(abs(h2 - h0), 360.0 - abs(h2 - h0))
        d12 = min(abs(h2 - h1), 360.0 - abs(h2 - h1))
        if 95.0 <= diff <= 145.0 and 95.0 <= d02 <= 145.0 and 95.0 <= d12 <= 145.0:
            return "triadic"
        if 125.0 <= diff <= 165.0 and 125.0 <= d02 <= 165.0:
            return "split_complementary"
    return "analogous" if diff <= 75.0 else "complementary"


def _cinematography_frame_metrics(
    buf: bytes,
    width: int,
    height: int,
    centroid: tuple[float, float],
) -> tuple[Literal["high_key", "normal_key", "low_key", "chiaroscuro"], float, float, float]:
    """Return `(lighting_key, rule_of_thirds_score, symmetry_index, warm_cool_balance)`."""
    n_px = width * height
    lumas = [0.0] * n_px
    sum_rb = 0.0
    dark_px = 0
    bright_px = 0
    for i in range(n_px):
        off = i * 3
        r, g, b = buf[off], buf[off + 1], buf[off + 2]
        y_val = 0.2126 * r + 0.7152 * g + 0.0722 * b
        lumas[i] = y_val
        sum_rb += (r - b) / 255.0
        if y_val < 52.0:
            dark_px += 1
        elif y_val > 195.0:
            bright_px += 1

    mean_luma = sum(lumas) / max(1, n_px)
    var = sum((v - mean_luma) ** 2 for v in lumas) / max(1, n_px)
    rms_contrast = math.sqrt(var)
    dark_frac = dark_px / max(1, n_px)
    bright_frac = bright_px / max(1, n_px)
    if dark_frac > 0.35 and bright_frac > 0.12 and rms_contrast >= 58.0:
        light_key: Literal["high_key", "normal_key", "low_key", "chiaroscuro"] = "chiaroscuro"
    elif mean_luma >= 158.0 and dark_frac < 0.18:
        light_key = "high_key"
    elif mean_luma <= 82.0:
        light_key = "low_key"
    else:
        light_key = "normal_key"

    thirds_pts = (
        (1.0 / 3.0, 1.0 / 3.0),
        (2.0 / 3.0, 1.0 / 3.0),
        (1.0 / 3.0, 2.0 / 3.0),
        (2.0 / 3.0, 2.0 / 3.0),
    )
    min_d = min(math.hypot(centroid[0] - px, centroid[1] - py) for px, py in thirds_pts)
    rot_score = round(max(0.0, min(1.0, 1.0 - (min_d / 0.38))), 4)

    sym_err = 0.0
    half_w = max(1, width // 2)
    sym_cnt = 0
    for y in range(0, height, 2):
        row = y * width
        for x in range(0, half_w, 2):
            diff = abs(lumas[row + x] - lumas[row + (width - 1 - x)]) / 255.0
            sym_err += diff
            sym_cnt += 1
    sym_idx = round(max(0.0, min(1.0, 1.0 - (sym_err / max(1, sym_cnt)))), 4)
    warm_cool = round(max(-1.0, min(1.0, sum_rb / max(1, n_px))), 4)
    return (light_key, rot_score, sym_idx, warm_cool)


def analyze_cross_cut_continuity(
    media_path: Path,
    cuts_s: list[float],
    *,
    sample_size: tuple[int, int] = (128, 72),
    max_cuts: int = 24,
) -> CutContinuityReport:
    """Measure eye-trace, exposure shock, Lab shift, lighting key, thirds, symmetry, and motion."""
    dur, fps = _probe_video_meta(media_path)
    w, h = sample_size
    dt = 1.0 / max(fps, 1.0)
    margin = max(2.0 * dt, 0.10)
    valid_cuts = sorted(
        {round(float(c), 4) for c in cuts_s if margin + dt < float(c) < dur - (margin + dt)}
    )[:max_cuts]

    per_cut: list[CutContinuityMetrics] = []
    all_hues: list[float] = []
    light_keys: list[Literal["high_key", "normal_key", "low_key", "chiaroscuro"]] = []
    rot_scores: list[float] = []
    sym_scores: list[float] = []
    wb_scores: list[float] = []
    issues: list[str] = []

    for cut_t in valid_cuts:
        f_pre2 = _extract_rgb_frame(media_path, max(0.0, cut_t - margin - dt), w, h)
        f_pre1 = _extract_rgb_frame(media_path, max(0.0, cut_t - margin), w, h)
        f_post1 = _extract_rgb_frame(media_path, min(dur - dt, cut_t + margin), w, h)
        f_post2 = _extract_rgb_frame(media_path, min(dur - dt, cut_t + margin + dt), w, h)
        if not (f_pre1 and f_post1):
            continue

        c_pre1, luma_pre, ab_pre, hues_pre = _frame_stats(f_pre1, w, h)
        c_post1, luma_post, ab_post, hues_post = _frame_stats(f_post1, w, h)
        lk_pre, rot_pre, sym_pre, wb_pre = _cinematography_frame_metrics(f_pre1, w, h, c_pre1)
        lk_post, rot_post, sym_post, wb_post = _cinematography_frame_metrics(f_post1, w, h, c_post1)
        light_keys.extend((lk_pre, lk_post))
        rot_scores.extend((rot_pre, rot_post))
        sym_scores.extend((sym_pre, sym_post))
        wb_scores.extend((wb_pre, wb_post))
        all_hues.extend(hues_pre)
        all_hues.extend(hues_post)

        eye_jump = round(math.hypot(c_post1[0] - c_pre1[0], c_post1[1] - c_pre1[1]), 4)
        delta_luma = round(abs(luma_post - luma_pre), 2)
        delta_ab = round(math.hypot(ab_post[0] - ab_pre[0], ab_post[1] - ab_pre[1]), 2)

        pre_dir = "static"
        post_dir = "static"
        if f_pre2:
            c_pre2, *_ = _frame_stats(f_pre2, w, h)
            pre_dir = _estimate_motion_dir(c_pre2, c_pre1)
        if f_post2:
            c_post2, *_ = _frame_stats(f_post2, w, h)
            post_dir = _estimate_motion_dir(c_post1, c_post2)

        dir_rev = (
            pre_dir in ("left_to_right", "right_to_left")
            and post_dir in ("left_to_right", "right_to_left")
            and pre_dir != post_dir
        )
        flags: list[str] = []
        if eye_jump > 0.38:
            flags.append("large_eye_jump")
        if delta_luma > 45.0:
            flags.append("exposure_shock")
        if delta_ab > 22.0:
            flags.append("unmatched_grade_jump")
        if dir_rev:
            flags.append("direction_reversal")

        per_cut.append(
            CutContinuityMetrics(
                cut_s=round(cut_t, 3),
                eye_trace_jump_norm=eye_jump,
                delta_luma=delta_luma,
                delta_lab_ab=delta_ab,
                pre_motion_dir=pre_dir,
                post_motion_dir=post_dir,
                direction_reversal=dir_rev,
                flags=flags,
            )
        )

    if not per_cut:
        mid_buf = _extract_rgb_frame(media_path, dur * 0.5, w, h)
        if mid_buf:
            c_mid, _, _, mid_hues = _frame_stats(mid_buf, w, h)
            all_hues.extend(mid_hues)
            lk_m, rot_m, sym_m, wb_m = _cinematography_frame_metrics(mid_buf, w, h, c_mid)
            light_keys.append(lk_m)
            rot_scores.append(rot_m)
            sym_scores.append(sym_m)
            wb_scores.append(wb_m)
        dom_lk: Literal["high_key", "normal_key", "low_key", "chiaroscuro"] = (
            min(set(light_keys), key=lambda k: (-light_keys.count(k), k))
            if light_keys
            else "normal_key"
        )
        return CutContinuityReport(
            cuts_analyzed=0,
            mean_eye_trace_jump=0.0,
            max_eye_trace_jump=0.0,
            mean_delta_luma=0.0,
            mean_delta_lab_ab=0.0,
            direction_reversals=0,
            exposure_shocks=0,
            color_harmony_class=_classify_color_harmony(all_hues),
            dominant_lighting_key=dom_lk,
            mean_rule_of_thirds_score=round(rot_scores[0], 4) if rot_scores else 0.0,
            mean_symmetry_index=round(sym_scores[0], 4) if sym_scores else 0.0,
            mean_warm_cool_balance=round(wb_scores[0], 4) if wb_scores else 0.0,
            per_cut=[],
            issues=[],
        )

    mean_eye = round(sum(c.eye_trace_jump_norm for c in per_cut) / len(per_cut), 4)
    max_eye = round(max(c.eye_trace_jump_norm for c in per_cut), 4)
    mean_luma = round(sum(c.delta_luma for c in per_cut) / len(per_cut), 2)
    mean_ab = round(sum(c.delta_lab_ab for c in per_cut) / len(per_cut), 2)
    revs = sum(1 for c in per_cut if c.direction_reversal)
    shocks = sum(1 for c in per_cut if "exposure_shock" in c.flags)
    dom_lk = (
        min(set(light_keys), key=lambda k: (-light_keys.count(k), k))
        if light_keys
        else "normal_key"
    )

    if mean_eye > 0.35:
        issues.append(f"mean cross-cut eye-trace displacement {mean_eye:.2f} exceeds 0.35")
    if shocks > 0:
        issues.append(f"{shocks} cut(s) show abrupt luminance exposure shock (> 45 luma)")
    if revs > 0:
        issues.append(f"{revs} cut(s) reverse horizontal motion direction")

    return CutContinuityReport(
        cuts_analyzed=len(per_cut),
        mean_eye_trace_jump=mean_eye,
        max_eye_trace_jump=max_eye,
        mean_delta_luma=mean_luma,
        mean_delta_lab_ab=mean_ab,
        direction_reversals=revs,
        exposure_shocks=shocks,
        color_harmony_class=_classify_color_harmony(all_hues),
        dominant_lighting_key=dom_lk,
        mean_rule_of_thirds_score=round(sum(rot_scores) / max(1, len(rot_scores)), 4),
        mean_symmetry_index=round(sum(sym_scores) / max(1, len(sym_scores)), 4),
        mean_warm_cool_balance=round(sum(wb_scores) / max(1, len(wb_scores)), 4),
        per_cut=per_cut,
        issues=issues,
    )


def detect_split_edits(
    cuts_s: list[float],
    speech_intervals_s: list[tuple[float, float]] | None = None,
    audio_onsets_s: list[float] | None = None,
    *,
    window_s: float = 1.2,
    deadzone_s: float = 0.08,
) -> SplitEditReport:
    """Classify each visual cut as J-cut, L-cut, or straight cut using audio continuity."""
    events: list[SplitEditEvent] = []
    j_leads: list[float] = []
    l_trails: list[float] = []
    intervals = sorted(
        ((float(st), float(en)) for st, en in (speech_intervals_s or []) if float(en) > float(st))
    )
    onset_anchors = sorted({float(t) for t in (audio_onsets_s or [])})

    for cut in sorted(cuts_s):
        c_val = float(cut)
        if intervals:
            spanning = next(
                (
                    (st, en)
                    for st, en in intervals
                    if st < c_val - deadzone_s and en > c_val + deadzone_s
                ),
                None,
            )
            if spanning is None:
                events.append(
                    SplitEditEvent(cut_s=round(c_val, 3), kind="straight_cut", audio_offset_s=0.0)
                )
                continue
            lead = c_val - spanning[0]
            trail = spanning[1] - c_val
            if lead <= window_s and (trail > lead or trail > window_s):
                offset = -round(lead, 3)
                events.append(
                    SplitEditEvent(cut_s=round(c_val, 3), kind="j_cut", audio_offset_s=offset)
                )
                j_leads.append(lead)
            elif trail <= window_s:
                offset = round(trail, 3)
                events.append(
                    SplitEditEvent(cut_s=round(c_val, 3), kind="l_cut", audio_offset_s=offset)
                )
                l_trails.append(trail)
            else:
                events.append(
                    SplitEditEvent(cut_s=round(c_val, 3), kind="straight_cut", audio_offset_s=0.0)
                )
            continue

        nearby = [a for a in onset_anchors if abs(a - c_val) <= window_s]
        if not nearby:
            events.append(
                SplitEditEvent(cut_s=round(c_val, 3), kind="straight_cut", audio_offset_s=0.0)
            )
            continue
        nearest = min(nearby, key=lambda a: abs(a - c_val))
        offset = round(nearest - c_val, 3)
        if offset <= -deadzone_s:
            events.append(
                SplitEditEvent(cut_s=round(c_val, 3), kind="j_cut", audio_offset_s=offset)
            )
            j_leads.append(abs(offset))
        else:
            events.append(
                SplitEditEvent(
                    cut_s=round(c_val, 3),
                    kind="straight_cut",
                    audio_offset_s=offset if abs(offset) < deadzone_s else 0.0,
                )
            )

    total = len(events)
    j_cnt = sum(1 for e in events if e.kind == "j_cut")
    l_cnt = sum(1 for e in events if e.kind == "l_cut")
    s_cnt = total - j_cnt - l_cnt
    return SplitEditReport(
        total_cuts=total,
        j_cut_count=j_cnt,
        l_cut_count=l_cnt,
        straight_cut_count=s_cnt,
        j_cut_ratio=round(j_cnt / total, 4) if total else 0.0,
        l_cut_ratio=round(l_cnt / total, 4) if total else 0.0,
        median_j_lead_s=round(float(statistics.median(j_leads)), 3) if j_leads else None,
        median_l_trail_s=round(float(statistics.median(l_trails)), 3) if l_trails else None,
        events=events,
    )


def _extract_audio_rms_series(media_path: Path, duration_s: float, bins: int) -> list[float]:
    """Compute normalized `[0..1]` RMS energy across `bins` timeline windows via FFmpeg."""
    if duration_s <= 0 or bins <= 0:
        return [0.0] * max(1, bins)
    sr = 4000
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
            str(sr),
            "-ac",
            "1",
            "-f",
            "s16le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0 or len(proc.stdout) < 4:
        return [0.0] * bins
    pcm = array.array("h")
    usable = len(proc.stdout) - (len(proc.stdout) % 2)
    pcm.frombytes(proc.stdout[:usable])
    if not pcm:
        return [0.0] * bins
    step = max(1, len(pcm) // bins)
    raw_rms: list[float] = []
    for i in range(bins):
        chunk = pcm[i * step : (i + 1) * step if i < bins - 1 else len(pcm)]
        if not chunk:
            raw_rms.append(0.0)
            continue
        mean_sq = sum(float(s) * float(s) for s in chunk) / len(chunk)
        raw_rms.append(math.sqrt(mean_sq))
    peak = max(raw_rms) or 1.0
    return [round(v / peak, 4) for v in raw_rms]


def compute_multimodal_tension_curve(
    duration_s: float,
    *,
    transcript: dict[str, Any] | None = None,
    storyboard: dict[str, Any] | None = None,
    cuts_s: list[float] | None = None,
    audio_rms_series: list[float] | None = None,
    bins: int = 10,
) -> TensionCurveReport:
    """Fuse speaking rate, visual cut/beat density, storyboard tension, and audio RMS."""
    dur = max(0.5, float(duration_s))
    n_bins = max(2, bins)
    bin_dur = dur / n_bins
    words = [w for w in ((transcript or {}).get("words") or []) if str(w.get("text", "")).strip()]
    beats = list((storyboard or {}).get("beats") or [])
    cuts = [float(c) for c in (cuts_s or []) if 0.0 < float(c) < dur]
    rms_vals = (
        audio_rms_series
        if audio_rms_series and len(audio_rms_series) == n_bins
        else [0.0] * n_bins
    )

    raw_bins: list[tuple[float, float, float, float | None]] = []
    for idx in range(n_bins):
        s0 = idx * bin_dur
        s1 = (idx + 1) * bin_dur
        w_cnt = sum(1 for w in words if s0 <= float(w.get("start_s", 0.0)) < s1)
        wpm = (w_cnt / bin_dur) * 60.0

        c_cnt = sum(1 for c in cuts if s0 <= c < s1)
        ev_cnt = (
            c_cnt
            if cuts
            else sum(
                1
                for b in beats
                if 0.05 < float(b.get("start_s", 0.0)) < dur
                and s0 <= float(b.get("start_s", 0.0)) < s1
            )
        )
        event_rate = (ev_cnt / bin_dur) * 60.0

        sb_tens = [
            float(b["tension_level"])
            for b in beats
            if b.get("tension_level") is not None
            and float(b.get("start_s", 0.0)) < s1
            and float(b.get("end_s", b.get("start_s", 0.0))) > s0
        ]
        mean_sb = (sum(sb_tens) / len(sb_tens)) if sb_tens else None
        raw_bins.append((wpm, event_rate, rms_vals[idx], mean_sb))

    max_wpm = max((r[0] for r in raw_bins), default=0.0) or 1.0
    max_rate = max((r[1] for r in raw_bins), default=0.0) or 1.0

    out_bins: list[TensionCurveBin] = []
    t_vals: list[float] = []
    for idx, (wpm, ev_rate, rms, sb_t) in enumerate(raw_bins):
        s0 = round(idx * bin_dur, 3)
        s1 = round((idx + 1) * bin_dur, 3)
        wpm_norm = min(1.0, wpm / max(180.0, max_wpm)) if words else 0.0
        rate_norm = min(1.0, ev_rate / max(24.0, max_rate)) if (cuts or beats) else 0.0

        parts: list[tuple[float, float]] = []
        if words:
            parts.append((wpm_norm, 0.30))
        if cuts or beats:
            parts.append((rate_norm, 0.30))
        if any(v > 0 for v in rms_vals):
            parts.append((rms, 0.20))
        if sb_t is not None:
            parts.append((sb_t, 0.40))

        if parts:
            w_tot = sum(w for _, w in parts)
            tension = round(sum(v * w for v, w in parts) / w_tot, 4)
        else:
            tension = 0.0
        t_vals.append(tension)
        out_bins.append(
            TensionCurveBin(
                bin_index=idx,
                start_s=s0,
                end_s=s1,
                wpm=round(wpm, 1),
                cut_rate_per_min=round(ev_rate, 1),
                audio_rms_norm=round(rms, 4),
                storyboard_tension=round(sb_t, 3) if sb_t is not None else None,
                tension_0_1=tension,
            )
        )

    variance = round(float(statistics.pstdev(t_vals)), 4) if len(t_vals) >= 2 else 0.0
    peak_idx = max(range(len(t_vals)), key=lambda i: t_vals[i]) if t_vals else 0
    peak_ratio = round((peak_idx + 0.5) / n_bins, 3)

    # Linear regression slope over normalized bin index [0..1].
    xs = [i / max(n_bins - 1, 1) for i in range(n_bins)]
    mx = sum(xs) / n_bins
    mt = sum(t_vals) / n_bins
    num = sum((x - mx) * (y - mt) for x, y in zip(xs, t_vals, strict=False))
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = round(num / den, 4)

    flat_warn = dur >= 20.0 and variance < 0.055 and any(v > 0 for v in t_vals)
    return TensionCurveReport(
        bins=out_bins,
        pacing_variance=variance,
        escalation_slope=slope,
        peak_bin_ratio=peak_ratio,
        flat_pacing_warning=flat_warn,
    )


def analyze_editorial_forensics(
    media_path: Path,
    *,
    cuts_s: list[float] | None = None,
    transcript: dict[str, Any] | None = None,
    storyboard: dict[str, Any] | None = None,
    bins: int = 10,
) -> EditorialForensicsReport:
    """Run full cross-cut continuity, split-edit, mono-phase, and tension-curve forensics."""
    src = media_path.expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Media file not found: {src}")
    dur, fps = _probe_video_meta(src)
    resolved_cuts = list(cuts_s or [])
    continuity = analyze_cross_cut_continuity(src, resolved_cuts)

    # Derive speech clause intervals from transcript when available.
    speech_intervals: list[tuple[float, float]] = []
    if transcript:
        words = [w for w in transcript.get("words") or [] if str(w.get("text", "")).strip()]
        if words:
            c_start = float(words[0]["start_s"])
            prev_end = float(words[0]["end_s"])
            for w in words[1:]:
                w_st = float(w["start_s"])
                if w_st - prev_end >= 0.22:
                    speech_intervals.append((c_start, prev_end))
                    c_start = w_st
                prev_end = float(w["end_s"])
            speech_intervals.append((c_start, prev_end))

    split_edits = detect_split_edits(resolved_cuts, speech_intervals_s=speech_intervals or None)
    rms_series = _extract_audio_rms_series(src, dur, bins)
    tension = compute_multimodal_tension_curve(
        dur,
        transcript=transcript,
        storyboard=storyboard,
        cuts_s=resolved_cuts,
        audio_rms_series=rms_series,
        bins=bins,
    )
    phase_corr = measure_mono_phase_correlation(src)
    return EditorialForensicsReport(
        source_path=str(src),
        duration_s=round(dur, 3),
        fps=round(fps, 3),
        continuity=continuity,
        split_edits=split_edits,
        tension_curve=tension,
        mono_phase_correlation=phase_corr,
    )
