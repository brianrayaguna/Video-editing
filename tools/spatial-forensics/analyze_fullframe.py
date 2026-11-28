#!/usr/bin/env python3
"""Native-FPS full-frame video forensic analyzer.

Processes every frame of a reference video to extract:
- Continuous optical-flow camera kinematics (pan, zoom log2/s, rotation, easing segments)
- Map and visual surface segmentation (satellite, parchment, dark vector, blueprint, 2D cutaway)
- Color palette, ocean/land sampling, vignette strength, and glow-bloom coverage
- Hard cuts, whip-zoom transitions, dissolves, and localized graphic event onsets
- Dense OCR typography, layout, halo/glow, tilt, and caption rail reconstruction
- Frame-aligned audio RMS, speech activity, and SFX transient impact sync
- Annotated timeline contact sheets and full-FPS transition burst strips plus FULLFRAME.md
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rapidocr_onnxruntime import RapidOCR

COLS = ("A", "B", "C", "D", "E", "F")


def _aspect_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "other"
    ratio = width / height
    for label, target in (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:5", 4 / 5)):
        if abs(ratio - target) <= 0.06:
            return label
    return "other"


def _rgb_to_hex(rgb: np.ndarray | tuple[float, float, float]) -> str:
    r, g, b = (int(np.clip(round(float(v)), 0, 255)) for v in rgb[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def _srgb_to_rel_luma(rgb: np.ndarray) -> float:
    c = np.clip(rgb.astype(np.float64) / 255.0, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])


def _wcag_contrast(rgb1: np.ndarray, rgb2: np.ndarray) -> float:
    l1 = _srgb_to_rel_luma(rgb1)
    l2 = _srgb_to_rel_luma(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return float(min(21.0, max(1.0, (hi + 0.05) / (lo + 0.05))))


def _grid_cell_label(x_norm: float, y_norm: float) -> str:
    col = COLS[min(len(COLS) - 1, max(0, int(x_norm * len(COLS))))]
    row = min(10, max(1, int(y_norm * 10) + 1))
    return f"{col}{row}"


def _classify_surface(small_bgr: np.ndarray, hsv: np.ndarray, gray: np.ndarray) -> dict[str, Any]:
    """Classify the cartographic or diagram surface style and sample map color roles."""
    h_ch = hsv[:, :, 0].astype(np.float32)  # 0..179 (OpenCV)
    s_ch = hsv[:, :, 1].astype(np.float32)  # 0..255
    v_ch = hsv[:, :, 2].astype(np.float32)  # 0..255

    mean_luma = float(gray.mean())
    mean_sat = float(s_ch.mean())

    # Vignette ratio: corner luminance / center luminance.
    sh, sw = gray.shape[:2]
    cy1, cy2 = int(sh * 0.25), int(sh * 0.75)
    cx1, cx2 = int(sw * 0.25), int(sw * 0.75)
    center_luma = float(gray[cy1:cy2, cx1:cx2].mean()) + 1e-4
    corner_mask = np.zeros_like(gray, dtype=bool)
    c_h, c_w = max(4, sh // 6), max(4, sw // 6)
    corner_mask[:c_h, :c_w] = True
    corner_mask[:c_h, -c_w:] = True
    corner_mask[-c_h:, :c_w] = True
    corner_mask[-c_h:, -c_w:] = True
    corner_luma = float(gray[corner_mask].mean())
    vignette_ratio = round(min(2.0, corner_luma / center_luma), 4)

    # Color masks in OpenCV HSV space (H: 0..179).
    ocean_teal_mask = (h_ch >= 82) & (h_ch <= 112) & (s_ch >= 45) & (v_ch >= 18) & (v_ch <= 145)
    blueprint_mask = (h_ch >= 100) & (h_ch <= 122) & (s_ch >= 90) & (v_ch >= 55) & (v_ch <= 175)
    land_earth_mask = (
        (((h_ch >= 12) & (h_ch <= 68)) & (s_ch >= 22) & (v_ch >= 35) & (v_ch <= 215))
    )
    parchment_mask = (h_ch >= 14) & (h_ch <= 28) & (s_ch >= 20) & (s_ch <= 105) & (v_ch >= 125) & (v_ch <= 220)
    dark_obs_mask = (v_ch <= 40) & (s_ch <= 65)
    sky_bright_mask = (s_ch <= 45) & (v_ch >= 175)
    glow_mask = (s_ch >= 150) & (v_ch >= 175)

    n_px = float(gray.size)
    ocean_ratio = float(ocean_teal_mask.sum()) / n_px
    blueprint_ratio = float(blueprint_mask.sum()) / n_px
    land_ratio = float(land_earth_mask.sum()) / n_px
    parchment_ratio = float(parchment_mask.sum()) / n_px
    dark_ratio = float(dark_obs_mask.sum()) / n_px
    glow_ratio = float(glow_mask.sum()) / n_px

    # Flat-vector quantization proxy: fraction of pixels with tiny local gradient.
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)
    flat_ratio = float((grad_mag < 8.0).mean())
    top_sky_ratio = float(sky_bright_mask[: max(1, sh // 3), :].mean())

    # Surface classification decision rules.
    if blueprint_ratio >= 0.42 and flat_ratio >= 0.55:
        surface = "blueprint_grid"
    elif dark_ratio >= 0.62 and ocean_ratio < 0.15:
        surface = "dark_vector"
    elif flat_ratio >= 0.64 and ocean_ratio < 0.12 and top_sky_ratio >= 0.25:
        surface = "flat_2d_cutaway"
    elif top_sky_ratio >= 0.45 and ocean_ratio < 0.08 and mean_luma >= 125:
        surface = "ground_illustration"
    elif parchment_ratio >= 0.36 and ocean_ratio < 0.20:
        surface = "parchment_map"
    elif (ocean_ratio + land_ratio) >= 0.35 or (ocean_ratio >= 0.12):
        surface = "satellite_relief"
    elif flat_ratio >= 0.72:
        surface = "flat_2d_cutaway"
    else:
        surface = "satellite_relief" if land_ratio >= 0.25 else "live_or_other"

    rgb = small_bgr[:, :, ::-1]
    ocean_hex = _rgb_to_hex(np.median(rgb[ocean_teal_mask], axis=0)) if ocean_teal_mask.sum() > 40 else None
    land_hex = _rgb_to_hex(np.median(rgb[land_earth_mask], axis=0)) if land_earth_mask.sum() > 40 else None

    # Accent hue buckets for glowing overlays.
    accent_hues: list[str] = []
    if glow_ratio >= 0.004:
        gh = h_ch[glow_mask]
        buckets = [
            ("crimson_red", ((gh <= 10) | (gh >= 168)).mean()),
            ("amber_gold", ((gh >= 15) & (gh <= 34)).mean()),
            ("emerald_green", ((gh >= 38) & (gh <= 82)).mean()),
            ("hydro_cyan", ((gh >= 83) & (gh <= 108)).mean()),
            ("cobalt_blue", ((gh >= 109) & (gh <= 135)).mean()),
        ]
        accent_hues = [name for name, frac in buckets if frac >= 0.12]

    return {
        "surface_class": surface,
        "mean_luma": round(mean_luma, 2),
        "mean_sat": round(mean_sat, 2),
        "vignette_ratio": vignette_ratio,
        "glow_coverage": round(glow_ratio, 4),
        "flat_ratio": round(flat_ratio, 4),
        "ocean_hex": ocean_hex,
        "land_hex": land_hex,
        "accent_hues": accent_hues,
    }


def _extract_dominant_palette(bgr: np.ndarray, k: int = 5) -> list[str]:
    """Fast deterministic quantized palette extraction."""
    small = cv2.resize(bgr, (96, 96), interpolation=cv2.INTER_AREA)
    rgb = small[:, :, ::-1].reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 2.0)
    _, labels, centers = cv2.kmeans(rgb, k, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    order = np.argsort(-counts)
    return [_rgb_to_hex(centers[i]) for i in order]


def _extract_audio_forensics(
    video_path: Path, fps: float, frame_count: int
) -> tuple[list[float], list[float], list[dict[str, Any]], float]:
    """Extract 16 kHz mono PCM and compute frame-aligned RMS dB, spectral flux, and transients."""
    sr = 16000
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "f32le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        zeros = [-60.0] * frame_count
        flux_z = [0.0] * frame_count
        return zeros, flux_z, [], 0.0

    pcm = np.frombuffer(proc.stdout, dtype=np.float32)
    samples_per_frame = max(1, int(round(sr / max(fps, 1.0))))
    rms_db_per_frame: list[float] = []
    flux_per_frame: list[float] = []
    speech_energy: list[float] = []
    band_energies: list[tuple[float, float, float]] = []

    prev_mag: np.ndarray | None = None
    win = np.hanning(max(64, samples_per_frame)).astype(np.float32)
    freqs = np.fft.rfftfreq(len(win), d=1.0 / sr)
    sub_mask = freqs < 140.0
    mid_mask = (freqs >= 140.0) & (freqs < 2800.0)
    speech_mask = (freqs >= 300.0) & (freqs <= 3400.0)
    high_mask = freqs >= 2800.0

    for fi in range(frame_count):
        s0 = int(round(fi * sr / max(fps, 1.0)))
        seg = pcm[s0 : s0 + len(win)]
        if len(seg) < len(win):
            seg = np.pad(seg, (0, len(win) - len(seg)))
        rms = float(np.sqrt(np.mean(seg * seg) + 1e-12))
        db = round(max(-60.0, 20.0 * math.log10(rms)), 2)
        rms_db_per_frame.append(db)

        mag = np.abs(np.fft.rfft(seg * win))
        if prev_mag is None:
            flux = 0.0
        else:
            diff = np.maximum(0.0, mag - prev_mag)
            flux = float(np.sum(diff) / (np.sum(mag) + 1e-6))
        prev_mag = mag
        flux_per_frame.append(round(flux, 4))

        sp_e = float(np.mean(mag[speech_mask])) if speech_mask.any() else 0.0
        speech_energy.append(sp_e)
        band_energies.append(
            (
                float(np.mean(mag[sub_mask])) if sub_mask.any() else 0.0,
                float(np.mean(mag[mid_mask])) if mid_mask.any() else 0.0,
                float(np.mean(mag[high_mask])) if high_mask.any() else 0.0,
            )
        )

    speech_thresh = max(0.05, float(np.percentile(speech_energy, 25)) * 1.4) if speech_energy else 0.1
    speech_active = sum(1 for v in speech_energy if v >= speech_thresh) / max(1, len(speech_energy))

    # Detect audio transient spikes (SFX impacts / whooshes / pops).
    flux_arr = np.array(flux_per_frame, dtype=np.float64)
    rms_arr = np.array(rms_db_per_frame, dtype=np.float64)
    flux_med = float(np.median(flux_arr)) if len(flux_arr) else 0.0
    flux_std = float(np.std(flux_arr)) if len(flux_arr) else 0.0
    thresh = max(0.32, flux_med + 2.0 * flux_std)

    transients: list[dict[str, Any]] = []
    min_gap_frames = max(3, int(round(fps * 0.22)))
    last_fi = -min_gap_frames
    for fi in range(1, len(flux_arr) - 1):
        if fi - last_fi < min_gap_frames:
            continue
        if flux_arr[fi] >= thresh and flux_arr[fi] >= flux_arr[fi - 1] and flux_arr[fi] >= flux_arr[fi + 1]:
            if rms_arr[fi] < -42.0:
                continue
            sub_e, mid_e, high_e = band_energies[fi]
            tot = sub_e + mid_e + high_e + 1e-9
            if sub_e / tot >= 0.45:
                band = "sub_bass"
            elif high_e / tot >= 0.35:
                band = "high_whoosh"
            elif mid_e / tot >= 0.50:
                band = "mid_impact"
            else:
                band = "broadband"
            transients.append(
                {
                    "frame_index": fi,
                    "timestamp_s": round(fi / fps, 4),
                    "strength_db": round(float(rms_arr[fi]), 2),
                    "band": band,
                }
            )
            last_fi = fi

    return rms_db_per_frame, flux_per_frame, transients, round(speech_active, 4)


def _nearest_transient_offset_ms(t_s: float, transients: list[dict[str, Any]], max_ms: float = 650.0) -> float | None:
    if not transients:
        return None
    best = min(transients, key=lambda tr: abs(tr["timestamp_s"] - t_s))
    delta_ms = (best["timestamp_s"] - t_s) * 1000.0
    if abs(delta_ms) <= max_ms:
        return round(delta_ms, 1)
    return None


def _classify_easing_shape(speeds: list[float]) -> str:
    if not speeds or max(speeds) < 1e-4:
        return "static_hold"
    n = len(speeds)
    if n < 4:
        return "constant_drift"
    peak_idx = int(np.argmax(speeds))
    peak_pos = peak_idx / max(1, n - 1)
    start_r = speeds[0] / (speeds[peak_idx] + 1e-6)
    end_r = speeds[-1] / (speeds[peak_idx] + 1e-6)
    if start_r > 0.65 and end_r > 0.65:
        return "constant_drift"
    if peak_pos >= 0.72 and end_r >= 0.65:
        return "accel_dive"
    if peak_pos <= 0.28 and start_r >= 0.65:
        return "decel_settle"
    return "bell_glide"


def _sample_text_visuals(bgr: np.ndarray, bbox: tuple[int, int, int, int]) -> dict[str, Any]:
    """Measure foreground ink, background ring, dark halo, glow halo, and container style."""
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = max(0, bbox[0]), max(0, bbox[1]), min(w, bbox[2]), min(h, bbox[3])
    crop = bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return {
            "fg_hex": "#FFFFFF",
            "bg_hex": "#000000",
            "wcag_contrast": 1.0,
            "has_dark_halo": False,
            "has_glow_halo": False,
            "glow_hex": None,
            "container_style": "boxless",
        }
    pad = max(4, min(16, int(round((y2 - y1) * 0.28))))
    ox1, oy1, ox2, oy2 = max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)
    outer = bgr[oy1:oy2, ox1:ox2]
    mask = np.ones(outer.shape[:2], dtype=bool)
    mask[(y1 - oy1) : (y2 - oy1), (x1 - ox1) : (x2 - ox1)] = False
    ring_bgr = outer[mask]
    if ring_bgr.size == 0:
        ring_bgr = crop.reshape(-1, 3)

    ring_rgb = ring_bgr[:, ::-1].astype(np.float64)
    bg_rgb = np.median(ring_rgb, axis=0)
    bg_luma = _srgb_to_rel_luma(bg_rgb)

    crop_rgb = crop.reshape(-1, 3)[:, ::-1].astype(np.float64)
    c_norm = np.clip(crop_rgb / 255.0, 0.0, 1.0)
    c_lin = np.where(c_norm <= 0.04045, c_norm / 12.92, ((c_norm + 0.055) / 1.055) ** 2.4)
    crop_luma = 0.2126 * c_lin[:, 0] + 0.7152 * c_lin[:, 1] + 0.0722 * c_lin[:, 2]
    diff = np.abs(crop_luma - bg_luma)
    top_k = crop_rgb[diff >= np.percentile(diff, 82)]
    fg_rgb = np.median(top_k, axis=0) if len(top_k) > 0 else np.median(crop_rgb, axis=0)
    contrast = round(_wcag_contrast(fg_rgb, bg_rgb), 2)

    # Dark halo vs luminous glow halo detection in immediate 4px rim.
    ring_hsv = cv2.cvtColor(ring_bgr.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    dark_halo = bool(float((ring_hsv[:, 2] < 48).mean()) >= 0.22 and _srgb_to_rel_luma(fg_rgb) > 0.35)
    glow_px = ring_rgb[(ring_hsv[:, 1] >= 135) & (ring_hsv[:, 2] >= 165)]
    has_glow = len(glow_px) >= max(8, int(len(ring_rgb) * 0.14))
    glow_hex = _rgb_to_hex(np.median(glow_px, axis=0)) if has_glow else None

    # Container style detection.
    ring_std = float(np.std(ring_rgb))
    outer2_pad = pad * 2
    fx1, fy1 = max(0, x1 - outer2_pad), max(0, y1 - outer2_pad)
    fx2, fy2 = min(w, x2 + outer2_pad), min(h, y2 + outer2_pad)
    far = bgr[fy1:fy2, fx1:fx2]
    far_mask = np.ones(far.shape[:2], dtype=bool)
    far_mask[(oy1 - fy1) : (oy2 - fy1), (ox1 - fx1) : (ox2 - fx1)] = False
    far_pixels = far[far_mask]
    container_style = "boxless"
    if far_pixels.size > 0 and ring_std < 18.0:
        far_rgb = np.median(far_pixels[:, ::-1].astype(np.float64), axis=0)
        if float(np.linalg.norm(bg_rgb - far_rgb)) > 38.0:
            aspect = (x2 - x1) / max(y2 - y1, 1)
            container_style = "chip" if aspect > 1.8 and (y2 - y1) < h * 0.12 else "card"

    return {
        "fg_hex": _rgb_to_hex(fg_rgb),
        "bg_hex": _rgb_to_hex(bg_rgb),
        "wcag_contrast": contrast,
        "has_dark_halo": dark_halo,
        "has_glow_halo": has_glow,
        "glow_hex": glow_hex,
        "container_style": container_style,
    }


def _classify_casing(text: str) -> str:
    stripped = text.strip()
    digits = sum(c.isdigit() for c in stripped)
    alpha = [c for c in stripped if c.isalpha()]
    if digits > 0 and digits >= len(alpha):
        return "numeric"
    if not alpha:
        return "other"
    if all(c.isupper() for c in alpha):
        return "upper"
    if all(c.islower() for c in alpha):
        return "lower"
    words = [w for w in stripped.split() if any(c.isalpha() for c in w)]
    if words and all(w[0].isupper() for w in words):
        return "title"
    return "sentence"


def _render_annotated_tile(
    bgr: np.ndarray,
    tile_w: int,
    tile_h: int,
    label_top: str,
    label_bot: str,
) -> Image.Image:
    resized = cv2.resize(bgr, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
    img = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)
    font = ImageFont.load_default()

    # Subtle 6x10 reference grid ticks on edges.
    for ci in range(1, 6):
        gx = int(round(ci * tile_w / 6.0))
        draw.line([(gx, 0), (gx, 6)], fill=(255, 255, 255, 160), width=1)
    for ri in range(1, 10):
        gy = int(round(ri * tile_h / 10.0))
        draw.line([(0, gy), (6, gy)], fill=(255, 255, 255, 160), width=1)

    draw.rectangle([(0, 0), (tile_w, 18)], fill=(8, 12, 18, 210))
    draw.text((4, 3), label_top[:44], fill=(245, 242, 232, 255), font=font)
    if label_bot:
        draw.rectangle([(0, tile_h - 18), (tile_w, tile_h)], fill=(8, 12, 18, 200))
        draw.text((4, tile_h - 15), label_bot[:44], fill=(124, 224, 249, 255), font=font)
    return Image.alpha_composite(img, ov).convert("RGB")


def _write_fullframe_md(result: dict[str, Any], out_path: Path) -> None:
    s = result["summary"]
    cam = s["camera"]
    surf = s["surfaces"]
    typ = s["layout_and_typography"]
    col = s["color_and_lighting"]
    aud = s["audio_and_sync"]

    lines: list[str] = [
        "# Full-Frame Video Forensic Report (`FULLFRAME.md`)",
        "",
        f"- **Source**: `{Path(result['source_path']).name}`",
        f"- **Specs**: `{result['width']}x{result['height']}` (`{result['aspect_ratio']}`) @ `{result['fps']} fps`, `{result['frame_count']}` frames (`{result['duration_s']}s`)",
        f"- **Platform Target**: `{result.get('platform_target_id') or 'none'}`",
        f"- **Per-Frame Telemetry**: `{Path(result['frame_telemetry_path']).name}`",
        "",
        "## 1. Visual DNA & Color System",
        "",
        "| Metric | Measured Value |",
        "| :--- | :--- |",
        f"| Dominant palette | `{'`, `'.join(col['dominant_palette_hex'])}` |",
        f"| Ocean / Land median hex | `{col.get('ocean_hex_p50')}` / `{col.get('land_hex_p50')}` |",
        f"| Accent glow hues | `{', '.join(col.get('accent_hues_detected') or ['none'])}` |",
        f"| Mean luma / saturation | `{col['mean_luma']}` / `{col['mean_saturation']}` |",
        f"| Corner/center vignette ratio | `{col['vignette_ratio']}` |",
        f"| Mean luminous glow coverage | `{col['glow_coverage_mean']:.2%}` |",
        "",
        "## 2. Surface & Map Register Timeline",
        "",
        f"- **Dominant surface**: `{surf['dominant_surface']}` | **Switches**: `{surf['surface_switch_count']}`",
        f"- **Coverage**: " + ", ".join(f"`{k}: {v:.1%}`" for k, v in surf["coverage_by_surface"].items()),
        "",
        "| # | Frames | Time (s) | Surface | Ocean / Land | Dominant Hex | Luma / Vignette |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for seg in result["surface_segments"]:
        dom = ", ".join(seg["dominant_hex"][:3])
        lines.append(
            f"| `{seg['segment_index']:02d}` | `{seg['start_frame']}–{seg['end_frame']}` | "
            f"`{seg['start_s']:.2f}–{seg['end_s']:.2f}` | `{seg['surface_class']}` | "
            f"`{seg.get('ocean_hex') or '-'} / {seg.get('land_hex') or '-'}` | `{dom}` | "
            f"`{seg['mean_luma']:.0f}` / `{seg['vignette_ratio']:.2f}` |"
        )

    lines.extend(
        [
            "",
            "## 3. Camera Choreography & Kinematics",
            "",
            f"- **Active camera ratio**: `{cam['active_ratio']:.1%}` | **Dominant regime**: `{cam['dominant_regime']}`",
            f"- **Peak pan / zoom**: `{cam['peak_pan_px_s']:.0f} px/s` / `{cam['peak_zoom_log2_s']:.2f} log2/s`",
            f"- **Direction flips (pan / zoom)**: `{cam['pan_direction_flips']}` / `{cam['zoom_direction_flips']}`",
            f"- **Hard cuts / graphic events**: `{cam['hard_cut_count']}` / `{cam['graphic_event_count']}`",
            "",
            "| # | Frames | Time (s) | Regime | Easing | Pan (vx, vy) px/s | Peak Pan | Zoom (log2/s) | Cum Zoom | Rot deg/s |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for cs in result["camera_segments"][:40]:
        lines.append(
            f"| `{cs['segment_index']:02d}` | `{cs['start_frame']}–{cs['end_frame']}` | "
            f"`{cs['start_s']:.2f}–{cs['end_s']:.2f}` | `{cs['regime']}` | `{cs['easing_shape']}` | "
            f"`({cs['mean_pan_vx_px_s']:+.0f}, {cs['mean_pan_vy_px_s']:+.0f})` | `{cs['peak_pan_px_s']:.0f}` | "
            f"`{cs['mean_zoom_log2_s']:+.2f}` | `{cs['cumulative_zoom_log2']:+.2f}` | `{cs['mean_rot_deg_s']:+.1f}` |"
        )

    lines.extend(
        [
            "",
            "## 4. Layout, Typography & Caption Rail",
            "",
            "| Metric | Measured Value |",
            "| :--- | :--- |",
            f"| Caption band Y (norm) | `{typ.get('caption_band_y_norm')}` |",
            f"| Caption height / est font px | `{typ.get('caption_height_px_p50')}` px / `{typ.get('caption_font_px_est')}` px |",
            f"| Caption color / contrast / style | `{typ.get('caption_fg_hex')}` / `{typ.get('caption_contrast_p50')}:1` / `{typ.get('caption_style')}` |",
            f"| Caption cues / words p50 / CPS p50 | `{typ['caption_cue_count']}` / `{typ.get('caption_words_per_cue_p50')}` / `{typ.get('caption_cps_p50')}` |",
            f"| In-world labels / hero counters | `{typ['in_world_label_count']}` / `{typ['hero_counter_count']}` |",
            f"| Glow-halo text ratio / tilted count | `{typ['glow_text_ratio']:.1%}` / `{typ['tilted_label_count']}` |",
            "",
            "### In-World Typography & Counters",
            "",
            "| ID | Frames | Time (s) | Role | Text | BBox (px) | Est Font | Color / Glow | Tilt | Motion |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for lb in result["in_world_text"][:80]:
        glow_s = f"glow:{lb['glow_hex']}" if lb["has_glow_halo"] else ("halo" if lb["has_dark_halo"] else "clean")
        lines.append(
            f"| `W{lb['track_id']:02d}` | `{lb['start_frame']}–{lb['end_frame']}` | "
            f"`{lb['start_s']:.2f}–{lb['end_s']:.2f}` | `{lb['role']}` | `{lb['text']}` | "
            f"`{lb['bbox_px']}` | `{lb['est_font_px']}px` | `{lb['fg_hex']}` ({glow_s}) | "
            f"`{lb['tilt_deg']:+.1f}°` | `{lb['motion_class']}` |"
        )

    lines.extend(
        [
            "",
            "### Caption Rail Cues",
            "",
            "| # | Frames | Time (s) | Text | Y norm | H px | Gap ms |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for c in result["captions"][:120]:
        gap = f"{c['gap_prev_ms']:.0f}" if c.get("gap_prev_ms") is not None else "-"
        lines.append(
            f"| `{c['cue_index']:02d}` | `{c['start_frame']}–{c['end_frame']}` | "
            f"`{c['start_s']:.2f}–{c['end_s']:.2f}` | `{c['text']}` | "
            f"`{c['y_center_norm']:.3f}` | `{c['height_px']}` | `{gap}` |"
        )

    lines.extend(
        [
            "",
            "## 5. Cuts, Transitions & Graphic Events",
            "",
            "| Type | Frame | Time (s) | Detail | Audio Sync (ms) |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for cut in result["cuts"]:
        sync = f"{cut['nearest_audio_transient_ms']:+.0f}" if cut.get("nearest_audio_transient_ms") is not None else "-"
        lines.append(
            f"| `{cut['kind']}` | `{cut['frame_index']}` | `{cut['timestamp_s']:.3f}` | "
            f"dLuma={cut['luma_delta']:+.1f}, hist={cut['hist_dist']:.2f}, blur={cut['blur_before']:.0f}->{cut['blur_after']:.0f} | `{sync}` |"
        )
    for ev in result["graphic_events"][:40]:
        sync = f"{ev['nearest_audio_transient_ms']:+.0f}" if ev.get("nearest_audio_transient_ms") is not None else "-"
        lines.append(
            f"| `graphic_event` | `{ev['frame_index']}` | `{ev['timestamp_s']:.3f}` | "
            f"cell={ev['peak_tile_grid']}, intensity={ev['intensity']:.2f}, new={ev.get('dominant_new_hex') or '-'} | `{sync}` |"
        )

    lines.extend(
        [
            "",
            "## 6. Audio & SFX Telemetry",
            "",
            f"- **SFX transients**: `{aud['transient_count']}` (`{aud['transients_per_min']:.1f}/min`)",
            f"- **Speech-band active ratio**: `{aud['speech_active_ratio']:.1%}`",
            f"- **Median A/V sync offset**: `{aud.get('median_av_sync_offset_ms')} ms`",
            "",
            "## 7. Visual Inspection Sheets",
            "",
            "- **Timeline sheets**: " + ", ".join(f"`{Path(p).name}`" for p in result["sheets"]["timeline_sheets"]),
            "- **Transition burst strips**: " + (", ".join(f"`{Path(p).name}`" for p in result["sheets"]["event_strips"]) or "none"),
        ]
    )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze_fullframe(
    video_path: Path,
    out_dir: Path,
    *,
    platform_target_id: str | None = None,
    ocr_fps: float = 3.0,
    sheet_fps: float = 1.0,
    max_event_strips: int = 16,
) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    raw_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    fps = raw_fps if (math.isfinite(raw_fps) and raw_fps > 0.0) else 30.0
    reported_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError(f"Invalid video dimensions: {width}x{height}")

    out_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir = out_dir / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    # Working resolution for full-frame optical flow & color pass (keeps 30fps scan fast).
    work_w = min(width, 360)
    scale_to_native = width / float(work_w)
    work_h = max(16, int(round(height / scale_to_native)))

    ocr = RapidOCR()
    ocr_step = max(1, int(round(fps / max(0.5, ocr_fps))))
    sheet_step = max(1, int(round(fps / max(0.2, sheet_fps))))

    frame_records: list[dict[str, Any]] = []
    ocr_frames_raw: list[tuple[int, list[dict[str, Any]]]] = []
    sheet_tiles: list[tuple[int, Image.Image]] = []
    palette_samples: list[np.ndarray] = []

    prev_gray: np.ndarray | None = None
    prev_hsv: np.ndarray | None = None
    prev_hist: np.ndarray | None = None
    prev_small_bgr: np.ndarray | None = None

    fi = 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break
            small = cv2.resize(bgr, (work_w, work_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            blur_var = float(cv2.Laplacian(gray, cv2.CV_32F).var())

            surf = _classify_surface(small, hsv, gray)

            pan_vx = 0.0
            pan_vy = 0.0
            zoom_log2_s = 0.0
            rot_deg_s = 0.0
            inlier_ratio = 1.0
            hist_dist = 0.0
            luma_delta = 0.0
            tile_diff_max = 0.0
            tile_peak_xy = (0.5, 0.5)
            new_accent_hex: str | None = None

            if prev_gray is not None and prev_hist is not None and prev_hsv is not None and prev_small_bgr is not None:
                hist_dist = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                luma_delta = float(gray.mean()) - float(prev_gray.mean())

                # Optical flow + RANSAC partial affine for true camera kinematics.
                pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=160, qualityLevel=0.015, minDistance=10)
                if pts is not None and len(pts) >= 8:
                    next_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts, None)
                    if next_pts is not None and status is not None:
                        good_prev = pts[status.ravel() == 1]
                        good_next = next_pts[status.ravel() == 1]
                        if len(good_prev) >= 6:
                            mat, inliers = cv2.estimateAffinePartial2D(
                                good_prev, good_next, method=cv2.RANSAC, ransacReprojThreshold=2.5
                            )
                            if mat is not None:
                                a, b = float(mat[0, 0]), float(mat[0, 1])
                                dx, dy = float(mat[0, 2]), float(mat[1, 2])
                                sc = max(0.25, math.hypot(a, b))
                                pan_vx = dx * scale_to_native * fps
                                pan_vy = dy * scale_to_native * fps
                                zoom_log2_s = math.log2(sc) * fps
                                rot_deg_s = math.degrees(math.atan2(-b, a)) * fps
                                if inliers is not None and len(inliers) > 0:
                                    inlier_ratio = float(inliers.mean())

                # Localized 6x10 grid change map (warped if camera moved, otherwise direct).
                diff_bgr = cv2.absdiff(small, prev_small_bgr)
                diff_gray = cv2.cvtColor(diff_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
                # Suppress global camera shift noise by subtracting median frame diff.
                base_diff = float(np.median(diff_gray))
                local_excess = np.maximum(0.0, diff_gray - base_diff * 1.35)
                grid_r, grid_c = 10, 6
                cell_h, cell_w = max(1, work_h // grid_r), max(1, work_w // grid_c)
                best_val = 0.0
                best_rc = (5, 3)
                for r in range(grid_r):
                    for c in range(grid_c):
                        patch = local_excess[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                        val = float(patch.mean())
                        if val > best_val:
                            best_val = val
                            best_rc = (r, c)
                tile_diff_max = round(best_val / 255.0, 4)
                tile_peak_xy = (
                    round((best_rc[1] + 0.5) / grid_c, 3),
                    round((best_rc[0] + 0.5) / grid_r, 3),
                )
                if tile_diff_max >= 0.07:
                    pr, pc = best_rc
                    p_bgr = small[pr * cell_h : (pr + 1) * cell_h, pc * cell_w : (pc + 1) * cell_w]
                    p_hsv = hsv[pr * cell_h : (pr + 1) * cell_h, pc * cell_w : (pc + 1) * cell_w]
                    sat_m = p_hsv[:, :, 1] >= 120
                    if sat_m.sum() >= 10:
                        new_accent_hex = _rgb_to_hex(np.median(p_bgr[:, :, ::-1][sat_m], axis=0))

            pan_speed = math.hypot(pan_vx, pan_vy)
            if hist_dist >= 0.42 or abs(luma_delta) >= 34.0:
                cam_reg = "cut_or_transition"
            elif abs(zoom_log2_s) >= 2.2:
                cam_reg = "whip_zoom"
            elif abs(zoom_log2_s) >= 0.14 and pan_speed >= 45.0:
                cam_reg = "complex_move"
            elif zoom_log2_s >= 0.12:
                cam_reg = "zoom_in"
            elif zoom_log2_s <= -0.12:
                cam_reg = "zoom_out"
            elif pan_speed >= 42.0:
                cam_reg = "pan"
            elif pan_speed >= 7.0 or abs(zoom_log2_s) >= 0.03:
                cam_reg = "slow_drift"
            else:
                cam_reg = "static"

            rec = {
                "frame_index": fi,
                "t_s": round(fi / fps, 6),
                "pan_vx": round(pan_vx, 2),
                "pan_vy": round(pan_vy, 2),
                "pan_speed": round(pan_speed, 2),
                "zoom_log2_s": round(zoom_log2_s, 4),
                "rot_deg_s": round(rot_deg_s, 2),
                "inlier_ratio": round(inlier_ratio, 3),
                "luma": surf["mean_luma"],
                "sat": surf["mean_sat"],
                "vignette_ratio": surf["vignette_ratio"],
                "glow_coverage": surf["glow_coverage"],
                "blur_var": round(blur_var, 2),
                "hist_dist": round(hist_dist, 4),
                "luma_delta": round(luma_delta, 2),
                "tile_diff_max": tile_diff_max,
                "tile_peak_xy": list(tile_peak_xy),
                "new_accent_hex": new_accent_hex,
                "surface_class": surf["surface_class"],
                "ocean_hex": surf["ocean_hex"],
                "land_hex": surf["land_hex"],
                "accent_hues": surf["accent_hues"],
                "camera_regime": cam_reg,
            }
            frame_records.append(rec)

            if fi % max(1, int(round(fps * 1.5))) == 0:
                palette_samples.append(small)

            # Run OCR on dense schedule OR right after any cut/major event.
            is_event_frame = (hist_dist >= 0.36) or (tile_diff_max >= 0.14)
            if fi % ocr_step == 0 or is_event_frame:
                res, _ = ocr(bgr)
                dets: list[dict[str, Any]] = []
                if res:
                    for poly, txt, score in res:
                        clean = str(txt).strip()
                        if float(score) < 0.55 or not clean:
                            continue
                        pts_a = np.array(poly, dtype=np.float64)
                        x1 = max(0, int(np.floor(pts_a[:, 0].min())))
                        y1 = max(0, int(np.floor(pts_a[:, 1].min())))
                        x2 = min(width, int(np.ceil(pts_a[:, 0].max())))
                        y2 = min(height, int(np.ceil(pts_a[:, 1].max())))
                        if x2 - x1 < 8 or y2 - y1 < 8:
                            continue
                        dx = float(pts_a[1, 0] - pts_a[0, 0])
                        dy = float(pts_a[1, 1] - pts_a[0, 1])
                        tilt_deg = round(math.degrees(math.atan2(dy, dx)), 1) if abs(dx) > 1e-3 else 0.0
                        vis = _sample_text_visuals(bgr, (x1, y1, x2, y2))
                        dets.append(
                            {
                                "text": clean[:80],
                                "bbox_px": [x1, y1, x2, y2],
                                "tilt_deg": tilt_deg,
                                **vis,
                            }
                        )
                ocr_frames_raw.append((fi, dets))

            if fi % sheet_step == 0:
                tile_w = 270 if height >= width else 360
                tile_h = int(round(tile_w * height / width))
                t_lbl = f"f={fi:04d} t={fi/fps:05.2f}s"
                b_lbl = f"{surf['surface_class'][:14]} | {cam_reg[:11]} z={zoom_log2_s:+.1f}"
                sheet_tiles.append((fi, _render_annotated_tile(bgr, tile_w, tile_h, t_lbl, b_lbl)))

            prev_gray = gray
            prev_hsv = hsv
            prev_hist = hist
            prev_small_bgr = small
            fi += 1
    finally:
        cap.release()

    frame_count = max(1, len(frame_records))
    duration_s = round(frame_count / fps, 4)

    # Audio extraction & alignment.
    rms_db, flux_arr, audio_transients, speech_ratio = _extract_audio_forensics(video_path, fps, frame_count)
    for i, rec in enumerate(frame_records):
        rec["audio_rms_db"] = rms_db[i] if i < len(rms_db) else -60.0
        rec["audio_flux"] = flux_arr[i] if i < len(flux_arr) else 0.0

    telemetry_path = out_dir / "frame_telemetry.jsonl"
    with telemetry_path.open("w", encoding="utf-8") as fh:
        for rec in frame_records:
            fh.write(json.dumps(rec) + "\n")

    # 1. Detect cuts and localized graphic events.
    cuts: list[dict[str, Any]] = []
    graphic_events: list[dict[str, Any]] = []
    min_cut_gap = max(4, int(round(fps * 0.25)))
    last_cut_fi = -min_cut_gap
    min_ev_gap = max(6, int(round(fps * 0.45)))
    last_ev_fi = -min_ev_gap

    for i in range(1, frame_count):
        rec = frame_records[i]
        prev = frame_records[i - 1]
        if (rec["hist_dist"] >= 0.40 or abs(rec["luma_delta"]) >= 32.0) and (i - last_cut_fi >= min_cut_gap):
            blur_b = prev["blur_var"]
            blur_a = rec["blur_var"]
            if min(blur_b, blur_a) < 45.0 and abs(prev["zoom_log2_s"]) >= 0.8:
                kind = "whip_zoom_cut"
            elif rec["hist_dist"] < 0.55 and abs(rec["luma_delta"]) < 24.0:
                kind = "dissolve_or_wipe"
            else:
                kind = "hard_cut"
            cuts.append(
                {
                    "frame_index": i,
                    "timestamp_s": round(i / fps, 4),
                    "kind": kind,
                    "luma_delta": round(rec["luma_delta"], 2),
                    "hist_dist": round(rec["hist_dist"], 3),
                    "blur_before": round(blur_b, 1),
                    "blur_after": round(blur_a, 1),
                    "nearest_audio_transient_ms": _nearest_transient_offset_ms(i / fps, audio_transients),
                }
            )
            last_cut_fi = i
        elif rec["tile_diff_max"] >= 0.085 and (i - last_ev_fi >= min_ev_gap) and (i - last_cut_fi >= 4):
            cx, cy = rec["tile_peak_xy"]
            graphic_events.append(
                {
                    "frame_index": i,
                    "timestamp_s": round(i / fps, 4),
                    "intensity": round(rec["tile_diff_max"], 4),
                    "centroid_norm": [cx, cy],
                    "peak_tile_grid": _grid_cell_label(cx, cy),
                    "dominant_new_hex": rec["new_accent_hex"],
                    "nearest_audio_transient_ms": _nearest_transient_offset_ms(i / fps, audio_transients),
                }
            )
            last_ev_fi = i

    # 2. Smooth & segment surface timeline (mode filter over 9-frame window to prevent flicker).
    raw_surfaces = [r["surface_class"] for r in frame_records]
    smoothed_surfaces: list[str] = []
    win_half = 4
    for i in range(frame_count):
        window = raw_surfaces[max(0, i - win_half) : min(frame_count, i + win_half + 1)]
        smoothed_surfaces.append(max(set(window), key=window.count))

    surface_segments: list[dict[str, Any]] = []
    seg_start = 0
    for i in range(1, frame_count + 1):
        if i == frame_count or smoothed_surfaces[i] != smoothed_surfaces[seg_start]:
            seg_recs = frame_records[seg_start:i]
            oc = [r["ocean_hex"] for r in seg_recs if r["ocean_hex"]]
            ld = [r["land_hex"] for r in seg_recs if r["land_hex"]]
            # Sample midpoint palette from palette_samples or approximate via medians.
            mid_idx = min(len(palette_samples) - 1, max(0, int(((seg_start + i) * 0.5) / max(1, frame_count) * len(palette_samples))))
            dom_hex = _extract_dominant_palette(palette_samples[mid_idx], k=4) if palette_samples else ["#083847"]
            surface_segments.append(
                {
                    "segment_index": len(surface_segments),
                    "start_frame": seg_start,
                    "end_frame": i - 1,
                    "start_s": round(seg_start / fps, 4),
                    "end_s": round((i - 1) / fps, 4),
                    "surface_class": smoothed_surfaces[seg_start],
                    "dominant_hex": dom_hex,
                    "ocean_hex": max(set(oc), key=oc.count) if oc else None,
                    "land_hex": max(set(ld), key=ld.count) if ld else None,
                    "mean_luma": round(statistics.mean(r["luma"] for r in seg_recs), 2),
                    "mean_sat": round(statistics.mean(r["sat"] for r in seg_recs), 2),
                    "vignette_ratio": round(statistics.mean(r["vignette_ratio"] for r in seg_recs), 3),
                }
            )
            seg_start = i

    # 3. Smooth & segment camera choreography.
    raw_regimes = [
        "static" if r["camera_regime"] == "cut_or_transition" else r["camera_regime"]
        for r in frame_records
    ]
    cut_set = {c["frame_index"] for c in cuts}
    smooth_regimes: list[str] = []
    for i in range(frame_count):
        window = raw_regimes[max(0, i - 4) : min(frame_count, i + 5)]
        smooth_regimes.append(max(set(window), key=window.count))

    camera_segments: list[dict[str, Any]] = []
    c_start = 0
    for i in range(1, frame_count + 1):
        is_boundary = (i == frame_count) or (i in cut_set) or (smooth_regimes[i] != smooth_regimes[c_start])
        if is_boundary:
            if i - c_start >= 3 or i == frame_count or i in cut_set:
                seg_r = frame_records[c_start:i]
                speeds = [r["pan_speed"] + abs(r["zoom_log2_s"]) * 240.0 for r in seg_r]
                camera_segments.append(
                    {
                        "segment_index": len(camera_segments),
                        "start_frame": c_start,
                        "end_frame": i - 1,
                        "start_s": round(c_start / fps, 4),
                        "end_s": round((i - 1) / fps, 4),
                        "regime": smooth_regimes[c_start],
                        "easing_shape": _classify_easing_shape(speeds),
                        "mean_pan_vx_px_s": round(statistics.mean(r["pan_vx"] for r in seg_r), 2),
                        "mean_pan_vy_px_s": round(statistics.mean(r["pan_vy"] for r in seg_r), 2),
                        "peak_pan_px_s": round(max(r["pan_speed"] for r in seg_r), 2),
                        "mean_zoom_log2_s": round(statistics.mean(r["zoom_log2_s"] for r in seg_r), 3),
                        "peak_zoom_log2_s": round(max(abs(r["zoom_log2_s"]) for r in seg_r), 3),
                        "cumulative_zoom_log2": round(sum(r["zoom_log2_s"] / fps for r in seg_r), 3),
                        "mean_rot_deg_s": round(statistics.mean(r["rot_deg_s"] for r in seg_r), 2),
                    }
                )
                c_start = i

    # Count shake flips across continuous frames (excluding cuts).
    pan_flips = 0
    zoom_flips = 0
    prev_vx = 0.0
    prev_z = 0.0
    for i in range(1, frame_count):
        if i in cut_set or (i - 1) in cut_set:
            prev_vx = 0.0
            prev_z = 0.0
            continue
        vx = frame_records[i]["pan_vx"]
        zv = frame_records[i]["zoom_log2_s"]
        if abs(vx) >= 30.0 and abs(prev_vx) >= 30.0 and (vx * prev_vx < 0):
            pan_flips += 1
        if abs(zv) >= 0.18 and abs(prev_z) >= 0.18 and (zv * prev_z < 0):
            zoom_flips += 1
        if abs(vx) >= 20.0:
            prev_vx = vx
        if abs(zv) >= 0.12:
            prev_z = zv

    # 4. Track OCR detections into Captions vs In-World Labels.
    captions: list[dict[str, Any]] = []
    in_world_tracks: list[dict[str, Any]] = []

    def _is_caption_box(bbox: list[int], tilt_deg: float) -> bool:
        x1, y1, x2, y2 = bbox
        yc = ((y1 + y2) * 0.5) / height
        xc = ((x1 + x2) * 0.5) / width
        h_pct = (y2 - y1) / height
        return (0.64 <= yc <= 0.88) and (abs(xc - 0.5) <= 0.22) and (0.014 <= h_pct <= 0.055) and abs(tilt_deg) <= 2.5

    active_cap: dict[str, Any] | None = None
    active_world: list[dict[str, Any]] = []

    for f_idx, dets in ocr_frames_raw:
        cap_dets = [d for d in dets if _is_caption_box(d["bbox_px"], d["tilt_deg"])]
        world_dets = [d for d in dets if not _is_caption_box(d["bbox_px"], d["tilt_deg"])]

        # Merge multi-line caption detections on the same frame.
        if cap_dets:
            cap_dets.sort(key=lambda d: (d["bbox_px"][1], d["bbox_px"][0]))
            joined = " ".join(d["text"] for d in cap_dets).strip()
            bx1 = min(d["bbox_px"][0] for d in cap_dets)
            by1 = min(d["bbox_px"][1] for d in cap_dets)
            bx2 = max(d["bbox_px"][2] for d in cap_dets)
            by2 = max(d["bbox_px"][3] for d in cap_dets)
            line_h = int(round(statistics.median(d["bbox_px"][3] - d["bbox_px"][1] for d in cap_dets)))
            ref_d = cap_dets[0]
            same_cap = (
                active_cap is not None
                and (f_idx - active_cap["end_frame"] <= ocr_step * 2)
                and (joined.lower() == active_cap["text"].lower() or joined.lower() in active_cap["text"].lower() or active_cap["text"].lower() in joined.lower())
            )
            if same_cap and active_cap is not None:
                active_cap["end_frame"] = f_idx
                if len(joined) > len(active_cap["text"]):
                    active_cap["text"] = joined
            else:
                if active_cap is not None:
                    captions.append(active_cap)
                active_cap = {
                    "start_frame": f_idx,
                    "end_frame": f_idx,
                    "text": joined,
                    "bbox_px": [bx1, by1, bx2, by2],
                    "height_px": line_h,
                    "fg_hex": ref_d["fg_hex"],
                    "wcag_contrast": ref_d["wcag_contrast"],
                    "container_style": ref_d["container_style"],
                }
        elif active_cap is not None and (f_idx - active_cap["end_frame"] > ocr_step):
            captions.append(active_cap)
            active_cap = None

        # Match world detections to active tracks.
        used_tracks: set[int] = set()
        for d in world_dets:
            x1, y1, x2, y2 = d["bbox_px"]
            cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
            best_i: int | None = None
            best_score = 1e9
            for ti, tr in enumerate(active_world):
                if ti in used_tracks or (f_idx - tr["end_frame"] > ocr_step * 3):
                    continue
                dist = math.hypot(cx - tr["last_cx"], cy - tr["last_cy"])
                same_txt = d["text"].lower() == tr["text"].lower()
                if (same_txt and dist < 240.0) or dist < 95.0:
                    if dist < best_score:
                        best_score = dist
                        best_i = ti
            if best_i is not None:
                used_tracks.add(best_i)
                tr = active_world[best_i]
                tr["end_frame"] = f_idx
                tr["positions"].append((cx, cy, x2 - x1, y2 - y1))
                tr["last_cx"], tr["last_cy"] = cx, cy
                tr["texts"].append(d["text"])
                if len(d["text"]) >= len(tr["text"]):
                    tr["text"] = d["text"]
            else:
                active_world.append(
                    {
                        "start_frame": f_idx,
                        "end_frame": f_idx,
                        "text": d["text"],
                        "texts": [d["text"]],
                        "bbox_px": d["bbox_px"],
                        "last_cx": cx,
                        "last_cy": cy,
                        "positions": [(cx, cy, x2 - x1, y2 - y1)],
                        "fg_hex": d["fg_hex"],
                        "bg_hex": d["bg_hex"],
                        "wcag_contrast": d["wcag_contrast"],
                        "has_dark_halo": d["has_dark_halo"],
                        "has_glow_halo": d["has_glow_halo"],
                        "glow_hex": d["glow_hex"],
                        "container_style": d["container_style"],
                        "tilt_deg": d["tilt_deg"],
                    }
                )

    if active_cap is not None:
        captions.append(active_cap)

    final_captions: list[dict[str, Any]] = []
    for ci, c in enumerate(captions):
        st_s = round(c["start_frame"] / fps, 4)
        en_s = round((c["end_frame"] + ocr_step) / fps, 4)
        dur = max(0.1, en_s - st_s)
        words = len(c["text"].split())
        gap_ms = None
        if ci > 0:
            gap_ms = round((st_s - final_captions[-1]["end_s"]) * 1000.0, 1)
        x1, y1, x2, y2 = c["bbox_px"]
        final_captions.append(
            {
                "cue_index": ci,
                "start_frame": c["start_frame"],
                "end_frame": min(frame_count - 1, c["end_frame"] + ocr_step - 1),
                "start_s": st_s,
                "end_s": min(duration_s, en_s),
                "text": c["text"],
                "words": words,
                "cps": round(len(c["text"]) / dur, 2),
                "bbox_px": c["bbox_px"],
                "y_center_norm": round(((y1 + y2) * 0.5) / height, 4),
                "height_px": c["height_px"],
                "fg_hex": c["fg_hex"],
                "wcag_contrast": c["wcag_contrast"],
                "container_style": c["container_style"],
                "gap_prev_ms": gap_ms,
            }
        )

    for tr in active_world:
        if tr["end_frame"] - tr["start_frame"] < ocr_step and len(tr["positions"]) < 2:
            # Keep single-frame hits only if large / high contrast (hero title or brief stamp).
            x1, y1, x2, y2 = tr["bbox_px"]
            if (y2 - y1) < height * 0.032:
                continue
        x1, y1, x2, y2 = tr["bbox_px"]
        cap_h = max(1, y2 - y1)
        est_font = int(round(cap_h * 1.22))
        casing = _classify_casing(tr["text"])
        uniq_texts = len({t.lower() for t in tr["texts"]})
        pos = tr["positions"]
        disp = math.hypot(pos[-1][0] - pos[0][0], pos[-1][1] - pos[0][1]) if len(pos) >= 2 else 0.0
        scale_r = pos[-1][2] / max(1.0, pos[0][2]) if len(pos) >= 2 else 1.0
        if casing == "numeric" and uniq_texts >= 2:
            motion_cls = "counter_tick"
        elif abs(scale_r - 1.0) >= 0.14:
            motion_cls = "scale_in"
        elif disp >= 18.0:
            motion_cls = "world_tracked_with_map"
        else:
            motion_cls = "static"

        if casing == "numeric" and cap_h >= height * 0.038:
            role = "hero_counter"
        elif cap_h >= height * 0.048:
            role = "hero_display"
        elif any(u in tr["text"].lower() for u in ("mi", "km", "ft", " m", "%")):
            role = "telemetry_unit"
        else:
            role = "map_label"

        in_world_tracks.append(
            {
                "track_id": len(in_world_tracks) + 1,
                "start_frame": tr["start_frame"],
                "end_frame": min(frame_count - 1, tr["end_frame"] + ocr_step - 1),
                "start_s": round(tr["start_frame"] / fps, 4),
                "end_s": round(min(frame_count - 1, tr["end_frame"] + ocr_step - 1) / fps, 4),
                "text": tr["text"],
                "role": role,
                "casing": casing,
                "bbox_px": [x1, y1, x2, y2],
                "bbox_norm": [
                    round(x1 / width, 4),
                    round(y1 / height, 4),
                    round(x2 / width, 4),
                    round(y2 / height, 4),
                ],
                "cap_height_px": cap_h,
                "est_font_px": est_font,
                "fg_hex": tr["fg_hex"],
                "bg_hex": tr["bg_hex"],
                "wcag_contrast": tr["wcag_contrast"],
                "has_dark_halo": tr["has_dark_halo"],
                "has_glow_halo": tr["has_glow_halo"],
                "glow_hex": tr["glow_hex"],
                "container_style": tr["container_style"],
                "tilt_deg": tr["tilt_deg"],
                "motion_class": motion_cls,
            }
        )

    # 5. Assemble dense timeline contact sheets (4x4 = 16 tiles per sheet).
    timeline_sheet_paths: list[str] = []
    per_sheet = 16
    for s_idx in range(0, len(sheet_tiles), per_sheet):
        batch = sheet_tiles[s_idx : s_idx + per_sheet]
        if not batch:
            continue
        tw, th = batch[0][1].size
        cols_s = 4
        rows_s = math.ceil(len(batch) / cols_s)
        canvas = Image.new("RGB", (tw * cols_s, th * rows_s), (6, 10, 14))
        for bi, (_, tile_img) in enumerate(batch):
            r, c = divmod(bi, cols_s)
            canvas.paste(tile_img, (c * tw, r * th))
        sp = sheets_dir / f"timeline_{len(timeline_sheet_paths) + 1:03d}.jpg"
        canvas.save(sp, quality=88)
        timeline_sheet_paths.append(str(sp.resolve()))

    # 6. Render full-FPS transition burst strips around detected cuts.
    event_strip_paths: list[str] = []
    if cuts and max_event_strips > 0:
        cap2 = cv2.VideoCapture(str(video_path))
        try:
            offsets = (-4, -2, -1, 0, 1, 2, 4, 8)
            for ci, cut in enumerate(cuts[:max_event_strips]):
                cf = cut["frame_index"]
                strip_imgs: list[Image.Image] = []
                tw = 200 if height >= width else 280
                th = int(round(tw * height / width))
                for off in offsets:
                    target_f = max(0, min(frame_count - 1, cf + off))
                    cap2.set(cv2.CAP_PROP_POS_FRAMES, target_f)
                    ok2, fr2 = cap2.read()
                    if not ok2 or fr2 is None:
                        continue
                    strip_imgs.append(
                        _render_annotated_tile(
                            fr2,
                            tw,
                            th,
                            f"{off:+d}f (f={target_f})",
                            f"t={target_f/fps:.3f}s",
                        )
                    )
                if strip_imgs:
                    strip = Image.new("RGB", (tw * len(strip_imgs), th), (6, 10, 14))
                    for si, im in enumerate(strip_imgs):
                        strip.paste(im, (si * tw, 0))
                    ep = sheets_dir / f"cut_{ci + 1:02d}_f{cf:04d}.jpg"
                    strip.save(ep, quality=88)
                    event_strip_paths.append(str(ep.resolve()))
        finally:
            cap2.release()

    # 7. Summaries.
    active_frames = sum(1 for r in frame_records if r["camera_regime"] != "static")
    reg_counts: dict[str, int] = {}
    for r in frame_records:
        rg = "static" if r["camera_regime"] == "cut_or_transition" else r["camera_regime"]
        reg_counts[rg] = reg_counts.get(rg, 0) + 1
    dom_cam_reg = max(reg_counts.items(), key=lambda kv: kv[1])[0] if reg_counts else "static"

    surf_counts: dict[str, int] = {}
    for s_cls in smoothed_surfaces:
        surf_counts[s_cls] = surf_counts.get(s_cls, 0) + 1
    cov_by_surf = {k: round(v / frame_count, 4) for k, v in sorted(surf_counts.items(), key=lambda kv: -kv[1])}
    dom_surface = next(iter(cov_by_surf.keys()), "satellite_relief")

    all_palette_bgr = np.vstack([p.reshape(-1, 3) for p in palette_samples]) if palette_samples else np.zeros((16, 3), dtype=np.uint8)
    global_palette = _extract_dominant_palette(all_palette_bgr.reshape(-1, 1, 3), k=6)
    ocean_hexes = [r["ocean_hex"] for r in frame_records if r["ocean_hex"]]
    land_hexes = [r["land_hex"] for r in frame_records if r["land_hex"]]
    hue_counts: dict[str, int] = {}
    for r in frame_records:
        for h_name in r["accent_hues"]:
            hue_counts[h_name] = hue_counts.get(h_name, 0) + 1
    accent_hues_detected = [k for k, v in sorted(hue_counts.items(), key=lambda kv: -kv[1]) if v >= max(3, int(frame_count * 0.01))]

    sync_offsets = [
        abs(e["nearest_audio_transient_ms"])
        for e in [*cuts, *graphic_events]
        if e.get("nearest_audio_transient_ms") is not None
    ]

    cap_y = round(statistics.median(c["y_center_norm"] for c in final_captions), 4) if final_captions else None
    cap_h_p50 = round(statistics.median(c["height_px"] for c in final_captions), 1) if final_captions else None
    cap_font_est = round(cap_h_p50 * 1.28, 1) if cap_h_p50 is not None else None
    cap_fg = max({c["fg_hex"] for c in final_captions}, key=lambda x: sum(1 for c in final_captions if c["fg_hex"] == x)) if final_captions else None
    cap_wcag = round(statistics.median(c["wcag_contrast"] for c in final_captions), 2) if final_captions else None
    cap_style = max({c["container_style"] for c in final_captions}, key=lambda x: sum(1 for c in final_captions if c["container_style"] == x)) if final_captions else None
    cap_w_p50 = round(statistics.median(c["words"] for c in final_captions), 1) if final_captions else None
    cap_cps_p50 = round(statistics.median(c["cps"] for c in final_captions), 2) if final_captions else None

    all_boxes = [c["bbox_px"] for c in final_captions] + [t["bbox_px"] for t in in_world_tracks]
    if all_boxes:
        margins = [
            round(min(b[0] / width for b in all_boxes), 4),
            round(min((width - b[2]) / width for b in all_boxes), 4),
            round(min(b[1] / height for b in all_boxes), 4),
            round(min((height - b[3]) / height for b in all_boxes), 4),
        ]
    else:
        margins = [0.0, 0.0, 0.0, 0.0]

    report_md = out_dir / "FULLFRAME.md"
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "source_path": str(video_path.resolve()),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "frame_count": frame_count,
        "duration_s": duration_s,
        "aspect_ratio": _aspect_label(width, height),
        "platform_target_id": platform_target_id,
        "output_dir": str(out_dir.resolve()),
        "report_md_path": str(report_md.resolve()),
        "frame_telemetry_path": str(telemetry_path.resolve()),
        "summary": {
            "camera": {
                "active_ratio": round(active_frames / frame_count, 4),
                "dominant_regime": dom_cam_reg,
                "peak_pan_px_s": round(max(r["pan_speed"] for r in frame_records), 2),
                "peak_zoom_log2_s": round(max(abs(r["zoom_log2_s"]) for r in frame_records), 3),
                "pan_direction_flips": pan_flips,
                "zoom_direction_flips": zoom_flips,
                "hard_cut_count": len(cuts),
                "graphic_event_count": len(graphic_events),
            },
            "surfaces": {
                "dominant_surface": dom_surface,
                "surface_switch_count": max(0, len(surface_segments) - 1),
                "coverage_by_surface": cov_by_surf,
            },
            "layout_and_typography": {
                "caption_band_y_norm": cap_y,
                "caption_height_px_p50": cap_h_p50,
                "caption_font_px_est": cap_font_est,
                "caption_fg_hex": cap_fg,
                "caption_contrast_p50": cap_wcag,
                "caption_style": cap_style,
                "caption_cue_count": len(final_captions),
                "caption_words_per_cue_p50": cap_w_p50,
                "caption_cps_p50": cap_cps_p50,
                "in_world_label_count": len(in_world_tracks),
                "hero_counter_count": sum(1 for t in in_world_tracks if t["role"] == "hero_counter"),
                "glow_text_ratio": round(
                    sum(1 for t in in_world_tracks if t["has_glow_halo"]) / max(1, len(in_world_tracks)),
                    4,
                ),
                "tilted_label_count": sum(1 for t in in_world_tracks if abs(t["tilt_deg"]) >= 2.0),
                "margin_lrtb_norm": margins,
            },
            "color_and_lighting": {
                "dominant_palette_hex": global_palette,
                "ocean_hex_p50": max(set(ocean_hexes), key=ocean_hexes.count) if ocean_hexes else None,
                "land_hex_p50": max(set(land_hexes), key=land_hexes.count) if land_hexes else None,
                "accent_hues_detected": accent_hues_detected,
                "mean_luma": round(statistics.mean(r["luma"] for r in frame_records), 2),
                "mean_saturation": round(statistics.mean(r["sat"] for r in frame_records), 2),
                "vignette_ratio": round(statistics.mean(r["vignette_ratio"] for r in frame_records), 4),
                "glow_coverage_mean": round(statistics.mean(r["glow_coverage"] for r in frame_records), 4),
            },
            "audio_and_sync": {
                "transient_count": len(audio_transients),
                "transients_per_min": round(len(audio_transients) / max(0.01, duration_s / 60.0), 2),
                "speech_active_ratio": speech_ratio,
                "median_av_sync_offset_ms": round(statistics.median(sync_offsets), 1) if sync_offsets else None,
            },
        },
        "surface_segments": surface_segments,
        "camera_segments": camera_segments,
        "cuts": cuts,
        "graphic_events": graphic_events,
        "captions": final_captions,
        "in_world_text": in_world_tracks,
        "audio_transients": audio_transients,
        "sheets": {
            "timeline_sheets": timeline_sheet_paths,
            "event_strips": event_strip_paths,
        },
    }

    (out_dir / "fullframe_forensics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _write_fullframe_md(result, report_md)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run native-FPS full-frame video forensics.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--platform-target-id", type=str, default=None)
    parser.add_argument("--ocr-fps", type=float, default=3.0)
    parser.add_argument("--sheet-fps", type=float, default=1.0)
    parser.add_argument("--max-event-strips", type=int, default=16)
    args = parser.parse_args()

    res = analyze_fullframe(
        args.video,
        args.out_dir,
        platform_target_id=args.platform_target_id,
        ocr_fps=args.ocr_fps,
        sheet_fps=args.sheet_fps,
        max_event_strips=args.max_event_strips,
    )
    print(
        json.dumps(
            {
                "fullframe_forensics_path": str((args.out_dir / "fullframe_forensics.json").resolve()),
                "report_md_path": res["report_md_path"],
                "frame_count": res["frame_count"],
                "surface_segments": len(res["surface_segments"]),
                "camera_segments": len(res["camera_segments"]),
                "cuts": len(res["cuts"]),
                "graphic_events": len(res["graphic_events"]),
                "captions": len(res["captions"]),
                "in_world_text": len(res["in_world_text"]),
                "timeline_sheets": len(res["sheets"]["timeline_sheets"]),
            }
        )
    )


if __name__ == "__main__":
    main()
