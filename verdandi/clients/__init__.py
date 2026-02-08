"""API client stubs for external services.

Each client follows the same pattern:
- Accepts API key(s) in __init__
- Exposes an `is_available` property (True when key is set)
- Returns realistic mock data when the API key is missing
- Uses httpx.AsyncClient for real HTTP calls (stubbed for now)
"""

from verdandi.clients.cloudflare import CloudflareClient
from verdandi.clients.emailoctopus import EmailOctopusClient
from verdandi.clients.exa import ExaClient
from verdandi.clients.hn_algolia import HNClient
from verdandi.clients.perplexity import PerplexityClient
from verdandi.clients.porkbun import PorkbunClient
from verdandi.clients.serper import SerperClient
from verdandi.clients.social.bluesky import BlueskyClient
from verdandi.clients.social.linkedin import LinkedInClient
from verdandi.clients.social.reddit import RedditClient
from verdandi.clients.social.twitter import TwitterClient
from verdandi.clients.tavily import TavilyClient
from verdandi.clients.umami import UmamiClient

__all__ = [
    "BlueskyClient",
    "CloudflareClient",
    "EmailOctopusClient",
    "ExaClient",
    "HNClient",
    "LinkedInClient",
    "PerplexityClient",
    "PorkbunClient",
    "RedditClient",
    "SerperClient",
    "TavilyClient",
    "TwitterClient",
    "UmamiClient",
]
