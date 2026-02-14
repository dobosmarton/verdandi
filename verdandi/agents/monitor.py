"""Step 10: Monitor — poll analytics and make go/no-go decision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.validation import MetricsSnapshot, ValidationDecision, ValidationReport

if TYPE_CHECKING:
    from pydantic import BaseModel


@register_step
class MonitorStep(AbstractStep):
    name = "monitor"
    step_number = 10

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_validation(ctx)
        # Real implementation will poll Umami + EmailOctopus APIs
        return self._mock_validation(ctx)

    def _mock_validation(self, ctx: StepContext) -> ValidationReport:
        metrics = MetricsSnapshot(
            total_visitors=347,
            unique_visitors=312,
            pageviews=521,
            bounce_rate=58.2,
            avg_time_on_page_seconds=42.5,
            cta_clicks=67,
            cta_click_rate=21.5,
            email_signups=38,
            email_signup_rate=12.2,
            referral_sources={
                "linkedin": 145,
                "twitter": 87,
                "reddit": 52,
                "direct": 28,
            },
        )

        # Apply decision logic
        go_rate = ctx.settings.monitor_email_signup_go
        nogo_rate = ctx.settings.monitor_email_signup_nogo
        max_bounce = ctx.settings.monitor_bounce_rate_max
        min_visitors = ctx.settings.monitor_min_visitors

        if metrics.unique_visitors < min_visitors:
            decision = ValidationDecision.INSUFFICIENT_DATA
            reasoning = f"Only {metrics.unique_visitors} visitors (need {min_visitors})"
        elif metrics.email_signup_rate >= go_rate and metrics.bounce_rate <= max_bounce:
            decision = ValidationDecision.GO
            reasoning = f"Strong signals: {metrics.email_signup_rate}% signup rate, {metrics.bounce_rate}% bounce"
        elif metrics.email_signup_rate < nogo_rate or metrics.bounce_rate > max_bounce:
            decision = ValidationDecision.NO_GO
            reasoning = f"Weak signals: {metrics.email_signup_rate}% signup rate, {metrics.bounce_rate}% bounce"
        else:
            decision = ValidationDecision.ITERATE
            reasoning = f"Mixed signals: {metrics.email_signup_rate}% signup rate, {metrics.bounce_rate}% bounce"

        return ValidationReport(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            metrics=metrics,
            decision=decision,
            reasoning=reasoning,
            days_monitored=7,
            snapshots_collected=14,
            go_email_signup_rate=go_rate,
            nogo_email_signup_rate=nogo_rate,
            max_bounce_rate=max_bounce,
            min_visitors_required=min_visitors,
            iterate_suggestions=[
                "Test alternative headlines",
                "Add more social proof",
                "Try different CTA copy",
            ],
            next_steps=[
                "Send follow-up email to signups asking about WTP",
                "Add pricing page for A/B test",
            ],
        )
