"""Tests for multi-turn research helpers and gap analysis models.

Covers:
- _merge_followup_queries: deduplication, capping, whitespace handling
- ResearchGapAnalysis / DimensionConfidence: validation, frozen, Literal enforcement
- _extract_tavily_followups: extracts from raw data
- _build_search_results: builds SearchResult list from raw API data
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from verdandi.agents.research import (
    _build_search_results,
    _extract_tavily_followups,
    _merge_followup_queries,
)
from verdandi.models.research import (
    RESEARCH_DIMENSIONS,
    DimensionConfidence,
    ResearchGapAnalysis,
)
from verdandi.research import RawResearchData

# =====================================================================
# _merge_followup_queries
# =====================================================================


class TestMergeFollowupQueries:
    @pytest.mark.parametrize(
        ("llm_queries", "tavily_questions", "max_total", "expected_len"),
        [
            (["q1", "q2"], ["q3"], 5, 3),
            (["q1", "q2"], ["q3"], 2, 2),
            (["TAM for dev tools"], ["tam for dev tools"], 5, 1),
            ([], [], 5, 0),
            (["  q1  ", ""], ["  q2  "], 5, 2),
        ],
        ids=["all-unique", "capped", "substring-dedup", "empty", "whitespace"],
    )
    def test_merge_followup_queries(
        self,
        llm_queries: list[str],
        tavily_questions: list[str],
        max_total: int,
        expected_len: int,
    ) -> None:
        result = _merge_followup_queries(llm_queries, tavily_questions, max_total)
        assert len(result) == expected_len

    def test_llm_queries_take_priority(self) -> None:
        """LLM queries appear first, Tavily appended after."""
        result = _merge_followup_queries(["llm_first"], ["tavily_second"], max_total=5)
        assert result[0] == "llm_first"
        assert result[1] == "tavily_second"

    def test_substring_dedup_bidirectional(self) -> None:
        """If Tavily question is a substring of LLM query, it's skipped."""
        result = _merge_followup_queries(
            ["market size for AI dev tools in 2025"],
            ["market size for AI dev tools"],
            max_total=5,
        )
        assert len(result) == 1

    def test_stripped_values_in_output(self) -> None:
        """Whitespace is stripped from output queries."""
        result = _merge_followup_queries(["  padded  "], [], max_total=5)
        assert result[0] == "padded"


# =====================================================================
# ResearchGapAnalysis model validation
# =====================================================================


def _make_dimension_scores() -> list[DimensionConfidence]:
    """Create valid dimension scores for all 5 dimensions."""
    return [
        DimensionConfidence(
            dimension=dim,
            confidence=0.5,
            justification=f"Moderate evidence for {dim}",
        )
        for dim in RESEARCH_DIMENSIONS
    ]


class TestResearchGapAnalysisModel:
    def test_valid_construction(self) -> None:
        gap = ResearchGapAnalysis(
            overall_confidence=0.6,
            dimension_scores=_make_dimension_scores(),
            weakest_dimensions=["pain_severity"],
            follow_up_queries=["What is the TAM?"],
            follow_up_perplexity_question="Analyze the TAM",
            reasoning="Some dimensions lack evidence.",
        )
        assert gap.overall_confidence == 0.6
        assert len(gap.dimension_scores) == 5
        assert gap.weakest_dimensions == ["pain_severity"]

    def test_frozen_immutability(self) -> None:
        gap = ResearchGapAnalysis(
            overall_confidence=0.6,
            dimension_scores=_make_dimension_scores(),
            weakest_dimensions=[],
            follow_up_queries=[],
            reasoning="OK",
        )
        with pytest.raises(ValidationError):
            gap.overall_confidence = 0.9  # type: ignore[misc]

    def test_confidence_bounds_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ResearchGapAnalysis(
                overall_confidence=1.5,  # out of bounds
                dimension_scores=_make_dimension_scores(),
                weakest_dimensions=[],
                follow_up_queries=[],
                reasoning="Bad",
            )

    def test_dimension_literal_enforced(self) -> None:
        with pytest.raises(ValidationError):
            DimensionConfidence(
                dimension="nonexistent_dimension",  # type: ignore[arg-type]
                confidence=0.5,
                justification="This should fail",
            )

    def test_requires_exactly_five_dimensions(self) -> None:
        with pytest.raises(ValidationError):
            ResearchGapAnalysis(
                overall_confidence=0.5,
                dimension_scores=_make_dimension_scores()[:3],  # only 3
                weakest_dimensions=[],
                follow_up_queries=[],
                reasoning="Too few",
            )

    def test_follow_up_queries_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ResearchGapAnalysis(
                overall_confidence=0.5,
                dimension_scores=_make_dimension_scores(),
                weakest_dimensions=[],
                follow_up_queries=["q1", "q2", "q3", "q4", "q5", "q6"],  # 6 > max 5
                reasoning="Too many queries",
            )


# =====================================================================
# DimensionConfidence model
# =====================================================================


class TestDimensionConfidence:
    def test_valid_construction(self) -> None:
        dc = DimensionConfidence(
            dimension="market_size",
            confidence=0.8,
            justification="Multiple sources confirm $2B TAM",
        )
        assert dc.dimension == "market_size"
        assert dc.confidence == 0.8

    def test_confidence_zero_and_one(self) -> None:
        """Boundary values 0.0 and 1.0 are valid."""
        dc_zero = DimensionConfidence(
            dimension="pain_severity", confidence=0.0, justification="No evidence"
        )
        dc_one = DimensionConfidence(
            dimension="pain_severity", confidence=1.0, justification="Strong evidence"
        )
        assert dc_zero.confidence == 0.0
        assert dc_one.confidence == 1.0


# =====================================================================
# _extract_tavily_followups
# =====================================================================


class TestExtractTavilyFollowups:
    def test_extracts_from_tavily_research(self) -> None:
        raw = RawResearchData(
            tavily_research={
                "summary": "A summary",
                "sources": [],
                "follow_up_questions": ["Q1", "Q2"],
            },
        )
        result = _extract_tavily_followups(raw)
        assert result == ["Q1", "Q2"]

    def test_returns_empty_when_no_research(self) -> None:
        raw = RawResearchData()
        result = _extract_tavily_followups(raw)
        assert result == []

    def test_returns_empty_when_no_followups(self) -> None:
        raw = RawResearchData(
            tavily_research={
                "summary": "A summary",
                "sources": [],
                "follow_up_questions": [],
            },
        )
        result = _extract_tavily_followups(raw)
        assert result == []


# =====================================================================
# _build_search_results
# =====================================================================


class TestBuildSearchResults:
    def test_builds_from_tavily(self) -> None:
        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Tavily Result",
                    "url": "https://tavily.com/1",
                    "content": "Long content " * 50,
                    "score": 0.95,
                    "published_date": "",
                }
            ],
        )
        results = _build_search_results(raw)
        assert len(results) == 1
        assert results[0].source == "tavily"
        assert results[0].relevance_score == 0.95
        assert len(results[0].snippet) <= 300

    def test_builds_from_serper(self) -> None:
        raw = RawResearchData(
            serper_results=[
                {
                    "title": "Serper Result",
                    "link": "https://serper.dev/1",
                    "snippet": "A snippet",
                    "position": 1,
                }
            ],
        )
        results = _build_search_results(raw)
        assert len(results) == 1
        assert results[0].source == "serper"
        assert results[0].url == "https://serper.dev/1"

    def test_builds_from_exa(self) -> None:
        raw = RawResearchData(
            exa_results=[
                {
                    "title": "Exa Result",
                    "url": "https://exa.ai/1",
                    "text": "Some text content",
                    "score": 0.88,
                    "published_date": "",
                    "author": "",
                }
            ],
        )
        results = _build_search_results(raw)
        assert len(results) == 1
        assert results[0].source == "exa"
        assert results[0].relevance_score == 0.88

    def test_combines_multiple_sources(self) -> None:
        raw = RawResearchData(
            tavily_results=[
                {
                    "title": "T1",
                    "url": "https://t.com",
                    "content": "C",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            serper_results=[
                {
                    "title": "S1",
                    "link": "https://s.com",
                    "snippet": "S",
                    "position": 1,
                }
            ],
            exa_results=[
                {
                    "title": "E1",
                    "url": "https://e.com",
                    "text": "E",
                    "score": 0.7,
                    "published_date": "",
                    "author": "",
                }
            ],
        )
        results = _build_search_results(raw)
        assert len(results) == 3
        sources = {r.source for r in results}
        assert sources == {"tavily", "serper", "exa"}

    def test_empty_raw_returns_empty(self) -> None:
        raw = RawResearchData()
        results = _build_search_results(raw)
        assert results == []
