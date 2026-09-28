"""Application liveness HTTP route."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health import get_liveness_status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report application liveness without checking external services."""
    return HealthResponse(status=get_liveness_status())
