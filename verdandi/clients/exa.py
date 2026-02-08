"""Client stub for Exa.ai semantic search API.

Exa provides neural/semantic search, finding results by meaning rather
than keywords. Especially valuable for competitor discovery and finding
niche communities. $10 one-time free credit (~2,000 searches).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import structlog

logger = structlog.get_logger()


class ExaSearchResult(TypedDict):
    title: str
    url: str
    text: str
    score: float
    published_date: str
    author: str | None


class ExaSimilarResult(TypedDict):
    title: str
    url: str
    score: float
    text: str


class ExaClient:
    """Exa.ai API client. Returns mock data until API key is configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://api.exa.ai"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, num_results: int = 10) -> list[ExaSearchResult]:
        """Semantic search - find results by meaning, not just keywords.

        Args:
            query: Natural language query (e.g., "tools for automating
                invoice processing for small businesses").
            num_results: Number of results to return.

        Returns:
            List of result dicts with keys: title, url, text, score,
            published_date, author.
        """
        if not self.is_available:
            logger.debug("Exa not configured, returning mock data")
            return self._mock_search(query, num_results)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/search",
        #         headers={"x-api-key": self.api_key},
        #         json={
        #             "query": query,
        #             "numResults": num_results,
        #             "type": "neural",
        #             "useAutoprompt": True,
        #             "contents": {"text": True},
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return data.get("results", [])
        logger.info("Exa search: %r (num_results=%d)", query, num_results)
        return self._mock_search(query, num_results)

    async def find_similar(self, url: str) -> list[ExaSimilarResult]:
        """Find websites similar to a given URL.

        Useful for competitor discovery - provide a known competitor URL
        and find others in the same space.

        Args:
            url: URL of a reference site to find similar sites for.

        Returns:
            List of similar site dicts with keys: title, url, score, text.
        """
        if not self.is_available:
            logger.debug("Exa not configured, returning mock similar data")
            return self._mock_find_similar(url)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/findSimilar",
        #         headers={"x-api-key": self.api_key},
        #         json={
        #             "url": url,
        #             "numResults": 10,
        #             "contents": {"text": True},
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return data.get("results", [])
        logger.info("Exa find_similar: %r", url)
        return self._mock_find_similar(url)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_search(self, query: str, num_results: int) -> list[ExaSearchResult]:
        results: list[ExaSearchResult] = []
        mock_sites = [
            ("Innovative SaaS Platform", "https://example-saas.com"),
            ("Enterprise Solution Provider", "https://enterprise-tool.io"),
            ("Startup Disrupting Legacy Market", "https://newdisruptor.com"),
            ("Open Source Alternative", "https://github.com/oss-project"),
            ("Niche Community Forum", "https://community.example.com"),
        ]
        for i in range(min(num_results, len(mock_sites))):
            title, url = mock_sites[i]
            results.append(
                {
                    "title": f"{title} - {query}",
                    "url": url,
                    "text": (
                        f"This company offers solutions related to '{query}'. "
                        f"Founded in 2023, they serve SMBs with a freemium model. "
                        f"Key differentiator: AI-powered automation."
                    ),
                    "score": round(0.92 - i * 0.05, 2),
                    "published_date": datetime.now(UTC).isoformat(),
                    "author": None,
                }
            )
        return results

    def _mock_find_similar(self, url: str) -> list[ExaSimilarResult]:
        return [
            {
                "title": "Similar Company A",
                "url": "https://similar-a.com",
                "score": 0.91,
                "text": (
                    f"A competitor to {url}. Focuses on small business "
                    "customers with a self-serve model. $49/month pricing."
                ),
            },
            {
                "title": "Similar Company B",
                "url": "https://similar-b.io",
                "score": 0.85,
                "text": (
                    f"Another company in the same space as {url}. "
                    "Enterprise-focused with custom pricing. Series A funded."
                ),
            },
            {
                "title": "Open Source Alternative",
                "url": "https://github.com/oss-similar",
                "score": 0.78,
                "text": (
                    f"Open source alternative to {url}. Active community, "
                    "1.2k GitHub stars. Self-hosted, MIT license."
                ),
            },
        ]
