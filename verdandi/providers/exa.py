"""Exa research provider — semantic search + find_similar.

Collects neural search results and optionally discovers similar sites
to a reference URL.  ``ExaSimilarResult`` is converted to
``ExaSearchResult`` so all Exa data lands in a single typed list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.clients.exa import ExaClient, ExaSearchResult
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import CachedCallFn


class ExaProvider:
    """Collects semantic search results and similar sites from Exa."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.exa_api_key

    @property
    def name(self) -> str:
        return "exa"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        client = ExaClient(api_key=self._api_key)
        results: list[ExaSearchResult] = []
        errors: list[str] = []

        if config.primary_query:
            pq = config.primary_query
            hits = cached_call(
                "exa",
                pq,
                lambda: client.search(pq, num_results=5),
                errors,
                label="Exa search",
            )
            if hits is not None:
                results.extend(hits)

        if config.exa_similar_url:
            url = config.exa_similar_url
            similar = cached_call(
                "exa_similar",
                url,
                lambda: client.find_similar(url),
                errors,
                label="Exa find_similar",
            )
            if similar is not None:
                results.extend(
                    ExaSearchResult(
                        title=s["title"],
                        url=s["url"],
                        text=s["text"],
                        score=s["score"],
                        published_date="",
                        author=None,
                    )
                    for s in similar
                )

        return RawResearchData(
            exa_results=results,
            sources_used=["exa"] if results else [],
            errors=errors,
        )
