"""Tests for the ResearchCollector and format_research_context.

Verifies:
- Collector aggregates results from multiple sources
- Graceful degradation when individual sources fail
- RuntimeError when ALL sources fail
- format_research_context produces valid markdown
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from verdandi.config import Settings
from verdandi.research import RawResearchData, ResearchCollector, format_research_context


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        tavily_api_key="tvly-test",
        serper_api_key="serper-test",
        exa_api_key="exa-test",
        perplexity_api_key="pplx-test",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
    )


@pytest.fixture()
def settings_no_keys() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
    )


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


class TestResearchCollector:
    @patch("verdandi.clients.hn_algolia.HNClient")
    @patch("verdandi.clients.tavily.TavilyClient")
    def test_collects_from_available_sources(
        self,
        mock_tavily_cls: MagicMock,
        mock_hn_cls: MagicMock,
        settings: Settings,
    ) -> None:
        # Mock Tavily
        mock_tavily = MagicMock()
        mock_tavily.is_available = True
        mock_tavily.search.return_value = [
            {
                "title": "Result",
                "url": "https://r.com",
                "content": "Content",
                "score": 0.9,
                "published_date": "",
            }
        ]
        mock_tavily_cls.return_value = mock_tavily

        # Mock HN (always available)
        mock_hn = MagicMock()
        mock_hn.search.return_value = [
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
        ]
        mock_hn.search_comments.return_value = []
        mock_hn_cls.return_value = mock_hn

        # Mock Serper, Exa, Perplexity as unavailable
        with (
            patch("verdandi.clients.serper.SerperClient") as mock_serper_cls,
            patch("verdandi.clients.exa.ExaClient") as mock_exa_cls,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_pplx_cls,
        ):
            mock_serper_cls.return_value = MagicMock(is_available=False)
            mock_exa_cls.return_value = MagicMock(is_available=False)
            mock_pplx_cls.return_value = MagicMock(is_available=False)

            collector = ResearchCollector(settings)
            result = collector.collect(
                ["test query"],
                include_reddit=False,
                include_hn_comments=False,
            )

        assert result.has_data
        assert "tavily" in result.sources_used
        assert "hn_algolia" in result.sources_used
        assert len(result.tavily_results) == 1
        assert len(result.hn_stories) == 1

    @patch("verdandi.clients.hn_algolia.HNClient")
    def test_graceful_degradation_on_failure(
        self,
        mock_hn_cls: MagicMock,
        settings: Settings,
    ) -> None:
        """When Tavily raises, collector continues with other sources."""
        # HN succeeds
        mock_hn = MagicMock()
        mock_hn.search.return_value = [
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
        mock_hn.search_comments.return_value = []
        mock_hn_cls.return_value = mock_hn

        with (
            patch("verdandi.clients.tavily.TavilyClient") as mock_tavily_cls,
            patch("verdandi.clients.serper.SerperClient") as mock_serper_cls,
            patch("verdandi.clients.exa.ExaClient") as mock_exa_cls,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_pplx_cls,
        ):
            # Tavily: available but raises
            mock_tavily = MagicMock()
            mock_tavily.is_available = True
            mock_tavily.search.side_effect = RuntimeError("API down")
            mock_tavily_cls.return_value = mock_tavily

            mock_serper_cls.return_value = MagicMock(is_available=False)
            mock_exa_cls.return_value = MagicMock(is_available=False)
            mock_pplx_cls.return_value = MagicMock(is_available=False)

            collector = ResearchCollector(settings)
            result = collector.collect(["test query"], include_hn_comments=False)

        assert result.has_data
        assert "hn_algolia" in result.sources_used
        assert len(result.errors) > 0
        assert "Tavily" in result.errors[0]

    def test_raises_when_all_sources_fail(self, settings: Settings) -> None:
        """When every source fails, RuntimeError is raised."""
        with (
            patch("verdandi.clients.tavily.TavilyClient") as mock_tavily_cls,
            patch("verdandi.clients.serper.SerperClient") as mock_serper_cls,
            patch("verdandi.clients.exa.ExaClient") as mock_exa_cls,
            patch("verdandi.clients.perplexity.PerplexityClient") as mock_pplx_cls,
            patch("verdandi.clients.hn_algolia.HNClient") as mock_hn_cls,
        ):
            for cls in [mock_tavily_cls, mock_serper_cls, mock_exa_cls]:
                mock = MagicMock()
                mock.is_available = True
                mock.search.side_effect = RuntimeError("down")
                cls.return_value = mock

            mock_serper_cls.return_value.search_reddit = MagicMock(side_effect=RuntimeError("down"))
            mock_pplx_cls.return_value = MagicMock(is_available=False)

            mock_hn = MagicMock()
            mock_hn.search.side_effect = RuntimeError("HN down")
            mock_hn.search_comments.side_effect = RuntimeError("HN down")
            mock_hn_cls.return_value = mock_hn

            collector = ResearchCollector(settings)
            with pytest.raises(RuntimeError, match="All research sources failed"):
                collector.collect(["test"])


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

    def test_empty_data_produces_minimal_output(self) -> None:
        raw = RawResearchData(sources_used=[], errors=[])
        text = format_research_context(raw)
        # Should at least have the sources summary
        assert "**Sources used**:" in text
