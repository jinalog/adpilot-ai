import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CampaignServiceDependency
from app.domain.campaign import CampaignStatus
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignStatusUpdate,
    CampaignUpdate,
)

router = APIRouter(prefix="/campaigns")


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(data: CampaignCreate, service: CampaignServiceDependency) -> CampaignResponse:
    return CampaignResponse.model_validate(service.create(data))


@router.get("", response_model=CampaignListResponse)
def list_campaigns(
    service: CampaignServiceDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    campaign_status: Annotated[CampaignStatus | None, Query(alias="status")] = None,
) -> CampaignListResponse:
    campaigns, total = service.list(offset=offset, limit=limit, status=campaign_status)
    return CampaignListResponse(
        items=[CampaignResponse.model_validate(campaign) for campaign in campaigns],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: uuid.UUID, service: CampaignServiceDependency) -> CampaignResponse:
    return CampaignResponse.model_validate(service.get(campaign_id))


@router.patch("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: uuid.UUID,
    data: CampaignUpdate,
    service: CampaignServiceDependency,
) -> CampaignResponse:
    return CampaignResponse.model_validate(service.update(campaign_id, data))


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_campaign(campaign_id: uuid.UUID, service: CampaignServiceDependency) -> Response:
    service.deactivate(campaign_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{campaign_id}/approve", response_model=CampaignResponse)
def approve_campaign(
    campaign_id: uuid.UUID, service: CampaignServiceDependency
) -> CampaignResponse:
    return CampaignResponse.model_validate(service.approve(campaign_id))


@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
def change_campaign_status(
    campaign_id: uuid.UUID,
    data: CampaignStatusUpdate,
    service: CampaignServiceDependency,
) -> CampaignResponse:
    return CampaignResponse.model_validate(service.change_status(campaign_id, data.status))
