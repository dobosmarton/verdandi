"""Base model for all step results."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BaseStepResult(BaseModel):
    """Common fields for every pipeline step result."""

    model_config = ConfigDict(frozen=True)

    experiment_id: int
    step_name: str
    created_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    worker_id: str = ""
