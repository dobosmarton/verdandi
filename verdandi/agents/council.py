"""Agent Council: multi-model scoring panel for go/no-go decisions.

Runs the same scoring prompt across multiple LLM providers and aggregates
their independent votes via majority rule.

Uses a quorum-based early-exit strategy: a randomly-chosen initial quorum of
``N // 2 + 1`` providers runs in parallel.  If they unanimously agree the
decision is locked and remaining providers are skipped.  Otherwise reserves
are added one-by-one until the majority can no longer be overturned.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import structlog

from verdandi.llm import LLMClient
from verdandi.metrics import (
    council_early_exits_total,
    council_evaluations_total,
    council_votes_total,
)
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

        votes = self._run_parallel(providers, user_prompt, system_prompt, scoring_output_type)

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
            providers_used=len(votes),
            providers_available=len(providers),
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

    def _score_one_sync(
        self,
        name: str,
        client: LLMClient,
        user_prompt: str,
        system_prompt: str,
        scoring_output_type: type[Any],
    ) -> CouncilMemberVote:
        """Score one provider synchronously. Runs in an executor thread."""
        threshold = self.settings.score_go_threshold
        result = client.generate(user_prompt, scoring_output_type, system=system_prompt)
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

    @staticmethod
    def _has_consensus(go_count: int, nogo_count: int, remaining: int) -> bool:
        """Check whether the majority decision is locked.

        Returns ``True`` when additional votes cannot change the outcome:
        - GO is locked if ``go_count`` already meets the majority threshold.
        - NO_GO is locked if GO cannot reach the majority even if every
          remaining provider votes GO.
        """
        max_total = go_count + nogo_count + remaining
        majority = math.ceil(max_total / 2)
        # GO already has enough votes
        if go_count >= majority:
            return True
        # GO can never reach majority even with all remaining
        return go_count + remaining < majority

    def _run_parallel(
        self,
        providers: list[tuple[str, LLMClient]],
        user_prompt: str,
        system_prompt: str,
        scoring_output_type: type[Any],
    ) -> list[CouncilMemberVote]:
        """Run scoring with quorum-based early-exit.

        1. Shuffle providers randomly for fairness.
        2. Run an initial quorum of ``N // 2 + 1`` in parallel.
        3. If the quorum unanimously agrees and consensus is locked, return
           immediately — remaining providers are never called.
        4. Otherwise add reserve providers one-by-one, stopping as soon as
           the majority can no longer be overturned.
        """
        shuffled = random.sample(providers, len(providers))
        n = len(shuffled)
        quorum_size = n // 2 + 1
        quorum = shuffled[:quorum_size]
        reserves = shuffled[quorum_size:]

        def _submit(
            executor: ThreadPoolExecutor, name: str, client: LLMClient
        ) -> Future[CouncilMemberVote]:
            return executor.submit(
                self._score_one_sync,
                name,
                client,
                user_prompt,
                system_prompt,
                scoring_output_type,
            )

        def _resolve(future: Future[CouncilMemberVote], name: str) -> CouncilMemberVote | None:
            try:
                return future.result()
            except Exception as exc:
                logger.error("Council member failed", provider=name, error=str(exc))
                return None

        with ThreadPoolExecutor(max_workers=quorum_size) as executor:
            # Phase 1 — run initial quorum in parallel
            futures = [_submit(executor, name, client) for name, client in quorum]
            votes: list[CouncilMemberVote] = []
            for i, future in enumerate(futures):
                vote = _resolve(future, quorum[i][0])
                if vote is not None:
                    votes.append(vote)

            go_count = sum(1 for v in votes if v.decision == Decision.GO)
            nogo_count = len(votes) - go_count

            # Check for early exit after quorum
            if votes and self._has_consensus(go_count, nogo_count, len(reserves)):
                council_early_exits_total.labels(
                    decision=Decision.GO.value if go_count >= nogo_count else Decision.NO_GO.value
                ).inc()
                logger.info(
                    "Council early exit",
                    decision=Decision.GO.value if go_count >= nogo_count else Decision.NO_GO.value,
                    providers_used=[v.provider_name for v in votes],
                    providers_skipped=[name for name, _ in reserves],
                )
                return votes

            # Phase 2 — add reserves one-by-one until consensus
            for idx, (name, client) in enumerate(reserves):
                vote = _resolve(_submit(executor, name, client), name)
                if vote is not None:
                    votes.append(vote)
                    if vote.decision == Decision.GO:
                        go_count += 1
                    else:
                        nogo_count += 1

                remaining = len(reserves) - idx - 1
                if self._has_consensus(go_count, nogo_count, remaining):
                    logger.info(
                        "Council consensus reached",
                        go_votes=go_count,
                        nogo_votes=nogo_count,
                        providers_used=[v.provider_name for v in votes],
                    )
                    break

            return votes

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
            f"{v.provider_name}={v.decision.value}({v.base_score})" for v in votes
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
