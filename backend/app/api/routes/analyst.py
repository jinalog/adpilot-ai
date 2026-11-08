from fastapi import APIRouter

from app.api.dependencies import AnalystServiceDependency
from app.schemas.analyst import AnalystQuestionRequest, AnalystResponse

router = APIRouter(prefix="/analyst")


@router.post("/questions", response_model=AnalystResponse)
def analyze_question(
    payload: AnalystQuestionRequest,
    service: AnalystServiceDependency,
) -> AnalystResponse:
    return service.analyze(payload)
