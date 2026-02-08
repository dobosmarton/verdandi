"""Client stub for EmailOctopus API.

EmailOctopus free tier: 2,500 subscribers and 10,000 emails/month
with full REST API access. Used for collecting email signups from
landing pages to validate product interest.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import structlog

logger = structlog.get_logger()


class EmailList(TypedDict):
    id: str
    name: str
    created_at: str
    double_opt_in: bool


class EmailContact(TypedDict):
    id: str
    email_address: str
    status: str
    list_id: str


class EmailListStats(TypedDict):
    id: str
    name: str
    total_contacts: int
    subscribed: int
    unsubscribed: int
    pending: int
    bounced: int


class EmailOctopusClient:
    """EmailOctopus API client. Returns mock data until API key is configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://emailoctopus.com/api/1.6"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def create_list(self, name: str) -> EmailList:
        """Create a new mailing list for an experiment.

        Args:
            name: Name for the mailing list (e.g., "myproject-waitlist").

        Returns:
            Dict with keys: id, name, created_at, double_opt_in.
        """
        if not self.is_available:
            logger.debug("EmailOctopus not configured, returning mock list")
            return self._mock_create_list(name)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/lists",
        #         json={
        #             "api_key": self.api_key,
        #             "name": name,
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "id": data["id"],
        #         "name": data["name"],
        #         "created_at": data["created_at"],
        #         "double_opt_in": data.get("double_opt_in", False),
        #     }
        logger.info("EmailOctopus create list: %s", name)
        return self._mock_create_list(name)

    async def add_contact(self, list_id: str, email: str) -> EmailContact:
        """Add a contact (email signup) to a mailing list.

        Args:
            list_id: ID of the target mailing list.
            email: Email address to add.

        Returns:
            Dict with keys: id, email_address, status, list_id.
        """
        if not self.is_available:
            logger.debug("EmailOctopus not configured, returning mock contact")
            return self._mock_add_contact(list_id, email)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/lists/{list_id}/contacts",
        #         json={
        #             "api_key": self.api_key,
        #             "email_address": email,
        #             "status": "SUBSCRIBED",
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "id": data["id"],
        #         "email_address": data["email_address"],
        #         "status": data["status"],
        #         "list_id": list_id,
        #     }
        logger.info("EmailOctopus add contact to list %s: %s", list_id, email)
        return self._mock_add_contact(list_id, email)

    async def get_list_stats(self, list_id: str) -> EmailListStats:
        """Get statistics for a mailing list.

        Used to track email signup counts for go/no-go decisions.

        Args:
            list_id: ID of the mailing list.

        Returns:
            Dict with keys: id, name, total_contacts, subscribed,
            unsubscribed, pending, bounced.
        """
        if not self.is_available:
            logger.debug("EmailOctopus not configured, returning mock stats")
            return self._mock_get_list_stats(list_id)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         f"{self.base_url}/lists/{list_id}",
        #         params={"api_key": self.api_key},
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     counts = data.get("counts", {})
        #     return {
        #         "id": data["id"],
        #         "name": data["name"],
        #         "total_contacts": counts.get("total", 0),
        #         "subscribed": counts.get("subscribed", 0),
        #         "unsubscribed": counts.get("unsubscribed", 0),
        #         "pending": counts.get("pending", 0),
        #         "bounced": counts.get("bounced", 0),
        #     }
        logger.info("EmailOctopus get list stats: %s", list_id)
        return self._mock_get_list_stats(list_id)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_create_list(self, name: str) -> EmailList:
        return {
            "id": f"mock-list-{name.replace(' ', '-').lower()}",
            "name": name,
            "created_at": datetime.now(UTC).isoformat(),
            "double_opt_in": False,
        }

    def _mock_add_contact(self, list_id: str, email: str) -> EmailContact:
        return {
            "id": f"mock-contact-{email.split('@')[0]}",
            "email_address": email,
            "status": "SUBSCRIBED",
            "list_id": list_id,
        }

    def _mock_get_list_stats(self, list_id: str) -> EmailListStats:
        return {
            "id": list_id,
            "name": "Mock Waitlist",
            "total_contacts": 47,
            "subscribed": 42,
            "unsubscribed": 3,
            "pending": 1,
            "bounced": 1,
        }
