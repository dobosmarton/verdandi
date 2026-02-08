"""FastAPI dependency injection."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from verdandi.config import Settings
from verdandi.db import Database


def _get_db(request: Request) -> Database:
    """Get the database instance from app state."""
    return request.app.state.db  # type: ignore[no-any-return]


def _get_settings(request: Request) -> Settings:
    """Get the settings instance from app state."""
    return request.app.state.settings  # type: ignore[no-any-return]


DbDep = Annotated[Database, Depends(_get_db)]
SettingsDep = Annotated[Settings, Depends(_get_settings)]
