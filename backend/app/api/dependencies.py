from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.analyst_provider import build_analyst_provider
from app.agents.campaign_setup import CampaignSetupWorkflow
from app.agents.performance_analyst import PerformanceAnalystWorkflow
from app.agents.providers import build_provider
from app.core.config import get_settings
from app.db.session import get_db_session
from app.domain.analyst_sql import DeterministicSQLCompiler, SQLASTValidator
from app.infrastructure.ai_campaign_repository import AICampaignRepository
from app.infrastructure.analyst_executor import ReadOnlySQLExecutor
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.infrastructure.campaign_repository import CampaignRepository
from app.services.ai_campaign_service import AICampaignService
from app.services.analyst_service import PerformanceAnalystService
from app.services.analytics_service import AnalyticsService
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


def get_analytics_service(session: DatabaseSession) -> AnalyticsService:
    return AnalyticsService(AnalyticsRepository(session))


AnalyticsServiceDependency = Annotated[AnalyticsService, Depends(get_analytics_service)]


def get_analyst_service(session: DatabaseSession) -> PerformanceAnalystService:
    settings = get_settings()
    engine = session.get_bind()
    workflow = PerformanceAnalystWorkflow(
        build_analyst_provider(settings.analyst_provider),
        DeterministicSQLCompiler(),
        SQLASTValidator(),
        ReadOnlySQLExecutor(
            engine,
            statement_timeout_ms=settings.analyst_statement_timeout_ms,
            absolute_max_rows=settings.analyst_absolute_max_rows,
        ),
        timeout_seconds=settings.analyst_provider_timeout_seconds,
        max_retries=settings.analyst_provider_max_retries,
    )
    return PerformanceAnalystService(AnalyticsRepository(session), workflow)


AnalystServiceDependency = Annotated[PerformanceAnalystService, Depends(get_analyst_service)]
