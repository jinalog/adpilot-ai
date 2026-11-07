import json
from collections.abc import Callable
from typing import Any

import streamlit as st

from api_client.client import (
    ApiClientError,
    ApiConnectionError,
    ApiResponseError,
    ApiTimeoutError,
)

CHANNEL_OPTIONS = ["mobile", "display", "search", "social", "video"]


def show_api_error(error: ApiClientError) -> None:
    if isinstance(error, ApiTimeoutError):
        st.error("API 요청 시간이 초과되었습니다. 잠시 후 다시 시도하세요.")
    elif isinstance(error, ApiConnectionError):
        st.error("Backend에 연결할 수 없습니다. 서버와 API_BASE_URL을 확인하세요.")
    elif isinstance(error, ApiResponseError) and error.status_code == 404:
        st.error(f"캠페인을 찾을 수 없습니다: {error.message}")
    elif isinstance(error, ApiResponseError) and error.status_code == 409:
        st.warning(f"현재 상태에서는 요청을 수행할 수 없습니다: {error.message}")
    elif isinstance(error, ApiResponseError) and error.status_code == 422:
        st.warning(f"입력값을 확인하세요: {error.message}")
    else:
        st.error(f"예상하지 못한 API 오류가 발생했습니다: {error.message}")


def parse_targeting(raw_value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("타게팅은 올바른 JSON 형식이어야 합니다.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("타게팅 JSON의 최상위 값은 객체여야 합니다.")
    return parsed


def format_budget(amount: int) -> str:
    return f"₩{amount:,}"


def set_flash(message: str) -> None:
    st.session_state["flash_message"] = message


def show_flash() -> None:
    message = st.session_state.pop("flash_message", None)
    if message:
        st.success(message)


Navigate = Callable[[str, str | None], None]
