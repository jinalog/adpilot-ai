import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.analytics import AnomalyTruthLabel, DailyAdMetric, SyntheticDatasetRun
from app.db.models.campaign import Campaign
from app.domain.analytics import MetricValue
from app.domain.synthetic_analytics import SyntheticDatasetPlan


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_dataset(self, dataset_run_id: uuid.UUID) -> SyntheticDatasetRun | None:
        return self.session.get(SyntheticDatasetRun, dataset_run_id)

    def get_dataset_by_name(self, name: str) -> SyntheticDatasetRun | None:
        return self.session.scalar(
            select(SyntheticDatasetRun).where(SyntheticDatasetRun.name == name)
        )

    def list_datasets(self) -> list[SyntheticDatasetRun]:
        return list(
            self.session.scalars(
                select(SyntheticDatasetRun).order_by(
                    SyntheticDatasetRun.created_at.desc(), SyntheticDatasetRun.id
                )
            )
        )

    def get_owned_campaign(
        self, dataset_run_id: uuid.UUID, campaign_id: uuid.UUID
    ) -> Campaign | None:
        return self.session.scalar(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.synthetic_dataset_run_id == dataset_run_id,
            )
        )

    def campaign_names(self, dataset_run_id: uuid.UUID) -> dict[uuid.UUID, str]:
        rows = self.session.execute(
            select(Campaign.id, Campaign.name)
            .where(Campaign.synthetic_dataset_run_id == dataset_run_id)
            .order_by(Campaign.name, Campaign.id)
        )
        return {campaign_id: name for campaign_id, name in rows}

    def list_metrics(
        self,
        *,
        dataset_run_id: uuid.UUID,
        start_date: date,
        end_date: date,
        campaign_id: uuid.UUID | None = None,
    ) -> list[MetricValue]:
        filters = [
            DailyAdMetric.dataset_run_id == dataset_run_id,
            DailyAdMetric.date >= start_date,
            DailyAdMetric.date <= end_date,
        ]
        if campaign_id is not None:
            filters.append(DailyAdMetric.campaign_id == campaign_id)
        rows = self.session.scalars(
            select(DailyAdMetric)
            .where(*filters)
            .order_by(DailyAdMetric.date, DailyAdMetric.campaign_id)
        )
        return [
            MetricValue(
                dataset_run_id=row.dataset_run_id,
                campaign_id=row.campaign_id,
                date=row.date,
                impressions=row.impressions,
                clicks=row.clicks,
                conversions=row.conversions,
                spend_krw=row.spend_krw,
                revenue_krw=row.revenue_krw,
            )
            for row in rows
        ]

    def list_truth_labels(self, dataset_run_id: uuid.UUID) -> list[AnomalyTruthLabel]:
        return list(
            self.session.scalars(
                select(AnomalyTruthLabel)
                .where(AnomalyTruthLabel.dataset_run_id == dataset_run_id)
                .order_by(
                    AnomalyTruthLabel.date,
                    AnomalyTruthLabel.campaign_id,
                    AnomalyTruthLabel.anomaly_type,
                )
            )
        )

    def add_plan(self, plan: SyntheticDatasetPlan) -> None:
        self.session.add(
            SyntheticDatasetRun(
                id=plan.id,
                name=plan.config.name,
                seed=plan.config.seed,
                schema_version=plan.config.schema_version,
                start_date=plan.config.start_date,
                end_date=plan.end_date,
                days=plan.config.days,
                generation_config=plan.config.as_dict(),
            )
        )
        self.session.flush()
        self.session.add_all(
            [
                Campaign(
                    id=campaign.id,
                    name=campaign.name,
                    objective=campaign.objective,
                    total_budget_krw=campaign.total_budget_krw,
                    daily_budget_krw=campaign.daily_budget_krw,
                    start_date=campaign.start_date,
                    end_date=campaign.end_date,
                    channels=campaign.channels,
                    targeting=campaign.targeting,
                    status="DRAFT",
                    synthetic_dataset_run_id=plan.id,
                )
                for campaign in plan.campaigns
            ]
        )
        self.session.flush()
        self.session.add_all(
            [
                DailyAdMetric(
                    id=metric.id,
                    dataset_run_id=metric.dataset_run_id,
                    campaign_id=metric.campaign_id,
                    date=metric.date,
                    impressions=metric.impressions,
                    clicks=metric.clicks,
                    conversions=metric.conversions,
                    spend_krw=metric.spend_krw,
                    revenue_krw=metric.revenue_krw,
                )
                for metric in plan.metrics
            ]
        )
        self.session.add_all(
            [
                AnomalyTruthLabel(
                    id=truth.id,
                    dataset_run_id=truth.dataset_run_id,
                    campaign_id=truth.campaign_id,
                    date=truth.date,
                    anomaly_type=truth.anomaly_type.value,
                    baseline_metadata=truth.baseline_metadata,
                    injection_strength=truth.injection_strength,
                    description=truth.description,
                )
                for truth in plan.truth_labels
            ]
        )
        self.session.flush()

    def delete_owned_dataset(self, dataset_run_id: uuid.UUID) -> None:
        self.session.execute(
            delete(AnomalyTruthLabel).where(AnomalyTruthLabel.dataset_run_id == dataset_run_id)
        )
        self.session.execute(
            delete(DailyAdMetric).where(DailyAdMetric.dataset_run_id == dataset_run_id)
        )
        self.session.execute(
            delete(Campaign).where(Campaign.synthetic_dataset_run_id == dataset_run_id)
        )
        self.session.execute(
            delete(SyntheticDatasetRun).where(SyntheticDatasetRun.id == dataset_run_id)
        )
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
