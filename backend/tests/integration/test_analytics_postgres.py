import os
import uuid
from collections.abc import Generator
from datetime import date
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.db.models.ai_campaign import AgentRun, CampaignDraft
from app.db.models.analytics import AnomalyTruthLabel, DailyAdMetric, SyntheticDatasetRun
from app.db.models.campaign import Campaign
from app.domain.analytics import aggregate_metrics
from app.domain.synthetic_analytics import SyntheticDatasetConfig, build_synthetic_dataset
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.services.analytics_service import AnalyticsService, SyntheticDatasetService

pytestmark = pytest.mark.integration


def clean_database(engine: Engine) -> None:
    with Session(engine) as session:
        session.execute(delete(AgentRun))
        session.execute(delete(CampaignDraft))
        session.execute(delete(AnomalyTruthLabel))
        session.execute(delete(DailyAdMetric))
        session.execute(delete(Campaign))
        session.execute(delete(SyntheticDatasetRun))
        session.commit()


@pytest.fixture
def postgres_engine(monkeypatch: pytest.MonkeyPatch) -> Generator[Engine, None, None]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not urlparse(database_url).path.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must target a database whose name ends with '_test'")
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(database_url)
    clean_database(engine)
    try:
        yield engine
    finally:
        clean_database(engine)
        engine.dispose()
        get_settings.cache_clear()


def non_owned_campaign() -> Campaign:
    return Campaign(
        id=uuid.uuid4(),
        name="Existing developer campaign",
        objective="Preserve me",
        total_budget_krw=1_000_000,
        daily_budget_krw=100_000,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 10, 31),
        channels=["search"],
        targeting={},
        status="DRAFT",
    )


def test_postgres_seed_is_idempotent_by_default_and_preserves_non_owned_data(
    postgres_engine: Engine,
) -> None:
    plan = build_synthetic_dataset(SyntheticDatasetConfig())
    existing = non_owned_campaign()
    with Session(postgres_engine, expire_on_commit=False) as session:
        session.add(existing)
        session.commit()
        service = SyntheticDatasetService(AnalyticsRepository(session))
        saved = service.create(plan)

        assert saved.id == plan.id
        assert session.scalar(select(func.count(DailyAdMetric.id))) == len(plan.metrics)
        assert session.scalar(select(func.count(AnomalyTruthLabel.id))) == 4
        assert session.get(Campaign, existing.id) is not None
        with pytest.raises(ConflictError, match="already exists"):
            service.create(plan)
        assert session.scalar(select(func.count(DailyAdMetric.id))) == len(plan.metrics)

        replaced = service.create(plan, replace_dataset_id=plan.id)
        assert replaced.id == plan.id
        assert session.get(Campaign, existing.id) is not None
        assert session.scalar(select(func.count(Campaign.id))) == len(plan.campaigns) + 1


def test_postgres_constraints_and_repository_aggregation(postgres_engine: Engine) -> None:
    plan = build_synthetic_dataset(SyntheticDatasetConfig())
    with Session(postgres_engine, expire_on_commit=False) as session:
        repository = AnalyticsRepository(session)
        SyntheticDatasetService(repository).create(plan)
        first = plan.metrics[0]
        session.add(
            DailyAdMetric(
                id=uuid.uuid4(),
                dataset_run_id=first.dataset_run_id,
                campaign_id=first.campaign_id,
                date=first.date,
                impressions=first.impressions,
                clicks=first.clicks,
                conversions=first.conversions,
                spend_krw=first.spend_krw,
                revenue_krw=first.revenue_krw,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            DailyAdMetric(
                id=uuid.uuid4(),
                dataset_run_id=first.dataset_run_id,
                campaign_id=first.campaign_id,
                date=first.date.replace(year=2025),
                impressions=10,
                clicks=11,
                conversions=0,
                spend_krw=0,
                revenue_krw=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        summary = AnalyticsService(repository).summary(
            plan.id,
            campaign_id=None,
            start_date=None,
            end_date=None,
        )
        expected = aggregate_metrics(
            repository.list_metrics(
                dataset_run_id=plan.id,
                start_date=plan.config.start_date,
                end_date=plan.end_date,
            )
        )
        assert summary.totals.impressions == expected.impressions
        assert summary.totals.spend_krw == expected.spend_krw
