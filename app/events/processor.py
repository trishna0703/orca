from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import uuid
from sqlalchemy.orm import Session

from app.events.dispatcher import EventDispatcher
from app.events.repository import OutboxRepository
from app.models.outbox_event import OutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


@dataclass
class ProcessingStats:
    processed: int = 0
    failed: int = 0
    skipped: int = 0


def process_pending_events(
    *,
    session: Session,
    dispatcher: EventDispatcher,
    batch_size: int = 50,
    application_id: uuid.UUID | None = None,
    for_update: bool = True,
    skip_locked: bool = True,
) -> ProcessingStats:
    """
    Processes pending OutboxEvent records in deterministic order (created_at ASC, id ASC).

    Transaction and Atomicity Strategy:
    - Uses SELECT ... FOR UPDATE SKIP LOCKED to safely claim events across concurrent workers without blocking.
    - Each event is dispatched in an isolated unit of work:
      * Handlers mutate projections and insert processed_events records in `session`.
      * If all handlers succeed: event.status is updated to 'processed', event.processed_at is set, and session.commit() seals both the projection and outbox status.
      * If a handler raises an exception: session.rollback() discards projection and idempotency changes, then in a separate transaction event.attempt_count is incremented and marked 'failed' if attempts exceed MAX_ATTEMPTS.
      * If no handlers are registered for the event: it is marked processed as 'skipped' so it does not block the pipeline.
    """
    repo = OutboxRepository(session)
    pending_events = repo.list_pending(
        limit=batch_size,
        application_id=application_id,
        for_update=for_update,
        skip_locked=skip_locked,
    )

    stats = ProcessingStats()

    for event in pending_events:
        event_id = event.id
        event_type = event.event_type
        logger.info(
            "Processing outbox event id=%s type=%s aggregate=%s request_id=%s",
            event_id,
            event_type,
            event.aggregate_id,
            event.request_id,
        )

        try:
            # Dispatch to registered handlers
            has_handlers = dispatcher.dispatch(session=session, event=event)

            # Update event status on success
            now = datetime.now(timezone.utc)
            event.status = OutboxStatus.PROCESSED.value
            event.processed_at = now

            session.commit()

            if has_handlers:
                stats.processed += 1
            else:
                stats.skipped += 1

        except Exception as exc:
            logger.exception(
                "Error processing outbox event id=%s type=%s: %s",
                event_id,
                event_type,
                exc,
            )
            # Rollback projection changes from the failed handler
            session.rollback()

            # In a clean transaction, record failure / increment attempt count on the OutboxEvent
            try:
                failed_event = session.get(OutboxEvent, event_id)
                if failed_event:
                    failed_event.attempt_count += 1
                    if failed_event.attempt_count >= MAX_ATTEMPTS:
                        failed_event.status = OutboxStatus.FAILED.value
                    else:
                        failed_event.status = OutboxStatus.PENDING.value
                    session.commit()
            except Exception as inner_exc:
                session.rollback()
                logger.exception(
                    "Failed to update status for failed event id=%s: %s",
                    event_id,
                    inner_exc,
                )

            stats.failed += 1

    return stats
