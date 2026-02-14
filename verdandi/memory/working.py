"""Ephemeral working memory for agent research steps.

ResearchSession accumulates raw research data within a single step,
deduplicates by URL/story ID, and formats a unified context for the LLM.
It also optionally threads LLM conversation history for multi-turn
refinement within the same step.

The session is discarded after the step completes — the orchestrator
decides what to persist to long-term memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from verdandi.research import RawResearchData, format_research_context

if TYPE_CHECKING:
    from verdandi.clients.exa import ExaSearchResult
    from verdandi.clients.hn_algolia import HNComment, HNStory
    from verdandi.clients.perplexity import PerplexityResult
    from verdandi.clients.serper import SerperRedditResult, SerperResult
    from verdandi.clients.tavily import TavilySearchResult

logger = structlog.get_logger()


class ResearchSession:
    """Ephemeral working memory for a single research step.

    Accumulates research data from multiple ``collect()`` calls,
    deduplicates results by URL or story ID, and provides a
    formatted context string for LLM consumption.

    Usage::

        session = ResearchSession("My Idea", "developer-tools")
        session.ingest(collector.collect(queries_1, ...))
        session.ingest(collector.collect(queries_2, ...))  # merge & dedup
        prompt = session.formatted_context
    """

    def __init__(self, idea_title: str, idea_category: str) -> None:
        self.idea_title = idea_title
        self.idea_category = idea_category

        # Accumulated raw data (mutable lists for merging)
        self._tavily: list[TavilySearchResult] = []
        self._serper: list[SerperResult] = []
        self._serper_reddit: list[SerperRedditResult] = []
        self._exa: list[ExaSearchResult] = []
        self._perplexity: PerplexityResult | None = None
        self._hn_stories: list[HNStory] = []
        self._hn_comments: list[HNComment] = []
        self._sources_used: list[str] = []
        self._errors: list[str] = []

        # Dedup tracking
        self._seen_urls: set[str] = set()
        self._seen_hn_ids: set[str] = set()

        # LLM history threading (for multi-turn refinement within step)
        self._llm_history: list[Any] = []

    def ingest(self, raw: RawResearchData) -> None:
        """Merge new research data, deduplicating by URL/story ID.

        Can be called multiple times to accumulate data from different
        query batches or research rounds.
        """
        # Tavily results — dedup by URL
        for tav in raw.tavily_results:
            url = tav.get("url", "")
            if url and url in self._seen_urls:
                continue
            if url:
                self._seen_urls.add(url)
            self._tavily.append(tav)

        # Serper results — dedup by link
        for serp in raw.serper_results:
            link = serp.get("link", "")
            if link and link in self._seen_urls:
                continue
            if link:
                self._seen_urls.add(link)
            self._serper.append(serp)

        # Serper Reddit — dedup by link
        for sr in raw.serper_reddit:
            link = sr.get("link", "")
            if link and link in self._seen_urls:
                continue
            if link:
                self._seen_urls.add(link)
            self._serper_reddit.append(sr)

        # Exa results — dedup by URL
        for exa_r in raw.exa_results:
            url = exa_r.get("url", "")
            if url and url in self._seen_urls:
                continue
            if url:
                self._seen_urls.add(url)
            self._exa.append(exa_r)

        # Perplexity — keep latest answer (overwrite)
        if raw.perplexity_answer is not None:
            self._perplexity = raw.perplexity_answer

        # HN stories — dedup by objectID
        for story in raw.hn_stories:
            obj_id = str(story.get("objectID", ""))
            if obj_id and obj_id in self._seen_hn_ids:
                continue
            if obj_id:
                self._seen_hn_ids.add(obj_id)
            self._hn_stories.append(story)

        # HN comments — dedup by objectID
        for comment in raw.hn_comments:
            obj_id = str(comment.get("objectID", ""))
            if obj_id and obj_id in self._seen_hn_ids:
                continue
            if obj_id:
                self._seen_hn_ids.add(obj_id)
            self._hn_comments.append(comment)

        # Merge sources and errors (dedup sources)
        for src in raw.sources_used:
            if src not in self._sources_used:
                self._sources_used.append(src)
        self._errors.extend(raw.errors)

        logger.debug(
            "Research session ingested",
            idea=self.idea_title,
            tavily=len(self._tavily),
            serper=len(self._serper),
            exa=len(self._exa),
            hn_stories=len(self._hn_stories),
            hn_comments=len(self._hn_comments),
        )

    @property
    def has_data(self) -> bool:
        """Check if the session has accumulated any research data."""
        return bool(
            self._tavily
            or self._serper
            or self._serper_reddit
            or self._exa
            or self._perplexity
            or self._hn_stories
            or self._hn_comments
        )

    def to_raw(self) -> RawResearchData:
        """Convert accumulated data back to RawResearchData for formatting."""
        return RawResearchData(
            tavily_results=self._tavily,
            serper_results=self._serper,
            serper_reddit=self._serper_reddit,
            exa_results=self._exa,
            perplexity_answer=self._perplexity,
            hn_stories=self._hn_stories,
            hn_comments=self._hn_comments,
            sources_used=self._sources_used,
            errors=self._errors,
        )

    @property
    def formatted_context(self) -> str:
        """Format accumulated data into LLM-consumable text.

        Uses the same format_research_context() as the collector,
        but on the deduplicated accumulated data.
        """
        return format_research_context(self.to_raw())

    def add_llm_turn(self, messages: list[Any]) -> None:
        """Record LLM conversation messages for multi-turn refinement.

        Useful when a step performs multiple LLM calls (e.g., Phase 1
        discovery then Phase 2 synthesis) and wants to thread history.
        """
        self._llm_history.extend(messages)

    @property
    def llm_history(self) -> list[Any]:
        """Retrieve the accumulated LLM conversation history."""
        return list(self._llm_history)

    @property
    def total_results(self) -> int:
        """Total number of deduplicated results across all sources."""
        return (
            len(self._tavily)
            + len(self._serper)
            + len(self._serper_reddit)
            + len(self._exa)
            + len(self._hn_stories)
            + len(self._hn_comments)
            + (1 if self._perplexity else 0)
        )
