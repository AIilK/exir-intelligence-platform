"""Sections 3 and 4 of the liquidity dashboard: operating inflows, outflows and financing.

Only cash and bank rows are read (no cheques: those belong to the cheque sections).
Every row is classified through ``account_map``.

The dimension is the sales channel, one per system: B2B = Rahkaran, هیبرید = Karamad.
The hybrid's stock settlement with the company appears in both systems; it is reported
per channel and eliminated from the group ("all") totals.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Callable, Iterable, Literal

from sqlalchemy import text

from app.services.liquidity.account_map import (
    CATEGORY_LABELS,
    NOTE_CHEQUE_COLLECTION,
    NOTE_FX_PURCHASE,
    Classification,
    classify,
)
from app.utils.jalali import _gregorian_to_jalali, _jalali_to_gregorian, format_jalali_date

SalesChannel = Literal["b2b", "hybrid", "all"]
CHANNEL_SYSTEMS: dict[str, tuple[str, ...]] = {
    "b2b": ("rahkaran",),
    "hybrid": ("karamad",),
    "all": ("rahkaran", "karamad"),
}
SYSTEM_CHANNEL = {"rahkaran": "b2b", "karamad": "hybrid"}
CHANNEL_LABELS = {"b2b": "B2B (راهکاران)", "hybrid": "هیبرید (کارآمد)"}
METHOD_LABELS = {"bank": "حواله / بانکی", "cash": "نقد"}
# Python weekday(): Monday=0 ... Friday=4 (Iranian weekend).
WEEKDAY_LABELS = {5: "شنبه", 6: "یکشنبه", 0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه"}
WEEKDAY_ORDER = (5, 6, 0, 1, 2, 3, 4)
FRIDAY = 4

HISTORY_DAYS = 400  # enough for a 12-Jalali-month trend and a 365-day base period
CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class Movement:
    day: date
    system: str
    direction: str
    method: str
    account_code: str | None
    account_name: str | None
    counterpart_code: str | None
    amount_rial: float
    count: int = 1
    counterpart_name: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class ClassifiedMovement:
    movement: Movement
    classification: Classification

    @property
    def signed_amount(self) -> float:
        return self.movement.amount_rial * self.classification.sign


# --------------------------------------------------------------------------- sources

_RAHKARAN_PART = """
    SELECT CAST(h.[Date] AS date) AS [Day], N'{direction}' AS [Direction], N'{method}' AS [Method],
           f.[Number] AS [AccountCode], COALESCE(sl.[Title], f.[Name]) AS [AccountName],
           dl.[Code] AS [CounterpartCode], dl.[Title] AS [CounterpartName],
           {note} AS [Note], SUM(d.[Amount]) AS [Amount], COUNT_BIG(*) AS [RowCount]
    FROM RPA3.[{detail}] AS d
    INNER JOIN RPA3.[{header}] AS h ON h.[{header_id}] = d.[{header_ref}]
    LEFT JOIN RPA3.[CashFlowFactor] AS f ON f.[CashFlowFactorID] = d.[CashFlowFactorRef]
    LEFT JOIN FIN3.[SL] AS sl ON sl.[SLID] = f.[SLRef]
    LEFT JOIN FIN3.[DL] AS dl ON dl.[DLID] = COALESCE(d.[CounterPartRef], h.[CounterPartRef])
    WHERE h.[ApproveState] = 3 AND h.[Date] >= :date_from AND h.[Date] < :date_to_exclusive
    GROUP BY CAST(h.[Date] AS date), f.[Number], COALESCE(sl.[Title], f.[Name]), dl.[Code], dl.[Title]{note_group}
"""

# A cheque cashed in (e.g. by the collection agent) is already counted by the cheque
# sections; the description is the only field that says so.
_CHEQUE_PHRASES = ("وصول چک", "نقد کردن چک")


def _cheque_note(*columns: str) -> str:
    matches = " OR ".join(f"{column} LIKE N'%{phrase}%'" for column in columns for phrase in _CHEQUE_PHRASES)
    return f"CASE WHEN {matches} THEN N'{NOTE_CHEQUE_COLLECTION}' END"


_RAHKARAN_CHEQUE_NOTE = _cheque_note("COALESCE(NULLIF(d.[Description], N''), h.[Description])")
_KARAMAD_CHEQUE_NOTE = _cheque_note("d.[Behalf]", "d.[Description]")
# Karamad payments to the group firms (SL 3112) are the hybrid's stock settlement, except
# FX bought for the company, which the «بابت» field names explicitly.
_KARAMAD_FX_NOTE = f"CASE WHEN d.[Behalf] LIKE N'%خرید ارز%' THEN N'{NOTE_FX_PURCHASE}' END"


def _note_args(note: str | None) -> dict[str, str]:
    # SQL Server rejects a constant GROUP BY expression, so NULL notes are not grouped.
    return {"note": note or "CAST(NULL AS nvarchar(20))", "note_group": f", {note}" if note else ""}


RAHKARAN_MOVEMENTS_SQL = "\nUNION ALL\n".join(
    _RAHKARAN_PART.format(direction=direction, method=method, detail=detail, header=header,
                          header_id=header_id, header_ref=header_ref, **_note_args(note))
    for direction, method, detail, header, header_id, header_ref, note in (
        ("inflow", "bank", "ReceiptDeposit", "Receipt", "ReceiptID", "ReceiptRef", _RAHKARAN_CHEQUE_NOTE),
        ("inflow", "cash", "ReceiptCashMoney", "Receipt", "ReceiptID", "ReceiptRef", _RAHKARAN_CHEQUE_NOTE),
        ("outflow", "bank", "PaymentDeposit", "Payment", "PaymentID", "PaymentRef", None),
        ("outflow", "cash", "PaymentCashMoney", "Payment", "PaymentID", "PaymentRef", None),
    )
)
_KARAMAD_PART = """
    SELECT CAST({day_expr} AS date) AS [Day], N'{direction}' AS [Direction], N'{method}' AS [Method],
           CAST(sl.[Code] AS nvarchar(50)) AS [AccountCode], sl.[Name] AS [AccountName],
           CAST(NULL AS nvarchar(50)) AS [CounterpartCode], CAST(NULL AS nvarchar(200)) AS [CounterpartName],
           {note} AS [Note], SUM(d.[{amount}]) AS [Amount], COUNT_BIG(*) AS [RowCount]
    FROM dbo.[{table}] AS d
    LEFT JOIN dbo.[tblSL] AS sl ON sl.[ID] = d.[SLRef]
    WHERE {day_expr} >= :date_from AND {day_expr} < :date_to_exclusive
    GROUP BY CAST({day_expr} AS date), sl.[Code], sl.[Name]{note_group}
"""

# tblDraftD.DraftDate is the bank date of the remittance (differs from BookDate on ~10%
# of rows); the other three tables only carry BookDate.
KARAMAD_MOVEMENTS_SQL = "\nUNION ALL\n".join(
    _KARAMAD_PART.format(direction=direction, method=method, table=table, amount=amount, day_expr=day_expr,
                         **_note_args(note))
    for direction, method, table, amount, day_expr, note in (
        ("inflow", "bank", "tblDraftD", "Price", "COALESCE(d.[DraftDate], d.[BookDate])", _KARAMAD_CHEQUE_NOTE),
        ("inflow", "cash", "tblCashD", "PriceN", "d.[BookDate]", _KARAMAD_CHEQUE_NOTE),
        ("outflow", "bank", "tblDraftP", "Price", "d.[BookDate]", _KARAMAD_FX_NOTE),
        ("outflow", "cash", "tblCashP", "PriceN", "d.[BookDate]", _KARAMAD_FX_NOTE),
    )
)


def _code(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:-2] if text_value.endswith(".0") else text_value or None


def _rows_to_movements(system: str, rows: Iterable[Any]) -> list[Movement]:
    movements = []
    for row in rows:
        day = row["Day"]
        movements.append(Movement(
            day=day if isinstance(day, date) else date.fromisoformat(str(day)[:10]),
            system=system,
            direction=row["Direction"],
            method=row["Method"],
            account_code=_code(row["AccountCode"]),
            account_name=row["AccountName"],
            counterpart_code=_code(row["CounterpartCode"]),
            counterpart_name=row["CounterpartName"],
            note=row["Note"],
            amount_rial=float(row["Amount"] or 0),
            count=int(row["RowCount"] or 0),
        ))
    return movements


def fetch_rahkaran_movements(start: date, end_exclusive: date) -> list[Movement]:
    from app.database.sqlserver import get_sqlserver_engine
    with get_sqlserver_engine().connect() as connection:
        rows = connection.execute(
            text(RAHKARAN_MOVEMENTS_SQL), {"date_from": start, "date_to_exclusive": end_exclusive},
        ).mappings().all()
    return _rows_to_movements("rahkaran", rows)


def fetch_karamad_movements(start: date, end_exclusive: date) -> list[Movement]:
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    with get_karamad_sqlserver_engine().connect() as connection:
        rows = connection.execute(
            text(KARAMAD_MOVEMENTS_SQL), {"date_from": start, "date_to_exclusive": end_exclusive},
        ).mappings().all()
    return _rows_to_movements("karamad", rows)


Fetcher = Callable[[date, date], list[Movement]]
DEFAULT_FETCHERS: dict[str, Fetcher] = {
    "rahkaran": fetch_rahkaran_movements,
    "karamad": fetch_karamad_movements,
}

_cache: dict[tuple[str, date], tuple[float, list[Movement]]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# --------------------------------------------------------------------------- helpers

def _jalali_ym(day: date) -> tuple[int, int]:
    year, month, _ = _gregorian_to_jalali(day.year, day.month, day.day)
    return year, month


def _jalali_month_start(year: int, month: int) -> date:
    return date(*_jalali_to_gregorian(year, month, 1))


def _previous_ym(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _last_months(today: date, count: int) -> list[tuple[int, int]]:
    months = [_jalali_ym(today)]
    while len(months) < count:
        months.append(_previous_ym(*months[-1]))
    return list(reversed(months))


def _month_label(year: int, month: int) -> str:
    return f"{year:04d}/{month:02d}"


def _round(value: float) -> float:
    return round(float(value), 2)


def _change_percent(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def _daily_stats(daily: dict[date, float], start: date, end_exclusive: date) -> dict[str, Any]:
    """Mean and median over working days (Fridays excluded); empty days count as zero."""
    days = [start + timedelta(days=i) for i in range((end_exclusive - start).days)]
    working = [d for d in days if d.weekday() != FRIDAY]
    values = [daily.get(d, 0.0) for d in working]
    return {
        "total_rial": _round(sum(daily.get(d, 0.0) for d in days)),
        "working_days": len(working),
        "mean_daily_rial": _round(mean(values)) if values else 0.0,
        "median_daily_rial": _round(median(values)) if values else 0.0,
    }


def _labelled_totals(totals: dict[str, float], key: str, labels: dict[str, str]) -> list[dict[str, Any]]:
    return [{key: k, "label": labels.get(k, k), "amount_rial": _round(v)}
            for k, v in sorted(totals.items(), key=lambda kv: -kv[1])]


# --------------------------------------------------------------------------- service

class CashMovementService:
    def __init__(
        self,
        today: date | None = None,
        fetchers: dict[str, Fetcher] | None = None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
    ):
        self.today = today or date.today()
        self.fetchers = fetchers or DEFAULT_FETCHERS
        self.cache_ttl_seconds = cache_ttl_seconds

    # -- data loading ---------------------------------------------------------

    def _load(self, system: str, refresh: bool) -> list[Movement]:
        key = (system, self.today)
        now = time.monotonic()
        with _cache_lock:
            hit = _cache.get(key)
            if hit and not refresh and now - hit[0] < self.cache_ttl_seconds:
                return hit[1]
        start = self.today - timedelta(days=HISTORY_DAYS)
        rows = self.fetchers[system](start, self.today + timedelta(days=1))
        with _cache_lock:
            _cache[key] = (now, rows)
        return rows

    def _classified(self, channel: SalesChannel, refresh: bool) -> tuple[list[ClassifiedMovement], list[str], list[dict[str, str]]]:
        classified: list[ClassifiedMovement] = []
        sources: list[str] = []
        warnings: list[dict[str, str]] = []
        for system in CHANNEL_SYSTEMS[channel]:
            try:
                rows = self._load(system, refresh)
            except Exception as exc:  # one unavailable system must not blank the page
                warnings.append({
                    "code": f"{system}_unavailable",
                    "message": f"داده {'راهکاران' if system == 'rahkaran' else 'کارآمد'} دریافت نشد؛ اعداد این بخش ناقص است. ({exc.__class__.__name__})",
                })
                continue
            sources.append(system)
            classified.extend(
                ClassifiedMovement(m, classify(m.system, m.direction, m.account_code, m.counterpart_code,
                                               m.counterpart_name, m.note))
                for m in rows
            )
        if channel == "all" and len(sources) < 2 and sources:
            warnings.append({
                "code": "settlement_elimination_partial",
                "message": "فقط یک سیستم در دسترس است؛ تسویه هیبرید با شرکت از هر دو طرف حذف شده ولی طرف دیگر قابل کنترل نیست.",
            })
        return classified, sources, warnings

    def _base_window(self, base_days: int) -> tuple[date, date]:
        """Complete days only: the window ends yesterday."""
        base_days = max(7, min(int(base_days), 365))
        return self.today - timedelta(days=base_days), self.today

    def _period(self, start: date, end: date) -> dict[str, Any]:
        last = end - timedelta(days=1)
        return {"from": start.isoformat(), "to": last.isoformat(), "from_jalali": format_jalali_date(start),
                "to_jalali": format_jalali_date(last), "days": (end - start).days}

    def _envelope(self, filters: dict[str, Any], data: dict[str, Any], sources: list[str],
                  warnings: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "status": "success",
            "as_of": self.today.isoformat(),
            "as_of_jalali": format_jalali_date(self.today),
            "filters": filters,
            "data": data,
            "sources": sources,
            "warnings": warnings,
        }

    def _month_comparison(self, rows: list[ClassifiedMovement]) -> dict[str, Any]:
        """Current Jalali month-to-date vs the same number of days of the previous month."""
        year, month = _jalali_ym(self.today)
        current_start = _jalali_month_start(year, month)
        elapsed = (self.today - current_start).days
        previous_start = _jalali_month_start(*_previous_ym(year, month))
        previous_end = min(previous_start + timedelta(days=elapsed), current_start)
        current = sum(r.signed_amount for r in rows if current_start <= r.movement.day < self.today)
        previous = sum(r.signed_amount for r in rows if previous_start <= r.movement.day < previous_end)
        return {
            "current_month": _month_label(year, month),
            "days_compared": elapsed,
            "current_month_to_date_rial": _round(current),
            "previous_month_same_period_rial": _round(previous),
            "change_percent": _change_percent(current, previous) if elapsed else None,
        }

    def _monthly_trend(self, rows: list[ClassifiedMovement], key: Callable[[ClassifiedMovement], str],
                       months: int = 12) -> list[dict[str, Any]]:
        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in rows:
            buckets[_jalali_ym(row.movement.day)][key(row)] += row.signed_amount
        trend = []
        for ym in _last_months(self.today, months):
            values = {k: _round(v) for k, v in buckets.get(ym, {}).items()}
            trend.append({"month": _month_label(*ym), "values": values, "total_rial": _round(sum(values.values()))})
        return trend

    @staticmethod
    def _settlement(rows: list[ClassifiedMovement], start: date, end: date, channel: SalesChannel) -> dict[str, Any]:
        """Hybrid ↔ company stock settlement seen from each side; never part of a group total."""
        received = paid = 0.0
        for r in rows:
            m = r.movement
            if r.classification.section != "internal" or not start <= m.day < end:
                continue
            if m.system == "rahkaran":
                received += m.amount_rial if m.direction == "inflow" else -m.amount_rial
            else:
                paid += m.amount_rial if m.direction == "outflow" else -m.amount_rial
        return {
            "received_by_company_rial": _round(received) if channel in ("b2b", "all") else None,
            "paid_by_hybrid_rial": _round(paid) if channel in ("hybrid", "all") else None,
            "eliminated_in_group": channel == "all",
            "rule": "هیبرید بهای موجودی را از طریق شرکت‌های گروه (پادینا، مولهنس، …) به شرکت می‌پردازد و همین پول در راهکاران «دریافت از هیبرید» ثبت می‌شود؛ در هر کانال جدا نمایش داده می‌شود و در جمع کل گروه حذف می‌شود.",
        }

    # -- section 3: inflows ---------------------------------------------------

    def inflows(self, base_days: int = 90, channel: SalesChannel = "all", method: str | None = None,
                refresh: bool = False) -> dict[str, Any]:
        rows, sources, warnings = self._classified(channel, refresh)
        start, end = self._base_window(base_days)
        inflow = [r for r in rows if r.classification.section == "inflow"
                  and (method is None or r.movement.method == method)]
        customer = [r for r in inflow if r.classification.category == "customer_collection"]
        in_base = [r for r in customer if start <= r.movement.day < end]

        daily: dict[date, float] = defaultdict(float)
        for r in in_base:
            daily[r.movement.day] += r.signed_amount
        stats = _daily_stats(daily, start, end)

        by_method: dict[str, float] = defaultdict(float)
        by_channel: dict[str, float] = defaultdict(float)
        for r in in_base:
            by_method[r.movement.method] += r.signed_amount
            by_channel[SYSTEM_CHANNEL[r.movement.system]] += r.signed_amount
        weekday_totals: dict[int, float] = defaultdict(float)
        for day, amount in daily.items():
            weekday_totals[day.weekday()] += amount
        weekday_counts: dict[int, int] = defaultdict(int)
        for i in range((end - start).days):
            weekday_counts[(start + timedelta(days=i)).weekday()] += 1

        other = sum(r.signed_amount for r in inflow
                    if r.classification.category == "other_operating_inflow" and start <= r.movement.day < end)
        data = {
            "base_period": self._period(start, end),
            "customer_collection": stats,
            "forecast_basis": {
                "median_daily_working_rial": stats["median_daily_rial"],
                "rule": "میانه ورودی روزانه در روزهای کاری (بدون جمعه) × روزهای کاری افق؛ برچسب «برآوردی».",
            },
            "month_comparison": self._month_comparison(customer),
            "by_method": _labelled_totals(by_method, "method", METHOD_LABELS),
            "by_channel": _labelled_totals(by_channel, "channel", CHANNEL_LABELS),
            "weekday_pattern": [
                {"weekday": w, "label": WEEKDAY_LABELS[w],
                 "average_rial": _round(weekday_totals[w] / weekday_counts[w]) if weekday_counts[w] else 0.0}
                for w in WEEKDAY_ORDER
            ],
            "monthly_trend": self._monthly_trend(customer, lambda r: SYSTEM_CHANNEL[r.movement.system]),
            "other_operating_inflow_rial": _round(other),
            "hybrid_settlement": self._settlement(rows, start, end, channel),
            "rule": "فقط وصول از مشتری نهایی (حواله و نقد) در میانگین می‌آید؛ چک، تسویه هیبرید با شرکت، انتقال بین‌بانکی، وام و سهامداران جدا هستند.",
        }
        return self._envelope({"base_days": (end - start).days, "channel": channel, "method": method},
                              data, sources, warnings)

    # -- section 4: outflows --------------------------------------------------

    def outflows(self, base_days: int = 90, channel: SalesChannel = "all", category: str | None = None,
                 refresh: bool = False) -> dict[str, Any]:
        rows, sources, warnings = self._classified(channel, refresh)
        start, end = self._base_window(base_days)
        outflow = [r for r in rows if r.classification.section == "outflow"
                   and (category is None or r.classification.category == category)]
        in_base = [r for r in outflow if start <= r.movement.day < end]

        daily_total: dict[date, float] = defaultdict(float)
        daily_by_category: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
        counts: dict[str, int] = defaultdict(int)
        by_channel: dict[str, float] = defaultdict(float)
        for r in in_base:
            daily_total[r.movement.day] += r.signed_amount
            daily_by_category[r.classification.category][r.movement.day] += r.signed_amount
            counts[r.classification.category] += r.movement.count
            by_channel[SYSTEM_CHANNEL[r.movement.system]] += r.signed_amount
        stats = _daily_stats(daily_total, start, end)

        categories = []
        for cat, daily in daily_by_category.items():
            cat_stats = _daily_stats(daily, start, end)
            categories.append({
                "category": cat,
                "label": CATEGORY_LABELS.get(cat, cat),
                "total_rial": cat_stats["total_rial"],
                "share_percent": round(cat_stats["total_rial"] / stats["total_rial"] * 100, 1) if stats["total_rial"] else None,
                "mean_daily_rial": cat_stats["mean_daily_rial"],
                "monthly_average_rial": _round(cat_stats["total_rial"] / ((end - start).days / 30)),
                "row_count": counts[cat],
                "month_comparison": self._month_comparison([r for r in outflow if r.classification.category == cat]),
            })
        categories.sort(key=lambda c: -c["total_rial"])

        data = {
            "base_period": self._period(start, end),
            "total": stats,
            "forecast_basis": {
                "median_daily_working_rial": stats["median_daily_rial"],
                "rule": "میانه خروجی روزانه در روزهای کاری (بدون جمعه) × روزهای کاری افق؛ برچسب «برآوردی».",
            },
            "month_comparison": self._month_comparison(outflow),
            "categories": categories,
            "by_channel": _labelled_totals(by_channel, "channel", CHANNEL_LABELS),
            "monthly_trend": self._monthly_trend(outflow, lambda r: r.classification.category),
            "hybrid_settlement": self._settlement(rows, start, end, channel),
            "rule": "پرداخت چکی (بخش ۲)، حقوق (بخش ۵)، تسویه هیبرید با شرکت، انتقال بین‌بانکی و برداشت سهامداران در این بخش نیستند؛ تنخواه فقط یک‌بار و هنگام شارژ حساب می‌شود.",
        }
        return self._envelope({"base_days": (end - start).days, "channel": channel, "category": category},
                              data, sources, warnings)

    # -- financing card -------------------------------------------------------

    def financing(self, base_days: int = 90, channel: SalesChannel = "all", refresh: bool = False) -> dict[str, Any]:
        rows, sources, warnings = self._classified(channel, refresh)
        start, end = self._base_window(base_days)
        financing = [r for r in rows if r.classification.section == "financing"]
        totals: dict[str, dict[str, float]] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0})
        for r in financing:
            if start <= r.movement.day < end:
                totals[r.classification.category][r.movement.direction] += r.movement.amount_rial
        items = [{
            "category": cat,
            "label": CATEGORY_LABELS.get(cat, cat),
            "inflow_rial": _round(v["inflow"]),
            "outflow_rial": _round(v["outflow"]),
            "net_rial": _round(v["inflow"] - v["outflow"]),
        } for cat, v in sorted(totals.items())]

        trend_buckets: dict[tuple[int, int], float] = defaultdict(float)
        for r in financing:
            m = r.movement
            trend_buckets[_jalali_ym(m.day)] += m.amount_rial if m.direction == "inflow" else -m.amount_rial
        data = {
            "base_period": self._period(start, end),
            "items": items,
            "inflow_rial": _round(sum(i["inflow_rial"] for i in items)),
            "outflow_rial": _round(sum(i["outflow_rial"] for i in items)),
            "net_rial": _round(sum(i["net_rial"] for i in items)),
            "monthly_net_trend": [{"month": _month_label(*ym), "net_rial": _round(trend_buckets.get(ym, 0.0))}
                                  for ym in _last_months(self.today, 12)],
            "in_forecast": False,
            "rule": "وام دریافتی و گردش سهامداران/جاری شرکا؛ جدا نمایش داده می‌شود و وارد پیش‌بینی نمی‌شود. اقساط وام در خروجی است.",
        }
        return self._envelope({"base_days": (end - start).days, "channel": channel}, data, sources, warnings)

    # -- data quality ---------------------------------------------------------

    def data_quality(self, base_days: int = 90, channel: SalesChannel = "all", refresh: bool = False) -> dict[str, Any]:
        rows, sources, warnings = self._classified(channel, refresh)
        start, end = self._base_window(base_days)
        in_base = [r for r in rows if start <= r.movement.day < end]
        review: dict[tuple[str, str, str | None, str | None], dict[str, float]] = defaultdict(
            lambda: {"inflow": 0.0, "outflow": 0.0, "count": 0})
        excluded: dict[str, float] = defaultdict(float)
        for r in in_base:
            m = r.movement
            if r.classification.section == "review":
                bucket = review[(r.classification.category, m.system, m.account_code, m.account_name)]
                bucket[m.direction] += m.amount_rial
                bucket["count"] += m.count
            elif r.classification.section == "excluded":
                excluded[r.classification.category] += m.amount_rial
        items = [{
            "category": cat,
            "label": CATEGORY_LABELS.get(cat, cat),
            "system": system,
            "channel": SYSTEM_CHANNEL[system],
            "account_code": code,
            "account_name": name,
            "inflow_rial": _round(v["inflow"]),
            "outflow_rial": _round(v["outflow"]),
            "row_count": int(v["count"]),
        } for (cat, system, code, name), v in review.items()]
        items.sort(key=lambda i: -(i["inflow_rial"] + i["outflow_rial"]))
        data = {
            "base_period": self._period(start, end),
            "review_items": items,
            "review_total_rial": _round(sum(i["inflow_rial"] + i["outflow_rial"] for i in items)),
            "excluded_totals": _labelled_totals(excluded, "category", CATEGORY_LABELS),
            "hybrid_settlement": self._settlement(rows, start, end, channel),
            "rule": "اقلام «نیازمند بازبینی» در هیچ جمعی حساب نمی‌شوند تا حسابشان در account_map مشخص شود.",
        }
        return self._envelope({"base_days": (end - start).days, "channel": channel}, data, sources, warnings)
