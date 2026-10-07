"""Section 5 of the liquidity dashboard: personnel payroll per company.

Rahkaran (HCM3) holds اکسیر، کادوس and فراز بهداشت, split by each employee's social-insurance
workshop in the payroll month.  Karamad's payroll module belongs entirely to زرین کالای کادوس,
whose sales staff are paid a monthly commission («اضافات»).  The forecast repeats each group's
last complete month (commission included, not modelled yet) on its own usual pay day.  Rahkaran months
are grouped by ``PayCalcItem.IssueYearMonth`` (one row per employee and factor per month,
verified on live data).

Grand total = net pay + employer's social insurance share (employee share and payroll tax are withheld, not a company cost),
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

# Each employee's company = the social-insurance workshop valid in that payroll month; the
# workshop's party is named after the company («... شعبه اشتهارد 0040 - اکسیر»).
PAYROLL_SQL = text(f"""
    WITH paid AS (
        SELECT DISTINCT i.[IssueYearMonth] AS [YearMonth], i.[EmployeeRef]
        FROM HCM3.[PayCalcItem] AS i
        WHERE i.[IssueYearMonth] >= :from_year_month
    ),
    workshop AS (
        SELECT paid.[YearMonth], paid.[EmployeeRef], ero.[OrganizationBranchRef],
               ROW_NUMBER() OVER (PARTITION BY paid.[YearMonth], paid.[EmployeeRef]
                                  ORDER BY ero.[EffectiveYearMonth] DESC, ero.[EmployeeRelatedOrganizationID] DESC) AS [rn]
        FROM paid
        INNER JOIN HCM3.[EmployeeRelatedOrganization] AS ero
            ON ero.[EmployeeRef] = paid.[EmployeeRef] AND ero.[IsInsurance] = 1
           AND ero.[EffectiveYearMonth] <= paid.[YearMonth]
           AND (ero.[ExpiryYearMonth] IS NULL OR ero.[ExpiryYearMonth] >= paid.[YearMonth])
    )
    SELECT i.[IssueYearMonth] AS [YearMonth], i.[CompensationFactorRef] AS [Factor],
           party.[CompanyName] AS [Workshop],
           COUNT(DISTINCT i.[EmployeeRef]) AS [Employees], SUM(i.[Value]) AS [Amount]
    FROM HCM3.[PayCalcItem] AS i
    LEFT JOIN workshop AS w
        ON w.[EmployeeRef] = i.[EmployeeRef] AND w.[YearMonth] = i.[IssueYearMonth] AND w.[rn] = 1
    LEFT JOIN HCM3.[OrganizationBranch] AS ob ON ob.[OrganizationBranchID] = w.[OrganizationBranchRef]
    LEFT JOIN GNR3.[Party] AS party ON party.[PartyID] = ob.[PartyRef]
    WHERE i.[CompensationFactorRef] IN ({", ".join(str(f) for f in PAYROLL_FACTORS)})
      AND i.[IssueYearMonth] >= :from_year_month
    GROUP BY i.[IssueYearMonth], i.[CompensationFactorRef], party.[CompanyName]
""")

# Karamad payroll belongs entirely to زرین کالای کادوس.  SumP = net pay (= Impure − employee
# insurance − SalaryTaxP); sales commission is booked in AdditionP («اضافات»), the
# CommissionP column is never used.
ZARIN_PAYROLL_SQL = text("""
    SELECT CAST([FiscalName] AS int) AS [Year], [MonthRef] AS [Month],
           COUNT(DISTINCT [EmployeeRef]) AS [Employees],
           SUM(ISNULL([FunctionP], 0)) AS [BasePay], SUM(ISNULL([AdditionP], 0)) AS [Commission],
           SUM(ISNULL([Impure], 0)) AS [Gross], SUM(ISNULL([SumP], 0)) AS [NetPay],
           SUM(ISNULL([InsuranceP], 0)) AS [EmployeeInsurance], SUM(ISNULL([InsuranceCP], 0)) AS [EmployerInsurance],
           SUM(ISNULL([SalaryTaxP], 0)) AS [Tax],
           COUNT(DISTINCT CASE WHEN [DepartmentName] LIKE N'%فروش%' THEN [EmployeeRef] END) AS [SalesEmployees],
           SUM(CASE WHEN [DepartmentName] LIKE N'%فروش%' THEN ISNULL([AdditionP], 0) ELSE 0 END) AS [SalesCommission]
    FROM dbo.[vwPR_Salary]
    WHERE CAST([FiscalName] AS int) * 100 + [MonthRef] >= :from_year_month
    GROUP BY CAST([FiscalName] AS int), [MonthRef]
""")

# Settlement of «حقوق و دستمزد پرداختی/حقوق پرداختنی» in Karamad's books: one large line a
# month on the pay day.  Used only to find Zarin's usual pay day.
ZARIN_PAYMENTS_SQL = text("""
    SELECT CAST(v.[DateE] AS date) AS [Day], SUM(l.[Debtor]) AS [Amount]
    FROM dbo.[tblVoucherLines] AS l
    INNER JOIN dbo.[tblVoucher] AS v ON v.[ID] = l.[VoucherRef]
    INNER JOIN dbo.[tblSL] AS sl ON sl.[ID] = l.[SLRef]
    WHERE sl.[Code] IN (3220, 3238) AND l.[Debtor] > 0 AND ISNULL(l.[isDeleted], 0) = 0
      AND v.[DateE] >= :date_from
    GROUP BY CAST(v.[DateE] AS date)
""")

# Rahkaran companies, matched in this order on the insurance workshop's name.
RAHKARAN_COMPANIES = (("faraz", "فراز", "فراز بهداشت"), ("exir", "اکسیر", "اکسیر"), ("kadus", "کادوس", "کادوس"))
UNINSURED_COMPANY = ("uninsured", "بدون بیمه (راهکاران)")
ZARIN_COMPANY = ("zarin", "زرین کالای کادوس")

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


def fetch_zarin_payroll_rows(from_year_month: int) -> list[dict[str, Any]]:
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    with get_karamad_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(ZARIN_PAYROLL_SQL, {"from_year_month": from_year_month}).mappings()]


def fetch_zarin_payments(date_from: date) -> list[dict[str, Any]]:
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    with get_karamad_sqlserver_engine().connect() as connection:
        return [dict(r) for r in connection.execute(ZARIN_PAYMENTS_SQL, {"date_from": date_from}).mappings()]


def rahkaran_company(workshop: str | None) -> tuple[str, str]:
    for key, needle, label in RAHKARAN_COMPANIES:
        if needle in (workshop or ""):
            return key, label
    return UNINSURED_COMPANY


def _mark_complete(months: list[dict[str, Any]]) -> None:
    """A trailing month whose headcount is far below the recent norm is still being calculated.

    Only the latest months can be in progress: a past dip followed by a full month (e.g. a
    Nowruz Farvardin) is a real, finished month.
    """
    for index, item in enumerate(months):
        previous = [m["headcount"] for m in months[max(0, index - 3):index]]
        norm = median(previous) if previous else item["headcount"]
        item["complete"] = bool(norm) and item["headcount"] >= norm * COMPLETE_HEADCOUNT_RATIO
    last_complete = max((i for i, m in enumerate(months) if m["complete"]), default=-1)
    for item in months[:last_complete]:
        item["complete"] = True


def _month_item(ym: int, headcount: int, net: float, employee_ins: float, employer_ins: float,
                tax: float) -> dict[str, Any]:
    # Management decision (1405/07/14): the employee's insurance share and the payroll tax are
    # withheld from the salary and are not a company cost, so the total is net pay + the
    # employer's insurance share; both are kept in the payload for reference.
    return {
        "year_month": ym,
        "month": _month_label(ym),
        "headcount": headcount,
        "net_pay_rial": _round(net),
        "employee_insurance_rial": _round(employee_ins),
        "employer_insurance_rial": _round(employer_ins),
        "insurance_rial": _round(employer_ins),
        "tax_rial": _round(tax),
        "insurance_and_tax_rial": _round(employer_ins + tax),
        "total_rial": _round(net + employer_ins),
    }


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
        fetch_zarin: Callable[[int], list[dict[str, Any]]] = fetch_zarin_payroll_rows,
        fetch_zarin_payments: Callable[[date], list[dict[str, Any]]] = fetch_zarin_payments,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
    ):
        self.today = today or date.today()
        self.fetch_rows = fetch_rows
        self.fetch_payments = fetch_payments
        self.fetch_zarin = fetch_zarin
        self.fetch_zarin_payments = fetch_zarin_payments
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

    def _from_year_month(self) -> int:
        year, month, _ = _jalali(self.today)
        return _ym_int(*_add_months(year, month, -15))

    def _rahkaran_rows(self, refresh: bool) -> list[dict[str, Any]]:
        from_ym = self._from_year_month()
        return self._cached("payroll_rows", lambda: self.fetch_rows(from_ym), refresh)

    @staticmethod
    def _series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rahkaran factor rows (possibly several workshops per month) → one item per month."""
        by_month: dict[int, dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"employees": 0, "amount": 0.0}))
        for row in rows:
            cell = by_month[int(row["YearMonth"])][int(row["Factor"])]
            cell["employees"] += int(row["Employees"] or 0)
            cell["amount"] += float(row["Amount"] or 0)
        months = []
        for ym in sorted(by_month):
            factors = by_month[ym]
            amount = lambda factor: factors[factor]["amount"] if factor in factors else 0.0  # noqa: E731
            headcount = factors[FACTOR_NET_PAY]["employees"] if FACTOR_NET_PAY in factors else 0
            months.append(_month_item(ym, headcount, amount(FACTOR_NET_PAY), amount(FACTOR_EMPLOYEE_INSURANCE),
                                      amount(FACTOR_EMPLOYER_INSURANCE), amount(FACTOR_PAYROLL_TAX)))
        _mark_complete(months)
        return months

    def _months(self, refresh: bool) -> list[dict[str, Any]]:
        """Rahkaran group total per month (all companies); the basis of the forecast."""
        return self._series(self._rahkaran_rows(refresh))

    def _rahkaran_companies(self, refresh: bool, group: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows_by_company: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in self._rahkaran_rows(refresh):
            rows_by_company[rahkaran_company(row.get("Workshop"))].append(row)
        # A company month is complete when the group month is (the run covers everyone at once).
        complete = {m["year_month"]: m["complete"] for m in group}
        order = [(k, label) for k, _, label in RAHKARAN_COMPANIES] + [UNINSURED_COMPANY]
        companies = []
        for key, label in order:
            if (key, label) not in rows_by_company:
                continue
            months = self._series(rows_by_company[(key, label)])
            for m in months:
                m["complete"] = complete.get(m["year_month"], m["complete"])
            companies.append({"key": key, "label": label, "system": "rahkaran", "channel": "b2b", "months": months})
        return companies

    def _zarin(self, refresh: bool) -> dict[str, Any]:
        from_ym = self._from_year_month()
        rows = self._cached("zarin_payroll_rows", lambda: self.fetch_zarin(from_ym), refresh)
        months = []
        for row in sorted(rows, key=lambda r: (int(r["Year"]), int(r["Month"]))):
            ym = _ym_int(int(row["Year"]), int(row["Month"]))
            value = lambda name: float(row.get(name) or 0)  # noqa: E731
            item = _month_item(ym, int(row["Employees"] or 0), value("NetPay"), value("EmployeeInsurance"),
                               value("EmployerInsurance"), value("Tax"))
            item.update({
                "base_pay_rial": _round(value("BasePay")),
                "commission_rial": _round(value("Commission")),
                "sales_commission_rial": _round(value("SalesCommission")),
                "sales_headcount": int(row.get("SalesEmployees") or 0),
                "gross_rial": _round(value("Gross")),
            })
            months.append(item)
        _mark_complete(months)
        key, label = ZARIN_COMPANY
        return {"key": key, "label": label, "system": "karamad", "channel": "hybrid", "months": months}

    # -- pay day --------------------------------------------------------------

    def _pay_day(self, refresh: bool, zarin: bool = False) -> dict[str, Any]:
        """Usual Jalali day of month of the largest payroll payment in each recent month."""
        since = self.today - timedelta(days=31 * (PAY_DAY_HISTORY_MONTHS + 1))
        if zarin:
            payments = self._cached("zarin_payroll_payments", lambda: self.fetch_zarin_payments(since), refresh)
        else:
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
            "rule": ("روز ماه شمسیِ بزرگ‌ترین تسویه «حقوق و دستمزد پرداختی» (۳۲۲۰/۳۲۳۸) کارآمد در هر یک از ۶ ماه اخیر؛ میانه این روزها."
                     if zarin else "روز ماه شمسیِ بزرگ‌ترین پرداخت حقوق (عامل ۵۱۲۰۰۲) در هر یک از ۶ ماه اخیر؛ میانه این روزها."),
        }

    # -- forecast -------------------------------------------------------------

    def schedule(self, horizon_days: int, refresh: bool = False, channel: str = "all") -> list[dict[str, Any]]:
        """Expected payroll outflows inside [today, today + horizon_days).

        Each company group's last complete month, once a month on its own usual pay day:
        Rahkaran (B2B) and Zarin (Karamad, hybrid).  Zarin is skipped when Karamad is down.
        """
        items: list[dict[str, Any]] = []
        if channel in ("b2b", "all"):
            complete = [m for m in self._months(refresh) if m["complete"]]
            items += self._monthly_items(horizon_days, complete[-1] if complete else None,
                                         self._pay_day(refresh)["usual_day_of_month"], "rahkaran", "راهکاران")
        if channel in ("hybrid", "all"):
            try:
                zarin = [m for m in self._zarin(refresh)["months"] if m["complete"]]
                pay_day = self._pay_day(refresh, zarin=True)["usual_day_of_month"]
            except Exception:
                zarin, pay_day = [], None
            items += self._monthly_items(horizon_days, zarin[-1] if zarin else None, pay_day, "zarin", ZARIN_COMPANY[1])
        return sorted(items, key=lambda i: i["date"])

    def _monthly_items(self, horizon_days: int, basis: dict[str, Any] | None, pay_day: int | None,
                       group: str, label: str) -> list[dict[str, Any]]:
        if basis is None or pay_day is None:
            return []
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
                    "group": group,
                    "label": label,
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

        companies = self._rahkaran_companies(refresh, all_months)
        sources = ["rahkaran"]
        try:
            companies.append(self._zarin(refresh))
            sources.append("karamad")
        except Exception as exc:
            warnings.append({"code": "karamad_unavailable",
                             "message": f"حقوق زرین از کارآمد دریافت نشد. ({exc.__class__.__name__})"})
        trend_length = max(1, min(int(months), 24))
        company_cards = []
        for company in companies:
            done = [m for m in company.pop("months") if m["complete"]]
            last, before = (done[-1] if done else None), (done[-2] if len(done) > 1 else None)
            company_cards.append({
                **company,
                "latest_month": last,
                "total_change_percent": None if not last or not before or not before["total_rial"]
                else round((last["total_rial"] - before["total_rial"]) / before["total_rial"] * 100, 1),
                "monthly_trend": done[-trend_length:],
            })
        # Month × company table: every complete month of every company.
        table: dict[str, dict[str, Any]] = {}
        for company in company_cards:
            for m in company["monthly_trend"]:
                row = table.setdefault(m["month"], {"month": m["month"], "companies": {}, "total_rial": 0.0, "headcount": 0})
                row["companies"][company["key"]] = m["total_rial"]
                row["total_rial"] = _round(row["total_rial"] + m["total_rial"])
                row["headcount"] += m["headcount"]
        by_company_monthly = [table[k] for k in sorted(table)][-trend_length:]

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
            "companies": company_cards,
            "by_company_monthly": by_company_monthly,
            "in_progress_months": [{"month": m["month"], "headcount": m["headcount"]} for m in in_progress],
            "pay_day": pay_day,
            "forecast": schedule,
            "rule": "اکسیر، کادوس و فراز از راهکاران به تفکیک کارگاه بیمه هر کارمند در همان ماه؛ کارکنان بدون کارگاه بیمه جدا آمده‌اند. زرین از حقوق کارآمد؛ پورسانت فروش زرین = «اضافات» فیش هر ماه. جمع کل = خالص پرداختی + بیمه سهم کارفرما؛ بیمه سهم کارمند و مالیات حقوق از حقوق کسر می‌شوند و هزینه شرکت حساب نمی‌شوند. در پیش‌بینی نقدینگی، جمع آخرین ماه کامل راهکاران و زرین (با همان پورسانت ثبت‌شده) هر کدام روی روز معمول پرداخت خودش می‌آید؛ پورسانت ماه‌های آینده فعلاً مدل نمی‌شود.",
        }
        return {
            "status": "success", "as_of": self.today.isoformat(), "as_of_jalali": format_jalali_date(self.today),
            "filters": {"months": months, "horizon_days": horizon_days}, "data": data,
            "sources": sources, "warnings": warnings,
        }
