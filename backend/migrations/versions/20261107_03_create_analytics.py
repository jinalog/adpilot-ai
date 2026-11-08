"""Create synthetic analytics tables and ownership link.

Revision ID: 20261107_03
Revises: 20261107_02
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_03"
down_revision: str | None = "20261107_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthetic_dataset_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("generation_config", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("days > 0", name="ck_synthetic_dataset_runs_days_positive"),
        sa.CheckConstraint("end_date >= start_date", name="ck_synthetic_dataset_runs_date_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column("campaigns", sa.Column("synthetic_dataset_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_campaigns_synthetic_dataset_run_id",
        "campaigns",
        "synthetic_dataset_runs",
        ["synthetic_dataset_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_campaigns_synthetic_dataset_run_id",
        "campaigns",
        ["synthetic_dataset_run_id"],
        unique=False,
    )
    op.create_table(
        "daily_ad_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_run_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False),
        sa.Column("clicks", sa.BigInteger(), nullable=False),
        sa.Column("conversions", sa.BigInteger(), nullable=False),
        sa.Column("spend_krw", sa.BigInteger(), nullable=False),
        sa.Column("revenue_krw", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("impressions >= 0", name="ck_daily_ad_metrics_impressions_nonnegative"),
        sa.CheckConstraint("clicks >= 0", name="ck_daily_ad_metrics_clicks_nonnegative"),
        sa.CheckConstraint("conversions >= 0", name="ck_daily_ad_metrics_conversions_nonnegative"),
        sa.CheckConstraint("spend_krw >= 0", name="ck_daily_ad_metrics_spend_nonnegative"),
        sa.CheckConstraint("revenue_krw >= 0", name="ck_daily_ad_metrics_revenue_nonnegative"),
        sa.CheckConstraint(
            "clicks <= impressions", name="ck_daily_ad_metrics_clicks_lte_impressions"
        ),
        sa.CheckConstraint(
            "conversions <= clicks", name="ck_daily_ad_metrics_conversions_lte_clicks"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_run_id"], ["synthetic_dataset_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_run_id",
            "campaign_id",
            "date",
            name="uq_daily_ad_metrics_run_campaign_date",
        ),
    )
    op.create_index(
        "ix_daily_ad_metrics_run_date",
        "daily_ad_metrics",
        ["dataset_run_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_daily_ad_metrics_campaign_date",
        "daily_ad_metrics",
        ["campaign_id", "date"],
        unique=False,
    )
    op.create_table(
        "anomaly_truth_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_run_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("anomaly_type", sa.String(length=30), nullable=False),
        sa.Column("baseline_metadata", sa.JSON(), nullable=False),
        sa.Column("injection_strength", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "anomaly_type IN ('CTR_DROP', 'CVR_DROP', 'SPEND_SPIKE', 'IMPRESSION_DROP')",
            name="ck_anomaly_truth_labels_type",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_run_id"], ["synthetic_dataset_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_run_id",
            "campaign_id",
            "date",
            "anomaly_type",
            name="uq_anomaly_truth_run_campaign_date_type",
        ),
    )
    op.create_index(
        "ix_anomaly_truth_run_date",
        "anomaly_truth_labels",
        ["dataset_run_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_truth_run_date", table_name="anomaly_truth_labels")
    op.drop_table("anomaly_truth_labels")
    op.drop_index("ix_daily_ad_metrics_campaign_date", table_name="daily_ad_metrics")
    op.drop_index("ix_daily_ad_metrics_run_date", table_name="daily_ad_metrics")
    op.drop_table("daily_ad_metrics")
    op.drop_index("ix_campaigns_synthetic_dataset_run_id", table_name="campaigns")
    op.drop_constraint("fk_campaigns_synthetic_dataset_run_id", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "synthetic_dataset_run_id")
    op.drop_table("synthetic_dataset_runs")
