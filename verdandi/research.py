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
from typing import TYPE_CHECKING, TypeVar

import structlog
from pydantic import BaseModel, ConfigDict, Field

from verdandi.clients.exa import ExaSearchResult
from verdandi.clients.firecrawl import FirecrawlPage
from verdandi.clients.hn_algolia import HNComment, HNStory
from verdandi.clients.perplexity import PerplexityDeepResult, PerplexityResult
from verdandi.clients.serper import SerperRedditResult, SerperResult, SerperTwitterResult
from verdandi.clients.socialdata import SocialDataTweet
from verdandi.clients.tavily import TavilyResearchResult, TavilySearchResult
from verdandi.retry import with_retry

if TYPE_CHECKING:
    from collections.abc import Callable

    from verdandi.cache import ResearchCache
    from verdandi.config import Settings
    from verdandi.protocols import ResearchProviderPort

logger = structlog.get_logger()

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class CollectionConfig:
    """Immutable collection parameters passed to each provider.

    Bundles the kwargs of ``ResearchCollector.collect()`` so providers
    can read only the fields they need without knowing the full API.
    """

    queries: list[str]
    primary_query: str
    include_reddit: bool = True
    include_twitter: bool = True
    include_hn_comments: bool = True
    perplexity_question: str = ""
    exa_similar_url: str = ""
    tavily_research_query: str = ""
    use_perplexity_deep: bool = False
    competitor_urls: list[str] = field(default_factory=list)


class RawResearchData(BaseModel):
    """Accumulated raw results from all research APIs."""

    model_config = ConfigDict(frozen=True)

    tavily_results: list[TavilySearchResult] = Field(default_factory=list)
    tavily_research: TavilyResearchResult | None = None
    serper_results: list[SerperResult] = Field(default_factory=list)
    serper_reddit: list[SerperRedditResult] = Field(default_factory=list)
    serper_twitter: list[SerperTwitterResult] = Field(default_factory=list)
    twitter_results: list[SocialDataTweet] = Field(default_factory=list)
    exa_results: list[ExaSearchResult] = Field(default_factory=list)
    perplexity_answer: PerplexityResult | None = None
    perplexity_deep_answer: PerplexityDeepResult | None = None
    hn_stories: list[HNStory] = Field(default_factory=list)
    hn_comments: list[HNComment] = Field(default_factory=list)
    firecrawl_pages: list[FirecrawlPage] = Field(default_factory=list)
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
            or self.serper_twitter
            or self.twitter_results
            or self.exa_results
            or self.perplexity_answer
            or self.hn_stories
            or self.hn_comments
            or self.firecrawl_pages
        )


def _merge_results(partials: list[RawResearchData]) -> RawResearchData:
    """Merge multiple partial RawResearchData objects into one.

    List fields are concatenated. Optional fields take the first non-None.
    Fully typed — no ``Any``.
    """
    return RawResearchData(
        tavily_results=[r for p in partials for r in p.tavily_results],
        tavily_research=next(
            (p.tavily_research for p in partials if p.tavily_research is not None),
            None,
        ),
        serper_results=[r for p in partials for r in p.serper_results],
        serper_reddit=[r for p in partials for r in p.serper_reddit],
        serper_twitter=[r for p in partials for r in p.serper_twitter],
        twitter_results=[r for p in partials for r in p.twitter_results],
        exa_results=[r for p in partials for r in p.exa_results],
        perplexity_answer=next(
            (p.perplexity_answer for p in partials if p.perplexity_answer is not None),
            None,
        ),
        perplexity_deep_answer=next(
            (p.perplexity_deep_answer for p in partials if p.perplexity_deep_answer is not None),
            None,
        ),
        hn_stories=[r for p in partials for r in p.hn_stories],
        hn_comments=[r for p in partials for r in p.hn_comments],
        firecrawl_pages=[r for p in partials for r in p.firecrawl_pages],
        sources_used=[s for p in partials for s in p.sources_used],
        errors=[e for p in partials for e in p.errors],
    )


class ResearchCollector:
    """Calls all available research APIs with graceful degradation.

    Each provider runs in its own thread via ``ThreadPoolExecutor``.
    Failures are logged and collected in the errors list, but never
    abort the collection.  Only raises if ALL sources fail to return
    any data.

    Providers can be injected for testing; otherwise
    ``default_providers(settings)`` constructs the full set.
    """

    def __init__(
        self,
        settings: Settings,
        providers: list[ResearchProviderPort] | None = None,
    ) -> None:
        self.settings = settings
        if providers is not None:
            self._providers = providers
        else:
            from verdandi.providers import default_providers

            self._providers = default_providers(settings)
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
    # Main collection orchestrator
    # ------------------------------------------------------------------

    def collect(
        self,
        queries: list[str],
        *,
        include_reddit: bool = True,
        include_twitter: bool = True,
        include_hn_comments: bool = True,
        perplexity_question: str = "",
        exa_similar_url: str = "",
        tavily_research_query: str = "",
        use_perplexity_deep: bool = False,
        competitor_urls: list[str] | None = None,
    ) -> RawResearchData:
        """Collect research data from all available providers in parallel.

        Each provider runs in its own thread with independent error
        handling — one provider failing never blocks the others.

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
            competitor_urls: Optional list of competitor website URLs for
                Firecrawl to scrape (pricing, features, about pages).

        Returns:
            RawResearchData with results from all sources that responded.

        Raises:
            RuntimeError: If no sources returned any data at all.
        """
        config = CollectionConfig(
            queries=queries,
            primary_query=queries[0] if queries else "",
            include_reddit=include_reddit,
            include_twitter=include_twitter,
            include_hn_comments=include_hn_comments,
            perplexity_question=perplexity_question,
            exa_similar_url=exa_similar_url,
            tavily_research_query=tavily_research_query,
            use_perplexity_deep=use_perplexity_deep,
            competitor_urls=competitor_urls or [],
        )

        available = [p for p in self._providers if p.is_available]

        with ThreadPoolExecutor(
            max_workers=max(len(available), 1),
            thread_name_prefix="research",
        ) as executor:
            futures = {executor.submit(p.collect, config, self._cached_call): p for p in available}

        partials: list[RawResearchData] = []
        for future, provider in futures.items():
            try:
                partials.append(future.result())
            except Exception as exc:
                logger.warning(
                    "Provider failed",
                    provider=provider.name,
                    error=str(exc),
                )
                partials.append(RawResearchData(errors=[f"{provider.name} failed: {exc}"]))

        raw = _merge_results(partials)

        logger.info(
            "Research collection complete",
            sources_used=raw.sources_used,
            error_count=len(raw.errors),
        )

        if not raw.has_data:
            raise RuntimeError(f"All research sources failed. Errors: {'; '.join(raw.errors)}")

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

    # Twitter/X discussions (via Serper site:x.com)
    if raw.serper_twitter:
        lines = ["## Twitter/X Discussions"]
        for tw in raw.serper_twitter:
            author_part = f"@{tw['author']}" if tw["author"] else "unknown"
            lines.append(f"- **{author_part}**: {tw['title']} ({tw['link']})")
            lines.append(f"  {tw['snippet']}")
        sections.append("\n".join(lines))

    # Twitter/X insights (via SocialData — rich engagement data)
    if raw.twitter_results:
        lines = ["## Twitter/X Insights (SocialData)"]
        for tweet in raw.twitter_results:
            lines.append(
                f"- **@{tweet['author_username']}** "
                f"({tweet['author_followers']:,} followers): "
                f"({tweet['url']})"
            )
            text = tweet["text"][:400]
            lines.append(f'  "{text}"')
            lines.append(
                f"  {tweet['favorite_count']} likes, "
                f"{tweet['retweet_count']} RTs, "
                f"{tweet['reply_count']} replies, "
                f"{tweet['views_count']:,} views"
            )
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

    # Firecrawl competitor pages
    if raw.firecrawl_pages:
        lines = ["## Competitor Deep Dive (Firecrawl)"]
        for page in raw.firecrawl_pages:
            lines.append(f"### {page['title'] or page['url']}")
            lines.append(f"**URL**: {page['url']}")
            if page["description"]:
                lines.append(f"**Description**: {page['description']}")
            lines.append(f"**Word count**: {page['word_count']}")
            # Truncate markdown to avoid overwhelming the LLM context
            md = page["markdown"]
            if len(md) > 2000:
                md = md[:2000] + "\n\n[... truncated]"
            lines.append(f"\n{md}")
        sections.append("\n".join(lines))

    # Sources summary
    lines = [f"\n---\n**Sources used**: {', '.join(raw.sources_used)}"]
    if raw.errors:
        lines.append(f"**Errors encountered**: {len(raw.errors)}")
        for err in raw.errors:
            lines.append(f"  - {err}")
    sections.append("\n".join(lines))

    return "\n\n".join(sections)
