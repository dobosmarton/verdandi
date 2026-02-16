"""Tests for the ResearchCollector and format_research_context.

Verifies:
- Collector aggregates results from multiple providers
- Graceful degradation when individual providers fail
- RuntimeError when ALL providers fail
- _merge_results produces correct merged data
- format_research_context produces valid markdown
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from verdandi.config import Settings
from verdandi.research import (
    CollectionConfig,
    RawResearchData,
    ResearchCollector,
    _merge_results,
    format_research_context,
)


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        tavily_api_key="tvly-test",
        serper_api_key="serper-test",
        exa_api_key="exa-test",
        perplexity_api_key="pplx-test",
        redis_url="",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
        _env_file=None,
    )


def _mock_provider(
    name: str,
    *,
    available: bool = True,
    result: RawResearchData | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock provider satisfying ResearchProviderPort."""
    mock = MagicMock()
    mock.name = name
    mock.is_available = available
    if side_effect is not None:
        mock.collect.side_effect = side_effect
    else:
        mock.collect.return_value = result or RawResearchData()
    return mock


class TestRawResearchData:
    def test_has_data_empty(self) -> None:
        raw = RawResearchData()
        assert raw.has_data is False

    def test_has_data_with_tavily(self) -> None:
        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Test",
                    "url": "https://t.co",
                    "content": "Test",
                    "score": 0.9,
                    "published_date": "",
                }
            ]
        )
        assert raw.has_data is True

    def test_has_data_with_hn_comments(self) -> None:
        raw = RawResearchData(
            hn_comments=[
                {
                    "comment_text": "Test",
                    "author": "user",
                    "story_title": "Story",
                    "story_url": None,
                    "points": 10,
                    "created_at": "",
                    "objectID": "1",
                }
            ]
        )
        assert raw.has_data is True

    def test_has_data_with_serper_twitter(self) -> None:
        raw = RawResearchData(
            serper_twitter=[
                {
                    "title": "Test tweet",
                    "link": "https://x.com/u/status/1",
                    "snippet": "Content",
                    "author": "u",
                    "position": 1,
                }
            ]
        )
        assert raw.has_data is True

    def test_has_data_with_twitter_results(self) -> None:
        raw = RawResearchData(
            twitter_results=[
                {
                    "tweet_id": "1",
                    "text": "Test",
                    "author_username": "u",
                    "author_name": "U",
                    "author_followers": 100,
                    "created_at": "",
                    "favorite_count": 10,
                    "retweet_count": 5,
                    "reply_count": 3,
                    "views_count": 500,
                    "url": "https://x.com/u/status/1",
                }
            ]
        )
        assert raw.has_data is True


class TestMergeResults:
    def test_merges_list_fields(self) -> None:
        a = RawResearchData(
            tavily_results=[
                {
                    "title": "A",
                    "url": "https://a.com",
                    "content": "C",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources_used=["tavily"],
        )
        b = RawResearchData(
            hn_stories=[
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
            sources_used=["hn_algolia"],
        )
        merged = _merge_results([a, b])
        assert len(merged.tavily_results) == 1
        assert len(merged.hn_stories) == 1
        assert merged.sources_used == ["tavily", "hn_algolia"]

    def test_merges_optional_fields_first_wins(self) -> None:
        a = RawResearchData(
            perplexity_answer={
                "answer": "First",
                "citations": [],
                "model": "sonar",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )
        b = RawResearchData(
            perplexity_answer={
                "answer": "Second",
                "citations": [],
                "model": "sonar",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )
        merged = _merge_results([a, b])
        assert merged.perplexity_answer is not None
        assert merged.perplexity_answer["answer"] == "First"

    def test_merges_errors(self) -> None:
        a = RawResearchData(errors=["error 1"])
        b = RawResearchData(errors=["error 2", "error 3"])
        merged = _merge_results([a, b])
        assert merged.errors == ["error 1", "error 2", "error 3"]

    def test_empty_partials(self) -> None:
        merged = _merge_results([])
        assert merged.has_data is False
        assert merged.sources_used == []


class TestResearchCollector:
    def test_collects_from_available_providers(self, settings: Settings) -> None:
        tavily_provider = _mock_provider(
            "tavily",
            result=RawResearchData(
                tavily_results=[
                    {
                        "title": "Result",
                        "url": "https://r.com",
                        "content": "Content",
                        "score": 0.9,
                        "published_date": "",
                    }
                ],
                sources_used=["tavily"],
            ),
        )
        hn_provider = _mock_provider(
            "hn_algolia",
            result=RawResearchData(
                hn_stories=[
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
                sources_used=["hn_algolia"],
            ),
        )

        collector = ResearchCollector(settings, providers=[tavily_provider, hn_provider])
        result = collector.collect(["test query"], include_hn_comments=False)

        assert result.has_data
        assert "tavily" in result.sources_used
        assert "hn_algolia" in result.sources_used
        assert len(result.tavily_results) == 1
        assert len(result.hn_stories) == 1

    def test_skips_unavailable_providers(self, settings: Settings) -> None:
        available = _mock_provider(
            "tavily",
            result=RawResearchData(
                tavily_results=[
                    {
                        "title": "R",
                        "url": "https://r.com",
                        "content": "C",
                        "score": 0.9,
                        "published_date": "",
                    }
                ],
                sources_used=["tavily"],
            ),
        )
        unavailable = _mock_provider("serper", available=False)

        collector = ResearchCollector(settings, providers=[available, unavailable])
        result = collector.collect(["test query"])

        assert result.has_data
        assert "tavily" in result.sources_used
        unavailable.collect.assert_not_called()

    def test_graceful_degradation_on_failure(self, settings: Settings) -> None:
        """When one provider raises, collector continues with others."""
        failing = _mock_provider("tavily", side_effect=RuntimeError("API down"))
        succeeding = _mock_provider(
            "hn_algolia",
            result=RawResearchData(
                hn_stories=[
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
                sources_used=["hn_algolia"],
            ),
        )

        collector = ResearchCollector(settings, providers=[failing, succeeding])
        result = collector.collect(["test query"], include_hn_comments=False)

        assert result.has_data
        assert "hn_algolia" in result.sources_used

    def test_raises_when_all_providers_fail(self, settings: Settings) -> None:
        """When every provider returns empty data, RuntimeError is raised."""
        empty_providers = [
            _mock_provider("tavily", result=RawResearchData(errors=["Tavily down"])),
            _mock_provider("serper", result=RawResearchData(errors=["Serper down"])),
            _mock_provider("hn_algolia", result=RawResearchData(errors=["HN down"])),
        ]

        collector = ResearchCollector(settings, providers=empty_providers)
        with pytest.raises(RuntimeError, match="All research sources failed"):
            collector.collect(["test"])

    def test_passes_collection_config_to_providers(self, settings: Settings) -> None:
        """Providers receive a CollectionConfig with correct parameters."""
        provider = _mock_provider(
            "tavily",
            result=RawResearchData(
                tavily_results=[
                    {
                        "title": "R",
                        "url": "https://r.com",
                        "content": "C",
                        "score": 0.9,
                        "published_date": "",
                    }
                ],
                sources_used=["tavily"],
            ),
        )

        collector = ResearchCollector(settings, providers=[provider])
        collector.collect(
            ["q1", "q2"],
            include_reddit=False,
            perplexity_question="What is the TAM?",
        )

        config: CollectionConfig = provider.collect.call_args[0][0]
        assert config.queries == ["q1", "q2"]
        assert config.primary_query == "q1"
        assert config.include_reddit is False
        assert config.perplexity_question == "What is the TAM?"


class TestFormatResearchContext:
    def test_formats_tavily_results(self) -> None:
        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Test Article",
                    "url": "https://test.com/article",
                    "content": "Article content about market trends",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources_used=["tavily"],
        )
        text = format_research_context(raw)

        assert "## Web Search Results (Tavily)" in text
        assert "Test Article" in text
        assert "https://test.com/article" in text
        assert "Article content" in text

    def test_formats_hn_comments(self) -> None:
        raw = RawResearchData(
            hn_comments=[
                {
                    "comment_text": "This tool changed my workflow",
                    "author": "dev_user",
                    "story_title": "Best Dev Tools",
                    "story_url": "https://hn.com/story",
                    "points": 30,
                    "created_at": "",
                    "objectID": "1",
                }
            ],
            sources_used=["hn_algolia"],
        )
        text = format_research_context(raw)

        assert "## Developer Pain Points" in text
        assert "dev_user" in text
        assert "This tool changed my workflow" in text

    def test_includes_sources_summary(self) -> None:
        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "T",
                    "url": "https://t.co",
                    "content": "C",
                    "score": 0.5,
                    "published_date": "",
                }
            ],
            sources_used=["tavily", "hn_algolia"],
            errors=["Serper failed: 500"],
        )
        text = format_research_context(raw)

        assert "**Sources used**: tavily, hn_algolia" in text
        assert "**Errors encountered**: 1" in text
        assert "Serper failed" in text

    def test_formats_serper_twitter(self) -> None:
        raw = RawResearchData(
            serper_twitter=[
                {
                    "title": "@dev: Tools are broken",
                    "link": "https://x.com/dev/status/1",
                    "snippet": "Everything is overpriced",
                    "author": "dev",
                    "position": 1,
                }
            ],
            sources_used=["serper"],
        )
        text = format_research_context(raw)

        assert "## Twitter/X Discussions" in text
        assert "@dev" in text
        assert "Everything is overpriced" in text

    def test_formats_socialdata_twitter(self) -> None:
        raw = RawResearchData(
            twitter_results=[
                {
                    "tweet_id": "1",
                    "text": "This market is broken",
                    "author_username": "founder",
                    "author_name": "F",
                    "author_followers": 5000,
                    "created_at": "",
                    "favorite_count": 100,
                    "retweet_count": 30,
                    "reply_count": 20,
                    "views_count": 15000,
                    "url": "https://x.com/founder/status/1",
                }
            ],
            sources_used=["socialdata"],
        )
        text = format_research_context(raw)

        assert "## Twitter/X Insights (SocialData)" in text
        assert "@founder" in text
        assert "5,000 followers" in text
        assert "100 likes" in text
        assert "15,000 views" in text

    def test_empty_data_produces_minimal_output(self) -> None:
        raw = RawResearchData(sources_used=[], errors=[])
        text = format_research_context(raw)
        # Should at least have the sources summary
        assert "**Sources used**:" in text
