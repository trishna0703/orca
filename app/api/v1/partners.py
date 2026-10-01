import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.authorization.dependencies import (
    get_current_user,
    get_partner_engage_app,
    get_partner_engage_country_scope,
    require_permission,
)
from app.core.request_id import get_request_id
from app.db.session import get_db
from app.models.application import Application
from app.models.user import User
from app.schemas.partner import PartnerCreate, PartnerResponse, PartnerUpdate
from app.services.partner_service import PartnerService

router = APIRouter(prefix="/partners", tags=["Partner Engage"])


@router.post(
    "",
    response_model=PartnerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a partner",
    description="Create a country-scoped Partner Engage partner and atomically record its audit log.",
    dependencies=[
        Depends(
            require_permission("partner:create", app_resolver=get_partner_engage_app)
        )
    ],
)
def create_partner(
    payload: PartnerCreate,
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_partner_engage_app),
    allowed_countries: set[uuid.UUID] = Depends(get_partner_engage_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> PartnerResponse:
    service = PartnerService(db)
    partner = service.create_partner(
        data=payload,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
    return PartnerResponse.model_validate(partner)


@router.get(
    "",
    response_model=list[PartnerResponse],
    summary="List partners",
    description="List non-deleted Partner Engage partners within the caller's allowed countries.",
    dependencies=[
        Depends(require_permission("partner:read", app_resolver=get_partner_engage_app))
    ],
)
def list_partners(
    current_app: Application = Depends(get_partner_engage_app),
    allowed_countries: set[uuid.UUID] = Depends(get_partner_engage_country_scope),
    db: Session = Depends(get_db),
) -> list[PartnerResponse]:
    service = PartnerService(db)
    partners = service.list_partners(
        application_id=current_app.id,
        allowed_country_ids=allowed_countries,
    )
    return [PartnerResponse.model_validate(p) for p in partners]


@router.get(
    "/{partner_id}",
    response_model=PartnerResponse,
    summary="Get a partner",
    description="Get one non-deleted partner within the caller's application and country scope.",
    dependencies=[
        Depends(require_permission("partner:read", app_resolver=get_partner_engage_app))
    ],
)
def get_partner(
    partner_id: uuid.UUID,
    current_app: Application = Depends(get_partner_engage_app),
    allowed_countries: set[uuid.UUID] = Depends(get_partner_engage_country_scope),
    db: Session = Depends(get_db),
) -> PartnerResponse:
    service = PartnerService(db)
    partner = service.get_partner(
        partner_id=partner_id,
        application_id=current_app.id,
        allowed_country_ids=allowed_countries,
    )
    return PartnerResponse.model_validate(partner)


@router.patch(
    "/{partner_id}",
    response_model=PartnerResponse,
    summary="Update a partner",
    description="Update mutable partner fields with optional optimistic concurrency checking.",
    dependencies=[
        Depends(
            require_permission("partner:update", app_resolver=get_partner_engage_app)
        )
    ],
)
def update_partner(
    partner_id: uuid.UUID,
    payload: PartnerUpdate,
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_partner_engage_app),
    allowed_countries: set[uuid.UUID] = Depends(get_partner_engage_country_scope),
    request_id: str = Depends(get_request_id),
    db: Session = Depends(get_db),
) -> PartnerResponse:
    service = PartnerService(db)
    partner = service.update_partner(
        partner_id=partner_id,
        data=payload,
        application_id=current_app.id,
        user_id=current_user.id,
        allowed_country_ids=allowed_countries,
        request_id=request_id,
    )
    return PartnerResponse.model_validate(partner)
