"""Tests for ResearchSession ephemeral working memory."""

from __future__ import annotations

from verdandi.memory.working import ResearchSession
from verdandi.research import RawResearchData


def _make_raw(
    *,
    tavily: list[dict[str, object]] | None = None,
    serper: list[dict[str, object]] | None = None,
    hn_stories: list[dict[str, object]] | None = None,
    hn_comments: list[dict[str, object]] | None = None,
    sources: list[str] | None = None,
    errors: list[str] | None = None,
) -> RawResearchData:
    """Helper to build RawResearchData with defaults."""
    return RawResearchData(
        tavily_results=tavily or [],
        serper_results=serper or [],
        hn_stories=hn_stories or [],
        hn_comments=hn_comments or [],
        sources_used=sources or [],
        errors=errors or [],
    )


class TestResearchSessionBasics:
    def test_empty_session_has_no_data(self) -> None:
        session = ResearchSession("Test Idea", "dev-tools")
        assert session.has_data is False
        assert session.total_results == 0

    def test_ingest_sets_has_data(self) -> None:
        session = ResearchSession("Test Idea", "dev-tools")
        raw = _make_raw(
            tavily=[
                {
                    "title": "Result",
                    "url": "https://example.com",
                    "content": "Content",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources=["tavily"],
        )
        session.ingest(raw)
        assert session.has_data is True
        assert session.total_results == 1

    def test_ingest_merges_multiple_calls(self) -> None:
        session = ResearchSession("Test Idea", "dev-tools")

        raw1 = _make_raw(
            tavily=[
                {
                    "title": "A",
                    "url": "https://a.com",
                    "content": "C1",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources=["tavily"],
        )
        raw2 = _make_raw(
            tavily=[
                {
                    "title": "B",
                    "url": "https://b.com",
                    "content": "C2",
                    "score": 0.8,
                    "published_date": "",
                }
            ],
            sources=["tavily"],
        )
        session.ingest(raw1)
        session.ingest(raw2)
        assert session.total_results == 2


class TestResearchSessionDedup:
    def test_dedup_tavily_by_url(self) -> None:
        session = ResearchSession("Test", "cat")
        raw1 = _make_raw(
            tavily=[
                {
                    "title": "A",
                    "url": "https://same.com/page",
                    "content": "C1",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
        )
        raw2 = _make_raw(
            tavily=[
                {
                    "title": "A copy",
                    "url": "https://same.com/page",
                    "content": "C1 copy",
                    "score": 0.8,
                    "published_date": "",
                }
            ],
        )
        session.ingest(raw1)
        session.ingest(raw2)
        # Only one result because same URL
        assert session.total_results == 1

    def test_dedup_hn_stories_by_objectid(self) -> None:
        session = ResearchSession("Test", "cat")
        raw1 = _make_raw(
            hn_stories=[
                {
                    "title": "HN Story",
                    "url": None,
                    "author": "user1",
                    "points": 100,
                    "num_comments": 50,
                    "created_at": "",
                    "objectID": "12345",
                    "tags": "story",
                }
            ],
        )
        raw2 = _make_raw(
            hn_stories=[
                {
                    "title": "HN Story (dup)",
                    "url": None,
                    "author": "user1",
                    "points": 100,
                    "num_comments": 50,
                    "created_at": "",
                    "objectID": "12345",
                    "tags": "story",
                }
            ],
        )
        session.ingest(raw1)
        session.ingest(raw2)
        assert session.total_results == 1

    def test_dedup_hn_comments_by_objectid(self) -> None:
        session = ResearchSession("Test", "cat")
        raw = _make_raw(
            hn_comments=[
                {
                    "comment_text": "Great tool",
                    "author": "dev",
                    "story_title": "S",
                    "story_url": None,
                    "points": 5,
                    "created_at": "",
                    "objectID": "99",
                },
                {
                    "comment_text": "Great tool (dup)",
                    "author": "dev",
                    "story_title": "S",
                    "story_url": None,
                    "points": 5,
                    "created_at": "",
                    "objectID": "99",
                },
            ],
        )
        session.ingest(raw)
        assert session.total_results == 1

    def test_sources_deduped(self) -> None:
        session = ResearchSession("Test", "cat")
        session.ingest(_make_raw(sources=["tavily", "serper"]))
        session.ingest(_make_raw(sources=["tavily", "exa"]))
        raw = session.to_raw()
        assert raw.sources_used == ["tavily", "serper", "exa"]


class TestResearchSessionFormatting:
    def test_formatted_context_includes_data(self) -> None:
        session = ResearchSession("Test", "cat")
        session.ingest(
            _make_raw(
                tavily=[
                    {
                        "title": "Market Analysis",
                        "url": "https://example.com/market",
                        "content": "The market is growing rapidly",
                        "score": 0.95,
                        "published_date": "",
                    }
                ],
                sources=["tavily"],
            )
        )
        text = session.formatted_context
        assert "Market Analysis" in text
        assert "example.com/market" in text

    def test_to_raw_round_trip(self) -> None:
        session = ResearchSession("Test", "cat")
        session.ingest(
            _make_raw(
                tavily=[
                    {
                        "title": "A",
                        "url": "https://a.com",
                        "content": "C",
                        "score": 0.5,
                        "published_date": "",
                    }
                ],
                sources=["tavily"],
                errors=["Serper failed"],
            )
        )
        raw = session.to_raw()
        assert raw.has_data is True
        assert len(raw.tavily_results) == 1
        assert len(raw.errors) == 1


class TestResearchSessionLLMHistory:
    def test_llm_history_empty_by_default(self) -> None:
        session = ResearchSession("Test", "cat")
        assert session.llm_history == []

    def test_add_and_retrieve_history(self) -> None:
        session = ResearchSession("Test", "cat")
        session.add_llm_turn([{"role": "user", "content": "Hello"}])
        session.add_llm_turn([{"role": "assistant", "content": "Hi"}])
        assert len(session.llm_history) == 2

    def test_llm_history_returns_copy(self) -> None:
        session = ResearchSession("Test", "cat")
        session.add_llm_turn([{"role": "user", "content": "q"}])
        history = session.llm_history
        history.append({"role": "fake"})
        # Original should be unaffected
        assert len(session.llm_history) == 1
