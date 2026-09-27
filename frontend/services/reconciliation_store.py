from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Literal
from uuid import uuid4

from app.core.config import settings


ReconciliationBusinessStatus = Literal[
    "posted",
    "reversed",
    "internal_transfer",
    "needs_review",
    "unposted",
]
_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


class ReconciliationNotFoundError(LookupError):
    pass


def _database_path() -> Path:
    return Path(settings.treasury_reconciliation_db).expanduser().resolve()


def _connect() -> sqlite3.Connection:
    database_path = _database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS treasury_reconciliation_reports (
            reconciliation_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            report_json TEXT NOT NULL
        )
        """
    )
    return connection


def _validate_id(reconciliation_id: str) -> str:
    cleaned = reconciliation_id.strip().lower()
    if not _ID_PATTERN.fullmatch(cleaned):
        raise ReconciliationNotFoundError("شناسه مغایرت‌گیری معتبر نیست.")
    return cleaned


def save_reconciliation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Store only the parsed result; the original bank file is never retained."""

    reconciliation_id = uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    stored_report = {
        **report,
        "reconciliation_id": reconciliation_id,
        "created_at": created_at,
    }
    serialized = json.dumps(stored_report, ensure_ascii=False)
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO treasury_reconciliation_reports (
                reconciliation_id,
                created_at,
                account_id,
                filename,
                report_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                reconciliation_id,
                created_at,
                int(stored_report["account"]["account_id"]),
                str(stored_report["file"]["filename"]),
                serialized,
            ),
        )
    return stored_report


def get_reconciliation_report(reconciliation_id: str) -> dict[str, Any]:
    cleaned = _validate_id(reconciliation_id)
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT report_json
            FROM treasury_reconciliation_reports
            WHERE reconciliation_id = ?
            """,
            (cleaned,),
        ).fetchone()
    if row is None:
        raise ReconciliationNotFoundError("گزارش مغایرت‌گیری پیدا نشد.")
    return json.loads(row["report_json"])


def get_reconciliation_summary(reconciliation_id: str) -> dict[str, Any]:
    report = get_reconciliation_report(reconciliation_id)
    return {
        "status": "success",
        "reconciliation_id": report["reconciliation_id"],
        "created_at": report["created_at"],
        "file": report["file"],
        "account": report["account"],
        "bank_account": report.get("bank_account", report["account"]),
        "matching_rules": report["matching_rules"],
        "summary": report["summary"],
    }


def get_reconciliation_rows(
    reconciliation_id: str,
    business_status: ReconciliationBusinessStatus,
    limit: int = 20,
) -> dict[str, Any]:
    report = get_reconciliation_report(reconciliation_id)
    safe_limit = max(1, min(int(limit), 100))
    rows = [
        row
        for row in report["rows"]
        if row["business_status"] == business_status
    ]
    return {
        "status": "success",
        "reconciliation_id": report["reconciliation_id"],
        "business_status": business_status,
        "business_status_fa": {
            "posted": "سندخورده",
            "reversed": "برگشت/خنثی‌شده",
            "internal_transfer": "انتقال داخلی شرکت",
            "needs_review": "نیازمند بررسی",
            "unposted": "بدون سند",
        }[business_status],
        "total_count": len(rows),
        "returned_count": min(len(rows), safe_limit),
        "rows": rows[:safe_limit],
    }
