"""Client stub for Bluesky (AT Protocol) API.

Bluesky is completely free and open for automated posting via the
AT Protocol. No rate limiting concerns for normal usage. Used as
a supplementary distribution channel.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()


class BlueskySession(TypedDict):
    did: str
    accessJwt: str


class BlueskyPostResult(TypedDict):
    uri: str
    cid: str
    text: str
    created_at: str
    url: str


class BlueskyClient:
    """Bluesky AT Protocol client. Returns mock data until credentials are configured."""

    def __init__(self, handle: str = "", app_password: str = "") -> None:
        self.handle = handle
        self.app_password = app_password
        self.base_url = "https://bsky.social/xrpc"
        self._session: BlueskySession | None = None

    @property
    def is_available(self) -> bool:
        return bool(self.handle and self.app_password)

    async def _ensure_session(self) -> None:
        """Create an authenticated session if we don't have one."""
        if self._session:
            return
        # TODO: Real session creation
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/com.atproto.server.createSession",
        #         json={
        #             "identifier": self.handle,
        #             "password": self.app_password,
        #         },
        #     )
        #     resp.raise_for_status()
        #     self._session = resp.json()
        self._session = {
            "did": "did:plc:mock123",
            "accessJwt": "mock-jwt-token",
        }

    async def post(self, text: str) -> BlueskyPostResult:
        """Create a Bluesky post (skeet).

        Args:
            text: Post text (max 300 characters for Bluesky).

        Returns:
            Dict with keys: uri, cid, text, created_at, url.
        """
        if not self.is_available:
            logger.debug("Bluesky not configured, returning mock post")
            return self._mock_post(text)

        # TODO: Real API call
        # await self._ensure_session()
        # now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/com.atproto.repo.createRecord",
        #         headers={
        #             "Authorization": f"Bearer {self._session['accessJwt']}",
        #         },
        #         json={
        #             "repo": self._session["did"],
        #             "collection": "app.bsky.feed.post",
        #             "record": {
        #                 "$type": "app.bsky.feed.post",
        #                 "text": text,
        #                 "createdAt": now,
        #             },
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "uri": data["uri"],
        #         "cid": data["cid"],
        #         "text": text,
        #         "created_at": now,
        #         "url": (
        #             f"https://bsky.app/profile/{self.handle}/post/"
        #             f"{data['uri'].split('/')[-1]}"
        #         ),
        #     }
        logger.info("Bluesky post: %s...", text[:50])
        return self._mock_post(text)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_post(self, text: str) -> BlueskyPostResult:
        now = datetime.now(UTC).isoformat()
        mock_rkey = "3abc123def456"
        handle = self.handle or "user.bsky.social"
        return {
            "uri": f"at://did:plc:mock123/app.bsky.feed.post/{mock_rkey}",
            "cid": "bafyreimock123",
            "text": text[:300],
            "created_at": now,
            "url": f"https://bsky.app/profile/{handle}/post/{mock_rkey}",
        }
