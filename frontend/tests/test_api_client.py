import json
from datetime import date
from typing import Any

import pytest
import requests

from api_client.client import (
    CAMPAIGN_STATUSES,
    AdPilotApiClient,
    ApiConnectionError,
    ApiResponseError,
    ApiTimeoutError,
)
from views.ai_campaign_setup import (
    acquire_save_lock,
    build_draft_view_model,
    build_refine_payload,
    complete_saved_draft,
)
from views.common import format_budget, parse_targeting
from views.performance_dashboard import build_anomaly_rows, build_timeseries_rows, format_nullable


def response(
    status_code: int, payload: Any | None = None, *, raw: bytes | None = None
) -> requests.Response:
    result = requests.Response()
    result.status_code = status_code
    result.headers["Content-Type"] = "application/json"
    result._content = raw if raw is not None else json.dumps(payload).encode()
    return result


class FakeSession:
    def __init__(self, results: list[requests.Response | Exception]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_campaign_api_methods_use_expected_rest_contract() -> None:
    campaign = {"id": "campaign-id", "status": "DRAFT"}
    session = FakeSession(
        [
            response(200, {"status": "ok"}),
            response(200, {"items": [campaign], "total": 1, "offset": 0, "limit": 20}),
            response(200, campaign),
            response(201, campaign),
            response(200, campaign),
            response(200, {**campaign, "status": "APPROVED"}),
            response(200, {**campaign, "status": "ACTIVE"}),
            response(204, raw=b""),
        ]
    )
    client = AdPilotApiClient("http://backend/api/v1", session=session)  # type: ignore[arg-type]

    assert client.health()["status"] == "ok"
    assert client.list_campaigns()["total"] == 1
    assert client.get_campaign("campaign-id")["id"] == "campaign-id"
    client.create_campaign({"name": "Campaign"})
    client.update_campaign("campaign-id", {"name": "Updated"})
    client.approve_campaign("campaign-id")
    client.change_campaign_status("campaign-id", "ACTIVE")
    client.deactivate_campaign("campaign-id")

    assert [call["method"] for call in session.calls] == [
        "GET",
        "GET",
        "GET",
        "POST",
        "PATCH",
        "POST",
        "PATCH",
        "DELETE",
    ]
    assert session.calls[-2]["json"] == {"status": "ACTIVE"}
    assert all(call["timeout"] == 5.0 for call in session.calls)


def test_campaign_counts_requests_only_totals_with_limit_one() -> None:
    totals = [12, 2, 3, 4, 1, 2]
    session = FakeSession(
        [response(200, {"items": [], "total": total, "offset": 0, "limit": 1}) for total in totals]
    )
    client = AdPilotApiClient(session=session)  # type: ignore[arg-type]

    counts = client.campaign_counts()

    assert counts == {"TOTAL": 12, **dict(zip(CAMPAIGN_STATUSES, totals[1:], strict=True))}
    assert all(call["params"]["limit"] == 1 for call in session.calls)
    assert len(session.calls) == 6


@pytest.mark.parametrize(
    ("status_code", "detail", "expected_code", "message"),
    [
        (404, {"code": "not_found", "message": "missing"}, "not_found", "missing"),
        (409, {"code": "conflict", "message": "invalid state"}, "conflict", "invalid state"),
        (
            422,
            [{"loc": ["body", "daily_budget_krw"], "msg": "must be positive"}],
            "validation_error",
            "daily_budget_krw: must be positive",
        ),
    ],
)
def test_http_errors_preserve_backend_validation_details(
    status_code: int, detail: Any, expected_code: str, message: str
) -> None:
    client = AdPilotApiClient(
        session=FakeSession([response(status_code, {"detail": detail})])  # type: ignore[arg-type]
    )

    with pytest.raises(ApiResponseError) as error:
        client.health()

    assert error.value.status_code == status_code
    assert error.value.code == expected_code
    assert error.value.message == message


@pytest.mark.parametrize(
    ("exception", "error_type"),
    [
        (requests.Timeout(), ApiTimeoutError),
        (requests.ConnectionError(), ApiConnectionError),
    ],
)
def test_transport_errors_are_classified(exception: Exception, error_type: type[Exception]) -> None:
    client = AdPilotApiClient(session=FakeSession([exception]))  # type: ignore[arg-type]

    with pytest.raises(error_type):
        client.health()


def test_invalid_json_and_campaign_list_shape_are_rejected() -> None:
    invalid_json_client = AdPilotApiClient(
        session=FakeSession([response(200, raw=b"not-json")])  # type: ignore[arg-type]
    )
    invalid_shape_client = AdPilotApiClient(
        session=FakeSession([response(200, {"items": {}, "total": "one"})])  # type: ignore[arg-type]
    )

    with pytest.raises(ApiResponseError, match="non-JSON"):
        invalid_json_client.health()
    with pytest.raises(ApiResponseError, match="invalid shape"):
        invalid_shape_client.list_campaigns()


def test_targeting_and_budget_ui_helpers() -> None:
    assert parse_targeting('{"country": "KR"}') == {"country": "KR"}
    assert format_budget(3_000_000) == "₩3,000,000"
    with pytest.raises(ValueError, match="JSON"):
        parse_targeting("not-json")
    with pytest.raises(ValueError, match="객체"):
        parse_targeting("[]")


def test_ai_campaign_api_methods_use_expected_contract() -> None:
    draft = {"draft_id": "draft-id", "status": "READY", "provider_mode": "mock"}
    saved = {"draft_id": "draft-id", "campaign_id": "campaign-id"}
    session = FakeSession(
        [response(201, draft), response(200, draft), response(200, draft), response(200, saved)]
    )
    client = AdPilotApiClient("http://backend/api/v1", session=session)  # type: ignore[arg-type]

    assert client.generate_ai_campaign_draft("request")["status"] == "READY"
    client.refine_ai_campaign_draft("draft-id", draft_updates={"name": "Edited"})
    client.get_ai_campaign_draft("draft-id")
    assert client.save_ai_campaign_draft("draft-id")["campaign_id"] == "campaign-id"

    assert [call["url"] for call in session.calls] == [
        "http://backend/api/v1/ai/campaign-drafts/generate",
        "http://backend/api/v1/ai/campaign-drafts/draft-id/refine",
        "http://backend/api/v1/ai/campaign-drafts/draft-id",
        "http://backend/api/v1/ai/campaign-drafts/draft-id/save",
    ]
    assert session.calls[1]["json"]["draft_updates"] == {"name": "Edited"}


def test_ready_preview_payload_serializes_editable_fields() -> None:
    payload = build_refine_payload(
        name="Preview",
        objective="Install",
        total_budget_krw=1_000_000,
        daily_budget_krw=100_000,
        start_date=date(2026, 12, 1),
        end_date=date(2026, 12, 10),
        channels=["mobile"],
        targeting_raw='{"country":"KR"}',
    )

    assert payload["start_date"] == "2026-12-01"
    assert payload["targeting"] == {"country": "KR"}


def test_ai_draft_view_model_exposes_ready_clarification_and_errors() -> None:
    ready = build_draft_view_model({"status": "READY", "provider_mode": "mock"})
    clarification = build_draft_view_model(
        {
            "status": "NEEDS_CLARIFICATION",
            "provider_mode": "mock",
            "missing_fields": ["name"],
            "clarification_questions": ["캠페인명을 알려주세요."],
        }
    )
    invalid = build_draft_view_model(
        {"status": "VALIDATION_FAILED", "validation_errors": ["invalid budget"]}
    )

    assert ready.provider_label == "MOCK"
    assert ready.can_edit and ready.can_save
    assert clarification.questions == ["캠페인명을 알려주세요."]
    assert not clarification.can_save
    assert invalid.errors == ["invalid budget"]


def test_save_lock_blocks_duplicate_click_and_completion_navigates() -> None:
    state: dict[str, Any] = {"ai_campaign_draft": {"status": "READY"}}
    navigation: list[tuple[str, str | None]] = []

    assert acquire_save_lock(state) is True
    assert acquire_save_lock(state) is False
    complete_saved_draft(
        state,
        {"campaign_id": "campaign-id"},
        lambda page, campaign_id=None: navigation.append((page, campaign_id)),
    )

    assert state["ai_save_in_progress"] is False
    assert navigation == [("Campaign Detail", "campaign-id")]


def test_analytics_client_uses_dataset_campaign_and_date_filters() -> None:
    session = FakeSession(
        [
            response(200, {"items": [{"id": "dataset-id"}]}),
            response(200, {"totals": {}, "kpis": {}}),
            response(200, {"items": []}),
            response(200, {"items": []}),
            response(200, {"items": []}),
        ]
    )
    client = AdPilotApiClient("http://backend/api/v1", session=session)  # type: ignore[arg-type]

    client.list_analytics_datasets()
    client.analytics_summary(
        "dataset-id",
        campaign_id="campaign-id",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )
    client.analytics_timeseries("dataset-id")
    client.analytics_campaigns("dataset-id")
    client.analytics_anomalies("dataset-id", campaign_id="campaign-id")

    assert [call["url"] for call in session.calls] == [
        "http://backend/api/v1/analytics/datasets",
        "http://backend/api/v1/analytics/summary",
        "http://backend/api/v1/analytics/timeseries",
        "http://backend/api/v1/analytics/campaigns",
        "http://backend/api/v1/analytics/anomalies",
    ]
    assert session.calls[1]["params"] == {
        "dataset_run_id": "dataset-id",
        "campaign_id": "campaign-id",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }


def test_performance_analyst_client_posts_question_without_raw_sql() -> None:
    session = FakeSession([response(200, {"status": "READY", "facts": []})])
    client = AdPilotApiClient("http://backend/api/v1", session=session)  # type: ignore[arg-type]
    payload = {
        "dataset_run_id": "dataset-id",
        "question": "CTR을 요약해 주세요.",
        "campaign_id": "campaign-id",
    }

    result = client.ask_performance_analyst(payload)

    assert result["status"] == "READY"
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"] == "http://backend/api/v1/analyst/questions"
    assert session.calls[0]["json"] == payload
    assert "sql" not in session.calls[0]["json"]


def test_performance_dashboard_helpers_show_null_and_anomaly_contract() -> None:
    assert format_nullable(None, kind="percent") == "N/A (분모 0)"
    assert format_nullable(0.1234, kind="percent") == "12.34%"
    assert format_nullable(71_593_179, kind="money_integer") == "₩71,593,179"
    assert format_nullable(1234.5, kind="money") == "₩1,234.50"
    rows = build_anomaly_rows(
        [
            {
                "campaign_name": "Synthetic 1",
                "date": "2026-09-22",
                "anomaly_type": "CTR_DROP",
                "observed_value": 0.03,
                "baseline_value": 0.05,
                "change_ratio": 0.6,
                "threshold": 0.6,
            }
        ]
    )
    assert rows[0]["Type"] == "CTR_DROP"
    assert rows[0]["Change"] == "60.0%"


def test_performance_dashboard_timeseries_rows_keep_units_and_null_rates() -> None:
    rows = build_timeseries_rows(
        [
            {
                "date": "2026-09-01",
                "totals": {
                    "impressions": 100,
                    "clicks": 0,
                    "conversions": 0,
                    "spend_krw": 1_000,
                    "revenue_krw": 0,
                },
                "kpis": {"ctr": 0.0, "cvr": None},
            }
        ]
    )

    assert rows == [
        {
            "Date": "2026-09-01",
            "Impressions": 100,
            "Clicks": 0,
            "Conversions": 0,
            "Spend (KRW)": 1_000,
            "Revenue (KRW)": 0,
            "CTR (%)": 0.0,
            "CVR (%)": None,
        }
    ]
