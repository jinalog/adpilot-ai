import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.agents.campaign_setup import CampaignSetupWorkflow
from app.agents.providers import ProviderError, ProviderResult
from app.core.exceptions import ConflictError
from app.db.models.ai_campaign import CampaignDraft
from app.infrastructure.ai_campaign_repository import AICampaignRepository
from app.infrastructure.campaign_repository import CampaignRepository
from app.schemas.ai_campaign import RefineDraftRequest
from app.services.ai_campaign_service import AICampaignService
from app.services.campaign_service import CampaignService


class FailingProvider:
    mode = "test"
    model = "test-model"

    def extract(self, text: str, *, timeout_seconds: float) -> ProviderResult:
        del text, timeout_seconds
        raise ProviderError("safe test failure")


def complete_draft() -> dict[str, object]:
    return {
        "name": "Preserved",
        "objective": "Install",
        "total_budget_krw": 1_000_000,
        "daily_budget_krw": 100_000,
        "start_date": "2026-12-01",
        "end_date": "2026-12-10",
        "channels": ["mobile"],
        "targeting": {},
    }


def test_provider_failure_preserves_ready_draft_in_database_and_keeps_save_blocked(
    db_session_factory: sessionmaker[Session],
) -> None:
    draft_id = uuid.uuid4()
    original = complete_draft()
    with db_session_factory() as session:
        session.add(
            CampaignDraft(
                id=draft_id,
                draft=original,
                missing_fields=[],
                validation_errors=[],
                clarification_questions=[],
                status="READY",
                provider_mode="mock",
            )
        )
        session.commit()

        service = AICampaignService(
            AICampaignRepository(session),
            CampaignService(CampaignRepository(session)),
            CampaignSetupWorkflow(FailingProvider(), timeout_seconds=1, max_retries=0),
        )
        response = service.refine(
            draft_id,
            RefineDraftRequest(additional_input="provider should fail"),
        )

        assert response.status.value == "PROVIDER_ERROR"
        assert response.draft.model_dump(mode="json", exclude_none=True) == original
        assert response.missing_fields == []
        persisted = session.get(CampaignDraft, draft_id)
        assert persisted is not None
        assert persisted.draft == original
        assert persisted.status == "PROVIDER_ERROR"

        with pytest.raises(ConflictError, match="only a READY"):
            service.save(draft_id)
