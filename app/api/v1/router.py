from fastapi import APIRouter

from app.api.v1.audit_logs import router as audit_logs_router
from app.api.v1.cases import router as cases_router
from app.api.v1.command_view import router as command_view_router
from app.api.v1.partners import router as partners_router

api_v1_router = APIRouter(prefix="/v1")

# Domain and Platform routers
api_v1_router.include_router(cases_router)
api_v1_router.include_router(audit_logs_router)
api_v1_router.include_router(command_view_router)
api_v1_router.include_router(partners_router)
