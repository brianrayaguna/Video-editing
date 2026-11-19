"""Capability port for forensic reference-video breakdown (strictly non-generative)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from vedit.models import VideoBreakdownResult


@dataclass(slots=True)
class BreakdownOptions:
    """Configuration options for forensic video breakdown."""

    use_vlm: bool = False
    prepare_review: bool = True
    ocr: bool = True
    stems: bool = True
    packaging: bool = True
    asr: bool = False
    lang: Literal["en", "zh"] = "en"
    ocr_lang: str | None = None
    env_file: Path | None = None
    workers: int = 3


@dataclass(slots=True)
class BreakdownReviewBundle:
    """Artifacts prepared for visual review by a multimodal AI directing client."""

    output_dir: Path
    tasks_path: Path
    answers_path: Path
    total_shots: int
    high_priority_shots: int
    videomd_path: Path | None = None
    storyboard_path: Path | None = None


@dataclass(slots=True)
class BreakdownSurveyStep:
    """One step of a visual-first contact-sheet survey pass."""

    output_dir: Path
    status: str
    round_index: int | None = None
    images: list[Path] = field(default_factory=list)
    waiting_files: list[Path] = field(default_factory=list)
    timeline_path: Path | None = None


@runtime_checkable
class VideoBreakdownPort(Protocol):
    """Provider-agnostic forensic breakdown port.

    Exposes shot/transition forensics, audio/packaging extraction, and visual review
    reconciliation only. Generative video remake or synthesis methods are intentionally
    omitted by architectural contract.
    """

    @property
    def provider_name(self) -> str: ...

    def survey(
        self,
        media_path: Path,
        output_dir: Path,
    ) -> BreakdownSurveyStep: ...

    def analyze(
        self,
        media_path: Path,
        output_dir: Path,
        options: BreakdownOptions | None = None,
    ) -> VideoBreakdownResult: ...

    def prepare_review(
        self,
        output_dir: Path,
        *,
        force: bool = False,
    ) -> BreakdownReviewBundle: ...

    def apply_review(
        self,
        output_dir: Path,
        *,
        reviewer: str,
        lang: Literal["en", "zh"] = "en",
    ) -> VideoBreakdownResult: ...

    def load_breakdown(
        self,
        path: Path,
    ) -> VideoBreakdownResult: ...
