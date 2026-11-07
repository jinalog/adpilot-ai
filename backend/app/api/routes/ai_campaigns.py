import uuid

from fastapi import APIRouter, status

from app.api.dependencies import AICampaignServiceDependency
from app.schemas.ai_campaign import (
    DraftResponse,
    GenerateDraftRequest,
    RefineDraftRequest,
    SaveDraftResponse,
)

router = APIRouter(prefix="/ai/campaign-drafts")


@router.post("/generate", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
def generate_draft(
    data: GenerateDraftRequest, service: AICampaignServiceDependency
) -> DraftResponse:
    return service.generate(data.prompt)


@router.post("/{draft_id}/refine", response_model=DraftResponse)
def refine_draft(
    draft_id: uuid.UUID,
    data: RefineDraftRequest,
    service: AICampaignServiceDependency,
) -> DraftResponse:
    return service.refine(draft_id, data)


@router.get("/{draft_id}", response_model=DraftResponse)
def get_draft(draft_id: uuid.UUID, service: AICampaignServiceDependency) -> DraftResponse:
    return service.get(draft_id)


@router.post("/{draft_id}/save", response_model=SaveDraftResponse)
def save_draft(draft_id: uuid.UUID, service: AICampaignServiceDependency) -> SaveDraftResponse:
    return service.save(draft_id)
