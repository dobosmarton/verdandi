"""Step 5: Human Review — pause pipeline for approval before spending money.

The step itself is side-effect-free: it returns a HumanReviewResult indicating
whether approval is needed. The orchestrator handles the actual DB status
update and notification dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.base import BaseStepResult
from verdandi.models.experiment import ExperimentStatus

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

        # Signal that review is needed — orchestrator handles DB write + notification
        return HumanReviewResult(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            approved=False,
            reason="Awaiting human review",
        )
