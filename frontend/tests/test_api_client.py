import json
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
from views.common import format_budget, parse_targeting


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
