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

    # Research APIs (optional)
    tavily_api_key: str = ""
    serper_api_key: str = ""
    exa_api_key: str = ""
    perplexity_api_key: str = ""

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

    # LLM settings
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.7

    # Data directory
    data_dir: Path = Path("./data")

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

    # Huey settings
    huey_workers: int = 4
    huey_immediate: bool = False

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
