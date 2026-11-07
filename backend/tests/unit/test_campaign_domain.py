from datetime import date

import pytest

from app.domain.campaign import (
    CampaignStatus,
    CampaignTransitionError,
    CampaignValidationError,
    CampaignValues,
    validate_campaign_values,
    validate_status_transition,
)


def valid_values(**overrides: object) -> CampaignValues:
    values = {
        "total_budget_krw": 3_000_000,
        "daily_budget_krw": 100_000,
        "start_date": date(2026, 11, 10),
        "end_date": date(2026, 12, 9),
    }
    values.update(overrides)
    return CampaignValues(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"total_budget_krw": 0}, "total_budget_krw"),
        ({"daily_budget_krw": 0}, "daily_budget_krw"),
        ({"daily_budget_krw": 3_000_001}, "cannot exceed"),
        ({"end_date": date(2026, 11, 9)}, "end_date"),
    ],
)
def test_campaign_value_validation_rejects_invalid_values(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(CampaignValidationError, match=message):
        validate_campaign_values(valid_values(**overrides))


def test_campaign_value_validation_accepts_same_day_campaign() -> None:
    validate_campaign_values(valid_values(end_date=date(2026, 11, 10)))


@pytest.mark.parametrize(
    ("current", "target", "approved"),
    [
        (CampaignStatus.APPROVED, CampaignStatus.ACTIVE, True),
        (CampaignStatus.ACTIVE, CampaignStatus.PAUSED, True),
        (CampaignStatus.PAUSED, CampaignStatus.ACTIVE, True),
        (CampaignStatus.DRAFT, CampaignStatus.INACTIVE, False),
    ],
)
def test_allowed_status_transitions(
    current: CampaignStatus, target: CampaignStatus, approved: bool
) -> None:
    validate_status_transition(current, target, approved=approved)


def test_draft_cannot_be_activated() -> None:
    with pytest.raises(CampaignTransitionError, match="not allowed"):
        validate_status_transition(CampaignStatus.DRAFT, CampaignStatus.ACTIVE, approved=False)


def test_activation_requires_approval_timestamp() -> None:
    with pytest.raises(CampaignTransitionError, match="must be approved"):
        validate_status_transition(CampaignStatus.APPROVED, CampaignStatus.ACTIVE, approved=False)
