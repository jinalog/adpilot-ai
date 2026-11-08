import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.domain.analyst_sql import CompiledQuery


class AnalystToolError(RuntimeError):
    code = "query_execution_failed"


class AnalystTimeoutError(AnalystToolError):
    code = "query_timeout"


@dataclass(frozen=True, slots=True)
class QueryResult:
    rows: list[dict[str, Any]]
    truncated: bool


class ReadOnlySQLExecutor:
    def __init__(
        self, engine: Engine, *, statement_timeout_ms: int, absolute_max_rows: int
    ) -> None:
        self.engine = engine
        self.statement_timeout_ms = min(max(statement_timeout_ms, 1), 30_000)
        self.absolute_max_rows = min(max(absolute_max_rows, 1), 500)

    def execute(self, query: CompiledQuery) -> QueryResult:
        effective_limit = min(query.row_limit, self.absolute_max_rows)
        parameters = dict(query.parameters)
        parameters["fetch_limit"] = effective_limit + 1
        with self.engine.connect() as connection:
            transaction = connection.begin()
            try:
                if connection.dialect.name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.execute(
                        text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                        {"timeout_ms": str(self.statement_timeout_ms)},
                    )
                else:
                    parameters = {
                        key: self._sqlite_value(value) for key, value in parameters.items()
                    }
                rows = [
                    dict(row) for row in connection.execute(text(query.sql), parameters).mappings()
                ]
                truncated = len(rows) > effective_limit
                transaction.rollback()
                return QueryResult(rows=rows[:effective_limit], truncated=truncated)
            except DBAPIError as exc:
                transaction.rollback()
                sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
                if sqlstate == "57014":
                    raise AnalystTimeoutError(
                        "analysis query exceeded the statement timeout"
                    ) from exc
                raise AnalystToolError("analysis query could not be executed") from exc
            except Exception:
                transaction.rollback()
                raise

    @staticmethod
    def _sqlite_value(value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return value.hex
        if isinstance(value, date):
            return value.isoformat()
        return value
