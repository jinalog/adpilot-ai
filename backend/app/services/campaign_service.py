import uuid
from datetime import UTC, datetime

from app.core.exceptions import BusinessRuleError, ConflictError, ResourceNotFoundError
from app.db.models.campaign import Campaign
from app.domain.campaign import (
    CampaignStatus,
    CampaignTransitionError,
    CampaignValidationError,
    CampaignValues,
    validate_campaign_values,
    validate_status_transition,
)
from app.infrastructure.campaign_repository import CampaignRepository
from app.schemas.campaign import CampaignCreate, CampaignUpdate


class CampaignService:
    def __init__(self, repository: CampaignRepository) -> None:
        self.repository = repository

    def create(self, data: CampaignCreate) -> Campaign:
        self._validate_values(data)
        campaign = Campaign(**data.model_dump(), status=CampaignStatus.DRAFT.value)
        try:
            self.repository.add(campaign)
            self.repository.commit()
            self.repository.refresh(campaign)
        except Exception:
            self.repository.rollback()
            raise
        return campaign

    def list(
        self,
        *,
        offset: int,
        limit: int,
        status: CampaignStatus | None,
    ) -> tuple[list[Campaign], int]:
        return self.repository.list(offset=offset, limit=limit, status=status)

    def get(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self.repository.get(campaign_id)
        if campaign is None:
            raise ResourceNotFoundError(f"campaign {campaign_id} was not found")
        return campaign

    def update(self, campaign_id: uuid.UUID, data: CampaignUpdate) -> Campaign:
        campaign = self.get(campaign_id)
        current_status = CampaignStatus(campaign.status)
        if current_status not in {CampaignStatus.DRAFT, CampaignStatus.APPROVED}:
            raise ConflictError(f"campaign in {current_status} status cannot be edited")

        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise BusinessRuleError("at least one field must be provided")

        values = CampaignValues(
            total_budget_krw=changes.get("total_budget_krw", campaign.total_budget_krw),
            daily_budget_krw=changes.get("daily_budget_krw", campaign.daily_budget_krw),
            start_date=changes.get("start_date", campaign.start_date),
            end_date=changes.get("end_date", campaign.end_date),
        )
        self._run_value_validation(values)

        for field, value in changes.items():
            setattr(campaign, field, value)

        if current_status is CampaignStatus.APPROVED:
            campaign.status = CampaignStatus.DRAFT.value
            campaign.approved_at = None

        return self._commit_and_refresh(campaign)

    def approve(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self.get(campaign_id)
        current_status = CampaignStatus(campaign.status)
        if current_status is not CampaignStatus.DRAFT:
            raise ConflictError(f"only DRAFT campaigns can be approved; current={current_status}")

        campaign.status = CampaignStatus.APPROVED.value
        campaign.approved_at = datetime.now(UTC)
        return self._commit_and_refresh(campaign)

    def change_status(self, campaign_id: uuid.UUID, target: CampaignStatus) -> Campaign:
        campaign = self.get(campaign_id)
        current = CampaignStatus(campaign.status)
        try:
            validate_status_transition(current, target, approved=campaign.approved_at is not None)
        except CampaignTransitionError as exc:
            raise ConflictError(str(exc)) from exc

        campaign.status = target.value
        if target is CampaignStatus.INACTIVE:
            campaign.deactivated_at = datetime.now(UTC)
        return self._commit_and_refresh(campaign)

    def deactivate(self, campaign_id: uuid.UUID) -> None:
        campaign = self.get(campaign_id)
        current = CampaignStatus(campaign.status)
        if current is CampaignStatus.INACTIVE:
            return
        self.change_status(campaign_id, CampaignStatus.INACTIVE)

    @staticmethod
    def _validate_values(data: CampaignCreate) -> None:
        CampaignService._run_value_validation(
            CampaignValues(
                total_budget_krw=data.total_budget_krw,
                daily_budget_krw=data.daily_budget_krw,
                start_date=data.start_date,
                end_date=data.end_date,
            )
        )

    @staticmethod
    def _run_value_validation(values: CampaignValues) -> None:
        try:
            validate_campaign_values(values)
        except CampaignValidationError as exc:
            raise BusinessRuleError(str(exc)) from exc

    def _commit_and_refresh(self, campaign: Campaign) -> Campaign:
        try:
            self.repository.commit()
            self.repository.refresh(campaign)
        except Exception:
            self.repository.rollback()
            raise
        return campaign
