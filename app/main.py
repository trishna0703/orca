from fastapi import FastAPI

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.request_id import RequestIdMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Shared backend foundation for ORCA domain applications.",
    openapi_tags=[
        {
            "name": "Care Companion",
            "description": "Country-scoped case lifecycle operations.",
        },
        {
            "name": "Partner Engage",
            "description": "Country-scoped partner management operations.",
        },
        {
            "name": "Command View",
            "description": "Read projections built from cross-application events.",
        },
        {
            "name": "Audit",
            "description": "Application- and country-scoped audit history.",
        },
        {
            "name": "Platform",
            "description": "Platform operational endpoints.",
        },
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add request correlation ID middleware
app.add_middleware(RequestIdMiddleware)


@app.get(
    "/health",
    tags=["Platform"],
    response_model=dict[str, str],
    summary="Check service health",
    description="Return a lightweight liveness response for the ORCA API.",
)
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Include API v1 router
app.include_router(api_v1_router)
