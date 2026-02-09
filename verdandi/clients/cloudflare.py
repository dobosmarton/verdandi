"""Client stub for Cloudflare Pages and DNS API.

Cloudflare Pages: unlimited bandwidth, unlimited sites on free tier.
Deploy via Direct Upload API (no Git required). Automatic SSL.
DNS zone management for custom domain setup.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()


class PagesProject(TypedDict):
    name: str
    subdomain: str
    id: str
    created_on: str


class PagesDeployment(TypedDict):
    id: str
    url: str
    environment: str
    created_on: str
    files_uploaded: list[str]


class DnsZone(TypedDict):
    id: str
    name: str
    nameservers: list[str]
    status: str


class DnsRecord(TypedDict):
    id: str
    type: str
    name: str
    content: str
    proxied: bool
    ttl: int


class CloudflareClient:
    """Cloudflare API client. Returns mock data until API token is configured."""

    def __init__(self, api_token: str = "", account_id: str = "") -> None:
        self.api_token = api_token
        self.account_id = account_id
        self.base_url = "https://api.cloudflare.com/client/v4"

    @property
    def is_available(self) -> bool:
        return bool(self.api_token and self.account_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def create_pages_project(self, name: str) -> PagesProject:
        """Create a new Cloudflare Pages project.

        Args:
            name: Project name (used in the default subdomain:
                {name}.pages.dev).

        Returns:
            Dict with keys: name, subdomain, id, created_on.
        """
        if not self.is_available:
            logger.debug("Cloudflare not configured, returning mock project")
            return self._mock_create_pages_project(name)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/accounts/{self.account_id}/pages/projects",
        #         headers=self._headers(),
        #         json={
        #             "name": name,
        #             "production_branch": "main",
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()["result"]
        #     return {
        #         "name": data["name"],
        #         "subdomain": f"{data['name']}.pages.dev",
        #         "id": data["id"],
        #         "created_on": data["created_on"],
        #     }
        logger.info("Cloudflare create Pages project: %s", name)
        return self._mock_create_pages_project(name)

    async def deploy_pages(self, project_name: str, files: dict[str, str]) -> PagesDeployment:
        """Deploy files to a Cloudflare Pages project via Direct Upload.

        Args:
            project_name: Name of the Pages project.
            files: Dict mapping file paths to content strings
                (e.g., {"index.html": "<html>...</html>"}).

        Returns:
            Dict with keys: id, url, environment, created_on, files_uploaded.
        """
        if not self.is_available:
            logger.debug("Cloudflare not configured, returning mock deployment")
            return self._mock_deploy_pages(project_name, files)

        # TODO: Real API call (multipart form upload)
        # The Direct Upload API requires creating a deployment first,
        # then uploading files as a multipart form.
        # async with httpx.AsyncClient() as client:
        #     # Step 1: Create deployment upload
        #     resp = await client.post(
        #         f"{self.base_url}/accounts/{self.account_id}"
        #         f"/pages/projects/{project_name}/deployments",
        #         headers={"Authorization": f"Bearer {self.api_token}"},
        #     )
        #     resp.raise_for_status()
        #     deploy = resp.json()["result"]
        #
        #     # Step 2: Upload files
        #     form_files = []
        #     for path, content in files.items():
        #         form_files.append(("files", (path, content.encode())))
        #     resp = await client.post(
        #         deploy["upload_url"],
        #         files=form_files,
        #     )
        #     resp.raise_for_status()
        #     return resp.json()["result"]
        logger.info(
            "Cloudflare deploy Pages: %s (%d files)",
            project_name,
            len(files),
        )
        return self._mock_deploy_pages(project_name, files)

    async def add_zone(self, domain: str) -> DnsZone:
        """Add a DNS zone for a domain to Cloudflare.

        After adding, configure the domain's nameservers at the registrar
        to point to the Cloudflare nameservers returned.

        Args:
            domain: Domain name to add (e.g., "myproject.com").

        Returns:
            Dict with keys: id, name, nameservers, status.
        """
        if not self.is_available:
            logger.debug("Cloudflare not configured, returning mock zone")
            return self._mock_add_zone(domain)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/zones",
        #         headers=self._headers(),
        #         json={
        #             "name": domain,
        #             "account": {"id": self.account_id},
        #             "type": "full",
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()["result"]
        #     return {
        #         "id": data["id"],
        #         "name": data["name"],
        #         "nameservers": data.get("name_servers", []),
        #         "status": data["status"],
        #     }
        logger.info("Cloudflare add zone: %s", domain)
        return self._mock_add_zone(domain)

    async def add_dns_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
    ) -> DnsRecord:
        """Add a DNS record to a Cloudflare zone.

        Args:
            zone_id: ID of the zone (from add_zone response).
            record_type: DNS record type (e.g., "CNAME", "A", "TXT").
            name: Record name (e.g., "www" or "@").
            content: Record value (e.g., "myproject.pages.dev").

        Returns:
            Dict with keys: id, type, name, content, proxied, ttl.
        """
        if not self.is_available:
            logger.debug("Cloudflare not configured, returning mock DNS record")
            return self._mock_add_dns_record(zone_id, record_type, name, content)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/zones/{zone_id}/dns_records",
        #         headers=self._headers(),
        #         json={
        #             "type": record_type,
        #             "name": name,
        #             "content": content,
        #             "proxied": True,
        #             "ttl": 1,  # Auto
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()["result"]
        #     return {
        #         "id": data["id"],
        #         "type": data["type"],
        #         "name": data["name"],
        #         "content": data["content"],
        #         "proxied": data["proxied"],
        #         "ttl": data["ttl"],
        #     }
        logger.info(
            "Cloudflare add DNS record: %s %s -> %s (zone=%s)",
            record_type,
            name,
            content,
            zone_id,
        )
        return self._mock_add_dns_record(zone_id, record_type, name, content)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_create_pages_project(self, name: str) -> PagesProject:
        return {
            "name": name,
            "subdomain": f"{name}.pages.dev",
            "id": f"mock-project-{name}",
            "created_on": datetime.now(UTC).isoformat(),
        }

    def _mock_deploy_pages(self, project_name: str, files: dict[str, str]) -> PagesDeployment:
        return {
            "id": f"mock-deploy-{project_name}-001",
            "url": f"https://{project_name}.pages.dev",
            "environment": "production",
            "created_on": datetime.now(UTC).isoformat(),
            "files_uploaded": list(files.keys()),
        }

    def _mock_add_zone(self, domain: str) -> DnsZone:
        return {
            "id": f"mock-zone-{domain.replace('.', '-')}",
            "name": domain,
            "nameservers": [
                "arya.ns.cloudflare.com",
                "tim.ns.cloudflare.com",
            ],
            "status": "pending",
        }

    def _mock_add_dns_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
    ) -> DnsRecord:
        return {
            "id": f"mock-record-{name}-{record_type}",
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": True,
            "ttl": 1,
        }
