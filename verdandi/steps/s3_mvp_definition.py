"""Step 3: MVP Definition — define what to build and how to present it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.models.mvp import Feature, MVPDefinition
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class MVPDefinitionStep(AbstractStep):
    name = "mvp_definition"
    step_number = 3

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_mvp(ctx)
        # Real implementation will use LLM to generate MVP spec from research
        return self._mock_mvp(ctx)

    def _mock_mvp(self, ctx: StepContext) -> MVPDefinition:
        return MVPDefinition(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            product_name=ctx.experiment.idea_title.split("—")[0].strip()
            if "—" in ctx.experiment.idea_title
            else ctx.experiment.idea_title,
            tagline="The simplest way to solve your problem",
            value_proposition="Save 10 hours per week with AI-powered automation. No setup required — works out of the box in 60 seconds.",
            target_persona="Sarah, a solo SaaS founder who ships features weekly but dreads the manual overhead of maintenance tasks.",
            features=[
                Feature(
                    title="One-Click Setup",
                    description="Connect your existing tools and get started in under 60 seconds",
                    icon_name="zap",
                ),
                Feature(
                    title="AI-Powered",
                    description="Intelligent automation that learns your preferences over time",
                    icon_name="brain",
                ),
                Feature(
                    title="Real-Time Updates",
                    description="Get instant notifications when something needs your attention",
                    icon_name="bell",
                ),
                Feature(
                    title="Simple Pricing",
                    description="One plan, one price. No surprises, no hidden fees.",
                    icon_name="dollar",
                ),
            ],
            pricing_model="Freemium — free for basic use, $19/month for pro features",
            cta_text="Get Early Access",
            cta_subtext="Free during beta. No credit card required.",
            domain_suggestions=[
                f"{ctx.experiment.idea_title.split('—')[0].strip().lower().replace(' ', '')}.com",
                f"get{ctx.experiment.idea_title.split('—')[0].strip().lower().replace(' ', '')}.com",
                f"try{ctx.experiment.idea_title.split('—')[0].strip().lower().replace(' ', '')}.dev",
            ],
            color_scheme="blue",
        )
