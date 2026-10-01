import uuid
from typing import Sequence
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    """
    Data access layer for AuditLog entities.
    Applies application, country scope, and query filters entirely at the SQL level.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_scoped(
        self,
        *,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        country_id: uuid.UUID | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.application_id == application_id)

        # Country scope enforcement: allow records scoped to user's allowed countries or global (null country_id)
        if not allowed_country_ids:
            # User has no country scope for this app; restrict to un-scoped audit records if any
            stmt = stmt.where(AuditLog.country_id.is_(None))
        else:
            stmt = stmt.where(
                or_(
                    AuditLog.country_id.in_(allowed_country_ids),
                    AuditLog.country_id.is_(None),
                )
            )

        # Optional filters
        if entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id)
        if country_id is not None:
            # Explicit country filter must also satisfy allowed_country_ids
            stmt = stmt.where(AuditLog.country_id == country_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)

        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())
