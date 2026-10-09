from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.api.routes.service_requests import router as service_requests_router
from app.api.routes.analytics import router as analytics_router

app = FastAPI(
    title="Montréal Municipal Service Intelligence",
    description=(
        "Analytics and forecasting for Montréal municipal "
        "service requests."
    ),
    version="0.1.0",
)
app.include_router(service_requests_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    """Confirm that the API process is running."""
    return HealthResponse(
        status="ok",
        service="montreal-service-intelligence",
        version=app.version,
    )