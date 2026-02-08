"""Client stub for Tavily search API.

Tavily provides AI-optimized web search with structured output.
Free tier: 1,000 searches/month. Paid: $0.008 per basic search.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import structlog

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
    """Tavily API client. Returns mock data until API key is configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, max_results: int = 5) -> list[TavilySearchResult]:
        """Search the web using Tavily's AI-optimized search.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (1-20).

        Returns:
            List of search result dicts with keys: title, url, content, score.
        """
        if not self.is_available:
            logger.debug("Tavily not configured, returning mock data")
            return self._mock_search(query, max_results)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/search",
        #         json={
        #             "api_key": self.api_key,
        #             "query": query,
        #             "max_results": max_results,
        #             "search_depth": "basic",
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return data.get("results", [])
        logger.info("Tavily search: %r (max_results=%d)", query, max_results)
        return self._mock_search(query, max_results)

    async def research(self, query: str) -> TavilyResearchResult:
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

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/research",
        #         json={
        #             "api_key": self.api_key,
        #             "query": query,
        #         },
        #     )
        #     resp.raise_for_status()
        #     return resp.json()
        logger.info("Tavily research: %r", query)
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
