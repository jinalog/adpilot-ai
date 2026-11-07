import os
from collections.abc import Mapping
from typing import Any

import requests

DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1"
CAMPAIGN_STATUSES = ("DRAFT", "APPROVED", "ACTIVE", "PAUSED", "INACTIVE")


class ApiClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str = "client_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class ApiConnectionError(ApiClientError):
    pass


class ApiTimeoutError(ApiClientError):
    pass


class ApiResponseError(ApiClientError):
    pass


class AdPilotApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 5.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def campaign_counts(self) -> dict[str, int]:
        counts = {"TOTAL": self.list_campaigns(limit=1)["total"]}
        for campaign_status in CAMPAIGN_STATUSES:
            counts[campaign_status] = self.list_campaigns(status=campaign_status, limit=1)["total"]
        return counts

    def list_campaigns(
        self,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        payload = self._request_json("GET", "/campaigns", params=params)
        if not isinstance(payload.get("items"), list) or not isinstance(payload.get("total"), int):
            raise ApiResponseError(
                "Campaign list response has an invalid shape", code="invalid_json"
            )
        return payload

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/campaigns", json=dict(payload))

    def update_campaign(self, campaign_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request_json("PATCH", f"/campaigns/{campaign_id}", json=dict(payload))

    def approve_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"/campaigns/{campaign_id}/approve")

    def change_campaign_status(self, campaign_id: str, status: str) -> dict[str, Any]:
        return self._request_json(
            "PATCH", f"/campaigns/{campaign_id}/status", json={"status": status}
        )

    def deactivate_campaign(self, campaign_id: str) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, path, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiResponseError(
                "Backend returned a non-JSON response",
                status_code=response.status_code,
                code="invalid_json",
            ) from exc
        if not isinstance(payload, dict):
            raise ApiResponseError(
                "Backend returned an unexpected JSON response",
                status_code=response.status_code,
                code="invalid_json",
            )
        return payload

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except requests.Timeout as exc:
            raise ApiTimeoutError("Backend request timed out", code="timeout") from exc
        except requests.ConnectionError as exc:
            raise ApiConnectionError(
                "Could not connect to the Backend", code="connection_error"
            ) from exc
        except requests.RequestException as exc:
            raise ApiClientError("Backend request failed", code="request_error") from exc

        if response.ok:
            return response
        raise self._http_error(response)

    @staticmethod
    def _http_error(response: requests.Response) -> ApiResponseError:
        message = f"Backend returned HTTP {response.status_code}"
        code = "http_error"
        try:
            detail = response.json().get("detail")
            if isinstance(detail, dict):
                code = str(detail.get("code", code))
                message = str(detail.get("message", message))
            elif isinstance(detail, list):
                validation_messages = []
                for item in detail:
                    if not isinstance(item, dict):
                        continue
                    location = ".".join(str(part) for part in item.get("loc", []) if part != "body")
                    item_message = str(item.get("msg", "Invalid value"))
                    validation_messages.append(
                        f"{location}: {item_message}" if location else item_message
                    )
                if validation_messages:
                    message = "; ".join(validation_messages)
                code = "validation_error"
            elif isinstance(detail, str):
                message = detail
        except (ValueError, AttributeError):
            pass
        return ApiResponseError(message, status_code=response.status_code, code=code)
