"""Local forensic video breakdown adapter backed by `rea-video` CLI.

Strictly whitelists non-generative forensic analysis subcommands only.
Generative remake, avatar, and synthesis commands are intentionally excluded.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from vedit.contracts import find_repo_root, validate_against_contract
from vedit.metrics import compute_quantiles
from vedit.models import (
    BreakdownAudioMetrics,
    BreakdownEditingMetrics,
    BreakdownGradeMetrics,
    BreakdownPackagingMetrics,
    BreakdownShot,
    VideoBreakdownResult,
)
from vedit.ports.video_breakdown import (
    BreakdownOptions,
    BreakdownReviewBundle,
    BreakdownSurveyStep,
)

_ALLOWED_SUBCOMMANDS = frozenset(
    {"survey", "decompose", "review", "apply-review", "summary", "videomd", "tiles"}
)
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_TRANSITION_MAP: dict[str, Literal[
    "start", "cut", "jump", "fade", "dissolve", "wipe", "flash", "other"
]] = {
    "start": "start",
    "cut": "cut",
    "jump": "jump",
    "fade": "fade",
    "dissolve": "dissolve",
    "wipe": "wipe",
    "flash": "flash",
}
_NARRATIVE_ROLES = frozenset(
    {"hook", "context", "info", "proof", "turn", "payoff", "cta", "mood"}
)
_ANIM_DEFAULT_MS: dict[str, int] = {
    "cut": 0,
    "pop": 140,
    "fade": 180,
    "slide": 180,
    "reveal": 120,
}


def resolve_rea_video_binary(
    options: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> Path:
    """Locate the `rea-video` executable (config, env, isolated tools venv, or PATH)."""
    explicit = (options or {}).get("binary")
    if isinstance(explicit, str) and explicit.strip():
        cand = Path(explicit).expanduser()
        if cand.is_file():
            return cand
        raise FileNotFoundError(f"Configured rea-video binary not found: {cand}")

    env_bin = os.environ.get("VEDIT_REA_VIDEO_BIN", "").strip()
    if env_bin:
        cand = Path(env_bin).expanduser()
        if cand.is_file():
            return cand
        raise FileNotFoundError(f"VEDIT_REA_VIDEO_BIN points to missing binary: {cand}")

    root = repo_root or find_repo_root()
    isolated = root / "tools" / "rea-video" / ".venv" / "bin" / "rea-video"
    if isolated.is_file():
        return isolated

    on_path = shutil.which("rea-video")
    if on_path:
        return Path(on_path)

    raise FileNotFoundError(
        "Local `rea-video` binary not found. Install the isolated toolchain with: "
        "`bash tools/rea-video/setup.sh`"
    )


def _normalize_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    if _HEX_RE.match(clean):
        return clean.upper()
    return None


def _canonical_aspect_ratio(
    width: int, height: int
) -> Literal["16:9", "9:16", "1:1", "4:5", "other"]:
    if width <= 0 or height <= 0:
        return "other"
    ratio = width / height
    candidates: list[tuple[float, Literal["16:9", "9:16", "1:1", "4:5"]]] = [
        (16.0 / 9.0, "16:9"),
        (9.0 / 16.0, "9:16"),
        (1.0, "1:1"),
        (4.0 / 5.0, "4:5"),
    ]
    best_dist, best_label = min((abs(ratio - target), label) for target, label in candidates)
    return best_label if best_dist <= 0.12 else "other"


def _classify_caption_case(
    texts: list[str],
) -> Literal["sentence", "uppercase", "title", "lowercase"] | None:
    votes: Counter[Literal["sentence", "uppercase", "title", "lowercase"]] = Counter()
    for raw in texts:
        words = [
            w
            for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", raw)
            if any(c.isalpha() for c in w)
        ]
        if not words:
            continue
        alpha_chars = "".join(c for c in raw if c.isalpha())
        if not alpha_chars:
            continue
        if alpha_chars.isupper():
            votes["uppercase"] += 1
        elif alpha_chars.islower():
            votes["lowercase"] += 1
        elif len(words) >= 2 and sum(1 for w in words if w[0].isupper()) >= max(
            2, int(len(words) * 0.75)
        ):
            votes["title"] += 1
        else:
            votes["sentence"] += 1
    if not votes:
        return None
    return votes.most_common(1)[0][0]


def _word_count(text: str) -> int:
    clean = text.strip()
    if not clean:
        return 0
    tokens = clean.split()
    if len(tokens) > 1:
        return len(tokens)
    # Handle CJK/no-space lines approximately by non-punctuation character groups.
    cjk_chars = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", clean)
    if cjk_chars:
        return max(1, round(len(cjk_chars) / 2.5))
    return 1


def _extract_drawn_hex(shot: dict[str, Any]) -> list[str]:
    motion = shot.get("motion")
    if not isinstance(motion, dict):
        return []
    colors: list[str] = []
    drawn = motion.get("drawn")
    if isinstance(drawn, dict):
        for entry in drawn.get("colours") or drawn.get("colors") or []:
            if isinstance(entry, dict):
                hx = _normalize_hex(entry.get("hex"))
                if hx and hx not in colors:
                    colors.append(hx)
            elif isinstance(entry, str):
                hx = _normalize_hex(entry)
                if hx and hx not in colors:
                    colors.append(hx)
    elif isinstance(drawn, list):
        for entry in drawn:
            hx = _normalize_hex(entry.get("hex") if isinstance(entry, dict) else entry)
            if hx and hx not in colors:
                colors.append(hx)
    return colors[:8]


def _extract_tone(grade_raw: dict[str, Any]) -> Literal["warm", "cool", "neutral"] | None:
    words = grade_raw.get("words") or {}
    tone_str = str(words.get("tone") or "").strip().lower()
    if "warm" in tone_str or "暖" in tone_str:
        return "warm"
    if "cool" in tone_str or "冷" in tone_str:
        return "cool"
    if "neutral" in tone_str or "中性" in tone_str:
        return "neutral"
    measured = grade_raw.get("measured") or {}
    mean_b = measured.get("mean_b")
    if isinstance(mean_b, (int, float)):
        if mean_b > 12.0:
            return "warm"
        if mean_b < 2.0:
            return "cool"
        return "neutral"
    return None


def parse_rea_breakdown(
    raw: dict[str, Any],
    output_dir: Path | None = None,
    *,
    provider_name: str = "rea_video",
    repo_root: Path | None = None,
    validate_contract: bool = True,
) -> VideoBreakdownResult:
    """Normalize a raw `rea-video` breakdown dictionary into `VideoBreakdownResult`."""
    source = raw.get("source") or {}
    rotation = int(source.get("rotation") or 0)
    raw_w = int(source.get("width") or 0)
    raw_h = int(source.get("height") or 0)
    width, height = (raw_h, raw_w) if abs(rotation) % 360 in (90, 270) else (raw_w, raw_h)
    fps = float(source.get("fps") or 0.0)
    duration_s = float(source.get("duration") or (raw.get("summary") or {}).get("duration") or 0.0)
    source_path = str(source.get("path") or source.get("filename") or "unknown")
    sha_head = source.get("sha256_head") or source.get("sha256")
    source_sha256 = str(sha_head) if isinstance(sha_head, str) and len(sha_head) >= 8 else None

    summary = raw.get("summary") or {}
    raw_shots = raw.get("shots") or []

    # Production mix
    production_mix: dict[str, float] = {}
    for entry in summary.get("production_mix") or []:
        if isinstance(entry, dict) and entry.get("label"):
            ratio = float(entry.get("ratio") or 0.0)
            production_mix[str(entry["label"])] = round(min(max(ratio, 0.0), 1.0), 4)
    if not production_mix and raw_shots:
        total_shot_dur = sum(float(s.get("duration") or 0.0) for s in raw_shots) or 1.0
        acc: dict[str, float] = {}
        for s in raw_shots:
            lbl = str(((s.get("base") or {}).get("label")) or "unknown")
            acc[lbl] = acc.get(lbl, 0.0) + float(s.get("duration") or 0.0)
        production_mix = {
            k: round(min(max(v / total_shot_dur, 0.0), 1.0), 4) for k, v in acc.items()
        }

    # Shots
    shots: list[BreakdownShot] = []
    reviewers: list[str] = []
    for idx, s in enumerate(raw_shots):
        base = s.get("base") or {}
        review = s.get("review") or {}
        vlm = s.get("vlm") or {}
        narrative = s.get("narrative") or {}
        if not narrative and isinstance(review.get("narrative"), dict):
            narrative = review["narrative"]

        raw_index = s.get("index")
        shot_index = int(raw_index) - 1 if isinstance(raw_index, int) and raw_index >= 1 else idx
        start_s = max(0.0, float(s.get("start") or 0.0))
        end_s = max(start_s, float(s.get("end") or start_s))
        shot_dur = max(0.0, float(s.get("duration") or (end_s - start_s)))

        raw_trans = str(s.get("transition_in") or "cut").lower()
        transition_in = _TRANSITION_MAP.get(raw_trans, "other")
        trans_obj = s.get("transition") if isinstance(s.get("transition"), dict) else {}
        trans_dur = (
            float(trans_obj["duration"])
            if isinstance(trans_obj.get("duration"), (int, float))
            else None
        )

        label = str(base.get("label") or "unknown")
        conf = min(max(float(base.get("confidence") or 0.0), 0.0), 1.0)
        decided_by = str(base.get("decided_by") or "")
        if decided_by == "fused_agent" and "agent" not in reviewers:
            reviewers.append("agent")
        elif decided_by == "fused" and "vlm" not in reviewers:
            reviewers.append("vlm")
        elif decided_by == "user" and "user" not in reviewers:
            reviewers.append("user")

        rev_by = review.get("_by")
        if isinstance(rev_by, str) and rev_by.strip() and rev_by.strip() not in reviewers:
            reviewers.append(rev_by.strip())

        raw_role = str(narrative.get("role") or "").strip().lower()
        narrative_role = raw_role if raw_role in _NARRATIVE_ROLES else None
        raw_point = str(narrative.get("point") or "").strip() or None
        desc = (
            str(review.get("description") or "").strip()
            or str(vlm.get("description") or "").strip()
            or None
        )

        beats = [
            round(float(b), 3)
            for b in (s.get("beats") or [])
            if isinstance(b, (int, float)) and float(b) >= 0.0
        ]
        mat = s.get("material") or {}
        has_real = bool(mat.get("has_real_material"))
        low_conf = bool(base.get("uncertain") or base.get("disputed") or conf < 0.72)

        assets = s.get("assets") or {}
        sheet_rel = assets.get("sheet")
        sheet_path = (
            str((output_dir / sheet_rel).resolve())
            if output_dir is not None and isinstance(sheet_rel, str)
            else (str(sheet_rel) if isinstance(sheet_rel, str) else None)
        )

        shots.append(
            BreakdownShot(
                shot_index=shot_index,
                start_s=round(start_s, 3),
                end_s=round(end_s, 3),
                duration_s=round(shot_dur, 3),
                transition_in=transition_in,
                transition_duration_s=round(trans_dur, 3) if trans_dur is not None else None,
                production_label=label,
                production_confidence=round(conf, 3),
                narrative_role=narrative_role,  # type: ignore[arg-type]
                narrative_point=raw_point,
                description=desc,
                beats_s=beats,
                drawn_palette_hex=_extract_drawn_hex(s),
                has_embedded_real_assets=has_real,
                low_confidence_flag=low_conf,
                sheet_path=sheet_path,
            )
        )

    if not reviewers:
        reviewers.append("tool")

    # Editing aspects
    aspects_raw = raw.get("aspects") or {}
    editing_raw = aspects_raw.get("editing") or {}
    audio_raw = raw.get("audio") or {}
    shot_count = len(shots)
    fallback_cpm = (
        round((max(shot_count - 1, 0) / max(duration_s, 0.1)) * 60.0, 2) if shot_count else 0.0
    )
    fallback_avg = round(duration_s / max(shot_count, 1), 3) if shot_count else round(duration_s, 3)

    # Estimate punch-in scale ratios from consecutive filmed-shot framing measurements.
    punch_ratios: list[float] = []
    for prev_s, cur_s in zip(raw_shots, raw_shots[1:], strict=False):
        p_fr = ((prev_s.get("aspects") or {}).get("framing") or {}).get("measured") or {}
        c_fr = ((cur_s.get("aspects") or {}).get("framing") or {}).get("measured") or {}
        p_area = p_fr.get("area")
        c_area = c_fr.get("area")
        s0 = p_fr.get("face_h") or (
            float(p_area) ** 0.5 if isinstance(p_area, (int, float)) and p_area > 0 else None
        )
        s1 = c_fr.get("face_h") or (
            float(c_area) ** 0.5 if isinstance(c_area, (int, float)) and c_area > 0 else None
        )
        if s0 and s1 and min(s0, s1) > 0:
            ratio = max(s0, s1) / min(s0, s1)
            if 1.15 <= ratio <= 2.5:
                punch_ratios.append(round(float(ratio), 3))

    editing = BreakdownEditingMetrics(
        cuts_per_min=float(editing_raw.get("cuts_per_min") or fallback_cpm),
        avg_shot_s=float(
            editing_raw.get("avg_shot_s") or summary.get("avg_shot_s") or fallback_avg
        ),
        camera_positions=(
            int(editing_raw["positions"])
            if isinstance(editing_raw.get("positions"), int)
            else None
        ),
        jump_cuts=int(editing_raw.get("jump_cuts") or 0),
        punch_ins=int(editing_raw.get("punch_ins") or 0),
        punch_in_scale_ratios=punch_ratios[:12],
        cuts_in_pauses_ratio=(
            min(max(float(editing_raw["cuts_in_pauses"]), 0.0), 1.0)
            if isinstance(editing_raw.get("cuts_in_pauses"), (int, float))
            else None
        ),
        insert_share=(
            min(max(float(editing_raw["insert_share"]), 0.0), 1.0)
            if isinstance(editing_raw.get("insert_share"), (int, float))
            else None
        ),
        beat_synced_edit=bool(
            editing_raw.get("beat_synced") or audio_raw.get("beat_synced_edit")
        ),
    )

    # Packaging (OCR captions, styled text, watermarks, stickers)
    pack = raw.get("packaging") or {}
    all_cues = [
        c
        for c in (pack.get("text_cues") or [])
        if isinstance(c, dict) and not c.get("part_of_picture") and c.get("kind") != "scene"
    ]
    subtitle_cues = [c for c in all_cues if c.get("kind") == "subtitle"]
    styled_cues = [c for c in all_cues if c.get("kind") in ("huazi", "title", "label", "counter")]
    active_stickers = [
        st
        for st in (pack.get("stickers") or [])
        if isinstance(st, dict)
        and not st.get("in_picture")
        and st.get("confidence") != "low"
    ]

    sub_texts = [
        str(c.get("text") or "").strip()
        for c in subtitle_cues
        if str(c.get("text") or "").strip()
    ]
    word_counts = [float(_word_count(t)) for t in sub_texts if _word_count(t) > 0]
    words_p50 = words_p75 = None
    if word_counts:
        _, words_p50, words_p75 = compute_quantiles(word_counts)
        words_p50 = round(words_p50, 2)
        words_p75 = round(words_p75, 2)

    band_map: dict[str, Literal["lower_third", "center_safe", "upper_safe"]] = {
        "bottom": "lower_third",
        "middle": "center_safe",
        "top": "upper_safe",
    }
    band_votes: Counter[Literal["lower_third", "center_safe", "upper_safe"]] = Counter()
    style_votes: Counter[Literal["plain", "chip", "bar"]] = Counter()
    anim_votes: Counter[str] = Counter()
    anim_ms_samples: list[float] = []
    fill_votes: Counter[str] = Counter()
    stroke_votes: Counter[str] = Counter()
    box_votes: Counter[str] = Counter()

    for cue in subtitle_cues:
        b = band_map.get(str(cue.get("band") or "").lower())
        if b:
            band_votes[b] += 1
        st = cue.get("style") or {}
        if isinstance(st, dict):
            hx_fill = _normalize_hex(st.get("fill"))
            if hx_fill:
                fill_votes[hx_fill] += 1
            hx_stroke = _normalize_hex(st.get("stroke"))
            if hx_stroke:
                stroke_votes[hx_stroke] += 1
            hx_box = _normalize_hex(st.get("box_color"))
            if hx_box:
                box_votes[hx_box] += 1
            if st.get("box"):
                bbox = cue.get("bbox")
                is_wide_bar = isinstance(bbox, list) and len(bbox) == 4 and float(bbox[2]) >= 0.72
                style_votes["bar" if is_wide_bar else "chip"] += 1
            else:
                style_votes["plain"] += 1
        anim_in = cue.get("anim_in")
        if isinstance(anim_in, dict) and anim_in.get("kind"):
            akind = str(anim_in["kind"]).lower()
            anim_votes[akind] += 1
            if akind in _ANIM_DEFAULT_MS:
                anim_ms_samples.append(float(_ANIM_DEFAULT_MS[akind]))

    global_layers = raw.get("global_layers") or {}
    has_persistent_cue = any(bool(c.get("persistent")) for c in all_cues)
    has_persistent_template = bool(global_layers.get("boxes")) or float(
        global_layers.get("frozen_ratio") or 0.0
    ) >= 0.015

    packaging = BreakdownPackagingMetrics(
        subtitle_count=len(subtitle_cues),
        caption_case_observed=_classify_caption_case(sub_texts),
        caption_style_observed=style_votes.most_common(1)[0][0] if style_votes else None,
        caption_band_observed=band_votes.most_common(1)[0][0] if band_votes else None,
        caption_words_p50=words_p50,
        caption_words_p75=words_p75,
        caption_entrance_animations=[k for k, _ in anim_votes.most_common(4)],
        caption_entrance_ms_median=(
            int(round(compute_quantiles(anim_ms_samples)[1])) if anim_ms_samples else None
        ),
        caption_fill_hex=fill_votes.most_common(1)[0][0] if fill_votes else None,
        caption_stroke_hex=stroke_votes.most_common(1)[0][0] if stroke_votes else None,
        caption_box_hex=box_votes.most_common(1)[0][0] if box_votes else None,
        persistent_watermark_detected=bool(has_persistent_cue or has_persistent_template),
        styled_text_count=len(styled_cues),
        sticker_count=len(active_stickers),
        overlay_text_samples=sub_texts[:8],
    )

    # Audio
    voice_raw = audio_raw.get("voice") or {}
    music_raw = audio_raw.get("music") or {}
    audio_plan = raw.get("audio_plan") or {}
    sfx_merged = [
        e
        for e in (audio_plan.get("sfx_merged") or (audio_raw.get("sfx") or {}).get("events") or [])
        if isinstance(e, dict) and not e.get("in_scene")
    ]
    sfx_types_counter: Counter[str] = Counter(
        str(e.get("type")).strip().lower()
        for e in sfx_merged
        if isinstance(e.get("type"), str) and e.get("type").strip()
    )
    sfx_alignment = pack.get("sfx_alignment") or {}
    aligned_confirmed = sum(
        int(v) for v in (sfx_alignment.get("sfx_on") or {}).values() if isinstance(v, (int, float))
    )
    if aligned_confirmed == 0:
        aligned_confirmed = sum(1 for e in sfx_merged if isinstance(e.get("on"), dict) and e["on"])

    raw_bpm = music_raw.get("tempo_bpm") or audio_raw.get("tempo_bpm")
    tempo_bpm = (
        round(float(raw_bpm), 1)
        if isinstance(raw_bpm, (int, float)) and 20.0 <= float(raw_bpm) <= 260.0
        else None
    )
    raw_bs = music_raw.get("beat_strength")
    beat_strength = (
        round(min(max(float(raw_bs), 0.0), 1.0), 3) if isinstance(raw_bs, (int, float)) else None
    )
    key_raw = music_raw.get("key") if isinstance(music_raw.get("key"), dict) else {}
    raw_mode = str(key_raw.get("mode") or "").lower()
    key_mode: Literal["major", "minor"] | None = (
        raw_mode if raw_mode in ("major", "minor") else None  # type: ignore[assignment]
    )
    raw_vstyle = str(voice_raw.get("style") or "").lower()
    vocal_style: Literal["speech", "singing", "rap_or_rhythmic"] | None = (
        raw_vstyle
        if raw_vstyle in ("speech", "singing", "rap_or_rhythmic")
        else None  # type: ignore[assignment]
    )
    section_changes = [
        round(float(t), 2)
        for t in (music_raw.get("section_changes") or [])
        if isinstance(t, (int, float)) and float(t) >= 0.0
    ]

    has_music = bool(music_raw.get("present"))
    no_beat = bool(music_raw.get("no_beat")) or (not has_music) or (tempo_bpm is None)
    audio = BreakdownAudioMetrics(
        has_audio=bool(audio_raw.get("has_audio", source.get("has_audio", False))),
        has_voice=bool(voice_raw.get("present")),
        has_music=has_music,
        tempo_bpm=None if no_beat else tempo_bpm,
        beat_strength=beat_strength,
        no_beat=no_beat,
        key_tonic=str(key_raw["tonic"]) if isinstance(key_raw.get("tonic"), str) else None,
        key_mode=key_mode,
        vocal_style=vocal_style,
        sfx_count=len(sfx_merged),
        sfx_types=[k for k, _ in sfx_types_counter.most_common(6)],
        sfx_aligned_to_visual_count=int(aligned_confirmed),
        music_section_changes_s=section_changes[:20],
    )

    # Color grade
    grade_raw = aspects_raw.get("grade") or {}
    g_meas = grade_raw.get("measured") or {}
    g_res = grade_raw.get("result") or {}
    grade = BreakdownGradeMetrics(
        look=str(g_res.get("look")).strip() if g_res.get("look") else None,
        saturation=(
            round(min(max(float(g_meas["sat"]), 0.0), 1.0), 3)
            if isinstance(g_meas.get("sat"), (int, float))
            else None
        ),
        contrast=(
            round(min(max(float(g_meas["contrast"]), 0.0), 1.0), 3)
            if isinstance(g_meas.get("contrast"), (int, float))
            else None
        ),
        black_level=(
            round(min(max(float(g_meas["black"]), 0.0), 100.0), 2)
            if isinstance(g_meas.get("black"), (int, float))
            else None
        ),
        white_level=(
            round(min(max(float(g_meas["white"]), 0.0), 100.0), 2)
            if isinstance(g_meas.get("white"), (int, float))
            else None
        ),
        shadow_b=(
            round(float(g_meas["shadow_b"]), 2)
            if isinstance(g_meas.get("shadow_b"), (int, float))
            else None
        ),
        highlight_b=(
            round(float(g_meas["highlight_b"]), 2)
            if isinstance(g_meas.get("highlight_b"), (int, float))
            else None
        ),
        mean_l=(
            round(min(max(float(g_meas["mean_l"]), 0.0), 100.0), 2)
            if isinstance(g_meas.get("mean_l"), (int, float))
            else None
        ),
        tone=_extract_tone(grade_raw),
    )

    # Paths & warnings
    videomd_path: str | None = None
    storyboard_path: str | None = None
    out_dir_str: str | None = None
    if output_dir is not None:
        resolved_out = output_dir.resolve()
        out_dir_str = str(resolved_out)
        vmd = resolved_out / "VIDEO.md"
        if vmd.is_file():
            videomd_path = str(vmd)
        sb = resolved_out / "storyboard.jpg"
        if sb.is_file():
            storyboard_path = str(sb)

    gen_share = production_mix.get("ai_video", 0.0) + production_mix.get("avatar", 0.0)
    overall_conf = min(max(float(summary.get("confidence") or 0.7), 0.0), 1.0)

    result = VideoBreakdownResult(
        provider=provider_name,
        source_path=source_path,
        source_sha256=source_sha256,
        duration_s=round(duration_s, 3),
        width=width,
        height=height,
        fps=round(fps, 3),
        aspect_ratio=_canonical_aspect_ratio(width, height),
        output_dir=out_dir_str,
        videomd_path=videomd_path,
        storyboard_path=storyboard_path,
        confidence=round(overall_conf, 3),
        reviewed_by=reviewers,
        verdict=str(summary.get("verdict") or "").strip() or None,
        generative_reference_warning=gen_share >= 0.05,
        production_mix=production_mix,
        shots=shots,
        editing=editing,
        packaging=packaging,
        audio=audio,
        grade=grade,
    )

    if validate_contract:
        errors = validate_against_contract(
            result.model_dump(exclude_none=True),
            "video_breakdown.schema.json",
            repo_root=repo_root,
        )
        if errors:
            raise ValueError(f"Normalized VideoBreakdownResult failed contract check: {errors}")

    return result


class ReaVideoBreakdownProvider:
    """`VideoBreakdownPort` adapter invoking the isolated `rea-video` CLI."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._options = dict(options or {})

    @property
    def provider_name(self) -> str:
        return "rea_video"

    def _run_cli(
        self,
        subcommand: str,
        args: list[str],
        *,
        env_file: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if subcommand not in _ALLOWED_SUBCOMMANDS:
            raise ValueError(
                f"Subcommand {subcommand!r} is forbidden by forensic-only policy. "
                f"Allowed: {sorted(_ALLOWED_SUBCOMMANDS)}"
            )
        binary = resolve_rea_video_binary(self._options)
        cmd = [str(binary)]
        if env_file is not None:
            cmd.extend(["--env-file", str(env_file)])
        cmd.append(subcommand)
        cmd.extend(args)

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"rea-video {subcommand} failed ({proc.returncode}): {err}")
        return proc

    def survey(self, media_path: Path, output_dir: Path) -> BreakdownSurveyStep:
        """Run one step of the visual-first contact-sheet survey pass."""
        out = output_dir.expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        proc = self._run_cli(
            "survey",
            [str(media_path.expanduser().resolve()), "-o", str(out), "--no-vlm"],
        )
        payload = json.loads(proc.stdout)
        images = [Path(p) for p in (payload.get("images") or [])]
        waiting = [Path(p) for p in (payload.get("waiting") or [])]
        tl_raw = payload.get("timeline")
        timeline = Path(tl_raw) if isinstance(tl_raw, str) and tl_raw else None
        return BreakdownSurveyStep(
            output_dir=out,
            status=str(payload.get("status") or "unknown"),
            round_index=int(payload["round"]) if isinstance(payload.get("round"), int) else None,
            images=images,
            waiting_files=waiting,
            timeline_path=timeline,
        )

    def analyze(
        self,
        media_path: Path,
        output_dir: Path,
        options: BreakdownOptions | None = None,
    ) -> VideoBreakdownResult:
        """Run forensic breakdown and optionally prepare visual review artifacts."""
        opts = options or BreakdownOptions(
            use_vlm=bool(self._options.get("use_vlm", False)),
            prepare_review=bool(self._options.get("prepare_review", True)),
            ocr=bool(self._options.get("ocr", True)),
            stems=bool(self._options.get("stems", True)),
            packaging=bool(self._options.get("packaging", True)),
            asr=bool(self._options.get("asr", False)),
            lang=str(self._options.get("lang", "en")),  # type: ignore[arg-type]
            ocr_lang=self._options.get("ocr_lang"),
            workers=int(self._options.get("workers", 3)),
        )
        out = output_dir.expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)

        cli_args = [
            str(media_path.expanduser().resolve()),
            "-o",
            str(out),
            "--lang",
            opts.lang,
            "--workers",
            str(max(1, opts.workers)),
        ]
        cli_args.append("--vlm" if opts.use_vlm else "--no-vlm")
        if not opts.ocr:
            cli_args.append("--no-ocr")
        if not opts.stems:
            cli_args.append("--no-stems")
        if not opts.packaging:
            cli_args.append("--no-packaging")
        if not opts.asr:
            cli_args.extend(["--no-asr", "--no-speakers"])
        if opts.ocr_lang:
            cli_args.extend(["--ocr-lang", opts.ocr_lang])

        self._run_cli("decompose", cli_args, env_file=opts.env_file)

        if opts.prepare_review:
            self.prepare_review(out, force=False)

        result = self.load_breakdown(out)
        self._write_normalized(out, result)
        return result

    def prepare_review(
        self,
        output_dir: Path,
        *,
        force: bool = False,
    ) -> BreakdownReviewBundle:
        """Generate `review_tasks.json` and `review_answers.json` for visual review."""
        out = output_dir.expanduser().resolve()
        args = [str(out)]
        if force:
            args.append("--force")
        self._run_cli("review", args)

        tasks_path = out / "review_tasks.json"
        answers_path = out / "review_answers.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        shot_tasks = tasks.get("shots") or []
        high_prio = sum(
            1 for s in shot_tasks if isinstance(s, dict) and s.get("priority") == "high"
        )
        vmd = out / "VIDEO.md"
        sb = out / "storyboard.jpg"
        return BreakdownReviewBundle(
            output_dir=out,
            tasks_path=tasks_path,
            answers_path=answers_path,
            total_shots=len(shot_tasks),
            high_priority_shots=high_prio,
            videomd_path=vmd if vmd.is_file() else None,
            storyboard_path=sb if sb.is_file() else None,
        )

    def apply_review(
        self,
        output_dir: Path,
        *,
        reviewer: str,
        lang: Literal["en", "zh"] = "en",
    ) -> VideoBreakdownResult:
        """Merge completed `review_answers.json` back into `breakdown.json` and `VIDEO.md`."""
        out = output_dir.expanduser().resolve()
        self._run_cli("apply-review", [str(out), "--by", reviewer, "--lang", lang])
        result = self.load_breakdown(out)
        self._write_normalized(out, result)
        return result

    def load_breakdown(self, path: Path) -> VideoBreakdownResult:
        """Load either a normalized `video_breakdown.json` or raw `rea-video` output directory."""
        target = path.expanduser().resolve()
        if target.is_dir():
            raw_path = target / "breakdown.json"
            norm_path = target / "video_breakdown.json"
            if raw_path.is_file():
                raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
                return parse_rea_breakdown(
                    raw_data, output_dir=target, provider_name=self.provider_name
                )
            if norm_path.is_file():
                return VideoBreakdownResult.model_validate_json(
                    norm_path.read_text(encoding="utf-8")
                )
            raise FileNotFoundError(
                f"Neither breakdown.json nor video_breakdown.json found in {target}"
            )

        if not target.is_file():
            raise FileNotFoundError(f"Breakdown path not found: {target}")

        payload = json.loads(target.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") == "1.0"
            and "editing" in payload
            and "packaging" in payload
        ):
            return VideoBreakdownResult.model_validate(payload)
        return parse_rea_breakdown(
            payload, output_dir=target.parent, provider_name=self.provider_name
        )

    @staticmethod
    def _write_normalized(output_dir: Path, result: VideoBreakdownResult) -> Path:
        dest = output_dir / "video_breakdown.json"
        dest.write_text(
            json.dumps(result.model_dump(exclude_none=True), indent=2) + "\n",
            encoding="utf-8",
        )
        return dest
