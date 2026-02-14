"""Step 1: Deep Research — comprehensive market research for an idea."""

from __future__ import annotations

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.research import Competitor, MarketResearch, SearchResult

logger = structlog.get_logger()


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

        logger.info(
            "Starting deep research",
            experiment_id=ctx.experiment.id,
            idea_title=idea.title,
            category=idea.category,
        )

        # Build targeted queries from the idea
        queries = [
            f"{idea.title} competitors alternatives",
            f"{idea.category} market size TAM",
            f'"{idea.target_audience}" pain points {idea.category}',
        ]

        # Collect raw research data from all available APIs
        collector = ResearchCollector(ctx.settings)
        raw_data = collector.collect(
            queries,
            include_reddit=True,
            include_hn_comments=True,
            perplexity_question=(
                f"What is the total addressable market for {idea.title}? "
                "Who are the main competitors and what gaps exist?"
            ),
            exa_similar_url="",
        )

        # Accumulate and deduplicate via ResearchSession
        session = ResearchSession(idea_title=idea.title, idea_category=idea.category)
        session.ingest(raw_data)
        research_text = session.formatted_context

        # Build prompts for LLM synthesis
        system_prompt = (
            "You are a market research analyst. Analyze the provided research "
            "data and produce a comprehensive market assessment. Be "
            "evidence-based — cite specific data points from the research. "
            "Do not invent statistics or data."
        )

        user_prompt = (
            f"## Product Idea\n\n"
            f"**Title**: {idea.title}\n"
            f"**Problem**: {idea.problem_statement}\n"
            f"**Target Audience**: {idea.target_audience}\n"
            f"**Category**: {idea.category}\n\n"
            f"## Research Data\n\n"
            f"{research_text}\n\n"
            f"## Instructions\n\n"
            f"Based on the research data above, produce a comprehensive market "
            f"assessment. For each field, ground your analysis in specific "
            f"evidence from the research data. Include concrete numbers, "
            f"quotes, and references where available."
        )

        # Generate structured LLM output
        llm = LLMClient(ctx.settings)
        result = llm.generate(
            user_prompt,
            _MarketResearchLLMOutput,
            system=system_prompt,
        )

        logger.info(
            "LLM synthesis complete",
            experiment_id=ctx.experiment.id,
            competitor_count=len(result.competitors),
            finding_count=len(result.key_findings),
        )

        # Build search_results from raw API data (NOT LLM-generated)
        search_results: list[SearchResult] = [
            SearchResult(
                title=tr["title"],
                url=tr["url"],
                snippet=tr["content"][:300],
                source="tavily",
                relevance_score=float(tr.get("score", 0.0)),
            )
            for tr in raw_data.tavily_results
        ]

        search_results.extend(
            SearchResult(
                title=sr["title"],
                url=sr["link"],
                snippet=sr["snippet"],
                source="serper",
                relevance_score=0.0,
            )
            for sr in raw_data.serper_results
        )

        search_results.extend(
            SearchResult(
                title=er["title"],
                url=er["url"],
                snippet=er["text"][:300] if er["text"] else "",
                source="exa",
                relevance_score=er["score"],
            )
            for er in raw_data.exa_results
        )

        logger.info(
            "Search results compiled",
            experiment_id=ctx.experiment.id,
            total_search_results=len(search_results),
            tavily_count=len(raw_data.tavily_results),
            serper_count=len(raw_data.serper_results),
            exa_count=len(raw_data.exa_results),
        )

        # Construct full MarketResearch from LLM output + search_results + metadata
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
