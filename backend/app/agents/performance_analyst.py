import re
import time
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.analyst_provider import AnalystPlanContext, AnalystPlanningProvider
from app.agents.providers import ProviderError
from app.domain.analyst_facts import AnalystFactBuilder
from app.domain.analyst_sql import (
    CompiledQuery,
    DeterministicSQLCompiler,
    SQLASTValidator,
    SQLSafetyError,
)
from app.infrastructure.analyst_executor import AnalystToolError, QueryResult, ReadOnlySQLExecutor
from app.schemas.analyst import AnalysisPlan, AnalystStatus, QuestionType

HIGH_CONFIDENCE_SQL_ATTACK = re.compile(
    r"(?:\b(?:drop\s+table|delete\s+from|insert\s+into|alter\s+table|"
    r"truncate\s+table|update\s+[a-z_][\w.]*\s+set|select\b[\s\S]+\bfrom\b)\b|"
    r"\b(?:execute|run)\s+(?:this\s+)?sql\b|"
    r"\bignore\s+(?:all\s+|previous\s+)?instructions\b[\s\S]*\b(?:execute|sql|query)\b|"
    r"\b(?:pg_sleep|information_schema|pg_catalog|anomaly_truth_labels)|"
    r"\b(?:drop|delete|insert|update|select)\b[\s\S]*(?:;|--|/\*|\*/))",
    re.IGNORECASE,
)


class AnalystState(TypedDict, total=False):
    request_id: uuid.UUID
    question: str
    context: AnalystPlanContext
    plan: AnalysisPlan
    compiled_query: CompiledQuery
    query_result: QueryResult
    facts: list[Any]
    evidence: list[Any]
    hypotheses: list[Any]
    recommendations: list[Any]
    answer_summary: str
    status: str
    clarification_questions: list[str]
    data_notices: list[str]
    provider_mode: str
    provider_model: str
    retry_count: int
    input_tokens: int | None
    output_tokens: int | None
    error_code: str | None
    failed_step: str | None
    latency_ms: int
    truncated: bool


class PerformanceAnalystWorkflow:
    def __init__(
        self,
        provider: AnalystPlanningProvider,
        compiler: DeterministicSQLCompiler,
        validator: SQLASTValidator,
        executor: ReadOnlySQLExecutor,
        *,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.provider = provider
        self.compiler = compiler
        self.validator = validator
        self.executor = executor
        self.timeout_seconds = timeout_seconds
        self.max_retries = min(max(max_retries, 0), 2)
        self.fact_builder = AnalystFactBuilder()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(AnalystState)
        graph.add_node("guard_question", self.guard_question)
        graph.add_node("plan_question", self.plan_question)
        graph.add_node("clarification_check", self.clarification_check)
        graph.add_node("compile_sql", self.compile_sql)
        graph.add_node("validate_sql", self.validate_sql)
        graph.add_node("execute_query", self.execute_query)
        graph.add_node("result_size_check", self.result_size_check)
        graph.add_node("calculate_facts", self.calculate_facts)
        graph.add_node("compose_response", self.compose_response)
        graph.add_node("provider_error", self.provider_error)
        graph.add_node("validation_blocked", self.validation_blocked)
        graph.add_node("tool_error", self.tool_error)
        graph.add_edge(START, "guard_question")
        graph.add_conditional_edges(
            "guard_question",
            lambda state: "blocked" if state.get("error_code") else "safe",
            {"blocked": "validation_blocked", "safe": "plan_question"},
        )
        graph.add_conditional_edges(
            "plan_question",
            lambda state: "error" if state.get("error_code") else "ok",
            {"error": "provider_error", "ok": "clarification_check"},
        )
        graph.add_conditional_edges(
            "clarification_check",
            lambda state: "clarify" if state.get("clarification_questions") else "ready",
            {"clarify": END, "ready": "compile_sql"},
        )
        graph.add_edge("compile_sql", "validate_sql")
        graph.add_conditional_edges(
            "validate_sql",
            lambda state: "blocked" if state.get("error_code") else "safe",
            {"blocked": "validation_blocked", "safe": "execute_query"},
        )
        graph.add_conditional_edges(
            "execute_query",
            lambda state: "error" if state.get("error_code") else "ok",
            {"error": "tool_error", "ok": "result_size_check"},
        )
        graph.add_conditional_edges(
            "result_size_check",
            lambda state: "narrow" if state.get("error_code") else "continue",
            {"narrow": END, "continue": "calculate_facts"},
        )
        graph.add_edge("calculate_facts", "compose_response")
        graph.add_edge("compose_response", END)
        graph.add_edge("provider_error", END)
        graph.add_edge("validation_blocked", END)
        graph.add_edge("tool_error", END)
        return graph.compile()

    def run(
        self,
        question: str,
        context: AnalystPlanContext,
        *,
        request_id: uuid.UUID | None = None,
    ) -> AnalystState:
        started = time.monotonic()
        result = self.graph.invoke(
            {
                "request_id": request_id or uuid.uuid4(),
                "question": question,
                "context": context,
                "provider_mode": self.provider.mode,
                "provider_model": self.provider.model,
                "retry_count": 0,
                "input_tokens": None,
                "output_tokens": None,
                "clarification_questions": [],
                "data_notices": [],
                "truncated": False,
            }
        )
        result["latency_ms"] = int((time.monotonic() - started) * 1_000)
        return result

    @staticmethod
    def guard_question(state: AnalystState) -> AnalystState:
        if HIGH_CONFIDENCE_SQL_ATTACK.search(state["question"]):
            return {"error_code": "unsafe_question", "failed_step": "guard_question"}
        return {"error_code": None, "failed_step": None}

    def plan_question(self, state: AnalystState) -> AnalystState:
        retry_count = 0
        while True:
            try:
                result = self.provider.plan(
                    state["question"], state["context"], timeout_seconds=self.timeout_seconds
                )
                if result.plan is not None and not self._plan_matches_context(
                    result.plan, state["context"]
                ):
                    return {
                        "error_code": "provider_context_mismatch",
                        "failed_step": "plan_question",
                        "retry_count": retry_count,
                    }
                return {
                    "plan": result.plan,
                    "clarification_questions": result.clarification_questions,
                    "provider_mode": result.provider,
                    "provider_model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "retry_count": retry_count,
                    "error_code": None,
                }
            except ValidationError:
                return {
                    "error_code": "provider_schema_mismatch",
                    "failed_step": "plan_question",
                    "retry_count": retry_count,
                }
            except ProviderError as exc:
                if not exc.transient or retry_count >= self.max_retries:
                    return {
                        "error_code": exc.code,
                        "failed_step": "plan_question",
                        "retry_count": retry_count,
                    }
                retry_count += 1

    @staticmethod
    def _plan_matches_context(plan: AnalysisPlan, context: AnalystPlanContext) -> bool:
        return (
            plan.dataset_run_id == context.dataset_run_id
            and plan.campaign_id == context.campaign_id
            and plan.start_date == context.start_date
            and plan.end_date == context.end_date
            and plan.comparison_start_date == context.comparison_start_date
            and plan.comparison_end_date == context.comparison_end_date
        )

    @staticmethod
    def clarification_check(state: AnalystState) -> AnalystState:
        if state.get("clarification_questions"):
            return {"status": AnalystStatus.NEEDS_CLARIFICATION.value}
        return {"status": AnalystStatus.READY.value}

    def compile_sql(self, state: AnalystState) -> AnalystState:
        return {"compiled_query": self.compiler.compile(state["plan"])}

    def validate_sql(self, state: AnalystState) -> AnalystState:
        try:
            self.validator.validate(state["compiled_query"])
        except SQLSafetyError as exc:
            return {"error_code": exc.code, "failed_step": "validate_sql"}
        return {"error_code": None}

    def execute_query(self, state: AnalystState) -> AnalystState:
        try:
            result = self.executor.execute(state["compiled_query"])
        except AnalystToolError as exc:
            return {"error_code": exc.code, "failed_step": "execute_query"}
        return {"query_result": result, "truncated": result.truncated, "error_code": None}

    @staticmethod
    def result_size_check(state: AnalystState) -> AnalystState:
        if state.get("truncated") and state["plan"].question_type in {
            QuestionType.RANK_CAMPAIGNS,
            QuestionType.ANOMALY_LOOKUP,
        }:
            return {
                "status": AnalystStatus.NEEDS_CLARIFICATION.value,
                "error_code": "analysis_result_too_large",
                "failed_step": "result_size_check",
                "clarification_questions": [
                    "정확한 분석을 위해 Campaign 또는 날짜 범위를 좁혀 주세요."
                ],
                "facts": [],
                "evidence": [],
            }
        return {"error_code": None}

    def calculate_facts(self, state: AnalystState) -> AnalystState:
        query = state["compiled_query"]
        result = state["query_result"]
        built = self.fact_builder.build(
            state["plan"], result.rows, query_fingerprint=query.fingerprint
        )
        return {
            "facts": built.facts,
            "evidence": built.evidence,
            "hypotheses": built.hypotheses,
            "recommendations": built.recommendations,
            "answer_summary": built.summary,
            "data_notices": list(built.data_notices),
            "status": (AnalystStatus.NO_DATA.value if built.no_data else AnalystStatus.READY.value),
        }

    @staticmethod
    def compose_response(state: AnalystState) -> AnalystState:
        return {
            "status": state.get("status", AnalystStatus.READY.value),
            "error_code": None,
            "failed_step": None,
        }

    @staticmethod
    def provider_error(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.PROVIDER_ERROR.value}

    @staticmethod
    def validation_blocked(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.VALIDATION_FAILED.value}

    @staticmethod
    def tool_error(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.TOOL_ERROR.value}
