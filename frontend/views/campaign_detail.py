import json
from datetime import date

import streamlit as st

from api_client.client import AdPilotApiClient, ApiClientError
from views.common import (
    CHANNEL_OPTIONS,
    Navigate,
    format_budget,
    parse_targeting,
    set_flash,
    show_api_error,
)

STATUS_ACTIONS = {
    "APPROVED": ("활성화", "ACTIVE"),
    "ACTIVE": ("일시정지", "PAUSED"),
    "PAUSED": ("재활성화", "ACTIVE"),
}


def render_campaign_detail(client: AdPilotApiClient, navigate: Navigate) -> None:
    st.header("Campaign Detail / Edit")
    campaign_id = st.text_input(
        "Campaign ID", value=st.session_state.get("selected_campaign_id", "")
    ).strip()
    if not campaign_id:
        st.info("Campaign List에서 캠페인을 선택하거나 ID를 입력하세요.")
        return
    st.session_state["selected_campaign_id"] = campaign_id

    try:
        campaign = client.get_campaign(campaign_id)
    except ApiClientError as exc:
        show_api_error(exc)
        return

    status = campaign["status"]
    st.subheader(campaign["name"])
    metrics = st.columns(4)
    metrics[0].metric("상태", status)
    metrics[1].metric("총예산", format_budget(campaign["total_budget_krw"]))
    metrics[2].metric("일예산", format_budget(campaign["daily_budget_krw"]))
    metrics[3].metric("기간", f"{campaign['start_date']} ~ {campaign['end_date']}")

    editable = status in {"DRAFT", "APPROVED"}
    if status == "APPROVED":
        st.warning("승인된 설정을 수정하면 기존 승인이 무효화되고 DRAFT로 돌아갑니다.")
    elif not editable:
        st.info(f"{status} 상태에서는 설정을 수정할 수 없습니다.")

    with st.form("campaign_edit_form"):
        name = st.text_input("캠페인명", value=campaign["name"], disabled=not editable)
        objective = st.text_area("광고 목표", value=campaign["objective"], disabled=not editable)
        budget_columns = st.columns(2)
        total_budget = budget_columns[0].number_input(
            "총예산(원)",
            min_value=1,
            value=campaign["total_budget_krw"],
            step=100_000,
            disabled=not editable,
        )
        daily_budget = budget_columns[1].number_input(
            "일예산(원)",
            min_value=1,
            value=campaign["daily_budget_krw"],
            step=10_000,
            disabled=not editable,
        )
        date_columns = st.columns(2)
        start_date = date_columns[0].date_input(
            "시작일", value=date.fromisoformat(campaign["start_date"]), disabled=not editable
        )
        end_date = date_columns[1].date_input(
            "종료일", value=date.fromisoformat(campaign["end_date"]), disabled=not editable
        )
        extra_channels = [
            channel for channel in campaign["channels"] if channel not in CHANNEL_OPTIONS
        ]
        channels = st.multiselect(
            "광고 채널",
            [*CHANNEL_OPTIONS, *extra_channels],
            default=campaign["channels"],
            disabled=not editable,
        )
        targeting_raw = st.text_area(
            "타게팅(JSON)",
            value=json.dumps(campaign["targeting"], ensure_ascii=False, indent=2),
            disabled=not editable,
        )
        update_submitted = st.form_submit_button("설정 저장", disabled=not editable)

    if update_submitted:
        _update_campaign(
            client,
            campaign_id,
            name=name,
            objective=objective,
            total_budget=total_budget,
            daily_budget=daily_budget,
            start_date=start_date,
            end_date=end_date,
            channels=channels,
            targeting_raw=targeting_raw,
        )

    st.divider()
    st.subheader("Approval / Status")
    _render_status_actions(client, campaign_id, status)

    if st.button("목록으로"):
        navigate("Campaign List", None)


def _update_campaign(
    client: AdPilotApiClient,
    campaign_id: str,
    *,
    name: str,
    objective: str,
    total_budget: int,
    daily_budget: int,
    start_date: date,
    end_date: date,
    channels: list[str],
    targeting_raw: str,
) -> None:
    if not name.strip() or not objective.strip() or not channels:
        st.warning("캠페인명, 광고 목표, 광고 채널은 필수입니다.")
        return
    if daily_budget > total_budget or end_date < start_date:
        st.warning("예산과 기간 입력값을 확인하세요.")
        return
    try:
        client.update_campaign(
            campaign_id,
            {
                "name": name,
                "objective": objective,
                "total_budget_krw": total_budget,
                "daily_budget_krw": daily_budget,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "channels": channels,
                "targeting": parse_targeting(targeting_raw),
            },
        )
    except ValueError as exc:
        st.warning(str(exc))
    except ApiClientError as exc:
        show_api_error(exc)
    else:
        set_flash("캠페인 설정이 저장되었습니다.")
        st.rerun()


def _render_status_actions(client: AdPilotApiClient, campaign_id: str, status: str) -> None:
    action_columns = st.columns(3)
    try:
        if status == "DRAFT" and action_columns[0].button("승인", type="primary"):
            client.approve_campaign(campaign_id)
            set_flash("캠페인이 승인되었습니다.")
            st.rerun()

        action = STATUS_ACTIONS.get(status)
        if action and action_columns[1].button(action[0], type="primary"):
            client.change_campaign_status(campaign_id, action[1])
            set_flash(f"캠페인 상태가 {action[1]}로 변경되었습니다.")
            st.rerun()

        can_deactivate = status != "INACTIVE"
        confirmation = st.checkbox(
            "비활성화를 확인합니다. INACTIVE는 최종 상태이며 되돌릴 수 없습니다.",
            disabled=not can_deactivate,
        )
        if action_columns[2].button(
            "비활성화",
            disabled=not can_deactivate or not confirmation,
            type="secondary",
        ):
            client.deactivate_campaign(campaign_id)
            set_flash("캠페인이 비활성화되었습니다.")
            st.rerun()
    except ApiClientError as exc:
        show_api_error(exc)
