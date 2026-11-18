"""Liquid AI System One decision model implementation of DecisionPort."""

from __future__ import annotations

import base64
import json
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


def _encode_image(img: ImageInput) -> dict[str, str]:
    if img.data is not None:
        raw_bytes = img.data
    elif img.path is not None:
        if not img.path.is_file():
            raise FileNotFoundError(f"Decision image file not found: {img.path}")
        raw_bytes = img.path.read_bytes()
    else:
        raise ValueError("ImageInput requires either `path` or `data`.")

    return {
        "content_type": img.content_type,
        "base64": base64.b64encode(raw_bytes).decode("ascii"),
    }


def _question_to_payload(q: DecisionQuestion) -> dict[str, Any]:
    q_type = "number" if q.question_type == "number_range" else q.question_type
    item: dict[str, Any] = {
        "name": q.name,
        "type": q_type,
        "instructions": q.instructions,
    }
    if q.criteria:
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
        return [
            SpatialBox(
                top=float(b["top"]),
                bottom=float(b["bottom"]),
                left=float(b["left"]),
                right=float(b["right"]),
            )
            for b in boxes
            if isinstance(b, dict)
        ]

    return []


class LiquidDecisionProvider:
    """REST `/decisions/v1/systemone` client implementing `DecisionPort`."""

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

        body: dict[str, Any] = {
            "model": self._model,
            "state": state,
            "questions": [_question_to_payload(q) for q in questions],
        }
        if imgs:
            body["images"] = [_encode_image(img) for img in imgs]

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
                question_type=q_types.get(q_name, ans_data.get("type", "noul")),
                raw=dict(ans_data),
            )

        usage = payload.get("usage") or {}
        return DecisionBatchResult(
            provider=self.provider_name,
            model=str(payload.get("model") or self._model),
            input_tokens=int(usage.get("input_tokens") or 0),
            answers=answers,
        )
