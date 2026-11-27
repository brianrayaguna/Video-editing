"""Durable job checkpointing and per-stage attribution telemetry."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class StageMetric(BaseModel):
    stage: str
    status: Literal["completed", "failed", "skipped_cached"]
    idempotency_key: str
    wall_ms: int = Field(ge=0)
    provider: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    estimated_usd: float = Field(default=0.0, ge=0.0)
    output_artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    recorded_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class JobCheckpoint(BaseModel):
    """Filesystem-first durable checkpoint allowing step-level resume and cost attribution."""

    job_id: str
    project_id: str
    brand_id: str
    platform_target_id: str
    completed_stages: dict[str, StageMetric] = Field(default_factory=dict)
    total_wall_ms: int = 0
    total_estimated_usd: float = 0.0

    @classmethod
    def load_or_create(
        cls,
        state_path: Path,
        *,
        job_id: str,
        project_id: str,
        brand_id: str,
        platform_target_id: str,
    ) -> JobCheckpoint:
        if state_path.is_file():
            loaded = cls.model_validate_json(state_path.read_text(encoding="utf-8"))
            if (
                loaded.job_id == job_id
                and loaded.project_id == project_id
                and loaded.brand_id == brand_id
                and loaded.platform_target_id == platform_target_id
            ):
                return loaded
        return cls(
            job_id=job_id,
            project_id=project_id,
            brand_id=brand_id,
            platform_target_id=platform_target_id,
        )

    def save(self, state_path: Path) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump_json(indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(state_path.parent),
            prefix=f".{state_path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                fp.write(payload)
            os.replace(tmp_name, state_path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def is_stage_done(self, stage: str, idempotency_key: str) -> bool:
        metric = self.completed_stages.get(stage)
        return (
            metric is not None
            and metric.status == "completed"
            and metric.idempotency_key == idempotency_key
        )

    def record(self, metric: StageMetric) -> None:
        self.completed_stages[metric.stage] = metric
        self.total_wall_ms = sum(m.wall_ms for m in self.completed_stages.values())
        self.total_estimated_usd = round(
            sum(m.estimated_usd for m in self.completed_stages.values()), 6
        )

    @contextmanager
    def track_stage(
        self,
        stage: str,
        idempotency_key: str,
        *,
        state_path: Path | None = None,
        provider: str | None = None,
    ) -> Iterator[dict[str, object]]:
        """Time a pipeline step and persist telemetry on exit."""
        meta: dict[str, object] = {
            "input_tokens": 0,
            "estimated_usd": 0.0,
            "output_artifacts": [],
        }
        t0 = time.perf_counter()
        try:
            yield meta
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self.record(
                StageMetric(
                    stage=stage,
                    status="failed",
                    idempotency_key=idempotency_key,
                    wall_ms=elapsed_ms,
                    provider=provider,
                    error=str(exc),
                )
            )
            if state_path is not None:
                self.save(state_path)
            raise
        else:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self.record(
                StageMetric(
                    stage=stage,
                    status="completed",
                    idempotency_key=idempotency_key,
                    wall_ms=elapsed_ms,
                    provider=provider,
                    input_tokens=int(meta.get("input_tokens", 0)),
                    estimated_usd=float(meta.get("estimated_usd", 0.0)),
                    output_artifacts=list(meta.get("output_artifacts", [])),
                )
            )
            if state_path is not None:
                self.save(state_path)


def compute_idempotency_key(**inputs: object) -> str:
    """Deterministic SHA-256 hash over canonical JSON stage inputs."""
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
