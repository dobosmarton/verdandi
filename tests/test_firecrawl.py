"""Tests for Firecrawl client, provider, and integration.

Covers:
- FirecrawlClient scrape/map with respx HTTP mocks
- FirecrawlClient mock fallbacks when API key absent
- FirecrawlProvider page discovery, filtering, and collection
- URL prioritization and high-value path detection
- RawResearchData merge with firecrawl_pages
- ResearchSession dedup for Firecrawl pages
- format_research_context Firecrawl section
- _extract_competitor_urls helper
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from verdandi.clients.firecrawl import FirecrawlClient, FirecrawlPage
from verdandi.config import Settings
from verdandi.memory.working import ResearchSession
from verdandi.providers.firecrawl import (
    FirecrawlProvider,
    _is_high_value_url,
    _prioritize_urls,
)
from verdandi.research import (
    CollectionConfig,
    RawResearchData,
    _merge_results,
    format_research_context,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        firecrawl_api_key="fc-test",
        redis_url="",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
        _env_file=None,
    )


@pytest.fixture()
def config_with_urls() -> CollectionConfig:
    return CollectionConfig(
        queries=["test query"],
        primary_query="test query",
        competitor_urls=["https://competitor.com", "https://rival.io"],
    )


@pytest.fixture()
def config_no_urls() -> CollectionConfig:
    return CollectionConfig(
        queries=["test query"],
        primary_query="test query",
        competitor_urls=[],
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
        return fn()

    mock.side_effect = side_effect
    return mock


def _make_failing_cached_call() -> MagicMock:
    """Create a mock cached_call that always returns None (failure)."""
    mock = MagicMock()

    def side_effect(
        source: str,
        query: str,
        fn: Any,
        errors: list[str],
        *,
        label: str = "",
    ) -> None:
        errors.append(f"{label} failed for '{query}': mock error")
        return

    mock.side_effect = side_effect
    return mock


def _sample_page(url: str = "https://competitor.com/pricing") -> FirecrawlPage:
    return {
        "url": url,
        "title": "Pricing - Competitor",
        "description": "Our pricing plans",
        "markdown": "# Pricing\n\n- Free: $0\n- Pro: $29/mo\n- Enterprise: Custom",
        "status_code": 200,
        "word_count": 12,
    }


# ------------------------------------------------------------------
# FirecrawlClient tests
# ------------------------------------------------------------------


class TestFirecrawlClient:
    def test_is_available_with_key(self) -> None:
        assert FirecrawlClient(api_key="fc-test").is_available is True

    def test_not_available_without_key(self) -> None:
        assert FirecrawlClient(api_key="").is_available is False

    def test_mock_scrape_without_key(self) -> None:
        client = FirecrawlClient(api_key="")
        result = client.scrape("https://example.com")
        assert result["url"] == "https://example.com"
        assert "Mock" in result["title"]
        assert result["status_code"] == 200
        assert result["word_count"] > 0

    def test_mock_map_without_key(self) -> None:
        client = FirecrawlClient(api_key="")
        result = client.map_site("https://example.com")
        assert len(result) > 0
        assert any("pricing" in url for url in result)

    @respx.mock
    def test_scrape_success(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "markdown": "# Pricing\n\n$29/mo",
                        "metadata": {
                            "title": "Pricing Page",
                            "sourceURL": "https://comp.com/pricing",
                            "description": "Our plans",
                            "statusCode": 200,
                        },
                    },
                },
            )
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.scrape("https://comp.com/pricing")

        assert result["url"] == "https://comp.com/pricing"
        assert result["title"] == "Pricing Page"
        assert result["description"] == "Our plans"
        assert "Pricing" in result["markdown"]
        assert result["status_code"] == 200
        assert result["word_count"] > 0

    @respx.mock
    def test_scrape_falls_back_on_unsuccessful(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(200, json={"success": False})
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.scrape("https://fail.com")
        assert "Mock" in result["title"]

    @respx.mock
    def test_scrape_raises_on_http_error(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/scrape").mock(return_value=httpx.Response(500))
        client = FirecrawlClient(api_key="fc-test")
        with pytest.raises(httpx.HTTPStatusError):
            client.scrape("https://error.com")

    @respx.mock
    def test_scrape_uses_og_description_fallback(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "markdown": "Content",
                        "metadata": {
                            "title": "Page",
                            "sourceURL": "https://comp.com",
                            "description": "",
                            "ogDescription": "OG fallback desc",
                            "statusCode": 200,
                        },
                    },
                },
            )
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.scrape("https://comp.com")
        assert result["description"] == "OG fallback desc"

    @respx.mock
    def test_map_site_success_with_dict_links(self) -> None:
        """Real /v2/map returns objects with url/title/description."""
        respx.post("https://api.firecrawl.dev/v2/map").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "links": [
                        {
                            "url": "https://comp.com/pricing",
                            "title": "Pricing",
                            "description": "Plans",
                        },
                        {
                            "url": "https://comp.com/features",
                            "title": "Features",
                            "description": "",
                        },
                        {"url": "https://comp.com/about", "title": "About", "description": ""},
                    ],
                },
            )
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.map_site("https://comp.com", search="pricing features about")

        assert len(result) == 3
        assert "https://comp.com/pricing" in result
        # Ensure we got clean URL strings, not dict reprs
        for url in result:
            assert url.startswith("https://")

    @respx.mock
    def test_map_site_success_with_string_links(self) -> None:
        """Handle older API format that returns plain URL strings."""
        respx.post("https://api.firecrawl.dev/v2/map").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "links": [
                        "https://comp.com/pricing",
                        "https://comp.com/features",
                    ],
                },
            )
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.map_site("https://comp.com")

        assert len(result) == 2
        assert "https://comp.com/pricing" in result

    @respx.mock
    def test_map_site_sends_search_param(self) -> None:
        route = respx.post("https://api.firecrawl.dev/v2/map").mock(
            return_value=httpx.Response(200, json={"success": True, "links": []})
        )
        client = FirecrawlClient(api_key="fc-test")
        client.map_site("https://comp.com", search="pricing")

        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body["search"] == "pricing"

    @respx.mock
    def test_map_site_respects_limit(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/map").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "links": [
                        {
                            "url": f"https://comp.com/page-{i}",
                            "title": f"Page {i}",
                            "description": "",
                        }
                        for i in range(100)
                    ],
                },
            )
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.map_site("https://comp.com", limit=5)
        assert len(result) == 5

    @respx.mock
    def test_map_site_skips_empty_urls_in_dicts(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/map").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "links": [
                        {"url": "https://comp.com/pricing", "title": "Pricing", "description": ""},
                        {"url": "", "title": "Empty", "description": ""},
                        {"title": "No URL key", "description": ""},
                    ],
                },
            )
        )
        client = FirecrawlClient(api_key="fc-test")
        result = client.map_site("https://comp.com")
        assert len(result) == 1
        assert result[0] == "https://comp.com/pricing"

    @respx.mock
    def test_map_site_raises_on_http_error(self) -> None:
        respx.post("https://api.firecrawl.dev/v2/map").mock(return_value=httpx.Response(500))
        client = FirecrawlClient(api_key="fc-test")
        with pytest.raises(httpx.HTTPStatusError):
            client.map_site("https://error.com")


# ------------------------------------------------------------------
# URL filtering & prioritization tests
# ------------------------------------------------------------------


class TestURLFiltering:
    def test_high_value_pricing(self) -> None:
        assert _is_high_value_url("https://comp.com/pricing") is True

    def test_high_value_features(self) -> None:
        assert _is_high_value_url("https://comp.com/features") is True

    def test_high_value_nested_path(self) -> None:
        assert _is_high_value_url("https://comp.com/product/pricing") is True

    def test_not_high_value_blog(self) -> None:
        assert _is_high_value_url("https://comp.com/blog/some-post") is False

    def test_not_high_value_root(self) -> None:
        assert _is_high_value_url("https://comp.com/") is False

    def test_prioritize_high_value_first(self) -> None:
        urls = [
            "https://comp.com/blog/post",
            "https://comp.com/pricing",
            "https://comp.com/docs/api",
            "https://comp.com/about",
        ]
        result = _prioritize_urls(urls, 3)
        # High-value URLs come first, sorted by path length (shorter = higher)
        assert result[0] == "https://comp.com/about"
        assert result[1] == "https://comp.com/pricing"
        assert len(result) == 3
        # blog/post should be last (non-high-value) or excluded
        assert "https://comp.com/blog/post" not in result or result.index(
            "https://comp.com/blog/post"
        ) > result.index("https://comp.com/pricing")

    def test_prioritize_respects_max_count(self) -> None:
        urls = [f"https://comp.com/page-{i}" for i in range(10)]
        result = _prioritize_urls(urls, 2)
        assert len(result) == 2


# ------------------------------------------------------------------
# FirecrawlProvider tests
# ------------------------------------------------------------------


class TestFirecrawlProvider:
    def test_name_and_availability(self, settings: Settings) -> None:
        provider = FirecrawlProvider(settings)
        assert provider.name == "firecrawl"
        assert provider.is_available is True

    def test_unavailable_without_key(self) -> None:
        no_key = Settings(
            anthropic_api_key="test",
            firecrawl_api_key="",
            redis_url="",
            _env_file=None,
        )
        assert FirecrawlProvider(no_key).is_available is False

    def test_returns_empty_without_competitor_urls(
        self, settings: Settings, config_no_urls: CollectionConfig
    ) -> None:
        cached_call = MagicMock()
        result = FirecrawlProvider(settings).collect(config_no_urls, cached_call)

        assert result.has_data is False
        assert result.firecrawl_pages == []
        cached_call.assert_not_called()

    def test_maps_and_scrapes_competitor(
        self, settings: Settings, config_with_urls: CollectionConfig
    ) -> None:
        cached_call = _make_cached_call(
            {
                "firecrawl_map": [
                    "https://competitor.com/pricing",
                    "https://competitor.com/features",
                ],
                "firecrawl_scrape": _sample_page(),
            }
        )
        result = FirecrawlProvider(settings).collect(config_with_urls, cached_call)

        assert "firecrawl" in result.sources_used
        assert len(result.firecrawl_pages) > 0

    def test_scrapes_root_when_map_fails(
        self, settings: Settings, config_with_urls: CollectionConfig
    ) -> None:
        call_count = 0

        def side_effect(
            source: str,
            query: str,
            fn: Any,
            errors: list[str],
            *,
            label: str = "",
        ) -> Any:
            nonlocal call_count
            call_count += 1
            if source == "firecrawl_map":
                return None  # map failed
            if source == "firecrawl_scrape":
                return _sample_page(url=query)
            return fn()

        cached_call = MagicMock(side_effect=side_effect)
        result = FirecrawlProvider(settings).collect(config_with_urls, cached_call)

        # Should have scraped root URLs as fallback
        assert len(result.firecrawl_pages) > 0

    def test_collects_errors(self, settings: Settings, config_with_urls: CollectionConfig) -> None:
        cached_call = _make_failing_cached_call()
        result = FirecrawlProvider(settings).collect(config_with_urls, cached_call)

        assert len(result.errors) > 0
        assert result.firecrawl_pages == []


# ------------------------------------------------------------------
# RawResearchData integration tests
# ------------------------------------------------------------------


class TestRawResearchDataFirecrawl:
    def test_has_data_with_firecrawl_pages(self) -> None:
        raw = RawResearchData(firecrawl_pages=[_sample_page()])
        assert raw.has_data is True

    def test_merge_firecrawl_pages(self) -> None:
        a = RawResearchData(
            firecrawl_pages=[_sample_page("https://a.com/pricing")],
            sources_used=["firecrawl"],
        )
        b = RawResearchData(
            firecrawl_pages=[_sample_page("https://b.com/pricing")],
            sources_used=["firecrawl"],
        )
        merged = _merge_results([a, b])
        assert len(merged.firecrawl_pages) == 2

    def test_merge_preserves_other_fields(self) -> None:
        a = RawResearchData(
            tavily_results=[
                {
                    "title": "T",
                    "url": "https://t.co",
                    "content": "C",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources_used=["tavily"],
        )
        b = RawResearchData(
            firecrawl_pages=[_sample_page()],
            sources_used=["firecrawl"],
        )
        merged = _merge_results([a, b])
        assert len(merged.tavily_results) == 1
        assert len(merged.firecrawl_pages) == 1


# ------------------------------------------------------------------
# ResearchSession dedup tests
# ------------------------------------------------------------------


class TestResearchSessionFirecrawl:
    def test_ingest_firecrawl_pages(self) -> None:
        session = ResearchSession("Test Idea", "saas")
        raw = RawResearchData(
            firecrawl_pages=[_sample_page()],
            sources_used=["firecrawl"],
        )
        session.ingest(raw)
        result = session.to_raw()
        assert len(result.firecrawl_pages) == 1

    def test_dedup_firecrawl_by_url(self) -> None:
        session = ResearchSession("Test Idea", "saas")
        page = _sample_page("https://comp.com/pricing")
        raw1 = RawResearchData(firecrawl_pages=[page], sources_used=["firecrawl"])
        raw2 = RawResearchData(firecrawl_pages=[page], sources_used=["firecrawl"])

        session.ingest(raw1)
        session.ingest(raw2)

        result = session.to_raw()
        assert len(result.firecrawl_pages) == 1

    def test_firecrawl_counted_in_total_results(self) -> None:
        session = ResearchSession("Test Idea", "saas")
        raw = RawResearchData(
            firecrawl_pages=[
                _sample_page("https://a.com/pricing"),
                _sample_page("https://b.com/pricing"),
            ],
            sources_used=["firecrawl"],
        )
        session.ingest(raw)
        assert session.total_results == 2

    def test_firecrawl_in_has_data(self) -> None:
        session = ResearchSession("Test Idea", "saas")
        raw = RawResearchData(firecrawl_pages=[_sample_page()])
        session.ingest(raw)
        assert session.has_data is True

    def test_ingest_with_delta_detects_new_pages(self) -> None:
        session = ResearchSession("Test Idea", "saas")
        raw1 = RawResearchData(
            firecrawl_pages=[_sample_page("https://a.com/pricing")],
        )
        raw2 = RawResearchData(
            firecrawl_pages=[_sample_page("https://b.com/pricing")],
        )
        session.ingest(raw1)
        delta = session.ingest_with_delta(raw2)
        assert delta == 1

    def test_ingest_with_delta_zero_for_duplicates(self) -> None:
        session = ResearchSession("Test Idea", "saas")
        page = _sample_page("https://a.com/pricing")
        raw = RawResearchData(firecrawl_pages=[page])
        session.ingest(raw)
        delta = session.ingest_with_delta(RawResearchData(firecrawl_pages=[page]))
        assert delta == 0


# ------------------------------------------------------------------
# format_research_context tests
# ------------------------------------------------------------------


class TestFormatContextFirecrawl:
    def test_formats_firecrawl_section(self) -> None:
        raw = RawResearchData(
            firecrawl_pages=[_sample_page()],
            sources_used=["firecrawl"],
        )
        text = format_research_context(raw)
        assert "## Competitor Deep Dive (Firecrawl)" in text
        assert "Pricing - Competitor" in text
        assert "https://competitor.com/pricing" in text
        assert "Pro: $29/mo" in text

    def test_truncates_long_markdown(self) -> None:
        page: FirecrawlPage = {
            "url": "https://comp.com",
            "title": "Comp",
            "description": "",
            "markdown": "x " * 2000,  # 4000 chars
            "status_code": 200,
            "word_count": 2000,
        }
        raw = RawResearchData(
            firecrawl_pages=[page],
            sources_used=["firecrawl"],
        )
        text = format_research_context(raw)
        assert "[... truncated]" in text


# ------------------------------------------------------------------
# _extract_competitor_urls tests
# ------------------------------------------------------------------


class TestExtractCompetitorUrls:
    def test_extracts_from_tavily(self) -> None:
        from verdandi.agents.research import _extract_competitor_urls

        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Competitor",
                    "url": "https://competitor.com/blog/post",
                    "content": "C",
                    "score": 0.9,
                    "published_date": "",
                },
            ],
        )
        urls = _extract_competitor_urls(raw)
        assert "https://competitor.com" in urls

    def test_extracts_from_serper(self) -> None:
        from verdandi.agents.research import _extract_competitor_urls

        raw = RawResearchData(
            serper_results=[
                {
                    "title": "Rival",
                    "link": "https://rival.io/features",
                    "snippet": "S",
                    "position": 1,
                },
            ],
        )
        urls = _extract_competitor_urls(raw)
        assert "https://rival.io" in urls

    def test_skips_social_domains(self) -> None:
        from verdandi.agents.research import _extract_competitor_urls

        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Reddit Thread",
                    "url": "https://www.reddit.com/r/SaaS/post/123",
                    "content": "C",
                    "score": 0.8,
                    "published_date": "",
                },
                {
                    "title": "HN Discussion",
                    "url": "https://news.ycombinator.com/item?id=123",
                    "content": "C",
                    "score": 0.7,
                    "published_date": "",
                },
                {
                    "title": "GitHub Repo",
                    "url": "https://github.com/org/repo",
                    "content": "C",
                    "score": 0.6,
                    "published_date": "",
                },
            ],
        )
        urls = _extract_competitor_urls(raw)
        assert len(urls) == 0

    def test_deduplicates_domains(self) -> None:
        from verdandi.agents.research import _extract_competitor_urls

        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Page 1",
                    "url": "https://comp.com/pricing",
                    "content": "C",
                    "score": 0.9,
                    "published_date": "",
                },
                {
                    "title": "Page 2",
                    "url": "https://comp.com/features",
                    "content": "C",
                    "score": 0.8,
                    "published_date": "",
                },
            ],
        )
        urls = _extract_competitor_urls(raw)
        assert len(urls) == 1

    def test_returns_empty_for_empty_data(self) -> None:
        from verdandi.agents.research import _extract_competitor_urls

        urls = _extract_competitor_urls(RawResearchData())
        assert urls == []

    def test_strips_www_prefix(self) -> None:
        from verdandi.agents.research import _extract_competitor_urls

        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "With WWW",
                    "url": "https://www.comp.com/pricing",
                    "content": "C",
                    "score": 0.9,
                    "published_date": "",
                },
                {
                    "title": "Without WWW",
                    "url": "https://comp.com/features",
                    "content": "C",
                    "score": 0.8,
                    "published_date": "",
                },
            ],
        )
        urls = _extract_competitor_urls(raw)
        # Should deduplicate www vs non-www
        assert len(urls) == 1
