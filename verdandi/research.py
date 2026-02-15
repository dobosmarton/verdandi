"""Research data collection and aggregation.

Central module that coordinates calls to all research API clients,
aggregates results, and formats them for LLM consumption. Follows
a collect-then-synthesize pattern with graceful degradation.

API calls are parallelized via ThreadPoolExecutor — each source
runs in its own thread, reducing wall-clock time from ~60-110s
to ~30-40s (bounded by the slowest source).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, TypeVar

import structlog
from pydantic import BaseModel, ConfigDict, Field

from verdandi.clients.exa import ExaSearchResult
from verdandi.clients.hn_algolia import HNComment, HNStory
from verdandi.clients.perplexity import PerplexityDeepResult, PerplexityResult
from verdandi.clients.serper import SerperRedditResult, SerperResult
from verdandi.clients.tavily import TavilyResearchResult, TavilySearchResult
from verdandi.retry import with_retry

if TYPE_CHECKING:
    from collections.abc import Callable

    from verdandi.cache import ResearchCache
    from verdandi.config import Settings

logger = structlog.get_logger()

_RESEARCH_WORKERS = 6
_T = TypeVar("_T")


class RawResearchData(BaseModel):
    """Accumulated raw results from all research APIs."""

    model_config = ConfigDict(frozen=True)

    tavily_results: list[TavilySearchResult] = Field(default_factory=list)
    tavily_research: TavilyResearchResult | None = None
    serper_results: list[SerperResult] = Field(default_factory=list)
    serper_reddit: list[SerperRedditResult] = Field(default_factory=list)
    exa_results: list[ExaSearchResult] = Field(default_factory=list)
    perplexity_answer: PerplexityResult | None = None
    perplexity_deep_answer: PerplexityDeepResult | None = None
    hn_stories: list[HNStory] = Field(default_factory=list)
    hn_comments: list[HNComment] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def has_data(self) -> bool:
        """Check if any source returned data."""
        return bool(
            self.tavily_results
            or self.tavily_research
            or self.serper_results
            or self.serper_reddit
            or self.exa_results
            or self.perplexity_answer
            or self.hn_stories
            or self.hn_comments
        )


# ---------------------------------------------------------------------------
# Batch result containers for parallel collection
# ---------------------------------------------------------------------------
# Each _*Batch is returned by one thread in the ThreadPoolExecutor.
# Frozen + slots for immutability and low overhead.


@dataclass(frozen=True, slots=True)
class _TavilySearchBatch:
    results: list[TavilySearchResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _TavilyResearchBatch:
    research: TavilyResearchResult | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _SerperBatch:
    results: list[SerperResult] = field(default_factory=list)
    reddit: list[SerperRedditResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ExaBatch:
    results: list[ExaSearchResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _PerplexityBatch:
    answer: PerplexityResult | None = None
    deep_answer: PerplexityDeepResult | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _HNBatch:
    stories: list[HNStory] = field(default_factory=list)
    comments: list[HNComment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ResearchCollector:
    """Calls all available research APIs with graceful degradation.

    Each API call is wrapped in try/except. Failures are logged and
    collected in the errors list, but never abort the collection.
    Only raises if ALL sources fail to return any data.

    API calls run in parallel via ThreadPoolExecutor (one thread per
    source group). Optionally caches results in Redis when configured.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: ResearchCache | None = None
        if settings.research_cache_enabled and settings.redis_url:
            try:
                from verdandi.cache import ResearchCache

                cache = ResearchCache(settings)
                if cache.ping():
                    self._cache = cache
                    logger.info("Research cache enabled via Redis")
                else:
                    logger.warning("Redis not reachable, caching disabled")
            except Exception as exc:
                logger.warning(
                    "Redis cache init failed, proceeding without cache",
                    error=str(exc),
                )

    def _check_cache(self, source: str, query: str) -> str | None:
        """Check cache. Returns raw JSON string or None."""
        if self._cache is None:
            return None
        try:
            return self._cache.get(source, query)
        except Exception:
            logger.debug("cache_read_failed", source=source)
            return None

    def _save_cache(self, source: str, query: str, data_json: str) -> None:
        """Save to cache. Fails silently."""
        if self._cache is None:
            return
        try:
            self._cache.set(source, query, data_json)
        except Exception:
            logger.debug("cache_write_failed", source=source)

    def _cached_call(
        self,
        source: str,
        query: str,
        fn: Callable[[], _T],
        errors: list[str],
        *,
        label: str = "",
    ) -> _T | None:
        """Execute fn with cache-check, retry, cache-save, and error collection.

        Returns the deserialized cached value on hit, the result of fn()
        on miss, or None on failure (appending to errors).
        """
        cached_json = self._check_cache(source, query)
        if cached_json is not None:
            return json.loads(cached_json)  # type: ignore[no-any-return]

        error_label = label or source
        try:
            result = with_retry(fn=fn, max_retries=2, base_delay=1.0)
            self._save_cache(source, query, json.dumps(result))
            return result
        except Exception as exc:
            errors.append(f"{error_label} failed for '{query}': {exc}")
            logger.warning(f"{error_label} failed", query=query, error=str(exc))
            return None

    # ------------------------------------------------------------------
    # Per-source collection methods (each runs in its own thread)
    # ------------------------------------------------------------------

    def _collect_tavily_search(self, queries: list[str]) -> _TavilySearchBatch:
        """Tavily web search across top queries."""
        from verdandi.clients.tavily import TavilyClient

        tavily = TavilyClient(api_key=self.settings.tavily_api_key)
        if not tavily.is_available:
            logger.debug("Tavily not configured, skipping")
            return _TavilySearchBatch()

        results: list[TavilySearchResult] = []
        errors: list[str] = []
        for q in queries[:3]:
            hits = self._cached_call(
                "tavily", q, partial(tavily.search, q, max_results=5), errors, label="Tavily search"
            )
            if hits is not None:
                results.extend(hits)

        return _TavilySearchBatch(results=results, errors=errors)

    def _collect_tavily_research(self, tavily_research_query: str) -> _TavilyResearchBatch:
        """Tavily multi-step deep research."""
        from verdandi.clients.tavily import TavilyClient

        tavily = TavilyClient(api_key=self.settings.tavily_api_key)
        if not tavily.is_available or not tavily_research_query:
            return _TavilyResearchBatch()

        errors: list[str] = []
        result = self._cached_call(
            "tavily_research",
            tavily_research_query,
            lambda: tavily.research(tavily_research_query),
            errors,
            label="Tavily research",
        )
        return _TavilyResearchBatch(research=result, errors=errors)

    def _collect_serper(
        self,
        queries: list[str],
        primary_query: str,
        include_reddit: bool,
    ) -> _SerperBatch:
        """Serper Google SERP data + Reddit discussions."""
        from verdandi.clients.serper import SerperClient

        serper = SerperClient(api_key=self.settings.serper_api_key)
        if not serper.is_available:
            logger.debug("Serper not configured, skipping")
            return _SerperBatch()

        results: list[SerperResult] = []
        reddit: list[SerperRedditResult] = []
        errors: list[str] = []

        for q in queries[:2]:
            hits = self._cached_call(
                "serper", q, partial(serper.search, q, num=10), errors, label="Serper search"
            )
            if hits is not None:
                results.extend(hits)

        if include_reddit and primary_query:
            reddit_hits = self._cached_call(
                "serper_reddit",
                primary_query,
                lambda: serper.search_reddit(primary_query),
                errors,
                label="Serper Reddit search",
            )
            if reddit_hits is not None:
                reddit.extend(reddit_hits)

        return _SerperBatch(results=results, reddit=reddit, errors=errors)

    def _collect_exa(self, primary_query: str, exa_similar_url: str) -> _ExaBatch:
        """Exa semantic/neural search + find_similar."""
        from verdandi.clients.exa import ExaClient

        exa = ExaClient(api_key=self.settings.exa_api_key)
        if not exa.is_available:
            logger.debug("Exa not configured, skipping")
            return _ExaBatch()

        results: list[ExaSearchResult] = []
        errors: list[str] = []

        if primary_query:
            hits = self._cached_call(
                "exa",
                primary_query,
                lambda: exa.search(primary_query, num_results=5),
                errors,
                label="Exa search",
            )
            if hits is not None:
                results.extend(hits)

        if exa_similar_url:
            similar = self._cached_call(
                "exa_similar",
                exa_similar_url,
                lambda: exa.find_similar(exa_similar_url),
                errors,
                label="Exa find_similar",
            )
            if similar is not None:
                results.extend(
                    {
                        "title": s["title"],
                        "url": s["url"],
                        "text": s["text"],
                        "score": s["score"],
                        "published_date": "",
                        "author": None,
                    }
                    for s in similar
                )

        return _ExaBatch(results=results, errors=errors)

    def _collect_perplexity(self, perplexity_question: str, use_deep: bool) -> _PerplexityBatch:
        """Perplexity synthesized answer with citations."""
        from verdandi.clients.perplexity import PerplexityClient

        perplexity = PerplexityClient(api_key=self.settings.perplexity_api_key)
        if not perplexity.is_available:
            logger.debug("Perplexity not configured, skipping")
            return _PerplexityBatch()
        if not perplexity_question:
            logger.debug("No Perplexity question provided, skipping")
            return _PerplexityBatch()

        errors: list[str] = []
        if use_deep:
            cache_key = f"perplexity_deep:{perplexity_question}"
            result = self._cached_call(
                "perplexity",
                cache_key,
                lambda: perplexity.deep_research(perplexity_question),
                errors,
                label="Perplexity deep_research",
            )
            if result is None:
                return _PerplexityBatch(errors=errors)
            return _PerplexityBatch(answer=result, deep_answer=result, errors=errors)

        basic_result = self._cached_call(
            "perplexity",
            perplexity_question,
            lambda: perplexity.query(perplexity_question),
            errors,
            label="Perplexity query",
        )
        if basic_result is None:
            return _PerplexityBatch(errors=errors)
        return _PerplexityBatch(answer=basic_result, errors=errors)

    def _collect_hn(self, primary_query: str, include_comments: bool) -> _HNBatch:
        """HN Algolia stories + comments (free, no auth)."""
        from verdandi.clients.hn_algolia import HNClient

        if not primary_query:
            return _HNBatch()

        hn = HNClient()
        stories: list[HNStory] = []
        comments: list[HNComment] = []
        errors: list[str] = []

        story_hits = self._cached_call(
            "hn_stories",
            primary_query,
            lambda: hn.search(primary_query, tags="story"),
            errors,
            label="HN story search",
        )
        if story_hits is not None:
            stories.extend(story_hits)

        if include_comments:
            comment_hits = self._cached_call(
                "hn_comments",
                primary_query,
                lambda: hn.search_comments(primary_query),
                errors,
                label="HN comment search",
            )
            if comment_hits is not None:
                comments.extend(comment_hits)

        return _HNBatch(stories=stories, comments=comments, errors=errors)

    # ------------------------------------------------------------------
    # Main collection orchestrator
    # ------------------------------------------------------------------

    def collect(
        self,
        queries: list[str],
        *,
        include_reddit: bool = True,
        include_hn_comments: bool = True,
        perplexity_question: str = "",
        exa_similar_url: str = "",
        tavily_research_query: str = "",
        use_perplexity_deep: bool = False,
    ) -> RawResearchData:
        """Collect research data from all available APIs in parallel.

        Submits all 6 source groups to a ThreadPoolExecutor and gathers
        results. Each source runs in its own thread with independent
        error handling — one source failing never blocks the others.

        Args:
            queries: List of search queries to distribute across APIs.
            include_reddit: Whether to search Reddit via Serper.
            include_hn_comments: Whether to search HN comments.
            perplexity_question: Optional synthesized question for Perplexity.
            exa_similar_url: Optional URL for Exa's find_similar.
            tavily_research_query: Optional query for Tavily's multi-step
                deep research mode (returns summary + sources + follow-ups).
            use_perplexity_deep: If True, use Perplexity Deep Research
                (sonar-deep-research) instead of basic sonar for richer analysis.

        Returns:
            RawResearchData with results from all sources that responded.

        Raises:
            RuntimeError: If no sources returned any data at all.
        """
        primary_query = queries[0] if queries else ""

        with ThreadPoolExecutor(
            max_workers=_RESEARCH_WORKERS, thread_name_prefix="research"
        ) as executor:
            ft_tavily = executor.submit(self._collect_tavily_search, queries)
            ft_tavily_r = executor.submit(self._collect_tavily_research, tavily_research_query)
            ft_serper = executor.submit(
                self._collect_serper, queries, primary_query, include_reddit
            )
            ft_exa = executor.submit(self._collect_exa, primary_query, exa_similar_url)
            ft_perplexity = executor.submit(
                self._collect_perplexity, perplexity_question, use_perplexity_deep
            )
            ft_hn = executor.submit(self._collect_hn, primary_query, include_hn_comments)

        # All futures complete after exiting the `with` block
        tavily_batch = ft_tavily.result()
        tavily_r_batch = ft_tavily_r.result()
        serper_batch = ft_serper.result()
        exa_batch = ft_exa.result()
        perplexity_batch = ft_perplexity.result()
        hn_batch = ft_hn.result()

        # Merge sources_used
        sources_used: list[str] = []
        if tavily_batch.results or tavily_r_batch.research:
            sources_used.append("tavily")
        if serper_batch.results or serper_batch.reddit:
            sources_used.append("serper")
        if exa_batch.results:
            sources_used.append("exa")
        if perplexity_batch.answer:
            sources_used.append("perplexity")
        if hn_batch.stories or hn_batch.comments:
            sources_used.append("hn_algolia")

        # Merge errors
        errors: list[str] = [
            *tavily_batch.errors,
            *tavily_r_batch.errors,
            *serper_batch.errors,
            *exa_batch.errors,
            *perplexity_batch.errors,
            *hn_batch.errors,
        ]

        raw = RawResearchData(
            tavily_results=tavily_batch.results,
            tavily_research=tavily_r_batch.research,
            serper_results=serper_batch.results,
            serper_reddit=serper_batch.reddit,
            exa_results=exa_batch.results,
            perplexity_answer=perplexity_batch.answer,
            perplexity_deep_answer=perplexity_batch.deep_answer,
            hn_stories=hn_batch.stories,
            hn_comments=hn_batch.comments,
            sources_used=sources_used,
            errors=errors,
        )

        logger.info(
            "Research collection complete",
            sources_used=sources_used,
            tavily_count=len(tavily_batch.results),
            serper_count=len(serper_batch.results),
            reddit_count=len(serper_batch.reddit),
            exa_count=len(exa_batch.results),
            has_perplexity=perplexity_batch.answer is not None,
            hn_stories=len(hn_batch.stories),
            hn_comments=len(hn_batch.comments),
            error_count=len(errors),
        )

        if not raw.has_data:
            raise RuntimeError(f"All research sources failed. Errors: {'; '.join(errors)}")

        return raw


def format_research_context(raw: RawResearchData) -> str:
    """Format raw research data into a text block for LLM consumption.

    Produces a structured markdown-like document that Claude can use
    to synthesize findings into a structured output.
    """
    sections: list[str] = []

    # Tavily results
    if raw.tavily_results:
        lines = ["## Web Search Results (Tavily)"]
        for tr in raw.tavily_results:
            lines.append(f"- **{tr['title']}** ({tr['url']})")
            lines.append(f"  {tr['content'][:300]}")
        sections.append("\n".join(lines))

    # Tavily deep research
    if raw.tavily_research:
        lines = ["## Deep Research Summary (Tavily Research)"]
        lines.append(raw.tavily_research["summary"])
        if raw.tavily_research["sources"]:
            lines.append("\nSources:")
            for src in raw.tavily_research["sources"]:
                lines.append(f"  - {src['title']} ({src['url']}) [relevance: {src['relevance']}]")
        if raw.tavily_research["follow_up_questions"]:
            lines.append("\nSuggested follow-up questions:")
            for q in raw.tavily_research["follow_up_questions"]:
                lines.append(f"  - {q}")
        sections.append("\n".join(lines))

    # Serper SERP results
    if raw.serper_results:
        lines = ["## Google SERP Results (Serper)"]
        for sr in raw.serper_results:
            lines.append(f"- **{sr['title']}** ({sr['link']})")
            lines.append(f"  {sr['snippet']}")
        sections.append("\n".join(lines))

    # Reddit discussions
    if raw.serper_reddit:
        lines = ["## Reddit Discussions"]
        for rr in raw.serper_reddit:
            lines.append(f"- **r/{rr['subreddit']}**: {rr['title']} ({rr['link']})")
            lines.append(f"  {rr['snippet']}")
        sections.append("\n".join(lines))

    # Exa semantic results
    if raw.exa_results:
        lines = ["## Semantic Search Results (Exa)"]
        for er in raw.exa_results:
            lines.append(f"- **{er['title']}** (score: {er['score']}) ({er['url']})")
            exa_text = er["text"]
            if exa_text:
                lines.append(f"  {exa_text[:300]}")
        sections.append("\n".join(lines))

    # Perplexity synthesis (deep research takes priority over basic)
    if raw.perplexity_deep_answer:
        lines = ["## AI Deep Research (Perplexity Deep Research)"]
        lines.append(raw.perplexity_deep_answer["answer"])
        lines.append(f"\n(Analyzed {raw.perplexity_deep_answer['sources_analyzed']} sources)")
        if raw.perplexity_deep_answer["citations"]:
            lines.append("\nCitations:")
            for citation_url in raw.perplexity_deep_answer["citations"]:
                lines.append(f"  - {citation_url}")
        sections.append("\n".join(lines))
    elif raw.perplexity_answer:
        lines = ["## AI-Synthesized Research (Perplexity)"]
        lines.append(raw.perplexity_answer["answer"])
        if raw.perplexity_answer["citations"]:
            lines.append("\nCitations:")
            for citation_url in raw.perplexity_answer["citations"]:
                lines.append(f"  - {citation_url}")
        sections.append("\n".join(lines))

    # HN stories
    if raw.hn_stories:
        lines = ["## Hacker News Discussions"]
        for hs in raw.hn_stories:
            url_part = f" ({hs['url']})" if hs.get("url") else ""
            lines.append(f"- **{hs['title']}**{url_part}")
            lines.append(
                f"  {hs['points']} points, {hs['num_comments']} comments by {hs['author']}"
            )
        sections.append("\n".join(lines))

    # HN comments (pain points)
    if raw.hn_comments:
        lines = ["## Developer Pain Points (HN Comments)"]
        for hc in raw.hn_comments:
            comment_text = hc["comment_text"][:400] if hc.get("comment_text") else ""
            lines.append(f"- **{hc['author']}** (in: {hc['story_title']}):")
            lines.append(f'  "{comment_text}"')
        sections.append("\n".join(lines))

    # Sources summary
    lines = [f"\n---\n**Sources used**: {', '.join(raw.sources_used)}"]
    if raw.errors:
        lines.append(f"**Errors encountered**: {len(raw.errors)}")
        for err in raw.errors:
            lines.append(f"  - {err}")
    sections.append("\n".join(lines))

    return "\n\n".join(sections)
