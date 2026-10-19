from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Process health check",
    description="Reports that the API process is running. It does not check database or storage connectivity.",
)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(service=settings.app_name, version=settings.app_version)
