"""Hacker News research provider — stories + developer comments.

Uses the free HN Algolia API (no authentication required).  Stories
are always collected; comments are gated by
``CollectionConfig.include_hn_comments``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.clients.hn_algolia import HNClient, HNComment, HNStory
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.protocols import CachedCallFn


class HNProvider:
    """Collects Hacker News stories and developer pain-point comments."""

    @property
    def name(self) -> str:
        return "hn_algolia"

    @property
    def is_available(self) -> bool:
        return True

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        if not config.primary_query:
            return RawResearchData()

        client = HNClient()
        stories: list[HNStory] = []
        comments: list[HNComment] = []
        errors: list[str] = []
        pq = config.primary_query

        story_hits = cached_call(
            "hn_stories",
            pq,
            lambda: client.search(pq, tags="story"),
            errors,
            label="HN story search",
        )
        if story_hits is not None:
            stories.extend(story_hits)

        if config.include_hn_comments:
            comment_hits = cached_call(
                "hn_comments",
                pq,
                lambda: client.search_comments(pq),
                errors,
                label="HN comment search",
            )
            if comment_hits is not None:
                comments.extend(comment_hits)

        return RawResearchData(
            hn_stories=stories,
            hn_comments=comments,
            sources_used=["hn_algolia"] if stories or comments else [],
            errors=errors,
        )
