"""Policy-driven boxless bottom-band ASS subtitle builders for scene timelines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from vedit.contracts import find_repo_root


def _fmt_ass_time(sec: float) -> str:
    total_cs = max(0, round(sec * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_geo_ass_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\\", "\\\u2060").replace("{", r"\{").replace("}", r"\}")
    return cleaned.replace("\n", r"\N")



def _segments_from_words(words: list[dict[str, Any]], max_words: int = 8) -> list[dict[str, Any]]:
    if not words:
        return []
    out: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []
    group_limit = max(4, min(10, max_words * 2))
    for w in words:
        txt = str(w.get("text") or "").strip()
        if not txt:
            continue
        t0 = float(w.get("start_s", w.get("start", 0.0)))
        if bucket:
            prev_end = float(bucket[-1].get("end_s", bucket[-1].get("end", t0)))
            if t0 - prev_end >= 0.35 or len(bucket) >= group_limit:
                out.append(
                    {
                        "start": float(bucket[0].get("start_s", bucket[0].get("start", 0.0))),
                        "end": prev_end,
                        "text": " ".join(str(x.get("text") or "").strip() for x in bucket),
                    }
                )
                bucket = []
        bucket.append(w)
        if txt.endswith((".", "?", "!", ",")) and len(bucket) >= max(2, max_words):
            out.append(
                {
                    "start": float(bucket[0].get("start_s", bucket[0].get("start", 0.0))),
                    "end": float(w.get("end_s", w.get("end", t0 + 0.2))),
                    "text": " ".join(str(x.get("text") or "").strip() for x in bucket),
                }
            )
            bucket = []
    if bucket:
        out.append(
            {
                "start": float(bucket[0].get("start_s", bucket[0].get("start", 0.0))),
                "end": float(bucket[-1].get("end_s", bucket[-1].get("end", 0.0))),
                "text": " ".join(str(x.get("text") or "").strip() for x in bucket),
            }
        )
    return out



def build_brand_ass_captions(
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
    font_name: str = "Inter",
    fg_color: str = "#F4F1EA",
    outline_color: str = "#03161F",
    outline_px: float | None = 0.55,
    shadow_px: float | None = 2.2,
    letter_spacing: float = 0.25,
    blur_px: float = 1.1,
) -> str:
    """Build calibrated boxless bottom-band ASS subtitles via the shared mastering ASS engine."""
    from vedit.mastering.ass_captions import build_ass_from_transcript

    return build_ass_from_transcript(
        transcript_data,
        width=width,
        height=height,
        speed=speed,
        max_words=max_words,
        font_size=font_size,
        margin_v=margin_v,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        gap_ms=gap_ms,
        font_name=font_name,
        fg_color=fg_color,
        outline_color=outline_color,
        outline_px=outline_px,
        shadow_px=shadow_px,
        letter_spacing=letter_spacing,
        blur_px=blur_px,
    )


def build_geoverum_ass_captions(
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
    font_name: str = "Inter",
    fg_color: str = "#F4F1EA",
    outline_color: str = "#03161F",
    outline_px: float | None = 0.55,
    shadow_px: float | None = 2.2,
    letter_spacing: float = 0.25,
    blur_px: float = 1.1,
) -> str:
    """Backward-compatible alias delegating to `build_brand_ass_captions`."""
    return build_brand_ass_captions(
        transcript_data,
        width=width,
        height=height,
        speed=speed,
        max_words=max_words,
        font_size=font_size,
        margin_v=margin_v,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        gap_ms=gap_ms,
        font_name=font_name,
        fg_color=fg_color,
        outline_color=outline_color,
        outline_px=outline_px,
        shadow_px=shadow_px,
        letter_spacing=letter_spacing,
        blur_px=blur_px,
    )


def build_captions_for_brand(
    transcript_file: Path,
    out_file: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    speed: float = 1.0,
    max_words: int | None = None,
    font_size: int | None = None,
    margin_v: int | None = None,
    fade_in_ms: int | None = None,
    fade_out_ms: int | None = None,
    gap_ms: int | None = None,
    brand: str | None = None,
    outline_px: float | None = None,
    shadow_px: float | None = None,
    blur_px: float | None = None,
) -> None:
    """Generate boxless bottom-band ASS subtitles using optional brand policy defaults."""
    from vedit.mastering.ass_captions import validate_ass_captions_readability

    is_portrait = height > width
    scale = min(width, height) / 1080.0
    eff_max_words = 4
    eff_font_size: int | None = round(46 * scale) if is_portrait else round(42 * scale)
    eff_margin_v: int | None = round(525 * (height / 1920.0)) if is_portrait else None
    eff_fade_in = 110
    eff_fade_out = 0
    eff_gap_ms = 67
    eff_font = "Inter"
    eff_fg = "#F5F7FA"
    eff_outline = "#071D26"
    eff_letter_spacing = -0.01 * eff_font_size
    if brand:
        try:
            policy_path = (
                find_repo_root() / "profiles" / "brands" / brand / "brand_style_policy.json"
            )
            if policy_path.is_file():
                pol = json.loads(policy_path.read_text(encoding="utf-8"))
                vtok = (pol.get("soft_priors") or {}).get("visual_tokens") or {}
                typo = vtok.get("typography") or {}
                pal = vtok.get("palette_roles") or {}
                eff_max_words = int(typo.get("max_words_per_caption_group", eff_max_words))
                if is_portrait:
                    raw_px = int(typo.get("caption_font_px_9x16", 46))
                    raw_mv = int(typo.get("caption_margin_v_px_9x16", 525))
                    eff_font_size = max(16, round(raw_px * scale))
                    eff_margin_v = round(raw_mv * (height / 1920.0))
                else:
                    cap_step = (typo.get("type_scale") or {}).get("caption") or {}
                    if cap_step.get("size_px_16x9") is not None:
                        eff_font_size = max(16, round(int(cap_step["size_px_16x9"]) * scale))
                if typo.get("caption_fade_in_ms") is not None:
                    eff_fade_in = int(typo["caption_fade_in_ms"])
                if typo.get("caption_fade_out_ms") is not None:
                    eff_fade_out = int(typo["caption_fade_out_ms"])
                if typo.get("caption_gap_ms") is not None:
                    eff_gap_ms = int(typo["caption_gap_ms"])
                if typo.get("caption_letter_spacing_em") is not None:
                    resolved_px = (
                        font_size
                        if font_size is not None
                        else (eff_font_size if eff_font_size is not None else round(46 * scale))
                    )
                    eff_letter_spacing = round(
                        float(typo["caption_letter_spacing_em"]) * resolved_px, 2
                    )
                raw_fam = typo.get("caption_font_family")
                if isinstance(raw_fam, str) and raw_fam.strip():
                    eff_font = raw_fam.split(",")[0].strip().strip("'\"") or eff_font
                if isinstance(pal.get("ink"), str):
                    eff_fg = pal["ink"]
                if isinstance(pal.get("ground"), str):
                    eff_outline = pal["ground"]
        except FileNotFoundError:
            pass

    data = json.loads(transcript_file.expanduser().resolve().read_text(encoding="utf-8"))
    ass_text = build_brand_ass_captions(
        data,
        width=width,
        height=height,
        speed=speed,
        max_words=max_words if max_words is not None else eff_max_words,
        font_size=font_size if font_size is not None else eff_font_size,
        margin_v=margin_v if margin_v is not None else eff_margin_v,
        fade_in_ms=fade_in_ms if fade_in_ms is not None else eff_fade_in,
        fade_out_ms=fade_out_ms if fade_out_ms is not None else eff_fade_out,
        gap_ms=gap_ms if gap_ms is not None else eff_gap_ms,
        font_name=eff_font,
        fg_color=eff_fg,
        outline_color=eff_outline,
        outline_px=outline_px if outline_px is not None else 0.55,
        shadow_px=shadow_px if shadow_px is not None else 2.2,
        letter_spacing=eff_letter_spacing,
        blur_px=blur_px if blur_px is not None else 1.1,
    )
    out = out_file.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ass_text, encoding="utf-8")
    readability_warnings = validate_ass_captions_readability(ass_text)
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "ass_path": str(out),
                "speed": speed,
                "width": width,
                "height": height,
                "readability_warnings": readability_warnings,
            },
            indent=2,
        )
    )
