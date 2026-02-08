"""Tests for system API endpoints (health, config check)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestHealthCheck:
    def test_healthy(self, client: TestClient):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert data["db_connected"] is True


class TestConfigCheck:
    def test_config_check(self, client: TestClient):
        resp = client.get("/api/v1/config/check")
        assert resp.status_code == 200
        data = resp.json()
        configured = data["configured"]

        # Our test settings have anthropic_api_key="test-key"
        assert configured["anthropic"] is True

        # All other keys should be False (empty strings in test settings)
        assert configured["tavily"] is False
        assert configured["cloudflare"] is False
