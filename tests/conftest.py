"""Shared test fixtures."""

from __future__ import annotations

import pytest
from pydantic_ai import models

from verdandi.config import Settings
from verdandi.db import Database
from verdandi.models.experiment import Experiment, ExperimentStatus

# Safety net: block all real LLM API calls during tests.
# TestModel and FunctionModel are exempt from this check.
# If a test accidentally triggers a real model request, it gets
# a clear error instead of a billable API call.
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        tavily_api_key="",
        serper_api_key="",
        exa_api_key="",
        perplexity_api_key="",
        cloudflare_api_token="",
        redis_url="",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
        max_retries=1,
        _env_file=None,
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
