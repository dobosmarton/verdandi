"""Step 1: Deep Research — comprehensive market research for an idea.

Collects research from all available providers in parallel, then optionally
performs follow-up rounds to fill evidence gaps identified by an LLM gap
analysis. The number of rounds is controlled by ``research_max_rounds``
(default 2: one broad collection + one targeted follow-up).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.research import (
    RESEARCH_DIMENSIONS,
    Competitor,
    MarketResearch,
    ResearchGapAnalysis,
    SearchResult,
)

if TYPE_CHECKING:
    from verdandi.research import RawResearchData

logger = structlog.get_logger()

# Maximum follow-up queries generated per round
_MAX_FOLLOWUP_QUERIES: int = 5

# Providers used for targeted follow-up rounds (cheaper + question-friendly)
_FOLLOWUP_PROVIDER_NAMES: frozenset[str] = frozenset({"tavily", "perplexity"})

_GAP_ANALYSIS_SYSTEM: str = (
    "You are a market research quality assessor. Your job is to identify "
    "what evidence is strong, what is missing, and what targeted queries "
    "would fill the gaps. Be rigorous — a dimension needs multiple "
    "independent data points to score above 0.7."
)

_SYNTHESIS_SYSTEM: str = (
    "You are a market research analyst. Analyze the provided research "
    "data and produce a comprehensive market assessment. Be "
    "evidence-based — cite specific data points from the research. "
    "Do not invent statistics or data."
)


# ------------------------------------------------------------------
# Pure helper functions
# ------------------------------------------------------------------


class _MarketResearchLLMOutput(BaseModel):
    """LLM-generated content fields for market research synthesis.

    Contains only the fields the LLM should produce. Metadata fields
    (experiment_id, worker_id, step_name, timestamps) are added by the
    step after generation.
    """

    model_config = ConfigDict(frozen=True)

    tam_estimate: str
    market_growth: str
    demand_signals: list[str]
    competitors: list[Competitor]
    competitor_gaps: list[str]
    target_audience_size: str
    willingness_to_pay: str
    common_complaints: list[str]
    key_findings: list[str]
    research_summary: str


def _build_gap_analysis_prompt(
    idea_title: str,
    problem_statement: str,
    category: str,
    research_text: str,
) -> str:
    """Build the prompt for the gap analysis LLM call."""
    dimension_lines = "\n".join(f"{i}. **{dim}**" for i, dim in enumerate(RESEARCH_DIMENSIONS, 1))
    return (
        f"## Product Idea\n\n"
        f"**Title**: {idea_title}\n"
        f"**Problem**: {problem_statement}\n"
        f"**Category**: {category}\n\n"
        f"## Research Data Collected So Far\n\n"
        f"{research_text}\n\n"
        f"## Instructions\n\n"
        f"Analyze the research data above and assess how confident we can be "
        f"in each of the following 5 dimensions:\n"
        f"{dimension_lines}\n\n"
        f"For each dimension, score confidence 0.0-1.0 where:\n"
        f"- < 0.3 = no credible evidence found\n"
        f"- 0.3-0.6 = some evidence but gaps remain\n"
        f"- 0.6-0.8 = solid evidence from multiple sources\n"
        f"- > 0.8 = strong multi-source evidence with specifics\n\n"
        f"Then generate up to {_MAX_FOLLOWUP_QUERIES} targeted follow-up "
        f"search queries that would fill the weakest gaps. Focus queries on "
        f"dimensions with confidence < 0.6. Be specific — include company "
        f"names, product names, or precise market terms.\n\n"
        f"Also generate a single synthesized question for Perplexity to "
        f"research in depth about the weakest gap."
    )


def _build_synthesis_prompt(
    idea_title: str,
    problem_statement: str,
    target_audience: str,
    category: str,
    research_text: str,
    rounds_completed: int,
) -> str:
    """Build the final synthesis prompt, noting multi-round provenance."""
    round_note = ""
    if rounds_completed > 1:
        round_note = (
            f"\n\n**Note**: This research was collected across "
            f"{rounds_completed} rounds. Later rounds targeted specific "
            f"gaps identified in earlier data. When evidence from follow-up "
            f"rounds contradicts or refines initial findings, prefer the "
            f"more specific and recent evidence.\n"
        )

    return (
        f"## Product Idea\n\n"
        f"**Title**: {idea_title}\n"
        f"**Problem**: {problem_statement}\n"
        f"**Target Audience**: {target_audience}\n"
        f"**Category**: {category}\n"
        f"{round_note}\n"
        f"## Research Data\n\n"
        f"{research_text}\n\n"
        f"## Instructions\n\n"
        f"Based on the research data above, produce a comprehensive market "
        f"assessment. For each field, ground your analysis in specific "
        f"evidence from the research data. Include concrete numbers, "
        f"quotes, and references where available."
    )


def _merge_followup_queries(
    llm_queries: list[str],
    tavily_questions: list[str],
    max_total: int = _MAX_FOLLOWUP_QUERIES,
) -> list[str]:
    """Merge LLM-generated and Tavily follow-up queries, deduplicating.

    LLM queries take priority. Tavily questions are appended if they are
    not near-duplicates of existing queries. Dedup uses lowercased substring
    matching — sufficient for a small list of 5-10 items.
    """
    merged: list[str] = []
    seen_lower: list[str] = []

    for q in llm_queries:
        if len(merged) >= max_total:
            break
        q_stripped = q.strip()
        if not q_stripped:
            continue
        merged.append(q_stripped)
        seen_lower.append(q_stripped.lower())

    for tq in tavily_questions:
        if len(merged) >= max_total:
            break
        tq_stripped = tq.strip()
        if not tq_stripped:
            continue
        tq_lower = tq_stripped.lower()
        # Skip if any existing query contains this one or vice versa
        is_dup = any(tq_lower in existing or existing in tq_lower for existing in seen_lower)
        if not is_dup:
            merged.append(tq_stripped)
            seen_lower.append(tq_lower)

    return merged


def _extract_tavily_followups(raw: RawResearchData) -> list[str]:
    """Extract follow_up_questions from Tavily research results if present."""
    if raw.tavily_research is not None:
        return list(raw.tavily_research.get("follow_up_questions", []))
    return []


def _build_search_results(raw: RawResearchData) -> list[SearchResult]:
    """Build SearchResult list from raw API data (NOT LLM-generated)."""
    results: list[SearchResult] = [
        SearchResult(
            title=tr["title"],
            url=tr["url"],
            snippet=tr["content"][:300],
            source="tavily",
            relevance_score=float(tr.get("score", 0.0)),
        )
        for tr in raw.tavily_results
    ]

    results.extend(
        SearchResult(
            title=sr["title"],
            url=sr["link"],
            snippet=sr["snippet"],
            source="serper",
            relevance_score=0.0,
        )
        for sr in raw.serper_results
    )

    results.extend(
        SearchResult(
            title=er["title"],
            url=er["url"],
            snippet=er["text"][:300] if er["text"] else "",
            source="exa",
            relevance_score=er["score"],
        )
        for er in raw.exa_results
    )

    return results


# ------------------------------------------------------------------
# Step implementation
# ------------------------------------------------------------------


@register_step
class DeepResearchStep(AbstractStep):
    name = "deep_research"
    step_number = 1

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_research(ctx)

        from verdandi.llm import LLMClient
        from verdandi.memory.working import ResearchSession
        from verdandi.models.idea import IdeaCandidate
        from verdandi.providers import default_providers
        from verdandi.research import ResearchCollector

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID — cannot run deep research")

        # Retrieve Step 0's IdeaCandidate via prior_results (or DB fallback)
        if ctx.prior_results is not None:
            idea = ctx.prior_results.get_typed("idea_discovery", IdeaCandidate)
        elif ctx.db is not None:
            step_result = ctx.db.get_step_result(experiment_id, "idea_discovery")
            if step_result is None:
                raise RuntimeError(
                    f"No idea_discovery result found for experiment {ctx.experiment.id}. "
                    "Step 0 must complete before Step 1 can run."
                )
            idea = IdeaCandidate.model_validate(step_result["data"])
        else:
            raise RuntimeError("No prior_results or db available to retrieve idea")

        max_rounds = ctx.settings.research_max_rounds

        logger.info(
            "Starting deep research",
            experiment_id=ctx.experiment.id,
            idea_title=idea.title,
            category=idea.category,
            max_rounds=max_rounds,
        )

        llm = LLMClient(ctx.settings)
        session = ResearchSession(idea_title=idea.title, idea_category=idea.category)

        # Build full provider set (for round 1) and follow-up subset
        all_providers = default_providers(ctx.settings)
        followup_providers = [p for p in all_providers if p.name in _FOLLOWUP_PROVIDER_NAMES]

        # ---- Round 1: broad collection with all providers ----
        queries = [
            f"{idea.title} competitors alternatives",
            f"{idea.category} market size TAM",
            f'"{idea.target_audience}" pain points {idea.category}',
        ]

        collector_full = ResearchCollector(ctx.settings, providers=all_providers)
        raw_data = collector_full.collect(
            queries,
            include_reddit=True,
            include_twitter=True,
            include_hn_comments=True,
            perplexity_question=(
                f"What is the total addressable market for {idea.title}? "
                "Who are the main competitors and what gaps exist?"
            ),
            exa_similar_url="",
            tavily_research_query=(
                f"Market analysis for {idea.title}: "
                f"TAM, competitors, gaps, and growth trajectory "
                f"in {idea.category}"
            ),
            use_perplexity_deep=True,
        )

        session.ingest(raw_data)
        tavily_followups = _extract_tavily_followups(raw_data)

        logger.info(
            "Round 1 collection complete",
            experiment_id=ctx.experiment.id,
            total_results=session.total_results,
            tavily_followups_available=len(tavily_followups),
        )

        # Track the latest gap analysis and round count
        gap_analysis: ResearchGapAnalysis | None = None
        rounds_completed = 1

        # ---- Follow-up rounds (round 2 .. max_rounds) ----
        for round_num in range(2, max_rounds + 1):
            research_text = session.formatted_context

            # Ask LLM: what gaps remain?
            gap_prompt = _build_gap_analysis_prompt(
                idea_title=idea.title,
                problem_statement=idea.problem_statement,
                category=idea.category,
                research_text=research_text,
            )
            gap_analysis = llm.generate(
                gap_prompt,
                ResearchGapAnalysis,
                system=_GAP_ANALYSIS_SYSTEM,
                temperature=0.3,
            )

            logger.info(
                "Gap analysis complete",
                experiment_id=ctx.experiment.id,
                round=round_num,
                overall_confidence=gap_analysis.overall_confidence,
                weakest_dimensions=gap_analysis.weakest_dimensions,
                followup_query_count=len(gap_analysis.follow_up_queries),
            )

            # Early exit if confidence is already high enough
            if gap_analysis.overall_confidence >= ctx.settings.research_confidence_threshold:
                logger.info(
                    "Research confidence threshold met, skipping further rounds",
                    experiment_id=ctx.experiment.id,
                    confidence=gap_analysis.overall_confidence,
                    threshold=ctx.settings.research_confidence_threshold,
                )
                break

            # Merge LLM follow-ups with Tavily's suggestions
            followup_queries = _merge_followup_queries(
                gap_analysis.follow_up_queries,
                tavily_followups,
            )

            if not followup_queries:
                logger.info(
                    "No follow-up queries generated, ending research",
                    experiment_id=ctx.experiment.id,
                    round=round_num,
                )
                break

            # Collect with targeted provider subset
            collector_targeted = ResearchCollector(
                ctx.settings,
                providers=followup_providers,
            )
            followup_raw = collector_targeted.collect(
                followup_queries,
                include_reddit=False,
                include_twitter=False,
                include_hn_comments=False,
                perplexity_question=gap_analysis.follow_up_perplexity_question,
                exa_similar_url="",
                tavily_research_query="",
                use_perplexity_deep=False,
            )

            # Ingest and check if we got new data
            new_results = session.ingest_with_delta(followup_raw)
            rounds_completed = round_num

            logger.info(
                "Follow-up round complete",
                experiment_id=ctx.experiment.id,
                round=round_num,
                new_results=new_results,
                total_results=session.total_results,
            )

            if new_results == 0:
                logger.info(
                    "Follow-up round returned no new data, ending research",
                    experiment_id=ctx.experiment.id,
                    round=round_num,
                )
                break

            # Refresh Tavily follow-ups from this round's data
            tavily_followups = _extract_tavily_followups(followup_raw)

        # ---- Final synthesis ----
        research_text = session.formatted_context

        synthesis_prompt = _build_synthesis_prompt(
            idea_title=idea.title,
            problem_statement=idea.problem_statement,
            target_audience=idea.target_audience,
            category=idea.category,
            research_text=research_text,
            rounds_completed=rounds_completed,
        )

        result = llm.generate(
            synthesis_prompt,
            _MarketResearchLLMOutput,
            system=_SYNTHESIS_SYSTEM,
        )

        logger.info(
            "LLM synthesis complete",
            experiment_id=ctx.experiment.id,
            competitor_count=len(result.competitors),
            finding_count=len(result.key_findings),
            rounds_completed=rounds_completed,
        )

        # Build search_results from the session's accumulated raw data
        accumulated_raw = session.to_raw()
        search_results = _build_search_results(accumulated_raw)

        logger.info(
            "Search results compiled",
            experiment_id=ctx.experiment.id,
            total_search_results=len(search_results),
        )

        return MarketResearch(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            tam_estimate=result.tam_estimate,
            market_growth=result.market_growth,
            demand_signals=result.demand_signals,
            competitors=result.competitors,
            competitor_gaps=result.competitor_gaps,
            target_audience_size=result.target_audience_size,
            willingness_to_pay=result.willingness_to_pay,
            common_complaints=result.common_complaints,
            search_results=search_results,
            key_findings=result.key_findings,
            research_summary=result.research_summary,
            research_rounds_completed=rounds_completed,
            gap_analysis=gap_analysis,
        )

    def _mock_research(self, ctx: StepContext) -> MarketResearch:
        return MarketResearch(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            tam_estimate="$2.5B global market for developer tools",
            market_growth="Growing at 15% CAGR, driven by AI adoption",
            demand_signals=[
                "500+ HN comments about this problem in the last 6 months",
                "Subreddit r/SaaS has weekly threads about this pain point",
                "Google Trends shows 40% increase in related searches YoY",
            ],
            competitors=[
                Competitor(
                    name="ExistingTool",
                    url="https://existingtool.com",
                    description="Market leader but expensive and complex",
                    pricing="$49/month starter, $199/month pro",
                    strengths=["Large user base", "Feature-rich"],
                    weaknesses=["Expensive", "Complex setup", "No AI features"],
                    estimated_users="~50,000",
                    funding="Series B, $25M",
                ),
                Competitor(
                    name="OpenSourceAlt",
                    url="https://github.com/example/alt",
                    description="Free but requires significant setup",
                    pricing="Free (self-hosted)",
                    strengths=["Free", "Customizable"],
                    weaknesses=["Requires DevOps", "Poor documentation", "No support"],
                    estimated_users="~5,000 GitHub stars",
                ),
            ],
            competitor_gaps=[
                "No existing solution offers AI-powered automation",
                "All competitors require 30+ minutes of initial setup",
                "Pricing gap between free self-hosted and $49/month SaaS",
            ],
            target_audience_size="~500,000 potential users globally",
            willingness_to_pay="Competitors charge $29-199/month; users actively pay for solutions in this space",
            common_complaints=[
                "Too expensive for indie developers",
                "Setup takes too long",
                "Missing key integrations",
            ],
            search_results=[
                SearchResult(
                    title="Discussion: Best tools for this problem",
                    url="https://news.ycombinator.com/item?id=12345",
                    snippet="Looking for a simpler alternative...",
                    source="hn",
                    relevance_score=0.92,
                ),
            ],
            key_findings=[
                "Strong demand signals across multiple channels",
                "Existing solutions are either too expensive or too complex",
                "AI-powered approach is a genuine differentiator",
            ],
            research_summary="Strong market opportunity with clear pain points and a viable gap in the competitive landscape. Recommend proceeding to scoring.",
        )
