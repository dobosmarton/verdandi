"""Firecrawl research provider — competitor website deep-dive.

Unlike other providers that return search snippets, Firecrawl scrapes
full competitor pages (pricing, features, about) to extract details
that search APIs cannot provide.  Activates only when competitor URLs
are supplied in ``CollectionConfig.competitor_urls`` — typically in
follow-up research rounds after Round 1 discovers competitor domains.

Strategy:
1. For each competitor URL, call ``map_site()`` with a targeted search
   to discover high-value pages (pricing, features, about, etc.)
2. Filter and cap discovered pages to stay within credit budget.
3. Scrape the top pages and return ``FirecrawlPage`` results.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog

from verdandi.clients.firecrawl import FirecrawlClient, FirecrawlPage
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import CachedCallFn

logger = structlog.get_logger()

# High-value page path patterns for competitor analysis
_HIGH_VALUE_PATHS: frozenset[str] = frozenset(
    {
        "pricing",
        "plans",
        "features",
        "about",
        "changelog",
        "customers",
        "case-studies",
        "case-study",
        "integrations",
        "enterprise",
        "compare",
        "vs",
        "alternatives",
    }
)

# Max pages to scrape per competitor (controls credit usage)
_MAX_PAGES_PER_COMPETITOR: int = 3

# Max total competitors to crawl per collection pass
_MAX_COMPETITORS: int = 5


def _is_high_value_url(url: str) -> bool:
    """Check if a URL path contains a high-value segment."""
    path = urlparse(url).path.lower().strip("/")
    segments = path.split("/")
    return any(seg in _HIGH_VALUE_PATHS for seg in segments)


def _prioritize_urls(urls: list[str], max_count: int) -> list[str]:
    """Sort URLs by value: high-value paths first, then by path depth."""
    high_value: list[str] = []
    other: list[str] = []
    for url in urls:
        if _is_high_value_url(url):
            high_value.append(url)
        else:
            other.append(url)
    # Prefer shorter paths within each group (more likely to be overview pages)
    high_value.sort(key=lambda u: len(urlparse(u).path))
    other.sort(key=lambda u: len(urlparse(u).path))
    return (high_value + other)[:max_count]


class FirecrawlProvider:
    """Scrapes competitor websites for pricing, features, and positioning."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.firecrawl_api_key

    @property
    def name(self) -> str:
        return "firecrawl"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        # Skip entirely if no competitor URLs provided (Round 1 typically)
        if not config.competitor_urls:
            return RawResearchData()

        client = FirecrawlClient(api_key=self._api_key)
        errors: list[str] = []
        pages: list[FirecrawlPage] = []

        for comp_url in config.competitor_urls[:_MAX_COMPETITORS]:
            # Discover high-value pages via map
            discovered = cached_call(
                "firecrawl_map",
                comp_url,
                partial(
                    client.map_site,
                    comp_url,
                    search="pricing features about plans",
                    limit=20,
                ),
                errors,
                label="Firecrawl map",
            )

            if discovered is None:
                # map failed — try scraping the root URL directly
                page = cached_call(
                    "firecrawl_scrape",
                    comp_url,
                    partial(client.scrape, comp_url),
                    errors,
                    label="Firecrawl scrape",
                )
                if page is not None:
                    pages.append(page)
                continue

            # Filter out invalid URLs (e.g. stale cache entries with dict reprs)
            valid_urls = [u for u in discovered if isinstance(u, str) and u.startswith("http")]

            # Prioritize and cap the discovered URLs
            targets = _prioritize_urls(valid_urls, _MAX_PAGES_PER_COMPETITOR)

            if not targets:
                # No pages discovered — scrape root
                targets = [comp_url]

            for target_url in targets:
                page = cached_call(
                    "firecrawl_scrape",
                    target_url,
                    partial(client.scrape, target_url),
                    errors,
                    label="Firecrawl scrape",
                )
                if page is not None:
                    pages.append(page)

        logger.info(
            "Firecrawl collection complete",
            competitor_count=len(config.competitor_urls[:_MAX_COMPETITORS]),
            pages_scraped=len(pages),
            error_count=len(errors),
        )

        return RawResearchData(
            firecrawl_pages=pages,
            sources_used=["firecrawl"] if pages else [],
            errors=errors,
        )
