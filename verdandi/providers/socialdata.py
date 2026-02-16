"""SocialData research provider — Twitter/X tweets with engagement metrics.

Collects tweets matching the primary query via SocialData.tools API.
Free tier provides 3 req/min (~4,300/month).  Only activates when
``include_twitter`` is set and an API key is configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.clients.socialdata import SocialDataClient, SocialDataTweet
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import CachedCallFn


class SocialDataProvider:
    """Collects Twitter/X tweets with engagement data from SocialData."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.socialdata_api_key

    @property
    def name(self) -> str:
        return "socialdata"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        if not config.include_twitter or not config.primary_query:
            return RawResearchData()

        client = SocialDataClient(api_key=self._api_key)
        results: list[SocialDataTweet] = []
        errors: list[str] = []

        pq = config.primary_query
        hits = cached_call(
            "socialdata",
            pq,
            lambda: client.search(pq, search_type="Top"),
            errors,
            label="SocialData search",
        )
        if hits is not None:
            results.extend(hits)

        return RawResearchData(
            twitter_results=results,
            sources_used=["socialdata"] if results else [],
            errors=errors,
        )
