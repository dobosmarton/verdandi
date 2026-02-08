"""Client stub for Perplexity Sonar API.

Perplexity synthesizes multi-source research answers with citations.
Basic query: ~$0.006. Deep Research: ~$0.41-$1.32 per query.
Best for TAM estimation and competitive landscape synthesis.
"""

from __future__ import annotations

from typing import TypedDict

import structlog

logger = structlog.get_logger()


class TokenUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class PerplexityResult(TypedDict):
    answer: str
    citations: list[str]
    model: str
    usage: TokenUsage


class PerplexityDeepResult(PerplexityResult):
    sources_analyzed: int


class PerplexityClient:
    """Perplexity Sonar API client. Returns mock data until API key is configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://api.perplexity.ai"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def query(self, question: str) -> PerplexityResult:
        """Ask a question via the Perplexity Sonar API.

        Uses the sonar model for fast, cited answers from multiple sources.

        Args:
            question: Natural language question (e.g., "What is the TAM
                for project management software?").

        Returns:
            Dict with keys: answer, citations, model, usage.
        """
        if not self.is_available:
            logger.debug("Perplexity not configured, returning mock data")
            return self._mock_query(question)

        # TODO: Real API call
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(
        #         f"{self.base_url}/chat/completions",
        #         headers={
        #             "Authorization": f"Bearer {self.api_key}",
        #             "Content-Type": "application/json",
        #         },
        #         json={
        #             "model": "sonar",
        #             "messages": [
        #                 {"role": "user", "content": question},
        #             ],
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "answer": data["choices"][0]["message"]["content"],
        #         "citations": data.get("citations", []),
        #         "model": data.get("model"),
        #         "usage": data.get("usage"),
        #     }
        logger.info("Perplexity query: %r", question)
        return self._mock_query(question)

    async def deep_research(self, question: str) -> PerplexityDeepResult:
        """Run Perplexity Deep Research for comprehensive analysis.

        More expensive (~$0.41-$1.32 per query) but performs multi-step
        research with extensive source synthesis. Best for TAM estimation
        and competitive landscape analysis.

        Args:
            question: Complex research question.

        Returns:
            Dict with keys: answer, citations, sources_analyzed, model, usage.
        """
        if not self.is_available:
            logger.debug("Perplexity not configured, returning mock deep research")
            return self._mock_deep_research(question)

        # TODO: Real API call with deep research model
        # async with httpx.AsyncClient(timeout=120.0) as client:
        #     resp = await client.post(
        #         f"{self.base_url}/chat/completions",
        #         headers={
        #             "Authorization": f"Bearer {self.api_key}",
        #             "Content-Type": "application/json",
        #         },
        #         json={
        #             "model": "sonar-deep-research",
        #             "messages": [
        #                 {"role": "user", "content": question},
        #             ],
        #         },
        #     )
        #     resp.raise_for_status()
        #     data = resp.json()
        #     return {
        #         "answer": data["choices"][0]["message"]["content"],
        #         "citations": data.get("citations", []),
        #         "sources_analyzed": len(data.get("citations", [])),
        #         "model": data.get("model"),
        #         "usage": data.get("usage"),
        #     }
        logger.info("Perplexity deep research: %r", question)
        return self._mock_deep_research(question)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    def _mock_query(self, question: str) -> PerplexityResult:
        return {
            "answer": (
                f"Based on multiple sources, here is what we know about "
                f"'{question}': The market is growing at 12% CAGR with "
                f"an estimated TAM of $4.2B by 2027. Key players include "
                f"3-5 established companies and 10+ startups. The primary "
                f"pain points are pricing opacity, poor integrations, and "
                f"steep learning curves."
            ),
            "citations": [
                "https://example.com/market-report-2025",
                "https://example.com/industry-analysis",
                "https://example.com/competitor-review",
            ],
            "model": "sonar",
            "usage": {
                "prompt_tokens": 45,
                "completion_tokens": 320,
                "total_tokens": 365,
            },
        }

    def _mock_deep_research(self, question: str) -> PerplexityDeepResult:
        return {
            "answer": (
                f"## Deep Research: {question}\n\n"
                "### Market Overview\n"
                "The total addressable market is estimated at $4.2B (2025), "
                "growing to $7.8B by 2028 (CAGR 12.3%). North America "
                "accounts for 45% of revenue.\n\n"
                "### Competitive Landscape\n"
                "- **Leader A**: $200M ARR, enterprise focus, 2,500 customers\n"
                "- **Leader B**: $80M ARR, SMB focus, freemium model\n"
                "- **Challenger C**: $15M ARR, AI-native, fastest growing\n\n"
                "### Key Pain Points (from user research)\n"
                "1. Complex onboarding (mentioned in 67% of negative reviews)\n"
                "2. Pricing not transparent (45% of churned users cite cost)\n"
                "3. Limited API / integration capabilities (38%)\n\n"
                "### Opportunity Assessment\n"
                "A focused solution addressing pain points 1 and 3 with "
                "transparent pricing could capture 2-5% of the SMB segment "
                "within 18 months, representing $8-20M opportunity."
            ),
            "citations": [
                "https://example.com/gartner-report",
                "https://example.com/g2-reviews",
                "https://example.com/crunchbase-data",
                "https://example.com/industry-blog",
                "https://example.com/user-survey-results",
            ],
            "sources_analyzed": 23,
            "model": "sonar-deep-research",
            "usage": {
                "prompt_tokens": 52,
                "completion_tokens": 2840,
                "total_tokens": 2892,
            },
        }
