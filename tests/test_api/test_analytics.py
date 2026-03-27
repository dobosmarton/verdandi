"""Tests for the analytics REST API endpoints.

Uses a dedicated TestClient fixture that includes the analytics router,
following the same pattern as other test_api modules.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from verdandi.api.middleware import CorrelationIdMiddleware, add_exception_handlers
from verdandi.api.routes import analytics as analytics_router_module
from verdandi.models.experiment import Experiment, ExperimentStatus

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.db import Database


# ---------------------------------------------------------------------------
# Analytics-specific client fixture
# ---------------------------------------------------------------------------


def _create_analytics_app(db: Database, settings: Settings) -> FastAPI:
    """Minimal FastAPI app with only the analytics router mounted."""
    app = FastAPI(title="Verdandi Analytics Test")
    app.state.db = db
    app.state.settings = settings
    app.add_middleware(CorrelationIdMiddleware)
    add_exception_handlers(app)
    app.include_router(analytics_router_module.router, prefix="/api/v1")
    return app


@pytest.fixture()
def analytics_client(db: Database, settings: Settings) -> TestClient:
    return TestClient(_create_analytics_app(db, settings))


@pytest.fixture()
def populated_analytics_client(db: Database, settings: Settings) -> TestClient:
    """Client with pre-populated experiment + step data."""
    # Two GO experiments
    for _ in range(2):
        exp = db.create_experiment(
            Experiment(
                idea_title="GO Idea",
                idea_summary="Strong idea",
                status=ExperimentStatus.COMPLETED,
                worker_id="test-worker",
            )
        )
        db.save_step_result(
            experiment_id=exp.id,
            step_name="scoring",
            step_number=2,
            data_json=json.dumps(
                {
                    "total_score": 75,
                    "decision": "go",
                    "components": [],
                    "risks": [],
                    "opportunities": [],
                    "reasoning": "",
                    "council_votes": [],
                }
            ),
        )
        db.save_step_result(
            experiment_id=exp.id,
            step_name="deep_research",
            step_number=1,
            data_json=json.dumps(
                {
                    "search_results": [
                        {"title": "T1", "url": "u1", "source": "tavily", "relevance_score": 0.9},
                        {"title": "T2", "url": "u2", "source": "serper", "relevance_score": 0.7},
                    ],
                    "tam_estimate": "$500M",
                    "market_growth": "growing",
                    "competitors": [],
                    "competitor_gaps": [],
                    "demand_signals": [],
                    "key_findings": [],
                    "common_complaints": [],
                    "target_audience_size": "500K",
                    "willingness_to_pay": "$30/mo",
                    "research_summary": "",
                    "research_rounds_completed": 1,
                    "gap_analysis": None,
                    "experiment_id": exp.id,
                    "step_name": "deep_research",
                    "created_at": None,
                    "completed_at": None,
                    "worker_id": "test-worker",
                }
            ),
        )

    # One NO_GO experiment
    exp_no_go = db.create_experiment(
        Experiment(
            idea_title="NO_GO Idea",
            idea_summary="Weak idea",
            status=ExperimentStatus.NO_GO,
            worker_id="test-worker",
        )
    )
    db.save_step_result(
        experiment_id=exp_no_go.id,
        step_name="scoring",
        step_number=2,
        data_json=json.dumps(
            {
                "total_score": 20,
                "decision": "no_go",
                "components": [],
                "risks": [],
                "opportunities": [],
                "reasoning": "",
                "council_votes": [],
            }
        ),
    )

    return TestClient(_create_analytics_app(db, settings))


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/overview
# ---------------------------------------------------------------------------


class TestAnalyticsOverview:
    def test_returns_200(self, analytics_client: TestClient):
        resp = analytics_client.get("/api/v1/analytics/overview")
        assert resp.status_code == 200

    def test_empty_db_response_shape(self, analytics_client: TestClient):
        data = analytics_client.get("/api/v1/analytics/overview").json()
        assert data["total_experiments"] == 0
        assert data["go_rate"] == 0.0
        assert data["avg_score"] is None
        assert data["experiments_with_score"] == 0
        assert isinstance(data["by_status"], dict)

    def test_populated_db_counts(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/overview").json()
        assert data["total_experiments"] == 3
        assert data["experiments_with_score"] == 3
        assert data["go_rate"] == pytest.approx(2 / 3)
        assert data["avg_score"] == pytest.approx((75 + 75 + 20) / 3)

    def test_date_filter_from_far_future(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get(
            "/api/v1/analytics/overview?from=2099-01-01"
        ).json()
        assert data["total_experiments"] == 0

    def test_date_filter_to_far_past(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get(
            "/api/v1/analytics/overview?to=2000-01-01"
        ).json()
        assert data["total_experiments"] == 0

    def test_date_filter_today_includes_data(self, populated_analytics_client: TestClient):
        import datetime

        today = datetime.date.today().isoformat()
        data = populated_analytics_client.get(
            f"/api/v1/analytics/overview?from={today}&to={today}"
        ).json()
        assert data["total_experiments"] == 3


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/providers
# ---------------------------------------------------------------------------


class TestAnalyticsProviders:
    def test_returns_200(self, analytics_client: TestClient):
        resp = analytics_client.get("/api/v1/analytics/providers")
        assert resp.status_code == 200

    def test_empty_db_returns_empty_list(self, analytics_client: TestClient):
        data = analytics_client.get("/api/v1/analytics/providers").json()
        assert data["providers"] == []

    def test_providers_present_after_research(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/providers").json()
        assert len(data["providers"]) >= 2

        provider_names = {p["provider"] for p in data["providers"]}
        assert "tavily" in provider_names
        assert "serper" in provider_names

    def test_provider_schema(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/providers").json()
        for p in data["providers"]:
            assert "provider" in p
            assert "total_calls" in p
            assert "successful_calls" in p
            assert "failed_calls" in p
            assert "success_rate" in p
            assert 0.0 <= p["success_rate"] <= 1.0

    def test_date_filter_excludes_results(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get(
            "/api/v1/analytics/providers?from=2099-01-01"
        ).json()
        assert data["providers"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/scores
# ---------------------------------------------------------------------------


class TestAnalyticsScores:
    def test_returns_200(self, analytics_client: TestClient):
        resp = analytics_client.get("/api/v1/analytics/scores")
        assert resp.status_code == 200

    def test_empty_db_shape(self, analytics_client: TestClient):
        data = analytics_client.get("/api/v1/analytics/scores").json()
        assert len(data["distribution"]) == 5
        assert all(b["count"] == 0 for b in data["distribution"])
        assert data["trend"] == []
        assert data["decision_counts"] == {}

    def test_distribution_bucket_labels(self, analytics_client: TestClient):
        data = analytics_client.get("/api/v1/analytics/scores").json()
        labels = [b["bucket_label"] for b in data["distribution"]]
        assert labels == ["0-20", "20-40", "40-60", "60-80", "80-100"]

    def test_populated_distribution(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/scores").json()
        bucket_map = {b["bucket_label"]: b["count"] for b in data["distribution"]}
        # Two experiments scored 75 → "60-80", one scored 20 → "0-20"
        assert bucket_map["60-80"] == 2
        assert bucket_map["0-20"] == 1

    def test_decision_counts_populated(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/scores").json()
        assert data["decision_counts"].get("go", 0) == 2
        assert data["decision_counts"].get("no_go", 0) == 1

    def test_trend_present(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/scores").json()
        assert len(data["trend"]) >= 1
        for pt in data["trend"]:
            assert "date" in pt
            assert "avg_score" in pt
            assert "count" in pt

    def test_date_filter(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get(
            "/api/v1/analytics/scores?from=2099-01-01"
        ).json()
        assert all(b["count"] == 0 for b in data["distribution"])


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/pipeline
# ---------------------------------------------------------------------------


class TestAnalyticsPipeline:
    def test_returns_200(self, analytics_client: TestClient):
        resp = analytics_client.get("/api/v1/analytics/pipeline")
        assert resp.status_code == 200

    def test_empty_db_shape(self, analytics_client: TestClient):
        data = analytics_client.get("/api/v1/analytics/pipeline").json()
        assert data["total_experiments"] == 0
        assert data["completed_experiments"] == 0
        assert data["completion_rate"] == 0.0
        assert data["steps"] == []

    def test_counts_populated(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/pipeline").json()
        assert data["total_experiments"] == 3
        # Two completed, one no_go
        assert data["completed_experiments"] == 2
        assert data["completion_rate"] == pytest.approx(2 / 3)

    def test_steps_listed(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/pipeline").json()
        step_names = {s["step_name"] for s in data["steps"]}
        assert "deep_research" in step_names
        assert "scoring" in step_names

    def test_step_schema(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/pipeline").json()
        for s in data["steps"]:
            assert "step_name" in s
            assert "step_number" in s
            assert "total_executions" in s
            assert "experiments_with_step" in s

    def test_steps_ordered_by_step_number(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get("/api/v1/analytics/pipeline").json()
        step_numbers = [s["step_number"] for s in data["steps"]]
        assert step_numbers == sorted(step_numbers)

    def test_date_filter(self, populated_analytics_client: TestClient):
        data = populated_analytics_client.get(
            "/api/v1/analytics/pipeline?from=2099-01-01"
        ).json()
        assert data["total_experiments"] == 0
        assert data["steps"] == []
