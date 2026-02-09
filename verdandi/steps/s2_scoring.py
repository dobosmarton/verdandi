"""Step 2: Pre-Build Scoring — quantified go/no-go decision."""

from __future__ import annotations

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.models.scoring import Decision, PreBuildScore, ScoreComponent
from verdandi.steps.base import AbstractStep, StepContext, register_step

logger = structlog.get_logger()

_SYSTEM_PROMPT = (
    "You are a product validation analyst. Score the following product idea "
    "across 5 dimensions based on the research evidence. Score each dimension "
    "0-100 where 50=neutral, below 40=negative signal, above 70=strong positive. "
    "Be calibrated — only score high when evidence strongly supports it. "
    "Do not be overly optimistic."
)

_USER_PROMPT_TEMPLATE = """\
## Product Idea

**Title:** {title}
**Problem Statement:** {problem_statement}
**Target Audience:** {target_audience}
**Category:** {category}
**Differentiation:** {differentiation}

## Research Findings

**TAM Estimate:** {tam_estimate}
**Market Growth:** {market_growth}

**Demand Signals:**
{demand_signals}

**Competitors:**
{competitors}

**Competitor Gaps:**
{competitor_gaps}

**Willingness to Pay:** {willingness_to_pay}

**Common Complaints:**
{common_complaints}

**Key Findings:**
{key_findings}

## Scoring Dimensions

Score each of the following dimensions from 0 to 100. Provide a reasoning \
for each score.

1. **pain_severity** (weight: 0.25) — How severe is the pain point? \
Look at pain point descriptions, severity ratings, and user quotes.
2. **frequency** (weight: 0.15) — How often do users encounter this problem? \
Daily problems score higher than annual ones.
3. **willingness_to_pay** (weight: 0.25) — Is there evidence of users paying \
for solutions? Look at competitor pricing, stated WTP, and market spending.
4. **competitor_gaps** (weight: 0.20) — Is there a clear gap in existing \
solutions? Fewer and weaker competitors score higher.
5. **tam_size** (weight: 0.15) — Is the market large enough to sustain a \
product? Consider TAM estimate and growth trajectory.

Also provide:
- A list of key risks for this product idea
- A list of key opportunities
- A reasoning summary explaining the overall assessment
"""


class _ScoringLLMOutput(BaseModel):
    """LLM-generated scoring output (content fields only)."""

    model_config = ConfigDict(frozen=True)

    components: list[ScoreComponent]
    risks: list[str]
    opportunities: list[str]
    reasoning_summary: str


def _format_bullet_list(items: list[str]) -> str:
    """Format a list of strings as a bullet-pointed block."""
    if not items:
        return "- (none available)"
    return "\n".join(f"- {item}" for item in items)


def _format_competitors(competitors: list[dict[str, object]]) -> str:
    """Format competitor data into a readable block."""
    if not competitors:
        return "- (no competitors found)"
    lines: list[str] = []
    for comp in competitors:
        name = comp.get("name", "Unknown")
        desc = comp.get("description", "")
        pricing = comp.get("pricing", "")
        strengths = comp.get("strengths", [])
        weaknesses = comp.get("weaknesses", [])
        parts = [f"- **{name}**"]
        if desc:
            parts.append(f"  Description: {desc}")
        if pricing:
            parts.append(f"  Pricing: {pricing}")
        if isinstance(strengths, list) and strengths:
            parts.append(f"  Strengths: {', '.join(str(s) for s in strengths)}")
        if isinstance(weaknesses, list) and weaknesses:
            parts.append(f"  Weaknesses: {', '.join(str(s) for s in weaknesses)}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


@register_step
class ScoringStep(AbstractStep):
    name = "scoring"
    step_number = 2

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_score(ctx)

        from verdandi.llm import LLMClient
        from verdandi.models.idea import IdeaCandidate
        from verdandi.models.research import MarketResearch

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID — cannot run scoring")

        # Retrieve Step 0 (Idea Discovery) result
        idea_result = ctx.db.get_step_result(experiment_id, "idea_discovery")
        if idea_result is None:
            raise RuntimeError(
                f"Step 0 (idea_discovery) result not found for experiment {ctx.experiment.id}. "
                "Cannot score without an idea."
            )
        idea_data = idea_result["data"]
        if not isinstance(idea_data, dict):
            raise RuntimeError("Step 0 result data is not a valid dict")
        idea = IdeaCandidate.model_validate(idea_data)

        # Retrieve Step 1 (Deep Research) result
        research_result = ctx.db.get_step_result(experiment_id, "deep_research")
        if research_result is None:
            raise RuntimeError(
                f"Step 1 (deep_research) result not found for experiment {ctx.experiment.id}. "
                "Cannot score without research data."
            )
        research_data = research_result["data"]
        if not isinstance(research_data, dict):
            raise RuntimeError("Step 1 result data is not a valid dict")
        research = MarketResearch.model_validate(research_data)

        # Build competitor list for formatting
        competitors_raw: list[dict[str, object]] = [
            comp.model_dump() for comp in research.competitors
        ]

        # Build user prompt
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            title=idea.title,
            problem_statement=idea.problem_statement,
            target_audience=idea.target_audience,
            category=idea.category,
            differentiation=idea.differentiation or "(not specified)",
            tam_estimate=research.tam_estimate or "(not available)",
            market_growth=research.market_growth or "(not available)",
            demand_signals=_format_bullet_list(research.demand_signals),
            competitors=_format_competitors(competitors_raw),
            competitor_gaps=_format_bullet_list(research.competitor_gaps),
            willingness_to_pay=research.willingness_to_pay or "(not available)",
            common_complaints=_format_bullet_list(research.common_complaints),
            key_findings=_format_bullet_list(research.key_findings),
        )

        # Call LLM
        llm = LLMClient(ctx.settings)
        logger.info(
            "Scoring idea via LLM",
            experiment_id=ctx.experiment.id,
            idea_title=idea.title,
        )
        result = llm.generate(user_prompt, _ScoringLLMOutput, system=_SYSTEM_PROMPT)

        # Sanity check: warn if all 5 component scores are identical (lazy LLM)
        if len(result.components) >= 5:
            scores = [c.score for c in result.components]
            if len(set(scores)) == 1:
                logger.warning(
                    "All component scores are identical — LLM may not have differentiated",
                    scores=scores,
                    experiment_id=ctx.experiment.id,
                )

        # Compute total score in code (not by the LLM)
        total = int(sum(c.score * c.weight for c in result.components))
        threshold = ctx.settings.score_go_threshold
        decision = Decision.GO if total >= threshold else Decision.NO_GO

        logger.info(
            "Scoring complete",
            experiment_id=ctx.experiment.id,
            total_score=total,
            threshold=threshold,
            decision=decision.value,
        )

        return PreBuildScore(
            experiment_id=ctx.experiment.id or 0,
            worker_id=ctx.worker_id,
            components=result.components,
            total_score=total,
            decision=decision,
            reasoning=result.reasoning_summary,
            risks=result.risks,
            opportunities=result.opportunities,
        )

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
