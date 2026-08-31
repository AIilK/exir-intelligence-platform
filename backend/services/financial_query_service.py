from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.services.treasury_service import _engine


ALLOWED_TABLES = {
    "RPA3.Receipt",
    "RPA3.ReceiptItem",
    "RPA3.Payment",
    "RPA3.PaymentItem",
    "RPA3.ReceivableNote",
    "RPA3.PayableNote",
    "RPA3.BankAccount",
    "RPA3.Bank",
    "RPA3.BankBranch",
    "FIN3.Account",
    "FIN3.Transaction",
    "FIN3.DL",
    "GNR3.Currency",
}

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|MERGE|EXEC(?:UTE)?|"
    r"GRANT|REVOKE|DENY|BACKUP|RESTORE|DBCC|BULK|OPENROWSET|OPENDATASOURCE|"
    r"INTO|WAITFOR|USE)\b",
    re.IGNORECASE,
)
TABLE_REFERENCE = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:\[[^\]]+\]|[A-Za-z0-9_]+)\."
    r"(?:\[[^\]]+\]|[A-Za-z0-9_]+))",
    re.IGNORECASE,
)


class FinancialQueryError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedFinancialQuery:
    sql: str
    explanation: str
    assumptions: list[str]


def _normalise_identifier(value: str) -> str:
    return value.replace("[", "").replace("]", "")


def _schema_metadata(engine: Engine) -> list[dict[str, Any]]:
    conditions = []
    parameters: dict[str, Any] = {}
    for index, qualified_name in enumerate(sorted(ALLOWED_TABLES)):
        schema_name, table_name = qualified_name.split(".", 1)
        conditions.append(
            f"(schema_name = :schema_{index} AND table_name = :table_{index})"
        )
        parameters[f"schema_{index}"] = schema_name
        parameters[f"table_{index}"] = table_name
    query = text(
        f"""
        SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS table_name,
               COLUMN_NAME AS column_name, DATA_TYPE AS data_type
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE {' OR '.join(conditions)}
        ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, parameters).mappings().all()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row['schema_name']}.{row['table_name']}"
        grouped.setdefault(key, {"table": key, "columns": []})["columns"].append(
            {"name": row["column_name"], "type": row["data_type"]}
        )
    return list(grouped.values())


def _extract_json(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise FinancialQueryError("مدل پاسخ SQL معتبر تولید نکرد.") from exc
    if not isinstance(payload, dict):
        raise FinancialQueryError("ساختار پاسخ مدل معتبر نیست.")
    return payload


def _add_top_limit(sql: str, max_rows: int) -> str:
    if re.search(r"^\s*SELECT\s+(?:DISTINCT\s+)?TOP\s*\(", sql, re.IGNORECASE):
        return sql
    return re.sub(
        r"^\s*SELECT\s+(DISTINCT\s+)?",
        lambda match: f"SELECT {match.group(1) or ''}TOP ({max_rows}) ",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )


def validate_financial_sql(sql: str) -> str:
    cleaned = str(sql or "").strip().rstrip(";").strip()
    if not re.match(r"^SELECT\b", cleaned, re.IGNORECASE):
        raise FinancialQueryError("فقط کوئری SELECT مجاز است.")
    if ";" in cleaned or "--" in cleaned or "/*" in cleaned:
        raise FinancialQueryError("چند دستور یا Comment در SQL مجاز نیست.")
    forbidden = FORBIDDEN.search(cleaned)
    if forbidden:
        raise FinancialQueryError(f"عبارت غیرمجاز در SQL: {forbidden.group(1)}")
    references = {
        _normalise_identifier(item) for item in TABLE_REFERENCE.findall(cleaned)
    }
    if not references:
        raise FinancialQueryError("هیچ جدول مجازی در SQL پیدا نشد.")
    disallowed = sorted(references - ALLOWED_TABLES)
    if disallowed:
        raise FinancialQueryError(
            "جدول خارج از محدوده مالی غیرمجاز است: " + ", ".join(disallowed)
        )
    return _add_top_limit(cleaned, settings.financial_query_max_rows)


def generate_financial_sql(
    question: str,
    *,
    engine: Engine | None = None,
) -> GeneratedFinancialQuery:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise FinancialQueryError("سؤال مالی نمی‌تواند خالی باشد.")
    if not settings.openai_api_key:
        raise FinancialQueryError("OPENAI_API_KEY تنظیم نشده است.")
    selected_engine = _engine(engine)
    metadata = _schema_metadata(selected_engine)
    if not metadata:
        raise FinancialQueryError("Metadata جداول مالی مجاز پیدا نشد.")
    prompt = f"""
You generate one safe read-only Microsoft SQL Server query for Rahkaran ERP.
Return JSON only with keys: sql, explanation_fa, assumptions_fa.
Rules:
- SQL must start with SELECT and contain one statement only.
- Use only tables and columns present in metadata.
- Never invent a code/state meaning. If the question requires an unknown business
  code, put the limitation in assumptions and avoid filtering by that code.
- Use explicit aliases, qualified columns, and deterministic ORDER BY.
- Never use SELECT *, cross-database names, system objects, temp tables or comments.
- Dates are stored as Gregorian dates. GETDATE() is allowed.
- Limit detail output with TOP ({settings.financial_query_max_rows}).
- ApproveState=3 means approved only for RPA3 Receipt and Payment in this project.
- CurrencyRef=1 is the configured operational currency ({settings.treasury_operational_currency_name}).

Question in Persian:
{cleaned_question}

Allowed metadata:
{json.dumps(metadata, ensure_ascii=False)}
"""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise FinancialQueryError(
            "بسته openai نصب نشده است؛ pip install openai را اجرا کنید."
        ) from exc
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(model=settings.openai_model, input=prompt)
    payload = _extract_json(response.output_text)
    safe_sql = validate_financial_sql(str(payload.get("sql") or ""))
    assumptions = payload.get("assumptions_fa") or []
    if isinstance(assumptions, str):
        assumptions = [assumptions]
    return GeneratedFinancialQuery(
        sql=safe_sql,
        explanation=str(payload.get("explanation_fa") or ""),
        assumptions=[str(item) for item in assumptions],
    )


def ask_financial_data(
    question: str,
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    selected_engine = _engine(engine)
    generated = generate_financial_sql(question, engine=selected_engine)
    with selected_engine.connect() as connection:
        raw_connection = getattr(connection.connection, "driver_connection", None)
        if raw_connection is not None:
            raw_connection.timeout = settings.financial_query_timeout_seconds
        rows = connection.execute(text(generated.sql)).mappings().fetchmany(
            settings.financial_query_max_rows
        )
    return {
        "status": "success",
        "report_type": "safe_financial_query",
        "question": question,
        "sql": generated.sql,
        "explanation": generated.explanation,
        "assumptions": generated.assumptions,
        "row_count": len(rows),
        "is_truncated": len(rows) >= settings.financial_query_max_rows,
        "rows": [dict(row) for row in rows],
        "safety": {
            "read_only": True,
            "allowed_tables_only": True,
            "max_rows": settings.financial_query_max_rows,
            "timeout_seconds": settings.financial_query_timeout_seconds,
        },
    }
