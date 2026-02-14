"""Huey task queue definitions for multi-worker execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from huey import SqliteHuey, crontab

from verdandi.config import Settings

if TYPE_CHECKING:
    from verdandi.memory.long_term import LongTermMemory

logger = structlog.get_logger()

# Initialize Huey with settings
_settings = Settings()
_settings.ensure_data_dir()

huey = SqliteHuey(
    name="verdandi",
    filename=str(_settings.huey_db_path),
    immediate=_settings.huey_immediate,
)


def _build_ltm(settings: Settings) -> LongTermMemory | None:
    """Construct LongTermMemory if Qdrant is configured."""
    if not settings.qdrant_url:
        return None
    from verdandi.memory import long_term

    return long_term.LongTermMemory(settings.qdrant_url, settings.qdrant_api_key)


def _discover_ideas(max_ideas: int, dry_run: bool) -> list[int]:
    """Inner logic for idea discovery (not wrapped by Huey)."""
    from verdandi.db import Database
    from verdandi.orchestrator import PipelineRunner

    settings = Settings()
    settings.ensure_data_dir()
    db = Database(settings.db_path)
    db.init_schema()

    try:
        runner = PipelineRunner(
            db=db, settings=settings, dry_run=dry_run, long_term_memory=_build_ltm(settings)
        )
        return runner.run_discovery_batch(max_ideas=max_ideas)
    finally:
        db.close()


@huey.task()  # type: ignore[untyped-decorator]
def discover_ideas_task(max_ideas: int = 3, dry_run: bool = False) -> list[int]:
    """Discover new product ideas and create experiments for each.

    Returns list of created experiment IDs.
    """
    return _discover_ideas(max_ideas, dry_run)


@huey.task()  # type: ignore[untyped-decorator]
def run_pipeline_task(
    experiment_id: int, dry_run: bool = False, stop_after: int | None = None
) -> str:
    """Run the pipeline for a single experiment.

    Args:
        experiment_id: The experiment to run.
        dry_run: Use mock data instead of real APIs.
        stop_after: If set, stop after this step number (e.g., 2 for scoring).

    Returns the final experiment status.
    """
    from verdandi.db import Database
    from verdandi.orchestrator import PipelineRunner

    settings = Settings()
    settings.ensure_data_dir()
    db = Database(settings.db_path)
    db.init_schema()

    try:
        runner = PipelineRunner(
            db=db, settings=settings, dry_run=dry_run, long_term_memory=_build_ltm(settings)
        )
        runner.run_experiment(experiment_id, stop_after=stop_after)
        exp = db.get_experiment(experiment_id)
        return exp.status.value if exp else "unknown"
    finally:
        db.close()


@huey.periodic_task(crontab(hour="*/6"))  # type: ignore[untyped-decorator]
@huey.lock_task("periodic-discovery-lock")  # type: ignore[untyped-decorator]
def periodic_discovery() -> list[int]:
    """Periodically discover new ideas (every 6 hours).

    Uses lock_task to prevent concurrent discovery batches.
    """
    logger.info("Periodic discovery triggered")
    return _discover_ideas(max_ideas=3, dry_run=False)
