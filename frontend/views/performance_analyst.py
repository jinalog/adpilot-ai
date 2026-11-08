from datetime import date
from typing import Any

import streamlit as st

from api_client.client import AdPilotApiClient, ApiClientError
from views.common import show_api_error

EXAMPLE_QUESTIONS = (
    "전체 Campaign의 CTR과 ROAS를 요약해 주세요.",
    "ROAS 상위 3개 Campaign을 보여 주세요.",
    "일별 CTR 추세를 보여 주세요.",
    "탐지된 anomaly를 사실 기반으로 알려 주세요.",
    "Campaign 비교를 보여 주세요.",
)


def render_performance_analyst(client: AdPilotApiClient) -> None:
    st.header("Performance Analyst")
    st.caption(
        "고정 seed 합성 광고 데이터만 조회합니다. Mock planner가 구조화 plan만 만들며 "
        "SQL 실행이나 광고 설정 변경 권한은 없습니다."
    )
    try:
        datasets = client.list_analytics_datasets()["items"]
    except ApiClientError as exc:
        show_api_error(exc)
        return
    if not datasets:
        st.info("분석할 합성 dataset이 없습니다.")
        return
    dataset_labels = {
        item["id"]: f"{item['name']} · seed {item['seed']} · {item['schema_version']}"
        for item in datasets
    }
    dataset_id = st.selectbox(
        "Synthetic dataset",
        list(dataset_labels),
        format_func=lambda value: dataset_labels[value],
    )
    selected_dataset = next(item for item in datasets if item["id"] == dataset_id)
    try:
        campaigns = client.analytics_campaigns(dataset_id)["items"]
    except ApiClientError as exc:
        show_api_error(exc)
        return
    campaign_options = {"": "전체 Campaign"}
    campaign_options.update({item["campaign_id"]: item["campaign_name"] for item in campaigns})
    with st.form("performance-analyst-question"):
        campaign_id = st.selectbox(
            "Campaign context (선택)",
            list(campaign_options),
            format_func=lambda value: campaign_options[value],
        )
        date_columns = st.columns(2)
        start_date = date_columns[0].date_input(
            "시작일", value=date.fromisoformat(selected_dataset["start_date"]), key="analyst_start"
        )
        end_date = date_columns[1].date_input(
            "종료일", value=date.fromisoformat(selected_dataset["end_date"]), key="analyst_end"
        )
        example = st.selectbox("대표 질문 예시", EXAMPLE_QUESTIONS)
        question = st.text_area("자연어 질문", value=example, max_chars=1_000, height=110)
        submitted = st.form_submit_button("안전한 분석 실행", type="primary")
    st.info("Provider: Mock · 실제 LLM 호출 없음 · 사용자 SQL 입력/실행 기능 없음")
    if not submitted:
        return
    payload: dict[str, Any] = {
        "dataset_run_id": dataset_id,
        "question": question,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if campaign_id:
        payload["campaign_id"] = campaign_id
    try:
        response = client.ask_performance_analyst(payload)
    except ApiClientError as exc:
        show_api_error(exc)
        return
    _render_response(response)


def _render_response(response: dict[str, Any]) -> None:
    status = response["status"]
    if status == "NEEDS_CLARIFICATION":
        st.warning("질문을 더 구체적으로 작성해 주세요.")
        for question in response["clarification_questions"]:
            st.write(f"- {question}")
        return
    if status != "READY":
        error_code = response.get("error_code") or "unknown_error"
        failed_step = response.get("failed_step") or "unknown_step"
        if error_code == "query_timeout":
            st.error(f"조회 timeout · 단계: {failed_step}")
        elif status == "VALIDATION_FAILED":
            st.error(f"SQL safety/입력 검증 차단 · {error_code} · 단계: {failed_step}")
        else:
            st.error(f"분석 실패 · {error_code} · 단계: {failed_step}")
        return
    st.success(response["answer_summary"])
    st.subheader("검증 가능한 Facts")
    facts = response["facts"]
    if facts:
        st.dataframe(
            [
                {
                    "Fact": item["label"],
                    "Value": item["value"],
                    "Unit": item["unit"],
                    "Evidence": ", ".join(item["evidence_ids"]),
                }
                for item in facts
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("선택 범위에서 확인된 사실이 없습니다.")
    if response["hypotheses"]:
        st.subheader("Hypotheses · 확인 필요")
        for item in response["hypotheses"]:
            st.warning(item["text"])
    if response["recommendations"]:
        st.subheader("Recommendations · 자동 실행되지 않음")
        for item in response["recommendations"]:
            st.info(item["text"])
    with st.expander("Evidence와 조회 범위"):
        st.json(
            {
                "plan": response["plan"],
                "evidence": response["evidence"],
                "truncated": response["truncated"],
                "provider": {
                    "mode": response["provider_mode"],
                    "model": response["provider_model"],
                    "retry_count": response["retry_count"],
                    "usage": response["usage"],
                },
            }
        )
    if response["truncated"]:
        st.warning("row limit 때문에 결과가 잘렸습니다. 전체 결과로 해석하지 마세요.")
