"""Application configuration via pydantic-settings."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_worker_id() -> str:
    """Generate a unique worker ID from hostname + PID."""
    return f"{socket.gethostname()}-{os.getpid()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required
    anthropic_api_key: str = ""

    # Agent Council (optional — multi-model scoring)
    council_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"

    # Research APIs (optional)
    tavily_api_key: str = ""
    serper_api_key: str = ""
    exa_api_key: str = ""
    perplexity_api_key: str = ""
    socialdata_api_key: str = ""
    firecrawl_api_key: str = ""

    # Deployment APIs (optional)
    porkbun_api_key: str = ""
    porkbun_secret_key: str = ""
    cloudflare_api_token: str = ""
    cloudflare_account_id: str = ""

    # Analytics & email (optional)
    umami_url: str = ""
    umami_api_key: str = ""
    emailoctopus_api_key: str = ""

    # Social distribution (optional)
    twitter_bearer_token: str = ""
    linkedin_access_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    bluesky_handle: str = ""
    bluesky_app_password: str = ""

    # Pipeline settings
    require_human_review: bool = True
    max_retries: int = 3
    score_go_threshold: int = 70
    discovery_disruption_ratio: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Target ratio of disruption vs moonshot ideas (0.7 = 70% disruption)",
    )

    # LLM settings
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int | None = None
    llm_temperature: float = 0.7

    # Data directory
    data_dir: Path = Path("./data")

    # Custom strategies directory
    strategies_dir: Path = Path("./strategies")

    # Monitoring thresholds
    monitor_email_signup_go: float = 10.0
    monitor_email_signup_nogo: float = 3.0
    monitor_bounce_rate_max: float = 80.0
    monitor_min_visitors: int = 200

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"

    # API server
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Remote API (if set, CLI talks to HTTP instead of local SQLite)
    api_url: str = ""  # e.g. "http://10.0.0.5:8000"

    # Huey settings
    huey_workers: int = 4
    huey_immediate: bool = False

    # Research settings
    research_max_rounds: int = Field(
        default=2,
        ge=1,
        le=5,
        description=(
            "Maximum research collection rounds per experiment. "
            "1 = single pass (backward compatible). "
            "2 = one initial + one follow-up (recommended)."
        ),
    )
    research_confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "If gap analysis overall_confidence >= this threshold, skip remaining follow-up rounds."
        ),
    )

    # Dissent analysis settings
    dissent_enabled: bool = False
    dissent_max_rounds: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Max follow-up research rounds when council members disagree.",
    )
    dissent_dimension_threshold: int = Field(
        default=25,
        ge=10,
        le=50,
        description="Score spread (max-min) across voters to flag a dimension as contested.",
    )
    dissent_decision_split_required: bool = Field(
        default=False,
        description=(
            "If True, dissent resolution only triggers when voters disagree on "
            "GO/NO_GO decision. If False, dimension spread alone is sufficient."
        ),
    )

    # Discovery query variation
    discovery_query_variation: bool = True

    # Redis cache
    redis_url: str = ""  # Empty = cache disabled. e.g. "redis://localhost:6379/0"
    research_cache_ttl_hours: int = 24
    research_cache_enabled: bool = True

    # Qdrant vector database (optional, for orchestrator long-term memory)
    qdrant_url: str = ""  # Empty = disabled. e.g. "http://localhost:6333"
    qdrant_api_key: str = ""

    # Worker identity
    worker_id: str = Field(default_factory=_default_worker_id)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "verdandi.db"

    @property
    def huey_db_path(self) -> Path:
        return self.data_dir / "huey_queue.db"

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
