"""Unit tests for the analytics service (verdandi/analytics.py).

All tests use the shared `db` fixture (in-memory SQLite) from conftest.py.
No LLM calls are made.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from verdandi.analytics import (
    get_overview,
    get_pipeline_analytics,
    get_provider_analytics,
    get_score_analytics,
)
from verdandi.models.experiment import Experiment, ExperimentStatus

if TYPE_CHECKING:
    from verdandi.db import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCORING_DATA_GO = {
    "total_score": 75,
    "decision": "go",
    "components": [],
    "risks": [],
    "opportunities": [],
    "reasoning": "Strong market fit",
    "council_votes": [],
}

_SCORING_DATA_NO_GO = {
    "total_score": 30,
    "decision": "no_go",
    "components": [],
    "risks": [],
    "opportunities": [],
    "reasoning": "Weak demand",
    "council_votes": [],
}

_RESEARCH_DATA = {
    "search_results": [
        {"title": "t1", "url": "u1", "source": "tavily", "relevance_score": 0.9},
        {"title": "t2", "url": "u2", "source": "tavily", "relevance_score": 0.8},
        {"title": "t3", "url": "u3", "source": "serper", "relevance_score": 0.7},
        {"title": "t4", "url": "u4", "source": "exa", "relevance_score": 0.6},
    ],
    "tam_estimate": "$1B",
    "market_growth": "growing",
    "competitors": [],
    "competitor_gaps": [],
    "demand_signals": [],
    "key_findings": [],
    "common_complaints": [],
    "search_results": [
        {"title": "t1", "url": "u1", "source": "tavily", "relevance_score": 0.9},
        {"title": "t2", "url": "u2", "source": "tavily", "relevance_score": 0.8},
        {"title": "t3", "url": "u3", "source": "serper", "relevance_score": 0.7},
        {"title": "t4", "url": "u4", "source": "exa", "relevance_score": 0.6},
    ],
    "target_audience_size": "1M",
    "willingness_to_pay": "$50/month",
    "research_summary": "Good opportunity",
    "research_rounds_completed": 1,
    "gap_analysis": None,
    # BaseStepResult fields (optional in JSON, ignored by service)
    "experiment_id": 1,
    "step_name": "deep_research",
    "created_at": None,
    "completed_at": None,
    "worker_id": "test",
}


def _make_experiment(db: Database, status: ExperimentStatus = ExperimentStatus.PENDING) -> Experiment:
    exp = Experiment(
        idea_title="Test Idea",
        idea_summary="Summary",
        status=status,
        worker_id="test-worker",
    )
    return db.create_experiment(exp)


def _save_scoring(db: Database, exp_id: int, data: dict) -> None:
    db.save_step_result(
        experiment_id=exp_id,
        step_name="scoring",
        step_number=2,
        data_json=json.dumps(data),
    )


def _save_research(db: Database, exp_id: int, data: dict) -> None:
    db.save_step_result(
        experiment_id=exp_id,
        step_name="deep_research",
        step_number=1,
        data_json=json.dumps(data),
    )


# ---------------------------------------------------------------------------
# get_overview
# ---------------------------------------------------------------------------


class TestGetOverview:
    def test_empty_db(self, db: Database):
        result = get_overview(db)
        assert result.total_experiments == 0
        assert result.by_status == {}
        assert result.go_rate == 0.0
        assert result.avg_score is None
        assert result.experiments_with_score == 0

    def test_counts_experiments_by_status(self, db: Database):
        _make_experiment(db, ExperimentStatus.PENDING)
        _make_experiment(db, ExperimentStatus.PENDING)
        _make_experiment(db, ExperimentStatus.COMPLETED)

        result = get_overview(db)
        assert result.total_experiments == 3
        assert result.by_status["pending"] == 2
        assert result.by_status["completed"] == 1

    def test_go_rate_all_go(self, db: Database):
        exp = _make_experiment(db)
        _save_scoring(db, exp.id, _SCORING_DATA_GO)

        result = get_overview(db)
        assert result.go_rate == 1.0
        assert result.experiments_with_score == 1
        assert result.avg_score == 75.0

    def test_go_rate_mixed(self, db: Database):
        exp1 = _make_experiment(db)
        exp2 = _make_experiment(db)
        _save_scoring(db, exp1.id, _SCORING_DATA_GO)
        _save_scoring(db, exp2.id, _SCORING_DATA_NO_GO)

        result = get_overview(db)
        assert result.go_rate == 0.5
        assert result.experiments_with_score == 2
        assert result.avg_score == pytest.approx(52.5)

    def test_date_filter_from(self, db: Database):
        # All experiments created now; filtering to far future returns zero
        _make_experiment(db)
        result = get_overview(db, date_from="2099-01-01")
        assert result.total_experiments == 0

    def test_date_filter_to(self, db: Database):
        _make_experiment(db)
        # Filter to ancient past — no results
        result = get_overview(db, date_to="2000-01-01")
        assert result.total_experiments == 0

    def test_date_filter_inclusive(self, db: Database):
        _make_experiment(db)
        # Today's date range should capture the experiment
        import datetime

        today = datetime.date.today().isoformat()
        result = get_overview(db, date_from=today, date_to=today)
        assert result.total_experiments == 1

    def test_returns_correct_model_type(self, db: Database):
        from verdandi.models.analytics import OverviewStats

        result = get_overview(db)
        assert isinstance(result, OverviewStats)


# ---------------------------------------------------------------------------
# get_provider_analytics
# ---------------------------------------------------------------------------


class TestGetProviderAnalytics:
    def test_empty_db(self, db: Database):
        result = get_provider_analytics(db)
        assert result.providers == []

    def test_counts_sources_from_search_results(self, db: Database):
        exp = _make_experiment(db)
        _save_research(db, exp.id, _RESEARCH_DATA)

        result = get_provider_analytics(db)
        providers_by_name = {p.provider: p for p in result.providers}

        assert "tavily" in providers_by_name
        assert "serper" in providers_by_name
        assert "exa" in providers_by_name

        assert providers_by_name["tavily"].successful_calls == 2
        assert providers_by_name["serper"].successful_calls == 1
        assert providers_by_name["exa"].successful_calls == 1

    def test_success_rate_no_errors(self, db: Database):
        exp = _make_experiment(db)
        _save_research(db, exp.id, _RESEARCH_DATA)

        result = get_provider_analytics(db)
        for provider in result.providers:
            assert provider.failed_calls == 0
            assert provider.success_rate == 1.0

    def test_errors_distributed_via_log(self, db: Database):
        exp = _make_experiment(db)
        _save_research(db, exp.id, _RESEARCH_DATA)
        # Log a step error for deep_research
        db.log_event(
            "step_error",
            "Tavily timeout",
            experiment_id=exp.id,
            step_name="deep_research",
        )

        result = get_provider_analytics(db)
        total_failed = sum(p.failed_calls for p in result.providers)
        assert total_failed == 1

    def test_date_filter_excludes_old_experiments(self, db: Database):
        exp = _make_experiment(db)
        _save_research(db, exp.id, _RESEARCH_DATA)
        # Future date filter — no matches
        result = get_provider_analytics(db, date_from="2099-01-01")
        assert result.providers == []

    def test_returns_correct_model_type(self, db: Database):
        from verdandi.models.analytics import ProviderAnalytics

        result = get_provider_analytics(db)
        assert isinstance(result, ProviderAnalytics)


# ---------------------------------------------------------------------------
# get_score_analytics
# ---------------------------------------------------------------------------


class TestGetScoreAnalytics:
    def test_empty_db(self, db: Database):
        result = get_score_analytics(db)
        assert all(b.count == 0 for b in result.distribution)
        assert result.trend == []
        assert result.decision_counts == {}

    def test_distribution_buckets_correct(self, db: Database):
        scores_and_buckets = [
            (10, "0-20"),
            (25, "20-40"),
            (55, "40-60"),
            (70, "60-80"),
            (90, "80-100"),
        ]
        for score, _ in scores_and_buckets:
            exp = _make_experiment(db)
            data = {**_SCORING_DATA_GO, "total_score": score}
            _save_scoring(db, exp.id, data)

        result = get_score_analytics(db)
        bucket_map = {b.bucket_label: b.count for b in result.distribution}
        for _, label in scores_and_buckets:
            assert bucket_map[label] == 1

    def test_decision_counts(self, db: Database):
        exp1 = _make_experiment(db)
        exp2 = _make_experiment(db)
        exp3 = _make_experiment(db)
        _save_scoring(db, exp1.id, _SCORING_DATA_GO)
        _save_scoring(db, exp2.id, _SCORING_DATA_GO)
        _save_scoring(db, exp3.id, _SCORING_DATA_NO_GO)

        result = get_score_analytics(db)
        assert result.decision_counts.get("go", 0) == 2
        assert result.decision_counts.get("no_go", 0) == 1

    def test_trend_has_entries_for_scored_experiments(self, db: Database):
        exp = _make_experiment(db)
        _save_scoring(db, exp.id, _SCORING_DATA_GO)

        result = get_score_analytics(db)
        assert len(result.trend) >= 1
        # The single point should have avg_score == 75
        assert result.trend[0].avg_score == pytest.approx(75.0)
        assert result.trend[0].count == 1

    def test_trend_sorted_chronologically(self, db: Database):
        for _ in range(3):
            exp = _make_experiment(db)
            _save_scoring(db, exp.id, _SCORING_DATA_GO)

        result = get_score_analytics(db)
        dates = [pt.date for pt in result.trend]
        assert dates == sorted(dates)

    def test_distribution_has_five_buckets(self, db: Database):
        result = get_score_analytics(db)
        assert len(result.distribution) == 5
        labels = [b.bucket_label for b in result.distribution]
        assert labels == ["0-20", "20-40", "40-60", "60-80", "80-100"]

    def test_date_filter(self, db: Database):
        exp = _make_experiment(db)
        _save_scoring(db, exp.id, _SCORING_DATA_GO)
        result = get_score_analytics(db, date_from="2099-01-01")
        assert all(b.count == 0 for b in result.distribution)


# ---------------------------------------------------------------------------
# get_pipeline_analytics
# ---------------------------------------------------------------------------


class TestGetPipelineAnalytics:
    def test_empty_db(self, db: Database):
        result = get_pipeline_analytics(db)
        assert result.total_experiments == 0
        assert result.completed_experiments == 0
        assert result.completion_rate == 0.0
        assert result.steps == []

    def test_counts_total_and_completed(self, db: Database):
        _make_experiment(db, ExperimentStatus.PENDING)
        _make_experiment(db, ExperimentStatus.COMPLETED)
        _make_experiment(db, ExperimentStatus.COMPLETED)

        result = get_pipeline_analytics(db)
        assert result.total_experiments == 3
        assert result.completed_experiments == 2
        assert result.completion_rate == pytest.approx(2 / 3)

    def test_step_counts_aggregated_by_sql(self, db: Database):
        for _ in range(3):
            exp = _make_experiment(db)
            db.save_step_result(
                experiment_id=exp.id,
                step_name="deep_research",
                step_number=1,
                data_json="{}",
            )
            db.save_step_result(
                experiment_id=exp.id,
                step_name="scoring",
                step_number=2,
                data_json="{}",
            )

        result = get_pipeline_analytics(db)
        step_map = {s.step_name: s for s in result.steps}

        assert "deep_research" in step_map
        assert step_map["deep_research"].total_executions == 3
        assert step_map["deep_research"].experiments_with_step == 3

        assert "scoring" in step_map
        assert step_map["scoring"].total_executions == 3

    def test_steps_ordered_by_step_number(self, db: Database):
        exp = _make_experiment(db)
        # Insert in reverse order
        db.save_step_result(exp.id, "scoring", 2, "{}")
        db.save_step_result(exp.id, "deep_research", 1, "{}")

        result = get_pipeline_analytics(db)
        step_numbers = [s.step_number for s in result.steps]
        assert step_numbers == sorted(step_numbers)

    def test_completion_rate_zero_when_none_complete(self, db: Database):
        _make_experiment(db, ExperimentStatus.PENDING)
        _make_experiment(db, ExperimentStatus.RUNNING)

        result = get_pipeline_analytics(db)
        assert result.completion_rate == 0.0

    def test_date_filter(self, db: Database):
        _make_experiment(db)
        result = get_pipeline_analytics(db, date_from="2099-01-01")
        assert result.total_experiments == 0

    def test_returns_correct_model_type(self, db: Database):
        from verdandi.models.analytics import PipelineAnalytics

        result = get_pipeline_analytics(db)
        assert isinstance(result, PipelineAnalytics)
