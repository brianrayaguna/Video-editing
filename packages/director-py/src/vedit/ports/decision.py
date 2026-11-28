"""Capability port for non-generative calibrated decision & spatial grounding models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

QuestionType = Literal[
    "noul",
    "choice",
    "score",
    "text",
    "number",
    "number_range",
    "date",
    "spans",
    "box",
    "boxes",
]


@dataclass(slots=True)
class ImageInput:
    """Reference to an image frame (local path or raw encoded bytes)."""

    content_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"
    path: Path | None = None
    data: bytes | None = None


@dataclass(slots=True)
class DecisionQuestion:
    name: str
    question_type: QuestionType
    instructions: str
    criteria: dict[str, str] | list[str] | None = None
    multiple: bool = False
    value_range: tuple[float, float] | None = None
    step: float | None = None
    unit: str | None = None
    max_items: int | None = None


@dataclass(slots=True)
class SpatialBox:
    top: float
    bottom: float
    left: float
    right: float
    confidence: float | None = None
    found: float | None = None


@dataclass(slots=True)
class DecisionAnswer:
    name: str
    question_type: QuestionType
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence(self) -> float | None:
        val = self.raw.get("confidence")
        if val is None or isinstance(val, bool):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @property
    def noul_prob(self) -> float | None:
        val = self.raw.get("noul")
        if val is None or isinstance(val, bool):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @property
    def choice_value(self) -> str | None:
        val = self.raw.get("choice")
        if val is None:
            val = self.raw.get("value")
        return str(val).strip() if val is not None else None

    @property
    def score_value(self) -> float | None:
        val = self.raw.get("score")
        if val is None:
            val = self.raw.get("value")
        if val is None or isinstance(val, bool):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @property
    def spans(self) -> list[dict[str, Any]]:
        raw_spans = self.raw.get("spans")
        if not isinstance(raw_spans, list):
            return []
        return [dict(item) for item in raw_spans if isinstance(item, dict)]


@dataclass(slots=True)
class DecisionBatchResult:
    provider: str
    model: str
    input_tokens: int
    answers: dict[str, DecisionAnswer]
    cost_usd: float | None = None


def validate_decision_batch(
    questions: list[DecisionQuestion],
    images: list[ImageInput],
    *,
    max_questions: int = 128,
    max_images: int = 8,
) -> None:
    """Enforce hard payload bounds before dispatching a decision batch."""
    if not questions:
        raise ValueError("Decision batch must contain at least one question.")
    if len(questions) > max_questions:
        raise ValueError(f"Too many questions in batch: {len(questions)} > {max_questions}.")
    if len(images) > max_images:
        raise ValueError(f"Too many images in batch: {len(images)} > {max_images}.")
    has_box = any(q.question_type in ("box", "boxes") for q in questions)
    if has_box and len(images) != 1:
        raise ValueError(
            "Spatial grounding questions ('box'/'boxes') require exactly 1 image per request."
        )


@runtime_checkable
class DecisionPort(Protocol):
    """Provider-agnostic calibrated decision, span extraction, and spatial grounding port."""

    @property
    def provider_name(self) -> str: ...

    def evaluate(
        self,
        *,
        state: dict[str, Any] | str,
        questions: list[DecisionQuestion],
        images: list[ImageInput] | None = None,
    ) -> DecisionBatchResult: ...
