"""FastAPI test client fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from verdandi.api.middleware import CorrelationIdMiddleware, add_exception_handlers
from verdandi.api.routes import actions, experiments, reservations, reviews, steps, system
from verdandi.models.experiment import Experiment, ExperimentStatus

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.db import Database


def _create_test_app(db: Database, settings: Settings) -> FastAPI:
    """Create a FastAPI app with injected test db/settings (no lifespan)."""
    app = FastAPI(title="Verdandi Test")

    app.state.db = db
    app.state.settings = settings

    app.add_middleware(CorrelationIdMiddleware)
    add_exception_handlers(app)

    prefix = "/api/v1"
    app.include_router(system.router, prefix=prefix)
    app.include_router(experiments.router, prefix=prefix)
    app.include_router(steps.router, prefix=prefix)
    app.include_router(reviews.router, prefix=prefix)
    app.include_router(reservations.router, prefix=prefix)
    app.include_router(actions.router, prefix=prefix)

    return app


@pytest.fixture()
def client(db: Database, settings: Settings) -> TestClient:
    app = _create_test_app(db, settings)
    return TestClient(app)


@pytest.fixture()
def populated_db(db: Database) -> Database:
    """DB with a few experiments for testing."""
    for i in range(3):
        db.create_experiment(
            Experiment(
                idea_title=f"Idea {i}",
                idea_summary=f"Summary {i}",
                status=ExperimentStatus.PENDING,
                worker_id="test-worker",
            )
        )
    # One awaiting review
    db.create_experiment(
        Experiment(
            idea_title="Review Me",
            idea_summary="Needs review",
            status=ExperimentStatus.AWAITING_REVIEW,
            worker_id="test-worker",
        )
    )
    return db


@pytest.fixture()
def populated_client(populated_db: Database, settings: Settings) -> TestClient:
    app = _create_test_app(populated_db, settings)
    return TestClient(app)
