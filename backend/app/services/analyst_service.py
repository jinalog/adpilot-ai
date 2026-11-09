from datetime import date

from app.agents.analyst_provider import AnalystPlanContext
from app.agents.performance_analyst import PerformanceAnalystWorkflow
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.schemas.analyst import AnalystQuestionRequest, AnalystResponse, AnalystUsage

MAX_ANALYSIS_DAYS = 366


class PerformanceAnalystService:
    def __init__(
        self,
        repository: AnalyticsRepository,
        workflow: PerformanceAnalystWorkflow,
    ) -> None:
        self.repository = repository
        self.workflow = workflow

    def analyze(self, request: AnalystQuestionRequest) -> AnalystResponse:
        dataset = self.repository.get_dataset(request.dataset_run_id)
        if dataset is None:
            raise ResourceNotFoundError(f"dataset {request.dataset_run_id} was not found")
        if (
            request.campaign_id is not None
            and self.repository.get_owned_campaign(request.dataset_run_id, request.campaign_id)
            is None
        ):
            raise ResourceNotFoundError(
                f"campaign {request.campaign_id} was not found in dataset {request.dataset_run_id}"
            )
        start_date = request.start_date or dataset.start_date
        end_date = request.end_date or dataset.end_date
        self._validate_range(start_date, end_date, "analysis")
        if (request.comparison_start_date is None) != (request.comparison_end_date is None):
            raise BusinessRuleError(
                "comparison_start_date and comparison_end_date are required together"
            )
        if request.comparison_start_date is not None and request.comparison_end_date is not None:
            self._validate_range(
                request.comparison_start_date,
                request.comparison_end_date,
                "comparison",
            )
        state = self.workflow.run(
            request.question,
            AnalystPlanContext(
                dataset_run_id=request.dataset_run_id,
                campaign_id=request.campaign_id,
                start_date=start_date,
                end_date=end_date,
                comparison_start_date=request.comparison_start_date,
                comparison_end_date=request.comparison_end_date,
            ),
        )
        return AnalystResponse(
            status=state["status"],
            request_id=state["request_id"],
            provider_mode=state["provider_mode"],
            provider_model=state["provider_model"],
            plan=state.get("plan"),
            answer_summary=state.get("answer_summary"),
            facts=state.get("facts", []),
            hypotheses=state.get("hypotheses", []),
            recommendations=state.get("recommendations", []),
            evidence=state.get("evidence", []),
            clarification_questions=state.get("clarification_questions", []),
            data_notices=state.get("data_notices", []),
            error_code=state.get("error_code"),
            failed_step=state.get("failed_step"),
            retry_count=state.get("retry_count", 0),
            latency_ms=state.get("latency_ms", 0),
            usage=AnalystUsage(
                input_tokens=state.get("input_tokens"),
                output_tokens=state.get("output_tokens"),
            ),
            truncated=state.get("truncated", False),
        )

    @staticmethod
    def _validate_range(start_date: date, end_date: date, label: str) -> None:
        if start_date > end_date:
            raise BusinessRuleError(f"{label}_start_date cannot be later than {label}_end_date")
        if (end_date - start_date).days + 1 > MAX_ANALYSIS_DAYS:
            raise BusinessRuleError(f"{label} date range cannot exceed {MAX_ANALYSIS_DAYS} days")
