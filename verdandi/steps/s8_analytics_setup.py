"""Step 8: Analytics Setup — configure Umami tracking."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from verdandi.models.deployment import AnalyticsSetup, DeploymentResult
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class AnalyticsSetupStep(AbstractStep):
    name = "analytics_setup"
    step_number = 8

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_analytics(ctx)
        # Real implementation will use Umami API
        return self._mock_analytics(ctx)

    def _mock_analytics(self, ctx: StepContext) -> DeploymentResult:
        website_id = str(uuid.uuid4())
        return DeploymentResult(
            experiment_id=ctx.experiment.id or 0,
            step_name="analytics_setup",
            worker_id=ctx.worker_id,
            analytics=AnalyticsSetup(
                website_id=website_id,
                tracking_script_url="https://analytics.example.com/script.js",
                dashboard_url=f"https://analytics.example.com/websites/{website_id}",
                injected=True,
            ),
        )
