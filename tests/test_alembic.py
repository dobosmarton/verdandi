"""Tests for Alembic migration infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

if TYPE_CHECKING:
    from pathlib import Path


def _run_migrations(db_path: Path) -> None:
    """Run Alembic migrations to head on the given database."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


class TestAlembicMigrations:
    def test_upgrade_to_head_creates_all_tables(self, tmp_path: Path) -> None:
        """Running 'alembic upgrade head' creates all 4 expected tables."""
        db_path = tmp_path / "test_alembic.db"
        _run_migrations(db_path)

        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        assert "experiments" in tables
        assert "step_results" in tables
        assert "pipeline_log" in tables
        assert "topic_reservations" in tables
        assert "alembic_version" in tables

    def test_experiments_table_has_expected_columns(self, tmp_path: Path) -> None:
        """Verify experiments table schema matches ORM definition."""
        db_path = tmp_path / "test_alembic.db"
        _run_migrations(db_path)

        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("experiments")}
        engine.dispose()

        expected = {
            "id",
            "idea_title",
            "idea_summary",
            "status",
            "current_step",
            "worker_id",
            "reviewed_by",
            "review_notes",
            "reviewed_at",
            "created_at",
            "updated_at",
        }
        assert expected == columns

    def test_topic_reservations_has_partial_unique_index(self, tmp_path: Path) -> None:
        """Verify the partial unique index on topic_reservations exists."""
        db_path = tmp_path / "test_alembic.db"
        _run_migrations(db_path)

        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        indexes = inspector.get_indexes("topic_reservations")
        engine.dispose()

        active_topic_idx = [i for i in indexes if i["name"] == "idx_reservations_active_topic"]
        assert len(active_topic_idx) == 1
        assert active_topic_idx[0]["unique"]
        assert active_topic_idx[0]["column_names"] == ["topic_key"]

    def test_downgrade_drops_all_tables(self, tmp_path: Path) -> None:
        """Running downgrade removes all Verdandi tables."""
        db_path = tmp_path / "test_alembic.db"
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        # Upgrade then downgrade
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        engine.dispose()

        # Only alembic_version should remain
        assert "experiments" not in tables
        assert "step_results" not in tables
