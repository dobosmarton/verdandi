"""Client stub for Hacker News Algolia API.

The HN Algolia API is free with no rate limits and requires no API key.
Invaluable for discovering developer pain points and trending topics.
Docs: https://hn.algolia.com/api
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import structlog

logger = structlog.get_logger()


class HNStory(TypedDict):
    title: str
    url: str | None
    author: str
    points: int
    num_comments: int
    created_at: str
    objectID: str
    tags: str


class HNComment(TypedDict):
    comment_text: str
    author: str
    story_title: str
    story_url: str | None
    points: int
    created_at: str
    objectID: str


class HNClient:
    """Hacker News Algolia API client. Always available (no API key needed)."""

    def __init__(self) -> None:
        self.base_url = "https://hn.algolia.com/api/v1"

    @property
    def is_available(self) -> bool:
        # HN Algolia API is free and requires no authentication.
        return True

    async def search(self, query: str, tags: str = "story") -> list[HNStory]:
        """Search Hacker News stories.

        Args:
            query: Search query string.
            tags: HN item type filter. Options: "story", "comment",
                "show_hn", "ask_hn", "poll". Combine with commas.

        Returns:
            List of HN item dicts with keys: title, url, author, points,
            num_comments, created_at, objectID.
        """
        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         f"{self.base_url}/search",
        #         params={
        #             "query": query,
        #             "tags": tags,
        #             "hitsPerPage": 20,
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return data.get("hits", [])
        logger.info("HN search: %r (tags=%s)", query, tags)
        return self._mock_search(query, tags)

    async def search_comments(self, query: str) -> list[HNComment]:
        """Search Hacker News comments for pain points and discussions.

        Comments often contain the most valuable insights about what
        developers actually struggle with.

        Args:
            query: Topic to search for in comments.

        Returns:
            List of comment dicts with keys: comment_text, author,
            story_title, story_url, points, created_at, objectID.
        """
        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         f"{self.base_url}/search",
        #         params={
        #             "query": query,
        #             "tags": "comment",
        #             "hitsPerPage": 20,
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return data.get("hits", [])
        logger.info("HN comment search: %r", query)
        return self._mock_search_comments(query)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_search(self, query: str, tags: str) -> list[HNStory]:
        now = datetime.now(UTC).isoformat()
        return [
            {
                "title": f"Show HN: An open source {query} tool",
                "url": f"https://github.com/example/{query.replace(' ', '-')}",
                "author": "techfounder",
                "points": 342,
                "num_comments": 187,
                "created_at": now,
                "objectID": "39001001",
                "tags": tags,
            },
            {
                "title": f"Ask HN: What {query} tools do you use?",
                "url": None,
                "author": "curious_dev",
                "points": 156,
                "num_comments": 234,
                "created_at": now,
                "objectID": "39001002",
                "tags": tags,
            },
            {
                "title": f"Why {query} is broken and how to fix it",
                "url": f"https://blog.example.com/{query.replace(' ', '-')}-broken",
                "author": "frustrated_engineer",
                "points": 89,
                "num_comments": 67,
                "created_at": now,
                "objectID": "39001003",
                "tags": tags,
            },
        ]

    def _mock_search_comments(self, query: str) -> list[HNComment]:
        now = datetime.now(UTC).isoformat()
        return [
            {
                "comment_text": (
                    f"I've been struggling with {query} for months. "
                    "The existing tools are either too expensive ($500+/mo) "
                    "or require significant engineering effort to set up. "
                    "Would happily pay $50/mo for something that just works."
                ),
                "author": "enterprise_dev",
                "story_title": f"Ask HN: What {query} tools do you use?",
                "story_url": None,
                "points": 45,
                "created_at": now,
                "objectID": "39002001",
            },
            {
                "comment_text": (
                    f"We evaluated 5 different {query} solutions last quarter. "
                    "None of them had a decent API. We ended up building "
                    "a custom solution internally, which took 3 months."
                ),
                "author": "team_lead_2025",
                "story_title": f"Show HN: An open source {query} tool",
                "story_url": f"https://github.com/example/{query.replace(' ', '-')}",
                "points": 23,
                "created_at": now,
                "objectID": "39002002",
            },
            {
                "comment_text": (
                    f"The biggest issue with current {query} tools is the "
                    "learning curve. My team of 5 spent 2 weeks just on "
                    "onboarding. Documentation is universally terrible."
                ),
                "author": "eng_manager",
                "story_title": f"Why {query} is broken and how to fix it",
                "story_url": f"https://blog.example.com/{query.replace(' ', '-')}-broken",
                "points": 67,
                "created_at": now,
                "objectID": "39002003",
            },
        ]
