"""Tests for individual research providers.

Each provider is tested in isolation with a mock ``cached_call`` callback.
This verifies that providers correctly:
- Report their name and availability
- Call the right client methods via cached_call
- Return properly structured RawResearchData
- Handle optional config parameters (e.g. exa_similar_url)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from verdandi.config import Settings
from verdandi.providers.exa import ExaProvider
from verdandi.providers.hn import HNProvider
from verdandi.providers.perplexity import PerplexityProvider
from verdandi.providers.serper import SerperProvider
from verdandi.providers.socialdata import SocialDataProvider
from verdandi.providers.tavily import TavilyProvider
from verdandi.research import CollectionConfig


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        tavily_api_key="tvly-test",
        serper_api_key="serper-test",
        exa_api_key="exa-test",
        perplexity_api_key="pplx-test",
        socialdata_api_key="sd-test",
        redis_url="",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
        _env_file=None,
    )


@pytest.fixture()
def config() -> CollectionConfig:
    return CollectionConfig(
        queries=["test query", "query 2", "query 3"],
        primary_query="test query",
        include_reddit=True,
        include_hn_comments=True,
        perplexity_question="What is the TAM?",
        exa_similar_url="https://competitor.com",
        tavily_research_query="market analysis for test",
        use_perplexity_deep=False,
    )


def _make_cached_call(return_values: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock cached_call that returns values based on source key."""
    mock = MagicMock()

    def side_effect(
        source: str,
        query: str,
        fn: Any,
        errors: list[str],
        *,
        label: str = "",
    ) -> Any:
        if return_values and source in return_values:
            return return_values[source]
        # Default: call the actual function
        return fn()

    mock.side_effect = side_effect
    return mock


class TestTavilyProvider:
    def test_name_and_availability(self, settings: Settings) -> None:
        provider = TavilyProvider(settings)
        assert provider.name == "tavily"
        assert provider.is_available is True

    def test_unavailable_without_key(self) -> None:
        settings = Settings(
            anthropic_api_key="test",
            tavily_api_key="",
            redis_url="",
            _env_file=None,
        )
        assert TavilyProvider(settings).is_available is False

    def test_collects_search_results(self, settings: Settings, config: CollectionConfig) -> None:
        cached_call = _make_cached_call(
            {
                "tavily": [
                    {
                        "title": "R",
                        "url": "https://r.com",
                        "content": "C",
                        "score": 0.9,
                        "published_date": "",
                    }
                ],
            }
        )
        result = TavilyProvider(settings).collect(config, cached_call)

        assert "tavily" in result.sources_used
        assert len(result.tavily_results) >= 1

    def test_collects_research_when_configured(
        self, settings: Settings, config: CollectionConfig
    ) -> None:
        cached_call = _make_cached_call(
            {
                "tavily": [],
                "tavily_research": {
                    "summary": "Market overview",
                    "sources": [],
                    "follow_up_questions": [],
                },
            }
        )
        result = TavilyProvider(settings).collect(config, cached_call)

        assert result.tavily_research is not None
        assert result.tavily_research["summary"] == "Market overview"


class TestSerperProvider:
    def test_name_and_availability(self, settings: Settings) -> None:
        provider = SerperProvider(settings)
        assert provider.name == "serper"
        assert provider.is_available is True

    def test_collects_search_and_reddit(self, settings: Settings, config: CollectionConfig) -> None:
        cached_call = _make_cached_call(
            {
                "serper": [
                    {"title": "SERP", "link": "https://s.com", "snippet": "S", "position": 1}
                ],
                "serper_reddit": [
                    {
                        "title": "Reddit",
                        "link": "https://reddit.com/r/test",
                        "snippet": "R",
                        "subreddit": "test",
                        "position": 1,
                    }
                ],
            }
        )
        result = SerperProvider(settings).collect(config, cached_call)

        assert "serper" in result.sources_used
        assert len(result.serper_results) >= 1
        assert len(result.serper_reddit) == 1

    def test_collects_twitter_results(self, settings: Settings, config: CollectionConfig) -> None:
        cached_call = _make_cached_call(
            {
                "serper": [
                    {"title": "SERP", "link": "https://s.com", "snippet": "S", "position": 1}
                ],
                "serper_twitter_x": [
                    {
                        "title": "@dev: Tools are broken",
                        "link": "https://x.com/dev/status/1",
                        "snippet": "Everything is overpriced",
                        "author": "dev",
                        "position": 1,
                    }
                ],
            }
        )
        result = SerperProvider(settings).collect(config, cached_call)

        assert "serper" in result.sources_used
        assert len(result.serper_twitter) == 1
        assert result.serper_twitter[0]["author"] == "dev"

    def test_skips_twitter_when_disabled(self, settings: Settings) -> None:
        no_twitter = CollectionConfig(
            queries=["q"],
            primary_query="q",
            include_twitter=False,
        )
        cached_call = _make_cached_call(
            {
                "serper": [
                    {"title": "SERP", "link": "https://s.com", "snippet": "S", "position": 1}
                ],
            }
        )
        result = SerperProvider(settings).collect(no_twitter, cached_call)

        assert len(result.serper_twitter) == 0

    def test_skips_reddit_when_disabled(self, settings: Settings) -> None:
        config = CollectionConfig(
            queries=["q"],
            primary_query="q",
            include_reddit=False,
        )
        cached_call = _make_cached_call(
            {
                "serper": [
                    {"title": "SERP", "link": "https://s.com", "snippet": "S", "position": 1}
                ],
            }
        )
        result = SerperProvider(settings).collect(config, cached_call)

        assert len(result.serper_reddit) == 0


class TestExaProvider:
    def test_name_and_availability(self, settings: Settings) -> None:
        provider = ExaProvider(settings)
        assert provider.name == "exa"
        assert provider.is_available is True

    def test_collects_search_and_similar(
        self, settings: Settings, config: CollectionConfig
    ) -> None:
        cached_call = _make_cached_call(
            {
                "exa": [
                    {
                        "title": "E",
                        "url": "https://e.com",
                        "text": "T",
                        "score": 0.9,
                        "published_date": "",
                        "author": None,
                    }
                ],
                "exa_similar": [{"title": "S", "url": "https://s.com", "text": "T", "score": 0.8}],
            }
        )
        result = ExaProvider(settings).collect(config, cached_call)

        assert "exa" in result.sources_used
        # 1 from search + 1 from find_similar (converted to ExaSearchResult)
        assert len(result.exa_results) == 2


class TestPerplexityProvider:
    def test_name_and_availability(self, settings: Settings) -> None:
        provider = PerplexityProvider(settings)
        assert provider.name == "perplexity"
        assert provider.is_available is True

    def test_collects_basic_query(self, settings: Settings, config: CollectionConfig) -> None:
        cached_call = _make_cached_call(
            {
                "perplexity": {
                    "answer": "Market is growing",
                    "citations": ["https://c.com"],
                    "model": "sonar",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60},
                },
            }
        )
        result = PerplexityProvider(settings).collect(config, cached_call)

        assert "perplexity" in result.sources_used
        assert result.perplexity_answer is not None
        assert result.perplexity_deep_answer is None

    def test_collects_deep_research(self, settings: Settings) -> None:
        deep_config = CollectionConfig(
            queries=["q"],
            primary_query="q",
            perplexity_question="Deep question",
            use_perplexity_deep=True,
        )
        cached_call = _make_cached_call(
            {
                "perplexity": {
                    "answer": "Deep analysis",
                    "citations": ["https://c.com"],
                    "sources_analyzed": 15,
                    "model": "sonar-deep-research",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 500, "total_tokens": 510},
                },
            }
        )
        result = PerplexityProvider(settings).collect(deep_config, cached_call)

        assert result.perplexity_answer is not None
        assert result.perplexity_deep_answer is not None

    def test_returns_empty_without_question(self, settings: Settings) -> None:
        config = CollectionConfig(queries=["q"], primary_query="q", perplexity_question="")
        cached_call = MagicMock()
        result = PerplexityProvider(settings).collect(config, cached_call)

        assert result.has_data is False
        cached_call.assert_not_called()


class TestHNProvider:
    def test_name_and_always_available(self) -> None:
        provider = HNProvider()
        assert provider.name == "hn_algolia"
        assert provider.is_available is True

    def test_collects_stories_and_comments(self, config: CollectionConfig) -> None:
        cached_call = _make_cached_call(
            {
                "hn_stories": [
                    {
                        "title": "HN Story",
                        "url": "https://hn.com",
                        "author": "user",
                        "points": 100,
                        "num_comments": 50,
                        "created_at": "",
                        "objectID": "1",
                        "tags": "story",
                    }
                ],
                "hn_comments": [
                    {
                        "comment_text": "Great insight",
                        "author": "dev",
                        "story_title": "Story",
                        "story_url": None,
                        "points": 10,
                        "created_at": "",
                        "objectID": "2",
                    }
                ],
            }
        )
        result = HNProvider().collect(config, cached_call)

        assert "hn_algolia" in result.sources_used
        assert len(result.hn_stories) == 1
        assert len(result.hn_comments) == 1

    def test_skips_comments_when_disabled(self) -> None:
        config = CollectionConfig(
            queries=["q"],
            primary_query="q",
            include_hn_comments=False,
        )
        cached_call = _make_cached_call(
            {
                "hn_stories": [
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
                ],
            }
        )
        result = HNProvider().collect(config, cached_call)

        assert len(result.hn_stories) == 1
        assert len(result.hn_comments) == 0

    def test_returns_empty_without_query(self) -> None:
        config = CollectionConfig(queries=[], primary_query="")
        cached_call = MagicMock()
        result = HNProvider().collect(config, cached_call)

        assert result.has_data is False
        cached_call.assert_not_called()


class TestSocialDataProvider:
    def test_name_and_availability(self, settings: Settings) -> None:
        provider = SocialDataProvider(settings)
        assert provider.name == "socialdata"
        assert provider.is_available is True

    def test_unavailable_without_key(self) -> None:
        no_key = Settings(
            anthropic_api_key="test",
            socialdata_api_key="",
            redis_url="",
            _env_file=None,
        )
        assert SocialDataProvider(no_key).is_available is False

    def test_collects_tweets(self, settings: Settings, config: CollectionConfig) -> None:
        cached_call = _make_cached_call(
            {
                "socialdata": [
                    {
                        "tweet_id": "123",
                        "text": "Pain point tweet",
                        "author_username": "dev",
                        "author_name": "Dev",
                        "author_followers": 500,
                        "created_at": "",
                        "favorite_count": 42,
                        "retweet_count": 10,
                        "reply_count": 5,
                        "views_count": 3000,
                        "url": "https://x.com/dev/status/123",
                    }
                ],
            }
        )
        result = SocialDataProvider(settings).collect(config, cached_call)

        assert "socialdata" in result.sources_used
        assert len(result.twitter_results) == 1
        assert result.twitter_results[0]["tweet_id"] == "123"

    def test_skips_when_twitter_disabled(self, settings: Settings) -> None:
        no_twitter_config = CollectionConfig(
            queries=["q"],
            primary_query="q",
            include_twitter=False,
        )
        cached_call = MagicMock()
        result = SocialDataProvider(settings).collect(no_twitter_config, cached_call)

        assert result.has_data is False
        cached_call.assert_not_called()

    def test_returns_empty_without_query(self, settings: Settings) -> None:
        empty_config = CollectionConfig(queries=[], primary_query="")
        cached_call = MagicMock()
        result = SocialDataProvider(settings).collect(empty_config, cached_call)

        assert result.has_data is False
        cached_call.assert_not_called()


class TestDefaultProviders:
    def test_creates_all_six_providers(self, settings: Settings) -> None:
        from verdandi.providers import default_providers

        providers = default_providers(settings)
        assert len(providers) == 6
        names = [p.name for p in providers]
        assert "tavily" in names
        assert "serper" in names
        assert "exa" in names
        assert "perplexity" in names
        assert "socialdata" in names
        assert "hn_algolia" in names
