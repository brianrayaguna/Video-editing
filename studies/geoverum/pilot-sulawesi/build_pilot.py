#!/usr/bin/env python3
"""Assemble and validate the full 70.600s Sulawesi documentary EditPlan for Modal cloud render."""

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
    VideoClipOp,
)

SHOT_ORDER = [
    ("clip_01_hook", "shot_01_hook_dive", None),
    ("clip_02_peninsulas", "shot_02_peninsulas", "whip_zoom_blur"),
    ("clip_03_three_gulfs", "shot_03_three_gulfs", None),
    ("clip_04_three_plates", "shot_04_three_plates", "whip_zoom_blur"),
    ("clip_05_puzzle", "shot_05_puzzle", None),
    ("clip_06_palu_koro", "shot_06_palu_koro", None),
    ("clip_07_archipelago", "shot_07_archipelago", None),
    ("clip_08_relief_climax", "shot_08_relief_climax", "amber_light_leak"),
    ("clip_09_outro_cta", "shot_09_outro_cta", "clean_fade"),
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
    nb_frames = int((meta.get("streams") or [{}])[0].get("nb_frames") or round(dur * 30.0))
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
    fade_out_at = round(max(0.5, duration_s - 0.35), 3)
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
      opacity: 0.72;
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
      <span class="geo-wordmark">geoverum</span>
    </div>
    """
    timeline_js = f"""
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#bug-hdr", {{ opacity: 0 }}, {{ opacity: 0.72, duration: 0.35, ease: "expo.out" }}, 0);
    tl.to("#bug-hdr", {{ opacity: 0, duration: 0.28, ease: "power2.in" }}, {fade_out_at});
    window.__timelines = window.__timelines || {{}};
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


def _outro_endcard_props(duration_s: float) -> dict[str, object]:
    fade_out_at = round(max(0.5, duration_s - 0.25), 3)
    custom_css = """
    .geo-endcard {
      position: absolute;
      top: 322px;
      left: 96px;
      right: 174px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 16px;
      pointer-events: none;
    }
    .geo-end-brand {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .geo-end-wordmark {
      font-family: 'Archivo Black', 'Space Grotesk', sans-serif;
      font-size: 40px;
      letter-spacing: 0.08em;
      color: #F4F1EA;
      line-height: 1;
    }
    .geo-end-rule {
      width: 64px;
      height: 2px;
      background: #F5C542;
    }
    .geo-end-prompt {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 24px;
      font-weight: 500;
      color: #F4F1EA;
      opacity: 0.92;
      line-height: 1.3;
    }
    .geo-end-tag {
      font-family: 'Space Grotesk', sans-serif;
      font-size: 18px;
      font-weight: 600;
      letter-spacing: 0.06em;
      color: #F5C542;
    }
    """
    custom_html = """
    <div id="outro-card" class="geo-endcard">
      <div class="geo-end-brand">
        <svg width="40" height="40" viewBox="0 0 34 34" fill="none">
          <circle cx="17" cy="17" r="13" stroke="#F4F1EA" stroke-width="2.2"/>
          <ellipse cx="17" cy="17" rx="6.2" ry="13" stroke="rgba(244,241,234,0.72)" stroke-width="1.3"/>
          <line x1="4" y1="17" x2="30" y2="17" stroke="rgba(244,241,234,0.72)" stroke-width="1.3"/>
          <circle cx="22.4" cy="12.2" r="2.8" fill="#F5C542"/>
        </svg>
        <span class="geo-end-wordmark">geoverum</span>
      </div>
      <div class="geo-end-rule"></div>
      <div class="geo-end-prompt">Berasal dari Sulawesi?</div>
      <div class="geo-end-tag">Tulis wilayahmu di komentar</div>
    </div>
    """
    timeline_js = f"""
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo(
      "#outro-card",
      {{ opacity: 0, y: 12 }},
      {{ opacity: 1, y: 0, duration: 0.34, ease: "expo.out" }},
      0
    );
    tl.to("#outro-card", {{ opacity: 0, duration: 0.22, ease: "power2.in" }}, {fade_out_at});
    window.__timelines = window.__timelines || {{}};
    window.__timelines["ov_outro_cta"] = tl;
    """
    return {
        "font_family": "Space Grotesk",
        "fg_color": "#F4F1EA",
        "bg_color": "#03161F",
        "accent_color": "#F5C542",
        "box": {"top": 0.16, "bottom": 0.36, "left": 0.08, "right": 0.84},
        "custom_css": custom_css,
        "custom_html": custom_html,
        "custom_timeline_js": timeline_js,
    }


def _caption_segments() -> list[tuple[float, float, str, str | None, str, dict[str, float]]]:
    lower_std = {"top": 0.700, "bottom": 0.748, "left": 0.06, "right": 0.84}
    lower_tomini = {"top": 0.713, "bottom": 0.749, "left": 0.06, "right": 0.84}
    upper_palu = {"top": 0.205, "bottom": 0.258, "left": 0.06, "right": 0.84}
    return [
        # Shot 01: Hook (0.000 -> 10.167)
        (0.40, 1.32, "Kalau lihat peta,", None, "lower_third", lower_std),
        (1.36, 2.42, "Sulawesi tampak seperti", "Sulawesi", "lower_third", lower_std),
        (2.44, 3.68, "huruf K yang patah", "K", "lower_third", lower_std),
        (3.74, 5.45, "atau gurita yang salah posisi.", "salah posisi.", "lower_third", lower_std),
        (5.72, 7.22, "Bentukannya ini bukan kebetulan,", None, "lower_third", lower_std),
        (7.30, 8.88, "melainkan hasil tabrakan geologi", "tabrakan", "lower_third", lower_std),
        (8.92, 10.02, "selama jutaan tahun.", None, "lower_third", lower_std),
        # Shot 02: Four peninsulas (10.167 -> 15.567)
        (10.32, 11.78, "Sulawesi punya empat semenanjung", "empat semenanjung", "lower_third", lower_std),
        (11.80, 12.92, "panjang yang menjulur ke", None, "lower_third", lower_std),
        (12.96, 13.56, "utara,", "utara,", "lower_third", lower_std),
        (13.58, 14.16, "timur,", "timur,", "lower_third", lower_std),
        (14.18, 14.74, "tenggara,", "tenggara,", "lower_third", lower_std),
        (14.75, 15.42, "dan selatan.", "selatan.", "lower_third", lower_std),
        # Shot 03: Three gulfs (15.567 -> 25.767)
        (15.74, 16.92, "Di sela-selanya,", None, "lower_third", lower_tomini),
        (16.94, 18.36, "laut masuk membentuk Teluk Tomini,", "Teluk Tomini,", "lower_third", lower_tomini),
        (18.42, 19.50, "Tolo, dan Bone.", "Tolo, dan Bone.", "lower_third", lower_tomini),
        (19.76, 21.82, "Itulah yang membuat bentuknya acak,", None, "lower_third", lower_tomini),
        (21.96, 23.80, "padahal sebenarnya menunjukkan", None, "lower_third", lower_tomini),
        (23.84, 25.58, "bekas proses tektonik yang rumit.", "tektonik", "lower_third", lower_tomini),
        # Shot 04: Three plates (25.767 -> 36.167)
        (26.00, 27.62, "Pulau ini berada di pertemuan", None, "lower_third", lower_std),
        (27.64, 29.02, "pecahan kerak dari Asia,", "Asia,", "lower_third", lower_std),
        (29.06, 30.80, "Australia, dan Samudera Purba.", "Samudera Purba.", "lower_third", lower_std),
        (31.12, 33.18, "Bagian kecil kerak bertabrakan,", "bertabrakan,", "lower_third", lower_std),
        (33.20, 34.48, "terserap, dan terlipat,", None, "lower_third", lower_std),
        (34.52, 36.02, "lalu retak dan bergeser.", "bergeser.", "lower_third", lower_std),
        # Shot 05: Geological puzzle (36.167 -> 42.300)
        (36.28, 38.68, "Hasil akhirnya bukan pulau bulat,", None, "lower_third", lower_std),
        (38.82, 40.55, "melainkan puzzle geologi", "puzzle geologi", "lower_third", lower_std),
        (40.62, 42.12, "yang dirakit sambil diguncang.", "diguncang.", "lower_third", lower_std),
        # Shot 06: Palu-Koro fault (42.300 -> 50.500 -> placed in upper clear sea band)
        (42.46, 44.20, "Sesar besar seperti Palu-Koro", "Palu-Koro", "upper_safe", upper_palu),
        (44.32, 45.60, "ikut mengacak bentuknya,", None, "upper_safe", upper_palu),
        (45.72, 47.92, "pengangkatan dan penurunan daratan", "daratan", "upper_safe", upper_palu),
        (47.96, 50.32, "membentuk lengan panjang Sulawesi.", "Sulawesi.", "upper_safe", upper_palu),
        # Shot 07: Archipelago (50.500 -> 56.800)
        (50.66, 52.45, "Jadi, bentuk unik ini", None, "lower_third", lower_std),
        (52.48, 53.78, "bukan karena pembuat peta iseng.", None, "lower_third", lower_std),
        (53.80, 56.58, "Sulawesi pulau paling rumit di Indonesia.", "Sulawesi", "lower_third", lower_std),
        # Shot 08: Relief climax (56.800 -> 66.033)
        (57.04, 59.32, "Itulah sebabnya Sulawesi rawan gempa", "rawan gempa", "lower_third", lower_std),
        (59.42, 61.50, "dan punya pegunungan saling bersilang,", "pegunungan", "lower_third", lower_std),
        (61.68, 63.76, "geolog menyebut Sulawesi sebagai", None, "lower_third", lower_std),
        (63.80, 65.86, "teka-teki tektonik Indonesia.", "teka-teki tektonik", "lower_third", lower_std),
        # Shot 09: Outro CTA (66.033 -> 70.600)
        (66.20, 67.20, "Nah geolovers,", None, "lower_third", lower_std),
        (67.22, 69.30, "ada yang berasal dari Sulawesi?", "Sulawesi?", "lower_third", lower_std),
        (69.50, 70.42, "Komen di bawah ya.", None, "lower_third", lower_std),
    ]


def main() -> int:
    root = find_repo_root()
    study_dir = root / "studies" / "geoverum" / "pilot-sulawesi"
    shots_dir = study_dir / "assets" / "shots"
    renders_dir = study_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    boxes_path = study_dir / "assets" / "subject_boxes.json"
    subject_boxes = json.loads(boxes_path.read_text(encoding="utf-8"))

    assets: list[AssetRef] = []
    video_tracks: list[VideoClipOp] = []
    cursor_s = 0.0

    for clip_id, shot_id, trans_in in SHOT_ORDER:
        mp4 = shots_dir / f"{shot_id}.mp4"
        if not mp4.is_file():
            raise FileNotFoundError(f"Missing rendered shot MP4: {mp4}")
        nb_frames, actual_dur = _probe_frames_and_dur(mp4)
        # Keep timeline clip duration anchored to exact frame duration while never exceeding actual_dur
        clip_dur = round(min(nb_frames / 30.0, actual_dur), 3)
        assets.append(
            AssetRef(
                asset_id=shot_id,
                sha256=_sha(mp4),
                kind="video",
                path=str(mp4),
                duration_s=round(actual_dur, 3),
                has_audio=False,
            )
        )
        video_tracks.append(
            VideoClipOp(
                clip_id=clip_id,
                asset_id=shot_id,
                timeline_start_s=round(cursor_s, 3),
                timeline_duration_s=clip_dur,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
                transition_in=trans_in,
                subject_safe_boxes=subject_boxes.get(shot_id, []),
            )
        )
        cursor_s = round(cursor_s + clip_dur, 3)

    total_dur = cursor_s
    print(f"Total assembled pilot video duration: {total_dur:.3f}s ({len(video_tracks)} shots)")

    vo_path = root / "assets" / "audio" / "sulawesi_vo_clean.wav"
    bgm_path = root / "assets" / "audio" / "music_c273725d-3f35-3506-9275-d1f6a00011bb_high.wav"
    whoosh_path = root / "assets" / "audio" / "sfx_36d506f7-b031-4bf5-8b50-cad859dde276_high.wav"
    riser_path = root / "assets" / "audio" / "sfx_bf1e97b7-996e-4b60-9306-d595088f9b9c_high.wav"
    impact_path = root / "assets" / "audio" / "sfx_d0ba83c3-79f2-4fd0-aa3b-6bf95f741f2a_high.wav"
    font_sg = root / "assets" / "geo" / "fonts" / "SpaceGrotesk-Variable.ttf"
    font_ab = root / "assets" / "geo" / "fonts" / "ArchivoBlack-Regular.ttf"
    transcript_path = root / "assets" / "audio" / "sulawesi_transcript.json"
    policy_path = root / "profiles" / "brands" / "geoverum" / "brand_style_policy.json"

    assets.extend(
        [
            AssetRef(
                asset_id="vo_clean",
                sha256=_sha(vo_path),
                kind="audio_speech",
                path=str(vo_path),
                duration_s=_probe_audio_dur(vo_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="bgm_main",
                sha256=_sha(bgm_path),
                kind="audio_bgm",
                path=str(bgm_path),
                duration_s=_probe_audio_dur(bgm_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="sfx_whoosh",
                sha256=_sha(whoosh_path),
                kind="audio_sfx",
                path=str(whoosh_path),
                duration_s=_probe_audio_dur(whoosh_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="sfx_riser",
                sha256=_sha(riser_path),
                kind="audio_sfx",
                path=str(riser_path),
                duration_s=_probe_audio_dur(riser_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="sfx_impact",
                sha256=_sha(impact_path),
                kind="audio_sfx",
                path=str(impact_path),
                duration_s=_probe_audio_dur(impact_path),
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
    )

    outro_start = video_tracks[-1].timeline_start_s
    bug_dur = round(outro_start - 0.15, 3)
    outro_dur = round(total_dur - outro_start, 3)

    overlays: list[OverlayCompositionOp] = [
        OverlayCompositionOp(
            overlay_id="ov_broadcast_bug",
            kind="full_scene",
            timeline_start_s=0.0,
            timeline_duration_s=bug_dur,
            transparent=True,
            safe_band="upper_safe",
            props=_broadcast_bug_props(bug_dur),
        ),
        OverlayCompositionOp(
            overlay_id="ov_outro_cta",
            kind="title_scene",
            timeline_start_s=outro_start,
            timeline_duration_s=outro_dur,
            transparent=True,
            safe_band="upper_safe",
            props=_outro_endcard_props(outro_dur),
        ),
    ]

    for idx, (s, e, text, hi, band, box) in enumerate(_caption_segments()):
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
                timeline_start_s=s,
                timeline_duration_s=round(e - s, 3),
                transparent=True,
                safe_band=band,  # type: ignore[arg-type]
                props=props,
            )
        )

    audio_tracks = [
        AudioTrackOp(
            track_id="vo_sulawesi_full",
            asset_id="vo_clean",
            audio_group="voiceover",
            timeline_start_s=0.0,
            timeline_duration_s=_probe_audio_dur(vo_path),
            source_start_s=0.0,
            gain_db=4.5,
            cleaned_speech_stem=True,
        ),
        AudioTrackOp(
            track_id="bgm_epidemic_full",
            asset_id="bgm_main",
            audio_group="music",
            timeline_start_s=0.0,
            timeline_duration_s=total_dur,
            source_start_s=12.0,
            gain_db=-18.0,
            carve_against_group="voiceover",
            carve_strength=0.85,
            cleaned_speech_stem=False,
        ),
        AudioTrackOp(
            track_id="sfx_hook_thud",
            asset_id="sfx_impact",
            audio_group="sfx",
            timeline_start_s=2.95,
            timeline_duration_s=1.15,
            source_start_s=1.79,
            gain_db=-14.0,
        ),
        AudioTrackOp(
            track_id="sfx_whip_peninsulas",
            asset_id="sfx_whoosh",
            audio_group="sfx",
            timeline_start_s=9.567,
            timeline_duration_s=1.40,
            source_start_s=0.24,
            gain_db=-11.0,
        ),
        AudioTrackOp(
            track_id="sfx_whip_plates",
            asset_id="sfx_whoosh",
            audio_group="sfx",
            timeline_start_s=25.167,
            timeline_duration_s=1.40,
            source_start_s=0.24,
            gain_db=-13.0,
        ),
        AudioTrackOp(
            track_id="sfx_quake_thud",
            asset_id="sfx_impact",
            audio_group="sfx",
            timeline_start_s=41.25,
            timeline_duration_s=1.20,
            source_start_s=1.79,
            gain_db=-13.5,
        ),
        AudioTrackOp(
            track_id="sfx_climax_riser",
            asset_id="sfx_riser",
            audio_group="sfx",
            timeline_start_s=55.760,
            timeline_duration_s=2.20,
            source_start_s=0.0,
            gain_db=-12.5,
        ),
    ]

    plan = EditPlan(
        schema_version="1.0",
        job_id="geoverum_sulawesi_pilot",
        project_id="geoverum",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=total_dur,
        fps=30.0,
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
    transcript = NormalizedTranscript.model_validate_json(transcript_path.read_text(encoding="utf-8"))

    verdict = verify_edit_plan(plan, policy, target, transcript=transcript)
    print("Verify verdict:", json.dumps(asdict(verdict), indent=2))
    if not verdict.passed:
        return 1

    plan = plan.model_copy(update={"verifier_passed": True})
    plan_path = study_dir / "edit_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote verified EditPlan -> {plan_path}")

    # Local HyperFrames compile & static lint dry-check before submitting to Modal
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
