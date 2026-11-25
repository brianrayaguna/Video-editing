#!/usr/bin/env python3
"""Deterministic spatial, grid, hierarchy, typography, and motion video forensics worker.

Invoked over a subprocess JSON boundary by `vedit breakdown structure`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rapidocr_onnxruntime import RapidOCR
from sklearn.cluster import DBSCAN

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODELS_DIR = SCRIPT_DIR / "models"


def _aspect_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "other"
    ratio = width / height
    for label, target in (
        ("16:9", 16 / 9),
        ("9:16", 9 / 16),
        ("1:1", 1.0),
        ("4:5", 4 / 5),
    ):
        if abs(ratio - target) <= 0.06:
            return label
    return "other"


def _srgb_to_rel_luma(rgb: np.ndarray) -> float:
    """Compute WCAG 2.1 relative luminance for an RGB triplet in [0, 255]."""
    c = np.clip(rgb.astype(np.float64) / 255.0, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])


def _wcag_contrast(rgb1: np.ndarray, rgb2: np.ndarray) -> float:
    l1 = _srgb_to_rel_luma(rgb1)
    l2 = _srgb_to_rel_luma(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return float(min(21.0, max(1.0, (hi + 0.05) / (lo + 0.05))))


def _rgb_to_hex(rgb: np.ndarray) -> str:
    r, g, b = (int(np.clip(round(v), 0, 255)) for v in rgb[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def _spectral_residual_saliency(bgr: np.ndarray) -> np.ndarray:
    """Fast FFT-based spectral residual saliency map normalized to [0.0, 1.0]."""
    h, w = bgr.shape[:2]
    scale = 96.0 / max(h, w, 1)
    sw, sh = max(16, int(round(w * scale))), max(16, int(round(h * scale)))
    gray = cv2.cvtColor(cv2.resize(bgr, (sw, sh)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    fft = np.fft.fft2(gray)
    mag = np.abs(fft)
    phase = np.angle(fft)
    log_mag = np.log(mag + 1e-6)
    residual = log_mag - cv2.blur(log_mag, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal.astype(np.float32), (7, 7), 2.0)
    sal_max = float(sal.max())
    if sal_max > 1e-8:
        sal = sal / sal_max
    return cv2.resize(sal, (w, h), interpolation=cv2.INTER_LINEAR)


def _saliency_centroid(sal: np.ndarray) -> tuple[float, float]:
    h, w = sal.shape[:2]
    thresh = float(np.percentile(sal, 85))
    mask = np.where(sal >= max(thresh, 1e-4), sal, 0.0)
    total = float(mask.sum())
    if total <= 1e-8:
        return (0.5, 0.5)
    ys, xs = np.indices((h, w))
    cx = float((xs * mask).sum() / total) / max(w, 1)
    cy = float((ys * mask).sum() / total) / max(h, 1)
    return (round(min(1.0, max(0.0, cx)), 4), round(min(1.0, max(0.0, cy)), 4))


def _detect_subject_mask(bgr: np.ndarray, rembg_session: Any | None) -> np.ndarray | None:
    if rembg_session is None:
        return None
    try:
        from rembg import remove

        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        mask_img = remove(pil_img, session=rembg_session, only_mask=True)
        mask = np.array(mask_img)
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        return (mask >= 128).astype(np.uint8)
    except Exception:
        return None


def _detect_faces_and_eyeline(
    bgr: np.ndarray, face_detector: Any | None
) -> tuple[list[tuple[int, int, int, int]], float | None]:
    if face_detector is None:
        return ([], None)
    try:
        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        res = face_detector.process(rgb)
        if not res or not res.detections:
            return ([], None)
        boxes: list[tuple[int, int, int, int]] = []
        eye_ys: list[float] = []
        for det in res.detections:
            rb = det.location_data.relative_bounding_box
            x1 = max(0, int(round(rb.xmin * w)))
            y1 = max(0, int(round(rb.ymin * h)))
            x2 = min(w, int(round((rb.xmin + rb.width) * w)))
            y2 = min(h, int(round((rb.ymin + rb.height) * h)))
            if x2 - x1 >= 12 and y2 - y1 >= 12:
                boxes.append((x1, y1, x2, y2))
                kps = det.location_data.relative_keypoints
                if len(kps) >= 2:
                    eye_ys.append(float((kps[0].y + kps[1].y) * 0.5))
                else:
                    eye_ys.append(float(rb.ymin + rb.height * 0.36))
        eye_line = round(float(statistics.median(eye_ys)), 4) if eye_ys else None
        if eye_line is not None:
            eye_line = min(1.0, max(0.0, eye_line))
        return (boxes, eye_line)
    except Exception:
        return ([], None)


def _detect_structural_dividers(bgr: np.ndarray) -> tuple[list[float], list[float]]:
    """Detect strong full/half-span horizontal and vertical divider lines via HoughLinesP."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    min_len = int(round(min(w, h) * 0.30))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=100,
        minLineLength=max(30, min_len),
        maxLineGap=12,
    )
    xs: list[float] = []
    ys: list[float] = []
    if lines is not None:
        for line in lines[:, 0]:
            x1, y1, x2, y2 = (int(v) for v in line)
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dx <= 4 and dy >= h * 0.28:
                xn = ((x1 + x2) * 0.5) / max(w, 1)
                if 0.03 <= xn <= 0.97:
                    xs.append(xn)
            elif dy <= 4 and dx >= w * 0.28:
                yn = ((y1 + y2) * 0.5) / max(h, 1)
                if 0.03 <= yn <= 0.97:
                    ys.append(yn)
    return (_cluster_1d(xs, eps=0.02), _cluster_1d(ys, eps=0.02))


def _cluster_1d(values: list[float], eps: float = 0.025) -> list[float]:
    if not values:
        return []
    arr = np.array(values, dtype=np.float64).reshape(-1, 1)
    labels = DBSCAN(eps=eps, min_samples=1).fit_predict(arr)
    centers: list[float] = []
    for lbl in sorted(set(labels)):
        pts = arr[labels == lbl, 0]
        centers.append(round(float(np.mean(pts)), 4))
    return sorted(centers)


def _sample_text_contrast_and_style(
    bgr: np.ndarray, bbox: tuple[int, int, int, int]
) -> tuple[float, str, str, str]:
    """Estimate foreground ink, local background ring color, WCAG contrast, and container style."""
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return (1.0, "#FFFFFF", "#000000", "boxless")

    pad = max(4, min(14, int(round((y2 - y1) * 0.25))))
    ox1, oy1 = max(0, x1 - pad), max(0, y1 - pad)
    ox2, oy2 = min(w, x2 + pad), min(h, y2 + pad)
    outer = bgr[oy1:oy2, ox1:ox2]
    mask = np.ones(outer.shape[:2], dtype=bool)
    mask[(y1 - oy1) : (y2 - oy1), (x1 - ox1) : (x2 - ox1)] = False
    ring_pixels = outer[mask]
    if ring_pixels.size == 0:
        ring_pixels = crop.reshape(-1, 3)

    ring_rgb = ring_pixels[:, ::-1].astype(np.float64)
    bg_rgb = np.median(ring_rgb, axis=0)
    bg_luma = _srgb_to_rel_luma(bg_rgb)

    crop_rgb = crop.reshape(-1, 3)[:, ::-1].astype(np.float64)
    # Pick foreground pixels as those furthest in luminance from the background ring.
    crop_luma = (
        0.2126 * (crop_rgb[:, 0] / 255.0)
        + 0.7152 * (crop_rgb[:, 1] / 255.0)
        + 0.0722 * (crop_rgb[:, 2] / 255.0)
    )
    diff = np.abs(crop_luma - bg_luma)
    top_k = crop_rgb[diff >= np.percentile(diff, 80)]
    fg_rgb = np.median(top_k, axis=0) if len(top_k) > 0 else np.median(crop_rgb, axis=0)

    contrast = round(_wcag_contrast(fg_rgb, bg_rgb), 2)

    # Container detection: low variance inside background ring + strong contrast against outer frame
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
        ring_vs_far = float(np.linalg.norm(bg_rgb - far_rgb))
        if ring_vs_far > 38.0:
            aspect = (x2 - x1) / max(y2 - y1, 1)
            container_style = "chip" if aspect > 1.8 and (y2 - y1) < h * 0.12 else "card"

    return (contrast, _rgb_to_hex(fg_rgb), _rgb_to_hex(bg_rgb), container_style)


def _detect_graphic_containers(
    bgr: np.ndarray, text_boxes: list[tuple[int, int, int, int]]
) -> list[tuple[int, int, int, int]]:
    """Detect prominent rectangular UI cards, callout panels, or graphic boxes."""
    h, w = bgr.shape[:2]
    frame_area = float(w * h)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = float(cw * ch)
        if area < frame_area * 0.015 or area > frame_area * 0.75:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        fill_ratio = cv2.contourArea(cnt) / max(area, 1.0)
        if len(approx) <= 8 and fill_ratio >= 0.65:
            cand = (x, y, x + cw, y + ch)
            # Skip boxes that tightly duplicate an existing text box.
            if any(_iou(cand, tb) > 0.70 for tb in text_boxes):
                continue
            boxes.append(cand)
    boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    return boxes[:6]


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
    return float(inter / (area_a + area_b - inter))


def _check_safe_zone(
    bbox_norm: tuple[float, float, float, float], safe_zone: dict[str, float] | None
) -> bool:
    if not safe_zone:
        return False
    x1, y1, x2, y2 = bbox_norm
    top = float(safe_zone.get("top_pct", 0.0))
    bottom = float(safe_zone.get("bottom_pct", 0.0))
    left = float(safe_zone.get("left_pct", 0.0))
    right = float(safe_zone.get("right_pct", 0.0))
    return bool(y1 < top or y2 > (1.0 - bottom) or x1 < left or x2 > (1.0 - right))


def _classify_text_role(height_pct: float, y_center_norm: float) -> str:
    if height_pct >= 0.055:
        return "display"
    if y_center_norm >= 0.65 and height_pct >= 0.022:
        return "caption"
    if height_pct >= 0.025:
        return "body"
    return "micro"


def _compute_visual_weight(
    bbox_norm: tuple[float, float, float, float],
    sal_map: np.ndarray,
    wcag_contrast: float | None,
    kind: str,
) -> float:
    h, w = sal_map.shape[:2]
    x1, y1, x2, y2 = bbox_norm
    area = max(0.0, (x2 - x1) * (y2 - y1))
    px1, py1 = max(0, int(x1 * w)), max(0, int(y1 * h))
    px2, py2 = min(w, int(x2 * w)), min(h, int(y2 * h))
    sal_patch = sal_map[py1:py2, px1:px2]
    sal_mean = float(sal_patch.mean()) if sal_patch.size > 0 else 0.2
    cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    dist_center = math.hypot(cx - 0.5, cy - 0.45)
    centrality = max(0.0, 1.0 - dist_center * 1.3)
    contrast_norm = min(1.0, (wcag_contrast or 4.5) / 12.0)
    area_score = min(1.0, math.sqrt(area) * 1.8)
    kind_boost = 0.12 if kind in ("face", "subject_foreground") else 0.05 if kind == "text" else 0.0
    weight = (
        0.35 * area_score
        + 0.30 * sal_mean
        + 0.20 * contrast_norm
        + 0.15 * centrality
        + kind_boost
    )
    return round(min(1.0, max(0.0, weight)), 4)


def _assign_hierarchy_tiers(elements: list[dict[str, Any]]) -> None:
    if not elements:
        return
    ordered = sorted(elements, key=lambda e: e["visual_weight"], reverse=True)
    top_w = ordered[0]["visual_weight"]
    for idx, el in enumerate(ordered):
        w = el["visual_weight"]
        if idx == 0 or (w >= top_w * 0.82 and w >= 0.48):
            el["hierarchy_tier"] = 1
        elif w >= top_w * 0.50 and w >= 0.28:
            el["hierarchy_tier"] = 2
        else:
            el["hierarchy_tier"] = 3


def _render_blueprint(
    bgr: np.ndarray,
    frame_data: dict[str, Any],
    safe_zone: dict[str, float] | None,
    sal_map: np.ndarray,
    out_path: Path,
) -> None:
    """Render a Set-of-Mark diagnostic blueprint with rulers, grid lines, safe zones, and badges."""
    h, w = bgr.shape[:2]
    max_dim = 1080
    scale = min(1.0, max_dim / max(w, h, 1))
    rw, rh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(bgr, (rw, rh), interpolation=cv2.INTER_AREA)

    # Overlay saliency top-20% contour in amber.
    sal_r = cv2.resize(sal_map, (rw, rh), interpolation=cv2.INTER_LINEAR)
    sal_thresh = max(0.35, float(np.percentile(sal_r, 82)))
    sal_bin = (sal_r >= sal_thresh).astype(np.uint8) * 255
    contours, _ = cv2.findContours(sal_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(resized, contours, -1, (0, 180, 255), 2)

    img = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    # Platform safe-zone translucent red bands.
    if safe_zone:
        top_px = int(round(safe_zone.get("top_pct", 0.0) * rh))
        bot_px = int(round(safe_zone.get("bottom_pct", 0.0) * rh))
        left_px = int(round(safe_zone.get("left_pct", 0.0) * rw))
        right_px = int(round(safe_zone.get("right_pct", 0.0) * rw))
        band_col = (230, 50, 50, 48)
        if top_px > 0:
            draw.rectangle([(0, 0), (rw, top_px)], fill=band_col)
        if bot_px > 0:
            draw.rectangle([(0, rh - bot_px), (rw, rh)], fill=band_col)
        if left_px > 0:
            draw.rectangle([(0, top_px), (left_px, rh - bot_px)], fill=band_col)
        if right_px > 0:
            draw.rectangle([(rw - right_px, top_px), (rw, rh - bot_px)], fill=band_col)

    # Latent grid & structural divider lines (dashed cyan).
    for xn in frame_data["grid_lines_x_norm"]:
        x = int(round(xn * rw))
        for y in range(0, rh, 14):
            draw.line([(x, y), (x, min(rh, y + 7))], fill=(0, 230, 255, 190), width=1)
    for yn in frame_data["grid_lines_y_norm"]:
        y = int(round(yn * rh))
        for x in range(0, rw, 14):
            draw.line([(x, y), (min(rw, x + 7), y)], fill=(0, 230, 255, 190), width=1)

    # Percentage ruler ticks along top and left borders.
    for pct in range(10, 100, 10):
        rx = int(round(pct / 100.0 * rw))
        ry = int(round(pct / 100.0 * rh))
        draw.line([(rx, 0), (rx, 8)], fill=(255, 255, 255, 220), width=1)
        draw.text((rx + 2, 2), f"{pct}", fill=(255, 255, 255, 220), font=font)
        draw.line([(0, ry), (8, ry)], fill=(255, 255, 255, 220), width=1)
        draw.text((2, ry + 2), f"{pct}", fill=(255, 255, 255, 220), font=font)

    # Saliency centroid crosshair.
    scx = int(round(frame_data["saliency_centroid_norm"][0] * rw))
    scy = int(round(frame_data["saliency_centroid_norm"][1] * rh))
    draw.line([(scx - 10, scy), (scx + 10, scy)], fill=(255, 215, 0, 240), width=2)
    draw.line([(scx, scy - 10), (scx, scy + 10)], fill=(255, 215, 0, 240), width=2)

    # Set-of-Mark element boxes color-coded by hierarchy tier.
    tier_colors = {
        1: (50, 235, 120, 245),  # Tier 1 Primary: bright green
        2: (70, 175, 255, 235),  # Tier 2 Support: sky blue
        3: (210, 160, 255, 220),  # Tier 3 Tertiary: lavender
    }
    for el in frame_data["elements"]:
        x1, y1, x2, y2 = el["bbox_norm"]
        bx1, by1 = int(round(x1 * rw)), int(round(y1 * rh))
        bx2, by2 = int(round(x2 * rw)), int(round(y2 * rh))
        col = (255, 70, 70, 245) if el.get("safe_zone_violation") else tier_colors[
            el["hierarchy_tier"]
        ]
        draw.rectangle([(bx1, by1), (bx2, by2)], outline=col, width=2)
        tag = f"[{el['element_id']}] T{el['hierarchy_tier']}"
        if el.get("wcag_contrast") is not None:
            tag += f" {el['wcag_contrast']:.1f}:1"
        tw = max(48, len(tag) * 6 + 8)
        ty = max(0, by1 - 15)
        draw.rectangle([(bx1, ty), (min(rw, bx1 + tw), ty + 14)], fill=(15, 18, 24, 215))
        draw.text((bx1 + 3, ty + 2), tag, fill=col, font=font)

    # Top-right header badge.
    header = (
        f"t={frame_data['timestamp_s']:.2f}s | calm={frame_data['whitespace_ratio']:.0%} "
        f"| signals={frame_data['competing_signals']}"
    )
    hw = len(header) * 6 + 14
    draw.rectangle([(rw - hw - 6, 6), (rw - 6, 22)], fill=(15, 18, 24, 215))
    draw.text((rw - hw, 9), header, fill=(255, 255, 255, 240), font=font)

    merged = Image.alpha_composite(img, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.save(out_path, quality=88)


def _analyze_motion_window(
    cap: cv2.VideoCapture,
    fps: float,
    start_s: float,
    end_s: float,
    window_index: int,
    shot_index: int | None,
    ocr: RapidOCR | None,
) -> dict[str, Any]:
    """Analyze camera velocity via optical flow + RANSAC and element entrance easing."""
    duration = max(0.25, min(0.75, end_s - start_s))
    sample_fps = min(10.0, max(5.0, fps))
    n_steps = max(4, int(round(duration * sample_fps)))
    times = [start_s + (i / sample_fps) for i in range(n_steps)]

    frames_bgr: list[np.ndarray] = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if ok and frame is not None:
            frames_bgr.append(frame)

    if len(frames_bgr) < 2:
        return {
            "window_index": window_index,
            "shot_index": shot_index,
            "start_s": round(start_s, 3),
            "end_s": round(start_s + duration, 3),
            "camera_regime": "static",
            "camera_pan_px_s": 0.0,
            "camera_zoom_pct_s": 0.0,
            "entrances": [],
        }

    # Global camera motion via sparse Lucas-Kanade + RANSAC partial affine.
    pan_speeds: list[float] = []
    zoom_rates: list[float] = []
    dt = 1.0 / sample_fps
    prev_gray = cv2.cvtColor(frames_bgr[0], cv2.COLOR_BGR2GRAY)
    for frame in frames_bgr[1:]:
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=150, qualityLevel=0.02, minDistance=12)
        if pts is not None and len(pts) >= 8:
            next_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, pts, None)
            if next_pts is not None and status is not None:
                good_prev = pts[status.ravel() == 1]
                good_next = next_pts[status.ravel() == 1]
                if len(good_prev) >= 6:
                    mat, _ = cv2.estimateAffinePartial2D(good_prev, good_next, method=cv2.RANSAC)
                    if mat is not None:
                        dx, dy = float(mat[0, 2]), float(mat[1, 2])
                        scale = math.hypot(float(mat[0, 0]), float(mat[1, 0]))
                        pan_speeds.append(math.hypot(dx, dy) / dt)
                        zoom_rates.append(((scale - 1.0) * 100.0) / dt)
        prev_gray = curr_gray

    pan_med = round(float(statistics.median(pan_speeds)), 2) if pan_speeds else 0.0
    zoom_med = round(float(statistics.median(zoom_rates)), 2) if zoom_rates else 0.0

    if abs(zoom_med) >= 4.0 and pan_med >= 40.0:
        regime = "complex"
    elif abs(zoom_med) >= 4.0:
        regime = "zoom"
    elif pan_med >= 35.0:
        regime = "pan"
    elif pan_med >= 6.0 or abs(zoom_med) >= 1.2:
        regime = "slow_drift"
    else:
        regime = "static"

    # Element entrance trajectory tracking using OCR bounding boxes across the burst.
    entrances: list[dict[str, Any]] = []
    if ocr is not None:
        tracks: dict[int, list[tuple[float, float, float, float, float, str]]] = {}
        next_tid = 0
        for step_idx, frame in enumerate(frames_bgr):
            t_rel = step_idx * dt
            res, _ = ocr(frame)
            dets: list[tuple[float, float, float, float, str]] = []
            if res:
                for poly, txt, score in res:
                    if float(score) < 0.55 or not str(txt).strip():
                        continue
                    xs = [p[0] for p in poly]
                    ys = [p[1] for p in poly]
                    cx, cy = (min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5
                    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
                    dets.append((cx, cy, bw, bh, str(txt).strip()))
            for cx, cy, bw, bh, txt in dets:
                matched_id: int | None = None
                best_dist = 120.0
                for tid, hist in tracks.items():
                    last = hist[-1]
                    dist = math.hypot(cx - last[1], cy - last[2])
                    if dist < best_dist:
                        best_dist = dist
                        matched_id = tid
                if matched_id is None:
                    matched_id = next_tid
                    next_tid += 1
                    tracks[matched_id] = []
                tracks[matched_id].append((t_rel, cx, cy, bw, bh, txt))

        for tid, hist in tracks.items():
            if len(hist) < 3:
                continue
            dx_total = hist[-1][1] - hist[0][1]
            dy_total = hist[-1][2] - hist[0][2]
            dw_ratio = hist[-1][3] / max(hist[0][3], 1.0)
            disp_total = math.hypot(dx_total, dy_total)

            if disp_total >= 12.0:
                if abs(dy_total) >= abs(dx_total):
                    vec = "slide_up" if dy_total < 0 else "slide_down"
                else:
                    vec = "slide_left" if dx_total < 0 else "slide_right"
            elif abs(dw_ratio - 1.0) >= 0.06:
                vec = "scale_in"
            else:
                vec = "static_pop"

            # Estimate settle frame & easing shape from per-step speeds.
            step_speeds = [
                math.hypot(hist[i][1] - hist[i - 1][1], hist[i][2] - hist[i - 1][2])
                for i in range(1, len(hist))
            ]
            settle_idx = len(hist) - 1
            for i, sp in enumerate(step_speeds):
                if i > 0 and sp < 2.0:
                    settle_idx = i
                    break
            dur_ms = int(round((hist[settle_idx][0] - hist[0][0]) * 1000.0))
            tail_drift = round(float(step_speeds[-1]) if step_speeds else 0.0, 2)

            if vec == "static_pop":
                easing = "hard_cut"
                dur_ms = 0
            elif len(step_speeds) >= 2 and step_speeds[0] > 0:
                first_half = float(np.mean(step_speeds[: max(1, len(step_speeds) // 2)]))
                second_half = float(np.mean(step_speeds[max(1, len(step_speeds) // 2) :]))
                # Check sign reversal for overshoot.
                step_dy = [hist[i][2] - hist[i - 1][2] for i in range(1, len(hist))]
                sign_flip = any(
                    step_dy[i] * step_dy[i - 1] < -9.0 for i in range(1, len(step_dy))
                )
                if sign_flip:
                    easing = "overshoot"
                elif first_half > second_half * 1.8:
                    easing = "snappy_ease_out"
                elif first_half > second_half * 1.15:
                    easing = "smooth_editorial"
                else:
                    easing = "linear"
            else:
                easing = "unknown"

            entrances.append(
                {
                    "track_id": tid,
                    "text": hist[-1][5][:60],
                    "duration_ms": max(0, dur_ms),
                    "vector": vec,
                    "easing_class": easing,
                    "landed_drift_px": max(0.0, tail_drift),
                }
            )

    return {
        "window_index": window_index,
        "shot_index": shot_index,
        "start_s": round(start_s, 3),
        "end_s": round(start_s + duration, 3),
        "camera_regime": regime,
        "camera_pan_px_s": pan_med,
        "camera_zoom_pct_s": zoom_med,
        "entrances": entrances,
    }


def _load_sample_timestamps(
    shots_json: Path | None, duration_s: float, max_frames: int
) -> list[tuple[float, int | None, float, float]]:
    """Return list of (midpoint_s, shot_index, shot_start_s, shot_end_s)."""
    max_frames = max(1, max_frames)
    shots: list[tuple[int, float, float]] = []
    if shots_json is not None and shots_json.is_file():
        data = json.loads(shots_json.read_text(encoding="utf-8"))
        raw_shots = data.get("shots") or []
        for idx, s in enumerate(raw_shots):
            st = max(0.0, float(s.get("start_s", s.get("start", 0.0))))
            en = max(st, float(s.get("end_s", s.get("end", st + 1.0))))
            shot_id = max(0, int(s.get("shot_index", idx)))
            if en > st:
                shots.append((shot_id, st, en))

    if shots:
        if len(shots) > max_frames:
            step = len(shots) / max_frames
            shots = [shots[int(i * step)] for i in range(max_frames)]
        return [
            (round(max(0.0, (st + en) * 0.5), 3), idx, round(st, 3), round(en, 3))
            for idx, st, en in shots
        ]

    safe_dur = max(0.0, duration_s)
    count = max(1, min(max_frames, max(3, int(round(safe_dur / 3.0)))))
    step = safe_dur / count if count > 0 else 1.0
    return [
        (
            round(max(0.0, min(max(0.0, safe_dur - 0.05), (i + 0.5) * step)), 3),
            i,
            round(i * step, 3),
            round(min(safe_dur, (i + 1) * step), 3),
        )
        for i in range(count)
    ]


def _write_structure_md(result: dict[str, Any], out_path: Path) -> None:
    s = result["summary"]
    g = s["grid"]
    t = s["typography"]
    h = s["hierarchy"]
    m = s["motion"]

    margins = (
        f"`{g['margin_left_pct']:.1%}` / `{g['margin_right_pct']:.1%}` / "
        f"`{g['margin_top_pct']:.1%}` / `{g['margin_bottom_pct']:.1%}`"
    )
    snap_str = f"`{g['alignment_snap_score']:.2f}` (`{g['dominant_alignment']}`)"
    focal_str = f"`({h['focal_centroid_norm'][0]:.2f}, {h['focal_centroid_norm'][1]:.2f})`"
    face_str = (
        f"`{h.get('face_present_ratio', 0.0):.1%}` / `{h.get('median_eye_line_y_norm')}`"
    )
    type_h_str = (
        f"`{t.get('display_height_pct_p50')}` / `{t.get('body_height_pct_p50')}` / "
        f"`{t.get('caption_height_pct_p50')}`"
    )
    wcag_str = f"`{t.get('median_wcag_contrast')}` / `{t.get('min_wcag_contrast')}`"
    tilt_box_str = f"`{t['tilted_text_count']}` / `{t['boxed_text_ratio']:.1%}`"

    lines = [
        "# Spatial & Structural Forensics (`STRUCTURE.md`)",
        "",
        f"- **Source**: `{Path(result['source_path']).name}` "
        f"({result['width']}x{result['height']} @ {result['fps']}fps, "
        f"{result['aspect_ratio']}, {result['duration_s']}s)",
        f"- **Platform Safe-Zone**: `{result.get('platform_target_id') or 'none'}`",
        "",
        "## 1. Latent Grid & Alignment",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| Inferred columns | `{g['inferred_columns']}` |",
        f"| Margins (L / R / T / B) | {margins} |",
        f"| Alignment snap score | {snap_str} |",
        f"| Structural dividers | `{g.get('structural_dividers_detected', 0)}` |",
        "",
        "## 2. Visual Hierarchy & Framing",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| Mean competing Tier-1 signals | `{h['mean_competing_signals']:.2f}` |",
        f"| Mean whitespace / calm ratio | `{h['mean_whitespace_ratio']:.1%}` |",
        f"| Focal centroid (x, y norm) | {focal_str} |",
        f"| Safe-zone violation rate | `{h['safe_zone_violation_rate']:.1%}` |",
        f"| Face present ratio / Eye-line Y | {face_str} |",
        "",
        "## 3. Micro-Typography & Local Contrast",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| Text blocks measured | `{t['text_block_count']}` |",
        f"| Display / Body / Caption height % | {type_h_str} |",
        f"| Display-to-Caption scale ratio | `{t.get('display_to_caption_ratio')}` |",
        f"| WCAG contrast (median / min) | {wcag_str} |",
        f"| Tilted text blocks / Boxed ratio | {tilt_box_str} |",
        "",
        "## 4. Motion & Easing Physics",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
        f"| Dominant camera regime | `{m['dominant_camera_regime']}` |",
        f"| Median entrance duration | `{m.get('median_entrance_ms')} ms` |",
        f"| Dominant easing class | `{m['dominant_easing_class']}` |",
        f"| Idle drift detected | `{m['idle_drift_detected']}` |",
        "",
        "## 5. Set-of-Mark Frame Blueprints",
        "",
        "| Frame | Time | Calm | Signals | Safe-Zone Flags | Blueprint |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for fr in result["frames"]:
        bp = Path(fr["blueprint_path"]).name if fr.get("blueprint_path") else "-"
        viol = ", ".join(fr["safe_zone_violations"]) if fr["safe_zone_violations"] else "ok"
        lines.append(
            f"| `#{fr['frame_index']:02d}` | `{fr['timestamp_s']:.2f}s` | "
            f"`{fr['whitespace_ratio']:.0%}` | `{fr['competing_signals']}` | "
            f"`{viol}` | `spatial/{bp}` |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze_video(
    video_path: Path,
    out_dir: Path,
    *,
    shots_json: Path | None = None,
    safe_zone: dict[str, float] | None = None,
    platform_target_id: str | None = None,
    max_frames: int = 12,
    max_motion_windows: int = 4,
    use_subject_mask: bool = True,
    use_face_detection: bool = True,
) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError(f"Video reported invalid dimensions ({width}x{height}): {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_s = round(frame_count / fps, 3) if fps > 0 and frame_count > 0 else 0.0

    ocr = RapidOCR()

    rembg_session = None
    if use_subject_mask:
        try:
            os.environ.setdefault("U2NET_HOME", str(DEFAULT_MODELS_DIR))
            model_file = Path(os.environ["U2NET_HOME"]) / "u2netp.onnx"
            if model_file.is_file():
                from rembg import new_session

                rembg_session = new_session("u2netp", providers=["CPUExecutionProvider"])
        except Exception:
            rembg_session = None

    face_detector = None
    if use_face_detection:
        try:
            import mediapipe as mp

            if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_detection"):
                face_detector = mp.solutions.face_detection.FaceDetection(
                    model_selection=1, min_detection_confidence=0.5
                )
        except Exception:
            face_detector = None

    samples = _load_sample_timestamps(shots_json, duration_s, max_frames)
    out_dir.mkdir(parents=True, exist_ok=True)
    spatial_dir = out_dir / "spatial"
    spatial_dir.mkdir(parents=True, exist_ok=True)

    frame_results: list[dict[str, Any]] = []
    all_lefts: list[float] = []
    all_rights: list[float] = []
    all_tops: list[float] = []
    all_bottoms: list[float] = []
    all_x_edges: list[float] = []
    align_votes: dict[str, int] = {"left": 0, "center": 0, "right": 0}
    total_dividers = 0

    display_h: list[float] = []
    body_h: list[float] = []
    caption_h: list[float] = []
    wcag_vals: list[float] = []
    tilted_count = 0
    boxed_count = 0
    total_text_blocks = 0
    eye_lines: list[float] = []
    face_frames = 0
    fg_bg_deltas: list[float] = []
    shot_scales: list[str] = []
    rot_scores: list[float] = []
    lighting_keys: list[str] = []

    for f_idx, (t_mid, shot_idx, _st, _en) in enumerate(samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t_mid) * 1000.0)
        ok, bgr = cap.read()
        if not ok or bgr is None:
            continue

        sal_map = _spectral_residual_saliency(bgr)
        sal_centroid = _saliency_centroid(sal_map)
        div_x, div_y = _detect_structural_dividers(bgr)
        total_dividers += len(div_x) + len(div_y)

        elements: list[dict[str, Any]] = []
        text_boxes_px: list[tuple[int, int, int, int]] = []
        frame_x_edges: list[float] = list(div_x)
        frame_y_edges: list[float] = list(div_y)
        violations: list[str] = []

        # 1. Micro-typography via RapidOCR.
        ocr_res, _ = ocr(bgr)
        t_counter = 1
        if ocr_res:
            for poly, txt, score in ocr_res:
                clean_txt = str(txt).strip()
                if float(score) < 0.55 or not clean_txt:
                    continue
                pts = np.array(poly, dtype=np.float64)
                x1, y1 = int(np.floor(pts[:, 0].min())), int(np.floor(pts[:, 1].min()))
                x2, y2 = int(np.ceil(pts[:, 0].max())), int(np.ceil(pts[:, 1].max()))
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                if x2 - x1 < 6 or y2 - y1 < 6:
                    continue

                # Top edge angle in degrees.
                dx = float(pts[1, 0] - pts[0, 0])
                dy = float(pts[1, 1] - pts[0, 1])
                tilt_deg = round(math.degrees(math.atan2(dy, dx)), 2) if abs(dx) > 1e-3 else 0.0
                if abs(tilt_deg) >= 1.5:
                    tilted_count += 1

                bbox_norm = (
                    round(x1 / width, 4),
                    round(y1 / height, 4),
                    round(x2 / width, 4),
                    round(y2 / height, 4),
                )
                h_pct = (y2 - y1) / height
                yc = (bbox_norm[1] + bbox_norm[3]) * 0.5
                xc = (bbox_norm[0] + bbox_norm[2]) * 0.5
                role = _classify_text_role(h_pct, yc)
                if role == "display":
                    display_h.append(h_pct)
                elif role == "caption":
                    caption_h.append(h_pct)
                elif role == "body":
                    body_h.append(h_pct)

                contrast, fg_hex, bg_hex, container_style = _sample_text_contrast_and_style(
                    bgr, (x1, y1, x2, y2)
                )
                wcag_vals.append(contrast)
                total_text_blocks += 1
                if container_style != "boxless":
                    boxed_count += 1

                viol = _check_safe_zone(bbox_norm, safe_zone)
                el_id = f"T{t_counter}"
                t_counter += 1
                if viol:
                    violations.append(el_id)

                text_boxes_px.append((x1, y1, x2, y2))
                all_lefts.append(bbox_norm[0])
                all_rights.append(1.0 - bbox_norm[2])
                all_tops.append(bbox_norm[1])
                all_bottoms.append(1.0 - bbox_norm[3])
                frame_x_edges.extend([bbox_norm[0], bbox_norm[2]])
                frame_y_edges.extend([bbox_norm[1], bbox_norm[3]])
                all_x_edges.extend([bbox_norm[0], xc, bbox_norm[2]])

                if abs(xc - 0.5) <= 0.06:
                    align_votes["center"] += 1
                elif bbox_norm[0] < (1.0 - bbox_norm[2]):
                    align_votes["left"] += 1
                else:
                    align_votes["right"] += 1

                elements.append(
                    {
                        "element_id": el_id,
                        "kind": "text",
                        "bbox_px": [x1, y1, x2, y2],
                        "bbox_norm": list(bbox_norm),
                        "hierarchy_tier": 2,
                        "visual_weight": _compute_visual_weight(
                            bbox_norm, sal_map, contrast, "text"
                        ),
                        "text": clean_txt[:80],
                        "text_role": role,
                        "container_style": container_style,
                        "tilt_deg": tilt_deg,
                        "wcag_contrast": contrast,
                        "fg_hex": fg_hex,
                        "bg_hex": bg_hex,
                        "safe_zone_violation": viol,
                    }
                )

        # 2. Graphic containers.
        g_boxes = _detect_graphic_containers(bgr, text_boxes_px)
        for g_idx, (x1, y1, x2, y2) in enumerate(g_boxes, start=1):
            bbox_norm = (
                round(x1 / width, 4),
                round(y1 / height, 4),
                round(x2 / width, 4),
                round(y2 / height, 4),
            )
            viol = _check_safe_zone(bbox_norm, safe_zone)
            el_id = f"G{g_idx}"
            if viol:
                violations.append(el_id)
            frame_x_edges.extend([bbox_norm[0], bbox_norm[2]])
            frame_y_edges.extend([bbox_norm[1], bbox_norm[3]])
            elements.append(
                {
                    "element_id": el_id,
                    "kind": "graphic_container",
                    "bbox_px": [x1, y1, x2, y2],
                    "bbox_norm": list(bbox_norm),
                    "hierarchy_tier": 2,
                    "visual_weight": _compute_visual_weight(
                        bbox_norm, sal_map, None, "graphic_container"
                    ),
                    "text": None,
                    "text_role": None,
                    "container_style": "card",
                    "tilt_deg": 0.0,
                    "wcag_contrast": None,
                    "fg_hex": None,
                    "bg_hex": None,
                    "safe_zone_violation": viol,
                }
            )

        # 3. Subject foreground mask (u2netp) & whitespace/calm ratio.
        subj_mask = _detect_subject_mask(bgr, rembg_session)
        if subj_mask is not None and subj_mask.sum() > (width * height * 0.02):
            ys, xs = np.where(subj_mask > 0)
            sx1, sy1, sx2, sy2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
            s_norm = (
                round(sx1 / width, 4),
                round(sy1 / height, 4),
                round(sx2 / width, 4),
                round(sy2 / height, 4),
            )
            elements.append(
                {
                    "element_id": "S1",
                    "kind": "subject_foreground",
                    "bbox_px": [sx1, sy1, sx2, sy2],
                    "bbox_norm": list(s_norm),
                    "hierarchy_tier": 1,
                    "visual_weight": _compute_visual_weight(
                        s_norm, sal_map, None, "subject_foreground"
                    ),
                    "text": None,
                    "text_role": None,
                    "container_style": None,
                    "tilt_deg": None,
                    "wcag_contrast": None,
                    "fg_hex": None,
                    "bg_hex": None,
                    "safe_zone_violation": False,
                }
            )
            occupied = subj_mask.astype(bool)
        else:
            occupied = sal_map >= max(0.30, float(np.percentile(sal_map, 75)))

        for el in elements:
            if el["kind"] in ("text", "graphic_container"):
                bx1, by1, bx2, by2 = el["bbox_px"]
                occupied[by1:by2, bx1:bx2] = True
        whitespace_ratio = round(float(1.0 - occupied.mean()), 4)

        # 4. Face & eye-line detection.
        face_boxes, eye_line = _detect_faces_and_eyeline(bgr, face_detector)
        if face_boxes:
            face_frames += 1
        if eye_line is not None:
            eye_lines.append(eye_line)
        for fi, (fx1, fy1, fx2, fy2) in enumerate(face_boxes, start=1):
            f_norm = (
                round(fx1 / width, 4),
                round(fy1 / height, 4),
                round(fx2 / width, 4),
                round(fy2 / height, 4),
            )
            elements.append(
                {
                    "element_id": f"F{fi}",
                    "kind": "face",
                    "bbox_px": [fx1, fy1, fx2, fy2],
                    "bbox_norm": list(f_norm),
                    "hierarchy_tier": 1,
                    "visual_weight": _compute_visual_weight(f_norm, sal_map, None, "face"),
                    "text": None,
                    "text_role": None,
                    "container_style": None,
                    "tilt_deg": None,
                    "wcag_contrast": None,
                    "fg_hex": None,
                    "bg_hex": None,
                    "safe_zone_violation": False,
                }
            )

        _assign_hierarchy_tiers(elements)
        competing = sum(1 for el in elements if el["hierarchy_tier"] == 1)

        # Estimate shot scale, headroom, and figure-ground luminance separation.
        fg_luma_delta: float | None = None
        if subj_mask is not None and subj_mask.any() and (~subj_mask.astype(bool)).any():
            gray_f = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            fg_m = float(gray_f[subj_mask > 0].mean())
            bg_m = float(gray_f[subj_mask == 0].mean())
            fg_luma_delta = round(abs(fg_m - bg_m), 2)
            fg_bg_deltas.append(fg_luma_delta)

        headroom_pct: float | None = None
        shot_scale_est: str = "graphic"
        if face_boxes:
            tallest = max(face_boxes, key=lambda b: b[3] - b[1])
            face_h_ratio = (tallest[3] - tallest[1]) / max(height, 1)
            headroom_pct = round(max(0.0, min(1.0, tallest[1] / max(height, 1))), 4)
            if face_h_ratio >= 0.45:
                shot_scale_est = "ecu"
            elif face_h_ratio >= 0.28:
                shot_scale_est = "cu"
            elif face_h_ratio >= 0.18:
                shot_scale_est = "mcu"
            elif face_h_ratio >= 0.10:
                shot_scale_est = "ms"
            else:
                shot_scale_est = "ws"
        elif subj_mask is not None and subj_mask.sum() > (width * height * 0.04):
            shot_scale_est = "ws"
        shot_scales.append(shot_scale_est)

        # Computational cinematography frame cues (lighting key, thirds, symmetry, warm/cool).
        gray_c = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        mean_y = float(gray_c.mean())
        rms_c = float(gray_c.std())
        dark_f = float((gray_c < 52.0).mean())
        bright_f = float((gray_c > 195.0).mean())
        if dark_f > 0.35 and bright_f > 0.12 and rms_c >= 58.0:
            lighting_key = "chiaroscuro"
        elif mean_y >= 158.0 and dark_f < 0.18:
            lighting_key = "high_key"
        elif mean_y <= 82.0:
            lighting_key = "low_key"
        else:
            lighting_key = "normal_key"
        lighting_keys.append(lighting_key)

        thirds_pts = ((1.0 / 3.0, 1.0 / 3.0), (2.0 / 3.0, 1.0 / 3.0), (1.0 / 3.0, 2.0 / 3.0), (2.0 / 3.0, 2.0 / 3.0))
        min_d = min(math.hypot(sal_centroid[0] - px, sal_centroid[1] - py) for px, py in thirds_pts)
        rot_score = round(max(0.0, min(1.0, 1.0 - (min_d / 0.38))), 4)
        rot_scores.append(rot_score)

        flipped_y = cv2.flip(gray_c, 1)
        sym_index = round(max(0.0, min(1.0, 1.0 - float(np.abs(gray_c - flipped_y).mean()) / 255.0)), 4)
        b_ch = bgr[:, :, 0].astype(np.float32)
        r_ch = bgr[:, :, 2].astype(np.float32)
        wb_balance = round(max(-1.0, min(1.0, float(((r_ch - b_ch) / 255.0).mean()))), 4)

        bp_path = spatial_dir / f"frame_{f_idx:03d}_blueprint.jpg"
        frame_entry: dict[str, Any] = {
            "frame_index": f_idx,
            "shot_index": shot_idx,
            "timestamp_s": round(max(0.0, t_mid), 3),
            "blueprint_path": str(bp_path),
            "saliency_centroid_norm": list(sal_centroid),
            "whitespace_ratio": whitespace_ratio,
            "competing_signals": competing,
            "eye_line_y_norm": eye_line,
            "shot_scale_est": shot_scale_est,
            "headroom_pct": headroom_pct,
            "figure_ground_luma_delta": fg_luma_delta,
            "lighting_key": lighting_key,
            "rule_of_thirds_score": rot_score,
            "symmetry_index": sym_index,
            "warm_cool_balance": wb_balance,
            "grid_lines_x_norm": _cluster_1d(frame_x_edges, eps=0.025),
            "grid_lines_y_norm": _cluster_1d(frame_y_edges, eps=0.025),
            "safe_zone_violations": violations,
            "elements": elements,
        }
        _render_blueprint(bgr, frame_entry, safe_zone, sal_map, bp_path)
        frame_results.append(frame_entry)

    # 5. Motion & easing windows at shot onsets.
    motion_windows: list[dict[str, Any]] = []
    win_samples = samples[:max_motion_windows]
    for w_idx, (_mid, shot_idx, st, en) in enumerate(win_samples):
        motion_windows.append(
            _analyze_motion_window(cap, fps, st, en, w_idx, shot_idx, ocr)
        )

    cap.release()
    if face_detector is not None:
        face_detector.close()

    # Aggregate video-level summaries.
    grid_clusters_x = _cluster_1d(all_x_edges, eps=0.03)
    inferred_cols = max(1, min(6, len(grid_clusters_x) // 2)) if grid_clusters_x else 1
    if all_x_edges and grid_clusters_x:
        snapped = sum(
            1 for x in all_x_edges if min(abs(x - c) for c in grid_clusters_x) <= 0.025
        )
        snap_score = round(snapped / len(all_x_edges), 4)
    else:
        snap_score = 0.0

    total_votes = sum(align_votes.values())
    if total_votes == 0:
        dom_align = "none"
    else:
        top_align, top_count = max(align_votes.items(), key=lambda kv: kv[1])
        dom_align = top_align if (top_count / total_votes) >= 0.55 else "mixed"

    disp_p50 = round(float(statistics.median(display_h)), 4) if display_h else None
    body_p50 = round(float(statistics.median(body_h)), 4) if body_h else None
    cap_p50 = round(float(statistics.median(caption_h)), 4) if caption_h else None
    scale_ratio = (
        round(disp_p50 / cap_p50, 2)
        if disp_p50 is not None and cap_p50 is not None and cap_p50 > 0
        else None
    )

    n_frames = max(1, len(frame_results))
    mean_cx = round(
        sum(f["saliency_centroid_norm"][0] for f in frame_results) / n_frames, 4
    )
    mean_cy = round(
        sum(f["saliency_centroid_norm"][1] for f in frame_results) / n_frames, 4
    )
    viol_frames = sum(1 for f in frame_results if f["safe_zone_violations"])

    regimes = [w["camera_regime"] for w in motion_windows]
    dom_regime = min(set(regimes), key=lambda r: (-regimes.count(r), r)) if regimes else "static"
    all_entrances = [e for w in motion_windows for e in w["entrances"]]
    ent_ms = [e["duration_ms"] for e in all_entrances if e["duration_ms"] > 0]
    easings = [e["easing_class"] for e in all_entrances if e["easing_class"] != "unknown"]
    dom_easing = min(set(easings), key=lambda e: (-easings.count(e), e)) if easings else "unknown"
    idle_drift = any(e["landed_drift_px"] >= 3.5 for e in all_entrances)

    structure_md = out_dir / "STRUCTURE.md"
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "source_path": str(video_path.resolve()),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "duration_s": duration_s,
        "aspect_ratio": _aspect_label(width, height),
        "platform_target_id": platform_target_id,
        "output_dir": str(out_dir.resolve()),
        "structure_md_path": str(structure_md.resolve()),
        "summary": {
            "grid": {
                "inferred_columns": inferred_cols,
                "margin_left_pct": round(min(all_lefts), 4) if all_lefts else 0.0,
                "margin_right_pct": round(min(all_rights), 4) if all_rights else 0.0,
                "margin_top_pct": round(min(all_tops), 4) if all_tops else 0.0,
                "margin_bottom_pct": round(min(all_bottoms), 4) if all_bottoms else 0.0,
                "alignment_snap_score": snap_score,
                "dominant_alignment": dom_align,
                "structural_dividers_detected": total_dividers,
            },
            "typography": {
                "text_block_count": total_text_blocks,
                "display_height_pct_p50": disp_p50,
                "body_height_pct_p50": body_p50,
                "caption_height_pct_p50": cap_p50,
                "display_to_caption_ratio": scale_ratio,
                "median_wcag_contrast": (
                    round(float(statistics.median(wcag_vals)), 2) if wcag_vals else None
                ),
                "min_wcag_contrast": round(min(wcag_vals), 2) if wcag_vals else None,
                "tilted_text_count": tilted_count,
                "boxed_text_ratio": (
                    round(boxed_count / total_text_blocks, 4) if total_text_blocks else 0.0
                ),
            },
            "hierarchy": {
                "mean_competing_signals": round(
                    sum(f["competing_signals"] for f in frame_results) / n_frames, 2
                ),
                "mean_whitespace_ratio": round(
                    sum(f["whitespace_ratio"] for f in frame_results) / n_frames, 4
                ),
                "focal_centroid_norm": [mean_cx, mean_cy],
                "safe_zone_violation_rate": round(viol_frames / n_frames, 4),
                "face_present_ratio": round(face_frames / n_frames, 4),
                "median_eye_line_y_norm": (
                    round(float(statistics.median(eye_lines)), 4) if eye_lines else None
                ),
                "mean_figure_ground_luma_delta": (
                    round(sum(fg_bg_deltas) / len(fg_bg_deltas), 2) if fg_bg_deltas else None
                ),
                "dominant_shot_scale": (
                    min(set(shot_scales), key=lambda s: (-shot_scales.count(s), s))
                    if shot_scales
                    else None
                ),
                "mean_rule_of_thirds_score": (
                    round(sum(rot_scores) / len(rot_scores), 4) if rot_scores else None
                ),
                "dominant_lighting_key": (
                    min(set(lighting_keys), key=lambda k: (-lighting_keys.count(k), k))
                    if lighting_keys
                    else None
                ),
            },
            "motion": {
                "dominant_camera_regime": dom_regime,
                "median_entrance_ms": int(round(statistics.median(ent_ms))) if ent_ms else None,
                "dominant_easing_class": dom_easing,
                "idle_drift_detected": idle_drift,
            },
        },
        "frames": frame_results,
        "motion_windows": motion_windows,
    }

    (out_dir / "spatial_forensics.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_structure_md(result, structure_md)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run spatial, grid, hierarchy, typography, and motion forensics on a video."
    )
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--shots-json", type=Path, default=None)
    parser.add_argument("--safe-zone-json", type=str, default=None)
    parser.add_argument("--platform-target-id", type=str, default=None)
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--max-motion-windows", type=int, default=4)
    parser.add_argument("--no-subject-mask", action="store_true")
    parser.add_argument("--no-face-detection", action="store_true")
    args = parser.parse_args()

    safe_zone = json.loads(args.safe_zone_json) if args.safe_zone_json else None
    result = analyze_video(
        args.video,
        args.out_dir,
        shots_json=args.shots_json,
        safe_zone=safe_zone,
        platform_target_id=args.platform_target_id,
        max_frames=args.max_frames,
        max_motion_windows=args.max_motion_windows,
        use_subject_mask=not args.no_subject_mask,
        use_face_detection=not args.no_face_detection,
    )
    summary_out = {
        "spatial_forensics_path": str(args.out_dir / "spatial_forensics.json"),
        "structure_md_path": result["structure_md_path"],
        "frames": len(result["frames"]),
    }
    print(json.dumps(summary_out))


if __name__ == "__main__":
    main()
