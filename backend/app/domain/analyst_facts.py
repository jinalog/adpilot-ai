from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.analytics import MetricTotals, MetricValue, calculate_kpis, detect_anomalies
from app.schemas.analyst import (
    AnalysisMetric,
    AnalysisPlan,
    AnalystEvidence,
    AnalystFact,
    AnalystHypothesis,
    AnalystRecommendation,
    QuestionType,
    SortDirection,
)

METRIC_UNITS = {
    AnalysisMetric.IMPRESSIONS: "count",
    AnalysisMetric.CLICKS: "count",
    AnalysisMetric.CONVERSIONS: "count",
    AnalysisMetric.SPEND_KRW: "KRW",
    AnalysisMetric.REVENUE_KRW: "KRW",
    AnalysisMetric.CTR: "ratio",
    AnalysisMetric.CVR: "ratio",
    AnalysisMetric.CPM_KRW: "KRW",
    AnalysisMetric.CPC_KRW: "KRW",
    AnalysisMetric.CPA_KRW: "KRW",
    AnalysisMetric.ROAS: "ratio",
}


def _values(row: dict[str, Any]) -> dict[str, int | float | None]:
    totals = MetricTotals(
        impressions=int(row.get("impressions", 0)),
        clicks=int(row.get("clicks", 0)),
        conversions=int(row.get("conversions", 0)),
        spend_krw=int(row.get("spend_krw", 0)),
        revenue_krw=int(row.get("revenue_krw", 0)),
    )
    kpis = calculate_kpis(totals)
    return {
        "impressions": totals.impressions,
        "clicks": totals.clicks,
        "conversions": totals.conversions,
        "spend_krw": totals.spend_krw,
        "revenue_krw": totals.revenue_krw,
        "ctr": None if kpis.ctr is None else float(kpis.ctr),
        "cvr": None if kpis.cvr is None else float(kpis.cvr),
        "cpm_krw": None if kpis.cpm_krw is None else float(kpis.cpm_krw),
        "cpc_krw": None if kpis.cpc_krw is None else float(kpis.cpc_krw),
        "cpa_krw": None if kpis.cpa_krw is None else float(kpis.cpa_krw),
        "roas": None if kpis.roas is None else float(kpis.roas),
    }


@dataclass(frozen=True, slots=True)
class FactBuildResult:
    facts: list[AnalystFact]
    evidence: list[AnalystEvidence]
    hypotheses: list[AnalystHypothesis]
    recommendations: list[AnalystRecommendation]
    summary: str
    no_data: bool = False
    data_notices: tuple[str, ...] = ()


class AnalystFactBuilder:
    def build(
        self,
        plan: AnalysisPlan,
        rows: list[dict[str, Any]],
        *,
        query_fingerprint: str,
    ) -> FactBuildResult:
        if not rows or not any(int(row.get("source_row_count", 1) or 0) > 0 for row in rows):
            return FactBuildResult(
                facts=[],
                evidence=[],
                hypotheses=[],
                recommendations=[],
                summary=(
                    f"합성 dataset의 {plan.start_date}~{plan.end_date} 범위에 "
                    "원본 metric 행이 없습니다."
                ),
                no_data=True,
            )
        if plan.question_type is QuestionType.ANOMALY_LOOKUP:
            return self._anomalies(plan, rows, query_fingerprint)
        prepared = [(row, _values(row)) for row in rows]
        if plan.question_type is QuestionType.RANK_CAMPAIGNS:
            metric = plan.metrics[0].value
            reverse = plan.sort_direction is SortDirection.DESC
            valid = [item for item in prepared if item[1].get(metric) is not None]
            nulls = [item for item in prepared if item[1].get(metric) is None]

            def tie_breaker(
                item: tuple[dict[str, Any], dict[str, int | float | None]],
            ) -> tuple[str, str]:
                return (
                    str(item[0].get("name") or ""),
                    str(item[0].get("campaign_id") or ""),
                )

            valid.sort(key=tie_breaker)
            valid.sort(key=lambda item: item[1][metric], reverse=reverse)
            nulls.sort(key=tie_breaker)
            prepared = [*valid, *nulls][: plan.limit]
        facts: list[AnalystFact] = []
        evidence: list[AnalystEvidence] = []
        for index, (row, values) in enumerate(prepared, start=1):
            evidence_id = f"evidence-{index}"
            campaign_id = row.get("campaign_id") or plan.campaign_id
            row_start, row_end = self._evidence_dates(plan, row)
            evidence.append(
                AnalystEvidence(
                    id=evidence_id,
                    dataset_run_id=plan.dataset_run_id,
                    campaign_id=campaign_id,
                    start_date=row_start,
                    end_date=row_end,
                    metrics=plan.metrics,
                    query_fingerprint=query_fingerprint,
                    row_count=1,
                    source_row_count=int(row.get("source_row_count", 1)),
                    values=values,
                )
            )
            prefix = self._label_prefix(row)
            for metric in plan.metrics:
                facts.append(
                    AnalystFact(
                        id=f"fact-{len(facts) + 1}",
                        label=f"{prefix}{metric.value}",
                        value=values[metric.value],
                        unit=METRIC_UNITS[metric],
                        evidence_ids=[evidence_id],
                    )
                )
        notices = self._period_notices(plan, rows)
        return FactBuildResult(
            facts=facts,
            evidence=evidence,
            hypotheses=self._hypotheses(plan),
            recommendations=self._recommendations(plan),
            summary=self._summary(plan, len(facts)),
            data_notices=tuple(notices),
        )

    @staticmethod
    def _period_notices(plan: AnalysisPlan, rows: list[dict[str, Any]]) -> list[str]:
        if plan.question_type is not QuestionType.PERIOD_COMPARISON:
            return []
        present = {str(row.get("period_label")) for row in rows}
        missing = [label for label in ("current", "comparison") if label not in present]
        return [f"{label} 기간에는 원본 metric 행이 없습니다." for label in missing]

    @staticmethod
    def _label_prefix(row: dict[str, Any]) -> str:
        parts = []
        if row.get("name"):
            parts.append(str(row["name"]))
        if row.get("date"):
            parts.append(str(row["date"]))
        if row.get("period_label"):
            parts.append(str(row["period_label"]))
        return " · ".join(parts) + (" · " if parts else "")

    @staticmethod
    def _evidence_dates(plan: AnalysisPlan, row: dict[str, Any]) -> tuple[date, date]:
        if row.get("date"):
            row_date = row["date"]
            return row_date, row_date
        if row.get("period_label") == "comparison":
            assert plan.comparison_start_date is not None
            assert plan.comparison_end_date is not None
            return plan.comparison_start_date, plan.comparison_end_date
        return plan.start_date, plan.end_date

    @staticmethod
    def _hypotheses(plan: AnalysisPlan) -> list[AnalystHypothesis]:
        if plan.question_type not in {
            QuestionType.PERIOD_COMPARISON,
            QuestionType.ANOMALY_LOOKUP,
        }:
            return []
        return [
            AnalystHypothesis(
                text=(
                    "관측된 변화의 원인은 현재 합성 성과 데이터만으로 확정할 수 없습니다. "
                    "소재·타게팅·외부 환경은 별도 근거 확인이 필요합니다."
                )
            )
        ]

    @staticmethod
    def _recommendations(plan: AnalysisPlan) -> list[AnalystRecommendation]:
        if plan.question_type not in {
            QuestionType.PERIOD_COMPARISON,
            QuestionType.ANOMALY_LOOKUP,
        }:
            return []
        return [
            AnalystRecommendation(
                text=(
                    "근거 기간과 Campaign 설정을 사람이 검토하세요. "
                    "예산·타게팅 변경은 자동 실행되지 않습니다."
                )
            )
        ]

    @staticmethod
    def _summary(plan: AnalysisPlan, fact_count: int) -> str:
        return (
            f"합성 dataset의 {plan.start_date}~{plan.end_date} 범위에서 "
            f"{plan.question_type.value} 사실 {fact_count}건을 계산했습니다."
        )

    def _anomalies(
        self,
        plan: AnalysisPlan,
        rows: list[dict[str, Any]],
        query_fingerprint: str,
    ) -> FactBuildResult:
        if not any(plan.start_date <= row["date"] <= plan.end_date for row in rows):
            return FactBuildResult(
                facts=[],
                evidence=[],
                hypotheses=[],
                recommendations=[],
                summary=(
                    f"합성 dataset의 {plan.start_date}~{plan.end_date} 범위에 "
                    "원본 metric 행이 없습니다."
                ),
                no_data=True,
            )
        metrics = [
            MetricValue(
                dataset_run_id=plan.dataset_run_id,
                campaign_id=row["campaign_id"],
                date=row["date"],
                impressions=int(row["impressions"]),
                clicks=int(row["clicks"]),
                conversions=int(row["conversions"]),
                spend_krw=int(row["spend_krw"]),
                revenue_krw=int(row["revenue_krw"]),
            )
            for row in rows
        ]
        names = {row["campaign_id"]: row["name"] for row in rows}
        detections = [
            item
            for item in detect_anomalies(metrics)
            if plan.start_date <= item.date <= plan.end_date
        ]
        facts: list[AnalystFact] = []
        evidence: list[AnalystEvidence] = []
        for index, detection in enumerate(detections, start=1):
            evidence_id = f"evidence-{index}"
            values = {
                "anomaly_type": detection.anomaly_type.value,
                "observed_value": float(detection.observed_value),
                "baseline_value": float(detection.baseline_value),
                "change_ratio": float(detection.change_ratio),
                "threshold": float(detection.threshold),
            }
            evidence.append(
                AnalystEvidence(
                    id=evidence_id,
                    dataset_run_id=plan.dataset_run_id,
                    campaign_id=detection.campaign_id,
                    start_date=detection.date,
                    end_date=detection.date,
                    metrics=plan.metrics,
                    query_fingerprint=query_fingerprint,
                    row_count=1,
                    source_row_count=int(
                        next(
                            row.get("source_row_count", 1)
                            for row in rows
                            if row["campaign_id"] == detection.campaign_id
                            and row["date"] == detection.date
                        )
                    ),
                    values=values,
                )
            )
            facts.append(
                AnalystFact(
                    id=f"fact-{index}",
                    label=(
                        f"{names.get(detection.campaign_id, 'Unknown campaign')} · "
                        f"{detection.date} · {detection.anomaly_type.value}"
                    ),
                    value=float(detection.observed_value),
                    unit="observed_value",
                    evidence_ids=[evidence_id],
                )
            )
        return FactBuildResult(
            facts=facts,
            evidence=evidence,
            hypotheses=self._hypotheses(plan),
            recommendations=self._recommendations(plan),
            summary=(
                "truth label을 조회하지 않고 raw metric에서 "
                f"anomaly 사실 {len(facts)}건을 계산했습니다."
            ),
        )
