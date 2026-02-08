"""SQLAlchemy engine factory and session maker for SQLite."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from sqlalchemy import Engine


def create_db_engine(db_path: str | object, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine configured for SQLite with WAL mode."""
    path_str = str(db_path)
    url = "sqlite://" if path_str == ":memory:" else f"sqlite:///{path_str}"

    engine = create_engine(url, echo=echo, connect_args={"timeout": 30.0})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: object, _connection_record: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
