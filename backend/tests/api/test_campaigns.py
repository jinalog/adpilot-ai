import uuid
from collections.abc import Mapping
from typing import Any

from fastapi.testclient import TestClient


def campaign_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "신규 쇼핑몰 전환 캠페인",
        "objective": "구매 전환 증대",
        "total_budget_krw": 3_000_000,
        "daily_budget_krw": 100_000,
        "start_date": "2026-11-10",
        "end_date": "2026-12-09",
        "channels": ["Mobile", "Display"],
        "targeting": {"country": "KR", "device": ["mobile"]},
    }
    payload.update(overrides)
    return payload


def create_campaign(client: TestClient, **overrides: Any) -> Mapping[str, Any]:
    response = client.post("/api/v1/campaigns", json=campaign_payload(**overrides))
    assert response.status_code == 201
    return response.json()


def test_create_and_get_campaign(client: TestClient) -> None:
    created = create_campaign(client)

    assert created["status"] == "DRAFT"
    assert created["channels"] == ["mobile", "display"]
    assert created["approved_at"] is None

    response = client.get(f"/api/v1/campaigns/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_create_rejects_invalid_budget_relationship(client: TestClient) -> None:
    response = client.post(
        "/api/v1/campaigns",
        json=campaign_payload(total_budget_krw=100_000, daily_budget_krw=100_001),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "business_rule_violation"


def test_create_rejects_invalid_date_range(client: TestClient) -> None:
    response = client.post(
        "/api/v1/campaigns",
        json=campaign_payload(start_date="2026-12-01", end_date="2026-11-30"),
    )

    assert response.status_code == 422
    assert "end_date" in response.json()["detail"]["message"]


def test_create_rejects_missing_and_blank_required_fields(client: TestClient) -> None:
    missing = campaign_payload()
    missing.pop("objective")

    missing_response = client.post("/api/v1/campaigns", json=missing)
    blank_response = client.post("/api/v1/campaigns", json=campaign_payload(name="   "))

    assert missing_response.status_code == 422
    assert blank_response.status_code == 422


def test_list_campaigns_supports_pagination_and_status_filter(client: TestClient) -> None:
    draft = create_campaign(client, name="Draft")
    approved_candidate = create_campaign(client, name="Approved")
    approve_response = client.post(f"/api/v1/campaigns/{approved_candidate['id']}/approve")
    assert approve_response.status_code == 200

    response = client.get("/api/v1/campaigns?status=DRAFT&offset=0&limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 1
    assert body["items"][0]["id"] == draft["id"]


def test_update_draft_campaign(client: TestClient) -> None:
    campaign = create_campaign(client)

    response = client.patch(
        f"/api/v1/campaigns/{campaign['id']}",
        json={"daily_budget_krw": 150_000, "name": "수정된 캠페인"},
    )

    assert response.status_code == 200
    assert response.json()["daily_budget_krw"] == 150_000
    assert response.json()["name"] == "수정된 캠페인"


def test_editing_approved_campaign_invalidates_approval(client: TestClient) -> None:
    campaign = create_campaign(client)
    approved = client.post(f"/api/v1/campaigns/{campaign['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["approved_at"] is not None

    response = client.patch(f"/api/v1/campaigns/{campaign['id']}", json={"objective": "새 목표"})

    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"
    assert response.json()["approved_at"] is None


def test_approve_activate_pause_and_reactivate(client: TestClient) -> None:
    campaign = create_campaign(client)
    campaign_url = f"/api/v1/campaigns/{campaign['id']}"

    approved = client.post(f"{campaign_url}/approve")
    activated = client.patch(f"{campaign_url}/status", json={"status": "ACTIVE"})
    paused = client.patch(f"{campaign_url}/status", json={"status": "PAUSED"})
    reactivated = client.patch(f"{campaign_url}/status", json={"status": "ACTIVE"})

    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert activated.json()["status"] == "ACTIVE"
    assert paused.json()["status"] == "PAUSED"
    assert reactivated.json()["status"] == "ACTIVE"


def test_invalid_status_transition_is_conflict(client: TestClient) -> None:
    campaign = create_campaign(client)

    response = client.patch(f"/api/v1/campaigns/{campaign['id']}/status", json={"status": "ACTIVE"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "conflict"


def test_delete_soft_deactivates_campaign(client: TestClient) -> None:
    campaign = create_campaign(client)

    response = client.delete(f"/api/v1/campaigns/{campaign['id']}")
    stored = client.get(f"/api/v1/campaigns/{campaign['id']}")

    assert response.status_code == 204
    assert stored.status_code == 200
    assert stored.json()["status"] == "INACTIVE"
    assert stored.json()["deactivated_at"] is not None


def test_active_campaign_cannot_be_edited(client: TestClient) -> None:
    campaign = create_campaign(client)
    campaign_url = f"/api/v1/campaigns/{campaign['id']}"
    client.post(f"{campaign_url}/approve")
    client.patch(f"{campaign_url}/status", json={"status": "ACTIVE"})

    response = client.patch(campaign_url, json={"name": "허용되지 않는 수정"})

    assert response.status_code == 409


def test_unknown_campaign_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/campaigns/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"
