"""Tests for thematic audio automation and multi-act geospatial mastering."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from vedit.cli import app
from vedit.geo_production import (
    classify_audio_theme,
    detect_narrative_pivot,
    master_geo_acts,
    plan_and_fetch_thematic_audio,
)
from vedit.ports.audio_catalog import AudioAssetResult


class _StubAudioCatalog:
    provider_name = "stub_catalog"

    def search_music(self, query: str, **kwargs: object) -> list[AudioAssetResult]:
        del kwargs
        tag = "tension" if "suspense" in query or "tension" in query else "curious"
        return [
            AudioAssetResult(
                asset_id=f"trk_{tag}_{i}",
                provider=self.provider_name,
                kind="music",
                title=f"Track {tag} {i}",
                duration_s=120.0,
                bpm=112.0,
                vocal_type="NONE",
            )
            for i in range(3)
        ]

    def search_sfx(self, query: str, **kwargs: object) -> list[AudioAssetResult]:
        del kwargs
        slug = query.split()[0]
        return [
            AudioAssetResult(
                asset_id=f"sfx_{slug}",
                provider=self.provider_name,
                kind="sfx",
                title=f"SFX {slug}",
                duration_s=3.0,
            )
        ]

    def download_asset(
        self, asset_id: str, *, kind: str, destination_dir: Path, quality: str = "high"
    ) -> Path:
        del kind, quality
        destination_dir.mkdir(parents=True, exist_ok=True)
        out = destination_dir / f"{asset_id}.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=220:sample_rate=48000:duration=0.4",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out


def _make_act_clip(path: Path, color: str, duration_s: float = 1.5) -> Path:
    del color
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1080x1920:rate=30:duration={duration_s}",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _make_norm_audio(path: Path, duration_s: float = 3.0) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=320:sample_rate=48000:duration={duration_s}",
            "-af",
            "loudnorm=I=-14.0:TP=-1.5:LRA=7.0",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_theme_classification_and_narrative_pivot_detection() -> None:
    transcript = {
        "duration_s": 57.3,
        "segments": [
            {"start_s": 0.0, "end_s": 5.0, "text": "Dari Pelabuhan Sabang di gerbang Selat Malaka"},
            {"start_s": 20.0, "end_s": 28.0, "text": "Kapal kargo raksasa dan dermaga laut dalam"},
            {
                "start_s": 40.3,
                "end_s": 46.0,
                "text": "Namun hingga 2026 belum ada rute kapal reguler",
            },
        ],
    }
    scene = {
        "acts": [
            {"act_id": "a1", "duration_s": 12.3},
            {"act_id": "a2", "duration_s": 12.2},
            {"act_id": "a3", "duration_s": 15.65},
            {"act_id": "a4", "duration_s": 17.15},
        ]
    }
    assert classify_audio_theme(transcript, scene) == "maritime"
    # Pivot at 40.3s snaps cleanly to act 4 boundary at 40.15s
    assert detect_narrative_pivot(transcript, scene) == 40.15


def test_plan_and_fetch_thematic_audio_with_stub_catalog(tmp_path: Path) -> None:
    scene = {
        "acts": [
            {
                "act_id": "a1",
                "duration_s": 12.0,
                "layers": [
                    {"type": "parchment_sheet", "start_s": 4.0, "bbox": [91.0, 4.0, 98.0, 11.0]},
                    {
                        "type": "map_sprites",
                        "start_s": 1.0,
                        "sprites": [
                            {"kind": "cargo_ship", "coord": [95.0, 6.0]},
                            {"kind": "cargo_ship", "coord": [96.0, 5.5]},
                            {"kind": "cargo_ship", "coord": [97.0, 5.0]},
                        ],
                    },
                ],
            },
            {
                "act_id": "a2",
                "kind": "cutaway_2d",
                "preset": "port_depth_cutaway",
                "transition_in": "disc_sweep",
                "duration_s": 8.0,
            },
            {"act_id": "a3", "duration_s": 10.0, "layers": []},
        ]
    }
    transcript = {
        "duration_s": 30.0,
        "segments": [
            {"start_s": 0.0, "end_s": 8.0, "text": "Pelabuhan kapal kargo di selat"},
            {"start_s": 20.1, "end_s": 26.0, "text": "Namun proyek itu belum berjalan"},
        ],
    }
    plan = plan_and_fetch_thematic_audio(
        scene,
        transcript,
        tmp_path / "audio",
        catalog=_StubAudioCatalog(),
        seed_key="ep_sabang",
    )
    assert plan["ok"] is True
    assert plan["theme"] == "maritime"
    assert plan["bgm_switch_s"] == 20.0
    assert plan["bgm_primary"] and Path(plan["bgm_primary"]).is_file()
    assert plan["bgm_second"] and Path(plan["bgm_second"]).is_file()
    assert plan["ambience_file"] and Path(plan["ambience_file"]).is_file()
    assert plan["extra_sfx_count"] >= 2
    assert Path(plan["extra_sfx_file"]).is_file()


def test_master_geo_acts_applies_disc_sweep_bt709_and_passes_audit(tmp_path: Path) -> None:
    acts_dir = tmp_path / "acts"
    acts_dir.mkdir()
    _make_act_clip(acts_dir / "act01.mp4", "#083847", duration_s=1.5)
    _make_act_clip(acts_dir / "act02.mp4", "#154957", duration_s=1.5)
    audio_wav = _make_norm_audio(tmp_path / "mix.wav", duration_s=3.0)

    scene_path = tmp_path / "map_scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "acts": [
                    {"act_id": "act01", "output_file": "act01.mp4", "duration_s": 1.5},
                    {
                        "act_id": "act02",
                        "output_file": "act02.mp4",
                        "duration_s": 1.5,
                        "transition_in": "disc_sweep",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    out_mp4 = tmp_path / "out" / "master.mp4"
    sheet_jpg = tmp_path / "out" / "sheet.jpg"
    audit_json = tmp_path / "out" / "audit.json"

    res = master_geo_acts(
        scene_path,
        acts_dir,
        audio_wav,
        out_mp4,
        contact_sheet=sheet_jpg,
        audit_out=audit_json,
        platform_id="shorts_9x16_1080p",
    )
    assert res["ok"] is True, res
    assert res["audit_passed"] is True, res["audit_errors"]
    assert res["disc_sweep_cuts"] == [1.5]
    assert out_mp4.is_file() and sheet_jpg.is_file() and audit_json.is_file()

    # Also verify CLI command `vedit geo master`
    cli_out = tmp_path / "out" / "cli_master.mp4"
    cli_res = CliRunner().invoke(
        app,
        [
            "geo",
            "master",
            "--scene-file",
            str(scene_path),
            "--acts-dir",
            str(acts_dir),
            "--audio",
            str(audio_wav),
            "-o",
            str(cli_out),
        ],
    )
    assert cli_res.exit_code == 0, cli_res.output
    payload = json.loads(cli_res.stdout)
    assert payload["ok"] is True and cli_out.is_file()
