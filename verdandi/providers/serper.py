"""Serper research provider — Google SERP data + Reddit discussions.

Collects structured search results across up to 2 queries and optionally
searches Reddit via ``site:reddit.com`` queries.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from verdandi.clients.serper import SerperClient, SerperRedditResult, SerperResult
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import CachedCallFn


class SerperProvider:
    """Collects Google SERP results and Reddit discussions from Serper."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.serper_api_key

    @property
    def name(self) -> str:
        return "serper"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        client = SerperClient(api_key=self._api_key)
        results: list[SerperResult] = []
        reddit: list[SerperRedditResult] = []
        errors: list[str] = []

        for q in config.queries[:2]:
            hits = cached_call(
                "serper",
                q,
                partial(client.search, q, num=10),
                errors,
                label="Serper search",
            )
            if hits is not None:
                results.extend(hits)

        if config.include_reddit and config.primary_query:
            pq = config.primary_query
            reddit_hits = cached_call(
                "serper_reddit",
                pq,
                lambda: client.search_reddit(pq),
                errors,
                label="Serper Reddit search",
            )
            if reddit_hits is not None:
                reddit.extend(reddit_hits)

        return RawResearchData(
            serper_results=results,
            serper_reddit=reddit,
            sources_used=["serper"] if results or reddit else [],
            errors=errors,
        )
