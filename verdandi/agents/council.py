"""Agent Council: multi-model scoring panel for go/no-go decisions.

Runs the same scoring prompt across multiple LLM providers (Anthropic, OpenAI,
Google) in parallel and aggregates their independent votes via majority rule.
"""

from __future__ import annotations

import asyncio
import math
from collections import Counter
from typing import TYPE_CHECKING, Any

import structlog

from verdandi.llm import LLMClient, _get_or_create_event_loop
from verdandi.metrics import council_evaluations_total, council_votes_total
from verdandi.models.scoring import (
    CouncilMemberVote,
    CouncilResult,
    Decision,
    PreBuildScore,
    ScoreComponent,
)

if TYPE_CHECKING:
    from verdandi.config import Settings

logger = structlog.get_logger()

_NOVELTY_BONUS_POINTS = 10

_DIMENSION_NAMES = (
    "pain_severity",
    "frequency",
    "willingness_to_pay",
    "competitor_gaps",
    "tam_size",
)


class AgentCouncil:
    """Runs the same scoring prompt across multiple LLM providers in parallel."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _discover_available_providers(self) -> list[tuple[str, LLMClient]]:
        """Detect which providers have valid API keys and return LLMClient instances."""
        providers: list[tuple[str, LLMClient]] = []

        if self.settings.anthropic_api_key:
            providers.append(("anthropic", LLMClient(self.settings, provider_name="anthropic")))

        if self.settings.openai_api_key:
            providers.append(("openai", LLMClient(self.settings, provider_name="openai")))

        if self.settings.google_api_key:
            providers.append(("google", LLMClient(self.settings, provider_name="google")))

        return providers

    def evaluate(
        self,
        user_prompt: str,
        system_prompt: str,
        scoring_output_type: type[Any],
        experiment_id: int,
        worker_id: str,
        novelty_score: float,
        threshold: int,
    ) -> PreBuildScore:
        """Run all council members in parallel and aggregate results."""
        providers = self._discover_available_providers()

        if len(providers) < 2:
            msg = (
                f"Council requires >= 2 providers but only {len(providers)} available. "
                "Disable council_enabled or add more API keys."
            )
            raise RuntimeError(msg)

        logger.info(
            "Council evaluation starting",
            providers=[name for name, _ in providers],
            experiment_id=experiment_id,
        )

        votes = self._run_parallel(
            providers, user_prompt, system_prompt, scoring_output_type
        )

        if not votes:
            msg = "All council members failed — cannot produce a score"
            raise RuntimeError(msg)

        council_result = self._aggregate(votes, novelty_score, threshold)

        # Record metrics
        for vote in votes:
            council_votes_total.labels(
                provider=vote.provider_name, decision=vote.decision.value
            ).inc()
        council_evaluations_total.labels(
            decision=council_result.decision.value,
            num_providers=str(len(votes)),
        ).inc()

        logger.info(
            "Council evaluation complete",
            experiment_id=experiment_id,
            go_votes=sum(1 for v in votes if v.decision == Decision.GO),
            nogo_votes=sum(1 for v in votes if v.decision == Decision.NO_GO),
            final_decision=council_result.decision.value,
            aggregated_score=council_result.total_score,
        )

        return PreBuildScore(
            experiment_id=experiment_id,
            worker_id=worker_id,
            components=council_result.aggregated_components,
            total_score=council_result.total_score,
            decision=council_result.decision,
            reasoning=council_result.reasoning,
            risks=council_result.aggregated_risks,
            opportunities=council_result.aggregated_opportunities,
            council_votes=votes,
        )

    def _run_parallel(
        self,
        providers: list[tuple[str, LLMClient]],
        user_prompt: str,
        system_prompt: str,
        scoring_output_type: type[Any],
    ) -> list[CouncilMemberVote]:
        """Run scoring across all providers concurrently."""
        threshold = self.settings.score_go_threshold

        async def _score_one(name: str, client: LLMClient) -> CouncilMemberVote:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: client.generate(
                    user_prompt,
                    scoring_output_type,
                    system=system_prompt,
                ),
            )
            base_total = int(sum(c.score * c.weight for c in result.components))
            decision = Decision.GO if base_total >= threshold else Decision.NO_GO

            return CouncilMemberVote(
                provider_name=name,
                model_name=client.model_name,
                components=list(result.components),
                base_score=base_total,
                decision=decision,
                risks=list(result.risks),
                opportunities=list(result.opportunities),
                reasoning_summary=result.reasoning_summary,
            )

        async def _gather_all() -> list[CouncilMemberVote]:
            tasks = [_score_one(name, client) for name, client in providers]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            votes: list[CouncilMemberVote] = []
            for i, result in enumerate(results):
                name = providers[i][0]
                if isinstance(result, BaseException):
                    logger.error(
                        "Council member failed",
                        provider=name,
                        error=str(result),
                    )
                    continue
                votes.append(result)
            return votes

        loop = _get_or_create_event_loop()
        return loop.run_until_complete(_gather_all())

    def _aggregate(
        self,
        votes: list[CouncilMemberVote],
        novelty_score: float,
        threshold: int,
    ) -> CouncilResult:
        """Aggregate individual votes into a council decision.

        - Component scores: median across all voters per dimension
        - Decision: majority vote (>= ceil(n/2) must agree GO)
        - Risks/Opportunities: union-deduplicated
        """
        # Majority vote
        decision_counts = Counter(v.decision for v in votes)
        majority_threshold = math.ceil(len(votes) / 2)
        go_count = decision_counts.get(Decision.GO, 0)
        final_decision = Decision.GO if go_count >= majority_threshold else Decision.NO_GO

        # Aggregate component scores using median
        aggregated_components: list[ScoreComponent] = []

        for dim in _DIMENSION_NAMES:
            dim_scores: list[int] = []
            dim_reasonings: list[str] = []
            dim_weight = 0.0

            for vote in votes:
                for comp in vote.components:
                    if comp.name == dim:
                        dim_scores.append(comp.score)
                        dim_reasonings.append(f"[{vote.provider_name}] {comp.reasoning}")
                        dim_weight = comp.weight
                        break

            if dim_scores:
                sorted_scores = sorted(dim_scores)
                mid = len(sorted_scores) // 2
                median_score = sorted_scores[mid]
                combined_reasoning = " | ".join(dim_reasonings)
                aggregated_components.append(
                    ScoreComponent(
                        name=dim,
                        score=median_score,
                        weight=dim_weight,
                        reasoning=combined_reasoning,
                    )
                )

        # Compute aggregated total with novelty bonus
        base_total = int(sum(c.score * c.weight for c in aggregated_components))
        novelty_bonus = int(novelty_score * _NOVELTY_BONUS_POINTS)
        total = min(base_total + novelty_bonus, 100)

        # Union risks and opportunities (deduplicated by lowercase)
        all_risks: list[str] = []
        all_opportunities: list[str] = []
        seen_risks: set[str] = set()
        seen_opps: set[str] = set()

        for vote in votes:
            for r in vote.risks:
                key = r.lower().strip()
                if key not in seen_risks:
                    seen_risks.add(key)
                    all_risks.append(r)
            for o in vote.opportunities:
                key = o.lower().strip()
                if key not in seen_opps:
                    seen_opps.add(key)
                    all_opportunities.append(o)

        # Build reasoning summary
        vote_summary = ", ".join(
            f"{v.provider_name}={v.decision.value}({v.base_score})"
            for v in votes
        )
        reasoning = (
            f"Council vote: {vote_summary}. "
            f"Decision: {final_decision.value} ({go_count}/{len(votes)} GO). "
            f"Aggregated score: {total}/100 (base={base_total}, novelty_bonus={novelty_bonus})."
        )

        return CouncilResult(
            votes=votes,
            aggregated_components=aggregated_components,
            total_score=total,
            decision=final_decision,
            reasoning=reasoning,
            aggregated_risks=all_risks,
            aggregated_opportunities=all_opportunities,
        )
