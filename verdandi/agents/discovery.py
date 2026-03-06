"""Step 0: Idea Discovery — two-phase discovery with specialized agents.

Phase 1 — Discovery: Collect research + generate a ProblemReport (disruption)
    or OpportunityReport (moonshot) from raw market signals.
Phase 2 — Synthesis: Take the discovery report and synthesize a concrete
    IdeaCandidate product idea.

The strategy (disruption vs moonshot) is passed through StepContext.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, TypedDict

import structlog
from pydantic import BaseModel, ConfigDict, Field

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.idea import (
    DiscoveryType,
    IdeaCandidate,
    OpportunityReport,
    PainPoint,
    ProblemReport,
)

if TYPE_CHECKING:
    from pydantic import BaseModel as BaseModelType

    from verdandi.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# LLM output schema for Phase 2 synthesis
# ---------------------------------------------------------------------------


class _IdeaLLMOutput(BaseModel):
    """Structured LLM output for idea synthesis — content fields only."""

    model_config = ConfigDict(frozen=True)

    title: str
    one_liner: str
    problem_statement: str
    target_audience: str
    category: str
    pain_points: list[PainPoint]
    existing_solutions: list[str]
    differentiation: str
    source_urls: list[str] = Field(default_factory=list)
    discovery_type: DiscoveryType = Field(default=DiscoveryType.DISRUPTION)


# ---------------------------------------------------------------------------
# Query variation — diversify research queries across discovery batches
# ---------------------------------------------------------------------------

_VARY_QUERIES_SYSTEM = (
    "You are a search query reformulator. Given base research queries and a "
    "deep-research question, produce semantically equivalent but differently-worded "
    "variants. Each variant should explore the same topic from a different angle, "
    "using different keywords and phrasing, to surface different results from search "
    "APIs. Keep the same intent but change specificity level, angle of approach, or "
    "vocabulary. Return the same number of queries as the input."
)


class _VariedQueries(BaseModel):
    """LLM output for reformulated search queries."""

    model_config = ConfigDict(frozen=True)

    queries: list[str] = Field(description="Reformulated search queries")
    perplexity_question: str = Field(
        description="Reformulated deep-research question",
    )


def _vary_queries(
    base_queries: list[str],
    base_perplexity_question: str,
    settings: Settings,
) -> _VariedQueries:
    """Reformulate discovery queries via LLM for cache-key diversity.

    Falls back to original queries on any error.
    """
    if not settings.discovery_query_variation:
        return _VariedQueries(
            queries=list(base_queries),
            perplexity_question=base_perplexity_question,
        )

    from verdandi.llm import LLMClient

    prompt = (
        "Reformulate each of these search queries and the deep-research question. "
        "Keep the same research intent but use different wording, angles, and keywords.\n\n"
        "## Search queries\n"
        + "\n".join(f"- {q}" for q in base_queries)
        + "\n\n## Deep-research question\n"
        + base_perplexity_question
    )

    try:
        llm = LLMClient(settings)
        result = llm.generate(
            prompt,
            _VariedQueries,
            system=_VARY_QUERIES_SYSTEM,
            temperature=0.9,
            max_tokens=512,
        )
        logger.info(
            "Discovery queries varied",
            original_count=len(base_queries),
            varied_count=len(result.queries),
        )
        return result
    except Exception:
        logger.warning("Query variation failed, using original queries", exc_info=True)
        return _VariedQueries(
            queries=list(base_queries),
            perplexity_question=base_perplexity_question,
        )


# ---------------------------------------------------------------------------
# Mock data infrastructure
# ---------------------------------------------------------------------------


class _PainPointDict(TypedDict):
    description: str
    severity: int
    frequency: str
    source: str
    quote: str


class _MockIdea(TypedDict):
    title: str
    one_liner: str
    problem_statement: str
    target_audience: str
    category: str
    pain_points: list[_PainPointDict]
    existing_solutions: list[str]
    differentiation: str
    discovery_type: str


_MOCK_IDEAS: list[_MockIdea] = [
    {
        "title": "DevLog — Automated Developer Changelog",
        "one_liner": "Automatically generate beautiful changelogs from git commits and PRs",
        "problem_statement": "Developers hate writing changelogs manually but users need them. Most projects either skip changelogs entirely or produce low-quality ones.",
        "target_audience": "Open-source maintainers and small SaaS teams (1-20 devs)",
        "category": "developer-tools",
        "pain_points": [
            {
                "description": "Writing changelogs is tedious and often skipped",
                "severity": 6,
                "frequency": "weekly",
                "source": "HackerNews",
                "quote": "I just stopped maintaining a changelog after v2",
            },
            {
                "description": "Auto-generated changelogs from commits are unreadable",
                "severity": 7,
                "frequency": "weekly",
                "source": "Reddit r/programming",
                "quote": "",
            },
        ],
        "existing_solutions": ["release-please", "conventional-changelog", "changelog.md manual"],
        "differentiation": "AI-powered summarization that produces human-quality prose, not just commit lists",
        "discovery_type": "disruption",
    },
    {
        "title": "FormShield — AI-Powered Form Spam Detection",
        "one_liner": "Block spam form submissions without CAPTCHAs using AI content analysis",
        "problem_statement": "Contact forms and signup forms get flooded with spam. CAPTCHAs hurt conversion rates. Honeypots catch only basic bots.",
        "target_audience": "Small business owners and indie developers with public-facing forms",
        "category": "security",
        "pain_points": [
            {
                "description": "Spam submissions waste time and pollute databases",
                "severity": 7,
                "frequency": "daily",
                "source": "Reddit r/webdev",
                "quote": "I get 50+ spam submissions a day on my contact form",
            },
            {
                "description": "CAPTCHAs reduce form completion rates by 10-30%",
                "severity": 8,
                "frequency": "daily",
                "source": "Baymard Institute",
                "quote": "",
            },
        ],
        "existing_solutions": ["reCAPTCHA", "Akismet", "Honeypot fields", "Turnstile"],
        "differentiation": "Zero-friction for users, analyzes content semantically rather than behavior patterns",
        "discovery_type": "disruption",
    },
    {
        "title": "PriceTrack — Competitor Pricing Monitor",
        "one_liner": "Get instant alerts when competitors change their pricing pages",
        "problem_statement": "SaaS companies need to monitor competitor pricing but checking manually is impractical. Most change detection tools are too generic.",
        "target_audience": "SaaS founders and product managers at companies with 5+ competitors",
        "category": "competitive-intelligence",
        "pain_points": [
            {
                "description": "Missing competitor price changes leads to lost revenue",
                "severity": 8,
                "frequency": "monthly",
                "source": "Reddit r/SaaS",
                "quote": "Our competitor dropped prices 30% and we didn't notice for 2 months",
            },
            {
                "description": "Generic monitoring tools produce too many false positives",
                "severity": 6,
                "frequency": "weekly",
                "source": "HackerNews",
                "quote": "",
            },
        ],
        "existing_solutions": ["Visualping", "Kompyte", "Crayon", "manual checking"],
        "differentiation": "Specifically designed for pricing pages with structured data extraction",
        "discovery_type": "disruption",
    },
    {
        "title": "MeetingBrief — Pre-Meeting Context Generator",
        "one_liner": "Get a one-page brief about everyone you're meeting with, auto-generated before each call",
        "problem_statement": "Salespeople and founders waste time researching meeting participants or go in blind. LinkedIn stalking before each call is tedious.",
        "target_audience": "B2B salespeople, founders, and account managers with 5+ external meetings per week",
        "category": "sales-tools",
        "pain_points": [
            {
                "description": "Going into meetings without context wastes the first 10 minutes",
                "severity": 7,
                "frequency": "daily",
                "source": "Reddit r/sales",
                "quote": "",
            },
            {
                "description": "Manually researching each participant takes 15-20 minutes",
                "severity": 6,
                "frequency": "daily",
                "source": "HackerNews",
                "quote": "I spend an hour a day just prepping for calls",
            },
        ],
        "existing_solutions": ["LinkedIn Sales Navigator", "Clearbit", "manual research"],
        "differentiation": "Fully automated, integrates with calendar, delivers brief 30 min before meeting",
        "discovery_type": "disruption",
    },
    {
        "title": "FleetPilot — Personal Vehicle Fleet Manager",
        "one_liner": "Send your self-driving car to run errands while you work",
        "problem_statement": "As autonomous vehicles become mainstream, car owners need tools to manage their vehicles as productive assets — scheduling deliveries, pickups, and errands.",
        "target_audience": "Early adopters of autonomous vehicles in urban areas",
        "category": "autonomous-vehicles",
        "pain_points": [
            {
                "description": "Cars sit idle 95% of the time, wasting a depreciating asset",
                "severity": 7,
                "frequency": "daily",
                "source": "HackerNews",
                "quote": "My car is parked 23 hours a day. What a waste.",
            },
            {
                "description": "No consumer-friendly tools for managing autonomous vehicle schedules",
                "severity": 8,
                "frequency": "daily",
                "source": "Reddit r/SelfDrivingCars",
                "quote": "",
            },
        ],
        "existing_solutions": ["Tesla app (limited)", "Waymo app (rides only)"],
        "differentiation": "First personal fleet management tool — treat your car as a productive agent",
        "discovery_type": "moonshot",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_source_urls(research_text: str) -> list[str]:
    """Extract unique URLs from formatted research context text.

    Scans the research text for URLs in parentheses (the format used by
    ``format_research_context``) and returns deduplicated results.
    """
    import re

    urls: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\(https?://[^\s)]+\)", research_text):
        url = match.group(0)[1:-1]  # strip parens
        if url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def _build_phase1_user_prompt(
    research_text: str,
    *,
    has_research: bool,
    preamble: str = "",
) -> str:
    """Build the user prompt for Phase 1 (discovery) LLM call."""
    if has_research:
        prompt = preamble + (
            "---\n\n"
            f"{research_text}\n\n"
            "---\n\n"
            "Based on the research data above, produce your discovery report."
        )
    else:
        prompt = preamble + (
            "No external research data is available. Using your training "
            "knowledge, identify a strong signal based on well-known, widely "
            "reported problems or trends. Be concrete and specific."
        )
    return prompt


def _build_synthesis_user_prompt(
    report: BaseModel,
    *,
    exclude_titles: list[str] | None = None,
    source_urls: list[str] | None = None,
) -> str:
    """Build the user prompt for Phase 2 (synthesis) LLM call."""
    prompt = (
        "## Discovery Report\n\n"
        f"{report.model_dump_json(indent=2)}\n\n"
        "---\n\n"
        "Based on this discovery report, propose ONE specific product idea. "
        "Reference findings from the report in your response."
    )

    if source_urls:
        prompt += "\n\nAvailable source URLs to reference:\n" + "\n".join(
            f"- {url}" for url in source_urls
        )

    if exclude_titles:
        prompt += (
            "\n\nIMPORTANT: Do NOT suggest any of these ideas or close variations:\n"
            + "\n".join(f"- {t}" for t in exclude_titles)
            + "\nPropose something in a COMPLETELY DIFFERENT domain or problem space."
        )

    return prompt


# ---------------------------------------------------------------------------
# Step implementation
# ---------------------------------------------------------------------------


@register_step
class IdeaDiscoveryStep(AbstractStep):
    name = "idea_discovery"
    step_number = 0

    def run(self, ctx: StepContext) -> BaseModelType:
        if ctx.dry_run:
            return self._mock_idea(ctx)
        return self._discover_idea_two_phase(ctx)

    # ------------------------------------------------------------------
    # Two-phase discovery
    # ------------------------------------------------------------------

    def _discover_idea_two_phase(self, ctx: StepContext) -> IdeaCandidate:
        """Two-phase discovery: Phase 1 (discovery report) + Phase 2 (synthesis)."""
        from verdandi.llm import LLMClient
        from verdandi.research import ResearchCollector, format_research_context

        if ctx.discovery_strategy is None:
            msg = "discovery_strategy is required for idea discovery"
            raise ValueError(msg)
        strategy = ctx.discovery_strategy

        logger.info(
            "Starting two-phase discovery",
            strategy=strategy.name,
            discovery_type=strategy.discovery_type.value,
        )

        # --- Vary queries for cache-key diversity ---
        varied = _vary_queries(
            strategy.discovery_queries,
            strategy.discovery_perplexity_question or "",
            ctx.settings,
        )

        # --- Collect research signals ---
        research_text = ""
        has_research = False

        try:
            collector = ResearchCollector(ctx.settings)
            raw_data = collector.collect(
                varied.queries,
                include_reddit=strategy.prioritize_reddit,
                include_twitter=strategy.prioritize_twitter,
                include_hn_comments=strategy.prioritize_hn,
                perplexity_question=varied.perplexity_question,
            )
            research_text = format_research_context(raw_data)
            has_research = True
            logger.info(
                "Research collected for discovery",
                strategy=strategy.name,
                sources=raw_data.sources_used,
                text_length=len(research_text),
            )
        except RuntimeError:
            logger.warning(
                "All research sources failed, falling back to LLM-only",
                strategy=strategy.name,
            )

        llm = LLMClient(ctx.settings)

        # --- Phase 1: Discovery report ---
        phase1_prompt = _build_phase1_user_prompt(
            research_text,
            has_research=has_research,
            preamble=strategy.discovery_user_preamble,
        )

        # Dispatch to the correct output model
        if strategy.discovery_output_model == "ProblemReport":
            report: ProblemReport | OpportunityReport = llm.generate(
                phase1_prompt, ProblemReport, system=strategy.discovery_system_prompt
            )
        else:
            report = llm.generate(
                phase1_prompt, OpportunityReport, system=strategy.discovery_system_prompt
            )

        logger.info(
            "Phase 1 complete — discovery report generated",
            strategy=strategy.name,
            report_type=strategy.discovery_output_model,
        )

        # --- Phase 2: Synthesis ---
        source_urls = _extract_source_urls(research_text) if has_research else []

        synthesis_prompt = _build_synthesis_user_prompt(
            report,
            exclude_titles=list(ctx.exclude_titles) if ctx.exclude_titles else None,
            source_urls=source_urls if source_urls else None,
        )

        result = llm.generate(
            synthesis_prompt, _IdeaLLMOutput, system=strategy.synthesis_system_prompt
        )

        logger.info(
            "Phase 2 complete — idea synthesized",
            strategy=strategy.name,
            title=result.title,
            category=result.category,
        )

        # Merge source URLs
        all_source_urls = list(result.source_urls)
        seen = set(all_source_urls)
        for url in source_urls:
            if url not in seen:
                all_source_urls.append(url)
                seen.add(url)

        return IdeaCandidate(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            title=result.title,
            one_liner=result.one_liner,
            problem_statement=result.problem_statement,
            target_audience=result.target_audience,
            category=result.category,
            pain_points=result.pain_points,
            existing_solutions=result.existing_solutions,
            differentiation=result.differentiation,
            source_urls=all_source_urls,
            discovery_type=strategy.discovery_type,
            discovery_report_json=report.model_dump_json(),
        )

    # ------------------------------------------------------------------
    # Mock data (dry-run mode)
    # ------------------------------------------------------------------

    def _mock_idea(self, ctx: StepContext) -> IdeaCandidate:
        strategy = ctx.discovery_strategy
        if strategy is not None:
            matching = [
                m for m in _MOCK_IDEAS if m["discovery_type"] == strategy.discovery_type.value
            ]
            mock = random.choice(matching) if matching else random.choice(_MOCK_IDEAS)
        else:
            mock = random.choice(_MOCK_IDEAS)

        return IdeaCandidate(
            experiment_id=ctx.experiment.id or 0,
            title=mock["title"],
            one_liner=mock["one_liner"],
            problem_statement=mock["problem_statement"],
            target_audience=mock["target_audience"],
            category=mock["category"],
            pain_points=[PainPoint(**pp) for pp in mock["pain_points"]],
            existing_solutions=mock["existing_solutions"],
            differentiation=mock["differentiation"],
            worker_id=ctx.worker_id,
            discovery_type=DiscoveryType(mock["discovery_type"]),
        )
