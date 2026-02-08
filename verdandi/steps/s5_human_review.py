"""Step 5: Human Review — pause pipeline for approval before spending money."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from verdandi.models.base import BaseStepResult
from verdandi.models.experiment import ExperimentStatus
from verdandi.notifications import notify_review_needed
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = structlog.get_logger()


class HumanReviewResult(BaseStepResult):
    """Output of Step 5: review status."""

    step_name: str = "human_review"
    approved: bool = False
    skipped: bool = False
    reason: str = ""


@register_step
class HumanReviewStep(AbstractStep):
    name = "human_review"
    step_number = 5

    def should_skip(self, ctx: StepContext) -> bool:
        """Skip review in dry-run mode or when review is disabled."""
        if ctx.dry_run:
            return True
        if not ctx.settings.require_human_review:
            return True
        # If already approved, skip
        return ctx.experiment.status == ExperimentStatus.APPROVED

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run or not ctx.settings.require_human_review:
            return HumanReviewResult(
                experiment_id=ctx.experiment.id or 0,
                worker_id=ctx.worker_id,
                approved=True,
                skipped=True,
                reason="Dry run" if ctx.dry_run else "Human review disabled",
            )

        if ctx.experiment.status == ExperimentStatus.APPROVED:
            return HumanReviewResult(
                experiment_id=ctx.experiment.id or 0,
                worker_id=ctx.worker_id,
                approved=True,
                reason="Previously approved",
            )

        # Pause pipeline — set status and notify
        ctx.db.update_experiment_status(
            ctx.experiment.id,  # type: ignore[arg-type]
            ExperimentStatus.AWAITING_REVIEW,
            current_step=self.step_number,
        )
        notify_review_needed(
            ctx.experiment.id or 0,
            ctx.experiment.idea_title,
        )

        return HumanReviewResult(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            approved=False,
            reason="Awaiting human review",
        )
