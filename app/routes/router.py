"""Central HTTP router registration."""

from fastapi import APIRouter

from app.routes.health import router as health_router
from app.routes.knowledge_base import router as knowledge_base_router

router = APIRouter()
router.include_router(health_router)
router.include_router(knowledge_base_router)
