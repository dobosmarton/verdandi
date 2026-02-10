"""Redis-backed research data cache with native TTL.

Caches individual API call results by (source, query) pair.
Uses Redis string keys with automatic TTL expiration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

import redis
import structlog

if TYPE_CHECKING:
    from verdandi.config import Settings

logger = structlog.get_logger()


class CacheStatsDict(TypedDict):
    """Statistics about the research cache."""

    total: int
    by_source: dict[str, int]


class ResearchCache:
    """Cache for research API results backed by Redis.

    Keys: verdandi:research:{source}:{normalized_query}
    Values: JSON-serialized API results
    TTL: Native Redis TTL (configurable, default 24h)
    """

    _PREFIX = "verdandi:research"

    def __init__(self, settings: Settings) -> None:
        # redis-py stubs: sync Redis.from_url returns Redis[bytes] by default
        self._client: redis.Redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self._ttl_seconds = settings.research_cache_ttl_hours * 3600

    @staticmethod
    def _normalize_query(query: str) -> str:
        """Normalize query for cache key: lowercase + collapse whitespace."""
        return " ".join(query.lower().split())

    def _make_key(self, source: str, query: str) -> str:
        """Build Redis key from source and normalized query."""
        normalized = self._normalize_query(query)
        return f"{self._PREFIX}:{source}:{normalized}"

    def get(self, source: str, query: str) -> str | None:
        """Get cached JSON string, or None if miss/expired."""
        key = self._make_key(source, query)
        # redis-py .get() returns bytes|str|None depending on decode_responses
        result = cast("str | None", self._client.get(key))
        if result is not None:
            logger.debug("research_cache_hit", source=source, query=query[:60])
        return result

    def set(self, source: str, query: str, data_json: str) -> None:
        """Cache a JSON string with TTL."""
        key = self._make_key(source, query)
        self._client.set(key, data_json, ex=self._ttl_seconds)
        logger.debug("research_cache_saved", source=source, query=query[:60])

    def purge_all(self) -> int:
        """Delete all research cache keys. Returns count deleted."""
        deleted = 0
        cursor: int = 0
        while True:
            # redis-py stubs return Awaitable|Any for sync calls — cast to actual type
            scan_result = cast(
                "tuple[int, list[str]]",
                self._client.scan(cursor, match=f"{self._PREFIX}:*", count=100),
            )
            cursor, keys = scan_result
            if keys:
                deleted += cast("int", self._client.delete(*keys))
            if cursor == 0:
                break
        return deleted

    def stats(self) -> CacheStatsDict:
        """Return cache statistics using SCAN (non-blocking)."""
        by_source: dict[str, int] = {}
        total = 0
        cursor: int = 0
        while True:
            # redis-py stubs return Awaitable|Any for sync calls — cast to actual type
            scan_result = cast(
                "tuple[int, list[str]]",
                self._client.scan(cursor, match=f"{self._PREFIX}:*", count=100),
            )
            cursor, keys = scan_result
            for key in keys:
                total += 1
                # Key format: verdandi:research:{source}:{query}
                parts = str(key).split(":", 3)
                if len(parts) >= 3:
                    source = parts[2]
                    by_source[source] = by_source.get(source, 0) + 1
            if cursor == 0:
                break
        return CacheStatsDict(total=total, by_source=by_source)

    def ping(self) -> bool:
        """Check Redis connectivity."""
        try:
            return bool(self._client.ping())
        except redis.ConnectionError:
            return False
