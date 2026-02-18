"""Models for Step 1: Deep Research."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult

# Literal type — prevents typos, enables exhaustiveness checking
ResearchDimension = Literal[
    "pain_severity",
    "market_size",
    "competitors",
    "demand_evidence",
    "willingness_to_pay",
]

RESEARCH_DIMENSIONS: tuple[ResearchDimension, ...] = (
    "pain_severity",
    "market_size",
    "competitors",
    "demand_evidence",
    "willingness_to_pay",
)


class DimensionConfidence(BaseModel):
    """Confidence assessment for a single research dimension."""

    model_config = ConfigDict(frozen=True)

    dimension: ResearchDimension
    confidence: float = Field(ge=0.0, le=1.0)
    justification: str


class ResearchGapAnalysis(BaseModel):
    """LLM output identifying gaps in current research.

    Used between research rounds to direct the next collection pass.
    Not persisted as a step result — ephemeral within the research step.
    """

    model_config = ConfigDict(frozen=True)

    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="0.0 = no evidence, 1.0 = strong multi-source evidence",
    )
    dimension_scores: list[DimensionConfidence] = Field(min_length=5, max_length=5)
    weakest_dimensions: list[ResearchDimension] = Field(
        description="Dimensions with confidence < 0.6, weakest first",
    )
    follow_up_queries: list[str] = Field(
        max_length=5,
        description="Targeted search queries to fill identified gaps",
    )
    follow_up_perplexity_question: str = Field(
        default="",
        description="Synthesized question for Perplexity about the weakest gap",
    )
    reasoning: str


class SearchResult(BaseModel):
    """A single search result from any research source."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    snippet: str = ""
    source: str = Field(description="tavily/serper/exa/perplexity/hn/firecrawl")
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class Competitor(BaseModel):
    """A competitor or alternative solution discovered during research."""

    model_config = ConfigDict(frozen=True)

    name: str
    url: str = ""
    description: str = ""
    pricing: str = Field(default="", description="Free/freemium/$X/month/enterprise")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    estimated_users: str = Field(default="", description="Rough user count estimate")
    funding: str = Field(default="", description="Known funding info")


class MarketResearch(BaseStepResult):
    """Output of Step 1: comprehensive market research for an idea."""

    step_name: str = "deep_research"

    # Market signals
    tam_estimate: str = Field(default="", description="Total addressable market estimate")
    market_growth: str = Field(default="", description="Growing/stable/declining + context")
    demand_signals: list[str] = Field(
        default_factory=list,
        description="Evidence of demand: forum posts, search volume, etc.",
    )

    # Competitors
    competitors: list[Competitor] = Field(default_factory=list)
    competitor_gaps: list[str] = Field(
        default_factory=list,
        description="Gaps or weaknesses in existing solutions",
    )

    # Audience insights
    target_audience_size: str = ""
    willingness_to_pay: str = Field(
        default="",
        description="Evidence of WTP: pricing of alternatives, survey data, etc.",
    )
    common_complaints: list[str] = Field(default_factory=list)

    # Raw data
    search_results: list[SearchResult] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    research_summary: str = ""

    # Multi-turn research metadata
    research_rounds_completed: int = Field(
        default=1,
        description="Number of research collection rounds performed",
    )
    gap_analysis: ResearchGapAnalysis | None = Field(
        default=None,
        description="Gap analysis from intermediate round (None if single-round)",
    )
