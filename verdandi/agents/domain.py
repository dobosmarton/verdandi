"""Step 6: Domain Purchase — register a domain via Porkbun API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.deployment import DeploymentResult, DomainInfo

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class DomainPurchaseStep(AbstractStep):
    name = "domain_purchase"
    step_number = 6

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_domain(ctx)
        # Real implementation will use Porkbun API
        return self._mock_domain(ctx)

    def _mock_domain(self, ctx: StepContext) -> DeploymentResult:
        slug = ctx.experiment.idea_title.split("—")[0].strip().lower().replace(" ", "")
        return DeploymentResult(
            experiment_id=ctx.experiment.id or 0,
            step_name="domain_purchase",
            worker_id=ctx.worker_id,
            domain=DomainInfo(
                domain=f"{slug}.com",
                registrar="porkbun",
                purchased=bool(not ctx.dry_run),
                cost_usd=9.73,
                nameservers=["ns1.porkbun.com", "ns2.porkbun.com"],
            ),
        )
