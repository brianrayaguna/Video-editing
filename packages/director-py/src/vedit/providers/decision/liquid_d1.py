"""Liquid AI System One (`d1.2-ultra`) decision model implementation of DecisionPort."""

from __future__ import annotations

import base64
import json
import math
import shutil
import struct
import subprocess
from typing import Any

import httpx

from vedit.ports.decision import (
    DecisionAnswer,
    DecisionBatchResult,
    DecisionQuestion,
    ImageInput,
    SpatialBox,
    validate_decision_batch,
)
from vedit.providers.http import ProviderAPIError, request_with_retry, require_api_key

MAX_BODY_BYTES = 4_500_000
MAX_PATCHES_PER_REQUEST = 9_500
_DEFAULT_SCORE_CRITERIA: list[str] = [
    "Poor",
    "Weak",
    "Acceptable",
    "Strong",
    "Broadcast-grade",
]


def _image_dimensions(raw: bytes) -> tuple[int, int] | None:
    """Read `(width, height)` from PNG or JPEG headers without external image libraries."""
    if len(raw) >= 24 and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        w, h = struct.unpack(">II", raw[16:24])
        return (int(w), int(h)) if w > 0 and h > 0 else None
    if len(raw) >= 4 and raw[:2] == b"\xff\xd8":
        pos = 2
        n = len(raw)
        while pos + 4 < n:
            if raw[pos] != 0xFF:
                pos += 1
                continue
            while pos < n and raw[pos] == 0xFF:
                pos += 1
            if pos >= n:
                break
            marker = raw[pos]
            pos += 1
            if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
                continue
            if pos + 2 > n:
                break
            seg_len = struct.unpack(">H", raw[pos : pos + 2])[0]
            if seg_len < 2 or pos + seg_len > n:
                break
            if marker in (
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            ):
                if pos + 7 <= n:
                    h, w = struct.unpack(">HH", raw[pos + 3 : pos + 7])
                    return (int(w), int(h)) if w > 0 and h > 0 else None
            pos += seg_len
    return None


def _patch_count(width: int, height: int) -> int:
    return math.ceil(width / 32) * math.ceil(height / 32)


def _downscale_image_bytes(raw: bytes, *, max_dim: int) -> tuple[bytes, str] | None:
    """Downscale an image via FFmpeg so its longest side fits within `max_dim`."""
    if shutil.which("ffmpeg") is None:
        return None
    vf = (
        f"scale='if(gte(iw,ih),min(iw,{max_dim}),-2)':"
        f"'if(gt(ih,iw),min(ih,{max_dim}),-2)'"
    )
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-frames:v",
            "1",
            "-vf",
            vf,
            "-f",
            "mjpeg",
            "-q:v",
            "4",
            "pipe:1",
        ],
        input=raw,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if proc.returncode == 0 and len(proc.stdout) > 64:
        return proc.stdout, "image/jpeg"
    return None


def _read_image_bytes(img: ImageInput) -> bytes:
    if img.data is not None:
        return img.data
    if img.path is not None:
        if not img.path.is_file():
            raise FileNotFoundError(f"Decision image file not found: {img.path}")
        return img.path.read_bytes()
    raise ValueError("ImageInput requires either `path` or `data`.")


def _encode_images_with_budget(
    imgs: list[ImageInput],
    *,
    max_image_dim: int = 768,
) -> list[dict[str, str]]:
    """Encode images as base64 while auto-downscaling oversized frames for Liquid patch limits."""
    prepared: list[tuple[bytes, str]] = []
    per_image_cap = max(256, int(max_image_dim))
    if len(imgs) > 1:
        # Keep multi-image batches comfortably within Liquid's 10,000 total 32x32 patch limit.
        max_patches_each = MAX_PATCHES_PER_REQUEST // len(imgs)
        patch_dim_cap = max(256, int(math.sqrt(max_patches_each) * 32))
        per_image_cap = min(per_image_cap, patch_dim_cap)

    for img in imgs:
        raw = _read_image_bytes(img)
        ctype = img.content_type
        dims = _image_dimensions(raw)
        if dims is not None:
            w, h = dims
            if max(w, h) > per_image_cap or _patch_count(w, h) > (
                MAX_PATCHES_PER_REQUEST // max(1, len(imgs))
            ):
                scaled = _downscale_image_bytes(raw, max_dim=per_image_cap)
                if scaled is not None:
                    raw, ctype = scaled
        prepared.append((raw, ctype))

    return [
        {
            "content_type": ctype,
            "base64": base64.b64encode(raw).decode("ascii"),
        }
        for raw, ctype in prepared
    ]


def _question_to_payload(q: DecisionQuestion) -> dict[str, Any]:
    q_type = "number" if q.question_type == "number_range" else q.question_type
    item: dict[str, Any] = {
        "type": q_type,
        "instructions": q.instructions,
    }
    if q_type == "score":
        if isinstance(q.criteria, list) and len(q.criteria) >= 2:
            item["criteria"] = [str(level) for level in q.criteria[:10]]
        elif isinstance(q.criteria, dict) and len(q.criteria) >= 2:
            item["criteria"] = [str(v or k) for k, v in list(q.criteria.items())[:10]]
        else:
            item["criteria"] = list(_DEFAULT_SCORE_CRITERIA)
    elif q.criteria:
        item["criteria"] = q.criteria
    if q.multiple and q_type == "choice":
        item["multiple"] = True
    if q.value_range is not None and q.question_type in ("number", "number_range"):
        item["range"] = [q.value_range[0], q.value_range[1]]
    if q.step is not None:
        item["step"] = q.step
    if q.unit is not None:
        item["unit"] = q.unit
    if q.max_items is not None and q_type in ("spans", "boxes"):
        item["max"] = q.max_items
    return item


def extract_spatial_boxes(answer: DecisionAnswer, min_found: float = 0.5) -> list[SpatialBox]:
    """Normalize a `box` or `boxes` DecisionAnswer into typed SpatialBox coordinates."""
    raw = answer.raw
    if answer.question_type == "box":
        found = float(raw.get("found", 0.0))
        box = raw.get("box")
        if found < min_found or not isinstance(box, dict):
            return []
        return [
            SpatialBox(
                top=float(box["top"]),
                bottom=float(box["bottom"]),
                left=float(box["left"]),
                right=float(box["right"]),
                confidence=float(raw["confidence"]) if "confidence" in raw else None,
                found=found,
            )
        ]

    if answer.question_type == "boxes":
        boxes = raw.get("boxes") or []
        parsed: list[SpatialBox] = []
        for entry in boxes:
            if not isinstance(entry, dict):
                continue
            coords = entry.get("box") if isinstance(entry.get("box"), dict) else entry
            if not all(k in coords for k in ("top", "bottom", "left", "right")):
                continue
            found_val = entry.get("found")
            if found_val is not None and float(found_val) < min_found:
                continue
            parsed.append(
                SpatialBox(
                    top=float(coords["top"]),
                    bottom=float(coords["bottom"]),
                    left=float(coords["left"]),
                    right=float(coords["right"]),
                    confidence=(
                        float(entry["confidence"]) if entry.get("confidence") is not None else None
                    ),
                    found=float(found_val) if found_val is not None else None,
                )
            )
        return parsed

    return []


class LiquidDecisionProvider:
    """REST `/decisions/v1/systemone` client implementing `DecisionPort` with `d1.2-ultra`."""

    def __init__(
        self,
        options: dict[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._options = dict(options or {})
        self._endpoint = str(
            self._options.get("endpoint") or "https://api.liquid.ai/decisions/v1/systemone"
        )
        self._model = str(self._options.get("model") or "d1.2-ultra")
        self._timeout_s = float(self._options.get("timeout_s") or 60.0)
        self._max_image_dim = int(self._options.get("max_image_dim") or 768)
        self._client = client

    @property
    def provider_name(self) -> str:
        return "liquid_d1"

    def evaluate(
        self,
        *,
        state: dict[str, Any] | str,
        questions: list[DecisionQuestion],
        images: list[ImageInput] | None = None,
    ) -> DecisionBatchResult:
        imgs = images or []
        validate_decision_batch(questions, imgs)
        api_key = require_api_key(self._options, "LIQUID_API_KEY", self.provider_name)

        q_map: dict[str, dict[str, Any]] = {}
        for q in questions:
            if q.name in q_map:
                raise ValueError(f"Duplicate question name in batch: {q.name!r}")
            q_map[q.name] = _question_to_payload(q)

        body: dict[str, Any] = {
            "model": self._model,
            "state": state,
            "questions": q_map,
        }
        if imgs:
            body["images"] = _encode_images_with_budget(imgs, max_image_dim=self._max_image_dim)

        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            raise ProviderAPIError(
                self.provider_name,
                None,
                f"Decision request JSON size ({len(encoded)} bytes) exceeds 4.5 MB limit. "
                "Downscale or compress keyframes before encoding.",
            )

        own_client = self._client is None
        client = self._client or httpx.Client(timeout=self._timeout_s)
        try:
            response = request_with_retry(
                client,
                "POST",
                self._endpoint,
                provider=self.provider_name,
                secret_to_redact=api_key,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                content=encoded,
            )
        finally:
            if own_client:
                client.close()

        payload = response.json()
        q_types = {q.name: q.question_type for q in questions}
        answers: dict[str, DecisionAnswer] = {}
        for q_name, ans_data in (payload.get("answers") or {}).items():
            answers[q_name] = DecisionAnswer(
                name=q_name,
                question_type=q_types.get(q_name, ans_data.get("type", "text")),
                raw=dict(ans_data),
            )

        usage = payload.get("usage") or {}
        raw_cost = usage.get("cost")
        cost_usd = (
            float(raw_cost)
            if raw_cost is not None and not isinstance(raw_cost, bool)
            else None
        )
        return DecisionBatchResult(
            provider=self.provider_name,
            model=str(payload.get("model") or self._model),
            input_tokens=int(usage.get("input_tokens") or 0),
            answers=answers,
            cost_usd=cost_usd,
        )
