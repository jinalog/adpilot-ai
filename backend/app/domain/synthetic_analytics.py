import json
import random
import uuid
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.domain.analytics import AnomalyType

DEFAULT_SEED = 20261107
DEFAULT_START_DATE = date(2026, 9, 1)
DEFAULT_DAYS = 70
DEFAULT_CAMPAIGN_COUNT = 6
SCHEMA_VERSION = "analytics-v1"
DATASET_NAMESPACE = uuid.UUID("1adcc695-68d6-4bd7-a6a0-acde0603fc86")


@dataclass(frozen=True, slots=True)
class SyntheticDatasetConfig:
    name: str = "phase3-default"
    seed: int = DEFAULT_SEED
    start_date: date = DEFAULT_START_DATE
    days: int = DEFAULT_DAYS
    campaign_count: int = DEFAULT_CAMPAIGN_COUNT
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("dataset name must not be blank")
        if self.days < 60:
            raise ValueError("synthetic analytics datasets require at least 60 days")
        if self.campaign_count < 6:
            raise ValueError("synthetic analytics datasets require at least 6 campaigns")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "start_date": self.start_date.isoformat(),
            "days": self.days,
            "campaign_count": self.campaign_count,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class SyntheticCampaign:
    id: uuid.UUID
    name: str
    objective: str
    total_budget_krw: int
    daily_budget_krw: int
    start_date: date
    end_date: date
    channels: list[str]
    targeting: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SyntheticMetric:
    id: uuid.UUID
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID
    date: date
    impressions: int
    clicks: int
    conversions: int
    spend_krw: int
    revenue_krw: int


@dataclass(frozen=True, slots=True)
class SyntheticTruth:
    id: uuid.UUID
    dataset_run_id: uuid.UUID
    campaign_id: uuid.UUID
    date: date
    anomaly_type: AnomalyType
    baseline_metadata: dict[str, Any]
    injection_strength: Decimal
    description: str


@dataclass(frozen=True, slots=True)
class SyntheticDatasetPlan:
    id: uuid.UUID
    config: SyntheticDatasetConfig
    end_date: date
    campaigns: list[SyntheticCampaign]
    metrics: list[SyntheticMetric]
    truth_labels: list[SyntheticTruth]


def build_synthetic_dataset(config: SyntheticDatasetConfig) -> SyntheticDatasetPlan:
    config.validate()
    canonical = json.dumps(config.as_dict(), sort_keys=True, separators=(",", ":"))
    run_id = uuid.uuid5(DATASET_NAMESPACE, canonical)
    end_date = config.start_date + timedelta(days=config.days - 1)
    generator = random.Random(config.seed)
    campaigns = [
        _campaign(run_id, config, end_date, index) for index in range(config.campaign_count)
    ]
    metrics: list[SyntheticMetric] = []
    for campaign_index, campaign in enumerate(campaigns):
        for day_index in range(config.days):
            metric_date = config.start_date + timedelta(days=day_index)
            metrics.append(
                _normal_metric(
                    generator,
                    run_id,
                    campaign,
                    campaign_index,
                    metric_date,
                )
            )

    truth_labels: list[SyntheticTruth] = []
    injection_specs = (
        (0, 21, AnomalyType.CTR_DROP, Decimal("0.30")),
        (1, 30, AnomalyType.CVR_DROP, Decimal("0.20")),
        (2, 39, AnomalyType.SPEND_SPIKE, Decimal("2.20")),
        (3, 48, AnomalyType.IMPRESSION_DROP, Decimal("0.35")),
    )
    metric_positions = {
        (item.campaign_id, item.date): position for position, item in enumerate(metrics)
    }
    for campaign_index, day_index, anomaly_type, strength in injection_specs:
        campaign = campaigns[campaign_index]
        metric_date = config.start_date + timedelta(days=day_index)
        position = metric_positions[(campaign.id, metric_date)]
        original = metrics[position]
        injected = _inject(original, anomaly_type, strength)
        metrics[position] = injected
        truth_labels.append(
            SyntheticTruth(
                id=uuid.uuid5(run_id, f"truth:{campaign.id}:{metric_date}:{anomaly_type.value}"),
                dataset_run_id=run_id,
                campaign_id=campaign.id,
                date=metric_date,
                anomaly_type=anomaly_type,
                baseline_metadata={
                    "pre_injection": {
                        "impressions": original.impressions,
                        "clicks": original.clicks,
                        "conversions": original.conversions,
                        "spend_krw": original.spend_krw,
                        "revenue_krw": original.revenue_krw,
                    }
                },
                injection_strength=strength,
                description=f"Deterministic {anomaly_type.value} injection",
            )
        )
    return SyntheticDatasetPlan(
        id=run_id,
        config=config,
        end_date=end_date,
        campaigns=campaigns,
        metrics=metrics,
        truth_labels=truth_labels,
    )


def _campaign(
    run_id: uuid.UUID,
    config: SyntheticDatasetConfig,
    end_date: date,
    index: int,
) -> SyntheticCampaign:
    campaign_id = uuid.uuid5(run_id, f"campaign:{index}")
    channels = [["search"], ["mobile"], ["display"], ["social"], ["search", "mobile"]][index % 5]
    return SyntheticCampaign(
        id=campaign_id,
        name=f"{config.name} · Synthetic Campaign {index + 1}",
        objective="Synthetic conversion performance evaluation",
        total_budget_krw=100_000_000,
        daily_budget_krw=2_000_000,
        start_date=config.start_date,
        end_date=end_date,
        channels=channels,
        targeting={"country": "KR", "audience_group": index + 1, "synthetic": True},
    )


def _normal_metric(
    generator: random.Random,
    run_id: uuid.UUID,
    campaign: SyntheticCampaign,
    campaign_index: int,
    metric_date: date,
) -> SyntheticMetric:
    impressions_base = 2_000 + campaign_index * 350
    impressions = impressions_base * (100 + generator.randint(-8, 8)) // 100
    ctr_basis_points = 450 + campaign_index * 30 + generator.randint(-18, 18)
    clicks = max(1, impressions * ctr_basis_points // 10_000)
    cvr_basis_points = 750 + campaign_index * 45 + generator.randint(-25, 25)
    conversions = max(1, clicks * cvr_basis_points // 10_000)
    cost_per_click = 850 + campaign_index * 90 + generator.randint(-30, 30)
    revenue_per_conversion = 28_000 + campaign_index * 4_000
    return SyntheticMetric(
        id=uuid.uuid5(run_id, f"metric:{campaign.id}:{metric_date}"),
        dataset_run_id=run_id,
        campaign_id=campaign.id,
        date=metric_date,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend_krw=clicks * cost_per_click,
        revenue_krw=conversions * revenue_per_conversion,
    )


def _inject(
    metric: SyntheticMetric,
    anomaly_type: AnomalyType,
    strength: Decimal,
) -> SyntheticMetric:
    if anomaly_type is AnomalyType.CTR_DROP:
        clicks = max(1, int(Decimal(metric.clicks) * strength))
        conversions = min(clicks, max(0, int(Decimal(metric.conversions) * strength)))
        return replace(
            metric,
            clicks=clicks,
            conversions=conversions,
            spend_krw=metric.spend_krw * clicks // metric.clicks,
            revenue_krw=(
                metric.revenue_krw * conversions // metric.conversions if metric.conversions else 0
            ),
        )
    if anomaly_type is AnomalyType.CVR_DROP:
        conversions = max(0, int(Decimal(metric.conversions) * strength))
        return replace(
            metric,
            conversions=conversions,
            revenue_krw=(
                metric.revenue_krw * conversions // metric.conversions if metric.conversions else 0
            ),
        )
    if anomaly_type is AnomalyType.SPEND_SPIKE:
        return replace(metric, spend_krw=int(Decimal(metric.spend_krw) * strength))
    impressions = max(1, int(Decimal(metric.impressions) * strength))
    clicks = min(impressions, max(1, metric.clicks * impressions // metric.impressions))
    conversions = min(clicks, metric.conversions * clicks // metric.clicks)
    return replace(
        metric,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend_krw=metric.spend_krw * clicks // metric.clicks,
        revenue_krw=(
            metric.revenue_krw * conversions // metric.conversions if metric.conversions else 0
        ),
    )
