"""Offline mocked HTTP tests for capability provider adapters and OpenEdit OAuth handling."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from vedit.contracts import validate_against_contract
from vedit.ports.decision import DecisionQuestion, ImageInput
from vedit.ports.media_ops import GenerativeVideoProhibitedError
from vedit.ports.transcription import TranscriptionOptions
from vedit.providers.audio_catalog.epidemic import EpidemicAudioCatalogProvider
from vedit.providers.decision.liquid_d1 import LiquidDecisionProvider, extract_spatial_boxes
from vedit.providers.env import load_dotenv_safe, upsert_env_var
from vedit.providers.http import ProviderAPIError
from vedit.providers.media_ops.ffmpeg_local import FfmpegMediaOpsProvider
from vedit.providers.media_ops.veed import VeedMediaOpsProvider
from vedit.providers.registry import build_default_registry
from vedit.providers.transcription.veed import VeedTranscriptionProvider
from vedit.providers.transcription.xai import XaiTranscriptionProvider
from vedit.providers.veed_oauth import VeedOAuthTokenStore


def test_builtin_registry_marks_all_providers_implemented() -> None:
    registry = build_default_registry()
    report = registry.status_report()
    assert {s["name"] for s in report["transcription"]["registered"]} == {
        "veed",
        "xai",
    }
    assert {s["name"] for s in report["media_ops"]["registered"]} == {
        "ffmpeg",
        "modal_cloud",
        "veed",
    }
    for capability in ("transcription", "decision", "media_ops", "audio_catalog"):
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


def test_openedit_oauth_store_refreshes_expired_token_atomically(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("VEED_ACCESS_TOKEN", raising=False)
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps(
            {
                "accessToken": "old-access",
                "refreshToken": "refresh-123",
                "expiresAt": 1000,
                "origin": "https://www.veed.io",
                "clientId": "client-xyz",
                "tokenEndpoint": "https://www.veed.io/api/v1/oauth2/token",
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://www.veed.io/api/v1/oauth2/token"
        body = parse_qs(request.read().decode("utf-8"))
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["refresh-123"]
        assert body["client_id"] == ["client-xyz"]
        return httpx.Response(
            200,
            json={
                "access_token": "fresh-access-999",
                "refresh_token": "refresh-456",
                "expires_in": 3600,
            },
        )

    store = VeedOAuthTokenStore(
        token_path=token_file,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        now_ms_fn=lambda: 500_000,
    )
    resolved = store.resolve_token()
    assert resolved == "fresh-access-999"

    persisted = json.loads(token_file.read_text(encoding="utf-8"))
    assert persisted["accessToken"] == "fresh-access-999"
    assert persisted["refreshToken"] == "refresh-456"
    assert (token_file.stat().st_mode & 0o777) == 0o600


def test_xai_transcription_multipart_order_itn_and_contract(tmp_path: Path) -> None:
    audio_file = tmp_path / "speech.wav"
    audio_file.write_bytes(b"RIFF0000WAVEfmt ")

    captured_body = b""
    captured_auth = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body, captured_auth
        captured_auth = request.headers["Authorization"]
        captured_body = request.read()
        return httpx.Response(
            200,
            json={
                "text": "Halo um dunia.",
                "language": "id",
                "duration": 2.5,
                "words": [
                    {"text": "Halo", "start": 0.1, "end": 0.5, "speaker": 0},
                    {"text": "um", "start": 0.55, "end": 0.7, "speaker": 0},
                    {"text": "dunia.", "start": 0.8, "end": 1.3, "speaker": 0},
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    stt = XaiTranscriptionProvider({"api_key": "xai-secret-token"}, client=client)
    transcript = stt.transcribe(
        audio_file,
        TranscriptionOptions(language="id", diarize=True, include_fillers=True, keyterms=["Vedit"]),
    )

    assert captured_auth == "Bearer xai-secret-token"
    assert captured_body.rfind(b'name="keyterm"') < captured_body.rfind(b'name="file"')
    assert b'name="format"' not in captured_body
    assert transcript.words[1].is_filler is True
    assert validate_against_contract(
        transcript.model_dump(exclude_none=True), "transcript.schema.json"
    ) == []


def test_veed_oauth_transcription_uploads_and_maps_chronologically(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEED_ACCESS_TOKEN", "veed-oauth-jwt")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"mp4-bytes")

    asset_polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal asset_polls
        url = str(request.url)
        if url.endswith("/api/v1/workspace") and request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "ws-1"}]})
        if url.endswith("/api/v1/asset") and request.method == "POST":
            return httpx.Response(
                200,
                json={"data": {"asset": {"id": "ast-1"}, "url": "https://gcs.example/upload/ast-1"}},
            )
        if url == "https://gcs.example/upload/ast-1" and request.method == "PUT":
            return httpx.Response(200)
        if url.endswith("/api/v1/asset/ast-1") and request.method == "GET":
            asset_polls += 1
            if asset_polls == 1:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={"data": {"id": "ast-1", "uploadState": "UPLOADED", "cdnUrl": "https://cdn.veed.test/ast-1.mp4"}},
            )
        if url.endswith("/api/v1/subtitles/assets/ast-1/transcribe") and request.method == "POST":
            return httpx.Response(200, json={"data": {"id": "sub-1", "status": "pending"}})
        if url.endswith("/api/v1/subtitles/sub-1") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "sub-1",
                        "status": "active",
                        "subtitles": {
                            "b": {"from": 1.0, "to": 1.6, "words": [{"value": "world."}]},
                            "a": {"from": 0.2, "to": 0.8, "words": [{"value": "Hello"}]},
                        },
                    }
                },
            )
        return httpx.Response(404)

    stt = VeedTranscriptionProvider(
        {"poll_interval_s": 0.0},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    transcript = stt.transcribe(video, TranscriptionOptions(language="en"))
    assert transcript.provider == "veed"
    assert [w.text for w in transcript.words] == ["Hello", "world."]
    assert transcript.words[0].start_s == pytest.approx(0.2)
    assert validate_against_contract(
        transcript.model_dump(exclude_none=True), "transcript.schema.json"
    ) == []


def test_xai_transcription_redacts_secret_in_error(tmp_path: Path) -> None:
    audio_file = tmp_path / "speech.wav"
    audio_file.write_bytes(b"RIFF")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Invalid token sk-super-secret-999")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    stt = XaiTranscriptionProvider({"api_key": "sk-super-secret-999"}, client=client)
    with pytest.raises(ProviderAPIError) as exc_info:
        stt.transcribe(audio_file)
    assert "sk-super-secret-999" not in str(exc_info.value)
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


def test_veed_oauth_remove_background_and_blocks_generative(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(GenerativeVideoProhibitedError):
        VeedMediaOpsProvider({"allow_generative_video": True})

    monkeypatch.setenv("VEED_ACCESS_TOKEN", "veed-oauth-jwt")
    src = tmp_path / "talking.mp4"
    src.write_bytes(b"mp4-data")
    out = tmp_path / "matte.mp4"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/api/v1/workspace"):
            return httpx.Response(200, json=[{"id": "ws-1"}])
        if url.endswith("/api/v1/workspace/ws-1/space/default"):
            return httpx.Response(200, json={"id": "sp-1"})
        if url.endswith("/api/v1/project") and request.method == "POST":
            return httpx.Response(200, json={"id": "proj-1"})
        if url.endswith("/api/v1/asset") and request.method == "POST":
            return httpx.Response(
                200,
                json={"asset": {"id": "ast-2"}, "url": "https://gcs.example/upload/ast-2"},
            )
        if url == "https://gcs.example/upload/ast-2" and request.method == "PUT":
            return httpx.Response(200)
        if url.endswith("/api/v1/asset/ast-2"):
            return httpx.Response(
                200,
                json={"id": "ast-2", "uploadState": "UPLOADED", "cdnUrl": "https://cdn.veed.test/ast-2.mp4"},
            )
        if url.endswith("/api/v1/remove-background") and request.method == "POST":
            return httpx.Response(200, json={"workflowId": "wf-1"})
        if "/api/v1/remove-background/status" in url:
            return httpx.Response(
                200,
                json={
                    "statuses": [
                        {
                            "workflowId": "wf-1",
                            "projectId": "proj-1",
                            "status": "COMPLETED",
                            "result": {"url": "https://cdn.veed.test/matte.mp4"},
                        }
                    ]
                },
            )
        if url == "https://cdn.veed.test/matte.mp4":
            return httpx.Response(200, content=b"matte-video-bytes")
        return httpx.Response(404)

    veed = VeedMediaOpsProvider(
        {"poll_interval_s": 0.0},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    res = veed.remove_background(src, out)
    assert res.output_path == out
    assert out.read_bytes() == b"matte-video-bytes"


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
            "transcription": CapabilityProviderConfig(
                primary="primary",
                fallback=["backup"],
                options={},
            )
        }
    )
    reg = ProviderRegistry(config=cfg)
    reg.register(ProviderSpec("transcription", "primary", _FailProvider))
    reg.register(ProviderSpec("transcription", "backup", _OkProvider))

    value = reg.call_with_fallback("transcription", lambda p: p.ping())
    assert value == "recovered"
