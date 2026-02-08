"""Step results and pipeline log endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from verdandi.api.deps import DbDep
from verdandi.api.schemas import LogEntryResponse, StepResultResponse

router = APIRouter(prefix="/experiments/{experiment_id}", tags=["steps"])


@router.get("/steps", response_model=list[StepResultResponse])
def get_all_steps(
    experiment_id: int,
    db: DbDep,
) -> list[StepResultResponse]:
    results = db.get_all_step_results(experiment_id)
    return [
        StepResultResponse(
            id=r["id"],
            experiment_id=r["experiment_id"],
            step_name=r["step_name"],
            step_number=r["step_number"],
            data=r["data"],
            worker_id=r["worker_id"],
            created_at=r["created_at"],
        )
        for r in results
    ]


@router.get("/steps/{step_name}", response_model=StepResultResponse | None)
def get_step_result(
    experiment_id: int,
    step_name: str,
    db: DbDep,
) -> StepResultResponse | None:
    r = db.get_step_result(experiment_id, step_name)
    if r is None:
        return None
    return StepResultResponse(
        id=r["id"],
        experiment_id=r["experiment_id"],
        step_name=r["step_name"],
        step_number=r["step_number"],
        data=r["data"],
        worker_id=r["worker_id"],
        created_at=r["created_at"],
    )


@router.get("/log", response_model=list[LogEntryResponse])
def get_pipeline_log(
    experiment_id: int,
    db: DbDep,
) -> list[LogEntryResponse]:
    entries = db.get_log(experiment_id)
    return [
        LogEntryResponse(
            id=e["id"],
            experiment_id=e["experiment_id"],
            step_name=e["step_name"],
            event=e["event"],
            message=e["message"],
            worker_id=e["worker_id"],
            created_at=e["created_at"],
        )
        for e in entries
    ]
