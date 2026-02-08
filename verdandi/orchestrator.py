"""Pipeline orchestrator: runs experiments through registered steps."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

from verdandi.models.experiment import Experiment, ExperimentStatus
from verdandi.models.scoring import Decision
from verdandi.retry import CircuitBreaker, with_retry
from verdandi.steps.base import AbstractStep, StepContext, get_step_registry

if TYPE_CHECKING:
    from pydantic import BaseModel

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.db import Database

logger = structlog.get_logger()


class PipelineRunner:
    """Orchestrates the execution of pipeline steps for experiments."""

    def __init__(self, db: Database, settings: Settings, dry_run: bool = False):
        self.db = db
        self.settings = settings
        self.dry_run = dry_run
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        # Ensure steps are imported and registered
        import verdandi.steps  # noqa: F401

    def _get_breaker(self, step_name: str) -> CircuitBreaker:
        if step_name not in self._circuit_breakers:
            self._circuit_breakers[step_name] = CircuitBreaker(name=step_name)
        return self._circuit_breakers[step_name]

    def run_experiment(self, experiment_id: int) -> None:
        """Run all remaining steps for an experiment, respecting checkpoints."""
        correlation_id = uuid.uuid4().hex[:12]
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            experiment_id=experiment_id,
        )

        exp = self.db.get_experiment(experiment_id)
        if exp is None:
            raise ValueError(f"Experiment {experiment_id} not found")

        if exp.status in (
            ExperimentStatus.COMPLETED,
            ExperimentStatus.ARCHIVED,
            ExperimentStatus.REJECTED,
        ):
            logger.info("Experiment already terminal", status=exp.status.value)
            return

        if exp.status == ExperimentStatus.AWAITING_REVIEW and not self.dry_run:
            logger.info("Experiment awaiting review — cannot proceed")
            return

        registry = get_step_registry()
        step_numbers = sorted(registry.keys())

        # Start from where we left off (skip step 0 — that's discovery)
        start_from = max(exp.current_step, 1) if exp.current_step > 0 else 1

        self.db.update_experiment_status(
            experiment_id,
            ExperimentStatus.RUNNING,
            worker_id=self.settings.worker_id,
        )
        self.db.log_event(
            "pipeline_start",
            f"Starting from step {start_from}",
            experiment_id=experiment_id,
            worker_id=self.settings.worker_id,
        )

        for step_num in step_numbers:
            if step_num < start_from:
                continue
            if step_num == 0:
                continue  # Step 0 is only run via run_discovery_batch

            step = registry[step_num]
            ctx = StepContext(
                db=self.db,
                settings=self.settings,
                experiment=exp,
                dry_run=self.dry_run,
                worker_id=self.settings.worker_id,
                correlation_id=correlation_id,
            )

            # Idempotency check
            if step.is_complete(ctx):
                logger.info("Step already complete — skipping", step=step.name, step_num=step_num)
                continue

            # Conditional skip
            if step.should_skip(ctx):
                logger.info("Step skipped", step=step.name, step_num=step_num)
                continue

            logger.info("Running step", step=step.name, step_num=step_num)
            self.db.log_event(
                "step_start",
                f"Running step {step.name}",
                experiment_id=experiment_id,
                step_name=step.name,
                worker_id=self.settings.worker_id,
            )

            try:
                breaker = self._get_breaker(step.name)

                def _run_step(
                    _b: CircuitBreaker = breaker,
                    _s: AbstractStep = step,
                    _c: StepContext = ctx,
                ) -> BaseModel:
                    return _b.call(lambda: _s.run(_c))

                result = with_retry(
                    fn=_run_step,
                    max_retries=self.settings.max_retries,
                    jitter=True,
                )
            except Exception as exc:
                logger.error("Step failed", step=step.name, step_num=step_num, error=str(exc))
                self.db.log_event(
                    "step_error",
                    str(exc),
                    experiment_id=experiment_id,
                    step_name=step.name,
                    worker_id=self.settings.worker_id,
                )
                self.db.update_experiment_status(
                    experiment_id, ExperimentStatus.FAILED, current_step=step_num
                )
                raise

            # Save step result
            self.db.save_step_result(
                experiment_id=experiment_id,
                step_name=step.name,
                step_number=step_num,
                data_json=result.model_dump_json(),
                worker_id=self.settings.worker_id,
            )
            self.db.update_experiment_status(
                experiment_id, ExperimentStatus.RUNNING, current_step=step_num
            )
            self.db.log_event(
                "step_complete",
                f"Step {step.name} completed",
                experiment_id=experiment_id,
                step_name=step.name,
                worker_id=self.settings.worker_id,
            )

            # Refresh experiment state
            exp = self.db.get_experiment(experiment_id)
            if exp is None:
                raise RuntimeError(f"Experiment {experiment_id} disappeared mid-pipeline")

            # Gate: scoring step produces GO/NO_GO
            if step.name == "scoring":
                scoring_result = self.db.get_step_result(experiment_id, "scoring")
                if scoring_result:
                    data = scoring_result["data"]
                    if isinstance(data, dict) and data.get("decision") == Decision.NO_GO:
                        logger.info("Experiment scored NO_GO — stopping")
                        self.db.update_experiment_status(
                            experiment_id, ExperimentStatus.NO_GO, current_step=step_num
                        )
                        self.db.log_event(
                            "pipeline_nogo",
                            "Pre-build score below threshold",
                            experiment_id=experiment_id,
                            worker_id=self.settings.worker_id,
                        )
                        return

            # Gate: human review
            if step.name == "human_review" and exp.status == ExperimentStatus.AWAITING_REVIEW:
                logger.info("Experiment paused for human review")
                return

        # All steps completed
        self.db.update_experiment_status(experiment_id, ExperimentStatus.COMPLETED)
        self.db.log_event(
            "pipeline_complete",
            "All steps completed",
            experiment_id=experiment_id,
            worker_id=self.settings.worker_id,
        )
        logger.info("Experiment completed")

    def run_discovery_batch(self, max_ideas: int = 3) -> list[int]:
        """Run Step 0 (Idea Discovery) and create experiments for each idea."""
        registry = get_step_registry()
        if 0 not in registry:
            raise RuntimeError("Step 0 (idea_discovery) not registered")

        step = registry[0]
        # Create a temporary experiment for discovery
        temp_exp = Experiment(
            idea_title="discovery_batch",
            idea_summary="Batch idea discovery",
            worker_id=self.settings.worker_id,
        )
        temp_exp = self.db.create_experiment(temp_exp)

        ctx = StepContext(
            db=self.db,
            settings=self.settings,
            experiment=temp_exp,
            dry_run=self.dry_run,
            worker_id=self.settings.worker_id,
        )

        self.db.log_event(
            "discovery_start",
            f"Discovering up to {max_ideas} ideas",
            experiment_id=temp_exp.id,
            worker_id=self.settings.worker_id,
        )

        result = step.run(ctx)

        # The discovery step returns a single IdeaCandidate.
        # In the real implementation, it would be called multiple times
        # or return multiple ideas. For now, each call produces one idea.
        experiment_ids: list[int] = []
        ideas = [result]  # Wrap single result; step can be called multiple times

        for idea in ideas:
            exp = Experiment(
                idea_title=getattr(idea, "title", "Untitled"),
                idea_summary=getattr(idea, "one_liner", ""),
                status=ExperimentStatus.PENDING,
                worker_id=self.settings.worker_id,
            )
            exp = self.db.create_experiment(exp)
            assert exp.id is not None
            # Save the idea as step 0 result
            self.db.save_step_result(
                experiment_id=exp.id,
                step_name="idea_discovery",
                step_number=0,
                data_json=idea.model_dump_json(),
                worker_id=self.settings.worker_id,
            )
            self.db.log_event(
                "idea_created",
                f"Created experiment for: {exp.idea_title}",
                experiment_id=exp.id,
                worker_id=self.settings.worker_id,
            )
            experiment_ids.append(exp.id)

        # Mark discovery batch experiment as completed
        assert temp_exp.id is not None
        self.db.update_experiment_status(
            temp_exp.id,
            ExperimentStatus.COMPLETED,
        )

        # Run discovery multiple times for max_ideas
        for _ in range(max_ideas - 1):
            result = step.run(ctx)
            exp = Experiment(
                idea_title=getattr(result, "title", "Untitled"),
                idea_summary=getattr(result, "one_liner", ""),
                status=ExperimentStatus.PENDING,
                worker_id=self.settings.worker_id,
            )
            exp = self.db.create_experiment(exp)
            assert exp.id is not None
            self.db.save_step_result(
                experiment_id=exp.id,
                step_name="idea_discovery",
                step_number=0,
                data_json=result.model_dump_json(),
                worker_id=self.settings.worker_id,
            )
            self.db.log_event(
                "idea_created",
                f"Created experiment for: {exp.idea_title}",
                experiment_id=exp.id,
                worker_id=self.settings.worker_id,
            )
            experiment_ids.append(exp.id)

        logger.info("Discovery batch complete", count=len(experiment_ids))
        return experiment_ids

    def run_all_pending(self) -> None:
        """Run pipeline for all pending/approved experiments."""
        experiments = self.db.list_experiments(ExperimentStatus.PENDING)
        experiments += self.db.list_experiments(ExperimentStatus.APPROVED)

        for exp in experiments:
            if exp.id is None:
                continue
            try:
                self.run_experiment(exp.id)
            except Exception as exc:
                logger.error("Experiment failed", experiment_id=exp.id, error=str(exc))
