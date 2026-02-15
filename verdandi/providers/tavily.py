"""Tavily research provider — web search + deep research.

Collects search results across up to 3 queries and optionally runs
Tavily's multi-step deep research mode.  Both are funnelled through
the shared ``cached_call`` callback for caching + retry.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from verdandi.clients.tavily import TavilyClient, TavilySearchResult
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import CachedCallFn


class TavilyProvider:
    """Collects web search results and optional deep research from Tavily."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.tavily_api_key

    @property
    def name(self) -> str:
        return "tavily"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        client = TavilyClient(api_key=self._api_key)
        errors: list[str] = []
        results: list[TavilySearchResult] = []

        for q in config.queries[:3]:
            hits = cached_call(
                "tavily",
                q,
                partial(client.search, q, max_results=5),
                errors,
                label="Tavily search",
            )
            if hits is not None:
                results.extend(hits)

        research = None
        if config.tavily_research_query:
            query = config.tavily_research_query
            research = cached_call(
                "tavily_research",
                query,
                lambda: client.research(query),
                errors,
                label="Tavily research",
            )

        return RawResearchData(
            tavily_results=results,
            tavily_research=research,
            sources_used=["tavily"] if results or research else [],
            errors=errors,
        )
