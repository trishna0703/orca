from typing import Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent, OutboxStatus


class OutboxRepository:
    """
    Data access layer for OutboxEvent records.
    Provides deterministic querying for pending events (for future dispatchers)
    without committing transactions.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_pending(
        self,
        *,
        limit: int = 50,
        application_id: uuid.UUID | None = None,
        for_update: bool = False,
        skip_locked: bool = False,
    ) -> list[OutboxEvent]:
        """
        Retrieves pending outbox events ordered deterministically by created_at ASC, id ASC.
        Supports SELECT ... FOR UPDATE SKIP LOCKED for concurrent processor workers.
        """
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING.value)
            .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
            .limit(limit)
        )
        if application_id is not None:
            stmt = stmt.where(OutboxEvent.application_id == application_id)

        if for_update:
            stmt = stmt.with_for_update(skip_locked=skip_locked)

        return list(self.session.execute(stmt).scalars().all())

    def get_by_id(self, event_id: uuid.UUID) -> OutboxEvent | None:
        return self.session.get(OutboxEvent, event_id)
