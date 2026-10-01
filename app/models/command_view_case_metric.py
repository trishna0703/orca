from datetime import datetime
import uuid
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommandViewCaseMetric(Base):
    """
    Read model table maintained by Command View for case aggregations per country.
    Mutated solely via integration events (e.g. case.created.v1, case.closed.v1).
    Inherits from Base directly because it is an application read projection, not an audited domain BaseEntity.
    """

    __tablename__ = "command_view_case_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("countries.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    open_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    in_progress_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    closed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("open_count >= 0", name="ck_metrics_open_count_non_negative"),
        CheckConstraint(
            "in_progress_count >= 0", name="ck_metrics_in_progress_count_non_negative"
        ),
        CheckConstraint(
            "closed_count >= 0", name="ck_metrics_closed_count_non_negative"
        ),
    )
