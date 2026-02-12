"""initial schema

Revision ID: dd015dde2562
Revises:
Create Date: 2026-02-12 18:47:33.365010

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd015dde2562"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Verdandi tables."""
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("idea_title", sa.Text, nullable=False, server_default=""),
        sa.Column("idea_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("current_step", sa.Integer, nullable=False, server_default="0"),
        sa.Column("worker_id", sa.Text, nullable=False, server_default=""),
        sa.Column("reviewed_by", sa.Text, nullable=False, server_default=""),
        sa.Column("review_notes", sa.Text, nullable=False, server_default=""),
        sa.Column("reviewed_at", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'awaiting_review', 'approved', "
            "'rejected', 'completed', 'failed', 'archived', 'no_go')",
            name="ck_experiments_status",
        ),
    )

    op.create_table(
        "step_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "experiment_id", sa.Integer, sa.ForeignKey("experiments.id"), nullable=False
        ),
        sa.Column("step_name", sa.Text, nullable=False),
        sa.Column("step_number", sa.Integer, nullable=False),
        sa.Column("data_json", sa.Text, nullable=False),
        sa.Column("worker_id", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.UniqueConstraint(
            "experiment_id", "step_name", name="uq_step_results_exp_step"
        ),
    )
    op.create_index("idx_step_results_experiment", "step_results", ["experiment_id"])

    op.create_table(
        "pipeline_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "experiment_id",
            sa.Integer,
            sa.ForeignKey("experiments.id"),
            nullable=True,
        ),
        sa.Column("step_name", sa.Text, nullable=False, server_default=""),
        sa.Column("event", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("worker_id", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_pipeline_log_experiment", "pipeline_log", ["experiment_id"])

    op.create_table(
        "topic_reservations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("topic_key", sa.Text, nullable=False),
        sa.Column("topic_description", sa.Text, nullable=False, server_default=""),
        sa.Column("niche_category", sa.Text, nullable=False, server_default=""),
        sa.Column("worker_id", sa.Text, nullable=False),
        sa.Column(
            "experiment_id",
            sa.Integer,
            sa.ForeignKey("experiments.id"),
            nullable=True,
        ),
        sa.Column("reserved_at", sa.Text, nullable=False),
        sa.Column("expires_at", sa.Text, nullable=False),
        sa.Column("renewed_at", sa.Text, nullable=True),
        sa.Column("released_at", sa.Text, nullable=True),
        sa.Column("embedding_json", sa.Text, nullable=True),
        sa.Column("fingerprint", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'released', 'completed')",
            name="ck_reservations_status",
        ),
    )
    op.create_index(
        "idx_reservations_active_topic",
        "topic_reservations",
        ["topic_key"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "idx_reservations_status",
        "topic_reservations",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    """Drop all Verdandi tables."""
    op.drop_table("topic_reservations")
    op.drop_table("pipeline_log")
    op.drop_table("step_results")
    op.drop_table("experiments")
