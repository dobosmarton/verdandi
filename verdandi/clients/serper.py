"""Client for Serper.dev Google SERP API.

Serper provides structured Google search results at the best price:
2,500 free queries (one-time), then $1 per 1,000 queries.
Key capability: site:reddit.com queries for extracting discussions.
"""

from __future__ import annotations

import httpx
import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()

_SEARCH_TIMEOUT = 30.0


class SerperResult(TypedDict):
    title: str
    link: str
    snippet: str
    position: int


class SerperRedditResult(TypedDict):
    title: str
    link: str
    snippet: str
    subreddit: str
    position: int


class SerperTwitterResult(TypedDict):
    title: str
    link: str
    snippet: str
    author: str
    position: int


def _extract_subreddit(link: str) -> str:
    """Extract subreddit name from a Reddit URL.

    Expected format: https://www.reddit.com/r/SUBREDDIT/...
    """
    parts = link.split("/")
    if "r" in parts:
        idx = parts.index("r")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _extract_twitter_author(link: str) -> str:
    """Extract Twitter/X username from a tweet URL.

    Expected format: ``https://x.com/USERNAME/status/...``
    or ``https://twitter.com/USERNAME/status/...``
    """
    parts = link.split("/")
    # https://x.com/username/status/123 -> parts = ['https:', '', 'x.com', 'username', ...]
    if len(parts) >= 4 and parts[2] in ("x.com", "twitter.com", "www.x.com"):
        return parts[3]
    return ""


class SerperClient:
    """Serper.dev API client. Returns mock data when API key is not configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://google.serper.dev"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, num: int = 10) -> list[SerperResult]:
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

        try:
            with httpx.Client(timeout=_SEARCH_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}/search",
                    headers={"X-API-KEY": self.api_key},
                    json={"q": query, "num": num},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                raw_results = data.get("organic", [])
                if not isinstance(raw_results, list):
                    raw_results = []
                results: list[SerperResult] = []
                for i, item in enumerate(raw_results):
                    if not isinstance(item, dict):
                        continue
                    result: SerperResult = {
                        "title": str(item.get("title", "")),
                        "link": str(item.get("link", "")),
                        "snippet": str(item.get("snippet", "")),
                        "position": i + 1,
                    }
                    results.append(result)
                logger.info("serper_search_complete", query=query, result_count=len(results))
                return results
        except httpx.HTTPError as exc:
            logger.warning("serper_search_failed", query=query, error=str(exc))
            return self._mock_search(query, num)

    def search_reddit(self, query: str) -> list[SerperRedditResult]:
        """Search Reddit discussions via Google site: queries.

        Uses site:reddit.com to find relevant Reddit threads discussing
        pain points, feature requests, and competitor complaints.

        Args:
            query: Topic to search for on Reddit.

        Returns:
            List of Reddit result dicts with keys: title, link, snippet,
            subreddit, position.
        """
        if not self.is_available:
            logger.debug("Serper not configured, returning mock Reddit data")
            return self._mock_search_reddit(query)

        full_query = f"site:reddit.com {query}"
        try:
            with httpx.Client(timeout=_SEARCH_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}/search",
                    headers={"X-API-KEY": self.api_key},
                    json={"q": full_query, "num": 10},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                raw_results = data.get("organic", [])
                if not isinstance(raw_results, list):
                    raw_results = []
                results: list[SerperRedditResult] = []
                for i, item in enumerate(raw_results):
                    if not isinstance(item, dict):
                        continue
                    link = str(item.get("link", ""))
                    result: SerperRedditResult = {
                        "title": str(item.get("title", "")),
                        "link": link,
                        "snippet": str(item.get("snippet", "")),
                        "subreddit": _extract_subreddit(link),
                        "position": i + 1,
                    }
                    results.append(result)
                logger.info(
                    "serper_reddit_search_complete",
                    query=query,
                    result_count=len(results),
                )
                return results
        except httpx.HTTPError as exc:
            logger.warning("serper_reddit_search_failed", query=query, error=str(exc))
            return self._mock_search_reddit(query)

    def search_twitter(self, query: str) -> list[SerperTwitterResult]:
        """Search Twitter/X discussions via Google ``site:x.com`` queries.

        Uses ``site:x.com`` to find relevant tweets discussing pain points,
        product feedback, and market signals.

        Args:
            query: Topic to search for on Twitter/X.

        Returns:
            List of Twitter result dicts with keys: title, link, snippet,
            author, position.
        """
        if not self.is_available:
            logger.debug("Serper not configured, returning mock Twitter data")
            return self._mock_search_twitter(query)

        full_query = f"site:x.com {query}"
        try:
            with httpx.Client(timeout=_SEARCH_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}/search",
                    headers={"X-API-KEY": self.api_key},
                    json={"q": full_query, "num": 10},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                raw_results = data.get("organic", [])
                if not isinstance(raw_results, list):
                    raw_results = []
                results: list[SerperTwitterResult] = []
                for i, item in enumerate(raw_results):
                    if not isinstance(item, dict):
                        continue
                    link = str(item.get("link", ""))
                    result: SerperTwitterResult = {
                        "title": str(item.get("title", "")),
                        "link": link,
                        "snippet": str(item.get("snippet", "")),
                        "author": _extract_twitter_author(link),
                        "position": i + 1,
                    }
                    results.append(result)
                logger.info(
                    "serper_twitter_search_complete",
                    query=query,
                    result_count=len(results),
                )
                return results
        except httpx.HTTPError as exc:
            logger.warning("serper_twitter_search_failed", query=query, error=str(exc))
            return self._mock_search_twitter(query)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_search(self, query: str, num: int) -> list[SerperResult]:
        results: list[SerperResult] = [
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
        return results

    def _mock_search_reddit(self, query: str) -> list[SerperRedditResult]:
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

    def _mock_search_twitter(self, query: str) -> list[SerperTwitterResult]:
        return [
            {
                "title": f"@devfounder: Frustrated with {query} tools...",
                "link": "https://x.com/devfounder/status/1234567890",
                "snippet": (
                    f"I've been looking for a decent {query} solution for months. "
                    "Everything is either overpriced or half-baked. "
                    "Would pay good money for something that just works."
                ),
                "author": "devfounder",
                "position": 1,
            },
            {
                "title": f"@saas_builder: The {query} market is ripe for disruption",
                "link": "https://x.com/saas_builder/status/1234567891",
                "snippet": (
                    f"Hot take: every {query} tool I've tried has the same "
                    "fundamental UX problem. Someone is going to build a "
                    "10x better version and clean up."
                ),
                "author": "saas_builder",
                "position": 2,
            },
            {
                "title": f"@indie_hacker: Just launched my {query} side project",
                "link": "https://x.com/indie_hacker/status/1234567892",
                "snippet": (
                    f"After 3 months of building, my {query} tool is live. "
                    "Already got 50 signups from a single tweet thread. "
                    "The demand is real."
                ),
                "author": "indie_hacker",
                "position": 3,
            },
        ]
