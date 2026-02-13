"""Tests for the embedding service."""

from __future__ import annotations

import pytest

from verdandi.embeddings import EmbeddingService


@pytest.fixture()
def embedder() -> EmbeddingService:
    return EmbeddingService()


class TestEmbeddingService:
    def test_is_available(self, embedder: EmbeddingService):
        assert embedder.is_available is True

    def test_embed_returns_384_dim_vector(self, embedder: EmbeddingService):
        vec = embedder.embed("Hello world")
        assert isinstance(vec, list)
        assert len(vec) == 384
        assert all(isinstance(v, float) for v in vec)

    def test_embed_normalized(self, embedder: EmbeddingService):
        """Normalized embeddings should have magnitude ~1.0."""
        import math

        vec = embedder.embed("Test embedding normalization")
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert abs(magnitude - 1.0) < 0.01

    def test_cosine_similarity_identical(self, embedder: EmbeddingService):
        vec = embedder.embed("AI-powered status page monitor")
        sim = EmbeddingService.cosine_similarity(vec, vec)
        assert sim > 0.99

    def test_cosine_similarity_similar(self, embedder: EmbeddingService):
        a = embedder.embed("Capacity Planning Dashboard for Professional Services")
        b = embedder.embed("Capacity Planner for Professional Services Firms")
        sim = EmbeddingService.cosine_similarity(a, b)
        # These are very similar ideas — should have high similarity
        assert sim > 0.7

    def test_cosine_similarity_unrelated(self, embedder: EmbeddingService):
        a = embedder.embed("AI-powered status page monitor for SaaS")
        b = embedder.embed("Recipe cookbook app for finding cooking ideas")
        sim = EmbeddingService.cosine_similarity(a, b)
        assert sim < 0.5

    def test_cosine_similarity_zero_vector(self):
        zero = [0.0] * 384
        normal = [1.0] + [0.0] * 383
        sim = EmbeddingService.cosine_similarity(zero, normal)
        assert sim == 0.0

    def test_model_lazy_loaded(self):
        """Model should not be loaded on init."""
        svc = EmbeddingService()
        assert svc._model is None
        # Accessing .model triggers lazy load
        _ = svc.embed("trigger load")
        assert svc._model is not None
