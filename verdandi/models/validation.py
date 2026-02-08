"""Models for Step 10: Monitor and Validate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class ValidationDecision(StrEnum):
    GO = "go"
    ITERATE = "iterate"
    NO_GO = "no_go"
    INSUFFICIENT_DATA = "insufficient_data"


class MetricsSnapshot(BaseModel):
    """Point-in-time analytics metrics."""

    model_config = ConfigDict(frozen=True)

    total_visitors: int = 0
    unique_visitors: int = 0
    pageviews: int = 0
    bounce_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    avg_time_on_page_seconds: float = 0.0
    cta_clicks: int = 0
    cta_click_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    email_signups: int = 0
    email_signup_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    referral_sources: dict[str, int] = Field(default_factory=dict)


class ValidationReport(BaseStepResult):
    """Output of Step 10: final validation assessment."""

    step_name: str = "validation"

    metrics: MetricsSnapshot = Field(default_factory=MetricsSnapshot)
    decision: ValidationDecision = ValidationDecision.INSUFFICIENT_DATA
    reasoning: str = ""
    days_monitored: int = 0
    snapshots_collected: int = 0

    # Thresholds used for this decision
    go_email_signup_rate: float = 10.0
    nogo_email_signup_rate: float = 3.0
    max_bounce_rate: float = 80.0
    min_visitors_required: int = 200

    # Recommendations
    iterate_suggestions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
