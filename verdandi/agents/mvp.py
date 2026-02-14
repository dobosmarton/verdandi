"""Step 3: MVP Definition — define what to build and how to present it."""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.mvp import Feature, MVPDefinition

logger = structlog.get_logger()

_SYSTEM_PROMPT = (
    "You are a product strategist defining an MVP for a landing page validation test. "
    "Create a compelling, specific product definition based on the research. "
    "The product name should be memorable and available as a .com domain. "
    "Suggest 3-5 features, a clear pricing model, and a strong call-to-action. "
    "Domain suggestions should use .com or .dev TLDs."
)


class _MVPDefinitionLLMOutput(BaseModel):
    """LLM-generated MVP content fields (no infrastructure fields)."""

    model_config = ConfigDict(frozen=True)

    product_name: str
    tagline: str
    value_proposition: str
    target_persona: str
    features: list[Feature]
    pricing_model: str
    cta_text: str
    cta_subtext: str
    domain_suggestions: list[str]
    color_scheme: str


@register_step
class MVPDefinitionStep(AbstractStep):
    name = "mvp_definition"
    step_number = 3

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_mvp(ctx)

        from verdandi.llm import LLMClient
        from verdandi.models.idea import IdeaCandidate
        from verdandi.models.research import MarketResearch

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID — cannot define MVP")

        # Retrieve Step 0 (idea) and Step 1 (research) results
        if ctx.prior_results is not None:
            idea = ctx.prior_results.get_typed("idea_discovery", IdeaCandidate)
            research = ctx.prior_results.get_typed("deep_research", MarketResearch)
        elif ctx.db is not None:
            idea_result = ctx.db.get_step_result(experiment_id, "idea_discovery")
            if idea_result is None:
                msg = f"No idea_discovery result found for experiment {ctx.experiment.id}"
                raise ValueError(msg)
            idea = IdeaCandidate.model_validate_json(json.dumps(idea_result["data"]))

            research_result = ctx.db.get_step_result(experiment_id, "deep_research")
            if research_result is None:
                msg = f"No deep_research result found for experiment {ctx.experiment.id}"
                raise ValueError(msg)
            research = MarketResearch.model_validate_json(json.dumps(research_result["data"]))
        else:
            raise RuntimeError("No prior_results or db available to retrieve prerequisites")

        # Build the user prompt with idea and research context
        competitor_summary = "\n".join(
            f"  - {c.name}: {c.description} (pricing: {c.pricing})" for c in research.competitors
        )
        gaps_summary = "\n".join(f"  - {gap}" for gap in research.competitor_gaps)
        complaints_summary = "\n".join(
            f"  - {complaint}" for complaint in research.common_complaints
        )
        pain_points_summary = "\n".join(
            f"  - {pp.description} (severity: {pp.severity}/10, frequency: {pp.frequency})"
            for pp in idea.pain_points
        )

        user_prompt = f"""Define an MVP for the following product idea based on the research below.

## Idea
- Title: {idea.title}
- One-liner: {idea.one_liner}
- Problem: {idea.problem_statement}
- Target audience: {idea.target_audience}
- Category: {idea.category}
- Differentiation: {idea.differentiation}

## Pain Points
{pain_points_summary}

## Market Research
- TAM estimate: {research.tam_estimate}
- Market growth: {research.market_growth}
- Target audience size: {research.target_audience_size}
- Willingness to pay: {research.willingness_to_pay}

## Competitors
{competitor_summary}

## Competitor Gaps
{gaps_summary}

## Common Complaints About Existing Solutions
{complaints_summary}

## Key Findings
{chr(10).join(f"  - {f}" for f in research.key_findings)}

## Research Summary
{research.research_summary}

Based on this research, define a compelling MVP with a memorable product name, clear value proposition, 3-5 specific features, pricing model, and call-to-action. The product should address the identified gaps and pain points. Suggest domain names using .com or .dev TLDs."""

        logger.info(
            "Generating MVP definition via LLM",
            experiment_id=ctx.experiment.id,
            idea_title=idea.title,
        )

        llm = LLMClient(ctx.settings)
        result = llm.generate(
            user_prompt,
            _MVPDefinitionLLMOutput,
            system=_SYSTEM_PROMPT,
        )

        logger.info(
            "MVP definition generated",
            experiment_id=ctx.experiment.id,
            product_name=result.product_name,
            num_features=len(result.features),
        )

        return MVPDefinition(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            product_name=result.product_name,
            tagline=result.tagline,
            value_proposition=result.value_proposition,
            target_persona=result.target_persona,
            features=result.features,
            pricing_model=result.pricing_model,
            cta_text=result.cta_text,
            cta_subtext=result.cta_subtext,
            domain_suggestions=result.domain_suggestions,
            color_scheme=result.color_scheme,
        )

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
