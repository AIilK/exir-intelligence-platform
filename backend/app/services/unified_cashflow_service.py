from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.sqlserver import get_sqlserver_engine
from app.services.received_cheque_current_status import received_cheque_is_approved_open_holding
from app.services.finance_prediction_service import FinancePredictionService
from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
from app.services.treasury_service import _as_jalali_date


class UnifiedDailyCashflowService:
    """A selectable cash runway, built only from read-only company data."""

    SALARY_MONTHLY_RIAL = 100_000_000_000  # 10 billion toman
    BASE_PORTFOLIO_RETURN_RATE_PERCENT = 25.0
    MIN_PORTFOLIO_RETURN_RATE_PERCENT = 20.0
    MAX_PORTFOLIO_RETURN_RATE_PERCENT = 30.0
    EXPENSE_CATEGORY_RULES = (
        ("tax_insurance", "مالیات و بیمه", ("مالیات", "دارایی", "بیمه", "تأمین اجتماعی", "تامين اجتماعي"), False),
        ("production_procurement", "مواد، بسته‌بندی و خرید تولید", ("مواد اولیه", "مواد اوليه", "کارتن", "قوطی", "قوطي", "لیبل", "برچسب", "بسته بندی", "بسته‌بندی", "چاپ", "مقوا", "خرید مواد", "خريد مواد"), True),
        ("freight", "حمل‌ونقل و لجستیک", ("باربری", "باربري", "حمل", "کرایه", "کرايه", "پست", "ارسال"), True),
        ("utilities_admin", "اداری و زیرساخت", ("برق", "آب", "گاز", "تلفن", "اینترنت", "اينترنت", "اجاره", "دفتر"), True),
        ("services", "خدمات و تعمیرات", ("خدمات", "مشاوره", "تعمیر", "تعمير", "نگهداری", "نگهداري", "پیمانکار", "پيمانکار"), True),
    )
    EXCLUDED_EXPENSE_KEYWORDS = ("تنخواه", "انتقال", "بانک به بانک", "بانک‌به‌بانک", "حواله شرکتی", "طرف حساب شرکتی", "سهامدار", "سود سهام", "وام", "بهره وام", "خرید دارایی", "خريد دارايي", "افزایش سرمایه", "افزايش سرمايه")

    def __init__(self, *, forecast_days: int = 30, history_days: int = 365,
                 allowed_term_days: int = 90, engine: Engine | None = None,
                 monthly_service: MonthlyCashflowExcelService | None = None):
        self.forecast_days = max(7, min(int(forecast_days), 180))
        self.history_days = max(30, min(int(history_days), 730))
        self.allowed_term_days = max(1, min(int(allowed_term_days), 365))
        self.engine = engine or get_sqlserver_engine()
        self.monthly_service = monthly_service or MonthlyCashflowExcelService()

    def build(self) -> dict[str, Any]:
        snapshot = self.monthly_service.latest_snapshot()
        opening_cash = float(snapshot.get("liquidity_rial") or 0) if snapshot else None
        prediction = FinancePredictionService(
            forecast_days=self.forecast_days, history_days=self.history_days,
            allowed_term_days=self.allowed_term_days, opening_cash=opening_cash,
            engine=self.engine,
        )
        base = prediction.cash_shortage_forecast()
        cheque_report = prediction.cheque_return_predictions(
            limit=None, batch_size=1000, include_all_open=True,
        )
        today = date.fromisoformat(base["as_of_date"])
        portfolio_reliability = self._portfolio_reliability()
        reliable_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        nominal_received_total = 0.0
        risk_reduction_total = 0.0
        for cheque in cheque_report.get("cheques") or []:
            days_to_due = cheque.get("days_to_due")
            if days_to_due is None:
                continue
            due_day = today + timedelta(days=int(days_to_due))
            if not 0 <= (due_day - today).days < self.forecast_days:
                continue
            amount = float(cheque.get("amount") or 0)
            collectible_amount = amount * portfolio_reliability["reliability_percent"] / 100.0
            nominal_received_total += amount
            risk_reduction_total += amount - collectible_amount
            reliable_by_day[due_day].append({
                "cheque_id": cheque.get("cheque_id"),
                "counterpart_name": cheque.get("counterpart_name"),
                "nominal_amount_rial": round(amount, 2),
                "amount_rial": round(collectible_amount, 2),
                "portfolio_reliability_percent": portfolio_reliability["reliability_percent"],
                "individual_reliability_percent": cheque.get("recommended_reliance_percent"),
                "due_date_jalali": cheque.get("due_date_jalali"),
                "source_system": "rahkaran",
            })

        # V106: current KarAmand received-cheque snapshot has real due dates.
        # Open future items are now part of the same forecast, while returned or
        # already-collected items are excluded. Issued KarAmand cheques are also
        # included when they are explicitly registered, but the source is marked
        # incomplete so the manager never interprets it as the full future book.
        from app.services.karamad_manual_import_service import KaramadManualImportService
        karamad_service = KaramadManualImportService()
        # KarAmand state is a *current* snapshot. Never leak it into a historical
        # backtest whose as-of date is not today.
        if today == date.today():
            karamad_received = karamad_service.cheque_rows("received_cheques")
            karamad_issued = karamad_service.cheque_rows("issued_cheques")
        else:
            karamad_received = []
            karamad_issued = []
        karamad_issued_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        karamad_received_forecast_count = 0
        karamad_received_forecast_amount = 0.0
        karamad_issued_forecast_count = 0
        karamad_issued_forecast_amount = 0.0

        for cheque in karamad_received:
            if not received_cheque_is_approved_open_holding(cheque):
                continue
            days_to_due = cheque.get("days_to_due")
            status_text = str(cheque.get("cheque_status") or cheque.get("state_label") or "").casefold()
            collected = bool(cheque.get("collection_date_jalali")) or any(x in status_text for x in ("وصول شده", "وصول‌شده", "نقد شده", "نقدشده"))
            returned = any(x in status_text for x in ("برگشت", "برگشتی نزد مشتری"))
            if days_to_due is None or collected or returned or not 0 <= int(days_to_due) < self.forecast_days:
                continue
            due_day = today + timedelta(days=int(days_to_due))
            amount = float(cheque.get("amount") or 0)
            collectible_amount = amount * portfolio_reliability["reliability_percent"] / 100.0
            nominal_received_total += amount
            risk_reduction_total += amount - collectible_amount
            karamad_received_forecast_count += 1
            karamad_received_forecast_amount += amount
            reliable_by_day[due_day].append({
                "cheque_id": cheque.get("cheque_id"),
                "counterpart_name": cheque.get("counterpart_name"),
                "nominal_amount_rial": round(amount, 2),
                "amount_rial": round(collectible_amount, 2),
                "portfolio_reliability_percent": portfolio_reliability["reliability_percent"],
                "individual_reliability_percent": None,
                "due_date_jalali": cheque.get("due_date_jalali"),
                "source_system": "karamad",
                "cheque_status": cheque.get("cheque_status") or cheque.get("state_label"),
            })

        for cheque in karamad_issued:
            days_to_due = cheque.get("days_to_due")
            if days_to_due is None or not 0 <= int(days_to_due) < self.forecast_days:
                continue
            due_day = today + timedelta(days=int(days_to_due))
            amount = float(cheque.get("amount") or 0)
            karamad_issued_forecast_count += 1
            karamad_issued_forecast_amount += amount
            karamad_issued_by_day[due_day].append(cheque)

        base_days = {date.fromisoformat(row["date"]): row for row in base.get("timeline") or []}
        expense_plan = self._operating_expense_plan(today)
        salary_daily = self.SALARY_MONTHLY_RIAL / 30.0
        historical_other_expenses_observed_daily = float(expense_plan["daily_operating_expense_rial"])
        historical_other_expenses_daily = 0.0

        running_cash = opening_cash
        timeline: list[dict[str, Any]] = []
        first_shortage: str | None = None
        worst_cash = opening_cash
        reliable_total = issued_total = salary_total = other_total = observed_other_total = 0.0
        for offset in range(self.forecast_days):
            day = today + timedelta(days=offset)
            raw = base_days.get(day, {})
            reliable_rows = reliable_by_day.get(day, [])
            reliable_in = sum(float(row["amount_rial"] or 0) for row in reliable_rows)
            rahkaran_issued_out = float(raw.get("issued_cheques_due") or 0)
            karamad_issued_rows = karamad_issued_by_day.get(day, [])
            karamad_issued_out = sum(float(row.get("amount") or 0) for row in karamad_issued_rows)
            issued_out = rahkaran_issued_out + karamad_issued_out
            salary_out = salary_daily
            other_out = historical_other_expenses_daily
            projected_in = reliable_in
            projected_out = issued_out + salary_out + other_out
            if running_cash is not None:
                running_cash += projected_in - projected_out
                if running_cash < 0 and first_shortage is None:
                    first_shortage = day.isoformat()
                if worst_cash is None or running_cash < worst_cash:
                    worst_cash = running_cash
            reliable_total += reliable_in
            issued_total += issued_out
            salary_total += salary_out
            other_total += other_out
            observed_other_total += historical_other_expenses_observed_daily
            timeline.append({
                "date": day.isoformat(), "date_jalali": _as_jalali_date(day),
                "opening_bank_balance_rial": opening_cash if offset == 0 else None,
                "reliable_received_cheques": round(reliable_in, 2),
                "reliable_received_cheque_count": len(reliable_rows),
                "reliable_received_cheque_details": reliable_rows,
                "issued_cheques_due": round(issued_out, 2),
                "rahkaran_issued_cheques_due": round(rahkaran_issued_out, 2),
                "karamad_registered_issued_cheques_due": round(karamad_issued_out, 2),
                "karamad_registered_issued_cheque_details": karamad_issued_rows,
                "salary_reserve": round(salary_out, 2),
                "historical_other_expenses": round(other_out, 2),
                "historical_other_expenses_observed": round(historical_other_expenses_observed_daily, 2),
                "historical_expense_categories": expense_plan["daily_category_amounts_rial"],
                "projected_inflow": round(projected_in, 2),
                "projected_outflow": round(projected_out, 2),
                "daily_net_change": round(projected_in - projected_out, 2),
                "projected_cash": None if running_cash is None else round(running_cash, 2),
                "cash_shortage": bool(running_cash is not None and running_cash < 0),
            })

        historical_comparison = self.monthly_service.historical_comparison(months_limit=6)
        from app.services.karamad_manual_import_service import KaramadManualImportService
        karamad_actuals = KaramadManualImportService().summary()
        return {
            "status": "success", "report_type": "cash_runway_forecast",
            "cashflow_mode": "selected_horizon_runway", "as_of_date": today.isoformat(),
            "forecast_days": self.forecast_days, "history_days": self.history_days,
            "opening_cash": opening_cash,
            "opening_balance": {"source": "latest_excel_snapshot", "amount_rial": opening_cash,
                "snapshot_date_jalali": snapshot.get("jalali_date") if snapshot else None,
                "snapshot_filename": snapshot.get("filename") if snapshot else None,
                "rule": "موجودی واقعی صورت‌حساب/Excel فقط یک‌بار، در ابتدای بازه وارد می‌شود."},
            "cashflow_policy": {
                "portfolio_reliability_percent": portfolio_reliability["reliability_percent"],
                "portfolio_return_rate_percent": portfolio_reliability["return_rate_percent"],
                "portfolio_return_rate_range_percent": [self.MIN_PORTFOLIO_RETURN_RATE_PERCENT, self.MAX_PORTFOLIO_RETURN_RATE_PERCENT],
                "portfolio_reliability_range_percent": [100 - self.MAX_PORTFOLIO_RETURN_RATE_PERCENT, 100 - self.MIN_PORTFOLIO_RETURN_RATE_PERCENT],
                "portfolio_reliability_source": portfolio_reliability["source"],
                "portfolio_resolved_cheque_count": portfolio_reliability["resolved_cheque_count"],
                "salary_monthly_rial": self.SALARY_MONTHLY_RIAL,
                "salary_daily_rial": round(salary_daily, 2),
                "historical_other_expenses_daily_rial": round(historical_other_expenses_daily, 2),
                "historical_other_expenses_observed_daily_rial": round(historical_other_expenses_observed_daily, 2),
                "historical_other_expenses_included": False,
                "ordinary_expense_rule": "سایر هزینه‌های تاریخی فقط برای کنترل نشان داده می‌شوند و تا تأیید برنامهٔ هزینهٔ آینده، وارد Cash Flow، خلاصه مدیریتی و Agent نقدینگی نیستند.",
                "petty_cash_included": False, "shareholder_paid_cheques_included": False,
                "karamad_historical_movements_in_forecast": False,
                "karamad_received_cheques_in_forecast": True,
                "karamad_registered_issued_cheques_in_forecast": True,
                "karamad_issued_future_data_complete": False,
                "karamad_rule": "حواله‌های تاریخی کارآمد فقط در عملکرد واقعی می‌آیند. چک‌های دریافتی Snapshot جدید چون تاریخ سررسید دارند در پیش‌بینی وارد می‌شوند. چک‌های پرداختی کارآمد فقط به اندازه رکوردهای ثبت‌شده لحاظ می‌شوند و منبع آینده کامل نیست.",
                "sql_server_write_operations": False,
            },
            "summary": {
                "opening_bank_balance_rial": opening_cash,
                "nominal_received_cheques_rial": round(nominal_received_total, 2),
                "reliable_received_cheques_rial": round(reliable_total, 2),
                "reliable_received_cheque_count": sum(len(rows) for rows in reliable_by_day.values()),
                "risk_reduction_rial": round(risk_reduction_total, 2),
                "issued_cheques_rial": round(issued_total, 2),
                "karamad_received_cheque_forecast_count": karamad_received_forecast_count,
                "karamad_received_cheque_forecast_nominal_rial": round(karamad_received_forecast_amount, 2),
                "karamad_registered_issued_cheque_forecast_count": karamad_issued_forecast_count,
                "karamad_registered_issued_cheque_forecast_rial": round(karamad_issued_forecast_amount, 2),
                "salary_reserve_rial": round(salary_total, 2),
                "historical_other_expenses_rial": round(other_total, 2),
                "historical_other_expenses_observed_rial": round(observed_other_total, 2),
                "remaining_cash_rial": None if running_cash is None else round(running_cash, 2),
                "first_predicted_shortage_date": first_shortage,
                "first_predicted_shortage_date_jalali": _as_jalali_date(first_shortage) if first_shortage else None,
                "worst_projected_cash": None if worst_cash is None else round(worst_cash, 2),
            },
            "historical_context": historical_comparison,
            "karamad_actuals": karamad_actuals,
            "historical_expense_plan": expense_plan,
            "management_summary": self._management_summary(
                opening_cash, reliable_total, issued_total, salary_total, running_cash,
                first_shortage, worst_cash, portfolio_reliability,
            ),
            "timeline": timeline,
            "method": "Opening bank balance + all received cheques adjusted by the portfolio's actual one-year collection reliability - issued cheques (maximum 20 overdue days) - monthly payroll reserve",
            "limitations": [
                "حقوق به‌صورت ذخیره روزانه از نرخ ثابت ۱۰ میلیارد تومان در ماه توزیع شده است؛ پس از ثبت تاریخ واقعی پرداخت حقوق می‌توان آن را روی همان روز قرار داد.",
                "سایر هزینه‌ها فقط برای کنترل نمایش داده می‌شوند و تا زمان تأیید برنامهٔ هزینهٔ آینده، وارد Cash Flow و پیشنهادهای Agent نیستند.",
                "تنخواه، انتقال داخلی و چک‌های پرداخت‌شدهٔ سهامداران در این Cash Flow نیستند. چک‌های دریافتی با سیاست محافظه‌کارانهٔ ۲۰ تا ۳۰٪ برگشت تعدیل می‌شوند؛ چک‌ها حذف نمی‌شوند.",
                "حواله‌های کارآمد گردش قطعی تاریخی‌اند و وارد پیش‌بینی آینده نمی‌شوند. Snapshot چک دریافتی کارآمد تاریخ سررسید دارد و وارد پیش‌بینی می‌شود؛ Snapshot چک پرداختی فقط ثبت‌شده‌های موجود را پوشش می‌دهد و آینده آن کامل نیست.",
            ],
        }

    def _management_summary(
        self,
        opening_cash: float | None,
        reliable_inflow: float,
        issued_outflow: float,
        salary_outflow: float,
        remaining_cash: float | None,
        first_shortage: str | None,
        worst_cash: float | None,
        portfolio_reliability: dict[str, Any],
    ) -> dict[str, Any]:
        fixed_outflows = issued_outflow + salary_outflow
        available_resources = (opening_cash or 0) + reliable_inflow
        coverage_percent = round(available_resources / fixed_outflows * 100, 1) if fixed_outflows else None
        net_cash_change = reliable_inflow - fixed_outflows
        status = "critical" if first_shortage else "attention" if remaining_cash is not None and remaining_cash < salary_outflow else "healthy"
        headline = (
            "کسری نقدینگی در بازهٔ انتخابی پیش‌بینی شده است."
            if status == "critical" else
            "ماندهٔ نقدینگی بازه، حقوق و چک‌های پرداختی را پوشش می‌دهد."
            if status == "healthy" else
            "ماندهٔ نقدینگی مثبت است، اما برای پوشش حقوق نیازمند توجه است."
        )
        return {
            "status": status,
            "headline": headline,
            "available_resources_rial": round(available_resources, 2),
            "fixed_outflows_rial": round(fixed_outflows, 2),
            "coverage_percent": coverage_percent,
            "net_cash_change_rial": round(net_cash_change, 2),
            "decision_basis": "موجودی واقعی ابتدای بازه + ۷۵٪ چک‌های دریافتی − چک‌های پرداختی − ذخیرهٔ حقوق",
            "key_points": [
                {"label": "موجودی شروع", "amount_rial": None if opening_cash is None else round(opening_cash, 2), "tone": "neutral"},
                {"label": "وصول قابل برنامه‌ریزی", "amount_rial": round(reliable_inflow, 2), "tone": "positive"},
                {"label": "خروجی قطعی", "amount_rial": round(fixed_outflows, 2), "tone": "negative"},
                {"label": "مانده پایان بازه", "amount_rial": None if remaining_cash is None else round(remaining_cash, 2), "tone": "positive" if (remaining_cash or 0) >= 0 else "negative"},
            ],
            "reliability_percent": portfolio_reliability["reliability_percent"],
            "return_rate_percent": portfolio_reliability["return_rate_percent"],
            "first_shortage_date_jalali": _as_jalali_date(first_shortage) if first_shortage else None,
            "worst_cash_rial": None if worst_cash is None else round(worst_cash, 2),
            "recommendations": [
                {"action": "رزرو وجه چک‌های پرداختی نزدیک", "priority": "critical" if issued_outflow else "high", "why": "چک‌های پرداختی در بازه، خروجی قطعی نقدینگی هستند.", "owner": "خزانه", "deadline": "روزانه پیش از شروع روز کاری"},
                {"action": "پیگیری وصول چک‌های نزدیک به سررسید", "priority": "high", "why": f"وصول با نرخ محافظه‌کارانهٔ {portfolio_reliability['reliability_percent']:.0f}٪ در پیش‌بینی لحاظ شده است.", "owner": "وصول", "deadline": "تا ۴۸ ساعت"},
                {"action": "به‌روزرسانی موجودی شروع از صورت‌حساب", "priority": "high", "why": "کیفیت تصمیم نقدینگی به موجودی واقعی ابتدای روز وابسته است.", "owner": "خزانه", "deadline": "هر صبح"},
                {"action": "ثبت برنامهٔ هزینه‌های قطعی", "priority": "medium", "why": "سایر هزینه‌های تاریخی عمداً وارد پیش‌بینی نشده‌اند.", "owner": "مدیر مالی", "deadline": "این هفته"},
                {"action": "تطبیق چک‌های معوق تا ۲۰ روز", "priority": "high", "why": "فقط معوق‌های کوتاه‌مدت در Cash Flow لحاظ شده‌اند و باید وضعیت واقعی‌شان روشن شود.", "owner": "خزانه", "deadline": "امروز"},
                {"action": "تأیید نرخ وصول سبد چک", "priority": "medium", "why": "نرخ وصول واقعی تعیین می‌کند چه مقدار از چک‌های سررسیددار قابل برنامه‌ریزی است.", "owner": "وصول", "deadline": "هفتگی"},
            ],
        }

    def _portfolio_reliability(self) -> dict[str, Any]:
        """Read actual history for audit; apply the management risk policy."""
        query = text("""
            SELECT
                SUM(CASE WHEN note.[State] = 3 THEN 1 ELSE 0 END) AS [CollectedCount],
                SUM(CASE WHEN note.[State] = 4 THEN 1 ELSE 0 END) AS [ReturnedCount]
            FROM RPA3.[ReceivableNote] AS note
            WHERE note.[NoteType] = 1
              AND note.[NormalORGuarantee] = 1
              AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
              AND note.[State] IN (3, 4)
              AND note.[DueDate] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
              AND note.[DueDate] < CAST(GETDATE() AS date)
        """)
        with self.engine.connect() as connection:
            row = connection.execute(query, {"history_days": self.history_days}).mappings().one()
        collected = int(row.get("CollectedCount") or 0)
        returned = int(row.get("ReturnedCount") or 0)
        resolved = collected + returned
        observed_return_rate = round(returned / resolved * 100, 2) if resolved else None
        return_rate = self.BASE_PORTFOLIO_RETURN_RATE_PERCENT
        return {
            "reliability_percent": 100 - return_rate,
            "return_rate_percent": return_rate,
            "resolved_cheque_count": resolved,
            "observed_return_rate_percent": observed_return_rate,
            "source": "سیاست مدیریتی: ۲۵٪ برگشت در سناریوی پایه؛ بازهٔ سناریویی ۲۰٪ تا ۳۰٪. تاریخچهٔ SQL فقط برای کنترل نگه‌داری می‌شود.",
        }

    def _operating_expense_plan(self, today: date) -> dict[str, Any]:
        """Build an auditable forecast from classified, read-only payment history."""
        query = text("""
            SELECT h.[Date] AS [DocumentDate],
                   COALESCE(d.[CurrencyAmount], d.[Amount], 0) AS [AmountRial],
                   COALESCE(NULLIF(d.[Description], N''), h.[Description], N'') AS [Description],
                   counterpart.[Title] AS [CounterPartName],
                   d.[CashFlowFactorRef] AS [CashFlowFactorRef]
            FROM RPA3.[PaymentCashMoney] AS d
            INNER JOIN RPA3.[Payment] AS h ON h.[PaymentID] = d.[PaymentRef]
            LEFT JOIN FIN3.[DL] AS counterpart ON counterpart.[DLID] = COALESCE(d.[CounterPartRef], h.[CounterPartRef])
            WHERE h.[ApproveState] = 3
              AND h.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
              AND h.[Date] < CAST(GETDATE() AS date)
            UNION ALL
            SELECT h.[Date], COALESCE(d.[CurrencyAmount], d.[Amount], 0),
                   COALESCE(NULLIF(d.[Description], N''), h.[Description], N''),
                   counterpart.[Title], d.[CashFlowFactorRef]
            FROM RPA3.[PaymentDeposit] AS d
            INNER JOIN RPA3.[Payment] AS h ON h.[PaymentID] = d.[PaymentRef]
            LEFT JOIN FIN3.[DL] AS counterpart ON counterpart.[DLID] = COALESCE(d.[CounterPartRef], h.[CounterPartRef])
            WHERE h.[ApproveState] = 3
              AND h.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
              AND h.[Date] < CAST(GETDATE() AS date)
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(query, {"history_days": self.history_days}).mappings().all()

        categories: dict[str, dict[str, Any]] = {
            code: {"code": code, "title": title, "historical_amount_rial": 0.0, "payment_count": 0,
                   "included_in_forecast": included, "needs_review": False, "samples": []}
            for code, title, _keywords, included in self.EXPENSE_CATEGORY_RULES
        }
        categories["other_operational_review"] = {
            "code": "other_operational_review", "title": "سایر پرداخت عملیاتی (نیازمند بازبینی)",
            "historical_amount_rial": 0.0, "payment_count": 0, "included_in_forecast": True,
            "needs_review": True, "samples": [],
        }
        excluded = {"historical_amount_rial": 0.0, "payment_count": 0, "samples": []}
        for row in rows:
            amount = float(row.get("AmountRial") or 0)
            text_value = f"{row.get('Description') or ''} {row.get('CounterPartName') or ''}".casefold()
            if any(keyword.casefold() in text_value for keyword in self.EXCLUDED_EXPENSE_KEYWORDS):
                excluded["historical_amount_rial"] += amount
                excluded["payment_count"] += 1
                if len(excluded["samples"]) < 5:
                    excluded["samples"].append({"description": row.get("Description") or row.get("CounterPartName") or "—", "amount_rial": round(amount, 2)})
                continue
            category = categories["other_operational_review"]
            for code, _title, keywords, _included in self.EXPENSE_CATEGORY_RULES:
                if any(keyword.casefold() in text_value for keyword in keywords):
                    category = categories[code]
                    break
            category["historical_amount_rial"] += amount
            category["payment_count"] += 1
            if len(category["samples"]) < 5:
                category["samples"].append({
                    "description": row.get("Description") or row.get("CounterPartName") or "—",
                    "amount_rial": round(amount, 2),
                    "cash_flow_factor_ref": row.get("CashFlowFactorRef"),
                })

        included_total = 0.0
        daily_amounts: dict[str, float] = {}
        result_categories = []
        for category in categories.values():
            amount = float(category["historical_amount_rial"])
            daily = amount / self.history_days if category["included_in_forecast"] else 0.0
            category["average_daily_rial"] = round(daily, 2)
            category["forecast_amount_rial"] = round(daily * self.forecast_days, 2)
            category["historical_amount_rial"] = round(amount, 2)
            if category["included_in_forecast"]:
                included_total += amount
                daily_amounts[category["code"]] = round(daily, 2)
            result_categories.append(category)
        return {
            "history_days": self.history_days,
            "forecast_days": self.forecast_days,
            "source": "approved RPA3.PaymentCashMoney and RPA3.PaymentDeposit; SQL Server read-only",
            "daily_operating_expense_rial": round(included_total / self.history_days, 2),
            "forecast_operating_expense_rial": round(included_total / self.history_days * self.forecast_days, 2),
            "categories": result_categories,
            "daily_category_amounts_rial": daily_amounts,
            "excluded_non_operating": {**excluded, "historical_amount_rial": round(float(excluded["historical_amount_rial"]), 2)},
            "rule": "مالیات و بیمه جداگانه نمایش داده می‌شوند و تا ثبت موعد واقعی وارد پیش‌بینی نیستند؛ انتقال، تنخواه، سهامدار و پرداخت‌های یک‌باره حذف می‌شوند؛ سایر موارد ناشناخته برای بازبینی برچسب می‌خورند.",
        }
