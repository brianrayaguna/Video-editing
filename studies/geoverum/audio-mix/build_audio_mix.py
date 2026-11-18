#!/usr/bin/env python3
"""Build, verify, compile, master, and QC the 15.567s Geoverum audio-mix study."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from vedit.analyzers.media_probe import hash_media
from vedit.compiler.hf_bridge import (
    assemble_v2,
    compile_edit_plan,
    plan_distributed_v2,
    render_chunk_v2,
)
from vedit.contracts import find_repo_root, load_platform_targets
from vedit.director.verifier import verify_edit_plan
from vedit.mastering.ffmpeg_master import assemble_hybrid_deliverable, master_audio_mix
from vedit.mastering.qc_audit import audit_mastered_deliverable
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


def _sha(path: Path) -> str:
    res = hash_media(path)
    return str(res["sha256"]) if isinstance(res, dict) else str(res.sha256)


def _probe_dur(path: Path) -> float:
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
    """Return unboxed broadcast top header custom HTML inside the upper safe margin."""
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
    tl.to("#bug-hdr", {{ opacity: 0, duration: 0.25, ease: "power2.in" }}, {fade_out_at});
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


def main() -> int:
    root = find_repo_root()
    study_dir = root / "studies" / "geoverum" / "audio-mix"
    renders_dir = study_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    shots_dir = root / "studies" / "geoverum" / "pilot-sulawesi" / "assets" / "shots"
    shot1 = shots_dir / "shot_01_hook_dive.mp4"
    shot2 = shots_dir / "shot_02_peninsulas.mp4"
    for req in (shot1, shot2):
        if not req.is_file():
            raise FileNotFoundError(f"Missing rendered shot asset: {req}")

    vo_path = root / "assets" / "audio" / "sulawesi_vo_clean.wav"
    bgm_path = root / "assets" / "audio" / "music_c273725d-3f35-3506-9275-d1f6a00011bb_high.wav"
    whoosh_path = root / "assets" / "audio" / "sfx_36d506f7-b031-4bf5-8b50-cad859dde276_high.wav"
    impact_path = root / "assets" / "audio" / "sfx_d0ba83c3-79f2-4fd0-aa3b-6bf95f741f2a_high.wav"
    font_sg = root / "assets" / "geo" / "fonts" / "SpaceGrotesk-Variable.ttf"
    transcript_path = root / "assets" / "audio" / "sulawesi_transcript.json"
    policy_path = root / "profiles" / "brands" / "geoverum" / "brand_style_policy.json"

    boxes_path = root / "studies" / "geoverum" / "pilot-sulawesi" / "assets" / "subject_boxes.json"
    subject_boxes = json.loads(boxes_path.read_text(encoding="utf-8")) if boxes_path.is_file() else {}
    s01_boxes = subject_boxes.get("shot_01_hook_dive", [])
    s02_boxes = subject_boxes.get("shot_02_peninsulas", [])

    total_dur = round(min(_probe_dur(shot1) + _probe_dur(shot2), 15.567), 3)
    shot1_dur = round(min(_probe_dur(shot1), 10.167), 3)
    shot2_dur = round(total_dur - shot1_dur, 3)
    captions = [
        (0.40, 1.35, "Kalau lihat peta,", None),
        (1.38, 2.45, "Sulawesi tampak seperti", "Sulawesi"),
        (2.45, 3.68, "huruf K yang patah", "K"),
        (3.74, 5.45, "atau gurita yang salah posisi.", "salah posisi."),
        (5.72, 7.22, "Bentukannya ini bukan kebetulan,", None),
        (7.30, 8.88, "melainkan hasil tabrakan geologi", "tabrakan"),
        (8.92, 10.02, "selama jutaan tahun.", None),
        (10.32, 11.78, "Sulawesi punya empat semenanjung", "empat semenanjung"),
        (11.80, 12.92, "panjang yang menjulur ke", None),
        (12.96, 13.56, "utara,", "utara,"),
        (13.58, 14.16, "timur,", "timur,"),
        (14.18, 14.74, "tenggara,", "tenggara,"),
        (14.75, 15.42, "dan selatan.", "selatan."),
    ]

    overlays: list[OverlayCompositionOp] = [
        OverlayCompositionOp(
            overlay_id="ov_broadcast_bug",
            kind="full_scene",
            timeline_start_s=0.0,
            timeline_duration_s=total_dur,
            transparent=True,
            safe_band="upper_safe",
            props=_broadcast_bug_props(total_dur),
        )
    ]
    for idx, (s, e, text, hi) in enumerate(captions):
        props: dict[str, object] = {
            "text": text,
            "font_family": "Space Grotesk",
            "fg_color": "#F4F1EA",
            "bg_color": "#03161F",
            "accent_color": "#F5C542",
            "box": {"top": 0.695, "bottom": 0.748, "left": 0.06, "right": 0.84},
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
                safe_band="lower_third",
                props=props,
            )
        )

    plan = EditPlan(
        schema_version="1.0",
        job_id="geoverum_audio_mix_study",
        project_id="geoverum",
        brand_id="geoverum",
        platform_target_id="shorts_9x16_1080p",
        render_strategy="hybrid",
        duration_s=total_dur,
        fps=30.0,
        width=1080,
        height=1920,
        assets=[
            AssetRef(
                asset_id="shot_01",
                sha256=_sha(shot1),
                kind="video",
                path=str(shot1),
                duration_s=_probe_dur(shot1),
                has_audio=False,
            ),
            AssetRef(
                asset_id="shot_02",
                sha256=_sha(shot2),
                kind="video",
                path=str(shot2),
                duration_s=_probe_dur(shot2),
                has_audio=False,
            ),
            AssetRef(
                asset_id="vo_clean",
                sha256=_sha(vo_path),
                kind="audio_speech",
                path=str(vo_path),
                duration_s=_probe_dur(vo_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="bgm_main",
                sha256=_sha(bgm_path),
                kind="audio_bgm",
                path=str(bgm_path),
                duration_s=_probe_dur(bgm_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="sfx_whoosh",
                sha256=_sha(whoosh_path),
                kind="audio_sfx",
                path=str(whoosh_path),
                duration_s=_probe_dur(whoosh_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="sfx_impact",
                sha256=_sha(impact_path),
                kind="audio_sfx",
                path=str(impact_path),
                duration_s=_probe_dur(impact_path),
                has_audio=True,
            ),
            AssetRef(
                asset_id="font_space_grotesk",
                sha256=_sha(font_sg),
                kind="font",
                path=str(font_sg),
            ),
        ],
        video_tracks=[
            VideoClipOp(
                clip_id="clip_01_hook",
                asset_id="shot_01",
                timeline_start_s=0.0,
                timeline_duration_s=shot1_dur,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
                subject_safe_boxes=s01_boxes,
            ),
            VideoClipOp(
                clip_id="clip_02_peninsulas",
                asset_id="shot_02",
                timeline_start_s=shot1_dur,
                timeline_duration_s=shot2_dur,
                source_start_s=0.0,
                role="a_roll",
                reframed_to_target=True,
                transition_in="whip_zoom_blur",
                subject_safe_boxes=s02_boxes,
            ),
        ],
        overlay_compositions=overlays,
        audio_tracks=[
            AudioTrackOp(
                track_id="vo_sulawesi_hook",
                asset_id="vo_clean",
                audio_group="voiceover",
                timeline_start_s=0.0,
                timeline_duration_s=total_dur,
                source_start_s=0.0,
                gain_db=4.5,
                cleaned_speech_stem=True,
            ),
            AudioTrackOp(
                track_id="bgm_epidemic_bed",
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
                track_id="sfx_k_thud",
                asset_id="sfx_impact",
                audio_group="sfx",
                timeline_start_s=2.95,
                timeline_duration_s=1.15,
                source_start_s=1.79,
                gain_db=-14.0,
            ),
            AudioTrackOp(
                track_id="sfx_whip_seam",
                asset_id="sfx_whoosh",
                audio_group="sfx",
                timeline_start_s=9.567,
                timeline_duration_s=1.4,
                source_start_s=0.24,
                gain_db=-11.0,
            ),
        ],
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

    hf_dir = study_dir / "hf_project"
    shutil.rmtree(hf_dir, ignore_errors=True)
    compiled = compile_edit_plan(plan, hf_dir, platform_target=target, run_lint=True, repo_root=root)
    if compiled.lint and not compiled.lint.ok:
        raise RuntimeError(f"HyperFrames lint errors: {compiled.lint.hyperframes_findings}")

    plan_v2_dir = study_dir / "plan_v2"
    overlay_mov = renders_dir / "audio_mix_overlay.mov"
    if not overlay_mov.is_file():
        shutil.rmtree(plan_v2_dir, ignore_errors=True)
        planned = plan_distributed_v2(
            hf_dir,
            plan_v2_dir,
            fps=round(target.fps),
            width=target.width,
            height=target.height,
            fmt="mov",
            chunk_frames=240,
            repo_root=root,
        )
        chunk_count = int(planned["manifest"]["chunkCount"])
        print(f"Plan v2 prepared ({chunk_count} chunk(s), {planned['manifest']['totalFrames']} frames)")

        chunk_paths: list[Path] = []
        for idx in range(chunk_count):
            out_c = renders_dir / f"overlay_chunk_{idx:04d}.mov"
            if not out_c.is_file():
                render_chunk_v2(plan_v2_dir, idx, out_c, repo_root=root)
            chunk_paths.append(out_c)
        assemble_v2(plan_v2_dir, chunk_paths, overlay_mov, repo_root=root)

    mastered_wav = renders_dir / "audio_mix_mastered.wav"
    audio_res = master_audio_mix(plan, target, mastered_wav)

    out_mp4 = renders_dir / "audio_mix_1080x1920.mp4"
    assemble_hybrid_deliverable(
        plan,
        target,
        out_mp4,
        overlay_video_path=overlay_mov,
        mastered_audio_path=mastered_wav,
    )

    qc = audit_mastered_deliverable(out_mp4, target, require_audio=True)
    qc_out = renders_dir / "audio_mix_qc.json"
    qc_payload = {
        "qc": qc.to_dict(),
        "audio_loudnorm_first_pass": asdict(audio_res.measurement),
        "target_lufs": audio_res.target_lufs,
        "target_tp_dbtp": audio_res.target_tp_dbtp,
    }
    qc_out.write_text(json.dumps(qc_payload, indent=2), encoding="utf-8")
    print("QC report:", json.dumps(qc_payload, indent=2))
    if not qc.passed:
        return 1

    sheet_path = renders_dir / "audio_mix_sheet.jpg"
    times = [1.4, 3.1, 6.4, 10.17, 13.3, 15.0]
    thumbs: list[Path] = []
    for i, t in enumerate(times):
        tp = renders_dir / f"_t{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-ss", f"{t:.3f}", "-i", str(out_mp4), "-frames:v", "1", str(tp)],
            check=True,
            capture_output=True,
        )
        thumbs.append(tp)

    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *[arg for tp in thumbs for arg in ("-i", str(tp))],
            "-filter_complex",
            "xstack=inputs=6:layout=0_0|w0_0|w0+w1_0|0_h0|w0_h0|w0+w1_h0,scale=1620:-1",
            "-q:v",
            "3",
            str(sheet_path),
        ],
        check=True,
        capture_output=True,
    )
    for tp in thumbs:
        tp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
