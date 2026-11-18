#!/usr/bin/env python3
"""Assemble and verify the native Geoverum 30s tectonics EditPlan for Modal cloud render."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from vedit.analyzers.media_probe import hash_media
from vedit.compiler.hf_bridge import compile_edit_plan
from vedit.contracts import find_repo_root, load_platform_targets
from vedit.director.verifier import verify_edit_plan
from vedit.models import (
    AssetRef,
    AudioTrackOp,
    BrandStylePolicy,
    EditPlan,
    NormalizedTranscript,
    OverlayCompositionOp,
    PlatformTarget,
    TranscriptWord,
    VideoClipOp,
)

DURATION_S = 30.0
FPS = 30.0
CAPTION_SCHEDULE = [
    (7, 51, "Turki dan India terpisah", "Turki"),
    (51, 150, "km, tidak berbagi perbatasan,", None),
    (150, 210, "bahkan berada di kawasan", None),
    (210, 360, "Namun hubungan keduanya kini", None),
    (375, 450, "Penyebab utamanya adalah Pakistan.", "Pakistan"),
    (480, 570, "Pakistan dalam isu Kashmir", "Kashmir"),
    (590, 645, "Ketegangan makin terasa setelah", None),
    (645, 720, "konflik India-Pakistan pada", "India-Pakistan"),
    (735, 780, "2025 ketika pesawat nirawak", "nirawak"),
    (780, 840, "buatan Turki dilaporkan", "Turki"),
    (840, 900, "India tidak membalas dengan", "India"),
]


def _sha(path: Path) -> str:
    res = hash_media(path)
    return str(res["sha256"]) if isinstance(res, dict) else str(res.sha256)


def _probe_frames_and_dur(path: Path) -> tuple[int, float]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_frames:format=duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    meta = json.loads(out)
    dur = float(meta["format"]["duration"])
    nb_frames = int((meta.get("streams") or [{}])[0].get("nb_frames") or round(dur * FPS))
    return nb_frames, dur


def _probe_audio_dur(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return round(float(out.strip()), 3)


def _broadcast_bug_props(duration_s: float) -> dict[str, object]:
    # Platform safe_zone.top_pct=0.14 → y≈269px (shorts_9x16_1080p).
    custom_css = """
    .geo-top-bug {
      position: absolute;
      top: 274px;
      left: 108px;
      right: 108px;
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 14px;
      opacity: 0.86;
      pointer-events: none;
    }
    .geo-wordmark {
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      font-size: 32px;
      letter-spacing: 0.12em;
      color: #F4F1EA;
      line-height: 1;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.68);
      text-transform: uppercase;
    }
    """
    custom_html = """
    <div id="bug-hdr" class="geo-top-bug">
      <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
        <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.2"/>
        <ellipse cx="17" cy="17" rx="6.2" ry="13" stroke="rgba(244,241,234,0.68)" stroke-width="1.3"/>
        <line x1="4" y1="17" x2="30" y2="17" stroke="rgba(244,241,234,0.68)" stroke-width="1.3"/>
        <circle cx="22.4" cy="12.2" r="2.6" fill="#C2412D"/>
      </svg>
      <span class="geo-wordmark">GEOVERUM</span>
    </div>
    """
    timeline_js = """
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#bug-hdr", { opacity: 0 }, { opacity: 0.86, duration: 0.20, ease: "expo.out" }, 0.10);
    window.__timelines = window.__timelines || {};
    window.__timelines["ov_broadcast_bug"] = tl;
    """
    return {
        "font_family": "Space Grotesk",
        "fg_color": "#F4F1EA",
        "bg_color": "#03161F",
        "accent_color": "#C2412D",
        "box": {"top": 0.142, "bottom": 0.178, "left": 0.18, "right": 0.82},
        "custom_css": custom_css,
        "custom_html": custom_html,
        "custom_timeline_js": timeline_js,
    }


def _metric_corridor_props() -> dict[str, object]:
    # Sits in upper clear band below the bug, inside platform safe zone, above subject landmass.
    custom_css = """
    .geo-metric {
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      font-family: 'Archivo Black', 'Space Grotesk', sans-serif;
      font-size: 28px;
      letter-spacing: 0.04em;
      color: #F4F1EA;
      text-shadow: 0 2px 8px rgba(0,0,0,0.75);
      pointer-events: none;
      white-space: nowrap;
    }
    """
    custom_html = """<div id="metric-chip" class="geo-metric">+4.000 KM</div>"""
    timeline_js = """
    const tl = gsap.timeline({ paused: true });
    tl.fromTo("#metric-chip", { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.28, ease: "expo.out" }, 0.15);
    tl.to("#metric-chip", { opacity: 0, duration: 0.22, ease: "power2.in" }, 5.6);
    window.__timelines = window.__timelines || {};
    window.__timelines["ov_metric_corridor"] = tl;
    """
    return {
        "font_family": "Archivo Black",
        "fg_color": "#F4F1EA",
        "bg_color": "#03161F",
        "accent_color": "#D9383A",
        "box": {"top": 0.200, "bottom": 0.255, "left": 0.28, "right": 0.72},
        "custom_css": custom_css,
        "custom_html": custom_html,
        "custom_timeline_js": timeline_js,
    }


def _caption_box() -> dict[str, float]:
    # Inside shorts safe zone: top>=0.14, bottom<=0.75, left>=0.05, right<=0.84
    return {"top": 0.700, "bottom": 0.748, "left": 0.06, "right": 0.84}


def _build_transcript(vo_sha: str, duration_s: float) -> NormalizedTranscript:
    words: list[TranscriptWord] = []
    texts: list[str] = []
    for start_f, end_f, text, _hi in CAPTION_SCHEDULE:
        start_s = start_f / FPS
        end_s = end_f / FPS
        parts = text.replace(",", "").replace(".", "").split()
        if not parts:
            continue
        texts.append(text)
        span = max(0.05, (end_s - start_s) / len(parts))
        for i, w in enumerate(parts):
            ws = round(start_s + i * span, 3)
            we = round(min(end_s, ws + span * 0.92), 3)
            words.append(
                TranscriptWord(
                    text=w,
                    start_s=ws,
                    end_s=we,
                    speaker=None,
                    confidence=0.9,
                    is_filler=False,
                )
            )
    return NormalizedTranscript(
        source_hash=vo_sha,
        provider="manual_caption_ledger",
        model="ref_tectonics_shot0_schedule",
        language="id",
        duration_s=duration_s,
        text=" ".join(texts),
        words=words,
    )


def main() -> int:
    root = find_repo_root()
    study_dir = root / "studies" / "geoverum" / "tectonics-30s"
    assets_dir = study_dir / "assets"
    renders_dir = study_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    basemap = assets_dir / "basemap-tectonics-30s.mp4"
    vo_path = assets_dir / "vo-30s.wav"
    font_sg = root / "assets" / "geo" / "fonts" / "SpaceGrotesk-Variable.ttf"
    font_ab = root / "assets" / "geo" / "fonts" / "ArchivoBlack-Regular.ttf"
    policy_path = root / "profiles" / "brands" / "geoverum" / "brand_style_policy.json"
    boxes_path = assets_dir / "subject_boxes.json"

    if not basemap.is_file():
        raise FileNotFoundError(f"Missing basemap A-roll: {basemap}")
    if not vo_path.is_file():
        raise FileNotFoundError(f"Missing VO stem: {vo_path}")

    nb_frames, actual_dur = _probe_frames_and_dur(basemap)
    total_dur = round(min(nb_frames / FPS, actual_dur, DURATION_S), 3)
    vo_dur = min(_probe_audio_dur(vo_path), DURATION_S)

    # Landmass core only — leaves upper bug/metric and lower_third caption bands clear.
    subject_boxes = [
        {
            "top": 0.32,
            "bottom": 0.62,
            "left": 0.22,
            "right": 0.78,
            "label": "map_landmass_primary",
        }
    ]
    if boxes_path.is_file():
        raw = json.loads(boxes_path.read_text(encoding="utf-8"))
        loaded = raw.get("basemap_tectonics_30s", raw.get("shot_0", []))
        if loaded:
            subject_boxes = loaded

    assets: list[AssetRef] = [
        AssetRef(
            asset_id="basemap_tectonics_30s",
            sha256=_sha(basemap),
            kind="video",
            path=str(basemap),
            duration_s=round(actual_dur, 3),
            has_audio=False,
        ),
        AssetRef(
            asset_id="vo_clean",
            sha256=_sha(vo_path),
            kind="audio_speech",
            path=str(vo_path),
            duration_s=vo_dur,
            has_audio=True,
        ),
        AssetRef(
            asset_id="font_space_grotesk",
            sha256=_sha(font_sg),
            kind="font",
            path=str(font_sg),
        ),
        AssetRef(
            asset_id="font_archivo_black",
            sha256=_sha(font_ab),
            kind="font",
            path=str(font_ab),
        ),
    ]

    # Split continuous A-roll into ≤12s clips at caption-gap boundaries
    # (never mid-keyword): 0→12.0, 12.0→19.2, 19.2→30.0.
    cut_points = [0.0, 12.0, 19.2, total_dur]
    video_tracks: list[VideoClipOp] = []
    for seg_i in range(len(cut_points) - 1):
        start = cut_points[seg_i]
        end = cut_points[seg_i + 1]
        dur = round(end - start, 3)
        if dur <= 0:
            continue
        video_tracks.append(
            VideoClipOp(
                clip_id=f"clip_tectonics_{seg_i:02d}",
                asset_id="basemap_tectonics_30s",
                timeline_start_s=round(start, 3),
                timeline_duration_s=dur,
                source_start_s=round(start, 3),
                role="a_roll",
                reframed_to_target=True,
                transition_in=None,
                subject_safe_boxes=subject_boxes,
            )
        )

    overlays: list[OverlayCompositionOp] = [
        OverlayCompositionOp(
            overlay_id="ov_broadcast_bug",
            kind="full_scene",
            timeline_start_s=0.0,
            timeline_duration_s=total_dur,
            transparent=True,
            safe_band="upper_safe",
            props=_broadcast_bug_props(total_dur),
        ),
        OverlayCompositionOp(
            overlay_id="ov_metric_corridor",
            kind="full_scene",
            timeline_start_s=1.20,
            timeline_duration_s=5.90,
            transparent=True,
            safe_band="upper_safe",
            props=_metric_corridor_props(),
        ),
    ]

    box = _caption_box()
    for idx, (sf, ef, text, hi) in enumerate(CAPTION_SCHEDULE):
        start_s = round(sf / FPS, 3)
        end_s = round(ef / FPS, 3)
        props: dict[str, object] = {
            "text": text,
            "font_family": "Space Grotesk",
            "fg_color": "#F4F1EA",
            "bg_color": "#03161F",
            "accent_color": "#F5C542",
            "box": box,
        }
        if hi:
            props["highlight_text"] = hi
        overlays.append(
            OverlayCompositionOp(
                overlay_id=f"cap_{idx:02d}",
                kind="caption_rail",
                timeline_start_s=start_s,
                timeline_duration_s=round(end_s - start_s, 3),
                transparent=True,
                safe_band="lower_third",
                props=props,
            )
        )

    audio_tracks = [
        AudioTrackOp(
            track_id="vo_tectonics_30s",
            asset_id="vo_clean",
            audio_group="voiceover",
            timeline_start_s=0.0,
            timeline_duration_s=vo_dur,
            source_start_s=0.0,
            gain_db=4.5,
            cleaned_speech_stem=True,
        )
    ]

    plan = EditPlan(
        schema_version="1.0",
        job_id="geoverum_tectonics_30s",
        project_id="geoverum",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=total_dur,
        fps=FPS,
        width=1080,
        height=1920,
        assets=assets,
        video_tracks=video_tracks,
        overlay_compositions=overlays,
        audio_tracks=audio_tracks,
    )

    targets = load_platform_targets()
    target = PlatformTarget.model_validate(targets["shorts_9x16_1080p"])
    policy = BrandStylePolicy.model_validate_json(policy_path.read_text(encoding="utf-8"))

    transcript_path = assets_dir / "vo_transcript.json"
    if transcript_path.is_file():
        transcript = NormalizedTranscript.model_validate_json(
            transcript_path.read_text(encoding="utf-8")
        )
    else:
        transcript = _build_transcript(_sha(vo_path), vo_dur)
        transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote caption-ledger transcript -> {transcript_path}")

    verdict = verify_edit_plan(plan, policy, target, transcript=transcript)
    print("Verify verdict:", json.dumps(asdict(verdict), indent=2))
    if not verdict.passed:
        return 1

    plan = plan.model_copy(update={"verifier_passed": True})
    plan_path = study_dir / "edit_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote verified EditPlan -> {plan_path}")

    dry_hf = study_dir / "_dry_hf_check"
    shutil.rmtree(dry_hf, ignore_errors=True)
    compiled = compile_edit_plan(
        plan,
        dry_hf,
        platform_target=target,
        copy_assets=False,
        run_lint=True,
        repo_root=root,
    )
    shutil.rmtree(dry_hf, ignore_errors=True)
    if compiled.lint:
        print(
            f"HyperFrames lint ok={compiled.lint.ok} errors={compiled.lint.total_errors} "
            f"warnings={compiled.lint.total_warnings}"
        )
        if not compiled.lint.ok:
            print("Lint findings:", compiled.lint.hyperframes_findings)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
