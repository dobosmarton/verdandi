"""Client for SocialData.tools Twitter/X search API.

SocialData provides access to Twitter search data including full tweet
text, engagement metrics, and author information.  Free tier: 3 req/min
(~4,300/month).  Docs: https://docs.socialdata.tools/reference/
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()

_TIMEOUT = 30.0
_BASE_URL = "https://api.socialdata.tools"


class SocialDataTweet(TypedDict):
    tweet_id: str
    text: str
    author_username: str
    author_name: str
    author_followers: int
    created_at: str
    favorite_count: int
    retweet_count: int
    reply_count: int
    views_count: int
    url: str


class SocialDataClient:
    """SocialData.tools API client.  Returns mock data when API key is not configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = _BASE_URL

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, search_type: str = "Latest") -> list[SocialDataTweet]:
        """Search Twitter/X via SocialData API.

        Args:
            query: Search query (supports Twitter search operators).
            search_type: ``'Latest'`` for recent tweets, ``'Top'`` for popular.

        Returns:
            List of tweet dicts with full engagement metrics.
        """
        if not self.is_available:
            logger.debug("SocialData not configured, returning mock data")
            return self._mock_search(query)

        logger.info("socialdata_search", query=query, type=search_type)
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(
                    f"{self.base_url}/twitter/search",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                    },
                    params={"query": query, "type": search_type},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                raw_tweets = data.get("tweets", [])
                if not isinstance(raw_tweets, list):
                    raw_tweets = []
                return self._parse_tweets(raw_tweets)
        except httpx.HTTPError as exc:
            logger.warning("socialdata_search_failed", query=query, error=str(exc))
            return self._mock_search(query)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tweets(raw_tweets: list[object]) -> list[SocialDataTweet]:
        results: list[SocialDataTweet] = []
        for item in raw_tweets:
            if not isinstance(item, dict):
                continue
            user_raw = item.get("user")
            user: dict[str, object] = user_raw if isinstance(user_raw, dict) else {}
            tweet_id = str(item.get("id_str", ""))
            screen_name = str(user.get("screen_name", ""))
            followers_raw = user.get("followers_count", 0)
            followers = int(followers_raw) if isinstance(followers_raw, (int, float)) else 0

            def _int(val: object) -> int:
                return int(val) if isinstance(val, (int, float)) else 0

            result: SocialDataTweet = {
                "tweet_id": tweet_id,
                "text": str(item.get("full_text", "")),
                "author_username": screen_name,
                "author_name": str(user.get("name", "")),
                "author_followers": followers,
                "created_at": str(item.get("tweet_created_at", "")),
                "favorite_count": _int(item.get("favorite_count", 0)),
                "retweet_count": _int(item.get("retweet_count", 0)),
                "reply_count": _int(item.get("reply_count", 0)),
                "views_count": _int(item.get("views_count", 0)),
                "url": (
                    f"https://x.com/{screen_name}/status/{tweet_id}"
                    if screen_name and tweet_id
                    else ""
                ),
            }
            results.append(result)
        logger.info("socialdata_parse_complete", result_count=len(results))
        return results

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_search(self, query: str) -> list[SocialDataTweet]:
        now = datetime.now(UTC).isoformat()
        return [
            {
                "tweet_id": "1800000000000000001",
                "text": (
                    f"I've been struggling with {query} for weeks. "
                    "Every tool I try is either $500/mo or requires a PhD "
                    "to configure. Would happily pay $30/mo for something simple."
                ),
                "author_username": "frustrated_founder",
                "author_name": "Alex Chen",
                "author_followers": 2340,
                "created_at": now,
                "favorite_count": 89,
                "retweet_count": 23,
                "reply_count": 45,
                "views_count": 12400,
                "url": "https://x.com/frustrated_founder/status/1800000000000000001",
            },
            {
                "tweet_id": "1800000000000000002",
                "text": (
                    f"Thread: Why the {query} market is about to explode. "
                    "1/ Every company I talk to has this problem. "
                    "2/ Current solutions are 10 years old. "
                    "3/ AI makes a 10x better approach possible now."
                ),
                "author_username": "vc_observer",
                "author_name": "Sarah Kim",
                "author_followers": 15600,
                "created_at": now,
                "favorite_count": 234,
                "retweet_count": 78,
                "reply_count": 56,
                "views_count": 45000,
                "url": "https://x.com/vc_observer/status/1800000000000000002",
            },
            {
                "tweet_id": "1800000000000000003",
                "text": (
                    f"Just shipped a {query} feature that took 2 weeks to build. "
                    "If someone made a standalone tool for this, "
                    "I'd have saved 80 hours of engineering time."
                ),
                "author_username": "cto_at_startup",
                "author_name": "Marcus Wright",
                "author_followers": 890,
                "created_at": now,
                "favorite_count": 45,
                "retweet_count": 12,
                "reply_count": 18,
                "views_count": 5600,
                "url": "https://x.com/cto_at_startup/status/1800000000000000003",
            },
        ]
