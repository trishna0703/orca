import uuid
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.audit.serializers import serialize_entity
from app.audit.service import record_audit
from app.models.partner import Partner
from app.repositories.partner_repository import PartnerRepository
from app.schemas.partner import PartnerCreate, PartnerUpdate


class PartnerService:
    """
    Business service layer coordinating Partner domain operations, authorization validation,
    and atomic transaction management including generic audit logging.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PartnerRepository(session)

    def list_partners(
        self,
        *,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
    ) -> list[Partner]:
        return self.repository.list_scoped(
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
        )

    def get_partner(
        self,
        *,
        partner_id: uuid.UUID,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
    ) -> Partner:
        partner = self.repository.get_scoped(
            partner_id=partner_id,
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
        )
        if not partner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Partner not found",
            )
        return partner

    def create_partner(
        self,
        *,
        data: PartnerCreate,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> Partner:
        if data.country_id not in allowed_country_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is not authorized for country_id '{data.country_id}'",
            )

        try:
            partner = self.repository.create(
                data=data,
                application_id=application_id,
                created_by_user_id=user_id,
            )

            after_payload = serialize_entity(partner)

            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="partner.created",
                entity_type="partner",
                entity_id=partner.id,
                country_id=partner.country_id,
                before_data=None,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            self.session.commit()
            self.session.refresh(partner)
            return partner
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise

    def update_partner(
        self,
        *,
        partner_id: uuid.UUID,
        data: PartnerUpdate,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> Partner:
        try:
            partner = self.repository.get_scoped(
                partner_id=partner_id,
                application_id=application_id,
                allowed_country_ids=allowed_country_ids,
            )
            if not partner:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Partner not found",
                )

            if (
                data.expected_version is not None
                and partner.version != data.expected_version
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Version conflict: current version is {partner.version}, expected {data.expected_version}",
                )

            before_payload = serialize_entity(partner)

            if data.name is not None:
                partner.name = data.name
            if data.partner_type is not None:
                partner.partner_type = data.partner_type
            if data.contact_email is not None:
                partner.contact_email = data.contact_email
            if data.status is not None:
                partner.status = data.status

            partner.updated_by = user_id
            partner.version += 1
            self.session.flush()

            after_payload = serialize_entity(partner)

            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="partner.updated",
                entity_type="partner",
                entity_id=partner.id,
                country_id=partner.country_id,
                before_data=before_payload,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            self.session.commit()
            self.session.refresh(partner)
            return partner
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
