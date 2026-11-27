"""Shared deterministic WCAG contrast, quantile, and normalized geometry helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from vedit.models import SafeZoneMargins


def parse_hex_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse a `#RRGGBB` color string into 8-bit RGB channels."""
    clean = hex_color.strip()
    if len(clean) != 7 or not clean.startswith("#"):
        raise ValueError(f"Expected #RRGGBB hex color, got: {hex_color!r}")
    return (int(clean[1:3], 16), int(clean[3:5], 16), int(clean[5:7], 16))


def relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance in `[0.0, 1.0]` for an sRGB `#RRGGBB` color."""
    rgb = parse_hex_rgb(hex_color)
    channels: list[float] = []
    for raw in rgb:
        s = raw / 255.0
        channels.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def wcag_contrast_ratio(color_a: str, color_b: str) -> float:
    """Compute WCAG 2.1 contrast ratio in `[1.0, 21.0]` between two `#RRGGBB` colors."""
    lum_a = relative_luminance(color_a)
    lum_b = relative_luminance(color_b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def pick_accessible_ink(
    ground_hex: str,
    *,
    min_contrast: float = 4.5,
    candidates: Sequence[str] = (),
) -> str:
    """Select an ink color guaranteed to clear `min_contrast` against `ground_hex`."""
    defaults = ["#F8FAFC", "#0F172A", "#FFFFFF", "#000000"]
    for candidate in [*candidates, *defaults]:
        try:
            if wcag_contrast_ratio(candidate, ground_hex) >= min_contrast:
                return candidate.upper()
        except ValueError:
            continue
    return max(("#FFFFFF", "#000000"), key=lambda c: wcag_contrast_ratio(c, ground_hex))


def hex_distance(color_a: str, color_b: str) -> float:
    """Compute Euclidean distance in 8-bit RGB space as a quick perceptual guard."""
    ra, ga, ba = parse_hex_rgb(color_a)
    rb, gb, bb = parse_hex_rgb(color_b)
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def pick_accent_color(
    ground_hex: str,
    candidates: Sequence[tuple[str, float, float]],
    *,
    min_contrast: float = 3.0,
    exclude_hex: str | None = None,
) -> str:
    """Choose a high-chroma, readable accent color from `(hex, lab_chroma, share)` tuples."""
    ranked = sorted(
        candidates,
        key=lambda item: (item[1] * (0.4 + min(item[2], 0.6))),
        reverse=True,
    )
    for hex_val, _, _ in ranked:
        normalized = hex_val.upper()
        if exclude_hex and normalized == exclude_hex.upper():
            continue
        if hex_distance(normalized, ground_hex) < 40.0:
            continue
        if wcag_contrast_ratio(normalized, ground_hex) >= min_contrast:
            return normalized

    fallback = "#38BDF8" if relative_luminance(ground_hex) < 0.3 else "#2563EB"
    if exclude_hex and fallback == exclude_hex.upper():
        fallback = "#F59E0B" if relative_luminance(ground_hex) < 0.3 else "#D97706"
    return fallback


def compute_quantiles(values: Sequence[float]) -> tuple[float, float, float]:
    """Return `(p25, p50, p75)` quantiles using linear interpolation."""
    if not values:
        raise ValueError("Cannot compute quantiles of an empty sequence.")
    ordered = sorted(float(v) for v in values)

    def _pct(q: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        pos = q * (len(ordered) - 1)
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return ordered[lo]
        frac = pos - lo
        return ordered[lo] * (1.0 - frac) + ordered[hi] * frac

    return (_pct(0.25), _pct(0.50), _pct(0.75))


@dataclass(frozen=True, slots=True)
class NormRect:
    """Normalized canvas rectangle in `[0.0, 1.0]` coordinates."""

    top: float
    bottom: float
    left: float
    right: float

    def area(self) -> float:
        return max(0.0, self.bottom - self.top) * max(0.0, self.right - self.left)

    def intersection_area(self, other: NormRect) -> float:
        i_top = max(self.top, other.top)
        i_bottom = min(self.bottom, other.bottom)
        i_left = max(self.left, other.left)
        i_right = min(self.right, other.right)
        if i_bottom <= i_top or i_right <= i_left:
            return 0.0
        return (i_bottom - i_top) * (i_right - i_left)

    def overlap_fraction(self, other: NormRect) -> float:
        inter = self.intersection_area(other)
        if inter <= 0.0:
            return 0.0
        denom = min(self.area(), other.area())
        return inter / denom if denom > 0.0 else 0.0


def resolve_overlay_rect(
    safe_band: str,
    safe_zone: SafeZoneMargins,
    explicit_box: Mapping[str, Any] | None = None,
) -> NormRect:
    """Resolve the effective normalized screen rectangle for an overlay composition."""
    if explicit_box and all(k in explicit_box for k in ("top", "bottom", "left", "right")):
        return NormRect(
            top=float(explicit_box["top"]),
            bottom=float(explicit_box["bottom"]),
            left=float(explicit_box["left"]),
            right=float(explicit_box["right"]),
        )

    s_top = safe_zone.top_pct
    s_bottom = 1.0 - safe_zone.bottom_pct
    s_left = safe_zone.left_pct
    s_right = 1.0 - safe_zone.right_pct

    if safe_band == "lower_third":
        return NormRect(
            top=max(s_top, s_bottom - 0.18),
            bottom=s_bottom,
            left=s_left,
            right=s_right,
        )
    if safe_band == "upper_safe":
        return NormRect(
            top=s_top,
            bottom=min(s_bottom, s_top + 0.16),
            left=s_left,
            right=s_right,
        )
    if safe_band == "left_rail":
        return NormRect(
            top=s_top,
            bottom=s_bottom,
            left=s_left,
            right=min(s_right, s_left + 0.36),
        )
    if safe_band == "right_rail":
        return NormRect(
            top=s_top,
            bottom=s_bottom,
            left=max(s_left, s_right - 0.36),
            right=s_right,
        )
    if safe_band == "center_safe":
        mid_y = (s_top + s_bottom) / 2.0
        return NormRect(
            top=max(s_top, mid_y - 0.10),
            bottom=min(s_bottom, mid_y + 0.10),
            left=s_left,
            right=s_right,
        )
    return NormRect(top=0.0, bottom=1.0, left=0.0, right=1.0)


def intervals_overlap(
    a_start: float,
    a_dur: float,
    b_start: float,
    b_dur: float,
    eps: float = 1e-6,
) -> bool:
    """Return True if `[a_start, a_start + a_dur)` intersects `[b_start, b_start + b_dur)`."""
    a_end = a_start + a_dur
    b_end = b_start + b_dur
    return min(a_end, b_end) - max(a_start, b_start) > eps
