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


class CouncilMemberVote(BaseModel):
    """A single council member's independent scoring vote."""

    model_config = ConfigDict(frozen=True)

    provider_name: str
    model_name: str
    components: list[ScoreComponent] = Field(default_factory=list)
    base_score: int = Field(ge=0, le=100)
    decision: Decision
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""


class CouncilResult(BaseModel):
    """Aggregated result from the Agent Council."""

    model_config = ConfigDict(frozen=True)

    votes: list[CouncilMemberVote] = Field(default_factory=list)
    aggregated_components: list[ScoreComponent] = Field(default_factory=list)
    total_score: int = Field(ge=0, le=100)
    decision: Decision
    reasoning: str = ""
    aggregated_risks: list[str] = Field(default_factory=list)
    aggregated_opportunities: list[str] = Field(default_factory=list)


class DimensionDissent(BaseModel):
    """A single scoring dimension where council members disagreed."""

    model_config = ConfigDict(frozen=True)

    dimension: str
    scores_by_provider: dict[str, int]
    spread: int
    median_score: int
    reasoning_excerpts: list[str] = Field(default_factory=list)


class DissentResolutionRound(BaseModel):
    """Record of one follow-up research + re-score cycle."""

    model_config = ConfigDict(frozen=True)

    round_number: int
    contested_dimensions: list[str]
    followup_queries: list[str]
    new_sources_count: int
    score_before: int
    score_after: int
    decision_changed: bool


class DissentAnalysis(BaseModel):
    """Full dissent analysis attached to PreBuildScore."""

    model_config = ConfigDict(frozen=True)

    dissent_detected: bool = False
    dimension_dissents: list[DimensionDissent] = Field(default_factory=list)
    resolution_rounds: list[DissentResolutionRound] = Field(default_factory=list)
    decision_flipped: bool = False
    initial_score: int = 0
    final_score: int = 0


class PreBuildScore(BaseStepResult):
    """Output of Step 2: quantified go/no-go decision."""

    step_name: str = "scoring"

    components: list[ScoreComponent] = Field(default_factory=list)
    total_score: int = Field(ge=0, le=100)
    decision: Decision
    reasoning: str = ""
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    council_votes: list[CouncilMemberVote] = Field(default_factory=list)
    dissent_analysis: DissentAnalysis | None = None

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
