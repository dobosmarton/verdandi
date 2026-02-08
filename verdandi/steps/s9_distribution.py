"""Step 9: Distribution — post to social channels and submit SEO."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.models.distribution import DistributionResult, SEOSubmission, SocialPost
from verdandi.steps.base import AbstractStep, StepContext, register_step

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class DistributionStep(AbstractStep):
    name = "distribution"
    step_number = 9

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_distribution(ctx)
        # Real implementation will use social APIs
        return self._mock_distribution(ctx)

    def _mock_distribution(self, ctx: StepContext) -> DistributionResult:
        title = ctx.experiment.idea_title
        return DistributionResult(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            social_posts=[
                SocialPost(
                    platform="linkedin",
                    content=f"Excited to launch {title}! Solving a real pain point for developers. Check it out and let me know what you think.",
                    url="https://linkedin.com/posts/mock-001",
                    posted=True,
                ),
                SocialPost(
                    platform="twitter",
                    content=f"Just shipped {title} 🚀 — built this to scratch my own itch. Would love your feedback!",
                    url="https://x.com/mock/status/001",
                    posted=True,
                ),
                SocialPost(
                    platform="reddit",
                    content=f"Show r/SaaS: I built {title} to solve {ctx.experiment.idea_summary or 'a common problem'}",
                    posted=False,
                ),
            ],
            seo=SEOSubmission(
                google_search_console_submitted=True,
                sitemap_url="https://example.com/sitemap.xml",
            ),
            total_reach_estimate=2500,
        )
