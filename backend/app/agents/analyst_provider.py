import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.agents.providers import ProviderError, ProviderSchemaError
from app.schemas.analyst import (
    AnalysisMetric,
    AnalysisPlan,
    GroupingUnit,
    QuestionType,
    SortDirection,
)

ALL_METRICS = list(AnalysisMetric)
METRIC_TERMS = {
    AnalysisMetric.IMPRESSIONS: ("impressions", "impression", "노출"),
    AnalysisMetric.CLICKS: ("clicks", "click", "클릭"),
    AnalysisMetric.CONVERSIONS: ("conversions", "conversion", "전환"),
    AnalysisMetric.SPEND_KRW: ("spend", "cost", "광고비", "비용", "지출"),
    AnalysisMetric.REVENUE_KRW: ("revenue", "매출"),
    AnalysisMetric.CTR: ("ctr", "클릭률"),
    AnalysisMetric.CVR: ("cvr", "전환율"),
    AnalysisMetric.CPM_KRW: ("cpm",),
    AnalysisMetric.CPC_KRW: ("cpc",),
    AnalysisMetric.CPA_KRW: ("cpa",),
    AnalysisMetric.ROAS: ("roas", "광고수익률"),
}


@dataclass(frozen=True, slots=True)
class AnalystPlanContext:
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID | None
    start_date: date
    end_date: date
    comparison_start_date: date | None = None
    comparison_end_date: date | None = None


@dataclass(frozen=True, slots=True)
class AnalystPlanResult:
    plan: AnalysisPlan | None
    clarification_questions: list[str]
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AnalystPlanningProvider(Protocol):
    mode: str
    model: str

    def plan(
        self, question: str, context: AnalystPlanContext, *, timeout_seconds: float
    ) -> AnalystPlanResult: ...


class MockAnalystProvider:
    """Deterministic question planner; it does not generate or execute SQL."""

    mode = "mock"
    model = "deterministic-analyst-plan-v1"

    def plan(
        self, question: str, context: AnalystPlanContext, *, timeout_seconds: float
    ) -> AnalystPlanResult:
        del timeout_seconds
        normalized = question.strip().lower()
        question_type = self._question_type(normalized)
        metrics = self._metrics(normalized)
        clarification: list[str] = []
        if question_type is QuestionType.RANK_CAMPAIGNS:
            if not metrics:
                clarification.append("순위를 계산할 KPI(예: CTR 또는 ROAS)를 지정해 주세요.")
            elif len(metrics) != 1:
                clarification.append("순위 기준 KPI를 정확히 하나만 지정해 주세요.")
            if context.campaign_id is not None:
                clarification.append(
                    "Campaign 순위는 전체 Campaign context에서만 조회할 수 있습니다."
                )
        if (
            question_type in {QuestionType.DAILY_TREND, QuestionType.PERIOD_COMPARISON}
            and not metrics
        ):
            clarification.append("분석할 metric(예: CTR, ROAS 또는 spend)을 지정해 주세요.")
        if question_type is QuestionType.PERIOD_COMPARISON and (
            context.comparison_start_date is None or context.comparison_end_date is None
        ):
            clarification.append("비교할 시작일과 종료일을 지정해 주세요.")
        if clarification:
            return AnalystPlanResult(
                plan=None,
                clarification_questions=clarification,
                provider=self.mode,
                model=self.model,
            )
        if not metrics:
            metrics = self._default_metrics(question_type)
        direction = None
        if question_type is QuestionType.RANK_CAMPAIGNS:
            direction = (
                SortDirection.ASC
                if any(term in normalized for term in ("하위", "낮", "bottom", "worst"))
                else SortDirection.DESC
            )
        limit = self._limit(normalized, question_type)
        plan = AnalysisPlan(
            question_type=question_type,
            dataset_run_id=context.dataset_run_id,
            metrics=metrics,
            campaign_id=context.campaign_id,
            start_date=context.start_date,
            end_date=context.end_date,
            grouping=self._grouping(question_type),
            comparison_start_date=(
                context.comparison_start_date
                if question_type is QuestionType.PERIOD_COMPARISON
                else None
            ),
            comparison_end_date=(
                context.comparison_end_date
                if question_type is QuestionType.PERIOD_COMPARISON
                else None
            ),
            sort_direction=direction,
            limit=limit,
        )
        return AnalystPlanResult(
            plan=plan,
            clarification_questions=[],
            provider=self.mode,
            model=self.model,
        )

    @staticmethod
    def _question_type(question: str) -> QuestionType:
        if any(term in question for term in ("anomaly", "이상", "급락", "급증")):
            return QuestionType.ANOMALY_LOOKUP
        if any(term in question for term in ("추세", "trend", "일별", "daily")):
            return QuestionType.DAILY_TREND
        if any(term in question for term in ("두 기간", "기간 비교", "전 기간", "previous period")):
            return QuestionType.PERIOD_COMPARISON
        if any(term in question for term in ("상위", "하위", "top", "bottom", "best", "worst")):
            return QuestionType.RANK_CAMPAIGNS
        if any(term in question for term in ("campaign 비교", "캠페인 비교", "campaigns compare")):
            return QuestionType.CAMPAIGN_COMPARISON
        return QuestionType.KPI_SUMMARY

    @staticmethod
    def _metrics(question: str) -> list[AnalysisMetric]:
        return [
            metric
            for metric, terms in METRIC_TERMS.items()
            if any(term in question for term in terms)
        ]

    @staticmethod
    def _default_metrics(question_type: QuestionType) -> list[AnalysisMetric]:
        if question_type is QuestionType.ANOMALY_LOOKUP:
            return [
                AnalysisMetric.IMPRESSIONS,
                AnalysisMetric.CLICKS,
                AnalysisMetric.CONVERSIONS,
                AnalysisMetric.SPEND_KRW,
                AnalysisMetric.CTR,
                AnalysisMetric.CVR,
            ]
        return ALL_METRICS

    @staticmethod
    def _grouping(question_type: QuestionType) -> GroupingUnit:
        return {
            QuestionType.KPI_SUMMARY: GroupingUnit.OVERALL,
            QuestionType.CAMPAIGN_COMPARISON: GroupingUnit.CAMPAIGN,
            QuestionType.RANK_CAMPAIGNS: GroupingUnit.CAMPAIGN,
            QuestionType.PERIOD_COMPARISON: GroupingUnit.PERIOD,
            QuestionType.DAILY_TREND: GroupingUnit.DAY,
            QuestionType.ANOMALY_LOOKUP: GroupingUnit.DAY,
        }[question_type]

    @staticmethod
    def _limit(question: str, question_type: QuestionType) -> int:
        if question_type is QuestionType.ANOMALY_LOOKUP:
            return 500
        match = re.search(r"(?:상위|하위|top|bottom)\s*(\d{1,3})", question)
        if match:
            return min(max(int(match.group(1)), 1), 100)
        return 100


def build_analyst_provider(provider_name: str) -> AnalystPlanningProvider:
    if provider_name == "mock":
        return MockAnalystProvider()
    raise ProviderError("unsupported Analyst provider; real LLM calls require explicit integration")


__all__ = [
    "AnalystPlanContext",
    "AnalystPlanResult",
    "AnalystPlanningProvider",
    "MockAnalystProvider",
    "ProviderSchemaError",
    "build_analyst_provider",
]
