"""Council Dissent Analyzer — detects vote splits and drives follow-up research.

When council members disagree on scoring dimensions (spread > threshold) or on
the overall GO/NO_GO decision, the analyzer generates targeted follow-up
queries, collects additional research, and triggers a re-scoring round with
the augmented evidence.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.models.scoring import (
    CouncilMemberVote,
    DimensionDissent,
    DissentAnalysis,
    DissentResolutionRound,
    PreBuildScore,
)

if TYPE_CHECKING:
    from verdandi.agents.base import StepContext
    from verdandi.config import Settings
    from verdandi.models.idea import IdeaCandidate
    from verdandi.models.research import MarketResearch
    from verdandi.protocols import ResearchProviderPort

logger = structlog.get_logger()

# Scoring dimension → research dimension mapping.
# Scoring and research evolved independently and use different names.
_SCORING_TO_RESEARCH_DIM: dict[str, str] = {
    "pain_severity": "pain_severity",
    "frequency": "demand_evidence",
    "willingness_to_pay": "willingness_to_pay",
    "competitor_gaps": "competitors",
    "tam_size": "market_size",
}

# Human-readable labels for LLM prompts
_DIM_LABELS: dict[str, str] = {
    "pain_severity": "pain severity and user complaints",
    "frequency": "problem frequency and demand evidence",
    "willingness_to_pay": "willingness to pay and pricing data",
    "competitor_gaps": "competitor weaknesses and market gaps",
    "tam_size": "total addressable market size and growth",
}

# Providers used for targeted follow-up (cheap + question-friendly)
_FOLLOWUP_PROVIDER_NAMES: frozenset[str] = frozenset({"tavily", "perplexity", "firecrawl"})

_QUERY_GEN_SYSTEM = (
    "You are a market research analyst. Generate specific, targeted search "
    "queries to resolve disagreements in a product scoring panel. Focus on "
    "finding concrete evidence — numbers, pricing data, user complaints, "
    "market reports. Be specific: include company names, product names, "
    "or precise market terms."
)


class _FollowupQueryOutput(BaseModel):
    """LLM output for follow-up query generation."""

    model_config = ConfigDict(frozen=True)

    queries: list[str]


class DissentAnalyzer:
    """Detects council vote splits and drives targeted follow-up research."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def detect_dissent(self, votes: list[CouncilMemberVote]) -> list[DimensionDissent]:
        """Find dimensions where council members disagree beyond threshold.

        A dimension is flagged when the spread (max - min) across all voters
        exceeds ``dissent_dimension_threshold``.
        """
        threshold = self.settings.dissent_dimension_threshold
        dissents: list[DimensionDissent] = []

        for dim_name in _SCORING_TO_RESEARCH_DIM:
            scores_by_provider: dict[str, int] = {}
            reasonings: list[str] = []

            for vote in votes:
                for comp in vote.components:
                    if comp.name == dim_name:
                        scores_by_provider[vote.provider_name] = comp.score
                        if comp.reasoning:
                            reasonings.append(f"{vote.provider_name}: {comp.reasoning}")
                        break

            if len(scores_by_provider) < 2:
                continue

            score_values = list(scores_by_provider.values())
            spread = max(score_values) - min(score_values)

            if spread >= threshold:
                median_score = int(statistics.median(score_values))
                dissents.append(
                    DimensionDissent(
                        dimension=dim_name,
                        scores_by_provider=scores_by_provider,
                        spread=spread,
                        median_score=median_score,
                        reasoning_excerpts=reasonings,
                    )
                )

        return dissents

    def _has_decision_split(self, votes: list[CouncilMemberVote]) -> bool:
        """Check if voters disagree on the GO/NO_GO decision."""
        decisions = {v.decision for v in votes}
        return len(decisions) > 1

    def build_followup_queries(
        self,
        dissents: list[DimensionDissent],
        idea: IdeaCandidate,
        research: MarketResearch,
    ) -> list[str]:
        """Generate targeted search queries for contested dimensions via LLM."""
        from verdandi.llm import LLMClient

        dim_details: list[str] = []
        for d in dissents:
            label = _DIM_LABELS.get(d.dimension, d.dimension)
            scores = ", ".join(f"{prov}: {score}" for prov, score in d.scores_by_provider.items())
            dim_details.append(f"- **{label}** (spread: {d.spread} points) — scores: {scores}")

        prompt = (
            f"## Product Idea\n\n"
            f"**Title**: {idea.title}\n"
            f"**Problem**: {idea.problem_statement}\n"
            f"**Category**: {idea.category}\n\n"
            f"## Contested Dimensions\n\n"
            f"A panel of AI models scored this idea and disagreed on:\n"
            f"{''.join(dim_details)}\n\n"
            f"## Existing Evidence Summary\n\n"
            f"- TAM: {research.tam_estimate or '(unknown)'}\n"
            f"- WTP: {research.willingness_to_pay or '(unknown)'}\n"
            f"- Competitors: {len(research.competitors)} found\n"
            f"- Sources: {len(research.search_results)} total\n\n"
            f"## Instructions\n\n"
            f"Generate 2-3 specific search queries per contested dimension "
            f"that would produce concrete evidence to resolve the disagreement. "
            f"Total queries should be at most {min(len(dissents) * 3, 8)}. "
            f"Focus on finding hard numbers, pricing pages, user reviews, "
            f"market reports, or usage statistics."
        )

        llm = LLMClient(self.settings)
        result = llm.generate(prompt, _FollowupQueryOutput, system=_QUERY_GEN_SYSTEM)
        return result.queries[: min(len(dissents) * 3, 8)]

    def run_followup_research(
        self,
        queries: list[str],
        idea: IdeaCandidate,
    ) -> int:
        """Collect targeted research and return the number of new sources."""
        from verdandi.research import ResearchCollector

        collector = ResearchCollector(
            self.settings,
            providers=self._get_followup_providers(),
        )

        raw = collector.collect(
            queries,
            include_reddit=False,
            include_twitter=False,
            include_hn_comments=False,
        )

        return len(raw.sources_used)

    def _get_followup_providers(self) -> list[ResearchProviderPort]:
        """Get only the follow-up subset of research providers."""
        from verdandi.providers import default_providers

        all_providers = default_providers(self.settings)
        return [p for p in all_providers if p.name in _FOLLOWUP_PROVIDER_NAMES and p.is_available]

    def resolve(
        self,
        ctx: StepContext,
        initial_score: PreBuildScore,
    ) -> PreBuildScore:
        """Full dissent resolution: detect -> research -> re-score -> attach analysis."""
        if not initial_score.council_votes:
            return initial_score.model_copy(
                update={"dissent_analysis": DissentAnalysis(dissent_detected=False)}
            )

        dissents = self.detect_dissent(initial_score.council_votes)
        has_decision_split = self._has_decision_split(initial_score.council_votes)

        # Check if dissent resolution should trigger
        if self.settings.dissent_decision_split_required and not has_decision_split:
            dissents = []

        if not dissents:
            logger.info(
                "No council dissent detected",
                experiment_id=ctx.experiment.id,
            )
            return initial_score.model_copy(
                update={
                    "dissent_analysis": DissentAnalysis(
                        dissent_detected=False,
                        initial_score=initial_score.total_score,
                        final_score=initial_score.total_score,
                    )
                }
            )

        logger.info(
            "Council dissent detected",
            experiment_id=ctx.experiment.id,
            contested_dimensions=[d.dimension for d in dissents],
            has_decision_split=has_decision_split,
        )

        # Load prerequisites for query generation
        from verdandi.models.idea import IdeaCandidate
        from verdandi.models.research import MarketResearch

        if ctx.prior_results is not None:
            idea = ctx.prior_results.get_typed("idea_discovery", IdeaCandidate)
            research = ctx.prior_results.get_typed("deep_research", MarketResearch)
        else:
            raise RuntimeError("No prior_results available for dissent resolution")

        resolution_rounds: list[DissentResolutionRound] = []
        current_score = initial_score
        max_rounds = self.settings.dissent_max_rounds

        for round_num in range(1, max_rounds + 1):
            logger.info(
                "Dissent resolution round",
                round=round_num,
                contested=[d.dimension for d in dissents],
                experiment_id=ctx.experiment.id,
            )

            # Generate follow-up queries
            queries = self.build_followup_queries(dissents, idea, research)
            if not queries:
                logger.info("No follow-up queries generated, stopping")
                break

            # Collect follow-up research
            new_sources = self.run_followup_research(queries, idea)

            # Re-score with augmented prompt
            augmented_score = self._rescore_with_context(ctx, idea, research, dissents, queries)

            decision_changed = augmented_score.decision != current_score.decision

            resolution_rounds.append(
                DissentResolutionRound(
                    round_number=round_num,
                    contested_dimensions=[d.dimension for d in dissents],
                    followup_queries=queries,
                    new_sources_count=new_sources,
                    score_before=current_score.total_score,
                    score_after=augmented_score.total_score,
                    decision_changed=decision_changed,
                )
            )

            current_score = augmented_score

            # Re-detect dissent on new votes
            if current_score.council_votes:
                dissents = self.detect_dissent(current_score.council_votes)
                if not dissents:
                    logger.info("Dissent resolved after round", round=round_num)
                    break

        decision_flipped = initial_score.decision != current_score.decision

        analysis = DissentAnalysis(
            dissent_detected=True,
            dimension_dissents=dissents,
            resolution_rounds=resolution_rounds,
            decision_flipped=decision_flipped,
            initial_score=initial_score.total_score,
            final_score=current_score.total_score,
        )

        logger.info(
            "Dissent resolution complete",
            experiment_id=ctx.experiment.id,
            rounds_completed=len(resolution_rounds),
            initial_score=initial_score.total_score,
            final_score=current_score.total_score,
            decision_flipped=decision_flipped,
        )

        return current_score.model_copy(update={"dissent_analysis": analysis})

    def _rescore_with_context(
        self,
        ctx: StepContext,
        idea: IdeaCandidate,
        research: MarketResearch,
        dissents: list[DimensionDissent],
        followup_queries: list[str],
    ) -> PreBuildScore:
        """Re-score via the Agent Council with dissent context added to prompt."""
        from verdandi.agents.council import AgentCouncil
        from verdandi.agents.scoring import (
            _SYSTEM_PROMPT,
            ScoringStep,
            _ScoringLLMOutput,
        )

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID")

        # Build the base prompt
        step = ScoringStep()
        base_prompt = step._build_user_prompt(idea, research)

        # Append dissent context
        dim_details: list[str] = []
        for d in dissents:
            scores = ", ".join(f"{prov}: {score}" for prov, score in d.scores_by_provider.items())
            dim_details.append(f"- **{d.dimension}** (spread: {d.spread}) — {scores}")

        dissent_section = (
            f"\n\n## Additional Context: Scoring Panel Disagreements\n\n"
            f"A previous scoring round revealed disagreements on these "
            f"dimensions:\n{''.join(dim_details)}\n\n"
            f"Follow-up research queries were conducted:\n"
            f"{''.join(f'- {q}' for q in followup_queries)}\n\n"
            f"Please pay special attention to these contested dimensions "
            f"and score based on the totality of evidence. If the original "
            f"research was ambiguous, note this in your reasoning."
        )

        augmented_prompt = base_prompt + dissent_section

        council = AgentCouncil(ctx.settings)
        return council.evaluate(
            user_prompt=augmented_prompt,
            system_prompt=_SYSTEM_PROMPT,
            scoring_output_type=_ScoringLLMOutput,
            experiment_id=experiment_id,
            worker_id=ctx.worker_id,
            novelty_score=idea.novelty_score,
            threshold=ctx.settings.score_go_threshold,
        )
