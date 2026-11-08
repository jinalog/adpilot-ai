import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalystStatus(StrEnum):
    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TOOL_ERROR = "TOOL_ERROR"


class QuestionType(StrEnum):
    KPI_SUMMARY = "KPI_SUMMARY"
    CAMPAIGN_COMPARISON = "CAMPAIGN_COMPARISON"
    RANK_CAMPAIGNS = "RANK_CAMPAIGNS"
    PERIOD_COMPARISON = "PERIOD_COMPARISON"
    DAILY_TREND = "DAILY_TREND"
    ANOMALY_LOOKUP = "ANOMALY_LOOKUP"


class AnalysisMetric(StrEnum):
    IMPRESSIONS = "impressions"
    CLICKS = "clicks"
    CONVERSIONS = "conversions"
    SPEND_KRW = "spend_krw"
    REVENUE_KRW = "revenue_krw"
    CTR = "ctr"
    CVR = "cvr"
    CPM_KRW = "cpm_krw"
    CPC_KRW = "cpc_krw"
    CPA_KRW = "cpa_krw"
    ROAS = "roas"


class GroupingUnit(StrEnum):
    OVERALL = "overall"
    CAMPAIGN = "campaign"
    DAY = "day"
    PERIOD = "period"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: QuestionType
    dataset_run_id: uuid.UUID
    metrics: list[AnalysisMetric] = Field(min_length=1)
    campaign_id: uuid.UUID | None = None
    start_date: date
    end_date: date
    grouping: GroupingUnit
    comparison_start_date: date | None = None
    comparison_end_date: date | None = None
    sort_direction: SortDirection | None = None
    limit: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_ranges(self) -> "AnalysisPlan":
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be later than end_date")
        if (self.end_date - self.start_date).days + 1 > 366:
            raise ValueError("analysis date range cannot exceed 366 days")
        comparison_values = (self.comparison_start_date, self.comparison_end_date)
        if self.question_type is QuestionType.PERIOD_COMPARISON:
            if any(value is None for value in comparison_values):
                raise ValueError("period comparison requires a comparison date range")
            assert self.comparison_start_date is not None
            assert self.comparison_end_date is not None
            if self.comparison_start_date > self.comparison_end_date:
                raise ValueError("comparison_start_date cannot be later than comparison_end_date")
            if (self.comparison_end_date - self.comparison_start_date).days + 1 > 366:
                raise ValueError("comparison date range cannot exceed 366 days")
        elif any(value is not None for value in comparison_values):
            raise ValueError("comparison dates are only allowed for period comparison")
        if self.question_type is QuestionType.RANK_CAMPAIGNS and self.sort_direction is None:
            raise ValueError("campaign ranking requires sort_direction")
        return self


class AnalystQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_run_id: uuid.UUID
    question: str = Field(min_length=1, max_length=1_000)
    campaign_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    comparison_start_date: date | None = None
    comparison_end_date: date | None = None

    @field_validator("question")
    @classmethod
    def question_must_have_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must contain non-whitespace text")
        return stripped


class AnalystFact(BaseModel):
    id: str
    label: str
    value: int | float | str | None
    unit: str
    evidence_ids: list[str] = Field(min_length=1)


class AnalystHypothesis(BaseModel):
    text: str
    requires_confirmation: bool = True


class AnalystRecommendation(BaseModel):
    text: str
    auto_applied: bool = False


class AnalystEvidence(BaseModel):
    id: str
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID | None = None
    start_date: date
    end_date: date
    metrics: list[AnalysisMetric]
    query_fingerprint: str
    row_count: int
    values: dict[str, Any]


class AnalystUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class AnalystResponse(BaseModel):
    status: AnalystStatus
    request_id: uuid.UUID
    provider_mode: str
    provider_model: str
    plan: AnalysisPlan | None = None
    answer_summary: str | None = None
    facts: list[AnalystFact] = Field(default_factory=list)
    hypotheses: list[AnalystHypothesis] = Field(default_factory=list)
    recommendations: list[AnalystRecommendation] = Field(default_factory=list)
    evidence: list[AnalystEvidence] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    error_code: str | None = None
    failed_step: str | None = None
    retry_count: int = 0
    latency_ms: int = 0
    usage: AnalystUsage = Field(default_factory=AnalystUsage)
    truncated: bool = False
