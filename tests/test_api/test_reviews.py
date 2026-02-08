"""Tests for review API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestListPendingReviews:
    def test_no_pending(self, client: TestClient):
        resp = client.get("/api/v1/reviews/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_with_pending(self, populated_client: TestClient):
        resp = populated_client.get("/api/v1/reviews/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["experiments"][0]["idea_title"] == "Review Me"


class TestSubmitReview:
    def test_approve(self, populated_client: TestClient):
        resp = populated_client.post(
            "/api/v1/reviews/4",
            json={"approved": True, "notes": "LGTM", "reviewed_by": "tester"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["reviewed_by"] == "tester"
        assert data["review_notes"] == "LGTM"

    def test_reject(self, populated_client: TestClient):
        resp = populated_client.post(
            "/api/v1/reviews/4",
            json={"approved": False, "notes": "Not ready"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

    def test_review_nonexistent(self, populated_client: TestClient):
        resp = populated_client.post(
            "/api/v1/reviews/99999",
            json={"approved": True},
        )
        assert resp.status_code >= 400

    def test_review_wrong_status(self, populated_client: TestClient):
        # Experiment 1 is pending, not awaiting_review
        resp = populated_client.post(
            "/api/v1/reviews/1",
            json={"approved": True},
        )
        assert resp.status_code >= 400
