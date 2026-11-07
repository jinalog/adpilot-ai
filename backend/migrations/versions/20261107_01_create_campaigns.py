"""Create campaigns table.

Revision ID: 20261107_01
Revises:
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("total_budget_krw", sa.BigInteger(), nullable=False),
        sa.Column("daily_budget_krw", sa.BigInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("targeting", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("daily_budget_krw > 0", name="ck_campaigns_daily_budget_positive"),
        sa.CheckConstraint(
            "daily_budget_krw <= total_budget_krw",
            name="ck_campaigns_daily_budget_lte_total",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_campaigns_date_range"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'ACTIVE', 'PAUSED', 'INACTIVE')",
            name="ck_campaigns_status",
        ),
        sa.CheckConstraint("total_budget_krw > 0", name="ck_campaigns_total_budget_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaigns_status_created_at", "campaigns", ["status", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_campaigns_status_created_at", table_name="campaigns")
    op.drop_table("campaigns")
