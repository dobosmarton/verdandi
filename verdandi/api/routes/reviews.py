"""Human review endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from verdandi.api.deps import DbDep
from verdandi.api.schemas import ExperimentListResponse, ExperimentResponse, ReviewRequest
from verdandi.models.experiment import ExperimentStatus

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/pending", response_model=ExperimentListResponse)
def list_pending_reviews(
    db: DbDep,
) -> ExperimentListResponse:
    from verdandi.api.routes.experiments import _experiment_to_response

    experiments = db.list_experiments(ExperimentStatus.AWAITING_REVIEW)
    return ExperimentListResponse(
        experiments=[_experiment_to_response(e) for e in experiments],
        total=len(experiments),
    )


@router.post("/{experiment_id}", response_model=ExperimentResponse)
def submit_review(
    experiment_id: int,
    review: ReviewRequest,
    db: DbDep,
) -> ExperimentResponse:
    from verdandi.api.routes.experiments import _experiment_to_response

    exp = db.get_experiment(experiment_id)
    if exp is None:
        raise ValueError(f"Experiment {experiment_id} not found")
    if exp.status != ExperimentStatus.AWAITING_REVIEW:
        raise ValueError(
            f"Experiment {experiment_id} is not awaiting review (status: {exp.status.value})"
        )

    db.update_experiment_review(
        experiment_id,
        approved=review.approved,
        reviewed_by=review.reviewed_by,
        notes=review.notes,
    )
    updated = db.get_experiment(experiment_id)
    assert updated is not None
    return _experiment_to_response(updated)
