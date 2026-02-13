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

    # Scoring guidance (used by Step 2)
    scoring_guidance: str = Field(default="", description="Guidance appended to scoring prompt")

    # Phase 1 output model name (for dispatch)
    discovery_output_model: str = Field(description="'ProblemReport' or 'OpportunityReport'")


# ---------------------------------------------------------------------------
# Disruption Agent — problem-first discovery
# ---------------------------------------------------------------------------

DISRUPTION_STRATEGY = DiscoveryStrategy(
    discovery_type=DiscoveryType.DISRUPTION,
    name="Disruption Agent",
    discovery_queries=[
        "most common workflow complaints professionals 2025 2026",
        "cumbersome manual processes people hate doing at work",
        "broken software tools specific professions complain about",
        "repetitive boring tasks specific user groups wish automated",
    ],
    discovery_perplexity_question=(
        "What specific workflows or processes do professionals in niche "
        "industries constantly complain about being manual, cumbersome, "
        "or broken? Give concrete examples with the specific user group "
        "and the painful workflow."
    ),
    discovery_system_prompt=(
        "You are a problem discovery agent. Your ONLY job is to find "
        "problems — specific workflows, processes, or tasks that people "
        "complain about. You are NOT proposing solutions.\n\n"
        "Focus on:\n"
        "1. Complaints from a SPECIFIC user group (one profession, one role, "
        "one type of worker — not 'businesses' or 'developers' broadly)\n"
        "2. Problems that MULTIPLE people mention independently — volume of "
        "complaints is a strong signal\n"
        "3. Workflows that are manual, cumbersome, boring, or error-prone\n"
        "4. Existing tools that people USE but HATE — broken flows, "
        "missing features, poor UX\n\n"
        "## Sector signals (derived from startup cohort analysis)\n\n"
        "Prioritize problems in these high-opportunity areas:\n"
        "- High-friction regulated industries (legal, healthcare, finance, "
        "insurance, compliance) — these consistently produce outsized outcomes\n"
        "- Vertical workflows where domain expertise creates a moat — "
        "vertical AI outperforms horizontal tools in traction and retention\n"
        "- Infrastructure gaps for AI agents (tooling, integrations, data "
        "pipelines) — fastest-growing new category\n\n"
        "Deprioritize:\n"
        "- Generic AI wrappers without domain-specific data or workflow moats\n"
        "- Pure consumer social apps (winner-take-all dynamics, extreme CAC)\n\n"
        "A good problem is: specific to one user group, frequently "
        "complained about, and has existing tools that fail to solve it well.\n\n"
        "Do NOT propose solutions or product ideas. Just document the "
        "problem area with evidence."
    ),
    discovery_user_preamble=(
        "Analyze the research data below to find ONE specific problem area "
        "where a defined user group consistently complains about a broken "
        "workflow, manual process, or inadequate tooling. Document the "
        "problem with evidence — quotes, complaint counts, sources.\n\n"
    ),
    synthesis_system_prompt=(
        "Based on the following problem report, propose ONE specific product "
        "idea that directly addresses this pain point. The product should be:\n"
        "- A focused micro-SaaS that a solo developer could build in 1-2 weeks\n"
        "- Targeted at the specific user group identified in the report\n"
        "- Clearly differentiated from the existing tools that are failing\n"
        "- Solving the most painful part of the workflow first\n\n"
        "Ground your idea in the evidence from the problem report. The product "
        "name should clearly communicate what it does."
    ),
    prioritize_reddit=True,
    prioritize_hn=True,
    scoring_guidance=(
        "This is a DISRUPTION idea — improving broken workflows in existing "
        "tools. Weight pain severity and willingness to pay heavily. Existing "
        "paid competitors validate the market. Complaint volume and user group "
        "specificity are strong positive signals. Frequency of pain is critical "
        "— daily pain scores higher than monthly."
    ),
    discovery_output_model="ProblemReport",
)

# ---------------------------------------------------------------------------
# Moonshot Agent — futures-first discovery
# ---------------------------------------------------------------------------

MOONSHOT_STRATEGY = DiscoveryStrategy(
    discovery_type=DiscoveryType.MOONSHOT,
    name="Moonshot Agent",
    discovery_queries=[
        "new AI capabilities what is now possible 2025 2026",
        "technology trends shaping the future 2026 2027 predictions",
        "emerging platforms APIs developers building on 2026",
        "how industries will transform next 5 years AI automation",
    ],
    discovery_perplexity_question=(
        "What new technologies, AI capabilities, or platform shifts have "
        "emerged recently that will fundamentally change how specific "
        "industries or user groups work in the next 2-5 years? Give "
        "concrete examples of what becomes possible that wasn't before."
    ),
    discovery_system_prompt=(
        "You are a futures discovery agent. Your job is to explore how "
        "the world is changing and identify opportunities for products "
        "that will be needed in the near future.\n\n"
        "Think about:\n"
        "1. New capabilities — AI models, APIs, hardware, protocols "
        "that are less than 12 months old and enable new product "
        "categories\n"
        "2. Future scenarios — how will specific industries look in "
        "2-5 years? What products will people need in that future?\n"
        "   Examples: self-driving cars → fleet management for personal "
        "vehicles; AI agents → products assuming everyone has a personal AI; "
        "creator economy evolution → tools for the next generation of "
        "influencers\n"
        "3. Specific user groups who will be most affected by these "
        "changes and will need new tools\n\n"
        "## Sector signals (derived from startup cohort analysis)\n\n"
        "Prioritize opportunities in these high-growth areas:\n"
        "- Infrastructure for AI agents (tooling, integrations, orchestration, "
        "data pipelines) — this category barely existed 18 months ago and is "
        "already producing unicorns\n"
        "- High-friction regulated industries being transformed by AI "
        "(legal, healthcare, defense, financial services) — clearest paths "
        "to outsized outcomes\n"
        "- Category-creating products that define a new market rather than "
        "competing in an existing one — category creators achieve 15x higher "
        "valuation-to-funding ratios\n"
        "- Underserved geographic or demographic markets with proven demand "
        "patterns but inadequate tooling\n\n"
        "Deprioritize:\n"
        "- Horizontal AI wrappers competing on model quality alone — models "
        "will commoditize, product-model integration is the durable moat\n"
        "- Hardware-dependent ideas requiring significant capital before "
        "validation\n\n"
        "Paint a concrete future scenario, identify the target user group, "
        "and explain why NOW is the time to build for that future."
    ),
    discovery_user_preamble=(
        "Analyze the research data below to identify ONE compelling "
        "opportunity where emerging technology or a major trend enables "
        "a product that was not possible before. Paint a concrete future "
        "scenario and identify the specific user group that will need "
        "new tools.\n\n"
    ),
    synthesis_system_prompt=(
        "Based on the following opportunity report, propose ONE specific "
        "product idea that positions for this future. The product should:\n"
        "- Target a specific user group identified in the report\n"
        "- Leverage the described capability or trend\n"
        "- Be buildable as an MVP by a solo developer in 2-4 weeks\n"
        "- Have a clear 'wow factor' or viral potential\n"
        "- Be something that would NOT have been possible 12 months ago\n\n"
        "The product name should evoke the future it's building toward."
    ),
    prioritize_reddit=False,
    prioritize_hn=True,
    scoring_guidance=(
        "This is a MOONSHOT idea — positioning for an emerging trend or "
        "new capability. Weight novelty and growth potential more heavily "
        "than proven willingness to pay. A small current market is "
        "acceptable if the future scenario is compelling and the growth "
        "trajectory is strong. Few competitors is expected (the space is "
        "new), not a weakness."
    ),
    discovery_output_model="OpportunityReport",
)

ALL_STRATEGIES: list[DiscoveryStrategy] = [DISRUPTION_STRATEGY, MOONSHOT_STRATEGY]
