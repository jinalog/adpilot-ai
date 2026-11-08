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
from app.schemas.analyst import AnalysisPlan, AnalystStatus

UNSAFE_QUESTION = re.compile(
    r"(?:;|--|/\*|\*/|\b(?:insert|update|delete|drop|alter|create|truncate|copy|call|do|set)\b|"
    r"\bpg_sleep\b|information_schema|pg_catalog|anomaly_truth_labels)",
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
            {"error": "tool_error", "ok": "calculate_facts"},
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
                "truncated": False,
            }
        )
        result["latency_ms"] = int((time.monotonic() - started) * 1_000)
        return result

    @staticmethod
    def guard_question(state: AnalystState) -> AnalystState:
        if UNSAFE_QUESTION.search(state["question"]):
            return {"error_code": "unsafe_question", "failed_step": "guard_question"}
        return {"error_code": None, "failed_step": None}

    def plan_question(self, state: AnalystState) -> AnalystState:
        retry_count = 0
        while True:
            try:
                result = self.provider.plan(
                    state["question"], state["context"], timeout_seconds=self.timeout_seconds
                )
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

    def calculate_facts(self, state: AnalystState) -> AnalystState:
        query = state["compiled_query"]
        result = state["query_result"]
        facts, evidence, hypotheses, recommendations, summary = self.fact_builder.build(
            state["plan"], result.rows, query_fingerprint=query.fingerprint
        )
        return {
            "facts": facts,
            "evidence": evidence,
            "hypotheses": hypotheses,
            "recommendations": recommendations,
            "answer_summary": summary,
        }

    @staticmethod
    def compose_response(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.READY.value, "error_code": None, "failed_step": None}

    @staticmethod
    def provider_error(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.PROVIDER_ERROR.value}

    @staticmethod
    def validation_blocked(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.VALIDATION_FAILED.value}

    @staticmethod
    def tool_error(_: AnalystState) -> AnalystState:
        return {"status": AnalystStatus.TOOL_ERROR.value}
