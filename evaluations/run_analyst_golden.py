import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.analyst_provider import MockAnalystProvider
from app.agents.performance_analyst import PerformanceAnalystWorkflow
from app.core.config import get_settings
from app.core.exceptions import ResourceNotFoundError
from app.db.models.campaign import Campaign
from app.domain.analyst_sql import DeterministicSQLCompiler, SQLASTValidator
from app.infrastructure.analyst_executor import ReadOnlySQLExecutor
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.schemas.analyst import AnalystQuestionRequest
from app.services.analyst_service import PerformanceAnalystService

DATASET = Path(__file__).with_name("datasets") / "analyst_questions_golden.json"


def build_service(
    session: Session, *, absolute_max_rows: int | None = None
) -> PerformanceAnalystService:
    settings = get_settings()
    workflow = PerformanceAnalystWorkflow(
        MockAnalystProvider(),
        DeterministicSQLCompiler(),
        SQLASTValidator(),
        ReadOnlySQLExecutor(
            session.get_bind(),
            statement_timeout_ms=settings.analyst_statement_timeout_ms,
            absolute_max_rows=absolute_max_rows or settings.analyst_absolute_max_rows,
        ),
        timeout_seconds=settings.analyst_provider_timeout_seconds,
        max_retries=0,
    )
    return PerformanceAnalystService(AnalyticsRepository(session), workflow)


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    cases = json.loads(DATASET.read_text())
    failures: list[str] = []
    with Session(engine) as session:
        repository = AnalyticsRepository(session)
        dataset = repository.get_dataset_by_name("phase3-default")
        if dataset is None:
            print("FAIL phase3-default dataset is required")
            return 1
        campaigns = repository.campaign_names(dataset.id)
        campaign_by_name = {name: campaign_id for campaign_id, name in campaigns.items()}
        foreign_campaign = session.scalar(
            select(Campaign.id).where(Campaign.synthetic_dataset_run_id != dataset.id).limit(1)
        )
        passed = 0
        for case in cases:
            service = build_service(session, absolute_max_rows=case.get("absolute_max_rows"))
            campaign_id = None
            if case.get("campaign_name"):
                campaign_id = campaign_by_name[case["campaign_name"]]
            elif case.get("campaign_id"):
                campaign_id = uuid.UUID(case["campaign_id"])
            elif case.get("foreign_campaign"):
                campaign_id = foreign_campaign or uuid.uuid4()
            request = AnalystQuestionRequest(
                dataset_run_id=dataset.id,
                question=case["question"],
                campaign_id=campaign_id,
                start_date=case.get("start_date"),
                end_date=case.get("end_date"),
                comparison_start_date=case.get("comparison_start_date"),
                comparison_end_date=case.get("comparison_end_date"),
            )
            try:
                response = service.analyze(request)
                actual_status = response.status.value
            except ResourceNotFoundError:
                response = None
                actual_status = "NOT_FOUND"
            errors: list[str] = []
            if actual_status != case["expected_status"]:
                errors.append(f"status={actual_status}")
            if response is not None:
                expected_type = case.get("expected_type")
                if expected_type and (
                    response.plan is None or response.plan.question_type.value != expected_type
                ):
                    errors.append("question_type")
                if case.get("expected_metrics") and (
                    response.plan is None
                    or not set(case["expected_metrics"])
                    <= {metric.value for metric in response.plan.metrics}
                ):
                    errors.append("metrics")
                if case.get("expected_direction") and (
                    response.plan is None
                    or response.plan.sort_direction is None
                    or response.plan.sort_direction.value != case["expected_direction"]
                ):
                    errors.append("direction")
                if case.get("expect_clarification") and not response.clarification_questions:
                    errors.append("clarification")
                if case.get("expect_hypotheses") and not response.hypotheses:
                    errors.append("hypotheses")
                if case.get("expected_error") != response.error_code:
                    if case.get("expected_error") is not None:
                        errors.append("error_code")
                if case.get("expected_fact_count") != len(response.facts):
                    if case.get("expected_fact_count") is not None:
                        errors.append(f"fact_count={len(response.facts)}")
                expected_fact = case.get("expected_fact")
                if expected_fact:
                    matched = [
                        fact for fact in response.facts if fact.label == expected_fact["label"]
                    ]
                    if not matched or matched[0].value != expected_fact["value"]:
                        errors.append("exact_fact")
                if case.get("fact_label_contains") and not any(
                    case["fact_label_contains"] in fact.label for fact in response.facts
                ):
                    errors.append("fact_order")
                if case.get("forbid_fact_text") and case["forbid_fact_text"] in str(response.facts):
                    errors.append("unsupported_fact")
                if response.facts and not all(fact.evidence_ids for fact in response.facts):
                    errors.append("evidence_link")
            if errors:
                failures.append(f"{case['id']}: {', '.join(errors)}")
            else:
                passed += 1
    engine.dispose()
    print(f"Mock Analyst golden dataset: {passed}/{len(cases)} passed")
    print("This deterministic Mock result is not real-LLM accuracy.")
    for failure in failures:
        print(f"FAIL {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
