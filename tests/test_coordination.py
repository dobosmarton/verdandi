"""Tests for multi-instance coordination and deduplication."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from verdandi.coordination import (
    TopicReservationManager,
    idea_fingerprint,
    jaccard_similarity,
    normalize_topic_key,
)

if TYPE_CHECKING:
    from verdandi.db import Database


@pytest.fixture()
def mgr(db: Database) -> TopicReservationManager:
    return TopicReservationManager(db.Session)


class TestIdeaFingerprint:
    def test_basic_fingerprint(self):
        fp = idea_fingerprint("AI Status Pages", "Monitor your website uptime with AI")
        assert isinstance(fp, str)
        assert len(fp) > 0
        assert "|" in fp  # Pipe-separated

    def test_deterministic(self):
        fp1 = idea_fingerprint("Widget Builder", "Build widgets fast")
        fp2 = idea_fingerprint("Widget Builder", "Build widgets fast")
        assert fp1 == fp2

    def test_stop_words_removed(self):
        fp = idea_fingerprint("The Best App For You", "A great tool to use")
        words = set(fp.split("|"))
        assert "the" not in words
        assert "for" not in words
        assert "tool" not in words

    def test_case_insensitive(self):
        fp1 = idea_fingerprint("AI Widget", "Build Things")
        fp2 = idea_fingerprint("ai widget", "build things")
        assert fp1 == fp2


class TestJaccardSimilarity:
    def test_identical(self):
        assert jaccard_similarity("a|b|c", "a|b|c") == 1.0

    def test_no_overlap(self):
        assert jaccard_similarity("a|b|c", "d|e|f") == 0.0

    def test_partial_overlap(self):
        sim = jaccard_similarity("a|b|c|d", "a|b|e|f")
        assert 0.0 < sim < 1.0
        # 2 shared out of 6 unique = 2/6 = 0.333...
        assert abs(sim - 2 / 6) < 0.01

    def test_empty_strings(self):
        assert jaccard_similarity("", "a|b") == 0.0
        assert jaccard_similarity("a|b", "") == 0.0
        assert jaccard_similarity("", "") == 0.0


class TestNormalizeTopicKey:
    def test_basic(self):
        assert normalize_topic_key("AI Status Pages") == "ai-status-pages"

    def test_special_chars(self):
        key = normalize_topic_key("Widget — AI-Powered!")
        assert "!" not in key
        # Special chars removed, spaces become dashes
        assert "widget" in key
        assert "ai-powered" in key

    def test_truncation(self):
        long_title = "A" * 200
        key = normalize_topic_key(long_title)
        assert len(key) <= 100


class TestTopicReservationManager:
    def test_try_reserve_success(self, mgr: TopicReservationManager):
        result = mgr.try_reserve("worker-1", "ai-status-pages", "Status page tool")
        assert result is True

    def test_try_reserve_duplicate_fails(self, mgr: TopicReservationManager):
        mgr.try_reserve("worker-1", "ai-status-pages")
        result = mgr.try_reserve("worker-2", "ai-status-pages")
        assert result is False

    def test_different_topics_succeed(self, mgr: TopicReservationManager):
        assert mgr.try_reserve("worker-1", "topic-a") is True
        assert mgr.try_reserve("worker-1", "topic-b") is True

    def test_release(self, mgr: TopicReservationManager):
        mgr.try_reserve("worker-1", "topic-a")
        released = mgr.release("worker-1", "topic-a")
        assert released is True

        # Can now reserve the same topic
        result = mgr.try_reserve("worker-2", "topic-a")
        assert result is True

    def test_release_nonexistent(self, mgr: TopicReservationManager):
        assert mgr.release("worker-1", "nonexistent") is False

    def test_release_completed(self, mgr: TopicReservationManager):
        mgr.try_reserve("worker-1", "topic-a")
        released = mgr.release("worker-1", "topic-a", completed=True)
        assert released is True

    def test_renew(self, mgr: TopicReservationManager):
        mgr.try_reserve("worker-1", "topic-a")
        renewed = mgr.renew("worker-1", "topic-a")
        assert renewed is True

    def test_renew_nonexistent(self, mgr: TopicReservationManager):
        assert mgr.renew("worker-1", "nonexistent") is False

    def test_list_active(self, mgr: TopicReservationManager):
        mgr.try_reserve("w1", "topic-a", "Desc A")
        mgr.try_reserve("w2", "topic-b", "Desc B")

        active = mgr.list_active()
        assert len(active) == 2
        keys = {r["topic_key"] for r in active}
        assert keys == {"topic-a", "topic-b"}

    def test_list_all_includes_released(self, mgr: TopicReservationManager):
        mgr.try_reserve("w1", "topic-a")
        mgr.release("w1", "topic-a")
        mgr.try_reserve("w2", "topic-b")

        all_reservations = mgr.list_all()
        assert len(all_reservations) == 2

        active = mgr.list_active()
        assert len(active) == 1

    def test_find_similar_by_fingerprint(self, mgr: TopicReservationManager):
        fp1 = idea_fingerprint("AI Status Monitor", "Monitor website uptime with AI")
        mgr.try_reserve("w1", "ai-status-monitor", fingerprint=fp1)

        fp2 = idea_fingerprint("AI Uptime Monitor", "Monitor website uptime using AI")
        matches = mgr.find_similar_by_fingerprint(fp2, threshold=0.3)
        assert len(matches) >= 1
        assert matches[0]["topic_key"] == "ai-status-monitor"

    def test_find_similar_no_match(self, mgr: TopicReservationManager):
        fp1 = idea_fingerprint("AI Status Monitor", "Monitor website uptime with AI")
        mgr.try_reserve("w1", "ai-status-monitor", fingerprint=fp1)

        fp2 = idea_fingerprint("Recipe Cookbook App", "Find and share cooking recipes")
        matches = mgr.find_similar_by_fingerprint(fp2, threshold=0.6)
        assert len(matches) == 0

    def test_find_similar_by_fingerprint_with_completed_status(self, mgr: TopicReservationManager):
        """Completed reservations should be found when statuses includes 'completed'."""
        fp1 = idea_fingerprint("Capacity Planning Dashboard", "Plan team capacity for services")
        mgr.try_reserve("w1", "capacity-planning", fingerprint=fp1)
        mgr.release("w1", "capacity-planning", completed=True)

        # Default statuses=("active",) should NOT find it
        fp2 = idea_fingerprint("Capacity Planner", "Plan team capacity for firms")
        matches_active = mgr.find_similar_by_fingerprint(fp2, threshold=0.3)
        assert len(matches_active) == 0

        # With completed status, should find it
        matches_all = mgr.find_similar_by_fingerprint(
            fp2, threshold=0.3, statuses=("active", "completed")
        )
        assert len(matches_all) >= 1
        assert matches_all[0]["topic_key"] == "capacity-planning"

    def test_find_similar_by_embedding(self, mgr: TopicReservationManager):
        """Embedding similarity should find semantically similar reservations."""
        from verdandi.embeddings import EmbeddingService

        embedder = EmbeddingService()
        if not embedder.is_available:
            pytest.skip("sentence-transformers not installed")

        emb1 = embedder.embed("AI-powered status page monitoring tool")
        mgr.try_reserve(
            "w1",
            "ai-status-monitor",
            embedding=emb1,
            fingerprint="ai|monitor|status",
        )

        emb2 = embedder.embed("Status page monitor with artificial intelligence")
        matches = mgr.find_similar_by_embedding(emb2, threshold=0.7)
        assert len(matches) >= 1
        assert matches[0]["topic_key"] == "ai-status-monitor"

    def test_compute_novelty_score_no_previous(self, mgr: TopicReservationManager):
        """With no previous ideas, novelty should be 1.0."""
        from verdandi.embeddings import EmbeddingService

        embedder = EmbeddingService()
        if not embedder.is_available:
            pytest.skip("sentence-transformers not installed")

        emb = embedder.embed("Brand new unique product idea")
        score = mgr.compute_novelty_score(emb)
        assert score == 1.0

    def test_compute_novelty_score_with_similar(self, mgr: TopicReservationManager):
        """Novelty score should be low when a similar idea exists."""
        from verdandi.embeddings import EmbeddingService

        embedder = EmbeddingService()
        if not embedder.is_available:
            pytest.skip("sentence-transformers not installed")

        emb1 = embedder.embed("Capacity Planning Dashboard for Professional Services")
        mgr.try_reserve("w1", "capacity-dashboard", embedding=emb1)

        emb2 = embedder.embed("Capacity Planner for Professional Services Firms")
        score = mgr.compute_novelty_score(emb2)
        # Very similar ideas — novelty should be low
        assert score < 0.3

    def test_compute_novelty_score_unrelated(self, mgr: TopicReservationManager):
        """Novelty score should be high for unrelated ideas."""
        from verdandi.embeddings import EmbeddingService

        embedder = EmbeddingService()
        if not embedder.is_available:
            pytest.skip("sentence-transformers not installed")

        emb1 = embedder.embed("Capacity Planning Dashboard for Professional Services")
        mgr.try_reserve("w1", "capacity-dashboard", embedding=emb1)

        emb2 = embedder.embed("Recipe cookbook app for finding and sharing cooking ideas")
        score = mgr.compute_novelty_score(emb2)
        assert score > 0.5
