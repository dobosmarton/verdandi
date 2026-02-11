"""Pipeline action endpoints (trigger discovery/run via Huey)."""

from __future__ import annotations

from fastapi import APIRouter

from verdandi.api.deps import DbDep
from verdandi.api.schemas import ActionResponse, DiscoverRequest, RunPipelineRequest

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/discover", response_model=ActionResponse)
def trigger_discover(
    request: DiscoverRequest,
    _db: DbDep,
) -> ActionResponse:
    from verdandi.tasks import discover_ideas_task

    result = discover_ideas_task(
        max_ideas=request.max_ideas,
        dry_run=request.dry_run,
    )
    task_id = result.id if hasattr(result, "id") else None
    return ActionResponse(
        message=f"Discovery enqueued (max_ideas={request.max_ideas}, dry_run={request.dry_run})",
        task_id=str(task_id) if task_id else None,
    )


@router.post("/run/{experiment_id}", response_model=ActionResponse)
def trigger_run(
    experiment_id: int,
    request: RunPipelineRequest,
    db: DbDep,
) -> ActionResponse:
    # Verify experiment exists
    exp = db.get_experiment(experiment_id)
    if exp is None:
        raise ValueError(f"Experiment {experiment_id} not found")

    from verdandi.tasks import run_pipeline_task

    result = run_pipeline_task(
        experiment_id=experiment_id,
        dry_run=request.dry_run,
        stop_after=request.stop_after,
    )
    task_id = result.id if hasattr(result, "id") else None
    return ActionResponse(
        message=f"Pipeline run enqueued for experiment {experiment_id}",
        task_id=str(task_id) if task_id else None,
    )
