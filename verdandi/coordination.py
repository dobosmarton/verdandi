"""Multi-instance coordination: topic reservations and idea deduplication."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, TypedDict

import structlog
from sqlalchemy import select, update

from verdandi.orm import TopicReservationRow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = structlog.get_logger()

DEFAULT_TTL_HOURS = 24
HEARTBEAT_INTERVAL_HOURS = 6

# Stop words for keyword fingerprinting
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "for",
        "to",
        "of",
        "and",
        "in",
        "with",
        "that",
        "is",
        "it",
        "on",
        "by",
        "as",
        "at",
        "from",
        "or",
        "be",
        "this",
        "tool",
        "app",
        "platform",
        "software",
        "saas",
        "product",
        "service",
        "use",
        "using",
        "can",
        "will",
        "way",
        "make",
        "help",
        "helps",
    }
)


class ReservationInfo(TypedDict):
    id: int
    topic_key: str
    topic_description: str
    worker_id: str
    similarity: float


def idea_fingerprint(title: str, description: str) -> str:
    """Create a normalized keyword fingerprint for fast dedup comparison."""
    text_ = f"{title} {description}".lower()
    text_ = re.sub(r"[^a-z0-9\s]", "", text_)
    words = [w for w in text_.split() if w not in _STOP_WORDS and len(w) > 2]
    top_words = [w for w, _ in Counter(words).most_common(10)]
    top_words.sort()
    return "|".join(top_words)


def jaccard_similarity(fp1: str, fp2: str) -> float:
    """Compare two keyword fingerprints."""
    set1 = set(fp1.split("|")) if fp1 else set()
    set2 = set(fp2.split("|")) if fp2 else set()
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def normalize_topic_key(title: str) -> str:
    """Normalize a title into a stable topic key."""
    key = title.lower().strip()
    key = re.sub(r"[^a-z0-9\s-]", "", key)
    key = re.sub(r"\s+", "-", key)
    return key[:100]


class TopicReservationManager:
    """Manages topic reservations to prevent duplicate work across workers."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def expire_stale(self) -> int:
        """Expire reservations past their TTL. Returns number expired."""
        with self._session_factory() as session:
            result = session.execute(
                update(TopicReservationRow)
                .where(
                    TopicReservationRow.status == "active",
                    TopicReservationRow.expires_at < _utcnow_str(),
                )
                .values(status="expired")
            )
            session.commit()
            return result.rowcount

    def try_reserve(
        self,
        worker_id: str,
        topic_key: str,
        topic_description: str = "",
        niche_category: str = "",
        experiment_id: int | None = None,
        embedding: list[float] | None = None,
        fingerprint: str | None = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ) -> bool:
        """Attempt to atomically reserve a topic. Returns True if successful."""
        expires_at = (datetime.now(UTC) + timedelta(hours=ttl_hours)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

        with self._session_factory() as session:
            # Use raw DBAPI connection for BEGIN IMMEDIATE (SQLite atomicity)
            raw_conn = session.connection().connection.dbapi_connection
            raw_conn.execute("BEGIN IMMEDIATE")
            try:
                # Expire stale reservations inline
                session.execute(
                    update(TopicReservationRow)
                    .where(
                        TopicReservationRow.status == "active",
                        TopicReservationRow.expires_at < _utcnow_str(),
                    )
                    .values(status="expired")
                )

                # Check exact key match
                existing = session.scalars(
                    select(TopicReservationRow).where(
                        TopicReservationRow.topic_key == topic_key,
                        TopicReservationRow.status == "active",
                    )
                ).first()
                if existing:
                    raw_conn.execute("ROLLBACK")
                    return False

                row = TopicReservationRow(
                    topic_key=topic_key,
                    topic_description=topic_description,
                    niche_category=niche_category,
                    worker_id=worker_id,
                    experiment_id=experiment_id,
                    expires_at=expires_at,
                    embedding_json=json.dumps(embedding) if embedding else None,
                    fingerprint=fingerprint,
                    status="active",
                )
                session.add(row)
                session.flush()
                raw_conn.execute("COMMIT")
                return True
            except Exception:
                raw_conn.execute("ROLLBACK")
                raise

    def release(
        self,
        worker_id: str,
        topic_key: str,
        completed: bool = False,
    ) -> bool:
        """Explicitly release a reservation. Returns True if found and released."""
        new_status = "completed" if completed else "released"
        with self._session_factory() as session:
            result = session.execute(
                update(TopicReservationRow)
                .where(
                    TopicReservationRow.topic_key == topic_key,
                    TopicReservationRow.worker_id == worker_id,
                    TopicReservationRow.status == "active",
                )
                .values(status=new_status, released_at=_utcnow_str())
            )
            session.commit()
            return result.rowcount == 1

    def renew(
        self,
        worker_id: str,
        topic_key: str,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ) -> bool:
        """Heartbeat: extend the reservation TTL. Returns True if successful."""
        new_expires = (datetime.now(UTC) + timedelta(hours=ttl_hours)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

        with self._session_factory() as session:
            result = session.execute(
                update(TopicReservationRow)
                .where(
                    TopicReservationRow.topic_key == topic_key,
                    TopicReservationRow.worker_id == worker_id,
                    TopicReservationRow.status == "active",
                )
                .values(expires_at=new_expires, renewed_at=_utcnow_str())
            )
            session.commit()
            return result.rowcount == 1

    def find_similar_by_fingerprint(
        self,
        fingerprint: str,
        threshold: float = 0.6,
    ) -> list[ReservationInfo]:
        """Find active reservations with similar keyword fingerprints."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(TopicReservationRow).where(
                    TopicReservationRow.status == "active",
                    TopicReservationRow.fingerprint.isnot(None),
                )
            ).all()

            matches: list[ReservationInfo] = []
            for row in rows:
                sim = jaccard_similarity(fingerprint, row.fingerprint or "")
                if sim >= threshold:
                    matches.append(
                        ReservationInfo(
                            id=row.id,
                            topic_key=row.topic_key,
                            topic_description=row.topic_description,
                            worker_id=row.worker_id,
                            similarity=sim,
                        )
                    )
            return sorted(matches, key=lambda x: -x["similarity"])

    def find_similar_by_embedding(
        self,
        embedding: list[float],
        threshold: float = 0.82,
    ) -> list[ReservationInfo]:
        """Find active reservations with similar embeddings.

        Stubbed for now — returns empty list. Real implementation requires
        sentence-transformers or similar embedding library.
        """
        # TODO: Implement when sentence-transformers is added
        return []

    def list_active(self) -> list[dict]:
        """List all active topic reservations."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(TopicReservationRow)
                .where(TopicReservationRow.status == "active")
                .order_by(TopicReservationRow.reserved_at)
            ).all()
            return [
                {
                    "id": r.id,
                    "topic_key": r.topic_key,
                    "topic_description": r.topic_description,
                    "niche_category": r.niche_category,
                    "worker_id": r.worker_id,
                    "experiment_id": r.experiment_id,
                    "reserved_at": r.reserved_at,
                    "expires_at": r.expires_at,
                    "fingerprint": r.fingerprint,
                }
                for r in rows
            ]

    def list_all(self) -> list[dict]:
        """List all topic reservations (including expired/released/completed)."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(TopicReservationRow).order_by(TopicReservationRow.id)
            ).all()
            return [
                {
                    "id": r.id,
                    "topic_key": r.topic_key,
                    "topic_description": r.topic_description,
                    "niche_category": r.niche_category,
                    "worker_id": r.worker_id,
                    "experiment_id": r.experiment_id,
                    "reserved_at": r.reserved_at,
                    "expires_at": r.expires_at,
                    "status": r.status,
                    "fingerprint": r.fingerprint,
                }
                for r in rows
            ]


def _utcnow_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
