from typing import Any
import uuid
from sqlalchemy.orm import Session

from app.audit.serializers import to_json_serializable
from app.models.outbox_event import OutboxEvent, OutboxStatus


class OutboxService:
    """
    Platform-level generic transactional outbox service.
    Persists integration and domain events into the outbox_events table
    within the caller's active database transaction.

    Crucial Architectural Invariant:
    - Does NOT call `session.commit()`. The calling service layer manages the business transaction boundary.
    - Does NOT contain entity-specific logic or contracts.
    """

    def record(
        self,
        *,
        session: Session,
        application_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        country_id: uuid.UUID | None,
        payload: dict[str, Any],
        request_id: str | uuid.UUID | None = None,
    ) -> OutboxEvent:
        """
        Adds an OutboxEvent entry to the session without committing.
        """
        event = OutboxEvent(
            application_id=application_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            country_id=country_id,
            payload=to_json_serializable(payload),
            status=OutboxStatus.PENDING.value,
            attempt_count=0,
            request_id=str(request_id) if request_id is not None else None,
        )
        session.add(event)
        return event


# Module-level instance and convenience helper
outbox_service = OutboxService()


def record_outbox_event(
    *,
    session: Session,
    application_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    country_id: uuid.UUID | None,
    payload: dict[str, Any],
    request_id: str | uuid.UUID | None = None,
) -> OutboxEvent:
    return outbox_service.record(
        session=session,
        application_id=application_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        country_id=country_id,
        payload=payload,
        request_id=request_id,
    )
