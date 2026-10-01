from collections.abc import Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.command_view_case_metric import CommandViewCaseMetric
from app.models.processed_event import ProcessedEvent


class CommandViewRepository:
    """
    Data access repository for Command View read model and idempotency checks.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def is_event_processed(self, *, event_id: uuid.UUID, consumer: str) -> bool:
        """
        Checks whether the given (event_id, consumer) has already been processed.
        """
        stmt = (
            select(ProcessedEvent.event_id)
            .where(
                ProcessedEvent.event_id == event_id,
                ProcessedEvent.consumer == consumer,
            )
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def mark_event_processed(self, *, event_id: uuid.UUID, consumer: str) -> None:
        """
        Inserts an idempotency ledger record for (event_id, consumer).
        Does NOT commit so it participates in the consumer's transaction.
        """
        record = ProcessedEvent(event_id=event_id, consumer=consumer)
        self.session.add(record)
        self.session.flush()

    def get_or_create_metric_for_update(
        self, country_id: uuid.UUID
    ) -> CommandViewCaseMetric:
        """
        Retrieves or initializes a CommandViewCaseMetric row with SELECT ... FOR UPDATE
        to ensure atomic, concurrency-safe counter updates.
        """
        stmt = (
            select(CommandViewCaseMetric)
            .where(CommandViewCaseMetric.country_id == country_id)
            .with_for_update()
        )
        metric = self.session.execute(stmt).scalar_one_or_none()
        if not metric:
            metric = CommandViewCaseMetric(
                country_id=country_id,
                open_count=0,
                in_progress_count=0,
                closed_count=0,
            )
            self.session.add(metric)
            self.session.flush()
        return metric

    def list_scoped(
        self,
        *,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
    ) -> list[CommandViewCaseMetric]:
        """
        Retrieves case metrics scoped strictly to allowed country IDs at the SQL query level.
        """
        if not allowed_country_ids:
            return []

        stmt = (
            select(CommandViewCaseMetric)
            .where(CommandViewCaseMetric.country_id.in_(allowed_country_ids))
            .order_by(CommandViewCaseMetric.updated_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())
