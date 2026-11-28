"""Offline mocked HTTP tests for capability provider adapters and registry plumbing."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from vedit.ports.decision import DecisionQuestion, ImageInput
from vedit.providers.audio_catalog.epidemic import EpidemicAudioCatalogProvider
from vedit.providers.decision.liquid_d1 import LiquidDecisionProvider, extract_spatial_boxes
from vedit.providers.env import load_dotenv_safe, upsert_env_var
from vedit.providers.http import ProviderAPIError
from vedit.providers.media_ops.ffmpeg_local import FfmpegMediaOpsProvider
from vedit.providers.registry import build_default_registry


def test_builtin_registry_marks_all_active_providers_implemented() -> None:
    registry = build_default_registry()
    report = registry.status_report()
    assert report["transcription"]["registered"] == []
    assert {s["name"] for s in report["media_ops"]["registered"]} == {
        "ffmpeg",
        "modal_cloud",
    }
    assert {s["name"] for s in report["decision"]["registered"]} == {"liquid_d1"}
    assert {s["name"] for s in report["audio_catalog"]["registered"]} == {"epidemic"}
    assert {s["name"] for s in report["geo_imagery"]["registered"]} == {
        "google_tiles",
        "open_imagery",
    }
    for capability in ("decision", "media_ops", "audio_catalog", "video_breakdown", "geo_imagery"):
        assert report[capability]["registered"]
        assert all(s["implemented"] for s in report[capability]["registered"])


def test_dotenv_upsert_and_load_preserves_existing_env(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    upsert_env_var(env_file, "SAMPLE_KEY", "secret-abc")
    mode = env_file.stat().st_mode & 0o777
    assert mode == 0o600

    monkeypatch.delenv("SAMPLE_KEY", raising=False)
    monkeypatch.setenv("KEEP_EXISTING", "from-shell")
    upsert_env_var(env_file, "KEEP_EXISTING", "from-file")
    monkeypatch.setenv("KEEP_EXISTING", "from-shell")

    load_dotenv_safe(repo_root=tmp_path)
    assert os.environ["SAMPLE_KEY"] == "secret-abc"
    assert os.environ["KEEP_EXISTING"] == "from-shell"


def test_liquid_decision_redacts_secret_in_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid token liq-super-secret-999")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = LiquidDecisionProvider({"api_key": "liq-super-secret-999"}, client=client)
    with pytest.raises(ProviderAPIError) as exc_info:
        engine.evaluate(
            state="hello",
            questions=[
                DecisionQuestion(
                    name="ok",
                    question_type="noul",
                    instructions="Is this valid?",
                )
            ],
        )
    assert "liq-super-secret-999" not in str(exc_info.value)
    assert "***REDACTED***" in str(exc_info.value)


def test_liquid_decision_handles_typed_questions_and_boxes(tmp_path: Path) -> None:
    img_path = tmp_path / "frame.jpg"
    img_path.write_bytes(b"\xff\xd8\xff\xe0dummyjpeg")

    seen_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        seen_payload = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "d1.2-ultra",
                "usage": {"input_tokens": 120, "output_tokens": 0},
                "answers": {
                    "face_box": {
                        "type": "box",
                        "found": 0.96,
                        "confidence": 0.94,
                        "box": {"top": 0.1, "bottom": 0.7, "left": 0.3, "right": 0.65},
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = LiquidDecisionProvider({"api_key": "liq-key"}, client=client)
    result = engine.evaluate(
        state={"shot_index": 0},
        questions=[
            DecisionQuestion(
                name="face_box",
                question_type="box",
                instructions="Locate the primary speaker.",
            )
        ],
        images=[ImageInput(path=img_path, content_type="image/jpeg")],
    )

    assert seen_payload["model"] == "d1.2-ultra"
    assert isinstance(seen_payload["questions"], dict)
    assert "face_box" in seen_payload["questions"]
    assert seen_payload["questions"]["face_box"]["type"] == "box"  # type: ignore[index]
    assert len(seen_payload["images"]) == 1  # type: ignore[arg-type]
    boxes = extract_spatial_boxes(result.answers["face_box"])
    assert len(boxes) == 1
    assert boxes[0].left == pytest.approx(0.3)
    assert result.input_tokens == 120


def test_ffmpeg_local_media_ops_clean_audio_and_reframe(tmp_path: Path) -> None:
    clip = tmp_path / "src_16x9.mp4"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(clip),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    ops = FfmpegMediaOpsProvider()
    clean_wav = tmp_path / "clean.wav"
    res_audio = ops.clean_audio(clip, clean_wav, strength=0.7)
    assert res_audio.output_path.is_file() and clean_wav.stat().st_size > 1000

    reframed = tmp_path / "reframed_9x16.mp4"
    res_vid = ops.reframe(clip, reframed, target_aspect_ratio="9:16")
    assert res_vid.metadata["width"] == 1080
    assert res_vid.metadata["height"] == 1920
    assert reframed.is_file() and reframed.stat().st_size > 1000


def test_epidemic_uses_repeated_query_keys_and_caches_downloads(tmp_path: Path) -> None:
    seen_queries: list[str] = []
    cdn_headers: dict[str, str] = {}
    api_download_hits = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cdn_headers, api_download_hits
        if request.url.host == "api.epidemicsound.com":
            seen_queries.append(request.url.query.decode("utf-8"))
            if request.url.path == "/v0/tracks/search":
                return httpx.Response(
                    200,
                    json={
                        "tracks": [
                            {
                                "id": "trk-1",
                                "title": "Clean Pulse",
                                "length": 124.5,
                                "bpm": 118,
                                "vocalType": "NONE",
                                "moods": [{"tag": "focused"}],
                                "genres": [{"tag": "electronic"}],
                            }
                        ]
                    },
                )
            if request.url.path == "/v0/tracks/trk-1/download":
                api_download_hits += 1
                return httpx.Response(
                    200, json={"url": "https://cdn.epidemicsound.test/trk-1.mp3?sig=ok"}
                )
        if request.url.host == "cdn.epidemicsound.test":
            cdn_headers = dict(request.headers)
            return httpx.Response(200, content=b"ID3mp3payload")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cat = EpidemicAudioCatalogProvider({"api_key": "epi-key"}, client=client)

    tracks = cat.search_music("minimal focus", vocal_type="NONE", moods=["focused", "tech"])
    assert len(tracks) == 1
    assert tracks[0].bpm == 118.0
    parsed = parse_qs(seen_queries[0])
    assert parsed["mood"] == ["focused", "tech"]
    assert parsed["vocalType"] == ["NONE"]

    p1 = cat.download_asset("trk-1", kind="music", destination_dir=tmp_path, quality="high")
    p2 = cat.download_asset("trk-1", kind="music", destination_dir=tmp_path, quality="high")
    assert p1 == p2
    assert p1.read_bytes() == b"ID3mp3payload"
    assert "authorization" not in {k.lower() for k in cdn_headers}
    assert api_download_hits == 1


def test_epidemic_mcp_transport_search_and_download(tmp_path: Path) -> None:
    seen_rpc_methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.epidemicsound.com":
            return httpx.Response(401, json={"message": "Unauthorized"})
        if request.url.host == "www.epidemicsound.com" and request.url.path == "/a/mcp-service/mcp":
            body = json.loads(request.content.decode("utf-8"))
            method = body.get("method")
            seen_rpc_methods.append(method)
            if method == "initialize":
                init_body = {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "result": {"protocolVersion": "2025-03-26"},
                }
                return httpx.Response(
                    200,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Mcp-Session-Id": "sess-123",
                    },
                    text=f"data: {json.dumps(init_body)}\n\n",
                )
            if method == "notifications/initialized":
                return httpx.Response(202, text="")
            if method == "tools/call":
                tool = body["params"]["name"]
                if tool == "SearchRecordings":
                    payload = {
                        "data": {
                            "recordings": {
                                "nodes": [
                                    {
                                        "recording": {
                                            "id": "872cd5d6-c040-335f-890d-dc68d9e58b09",
                                            "title": "Grieving Volcano",
                                            "bpm": 60,
                                            "audioFile": {
                                                "durationInMilliseconds": 173638,
                                                "lqmp3Url": "https://cdn.test/prev.mp3",
                                            },
                                            "tags": [
                                                {
                                                    "displayName": "ambient",
                                                    "dimension": {"name": "genre"},
                                                },
                                                {
                                                    "displayName": "mysterious",
                                                    "dimension": {"name": "mood"},
                                                },
                                                {
                                                    "displayName": "no vocals",
                                                    "dimension": {"name": "vocals"},
                                                },
                                            ],
                                        }
                                    }
                                ]
                            }
                        }
                    }
                    rpc_res = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
                    }
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "text/event-stream"},
                        text=f"data: {json.dumps(rpc_res)}\n\n",
                    )
                if tool == "DownloadSoundEffect":
                    dl_payload = {
                        "data": {"soundEffectDownload": {"assetUrl": "https://cdn.test/sfx.wav"}}
                    }
                    dl_rpc = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"content": [{"type": "text", "text": json.dumps(dl_payload)}]},
                    }
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        json=dl_rpc,
                    )
        if request.url.host == "cdn.test":
            return httpx.Response(200, content=b"RIFFwavdata")
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cat = EpidemicAudioCatalogProvider({"api_key": "epidemic_live_test"}, client=client)

    tracks = cat.search_music("documentary", vocal_type="NONE")
    assert len(tracks) == 1
    assert tracks[0].title == "Grieving Volcano"
    assert tracks[0].duration_s == 173.638
    assert tracks[0].bpm == 60.0
    assert tracks[0].vocal_type == "NONE"

    sfx_path = cat.download_asset(
        "9e26e4dc-2b6e-4f10-8bc4-6a2f158c3401",
        kind="sfx",
        destination_dir=tmp_path,
        quality="high",
    )
    assert sfx_path.suffix == ".wav"
    assert sfx_path.read_bytes() == b"RIFFwavdata"
    assert seen_rpc_methods == [
        "initialize",
        "notifications/initialized",
        "tools/call",
        "tools/call",
    ]


def test_registry_call_with_fallback_promotes_secondary_provider() -> None:
    from vedit.providers.config import CapabilityProviderConfig, ProvidersConfig
    from vedit.providers.registry import ProviderRegistry, ProviderSpec

    class _FailProvider:
        def __init__(self, _cfg: dict) -> None:
            pass

        def ping(self) -> str:
            raise ProviderAPIError("primary", 402, "insufficient credits")

    class _OkProvider:
        def __init__(self, _cfg: dict) -> None:
            pass

        def ping(self) -> str:
            return "recovered"

    cfg = ProvidersConfig(
        defaults={
            "media_ops": CapabilityProviderConfig(
                primary="primary",
                fallback=["backup"],
                options={},
            )
        }
    )
    reg = ProviderRegistry(config=cfg)
    reg.register(ProviderSpec("media_ops", "primary", _FailProvider))
    reg.register(ProviderSpec("media_ops", "backup", _OkProvider))

    value = reg.call_with_fallback("media_ops", lambda p: p.ping())
    assert value == "recovered"


def test_dotenv_round_trip_unescapes_quotes_and_backslashes(tmp_path: Path) -> None:
    from vedit.providers.env import _parse_dotenv_lines, upsert_env_var
    from vedit.providers.media_ops import __all__ as media_ops_all

    env_path = tmp_path / ".env"
    secret = 'abc"def\\ghi'
    upsert_env_var(env_path, "TEST_ROUNDTRIP_KEY", secret)
    parsed = _parse_dotenv_lines(env_path.read_text(encoding="utf-8"))
    assert parsed["TEST_ROUNDTRIP_KEY"] == secret
    assert "ModalCloudMediaOpsProvider" in media_ops_all


def test_all_registered_media_ops_providers_implement_full_media_ops_port(
    tmp_path: Path,
) -> None:
    from vedit.ports.media_ops import MediaOpsPort
    from vedit.providers.media_ops.modal_cloud import ModalCloudMediaOpsProvider

    registry = build_default_registry()
    for name in ("ffmpeg", "modal_cloud"):
        provider = registry.resolve("media_ops", provider_name=name)
        assert isinstance(provider, MediaOpsPort), (
            f"media_ops provider {name!r} must satisfy MediaOpsPort"
        )

    src = tmp_path / "sample.mp4"
    src.write_bytes(b"fake")
    out = tmp_path / "out.mp4"

    remote_provider = ModalCloudMediaOpsProvider()
    with pytest.raises(ProviderAPIError, match="ffmpeg"):
        remote_provider.trim(src, out, start_s=0.0, end_s=1.0)
    with pytest.raises(ProviderAPIError, match="ffmpeg"):
        remote_provider.remove_silence(src, out)
    with pytest.raises(ProviderAPIError, match="ffmpeg"):
        remote_provider.restore_footage(src, out)


def test_cli_modules_route_strictly_through_registry_and_config_ports() -> None:
    import ast

    cli_dir = Path(__file__).resolve().parents[1] / "src" / "vedit" / "cli"
    forbidden_prefixes = (
        "vedit.providers.media_ops",
        "vedit.providers.transcription",
        "vedit.providers.decision",
        "vedit.providers.audio_catalog",
        "vedit.providers.video_breakdown",
        "vedit.providers.geo_imagery",
    )
    for py_file in sorted(cli_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not (
                        node.module == prefix or node.module.startswith(f"{prefix}.")
                    ), f"{py_file.name} imports concrete provider module {node.module!r}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        assert not (
                            alias.name == prefix or alias.name.startswith(f"{prefix}.")
                        ), f"{py_file.name} imports concrete provider module {alias.name!r}"


def test_cli_media_local_ops_use_ports_without_direct_vendor_imports(
    tmp_path: Path, monkeypatch
) -> None:
    from typer.testing import CliRunner

    from vedit.cli import app
    from vedit.ports.media_ops import MediaOpResult
    from vedit.providers.config import CapabilityProviderConfig

    calls: list[tuple[str, str | None]] = []

    class _FakeMediaOps:
        provider_name = "fake_ops"

        def trim(self, video_input: Path, output_path: Path, **kwargs) -> MediaOpResult:
            calls.append(("trim", kwargs.get("mode")))
            return MediaOpResult(provider="fake_ops", operation="trim", output_path=output_path)

        def remove_silence(self, speech_input: Path, output_path: Path, **kwargs) -> MediaOpResult:
            calls.append(("remove_silence", None))
            return MediaOpResult(
                provider="fake_ops", operation="remove_silence", output_path=output_path
            )

        def restore_footage(self, video_input: Path, output_path: Path, **kwargs) -> MediaOpResult:
            calls.append(("restore_footage", None))
            return MediaOpResult(
                provider="fake_ops", operation="restore_footage", output_path=output_path
            )

    class _FakeRegistry:
        def resolve(self, capability: str, provider_name: str | None = None):
            assert capability == "media_ops"
            calls.append(("resolve", provider_name))
            return _FakeMediaOps()

    monkeypatch.setattr("vedit.cli.media.build_default_registry", lambda: _FakeRegistry())
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"data")
    out = tmp_path / "out.mp4"

    runner = CliRunner()
    res_trim = runner.invoke(app, ["trim", str(src), str(out), "--start", "0", "--end", "2"])
    assert res_trim.exit_code == 0, res_trim.output
    res_sil = runner.invoke(app, ["remove-silence", str(src), str(out)])
    assert res_sil.exit_code == 0, res_sil.output
    res_rest = runner.invoke(
        app, ["restore-footage", str(src), str(out), "--provider", "custom_local"]
    )
    assert res_rest.exit_code == 0, res_rest.output

    assert ("resolve", "ffmpeg") in calls
    assert ("resolve", "custom_local") in calls
    assert [c[0] for c in calls if c[0] != "resolve"] == [
        "trim",
        "remove_silence",
        "restore_footage",
    ]

    local_cfg = CapabilityProviderConfig(primary="ffmpeg", options={"auth_type": "local"})
    assert local_cfg.has_credentials() is True
