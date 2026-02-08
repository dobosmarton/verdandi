"""Step 7: Deploy — deploy landing page to Cloudflare Pages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.models.deployment import CloudflareDeployment, DeploymentResult
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class DeployStep(AbstractStep):
    name = "deploy"
    step_number = 7

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_deploy(ctx)
        # Real implementation will use Cloudflare Pages API
        return self._mock_deploy(ctx)

    def _mock_deploy(self, ctx: StepContext) -> DeploymentResult:
        slug = ctx.experiment.idea_title.split("—")[0].strip().lower().replace(" ", "")
        return DeploymentResult(
            experiment_id=ctx.experiment.id or 0,
            step_name="deploy",
            worker_id=ctx.worker_id,
            cloudflare=CloudflareDeployment(
                project_name=slug,
                deployment_url=f"https://{slug}.pages.dev",
                custom_domain=f"{slug}.com",
                ssl_active=True,
                deployment_id="mock-deploy-001",
            ),
            live_url=f"https://{slug}.com",
        )
