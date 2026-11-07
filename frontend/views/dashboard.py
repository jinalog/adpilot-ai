import streamlit as st

from api_client.client import AdPilotApiClient, ApiClientError
from views.common import show_api_error


def render_dashboard(client: AdPilotApiClient) -> None:
    st.header("Dashboard")
    try:
        health = client.health()
        st.success(f"Backend connected · {health['service']} v{health['version']}")
        counts = client.campaign_counts()
    except ApiClientError as exc:
        show_api_error(exc)
        return

    labels = ["전체", "DRAFT", "APPROVED", "ACTIVE", "PAUSED", "INACTIVE"]
    keys = ["TOTAL", "DRAFT", "APPROVED", "ACTIVE", "PAUSED", "INACTIVE"]
    columns = st.columns(3)
    for index, (label, key) in enumerate(zip(labels, keys, strict=True)):
        columns[index % 3].metric(label, counts[key])

    st.caption(
        "상태별 집계는 목록 API의 total 값을 사용하며 캠페인 전체 데이터를 내려받지 않습니다."
    )
