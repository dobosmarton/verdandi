"""Perplexity research provider — synthesized answers with citations.

Supports both the fast Sonar query and the more expensive Deep Research
mode.  The mode is controlled by ``CollectionConfig.use_perplexity_deep``.
When deep research is used, the result populates both ``perplexity_answer``
and ``perplexity_deep_answer``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.clients.perplexity import PerplexityClient
from verdandi.research import CollectionConfig, RawResearchData

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import CachedCallFn


class PerplexityProvider:
    """Collects synthesized research answers from Perplexity Sonar."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.perplexity_api_key

    @property
    def name(self) -> str:
        return "perplexity"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def collect(
        self,
        config: CollectionConfig,
        cached_call: CachedCallFn,
    ) -> RawResearchData:
        if not config.perplexity_question:
            return RawResearchData()

        client = PerplexityClient(api_key=self._api_key)
        errors: list[str] = []
        question = config.perplexity_question

        if config.use_perplexity_deep:
            cache_key = f"perplexity_deep:{question}"
            result = cached_call(
                "perplexity",
                cache_key,
                lambda: client.deep_research(question),
                errors,
                label="Perplexity deep_research",
            )
            if result is None:
                return RawResearchData(errors=errors)
            return RawResearchData(
                perplexity_answer=result,
                perplexity_deep_answer=result,
                sources_used=["perplexity"],
                errors=errors,
            )

        basic_result = cached_call(
            "perplexity",
            question,
            lambda: client.query(question),
            errors,
            label="Perplexity query",
        )
        if basic_result is None:
            return RawResearchData(errors=errors)
        return RawResearchData(
            perplexity_answer=basic_result,
            sources_used=["perplexity"],
            errors=errors,
        )
