"""Section 2 of the liquidity dashboard: open issued cheques (100% outflow).

Management rules:
- every open issued cheque is a certain outflow; there is no collection adjustment;
- overdue open cheques up to 20 days land on today's outflow and get their own card.
  Older ones are not counted: Rahkaran keeps thousands of cheques «open» for years (1,645B
  toman older than 90 days on 1405/07/08) that were paid but never posted, so they go to a
  «needs status review» list for treasury instead;
- payment orders are not included, only cheques actually issued;
- guarantee cheques are excluded;
- cheques to «سهامداران» are drawn on the shareholders' personal accounts and payable to the
  company («انتقال از 966 نادر علیزاده به 5565 اکسیر»).  Management treats every cheque
  moving to or from the shareholders as intra-company: neither outflow nor inflow, so they
  are left out of every total, card and the forecast.  The personal accounts themselves
  never count in the company's liquidity balance.

Channels follow the rest of the dashboard: B2B = Rahkaran, هیبرید = Karamad.  A hybrid
cheque written to the group firms (Karamad SL 3112) is the stock settlement with the
company: shown on the hybrid channel, eliminated from the group total.

A cheque payable to the very bank account it is drawn on (Karamad: «ملت ظفر9203348030»
drawn on بانک ملت ظفر9203348030) moves money between the company's own accounts or to its
cash box.  Like every inter-bank transfer it is never an outflow; it is listed on its own.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import text

from app.services.liquidity.cash_movements import CHANNEL_LABELS, CHANNEL_SYSTEMS, SYSTEM_CHANNEL, SalesChannel
from app.utils.jalali import format_jalali_date

CACHE_TTL_SECONDS = 300
HYBRID_SETTLEMENT_SL = "3112"
OVERDUE_COUNTED_DAYS = 20
SHAREHOLDERS_DL_CODE = "950031"  # FIN3.DL «سهامداران»
REVIEW_AGE_BUCKETS = ((21, 90, "۲۱ تا ۹۰ روز"), (91, 365, "۳ ماه تا یک سال"), (366, None, "بیش از یک سال"))
TOP_PAYEES = 10
MAX_LISTED_CHEQUES = 3000

RAHKARAN_OPEN_ISSUED_SQL = text("""
    SELECT note.[PayableNoteID] AS [ChequeID], note.[Amount], note.[DueDate],
           note.[SerialNumber], note.[AccountNumber], bank.[Name] AS [BankName], note.[BankBranchName],
           counterpart.[Code] AS [PayeeCode], counterpart.[Title] AS [PayeeName], note.[Description]
    FROM RPA3.[PayableNote] AS note
    LEFT JOIN RPA3.[Bank] AS bank ON bank.[BankID] = note.[BankRef]
    LEFT JOIN FIN3.[DL] AS counterpart ON counterpart.[DLID] = note.[CounterPartRef]
    OUTER APPLY (
        SELECT TOP (1) pnt.[DocumentRef] AS [StatusDocumentID]
        FROM RPA3.[PayableNoteTransaction] AS pnt
        WHERE pnt.[PayableNoteRef] = note.[PayableNoteID]
          AND pnt.[State] = 11 AND pnt.[DocumentItemType] IN (24, 26) AND pnt.[DocumentState] = 3
          AND (ISNULL(pnt.[Description], N'') LIKE N'%تعیین وضعیت چک%'
            OR ISNULL(pnt.[Description], N'') LIKE N'%تعین وضعیت چک%'
            OR ISNULL(pnt.[Description], N'') LIKE N'%وصول چ%'
            OR ISNULL(pnt.[Description], N'') LIKE N'%پرداخت چک%'
            OR ISNULL(pnt.[Description], N'') LIKE N'%برداشت وجه چک%')
    ) AS status_link
    WHERE note.[NoteType] = 1
      AND note.[State] = 11
      AND status_link.[StatusDocumentID] IS NULL
      AND note.[NormalORGuarantee] = 1
      AND note.[DueDate] IS NOT NULL
      AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
      AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
      AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
""")

# Final status 2 = «عادی» (open); 3 = collected.  Guarantee cheques carry «تضمین» in the SL.
KARAMAD_OPEN_ISSUED_SQL = text("""
    SELECT [ChequeRef] AS [ChequeID], [Price] AS [Amount], [DueDate], [inx] AS [SerialNumber],
           CAST(NULL AS nvarchar(50)) AS [AccountNumber], [BankName], CAST(NULL AS nvarchar(200)) AS [BankBranchName],
           CAST([DLCode] AS nvarchar(50)) AS [PayeeCode], COALESCE([DLName], [DL2Name], [DL3Name], [Behalf]) AS [PayeeName],
           COALESCE([Description], [Behalf]) AS [Description], CAST([SLCode] AS nvarchar(50)) AS [SLCode]
    FROM dbo.[vwChequePLinesFull]
    WHERE [LastStatusRef] = 2
      AND [DueDate] IS NOT NULL
      AND ISNULL([SLName], N'') NOT LIKE N'%تضمین%'
""")


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value)[:10])
    return None


def _code(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:-2] if text_value.endswith(".0") else text_value or None


def fetch_rahkaran_issued() -> list[dict[str, Any]]:
    from app.database.sqlserver import get_sqlserver_engine
    with get_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(RAHKARAN_OPEN_ISSUED_SQL).mappings()]


def fetch_karamad_issued() -> list[dict[str, Any]]:
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    with get_karamad_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(KARAMAD_OPEN_ISSUED_SQL).mappings()]


Fetcher = Callable[[], list[dict[str, Any]]]
DEFAULT_FETCHERS: dict[str, Fetcher] = {"rahkaran": fetch_rahkaran_issued, "karamad": fetch_karamad_issued}

_cache: dict[tuple[str, date], tuple[float, list[dict[str, Any]]]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _round(value: float) -> float:
    return round(float(value), 2)


def is_own_account_transfer(payee_name: str | None, bank_name: str | None, account_number: str | None) -> bool:
    """The payee names an account number (8+ digits) of the account the cheque is drawn on."""
    drawer = re.sub(r"\D", "", f"{bank_name or ''}{account_number or ''}")
    return bool(drawer) and any(run in drawer for run in re.findall(r"\d{8,}", payee_name or ""))


def _public(cheque: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in cheque.items() if k != "hybrid_settlement"}


class IssuedChequeService:
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
        rows = self.fetchers[system]()
        with _cache_lock:
            _cache[key] = (now, rows)
        return rows

    def _normalize(self, system: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cheques: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            cheque_id = f"{system}:{row['ChequeID']}"
            # vwChequePLinesFull can repeat a cheque on several lines; count it once.
            if cheque_id in seen:
                continue
            seen.add(cheque_id)
            due = _as_date(row["DueDate"])
            if due is None:
                continue
            bank_name = (row.get("BankName") or "").strip() or "بانک نامشخص"
            account_number = _code(row.get("AccountNumber"))
            internal = system == "karamad" and _code(row.get("SLCode")) == HYBRID_SETTLEMENT_SL
            cheques.append({
                "cheque_id": cheque_id,
                "system": system,
                "channel": SYSTEM_CHANNEL[system],
                "serial_number": _code(row.get("SerialNumber")),
                "amount_rial": float(row["Amount"] or 0),
                "due_date": due.isoformat(),
                "due_date_jalali": format_jalali_date(due),
                "days_to_due": (due - self.today).days,
                "payee_code": _code(row.get("PayeeCode")),
                "payee_name": (row.get("PayeeName") or "").strip() or "ذی‌نفع نامشخص",
                "bank_name": bank_name,
                "bank_branch_name": row.get("BankBranchName"),
                "account_number": account_number,
                "bank_account_key": f"{system}|{bank_name}|{account_number or ''}",
                "description": row.get("Description"),
                "shareholder": system == "rahkaran" and _code(row.get("PayeeCode")) == SHAREHOLDERS_DL_CODE,
                "hybrid_settlement": internal,
                "own_account_transfer": is_own_account_transfer(row.get("PayeeName"), bank_name, account_number),
            })
        return cheques

    def _cheques(self, channel: SalesChannel, refresh: bool) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
        cheques: list[dict[str, Any]] = []
        sources: list[str] = []
        warnings: list[dict[str, str]] = []
        for system in CHANNEL_SYSTEMS[channel]:
            try:
                rows = self._load(system, refresh)
            except Exception as exc:
                warnings.append({
                    "code": f"{system}_unavailable",
                    "message": f"چک‌های پرداختی {'راهکاران' if system == 'rahkaran' else 'کارآمد'} دریافت نشد؛ تعهدات ناقص است. ({exc.__class__.__name__})",
                })
                continue
            sources.append(system)
            cheques.extend(self._normalize(system, rows))
        return cheques, sources, warnings

    @staticmethod
    def _sum(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"amount_rial": _round(sum(c["amount_rial"] for c in items)), "count": len(items)}

    @staticmethod
    def _is_counted_overdue(cheque: dict[str, Any]) -> bool:
        return -OVERDUE_COUNTED_DAYS <= cheque["days_to_due"] < 0

    @staticmethod
    def _needs_review(cheque: dict[str, Any]) -> bool:
        return cheque["days_to_due"] < -OVERDUE_COUNTED_DAYS

    def _review_card(self, stale: list[dict[str, Any]]) -> dict[str, Any]:
        buckets = []
        for low, high, label in REVIEW_AGE_BUCKETS:
            items = [c for c in stale if low <= -c["days_to_due"] and (high is None or -c["days_to_due"] <= high)]
            buckets.append({"label": label, **self._sum(items)})
        oldest = min(stale, key=lambda c: c["days_to_due"], default=None)
        return {
            **self._sum(stale),
            "age_buckets": buckets,
            "oldest": None if oldest is None else {
                "due_date_jalali": oldest["due_date_jalali"], "days_overdue": -oldest["days_to_due"],
                "payee_name": oldest["payee_name"], "amount_rial": oldest["amount_rial"]},
            "cheques": sorted(stale, key=lambda c: -c["amount_rial"])[:MAX_LISTED_CHEQUES],
            "in_forecast": False,
            "rule": f"چک‌های باز با بیش از {OVERDUE_COUNTED_DAYS} روز تأخیر در خروجی حساب نمی‌شوند؛ احتمالاً پاس شده ولی وضعیتشان در راهکاران به‌روز نشده و باید خزانه بررسی کند.",
        }

    def _daily(self, cheques: list[dict[str, Any]], horizon_days: int) -> dict[str, float]:
        """Counted overdue on today, then each due day inside the horizon."""
        end = self.today + timedelta(days=horizon_days)
        daily: dict[str, float] = defaultdict(float)
        for c in cheques:
            due = date.fromisoformat(c["due_date"])
            if due < end:
                daily[max(due, self.today).isoformat()] += c["amount_rial"]
        return dict(daily)

    def _forecastable(self, cheques: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [c for c in cheques if not self._set_aside(c) and not self._needs_review(c)]

    @staticmethod
    def _set_aside(cheque: dict[str, Any]) -> bool:
        """Not an outflow at all: hybrid stock settlement, own-account transfer or shareholders."""
        return cheque["hybrid_settlement"] or cheque["own_account_transfer"] or cheque["shareholder"]

    def schedule(self, horizon_days: int, channel: SalesChannel = "all", refresh: bool = False) -> dict[str, float]:
        """Daily issued-cheque outflow for the forecast."""
        cheques, _, _ = self._cheques(channel, refresh)
        return self._daily(self._forecastable(cheques), horizon_days)

    def report(
        self,
        horizon_days: int = 30,
        channel: SalesChannel = "all",
        bank_account: str | None = None,
        payee: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        horizon_days = max(1, min(int(horizon_days), 365))
        cheques, sources, warnings = self._cheques(channel, refresh)
        if bank_account:
            cheques = [c for c in cheques if c["bank_account_key"] == bank_account]
        if payee:
            needle = payee.strip().lower()
            cheques = [c for c in cheques if needle in c["payee_name"].lower() or needle == (c["payee_code"] or "")]
        if min_amount is not None:
            cheques = [c for c in cheques if c["amount_rial"] >= min_amount]
        if max_amount is not None:
            cheques = [c for c in cheques if c["amount_rial"] <= max_amount]

        settlement = [c for c in cheques if c["hybrid_settlement"]]
        transfers = [c for c in cheques if c["own_account_transfer"] and not c["hybrid_settlement"]]
        stale = [c for c in cheques if not self._set_aside(c) and self._needs_review(c)]
        counted = self._forecastable(cheques)
        overdue = [c for c in counted if self._is_counted_overdue(c)]
        in_horizon = [c for c in counted if 0 <= c["days_to_due"] < horizon_days]
        today_items = [c for c in counted if c["days_to_due"] == 0]
        next_7 = [c for c in counted if 0 <= c["days_to_due"] < 7]

        calendar: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for c in in_horizon:
            calendar[c["days_to_due"]].append(c)
        days = []
        for offset in range(horizon_days):
            day = self.today + timedelta(days=offset)
            items = calendar.get(offset, [])
            days.append({"date": day.isoformat(), "date_jalali": format_jalali_date(day),
                         "weekday": day.weekday(), **self._sum(items)})
        peak = max(days, key=lambda d: d["amount_rial"], default=None)

        accounts: dict[str, dict[str, Any]] = {}
        for c in counted + stale:
            key = c["bank_account_key"]
            account = accounts.setdefault(key, {
                "bank_account_key": key, "system": c["system"], "channel": c["channel"],
                "bank_name": c["bank_name"], "account_number": c["account_number"],
                "overdue_rial": 0.0, "next_7_days_rial": 0.0, "next_30_days_rial": 0.0,
                "next_90_days_rial": 0.0, "open_count": 0, "needs_review_rial": 0.0,
                # Filled from bank balances in the summary step (step 5).
                "balance_rial": None, "coverage_percent": None,
            })
            d = c["days_to_due"]
            if self._needs_review(c):
                account["needs_review_rial"] += c["amount_rial"]
                continue
            account["open_count"] += 1
            if d < 0:
                account["overdue_rial"] += c["amount_rial"]
            for limit, field in ((7, "next_7_days_rial"), (30, "next_30_days_rial"), (90, "next_90_days_rial")):
                if 0 <= d < limit:
                    account[field] += c["amount_rial"]
        by_account = sorted(({k: (_round(v) if k.endswith("_rial") and v is not None else v)
                              for k, v in a.items()} for a in accounts.values()),
                            key=lambda a: -(a["overdue_rial"] + a["next_30_days_rial"]))

        payee_totals: dict[tuple[str | None, str], dict[str, Any]] = {}
        for c in overdue + in_horizon:
            item = payee_totals.setdefault((c["payee_code"], c["payee_name"]), {
                "payee_code": c["payee_code"], "payee_name": c["payee_name"], "amount_rial": 0.0, "count": 0})
            item["amount_rial"] += c["amount_rial"]
            item["count"] += 1
        top_payees = sorted(payee_totals.values(), key=lambda p: -p["amount_rial"])[:TOP_PAYEES]
        for item in top_payees:
            item["amount_rial"] = _round(item["amount_rial"])

        by_channel: dict[str, float] = defaultdict(float)
        for c in overdue + in_horizon:
            by_channel[c["channel"]] += c["amount_rial"]

        listed = sorted(overdue + in_horizon, key=lambda c: (c["days_to_due"], -c["amount_rial"]))
        review = self._review_card(stale)
        review["cheques"] = [_public(c) for c in review["cheques"]]
        data = {
            "horizon": {"days": horizon_days, "from": self.today.isoformat(),
                        "to": (self.today + timedelta(days=horizon_days - 1)).isoformat(),
                        "from_jalali": format_jalali_date(self.today),
                        "to_jalali": format_jalali_date(self.today + timedelta(days=horizon_days - 1))},
            "kpis": {
                "horizon": self._sum(in_horizon),
                "today": self._sum(today_items),
                "next_7_days": self._sum(next_7),
                "overdue": self._sum(overdue),
                "total_due_by_horizon_end": self._sum(overdue + in_horizon),
                "peak_day": None if not peak or not peak["amount_rial"] else peak,
            },
            "overdue": {
                **self._sum(overdue),
                "rule": f"چک‌های باز با حداکثر {OVERDUE_COUNTED_DAYS} روز تأخیر روی خروجی امروز جمع می‌شوند.",
            },
            "needs_status_review": review,
            "by_channel": [{"channel": k, "label": CHANNEL_LABELS[k], "amount_rial": _round(v)}
                           for k, v in sorted(by_channel.items(), key=lambda kv: -kv[1])],
            "calendar": days,
            "by_bank_account": by_account,
            "top_payees": top_payees,
            "cheques": [_public(c) for c in listed[:MAX_LISTED_CHEQUES]],
            "cheque_count": len(listed),
            "own_account_transfers": {
                **self._sum(transfers),
                "cheques": [_public(c) for c in sorted(transfers, key=lambda c: -c["days_to_due"])],
                "in_forecast": False,
                "rule": "چکی که در وجه همان حسابی صادر شده که از آن کشیده شده (مثلاً «ملت ظفر9203348030» از بانک ملت ظفر9203348030) جابه‌جایی بین حساب‌های خود شرکت یا برداشت به صندوق است؛ مثل انتقال بین‌بانکی خروجی حساب نمی‌شود.",
            },
            "hybrid_settlement": {
                **self._sum([c for c in settlement if c["days_to_due"] < horizon_days]),
                "eliminated_in_group": channel == "all",
                "rule": "چک‌های هیبرید در وجه شرکت‌های گروه (حساب ۳۱۱۲ کارآمد) تسویه موجودی با شرکت است؛ در جمع گروه حساب نمی‌شود.",
            },
            "rule": f"چک پرداختی ۱۰۰٪ خروجی قطعی است؛ معوق تا {OVERDUE_COUNTED_DAYS} روز روی امروز می‌آید و قدیمی‌ترها نیازمند بررسی وضعیت‌اند. دستور پرداخت، چک تضمینی و چک‌های در وجه سهامداران (درون‌شرکتی) حساب نمی‌شوند.",
        }
        filters = {"horizon_days": horizon_days, "channel": channel, "bank_account": bank_account,
                   "payee": payee, "min_amount": min_amount, "max_amount": max_amount}
        return {"status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
                "filters": filters, "data": data, "sources": sources, "warnings": warnings}
