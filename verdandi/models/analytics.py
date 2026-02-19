"""Analytics domain models for historical experiment data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProviderReliabilityStats(BaseModel):
    """Reliability statistics for a single research provider."""

    model_config = ConfigDict(frozen=True)

    provider: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float = Field(ge=0.0, le=1.0)


class ScoreDistributionBucket(BaseModel):
    """A single bucket in the score histogram."""

    model_config = ConfigDict(frozen=True)

    bucket_label: str  # e.g. "0-20", "20-40", …
    low: int
    high: int
    count: int


class ScoreTrendPoint(BaseModel):
    """Average score for experiments created on a given date."""

    model_config = ConfigDict(frozen=True)

    date: str  # ISO date "YYYY-MM-DD"
    avg_score: float
    count: int


class StepDurationStats(BaseModel):
    """Throughput / duration statistics for a single pipeline step."""

    model_config = ConfigDict(frozen=True)

    step_name: str
    step_number: int
    total_executions: int
    experiments_with_step: int


class OverviewStats(BaseModel):
    """High-level summary of all experiments."""

    model_config = ConfigDict(frozen=True)

    total_experiments: int
    by_status: dict[str, int]
    go_rate: float = Field(ge=0.0, le=1.0, description="Fraction of scored experiments that were GO")
    avg_score: float | None = Field(default=None, description="Mean total_score across scored experiments")
    experiments_with_score: int
    date_from: str | None = None
    date_to: str | None = None


class ProviderAnalytics(BaseModel):
    """Provider reliability analytics response."""

    model_config = ConfigDict(frozen=True)

    providers: list[ProviderReliabilityStats]
    date_from: str | None = None
    date_to: str | None = None


class ScoreAnalytics(BaseModel):
    """Score distribution and trend analytics response."""

    model_config = ConfigDict(frozen=True)

    distribution: list[ScoreDistributionBucket]
    trend: list[ScoreTrendPoint]
    decision_counts: dict[str, int]
    date_from: str | None = None
    date_to: str | None = None


class PipelineAnalytics(BaseModel):
    """Pipeline throughput and step completion analytics response."""

    model_config = ConfigDict(frozen=True)

    steps: list[StepDurationStats]
    total_experiments: int
    completed_experiments: int
    completion_rate: float = Field(ge=0.0, le=1.0)
    date_from: str | None = None
    date_to: str | None = None
