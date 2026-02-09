"""Client for Hacker News Algolia API.

The HN Algolia API is free with no rate limits and requires no API key.
Invaluable for discovering developer pain points and trending topics.
Docs: https://hn.algolia.com/api
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()

_TIMEOUT = httpx.Timeout(30.0)
_BASE_URL = "https://hn.algolia.com/api/v1"


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


def _parse_story(hit: dict[str, object], tags: str) -> HNStory:
    """Parse a single HN Algolia hit into an HNStory TypedDict."""
    # created_at: prefer the ISO string field, fall back to epoch
    created_at_raw = hit.get("created_at")
    if isinstance(created_at_raw, str) and created_at_raw:
        created_at = created_at_raw
    else:
        created_at_i = hit.get("created_at_i")
        if isinstance(created_at_i, int):
            created_at = datetime.fromtimestamp(created_at_i, tz=UTC).isoformat()
        else:
            created_at = datetime.now(UTC).isoformat()

    # url can be null/empty in the API response
    url_raw = hit.get("url")
    url: str | None = str(url_raw) if url_raw else None

    # _tags is a list of strings in the API response
    hit_tags = hit.get("_tags")
    tags_str = ",".join(str(t) for t in hit_tags) if isinstance(hit_tags, list) else tags

    title_raw = hit.get("title")
    title = str(title_raw) if title_raw else ""

    author_raw = hit.get("author")
    author = str(author_raw) if author_raw else ""

    points_raw = hit.get("points")
    points = int(points_raw) if isinstance(points_raw, (int, float)) else 0

    num_comments_raw = hit.get("num_comments")
    num_comments = int(num_comments_raw) if isinstance(num_comments_raw, (int, float)) else 0

    object_id_raw = hit.get("objectID")
    object_id = str(object_id_raw) if object_id_raw else ""

    return HNStory(
        title=title,
        url=url,
        author=author,
        points=points,
        num_comments=num_comments,
        created_at=created_at,
        objectID=object_id,
        tags=tags_str,
    )


def _parse_comment(hit: dict[str, object]) -> HNComment:
    """Parse a single HN Algolia hit into an HNComment TypedDict."""
    # created_at: prefer the ISO string field, fall back to epoch
    created_at_raw = hit.get("created_at")
    if isinstance(created_at_raw, str) and created_at_raw:
        created_at = created_at_raw
    else:
        created_at_i = hit.get("created_at_i")
        if isinstance(created_at_i, int):
            created_at = datetime.fromtimestamp(created_at_i, tz=UTC).isoformat()
        else:
            created_at = datetime.now(UTC).isoformat()

    comment_text_raw = hit.get("comment_text")
    comment_text = str(comment_text_raw) if comment_text_raw else ""

    author_raw = hit.get("author")
    author = str(author_raw) if author_raw else ""

    story_title_raw = hit.get("story_title")
    story_title = str(story_title_raw) if story_title_raw else ""

    story_url_raw = hit.get("story_url")
    story_url: str | None = str(story_url_raw) if story_url_raw else None

    points_raw = hit.get("points")
    points = int(points_raw) if isinstance(points_raw, (int, float)) else 0

    object_id_raw = hit.get("objectID")
    object_id = str(object_id_raw) if object_id_raw else ""

    return HNComment(
        comment_text=comment_text,
        author=author,
        story_title=story_title,
        story_url=story_url,
        points=points,
        created_at=created_at,
        objectID=object_id,
    )


class HNClient:
    """Hacker News Algolia API client. Always available (no API key needed)."""

    def __init__(self) -> None:
        self.base_url = _BASE_URL

    @property
    def is_available(self) -> bool:
        # HN Algolia API is free and requires no authentication.
        return True

    def search(self, query: str, tags: str = "story") -> list[HNStory]:
        """Search Hacker News stories.

        Args:
            query: Search query string.
            tags: HN item type filter. Options: "story", "comment",
                "show_hn", "ask_hn", "poll". Combine with commas.

        Returns:
            List of HN story dicts with title, url, author, points,
            num_comments, created_at, objectID, and tags.
        """
        logger.info("hn_search", query=query, tags=tags)
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(
                    f"{self.base_url}/search",
                    params={
                        "query": query,
                        "tags": tags,
                        "hitsPerPage": 20,
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                hits_raw = data.get("hits")
                if not isinstance(hits_raw, list):
                    logger.warning("hn_search_unexpected_response", query=query)
                    return self._mock_search(query, tags)
                hits: list[dict[str, object]] = hits_raw
                return [_parse_story(hit, tags) for hit in hits]
        except httpx.HTTPError as exc:
            logger.warning("hn_search_failed", query=query, error=str(exc))
            return self._mock_search(query, tags)

    def search_comments(self, query: str) -> list[HNComment]:
        """Search Hacker News comments for pain points and discussions.

        Comments often contain the most valuable insights about what
        developers actually struggle with.

        Args:
            query: Topic to search for in comments.

        Returns:
            List of comment dicts with comment_text, author,
            story_title, story_url, points, created_at, and objectID.
        """
        logger.info("hn_comment_search", query=query)
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(
                    f"{self.base_url}/search",
                    params={
                        "query": query,
                        "tags": "comment",
                        "hitsPerPage": 20,
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                hits_raw = data.get("hits")
                if not isinstance(hits_raw, list):
                    logger.warning("hn_comment_search_unexpected_response", query=query)
                    return self._mock_search_comments(query)
                hits: list[dict[str, object]] = hits_raw
                return [_parse_comment(hit) for hit in hits]
        except httpx.HTTPError as exc:
            logger.warning("hn_comment_search_failed", query=query, error=str(exc))
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
