import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import traverse_scope

from app.schemas.analyst import AnalysisPlan, QuestionType

ALLOWED_TABLES = {"daily_ad_metrics", "campaigns"}
TABLE_COLUMNS = {
    "daily_ad_metrics": {
        "dataset_run_id",
        "campaign_id",
        "date",
        "impressions",
        "clicks",
        "conversions",
        "spend_krw",
        "revenue_krw",
    },
    "campaigns": {"id", "name", "synthetic_dataset_run_id"},
}
ALLOWED_COLUMNS = set().union(*TABLE_COLUMNS.values()) | {"period_label", "source_row_count"}
ALLOWED_FUNCTIONS = {"AND", "CASE", "COUNT", "IF", "OR", "SUM"}
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
                "COUNT(*) AS source_row_count",
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
            if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
                raise SQLSafetyError("wildcard access is not allowed")
        cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
        tables = {table.name.lower() for table in statement.find_all(exp.Table)}
        physical_tables = tables - cte_names
        if not physical_tables or not physical_tables <= ALLOWED_TABLES:
            raise SQLSafetyError("query references a forbidden table")
        if any(table.db or table.catalog for table in statement.find_all(exp.Table)):
            raise SQLSafetyError("schema-qualified tables are not allowed")
        table_aliases: dict[str, str] = {}
        for table in statement.find_all(exp.Table):
            name = table.name.lower()
            if name in ALLOWED_TABLES:
                table_aliases[table.alias_or_name.lower()] = name
        aliases = {alias.alias.lower() for alias in statement.find_all(exp.Alias) if alias.alias}
        for column in statement.find_all(exp.Column):
            name = column.name.lower()
            qualifier = column.table.lower() if column.table else ""
            if qualifier in table_aliases and name not in TABLE_COLUMNS[table_aliases[qualifier]]:
                raise SQLSafetyError(f"column {column.sql()} is not allowed for its table")
            if qualifier and qualifier not in set(table_aliases) | cte_names:
                raise SQLSafetyError(f"table alias {qualifier} is not allowed")
            if (
                not qualifier
                and name not in aliases
                and table_aliases
                and not any(name in TABLE_COLUMNS[table] for table in table_aliases.values())
            ):
                raise SQLSafetyError(f"column {name} is not allowed for referenced tables")
            if name not in ALLOWED_COLUMNS | aliases:
                raise SQLSafetyError(f"column {column.name} is not allowed")
        for function in statement.find_all(exp.Func):
            if function.sql_name().upper() not in ALLOWED_FUNCTIONS:
                raise SQLSafetyError(f"function {function.sql_name()} is not allowed")
        placeholders = {item.name for item in statement.find_all(exp.Placeholder)}
        self._validate_dataset_scopes(statement)
        limit = statement.args.get("limit")
        if (
            limit is None
            or not isinstance(limit.expression, exp.Placeholder)
            or limit.expression.name != "fetch_limit"
        ):
            raise SQLSafetyError("named row limit is required")
        if statement.args.get("offset") is not None:
            raise SQLSafetyError("OFFSET is not allowed")
        if isinstance(query, CompiledQuery):
            self._validate_compiled_contract(query, placeholders)

    @classmethod
    def _validate_dataset_scopes(cls, statement: exp.Select) -> None:
        metric_scope_found = False
        for scope in traverse_scope(statement):
            metric_tables = [
                table
                for table in scope.tables
                if isinstance(table, exp.Table) and table.name.lower() == "daily_ad_metrics"
            ]
            for table in metric_tables:
                metric_scope_found = True
                alias = table.alias_or_name.lower()
                where = scope.expression.args.get("where")
                predicates = cls._and_predicates(where.this) if where is not None else []
                if not any(cls._is_dataset_equality(item, alias) for item in predicates):
                    raise SQLSafetyError(
                        f"dataset_run_id equality scope is required for metric table {alias}"
                    )
        if not metric_scope_found:
            raise SQLSafetyError("query must read the physical metric table")

    @classmethod
    def _and_predicates(cls, expression: exp.Expression) -> list[exp.Expression]:
        if isinstance(expression, exp.And):
            return [
                *cls._and_predicates(expression.left),
                *cls._and_predicates(expression.right),
            ]
        return [expression]

    @staticmethod
    def _is_dataset_equality(expression: exp.Expression, table_alias: str) -> bool:
        if not isinstance(expression, exp.EQ):
            return False

        def is_column(value: exp.Expression) -> bool:
            return (
                isinstance(value, exp.Column)
                and value.name.lower() == "dataset_run_id"
                and (not value.table or value.table.lower() == table_alias)
            )

        def is_parameter(value: exp.Expression) -> bool:
            return isinstance(value, exp.Placeholder) and value.name == "dataset_run_id"

        return (is_column(expression.left) and is_parameter(expression.right)) or (
            is_parameter(expression.left) and is_column(expression.right)
        )

    @staticmethod
    def _validate_compiled_contract(query: CompiledQuery, placeholders: set[str]) -> None:
        parameter_keys = set(query.parameters)
        if placeholders != parameter_keys:
            missing = placeholders - parameter_keys
            extra = parameter_keys - placeholders
            raise SQLSafetyError(
                f"bind parameter mismatch; missing={sorted(missing)} extra={sorted(extra)}"
            )
        required = {"dataset_run_id", "start_date", "end_date", "fetch_limit"}
        if not required <= parameter_keys:
            raise SQLSafetyError("compiled query is missing required scope parameters")
        if query.row_limit < 1 or query.row_limit > ABSOLUTE_MAX_ROWS:
            raise SQLSafetyError("compiled row limit is outside the allowed range")
        if query.parameters["fetch_limit"] != query.row_limit + 1:
            raise SQLSafetyError("fetch_limit must equal row_limit + 1")


def safe_query_id() -> uuid.UUID:
    return uuid.uuid4()
