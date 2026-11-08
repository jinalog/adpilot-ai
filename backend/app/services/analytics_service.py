import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from app.core.exceptions import BusinessRuleError, ConflictError, ResourceNotFoundError
from app.db.models.analytics import SyntheticDatasetRun
from app.domain.analytics import (
    KPIValues,
    MetricTotals,
    MetricValue,
    aggregate_metrics,
    calculate_kpis,
    detect_anomalies,
    round_money,
    round_rate,
)
from app.domain.synthetic_analytics import SyntheticDatasetPlan
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.schemas.analytics import (
    AnalyticsPointResponse,
    AnalyticsSummaryResponse,
    AnalyticsTimeseriesResponse,
    AnomalyDetectionListResponse,
    AnomalyDetectionResponse,
    CampaignPerformanceListResponse,
    CampaignPerformanceResponse,
    DatasetRunListResponse,
    DatasetRunResponse,
    KPIResponse,
    MetricTotalsResponse,
)

MAX_QUERY_DAYS = 366


class SyntheticDatasetService:
    def __init__(self, repository: AnalyticsRepository) -> None:
        self.repository = repository

    def create(
        self,
        plan: SyntheticDatasetPlan,
        *,
        replace_dataset_id: uuid.UUID | None = None,
    ) -> DatasetRunResponse:
        existing = self.repository.get_dataset_by_name(plan.config.name)
        if existing is not None and replace_dataset_id != existing.id:
            raise ConflictError(
                "dataset name already exists; provide its exact ID with --replace-dataset-id"
            )
        if existing is None and replace_dataset_id is not None:
            raise ConflictError("replace dataset ID does not match an existing dataset name")
        try:
            if existing is not None:
                self.repository.delete_owned_dataset(existing.id)
            self.repository.add_plan(plan)
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise
        saved = self.repository.get_dataset(plan.id)
        assert saved is not None
        return DatasetRunResponse.model_validate(saved)


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository) -> None:
        self.repository = repository

    def list_datasets(self) -> DatasetRunListResponse:
        return DatasetRunListResponse(
            items=[
                DatasetRunResponse.model_validate(item) for item in self.repository.list_datasets()
            ]
        )

    def summary(
        self,
        dataset_run_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None,
        start_date: date | None,
        end_date: date | None,
    ) -> AnalyticsSummaryResponse:
        start, end = self._scope(dataset_run_id, campaign_id, start_date, end_date)
        metrics = self.repository.list_metrics(
            dataset_run_id=dataset_run_id,
            campaign_id=campaign_id,
            start_date=start,
            end_date=end,
        )
        totals = aggregate_metrics(metrics)
        return AnalyticsSummaryResponse(
            dataset_run_id=dataset_run_id,
            campaign_id=campaign_id,
            start_date=start,
            end_date=end,
            totals=_totals_response(totals),
            kpis=_kpi_response(calculate_kpis(totals)),
        )

    def timeseries(
        self,
        dataset_run_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None,
        start_date: date | None,
        end_date: date | None,
    ) -> AnalyticsTimeseriesResponse:
        start, end = self._scope(dataset_run_id, campaign_id, start_date, end_date)
        metrics = self.repository.list_metrics(
            dataset_run_id=dataset_run_id,
            campaign_id=campaign_id,
            start_date=start,
            end_date=end,
        )
        grouped: dict[date, list[MetricValue]] = defaultdict(list)
        for metric in metrics:
            grouped[metric.date].append(metric)
        items = []
        for metric_date in sorted(grouped):
            totals = aggregate_metrics(grouped[metric_date])
            items.append(
                AnalyticsPointResponse(
                    date=metric_date,
                    totals=_totals_response(totals),
                    kpis=_kpi_response(calculate_kpis(totals)),
                )
            )
        return AnalyticsTimeseriesResponse(
            dataset_run_id=dataset_run_id,
            campaign_id=campaign_id,
            start_date=start,
            end_date=end,
            items=items,
        )

    def campaigns(
        self,
        dataset_run_id: uuid.UUID,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> CampaignPerformanceListResponse:
        start, end = self._scope(dataset_run_id, None, start_date, end_date)
        metrics = self.repository.list_metrics(
            dataset_run_id=dataset_run_id,
            campaign_id=None,
            start_date=start,
            end_date=end,
        )
        grouped: dict[uuid.UUID, list[MetricValue]] = defaultdict(list)
        for metric in metrics:
            grouped[metric.campaign_id].append(metric)
        names = self.repository.campaign_names(dataset_run_id)
        items = []
        for campaign_id, name in sorted(names.items(), key=lambda item: (item[1], item[0])):
            totals = aggregate_metrics(grouped.get(campaign_id, []))
            items.append(
                CampaignPerformanceResponse(
                    campaign_id=campaign_id,
                    campaign_name=name,
                    totals=_totals_response(totals),
                    kpis=_kpi_response(calculate_kpis(totals)),
                )
            )
        return CampaignPerformanceListResponse(
            dataset_run_id=dataset_run_id,
            start_date=start,
            end_date=end,
            items=items,
        )

    def anomalies(
        self,
        dataset_run_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None,
        start_date: date | None,
        end_date: date | None,
    ) -> AnomalyDetectionListResponse:
        start, end = self._scope(dataset_run_id, campaign_id, start_date, end_date)
        metrics = self.repository.list_metrics(
            dataset_run_id=dataset_run_id,
            campaign_id=campaign_id,
            start_date=max(start - timedelta(days=7), self._dataset(dataset_run_id).start_date),
            end_date=end,
        )
        names = self.repository.campaign_names(dataset_run_id)
        detections = [item for item in detect_anomalies(metrics) if start <= item.date <= end]
        return AnomalyDetectionListResponse(
            dataset_run_id=dataset_run_id,
            start_date=start,
            end_date=end,
            items=[
                AnomalyDetectionResponse(
                    campaign_id=item.campaign_id,
                    campaign_name=names.get(item.campaign_id, "Unknown campaign"),
                    date=item.date,
                    anomaly_type=item.anomaly_type,
                    observed_value=float(item.observed_value),
                    baseline_value=float(item.baseline_value),
                    change_ratio=float(item.change_ratio),
                    threshold=float(item.threshold),
                    detector_version=item.detector_version,
                )
                for item in detections
            ],
        )

    def _scope(
        self,
        dataset_run_id: uuid.UUID,
        campaign_id: uuid.UUID | None,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[date, date]:
        dataset = self._dataset(dataset_run_id)
        if (
            campaign_id is not None
            and self.repository.get_owned_campaign(dataset_run_id, campaign_id) is None
        ):
            raise ResourceNotFoundError(
                f"campaign {campaign_id} was not found in dataset {dataset_run_id}"
            )
        start = start_date or dataset.start_date
        end = end_date or dataset.end_date
        if start > end:
            raise BusinessRuleError("start_date cannot be later than end_date")
        if (end - start).days + 1 > MAX_QUERY_DAYS:
            raise BusinessRuleError(f"analytics queries are limited to {MAX_QUERY_DAYS} days")
        return start, end

    def _dataset(self, dataset_run_id: uuid.UUID) -> SyntheticDatasetRun:
        dataset = self.repository.get_dataset(dataset_run_id)
        if dataset is None:
            raise ResourceNotFoundError(f"dataset {dataset_run_id} was not found")
        return dataset


def _totals_response(totals: MetricTotals) -> MetricTotalsResponse:
    return MetricTotalsResponse(
        impressions=totals.impressions,
        clicks=totals.clicks,
        conversions=totals.conversions,
        spend_krw=totals.spend_krw,
        revenue_krw=totals.revenue_krw,
    )


def _kpi_response(kpis: KPIValues) -> KPIResponse:
    return KPIResponse(
        ctr=_as_float(round_rate(kpis.ctr)),
        cvr=_as_float(round_rate(kpis.cvr)),
        cpm_krw=_as_float(round_money(kpis.cpm_krw)),
        cpc_krw=_as_float(round_money(kpis.cpc_krw)),
        cpa_krw=_as_float(round_money(kpis.cpa_krw)),
        roas=_as_float(round_rate(kpis.roas)),
    )


def _as_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
