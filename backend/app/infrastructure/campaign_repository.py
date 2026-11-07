import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign
from app.domain.campaign import CampaignStatus


class CampaignRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, campaign: Campaign) -> Campaign:
        self.session.add(campaign)
        self.session.flush()
        self.session.refresh(campaign)
        return campaign

    def get(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.session.get(Campaign, campaign_id)

    def list(
        self,
        *,
        offset: int,
        limit: int,
        status: CampaignStatus | None,
    ) -> tuple[list[Campaign], int]:
        filters = [] if status is None else [Campaign.status == status.value]
        total = self.session.scalar(select(func.count(Campaign.id)).where(*filters)) or 0
        statement = (
            select(Campaign)
            .where(*filters)
            .order_by(Campaign.created_at.desc(), Campaign.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement)), total

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, campaign: Campaign) -> None:
        self.session.refresh(campaign)
