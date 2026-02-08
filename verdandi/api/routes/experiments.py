"""Experiment CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from verdandi.api.deps import DbDep
from verdandi.api.schemas import ExperimentListResponse, ExperimentResponse
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
