"""Client stub for LinkedIn API.

LinkedIn API is free for personal posting. High-quality B2B reach
for product validation announcements.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()


class LinkedInPostResult(TypedDict):
    id: str
    text: str
    created_at: str
    url: str


class LinkedInClient:
    """LinkedIn API client. Returns mock data until access token is configured."""

    def __init__(self, access_token: str = "") -> None:
        self.access_token = access_token
        self.base_url = "https://api.linkedin.com/v2"

    @property
    def is_available(self) -> bool:
        return bool(self.access_token)

    async def post(self, text: str) -> LinkedInPostResult:
        """Create a LinkedIn post (share).

        Args:
            text: Post text content. LinkedIn supports up to 3,000
                characters for organic posts.

        Returns:
            Dict with keys: id, text, created_at, url.
        """
        if not self.is_available:
            logger.debug("LinkedIn not configured, returning mock post")
            return self._mock_post(text)

        # TODO: Real API call
        # The LinkedIn API requires the user's URN for posting.
        # async with httpx.AsyncClient() as client:
        #     # First get the user profile URN
        #     me_resp = await client.get(
        #         f"{self.base_url}/userinfo",
        #         headers={"Authorization": f"Bearer {self.access_token}"},
        #     )
        #     me_resp.raise_for_status()
        #     user_urn = f"urn:li:person:{me_resp.json()['sub']}"
        #
        #     resp = await client.post(
        #         f"{self.base_url}/ugcPosts",
        #         headers={
        #             "Authorization": f"Bearer {self.access_token}",
        #             "Content-Type": "application/json",
        #             "X-Restli-Protocol-Version": "2.0.0",
        #         },
        #         json={
        #             "author": user_urn,
        #             "lifecycleState": "PUBLISHED",
        #             "specificContent": {
        #                 "com.linkedin.ugc.ShareContent": {
        #                     "shareCommentary": {"text": text},
        #                     "shareMediaCategory": "NONE",
        #                 }
        #             },
        #             "visibility": {
        #                 "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        #             },
        #         },
        #     )
        #     resp.raise_for_status()
        #     post_id = resp.json().get("id", "")
        #     return {
        #         "id": post_id,
        #         "text": text,
        #         "created_at": datetime.now(timezone.utc).isoformat(),
        #         "url": f"https://www.linkedin.com/feed/update/{post_id}/",
        #     }
        logger.info("LinkedIn post: %s...", text[:50])
        return self._mock_post(text)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_post(self, text: str) -> LinkedInPostResult:
        mock_id = "urn:li:share:7000000000000000001"
        return {
            "id": mock_id,
            "text": text[:3000],
            "created_at": datetime.now(UTC).isoformat(),
            "url": f"https://www.linkedin.com/feed/update/{mock_id}/",
        }
