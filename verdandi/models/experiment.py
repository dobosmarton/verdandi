"""Experiment model — central state for a validation pipeline run."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExperimentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"
    NO_GO = "no_go"


class Experiment(BaseModel):
    """Represents one product validation experiment."""

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    idea_title: str = ""
    idea_summary: str = ""
    status: ExperimentStatus = ExperimentStatus.PENDING
    current_step: int = 0
    worker_id: str = ""

    # Review
    reviewed_by: str = ""
    review_notes: str = ""
    reviewed_at: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
