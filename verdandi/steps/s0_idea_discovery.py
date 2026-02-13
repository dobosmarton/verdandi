"""Step 0: Idea Discovery — find product ideas worth validating."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, TypedDict

import structlog
from pydantic import BaseModel, ConfigDict, Field

from verdandi.models.idea import IdeaCandidate, PainPoint
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel as BaseModelType

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Discovery search queries
# ---------------------------------------------------------------------------

_DISCOVERY_QUERIES: list[str] = [
    "trending micro-SaaS ideas 2025 and 2026",
    "tools developers wish existed",
    "underserved pain points for small businesses",
]

_PERPLEXITY_QUESTION = (
    "What are the most promising underserved software product opportunities right now?"
)

_SYSTEM_PROMPT = (
    "You are a product discovery agent analyzing market signals for underserved "
    "pain points. Identify ONE specific, actionable product idea that addresses "
    "a real pain point with evidence. Focus on micro-SaaS ideas that a solo "
    "developer could build in 1-2 weeks."
)

# ---------------------------------------------------------------------------
# LLM output schema (content fields only — no experiment_id, worker_id, etc.)
# ---------------------------------------------------------------------------


class _IdeaLLMOutput(BaseModel):
    """Structured LLM output for idea discovery — content fields only."""

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


# ---------------------------------------------------------------------------
# Mock data infrastructure (unchanged)
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
    },
    {
        "title": "StatusSnap — Beautiful Status Pages in 60 Seconds",
        "one_liner": "Create a professional status page for your product without any configuration",
        "problem_statement": "Every SaaS needs a status page but setting one up is surprisingly complex. Existing solutions are either expensive or require significant setup.",
        "target_audience": "Indie hackers and small SaaS teams who need a status page but don't want to manage one",
        "category": "developer-tools",
        "pain_points": [
            {
                "description": "Existing status page tools cost $29-99/month for basic features",
                "severity": 6,
                "frequency": "monthly",
                "source": "Reddit r/SaaS",
                "quote": "Statuspage.io wants $79/month for what should be a simple page",
            },
            {
                "description": "Self-hosted alternatives require DevOps knowledge",
                "severity": 7,
                "frequency": "monthly",
                "source": "HackerNews",
                "quote": "",
            },
        ],
        "existing_solutions": ["Statuspage.io", "Instatus", "Cachet (self-hosted)", "Upptime"],
        "differentiation": "Zero-config setup: connect your monitoring tool and get a beautiful page instantly",
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


def _build_user_prompt(
    research_text: str,
    *,
    has_research: bool,
    exclude_titles: list[str] | None = None,
) -> str:
    """Build the user prompt for idea discovery LLM call.

    Args:
        research_text: Formatted research context.
        has_research: Whether research data was successfully collected.
        exclude_titles: Previously discovered idea titles to avoid.
    """
    if has_research:
        prompt = (
            "Based on the following market research signals, identify ONE specific, "
            "actionable micro-SaaS product idea. The idea must address a real pain "
            "point backed by the evidence below. Include specific pain points with "
            "severity ratings, existing solutions, and how this idea differentiates.\n\n"
            "---\n\n"
            f"{research_text}\n\n"
            "---\n\n"
            "Respond with a single structured product idea. Reference source URLs "
            "from the research data in the source_urls field where applicable."
        )
    else:
        prompt = (
            "No external research data is available. Using your training knowledge, "
            "identify ONE specific, actionable micro-SaaS product idea that addresses "
            "a real, underserved pain point. Focus on problems you have strong evidence "
            "exist based on common developer and small-business complaints. Include "
            "specific pain points with severity ratings, existing solutions, and how "
            "this idea differentiates. Be concrete and specific — avoid generic ideas."
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
        return self._discover_idea(ctx)

    def _discover_idea(self, ctx: StepContext) -> IdeaCandidate:
        """Run real idea discovery: research APIs + LLM synthesis."""
        from verdandi.llm import LLMClient
        from verdandi.research import ResearchCollector, format_research_context

        # --- Collect research signals ---
        research_text = ""
        has_research = False

        try:
            collector = ResearchCollector(ctx.settings)
            raw_data = collector.collect(
                _DISCOVERY_QUERIES,
                include_reddit=True,
                include_hn_comments=True,
                perplexity_question=_PERPLEXITY_QUESTION,
            )
            research_text = format_research_context(raw_data)
            has_research = True
            logger.info(
                "Research collected for idea discovery",
                sources=raw_data.sources_used,
                text_length=len(research_text),
            )
        except RuntimeError:
            logger.warning("All research sources failed, falling back to LLM-only discovery")

        # --- Synthesize via LLM ---
        user_prompt = _build_user_prompt(
            research_text,
            has_research=has_research,
            exclude_titles=list(ctx.exclude_titles) if ctx.exclude_titles else None,
        )
        llm = LLMClient(ctx.settings)
        result = llm.generate(user_prompt, _IdeaLLMOutput, system=_SYSTEM_PROMPT)

        logger.info(
            "Idea discovered via LLM",
            title=result.title,
            category=result.category,
            pain_points_count=len(result.pain_points),
            has_research=has_research,
        )

        # Merge LLM-produced source_urls with any URLs extracted from research
        source_urls = list(result.source_urls)
        if has_research:
            extracted = _extract_source_urls(research_text)
            seen = set(source_urls)
            for url in extracted:
                if url not in seen:
                    source_urls.append(url)
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
            source_urls=source_urls,
        )

    def _mock_idea(self, ctx: StepContext) -> IdeaCandidate:
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
        )
