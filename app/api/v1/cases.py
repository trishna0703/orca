import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.authorization.dependencies import (
    get_care_companion_app,
    get_current_user,
    get_user_country_scope,
    require_permission,
)
from app.core.request_id import get_request_id
from app.db.session import get_db
from app.models.application import Application
from app.models.user import User
from app.schemas.case import CaseAssignRequest, CaseCreate, CaseResponse, CaseUpdate
from app.services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["Care Companion"])


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a case",
    description="Create a country-scoped Care Companion case and atomically record its audit log and outbox event.",
    dependencies=[Depends(require_permission("case:create"))],
)
def create_case(
    payload: CaseCreate,
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> CaseResponse:
    """
    Creates a new Case entity within Care Companion.
    Enforces 'case:create' permission and country scope authorization.
    Platform fields (owner_app_id, created_by) are strictly server-managed.
    Atomically generates an immutable AuditLog entry and OutboxEvent (case.created.v1) correlated with request_id.
    """
    service = CaseService(db)
    case = service.create_case(
        data=payload,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
    return CaseResponse.model_validate(case)


@router.get(
    "",
    response_model=list[CaseResponse],
    summary="List cases",
    description="List non-deleted Care Companion cases within the caller's allowed countries.",
    dependencies=[Depends(require_permission("case:read"))],
)
def list_cases(
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    db: Session = Depends(get_db),
) -> list[CaseResponse]:
    """
    Lists Cases scoped to Care Companion and user's allowed country scopes.
    Excludes soft-deleted records. Scoping is enforced entirely in the SQL query.
    """
    service = CaseService(db)
    cases = service.list_cases(
        application_id=current_app.id,
        allowed_country_ids=allowed_countries,
    )
    return [CaseResponse.model_validate(c) for c in cases]


@router.get(
    "/{case_id}",
    response_model=CaseResponse,
    summary="Get a case",
    description="Get one non-deleted case within the caller's application and country scope.",
    dependencies=[Depends(require_permission("case:read"))],
)
def get_case(
    case_id: uuid.UUID,
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    db: Session = Depends(get_db),
) -> CaseResponse:
    """
    Retrieves a single Case by ID.
    Enforces application ownership, country scope, and soft-delete exclusion in the SQL query.
    Returns 404 if inaccessible or non-existent to avoid information leakage.
    """
    service = CaseService(db)
    case = service.get_case(
        case_id=case_id,
        application_id=current_app.id,
        allowed_country_ids=allowed_countries,
    )
    return CaseResponse.model_validate(case)


@router.patch(
    "/{case_id}",
    response_model=CaseResponse,
    summary="Update a case",
    description="Update mutable case fields with optional optimistic concurrency checking.",
    dependencies=[Depends(require_permission("case:update"))],
)
def update_case(
    case_id: uuid.UUID,
    payload: CaseUpdate,
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> CaseResponse:
    """
    Updates mutable fields of a Case (title, description).
    Enforces 'case:update' permission and country scope authorization.
    Atomically generates AuditLog (case.updated) and OutboxEvent (case.updated.v1).
    """
    service = CaseService(db)
    case = service.update_case(
        case_id=case_id,
        data=payload,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
    return CaseResponse.model_validate(case)


@router.post(
    "/{case_id}/assign",
    response_model=CaseResponse,
    summary="Assign a case",
    description="Assign a case to an eligible user in the same application and country scope.",
    dependencies=[Depends(require_permission("case:assign"))],
)
def assign_case(
    case_id: uuid.UUID,
    payload: CaseAssignRequest,
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> CaseResponse:
    """
    Assigns a Case to a user.
    Enforces 'case:assign' permission and country scope authorization.
    Validates assignee eligibility (assignee must have an app role and country scope for this case).
    Atomically generates AuditLog (case.assigned) and OutboxEvent (case.assigned.v1).
    """
    service = CaseService(db)
    case = service.assign_case(
        case_id=case_id,
        data=payload,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
    return CaseResponse.model_validate(case)


@router.post(
    "/{case_id}/close",
    response_model=CaseResponse,
    summary="Close a case",
    description="Close a case and atomically emit the audit and outbox records used by Command View.",
    dependencies=[Depends(require_permission("case:close"))],
)
def close_case(
    case_id: uuid.UUID,
    expected_version: int | None = Query(
        default=None, description="Expected version for optimistic concurrency"
    ),
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> CaseResponse:
    """
    Closes an open or in_progress Case.
    Enforces 'case:close' permission and country scope authorization.
    Rejects closing already-closed cases with 409 Conflict.
    Atomically generates AuditLog (case.closed) and OutboxEvent (case.closed.v1).
    """
    service = CaseService(db)
    case = service.close_case(
        case_id=case_id,
        expected_version=expected_version,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
    return CaseResponse.model_validate(case)


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a case",
    description="Soft-delete a case within the caller's application and country scope.",
    dependencies=[Depends(require_permission("case:delete"))],
)
def delete_case(
    case_id: uuid.UUID,
    expected_version: int | None = Query(
        default=None, description="Expected version for optimistic concurrency"
    ),
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_care_companion_app),
    allowed_countries: set[uuid.UUID] = Depends(get_user_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> None:
    """
    Soft deletes a Case.
    Enforces 'case:delete' permission and country scope authorization.
    Atomically generates AuditLog (case.deleted) and OutboxEvent (case.deleted.v1).
    """
    service = CaseService(db)
    service.soft_delete_case(
        case_id=case_id,
        expected_version=expected_version,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
