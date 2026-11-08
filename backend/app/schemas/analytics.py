import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.domain.analytics import AnomalyType


class MetricTotalsResponse(BaseModel):
    impressions: int
    clicks: int
    conversions: int
    spend_krw: int
    revenue_krw: int


class KPIResponse(BaseModel):
    ctr: float | None
    cvr: float | None
    cpm_krw: float | None
    cpc_krw: float | None
    cpa_krw: float | None
    roas: float | None


class AnalyticsSummaryResponse(BaseModel):
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID | None
    start_date: date
    end_date: date
    totals: MetricTotalsResponse
    kpis: KPIResponse


class AnalyticsPointResponse(BaseModel):
    date: date
    totals: MetricTotalsResponse
    kpis: KPIResponse


class AnalyticsTimeseriesResponse(BaseModel):
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID | None
    start_date: date
    end_date: date
    items: list[AnalyticsPointResponse]


class CampaignPerformanceResponse(BaseModel):
    campaign_id: uuid.UUID
    campaign_name: str
    totals: MetricTotalsResponse
    kpis: KPIResponse


class CampaignPerformanceListResponse(BaseModel):
    dataset_run_id: uuid.UUID
    start_date: date
    end_date: date
    items: list[CampaignPerformanceResponse]


class AnomalyDetectionResponse(BaseModel):
    campaign_id: uuid.UUID
    campaign_name: str
    date: date
    anomaly_type: AnomalyType
    observed_value: float
    baseline_value: float
    change_ratio: float
    threshold: float
    detector_version: str


class AnomalyDetectionListResponse(BaseModel):
    dataset_run_id: uuid.UUID
    start_date: date
    end_date: date
    items: list[AnomalyDetectionResponse]


class DatasetRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    seed: int
    schema_version: str
    start_date: date
    end_date: date
    days: int
    generation_config: dict[str, object]
    created_at: datetime


class DatasetRunListResponse(BaseModel):
    items: list[DatasetRunResponse]
