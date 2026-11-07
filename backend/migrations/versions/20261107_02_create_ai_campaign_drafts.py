"""Create AI campaign draft and agent run tables.

Revision ID: 20261107_02
Revises: 20261107_01
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_02"
down_revision: str | None = "20261107_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("clarification_questions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_mode", sa.String(length=30), nullable=False),
        sa.Column("saved_campaign_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('READY', 'NEEDS_CLARIFICATION', 'VALIDATION_FAILED', "
            "'PROVIDER_ERROR', 'SAVED')",
            name="ck_campaign_drafts_status",
        ),
        sa.ForeignKeyConstraint(["saved_campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("saved_campaign_id"),
    )
    op.create_index(
        "ix_campaign_drafts_status_updated_at",
        "campaign_drafts",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("failed_step", sa.String(length=60), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["campaign_drafts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        "ix_agent_runs_draft_created_at",
        "agent_runs",
        ["draft_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_draft_created_at", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_campaign_drafts_status_updated_at", table_name="campaign_drafts")
    op.drop_table("campaign_drafts")
