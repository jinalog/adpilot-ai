from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.infrastructure.campaign_repository import CampaignRepository
from app.services.campaign_service import CampaignService

DatabaseSession = Annotated[Session, Depends(get_db_session)]


def get_campaign_service(session: DatabaseSession) -> CampaignService:
    return CampaignService(CampaignRepository(session))


CampaignServiceDependency = Annotated[CampaignService, Depends(get_campaign_service)]
