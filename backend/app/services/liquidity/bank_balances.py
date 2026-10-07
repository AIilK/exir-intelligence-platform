"""Section 1 of the liquidity dashboard: opening bank and cash balance.

Balances are built from the accounting vouchers of the current fiscal year (the opening
voucher included), up to today:
- Rahkaran: FIN3.VoucherItem Debit − Credit on SL 126001/126002 (banks) and 126003/126004
  (cash), one row per DL (the DL title names the account);
- Karamad: tblVoucherLines Debtor − Creditor on SL 1113 (banks) and 1111 (cash), per DL.

Excluded from the company balance:
- the shareholders' personal accounts booked in Rahkaran (نادر/ناصر علیزاده، آهنگردوست،
  «شخصی»): they are financing, not company cash;
- foreign-currency accounts (126002): not spendable in rial;
- account صادرات …55005 (زرین کالای کادوس) is booked in both systems; Rahkaran is the live
  side (Karamad only carries its opening line), so it is counted once from Rahkaran.

Cash boxes are reported but stay out of the forecast opening unless asked: the Rahkaran
cash desk carries a book balance (~11B toman) that treasury has not confirmed.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import text

from app.services.liquidity.cash_movements import CHANNEL_LABELS, CHANNEL_SYSTEMS, SYSTEM_CHANNEL, SalesChannel
from app.utils.jalali import format_jalali_date

CACHE_TTL_SECONDS = 300
STALE_POSTING_DAYS = 3
DUPLICATE_ACCOUNT_DIGITS = "55005"  # صادرات 0112779955005، در هر دو سیستم

RAHKARAN_BANK_SL = {"126001": "bank", "126002": "fx", "126003": "cash", "126004": "cash"}
KARAMAD_BANK_SL = {"1113": "bank", "1111": "cash"}
PERSONAL_PATTERNS = ("علیزاده", "آهنگردوست", "شخصی")

KIND_LABELS = {"bank": "بانک", "cash": "صندوق", "fx": "حساب ارزی"}
EXCLUSION_LABELS = {
    "shareholder_personal": "حساب شخصی سهامداران",
    "fx": "حساب ارزی (غیرریالی)",
    "duplicate": "تکراری؛ از راهکاران شمرده می‌شود",
}

RAHKARAN_BALANCES_SQL = text("""
    SELECT vi.[SLCode] AS [SLCode], vi.[DLLevel4] AS [AccountCode], dl.[Title] AS [AccountName],
           SUM(ISNULL(vi.[Debit], 0) - ISNULL(vi.[Credit], 0)) AS [Balance],
           MAX(CAST(v.[Date] AS date)) AS [LastDate]
    FROM FIN3.[VoucherItem] AS vi
    INNER JOIN FIN3.[Voucher] AS v ON v.[VoucherID] = vi.[VoucherRef]
    LEFT JOIN FIN3.[DL] AS dl ON dl.[Code] = vi.[DLLevel4]
    WHERE vi.[SLCode] IN ('126001', '126002', '126003', '126004')
      AND v.[FiscalYearRef] = (SELECT MAX([FiscalYearRef]) FROM FIN3.[Voucher])
      AND v.[Date] < :date_to_exclusive
    GROUP BY vi.[SLCode], vi.[DLLevel4], dl.[Title]
""")

# Karamad also holds vouchers dated in the future; they are not cash yet.
KARAMAD_BALANCES_SQL = text("""
    SELECT CAST(sl.[Code] AS nvarchar(20)) AS [SLCode], CAST(l.[DLRef] AS nvarchar(20)) AS [AccountCode],
           dl.[Name] AS [AccountName],
           SUM(ISNULL(l.[Debtor], 0) - ISNULL(l.[Creditor], 0)) AS [Balance],
           MAX(CAST(v.[DateE] AS date)) AS [LastDate]
    FROM dbo.[tblVoucherLines] AS l
    INNER JOIN dbo.[tblVoucher] AS v ON v.[ID] = l.[VoucherRef]
    INNER JOIN dbo.[tblSL] AS sl ON sl.[ID] = l.[SLRef]
    LEFT JOIN dbo.[tblDL] AS dl ON dl.[ID] = l.[DLRef]
    WHERE sl.[Code] IN (1111, 1113)
      AND ISNULL(l.[isDeleted], 0) = 0
      AND v.[FiscalYear] = (SELECT MAX([FiscalYear]) FROM dbo.[tblVoucher])
      AND v.[DateE] < :date_to_exclusive
    GROUP BY sl.[Code], l.[DLRef], dl.[Name]
""")


def fetch_rahkaran_balances(end_exclusive: date) -> list[dict[str, Any]]:
    from app.database.sqlserver import get_sqlserver_engine
    with get_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(RAHKARAN_BALANCES_SQL, {"date_to_exclusive": end_exclusive}).mappings()]


def fetch_karamad_balances(end_exclusive: date) -> list[dict[str, Any]]:
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    with get_karamad_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(KARAMAD_BALANCES_SQL, {"date_to_exclusive": end_exclusive}).mappings()]


Fetcher = Callable[[date], list[dict[str, Any]]]
DEFAULT_FETCHERS: dict[str, Fetcher] = {"rahkaran": fetch_rahkaran_balances, "karamad": fetch_karamad_balances}

_cache: dict[tuple[str, date], tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _round(value: float) -> float:
    return round(float(value), 2)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10]) if value else None


def _code(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:-2] if text_value.endswith(".0") else text_value or None


def account_numbers(title: str | None) -> list[str]:
    """Digit runs long enough to be an account number («611828288000026601»)."""
    return [n for n in re.findall(r"\d+", (title or "").replace("/", "")) if len(n) >= 8 or n == DUPLICATE_ACCOUNT_DIGITS]


class BankBalanceService:
    def __init__(self, today: date | None = None, fetchers: dict[str, Fetcher] | None = None,
                 cache_ttl_seconds: int = CACHE_TTL_SECONDS):
        self.today = today or date.today()
        self.fetchers = fetchers or DEFAULT_FETCHERS
        self.cache_ttl_seconds = cache_ttl_seconds

    def _load(self, system: str, refresh: bool) -> list[dict[str, Any]]:
        key = (system, self.today)
        now = time.monotonic()
        with _cache_lock:
            hit = _cache.get(key)
            if hit and not refresh and now - hit[0] < self.cache_ttl_seconds:
                return hit[1]
        rows = self.fetchers[system](self.today + timedelta(days=1))
        with _cache_lock:
            _cache[key] = (now, rows)
        return rows

    def _normalize(self, system: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sl_kinds = RAHKARAN_BANK_SL if system == "rahkaran" else KARAMAD_BANK_SL
        accounts = []
        for row in rows:
            sl = _code(row["SLCode"])
            kind = sl_kinds.get(sl or "")
            if kind is None:
                continue
            balance = float(row["Balance"] or 0)
            title = (row.get("AccountName") or "").strip() or f"حساب {_code(row.get('AccountCode')) or 'نامشخص'}"
            if not balance and not row.get("AccountName"):
                continue
            numbers = account_numbers(title)
            excluded = None
            if system == "rahkaran" and any(p in title for p in PERSONAL_PATTERNS):
                excluded = "shareholder_personal"
            elif kind == "fx":
                excluded = "fx"
            elif system == "karamad" and any(n.endswith(DUPLICATE_ACCOUNT_DIGITS) for n in numbers):
                excluded = "duplicate"
            last = _as_date(row.get("LastDate"))
            accounts.append({
                "account_key": f"{system}|{sl}|{_code(row.get('AccountCode')) or ''}",
                "system": system,
                "channel": SYSTEM_CHANNEL[system],
                "sl_code": sl,
                "kind": "bank" if kind == "fx" else kind,
                "kind_label": KIND_LABELS[kind],
                "account_code": _code(row.get("AccountCode")),
                "account_name": title,
                "account_numbers": numbers,
                "balance_rial": _round(balance),
                "last_posted_date": last.isoformat() if last else None,
                "last_posted_date_jalali": format_jalali_date(last) if last else None,
                "included": excluded is None,
                "excluded_reason": excluded,
                "excluded_label": EXCLUSION_LABELS.get(excluded) if excluded else None,
                "negative": balance < 0,
            })
        return accounts

    def accounts(self, channel: SalesChannel = "all", refresh: bool = False
                 ) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
        accounts: list[dict[str, Any]] = []
        sources: list[str] = []
        warnings: list[dict[str, str]] = []
        for system in CHANNEL_SYSTEMS[channel]:
            try:
                rows = self._load(system, refresh)
            except Exception as exc:
                warnings.append({
                    "code": f"{system}_unavailable",
                    "message": f"موجودی {'راهکاران' if system == 'rahkaran' else 'کارآمد'} دریافت نشد؛ موجودی ناقص است. ({exc.__class__.__name__})",
                })
                continue
            sources.append(system)
            accounts.extend(self._normalize(system, rows))
        return accounts, sources, warnings

    def report(self, channel: SalesChannel = "all", refresh: bool = False) -> dict[str, Any]:
        accounts, sources, warnings = self.accounts(channel, refresh)
        included = [a for a in accounts if a["included"]]
        bank = [a for a in included if a["kind"] == "bank"]
        cash = [a for a in included if a["kind"] == "cash"]

        by_system = []
        for system in sources:
            items = [a for a in included if a["system"] == system]
            dates = [a["last_posted_date"] for a in items if a["last_posted_date"]]
            last = max(dates) if dates else None
            lag = (self.today - date.fromisoformat(last)).days if last else None
            by_system.append({
                "system": system, "channel": SYSTEM_CHANNEL[system], "label": CHANNEL_LABELS[SYSTEM_CHANNEL[system]],
                "bank_rial": _round(sum(a["balance_rial"] for a in items if a["kind"] == "bank")),
                "cash_rial": _round(sum(a["balance_rial"] for a in items if a["kind"] == "cash")),
                "last_posted_date": last, "last_posted_date_jalali": format_jalali_date(date.fromisoformat(last)) if last else None,
                "posting_lag_days": lag,
            })
            if lag is not None and lag > STALE_POSTING_DAYS:
                warnings.append({
                    "code": f"{system}_posting_lag",
                    "message": f"آخرین سند بانک در {'راهکاران' if system == 'rahkaran' else 'کارآمد'} {lag} روز پیش ثبت شده؛ موجودی دفتری ممکن است عقب باشد.",
                })

        excluded_totals: dict[str, dict[str, Any]] = {}
        for a in accounts:
            if a["included"]:
                continue
            item = excluded_totals.setdefault(a["excluded_reason"], {
                "reason": a["excluded_reason"], "label": a["excluded_label"], "amount_rial": 0.0, "count": 0})
            item["amount_rial"] += a["balance_rial"]
            item["count"] += 1
        for item in excluded_totals.values():
            item["amount_rial"] = _round(item["amount_rial"])

        negative = [a for a in bank if a["negative"]]
        if negative:
            warnings.append({
                "code": "negative_bank_balance",
                "message": f"{len(negative)} حساب بانکی مانده دفتری منفی دارد (مثلاً چک صادره‌ای که هنوز ثبت واریزش نیامده)؛ با صورت‌حساب کنترل شود.",
            })

        data = {
            "bank_rial": _round(sum(a["balance_rial"] for a in bank)),
            "cash_rial": _round(sum(a["balance_rial"] for a in cash)),
            "total_rial": _round(sum(a["balance_rial"] for a in included)),
            "by_system": by_system,
            "accounts": sorted(accounts, key=lambda a: (not a["included"], a["kind"] != "bank", -a["balance_rial"])),
            "excluded": sorted(excluded_totals.values(), key=lambda e: -abs(e["amount_rial"])),
            "validated_against_statement": False,
            "rule": "موجودی دفتری از اسناد حسابداری سال مالی جاری تا امروز. حساب‌های شخصی سهامداران و حساب‌های ارزی جزو موجودی نیستند؛ حساب صادرات …55005 فقط یک‌بار (از راهکاران) شمرده می‌شود. هنوز با صورت‌حساب بانک تطبیق داده نشده است.",
        }
        return {"status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
                "filters": {"channel": channel}, "data": data, "sources": sources, "warnings": warnings}
