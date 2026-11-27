"""Native FFmpeg libass generator for plain captions, text watermarks, and source credits.

Routing static/plain documentary text overlays through FFmpeg's libass renderer avoids
headless Chromium + ProRes 4444 RGBA rendering for frames that require zero DOM animation.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from vedit.models import EditPlan, OverlayCompositionOp, PlatformTarget

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _merge_overlay_props(ov: OverlayCompositionOp | None) -> dict[str, Any]:
    if ov is None:
        return {}
    return {
        **(ov.props or {}),
        **{k: v for k, v in (ov.variables or {}).items() if v is not None},
    }


def is_ass_fastpath_overlay(ov: OverlayCompositionOp) -> bool:
    """Return True when an overlay can render natively via FFmpeg libass without Chromium."""
    props = ov.props or {}
    if props.get("custom_html") or props.get("custom_css") or props.get("custom_timeline_js"):
        return False

    merged = _merge_overlay_props(ov)
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


def _primary_font_name(raw_family: Any, default: str = "Rubik") -> str:
    if not isinstance(raw_family, str) or not raw_family.strip():
        return default
    return raw_family.split(",")[0].strip().strip("'\"") or default


def _caption_style(
    merged: dict[str, Any], *, width: int, height: int, is_portrait: bool
) -> dict[str, Any]:
    """Resolve caption typography from overlay props, defaulting to the engine house style.

    Supported props (all optional): `caption_font_px`, `caption_bottom_pct`,
    `caption_bold`, `caption_opacity`, `caption_outline_px`, `caption_shadow_px`,
    `caption_shadow_opacity`, `caption_shadow_blur_px`, `caption_letter_spacing`,
    `caption_letter_spacing_em`.
    """

    def _num(key: str) -> float | None:
        raw = merged.get(key)
        if raw is None or isinstance(raw, bool):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    scale = min(width, height) / 1080.0
    default_px = round(56 * scale) if is_portrait else round(46 * scale)
    font_px = _num("caption_font_px")
    resolved_font_px = round(font_px) if font_px and font_px > 0 else default_px
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
    if spacing is None:
        spacing_em = _num("caption_letter_spacing_em")
        if spacing_em is not None:
            spacing = round(spacing_em * resolved_font_px, 2)
    outline_blur = _num("caption_outline_blur_px")
    gap_ms = _num("caption_gap_ms")
    bold_raw = merged.get("caption_bold", True)
    norm_bottom = (
        (bottom_pct / 100.0) if (bottom_pct is not None and bottom_pct > 1.0) else bottom_pct
    )
    return {
        "font_px": resolved_font_px,
        "bottom_pct": min(max(norm_bottom, 0.0), 0.9) if norm_bottom is not None else None,
        "bold": bool(bold_raw),
        "opacity": min(max(opacity, 0.0), 1.0) if opacity is not None else 1.0,
        "outline_px": max(_num("caption_outline_px") or 0.0, 0.0)
        if _num("caption_outline_px") is not None
        else None,
        "outline_blur_px": max(outline_blur, 0.0) if outline_blur is not None else 0.0,
        "shadow_px": max(_num("caption_shadow_px") or 0.0, 0.0)
        if _num("caption_shadow_px") is not None
        else None,
        "shadow_opacity": min(max(shadow_opacity, 0.0), 1.0)
        if shadow_opacity is not None
        else 0.88,
        "shadow_blur_px": max(blur, 0.0) if blur is not None else 0.0,
        "glow_color": glow_color,
        "glow_px": max(glow_px, 0.0) if glow_px is not None else 0.0,
        "letter_spacing": spacing if spacing is not None else 0.3,
        "gap_ms": max(0, min(250, round(gap_ms))) if gap_ms is not None else 0,
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
    # Unified caption scale matches HyperFrames CSS and build_ass_from_transcript:
    # 56px @ 1080x1920 portrait and 46px @ 1920x1080 landscape.
    wm_font_px = max(18, round(24 * scale))
    wm_margin_v = round(height * (0.16 if is_portrait else 0.075))
    wm_margin_r = round(width * (0.055 if is_portrait else 0.05))
    credit_margin_l = round(width * sz.left_pct)

    first_cap = next((o for o in overlays if o.kind == "caption_rail"), None)
    cap_merged = _merge_overlay_props(first_cap)
    cap_font = _primary_font_name(
        cap_merged.get("caption_font_family") or cap_merged.get("font_family"), "Rubik"
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
    wm_merged = _merge_overlay_props(wm_ov)
    wm_font = _primary_font_name(wm_merged.get("font_family"), "Inter")
    wm_opacity = float(wm_merged.get("opacity", 0.72))
    wm_color = _hex_to_ass_color(str(wm_merged.get("fg_color") or "#F4F1EA"), wm_opacity)
    wm_shadow = _hex_to_ass_color("#000000", 0.65)

    credit_ov = next((o for o in overlays if o.template_id == "source_credit"), None)
    cr_merged = _merge_overlay_props(credit_ov)
    cr_opacity = float(cr_merged.get("opacity", 0.78))
    cr_color = _hex_to_ass_color(str(cr_merged.get("fg_color") or "#F4F1EA"), cr_opacity)
    cr_font_px = max(14, round(float(cr_merged.get("font_size_px") or (22 * scale))))

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
        "WrapStyle: 0",
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
            f"{wm_shadow},{wm_shadow},-1,0,0,0,100,100,2.2,0,1,0.8,1.5,"
            f"9,{sym_x_px},{wm_margin_r},{wm_margin_v},1"
        ),
        (
            f"Style: SourceCredit,{cap_font},{cr_font_px},{cr_color},{cr_color},"
            f"{outline_color},{wm_shadow},-1,0,0,0,100,100,0.4,0,1,1.6,1.8,"
            f"7,{credit_margin_l},{sym_x_px},{upper_margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    sorted_overlays = sorted(overlays, key=lambda item: item.timeline_start_s)
    caption_starts: list[tuple[str, float]] = [
        (item.overlay_id, item.timeline_start_s)
        for item in sorted_overlays
        if item.kind == "caption_rail"
    ]
    next_caption_start: dict[str, float] = {}
    for idx in range(len(caption_starts) - 1):
        next_caption_start[caption_starts[idx][0]] = caption_starts[idx + 1][1]

    for ov in sorted_overlays:
        merged = _merge_overlay_props(ov)
        end_s = ov.timeline_start_s + ov.timeline_duration_s
        if ov.kind == "caption_rail" and cap_style["gap_ms"] > 0:
            raw_out_check = merged.get("caption_fade_out_ms")
            if raw_out_check == 0 and ov.overlay_id in next_caption_start:
                nxt_start = next_caption_start[ov.overlay_id]
                gap_s = cap_style["gap_ms"] / 1000.0
                if nxt_start - end_s < gap_s and (nxt_start - gap_s) >= ov.timeline_start_s + 0.2:
                    end_s = nxt_start - gap_s
        start_ts = _format_ass_time(ov.timeline_start_s)
        end_ts = _format_ass_time(end_s)

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
        raw_trans = merged.get("caption_transition_ms")
        trans_ms = max(0, min(200, int(120 if raw_trans is None else raw_trans)))
        raw_in = merged.get("caption_fade_in_ms")
        raw_out = merged.get("caption_fade_out_ms")
        fade_in_ms = max(0, min(200, int(trans_ms if raw_in is None else raw_in)))
        fade_out_ms = max(0, min(200, int(trans_ms if raw_out is None else raw_out)))
        fade = (
            f"\\fad({fade_in_ms},{fade_out_ms})" if (fade_in_ms or fade_out_ms) else ""
        )
        outline_blur_tag = (
            f"\\blur{cap_style['outline_blur_px']:g}"
            if cap_style["outline_blur_px"] > 0
            else ""
        )
        main_tags = f"{fade}{outline_blur_tag}"
        fade_tag = f"{{{main_tags}}}" if main_tags else ""
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


def _chunk_words_by_pause_and_rate(
    words: list[dict[str, Any]],
    *,
    max_words: int = 4,
    pause_threshold_s: float = 0.18,
) -> list[dict[str, Any]]:
    """Group word timestamps into balanced phrase segments respecting speech pauses and rate."""
    clean = [w for w in words if str(w.get("word") or w.get("text") or "").strip()]
    if not clean:
        return []
    out: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []
    for word in clean:
        txt = str(word.get("word") or word.get("text") or "").strip()
        w_start = float(word.get("start", word.get("start_s", 0.0)))
        w_end = float(word.get("end", word.get("end_s", w_start + 0.18)))
        if buf:
            prev_end = float(buf[-1].get("end", buf[-1].get("end_s", w_start)))
            prev_txt = str(buf[-1].get("word") or buf[-1].get("text") or "").strip()
            buf_start = float(buf[0].get("start", buf[0].get("start_s", prev_end)))
            buf_span = max(0.15, prev_end - buf_start)
            rate_wps = len(buf) / buf_span
            # Adaptive word cap under rapid speech keeps CPS within comfortable mobile range.
            eff_cap = max_words
            if rate_wps > 3.6 and max_words > 2:
                eff_cap = max(2, max_words - 2)
            elif rate_wps > 2.8 and max_words > 3:
                eff_cap = max(3, max_words - 1)
            gap = w_start - prev_end
            ends_clause = prev_txt.endswith((".", "!", "?", ";", ":", ","))
            if len(buf) >= eff_cap or gap >= pause_threshold_s or ends_clause:
                out.append(
                    {
                        "start": buf_start,
                        "end": prev_end,
                        "text": " ".join(
                            str(x.get("word") or x.get("text") or "").strip() for x in buf
                        ),
                    }
                )
                buf = []
        buf.append({"word": txt, "start": w_start, "end": w_end})
    if buf:
        out.append(
            {
                "start": float(buf[0]["start"]),
                "end": float(buf[-1]["end"]),
                "text": " ".join(str(x["word"]) for x in buf),
            }
        )
    return out


def build_ass_from_transcript(
    transcript_data: dict[str, Any] | list[dict[str, Any]],
    *,
    width: int = 1080,
    height: int = 1920,
    speed: float = 1.0,
    max_words: int = 4,
    font_size: int | None = None,
    margin_v: int | None = None,
    fade_in_ms: int = 130,
    fade_out_ms: int = 0,
    gap_ms: int = 67,
    font_name: str = "Rubik",
    fg_color: str = "#F4F1EA",
    outline_color: str = "#03161F",
    outline_opacity: float = 0.88,
    outline_px: float | None = None,
    shadow_px: float | None = None,
    shadow_opacity: float = 0.88,
    letter_spacing: float = 0.3,
    blur_px: float = 0.8,
) -> str:
    """Generate a broadcast-calibrated ASS script from transcript segments or word timestamps.

    Shared single-source ASS generator used by both mastering and CLI caption builders so
    outline opacity, safe margins, balanced wrapping, perceptual inter-cue gaps, and 9:16 vs
    16:9 scaling stay identical across every pipeline entry point.
    """
    if speed <= 0:
        raise ValueError("speed must be > 0")
    is_portrait = height > width
    scale = min(width, height) / 1080.0
    eff_font_px = (
        int(font_size)
        if font_size is not None
        else (round(56 * scale) if is_portrait else round(46 * scale))
    )
    eff_margin_v = (
        int(margin_v)
        if margin_v is not None
        else (round(348 * (height / 1920.0)) if is_portrait else round(height * 0.095))
    )
    eff_margin_x = round(width * (0.078 if is_portrait else 0.125))
    eff_outline = round(outline_px if outline_px is not None else 2.4 * scale, 2)
    eff_shadow = round(shadow_px if shadow_px is not None else 2.4 * scale, 2)
    fade_in = max(0, min(200, int(fade_in_ms)))
    fade_out = max(0, min(200, int(fade_out_ms)))
    eff_gap_s = max(0, min(250, int(gap_ms))) / 1000.0
    primary_ass = _hex_to_ass_color(fg_color, 1.0)
    outline_ass = _hex_to_ass_color(outline_color, outline_opacity)
    shadow_ass = _hex_to_ass_color("#000000", shadow_opacity)

    tag_parts: list[str] = []
    if fade_in or fade_out:
        tag_parts.append(f"\\fad({fade_in},{fade_out})")
    if blur_px > 0:
        tag_parts.append(f"\\blur{blur_px:g}")
    tag_prefix = f"{{{''.join(tag_parts)}}}" if tag_parts else ""

    if isinstance(transcript_data, list):
        segments = transcript_data
    else:
        segments = list(transcript_data.get("segments") or [])
        if not segments and isinstance(transcript_data.get("words"), list):
            segments = _chunk_words_by_pause_and_rate(
                list(transcript_data["words"]), max_words=max_words
            )

    cues: list[tuple[float, float, str]] = []
    for seg in segments:
        t0 = float(seg.get("start", seg.get("start_s", 0.0))) / speed
        t1 = float(seg.get("end", seg.get("end_s", t0 + 0.5))) / speed
        raw_text = " ".join(str(seg.get("text") or "").split())
        if not raw_text or t1 <= t0:
            continue
        words = raw_text.split()
        if len(words) <= max_words:
            chunks = [words]
        else:
            n_chunks = math.ceil(len(words) / max_words)
            base = len(words) // n_chunks
            rem = len(words) % n_chunks
            chunks = []
            pos = 0
            for ci in range(n_chunks):
                take = base + (1 if ci < rem else 0)
                chunks.append(words[pos : pos + take])
                pos += take
        total_chars = max(1, sum(len(" ".join(c)) for c in chunks))
        cur_t = t0
        for ci, chunk in enumerate(chunks):
            txt = " ".join(chunk)
            if txt.endswith((",", ".")):
                txt = txt[:-1]
            dur_c = (t1 - t0) * (len(txt) / total_chars)
            end_t = t1 if ci == len(chunks) - 1 else min(t1, cur_t + max(0.18, dur_c))
            cues.append((cur_t, end_t, txt))
            cur_t = end_t

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{_primary_font_name(font_name, 'Rubik')},{eff_font_px},{primary_ass},"
        f"{primary_ass},{outline_ass},{shadow_ass},-1,0,0,0,100,100,{letter_spacing:g},0,1,"
        f"{eff_outline:g},{eff_shadow:g},2,{eff_margin_x},{eff_margin_x},{eff_margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for idx, (c_start, c_end, txt) in enumerate(cues):
        adj_end = c_end
        if eff_gap_s > 0 and fade_out == 0 and idx + 1 < len(cues):
            nxt_start = cues[idx + 1][0]
            if nxt_start - adj_end < eff_gap_s and (nxt_start - eff_gap_s) >= c_start + 0.18:
                adj_end = nxt_start - eff_gap_s
        lines.append(
            f"Dialogue: 0,{_format_ass_time(c_start)},{_format_ass_time(adj_end)},"
            f"Default,,0,0,0,,{tag_prefix}{_escape_ass_text(txt)}"
        )
    return "\n".join(lines) + "\n"


_ASS_TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")
_ASS_TAG_STRIP_RE = re.compile(r"\{[^}]*\}")


def _parse_ass_time(ts: str) -> float | None:
    m = _ASS_TIME_RE.match(ts.strip())
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 100.0


def validate_ass_captions_readability(
    ass_text: str,
    *,
    max_cps: float = 20.0,
    min_multiword_dur_s: float = 0.65,
) -> list[str]:
    """Audit generated ASS captions for reading speed (CPS), brief flashes, and overlaps."""
    warnings: list[str] = []
    parsed: list[tuple[float, float, str]] = []
    for line in ass_text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        style = parts[3].strip()
        if style in {"Watermark", "SourceCredit"}:
            continue
        t0 = _parse_ass_time(parts[1])
        t1 = _parse_ass_time(parts[2])
        if t0 is None or t1 is None or t1 <= t0:
            continue
        visible = _ASS_TAG_STRIP_RE.sub("", parts[9]).replace(r"\N", " ").strip()
        if not visible:
            continue
        parsed.append((t0, t1, visible))
    parsed.sort(key=lambda item: item[0])
    for idx, (t0, t1, txt) in enumerate(parsed):
        dur = t1 - t0
        cps = len(txt) / max(dur, 0.01)
        words = txt.split()
        if len(txt) >= 10 and cps > max_cps:
            warnings.append(
                f"Caption {t0:.2f}-{t1:.2f}s '{txt}' runs at {cps:.1f} cps (> {max_cps:g} cps)."
            )
        if len(words) >= 4 and dur < min_multiword_dur_s:
            warnings.append(
                f"Caption {t0:.2f}-{t1:.2f}s '{txt}' lasts {dur:.2f}s "
                f"(< {min_multiword_dur_s:.2f}s)."
            )
        if idx + 1 < len(parsed):
            nxt_t0 = parsed[idx + 1][0]
            if nxt_t0 < t1 - 0.005:
                warnings.append(
                    f"Caption {t0:.2f}-{t1:.2f}s overlaps next cue starting at {nxt_t0:.2f}s."
                )
    return warnings


def escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a filesystem path for single-quoted FFmpeg `ass`/`subtitles` filter options."""
    raw = str(path.resolve())
    return raw.replace("\\", r"\\\\").replace(":", r"\:").replace("'", r"'\\\''")
