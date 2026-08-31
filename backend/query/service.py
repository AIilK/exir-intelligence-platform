from typing import Any

from sqlalchemy.orm import Session

from app.models.datasource.connection import Connection
from app.query.executor import QueryExecutor
from app.query.query_plan import QueryPlanner
from app.query.schema_context import SchemaContextBuilder
from app.query.schema_validator import SchemaValidator
from app.query.sql_generator import SQLGenerator
from app.query.sql_validator import SQLValidator
from app.llm.mock_client import MockLLMClient


class QueryService:
    """Shared, read-only natural-language-to-SQL pipeline."""

    def __init__(self, llm_client: Any | None = None):
        self.llm_client = llm_client or MockLLMClient()
        self.sql_generator = SQLGenerator(llm_client=self.llm_client)
        self.sql_validator = SQLValidator()
        self.schema_validator = SchemaValidator()
        self.query_planner = QueryPlanner()

    def _context(self, db: Session, connection_id: int, question: str) -> dict[str, Any]:
        return SchemaContextBuilder(db).build(
            connection_id=connection_id,
            question=question,
        )

    def build_query_plan(
        self,
        db: Session,
        connection_id: int,
        question: str,
    ) -> dict[str, Any]:
        context = self._context(db, connection_id, question)
        if not context.get("tables"):
            return {
                "success": False,
                "question": question,
                "tables": [],
                "relationships": [],
                "error": "No matching tables found",
            }

        plan = self.query_planner.build_plan(context)
        return {
            "success": True,
            "question": question,
            "tables": plan.get("tables", []),
            "relationships": plan.get("relationships", []),
            "error": None,
        }

    # Backwards-compatible alias used by older callers.
    create_query_plan = build_query_plan

    def generate_sql(
        self,
        db: Session,
        connection_id: int,
        question: str,
    ) -> dict[str, Any]:
        context = self._context(db, connection_id, question)
        if not context.get("tables"):
            return {
                "success": False,
                "question": question,
                "sql": "",
                "error": "No matching table found",
            }

        sql = self.sql_generator.generate(context=context)

        sql_validation = self.sql_validator.validate(sql)
        if not sql_validation["valid"]:
            return {
                "success": False,
                "question": question,
                "sql": sql,
                "error": sql_validation["reason"],
            }

        schema_validation = self.schema_validator.validate(sql=sql, context=context)
        if not schema_validation["valid"]:
            return {
                "success": False,
                "question": question,
                "sql": sql,
                "error": schema_validation["reason"],
            }

        return {
            "success": True,
            "question": question,
            "sql": sql,
            "error": None,
        }

    def execute_sql(
        self,
        db: Session,
        connection_id: int,
        sql: str,
    ) -> dict[str, Any]:
        validation = self.sql_validator.validate(sql)
        if not validation["valid"]:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": validation["reason"],
            }

        connection = (
            db.query(Connection)
            .filter(Connection.id == connection_id)
            .first()
        )
        if connection is None:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": "Connection not found",
            }

        try:
            executor = QueryExecutor(connection.connection_config)
            result = executor.execute(sql)
            return {**result, "error": None}
        except Exception as exc:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": str(exc),
            }

    def execute_question(
        self,
        db: Session,
        connection_id: int,
        question: str,
    ) -> dict[str, Any]:
        generated = self.generate_sql(
            db=db,
            connection_id=connection_id,
            question=question,
        )
        if not generated["success"]:
            return {
                "success": False,
                "question": question,
                "sql": generated.get("sql", ""),
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": generated.get("error"),
            }

        executed = self.execute_sql(
            db=db,
            connection_id=connection_id,
            sql=generated["sql"],
        )
        return {
            "success": bool(executed.get("success")),
            "question": question,
            "sql": generated["sql"],
            "columns": executed.get("columns", []),
            "rows": executed.get("rows", []),
            "row_count": executed.get("row_count", 0),
            "error": executed.get("error"),
        }
