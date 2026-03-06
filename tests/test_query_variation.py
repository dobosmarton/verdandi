"""Tests for discovery query variation (_vary_queries)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from verdandi.agents.discovery import _VariedQueries, _vary_queries
from verdandi.config import Settings


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        discovery_query_variation=True,
    )


@pytest.fixture()
def base_queries() -> list[str]:
    return [
        "most common workflow complaints professionals 2025 2026",
        "cumbersome manual processes people hate doing at work",
    ]


@pytest.fixture()
def base_perplexity_question() -> str:
    return "What specific workflows do professionals complain about?"


class TestVaryQueries:
    def test_returns_varied_queries_from_llm(
        self,
        settings: Settings,
        base_queries: list[str],
        base_perplexity_question: str,
    ) -> None:
        varied_output = _VariedQueries(
            queries=[
                "biggest pain points in professional workflows 2025",
                "manual repetitive tasks workers despise",
            ],
            perplexity_question="Which professional processes are most frustrating?",
        )

        with patch(
            "verdandi.llm.LLMClient.generate",
            return_value=varied_output,
        ):
            result = _vary_queries(base_queries, base_perplexity_question, settings)

        assert result.queries != base_queries
        assert len(result.queries) == 2
        assert result.perplexity_question != base_perplexity_question

    def test_fallback_on_llm_error(
        self,
        settings: Settings,
        base_queries: list[str],
        base_perplexity_question: str,
    ) -> None:
        with patch(
            "verdandi.llm.LLMClient.generate",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = _vary_queries(base_queries, base_perplexity_question, settings)

        assert result.queries == base_queries
        assert result.perplexity_question == base_perplexity_question

    def test_disabled_via_setting(
        self,
        base_queries: list[str],
        base_perplexity_question: str,
    ) -> None:
        disabled_settings = Settings(
            anthropic_api_key="test-key",
            discovery_query_variation=False,
        )

        with patch(
            "verdandi.llm.LLMClient.generate",
        ) as mock_generate:
            result = _vary_queries(base_queries, base_perplexity_question, disabled_settings)

        mock_generate.assert_not_called()
        assert result.queries == base_queries
        assert result.perplexity_question == base_perplexity_question

    def test_varied_queries_model_is_frozen(self) -> None:
        vq = _VariedQueries(
            queries=["q1", "q2"],
            perplexity_question="question?",
        )
        with pytest.raises(Exception):  # noqa: B017
            vq.queries = ["changed"]
