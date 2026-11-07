import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.ai_campaign import AgentRun, CampaignDraft


class AICampaignRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_draft(self, draft: CampaignDraft) -> CampaignDraft:
        self.session.add(draft)
        self.session.flush()
        return draft

    def add_run(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        self.session.flush()
        return run

    def get_draft(self, draft_id: uuid.UUID, *, for_update: bool = False) -> CampaignDraft | None:
        statement = select(CampaignDraft).where(CampaignDraft.id == draft_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def latest_run(self, draft_id: uuid.UUID) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(AgentRun.draft_id == draft_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, value: CampaignDraft) -> None:
        self.session.refresh(value)
