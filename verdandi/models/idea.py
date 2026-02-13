"""Models for Step 0: Idea Discovery."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class PainPoint(BaseModel):
    """A specific user pain point discovered during research."""

    model_config = ConfigDict(frozen=True)

    description: str
    severity: int = Field(ge=1, le=10, description="1=mild annoyance, 10=critical blocker")
    frequency: str = Field(description="How often users encounter this: daily/weekly/monthly")
    source: str = Field(description="Where this was discovered: HN/Reddit/forum/etc")
    quote: str = Field(default="", description="Direct quote from a user if available")


class IdeaCandidate(BaseStepResult):
    """Output of Step 0: a product idea worth investigating."""

    step_name: str = "idea_discovery"

    title: str
    one_liner: str = Field(description="Single sentence elevator pitch")
    problem_statement: str
    target_audience: str
    category: str = Field(description="e.g. developer-tools, email-marketing, analytics")
    pain_points: list[PainPoint] = Field(default_factory=list)
    existing_solutions: list[str] = Field(
        default_factory=list,
        description="Known competitors or workarounds",
    )
    differentiation: str = Field(
        default="",
        description="How this idea differs from existing solutions",
    )
    source_urls: list[str] = Field(default_factory=list)
    novelty_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Semantic novelty vs previous ideas (1.0=completely novel)",
    )
