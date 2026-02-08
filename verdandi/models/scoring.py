"""Models for Step 2: Pre-Build Scoring."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


class Decision(StrEnum):
    GO = "go"
    NO_GO = "no_go"
    ITERATE = "iterate"


class ScoreComponent(BaseModel):
    """Individual scoring dimension."""

    model_config = ConfigDict(frozen=True)

    name: str
    score: int = Field(ge=0, le=100)
    weight: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class PreBuildScore(BaseStepResult):
    """Output of Step 2: quantified go/no-go decision."""

    step_name: str = "scoring"

    components: list[ScoreComponent] = Field(default_factory=list)
    total_score: int = Field(ge=0, le=100)
    decision: Decision
    reasoning: str = ""
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)

    @classmethod
    def default_components(cls) -> list[ScoreComponent]:
        """Standard scoring dimensions with weights summing to 1.0."""
        return [
            ScoreComponent(name="pain_severity", score=0, weight=0.25, reasoning=""),
            ScoreComponent(name="frequency", score=0, weight=0.15, reasoning=""),
            ScoreComponent(name="willingness_to_pay", score=0, weight=0.25, reasoning=""),
            ScoreComponent(name="competitor_gaps", score=0, weight=0.20, reasoning=""),
            ScoreComponent(name="tam_size", score=0, weight=0.15, reasoning=""),
        ]
