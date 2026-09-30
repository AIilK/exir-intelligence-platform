"""Section 5 of the liquidity dashboard: personnel payroll, from Rahkaran only.

Management decision: every payroll figure comes from Rahkaran (HCM3); Karamad payroll
is ignored.  Monthly figures are grouped by ``PayCalcItem.IssueYearMonth`` (one row per
employee and factor per month, verified on live data).

Grand total = net pay + social insurance (employee and employer share) + payroll tax,
i.e. all cash that leaves the company for a payroll month.  The forecast places the last
fully calculated month's total, in one lump, on the usual pay day of each coming month.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any, Callable

from sqlalchemy import text

from app.utils.jalali import _gregorian_to_jalali, _jalali_to_gregorian, format_jalali_date

FACTOR_NET_PAY = 63                 # NetPay — خالص پرداختی
FACTOR_EMPLOYEE_INSURANCE = 46      # EmployeeMainInsurance — بیمه تامین اجتماعی سهم کارمند
FACTOR_EMPLOYER_INSURANCE = 64      # BossMainInsurance — بیمه تامین اجتماعی سهم کارفرما
FACTOR_PAYROLL_TAX = 49             # MonthlyTax — مالیات حقوق
PAYROLL_FACTORS = (FACTOR_NET_PAY, FACTOR_EMPLOYEE_INSURANCE, FACTOR_EMPLOYER_INSURANCE, FACTOR_PAYROLL_TAX)
PAYROLL_PAYMENT_FACTOR = "512002"   # CashFlowFactor «حقوق و دستمزد پرداختنی»

# A month whose headcount is below this share of the recent norm is still being calculated
# (e.g. 1405/06 had 8 employees while the months before had ~143).
COMPLETE_HEADCOUNT_RATIO = 0.8
PAY_DAY_HISTORY_MONTHS = 6
CACHE_TTL_SECONDS = 300

PAYROLL_SQL = text(f"""
    SELECT i.[IssueYearMonth] AS [YearMonth], i.[CompensationFactorRef] AS [Factor],
           COUNT(DISTINCT i.[EmployeeRef]) AS [Employees], SUM(i.[Value]) AS [Amount]
    FROM HCM3.[PayCalcItem] AS i
    WHERE i.[CompensationFactorRef] IN ({", ".join(str(f) for f in PAYROLL_FACTORS)})
      AND i.[IssueYearMonth] >= :from_year_month
    GROUP BY i.[IssueYearMonth], i.[CompensationFactorRef]
""")

PAYROLL_PAYMENTS_SQL = text("""
    SELECT CAST(h.[Date] AS date) AS [Day], SUM(t.[Amount]) AS [Amount]
    FROM (
        SELECT d.[PaymentRef], d.[Amount], d.[CashFlowFactorRef] FROM RPA3.[PaymentDeposit] AS d
        UNION ALL
        SELECT d.[PaymentRef], d.[Amount], d.[CashFlowFactorRef] FROM RPA3.[PaymentCashMoney] AS d
    ) AS t
    INNER JOIN RPA3.[Payment] AS h ON h.[PaymentID] = t.[PaymentRef]
    INNER JOIN RPA3.[CashFlowFactor] AS f ON f.[CashFlowFactorID] = t.[CashFlowFactorRef]
    WHERE h.[ApproveState] = 3 AND f.[Number] = :factor AND h.[Date] >= :date_from
    GROUP BY CAST(h.[Date] AS date)
""")


def _jalali(day: date) -> tuple[int, int, int]:
    return _gregorian_to_jalali(day.year, day.month, day.day)


def _ym_int(year: int, month: int) -> int:
    return year * 100 + month


def _split_ym(value: int) -> tuple[int, int]:
    return value // 100, value % 100


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _jalali_date(year: int, month: int, day: int) -> date:
    # Months 7-11 have 30 days and Esfand 29/30: clamp so the date always exists.
    last_day = 31 if month <= 6 else 30
    day = min(day, last_day)
    while True:
        try:
            gregorian = date(*_jalali_to_gregorian(year, month, day))
        except ValueError:
            day -= 1
            continue
        if _jalali(gregorian)[1] == month:
            return gregorian
        day -= 1


def _month_label(value: int) -> str:
    year, month = _split_ym(value)
    return f"{year:04d}/{month:02d}"


def _round(value: float) -> float:
    return round(float(value), 2)


def fetch_payroll_rows(from_year_month: int) -> list[dict[str, Any]]:
    from app.database.sqlserver import get_sqlserver_engine
    with get_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(PAYROLL_SQL, {"from_year_month": from_year_month}).mappings()]


def fetch_payroll_payments(date_from: date) -> list[dict[str, Any]]:
    from app.database.sqlserver import get_sqlserver_engine
    with get_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(
            PAYROLL_PAYMENTS_SQL, {"factor": PAYROLL_PAYMENT_FACTOR, "date_from": date_from}).mappings()]


_cache: dict[tuple[str, date], tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


class PayrollService:
    def __init__(
        self,
        today: date | None = None,
        fetch_rows: Callable[[int], list[dict[str, Any]]] = fetch_payroll_rows,
        fetch_payments: Callable[[date], list[dict[str, Any]]] = fetch_payroll_payments,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
    ):
        self.today = today or date.today()
        self.fetch_rows = fetch_rows
        self.fetch_payments = fetch_payments
        self.cache_ttl_seconds = cache_ttl_seconds

    def _cached(self, name: str, loader: Callable[[], Any], refresh: bool) -> Any:
        key = (name, self.today)
        now = time.monotonic()
        with _cache_lock:
            hit = _cache.get(key)
            if hit and not refresh and now - hit[0] < self.cache_ttl_seconds:
                return hit[1]
        value = loader()
        with _cache_lock:
            _cache[key] = (now, value)
        return value

    # -- monthly figures ------------------------------------------------------

    def _months(self, refresh: bool) -> list[dict[str, Any]]:
        year, month, _ = _jalali(self.today)
        from_ym = _ym_int(*_add_months(year, month, -15))
        rows = self._cached("payroll_rows", lambda: self.fetch_rows(from_ym), refresh)
        by_month: dict[int, dict[int, dict[str, float]]] = defaultdict(dict)
        for row in rows:
            by_month[int(row["YearMonth"])][int(row["Factor"])] = {
                "employees": int(row["Employees"] or 0), "amount": float(row["Amount"] or 0)}
        months = []
        for ym in sorted(by_month):
            factors = by_month[ym]
            amount = lambda factor: factors.get(factor, {}).get("amount", 0.0)  # noqa: E731
            net = amount(FACTOR_NET_PAY)
            insurance = amount(FACTOR_EMPLOYEE_INSURANCE) + amount(FACTOR_EMPLOYER_INSURANCE)
            tax = amount(FACTOR_PAYROLL_TAX)
            months.append({
                "year_month": ym,
                "month": _month_label(ym),
                "headcount": factors.get(FACTOR_NET_PAY, {}).get("employees", 0),
                "net_pay_rial": _round(net),
                "employee_insurance_rial": _round(amount(FACTOR_EMPLOYEE_INSURANCE)),
                "employer_insurance_rial": _round(amount(FACTOR_EMPLOYER_INSURANCE)),
                "insurance_rial": _round(insurance),
                "tax_rial": _round(tax),
                "insurance_and_tax_rial": _round(insurance + tax),
                "total_rial": _round(net + insurance + tax),
            })
        # Mark months still being calculated: headcount far below the recent norm.
        for index, item in enumerate(months):
            previous = [m["headcount"] for m in months[max(0, index - 3):index]]
            norm = median(previous) if previous else item["headcount"]
            item["complete"] = bool(norm) and item["headcount"] >= norm * COMPLETE_HEADCOUNT_RATIO
        return months

    # -- pay day --------------------------------------------------------------

    def _pay_day(self, refresh: bool) -> dict[str, Any]:
        """Usual Jalali day of month of the largest payroll payment in each recent month."""
        since = self.today - timedelta(days=31 * (PAY_DAY_HISTORY_MONTHS + 1))
        payments = self._cached("payroll_payments", lambda: self.fetch_payments(since), refresh)
        current_month = _jalali(self.today)[:2]
        largest: dict[tuple[int, int], tuple[float, date]] = {}
        for row in payments:
            day = row["Day"] if isinstance(row["Day"], date) else date.fromisoformat(str(row["Day"])[:10])
            jy, jm, _ = _jalali(day)
            # The current month may not have had its payroll run yet.
            if day >= self.today or (jy, jm) == current_month:
                continue
            amount = float(row["Amount"] or 0)
            if (jy, jm) not in largest or amount > largest[(jy, jm)][0]:
                largest[(jy, jm)] = (amount, day)
        recent = sorted(largest.items())[-PAY_DAY_HISTORY_MONTHS:]
        days = [_jalali(day)[2] for _, (_, day) in recent]
        return {
            "usual_day_of_month": int(median(days)) if days else None,
            "observed": [{"month": f"{ym[0]:04d}/{ym[1]:02d}", "date": day.isoformat(),
                          "date_jalali": format_jalali_date(day), "amount_rial": _round(amount)}
                         for ym, (amount, day) in recent],
            "rule": "روز ماه شمسیِ بزرگ‌ترین پرداخت حقوق (عامل ۵۱۲۰۰۲) در هر یک از ۶ ماه اخیر؛ میانه این روزها.",
        }

    # -- forecast -------------------------------------------------------------

    def schedule(self, horizon_days: int, refresh: bool = False) -> list[dict[str, Any]]:
        """Expected payroll outflows inside [today, today + horizon_days)."""
        months = self._months(refresh)
        complete = [m for m in months if m["complete"]]
        pay_day = self._pay_day(refresh)["usual_day_of_month"]
        if not complete or pay_day is None:
            return []
        basis = complete[-1]
        end = self.today + timedelta(days=horizon_days)
        year, month, _ = _jalali(self.today)
        items = []
        for offset in range(0, horizon_days // 28 + 2):
            jy, jm = _add_months(year, month, offset)
            expected = _jalali_date(jy, jm, pay_day)
            if self.today <= expected < end:
                payroll_month = _add_months(jy, jm, -1)
                items.append({
                    "date": expected.isoformat(),
                    "date_jalali": format_jalali_date(expected),
                    "payroll_month": f"{payroll_month[0]:04d}/{payroll_month[1]:02d}",
                    "amount_rial": basis["total_rial"],
                    "basis_month": basis["month"],
                })
        return items

    # -- section payload ------------------------------------------------------

    def report(self, months: int = 12, horizon_days: int = 90, refresh: bool = False) -> dict[str, Any]:
        warnings: list[dict[str, str]] = []
        try:
            all_months = self._months(refresh)
            pay_day = self._pay_day(refresh)
            schedule = self.schedule(horizon_days, refresh)
        except Exception as exc:
            return {
                "status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
                "filters": {"months": months, "horizon_days": horizon_days}, "data": None, "sources": [],
                "warnings": [{"code": "rahkaran_unavailable",
                              "message": f"داده حقوق راهکاران دریافت نشد. ({exc.__class__.__name__})"}],
            }
        complete = [m for m in all_months if m["complete"]]
        latest = complete[-1] if complete else None
        previous = complete[-2] if len(complete) > 1 else None
        in_progress = [m for m in all_months if not m["complete"] and (latest is None or m["year_month"] > latest["year_month"])]
        if not complete:
            warnings.append({"code": "no_complete_month", "message": "هیچ ماه حقوقی کاملی در HCM3 پیدا نشد."})
        trend = complete[-max(1, min(int(months), 24)):]

        def change(key: str) -> float | None:
            if not latest or not previous or not previous[key]:
                return None
            return round((latest[key] - previous[key]) / previous[key] * 100, 1)

        data = {
            "latest_month": latest,
            "kpis": None if latest is None else {
                "headcount": latest["headcount"],
                "net_pay_rial": latest["net_pay_rial"],
                "insurance_and_tax_rial": latest["insurance_and_tax_rial"],
                "total_rial": latest["total_rial"],
                "total_change_percent": change("total_rial"),
                "headcount_change": None if not previous else latest["headcount"] - previous["headcount"],
            },
            "monthly_trend": trend,
            "in_progress_months": [{"month": m["month"], "headcount": m["headcount"]} for m in in_progress],
            "pay_day": pay_day,
            "forecast": schedule,
            "rule": "همه اعداد حقوق فقط از راهکاران (HCM3) است. جمع کل = خالص پرداختی + بیمه سهم کارمند و کارفرما + مالیات حقوق. در پیش‌بینی، جمع آخرین ماه کامل یکجا روی روز معمول پرداخت هر ماه قرار می‌گیرد.",
        }
        return {
            "status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
            "filters": {"months": months, "horizon_days": horizon_days}, "data": data,
            "sources": ["rahkaran"], "warnings": warnings,
        }
