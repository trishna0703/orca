from collections.abc import Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authorization.service import apply_entity_scope
from app.models.partner import Partner
from app.schemas.partner import PartnerCreate


class PartnerRepository:
    """
    Data access layer for Partner entities.
    Applies entity-level and geographic-level query constraints in SQL via apply_entity_scope.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_scoped(
        self,
        *,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
    ) -> list[Partner]:
        stmt = select(Partner)
        stmt = apply_entity_scope(
            stmt,
            entity_cls=Partner,
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
            include_deleted=False,
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_scoped(
        self,
        *,
        partner_id: uuid.UUID,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
    ) -> Partner | None:
        stmt = select(Partner).where(Partner.id == partner_id)
        stmt = apply_entity_scope(
            stmt,
            entity_cls=Partner,
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
            include_deleted=False,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        data: PartnerCreate,
        application_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
    ) -> Partner:
        partner = Partner(
            name=data.name,
            partner_type=data.partner_type,
            contact_email=data.contact_email,
            status=data.status,
            country_id=data.country_id,
            owner_app_id=application_id,
            created_by=created_by_user_id,
        )
        self.session.add(partner)
        self.session.flush()
        return partner
