import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.providers import CampaignExtractionProvider, ProviderError, ProviderResult
from app.core.exceptions import BusinessRuleError
from app.schemas.ai_campaign import DraftStatus, PartialCampaignDraft
from app.schemas.campaign import CampaignCreate
from app.services.campaign_service import CampaignService

REQUIRED_FIELDS = tuple(PartialCampaignDraft.model_fields)
QUESTIONS = {
    "name": "캠페인명을 알려주세요.",
    "objective": "측정 가능한 광고 목표를 알려주세요.",
    "total_budget_krw": "총예산(원)을 알려주세요.",
    "daily_budget_krw": "일예산(원)을 알려주세요. 총예산에서 자동 계산하지 않습니다.",
    "start_date": "확정된 시작일을 YYYY-MM-DD 형식으로 알려주세요.",
    "end_date": "확정된 종료일을 YYYY-MM-DD 형식으로 알려주세요.",
    "channels": "사용할 광고 채널을 하나 이상 알려주세요.",
    "targeting": "타게팅 조건을 JSON 객체로 알려주세요. 조건이 없으면 {}로 입력하세요.",
}


class CampaignSetupState(TypedDict, total=False):
    input_text: str
    current_draft: dict[str, Any]
    explicit_updates: dict[str, Any]
    extracted_draft: dict[str, Any]
    draft: dict[str, Any]
    missing_fields: list[str]
    validation_errors: list[str]
    clarification_questions: list[str]
    status: str
    provider_error_code: str | None
    failed_step: str | None
    retry_count: int
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class CampaignSetupWorkflow:
    def __init__(
        self,
        provider: CampaignExtractionProvider,
        *,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.max_retries = min(max(max_retries, 0), 2)
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(CampaignSetupState)
        graph.add_node("extract_requirements", self.extract_requirements)
        graph.add_node("merge_context", self.merge_context)
        graph.add_node("check_missing_fields", self.check_missing_fields)
        graph.add_node("validate_draft", self.validate_draft)
        graph.add_node("prepare_preview", self.prepare_preview)
        graph.add_node("prepare_clarification", self.prepare_clarification)
        graph.add_node("handle_provider_error", self.handle_provider_error)
        graph.add_edge(START, "extract_requirements")
        graph.add_conditional_edges(
            "extract_requirements",
            lambda state: "error" if state.get("provider_error_code") else "ok",
            {"error": "handle_provider_error", "ok": "merge_context"},
        )
        graph.add_edge("merge_context", "check_missing_fields")
        graph.add_conditional_edges(
            "check_missing_fields",
            lambda state: "missing" if state["missing_fields"] else "complete",
            {"missing": "prepare_clarification", "complete": "validate_draft"},
        )
        graph.add_conditional_edges(
            "validate_draft",
            lambda state: "invalid" if state["validation_errors"] else "valid",
            {"invalid": END, "valid": "prepare_preview"},
        )
        graph.add_edge("prepare_preview", END)
        graph.add_edge("prepare_clarification", END)
        graph.add_edge("handle_provider_error", END)
        return graph.compile()

    def run(
        self,
        input_text: str,
        *,
        current_draft: PartialCampaignDraft | None = None,
        explicit_updates: PartialCampaignDraft | None = None,
    ) -> CampaignSetupState:
        initial: CampaignSetupState = {
            "input_text": input_text,
            "current_draft": (current_draft.model_dump(exclude_none=True) if current_draft else {}),
            "explicit_updates": (
                explicit_updates.model_dump(exclude_none=True) if explicit_updates else {}
            ),
            "retry_count": 0,
            "provider": self.provider.mode,
            "model": self.provider.model,
        }
        return self.graph.invoke(initial)

    def extract_requirements(self, state: CampaignSetupState) -> CampaignSetupState:
        started = time.monotonic()
        result: ProviderResult | None = None
        error: ProviderError | None = None
        retry_count = 0
        while True:
            try:
                result = self.provider.extract(
                    state["input_text"], timeout_seconds=self.timeout_seconds
                )
                break
            except ProviderError as exc:
                error = exc
                if not exc.transient or retry_count >= self.max_retries:
                    break
                retry_count += 1
        update: CampaignSetupState = {
            "retry_count": retry_count,
            "latency_ms": int((time.monotonic() - started) * 1_000),
        }
        if error is not None and result is None:
            update.update(
                provider_error_code=error.code,
                failed_step="extract_requirements",
            )
            return update
        assert result is not None
        update.update(
            extracted_draft=result.draft.model_dump(exclude_none=True),
            provider=result.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            provider_error_code=None,
        )
        return update

    @staticmethod
    def merge_context(state: CampaignSetupState) -> CampaignSetupState:
        merged = dict(state.get("current_draft", {}))
        merged.update(state.get("extracted_draft", {}))
        merged.update(state.get("explicit_updates", {}))
        return {"draft": merged}

    @staticmethod
    def check_missing_fields(state: CampaignSetupState) -> CampaignSetupState:
        draft = state["draft"]
        missing = [field for field in REQUIRED_FIELDS if draft.get(field) is None]
        return {"missing_fields": missing}

    @staticmethod
    def validate_draft(state: CampaignSetupState) -> CampaignSetupState:
        errors: list[str] = []
        try:
            campaign = CampaignCreate.model_validate(state["draft"])
            CampaignService.validate_create(campaign)
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors()
            ]
        except BusinessRuleError as exc:
            errors = [exc.message]
        return {
            "validation_errors": errors,
            "status": (DraftStatus.VALIDATION_FAILED.value if errors else DraftStatus.READY.value),
        }

    @staticmethod
    def prepare_preview(_: CampaignSetupState) -> CampaignSetupState:
        return {"status": DraftStatus.READY.value, "clarification_questions": []}

    @staticmethod
    def prepare_clarification(state: CampaignSetupState) -> CampaignSetupState:
        return {
            "status": DraftStatus.NEEDS_CLARIFICATION.value,
            "validation_errors": [],
            "clarification_questions": [QUESTIONS[field] for field in state["missing_fields"]],
        }

    @staticmethod
    def handle_provider_error(state: CampaignSetupState) -> CampaignSetupState:
        return {
            "status": DraftStatus.PROVIDER_ERROR.value,
            "draft": dict(state.get("current_draft", {})),
            "missing_fields": list(REQUIRED_FIELDS),
            "validation_errors": [],
            "clarification_questions": [],
        }
