"""Client stub for Umami analytics API.

Umami is a self-hosted, privacy-focused analytics platform.
Completely free when self-hosted, GDPR-compliant, no cookies.
REST API for programmatic data retrieval and website management.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()


class UmamiClient:
    """Umami API client. Returns mock data until instance URL and key are configured."""

    def __init__(self, base_url: str = "", api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.api_key = api_key

    @property
    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_website(self, name: str, domain: str) -> dict:
        """Register a new website in Umami for tracking.

        Args:
            name: Display name for the website.
            domain: Domain of the website (e.g., "myproject.com").

        Returns:
            Dict with keys: id, name, domain, tracking_code.
            tracking_code is the <script> tag to inject in the landing page.
        """
        if not self.is_available:
            logger.debug("Umami not configured, returning mock website")
            return self._mock_create_website(name, domain)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/api/websites",
        #         headers=self._headers(),
        #         json={"name": name, "domain": domain},
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     website_id = data["id"]
        #     tracking_code = (
        #         f'<script defer src="{self.base_url}/script.js" '
        #         f'data-website-id="{website_id}"></script>'
        #     )
        #     return {
        #         "id": website_id,
        #         "name": name,
        #         "domain": domain,
        #         "tracking_code": tracking_code,
        #     }
        logger.info("Umami create website: %s (%s)", name, domain)
        return self._mock_create_website(name, domain)

    async def get_stats(self, website_id: str, start_at: int, end_at: int) -> dict:
        """Get aggregate statistics for a website over a time range.

        Args:
            website_id: UUID of the website in Umami.
            start_at: Start timestamp in milliseconds since epoch.
            end_at: End timestamp in milliseconds since epoch.

        Returns:
            Dict with keys: pageviews, visitors, visits, bounce_rate,
            total_time, avg_time.
        """
        if not self.is_available:
            logger.debug("Umami not configured, returning mock stats")
            return self._mock_get_stats(website_id)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         f"{self.base_url}/api/websites/{website_id}/stats",
        #         headers=self._headers(),
        #         params={"startAt": start_at, "endAt": end_at},
        #     )
        #     resp.raise_for_status()
        #     return resp.json()
        logger.info(
            "Umami get stats: website=%s, range=%d-%d",
            website_id,
            start_at,
            end_at,
        )
        return self._mock_get_stats(website_id)

    async def get_events(self, website_id: str) -> list[dict]:
        """Get custom events (CTA clicks, form submissions, etc.).

        Events are tracked in the landing page via umami.track('event-name').

        Args:
            website_id: UUID of the website in Umami.

        Returns:
            List of event dicts with keys: event_name, count, last_at.
        """
        if not self.is_available:
            logger.debug("Umami not configured, returning mock events")
            return self._mock_get_events(website_id)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         f"{self.base_url}/api/websites/{website_id}/events",
        #         headers=self._headers(),
        #     )
        #     resp.raise_for_status()
        #     return resp.json()
        logger.info("Umami get events: website=%s", website_id)
        return self._mock_get_events(website_id)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_create_website(self, name: str, domain: str) -> dict:
        mock_id = f"mock-{domain.replace('.', '-')}"
        umami_url = self.base_url or "https://analytics.example.com"
        return {
            "id": mock_id,
            "name": name,
            "domain": domain,
            "tracking_code": (
                f'<script defer src="{umami_url}/script.js" data-website-id="{mock_id}"></script>'
            ),
        }

    def _mock_get_stats(self, website_id: str) -> dict:
        return {
            "pageviews": {"value": 847, "change": 23},
            "visitors": {"value": 312, "change": 15},
            "visits": {"value": 401, "change": 18},
            "bounce_rate": {"value": 62.4, "change": -3.2},
            "total_time": {"value": 145200, "change": 8},
            "avg_time": {"value": 362, "change": 12},
        }

    def _mock_get_events(self, website_id: str) -> list[dict]:
        now = datetime.now(UTC).isoformat()
        return [
            {"event_name": "cta-click", "count": 47, "last_at": now},
            {"event_name": "email-signup", "count": 23, "last_at": now},
            {"event_name": "pricing-view", "count": 89, "last_at": now},
            {"event_name": "faq-expand", "count": 34, "last_at": now},
        ]
