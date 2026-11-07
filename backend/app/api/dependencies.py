from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.campaign_setup import CampaignSetupWorkflow
from app.agents.providers import build_provider
from app.core.config import get_settings
from app.db.session import get_db_session
from app.infrastructure.ai_campaign_repository import AICampaignRepository
from app.infrastructure.campaign_repository import CampaignRepository
from app.services.ai_campaign_service import AICampaignService
from app.services.campaign_service import CampaignService

DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_campaign_service(session: DatabaseSession) -> CampaignService:
    return CampaignService(CampaignRepository(session))


CampaignServiceDependency = Annotated[CampaignService, Depends(get_campaign_service)]


def get_ai_campaign_service(session: DatabaseSession) -> AICampaignService:
    settings = get_settings()
    campaign_service = CampaignService(CampaignRepository(session))
    workflow = CampaignSetupWorkflow(
        build_provider(settings),
        timeout_seconds=settings.ai_provider_timeout_seconds,
        max_retries=settings.ai_provider_max_retries,
    )
    return AICampaignService(AICampaignRepository(session), campaign_service, workflow)


AICampaignServiceDependency = Annotated[AICampaignService, Depends(get_ai_campaign_service)]
