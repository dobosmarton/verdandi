"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from verdandi.models.experiment import ExperimentStatus
from verdandi.orchestrator import PipelineRunner

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.db import Database


@pytest.fixture()
def runner(db: Database, settings: Settings) -> PipelineRunner:
    return PipelineRunner(db=db, settings=settings, dry_run=True)


class TestPipelineRunner:
    def test_discovery_batch(self, runner: PipelineRunner):
        ids = runner.run_discovery_batch(max_ideas=2)
        assert len(ids) == 2
        for eid in ids:
            exp = runner.db.get_experiment(eid)
            assert exp is not None
            assert exp.status == ExperimentStatus.PENDING

    def test_run_experiment_completes(self, runner: PipelineRunner):
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        runner.run_experiment(exp_id)

        exp = runner.db.get_experiment(exp_id)
        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.current_step == 10

    def test_run_experiment_saves_step_results(self, runner: PipelineRunner):
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        runner.run_experiment(exp_id)

        results = runner.db.get_all_step_results(exp_id)
        # Should have results for all steps (step 0 saved during discovery,
        # steps 1-4, 6-10 saved during run, step 5 skipped)
        step_names = {r["step_name"] for r in results}
        assert "idea_discovery" in step_names
        assert "deep_research" in step_names
        assert "scoring" in step_names
        assert "landing_page" in step_names
        assert "monitor" in step_names

    def test_run_experiment_creates_log(self, runner: PipelineRunner):
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        runner.run_experiment(exp_id)

        log = runner.db.get_log(exp_id)
        events = [entry["event"] for entry in log]
        assert "pipeline_start" in events
        assert "pipeline_complete" in events
        assert "step_start" in events
        assert "step_complete" in events

    def test_run_experiment_not_found(self, runner: PipelineRunner):
        with pytest.raises(ValueError, match="not found"):
            runner.run_experiment(99999)

    def test_run_completed_experiment_is_noop(self, runner: PipelineRunner):
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        runner.run_experiment(exp_id)
        # Run again — should be a no-op
        runner.run_experiment(exp_id)

        exp = runner.db.get_experiment(exp_id)
        assert exp.status == ExperimentStatus.COMPLETED

    def test_run_all_pending(self, runner: PipelineRunner):
        runner.run_discovery_batch(max_ideas=2)
        runner.run_all_pending()

        for exp in runner.db.list_experiments():
            if exp.idea_title != "discovery_batch":
                assert exp.status == ExperimentStatus.COMPLETED

    def test_pipeline_resumes_from_checkpoint(self, runner: PipelineRunner, db: Database):
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        # Manually set the experiment to step 5 as if it paused
        db.update_experiment_status(exp_id, ExperimentStatus.RUNNING, current_step=5)

        runner.run_experiment(exp_id)

        exp = db.get_experiment(exp_id)
        assert exp.status == ExperimentStatus.COMPLETED
        # Should have step results only for steps 6+
        results = db.get_all_step_results(exp_id)
        step_numbers = {r["step_number"] for r in results}
        # Step 0 was from discovery; steps 6+ from resume
        assert 0 in step_numbers
        assert 6 in step_numbers
