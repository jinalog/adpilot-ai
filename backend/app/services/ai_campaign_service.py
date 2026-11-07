import uuid

from app.agents.campaign_setup import CampaignSetupWorkflow
from app.core.exceptions import BusinessRuleError, ConflictError, ResourceNotFoundError
from app.db.models.ai_campaign import AgentRun, CampaignDraft
from app.infrastructure.ai_campaign_repository import AICampaignRepository
from app.schemas.ai_campaign import (
    DraftResponse,
    DraftStatus,
    PartialCampaignDraft,
    RefineDraftRequest,
    SaveDraftResponse,
)
from app.schemas.campaign import CampaignCreate
from app.services.campaign_service import CampaignService


class AICampaignService:
    def __init__(
        self,
        repository: AICampaignRepository,
        campaign_service: CampaignService,
        workflow: CampaignSetupWorkflow,
    ) -> None:
        self.repository = repository
        self.campaign_service = campaign_service
        self.workflow = workflow

    def generate(self, prompt: str) -> DraftResponse:
        result = self.workflow.run(prompt)
        return self._persist_result(result)

    def refine(self, draft_id: uuid.UUID, data: RefineDraftRequest) -> DraftResponse:
        draft = self._get_draft(draft_id)
        if draft.saved_campaign_id is not None or draft.status == DraftStatus.SAVED.value:
            raise ConflictError("a saved AI draft cannot be refined")
        if not data.additional_input.strip() and data.draft_updates is None:
            raise BusinessRuleError("additional_input or draft_updates must be provided")
        current = PartialCampaignDraft.model_validate(draft.draft)
        result = self.workflow.run(
            data.additional_input,
            current_draft=current,
            explicit_updates=data.draft_updates,
        )
        return self._persist_result(result, draft=draft)

    def get(self, draft_id: uuid.UUID) -> DraftResponse:
        draft = self._get_draft(draft_id)
        run = self.repository.latest_run(draft.id)
        if run is None:
            raise ResourceNotFoundError(f"agent run for draft {draft_id} was not found")
        return self._response(draft, run)

    def save(self, draft_id: uuid.UUID) -> SaveDraftResponse:
        draft = self.repository.get_draft(draft_id, for_update=True)
        if draft is None:
            raise ResourceNotFoundError(f"AI campaign draft {draft_id} was not found")
        if draft.saved_campaign_id is not None:
            campaign = self.campaign_service.get(draft.saved_campaign_id)
            return SaveDraftResponse(
                draft_id=draft.id,
                campaign_id=campaign.id,
                campaign_status=campaign.status,
                already_saved=True,
            )
        if draft.status != DraftStatus.READY.value:
            raise ConflictError("only a READY AI draft can be saved")
        try:
            create_data = CampaignCreate.model_validate(draft.draft)
            campaign = self.campaign_service.create(create_data, commit=False)
            draft.saved_campaign_id = campaign.id
            draft.status = DraftStatus.SAVED.value
            self.repository.commit()
            self.repository.refresh(draft)
        except Exception:
            self.repository.rollback()
            raise
        return SaveDraftResponse(
            draft_id=draft.id,
            campaign_id=campaign.id,
            campaign_status=campaign.status,
            already_saved=False,
        )

    def _persist_result(
        self,
        result: dict[str, object],
        *,
        draft: CampaignDraft | None = None,
    ) -> DraftResponse:
        request_id = uuid.uuid4()
        if draft is None:
            draft = CampaignDraft(
                draft={},
                missing_fields=[],
                validation_errors=[],
                clarification_questions=[],
                status=DraftStatus.PROVIDER_ERROR.value,
                provider_mode=str(result.get("provider", "unknown")),
            )
            self.repository.add_draft(draft)
        partial = PartialCampaignDraft.model_validate(result.get("draft", {}))
        draft.draft = partial.model_dump(mode="json", exclude_none=True)
        draft.missing_fields = list(result.get("missing_fields", []))
        draft.validation_errors = list(result.get("validation_errors", []))
        draft.clarification_questions = list(result.get("clarification_questions", []))
        draft.status = str(result["status"])
        draft.provider_mode = str(result.get("provider", "unknown"))
        run = AgentRun(
            request_id=request_id,
            draft_id=draft.id,
            status=draft.status,
            failed_step=result.get("failed_step"),
            provider=draft.provider_mode,
            model=str(result.get("model", "unknown")),
            retry_count=int(result.get("retry_count", 0)),
            latency_ms=int(result.get("latency_ms", 0)),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
            error_code=result.get("provider_error_code"),
        )
        try:
            self.repository.add_run(run)
            self.repository.commit()
            self.repository.refresh(draft)
        except Exception:
            self.repository.rollback()
            raise
        return self._response(draft, run)

    def _get_draft(self, draft_id: uuid.UUID) -> CampaignDraft:
        draft = self.repository.get_draft(draft_id)
        if draft is None:
            raise ResourceNotFoundError(f"AI campaign draft {draft_id} was not found")
        return draft

    @staticmethod
    def _response(draft: CampaignDraft, run: AgentRun) -> DraftResponse:
        return DraftResponse(
            request_id=run.request_id,
            draft_id=draft.id,
            status=DraftStatus(draft.status),
            draft=PartialCampaignDraft.model_validate(draft.draft),
            missing_fields=draft.missing_fields,
            validation_errors=draft.validation_errors,
            clarification_questions=draft.clarification_questions,
            provider_mode=draft.provider_mode,
            retry_count=run.retry_count,
            saved=draft.saved_campaign_id is not None,
            campaign_id=draft.saved_campaign_id,
            error_code=run.error_code,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
