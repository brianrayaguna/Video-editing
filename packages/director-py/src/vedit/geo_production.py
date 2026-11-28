"""End-to-end geospatial documentary audio automation and multi-act mastering."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root
from vedit.mastering.qc_audit import audit_mastered_deliverable

_PIVOT_RE = re.compile(
    r"\b("
    r"namun|tetapi|tapi|sayangnya|ironisnya|padahal|sebaliknya|kenyataannya|"
    r"however|unfortunately|ironically|turns out|in reality|instead|yet|but"
    r")\b",
    re.IGNORECASE,
)

_THEME_PROFILES: dict[str, dict[str, Any]] = {
    "maritime": {
        "keywords": (
            "pelabuhan", "kapal", "selat", "laut", "dermaga", "samudra", "kargo", "maritim",
            "port", "ship", "strait", "ocean", "sea", "maritime", "vessel", "canal", "harbor",
        ),
        "curious_query": "mysterious rhythmic marimba documentary",
        "tension_query": "dark suspense orchestral hybrid documentary",
        "ambience_query": "ocean waves sea ambience",
        "ambience_gain_db": -27.5,
        "foley": {
            "maritime_horn": ("distant cargo ship fog horn", -17.0, 2.4, 0.8),
            "underwater_dive": ("underwater dive splash submerge", -9.5, 2.2, 0.7),
        },
    },
    "weather": {
        "keywords": (
            "badai", "debu", "angin", "kering", "kekeringan", "hujan", "salju", "iklim",
            "storm", "dust", "wind", "drought", "blizzard", "hurricane", "climate", "monsoon",
        ),
        "curious_query": "minimal documentary acoustic investigative",
        "tension_query": "ominous dark ambient tension documentary",
        "ambience_query": "wind blowing prairie ambience",
        "ambience_gain_db": -26.5,
        "foley": {
            "wind_gust": ("strong wind dust gust", -14.0, 2.2, 0.7),
        },
    },
    "infrastructure": {
        "keywords": (
            "kereta", "jembatan", "terowongan", "bendungan", "jalan", "tol", "pipa", "kabel",
            "railway", "train", "bridge", "tunnel", "dam", "highway", "pipeline", "cable", "grid",
        ),
        "curious_query": "pulsing minimal tech documentary",
        "tension_query": "tense pulse investigative documentary",
        "ambience_query": "distant industrial city hum ambience",
        "ambience_gain_db": -28.0,
        "foley": {},
    },
    "geology": {
        "keywords": (
            "gunung", "gempa", "lempeng", "vulkanik", "magma", "patahan", "sungai", "lembah",
            "volcano", "earthquake", "tectonic", "fault", "magma", "canyon", "glacier", "river",
        ),
        "curious_query": "cinematic atmospheric wonder documentary",
        "tension_query": "deep rumble suspense documentary",
        "ambience_query": "deep mountain wind nature ambience",
        "ambience_gain_db": -27.5,
        "foley": {},
    },
    "aviation": {
        "keywords": (
            "pesawat", "bandara", "penerbangan", "udara", "rute terbang",
            "aircraft", "airport", "flight", "airspace", "airline", "aviation",
        ),
        "curious_query": "modern investigative electronic documentary",
        "tension_query": "suspenseful hybrid documentary",
        "ambience_query": "distant airplane jet ambience",
        "ambience_gain_db": -28.0,
        "foley": {},
    },
    "geopolitics": {
        "keywords": (
            "perbatasan", "negara", "perjanjian", "wilayah", "ekonomi", "miliar", "strategis",
            "border", "treaty", "territory", "sovereignty", "geopolitics", "billion", "enclave",
        ),
        "curious_query": "investigative minimal documentary marimba",
        "tension_query": "dark investigative tension orchestral",
        "ambience_query": "subtle outdoor air room ambience",
        "ambience_gain_db": -30.0,
        "foley": {},
    },
}


def _transcript_text(transcript: dict[str, Any] | None) -> str:
    if not transcript:
        return ""
    segs = transcript.get("segments") or []
    if segs:
        return " ".join(str(s.get("text") or "") for s in segs)
    words = transcript.get("words") or []
    return " ".join(str(w.get("word") or w.get("text") or "") for w in words)


def classify_audio_theme(
    transcript: dict[str, Any] | None,
    scene: dict[str, Any] | None = None,
) -> str:
    """Classify documentary domain theme from narration text and declarative scene layers."""
    haystack = _transcript_text(transcript).lower()
    if scene:
        for act in scene.get("acts") or []:
            haystack += " " + str(act.get("act_id") or "").lower()
            haystack += " " + str(act.get("preset") or "").lower()
            for layer in act.get("layers") or []:
                haystack += " " + str(layer.get("type") or "").lower()
                for sp in layer.get("sprites") or layer.get("items") or []:
                    haystack += " " + str(sp.get("kind") or "").lower()

    best_theme = "geopolitics"
    best_score = 0
    for theme, cfg in _THEME_PROFILES.items():
        score = sum(haystack.count(kw) for kw in cfg["keywords"])
        if score > best_score:
            best_score = score
            best_theme = theme
    return best_theme


def detect_narrative_pivot(
    transcript: dict[str, Any] | None,
    scene: dict[str, Any] | None = None,
) -> float | None:
    """Detect emotional/narrative hinge timestamp (in seconds) for a two-track BGM pivot."""
    acts = (scene or {}).get("acts") or []
    act_starts: list[float] = []
    acc = 0.0
    for act in acts:
        act_starts.append(round(acc, 3))
        acc += float(act.get("duration_s") or 0.0)
    total_dur = acc
    if total_dur <= 0.0 and transcript:
        total_dur = float(transcript.get("duration_s") or 0.0)
    if total_dur < 12.0:
        return None

    lo = total_dur * 0.35
    hi = total_dur * 0.85
    raw_pivot: float | None = None
    if transcript:
        for seg in transcript.get("segments") or []:
            t0 = float(seg.get("start_s", seg.get("start", 0.0)))
            if lo <= t0 <= hi and _PIVOT_RE.search(str(seg.get("text") or "")):
                raw_pivot = t0
                break

    if raw_pivot is not None:
        # Snap cleanly to an act boundary when within 2.5s so the silence breath hits on the cut.
        for a_start in act_starts[1:]:
            if abs(a_start - raw_pivot) <= 2.5:
                return round(a_start, 3)
        return round(raw_pivot, 3)

    # Fallback: pick an act cut in the final third if there are >= 3 acts.
    for a_start in act_starts[1:]:
        if total_dur * 0.55 <= a_start <= total_dur * 0.80:
            return round(a_start, 3)
    return None


def _convert_to_wav48(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(src),
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return dst


def _pick_result(results: list[Any], seed_key: str, *, exclude_ids: set[str] | None = None) -> Any:
    filtered = [r for r in results if not exclude_ids or r.asset_id not in exclude_ids]
    pool = filtered or results
    if not pool:
        return None
    top = pool[: min(5, len(pool))]
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return top[digest[0] % len(top)]


def plan_and_fetch_thematic_audio(
    scene: dict[str, Any],
    transcript: dict[str, Any] | None,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
    catalog: Any | None = None,
    seed_key: str | None = None,
) -> dict[str, Any]:
    """Select and cache theme-matched studio BGM (primary + pivot tension), ambience, and foley."""
    root = repo_root or find_repo_root()
    out_dir = out_dir.expanduser().resolve()
    sfx_out = out_dir / "sfx"
    out_dir.mkdir(parents=True, exist_ok=True)
    sfx_out.mkdir(parents=True, exist_ok=True)

    theme = classify_audio_theme(transcript, scene)
    cfg = _THEME_PROFILES[theme]
    pivot_s = detect_narrative_pivot(transcript, scene)
    seed = seed_key or f"{theme}:{len(scene.get('acts') or [])}"

    if catalog is None:
        try:
            from vedit.providers.builtins import build_default_registry

            catalog = build_default_registry().resolve("audio_catalog")
        except Exception:
            catalog = None

    used_ids: set[str] = set()
    bgm_primary: Path | None = None
    bgm_second: Path | None = None
    ambience_wav: Path | None = None
    extra_sfx: list[dict[str, Any]] = []
    source_notes: list[str] = []

    def _fetch_music(query: str, out_wav: Path, tag: str) -> Path | None:
        if out_wav.is_file() and out_wav.stat().st_size > 16384:
            source_notes.append(f"{tag}:cached:{out_wav.name}")
            return out_wav
        if catalog is None:
            return None
        try:
            res = catalog.search_music(query, vocal_type="NONE", bpm_range=(76, 134), limit=6)
            pick = _pick_result(res, f"{seed}:{tag}", exclude_ids=used_ids)
            if pick is None:
                return None
            used_ids.add(pick.asset_id)
            raw_path = catalog.download_asset(
                pick.asset_id, kind="music", destination_dir=out_dir / "_dl", quality="high"
            )
            _convert_to_wav48(raw_path, out_wav)
            source_notes.append(f"{tag}:catalog:{pick.asset_id}:{pick.title}")
            return out_wav
        except Exception as exc:
            source_notes.append(f"{tag}:catalog_error:{exc}")
            return None

    def _fetch_sfx(query: str, out_wav: Path, tag: str) -> Path | None:
        if out_wav.is_file() and out_wav.stat().st_size > 4096:
            return out_wav
        if catalog is None:
            return None
        try:
            res = catalog.search_sfx(query, limit=5)
            if not res:
                return None
            pick = res[0]
            raw_path = catalog.download_asset(
                pick.asset_id, kind="sfx", destination_dir=sfx_out / "_dl", quality="high"
            )
            _convert_to_wav48(raw_path, out_wav)
            source_notes.append(f"{tag}:catalog:{pick.asset_id}:{pick.title}")
            return out_wav
        except Exception as exc:
            source_notes.append(f"{tag}:catalog_error:{exc}")
            return None

    bgm_primary = _fetch_music(cfg["curious_query"], out_dir / "bgm_curious.wav", "bgm_primary")
    if bgm_primary is None:
        local_bgm = root / "assets" / "audio" / "bgm" / "documentary_curious.wav"
        if local_bgm.is_file():
            bgm_primary = local_bgm
            source_notes.append(f"bgm_primary:studio_library:{local_bgm.name}")

    if pivot_s is not None:
        bgm_second = _fetch_music(cfg["tension_query"], out_dir / "bgm_tension.wav", "bgm_second")
        if bgm_second is None:
            local_t = root / "assets" / "audio" / "bgm" / "documentary_tension.wav"
            if local_t.is_file():
                bgm_second = local_t
                source_notes.append(f"bgm_second:studio_library:{local_t.name}")

    ambience_wav = _fetch_sfx(cfg["ambience_query"], sfx_out / f"ambience_{theme}.wav", "ambience")

    # Map scene beats to domain-specific real recorded foley
    repo_sfx = root / "assets" / "audio" / "sfx"
    t_off = 0.0
    for act in scene.get("acts") or []:
        dur = float(act.get("duration_s") or 0.0)
        act_kind = str(act.get("kind") or "map")
        preset = str(act.get("preset") or "")
        if act.get("transition_in") in {"disc_sweep", "feathered_dark_wipe"} and t_off > 0.1:
            sw = repo_sfx / "flash_swish.wav"
            if sw.is_file():
                extra_sfx.append(
                    {"t_s": round(max(0.0, t_off - 0.12), 3), "path": str(sw), "gain_db": -9.5}
                )
        if act_kind == "cutaway_2d" and "port" in preset and "underwater_dive" in cfg["foley"]:
            q, g_db, tr_s, fo_s = cfg["foley"]["underwater_dive"]
            dive_wav = _fetch_sfx(q, sfx_out / "underwater_dive.wav", "underwater_dive")
            if dive_wav is not None:
                extra_sfx.append(
                    {
                        "t_s": round(max(0.0, t_off - 0.25), 3),
                        "path": str(dive_wav),
                        "gain_db": g_db,
                        "trim_s": tr_s,
                        "fade_out_s": fo_s,
                    }
                )
        for layer in act.get("layers") or []:
            ltype = str(layer.get("type") or "")
            t0 = t_off + float(layer.get("start_s") or 0.0)
            if ltype == "parchment_sheet":
                p_wav = repo_sfx / "paper_unfold.wav"
                if not p_wav.is_file():
                    p_wav = _fetch_sfx(
                        "paper map unfold rustle", sfx_out / "paper_unfold.wav", "paper_unfold"
                    ) or p_wav
                if p_wav.is_file():
                    extra_sfx.append({"t_s": round(t0, 3), "path": str(p_wav), "gain_db": -8.5})
            elif ltype == "map_sprites" and theme == "maritime" and "maritime_horn" in cfg["foley"]:
                sprites = layer.get("sprites") or layer.get("items") or []
                has_ships = any(str(sp.get("kind") or "") == "cargo_ship" for sp in sprites)
                if has_ships and len(sprites) >= 3:
                    q, g_db, tr_s, fo_s = cfg["foley"]["maritime_horn"]
                    horn_wav = _fetch_sfx(q, sfx_out / "ship_horn.wav", "ship_horn")
                    if horn_wav is not None:
                        extra_sfx.append(
                            {
                                "t_s": round(t0 + 0.85, 3),
                                "path": str(horn_wav),
                                "gain_db": g_db,
                                "pan": 0.2,
                                "trim_s": tr_s,
                                "fade_out_s": fo_s,
                            }
                        )
        t_off += dur

    extra_sfx_path = out_dir / "extra_sfx.json"
    extra_sfx_path.write_text(json.dumps(extra_sfx, indent=2), encoding="utf-8")

    plan = {
        "ok": True,
        "theme": theme,
        "bgm_primary": str(bgm_primary) if bgm_primary else None,
        "bgm_second": str(bgm_second) if bgm_second else None,
        "bgm_switch_s": pivot_s,
        "ambience_file": str(ambience_wav) if ambience_wav else None,
        "ambience_gain_db": cfg["ambience_gain_db"],
        "extra_sfx_file": str(extra_sfx_path),
        "extra_sfx_count": len(extra_sfx),
        "sources": source_notes,
    }
    (out_dir / "audio_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def master_geo_acts(
    scene_file: Path,
    acts_dir: Path,
    audio_file: Path,
    out_file: Path,
    *,
    captions_file: Path | None = None,
    caption_renderer: str = "html",
    credit_ass_file: Path | None = None,
    contact_sheet: Path | None = None,
    audit_out: Path | None = None,
    platform_id: str | None = None,
    brand_id: str | None = None,
    strict_verify: bool = False,
    crf: int = 17,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Assemble baked map/cutaway acts through the canonical EditPlan and ffmpeg_master spine."""
    import vedit.mastering.ffmpeg_master as ffmpeg_master
    from vedit.contracts import validate_against_contract
    from vedit.director.verifier import verify_edit_plan
    from vedit.geo.plan_bridge import build_edit_plan_from_geo_acts
    from vedit.models import BrandStylePolicy

    root = repo_root or find_repo_root()
    plan, target_model, disc_cuts = build_edit_plan_from_geo_acts(
        scene_file,
        acts_dir,
        audio_file,
        platform_id=platform_id,
        brand_id=brand_id,
        repo_root=root,
    )
    width = plan.width
    height = plan.height
    fps = int(round(plan.fps))
    target_dur = plan.duration_s
    audio_p = audio_file.expanduser().resolve()
    out_p = out_file.expanduser().resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Pre-master verification against brand policy when a brand is resolved, else schema contract.
    verification_passed = True
    verification_errors: list[dict[str, Any]] = []
    verification_warnings: list[dict[str, Any]] = []
    policy_path = (
        root / "profiles" / "brands" / plan.brand_id / "brand_style_policy.json"
        if plan.brand_id != "unbranded"
        else None
    )
    if policy_path is not None and policy_path.is_file():
        policy = BrandStylePolicy.model_validate(
            json.loads(policy_path.read_text(encoding="utf-8"))
        )
        vrep = verify_edit_plan(plan, policy, target_model, repo_root=root).to_dict()
        verification_passed = bool(vrep["passed"])
        verification_errors = list(vrep["errors"])
        verification_warnings = list(vrep["warnings"])
    else:
        schema_errs = validate_against_contract(
            plan.model_dump(exclude_none=True), "edit_plan.schema.json", repo_root=root
        )
        if schema_errs:
            verification_passed = False
            verification_errors = [
                {"severity": "error", "code": "EDIT_PLAN_SCHEMA_INVALID", "message": e}
                for e in schema_errs
            ]

    if strict_verify and not verification_passed:
        raise ValueError(f"EditPlan verification failed: {verification_errors}")

    with tempfile.TemporaryDirectory(prefix="vedit_geo_master_") as td:
        tdp = Path(td)
        transition_overlays: list[tuple[Path, float]] = []
        if disc_cuts:
            disc_mov = tdp / "disc_sweep.mov"
            rad = round(max(width, height) * 0.64)
            feather = max(60, round(width * 0.20))
            start_x = round(width * 1.37)
            step_x = round(width * 0.35)
            cy = height // 2
            disc_vf = (
                "format=rgba,"
                "geq=r=3:g=12:b=18:"
                f"a='255*clip(({rad}-hypot(X-({start_x}-N*{step_x}),Y-{cy}))/{feather},0,1)'"
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=black@0.0:s={width}x{height}:r={fps}:d={6 / fps:.3f}",
                    "-vf",
                    disc_vf,
                    "-frames:v",
                    "6",
                    "-c:v",
                    "png",
                    "-pix_fmt",
                    "rgba",
                    str(disc_mov),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            for cut_t in disc_cuts:
                transition_overlays.append((disc_mov, max(0.0, cut_t - (3.0 / fps))))

        external_caption_concat: tuple[Path, int] | None = None
        ass_cap_for_master: Path | None = None
        caption_renderer_used = "none"
        cap_p = (
            captions_file.expanduser().resolve()
            if captions_file is not None and captions_file.expanduser().is_file()
            else None
        )
        if cap_p is not None:
            want_html = str(caption_renderer or "html").strip().lower() == "html"
            overlay_script = root / "tools" / "geo-assets" / "render_captions_overlay.mjs"
            if want_html and overlay_script.is_file():
                html_out = tdp / "html_captions"
                render_proc = subprocess.run(
                    [
                        "node",
                        str(overlay_script),
                        "--captions",
                        str(cap_p),
                        "--out-dir",
                        str(html_out),
                        "--width",
                        str(width),
                        "--height",
                        str(height),
                        "--fps",
                        str(fps),
                        "--duration",
                        f"{target_dur:.3f}",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if render_proc.returncode == 0 and render_proc.stdout.strip():
                    try:
                        parsed_meta = json.loads(render_proc.stdout.strip().splitlines()[-1])
                        if parsed_meta.get("ok") and Path(parsed_meta["concat_file"]).is_file():
                            external_caption_concat = (
                                Path(parsed_meta["concat_file"]),
                                int(parsed_meta.get("y_top", 0)),
                            )
                            caption_renderer_used = "html"
                    except (ValueError, KeyError):
                        external_caption_concat = None
            if external_caption_concat is None:
                ass_cap_for_master = cap_p
                caption_renderer_used = "libass"

        cred_p = (
            credit_ass_file.expanduser().resolve()
            if credit_ass_file is not None and credit_ass_file.expanduser().is_file()
            else None
        )
        ffmpeg_master.assemble_hybrid_deliverable(
            plan,
            target_model,
            out_p,
            transition_overlays=transition_overlays or None,
            external_caption_concat=external_caption_concat,
            mastered_audio_path=audio_p,
            captions_ass_path=ass_cap_for_master,
            credit_ass_path=cred_p,
            use_ass_fastpath=False,
            encode_preset="medium",
            crf=crf,
            stamp_vui_metadata=True,
        )

    sheet_out: str | None = None
    if contact_sheet is not None:
        sheet_p = contact_sheet.expanduser().resolve()
        sheet_p.parent.mkdir(parents=True, exist_ok=True)
        sample_fps = 16.0 / max(1.0, target_dur)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(out_p),
                "-vf",
                f"fps={sample_fps:.6f},scale=360:-1,tile=4x4:padding=8:color=#03161F",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(sheet_p),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        sheet_out = str(sheet_p)

    audit_payload: dict[str, Any] | None = None
    if audit_out is not None or platform_id is not None:
        qc = audit_mastered_deliverable(out_p, target_model)
        audit_payload = qc.to_dict()
        if audit_out is not None:
            ap = audit_out.expanduser().resolve()
            ap.parent.mkdir(parents=True, exist_ok=True)
            ap.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")

    return {
        "ok": True if audit_payload is None else bool(audit_payload.get("passed", False)),
        "master_file": str(out_p),
        "edit_plan_job_id": plan.job_id,
        "brand_id": plan.brand_id,
        "verification_passed": verification_passed,
        "verification_errors": verification_errors,
        "verification_warnings": verification_warnings,
        "duration_s": round(target_dur, 3),
        "acts_count": len(plan.video_tracks),
        "disc_sweep_cuts": disc_cuts,
        "caption_renderer": caption_renderer_used,
        "contact_sheet": sheet_out,
        "audit_passed": None if audit_payload is None else audit_payload.get("passed"),
        "audit_errors": [] if audit_payload is None else audit_payload.get("errors", []),
        "audit_warnings": [] if audit_payload is None else audit_payload.get("warnings", []),
    }
