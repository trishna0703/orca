import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.authorization.dependencies import (
    get_care_companion_app,
    get_user_country_scope,
    require_permission,
)
from app.db.session import get_db
from app.models.application import Application
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get(
    "",
    response_model=list[AuditLogResponse],
    summary="List audit logs",
    description="List immutable Care Companion audit records within the caller's application and country scope.",
    dependencies=[Depends(require_permission("audit:read"))],
)
def list_audit_logs(
    entity_type: str | None = Query(
        default=None, description="Filter by entity type (e.g. case)"
    ),
    entity_id: uuid.UUID | None = Query(
        default=None, description="Filter by specific entity ID"
    ),
    actor_id: uuid.UUID | None = Query(default=None, description="Filter by actor ID"),
    country_id: uuid.UUID | None = Query(
        default=None, description="Filter by country ID"
    ),
    action: str | None = Query(
        default=None, description="Filter by action name (e.g. case.created)"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    db: Session = Depends(get_db),
) -> list[AuditLogResponse]:
    """
    Lists audit logs scoped to the active application and the user's geographic country permissions.
    Requires 'audit:read' permission.
    Query-level filtering prevents access to audit trails of out-of-scope countries or foreign apps.
    """
    repo = AuditLogRepository(db)
    logs = repo.list_scoped(
        application_id=current_app.id,
        allowed_country_ids=allowed_countries,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        country_id=country_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return [AuditLogResponse.model_validate(log) for log in logs]
