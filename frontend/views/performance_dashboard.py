from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from api_client.client import AdPilotApiClient, ApiClientError
from views.common import show_api_error


def format_nullable(value: float | int | None, *, kind: str) -> str:
    if value is None:
        return "N/A"
    if kind == "percent":
        return f"{float(value) * 100:.2f}%"
    if kind == "money":
        return f"₩{float(value):,.2f}"
    if kind == "ratio":
        return f"{float(value):.2f}x"
    return f"{int(value):,}"


def build_anomaly_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Campaign": item["campaign_name"],
            "Date": item["date"],
            "Type": item["anomaly_type"],
            "Observed": item["observed_value"],
            "Baseline": item["baseline_value"],
            "Change": f"{float(item['change_ratio']) * 100:.1f}%",
            "Threshold": f"{float(item['threshold']) * 100:.1f}%",
        }
        for item in items
    ]


def render_performance_dashboard(client: AdPilotApiClient) -> None:
    st.header("Performance Dashboard")
    st.caption("고정 seed로 생성된 합성 광고 데이터입니다. 실제 광고 성과가 아닙니다.")
    try:
        datasets = client.list_analytics_datasets()["items"]
    except ApiClientError as exc:
        show_api_error(exc)
        return
    if not datasets:
        st.info("조회할 합성 dataset이 없습니다. seed generator를 먼저 실행하세요.")
        return

    dataset_labels = {
        f"{item['name']} · seed {item['seed']} · {item['schema_version']}": item
        for item in datasets
    }
    selected_label = st.selectbox("Dataset", list(dataset_labels))
    selected_dataset = dataset_labels[selected_label]
    dataset_id = selected_dataset["id"]
    default_start = date.fromisoformat(selected_dataset["start_date"])
    default_end = date.fromisoformat(selected_dataset["end_date"])

    try:
        all_campaigns = client.analytics_campaigns(dataset_id)["items"]
    except ApiClientError as exc:
        show_api_error(exc)
        return
    campaign_options = {"전체 Campaign": None}
    campaign_options.update({item["campaign_name"]: item["campaign_id"] for item in all_campaigns})

    filter_columns = st.columns(3)
    start_date = filter_columns[0].date_input("시작일", value=default_start)
    end_date = filter_columns[1].date_input("종료일", value=default_end)
    selected_campaign = filter_columns[2].selectbox("Campaign", list(campaign_options))
    campaign_id = campaign_options[selected_campaign]

    try:
        summary = client.analytics_summary(
            dataset_id,
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
        )
        timeseries = client.analytics_timeseries(
            dataset_id,
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
        )
        campaign_comparison = client.analytics_campaigns(
            dataset_id, start_date=start_date, end_date=end_date
        )
        anomalies = client.analytics_anomalies(
            dataset_id,
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ApiClientError as exc:
        show_api_error(exc)
        return

    _render_kpis(summary)
    if not timeseries["items"]:
        st.info("선택한 기간과 Campaign에 성과 데이터가 없습니다.")
        return
    _render_timeseries(timeseries["items"])
    _render_campaign_comparison(campaign_comparison["items"])
    _render_anomalies(anomalies["items"])
    st.caption(
        "Anomaly는 저장된 truth를 읽지 않는 rules-v1 detector 결과입니다. "
        "합성 회귀 평가 수치는 실제 운영 정확도를 의미하지 않습니다."
    )


def _render_kpis(summary: dict[str, Any]) -> None:
    totals = summary["totals"]
    kpis = summary["kpis"]
    raw = [
        ("Impressions", totals["impressions"], "count"),
        ("Clicks", totals["clicks"], "count"),
        ("Conversions", totals["conversions"], "count"),
        ("Spend", totals["spend_krw"], "money"),
        ("Revenue", totals["revenue_krw"], "money"),
    ]
    derived = [
        ("CTR", kpis["ctr"], "percent"),
        ("CVR", kpis["cvr"], "percent"),
        ("CPM", kpis["cpm_krw"], "money"),
        ("CPC", kpis["cpc_krw"], "money"),
        ("CPA", kpis["cpa_krw"], "money"),
        ("ROAS", kpis["roas"], "ratio"),
    ]
    for values in (raw, derived):
        columns = st.columns(len(values))
        for column, (label, value, kind) in zip(columns, values, strict=True):
            column.metric(label, format_nullable(value, kind=kind))


def _render_timeseries(items: list[dict[str, Any]]) -> None:
    rows = [
        {
            "date": item["date"],
            **item["totals"],
            "ctr_percent": (item["kpis"]["ctr"] * 100 if item["kpis"]["ctr"] is not None else None),
            "cvr_percent": (item["kpis"]["cvr"] * 100 if item["kpis"]["cvr"] is not None else None),
        }
        for item in items
    ]
    frame = pd.DataFrame(rows).set_index("date")
    st.subheader("일별 성과 추세")
    st.line_chart(frame[["impressions", "clicks", "conversions"]])
    st.line_chart(frame[["spend_krw", "revenue_krw"]])
    st.line_chart(frame[["ctr_percent", "cvr_percent"]])


def _render_campaign_comparison(items: list[dict[str, Any]]) -> None:
    st.subheader("Campaign별 성과 비교")
    rows = [
        {
            "Campaign": item["campaign_name"],
            "Impressions": item["totals"]["impressions"],
            "Clicks": item["totals"]["clicks"],
            "Conversions": item["totals"]["conversions"],
            "Spend": item["totals"]["spend_krw"],
            "Revenue": item["totals"]["revenue_krw"],
            "CTR": format_nullable(item["kpis"]["ctr"], kind="percent"),
            "CVR": format_nullable(item["kpis"]["cvr"], kind="percent"),
            "ROAS": format_nullable(item["kpis"]["roas"], kind="ratio"),
        }
        for item in items
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_anomalies(items: list[dict[str, Any]]) -> None:
    st.subheader("규칙 기반 Anomaly 탐지")
    if not items:
        st.info("선택 범위에서 탐지된 anomaly가 없습니다.")
        return
    st.dataframe(build_anomaly_rows(items), use_container_width=True, hide_index=True)
