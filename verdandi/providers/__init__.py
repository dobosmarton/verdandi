"""Research providers — one per external API service.

Each provider wraps a single research client and knows how to collect
data from it.  The ``ResearchCollector`` iterates over registered
providers, runs them in parallel via ``ThreadPoolExecutor``, and merges
the results with ``_merge_results``.

To add a new research source:
1. Create a client in ``verdandi/clients/``  (HTTP transport)
2. Create a provider in ``verdandi/providers/`` implementing
   ``ResearchProviderPort``
3. Register it in ``default_providers()`` below
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdandi.providers.exa import ExaProvider
from verdandi.providers.firecrawl import FirecrawlProvider
from verdandi.providers.hn import HNProvider
from verdandi.providers.perplexity import PerplexityProvider
from verdandi.providers.serper import SerperProvider
from verdandi.providers.socialdata import SocialDataProvider
from verdandi.providers.tavily import TavilyProvider

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.protocols import ResearchProviderPort

__all__ = [
    "ExaProvider",
    "FirecrawlProvider",
    "HNProvider",
    "PerplexityProvider",
    "SerperProvider",
    "SocialDataProvider",
    "TavilyProvider",
    "default_providers",
]


def default_providers(settings: Settings) -> list[ResearchProviderPort]:
    """Construct all research providers from settings."""
    return [
        TavilyProvider(settings),
        SerperProvider(settings),
        ExaProvider(settings),
        PerplexityProvider(settings),
        SocialDataProvider(settings),
        FirecrawlProvider(settings),
        HNProvider(),
    ]
