"""FastAPI application factory and entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from verdandi.api.middleware import CorrelationIdMiddleware, add_exception_handlers
from verdandi.api.routes import actions, experiments, reservations, reviews, steps, system
from verdandi.config import Settings
from verdandi.db import Database
from verdandi.logging import configure_logging

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize DB and settings on startup, cleanup on shutdown."""
    settings = Settings()
    settings.ensure_data_dir()

    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    db = Database(settings.db_path)
    db.init_schema()

    app.state.db = db
    app.state.settings = settings

    logger.info("Verdandi API started", host=settings.api_host, port=settings.api_port)
    yield

    db.close()
    logger.info("Verdandi API shut down")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Verdandi",
        description="Autonomous product validation factory API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    add_exception_handlers(app)

    # Prometheus metrics endpoint
    from prometheus_client import make_asgi_app

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Mount routes under /api/v1
    prefix = "/api/v1"
    app.include_router(system.router, prefix=prefix)
    app.include_router(experiments.router, prefix=prefix)
    app.include_router(steps.router, prefix=prefix)
    app.include_router(reviews.router, prefix=prefix)
    app.include_router(reservations.router, prefix=prefix)
    app.include_router(actions.router, prefix=prefix)

    return app


def main() -> None:
    """Entry point for `verdandi-api` command."""
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "verdandi.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
    )
