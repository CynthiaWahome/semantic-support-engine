"""Central HTTP router registration."""

from fastapi import APIRouter

from app.views.health import router as health_router

router = APIRouter()
router.include_router(health_router)
