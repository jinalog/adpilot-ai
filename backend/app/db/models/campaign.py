import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.campaign import CampaignStatus


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("total_budget_krw > 0", name="ck_campaigns_total_budget_positive"),
        CheckConstraint("daily_budget_krw > 0", name="ck_campaigns_daily_budget_positive"),
        CheckConstraint(
            "daily_budget_krw <= total_budget_krw",
            name="ck_campaigns_daily_budget_lte_total",
        ),
        CheckConstraint("end_date >= start_date", name="ck_campaigns_date_range"),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'ACTIVE', 'PAUSED', 'INACTIVE')",
            name="ck_campaigns_status",
        ),
        Index("ix_campaigns_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    total_budget_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_budget_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    targeting: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CampaignStatus.DRAFT.value
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
