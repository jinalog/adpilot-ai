from datetime import date, timedelta

import streamlit as st

from api_client.client import AdPilotApiClient, ApiClientError
from views.common import (
    CHANNEL_OPTIONS,
    Navigate,
    parse_targeting,
    set_flash,
    show_api_error,
)


def render_campaign_create(client: AdPilotApiClient, navigate: Navigate) -> None:
    st.header("Campaign Create")
    st.caption("새 캠페인은 항상 DRAFT 상태로 생성되며 Backend가 최종 검증합니다.")

    today = date.today()
    with st.form("campaign_create_form"):
        name = st.text_input("캠페인명 *", max_chars=120)
        objective = st.text_area("광고 목표 *", max_chars=2_000)
        budget_columns = st.columns(2)
        total_budget = budget_columns[0].number_input(
            "총예산(원) *", min_value=1, value=3_000_000, step=100_000
        )
        daily_budget = budget_columns[1].number_input(
            "일예산(원) *", min_value=1, value=100_000, step=10_000
        )
        date_columns = st.columns(2)
        start_date = date_columns[0].date_input("시작일 *", value=today)
        end_date = date_columns[1].date_input("종료일 *", value=today + timedelta(days=29))
        channels = st.multiselect("광고 채널 *", CHANNEL_OPTIONS, default=["mobile"])
        targeting_raw = st.text_area(
            "타게팅(JSON)", value='{"country": "KR", "device": ["mobile"]}'
        )
        submitted = st.form_submit_button("DRAFT 생성", type="primary")

    if not submitted:
        return
    if not name.strip() or not objective.strip() or not channels:
        st.warning("캠페인명, 광고 목표, 광고 채널은 필수입니다.")
        return
    if daily_budget > total_budget:
        st.warning("일예산은 총예산보다 클 수 없습니다.")
        return
    if end_date < start_date:
        st.warning("종료일은 시작일보다 빠를 수 없습니다.")
        return
    try:
        targeting = parse_targeting(targeting_raw)
        campaign = client.create_campaign(
            {
                "name": name,
                "objective": objective,
                "total_budget_krw": total_budget,
                "daily_budget_krw": daily_budget,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "channels": channels,
                "targeting": targeting,
            }
        )
    except ValueError as exc:
        st.warning(str(exc))
    except ApiClientError as exc:
        show_api_error(exc)
    else:
        set_flash(f"캠페인 '{campaign['name']}'이 DRAFT로 생성되었습니다.")
        navigate("Campaign Detail", campaign["id"])
