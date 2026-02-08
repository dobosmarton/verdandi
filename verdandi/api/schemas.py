"""API request/response schemas (separate from domain models)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# --- Responses ---


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None
    idea_title: str
    idea_summary: str
    status: str
    current_step: int
    worker_id: str
    reviewed_by: str
    review_notes: str
    reviewed_at: str | None
    created_at: str
    updated_at: str


class ExperimentListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiments: list[ExperimentResponse]
    total: int


class StepResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    experiment_id: int
    step_name: str
    step_number: int
    data: dict
    worker_id: str
    created_at: str


class LogEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    experiment_id: int | None
    step_name: str
    event: str
    message: str
    worker_id: str
    created_at: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    version: str
    db_connected: bool
    checks: dict[str, bool] = Field(default_factory=dict)


class ConfigCheckResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    configured: dict[str, bool]


class ReservationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    topic_key: str
    topic_description: str
    worker_id: str
    reserved_at: str | None = None
    expires_at: str | None = None
    status: str | None = None


class ActionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str
    task_id: str | None = None


# --- Requests ---


class ReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    approved: bool
    notes: str = ""
    reviewed_by: str = "api"


class DiscoverRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_ideas: int = Field(default=3, ge=1, le=20)
    dry_run: bool = False


class RunPipelineRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dry_run: bool = False
