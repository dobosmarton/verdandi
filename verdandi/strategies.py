"""Discovery strategy definitions for the dual-agent discovery system.

Each strategy encapsulates the complete "personality" of a discovery agent:
research queries, LLM prompts (Phase 1 discovery + Phase 2 synthesis),
source preferences, and scoring guidance.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.idea import DiscoveryType


class DiscoveryStrategy(BaseModel):
    """Configuration for a specialized discovery agent type."""

    model_config = ConfigDict(frozen=True)

    discovery_type: DiscoveryType
    name: str = Field(description="Human-readable label for logging")

    # Phase 1: Discovery — research queries
    discovery_queries: list[str] = Field(description="Search queries for ResearchCollector")
    discovery_perplexity_question: str = Field(
        description="Perplexity synthesis question for Phase 1"
    )

    # Phase 1: Discovery — LLM prompts
    discovery_system_prompt: str = Field(
        description="System prompt for Phase 1 (discovery) LLM call"
    )
    discovery_user_preamble: str = Field(
        default="",
        description="Prepended to Phase 1 user prompt before research data",
    )

    # Phase 2: Synthesis — LLM prompt
    synthesis_system_prompt: str = Field(
        description="System prompt for Phase 2 (idea synthesis) LLM call"
    )

    # Source preferences
    prioritize_reddit: bool = Field(default=True, description="Whether to include Reddit searches")
    prioritize_hn: bool = Field(default=True, description="Whether to include HN comments")
    prioritize_twitter: bool = Field(
        default=True, description="Whether to include Twitter/X searches"
    )

    # Scoring guidance (used by Step 2)
    scoring_guidance: str = Field(default="", description="Guidance appended to scoring prompt")

    # Phase 1 output model name (for dispatch)
    discovery_output_model: str = Field(description="'ProblemReport' or 'OpportunityReport'")
