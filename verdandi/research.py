"""Research data collection and aggregation.

Central module that coordinates calls to all research API clients,
aggregates results, and formats them for LLM consumption. Follows
a collect-then-synthesize pattern with graceful degradation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

from verdandi.clients.exa import ExaSearchResult
from verdandi.clients.hn_algolia import HNComment, HNStory
from verdandi.clients.perplexity import PerplexityResult
from verdandi.clients.serper import SerperRedditResult, SerperResult
from verdandi.clients.tavily import TavilySearchResult

if TYPE_CHECKING:
    from verdandi.cache import ResearchCache
    from verdandi.config import Settings

logger = structlog.get_logger()


class RawResearchData(BaseModel):
    """Accumulated raw results from all research APIs."""

    model_config = ConfigDict(frozen=True)

    tavily_results: list[TavilySearchResult] = Field(default_factory=list)
    serper_results: list[SerperResult] = Field(default_factory=list)
    serper_reddit: list[SerperRedditResult] = Field(default_factory=list)
    exa_results: list[ExaSearchResult] = Field(default_factory=list)
    perplexity_answer: PerplexityResult | None = None
    hn_stories: list[HNStory] = Field(default_factory=list)
    hn_comments: list[HNComment] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def has_data(self) -> bool:
        """Check if any source returned data."""
        return bool(
            self.tavily_results
            or self.serper_results
            or self.serper_reddit
            or self.exa_results
            or self.perplexity_answer
            or self.hn_stories
            or self.hn_comments
        )


class ResearchCollector:
    """Calls all available research APIs with graceful degradation.

    Each API call is wrapped in try/except. Failures are logged and
    collected in the errors list, but never abort the collection.
    Only raises if ALL sources fail to return any data.

    Optionally caches results in Redis when configured via settings.
    Cache degrades gracefully if Redis is unavailable.
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

    def collect(
        self,
        queries: list[str],
        *,
        include_reddit: bool = True,
        include_hn_comments: bool = True,
        perplexity_question: str = "",
        exa_similar_url: str = "",
    ) -> RawResearchData:
        """Collect research data from all available APIs.

        Args:
            queries: List of search queries to distribute across APIs.
            include_reddit: Whether to search Reddit via Serper.
            include_hn_comments: Whether to search HN comments.
            perplexity_question: Optional synthesized question for Perplexity.
            exa_similar_url: Optional URL for Exa's find_similar.

        Returns:
            RawResearchData with results from all sources that responded.

        Raises:
            RuntimeError: If no sources returned any data at all.
        """
        from verdandi.clients.exa import ExaClient
        from verdandi.clients.hn_algolia import HNClient
        from verdandi.clients.perplexity import PerplexityClient
        from verdandi.clients.serper import SerperClient
        from verdandi.clients.tavily import TavilyClient

        tavily_results: list[TavilySearchResult] = []
        serper_results: list[SerperResult] = []
        serper_reddit: list[SerperRedditResult] = []
        exa_results: list[ExaSearchResult] = []
        perplexity_answer: PerplexityResult | None = None
        hn_stories: list[HNStory] = []
        hn_comments: list[HNComment] = []
        sources_used: list[str] = []
        errors: list[str] = []

        primary_query = queries[0] if queries else ""

        # --- Tavily: best for general web search ---
        tavily = TavilyClient(api_key=self.settings.tavily_api_key)
        if tavily.is_available:
            for q in queries[:3]:  # Tavily credits are limited, use top 3 queries
                cached_json = self._check_cache("tavily", q)
                if cached_json is not None:
                    cached_tavily: list[TavilySearchResult] = json.loads(cached_json)
                    tavily_results.extend(cached_tavily)
                    continue
                try:
                    tavily_hits = tavily.search(q, max_results=5)
                    tavily_results.extend(tavily_hits)
                    self._save_cache("tavily", q, json.dumps(tavily_hits))
                except Exception as exc:
                    errors.append(f"Tavily search failed for '{q}': {exc}")
                    logger.warning("Tavily search failed", query=q, error=str(exc))
            if tavily_results:
                sources_used.append("tavily")
        else:
            logger.debug("Tavily not configured, skipping")

        # --- Serper: Google SERP data + Reddit ---
        serper = SerperClient(api_key=self.settings.serper_api_key)
        if serper.is_available:
            for q in queries[:2]:  # Serper is cheap but be conservative
                cached_json = self._check_cache("serper", q)
                if cached_json is not None:
                    cached_serper: list[SerperResult] = json.loads(cached_json)
                    serper_results.extend(cached_serper)
                    continue
                try:
                    serper_hits = serper.search(q, num=10)
                    serper_results.extend(serper_hits)
                    self._save_cache("serper", q, json.dumps(serper_hits))
                except Exception as exc:
                    errors.append(f"Serper search failed for '{q}': {exc}")
                    logger.warning("Serper search failed", query=q, error=str(exc))

            if include_reddit and primary_query:
                cached_json = self._check_cache("serper_reddit", primary_query)
                if cached_json is not None:
                    cached_reddit: list[SerperRedditResult] = json.loads(cached_json)
                    serper_reddit.extend(cached_reddit)
                else:
                    try:
                        reddit_hits = serper.search_reddit(primary_query)
                        serper_reddit.extend(reddit_hits)
                        self._save_cache("serper_reddit", primary_query, json.dumps(reddit_hits))
                    except Exception as exc:
                        errors.append(f"Serper Reddit search failed: {exc}")
                        logger.warning("Serper Reddit failed", error=str(exc))

            if serper_results or serper_reddit:
                sources_used.append("serper")
        else:
            logger.debug("Serper not configured, skipping")

        # --- Exa: semantic/neural search ---
        exa = ExaClient(api_key=self.settings.exa_api_key)
        if exa.is_available:
            if primary_query:
                cached_json = self._check_cache("exa", primary_query)
                if cached_json is not None:
                    cached_exa: list[ExaSearchResult] = json.loads(cached_json)
                    exa_results.extend(cached_exa)
                else:
                    try:
                        exa_hits = exa.search(primary_query, num_results=5)
                        exa_results.extend(exa_hits)
                        self._save_cache("exa", primary_query, json.dumps(exa_hits))
                    except Exception as exc:
                        errors.append(f"Exa search failed: {exc}")
                        logger.warning("Exa search failed", error=str(exc))

            if exa_similar_url:
                cached_json = self._check_cache("exa_similar", exa_similar_url)
                if cached_json is not None:
                    cached_exa_similar: list[ExaSearchResult] = json.loads(cached_json)
                    exa_results.extend(cached_exa_similar)
                else:
                    try:
                        similar = exa.find_similar(exa_similar_url)
                        converted: list[ExaSearchResult] = [
                            {
                                "title": s["title"],
                                "url": s["url"],
                                "text": s["text"],
                                "score": s["score"],
                                "published_date": "",
                                "author": None,
                            }
                            for s in similar
                        ]
                        exa_results.extend(converted)
                        self._save_cache("exa_similar", exa_similar_url, json.dumps(converted))
                    except Exception as exc:
                        errors.append(f"Exa find_similar failed: {exc}")
                        logger.warning("Exa find_similar failed", error=str(exc))

            if exa_results:
                sources_used.append("exa")
        else:
            logger.debug("Exa not configured, skipping")

        # --- Perplexity: synthesized answer with citations ---
        perplexity = PerplexityClient(api_key=self.settings.perplexity_api_key)
        if perplexity.is_available and perplexity_question:
            cached_json = self._check_cache("perplexity", perplexity_question)
            if cached_json is not None:
                cached_pplx: PerplexityResult = json.loads(cached_json)
                perplexity_answer = cached_pplx
                sources_used.append("perplexity")
            else:
                try:
                    perplexity_answer = perplexity.query(perplexity_question)
                    sources_used.append("perplexity")
                    self._save_cache(
                        "perplexity", perplexity_question, json.dumps(perplexity_answer)
                    )
                except Exception as exc:
                    errors.append(f"Perplexity query failed: {exc}")
                    logger.warning("Perplexity query failed", error=str(exc))
        elif not perplexity_question:
            logger.debug("No Perplexity question provided, skipping")
        else:
            logger.debug("Perplexity not configured, skipping")

        # --- HN Algolia: always available (free, no auth) ---
        hn = HNClient()
        if primary_query:
            cached_json = self._check_cache("hn_stories", primary_query)
            if cached_json is not None:
                cached_hn: list[HNStory] = json.loads(cached_json)
                hn_stories.extend(cached_hn)
            else:
                try:
                    hn_hits = hn.search(primary_query, tags="story")
                    hn_stories.extend(hn_hits)
                    self._save_cache("hn_stories", primary_query, json.dumps(hn_hits))
                except Exception as exc:
                    errors.append(f"HN story search failed: {exc}")
                    logger.warning("HN story search failed", error=str(exc))

            if include_hn_comments:
                cached_json = self._check_cache("hn_comments", primary_query)
                if cached_json is not None:
                    cached_hn_c: list[HNComment] = json.loads(cached_json)
                    hn_comments.extend(cached_hn_c)
                else:
                    try:
                        hn_comment_hits = hn.search_comments(primary_query)
                        hn_comments.extend(hn_comment_hits)
                        self._save_cache("hn_comments", primary_query, json.dumps(hn_comment_hits))
                    except Exception as exc:
                        errors.append(f"HN comment search failed: {exc}")
                        logger.warning("HN comment search failed", error=str(exc))

            if hn_stories or hn_comments:
                sources_used.append("hn_algolia")

        raw = RawResearchData(
            tavily_results=tavily_results,
            serper_results=serper_results,
            serper_reddit=serper_reddit,
            exa_results=exa_results,
            perplexity_answer=perplexity_answer,
            hn_stories=hn_stories,
            hn_comments=hn_comments,
            sources_used=sources_used,
            errors=errors,
        )

        logger.info(
            "Research collection complete",
            sources_used=sources_used,
            tavily_count=len(tavily_results),
            serper_count=len(serper_results),
            reddit_count=len(serper_reddit),
            exa_count=len(exa_results),
            has_perplexity=perplexity_answer is not None,
            hn_stories=len(hn_stories),
            hn_comments=len(hn_comments),
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

    # Perplexity synthesis
    if raw.perplexity_answer:
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
