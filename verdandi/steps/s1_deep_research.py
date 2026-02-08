"""Step 1: Deep Research — comprehensive market research for an idea."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.models.research import Competitor, MarketResearch, SearchResult
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class DeepResearchStep(AbstractStep):
    name = "deep_research"
    step_number = 1

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_research(ctx)
        # Real implementation will use Tavily, Serper, Exa, Perplexity
        return self._mock_research(ctx)

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
