"""Pipeline orchestrator: runs experiments through registered steps."""

from __future__ import annotations

import time as time_mod
import uuid
from typing import TYPE_CHECKING

import structlog

from verdandi.metrics import step_duration_seconds, step_executions_total
from verdandi.models.experiment import Experiment, ExperimentStatus
from verdandi.models.scoring import Decision
from verdandi.retry import CircuitBreaker, with_retry
from verdandi.steps.base import AbstractStep, StepContext, get_step_registry

if TYPE_CHECKING:
    from pydantic import BaseModel

    from verdandi.config import Settings
    from verdandi.coordination import TopicReservationManager
    from verdandi.db import Database
    from verdandi.embeddings import EmbeddingService

logger = structlog.get_logger()

_MAX_DEDUP_RETRIES = 3


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

    def run_experiment(self, experiment_id: int, *, stop_after: int | None = None) -> None:
        """Run remaining steps for an experiment, respecting checkpoints.

        Args:
            experiment_id: The experiment to run.
            stop_after: If set, stop after this step number completes
                (e.g., stop_after=2 halts after scoring for research-only runs).
        """
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

                _t0 = time_mod.monotonic()
                result = with_retry(
                    fn=_run_step,
                    max_retries=self.settings.max_retries,
                    jitter=True,
                )
                step_duration_seconds.labels(step_name=step.name).observe(
                    time_mod.monotonic() - _t0
                )
                step_executions_total.labels(step_name=step.name, status="success").inc()
            except Exception as exc:
                step_executions_total.labels(step_name=step.name, status="error").inc()
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

            # Gate: stop_after — intentional early stop for research-only runs
            if stop_after is not None and step_num >= stop_after:
                logger.info(
                    "Pipeline stopped per stop_after",
                    step=step.name,
                    step_num=step_num,
                    stop_after=stop_after,
                )
                self.db.log_event(
                    "pipeline_stopped",
                    f"Stopped after step {step_num} ({step.name}) per stop_after={stop_after}",
                    experiment_id=experiment_id,
                    worker_id=self.settings.worker_id,
                )
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
        """Run Step 0 (Idea Discovery) with novelty-aware dedup.

        For each idea slot:
        1. Generate an idea via Step 0
        2. Fast-pass dedup: Jaccard fingerprint similarity
        3. Semantic dedup: embedding cosine similarity (if available)
        4. Compute novelty score (1.0 = completely novel)
        5. Reserve the topic atomically
        6. Create the experiment

        If a duplicate is detected, retries up to ``_MAX_DEDUP_RETRIES`` times
        with LLM exclusion hints to steer toward a different domain.
        """
        from verdandi.coordination import TopicReservationManager
        from verdandi.embeddings import EmbeddingService

        registry = get_step_registry()
        if 0 not in registry:
            raise RuntimeError("Step 0 (idea_discovery) not registered")

        step = registry[0]
        mgr = TopicReservationManager(self.db.Session)
        embedder = EmbeddingService()

        # Create a temporary experiment for discovery
        temp_exp = Experiment(
            idea_title="discovery_batch",
            idea_summary="Batch idea discovery",
            worker_id=self.settings.worker_id,
        )
        temp_exp = self.db.create_experiment(temp_exp)

        self.db.log_event(
            "discovery_start",
            f"Discovering up to {max_ideas} ideas",
            experiment_id=temp_exp.id,
            worker_id=self.settings.worker_id,
        )

        experiment_ids: list[int] = []
        all_exclude_titles: list[str] = []

        for idea_slot in range(max_ideas):
            idea = self._discover_unique_idea(
                step=step,
                temp_exp=temp_exp,
                mgr=mgr,
                embedder=embedder,
                exclude_titles=all_exclude_titles,
            )
            if idea is None:
                logger.warning(
                    "Could not find unique idea for slot",
                    slot=idea_slot,
                    attempted_retries=_MAX_DEDUP_RETRIES,
                )
                continue

            # Create experiment for the idea
            exp = Experiment(
                idea_title=getattr(idea, "title", "Untitled"),
                idea_summary=getattr(idea, "one_liner", ""),
                status=ExperimentStatus.PENDING,
                worker_id=self.settings.worker_id,
            )
            exp = self.db.create_experiment(exp)
            assert exp.id is not None

            self.db.save_step_result(
                experiment_id=exp.id,
                step_name="idea_discovery",
                step_number=0,
                data_json=idea.model_dump_json(),
                worker_id=self.settings.worker_id,
            )
            self.db.log_event(
                "idea_created",
                f"Created experiment for: {exp.idea_title} (novelty={getattr(idea, 'novelty_score', 0.0):.2f})",
                experiment_id=exp.id,
                worker_id=self.settings.worker_id,
            )
            experiment_ids.append(exp.id)
            all_exclude_titles.append(getattr(idea, "title", ""))

        # Mark discovery batch experiment as completed
        assert temp_exp.id is not None
        self.db.update_experiment_status(temp_exp.id, ExperimentStatus.COMPLETED)

        logger.info("Discovery batch complete", count=len(experiment_ids))
        return experiment_ids

    def _discover_unique_idea(
        self,
        step: AbstractStep,
        temp_exp: Experiment,
        mgr: TopicReservationManager,
        embedder: EmbeddingService,
        exclude_titles: list[str],
    ) -> BaseModel | None:
        """Generate a unique idea with two-pass dedup + novelty scoring.

        Returns an IdeaCandidate with novelty_score set, or None if all
        retry attempts produced duplicates.
        """
        from verdandi.coordination import idea_fingerprint, normalize_topic_key

        _all_statuses = ("active", "completed")
        local_excludes = list(exclude_titles)

        for attempt in range(_MAX_DEDUP_RETRIES + 1):
            ctx = StepContext(
                db=self.db,
                settings=self.settings,
                experiment=temp_exp,
                dry_run=self.dry_run,
                worker_id=self.settings.worker_id,
                exclude_titles=tuple(local_excludes),
            )

            result = step.run(ctx)
            title = getattr(result, "title", "Untitled")
            one_liner = getattr(result, "one_liner", "")

            # --- Fast pass: Jaccard fingerprint ---
            fp = idea_fingerprint(title, one_liner)
            fp_matches = mgr.find_similar_by_fingerprint(fp, threshold=0.6, statuses=_all_statuses)
            if fp_matches:
                logger.warning(
                    "Duplicate detected (fingerprint)",
                    title=title,
                    similar_to=fp_matches[0]["topic_key"],
                    similarity=fp_matches[0]["similarity"],
                    attempt=attempt + 1,
                )
                local_excludes.append(title)
                continue

            # --- Semantic pass: embedding similarity ---
            embedding: list[float] = []
            if embedder.is_available:
                embedding = embedder.embed(f"{title} {one_liner}")
                emb_matches = mgr.find_similar_by_embedding(
                    embedding, threshold=0.82, statuses=_all_statuses
                )
                if emb_matches:
                    logger.warning(
                        "Duplicate detected (embedding)",
                        title=title,
                        similar_to=emb_matches[0]["topic_key"],
                        similarity=emb_matches[0]["similarity"],
                        attempt=attempt + 1,
                    )
                    local_excludes.append(title)
                    continue

            # --- Compute novelty score ---
            novelty_score = 1.0
            if embedder.is_available and embedding:
                novelty_score = mgr.compute_novelty_score(embedding)

            # --- Set novelty score on the idea ---
            result = result.model_copy(update={"novelty_score": novelty_score})

            # --- Reserve the topic ---
            topic_key = normalize_topic_key(title)
            reserved = mgr.try_reserve(
                worker_id=self.settings.worker_id,
                topic_key=topic_key,
                topic_description=one_liner,
                niche_category=getattr(result, "category", ""),
                fingerprint=fp,
                embedding=embedding if embedding else None,
            )
            if not reserved:
                logger.warning(
                    "Topic reservation failed (race condition)",
                    title=title,
                    topic_key=topic_key,
                    attempt=attempt + 1,
                )
                local_excludes.append(title)
                continue

            logger.info(
                "Unique idea discovered",
                title=title,
                novelty_score=novelty_score,
                topic_key=topic_key,
                attempt=attempt + 1,
            )
            return result

        return None

    def run_all_pending(self, *, stop_after: int | None = None) -> None:
        """Run pipeline for all pending/approved experiments."""
        experiments = self.db.list_experiments(ExperimentStatus.PENDING)
        experiments += self.db.list_experiments(ExperimentStatus.APPROVED)

        for exp in experiments:
            if exp.id is None:
                continue
            try:
                self.run_experiment(exp.id, stop_after=stop_after)
            except Exception as exc:
                logger.error("Experiment failed", experiment_id=exp.id, error=str(exc))
