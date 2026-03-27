"""Analytics service: SQL aggregations over historical experiment data.

All heavy lifting is done in SQL via SQLAlchemy Core expressions —
no Python-side loops over large result sets.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import case, cast, func, select, text

from verdandi.db.orm import ExperimentRow, PipelineLogRow, StepResultRow
from verdandi.models.analytics import (
    OverviewStats,
    PipelineAnalytics,
    ProviderAnalytics,
    ProviderReliabilityStats,
    ScoreAnalytics,
    ScoreDistributionBucket,
    ScoreTrendPoint,
    StepDurationStats,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker, Session

    from verdandi.db import Database


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _date_filter_clause(
    column: object,
    date_from: str | None,
    date_to: str | None,
) -> list[object]:
    """Return a list of SQLAlchemy WHERE clauses for an ISO-date range."""
    clauses: list[object] = []
    if date_from:
        clauses.append(column >= f"{date_from}T00:00:00.000000Z")  # type: ignore[operator]
    if date_to:
        clauses.append(column <= f"{date_to}T23:59:59.999999Z")  # type: ignore[operator]
    return clauses


# ---------------------------------------------------------------------------
# Public analytics functions — each opens its own session(s)
# ---------------------------------------------------------------------------


def get_overview(
    db: Database,
    date_from: str | None = None,
    date_to: str | None = None,
) -> OverviewStats:
    """Return high-level experiment counts, GO rate, and average score.

    * Status counts: pure SQL GROUP BY on experiments.status.
    * Score aggregation: iterate only over the (small) scoring step_results
      that pass the date filter — SQLite has no JSON extract function, so we
      pull only the data_json column and parse in Python.
    """
    with db.Session() as session:
        # --- 1. Status distribution ---
        date_clauses = _date_filter_clause(ExperimentRow.created_at, date_from, date_to)

        status_stmt = select(
            ExperimentRow.status,
            func.count(ExperimentRow.id).label("cnt"),
        ).group_by(ExperimentRow.status)
        for clause in date_clauses:
            status_stmt = status_stmt.where(clause)

        rows = session.execute(status_stmt).all()
        by_status: dict[str, int] = {r.status: r.cnt for r in rows}
        total = sum(by_status.values())

        # --- 2. Score stats from scoring step_results ---
        score_stmt = select(StepResultRow.data_json).where(
            StepResultRow.step_name == "scoring"
        )
        # Join experiments for date filtering on experiment creation date
        if date_clauses:
            score_stmt = score_stmt.join(
                ExperimentRow,
                StepResultRow.experiment_id == ExperimentRow.id,
            )
            for clause in date_clauses:
                score_stmt = score_stmt.where(clause)

        score_rows = session.scalars(score_stmt).all()

    scores: list[int] = []
    go_count = 0
    for data_json in score_rows:
        try:
            data = json.loads(data_json)
        except (json.JSONDecodeError, TypeError):
            continue
        total_score = data.get("total_score")
        decision = data.get("decision", "")
        if isinstance(total_score, int | float):
            scores.append(int(total_score))
        if isinstance(decision, str) and decision.lower() == "go":
            go_count += 1

    experiments_with_score = len(scores)
    go_rate = go_count / experiments_with_score if experiments_with_score else 0.0
    avg_score = sum(scores) / experiments_with_score if experiments_with_score else None

    return OverviewStats(
        total_experiments=total,
        by_status=by_status,
        go_rate=go_rate,
        avg_score=avg_score,
        experiments_with_score=experiments_with_score,
        date_from=date_from,
        date_to=date_to,
    )


def get_provider_analytics(
    db: Database,
    date_from: str | None = None,
    date_to: str | None = None,
) -> ProviderAnalytics:
    """Return per-provider reliability stats derived from pipeline_log.

    Provider reliability is inferred from step_start / step_error events
    in pipeline_log for the "deep_research" step, where each provider runs
    as a sub-call.  Since there is no per-provider log row, we fall back to
    parsing the search_results[].source field from the deep_research
    step_result JSON — counting distinct sources as "successful" calls and
    cross-referencing step_error rows to estimate failures.

    Strategy:
    - For each deep_research StepResultRow, parse search_results and count
      by .source  → these are confirmed successful provider calls.
    - For each step_error log row on "deep_research", add 1 failure across
      all configured providers (coarse approximation — we can't tell which
      provider failed without structured error data).
    """
    with db.Session() as session:
        # Collect all deep_research data_json (filtered by experiment creation date)
        research_stmt = select(StepResultRow.data_json).where(
            StepResultRow.step_name == "deep_research"
        )
        if date_from or date_to:
            date_clauses = _date_filter_clause(ExperimentRow.created_at, date_from, date_to)
            research_stmt = research_stmt.join(
                ExperimentRow,
                StepResultRow.experiment_id == ExperimentRow.id,
            )
            for clause in date_clauses:
                research_stmt = research_stmt.where(clause)

        research_rows = session.scalars(research_stmt).all()

        # Count step_error events for deep_research (date-filtered via join)
        error_stmt = select(func.count(PipelineLogRow.id)).where(
            PipelineLogRow.step_name == "deep_research",
            PipelineLogRow.event == "step_error",
        )
        if date_from or date_to:
            date_clauses_log = _date_filter_clause(PipelineLogRow.created_at, date_from, date_to)
            for clause in date_clauses_log:
                error_stmt = error_stmt.where(clause)

        total_errors: int = session.execute(error_stmt).scalar_one()

    # Parse search results to count per-provider successful calls
    source_counts: Counter[str] = Counter()
    for data_json in research_rows:
        try:
            data = json.loads(data_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for sr in data.get("search_results", []):
            src = sr.get("source", "")
            if src:
                source_counts[src] += 1

    # If no research data exists (empty DB or date filter excluded everything),
    # return an empty list — there's nothing meaningful to report.
    if not source_counts and total_errors == 0:
        return ProviderAnalytics(providers=[], date_from=date_from, date_to=date_to)

    # Known providers: those that appear in source_counts plus any that only
    # show up as errors (we have no way to name them, so we distribute errors
    # evenly across observed providers, or all configured ones if none observed).
    known_providers = sorted(source_counts.keys()) or ["tavily", "serper", "exa", "perplexity", "hn"]
    errors_per_provider = total_errors // max(len(known_providers), 1)
    remainder = total_errors % max(len(known_providers), 1)

    stats: list[ProviderReliabilityStats] = []
    for i, provider in enumerate(known_providers):
        successful = source_counts.get(provider, 0)
        # Distribute errors: first `remainder` providers get 1 extra
        failed = errors_per_provider + (1 if i < remainder else 0)
        total_calls = successful + failed
        stats.append(
            ProviderReliabilityStats(
                provider=provider,
                total_calls=total_calls,
                successful_calls=successful,
                failed_calls=failed,
                success_rate=successful / total_calls if total_calls else 1.0,
            )
        )

    return ProviderAnalytics(
        providers=stats,
        date_from=date_from,
        date_to=date_to,
    )


def get_score_analytics(
    db: Database,
    date_from: str | None = None,
    date_to: str | None = None,
) -> ScoreAnalytics:
    """Return score distribution histogram, trend over time, and decision counts.

    Distribution buckets: 0–20, 20–40, 40–60, 60–80, 80–100.
    Trend: group scoring step_results by the date portion of created_at and
    compute the mean total_score per day.
    """
    with db.Session() as session:
        score_stmt = select(
            StepResultRow.data_json,
            StepResultRow.created_at,
        ).where(StepResultRow.step_name == "scoring")

        if date_from or date_to:
            date_clauses = _date_filter_clause(ExperimentRow.created_at, date_from, date_to)
            score_stmt = score_stmt.join(
                ExperimentRow,
                StepResultRow.experiment_id == ExperimentRow.id,
            )
            for clause in date_clauses:
                score_stmt = score_stmt.where(clause)

        score_stmt = score_stmt.order_by(StepResultRow.created_at)
        rows = session.execute(score_stmt).all()

    # Parse in Python (SQLite lacks JSON functions in older versions)
    bucket_counts: dict[str, int] = {
        "0-20": 0,
        "20-40": 0,
        "40-60": 0,
        "60-80": 0,
        "80-100": 0,
    }
    decision_counts: Counter[str] = Counter()
    # For trend: date string -> (sum_score, count)
    date_accumulator: dict[str, tuple[int, int]] = {}

    for data_json, created_at in rows:
        try:
            data = json.loads(data_json)
        except (json.JSONDecodeError, TypeError):
            continue

        total_score = data.get("total_score")
        decision = data.get("decision", "unknown")

        if isinstance(total_score, int | float):
            score_int = int(total_score)
            # Bucket assignment: labels are inclusive upper bounds (0–20, 21–40, …)
            if score_int <= 20:
                bucket_counts["0-20"] += 1
            elif score_int <= 40:
                bucket_counts["20-40"] += 1
            elif score_int <= 60:
                bucket_counts["40-60"] += 1
            elif score_int <= 80:
                bucket_counts["60-80"] += 1
            else:
                bucket_counts["80-100"] += 1

            # Trend: extract date portion "YYYY-MM-DD" from ISO timestamp
            date_str = str(created_at)[:10] if created_at else "unknown"
            prev_sum, prev_cnt = date_accumulator.get(date_str, (0, 0))
            date_accumulator[date_str] = (prev_sum + score_int, prev_cnt + 1)

        if isinstance(decision, str) and decision:
            decision_counts[decision.lower()] += 1

    # Build distribution
    bucket_definitions = [
        ("0-20", 0, 20),
        ("20-40", 20, 40),
        ("40-60", 40, 60),
        ("60-80", 60, 80),
        ("80-100", 80, 100),
    ]
    distribution = [
        ScoreDistributionBucket(
            bucket_label=label,
            low=low,
            high=high,
            count=bucket_counts[label],
        )
        for label, low, high in bucket_definitions
    ]

    # Build trend (sorted chronologically)
    trend = [
        ScoreTrendPoint(
            date=date_str,
            avg_score=round(total / count, 2),
            count=count,
        )
        for date_str, (total, count) in sorted(date_accumulator.items())
    ]

    return ScoreAnalytics(
        distribution=distribution,
        trend=trend,
        decision_counts=dict(decision_counts),
        date_from=date_from,
        date_to=date_to,
    )


def get_pipeline_analytics(
    db: Database,
    date_from: str | None = None,
    date_to: str | None = None,
) -> PipelineAnalytics:
    """Return step completion counts and pipeline throughput.

    Uses SQL GROUP BY on step_results to count executions per step.
    Completion rate = experiments with status='completed' / total.
    """
    with db.Session() as session:
        # Step completion counts via SQL GROUP BY
        step_stmt = select(
            StepResultRow.step_name,
            StepResultRow.step_number,
            func.count(StepResultRow.id).label("total_executions"),
            func.count(StepResultRow.experiment_id.distinct()).label("experiments_with_step"),
        ).group_by(StepResultRow.step_name, StepResultRow.step_number)

        if date_from or date_to:
            date_clauses = _date_filter_clause(ExperimentRow.created_at, date_from, date_to)
            step_stmt = step_stmt.join(
                ExperimentRow,
                StepResultRow.experiment_id == ExperimentRow.id,
            )
            for clause in date_clauses:
                step_stmt = step_stmt.where(clause)

        step_stmt = step_stmt.order_by(StepResultRow.step_number)
        step_rows = session.execute(step_stmt).all()

        # Experiment totals
        exp_date_clauses = _date_filter_clause(ExperimentRow.created_at, date_from, date_to)
        total_stmt = select(func.count(ExperimentRow.id))
        completed_stmt = select(func.count(ExperimentRow.id)).where(
            ExperimentRow.status == "completed"
        )
        for clause in exp_date_clauses:
            total_stmt = total_stmt.where(clause)
            completed_stmt = completed_stmt.where(clause)

        total_experiments: int = session.execute(total_stmt).scalar_one()
        completed_experiments: int = session.execute(completed_stmt).scalar_one()

    steps = [
        StepDurationStats(
            step_name=r.step_name,
            step_number=r.step_number,
            total_executions=r.total_executions,
            experiments_with_step=r.experiments_with_step,
        )
        for r in step_rows
    ]

    completion_rate = completed_experiments / total_experiments if total_experiments else 0.0

    return PipelineAnalytics(
        steps=steps,
        total_experiments=total_experiments,
        completed_experiments=completed_experiments,
        completion_rate=completion_rate,
        date_from=date_from,
        date_to=date_to,
    )
