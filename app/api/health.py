"""Health and status endpoints."""
from fastapi import APIRouter

from app.ai.providers import provider_status
from app.config.settings import settings
from app.database.mongo import mongo
from app.utils.security import password_backend

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok" if mongo.connected else "degraded",
        "app": settings.APP_NAME,
        "database": "connected" if mongo.connected else "unavailable",
        "demo_mode": settings.DEMO_MODE,
        "ai_providers": provider_status(),
        "llm_chain": settings.llm_chain,
        "password_hashing": password_backend(),
        "email_configured": settings.email_enabled,
        "match_radius_meters": settings.MATCH_RADIUS_METERS,
        "max_match_radius_meters": settings.MAX_MATCH_RADIUS_METERS,
    }
