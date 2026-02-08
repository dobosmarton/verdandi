"""Client stub for Serper.dev Google SERP API.

Serper provides structured Google search results at the best price:
2,500 free queries (one-time), then $1 per 1,000 queries.
Key capability: site:reddit.com queries for extracting discussions.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class SerperClient:
    """Serper.dev API client. Returns mock data until API key is configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://google.serper.dev"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, num: int = 10) -> list[dict]:
        """Search Google via Serper and return structured SERP data.

        Args:
            query: Search query string.
            num: Number of results to return (max 100).

        Returns:
            List of result dicts with keys: title, link, snippet, position.
        """
        if not self.is_available:
            logger.debug("Serper not configured, returning mock data")
            return self._mock_search(query, num)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/search",
        #         headers={"X-API-KEY": self.api_key},
        #         json={"q": query, "num": num},
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return data.get("organic", [])
        logger.info("Serper search: %r (num=%d)", query, num)
        return self._mock_search(query, num)

    async def search_reddit(self, query: str) -> list[dict]:
        """Search Reddit discussions via Google site: queries.

        Uses site:reddit.com to find relevant Reddit threads discussing
        pain points, feature requests, and competitor complaints.

        Args:
            query: Topic to search for on Reddit.

        Returns:
            List of Reddit result dicts with keys: title, link, snippet,
            subreddit.
        """
        if not self.is_available:
            logger.debug("Serper not configured, returning mock Reddit data")
            return self._mock_search_reddit(query)

        # TODO: Real API call with site:reddit.com prefix
        # full_query = f"site:reddit.com {query}"
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/search",
        #         headers={"X-API-KEY": self.api_key},
        #         json={"q": full_query, "num": 10},
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     results = data.get("organic", [])
        #     for r in results:
        #         # Extract subreddit from URL
        #         parts = r.get("link", "").split("/")
        #         if "r" in parts:
        #             idx = parts.index("r")
        #             r["subreddit"] = parts[idx + 1] if idx + 1 < len(parts) else ""
        #     return results
        logger.info("Serper Reddit search: %r", query)
        return self._mock_search_reddit(query)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_search(self, query: str, num: int) -> list[dict]:
        results: list[dict] = [
            {
                "title": f"Mock SERP result {i + 1} for '{query}'",
                "link": f"https://example.com/serp-{i + 1}",
                "snippet": (
                    f"Mock snippet for result {i + 1}. This page discusses {query} in detail."
                ),
                "position": i + 1,
            }
            for i in range(min(num, 5))
        ]
        # Include People Also Ask mock data
        results.append(
            {
                "people_also_ask": [
                    {"question": f"What is the best {query}?"},
                    {"question": f"How much does {query} cost?"},
                    {"question": f"Is {query} worth it?"},
                ],
            }
        )
        return results

    def _mock_search_reddit(self, query: str) -> list[dict]:
        return [
            {
                "title": f"[Discussion] Anyone else frustrated with {query}?",
                "link": f"https://reddit.com/r/SaaS/comments/abc123/{query.replace(' ', '_')}",
                "snippet": (
                    f"I've been looking for a good {query} solution but "
                    "everything on the market is either too expensive or "
                    "missing critical features..."
                ),
                "subreddit": "SaaS",
                "position": 1,
            },
            {
                "title": f"Best alternatives for {query} in 2025?",
                "link": f"https://reddit.com/r/startups/comments/def456/best_{query.replace(' ', '_')}",
                "snippet": (
                    f"What are people using for {query}? The top tools "
                    "seem to have poor UX and limited integrations."
                ),
                "subreddit": "startups",
                "position": 2,
            },
            {
                "title": f"I built a {query} tool - feedback welcome",
                "link": f"https://reddit.com/r/SideProject/comments/ghi789/{query.replace(' ', '_')}_tool",
                "snippet": (
                    f"After months of struggling with existing {query} "
                    "solutions, I decided to build my own. Here's what "
                    "I learned about the market..."
                ),
                "subreddit": "SideProject",
                "position": 3,
            },
        ]
