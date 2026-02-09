"""Client for Perplexity Sonar API.

Perplexity synthesizes multi-source research answers with citations.
Basic query: ~$0.006. Deep Research: ~$0.41-$1.32 per query.
Best for TAM estimation and competitive landscape synthesis.
"""

from __future__ import annotations

import httpx
import structlog
from typing_extensions import TypedDict

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


def _parse_usage(data: dict[str, object]) -> TokenUsage:
    """Extract TokenUsage from the API response, falling back to zeros."""
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    prompt = raw.get("prompt_tokens", 0)
    completion = raw.get("completion_tokens", 0)
    total = raw.get("total_tokens", 0)
    return {
        "prompt_tokens": prompt if isinstance(prompt, int) else 0,
        "completion_tokens": completion if isinstance(completion, int) else 0,
        "total_tokens": total if isinstance(total, int) else 0,
    }


def _parse_answer(data: dict[str, object]) -> str:
    """Extract the answer string from the choices array."""
    choices = data.get("choices", [])
    if choices and isinstance(choices, list):
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message", {})
            if isinstance(msg, dict):
                content = msg.get("content", "")
                return str(content)
    return ""


def _parse_citations(data: dict[str, object]) -> list[str]:
    """Extract the citations list from the response."""
    raw = data.get("citations", [])
    if not isinstance(raw, list):
        return []
    return [str(c) for c in raw]


def _parse_model(data: dict[str, object], default: str) -> str:
    """Extract the model name from the response."""
    raw = data.get("model", default)
    return str(raw) if raw is not None else default


class PerplexityClient:
    """Perplexity Sonar API client. Returns mock data until API key is configured."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.base_url = "https://api.perplexity.ai"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def query(self, question: str) -> PerplexityResult:
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

        logger.info("perplexity_query", question=question)
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "user", "content": question},
                        ],
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "perplexity_query_failed",
                question=question,
                error=str(exc),
            )
            return self._mock_query(question)

        return {
            "answer": _parse_answer(data),
            "citations": _parse_citations(data),
            "model": _parse_model(data, "sonar"),
            "usage": _parse_usage(data),
        }

    def deep_research(self, question: str) -> PerplexityDeepResult:
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

        logger.info("perplexity_deep_research", question=question)
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar-deep-research",
                        "messages": [
                            {"role": "user", "content": question},
                        ],
                    },
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "perplexity_deep_research_failed",
                question=question,
                error=str(exc),
            )
            return self._mock_deep_research(question)

        citations = _parse_citations(data)
        return {
            "answer": _parse_answer(data),
            "citations": citations,
            "sources_analyzed": len(citations),
            "model": _parse_model(data, "sonar-deep-research"),
            "usage": _parse_usage(data),
        }

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
