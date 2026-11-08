import os
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.agents.analyst_provider import MockAnalystProvider
from app.agents.performance_analyst import PerformanceAnalystWorkflow
from app.core.config import get_settings
from app.db.models.campaign import Campaign
from app.domain.analyst_sql import (
    CompiledQuery,
    DeterministicSQLCompiler,
    SQLASTValidator,
    SQLSafetyError,
)
from app.domain.synthetic_analytics import SyntheticDatasetConfig, build_synthetic_dataset
from app.infrastructure.analyst_executor import (
    AnalystTimeoutError,
    AnalystToolError,
    ReadOnlySQLExecutor,
)
from app.infrastructure.analytics_repository import AnalyticsRepository
from app.schemas.analyst import (
    AnalysisMetric,
    AnalysisPlan,
    AnalystQuestionRequest,
    GroupingUnit,
    QuestionType,
)
from app.services.analyst_service import PerformanceAnalystService
from app.services.analytics_service import SyntheticDatasetService

pytestmark = pytest.mark.integration


@pytest.fixture
def analyst_engine(monkeypatch: pytest.MonkeyPatch) -> Generator[Engine, None, None]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not urlparse(database_url).path.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must target a database whose name ends with '_test'")
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()


def seed(engine: Engine, *, name: str = "phase4-integration", seed_value: int = 20261107):
    plan = build_synthetic_dataset(SyntheticDatasetConfig(name=name, seed=seed_value))
    with Session(engine) as session:
        repository = AnalyticsRepository(session)
        existing = repository.get_dataset_by_name(name)
        service = SyntheticDatasetService(repository)
        if existing is None:
            service.create(plan)
        else:
            service.create(plan, replace_dataset_id=existing.id)
    return plan


def service(engine: Engine, *, timeout_ms: int = 2_500) -> PerformanceAnalystService:
    session = Session(engine)
    workflow = PerformanceAnalystWorkflow(
        MockAnalystProvider(),
        DeterministicSQLCompiler(),
        SQLASTValidator(),
        ReadOnlySQLExecutor(engine, statement_timeout_ms=timeout_ms, absolute_max_rows=500),
        timeout_seconds=1,
        max_retries=0,
    )
    result = PerformanceAnalystService(AnalyticsRepository(session), workflow)
    result._integration_session = session  # type: ignore[attr-defined]
    return result


def test_postgres_read_only_analyst_returns_exact_fact_and_dataset_scope(
    analyst_engine: Engine,
) -> None:
    first = seed(analyst_engine)
    seed(analyst_engine, name="phase4-other", seed_value=20261108)
    analyst = service(analyst_engine)
    try:
        response = analyst.analyze(
            AnalystQuestionRequest(
                dataset_run_id=first.id,
                question="전체 impressions와 CTR을 요약해 주세요.",
            )
        )
    finally:
        analyst._integration_session.close()  # type: ignore[attr-defined]

    facts = {fact.label: fact.value for fact in response.facts}
    assert response.status == "READY"
    assert facts["impressions"] == 1_195_362
    assert facts["ctr"] == pytest.approx(63_725 / 1_195_362)
    assert {item.dataset_run_id for item in response.evidence} == {first.id}
    assert all("anomaly_truth" not in item.query_fingerprint for item in response.evidence)


def test_postgres_read_only_transaction_rejects_write_and_rolls_back(
    analyst_engine: Engine,
) -> None:
    plan = seed(analyst_engine)
    executor = ReadOnlySQLExecutor(
        analyst_engine, statement_timeout_ms=2_500, absolute_max_rows=500
    )
    before = None
    with Session(analyst_engine) as session:
        before = session.scalar(select(func.count(Campaign.id)))
    write = CompiledQuery(
        sql=(
            "UPDATE campaigns SET name = 'forbidden' "
            "WHERE synthetic_dataset_run_id = :dataset_run_id"
        ),
        parameters={"dataset_run_id": plan.id},
        row_limit=1,
        fingerprint="unsafe-test-only",
    )

    with pytest.raises(AnalystToolError):
        executor.execute(write)
    with Session(analyst_engine) as session:
        assert session.scalar(select(func.count(Campaign.id))) == before
        forbidden_count = session.scalar(
            select(func.count(Campaign.id)).where(Campaign.name == "forbidden")
        )
        assert forbidden_count == 0


def test_postgres_statement_timeout_occurs_while_table_is_locked(analyst_engine: Engine) -> None:
    plan = seed(analyst_engine)
    query = DeterministicSQLCompiler().compile(
        AnalysisPlan(
            question_type=QuestionType.KPI_SUMMARY,
            dataset_run_id=plan.id,
            metrics=[AnalysisMetric.CTR],
            start_date=plan.config.start_date,
            end_date=plan.end_date,
            grouping=GroupingUnit.OVERALL,
        )
    )
    executor = ReadOnlySQLExecutor(analyst_engine, statement_timeout_ms=50, absolute_max_rows=500)
    with analyst_engine.connect() as locker:
        transaction = locker.begin()
        locker.exec_driver_sql("LOCK TABLE daily_ad_metrics IN ACCESS EXCLUSIVE MODE")
        with pytest.raises(AnalystTimeoutError):
            executor.execute(query)
        transaction.rollback()


def test_postgres_row_limit_is_explicitly_truncated(analyst_engine: Engine) -> None:
    plan = seed(analyst_engine)
    query = DeterministicSQLCompiler().compile(
        AnalysisPlan(
            question_type=QuestionType.DAILY_TREND,
            dataset_run_id=plan.id,
            metrics=[AnalysisMetric.CTR],
            start_date=plan.config.start_date,
            end_date=plan.end_date,
            grouping=GroupingUnit.DAY,
            limit=5,
        )
    )
    SQLASTValidator().validate(query)
    result = ReadOnlySQLExecutor(
        analyst_engine, statement_timeout_ms=2_500, absolute_max_rows=500
    ).execute(query)
    assert len(result.rows) == 5
    assert result.truncated is True
    assert [row["date"] for row in result.rows] == sorted(row["date"] for row in result.rows)


def test_truth_table_and_write_sql_never_pass_ast_boundary(analyst_engine: Engine) -> None:
    del analyst_engine
    validator = SQLASTValidator()
    with pytest.raises(SQLSafetyError):
        validator.validate(
            "SELECT id FROM anomaly_truth_labels "
            "WHERE dataset_run_id=:dataset_run_id LIMIT :fetch_limit"
        )
    with pytest.raises(SQLSafetyError):
        validator.validate("DELETE FROM daily_ad_metrics WHERE dataset_run_id=:dataset_run_id")
