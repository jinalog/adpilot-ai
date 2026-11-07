import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.campaign import CampaignStatus


class CampaignFields(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    objective: str = Field(min_length=1, max_length=2_000)
    total_budget_krw: int = Field(gt=0)
    daily_budget_krw: int = Field(gt=0)
    start_date: date
    end_date: date
    channels: list[str] = Field(min_length=1, max_length=20)
    targeting: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "objective")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("channels")
    @classmethod
    def normalize_channels(cls, value: list[str]) -> list[str]:
        normalized = [channel.strip().lower() for channel in value]
        if any(not channel for channel in normalized):
            raise ValueError("channels must not contain blank values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("channels must not contain duplicates")
        return normalized


class CampaignCreate(CampaignFields):
    pass


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    objective: str | None = Field(default=None, min_length=1, max_length=2_000)
    total_budget_krw: int | None = Field(default=None, gt=0)
    daily_budget_krw: int | None = Field(default=None, gt=0)
    start_date: date | None = None
    end_date: date | None = None
    channels: list[str] | None = Field(default=None, min_length=1, max_length=20)
    targeting: dict[str, Any] | None = None

    @field_validator("name", "objective")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("channels")
    @classmethod
    def normalize_optional_channels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return CampaignFields.normalize_channels(value)


class CampaignStatusUpdate(BaseModel):
    status: CampaignStatus


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    objective: str
    total_budget_krw: int
    daily_budget_krw: int
    start_date: date
    end_date: date
    channels: list[str]
    targeting: dict[str, Any]
    status: CampaignStatus
    approved_at: datetime | None
    deactivated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    offset: int
    limit: int
