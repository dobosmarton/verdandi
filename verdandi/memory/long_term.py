"""Long-term memory via Qdrant vector database.

Provides indexed semantic search over all previous idea embeddings,
replacing the O(n) Python-loop in coordination.py with Qdrant's
HNSW-indexed vector search.

Every public method wraps Qdrant calls in try/except so that failures
degrade gracefully — the orchestrator falls back to coordination.py's
Python-loop or fingerprint-only dedup.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

logger = structlog.get_logger()

# Namespace for deterministic UUID5 point IDs from topic keys.
_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef0123456789")


class SimilarIdeaResult(BaseModel):
    """A single result from a similarity search in long-term memory."""

    model_config = ConfigDict(frozen=True)

    point_id: str
    topic_key: str
    topic_description: str
    similarity: float


class LongTermMemory:
    """Qdrant-backed long-term memory for the orchestrator.

    Stores idea embeddings as Qdrant points with payload metadata.
    Provides O(log n) similarity search via HNSW indexing, compared
    to coordination.py's O(n) Python-loop fallback.

    Usage::

        ltm = LongTermMemory(qdrant_url="http://localhost:6333")
        if ltm.is_available:
            ltm.ensure_collection()
            ltm.store_idea_embedding(topic_key, embedding, payload)
            similar = ltm.find_similar_ideas(embedding, threshold=0.82)
    """

    COLLECTION = "idea_embeddings"
    VECTOR_SIZE = 384

    def __init__(
        self,
        qdrant_url: str = "",
        qdrant_api_key: str = "",
        *,
        client: QdrantClient | None = None,
    ) -> None:
        self._url = qdrant_url
        self._api_key = qdrant_api_key
        self._client: QdrantClient | None = client
        self._available: bool | None = None
        self._last_health_check: float = 0.0
        self._collection_ensured: bool = False

    def _get_client(self) -> QdrantClient:
        """Lazy-init Qdrant client."""
        if self._client is None:
            from qdrant_client import QdrantClient as _QdrantClient

            kwargs: dict[str, Any] = {"url": self._url}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = _QdrantClient(**kwargs)
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if Qdrant is reachable. Result cached for 60 seconds."""
        now = time.monotonic()
        if self._available is not None and (now - self._last_health_check) < 60.0:
            return self._available

        if not self._url and self._client is None:
            self._available = False
            self._last_health_check = now
            return False

        try:
            client = self._get_client()
            # collection_exists is a lightweight call that verifies connectivity
            client.collection_exists(self.COLLECTION)
            self._available = True
        except Exception as exc:
            logger.warning("Qdrant health check failed", error=str(exc))
            self._available = False

        self._last_health_check = now
        return self._available

    def ensure_collection(self) -> bool:
        """Create the idea_embeddings collection if it doesn't exist.

        Returns True if collection exists (or was created), False on error.
        """
        try:
            from qdrant_client.http.models import Distance, VectorParams

            client = self._get_client()
            if not client.collection_exists(self.COLLECTION):
                client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection", collection=self.COLLECTION)
            return True
        except Exception as exc:
            logger.warning("Failed to ensure Qdrant collection", error=str(exc))
            return False

    @staticmethod
    def topic_key_to_point_id(topic_key: str) -> str:
        """Deterministic UUID5 from topic_key for idempotent upserts."""
        return str(uuid.uuid5(_NAMESPACE, topic_key))

    def store_idea_embedding(
        self,
        topic_key: str,
        embedding: list[float],
        payload: dict[str, Any],
    ) -> bool:
        """Store an idea embedding as a Qdrant point.

        Uses UUID5(topic_key) as point ID for idempotent upserts —
        re-storing the same topic_key overwrites the previous point.

        Returns True on success, False on error.
        """
        try:
            from qdrant_client.http.models import PointStruct

            if not self._collection_ensured:
                self._collection_ensured = self.ensure_collection()

            client = self._get_client()
            point_id = self.topic_key_to_point_id(topic_key)

            # Ensure payload includes the topic_key for retrieval
            full_payload = {**payload, "topic_key": topic_key}

            client.upsert(
                collection_name=self.COLLECTION,
                wait=True,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=full_payload,
                    ),
                ],
            )
            logger.debug("Stored idea embedding", topic_key=topic_key, point_id=point_id)
            return True
        except Exception as exc:
            logger.warning("Failed to store idea embedding", topic_key=topic_key, error=str(exc))
            return False

    def find_similar_ideas(
        self,
        embedding: list[float],
        *,
        threshold: float = 0.82,
        limit: int = 5,
        status_filter: tuple[str, ...] | None = None,
    ) -> list[SimilarIdeaResult]:
        """Find ideas similar to the given embedding.

        Args:
            embedding: Query vector (384-dim).
            threshold: Minimum cosine similarity score.
            limit: Maximum results to return.
            status_filter: If set, only match points with these statuses.

        Returns:
            List of SimilarIdeaResult sorted by similarity (descending).
        """
        try:
            client = self._get_client()

            query_filter = None
            if status_filter:
                from qdrant_client.http.models import (
                    FieldCondition,
                    Filter,
                    MatchAny,
                )

                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="status",
                            match=MatchAny(any=list(status_filter)),
                        ),
                    ],
                )

            response = client.query_points(
                collection_name=self.COLLECTION,
                query=embedding,
                query_filter=query_filter,
                limit=limit,
                score_threshold=threshold,
            )

            results: list[SimilarIdeaResult] = []
            for hit in response.points:
                payload = hit.payload or {}
                results.append(
                    SimilarIdeaResult(
                        point_id=str(hit.id),
                        topic_key=str(payload.get("topic_key", "")),
                        topic_description=str(payload.get("topic_description", "")),
                        similarity=hit.score if hit.score is not None else 0.0,
                    )
                )
            return results

        except Exception as exc:
            logger.warning("Qdrant similarity search failed", error=str(exc))
            return []

    def compute_novelty_score(
        self,
        embedding: list[float],
        *,
        status_filter: tuple[str, ...] | None = None,
    ) -> float:
        """Compute novelty as 1.0 - max_similarity to existing ideas.

        Returns 1.0 (completely novel) if no similar ideas exist or on error.
        Returns close to 0.0 if a near-duplicate exists.
        """
        try:
            # Search with a very low threshold to find the closest match
            similar = self.find_similar_ideas(
                embedding,
                threshold=0.0,
                limit=1,
                status_filter=status_filter,
            )
            if not similar:
                return 1.0
            return max(0.0, 1.0 - similar[0].similarity)
        except Exception as exc:
            logger.warning("Qdrant novelty computation failed", error=str(exc))
            return 1.0

    def update_status(self, topic_key: str, new_status: str) -> bool:
        """Update the status payload field on an existing point.

        Returns True on success, False on error.
        """
        try:
            client = self._get_client()
            point_id = self.topic_key_to_point_id(topic_key)

            client.set_payload(
                collection_name=self.COLLECTION,
                payload={"status": new_status},
                points=[point_id],
            )
            logger.debug("Updated point status", topic_key=topic_key, status=new_status)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to update point status",
                topic_key=topic_key,
                error=str(exc),
            )
            return False
