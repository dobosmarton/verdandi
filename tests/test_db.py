"""Tests for SQLite database CRUD operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import inspect

from verdandi.models.experiment import Experiment, ExperimentStatus

if TYPE_CHECKING:
    from verdandi.db import Database


class TestSchemaInit:
    def test_init_schema_creates_tables(self, db: Database):
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        assert "experiments" in table_names
        assert "step_results" in table_names
        assert "pipeline_log" in table_names
        assert "topic_reservations" in table_names

    def test_init_schema_idempotent(self, db: Database):
        # Calling init_schema again should not raise
        db.init_schema()
        db.init_schema()


class TestExperimentsCRUD:
    def test_create_experiment(self, db: Database):
        exp = Experiment(
            idea_title="Test Idea",
            idea_summary="Testing",
            status=ExperimentStatus.PENDING,
            worker_id="w1",
        )
        created = db.create_experiment(exp)
        assert created.id is not None
        assert created.id > 0
        assert created.idea_title == "Test Idea"

    def test_get_experiment(self, db: Database, sample_experiment: Experiment):
        fetched = db.get_experiment(sample_experiment.id)
        assert fetched is not None
        assert fetched.id == sample_experiment.id
        assert fetched.idea_title == sample_experiment.idea_title

    def test_get_nonexistent_experiment(self, db: Database):
        assert db.get_experiment(99999) is None

    def test_list_experiments(self, db: Database):
        for i in range(3):
            db.create_experiment(Experiment(idea_title=f"Idea {i}"))
        all_exps = db.list_experiments()
        assert len(all_exps) == 3

    def test_list_experiments_by_status(self, db: Database):
        db.create_experiment(Experiment(idea_title="Pending", status=ExperimentStatus.PENDING))
        db.create_experiment(Experiment(idea_title="Running", status=ExperimentStatus.RUNNING))
        db.create_experiment(Experiment(idea_title="Completed", status=ExperimentStatus.COMPLETED))

        pending = db.list_experiments(ExperimentStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].idea_title == "Pending"

        running = db.list_experiments(ExperimentStatus.RUNNING)
        assert len(running) == 1

    def test_update_experiment_status(self, db: Database, sample_experiment: Experiment):
        db.update_experiment_status(
            sample_experiment.id,
            ExperimentStatus.RUNNING,
            current_step=3,
            worker_id="w2",
        )
        updated = db.get_experiment(sample_experiment.id)
        assert updated.status == ExperimentStatus.RUNNING
        assert updated.current_step == 3
        assert updated.worker_id == "w2"

    def test_update_experiment_review(self, db: Database, sample_experiment: Experiment):
        db.update_experiment_review(
            sample_experiment.id,
            approved=True,
            reviewed_by="human",
            notes="Looks good",
        )
        updated = db.get_experiment(sample_experiment.id)
        assert updated.status == ExperimentStatus.APPROVED
        assert updated.reviewed_by == "human"
        assert updated.review_notes == "Looks good"

    def test_archive_experiment(self, db: Database, sample_experiment: Experiment):
        db.archive_experiment(sample_experiment.id)
        updated = db.get_experiment(sample_experiment.id)
        assert updated.status == ExperimentStatus.ARCHIVED


class TestStepResults:
    def test_save_and_get_step_result(self, db: Database, sample_experiment: Experiment):
        data = {"title": "TestWidget", "score": 85}
        db.save_step_result(
            experiment_id=sample_experiment.id,
            step_name="scoring",
            step_number=2,
            data_json=json.dumps(data),
            worker_id="w1",
        )
        result = db.get_step_result(sample_experiment.id, "scoring")
        assert result is not None
        assert result["data"]["title"] == "TestWidget"
        assert result["data"]["score"] == 85

    def test_get_nonexistent_step_result(self, db: Database, sample_experiment: Experiment):
        assert db.get_step_result(sample_experiment.id, "nonexistent") is None

    def test_get_all_step_results(self, db: Database, sample_experiment: Experiment):
        for i in range(3):
            db.save_step_result(
                experiment_id=sample_experiment.id,
                step_name=f"step_{i}",
                step_number=i,
                data_json=json.dumps({"step": i}),
            )
        results = db.get_all_step_results(sample_experiment.id)
        assert len(results) == 3
        assert results[0]["step_number"] == 0
        assert results[2]["step_number"] == 2

    def test_upsert_step_result(self, db: Database, sample_experiment: Experiment):
        db.save_step_result(
            experiment_id=sample_experiment.id,
            step_name="scoring",
            step_number=2,
            data_json=json.dumps({"version": 1}),
        )
        db.save_step_result(
            experiment_id=sample_experiment.id,
            step_name="scoring",
            step_number=2,
            data_json=json.dumps({"version": 2}),
        )
        result = db.get_step_result(sample_experiment.id, "scoring")
        assert result["data"]["version"] == 2

        # Should still only have one row
        all_results = db.get_all_step_results(sample_experiment.id)
        assert len(all_results) == 1


class TestPipelineLog:
    def test_log_event(self, db: Database, sample_experiment: Experiment):
        db.log_event(
            "step_start",
            "Running step scoring",
            experiment_id=sample_experiment.id,
            step_name="scoring",
            worker_id="w1",
        )
        log = db.get_log(sample_experiment.id)
        assert len(log) == 1
        assert log[0]["event"] == "step_start"
        assert log[0]["message"] == "Running step scoring"

    def test_log_ordering(self, db: Database, sample_experiment: Experiment):
        db.log_event("step_start", "Start", experiment_id=sample_experiment.id)
        db.log_event("step_complete", "Done", experiment_id=sample_experiment.id)
        db.log_event("step_start", "Start 2", experiment_id=sample_experiment.id)

        log = db.get_log(sample_experiment.id)
        assert len(log) == 3
        assert log[0]["event"] == "step_start"
        assert log[1]["event"] == "step_complete"
