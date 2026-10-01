import uuid
from typing import Any
from sqlalchemy.orm import Session

from app.audit.serializers import to_json_serializable
from app.models.audit_log import AuditLog


class AuditService:
    """
    Generic platform-level audit service.
    Persists immutable audit records for any domain entity across any ORCA application.

    Crucial Architectural Contract:
    - Does NOT call `session.commit()`. The calling service layer manages the business transaction boundary.
    - Sanitizes payload dictionaries into JSON-compliant structures.
    """

    def record(
        self,
        *,
        session: Session,
        actor_id: uuid.UUID | None,
        application_id: uuid.UUID,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        country_id: uuid.UUID | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | uuid.UUID | None = None,
    ) -> AuditLog:
        """
        Appends an AuditLog entry to the provided session without committing.
        """
        audit_entry = AuditLog(
            actor_id=actor_id,
            application_id=application_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            country_id=country_id,
            before_data=(
                to_json_serializable(before_data) if before_data is not None else None
            ),
            after_data=(
                to_json_serializable(after_data) if after_data is not None else None
            ),
            metadata_=to_json_serializable(metadata) if metadata is not None else None,
            request_id=str(request_id) if request_id is not None else None,
        )
        session.add(audit_entry)
        return audit_entry


# Module-level convenience instance and function
audit_service = AuditService()


def record_audit(
    *,
    session: Session,
    actor_id: uuid.UUID | None,
    application_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    country_id: uuid.UUID | None = None,
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | uuid.UUID | None = None,
) -> AuditLog:
    """
    Generic platform audit recording function.
    """
    return audit_service.record(
        session=session,
        actor_id=actor_id,
        application_id=application_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        country_id=country_id,
        before_data=before_data,
        after_data=after_data,
        metadata=metadata,
        request_id=request_id,
    )
