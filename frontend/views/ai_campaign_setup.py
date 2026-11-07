import json
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import streamlit as st

from api_client.client import AdPilotApiClient, ApiClientError
from views.common import CHANNEL_OPTIONS, Navigate, parse_targeting, set_flash, show_api_error


@dataclass(frozen=True, slots=True)
class DraftViewModel:
    status: str
    provider_label: str
    missing_fields: list[str]
    questions: list[str]
    errors: list[str]
    can_edit: bool
    can_save: bool


def build_draft_view_model(response: dict[str, Any]) -> DraftViewModel:
    status = str(response.get("status", "UNKNOWN"))
    return DraftViewModel(
        status=status,
        provider_label=str(response.get("provider_mode", "unknown")).upper(),
        missing_fields=list(response.get("missing_fields", [])),
        questions=list(response.get("clarification_questions", [])),
        errors=list(response.get("validation_errors", [])),
        can_edit=status == "READY",
        can_save=status == "READY" and not bool(response.get("saved", False)),
    )


def acquire_save_lock(state: MutableMapping[str, Any]) -> bool:
    if state.get("ai_save_in_progress"):
        return False
    state["ai_save_in_progress"] = True
    return True


def complete_saved_draft(
    state: MutableMapping[str, Any],
    saved: dict[str, Any],
    navigate: Callable[[str, str | None], None],
) -> None:
    state["ai_campaign_draft"] = None
    state["ai_save_in_progress"] = False
    navigate("Campaign Detail", str(saved["campaign_id"]))


def build_refine_payload(
    *,
    name: str,
    objective: str,
    total_budget_krw: int,
    daily_budget_krw: int,
    start_date: date,
    end_date: date,
    channels: list[str],
    targeting_raw: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "objective": objective,
        "total_budget_krw": total_budget_krw,
        "daily_budget_krw": daily_budget_krw,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "channels": channels,
        "targeting": parse_targeting(targeting_raw),
    }


def render_ai_campaign_setup(client: AdPilotApiClient, navigate: Navigate) -> None:
    st.header("AI Campaign Setup")
    st.caption(
        "자연어를 구조화된 초안으로 변환합니다. 저장 전에는 Campaign을 만들지 않으며, "
        "저장 후에도 상태는 DRAFT입니다."
    )
    with st.form("ai_generate_form"):
        prompt = st.text_area(
            "캠페인 요청",
            height=150,
            placeholder=(
                "캠페인명: 겨울 앱 설치; 목표: 신규 앱 설치; 총예산: 300만원; "
                "일예산: 10만원; 시작일: 2026-12-01; 종료일: 2026-12-31; "
                '채널: mobile, search; 타게팅: {"country":"KR"}'
            ),
        )
        generated = st.form_submit_button("AI 초안 생성", type="primary")
    if generated:
        try:
            st.session_state["ai_campaign_draft"] = client.generate_ai_campaign_draft(prompt)
        except ApiClientError as exc:
            show_api_error(exc)

    response = st.session_state.get("ai_campaign_draft")
    if not isinstance(response, dict):
        return
    _render_result(client, navigate, response)


def _render_result(client: AdPilotApiClient, navigate: Navigate, response: dict[str, Any]) -> None:
    view = build_draft_view_model(response)
    st.info(f"Provider mode: {view.provider_label} · 실제 LLM 정확도 평가 결과가 아닙니다.")
    status = view.status
    st.subheader(f"초안 상태: {status}")
    if response.get("error_code"):
        st.error(f"Provider 처리 실패: {response['error_code']}")
    for error in view.errors:
        st.error(error)
    missing = view.missing_fields
    questions = view.questions
    if missing:
        st.warning("누락 필드: " + ", ".join(missing))
    for question in questions:
        st.write(f"- {question}")

    draft = response.get("draft", {})
    st.json(draft)
    if status in {"NEEDS_CLARIFICATION", "VALIDATION_FAILED"}:
        with st.form("ai_refine_form"):
            additional = st.text_area("추가 정보")
            refined = st.form_submit_button("초안 보완")
        if refined:
            try:
                st.session_state["ai_campaign_draft"] = client.refine_ai_campaign_draft(
                    response["draft_id"], additional_input=additional
                )
                st.rerun()
            except ApiClientError as exc:
                show_api_error(exc)
    if not view.can_edit:
        return

    st.subheader("편집 가능한 미리보기")
    with st.form("ai_preview_form"):
        name = st.text_input("캠페인명", value=draft.get("name", ""))
        objective = st.text_area("광고 목표", value=draft.get("objective", ""))
        budgets = st.columns(2)
        total_budget = budgets[0].number_input(
            "총예산(원)", min_value=1, value=int(draft.get("total_budget_krw", 1))
        )
        daily_budget = budgets[1].number_input(
            "일예산(원)", min_value=1, value=int(draft.get("daily_budget_krw", 1))
        )
        dates = st.columns(2)
        start_date = dates[0].date_input("시작일", value=date.fromisoformat(draft["start_date"]))
        end_date = dates[1].date_input("종료일", value=date.fromisoformat(draft["end_date"]))
        channels = st.multiselect("광고 채널", CHANNEL_OPTIONS, default=draft.get("channels", []))
        targeting_raw = st.text_area(
            "타게팅(JSON)", value=json.dumps(draft.get("targeting", {}), ensure_ascii=False)
        )
        previewed = st.form_submit_button("수정값 검증")
    if previewed:
        try:
            updates = build_refine_payload(
                name=name,
                objective=objective,
                total_budget_krw=total_budget,
                daily_budget_krw=daily_budget,
                start_date=start_date,
                end_date=end_date,
                channels=channels,
                targeting_raw=targeting_raw,
            )
            st.session_state["ai_campaign_draft"] = client.refine_ai_campaign_draft(
                response["draft_id"], draft_updates=updates
            )
            st.rerun()
        except (ValueError, ApiClientError) as exc:
            if isinstance(exc, ApiClientError):
                show_api_error(exc)
            else:
                st.warning(str(exc))

    saving = bool(st.session_state.get("ai_save_in_progress", False))
    if st.button("확인 후 DRAFT 저장", type="primary", disabled=saving):
        if not acquire_save_lock(st.session_state):
            return
        try:
            saved = client.save_ai_campaign_draft(response["draft_id"])
        except ApiClientError as exc:
            show_api_error(exc)
            st.session_state["ai_save_in_progress"] = False
        else:
            set_flash("AI 초안이 DRAFT 캠페인으로 저장되었습니다.")
            complete_saved_draft(st.session_state, saved, navigate)
