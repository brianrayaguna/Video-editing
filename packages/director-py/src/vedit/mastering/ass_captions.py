"""Native FFmpeg libass generator for plain captions, text watermarks, and source credits.

Routing static/plain documentary text overlays through FFmpeg's libass renderer avoids
headless Chromium + ProRes 4444 RGBA rendering for frames that require zero DOM animation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from vedit.models import EditPlan, OverlayCompositionOp, PlatformTarget

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_ass_fastpath_overlay(ov: OverlayCompositionOp) -> bool:
    """Return True when an overlay can render natively via FFmpeg libass without Chromium."""
    props = ov.props or {}
    if props.get("custom_html") or props.get("custom_css") or props.get("custom_timeline_js"):
        return False

    merged: dict[str, Any] = {**(ov.variables or {}), **props}
    if ov.kind == "caption_rail":
        style = str(merged.get("caption_style") or "plain").lower()
        return style == "plain"

    if ov.template_id in ("broadcast_bug", "source_credit"):
        return True

    return False


def partition_overlays_for_hybrid(
    plan: EditPlan,
    *,
    force_hyperframes: bool = False,
) -> tuple[list[OverlayCompositionOp], list[OverlayCompositionOp]]:
    """Split hybrid overlays into (ass_fastpath_overlays, hyperframes_animated_overlays)."""
    if force_hyperframes or plan.render_strategy != "hybrid":
        return [], list(plan.overlay_compositions)

    ass_overlays: list[OverlayCompositionOp] = []
    hf_overlays: list[OverlayCompositionOp] = []
    for ov in plan.overlay_compositions:
        if is_ass_fastpath_overlay(ov):
            ass_overlays.append(ov)
        else:
            hf_overlays.append(ov)
    return ass_overlays, hf_overlays


def build_sparse_hf_plan(
    plan: EditPlan,
    hf_overlays: list[OverlayCompositionOp],
) -> EditPlan:
    """Return a trimmed hybrid EditPlan covering only active animated HyperFrames overlays.

    Trailing transparent frames after the final animated overlay end time are omitted;
    FFmpeg's `overlay=0:0:shortest=0:eof_action=pass` passes base video through cleanly.
    """
    if not hf_overlays:
        return plan.model_copy(update={"overlay_compositions": []})
    max_end = max(ov.timeline_start_s + ov.timeline_duration_s for ov in hf_overlays)
    # Keep at least 0.2s padding and never exceed plan.duration_s.
    trimmed_dur = round(min(plan.duration_s, max(0.5, max_end + 0.1)), 3)
    return plan.model_copy(
        update={
            "duration_s": trimmed_dur,
            "overlay_compositions": hf_overlays,
        }
    )


def _hex_to_ass_color(hex_color: str, alpha_0_to_1: float = 1.0) -> str:
    """Convert `#RRGGBB` and opacity `[0..1]` into ASS `&HAABBGGRR` (00=opaque, FF=transparent)."""
    clean = hex_color.strip().upper() if _HEX_RE.fullmatch(hex_color.strip()) else "#F4F1EA"
    r = int(clean[1:3], 16)
    g = int(clean[3:5], 16)
    b = int(clean[5:7], 16)
    a_inv = round((1.0 - max(0.0, min(1.0, alpha_0_to_1))) * 255)
    return f"&H{a_inv:02X}{b:02X}{g:02X}{r:02X}"


def _format_ass_time(seconds: float) -> str:
    total_cs = max(0, round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    secs = total_s % 60
    total_m = total_s // 60
    mins = total_m % 60
    hours = total_m // 60
    return f"{hours}:{mins:02d}:{secs:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\\", "\\\u2060").replace("{", r"\{").replace("}", r"\}")
    return cleaned.replace("\n", r"\N")


def _primary_font_name(raw_family: Any, default: str = "Space Grotesk") -> str:
    if not isinstance(raw_family, str) or not raw_family.strip():
        return default
    return raw_family.split(",")[0].strip().strip("'\"") or default


def _caption_style(
    merged: dict[str, Any], *, width: int, height: int, is_portrait: bool
) -> dict[str, Any]:
    """Resolve caption typography from overlay props, defaulting to the engine house style.

    Supported props (all optional): `caption_font_px`, `caption_bottom_pct`,
    `caption_bold`, `caption_opacity`, `caption_outline_px`, `caption_shadow_px`,
    `caption_shadow_opacity`, `caption_shadow_blur_px`, `caption_letter_spacing`.
    """

    def _num(key: str) -> float | None:
        raw = merged.get(key)
        if raw is None or isinstance(raw, bool):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    default_px = round(width * 0.056) if is_portrait else round(height * 0.054)
    font_px = _num("caption_font_px")
    bottom_pct = _num("caption_bottom_pct")
    opacity = _num("caption_opacity")
    shadow_opacity = _num("caption_shadow_opacity")
    blur = _num("caption_shadow_blur_px")
    glow_px = _num("caption_glow_px")
    glow_color_raw = merged.get("caption_glow_color") or merged.get("glow_color")
    glow_color = (
        str(glow_color_raw).strip().upper()
        if isinstance(glow_color_raw, str) and _HEX_RE.fullmatch(glow_color_raw.strip())
        else None
    )
    spacing = _num("caption_letter_spacing")
    bold_raw = merged.get("caption_bold", True)
    return {
        "font_px": round(font_px) if font_px and font_px > 0 else default_px,
        "bottom_pct": min(max(bottom_pct, 0.0), 0.9) if bottom_pct is not None else None,
        "bold": bool(bold_raw),
        "opacity": min(max(opacity, 0.0), 1.0) if opacity is not None else 1.0,
        "outline_px": max(_num("caption_outline_px") or 0.0, 0.0)
        if _num("caption_outline_px") is not None
        else None,
        "shadow_px": max(_num("caption_shadow_px") or 0.0, 0.0)
        if _num("caption_shadow_px") is not None
        else None,
        "shadow_opacity": min(max(shadow_opacity, 0.0), 1.0)
        if shadow_opacity is not None
        else 0.88,
        "shadow_blur_px": max(blur, 0.0) if blur is not None else 0.0,
        "glow_color": glow_color,
        "glow_px": max(glow_px, 0.0) if glow_px is not None else 0.0,
        "letter_spacing": spacing if spacing is not None else -0.3,
    }


def write_ass_overlays_file(
    overlays: list[OverlayCompositionOp],
    platform_target: PlatformTarget,
    output_ass_path: Path,
) -> Path:
    """Generate a pixel-accurate ASS v4+ script for plain captions, watermarks, and credits."""
    width = platform_target.width
    height = platform_target.height
    is_portrait = height > width
    scale = min(width, height) / 1080.0
    sz = platform_target.safe_zone

    sym_x_px = round(width * max(sz.left_pct, sz.right_pct, 0.06))
    upper_margin_v = round(height * sz.top_pct)
    # ASS Fontsize scales by ascender+descender (~0.72x CSS visual cap-height); scale
    # proportionally so visual size matches CSS 44px @ 1080x1920 and 42px @ 1920x1080.
    wm_font_px = max(18, round(24 * scale))
    wm_margin_v = round(height * (0.16 if is_portrait else 0.075))
    wm_margin_r = round(width * (0.055 if is_portrait else 0.05))
    credit_font_px = max(16, round(20 * scale))
    credit_margin_l = round(width * sz.left_pct)

    first_cap = next((o for o in overlays if o.kind == "caption_rail"), None)
    cap_merged = {**(first_cap.variables or {}), **(first_cap.props or {})} if first_cap else {}
    cap_font = _primary_font_name(
        cap_merged.get("caption_font_family") or cap_merged.get("font_family"), "Space Grotesk"
    )
    cap_style = _caption_style(cap_merged, width=width, height=height, is_portrait=is_portrait)
    cap_bottom_pct = cap_style["bottom_pct"]
    if cap_bottom_pct is None:
        cap_bottom_pct = max(sz.bottom_pct, 0.285) if is_portrait else max(sz.bottom_pct, 0.095)
    cap_margin_v = round(height * cap_bottom_pct)
    cap_font_px = cap_style["font_px"]
    cap_color = _hex_to_ass_color(
        str(cap_merged.get("fg_color") or "#F4F1EA"), cap_style["opacity"]
    )
    shadow_color = _hex_to_ass_color("#000000", cap_style["shadow_opacity"])
    outline_color = _hex_to_ass_color("#03161F", 0.88)

    wm_ov = next((o for o in overlays if o.template_id == "broadcast_bug"), None)
    wm_merged = {**(wm_ov.variables or {}), **(wm_ov.props or {})} if wm_ov else {}
    wm_font = _primary_font_name(wm_merged.get("font_family"), cap_font)
    wm_opacity = float(wm_merged.get("opacity", 0.72))
    wm_color = _hex_to_ass_color(str(wm_merged.get("fg_color") or "#F4F1EA"), wm_opacity)
    wm_shadow = _hex_to_ass_color("#000000", 0.65)

    credit_ov = next((o for o in overlays if o.template_id == "source_credit"), None)
    cr_merged = {**(credit_ov.variables or {}), **(credit_ov.props or {})} if credit_ov else {}
    cr_opacity = float(cr_merged.get("opacity", 0.62))
    cr_color = _hex_to_ass_color(str(cr_merged.get("fg_color") or "#F4F1EA"), cr_opacity)

    outline_w = (
        cap_style["outline_px"] if cap_style["outline_px"] is not None else round(2.6 * scale, 2)
    )
    shadow_d = (
        cap_style["shadow_px"] if cap_style["shadow_px"] is not None else round(2.4 * scale, 2)
    )
    cap_bold = -1 if cap_style["bold"] else 0
    soft_shadow = cap_style["shadow_blur_px"] > 0
    soft_shadow_px = shadow_d
    soft_shadow_alpha = f"&H{round((1.0 - cap_style['shadow_opacity']) * 255):02X}&"
    if soft_shadow:
        shadow_d = 0
    cap_spacing = cap_style["letter_spacing"]

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: CaptionLower,{cap_font},{cap_font_px},{cap_color},{cap_color},"
            f"{outline_color},{shadow_color},{cap_bold},0,0,0,100,100,{cap_spacing},0,1,"
            f"{outline_w},{shadow_d},"
            f"2,{sym_x_px},{sym_x_px},{cap_margin_v},1"
        ),
        (
            f"Style: CaptionCenter,{cap_font},{cap_font_px},{cap_color},{cap_color},"
            f"{outline_color},{shadow_color},{cap_bold},0,0,0,100,100,{cap_spacing},0,1,"
            f"{outline_w},{shadow_d},"
            f"5,{sym_x_px},{sym_x_px},0,1"
        ),
        (
            f"Style: CaptionUpper,{cap_font},{cap_font_px},{cap_color},{cap_color},"
            f"{outline_color},{shadow_color},{cap_bold},0,0,0,100,100,{cap_spacing},0,1,"
            f"{outline_w},{shadow_d},"
            f"8,{sym_x_px},{sym_x_px},{upper_margin_v},1"
        ),
        (
            f"Style: Watermark,{wm_font},{wm_font_px},{wm_color},{wm_color},"
            f"{wm_shadow},{wm_shadow},1,0,0,0,100,100,2.2,0,1,0.8,1.5,"
            f"9,{sym_x_px},{wm_margin_r},{wm_margin_v},1"
        ),
        (
            f"Style: SourceCredit,{cap_font},{credit_font_px},{cr_color},{cr_color},"
            f"{wm_shadow},{wm_shadow},0,0,0,0,100,100,0.4,0,1,0.8,1.2,"
            f"7,{credit_margin_l},{sym_x_px},{upper_margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for ov in sorted(overlays, key=lambda item: item.timeline_start_s):
        merged = {**(ov.variables or {}), **(ov.props or {})}
        start_ts = _format_ass_time(ov.timeline_start_s)
        end_ts = _format_ass_time(ov.timeline_start_s + ov.timeline_duration_s)

        if ov.template_id == "broadcast_bug":
            text = _escape_ass_text(str(merged.get("text") or "geoverum"))
            lines.append(
                f"Dialogue: 2,{start_ts},{end_ts},Watermark,,0,0,0,,{{\\fad(180,140)}}{text}"
            )
            continue

        if ov.template_id == "source_credit":
            text = _escape_ass_text(str(merged.get("text") or ""))
            if text:
                lines.append(
                    f"Dialogue: 2,{start_ts},{end_ts},SourceCredit,,0,0,0,,{{\\fad(160,120)}}{text}"
                )
            continue

        raw_text = str(merged.get("text") or merged.get("headline") or "").strip()
        if not raw_text:
            continue
        style_name = "CaptionLower"
        if ov.safe_band == "center_safe":
            style_name = "CaptionCenter"
        elif ov.safe_band == "upper_safe":
            style_name = "CaptionUpper"
        trans_ms = max(0, min(200, int(merged.get("caption_transition_ms", 120))))
        fade_in_ms = max(0, min(200, int(merged.get("caption_fade_in_ms", trans_ms))))
        fade_out_ms = max(0, min(200, int(merged.get("caption_fade_out_ms", trans_ms))))
        fade = (
            f"\\fad({fade_in_ms},{fade_out_ms})" if (fade_in_ms or fade_out_ms) else ""
        )
        fade_tag = f"{{{fade}}}" if fade else ""
        escaped_text = _escape_ass_text(raw_text)
        if cap_style["glow_color"] and cap_style["glow_px"] > 0:
            gc = cap_style["glow_color"]
            bgr = f"&H{gc[5:7]}{gc[3:5]}{gc[1:3]}&"
            glow_tags = (
                f"{{{fade}\\1c{bgr}\\1a&H55&\\3c{bgr}\\3a&H66&"
                f"\\bord{max(2.0, cap_style['glow_px'] * 0.45):g}\\shad0"
                f"\\blur{cap_style['glow_px']:g}}}"
            )
            lines.append(
                f"Dialogue: 0,{start_ts},{end_ts},{style_name},,0,0,0,,{glow_tags}{escaped_text}"
            )
        elif soft_shadow:
            # Soft drop shadow: a blurred dark copy on a lower layer, offset by the shadow distance.
            dx = round(soft_shadow_px)
            margin_v = {"CaptionLower": cap_margin_v, "CaptionUpper": upper_margin_v}.get(
                style_name, 0
            )
            shadow_margin_v = margin_v - dx if style_name == "CaptionLower" else margin_v + dx
            shadow_tags = (
                f"{{{fade}\\1c&H000000&\\1a{soft_shadow_alpha}\\bord0\\shad0"
                f"\\blur{cap_style['shadow_blur_px']:g}}}"
            )
            lines.append(
                f"Dialogue: 0,{start_ts},{end_ts},{style_name},,{sym_x_px + 2 * dx},{sym_x_px},"
                f"{max(shadow_margin_v, 0)},,{shadow_tags}{escaped_text}"
            )
        lines.append(
            f"Dialogue: 1,{start_ts},{end_ts},{style_name},,0,0,0,,{fade_tag}{escaped_text}"
        )

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    output_ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_ass_path


def escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a filesystem path for single-quoted FFmpeg `ass`/`subtitles` filter options."""
    raw = str(path.resolve())
    return raw.replace("\\", r"\\\\").replace(":", r"\:").replace("'", r"'\\\''")
