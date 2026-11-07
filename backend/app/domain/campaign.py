from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class CampaignStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    INACTIVE = "INACTIVE"


class CampaignValidationError(ValueError):
    """Raised when deterministic campaign business rules are violated."""


class CampaignTransitionError(ValueError):
    """Raised when a campaign status transition is not allowed."""


@dataclass(frozen=True, slots=True)
class CampaignValues:
    total_budget_krw: int
    daily_budget_krw: int
    start_date: date
    end_date: date


ALLOWED_STATUS_TRANSITIONS: dict[CampaignStatus, frozenset[CampaignStatus]] = {
    CampaignStatus.DRAFT: frozenset({CampaignStatus.INACTIVE}),
    CampaignStatus.APPROVED: frozenset({CampaignStatus.ACTIVE, CampaignStatus.INACTIVE}),
    CampaignStatus.ACTIVE: frozenset({CampaignStatus.PAUSED, CampaignStatus.INACTIVE}),
    CampaignStatus.PAUSED: frozenset({CampaignStatus.ACTIVE, CampaignStatus.INACTIVE}),
    CampaignStatus.INACTIVE: frozenset(),
}


def validate_campaign_values(values: CampaignValues) -> None:
    if values.total_budget_krw <= 0:
        raise CampaignValidationError("total_budget_krw must be greater than zero")
    if values.daily_budget_krw <= 0:
        raise CampaignValidationError("daily_budget_krw must be greater than zero")
    if values.daily_budget_krw > values.total_budget_krw:
        raise CampaignValidationError("daily_budget_krw cannot exceed total_budget_krw")
    if values.end_date < values.start_date:
        raise CampaignValidationError("end_date cannot be earlier than start_date")


def validate_status_transition(
    current: CampaignStatus,
    target: CampaignStatus,
    *,
    approved: bool,
) -> None:
    if target not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise CampaignTransitionError(f"transition from {current} to {target} is not allowed")
    if target is CampaignStatus.ACTIVE and not approved:
        raise CampaignTransitionError("campaign must be approved before activation")
