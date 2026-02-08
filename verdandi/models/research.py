"""Models for Step 1: Deep Research."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult


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
