"""Tests for experiment API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestListExperiments:
    def test_empty_list(self, client: TestClient):
        resp = client.get("/api/v1/experiments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["experiments"] == []
        assert data["total"] == 0

    def test_list_all(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4

    def test_filter_by_status(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        for exp in data["experiments"]:
            assert exp["status"] == "pending"


class TestGetExperiment:
    def test_get_existing(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["idea_title"] == "Idea 0"

    def test_get_nonexistent(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/experiments/99999")
        # Should return error (our handler raises ValueError which becomes 500 or 422)
        assert resp.status_code >= 400


class TestCorrelationId:
    def test_response_has_correlation_id(self, client: TestClient):
        resp = client.get("/api/v1/health")
        assert "x-correlation-id" in resp.headers
        assert len(resp.headers["x-correlation-id"]) > 0

    def test_echoes_provided_correlation_id(self, client: TestClient):
        resp = client.get(
            "/api/v1/health",
            headers={"X-Correlation-ID": "test-123"},
        )
        assert resp.headers["x-correlation-id"] == "test-123"
