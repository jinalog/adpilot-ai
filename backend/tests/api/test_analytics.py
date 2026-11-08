import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.domain.synthetic_analytics import SyntheticDatasetConfig, build_synthetic_dataset
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.services.analytics_service import SyntheticDatasetService


def seed_dataset(factory: sessionmaker[Session]) -> tuple[str, str]:
    plan = build_synthetic_dataset(SyntheticDatasetConfig())
    with factory() as session:
        SyntheticDatasetService(AnalyticsRepository(session)).create(plan)
    return str(plan.id), str(plan.campaigns[0].id)


def test_analytics_endpoints_return_summary_sorted_series_campaigns_and_anomalies(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    dataset_id, campaign_id = seed_dataset(db_session_factory)
    params = {"dataset_run_id": dataset_id}

    datasets = client.get("/api/v1/analytics/datasets")
    summary = client.get("/api/v1/analytics/summary", params=params)
    timeseries = client.get("/api/v1/analytics/timeseries", params=params)
    campaigns = client.get("/api/v1/analytics/campaigns", params=params)
    anomalies = client.get("/api/v1/analytics/anomalies", params=params)

    assert datasets.status_code == 200
    assert datasets.json()["items"][0]["seed"] == 20261107
    assert summary.status_code == 200
    assert summary.json()["totals"]["impressions"] > 0
    assert summary.json()["kpis"]["ctr"] > 0
    assert timeseries.status_code == 200
    dates = [item["date"] for item in timeseries.json()["items"]]
    assert dates == sorted(dates)
    assert len(campaigns.json()["items"]) == 6
    assert {item["anomaly_type"] for item in anomalies.json()["items"]} == {
        "CTR_DROP",
        "CVR_DROP",
        "SPEND_SPIKE",
        "IMPRESSION_DROP",
    }
    assert "baseline_metadata" not in anomalies.text

    campaign_summary = client.get(
        "/api/v1/analytics/summary",
        params={**params, "campaign_id": campaign_id},
    )
    assert campaign_summary.status_code == 200
    assert campaign_summary.json()["campaign_id"] == campaign_id


def test_analytics_validation_not_found_and_empty_result_contracts(
    client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    dataset_id, _ = seed_dataset(db_session_factory)
    other_plan = build_synthetic_dataset(
        SyntheticDatasetConfig(name="other-dataset", seed=20261108)
    )
    with db_session_factory() as session:
        SyntheticDatasetService(AnalyticsRepository(session)).create(other_plan)
    invalid_range = client.get(
        "/api/v1/analytics/summary",
        params={
            "dataset_run_id": dataset_id,
            "start_date": "2026-10-01",
            "end_date": "2026-09-01",
        },
    )
    invalid_uuid = client.get("/api/v1/analytics/summary", params={"dataset_run_id": "not-a-uuid"})
    too_wide = client.get(
        "/api/v1/analytics/summary",
        params={
            "dataset_run_id": dataset_id,
            "start_date": "2026-01-01",
            "end_date": "2027-01-02",
        },
    )
    missing_dataset = client.get(
        "/api/v1/analytics/summary", params={"dataset_run_id": str(uuid.uuid4())}
    )
    missing_campaign = client.get(
        "/api/v1/analytics/summary",
        params={"dataset_run_id": dataset_id, "campaign_id": str(uuid.uuid4())},
    )
    foreign_campaign = client.get(
        "/api/v1/analytics/summary",
        params={"dataset_run_id": dataset_id, "campaign_id": str(other_plan.campaigns[0].id)},
    )
    empty = client.get(
        "/api/v1/analytics/timeseries",
        params={
            "dataset_run_id": dataset_id,
            "start_date": date(2027, 1, 1).isoformat(),
            "end_date": date(2027, 1, 2).isoformat(),
        },
    )

    assert invalid_range.status_code == 422
    assert invalid_uuid.status_code == 422
    assert too_wide.status_code == 422
    assert missing_dataset.status_code == 404
    assert missing_campaign.status_code == 404
    assert foreign_campaign.status_code == 404
    assert empty.status_code == 200
    assert empty.json()["items"] == []
