from fastapi import APIRouter

from app.api.routes.ai_campaigns import router as ai_campaigns_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(campaigns_router, tags=["campaigns"])
api_router.include_router(ai_campaigns_router, tags=["ai-campaign-setup"])
api_router.include_router(analytics_router, tags=["analytics"])
