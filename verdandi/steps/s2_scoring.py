"""Step 2: Pre-Build Scoring — quantified go/no-go decision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.models.scoring import Decision, PreBuildScore, ScoreComponent
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class ScoringStep(AbstractStep):
    name = "scoring"
    step_number = 2

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_score(ctx)
        # Real implementation will use LLM to analyze research results
        return self._mock_score(ctx)

    def _mock_score(self, ctx: StepContext) -> PreBuildScore:
        components = [
            ScoreComponent(
                name="pain_severity",
                score=78,
                weight=0.25,
                reasoning="Multiple sources confirm this is a real, recurring pain point",
            ),
            ScoreComponent(
                name="frequency",
                score=72,
                weight=0.15,
                reasoning="Users encounter this weekly to daily",
            ),
            ScoreComponent(
                name="willingness_to_pay",
                score=80,
                weight=0.25,
                reasoning="Existing paid solutions at $29-199/month validate WTP",
            ),
            ScoreComponent(
                name="competitor_gaps",
                score=85,
                weight=0.20,
                reasoning="Clear gap for AI-powered, zero-config solution",
            ),
            ScoreComponent(
                name="tam_size",
                score=65,
                weight=0.15,
                reasoning="Niche market but sufficient for validation ($2.5B TAM)",
            ),
        ]
        total = int(sum(c.score * c.weight for c in components))
        threshold = ctx.settings.score_go_threshold
        decision = Decision.GO if total >= threshold else Decision.NO_GO

        return PreBuildScore(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            components=components,
            total_score=total,
            decision=decision,
            reasoning=f"Score {total}/100 ({'above' if total >= threshold else 'below'} threshold {threshold}). Strong market signals and clear competitor gaps.",
            risks=[
                "Crowded market with well-funded incumbents",
                "AI features require ongoing model costs",
            ],
            opportunities=[
                "First-mover advantage in AI-powered niche",
                "Low-cost acquisition via developer communities",
            ],
        )
