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
    data: object
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


# --- Report ---


class ReportPainPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str
    severity: int
    frequency: str
    source: str
    quote: str = ""


class ReportIdeaSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    one_liner: str
    category: str
    target_audience: str
    problem_statement: str
    novelty_score: float
    discovery_type: str
    pain_points: list[ReportPainPoint]
    existing_solutions: list[str]
    differentiation: str


class ReportCompetitor(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    url: str = ""
    description: str = ""
    pricing: str = ""
    strengths: list[str]
    weaknesses: list[str]
    estimated_users: str = ""
    funding: str = ""


class ReportMarketSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    tam_estimate: str
    market_growth: str
    target_audience_size: str
    willingness_to_pay: str
    demand_signals: list[str]
    key_findings: list[str]
    common_complaints: list[str]
    competitors: list[ReportCompetitor]
    competitor_gaps: list[str]
    research_summary: str
    source_count: int
    sources_by_api: dict[str, int]


class ReportScoreComponent(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    score: int
    weight: float
    reasoning: str = ""


class ReportScoringSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_score: int
    decision: str
    reasoning: str = ""
    components: list[ReportScoreComponent]
    risks: list[str]
    opportunities: list[str]


class ReportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    experiment_id: int
    status: str
    idea: ReportIdeaSection | None = None
    market_research: ReportMarketSection | None = None
    scoring: ReportScoringSection | None = None


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
    strategy: str | None = None  # "disruption", "moonshot", or None for auto


class RunPipelineRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dry_run: bool = False
    stop_after: int | None = None
