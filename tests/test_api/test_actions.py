"""Tests for action API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from verdandi.db import Database


class TestStepsEndpoints:
    def test_get_steps_empty(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments/1/steps")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_log_empty(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments/1/log")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_steps_with_data(self, populated_client: TestClient, populated_db: Database):
        import json

        populated_db.save_step_result(
            experiment_id=1,
            step_name="scoring",
            step_number=2,
            data_json=json.dumps({"score": 85}),
            worker_id="test",
        )
        resp = populated_client.get("/api/v1/experiments/1/steps")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["step_name"] == "scoring"

    def test_get_single_step(self, populated_client: TestClient, populated_db: Database):
        import json

        populated_db.save_step_result(
            experiment_id=1,
            step_name="scoring",
            step_number=2,
            data_json=json.dumps({"score": 85}),
            worker_id="test",
        )
        resp = populated_client.get("/api/v1/experiments/1/steps/scoring")
        assert resp.status_code == 200
        data = resp.json()
        assert data["step_name"] == "scoring"
        assert data["data"]["score"] == 85

    def test_get_nonexistent_step(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments/1/steps/nonexistent")
        assert resp.status_code == 200
        assert resp.json() is None
