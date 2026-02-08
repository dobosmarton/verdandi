"""Client stub for Porkbun domain registrar API.

Porkbun offers programmatic domain registration with competitive pricing:
.com at $7.97/yr, .xyz at ~$2/yr. Includes free WHOIS privacy, email
forwarding, and SSL. API docs: https://porkbun.com/api/json/v3/documentation
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class PorkbunClient:
    """Porkbun API client. Returns mock data until API keys are configured."""

    def __init__(self, api_key: str = "", secret_key: str = "") -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.porkbun.com/api/json/v3"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _auth_payload(self) -> dict:
        """Return the authentication payload required by all Porkbun endpoints."""
        return {
            "apikey": self.api_key,
            "secretapikey": self.secret_key,
        }

    async def check_availability(self, domain: str) -> dict:
        """Check if a domain is available for registration.

        Args:
            domain: Full domain name (e.g., "myproject.xyz").

        Returns:
            Dict with keys: domain, available (bool), price, currency.
        """
        if not self.is_available:
            logger.debug("Porkbun not configured, returning mock availability")
            return self._mock_check_availability(domain)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/domain/checkAvailability/{domain}",
        #         json=self._auth_payload(),
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "domain": domain,
        #         "available": data.get("status") == "SUCCESS"
        #                      and data.get("avail", "") == "yes",
        #         "price": data.get("pricing", {}).get("registration"),
        #         "currency": "USD",
        #     }
        logger.info("Porkbun check availability: %s", domain)
        return self._mock_check_availability(domain)

    async def register_domain(self, domain: str) -> dict:
        """Purchase and register a domain.

        Args:
            domain: Full domain name to register (e.g., "myproject.xyz").

        Returns:
            Dict with keys: domain, registered (bool), expiry_date,
            nameservers, price_paid.
        """
        if not self.is_available:
            logger.debug("Porkbun not configured, returning mock registration")
            return self._mock_register_domain(domain)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/domain/create/{domain}",
        #         json=self._auth_payload(),
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "domain": domain,
        #         "registered": data.get("status") == "SUCCESS",
        #         "expiry_date": data.get("expiry_date"),
        #         "nameservers": data.get("defaultNameservers", []),
        #         "price_paid": data.get("total"),
        #     }
        logger.info("Porkbun register domain: %s", domain)
        return self._mock_register_domain(domain)

    async def set_nameservers(self, domain: str, nameservers: list[str]) -> dict:
        """Update nameservers for a domain (e.g., point to Cloudflare).

        Args:
            domain: Domain to update.
            nameservers: List of nameserver hostnames (e.g.,
                ["ns1.cloudflare.com", "ns2.cloudflare.com"]).

        Returns:
            Dict with keys: domain, nameservers, updated (bool).
        """
        if not self.is_available:
            logger.debug("Porkbun not configured, returning mock nameserver update")
            return self._mock_set_nameservers(domain, nameservers)

        # TODO: Real API call
        # payload = self._auth_payload()
        # payload["ns"] = nameservers
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/domain/updateNs/{domain}",
        #         json=payload,
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "domain": domain,
        #         "nameservers": nameservers,
        #         "updated": data.get("status") == "SUCCESS",
        #     }
        logger.info("Porkbun set nameservers: %s -> %s", domain, nameservers)
        return self._mock_set_nameservers(domain, nameservers)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_check_availability(self, domain: str) -> dict:
        tld = domain.rsplit(".", 1)[-1] if "." in domain else "com"
        prices = {"com": "7.97", "xyz": "2.00", "site": "1.00", "io": "29.88"}
        return {
            "domain": domain,
            "available": True,
            "price": prices.get(tld, "9.99"),
            "currency": "USD",
        }

    def _mock_register_domain(self, domain: str) -> dict:
        tld = domain.rsplit(".", 1)[-1] if "." in domain else "com"
        prices = {"com": "7.97", "xyz": "2.00", "site": "1.00", "io": "29.88"}
        return {
            "domain": domain,
            "registered": True,
            "expiry_date": "2026-02-07T00:00:00Z",
            "nameservers": [
                "ns1.porkbun.com",
                "ns2.porkbun.com",
            ],
            "price_paid": prices.get(tld, "9.99"),
        }

    def _mock_set_nameservers(self, domain: str, nameservers: list[str]) -> dict:
        return {
            "domain": domain,
            "nameservers": nameservers,
            "updated": True,
        }
