"""Topic reservation endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from verdandi.api.deps import DbDep
from verdandi.api.schemas import ActionResponse, ReservationResponse
from verdandi.db.orm import TopicReservationRow
from verdandi.orchestrator.coordination import TopicReservationManager

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.get("", response_model=list[ReservationResponse])
def list_reservations(
    db: DbDep,
    active_only: bool = True,
) -> list[ReservationResponse]:
    mgr = TopicReservationManager(db.Session)
    rows = mgr.list_active() if active_only else mgr.list_all()
    return [
        ReservationResponse(
            id=r["id"],
            topic_key=r["topic_key"],
            topic_description=r["topic_description"],
            worker_id=r["worker_id"],
            reserved_at=r["reserved_at"],
            expires_at=r["expires_at"],
            status=r["status"],
        )
        for r in rows
    ]


@router.delete("/{reservation_id}", response_model=ActionResponse)
def release_reservation(
    reservation_id: int,
    db: DbDep,
) -> ActionResponse:
    # Look up the reservation to get its topic_key and worker_id
    with db.Session() as session:
        row = session.scalars(
            select(TopicReservationRow).where(
                TopicReservationRow.id == reservation_id,
                TopicReservationRow.status == "active",
            )
        ).first()
        if row is None:
            raise ValueError(f"Active reservation {reservation_id} not found")
        topic_key = row.topic_key
        worker_id = row.worker_id

    mgr = TopicReservationManager(db.Session)
    mgr.release(worker_id, topic_key)
    return ActionResponse(message=f"Reservation {reservation_id} released")
