"""Tests for Qdrant-backed long-term memory.

Uses QdrantClient(":memory:") for fast in-process testing
without requiring a running Qdrant server.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient  # type: ignore[import-untyped]

from verdandi.memory.long_term import LongTermMemory, SimilarIdeaResult


@pytest.fixture()
def qdrant_client() -> QdrantClient:
    """In-memory Qdrant client for testing."""
    return QdrantClient(":memory:")


@pytest.fixture()
def ltm(qdrant_client: QdrantClient) -> LongTermMemory:
    """LongTermMemory backed by in-memory Qdrant."""
    mem = LongTermMemory(client=qdrant_client)
    mem.ensure_collection()
    return mem


def _fake_embedding(seed: float = 0.5) -> list[float]:
    """Generate a deterministic 384-dim embedding for testing."""
    import math

    return [math.sin(seed * (i + 1)) for i in range(384)]


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------


class TestCollectionManagement:
    def test_ensure_collection_creates_it(self, qdrant_client: QdrantClient) -> None:
        ltm = LongTermMemory(client=qdrant_client)
        assert ltm.ensure_collection() is True
        assert qdrant_client.collection_exists(LongTermMemory.COLLECTION)

    def test_ensure_collection_idempotent(self, ltm: LongTermMemory) -> None:
        # Already created by fixture — should succeed again
        assert ltm.ensure_collection() is True

    def test_is_available_with_in_memory(self, ltm: LongTermMemory) -> None:
        assert ltm.is_available is True

    def test_is_available_no_url_no_client(self) -> None:
        ltm = LongTermMemory(qdrant_url="")
        assert ltm.is_available is False


# ---------------------------------------------------------------------------
# Store and retrieve
# ---------------------------------------------------------------------------


class TestStoreAndRetrieve:
    def test_store_and_find_similar(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(1.0)
        payload = {
            "topic_description": "AI-powered invoice reconciliation",
            "niche_category": "fintech",
            "status": "active",
        }
        assert ltm.store_idea_embedding("invoice-recon", emb, payload) is True

        # Search with same embedding — should find itself
        results = ltm.find_similar_ideas(emb, threshold=0.9)
        assert len(results) >= 1
        assert results[0].topic_key == "invoice-recon"
        assert results[0].similarity > 0.99

    def test_store_idempotent_upsert(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(2.0)
        ltm.store_idea_embedding("my-topic", emb, {"status": "active"})
        ltm.store_idea_embedding("my-topic", emb, {"status": "completed"})

        # Should still find only one point
        results = ltm.find_similar_ideas(emb, threshold=0.9)
        assert len(results) == 1
        assert results[0].topic_key == "my-topic"

    def test_find_no_similar_when_empty(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(3.0)
        results = ltm.find_similar_ideas(emb, threshold=0.82)
        assert results == []

    def test_find_filters_by_threshold(self, ltm: LongTermMemory) -> None:
        # Store two embeddings that are very different
        emb_a = _fake_embedding(1.0)
        emb_b = _fake_embedding(100.0)  # Very different seed
        ltm.store_idea_embedding("topic-a", emb_a, {"status": "active"})
        ltm.store_idea_embedding("topic-b", emb_b, {"status": "active"})

        # Search with emb_a and high threshold — should only find topic-a
        results = ltm.find_similar_ideas(emb_a, threshold=0.9)
        topic_keys = {r.topic_key for r in results}
        assert "topic-a" in topic_keys
        # topic-b might or might not appear depending on similarity

    def test_find_with_status_filter(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(5.0)
        ltm.store_idea_embedding("active-idea", emb, {"status": "active"})
        ltm.store_idea_embedding("completed-idea", emb, {"status": "completed"})

        # Filter to only active
        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("active",))
        topic_keys = {r.topic_key for r in results}
        assert "active-idea" in topic_keys
        assert "completed-idea" not in topic_keys


# ---------------------------------------------------------------------------
# Novelty scoring
# ---------------------------------------------------------------------------


class TestNoveltyScoring:
    def test_novelty_1_when_empty(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(7.0)
        score = ltm.compute_novelty_score(emb)
        assert score == 1.0

    def test_novelty_low_for_duplicate(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(8.0)
        ltm.store_idea_embedding("existing", emb, {"status": "active"})

        # Same embedding — should be near-zero novelty
        score = ltm.compute_novelty_score(emb)
        assert score < 0.05  # Very low novelty (near-duplicate)

    def test_novelty_high_for_unrelated(self, ltm: LongTermMemory) -> None:
        emb_existing = _fake_embedding(9.0)
        emb_new = _fake_embedding(200.0)
        ltm.store_idea_embedding("existing", emb_existing, {"status": "active"})

        score = ltm.compute_novelty_score(emb_new)
        assert score > 0.3  # Reasonably novel


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------


class TestStatusUpdate:
    def test_update_status(self, ltm: LongTermMemory) -> None:
        emb = _fake_embedding(10.0)
        ltm.store_idea_embedding("update-me", emb, {"status": "active"})

        assert ltm.update_status("update-me", "completed") is True

        # Verify by filtering — active filter should NOT find it
        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("active",))
        active_keys = {r.topic_key for r in results}
        assert "update-me" not in active_keys

        # Completed filter SHOULD find it
        results = ltm.find_similar_ideas(emb, threshold=0.5, status_filter=("completed",))
        completed_keys = {r.topic_key for r in results}
        assert "update-me" in completed_keys


# ---------------------------------------------------------------------------
# Point ID generation
# ---------------------------------------------------------------------------


class TestPointId:
    def test_deterministic_uuid(self) -> None:
        id1 = LongTermMemory.topic_key_to_point_id("my-topic")
        id2 = LongTermMemory.topic_key_to_point_id("my-topic")
        assert id1 == id2

    def test_different_topics_different_ids(self) -> None:
        id1 = LongTermMemory.topic_key_to_point_id("topic-a")
        id2 = LongTermMemory.topic_key_to_point_id("topic-b")
        assert id1 != id2


# ---------------------------------------------------------------------------
# SimilarIdeaResult model
# ---------------------------------------------------------------------------


class TestSimilarIdeaResult:
    def test_frozen_model(self) -> None:
        result = SimilarIdeaResult(
            point_id="abc",
            topic_key="test",
            topic_description="desc",
            similarity=0.95,
        )
        with pytest.raises(ValidationError):
            result.similarity = 0.5  # type: ignore[misc]
