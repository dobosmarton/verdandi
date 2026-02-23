"""Step 2: Pre-Build Scoring — quantified go/no-go decision.

Supports single-model scoring (default) and multi-model Agent Council
when ``council_enabled`` is set in configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict

from verdandi.agents.base import AbstractStep, StepContext, register_step
from verdandi.models.idea import DiscoveryType
from verdandi.models.scoring import (
    CouncilMemberVote,
    Decision,
    DimensionDissent,
    DissentAnalysis,
    DissentResolutionRound,
    PreBuildScore,
    ScoreComponent,
)

if TYPE_CHECKING:
    from verdandi.models.idea import IdeaCandidate
    from verdandi.models.research import MarketResearch

logger = structlog.get_logger()

_SYSTEM_PROMPT = (
    "You are a product validation analyst. Score the following product idea "
    "across 5 dimensions based on the research evidence. Score each dimension "
    "0-100 where 50=neutral, below 40=negative signal, above 70=strong positive. "
    "Be calibrated — only score high when evidence strongly supports it. "
    "Do not be overly optimistic.\n\n"
    "Calibration context (derived from startup cohort analysis):\n"
    "- Category-creating products (defining a new market rather than entering an "
    "existing one) consistently achieve outsized outcomes — treat clear category "
    "creation potential as a positive signal across all dimensions\n"
    "- Vertical AI (domain-specific) outperforms horizontal AI in traction and "
    "retention — score domain moats and specialized data advantages higher\n"
    "- Capital efficiency is critical for solo-dev validation — ideas requiring "
    "significant upfront capital or hardware before proving demand should score "
    "lower on competitor_gaps and willingness_to_pay\n"
    "- Prosumer distribution (product usage naturally creates shareable content or "
    "visible output) is a strong positive signal — factor this into tam_size "
    "and frequency assessments"
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

**Novelty Score:** {novelty_score} (1.0=completely novel vs previous experiments, 0.0=already explored)

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

_NOVELTY_BONUS_POINTS = 10


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


def _scoring_context_for_discovery_type(discovery_type: DiscoveryType) -> str:
    """Return scoring guidance tailored to the discovery type."""
    if discovery_type == DiscoveryType.DISRUPTION:
        return (
            "\n\n## Scoring Context\n\n"
            "This is a **DISRUPTION** idea — it addresses a known pain point in "
            "existing workflows. When scoring:\n"
            "- Weight **pain_severity** and **willingness_to_pay** heavily — "
            "existing paid competitors validate the market\n"
            "- **Complaint volume** and user group specificity are strong positive signals\n"
            "- **Frequency** of pain is critical — daily pain scores higher than monthly\n"
            "- A smaller TAM is acceptable if the pain is severe and frequent\n"
        )
    # DiscoveryType.MOONSHOT
    return (
        "\n\n## Scoring Context\n\n"
        "This is a **MOONSHOT** idea — it positions for an emerging trend or "
        "new capability. When scoring:\n"
        "- Weight **tam_size** growth potential and **competitor_gaps** more heavily\n"
        "- A small current market is acceptable if the future scenario and growth "
        "trajectory are compelling\n"
        "- Few competitors is expected (the space is new), not a weakness\n"
        "- **willingness_to_pay** may be unproven — that's acceptable for moonshots\n"
        "- Novelty and timing ('why now') are key differentiators\n"
    )


@register_step
class ScoringStep(AbstractStep):
    name = "scoring"
    step_number = 2

    def run(self, ctx: StepContext) -> BaseModel:
        if ctx.dry_run:
            return self._mock_score(ctx)

        if ctx.settings.council_enabled:
            return self._run_council(ctx)

        return self._run_single(ctx)

    # ------------------------------------------------------------------
    # Prerequisites & prompt building (shared by single + council paths)
    # ------------------------------------------------------------------

    def _load_prerequisites(self, ctx: StepContext) -> tuple[IdeaCandidate, MarketResearch]:
        """Load idea and research from prior results or database."""
        from verdandi.models.idea import IdeaCandidate
        from verdandi.models.research import MarketResearch

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID — cannot run scoring")

        if ctx.prior_results is not None:
            idea = ctx.prior_results.get_typed("idea_discovery", IdeaCandidate)
            research = ctx.prior_results.get_typed("deep_research", MarketResearch)
        elif ctx.db is not None:
            idea_result = ctx.db.get_step_result(experiment_id, "idea_discovery")
            if idea_result is None:
                raise RuntimeError(
                    f"Step 0 (idea_discovery) result not found for experiment {experiment_id}. "
                    "Cannot score without an idea."
                )
            idea_data = idea_result["data"]
            if not isinstance(idea_data, dict):
                raise RuntimeError("Step 0 result data is not a valid dict")
            idea = IdeaCandidate.model_validate(idea_data)

            research_result = ctx.db.get_step_result(experiment_id, "deep_research")
            if research_result is None:
                raise RuntimeError(
                    f"Step 1 (deep_research) result not found for experiment {experiment_id}. "
                    "Cannot score without research data."
                )
            research_data = research_result["data"]
            if not isinstance(research_data, dict):
                raise RuntimeError("Step 1 result data is not a valid dict")
            research = MarketResearch.model_validate(research_data)
        else:
            raise RuntimeError("No prior_results or db available to retrieve prerequisites")

        return idea, research

    def _build_user_prompt(self, idea: IdeaCandidate, research: MarketResearch) -> str:
        """Build the scoring user prompt from idea and research data."""
        competitors_raw: list[dict[str, object]] = [
            comp.model_dump() for comp in research.competitors
        ]

        novelty_val = idea.novelty_score
        novelty_display = f"{novelty_val:.2f}" if novelty_val > 0.0 else "(not available)"
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
            novelty_score=novelty_display,
        )

        user_prompt += _scoring_context_for_discovery_type(idea.discovery_type)
        return user_prompt

    # ------------------------------------------------------------------
    # Single-model scoring (original path)
    # ------------------------------------------------------------------

    def _run_single(self, ctx: StepContext) -> PreBuildScore:
        """Score using a single LLM (original behavior)."""
        from verdandi.llm import LLMClient

        idea, research = self._load_prerequisites(ctx)
        user_prompt = self._build_user_prompt(idea, research)

        llm = LLMClient(ctx.settings)
        logger.info(
            "Scoring idea via LLM",
            experiment_id=ctx.experiment.id,
            idea_title=idea.title,
        )
        result = llm.generate(user_prompt, _ScoringLLMOutput, system=_SYSTEM_PROMPT)

        # Sanity check: warn if all 5 component scores are identical
        if len(result.components) >= 5:
            scores = [c.score for c in result.components]
            if len(set(scores)) == 1:
                logger.warning(
                    "All component scores are identical — LLM may not have differentiated",
                    scores=scores,
                    experiment_id=ctx.experiment.id,
                )

        # Compute total score in code (not by the LLM)
        novelty_val = idea.novelty_score
        base_total = int(sum(c.score * c.weight for c in result.components))
        novelty_bonus = int(novelty_val * _NOVELTY_BONUS_POINTS)
        total = min(base_total + novelty_bonus, 100)

        threshold = ctx.settings.score_go_threshold
        decision = Decision.GO if total >= threshold else Decision.NO_GO

        logger.info(
            "Scoring complete",
            experiment_id=ctx.experiment.id,
            base_total=base_total,
            novelty_bonus=novelty_bonus,
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

    # ------------------------------------------------------------------
    # Council scoring (multi-model path)
    # ------------------------------------------------------------------

    def _run_council(self, ctx: StepContext) -> PreBuildScore:
        """Score using the Agent Council (multi-model majority vote)."""
        from verdandi.agents.council import AgentCouncil

        experiment_id = ctx.experiment.id
        if experiment_id is None:
            raise RuntimeError("Experiment has no ID — cannot run scoring")

        idea, research = self._load_prerequisites(ctx)
        user_prompt = self._build_user_prompt(idea, research)

        # Check available provider count
        available_count = sum(
            [
                bool(ctx.settings.anthropic_api_key),
                bool(ctx.settings.openai_api_key),
                bool(ctx.settings.google_api_key),
            ]
        )

        if available_count < 2:
            logger.warning(
                "Council enabled but < 2 providers available, falling back to single-model",
                available_providers=available_count,
                experiment_id=experiment_id,
            )
            return self._run_single(ctx)

        logger.info(
            "Scoring idea via Agent Council",
            experiment_id=experiment_id,
            idea_title=idea.title,
        )

        try:
            council = AgentCouncil(ctx.settings)
            score = council.evaluate(
                user_prompt=user_prompt,
                system_prompt=_SYSTEM_PROMPT,
                scoring_output_type=_ScoringLLMOutput,
                experiment_id=experiment_id,
                worker_id=ctx.worker_id,
                novelty_score=idea.novelty_score,
                threshold=ctx.settings.score_go_threshold,
            )

            # Dissent resolution (if enabled)
            if ctx.settings.dissent_enabled:
                from verdandi.agents.dissent import DissentAnalyzer

                analyzer = DissentAnalyzer(ctx.settings)
                score = analyzer.resolve(ctx, score)

            return score
        except Exception as exc:
            logger.error(
                "Council evaluation failed, falling back to single-model",
                error=str(exc),
                experiment_id=experiment_id,
            )
            return self._run_single(ctx)

    # ------------------------------------------------------------------
    # Dry-run mock
    # ------------------------------------------------------------------

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

        council_votes: list[CouncilMemberVote] = []
        if ctx.settings.council_enabled:
            council_votes = [
                CouncilMemberVote(
                    provider_name=provider,
                    model_name=f"mock-{provider}",
                    components=components,
                    base_score=total,
                    decision=decision,
                    risks=["Crowded market with well-funded incumbents"],
                    opportunities=["First-mover advantage in AI-powered niche"],
                    reasoning_summary=f"Mock {provider} vote.",
                )
                for provider in ("anthropic", "openai", "google")
            ]

        # Mock dissent analysis when dissent is enabled
        dissent_analysis: DissentAnalysis | None = None
        if ctx.settings.dissent_enabled and ctx.settings.council_enabled:
            dissent_analysis = DissentAnalysis(
                dissent_detected=True,
                dimension_dissents=[
                    DimensionDissent(
                        dimension="willingness_to_pay",
                        scores_by_provider={"anthropic": 80, "openai": 55, "google": 90},
                        spread=35,
                        median_score=80,
                        reasoning_excerpts=[
                            "anthropic: Strong WTP signals from competitor pricing",
                            "openai: Limited direct pricing evidence",
                        ],
                    ),
                ],
                resolution_rounds=[
                    DissentResolutionRound(
                        round_number=1,
                        contested_dimensions=["willingness_to_pay"],
                        followup_queries=[
                            "competitor pricing analysis for target market",
                            "willingness to pay survey data B2B SaaS",
                        ],
                        new_sources_count=4,
                        score_before=total,
                        score_after=total,
                        decision_changed=False,
                    ),
                ],
                decision_flipped=False,
                initial_score=total,
                final_score=total,
            )

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
            council_votes=council_votes,
            dissent_analysis=dissent_analysis,
        )
