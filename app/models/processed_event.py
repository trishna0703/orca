from datetime import datetime
import uuid
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessedEvent(Base):
    """
    Consumer idempotency ledger.
    Tracks which integration events have been processed by which consumer.
    Supports multiple independent consumers per event via composite primary key (event_id, consumer).
    """

    __tablename__ = "processed_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )

    consumer: Mapped[str] = mapped_column(
        String(150),
        primary_key=True,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
