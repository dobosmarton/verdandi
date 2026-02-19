"""Client for Firecrawl web scraping API.

Firecrawl converts web pages into clean LLM-ready markdown.
Free tier: 500 credits/month.  Paid: $16/month for 3,000 credits.

Used for deep competitor analysis — scraping pricing pages, feature
lists, and about pages that search APIs only return snippets for.
"""

from __future__ import annotations

import httpx
import structlog
from typing_extensions import TypedDict

logger = structlog.get_logger()


class FirecrawlPage(TypedDict):
    """Scraped page content with metadata."""

    url: str
    title: str
    description: str
    markdown: str
    status_code: int
    word_count: int


class FirecrawlClient:
    """Firecrawl API client for page scraping and site mapping.

    Returns mock data when API key is not configured.
    """

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://api.firecrawl.dev"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def scrape(self, url: str) -> FirecrawlPage:
        """Scrape a single URL and return clean markdown + metadata.

        Args:
            url: The URL to scrape.

        Returns:
            Dict with keys: url, title, description, markdown,
            status_code, word_count.
        """
        if not self.is_available:
            logger.debug("Firecrawl not configured, returning mock data")
            return self._mock_scrape(url)

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.base_url}/v2/scrape",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"url": url, "formats": ["markdown"]},
                )
                resp.raise_for_status()
                body: dict[str, object] = resp.json()

                if not body.get("success", False):
                    logger.warning("Firecrawl scrape unsuccessful", url=url)
                    return self._mock_scrape(url)

                data = body.get("data", {})
                if not isinstance(data, dict):
                    data = {}

                metadata = data.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}

                markdown = str(data.get("markdown", ""))

                result: FirecrawlPage = {
                    "url": str(metadata.get("sourceURL", url)),
                    "title": str(metadata.get("title", "")),
                    "description": str(
                        metadata.get("description", "") or metadata.get("ogDescription", "")
                    ),
                    "markdown": markdown,
                    "status_code": int(metadata.get("statusCode", 200)),
                    "word_count": len(markdown.split()),
                }
                return result
        except httpx.HTTPError as exc:
            logger.warning(
                "Firecrawl scrape API error",
                url=url,
                error=str(exc),
            )
            raise

    def map_site(
        self,
        url: str,
        search: str = "",
        limit: int = 50,
    ) -> list[str]:
        """Discover URLs on a website via sitemap + link crawling.

        Args:
            url: The root URL of the site to map.
            search: Optional search term to filter discovered URLs
                (e.g. "pricing features about").
            limit: Maximum number of URLs to return.

        Returns:
            List of discovered URL strings.
        """
        if not self.is_available:
            logger.debug("Firecrawl not configured, returning mock data")
            return self._mock_map(url)

        try:
            payload: dict[str, object] = {"url": url, "limit": limit}
            if search:
                payload["search"] = search

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base_url}/v2/map",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                body: dict[str, object] = resp.json()

                if not body.get("success", False):
                    logger.warning("Firecrawl map unsuccessful", url=url)
                    return self._mock_map(url)

                raw_links = body.get("links", [])
                if not isinstance(raw_links, list):
                    return []
                # /v2/map returns objects {"url": "...", "title": "..."}
                # or plain URL strings depending on API version.
                urls: list[str] = []
                for link in raw_links[:limit]:
                    if isinstance(link, dict):
                        link_url = link.get("url", "")
                        if link_url:
                            urls.append(str(link_url))
                    elif isinstance(link, str) and link:
                        urls.append(link)
                return urls
        except httpx.HTTPError as exc:
            logger.warning(
                "Firecrawl map API error",
                url=url,
                error=str(exc),
            )
            raise

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_scrape(self, url: str) -> FirecrawlPage:
        return {
            "url": url,
            "title": f"Mock page for {url}",
            "description": "Mock description for competitor analysis",
            "markdown": (
                f"# Mock Page Content\n\n"
                f"This is mock scraped content for {url}. "
                f"In production, this would contain the full page "
                f"content in clean markdown format.\n\n"
                f"## Pricing\n\n"
                f"- Free tier: Limited features\n"
                f"- Pro: $29/month\n"
                f"- Enterprise: Contact sales\n"
            ),
            "status_code": 200,
            "word_count": 42,
        }

    def _mock_map(self, url: str) -> list[str]:
        base = url.rstrip("/")
        return [
            f"{base}/pricing",
            f"{base}/features",
            f"{base}/about",
            f"{base}/blog",
        ]
