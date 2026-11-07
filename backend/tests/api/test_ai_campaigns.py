from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.ai_campaign import AgentRun
from app.db.models.campaign import Campaign


def complete_prompt() -> str:
    return (
        "캠페인명: 겨울 설치; 목표: 신규 앱 설치; 총예산: 300만원; 일예산: 10만원; "
        "시작일: 2026-12-01; 종료일: 2026-12-31; 채널: mobile, search; "
        '타게팅: {"country":"KR"}'
    )


def generate(client: TestClient, prompt: str) -> dict[str, Any]:
    response = client.post("/api/v1/ai/campaign-drafts/generate", json={"prompt": prompt})
    assert response.status_code == 201
    return response.json()


def test_generate_is_ready_and_does_not_create_campaign(client: TestClient) -> None:
    result = generate(client, complete_prompt())

    campaigns = client.get("/api/v1/campaigns").json()
    fetched = client.get(f"/api/v1/ai/campaign-drafts/{result['draft_id']}")

    assert result["status"] == "READY"
    assert result["provider_mode"] == "mock"
    assert result["saved"] is False
    assert campaigns["total"] == 0
    assert fetched.status_code == 200


def test_refine_preserves_existing_values_and_creates_run_history(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    draft = generate(client, "캠페인명: 보완 캠페인; 목표: 설치")
    response = client.post(
        f"/api/v1/ai/campaign-drafts/{draft['draft_id']}/refine",
        json={
            "draft_updates": {
                "total_budget_krw": 1_000_000,
                "daily_budget_krw": 100_000,
                "start_date": "2026-12-01",
                "end_date": "2026-12-10",
                "channels": ["mobile"],
                "targeting": {},
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "READY"
    assert response.json()["draft"]["name"] == "보완 캠페인"
    assert response.json()["provider_mode"] == "not_used"
    assert response.json()["retry_count"] == 0
    with db_session_factory() as session:
        assert session.scalar(select(func.count(AgentRun.id))) == 2
        skipped_run = session.scalar(select(AgentRun).where(AgentRun.provider == "not_used"))
        assert skipped_run is not None
        assert skipped_run.model == "structured-updates-only"
        assert skipped_run.input_tokens is None
        assert skipped_run.output_tokens is None


def test_non_ready_save_is_blocked(client: TestClient) -> None:
    draft = generate(client, "캠페인명: incomplete")

    response = client.post(f"/api/v1/ai/campaign-drafts/{draft['draft_id']}/save")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "conflict"


def test_provider_schema_failure_has_safe_error_contract_and_no_campaign(
    client: TestClient,
) -> None:
    result = generate(client, "{not-valid-json")

    assert result["status"] == "PROVIDER_ERROR"
    assert result["error_code"] == "provider_schema_mismatch"
    assert client.get("/api/v1/campaigns").json()["total"] == 0


def test_ready_save_creates_one_draft_campaign_and_is_idempotent(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    draft = generate(client, complete_prompt())
    url = f"/api/v1/ai/campaign-drafts/{draft['draft_id']}/save"

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == 200
    assert first.json()["campaign_status"] == "DRAFT"
    assert first.json()["already_saved"] is False
    assert second.status_code == 200
    assert second.json()["campaign_id"] == first.json()["campaign_id"]
    assert second.json()["already_saved"] is True
    with db_session_factory() as session:
        assert session.scalar(select(func.count(Campaign.id))) == 1


def test_saved_draft_cannot_be_refined(client: TestClient) -> None:
    draft = generate(client, complete_prompt())
    client.post(f"/api/v1/ai/campaign-drafts/{draft['draft_id']}/save")

    response = client.post(
        f"/api/v1/ai/campaign-drafts/{draft['draft_id']}/refine",
        json={"additional_input": "목표: 변경"},
    )

    assert response.status_code == 409


def test_unknown_draft_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/ai/campaign-drafts/00000000-0000-0000-0000-000000000001")

    assert response.status_code == 404
