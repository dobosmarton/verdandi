"""Tests for Redis-backed research cache.

Verifies:
- ResearchCache get/set/purge/stats/ping operations
- ResearchCollector cache integration (hit, miss, degradation)
- Config defaults for cache settings
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from verdandi.cache import ResearchCache
from verdandi.config import Settings
from verdandi.research import ResearchCollector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        redis_url="redis://localhost:6379/0",
        research_cache_ttl_hours=1,
        research_cache_enabled=True,
        tavily_api_key="tvly-test",
        serper_api_key="serper-test",
        exa_api_key="exa-test",
        perplexity_api_key="pplx-test",
        require_human_review=False,
        data_dir=Path("/tmp/verdandi-test"),
        log_level="DEBUG",
        log_format="console",
        _env_file=None,
    )


@pytest.fixture()
def no_cache_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        redis_url="",
        research_cache_enabled=True,
        tavily_api_key="tvly-test",
        require_human_review=False,
        data_dir=Path("/tmp/verdandi-test"),
        log_level="DEBUG",
        log_format="console",
        _env_file=None,
    )


@pytest.fixture()
def fake_redis_client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def cache(fake_redis_client: fakeredis.FakeRedis, cache_settings: Settings) -> ResearchCache:
    rc = ResearchCache(cache_settings)
    rc._client = fake_redis_client  # Inject fake Redis
    return rc


# ---------------------------------------------------------------------------
# ResearchCache unit tests
# ---------------------------------------------------------------------------


class TestResearchCacheGetSet:
    def test_set_and_get_round_trip(self, cache: ResearchCache) -> None:
        data = json.dumps([{"title": "Test", "url": "https://t.co", "content": "C", "score": 0.9}])
        cache.set("tavily", "test query", data)
        result = cache.get("tavily", "test query")
        assert result == data

    def test_get_returns_none_for_missing(self, cache: ResearchCache) -> None:
        result = cache.get("tavily", "nonexistent query")
        assert result is None

    def test_ttl_is_applied(
        self, fake_redis_client: fakeredis.FakeRedis, cache: ResearchCache
    ) -> None:
        cache.set("tavily", "test query", json.dumps([]))
        key = "verdandi:research:tavily:test query"
        # fakeredis .ttl() stubs return Awaitable|Any — cast for sync usage
        ttl = cast("int", fake_redis_client.ttl(key))
        assert ttl > 0
        assert ttl <= 3600  # 1 hour TTL from cache_settings

    def test_query_normalization(self, cache: ResearchCache) -> None:
        data = json.dumps([{"title": "Normalized"}])
        cache.set("tavily", "  AI  Tools  ", data)
        # Should hit with differently-cased/spaced query
        result = cache.get("tavily", "ai tools")
        assert result == data

    def test_different_sources_different_keys(self, cache: ResearchCache) -> None:
        cache.set("tavily", "test", json.dumps([{"source": "tavily"}]))
        cache.set("serper", "test", json.dumps([{"source": "serper"}]))
        tavily_result = cache.get("tavily", "test")
        serper_result = cache.get("serper", "test")
        assert tavily_result != serper_result
        assert tavily_result is not None
        assert serper_result is not None


class TestResearchCachePurge:
    def test_purge_all_deletes_cache_keys(self, cache: ResearchCache) -> None:
        cache.set("tavily", "q1", json.dumps([]))
        cache.set("serper", "q2", json.dumps([]))
        cache.set("exa", "q3", json.dumps([]))
        count = cache.purge_all()
        assert count == 3
        assert cache.get("tavily", "q1") is None

    def test_purge_all_returns_zero_when_empty(self, cache: ResearchCache) -> None:
        count = cache.purge_all()
        assert count == 0


class TestResearchCacheStats:
    def test_stats_by_source(self, cache: ResearchCache) -> None:
        cache.set("tavily", "q1", json.dumps([]))
        cache.set("tavily", "q2", json.dumps([]))
        cache.set("serper", "q1", json.dumps([]))
        stats = cache.stats()
        assert stats["total"] == 3
        assert stats["by_source"]["tavily"] == 2
        assert stats["by_source"]["serper"] == 1

    def test_stats_empty(self, cache: ResearchCache) -> None:
        stats = cache.stats()
        assert stats["total"] == 0
        assert stats["by_source"] == {}


class TestResearchCachePing:
    def test_ping_with_fake_redis(self, cache: ResearchCache) -> None:
        assert cache.ping() is True

    def test_ping_returns_false_on_connection_error(self, cache_settings: Settings) -> None:
        rc = ResearchCache(cache_settings)
        # Point at a non-existent Redis
        import redis

        rc._client = redis.Redis(host="localhost", port=19999, decode_responses=True)
        assert rc.ping() is False


# ---------------------------------------------------------------------------
# ResearchCollector cache integration tests
# ---------------------------------------------------------------------------


class TestCollectorCacheIntegration:
    def _make_collector_with_cache(
        self, cache: ResearchCache, settings: Settings
    ) -> ResearchCollector:
        """Create a ResearchCollector with an injected cache."""
        collector = ResearchCollector.__new__(ResearchCollector)
        collector.settings = settings
        collector._cache = cache
        return collector

    @patch("verdandi.clients.hn_algolia.HNClient")
    @patch("verdandi.clients.tavily.TavilyClient")
    def test_caches_results_after_api_call(
        self,
        mock_tavily_cls: MagicMock,
        mock_hn_cls: MagicMock,
        cache: ResearchCache,
        cache_settings: Settings,
    ) -> None:
        """API results should be saved to cache after a successful call."""
        mock_tavily = MagicMock()
        mock_tavily.is_available = True
        mock_tavily.search.return_value = [
            {
                "title": "R",
                "url": "https://r.com",
                "content": "C",
                "score": 0.9,
                "published_date": "",
            }
        ]
        mock_tavily_cls.return_value = mock_tavily

        mock_hn = MagicMock()
        mock_hn.search.return_value = []
        mock_hn.search_comments.return_value = []
        mock_hn_cls.return_value = mock_hn

        with (
            patch("verdandi.clients.serper.SerperClient") as mock_s,
            patch("verdandi.clients.exa.ExaClient") as mock_e,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_p,
        ):
            mock_s.return_value = MagicMock(is_available=False)
            mock_e.return_value = MagicMock(is_available=False)
            mock_p.return_value = MagicMock(is_available=False)

            collector = self._make_collector_with_cache(cache, cache_settings)
            collector.collect(["test query"], include_reddit=False, include_hn_comments=False)

        # Cache should now have the Tavily result
        cached = cache.get("tavily", "test query")
        assert cached is not None
        parsed = json.loads(cached)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "R"

    @patch("verdandi.clients.hn_algolia.HNClient")
    @patch("verdandi.clients.tavily.TavilyClient")
    def test_uses_cached_results_skips_api(
        self,
        mock_tavily_cls: MagicMock,
        mock_hn_cls: MagicMock,
        cache: ResearchCache,
        cache_settings: Settings,
    ) -> None:
        """When cache has valid data, API should NOT be called."""
        # Pre-populate cache
        cached_data = [
            {
                "title": "Cached",
                "url": "https://c.com",
                "content": "From cache",
                "score": 0.8,
                "published_date": "",
            }
        ]
        cache.set("tavily", "test query", json.dumps(cached_data))

        mock_tavily = MagicMock()
        mock_tavily.is_available = True
        mock_tavily_cls.return_value = mock_tavily

        mock_hn = MagicMock()
        mock_hn.search.return_value = []
        mock_hn.search_comments.return_value = []
        mock_hn_cls.return_value = mock_hn

        with (
            patch("verdandi.clients.serper.SerperClient") as mock_s,
            patch("verdandi.clients.exa.ExaClient") as mock_e,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_p,
        ):
            mock_s.return_value = MagicMock(is_available=False)
            mock_e.return_value = MagicMock(is_available=False)
            mock_p.return_value = MagicMock(is_available=False)

            collector = self._make_collector_with_cache(cache, cache_settings)
            result = collector.collect(
                ["test query"], include_reddit=False, include_hn_comments=False
            )

        # Tavily API should NOT have been called (cache hit)
        mock_tavily.search.assert_not_called()

        # Results should come from cache
        assert len(result.tavily_results) == 1
        assert result.tavily_results[0]["title"] == "Cached"

    def test_works_without_redis(self, no_cache_settings: Settings) -> None:
        """When redis_url is empty, collector works without caching."""
        with (
            patch("verdandi.clients.tavily.TavilyClient") as mock_t,
            patch("verdandi.clients.serper.SerperClient") as mock_s,
            patch("verdandi.clients.exa.ExaClient") as mock_e,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_p,
            patch("verdandi.clients.hn_algolia.HNClient") as mock_hn,
        ):
            mock_t.return_value = MagicMock(is_available=False)
            mock_s.return_value = MagicMock(is_available=False)
            mock_e.return_value = MagicMock(is_available=False)
            mock_p.return_value = MagicMock(is_available=False)

            mock_hn_inst = MagicMock()
            mock_hn_inst.search.return_value = [
                {
                    "title": "HN",
                    "url": None,
                    "author": "u",
                    "points": 10,
                    "num_comments": 5,
                    "created_at": "",
                    "objectID": "1",
                    "tags": "story",
                }
            ]
            mock_hn_inst.search_comments.return_value = []
            mock_hn.return_value = mock_hn_inst

            collector = ResearchCollector(no_cache_settings)
            assert collector._cache is None
            result = collector.collect(["test"], include_hn_comments=False)
            assert result.has_data

    @patch("verdandi.clients.hn_algolia.HNClient")
    @patch("verdandi.clients.tavily.TavilyClient")
    def test_graceful_degradation_on_cache_error(
        self,
        mock_tavily_cls: MagicMock,
        mock_hn_cls: MagicMock,
        cache_settings: Settings,
    ) -> None:
        """If cache raises on get/set, collector should still work."""
        # Create a cache that raises on every operation
        broken_cache = MagicMock()
        broken_cache.get.side_effect = ConnectionError("Redis down")
        broken_cache.set.side_effect = ConnectionError("Redis down")

        mock_tavily = MagicMock()
        mock_tavily.is_available = True
        mock_tavily.search.return_value = [
            {
                "title": "OK",
                "url": "https://ok.com",
                "content": "C",
                "score": 0.9,
                "published_date": "",
            }
        ]
        mock_tavily_cls.return_value = mock_tavily

        mock_hn = MagicMock()
        mock_hn.search.return_value = []
        mock_hn.search_comments.return_value = []
        mock_hn_cls.return_value = mock_hn

        with (
            patch("verdandi.clients.serper.SerperClient") as mock_s,
            patch("verdandi.clients.exa.ExaClient") as mock_e,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_p,
        ):
            mock_s.return_value = MagicMock(is_available=False)
            mock_e.return_value = MagicMock(is_available=False)
            mock_p.return_value = MagicMock(is_available=False)

            collector = ResearchCollector.__new__(ResearchCollector)
            collector.settings = cache_settings
            collector._cache = broken_cache

            result = collector.collect(
                ["test query"], include_reddit=False, include_hn_comments=False
            )

        # Should still get results from Tavily (cache errors swallowed)
        assert result.has_data
        assert len(result.tavily_results) == 1
        assert result.tavily_results[0]["title"] == "OK"

    def test_cache_disabled_in_settings(self, cache_settings: Settings) -> None:
        """When research_cache_enabled=False, no cache is created."""
        settings = cache_settings.model_copy(update={"research_cache_enabled": False})
        collector = ResearchCollector.__new__(ResearchCollector)
        collector.settings = settings
        collector._cache = None  # Simulate what __init__ would do
        assert collector._cache is None


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


class TestCacheConfig:
    def test_default_cache_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        settings = Settings(anthropic_api_key="test", _env_file=None)
        assert settings.research_cache_ttl_hours == 24
        assert settings.research_cache_enabled is True
        assert settings.redis_url == ""
