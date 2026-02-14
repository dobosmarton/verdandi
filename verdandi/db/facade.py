"""SQLAlchemy-backed database connection and CRUD helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select, text

from verdandi.db.engine import create_db_engine, create_session_factory
from verdandi.db.orm import (
    Base,
    ExperimentRow,
    PipelineLogRow,
    StepResultRow,
)
from verdandi.models.experiment import Experiment, ExperimentStatus

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy import Engine
    from sqlalchemy.orm import Session, sessionmaker


class StepResultDict(TypedDict):
    id: int
    experiment_id: int
    step_name: str
    step_number: int
    data: object
    worker_id: str
    created_at: str


class LogEntryDict(TypedDict):
    id: int
    experiment_id: int | None
    step_name: str
    event: str
    message: str
    worker_id: str
    created_at: str


class Database:
    """SQLAlchemy-backed wrapper with CRUD helpers for experiments and step results."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._engine: Engine = create_db_engine(self.db_path)
        self._session_factory: sessionmaker[Session] = create_session_factory(self._engine)

    @property
    def engine(self) -> Engine:
        """Expose the SQLAlchemy engine for inspection and advanced use."""
        return self._engine

    @property
    def Session(self) -> sessionmaker[Session]:  # noqa: N802
        """Expose the session factory for consumers that need direct access."""
        return self._session_factory

    def init_schema(self) -> None:
        """Create all tables via ORM metadata."""
        Base.metadata.create_all(self._engine)

    def close(self) -> None:
        self._engine.dispose()

    def check_connection(self) -> bool:
        """Verify the database is reachable. Returns True or raises."""
        with self._session_factory() as session:
            session.execute(text("SELECT 1"))
        return True

    # --- Experiments ---

    def create_experiment(self, experiment: Experiment) -> Experiment:
        with self._session_factory() as session:
            row = ExperimentRow(
                idea_title=experiment.idea_title,
                idea_summary=experiment.idea_summary,
                status=experiment.status.value,
                current_step=experiment.current_step,
                worker_id=experiment.worker_id,
            )
            session.add(row)
            session.commit()
            return experiment.model_copy(update={"id": row.id})

    def get_experiment(self, experiment_id: int) -> Experiment | None:
        with self._session_factory() as session:
            row = session.get(ExperimentRow, experiment_id)
            if row is None:
                return None
            return self._row_to_experiment(row)

    def list_experiments(self, status: ExperimentStatus | None = None) -> list[Experiment]:
        with self._session_factory() as session:
            stmt = select(ExperimentRow).order_by(ExperimentRow.id)
            if status:
                stmt = stmt.where(ExperimentRow.status == status.value)
            rows = session.scalars(stmt).all()
            return [self._row_to_experiment(r) for r in rows]

    def update_experiment_status(
        self,
        experiment_id: int,
        status: ExperimentStatus,
        current_step: int | None = None,
        worker_id: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            row = session.get(ExperimentRow, experiment_id)
            if row is None:
                return
            row.status = status.value
            row.updated_at = _utcnow_str()
            if current_step is not None:
                row.current_step = current_step
            if worker_id is not None:
                row.worker_id = worker_id
            session.commit()

    def update_experiment_review(
        self,
        experiment_id: int,
        approved: bool,
        reviewed_by: str = "cli",
        notes: str = "",
    ) -> None:
        new_status = ExperimentStatus.APPROVED if approved else ExperimentStatus.REJECTED
        now = _utcnow_str()
        with self._session_factory() as session:
            row = session.get(ExperimentRow, experiment_id)
            if row is None:
                return
            row.status = new_status.value
            row.reviewed_by = reviewed_by
            row.review_notes = notes
            row.reviewed_at = now
            row.updated_at = now
            session.commit()

    def archive_experiment(self, experiment_id: int) -> None:
        self.update_experiment_status(experiment_id, ExperimentStatus.ARCHIVED)

    # --- Step Results ---

    def save_step_result(
        self,
        experiment_id: int,
        step_name: str,
        step_number: int,
        data_json: str,
        worker_id: str = "",
    ) -> int:
        with self._session_factory() as session:
            # Upsert: try to find existing, update or insert
            stmt = select(StepResultRow).where(
                StepResultRow.experiment_id == experiment_id,
                StepResultRow.step_name == step_name,
            )
            existing = session.scalars(stmt).first()
            if existing:
                existing.data_json = data_json
                existing.worker_id = worker_id
                session.commit()
                return existing.id
            row = StepResultRow(
                experiment_id=experiment_id,
                step_name=step_name,
                step_number=step_number,
                data_json=data_json,
                worker_id=worker_id,
            )
            session.add(row)
            session.commit()
            return row.id

    def get_step_result(self, experiment_id: int, step_name: str) -> StepResultDict | None:
        with self._session_factory() as session:
            stmt = select(StepResultRow).where(
                StepResultRow.experiment_id == experiment_id,
                StepResultRow.step_name == step_name,
            )
            row = session.scalars(stmt).first()
            if row is None:
                return None
            return self._step_row_to_dict(row)

    def get_all_step_results(self, experiment_id: int) -> list[StepResultDict]:
        with self._session_factory() as session:
            stmt = (
                select(StepResultRow)
                .where(StepResultRow.experiment_id == experiment_id)
                .order_by(StepResultRow.step_number)
            )
            rows = session.scalars(stmt).all()
            return [self._step_row_to_dict(r) for r in rows]

    # --- Pipeline Log ---

    def log_event(
        self,
        event: str,
        message: str = "",
        experiment_id: int | None = None,
        step_name: str = "",
        worker_id: str = "",
    ) -> None:
        with self._session_factory() as session:
            row = PipelineLogRow(
                experiment_id=experiment_id,
                step_name=step_name,
                event=event,
                message=message,
                worker_id=worker_id,
            )
            session.add(row)
            session.commit()

    def get_log(self, experiment_id: int) -> list[LogEntryDict]:
        with self._session_factory() as session:
            stmt = (
                select(PipelineLogRow)
                .where(PipelineLogRow.experiment_id == experiment_id)
                .order_by(PipelineLogRow.id)
            )
            rows = session.scalars(stmt).all()
            return [
                {
                    "id": r.id,
                    "experiment_id": r.experiment_id,
                    "step_name": r.step_name,
                    "event": r.event,
                    "message": r.message,
                    "worker_id": r.worker_id,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # --- Helpers ---

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _parse_dt_opt(value: str | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _row_to_experiment(row: ExperimentRow) -> Experiment:
        return Experiment(
            id=row.id,
            idea_title=row.idea_title,
            idea_summary=row.idea_summary,
            status=ExperimentStatus(row.status),
            current_step=row.current_step,
            worker_id=row.worker_id,
            reviewed_by=row.reviewed_by,
            review_notes=row.review_notes,
            reviewed_at=Database._parse_dt_opt(row.reviewed_at),
            created_at=Database._parse_dt(row.created_at),
            updated_at=Database._parse_dt(row.updated_at),
        )

    @staticmethod
    def _step_row_to_dict(row: StepResultRow) -> StepResultDict:
        return {
            "id": row.id,
            "experiment_id": row.experiment_id,
            "step_name": row.step_name,
            "step_number": row.step_number,
            "data": json.loads(row.data_json),
            "worker_id": row.worker_id,
            "created_at": row.created_at,
        }


def _utcnow_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
