"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qdrant_client import QdrantClient  # type: ignore[import-untyped]

from verdandi.memory.long_term import LongTermMemory
from verdandi.models.experiment import ExperimentStatus
from verdandi.orchestrator import PipelineRunner

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.db import Database


@pytest.fixture()
def runner(db: Database, settings: Settings) -> PipelineRunner:
    return PipelineRunner(db=db, settings=settings, dry_run=True)


@pytest.fixture()
def ltm() -> LongTermMemory:
    """In-memory Qdrant-backed LTM for testing status lifecycle."""
    client = QdrantClient(":memory:")
    mem = LongTermMemory(client=client)
    mem.ensure_collection()
    return mem


@pytest.fixture()
def runner_with_ltm(db: Database, settings: Settings, ltm: LongTermMemory) -> PipelineRunner:
    return PipelineRunner(db=db, settings=settings, dry_run=True, long_term_memory=ltm)


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

    def test_stop_after_halts_at_scoring(self, runner: PipelineRunner) -> None:
        """stop_after=2 halts after scoring — Step 3+ not executed."""
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        runner.run_experiment(exp_id, stop_after=2)

        exp = runner.db.get_experiment(exp_id)
        assert exp is not None
        assert exp.current_step == 2
        assert exp.status != ExperimentStatus.COMPLETED

        results = runner.db.get_all_step_results(exp_id)
        step_numbers = {r["step_number"] for r in results}
        assert 2 in step_numbers  # scoring ran
        assert 3 not in step_numbers  # mvp_definition did NOT run

    def test_stop_after_none_runs_full_pipeline(self, runner: PipelineRunner) -> None:
        """stop_after=None preserves existing full-run behavior."""
        ids = runner.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]

        runner.run_experiment(exp_id, stop_after=None)

        exp = runner.db.get_experiment(exp_id)
        assert exp is not None
        assert exp.status == ExperimentStatus.COMPLETED

    def test_run_all_pending_with_stop_after(self, runner: PipelineRunner) -> None:
        """stop_after propagates through run_all_pending."""
        runner.run_discovery_batch(max_ideas=2)
        runner.run_all_pending(stop_after=2)

        for exp in runner.db.list_experiments():
            if exp.idea_title != "discovery_batch":
                assert exp.current_step == 2

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


class TestDiscoveryDedup:
    """Tests for novelty-aware dedup in discovery batch."""

    def test_discovery_batch_creates_reservations(self, runner: PipelineRunner, db: Database):
        """Each discovered idea should create a topic reservation."""
        from verdandi.orchestrator.coordination import TopicReservationManager

        ids = runner.run_discovery_batch(max_ideas=2)
        assert len(ids) >= 1

        mgr = TopicReservationManager(db.Session)
        active = mgr.list_active()
        # Should have at least as many reservations as ideas
        assert len(active) >= len(ids)

    def test_discovery_batch_stores_fingerprints(self, runner: PipelineRunner, db: Database):
        """Reservations should have fingerprints for dedup."""
        from verdandi.orchestrator.coordination import TopicReservationManager

        runner.run_discovery_batch(max_ideas=1)
        mgr = TopicReservationManager(db.Session)
        active = mgr.list_active()
        assert len(active) >= 1
        # At least one reservation should have a fingerprint
        assert any(r["fingerprint"] for r in active)

    def test_discovery_batch_ideas_have_novelty_score(self, runner: PipelineRunner, db: Database):
        """IdeaCandidate saved in step results should have novelty_score."""
        ids = runner.run_discovery_batch(max_ideas=1)
        result = db.get_step_result(ids[0], "idea_discovery")
        assert result is not None
        data = result["data"]
        assert isinstance(data, dict)
        # novelty_score should exist (may be 0.0 for dry_run mock data)
        assert "novelty_score" in data


class TestLtmStatusLifecycle:
    """Tests for Qdrant point status updates at pipeline terminal states."""

    @staticmethod
    def _fake_embedding(seed: float = 0.5) -> list[float]:
        import math

        return [math.sin(seed * (i + 1)) for i in range(384)]

    def test_update_ltm_status_completed(
        self, runner_with_ltm: PipelineRunner, ltm: LongTermMemory
    ):
        """_update_ltm_status sets point to 'completed'."""
        emb = self._fake_embedding(1.0)
        ltm.store_idea_embedding(
            "test-idea", emb, {"topic_description": "test", "status": "active"}
        )

        runner_with_ltm._update_ltm_status("Test Idea", "completed")

        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("completed",))
        assert any(r.topic_key == "test-idea" for r in results)

    def test_update_ltm_status_rejected(self, runner_with_ltm: PipelineRunner, ltm: LongTermMemory):
        """_update_ltm_status sets point to 'rejected'."""
        emb = self._fake_embedding(2.0)
        ltm.store_idea_embedding(
            "rejected-idea", emb, {"topic_description": "test", "status": "active"}
        )

        runner_with_ltm._update_ltm_status("Rejected Idea", "rejected")

        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("rejected",))
        assert any(r.topic_key == "rejected-idea" for r in results)

    def test_update_ltm_status_failed(self, runner_with_ltm: PipelineRunner, ltm: LongTermMemory):
        """_update_ltm_status sets point to 'failed'."""
        emb = self._fake_embedding(3.0)
        ltm.store_idea_embedding(
            "failed-idea", emb, {"topic_description": "test", "status": "active"}
        )

        runner_with_ltm._update_ltm_status("Failed Idea", "failed")

        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("failed",))
        assert any(r.topic_key == "failed-idea" for r in results)

    def test_update_ltm_status_no_ltm_is_noop(self, runner: PipelineRunner):
        """When LTM is None, _update_ltm_status doesn't raise."""
        # runner fixture has no LTM — should not raise
        runner._update_ltm_status("Some Idea", "completed")

    def test_update_ltm_status_empty_title_is_noop(self, runner_with_ltm: PipelineRunner):
        """Empty idea_title skips the update without error."""
        runner_with_ltm._update_ltm_status("", "completed")

    def test_pipeline_completed_updates_qdrant(
        self, runner_with_ltm: PipelineRunner, ltm: LongTermMemory, db: Database
    ):
        """Full pipeline completion updates Qdrant point status to 'completed'."""
        ids = runner_with_ltm.run_discovery_batch(max_ideas=1)
        exp_id = ids[0]
        exp = db.get_experiment(exp_id)
        assert exp is not None

        # Pre-store embedding for this idea so update_status has a target
        from verdandi.orchestrator.coordination import normalize_topic_key

        topic_key = normalize_topic_key(exp.idea_title)
        emb = self._fake_embedding(42.0)
        ltm.store_idea_embedding(
            topic_key, emb, {"topic_description": exp.idea_title, "status": "active"}
        )

        runner_with_ltm.run_experiment(exp_id)

        # Verify the point was updated
        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("completed",))
        assert any(r.topic_key == topic_key for r in results)
