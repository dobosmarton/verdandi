"""Experiment CRUD endpoints."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException

from verdandi.api.deps import DbDep
from verdandi.api.schemas import (
    ExperimentListResponse,
    ExperimentResponse,
    ReportCompetitor,
    ReportIdeaSection,
    ReportMarketSection,
    ReportPainPoint,
    ReportResponse,
    ReportScoreComponent,
    ReportScoringSection,
)
from verdandi.db import StepResultDict
from verdandi.models.experiment import ExperimentStatus

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _experiment_to_response(exp: object) -> ExperimentResponse:
    from verdandi.models.experiment import Experiment

    assert isinstance(exp, Experiment)
    return ExperimentResponse(
        id=exp.id,
        idea_title=exp.idea_title,
        idea_summary=exp.idea_summary,
        status=exp.status.value,
        current_step=exp.current_step,
        worker_id=exp.worker_id,
        reviewed_by=exp.reviewed_by,
        review_notes=exp.review_notes,
        reviewed_at=str(exp.reviewed_at) if exp.reviewed_at else None,
        created_at=str(exp.created_at),
        updated_at=str(exp.updated_at),
    )


@router.get("", response_model=ExperimentListResponse)
def list_experiments(
    db: DbDep,
    status: str | None = None,
) -> ExperimentListResponse:
    exp_status = ExperimentStatus(status) if status else None
    experiments = db.list_experiments(exp_status)
    return ExperimentListResponse(
        experiments=[_experiment_to_response(e) for e in experiments],
        total=len(experiments),
    )


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: int,
    db: DbDep,
) -> ExperimentResponse:
    exp = db.get_experiment(experiment_id)
    if exp is None:
        raise ValueError(f"Experiment {experiment_id} not found")
    return _experiment_to_response(exp)


# --- Report helpers ---


def _build_idea_section(step_data: StepResultDict) -> ReportIdeaSection | None:
    data = step_data.get("data")
    if not isinstance(data, dict):
        return None
    from verdandi.models.idea import IdeaCandidate

    idea = IdeaCandidate(**data)
    return ReportIdeaSection(
        title=idea.title,
        one_liner=idea.one_liner,
        category=idea.category,
        target_audience=idea.target_audience,
        problem_statement=idea.problem_statement,
        novelty_score=idea.novelty_score,
        discovery_type=idea.discovery_type.value,
        pain_points=[
            ReportPainPoint(
                description=pp.description,
                severity=pp.severity,
                frequency=pp.frequency,
                source=pp.source,
                quote=pp.quote,
            )
            for pp in idea.pain_points
        ],
        existing_solutions=idea.existing_solutions,
        differentiation=idea.differentiation,
    )


def _build_market_section(step_data: StepResultDict) -> ReportMarketSection | None:
    data = step_data.get("data")
    if not isinstance(data, dict):
        return None
    from verdandi.models.research import MarketResearch

    mkt = MarketResearch(**data)
    source_counts: Counter[str] = Counter(sr.source for sr in mkt.search_results)
    return ReportMarketSection(
        tam_estimate=mkt.tam_estimate,
        market_growth=mkt.market_growth,
        target_audience_size=mkt.target_audience_size,
        willingness_to_pay=mkt.willingness_to_pay,
        demand_signals=mkt.demand_signals,
        key_findings=mkt.key_findings,
        common_complaints=mkt.common_complaints,
        competitors=[
            ReportCompetitor(
                name=c.name,
                url=c.url,
                description=c.description,
                pricing=c.pricing,
                strengths=c.strengths,
                weaknesses=c.weaknesses,
                estimated_users=c.estimated_users,
                funding=c.funding,
            )
            for c in mkt.competitors
        ],
        competitor_gaps=mkt.competitor_gaps,
        research_summary=mkt.research_summary,
        source_count=len(mkt.search_results),
        sources_by_api=dict(source_counts),
    )


def _build_scoring_section(step_data: StepResultDict) -> ReportScoringSection | None:
    data = step_data.get("data")
    if not isinstance(data, dict):
        return None
    from verdandi.models.scoring import PreBuildScore

    score = PreBuildScore(**data)
    return ReportScoringSection(
        total_score=score.total_score,
        decision=score.decision.value,
        reasoning=score.reasoning,
        components=[
            ReportScoreComponent(
                name=sc.name,
                score=sc.score,
                weight=sc.weight,
                reasoning=sc.reasoning,
            )
            for sc in score.components
        ],
        risks=score.risks,
        opportunities=score.opportunities,
    )


@router.get("/{experiment_id}/report", response_model=ReportResponse)
def get_experiment_report(
    experiment_id: int,
    db: DbDep,
) -> ReportResponse:
    """Get a structured research report for an experiment."""
    exp = db.get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")

    idea_result = db.get_step_result(experiment_id, "idea_discovery")
    research_result = db.get_step_result(experiment_id, "deep_research")
    scoring_result = db.get_step_result(experiment_id, "scoring")

    return ReportResponse(
        experiment_id=experiment_id,
        status=exp.status.value,
        idea=_build_idea_section(idea_result) if idea_result else None,
        market_research=_build_market_section(research_result) if research_result else None,
        scoring=_build_scoring_section(scoring_result) if scoring_result else None,
    )


@router.post("/{experiment_id}/archive", response_model=ExperimentResponse)
def archive_experiment(
    experiment_id: int,
    db: DbDep,
) -> ExperimentResponse:
    """Archive an experiment."""
    exp = db.get_experiment(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
    db.archive_experiment(experiment_id)
    updated = db.get_experiment(experiment_id)
    assert updated is not None
    return _experiment_to_response(updated)
