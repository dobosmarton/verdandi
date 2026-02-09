"""Client for Tavily search API.

Tavily provides AI-optimized web search with structured output.
Free tier: 1,000 searches/month. Paid: $0.008 per basic search.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()


class TavilySearchResult(TypedDict):
    title: str
    url: str
    content: str
    score: float
    published_date: str


class TavilySource(TypedDict):
    title: str
    url: str
    relevance: float


class TavilyResearchResult(TypedDict):
    summary: str
    sources: list[TavilySource]
    follow_up_questions: list[str]


class TavilyClient:
    """Tavily API client. Returns mock data when API key is not configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> list[TavilySearchResult]:
        """Search the web using Tavily's AI-optimized search.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (1-20).

        Returns:
            List of search result dicts with keys: title, url, content,
            score, published_date.
        """
        if not self.is_available:
            logger.debug("Tavily not configured, returning mock data")
            return self._mock_search(query, max_results)

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base_url}/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                raw_results = data.get("results", [])
                if not isinstance(raw_results, list):
                    raw_results = []
                results: list[TavilySearchResult] = []
                for item in raw_results:
                    if not isinstance(item, dict):
                        continue
                    result: TavilySearchResult = {
                        "title": str(item.get("title", "")),
                        "url": str(item.get("url", "")),
                        "content": str(item.get("content", "")),
                        "score": float(item.get("score", 0.0)),
                        "published_date": str(item.get("published_date", "")),
                    }
                    results.append(result)
                return results
        except httpx.HTTPError as exc:
            logger.warning(
                "Tavily search API error, falling back to mock data",
                query=query,
                error=str(exc),
            )
            return self._mock_search(query, max_results)

    def research(self, query: str) -> TavilyResearchResult:
        """Run Tavily's multi-step deep research mode.

        This endpoint performs agent-mode research with multiple search
        iterations for complex queries like market analysis.

        Args:
            query: Research question or topic.

        Returns:
            Dict with keys: summary, sources, follow_up_questions.
        """
        if not self.is_available:
            logger.debug("Tavily not configured, returning mock research data")
            return self._mock_research(query)

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{self.base_url}/research",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()

                raw_sources = data.get("sources", [])
                if not isinstance(raw_sources, list):
                    raw_sources = []
                sources: list[TavilySource] = []
                for src in raw_sources:
                    if not isinstance(src, dict):
                        continue
                    source: TavilySource = {
                        "title": str(src.get("title", "")),
                        "url": str(src.get("url", "")),
                        "relevance": float(src.get("relevance", 0.0)),
                    }
                    sources.append(source)

                raw_questions = data.get("follow_up_questions", [])
                if not isinstance(raw_questions, list):
                    raw_questions = []
                follow_up_questions: list[str] = [str(q) for q in raw_questions]

                result: TavilyResearchResult = {
                    "summary": str(data.get("summary", "")),
                    "sources": sources,
                    "follow_up_questions": follow_up_questions,
                }
                return result
        except httpx.HTTPError as exc:
            logger.warning(
                "Tavily research API error, falling back to mock data",
                query=query,
                error=str(exc),
            )
            return self._mock_research(query)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_search(self, query: str, max_results: int) -> list[TavilySearchResult]:
        return [
            {
                "title": f"Mock result {i + 1} for '{query}'",
                "url": f"https://example.com/result-{i + 1}",
                "content": (
                    f"This is mock content for search result {i + 1} "
                    f"related to '{query}'. In production, this would "
                    f"contain a relevant snippet from the web page."
                ),
                "score": round(0.95 - i * 0.1, 2),
                "published_date": datetime.now(UTC).isoformat(),
            }
            for i in range(min(max_results, 3))
        ]

    def _mock_research(self, query: str) -> TavilyResearchResult:
        return {
            "summary": (
                f"Mock research summary for '{query}'. "
                "The market shows strong demand signals with multiple "
                "underserved segments. Key competitors lack critical "
                "features that users frequently request."
            ),
            "sources": [
                {
                    "title": "Industry Analysis Report",
                    "url": "https://example.com/report",
                    "relevance": 0.95,
                },
                {
                    "title": "User Forum Discussion",
                    "url": "https://example.com/forum",
                    "relevance": 0.87,
                },
            ],
            "follow_up_questions": [
                "What is the total addressable market size?",
                "Who are the top 3 competitors by market share?",
                "What pricing models do existing solutions use?",
            ],
        }
