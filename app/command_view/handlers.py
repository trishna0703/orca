import logging
from sqlalchemy.orm import Session

from app.command_view.repository import CommandViewRepository
from app.events.contracts import CaseClosedV1Payload, CaseCreatedV1Payload
from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)

COMMAND_VIEW_CONSUMER_ID = "command-view.case-metrics.v1"


def handle_case_created(
    *,
    session: Session,
    event: OutboxEvent,
) -> None:
    """
    Projection handler for 'case.created.v1'.
    Increments open_count for the case's country.
    Enforces idempotency using ProcessedEvent(event_id, consumer).
    """
    repo = CommandViewRepository(session)

    # 1. Idempotency check
    if repo.is_event_processed(event_id=event.id, consumer=COMMAND_VIEW_CONSUMER_ID):
        logger.info(
            "Event id=%s already processed by %s. Skipping projection mutation.",
            event.id,
            COMMAND_VIEW_CONSUMER_ID,
        )
        return

    # 2. Validate payload contract
    payload = CaseCreatedV1Payload.model_validate(event.payload)

    # 3. Retrieve row with FOR UPDATE lock and mutate counter
    metric = repo.get_or_create_metric_for_update(payload.country_id)
    metric.open_count += 1
    session.flush()

    # 4. Record consumer idempotency
    repo.mark_event_processed(event_id=event.id, consumer=COMMAND_VIEW_CONSUMER_ID)
    logger.info(
        "Updated Command View metrics for country_id=%s on case.created: open_count=%s",
        payload.country_id,
        metric.open_count,
    )


def handle_case_closed(
    *,
    session: Session,
    event: OutboxEvent,
) -> None:
    """
    Projection handler for 'case.closed.v1'.
    Decrements previous status counter (open or in_progress) and increments closed_count.
    Enforces idempotency and non-negative count constraints.
    """
    repo = CommandViewRepository(session)

    # 1. Idempotency check
    if repo.is_event_processed(event_id=event.id, consumer=COMMAND_VIEW_CONSUMER_ID):
        logger.info(
            "Event id=%s already processed by %s. Skipping projection mutation.",
            event.id,
            COMMAND_VIEW_CONSUMER_ID,
        )
        return

    # 2. Validate payload contract
    payload = CaseClosedV1Payload.model_validate(event.payload)

    # 3. Retrieve row with FOR UPDATE lock and mutate counters
    metric = repo.get_or_create_metric_for_update(payload.country_id)

    if payload.previous_status == "open":
        if metric.open_count <= 0:
            raise ValueError(
                f"Cannot decrement open_count below 0 for country {payload.country_id} (current={metric.open_count})"
            )
        metric.open_count -= 1
        metric.closed_count += 1
    elif payload.previous_status == "in_progress":
        if metric.in_progress_count <= 0:
            raise ValueError(
                f"Cannot decrement in_progress_count below 0 for country {payload.country_id} (current={metric.in_progress_count})"
            )
        metric.in_progress_count -= 1
        metric.closed_count += 1
    else:
        raise ValueError(
            f"Invalid previous_status '{payload.previous_status}' for case.closed.v1 transition"
        )

    session.flush()

    # 4. Record consumer idempotency
    repo.mark_event_processed(event_id=event.id, consumer=COMMAND_VIEW_CONSUMER_ID)
    logger.info(
        "Updated Command View metrics for country_id=%s on case.closed: open_count=%s, in_progress=%s, closed_count=%s",
        payload.country_id,
        metric.open_count,
        metric.in_progress_count,
        metric.closed_count,
    )
