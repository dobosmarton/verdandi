"""Tests for research API clients.

Uses respx to mock httpx transport-layer calls, verifying:
- Real response parsing from JSON fixtures
- Graceful degradation on HTTP 500
- Mock fallback when API key is missing
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from verdandi.clients.exa import ExaClient
from verdandi.clients.hn_algolia import HNClient
from verdandi.clients.perplexity import PerplexityClient
from verdandi.clients.serper import SerperClient, _extract_subreddit
from verdandi.clients.tavily import TavilyClient

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[return-value]


# =====================================================================
# Tavily
# =====================================================================


class TestTavilyClient:
    def test_mock_fallback_no_api_key(self) -> None:
        """Client without API key returns mock data."""
        client = TavilyClient(api_key="")
        results = client.search("test query")
        assert len(results) > 0
        assert results[0]["title"].startswith("Mock result")

    @respx.mock
    def test_search_parses_response(self) -> None:
        """Client correctly parses a real Tavily API response."""
        fixture = _load_fixture("tavily_search.json")
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = TavilyClient(api_key="tvly-test-key")
        results = client.search("trending micro-SaaS ideas", max_results=5)

        assert len(results) == 3
        assert results[0]["title"] == "50 Micro-SaaS Ideas for 2025"
        assert results[0]["url"] == "https://example.com/micro-saas-ideas"
        assert results[0]["score"] == 0.95
        assert "micro-SaaS" in results[0]["content"]

    @respx.mock
    def test_search_falls_back_on_500(self) -> None:
        """Client falls back to mock data on HTTP 500."""
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        client = TavilyClient(api_key="tvly-test-key")
        results = client.search("test query")
        assert len(results) > 0
        assert results[0]["title"].startswith("Mock result")

    @respx.mock
    def test_research_parses_response(self) -> None:
        """Client correctly parses a research endpoint response."""
        fixture = {
            "summary": "Market analysis shows strong demand.",
            "sources": [{"title": "Report A", "url": "https://a.com", "relevance": 0.9}],
            "follow_up_questions": ["What is the TAM?"],
        }
        respx.post("https://api.tavily.com/research").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = TavilyClient(api_key="tvly-test-key")
        result = client.research("market analysis")

        assert "strong demand" in result["summary"]
        assert len(result["sources"]) == 1
        assert result["sources"][0]["title"] == "Report A"

    def test_is_available(self) -> None:
        assert TavilyClient(api_key="key").is_available is True
        assert TavilyClient(api_key="").is_available is False


# =====================================================================
# Serper
# =====================================================================


class TestSerperClient:
    def test_mock_fallback_no_api_key(self) -> None:
        client = SerperClient(api_key="")
        results = client.search("test query")
        assert len(results) > 0
        assert results[0]["title"].startswith("Mock SERP")

    @respx.mock
    def test_search_parses_response(self) -> None:
        fixture = _load_fixture("serper_search.json")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = SerperClient(api_key="serper-test-key")
        results = client.search("developer tools", num=10)

        assert len(results) == 2
        assert results[0]["title"] == "Best Developer Tools 2025 - TechCrunch"
        assert results[0]["link"] == "https://techcrunch.com/developer-tools-2025"
        assert results[0]["position"] == 1

    @respx.mock
    def test_search_reddit_parses_subreddit(self) -> None:
        fixture = _load_fixture("serper_reddit.json")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = SerperClient(api_key="serper-test-key")
        results = client.search_reddit("changelog automation")

        assert len(results) == 2
        assert results[0]["subreddit"] == "SaaS"
        assert results[1]["subreddit"] == "startups"

    @respx.mock
    def test_search_falls_back_on_error(self) -> None:
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(429, text="Rate limited")
        )

        client = SerperClient(api_key="serper-test-key")
        results = client.search("test")
        assert len(results) > 0
        assert results[0]["title"].startswith("Mock SERP")

    def test_extract_subreddit(self) -> None:
        assert _extract_subreddit("https://www.reddit.com/r/SaaS/comments/abc") == "SaaS"
        assert _extract_subreddit("https://www.reddit.com/r/startups/comments/def") == "startups"
        assert _extract_subreddit("https://example.com/not-reddit") == ""


# =====================================================================
# Exa
# =====================================================================


class TestExaClient:
    def test_mock_fallback_no_api_key(self) -> None:
        client = ExaClient(api_key="")
        results = client.search("test query")
        assert len(results) > 0
        assert "Innovative SaaS Platform" in results[0]["title"]

    @respx.mock
    def test_search_parses_response(self) -> None:
        fixture = _load_fixture("exa_search.json")
        respx.post("https://api.exa.ai/search").mock(return_value=httpx.Response(200, json=fixture))

        client = ExaClient(api_key="exa-test-key")
        results = client.search("AI changelog tools", num_results=5)

        assert len(results) == 2
        assert results[0]["title"] == "ChangeBot - AI Changelog Generator"
        assert results[0]["score"] == 0.92
        # JSON null → str(None) → 'None' (string), not Python None
        assert results[1]["author"] is None or results[1]["author"] == "None"

    @respx.mock
    def test_find_similar(self) -> None:
        fixture = {
            "results": [
                {
                    "title": "Similar Co",
                    "url": "https://sim.co",
                    "score": 0.88,
                    "text": "Similar product",
                }
            ]
        }
        respx.post("https://api.exa.ai/findSimilar").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = ExaClient(api_key="exa-test-key")
        results = client.find_similar("https://example.com")

        assert len(results) == 1
        assert results[0]["title"] == "Similar Co"
        assert results[0]["score"] == 0.88

    @respx.mock
    def test_search_falls_back_on_error(self) -> None:
        respx.post("https://api.exa.ai/search").mock(
            return_value=httpx.Response(500, text="Server Error")
        )

        client = ExaClient(api_key="exa-test-key")
        results = client.search("test")
        assert len(results) > 0

    def test_is_available(self) -> None:
        assert ExaClient(api_key="key").is_available is True
        assert ExaClient(api_key="").is_available is False


# =====================================================================
# Perplexity
# =====================================================================


class TestPerplexityClient:
    def test_mock_fallback_no_api_key(self) -> None:
        client = PerplexityClient(api_key="")
        result = client.query("What is the TAM?")
        assert "market" in result["answer"].lower() or "growing" in result["answer"].lower()
        assert result["model"] == "sonar"

    @respx.mock
    def test_query_parses_response(self) -> None:
        fixture = _load_fixture("perplexity_query.json")
        respx.post("https://api.perplexity.ai/chat/completions").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = PerplexityClient(api_key="pplx-test-key")
        result = client.query("What is the TAM for changelog tools?")

        assert "$850M" in result["answer"]
        assert len(result["citations"]) == 2
        assert result["model"] == "sonar"
        assert result["usage"]["total_tokens"] == 227

    @respx.mock
    def test_deep_research_parses_response(self) -> None:
        fixture = {
            "model": "sonar-deep-research",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Deep analysis complete."},
                    "finish_reason": "stop",
                }
            ],
            "citations": ["https://a.com", "https://b.com", "https://c.com"],
            "usage": {"prompt_tokens": 50, "completion_tokens": 500, "total_tokens": 550},
        }
        respx.post("https://api.perplexity.ai/chat/completions").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = PerplexityClient(api_key="pplx-test-key")
        result = client.deep_research("Market analysis for dev tools")

        assert result["answer"] == "Deep analysis complete."
        assert result["sources_analyzed"] == 3
        assert result["model"] == "sonar-deep-research"

    @respx.mock
    def test_query_falls_back_on_error(self) -> None:
        respx.post("https://api.perplexity.ai/chat/completions").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )

        client = PerplexityClient(api_key="pplx-test-key")
        result = client.query("test")
        assert result["model"] == "sonar"  # mock always returns sonar


# =====================================================================
# HN Algolia
# =====================================================================


class TestHNClient:
    def test_always_available(self) -> None:
        """HN client needs no API key."""
        client = HNClient()
        assert client.is_available is True

    @respx.mock
    def test_search_stories(self) -> None:
        fixture = _load_fixture("hn_search.json")
        respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = HNClient()
        results = client.search("AI changelog", tags="story")

        assert len(results) == 2
        assert results[0]["title"] == "Show HN: I built an AI changelog generator"
        assert results[0]["points"] == 234
        assert results[0]["num_comments"] == 89
        assert results[0]["author"] == "devfounder"
        assert results[0]["url"] == "https://github.com/example/ai-changelog"
        assert results[1]["url"] is None  # null in fixture

    @respx.mock
    def test_search_comments(self) -> None:
        fixture = _load_fixture("hn_comments.json")
        respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )

        client = HNClient()
        results = client.search_comments("changelog automation")

        assert len(results) == 2
        assert results[0]["author"] == "tired_maintainer"
        assert "$20/month" in results[0]["comment_text"]
        assert results[1]["story_url"] is None

    @respx.mock
    def test_search_falls_back_on_error(self) -> None:
        respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(500, text="Server Error")
        )

        client = HNClient()
        results = client.search("test")
        assert len(results) > 0
        assert "Show HN" in results[0]["title"]

    @respx.mock
    def test_search_with_empty_hits(self) -> None:
        """Handles response with no hits gracefully."""
        respx.get("https://hn.algolia.com/api/v1/search").mock(
            return_value=httpx.Response(200, json={"hits": [], "nbHits": 0})
        )

        client = HNClient()
        results = client.search("nonexistent query")
        assert results == []
