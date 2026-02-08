"""Shared test fixtures."""

from __future__ import annotations

import pytest

from verdandi.config import Settings
from verdandi.db import Database
from verdandi.models.experiment import Experiment, ExperimentStatus


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
        max_retries=1,
    )


@pytest.fixture()
def db(tmp_path) -> Database:
    db = Database(tmp_path / "test.db")
    db.init_schema()
    yield db
    db.close()


@pytest.fixture()
def sample_experiment(db: Database) -> Experiment:
    exp = Experiment(
        idea_title="TestWidget — AI-Powered Test Tool",
        idea_summary="An automated test tool for developers",
        status=ExperimentStatus.PENDING,
        worker_id="test-worker-1",
    )
    return db.create_experiment(exp)
