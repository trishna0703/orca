import enum
from sqlalchemy import Enum as SQLEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_entity import BaseEntity


class PartnerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Partner(BaseEntity):
    __tablename__ = "partners"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    partner_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    contact_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[PartnerStatus] = mapped_column(
        SQLEnum(
            PartnerStatus,
            name="partner_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=PartnerStatus.ACTIVE,
    )
