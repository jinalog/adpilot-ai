import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DraftStatus(StrEnum):
    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    SAVED = "SAVED"


class PartialCampaignDraft(BaseModel):
    name: str | None = None
    objective: str | None = None
    total_budget_krw: int | None = None
    daily_budget_krw: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    channels: list[str] | None = None
    targeting: dict[str, Any] | None = None


class GenerateDraftRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)


class RefineDraftRequest(BaseModel):
    additional_input: str = Field(default="", max_length=10_000)
    draft_updates: PartialCampaignDraft | None = None


class DraftResponse(BaseModel):
    request_id: uuid.UUID
    draft_id: uuid.UUID
    status: DraftStatus
    draft: PartialCampaignDraft
    missing_fields: list[str]
    validation_errors: list[str]
    clarification_questions: list[str]
    provider_mode: str
    retry_count: int
    saved: bool
    campaign_id: uuid.UUID | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class SaveDraftResponse(BaseModel):
    draft_id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_status: str
    already_saved: bool
