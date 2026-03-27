"""Analytics REST API endpoints.

GET /api/v1/analytics/overview    — total experiments, GO rate, avg score
GET /api/v1/analytics/providers   — per-provider reliability stats
GET /api/v1/analytics/scores      — score distribution and trend
GET /api/v1/analytics/pipeline    — step completion counts, throughput

All endpoints support optional ?from=YYYY-MM-DD&to=YYYY-MM-DD filtering.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from verdandi.analytics import (
    get_overview,
    get_pipeline_analytics,
    get_provider_analytics,
    get_score_analytics,
)
from verdandi.api.deps import DbDep
from verdandi.models.analytics import (
    OverviewStats,
    PipelineAnalytics,
    ProviderAnalytics,
    ScoreAnalytics,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewStats)
def analytics_overview(
    db: DbDep,
    from_: str | None = Query(
        default=None,
        alias="from",
        description="Start date (YYYY-MM-DD)",
    ),
    to: str | None = Query(
        default=None,
        description="End date (YYYY-MM-DD)",
    ),
) -> OverviewStats:
    """Return a high-level summary: total experiments, GO rate, and mean score."""
    return get_overview(db, date_from=from_, date_to=to)


@router.get("/providers", response_model=ProviderAnalytics)
def analytics_providers(
    db: DbDep,
    from_: str | None = Query(
        default=None,
        alias="from",
        description="Start date (YYYY-MM-DD)",
    ),
    to: str | None = Query(
        default=None,
        description="End date (YYYY-MM-DD)",
    ),
) -> ProviderAnalytics:
    """Return per-provider reliability statistics derived from research step results."""
    return get_provider_analytics(db, date_from=from_, date_to=to)


@router.get("/scores", response_model=ScoreAnalytics)
def analytics_scores(
    db: DbDep,
    from_: str | None = Query(
        default=None,
        alias="from",
        description="Start date (YYYY-MM-DD)",
    ),
    to: str | None = Query(
        default=None,
        description="End date (YYYY-MM-DD)",
    ),
) -> ScoreAnalytics:
    """Return score distribution histogram, daily trend, and decision counts."""
    return get_score_analytics(db, date_from=from_, date_to=to)


@router.get("/pipeline", response_model=PipelineAnalytics)
def analytics_pipeline(
    db: DbDep,
    from_: str | None = Query(
        default=None,
        alias="from",
        description="Start date (YYYY-MM-DD)",
    ),
    to: str | None = Query(
        default=None,
        description="End date (YYYY-MM-DD)",
    ),
) -> PipelineAnalytics:
    """Return step completion counts and overall pipeline throughput."""
    return get_pipeline_analytics(db, date_from=from_, date_to=to)
