import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.schemas.analyst import AnalysisPlan, QuestionType

ALLOWED_TABLES = {"daily_ad_metrics", "campaigns"}
ALLOWED_COLUMNS = {
    "id",
    "name",
    "synthetic_dataset_run_id",
    "dataset_run_id",
    "campaign_id",
    "date",
    "impressions",
    "clicks",
    "conversions",
    "spend_krw",
    "revenue_krw",
    "period_label",
}
ALLOWED_FUNCTIONS = {"AND", "CASE", "IF", "OR", "SUM"}
FORBIDDEN_NODE_NAMES = {
    "Alter",
    "Command",
    "Copy",
    "Create",
    "Delete",
    "Drop",
    "Insert",
    "Lock",
    "Merge",
    "Set",
    "Transaction",
    "TruncateTable",
    "Update",
}
ABSOLUTE_MAX_ROWS = 500


class SQLSafetyError(ValueError):
    code = "sql_validation_blocked"


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    sql: str
    parameters: dict[str, Any]
    row_limit: int
    fingerprint: str


class DeterministicSQLCompiler:
    def compile(self, plan: AnalysisPlan) -> CompiledQuery:
        if plan.question_type is QuestionType.KPI_SUMMARY:
            sql = self._summary_sql(plan.campaign_id is not None)
        elif plan.question_type is QuestionType.PERIOD_COMPARISON:
            sql = self._period_comparison_sql(plan.campaign_id is not None)
        elif plan.question_type is QuestionType.DAILY_TREND:
            sql = self._daily_sql(plan.campaign_id is not None)
        else:
            sql = self._grouped_sql(
                by_day=plan.question_type is QuestionType.ANOMALY_LOOKUP,
                campaign_filter=plan.campaign_id is not None,
            )
        execution_limit = (
            ABSOLUTE_MAX_ROWS
            if plan.question_type in {QuestionType.RANK_CAMPAIGNS, QuestionType.ANOMALY_LOOKUP}
            else min(plan.limit, ABSOLUTE_MAX_ROWS)
        )
        parameters: dict[str, Any] = {
            "dataset_run_id": plan.dataset_run_id,
            "start_date": (
                plan.start_date - timedelta(days=7)
                if plan.question_type is QuestionType.ANOMALY_LOOKUP
                else plan.start_date
            ),
            "end_date": plan.end_date,
            "fetch_limit": execution_limit + 1,
        }
        if plan.campaign_id is not None:
            parameters["campaign_id"] = plan.campaign_id
        if plan.question_type is QuestionType.PERIOD_COMPARISON:
            parameters["comparison_start_date"] = plan.comparison_start_date
            parameters["comparison_end_date"] = plan.comparison_end_date
        normalized = " ".join(sql.split())
        return CompiledQuery(
            sql=sql,
            parameters=parameters,
            row_limit=execution_limit,
            fingerprint=hashlib.sha256(normalized.encode()).hexdigest()[:16],
        )

    @staticmethod
    def _totals_select(prefix: str = "m") -> str:
        return ",\n".join(
            [
                f"SUM({prefix}.impressions) AS impressions",
                f"SUM({prefix}.clicks) AS clicks",
                f"SUM({prefix}.conversions) AS conversions",
                f"SUM({prefix}.spend_krw) AS spend_krw",
                f"SUM({prefix}.revenue_krw) AS revenue_krw",
            ]
        )

    def _summary_sql(self, campaign_filter: bool) -> str:
        campaign_clause = "\n  AND m.campaign_id = :campaign_id" if campaign_filter else ""
        return f"""SELECT
{self._totals_select()}
FROM daily_ad_metrics AS m
WHERE m.dataset_run_id = :dataset_run_id
  AND m.date BETWEEN :start_date AND :end_date{campaign_clause}
LIMIT :fetch_limit"""

    def _grouped_sql(self, *, by_day: bool, campaign_filter: bool) -> str:
        date_select = ",\n  m.date" if by_day else ""
        date_group = ", m.date" if by_day else ""
        date_order = "m.date, " if by_day else ""
        campaign_clause = "\n  AND m.campaign_id = :campaign_id" if campaign_filter else ""
        return f"""SELECT
  m.campaign_id,
  c.name{date_select},
  {self._totals_select()}
FROM daily_ad_metrics AS m
JOIN campaigns AS c
  ON c.id = m.campaign_id
 AND c.synthetic_dataset_run_id = m.dataset_run_id
WHERE m.dataset_run_id = :dataset_run_id
  AND m.date BETWEEN :start_date AND :end_date{campaign_clause}
GROUP BY m.campaign_id, c.name{date_group}
ORDER BY {date_order}c.name, m.campaign_id
LIMIT :fetch_limit"""

    def _daily_sql(self, campaign_filter: bool) -> str:
        campaign_clause = "\n  AND m.campaign_id = :campaign_id" if campaign_filter else ""
        return f"""SELECT
  m.date,
  {self._totals_select()}
FROM daily_ad_metrics AS m
WHERE m.dataset_run_id = :dataset_run_id
  AND m.date BETWEEN :start_date AND :end_date{campaign_clause}
GROUP BY m.date
ORDER BY m.date
LIMIT :fetch_limit"""

    def _period_comparison_sql(self, campaign_filter: bool) -> str:
        campaign_clause = "\n  AND m.campaign_id = :campaign_id" if campaign_filter else ""
        period_case = (
            "CASE WHEN m.date BETWEEN :start_date AND :end_date "
            "THEN 'current' ELSE 'comparison' END"
        )
        return f"""SELECT
  {period_case} AS period_label,
  {self._totals_select()}
FROM daily_ad_metrics AS m
WHERE m.dataset_run_id = :dataset_run_id
  AND ((m.date BETWEEN :start_date AND :end_date)
    OR (m.date BETWEEN :comparison_start_date AND :comparison_end_date)){campaign_clause}
GROUP BY {period_case}
ORDER BY period_label
LIMIT :fetch_limit"""


class SQLASTValidator:
    def validate(self, query: CompiledQuery | str) -> None:
        sql = query.sql if isinstance(query, CompiledQuery) else query
        if re.search(r"--|/\*|\*/", sql):
            raise SQLSafetyError("SQL comments are not allowed")
        try:
            statements = parse(sql, read="postgres")
        except ParseError as exc:
            raise SQLSafetyError("SQL could not be parsed") from exc
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise SQLSafetyError("only one SELECT statement is allowed")
        statement = statements[0]
        if statement.args.get("into") is not None:
            raise SQLSafetyError("SELECT INTO is not allowed")
        if statement.args.get("locks") or statement.args.get("lock"):
            raise SQLSafetyError("locking clauses are not allowed")
        for node in statement.walk():
            if type(node).__name__ in FORBIDDEN_NODE_NAMES:
                raise SQLSafetyError(f"{type(node).__name__} is not allowed")
            if isinstance(node, exp.Star):
                raise SQLSafetyError("wildcard access is not allowed")
        cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
        tables = {table.name.lower() for table in statement.find_all(exp.Table)}
        physical_tables = tables - cte_names
        if not physical_tables or not physical_tables <= ALLOWED_TABLES:
            raise SQLSafetyError("query references a forbidden table")
        if any(table.db or table.catalog for table in statement.find_all(exp.Table)):
            raise SQLSafetyError("schema-qualified tables are not allowed")
        aliases = {alias.alias.lower() for alias in statement.find_all(exp.Alias) if alias.alias}
        for column in statement.find_all(exp.Column):
            if column.name.lower() not in ALLOWED_COLUMNS | aliases:
                raise SQLSafetyError(f"column {column.name} is not allowed")
        for function in statement.find_all(exp.Func):
            if function.sql_name().upper() not in ALLOWED_FUNCTIONS:
                raise SQLSafetyError(f"function {function.sql_name()} is not allowed")
        placeholders = {item.name for item in statement.find_all(exp.Placeholder)}
        if "dataset_run_id" not in placeholders:
            raise SQLSafetyError("dataset_run_id bind parameter is required")
        scoped_columns = {column.name.lower() for column in statement.find_all(exp.Column)}
        if "dataset_run_id" not in scoped_columns:
            raise SQLSafetyError("dataset_run_id scope is required")
        if statement.args.get("limit") is None or "fetch_limit" not in placeholders:
            raise SQLSafetyError("named row limit is required")


def safe_query_id() -> uuid.UUID:
    return uuid.uuid4()
