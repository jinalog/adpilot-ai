import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyntheticDatasetRun(Base):
    __tablename__ = "synthetic_dataset_runs"
    __table_args__ = (
        CheckConstraint("days > 0", name="ck_synthetic_dataset_runs_days_positive"),
        CheckConstraint("end_date >= start_date", name="ck_synthetic_dataset_runs_date_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DailyAdMetric(Base):
    __tablename__ = "daily_ad_metrics"
    __table_args__ = (
        CheckConstraint("impressions >= 0", name="ck_daily_ad_metrics_impressions_nonnegative"),
        CheckConstraint("clicks >= 0", name="ck_daily_ad_metrics_clicks_nonnegative"),
        CheckConstraint("conversions >= 0", name="ck_daily_ad_metrics_conversions_nonnegative"),
        CheckConstraint("spend_krw >= 0", name="ck_daily_ad_metrics_spend_nonnegative"),
        CheckConstraint("revenue_krw >= 0", name="ck_daily_ad_metrics_revenue_nonnegative"),
        CheckConstraint("clicks <= impressions", name="ck_daily_ad_metrics_clicks_lte_impressions"),
        CheckConstraint("conversions <= clicks", name="ck_daily_ad_metrics_conversions_lte_clicks"),
        UniqueConstraint(
            "dataset_run_id",
            "campaign_id",
            "date",
            name="uq_daily_ad_metrics_run_campaign_date",
        ),
        Index("ix_daily_ad_metrics_run_date", "dataset_run_id", "date"),
        Index("ix_daily_ad_metrics_campaign_date", "campaign_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    dataset_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("synthetic_dataset_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spend_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revenue_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnomalyTruthLabel(Base):
    __tablename__ = "anomaly_truth_labels"
    __table_args__ = (
        CheckConstraint(
            "anomaly_type IN ('CTR_DROP', 'CVR_DROP', 'SPEND_SPIKE', 'IMPRESSION_DROP')",
            name="ck_anomaly_truth_labels_type",
        ),
        UniqueConstraint(
            "dataset_run_id",
            "campaign_id",
            "date",
            "anomaly_type",
            name="uq_anomaly_truth_run_campaign_date_type",
        ),
        Index("ix_anomaly_truth_run_date", "dataset_run_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    dataset_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("synthetic_dataset_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(30), nullable=False)
    baseline_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    injection_strength: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
