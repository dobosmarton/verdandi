"""Client stub for Reddit API.

Reddit API is free but has strict rules: max 10% self-promotion,
karma requirements vary by subreddit. Used for targeted distribution
in relevant communities.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()


class RedditClient:
    """Reddit API client. Returns mock data until credentials are configured."""

    def __init__(self, client_id: str = "", client_secret: str = "") -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://oauth.reddit.com"
        self._access_token: str = ""

    @property
    def is_available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _ensure_token(self) -> None:
        """Obtain an OAuth2 access token if we don't have one."""
        if self._access_token:
            return
        # TODO: Real token exchange
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         "https://www.reddit.com/api/v1/access_token",
        #         auth=(self.client_id, self.client_secret),
        #         data={"grant_type": "client_credentials"},
        #         headers={"User-Agent": "verdandi/0.1.0"},
        #     )
        #     resp.raise_for_status()
        #     self._access_token = resp.json()["access_token"]
        self._access_token = "mock-token"

    async def submit(self, subreddit: str, title: str, text: str) -> dict:
        """Submit a self-post to a subreddit.

        Important: Reddit enforces a 10% self-promotion rule. Ensure
        the account has adequate karma and posting history before
        submitting promotional content.

        Args:
            subreddit: Target subreddit name (without r/ prefix).
            title: Post title.
            text: Post body (markdown supported).

        Returns:
            Dict with keys: id, subreddit, title, url, created_at.
        """
        if not self.is_available:
            logger.debug("Reddit not configured, returning mock submission")
            return self._mock_submit(subreddit, title, text)

        # TODO: Real API call
        # await self._ensure_token()
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/api/submit",
        #         headers={
        #             "Authorization": f"Bearer {self._access_token}",
        #             "User-Agent": "verdandi/0.1.0",
        #         },
        #         data={
        #             "sr": subreddit,
        #             "kind": "self",
        #             "title": title,
        #             "text": text,
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()["json"]["data"]
        #     return {
        #         "id": data["id"],
        #         "subreddit": subreddit,
        #         "title": title,
        #         "url": data["url"],
        #         "created_at": datetime.now(timezone.utc).isoformat(),
        #     }
        logger.info("Reddit submit to r/%s: %s", subreddit, title[:50])
        return self._mock_submit(subreddit, title, text)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_submit(self, subreddit: str, title: str, text: str) -> dict:
        mock_id = "t3_abc123"
        return {
            "id": mock_id,
            "subreddit": subreddit,
            "title": title,
            "url": f"https://reddit.com/r/{subreddit}/comments/abc123/",
            "created_at": datetime.now(UTC).isoformat(),
        }
