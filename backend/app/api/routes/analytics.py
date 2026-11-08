import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import AnalyticsServiceDependency
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    AnalyticsTimeseriesResponse,
    AnomalyDetectionListResponse,
    CampaignPerformanceListResponse,
    DatasetRunListResponse,
)

router = APIRouter(prefix="/analytics")


@router.get("/datasets", response_model=DatasetRunListResponse)
def list_datasets(service: AnalyticsServiceDependency) -> DatasetRunListResponse:
    return service.list_datasets()


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_summary(
    service: AnalyticsServiceDependency,
    dataset_run_id: Annotated[uuid.UUID, Query()],
    campaign_id: Annotated[uuid.UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AnalyticsSummaryResponse:
    return service.summary(
        dataset_run_id,
        campaign_id=campaign_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/timeseries", response_model=AnalyticsTimeseriesResponse)
def get_timeseries(
    service: AnalyticsServiceDependency,
    dataset_run_id: Annotated[uuid.UUID, Query()],
    campaign_id: Annotated[uuid.UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AnalyticsTimeseriesResponse:
    return service.timeseries(
        dataset_run_id,
        campaign_id=campaign_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/campaigns", response_model=CampaignPerformanceListResponse)
def get_campaigns(
    service: AnalyticsServiceDependency,
    dataset_run_id: Annotated[uuid.UUID, Query()],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> CampaignPerformanceListResponse:
    return service.campaigns(dataset_run_id, start_date=start_date, end_date=end_date)


@router.get("/anomalies", response_model=AnomalyDetectionListResponse)
def get_anomalies(
    service: AnalyticsServiceDependency,
    dataset_run_id: Annotated[uuid.UUID, Query()],
    campaign_id: Annotated[uuid.UUID | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AnomalyDetectionListResponse:
    return service.anomalies(
        dataset_run_id,
        campaign_id=campaign_id,
        start_date=start_date,
        end_date=end_date,
    )
