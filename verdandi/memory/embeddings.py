"""Embedding service for semantic similarity using all-MiniLM-L6-v2."""

from __future__ import annotations

import math

import structlog

logger = structlog.get_logger()


def _dot_product(a: list[float], b: list[float]) -> float:
    """Compute dot product of two vectors."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def _magnitude(v: list[float]) -> float:
    """Compute the magnitude (L2 norm) of a vector."""
    return math.sqrt(sum(x * x for x in v))


class EmbeddingService:
    """Compute text embeddings via all-MiniLM-L6-v2.

    The model is lazy-loaded on first use so that importing this module
    doesn't incur torch startup cost for CLI commands that don't need
    embeddings.
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._available: bool | None = None

    @property
    def is_available(self) -> bool:
        """Check if sentence-transformers is installed and importable."""
        if self._available is None:
            try:
                import sentence_transformers  # noqa: F401  # type: ignore[import-untyped]

                self._available = True
            except ImportError:
                self._available = False
        return self._available

    @property
    def model(self) -> object:
        """Lazy-load the SentenceTransformer model."""
        if self._model is None:
            if not self.is_available:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Install with: pip install sentence-transformers"
                )
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model", model="all-MiniLM-L6-v2")
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def embed(self, text: str) -> list[float]:
        """Compute a 384-dimensional normalized embedding for text.

        Because ``normalize_embeddings=True``, cosine similarity between
        two embeddings equals their dot product (faster computation).
        """
        from sentence_transformers import SentenceTransformer

        model = self.model
        assert isinstance(model, SentenceTransformer)
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two embedding vectors.

        For normalized vectors (from ``embed()``), this equals the dot
        product.  Falls back to full cosine formula for safety.
        """
        dot = _dot_product(a, b)
        mag_a = _magnitude(a)
        mag_b = _magnitude(b)
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)
