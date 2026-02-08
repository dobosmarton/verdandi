"""SQLAlchemy ORM models mapping to the Verdandi database tables."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Base(DeclarativeBase):
    pass


class ExperimentRow(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idea_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    idea_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Review fields
    reviewed_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_at: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Timestamps
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=_utcnow_str)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default=_utcnow_str)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'awaiting_review', 'approved', "
            "'rejected', 'completed', 'failed', 'archived', 'no_go')",
            name="ck_experiments_status",
        ),
    )


class StepResultRow(Base):
    __tablename__ = "step_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(Text, nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    worker_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=_utcnow_str)

    __table_args__ = (
        UniqueConstraint("experiment_id", "step_name", name="uq_step_results_exp_step"),
        Index("idx_step_results_experiment", "experiment_id"),
    )


class PipelineLogRow(Base):
    __tablename__ = "pipeline_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("experiments.id"), nullable=True
    )
    step_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    event: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worker_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=_utcnow_str)

    __table_args__ = (Index("idx_pipeline_log_experiment", "experiment_id"),)


class TopicReservationRow(Base):
    __tablename__ = "topic_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_key: Mapped[str] = mapped_column(Text, nullable=False)
    topic_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    niche_category: Mapped[str] = mapped_column(Text, nullable=False, default="")

    worker_id: Mapped[str] = mapped_column(Text, nullable=False)
    experiment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("experiments.id"), nullable=True
    )

    reserved_at: Mapped[str] = mapped_column(Text, nullable=False, default=_utcnow_str)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    renewed_at: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    released_at: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'released', 'completed')",
            name="ck_reservations_status",
        ),
        # Only one active reservation per topic_key (partial unique index)
        Index(
            "idx_reservations_active_topic",
            "topic_key",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
        Index("idx_reservations_status", "status", "expires_at"),
    )
