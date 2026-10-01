import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.authorization.dependencies import (
    get_command_view_app,
    get_command_view_country_scope,
    require_permission,
)
from app.command_view.schemas import CaseMetricResponse
from app.command_view.service import CommandViewService
from app.db.session import get_db

router = APIRouter(prefix="/command-view", tags=["Command View"])


@router.get(
    "/case-metrics",
    response_model=list[CaseMetricResponse],
    summary="List case metrics",
    description="Return country-scoped case counts projected from Care Companion outbox events.",
    dependencies=[
        Depends(
            require_permission("case-metrics:read", app_resolver=get_command_view_app)
        )
    ],
)
def get_case_metrics(
    allowed_countries: set[uuid.UUID] = Depends(get_command_view_country_scope),
    db: Session = Depends(get_db),
) -> list[CaseMetricResponse]:
    """
    Retrieves aggregated Case metrics per country for Command View.
    Enforces 'case-metrics:read' permission in Command View and country scoping in SQL.
    Does NOT query the domain `cases` table.
    """
    service = CommandViewService(db)
    metrics = service.get_case_metrics(allowed_country_ids=allowed_countries)
    return [CaseMetricResponse.model_validate(m) for m in metrics]
