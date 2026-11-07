import os
import threading
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.campaign_setup import CampaignSetupWorkflow
from app.agents.providers import MockCampaignProvider
from app.core.config import get_settings
from app.db.models.ai_campaign import AgentRun, CampaignDraft
from app.db.models.campaign import Campaign
from app.infrastructure.ai_campaign_repository import AICampaignRepository
from app.infrastructure.campaign_repository import CampaignRepository
from app.services.ai_campaign_service import AICampaignService
from app.services.campaign_service import CampaignService

pytestmark = pytest.mark.integration


def complete_draft() -> dict[str, object]:
    return {
        "name": "Concurrent save",
        "objective": "Install",
        "total_budget_krw": 1_000_000,
        "daily_budget_krw": 100_000,
        "start_date": "2026-12-01",
        "end_date": "2026-12-10",
        "channels": ["mobile"],
        "targeting": {},
    }


def clean_database(engine: Engine) -> None:
    with Session(engine) as session:
        session.execute(delete(AgentRun))
        session.execute(delete(CampaignDraft))
        session.execute(delete(Campaign))
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


def build_service(session: Session, repository: AICampaignRepository) -> AICampaignService:
    return AICampaignService(
        repository,
        CampaignService(CampaignRepository(session)),
        CampaignSetupWorkflow(MockCampaignProvider(), timeout_seconds=1, max_retries=0),
    )


class CoordinatedRepository(AICampaignRepository):
    def __init__(
        self,
        session: Session,
        *,
        lock_acquired: threading.Event | None = None,
        release_lock: threading.Event | None = None,
        lock_attempted: threading.Event | None = None,
    ) -> None:
        super().__init__(session)
        self.lock_acquired = lock_acquired
        self.release_lock = release_lock
        self.lock_attempted = lock_attempted

    def get_draft(self, draft_id: uuid.UUID, *, for_update: bool = False) -> CampaignDraft | None:
        if for_update and self.lock_attempted is not None:
            self.lock_attempted.set()
        draft = super().get_draft(draft_id, for_update=for_update)
        if for_update and self.lock_acquired is not None:
            self.lock_acquired.set()
            assert self.release_lock is not None
            if not self.release_lock.wait(timeout=10):
                raise TimeoutError("test did not release the PostgreSQL row lock")
        return draft


class FailingCommitRepository(AICampaignRepository):
    def commit(self) -> None:
        raise RuntimeError("injected transaction failure")


def test_concurrent_save_returns_one_campaign_and_consistent_draft_link(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(bind=postgres_engine, class_=Session, expire_on_commit=False)
    draft_id = uuid.uuid4()
    with factory() as session:
        session.add(
            CampaignDraft(
                id=draft_id,
                draft=complete_draft(),
                missing_fields=[],
                validation_errors=[],
                clarification_questions=[],
                status="READY",
                provider_mode="mock",
            )
        )
        session.commit()

    lock_acquired = threading.Event()
    release_lock = threading.Event()
    second_lock_attempted = threading.Event()

    def save_first() -> object:
        with factory() as session:
            repository = CoordinatedRepository(
                session,
                lock_acquired=lock_acquired,
                release_lock=release_lock,
            )
            return build_service(session, repository).save(draft_id)

    def save_second() -> object:
        with factory() as session:
            repository = CoordinatedRepository(
                session,
                lock_attempted=second_lock_attempted,
            )
            return build_service(session, repository).save(draft_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(save_first)
        assert lock_acquired.wait(timeout=10)
        second_future = executor.submit(save_second)
        assert second_lock_attempted.wait(timeout=10)
        release_lock.set()
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)

    assert first.campaign_id == second.campaign_id
    assert {first.already_saved, second.already_saved} == {False, True}
    with factory() as session:
        assert session.scalar(select(func.count(Campaign.id))) == 1
        draft = session.get(CampaignDraft, draft_id)
        assert draft is not None
        assert draft.saved_campaign_id == first.campaign_id
        assert draft.status == "SAVED"


def test_save_transaction_failure_leaves_no_orphan_campaign_or_draft_link(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(bind=postgres_engine, class_=Session, expire_on_commit=False)
    draft_id = uuid.uuid4()
    with factory() as session:
        session.add(
            CampaignDraft(
                id=draft_id,
                draft=complete_draft(),
                missing_fields=[],
                validation_errors=[],
                clarification_questions=[],
                status="READY",
                provider_mode="mock",
            )
        )
        session.commit()

    with factory() as session:
        service = build_service(session, FailingCommitRepository(session))
        with pytest.raises(RuntimeError, match="injected transaction failure"):
            service.save(draft_id)

    with factory() as session:
        assert session.scalar(select(func.count(Campaign.id))) == 0
        draft = session.get(CampaignDraft, draft_id)
        assert draft is not None
        assert draft.saved_campaign_id is None
        assert draft.status == "READY"
