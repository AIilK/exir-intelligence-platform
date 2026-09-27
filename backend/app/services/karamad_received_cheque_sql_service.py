from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from threading import RLock
import time
import re
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.utils.jalali import format_jalali_date


def _as_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _date(v: Any) -> str | None:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v) if v else None


def _jalali(v: Any) -> str | None:
    if not v:
        return None
    try:
        if isinstance(v, datetime):
            return format_jalali_date(v.date())
        if isinstance(v, date):
            return format_jalali_date(v)
    except Exception:
        pass
    return None


@lru_cache(maxsize=1)
def get_karamad_sql_engine() -> Engine:
    if not settings.KARAMAD_SQLSERVER_PASSWORD:
        raise RuntimeError("KARAMAD_SQLSERVER_PASSWORD is not configured in .env")
    trust = "yes" if settings.KARAMAD_SQLSERVER_TRUST_CERTIFICATE else "no"
    conn = (
        f"DRIVER={{{settings.KARAMAD_SQLSERVER_DRIVER}}};"
        f"SERVER={settings.KARAMAD_SQLSERVER_SERVER};"
        f"DATABASE={settings.KARAMAD_SQLSERVER_DATABASE};"
        f"UID={settings.KARAMAD_SQLSERVER_USERNAME};"
        f"PWD={settings.KARAMAD_SQLSERVER_PASSWORD};"
        "Encrypt=yes;"
        f"TrustServerCertificate={trust};"
        "ApplicationIntent=ReadOnly;"
    )
    return create_engine(
        "mssql+pyodbc:///?odbc_connect=" + quote_plus(conn),
        pool_pre_ping=True,
        pool_recycle=1800,
    )


_RECEIVED_CACHE_TTL_SECONDS = 180
_received_cache_lock = RLock()
_received_cache: dict[str, Any] = {"loaded_at": 0.0, "rows": None, "count": 0, "total_amount_rial": 0.0}

KARAMAD_MAIN_STATUS_REFS = frozenset({1, 2, 3, 6, 7, 10})
KARAMAD_MAIN_STATUS_BUCKETS = frozenset({
    "غیر قطعی", "نزد صندوق", "واگذار شده", "برگشت نزد صندوق",
    "برگشتی نزد مشتری", "برگشتی نزد صندوق",
})


class KaramadReceivedChequeSQLService:
    """Read-only live KarAmand received-cheque source.

    We intentionally read the full ListData view first and apply the portfolio
    business rules in Python. This keeps the filtering rules in our backend,
    rather than baking assumptions into a vendor SQL query.
    """

    BASE_QUERY = text("""
        SELECT
            [inx], [Code], [DueDate], [BookDate], [Price], [Bank], [AccountNo],
            [Behalf], [Description], [Confirmed], [StatusName], [SLName], [DLName],
            [DL2Name], [DL3Name], [DLRef], [DLCode], [FiscalYear], [BranchRef], [BranchName],
            [StatusRef], [BankIDRef], [BranchIDRef], [Serial], [BankCode], [BankName],
            [BankBranchCode], [BankBranchName], [isInclusion], [isOpening],
            [OpeningBank], [ReceiptDate], [ReturnChequeRef], [CustomerDebtRef],
            [PayoffMultiRef], [InquiryCode], [DueDiff], [ReceiptDiff],
            [LastSLName], [LastDLName], [LastDL2Name], [LastDL3Name], [ExitRef],
            [ExitCode], [FactorFDateE], [isSent], [AssignCode], [AssignName],
            [AssignmentDate], [IsSystemCheque], [OwnerName], [OwnerIDCode],
            [FactorDRef], [IsMarket], [MarketPurserRef], [Nonbranchable],
            [ReturnReasonRef], [ReturnReasonName], [IsECheque], [ExitDisDateE],
            [ExitDateE], [AssignRef]
        FROM dbo.[vwChequeDList]
        WHERE [StatusRef] IN (1, 2, 3, 6, 7, 10)
          AND ISNULL([StatusName], N'') NOT LIKE N'%وصول شده%'
          AND ISNULL([StatusName], N'') NOT LIKE N'%وصول‌شده%'
    """)

    def fetch_all(self, limit: int = 200_000) -> list[dict[str, Any]]:
        # IMPORTANT: `limit` is kept for API compatibility, but the live source
        # is intentionally NOT truncated. We need the complete Karamad portfolio
        # so totals never change just because the UI/backend requested a page.
        with get_karamad_sql_engine().connect() as conn:
            rows = conn.execute(self.BASE_QUERY).mappings().fetchall()
        return [self._normalize(dict(row)) for row in rows]

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        status = str(row.get("StatusName") or "").strip()
        status_norm = status.replace("ي", "ی").replace("ك", "ک")
        record = {
            "cheque_id": row.get("inx"),
            "cheque_code": str(row.get("Code") or "").strip(),
            "amount": _as_float(row.get("Price")),
            "due_date": _date(row.get("DueDate")),
            "due_date_jalali": _jalali(row.get("DueDate")),
            "days_to_due": (row.get("DueDate").date() - date.today()).days if isinstance(row.get("DueDate"), datetime) else ((row.get("DueDate") - date.today()).days if isinstance(row.get("DueDate"), date) else None),
            "book_date": _date(row.get("BookDate")),
            "book_date_jalali": _jalali(row.get("BookDate")),
            "receipt_date": _date(row.get("ReceiptDate")),
            "receipt_date_jalali": _jalali(row.get("ReceiptDate")),
            "status_ref": row.get("StatusRef"),
            "cheque_status": status_norm,
            "state_label": status_norm,
            "bank_name": row.get("BankName") or row.get("Bank"),
            "bank": row.get("Bank"),
            "bank_code": row.get("BankCode"),
            "bank_branch_code": row.get("BankBranchCode"),
            "bank_branch_name": row.get("BankBranchName"),
            "account_number": row.get("AccountNo"),
            "serial_number": row.get("Serial"),
            "sayad_number": None,
            "counterpart_name": row.get("DLName"),
            "counterpart_code": row.get("DLCode"),
            "counterpart_ref": row.get("DLRef"),
            "customer_name": row.get("DLName"),
            "customer_code": row.get("DLCode"),
            "customer_id": row.get("DLRef"),
            "branch_ref": row.get("BranchRef"),
            "branch_name": row.get("BranchName"),
            "description": row.get("Description"),
            "return_reason": row.get("ReturnReasonName"),
            "source_system": "karamad",
            "source_label": "کارآمد",
        }
        return record

    @staticmethod
    def _is_received_candidate(row: dict[str, Any]) -> bool:
        # The view is shared by cheque flows. Customer-side received cheques are
        # identified by having a receivable/customer detail and no payable exit.
        # This is deliberately conservative; status/holding filtering is separate.
        return bool(row.get("counterpart_ref") or row.get("customer_id")) and not bool(row.get("ExitRef"))

    @staticmethod
    def status_bucket(status: str, status_ref: Any = None) -> str | None:
        """Map Karamad received-cheque status using StatusRef first.

        StatusRef is the authoritative discriminator for the six management
        buckets. Text is only a fallback for older/partial rows. In particular,
        StatusRef=7 and StatusRef=10 must not be collapsed into the same bucket.
        """
        raw = "" if status is None else str(status)
        text = raw.replace("ي", "ی").replace("ك", "ک").strip()

        # StatusRef is authoritative when it exists. This prevents a blank
        # StatusName on a settled/other status from being misclassified as
        # non-certain. StatusRef=1 is the official non-certain bucket.
        try:
            ref = int(status_ref) if status_ref is not None and str(status_ref).strip() else None
        except (TypeError, ValueError):
            ref = None
        ref_map = {
            1: "غیر قطعی",
            2: "نزد صندوق",
            3: "واگذار شده",
            6: "برگشت نزد صندوق",
            7: "برگشتی نزد مشتری",
            10: "برگشتی نزد صندوق",
        }
        # A cheque may carry an older holding status such as 6 while its
        # displayed/current status text also contains «برگشتی وصول شده».
        # That means it must not remain in «برگشت نزد صندوق». The textual
        # terminal outcome wins over the historical/ref bucket.
        if "وصول شده" in text or "وصول‌شده" in text:
            return None

        if ref in ref_map:
            return ref_map[ref]

        # Only use the empty StatusName rule when StatusRef is genuinely
        # unavailable. This keeps legacy rows compatible without allowing
        # StatusRef 4/5/8/9/11 to leak into the main portfolio.
        if ref is None and (not text or text in {"وضعیت نامشخص", "نامشخص"}):
            return "غیر قطعی"

        compact = re.sub(r"\s+", " ", text)
        if "برگشت" in compact or "برگشتی" in compact or "واخواست" in compact:
            if "مشتری" in compact or "بدهکار" in compact or "طرف حساب" in compact:
                return "برگشت نزد مشتری"
            return "برگشت نزد صندوق"
        if "واگذار" in compact and ("شده" in compact or "در جریان وصول" in compact):
            return "واگذار شده"
        if "نزد صندوق" in compact or "نزد شرکت" in compact:
            return "نزد صندوق"
        if "غیر قطعی" in compact or "غیرقطعی" in compact:
            return "غیر قطعی"

        # Preserve an unknown non-empty source status; do NOT call it non-certain.
        return "سایر"

    def _load_received_snapshot(self, limit: int = 200_000) -> tuple[list[dict[str, Any]], int, float]:
        """Load the COMPLETE received portfolio once and reuse it for filters.

        The cache is a performance layer only: it never changes the source rows,
        applies no row-count limit, and expires after a short TTL so live data
        remains fresh.
        """
        now = time.monotonic()
        with _received_cache_lock:
            cached = _received_cache.get("rows")
            if cached is not None and now - float(_received_cache.get("loaded_at", 0.0)) < _RECEIVED_CACHE_TTL_SECONDS:
                return cached, int(_received_cache.get("count", len(cached))), float(_received_cache.get("total_amount_rial", 0.0))

            raw = self.fetch_all(limit=limit)
            out: list[dict[str, Any]] = []
            for row in raw:
                if not self._is_received_candidate(row):
                    continue
                raw_status = str(row.get("cheque_status") or row.get("state_label") or "")
                row["status_bucket"] = self.status_bucket(raw_status, row.get("status_ref"))
                # The Karamad management portfolio is strictly limited to these
                # six official StatusRef buckets. Other source statuses remain
                # available in SQL but never enter this portfolio response.
                if row["status_bucket"] is None:
                    continue
                if row["status_bucket"] not in KARAMAD_MAIN_STATUS_BUCKETS:
                    continue
                row["is_non_certain"] = row["status_bucket"] == "غیر قطعی"
                # Never overwrite the source status. The UI may display the
                # derived bucket separately, but SQL's raw StatusName remains intact.
                row["status_source_empty"] = not raw_status.strip()
                row["is_karamad_received"] = True
                out.append(row)

            total = sum(_as_float(r.get("amount")) for r in out)
            _received_cache.update({"loaded_at": now, "rows": out, "count": len(out), "total_amount_rial": total})
            return out, len(out), total

    def open_received(self, limit: int = 200_000) -> list[dict[str, Any]]:
        rows, _, _ = self._load_received_snapshot(limit=limit)
        return rows

    @staticmethod
    def cache_info() -> dict[str, Any]:
        with _received_cache_lock:
            rows = _received_cache.get("rows")
            return {
                "loaded": rows is not None,
                "age_seconds": None if rows is None else max(0.0, time.monotonic() - float(_received_cache.get("loaded_at", 0.0))),
                "count": int(_received_cache.get("count", 0)),
                "total_amount_rial": float(_received_cache.get("total_amount_rial", 0.0)),
                "ttl_seconds": _RECEIVED_CACHE_TTL_SECONDS,
            }

    def filter_buckets(self, rows: list[dict[str, Any]], buckets: list[str] | None) -> list[dict[str, Any]]:
        if not buckets or "all" in buckets:
            return rows
        allowed = set(buckets)
        return [row for row in rows if row.get("status_bucket") in allowed]

    def report(self, limit: int = 200_000, selected_buckets: list[str] | None = None) -> dict[str, Any]:
        rows = self.open_received(limit=limit)
        filtered_rows = self.filter_buckets(rows, selected_buckets)
        total = sum(_as_float(r["amount"]) for r in rows)
        cache = self.cache_info()
        buckets = ["غیر قطعی", "نزد صندوق", "واگذار شده", "برگشت نزد صندوق", "برگشتی نزد مشتری", "برگشتی نزد صندوق"]
        counts = {b: sum(1 for r in rows if r.get("status_bucket") == b) for b in buckets}
        amounts = {b: sum(_as_float(r["amount"]) for r in rows if r.get("status_bucket") == b) for b in buckets}
        return {
            "status": "success",
            "source": "karamad_sql",
            "source_label": "کارآمد",
            "count": len(filtered_rows),
            "total_amount_rial": sum(_as_float(r["amount"]) for r in filtered_rows),
            "currency": "ریال",
            "cheques": filtered_rows,
            "status_buckets": buckets,
            "non_certain_rule": "StatusRef = 1 (fallback to empty StatusName only when StatusRef is unavailable)",
            "status_counts": counts,
            "status_amounts_rial": amounts,
            "cache": {
                "enabled": True,
                "ttl_seconds": cache["ttl_seconds"],
                "age_seconds": round(cache["age_seconds"], 2) if cache["age_seconds"] is not None else None,
                "snapshot_count": cache["count"],
                "snapshot_total_amount_rial": cache["total_amount_rial"],
                "data_reduced": False,
                "source_query_truncated": False,
            },
            "filter_policy": {
                "applied_in_backend": True,
                "source_scope": "فقط کارآمد",
                "excluded_before_filtering": [],
                "status_buckets": buckets,
            "non_certain_rule": "StatusRef = 1 (fallback to empty StatusName only when StatusRef is unavailable)",
            },
        }
