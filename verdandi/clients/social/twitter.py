"""Client stub for Twitter/X API.

X free tier: 500 posts/month (write-only access).
Used for distributing landing page announcements.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import structlog

logger = structlog.get_logger()


class TweetResult(TypedDict):
    id: str
    text: str
    created_at: str
    url: str


class TwitterClient:
    """Twitter/X API client. Returns mock data until bearer token is configured."""

    def __init__(self, bearer_token: str = "") -> None:
        self.bearer_token = bearer_token
        self.base_url = "https://api.x.com/2"

    @property
    def is_available(self) -> bool:
        return bool(self.bearer_token)

    async def post(self, text: str) -> TweetResult:
        """Post a tweet.

        Args:
            text: Tweet text (max 280 characters).

        Returns:
            Dict with keys: id, text, created_at, url.
        """
        if not self.is_available:
            logger.debug("Twitter not configured, returning mock post")
            return self._mock_post(text)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/tweets",
        #         headers={
        #             "Authorization": f"Bearer {self.bearer_token}",
        #             "Content-Type": "application/json",
        #         },
        #         json={"text": text},
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()["data"]
        #     return {
        #         "id": data["id"],
        #         "text": data["text"],
        #         "created_at": data.get("created_at"),
        #         "url": f"https://x.com/i/status/{data['id']}",
        #     }
        logger.info("Twitter post: %s...", text[:50])
        return self._mock_post(text)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_post(self, text: str) -> TweetResult:
        mock_id = "1234567890123456789"
        return {
            "id": mock_id,
            "text": text[:280],
            "created_at": datetime.now(UTC).isoformat(),
            "url": f"https://x.com/i/status/{mock_id}",
        }
