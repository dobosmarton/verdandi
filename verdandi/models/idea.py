"""Models for Step 0: Idea Discovery."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.base import BaseStepResult

# ---------------------------------------------------------------------------
# Discovery type enum
# ---------------------------------------------------------------------------


class DiscoveryType(StrEnum):
    """Which discovery agent lens found this idea."""

    DISRUPTION = "disruption"
    MOONSHOT = "moonshot"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class PainPoint(BaseModel):
    """A specific user pain point discovered during research."""

    model_config = ConfigDict(frozen=True)

    description: str
    severity: int = Field(ge=1, le=10, description="1=mild annoyance, 10=critical blocker")
    frequency: str = Field(description="How often users encounter this: daily/weekly/monthly")
    source: str = Field(description="Where this was discovered: HN/Reddit/forum/etc")
    quote: str = Field(default="", description="Direct quote from a user if available")


# ---------------------------------------------------------------------------
# Phase 1 outputs — Disruption Agent
# ---------------------------------------------------------------------------


class ComplaintEvidence(BaseModel):
    """A single piece of evidence for a problem area."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="e.g. 'Reddit r/accounting', 'HN', 'G2 review'")
    quote: str = Field(description="Direct quote or paraphrase of the complaint")
    url: str = Field(default="", description="Source URL if available")
    upvotes: int = Field(default=0, ge=0, description="Engagement signal (0 if unknown)")


class ProblemReport(BaseModel):
    """Phase 1 output of the Disruption Agent: raw problem evidence."""

    model_config = ConfigDict(frozen=True)

    problem_area: str = Field(
        description="Specific problem area, e.g. 'Invoice reconciliation for freelance accountants'"
    )
    user_group: str = Field(
        description="Specific user group, e.g. 'Freelance accountants with 10-50 clients'"
    )
    workflow_description: str = Field(description="The specific broken workflow or manual process")
    pain_severity: int = Field(
        ge=1, le=10, description="Aggregate severity assessment (1=mild, 10=critical)"
    )
    pain_frequency: str = Field(description="How often pain occurs: daily/weekly/monthly")
    complaint_count: int = Field(ge=0, description="Number of distinct complaints found")
    evidence: list[ComplaintEvidence] = Field(default_factory=list)
    existing_tools: list[str] = Field(
        default_factory=list,
        description="What people currently use (even if broken)",
    )
    why_existing_tools_fail: str = Field(
        default="", description="Why current tools don't solve the problem"
    )
    discovery_type: DiscoveryType = Field(default=DiscoveryType.DISRUPTION)


# ---------------------------------------------------------------------------
# Phase 1 outputs — Moonshot Agent
# ---------------------------------------------------------------------------


class TrendSignal(BaseModel):
    """A signal about an emerging technology or capability."""

    model_config = ConfigDict(frozen=True)

    description: str = Field(
        description="e.g. 'Multimodal AI models can now process video in real-time'"
    )
    source: str = Field(description="e.g. 'OpenAI blog', 'arXiv', 'TechCrunch'")
    url: str = Field(default="", description="Source URL if available")
    recency: str = Field(default="", description="How old: '2 months', '6 months', etc.")


class OpportunityReport(BaseModel):
    """Phase 1 output of the Moonshot Agent: future-oriented opportunity."""

    model_config = ConfigDict(frozen=True)

    capability_or_trend: str = Field(
        description="The new capability or trend, e.g. 'Real-time video understanding via multimodal AI'"
    )
    future_scenario: str = Field(
        description="Concrete future scenario, e.g. 'In 2-3 years, every creator will have AI editing...'"
    )
    target_user_group: str = Field(
        description="Specific user group, e.g. 'YouTube creators with 10K-100K subscribers'"
    )
    why_now: str = Field(description="What changed recently that makes this possible")
    signals: list[TrendSignal] = Field(default_factory=list)
    existing_attempts: list[str] = Field(default_factory=list, description="Early movers if any")
    moat_potential: str = Field(default="", description="Why this could be defensible")
    discovery_type: DiscoveryType = Field(default=DiscoveryType.MOONSHOT)


# ---------------------------------------------------------------------------
# Phase 2 output — IdeaCandidate (both agent types)
# ---------------------------------------------------------------------------


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
    discovery_type: DiscoveryType = Field(
        default=DiscoveryType.DISRUPTION,
        description="Which discovery agent lens found this idea",
    )
    discovery_report_json: str = Field(
        default="",
        description="Serialized Phase 1 report (ProblemReport or OpportunityReport)",
    )
