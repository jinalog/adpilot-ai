import math

import streamlit as st

from api_client.client import CAMPAIGN_STATUSES, AdPilotApiClient, ApiClientError
from views.common import Navigate, format_budget, show_api_error


def render_campaign_list(client: AdPilotApiClient, navigate: Navigate) -> None:
    title_column, action_column = st.columns([4, 1])
    title_column.header("Campaign List")
    if action_column.button("새 캠페인", type="primary", use_container_width=True):
        navigate("Campaign Create", None)

    filter_column, size_column = st.columns([3, 1])
    status_filter = filter_column.selectbox("상태 필터", ["ALL", *CAMPAIGN_STATUSES])
    page_size = size_column.selectbox("페이지 크기", [10, 20, 50], index=1)
    page_key = f"campaign_page_{status_filter}_{page_size}"
    page = st.session_state.get(page_key, 1)
    offset = (page - 1) * page_size

    try:
        result = client.list_campaigns(
            status=None if status_filter == "ALL" else status_filter,
            offset=offset,
            limit=page_size,
        )
    except ApiClientError as exc:
        show_api_error(exc)
        return

    total = result["total"]
    total_pages = max(1, math.ceil(total / page_size))
    if page > total_pages:
        st.session_state[page_key] = total_pages
        st.rerun()

    rows = [
        {
            "Campaign ID": item["id"],
            "Campaign Name": item["name"],
            "Objective": item["objective"],
            "Total Budget": format_budget(item["total_budget_krw"]),
            "Channel": ", ".join(item["channels"]),
            "Start Date": item["start_date"],
            "End Date": item["end_date"],
            "Status": item["status"],
        }
        for item in result["items"]
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(f"총 {total}개 · {page}/{total_pages} 페이지")

    previous_column, next_column, _ = st.columns([1, 1, 4])
    if previous_column.button("이전", disabled=page <= 1, use_container_width=True):
        st.session_state[page_key] = page - 1
        st.rerun()
    if next_column.button("다음", disabled=page >= total_pages, use_container_width=True):
        st.session_state[page_key] = page + 1
        st.rerun()

    if result["items"]:
        selected_id = st.selectbox(
            "상세 조회할 캠페인",
            options=[item["id"] for item in result["items"]],
            format_func=lambda campaign_id: next(
                item["name"] for item in result["items"] if item["id"] == campaign_id
            ),
        )
        if st.button("상세 보기"):
            navigate("Campaign Detail", selected_id)
