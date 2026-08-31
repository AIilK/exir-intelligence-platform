from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.database.sqlserver import get_sqlserver_engine
from app.services.treasury_service import _as_number, _as_jalali_date
from app.services.customer_cheque_behavior_engine import CustomerChequeBehaviorEngine


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _pct(value: float) -> float:
    return round(_clamp(value) * 100.0, 2)


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


class FinancePredictionService:
    """Explainable finance prediction layer backed only by company SQL data.

    Important: these forecasts are deterministic/empirical estimates, not trained
    ML probabilities. Every output declares its method and limitations.
    """

    def __init__(
        self,
        *,
        history_days: int = 365,
        forecast_days: int = 30,
        allowed_term_days: int = 90,
        opening_cash: float | None = None,
        engine: Engine | None = None,
    ):
        self.history_days = max(30, min(int(history_days), 730))
        self.forecast_days = max(1, min(int(forecast_days), 180))
        self.allowed_term_days = max(1, min(int(allowed_term_days), 365))
        self.opening_cash = None if opening_cash is None else max(0.0, float(opening_cash))
        self.engine = engine or get_sqlserver_engine()

    # ------------------------------------------------------------------
    # Customer collection / late-payment / return-risk predictions
    # ------------------------------------------------------------------
    def customer_predictions(self, limit: int | None = 200) -> dict[str, Any]:
        safe_limit = None if limit is None else max(1, min(int(limit), 5000))
        rows = self._customer_behavior_rows()
        items = [self._build_customer_prediction(dict(row)) for row in rows]
        items.sort(
            key=lambda x: (
                x["collection_priority_base_score"],
                x["open_exposure"],
            ),
            reverse=True,
        )
        if safe_limit is not None:
            items = items[:safe_limit]
        return {
            "status": "success",
            "report_type": "customer_collection_predictions",
            "as_of_date": date.today().isoformat(),
            "history_days": self.history_days,
            "customer_cheque_history_scope": "all_available_history",
            "forecast_days": self.forecast_days,
            "allowed_term_days": self.allowed_term_days,
            "currency_name": settings.treasury_operational_currency_name,
            "prediction_type": "explainable_empirical_estimate",
            "customers": items,
            "count": len(items),
            "method": (
                "Bayesian-smoothed historical cheque outcome rate + current overdue "
                "exposure + term-policy deviation"
            ),
            "limitations": [
                "این خروجی احتمال آماری آموزش‌دیده با ML نیست؛ برآورد تجربی و قاعده‌محور است.",
                "این نسخه وصول مبتنی بر چک را پوشش می‌دهد و هنوز تمام فاکتورهای باز فروش را شامل نمی‌شود.",
                "برای مدل دقیق دیرکرد، تاریخ واقعی وصول/تسویه هر چک باید به‌صورت تاریخی ثبت و متصل شود.",
            ],
        }

    def customer_prediction(self, counterpart_ref: int) -> dict[str, Any]:
        report = self.customer_predictions(limit=1000)
        for item in report["customers"]:
            if int(item["counterpart_ref"]) == int(counterpart_ref):
                return {**report, "customers": [item], "count": 1}
        return {
            "status": "not_found",
            "counterpart_ref": int(counterpart_ref),
            "message": "برای این طرف حساب در بازه انتخاب‌شده سابقه چک قابل تحلیل پیدا نشد.",
        }

    def customer_open_cheques(self, counterpart_ref: int) -> list[dict[str, Any]]:
        """Return the customer's currently open received cheques with due timing."""
        query = text(
            """
            SELECT
                master_note.[ReceivableNoteID] AS [ChequeID],
                master_note.[SerialNumber],
                master_note.[SayadNumber],
                note.[Amount],
                receipt.[Date] AS [ReceiptDate],
                master_note.[DueDate],
                master_note.[State],
                DATEDIFF(day, CAST(GETDATE() AS date), CAST(master_note.[DueDate] AS date)) AS [DaysToDue],
                DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(master_note.[DueDate] AS date)) AS [TermDays]
            FROM RPA3.[ReceiptReceivableNote] AS note
            INNER JOIN RPA3.[Receipt] AS receipt
                ON receipt.[ReceiptID] = note.[ReceiptRef]
            INNER JOIN RPA3.[ReceivableNote] AS master_note
                ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
            WHERE receipt.[ApproveState] = 3
              AND receipt.[ItemType] = 1
              AND master_note.[NoteType] = 1
              AND master_note.[NormalORGuarantee] = 1
              AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
              AND master_note.[State] IN (1, 2)
              AND note.[CounterPartRef] = :counterpart_ref
            ORDER BY master_note.[DueDate], master_note.[ReceivableNoteID]
            """
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query, {"counterpart_ref": int(counterpart_ref)}).mappings().all()
        return [
            {
                "cheque_id": int(row["ChequeID"]),
                "serial_number": str(row["SerialNumber"]) if row.get("SerialNumber") else None,
                "sayad_number": str(row["SayadNumber"]) if row.get("SayadNumber") else None,
                "amount": round(_money(row.get("Amount")), 2),
                "receipt_date": row["ReceiptDate"].isoformat() if row.get("ReceiptDate") else None,
                "receipt_date_jalali": _as_jalali_date(row.get("ReceiptDate")),
                "due_date": row["DueDate"].isoformat() if row.get("DueDate") else None,
                "due_date_jalali": _as_jalali_date(row.get("DueDate")),
                "state": int(row.get("State") or 0),
                "state_label": "در جریان وصول" if int(row.get("State") or 0) == 2 else "نزد شرکت",
                "days_to_due": int(row["DaysToDue"]) if row.get("DaysToDue") is not None else None,
                "days_overdue": abs(int(row["DaysToDue"])) if row.get("DaysToDue") is not None and int(row["DaysToDue"]) < 0 else 0,
                "term_days": int(row["TermDays"]) if row.get("TermDays") is not None else None,
            }
            for row in rows
        ]

    def cheque_return_predictions(
        self,
        limit: int | None = 100,
        *,
        batch_size: int = 1000,
        include_all_open: bool = False,
    ) -> dict[str, Any]:
        """Risk prediction for open received cheques.

        ``limit=None`` reads every matching cheque in deterministic SQL batches.
        Only the rule engine receives the full result; the LLM still receives a
        short ranked summary.
        """
        safe_limit = None if limit is None else max(1, min(int(limit), 5000))
        safe_batch_size = max(100, min(int(batch_size), 5000))
        customer_report = self.customer_predictions(limit=None)
        by_ref = {int(x["counterpart_ref"]): x for x in customer_report.get("customers", [])}

        due_scope = "" if include_all_open else """
              AND note.[DueDate] >= CAST(GETDATE() AS date)
              AND note.[DueDate] < DATEADD(day, :forecast_days + 1, CAST(GETDATE() AS date))
        """
        query = text(
            f"""
            WITH note_receipt AS (
                SELECT
                    rrn.[ReceivableNoteRef],
                    MIN(receipt.[Date]) AS [ReceiptDate]
                FROM RPA3.[ReceiptReceivableNote] AS rrn
                INNER JOIN RPA3.[Receipt] AS receipt
                    ON receipt.[ReceiptID] = rrn.[ReceiptRef]
                WHERE receipt.[ApproveState] = 3
                  AND receipt.[ItemType] = 1
                GROUP BY rrn.[ReceivableNoteRef]
            )
            SELECT
                note.[ReceivableNoteID] AS [ChequeID],
                note.[CounterPartRef],
                counterpart.[Code] AS [CounterPartCode],
                counterpart.[Title] AS [CounterPartName],
                note.[Amount],
                note.[DueDate],
                note.[State],
                note.[SerialNumber],
                note.[SayadNumber],
                nr.[ReceiptDate],
                CASE WHEN nr.[ReceiptDate] IS NOT NULL AND note.[DueDate] IS NOT NULL
                     THEN DATEDIFF(day, CAST(nr.[ReceiptDate] AS date), CAST(note.[DueDate] AS date))
                     ELSE NULL END AS [TermDays],
                CASE WHEN note.[DueDate] IS NOT NULL
                     THEN DATEDIFF(day, CAST(GETDATE() AS date), CAST(note.[DueDate] AS date))
                     ELSE NULL END AS [DaysToDue]
            FROM RPA3.[ReceivableNote] AS note
            LEFT JOIN FIN3.[DL] AS counterpart
                ON counterpart.[DLID] = note.[CounterPartRef]
            LEFT JOIN note_receipt AS nr
                ON nr.[ReceivableNoteRef] = note.[ReceivableNoteID]
            WHERE note.[NoteType] = 1
              AND note.[NormalORGuarantee] = 1
              AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
              AND note.[State] IN (1, 2)
              AND note.[CounterPartRef] IS NOT NULL
              {due_scope}
            ORDER BY note.[DueDate], note.[ReceivableNoteID]
            OFFSET :offset ROWS FETCH NEXT :batch_size ROWS ONLY
            """
        )
        excluded_guarantee_query = text(
            f"""
            SELECT
                COUNT_BIG(*) AS [ExcludedCount],
                COALESCE(SUM(note.[Amount]), 0) AS [ExcludedAmount]
            FROM RPA3.[ReceivableNote] AS note
            WHERE note.[NoteType] = 1
              AND (
                    ISNULL(note.[NormalORGuarantee], -1) <> 1
                    OR ISNULL(note.[Description], N'') LIKE N'%ضمانت%'
                    OR ISNULL(note.[Description], N'') LIKE N'%تضمین%'
                    OR ISNULL(note.[Description], N'') LIKE N'%حسن انجام%'
                  )
              AND note.[State] IN (1, 2)
              AND note.[CounterPartRef] IS NOT NULL
              {due_scope}
            """
        )
        rows: list[Any] = []
        with self.engine.connect() as connection:
            excluded_guarantees = connection.execute(
                excluded_guarantee_query,
                {"forecast_days": self.forecast_days},
            ).mappings().one()
            offset = 0
            while True:
                remaining = safe_batch_size if safe_limit is None else min(safe_batch_size, safe_limit - len(rows))
                if remaining <= 0:
                    break
                batch = connection.execute(
                    query,
                    {
                        "forecast_days": self.forecast_days,
                        "offset": offset,
                        "batch_size": remaining,
                    },
                ).mappings().all()
                rows.extend(batch)
                if len(batch) < remaining:
                    break
                offset += len(batch)

        predictions: list[dict[str, Any]] = []
        for row in rows:
            ref = int(row["CounterPartRef"])
            customer = by_ref.get(ref)
            base = (customer or {}).get("cheque_return_probability", {}).get("value", 10.0) / 100.0
            avg_amount = max(float((customer or {}).get("historical_average_cheque_amount", 0) or 0), 1.0)
            amount_ratio = _money(row["Amount"]) / avg_amount
            term_days = row["TermDays"]
            days_to_due = row["DaysToDue"]

            adjustment = 0.0
            reasons: list[str] = []
            if term_days is not None and term_days > self.allowed_term_days:
                adjustment += min(0.15, (term_days - self.allowed_term_days) / 365.0)
                reasons.append(
                    f"سررسید {term_days} روزه از سقف {self.allowed_term_days} روز بیشتر است."
                )
            if amount_ratio >= 2.0:
                adjustment += 0.08
                reasons.append("مبلغ چک حداقل دو برابر میانگین تاریخی چک‌های این مشتری است.")
            elif amount_ratio >= 1.5:
                adjustment += 0.04
                reasons.append("مبلغ چک به‌طور محسوسی از میانگین تاریخی مشتری بالاتر است.")
            if customer and customer.get("current_overdue_open_ratio_percent", 0) >= 25:
                adjustment += 0.08
                reasons.append("بخش قابل توجهی از چک‌های باز فعلی مشتری سررسیدگذشته است.")

            probability = _clamp(base + adjustment, 0.01, 0.95)
            level = "high" if probability >= 0.35 else "medium" if probability >= 0.18 else "low"
            customer_reliance = _money(
                (customer or {}).get("credit_decision", {}).get(
                    "recommended_reliance_percent",
                    50,
                )
            )
            cheque_reliance = customer_reliance
            reliance_deductions: list[dict[str, Any]] = []
            reliance_reasons = [
                f"درصد اتکای پایه مشتری براساس سابقه تعیین‌تکلیف‌شده {customer_reliance:.1f}٪ است."
            ]
            if term_days is not None and term_days > self.allowed_term_days:
                cheque_reliance -= 10
                reliance_deductions.append({"code": "over_term_policy", "deduction_percent": 10, "reason": f"مدت چک از سقف {self.allowed_term_days} روز بیشتر است."})
                reliance_reasons.append("۱۰ واحد درصد به علت عبور از سقف سررسید کسر شد.")
            if amount_ratio >= 2.0:
                cheque_reliance -= 15
                reliance_deductions.append({"code": "unusual_amount", "deduction_percent": 15, "reason": "مبلغ چک حداقل دو برابر میانگین تاریخی مشتری است."})
                reliance_reasons.append("۱۵ واحد درصد به علت مبلغ غیرعادی چک کسر شد.")
            elif amount_ratio >= 1.5:
                cheque_reliance -= 7
                reliance_deductions.append({"code": "above_average_amount", "deduction_percent": 7, "reason": "مبلغ چک بالاتر از رفتار معمول مشتری است."})
                reliance_reasons.append("۷ واحد درصد به علت مبلغ بالاتر از سابقه کسر شد.")
            overdue_ratio = _money(
                (customer or {}).get("current_overdue_open_ratio_percent")
            )
            if overdue_ratio >= 50:
                cheque_reliance -= 20
                reliance_deductions.append({"code": "high_overdue_exposure", "deduction_percent": 20, "reason": "حداقل نیمی از چک‌های باز مشتری سررسیدگذشته است."})
                reliance_reasons.append("۲۰ واحد درصد به علت مانده باز سررسیدگذشته بالا کسر شد.")
            elif overdue_ratio >= 25:
                cheque_reliance -= 10
                reliance_deductions.append({"code": "overdue_exposure", "deduction_percent": 10, "reason": "بخشی از چک‌های باز مشتری سررسیدگذشته است."})
                reliance_reasons.append("۱۰ واحد درصد به علت مانده باز سررسیدگذشته کسر شد.")
            cheque_reliance = max(
                5.0,
                min(
                    cheque_reliance,
                    (1.0 - probability) * 100.0,
                    95.0,
                ),
            )
            predictions.append(
                {
                    "cheque_id": row["ChequeID"],
                    "counterpart_ref": ref,
                    "counterpart_code": row["CounterPartCode"],
                    "counterpart_name": row["CounterPartName"],
                    "amount": _as_number(row["Amount"]),
                    "due_date": str(row["DueDate"]),
                    "due_date_jalali": _as_jalali_date(row["DueDate"]),
                    "term_days": term_days,
                    "days_to_due": days_to_due,
                    "days_overdue": abs(days_to_due) if days_to_due is not None and days_to_due < 0 else 0,
                    "due_status": "overdue" if days_to_due is not None and days_to_due < 0 else "due_today" if days_to_due == 0 else "upcoming",
                    "historical_amount_ratio": round(amount_ratio, 2),
                    "customer_reliability_score": (customer or {}).get("customer_behavior", {}).get("reliability_score", 50),
                    "customer_behavior_level": (customer or {}).get("customer_behavior", {}).get("behavior_level", "unknown"),
                    "historical_collection_rate_percent": (customer or {}).get("customer_behavior", {}).get("historical_collection_rate_percent", 0),
                    "historical_return_rate_percent": (customer or {}).get("customer_behavior", {}).get("historical_return_rate_percent", 0),
                    "customer_base_reliance_percent": round(customer_reliance, 2),
                    "recommended_reliance_percent": round(cheque_reliance, 2),
                    "risk_adjusted_collectible_amount_rial": round(
                        _money(row["Amount"]) * cheque_reliance / 100.0,
                        2,
                    ),
                    "reliance_source": "customer_cheque_behavior_engine_plus_cheque_rules",
                    "reliance_reasons": reliance_reasons,
                    "reliance_breakdown": {
                        "customer_base_percent": round(customer_reliance, 2),
                        "deductions": reliance_deductions,
                        "collection_probability_cap_percent": round((1.0 - probability) * 100.0, 2),
                        "final_percent": round(cheque_reliance, 2),
                    },
                    "improvement_actions": (customer or {}).get("credit_decision", {}).get("improvement_actions", []),
                    "recommended_credit_policy": (customer or {}).get("credit_decision", {}).get("policy", "review"),
                    "estimated_return_probability_percent": _pct(probability),
                    "risk_level": level,
                    "reasons": reasons or ["ریسک عمدتاً از سابقه تاریخی مشتری محاسبه شده است."],
                    "method": "customer_empirical_return_rate_plus_cheque_specific_adjustments",
                    "calculation_type": "forecast",
                }
            )

        predictions.sort(
            key=lambda x: (x["estimated_return_probability_percent"], x["amount"]),
            reverse=True,
        )
        return {
            "status": "success",
            "report_type": "cheque_return_predictions",
            "forecast_days": self.forecast_days,
            "currency_name": settings.treasury_operational_currency_name,
            "count": len(predictions),
            "processed_all_matching_cheques": safe_limit is None,
            "batch_size": safe_batch_size,
            "scope": "all_open_received_cheques" if include_all_open else "forecast_window_open_received_cheques",
            "normal_or_guarantee_filter": 1,
            "guarantee_cheques_excluded": True,
            "guarantee_detection_rules": [
                "NormalORGuarantee must equal 1",
                "Description must not contain ضمانت, تضمین or حسن انجام",
            ],
            "excluded_guarantee_cheque_count": int(
                excluded_guarantees["ExcludedCount"] or 0
            ),
            "excluded_guarantee_cheque_amount": _as_number(
                excluded_guarantees["ExcludedAmount"]
            ),
            "cheques": predictions,
            "limitations": [
                "احتمال برگشت، برآورد توضیح‌پذیر است و مدل ML آموزش‌دیده نیست.",
                "نتیجه برای تصمیم‌یار است و نباید به‌تنهایی مبنای رد یا پذیرش اعتبار باشد.",
            ],
        }

    # ------------------------------------------------------------------
    # Daily cash-pressure / shortage forecast
    # ------------------------------------------------------------------
    def cash_shortage_forecast(self) -> dict[str, Any]:
        hist_query = text(
            """
            SELECT document_type, COALESCE(SUM(amount), 0) AS total_amount
            FROM (
                SELECT 'receipt' AS document_type, COALESCE(d.[CurrencyAmount], d.[Amount], 0) AS amount
                FROM RPA3.[ReceiptCashMoney] d
                INNER JOIN RPA3.[Receipt] h ON h.[ReceiptID] = d.[ReceiptRef]
                WHERE h.[ApproveState] = 3
                  AND h.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
                  AND h.[Date] < CAST(GETDATE() AS date)
                UNION ALL
                SELECT 'receipt', COALESCE(d.[CurrencyAmount], d.[Amount], 0)
                FROM RPA3.[ReceiptDeposit] d
                INNER JOIN RPA3.[Receipt] h ON h.[ReceiptID] = d.[ReceiptRef]
                WHERE h.[ApproveState] = 3
                  AND h.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
                  AND h.[Date] < CAST(GETDATE() AS date)
                UNION ALL
                SELECT 'payment', COALESCE(d.[CurrencyAmount], d.[Amount], 0)
                FROM RPA3.[PaymentCashMoney] d
                INNER JOIN RPA3.[Payment] h ON h.[PaymentID] = d.[PaymentRef]
                WHERE h.[ApproveState] = 3
                  AND h.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
                  AND h.[Date] < CAST(GETDATE() AS date)
                UNION ALL
                SELECT 'payment', COALESCE(d.[CurrencyAmount], d.[Amount], 0)
                FROM RPA3.[PaymentDeposit] d
                INNER JOIN RPA3.[Payment] h ON h.[PaymentID] = d.[PaymentRef]
                WHERE h.[ApproveState] = 3
                  AND h.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
                  AND h.[Date] < CAST(GETDATE() AS date)
            ) AS history
            GROUP BY document_type
            """
        )
        issued_query = text(
            """
            SELECT CAST([DueDate] AS date) AS due_date, COALESCE(SUM([Amount]),0) AS amount
            FROM RPA3.[PayableNote]
            WHERE [NoteType] = 1
              AND [NormalORGuarantee] = 1
              AND ISNULL([Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL([Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL([Description], N'') NOT LIKE N'%حسن انجام%'
              AND [State] = 11
              AND [DueDate] >= CAST(GETDATE() AS date)
              AND [DueDate] < DATEADD(day, :forecast_days + 1, CAST(GETDATE() AS date))
            GROUP BY CAST([DueDate] AS date)
            """
        )
        received_query = text(
            """
            SELECT CAST([DueDate] AS date) AS due_date, COALESCE(SUM([Amount]),0) AS amount
            FROM RPA3.[ReceivableNote]
            WHERE [NoteType] = 1
              AND [NormalORGuarantee] = 1
              AND ISNULL([Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL([Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL([Description], N'') NOT LIKE N'%حسن انجام%'
              AND [State] IN (1, 2)
              AND [DueDate] >= CAST(GETDATE() AS date)
              AND [DueDate] < DATEADD(day, :forecast_days + 1, CAST(GETDATE() AS date))
            GROUP BY CAST([DueDate] AS date)
            """
        )
        with self.engine.connect() as connection:
            hist = connection.execute(hist_query, {"history_days": self.history_days}).mappings().all()
            issued = connection.execute(issued_query, {"forecast_days": self.forecast_days}).mappings().all()
            received = connection.execute(received_query, {"forecast_days": self.forecast_days}).mappings().all()

        hist_map = {r["document_type"]: _money(r["total_amount"]) for r in hist}
        avg_receipts = hist_map.get("receipt", 0.0) / self.history_days
        avg_payments = hist_map.get("payment", 0.0) / self.history_days
        issued_map = {r["due_date"]: _money(r["amount"]) for r in issued}
        # Replace the old flat 75% assumption with the customer-specific
        # reliance calculated by CustomerChequeBehaviorEngine.
        received_report = self.cheque_return_predictions(
            limit=None,
            batch_size=1000,
            include_all_open=True,
        )
        received_map: dict[date, float] = defaultdict(float)
        gross_received_map: dict[date, float] = defaultdict(float)
        received_details_map: dict[date, list[dict[str, Any]]] = defaultdict(list)
        today = date.today()
        for cheque in received_report.get("cheques") or []:
            days_to_due = cheque.get("days_to_due")
            if days_to_due is None:
                continue
            days_to_due = int(days_to_due)
            if not 1 <= days_to_due <= self.forecast_days:
                continue
            due_day = today + timedelta(days=days_to_due)
            amount = _money(cheque.get("amount"))
            reliance_percent = _clamp(
                _money(cheque.get("recommended_reliance_percent")) / 100.0,
                0.05,
                0.95,
            )
            expected_amount = amount * reliance_percent
            gross_received_map[due_day] += amount
            received_map[due_day] += expected_amount
            received_details_map[due_day].append(
                {
                    "cheque_id": cheque.get("cheque_id"),
                    "counterpart_ref": cheque.get("counterpart_ref"),
                    "counterpart_name": cheque.get("counterpart_name"),
                    "amount_rial": round(amount, 2),
                    "reliance_percent": round(reliance_percent * 100, 2),
                    "risk_adjusted_collectible_amount_rial": round(expected_amount, 2),
                    "risk_level": cheque.get("risk_level"),
                    "due_date_jalali": cheque.get("due_date_jalali"),
                }
            )

        running_change = 0.0
        timeline: list[dict[str, Any]] = []
        first_shortage_date: str | None = None
        worst_cash: float | None = self.opening_cash
        worst_date: str | None = None
        negative_pressure_days = 0

        for offset in range(1, self.forecast_days + 1):
            day = today + timedelta(days=offset)
            due_in = received_map.get(day, 0.0)
            gross_due_in = gross_received_map.get(day, 0.0)
            due_out = issued_map.get(day, 0.0)
            projected_in = avg_receipts + due_in
            projected_out = avg_payments + due_out
            daily_net = projected_in - projected_out
            running_change += daily_net
            projected_cash = None if self.opening_cash is None else self.opening_cash + running_change
            if daily_net < 0:
                negative_pressure_days += 1
            if projected_cash is not None and projected_cash < 0 and first_shortage_date is None:
                first_shortage_date = day.isoformat()
            if projected_cash is not None and (worst_cash is None or projected_cash < worst_cash):
                worst_cash = projected_cash
                worst_date = day.isoformat()

            timeline.append(
                {
                    "date": day.isoformat(),
                    "date_jalali": _as_jalali_date(day),
                    "historical_average_operating_inflow": round(avg_receipts, 2),
                    "gross_received_cheques": round(gross_due_in, 2),
                    "weighted_received_cheques": round(due_in, 2),
                    "received_cheque_details": sorted(
                        received_details_map.get(day, []),
                        key=lambda item: (
                            item["reliance_percent"],
                            item["amount_rial"],
                        ),
                        reverse=True,
                    ),
                    "historical_average_operating_outflow": round(avg_payments, 2),
                    "issued_cheques_due": round(due_out, 2),
                    "projected_inflow": round(projected_in, 2),
                    "projected_outflow": round(projected_out, 2),
                    "daily_net_change": round(daily_net, 2),
                    "cumulative_net_change": round(running_change, 2),
                    "projected_cash": None if projected_cash is None else round(projected_cash, 2),
                    "cash_shortage": bool(projected_cash is not None and projected_cash < 0),
                }
            )

        nominal_received_total = sum(gross_received_map.values())
        adjusted_received_total = sum(received_map.values())
        portfolio_reliance_percent = (
            adjusted_received_total / nominal_received_total * 100
            if nominal_received_total else 0.0
        )
        reliance_reduction = max(0.0, nominal_received_total - adjusted_received_total)

        return {
            "status": "success",
            "report_type": "daily_cash_shortage_forecast",
            "as_of_date": today.isoformat(),
            "forecast_days": self.forecast_days,
            "history_days": self.history_days,
            "currency_name": settings.treasury_operational_currency_name,
            "opening_cash": self.opening_cash,
            "first_predicted_shortage_date": first_shortage_date,
            "first_predicted_shortage_date_jalali": _as_jalali_date(first_shortage_date) if first_shortage_date else None,
            "worst_projected_cash": None if worst_cash is None else round(worst_cash, 2),
            "worst_projected_cash_date": worst_date,
            "negative_cash_pressure_days": negative_pressure_days,
            "absolute_shortage_available": self.opening_cash is not None,
            "reliance_summary": {
                "nominal_received_cheques_rial": round(nominal_received_total, 2),
                "risk_adjusted_received_cheques_rial": round(adjusted_received_total, 2),
                "portfolio_reliance_percent": round(portfolio_reliance_percent, 2),
                "risk_reduction_rial": round(reliance_reduction, 2),
                "why_fa": (
                    "مبلغ اسمی همه چک‌ها ورودی قطعی نیست؛ هر چک براساس سابقه وصول و "
                    "واخواست مشتری، چک‌های باز سررسیدگذشته، مدت چک و غیرعادی‌بودن "
                    "مبلغ آن وزن‌دهی شده است."
                ),
                "how_to_improve_fa": [
                    "نتیجه قطعی وصول و واخواست هر چک در راهکاران ثبت شود.",
                    f"برای چک‌های جدید سقف سررسید {self.allowed_term_days} روز رعایت شود.",
                    "چک‌های باز سررسیدگذشته قبل از پذیرش تعهد جدید تعیین‌تکلیف شوند.",
                    "برای مبلغ بالاتر از میانگین تاریخی مشتری، تأیید مدیر مالی گرفته شود.",
                ],
            },
            "timeline": timeline,
            "method": "approved cash/bank detail averages + customer-specific risk-adjusted received cheques - issued cheques due",
            "limitations": [
                "اگر opening_cash داده نشود، سیستم فقط فشار/تغییر خالص روزانه را نشان می‌دهد و کسری مطلق اعلام نمی‌کند.",
                "درصد اتکای هر چک از سابقه تعیین‌تکلیف‌شده همان مشتری و قواعد قابل حسابرسی محاسبه می‌شود.",
                "اسناد تاریخی معادل مانده واقعی بانک نیستند.",
                "میانگین عملیاتی فقط از ریز دریافت/پرداخت نقدی و بانکی قطعی ساخته می‌شود؛ چک و انتقال داخلی دوباره شمرده نمی‌شود.",
            ],
        }

    # ------------------------------------------------------------------
    # Collection priority recommendations
    # ------------------------------------------------------------------
    def collection_priorities(self, limit: int = 25) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 200))
        report = self.customer_predictions(limit=1000)
        customers = report.get("customers", [])
        if not customers:
            return {"status": "success", "count": 0, "customers": []}

        max_exposure = max(float(x.get("open_exposure", 0) or 0) for x in customers) or 1.0
        ranked: list[dict[str, Any]] = []
        for item in customers:
            exposure_factor = float(item.get("open_exposure", 0) or 0) / max_exposure
            overdue_factor = float(item.get("current_overdue_open_ratio_percent", 0) or 0) / 100.0
            late_factor = float(item["late_payment_risk"]["value"] or 0) / 100.0
            return_factor = float(item["cheque_return_probability"]["value"] or 0) / 100.0
            score = 100 * (
                0.35 * exposure_factor
                + 0.30 * overdue_factor
                + 0.20 * late_factor
                + 0.15 * return_factor
            )
            reasons: list[str] = []
            if exposure_factor >= 0.5:
                reasons.append("مبلغ چک‌های دریافتی باز در بین مشتریان بالاست.")
            if overdue_factor >= 0.25:
                reasons.append("حداقل ۲۵٪ مبلغ چک‌های دریافتی باز فعلی سررسیدگذشته است.")
            if late_factor >= 0.4:
                reasons.append("ریسک دیرکرد برآوردی بالا است.")
            if return_factor >= 0.2:
                reasons.append("ریسک برگشت چک نسبت به سطح پایه بالاست.")
            ranked.append(
                {
                    "counterpart_ref": item["counterpart_ref"],
                    "counterpart_code": item["counterpart_code"],
                    "counterpart_name": item["counterpart_name"],
                    "priority_score": round(score, 1),
                    "priority_level": "high" if score >= 60 else "medium" if score >= 35 else "normal",
                    "open_exposure": item["open_exposure"],
                    "overdue_open_amount": item["overdue_open_amount"],
                    "expected_collection_amount": item["collection_forecast"]["expected_collection_amount"],
                    "late_payment_risk_percent": item["late_payment_risk"]["value"],
                    "cheque_return_probability_percent": item["cheque_return_probability"]["value"],
                    "reasons": reasons or ["اولویت بر اساس ترکیب مبلغ مواجهه و شاخص‌های ریسک محاسبه شده است."],
                    "recommendation": "پیگیری وصول در برنامه روزانه تیم مالی قرار گیرد." if score >= 35 else "پایش عادی ادامه یابد.",
                }
            )
        ranked.sort(key=lambda x: (x["priority_score"], x["open_exposure"]), reverse=True)
        for idx, row in enumerate(ranked[:safe_limit], 1):
            row["rank"] = idx
        return {
            "status": "success",
            "report_type": "collection_priority_recommendations",
            "currency_name": settings.treasury_operational_currency_name,
            "count": min(len(ranked), safe_limit),
            "customers": ranked[:safe_limit],
            "method": "weighted exposure + overdue ratio + late risk + return risk",
            "limitations": [
                "اولویت وصول پیشنهاد تصمیم‌یار است و جایگزین سیاست اعتباری مصوب شرکت نیست.",
                "تا اتصال فاکتورهای باز فروش، مبنای مبلغ این نسخه چک‌های باز مشتری است.",
            ],
        }

    # ------------------------------------------------------------------
    # Internal SQL / scoring helpers
    # ------------------------------------------------------------------
    def _customer_behavior_rows(self):
        query = text(
            """
            SELECT
                note.[CounterPartRef],
                counterpart.[Code] AS [CounterPartCode],
                counterpart.[Title] AS [CounterPartName],
                COUNT_BIG(*) AS [ChequeCount],
                COUNT_BIG(DISTINCT master_note.[ReceivableNoteID]) AS [DistinctChequeCount],
                COUNT_BIG(*) - COUNT_BIG(DISTINCT master_note.[ReceivableNoteID]) AS [RepeatedSourceRowCount],
                COALESCE(SUM(note.[Amount]), 0) AS [TotalAmount],
                COALESCE(SUM(CASE WHEN master_note.[State] = 3 THEN 1 ELSE 0 END), 0) AS [CollectedCount],
                COALESCE(SUM(CASE WHEN master_note.[State] = 3 THEN note.[Amount] ELSE 0 END), 0) AS [CollectedAmount],
                COALESCE(SUM(CASE WHEN master_note.[State] = 4 THEN 1 ELSE 0 END), 0) AS [ReturnedCount],
                COALESCE(SUM(CASE WHEN master_note.[State] IN (1,2) THEN 1 ELSE 0 END), 0) AS [OpenCount],
                COALESCE(SUM(CASE WHEN master_note.[State] IN (1,2) THEN note.[Amount] ELSE 0 END), 0) AS [OpenAmount],
                COALESCE(SUM(CASE
                    WHEN master_note.[State] IN (1,2) AND note.[DueDate] < CAST(GETDATE() AS date)
                    THEN 1 ELSE 0 END), 0) AS [OverdueOpenCount],
                COALESCE(SUM(CASE
                    WHEN master_note.[State] IN (1,2) AND note.[DueDate] < CAST(GETDATE() AS date)
                    THEN note.[Amount] ELSE 0 END), 0) AS [OverdueOpenAmount],
                COALESCE(SUM(CASE
                    WHEN master_note.[State] IN (1,2)
                     AND note.[DueDate] >= CAST(GETDATE() AS date)
                     AND note.[DueDate] < DATEADD(day, :forecast_days + 1, CAST(GETDATE() AS date))
                    THEN note.[Amount] ELSE 0 END), 0) AS [UpcomingOpenAmount],
                COALESCE(SUM(CASE WHEN master_note.[State] = 4 THEN note.[Amount] ELSE 0 END), 0) AS [ReturnedAmount],
                COALESCE(SUM(CASE WHEN master_note.[State] NOT IN (1,2,3,4) THEN 1 ELSE 0 END), 0) AS [OtherStateCount],
                COALESCE(SUM(CASE WHEN master_note.[State] NOT IN (1,2,3,4) THEN note.[Amount] ELSE 0 END), 0) AS [OtherStateAmount],
                AVG(CAST(note.[Amount] AS float)) AS [AverageChequeAmount],
                AVG(CASE WHEN note.[DueDate] IS NOT NULL AND receipt.[Date] IS NOT NULL
                    THEN CAST(DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date)) AS float)
                    ELSE NULL END) AS [AverageTermDays],
                MAX(CASE WHEN note.[DueDate] IS NOT NULL AND receipt.[Date] IS NOT NULL
                    THEN DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date))
                    ELSE NULL END) AS [MaxTermDays],
                COALESCE(SUM(CASE
                    WHEN note.[DueDate] IS NOT NULL AND receipt.[Date] IS NOT NULL
                     AND DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date)) > :allowed_term_days
                    THEN 1 ELSE 0 END), 0) AS [OverPolicyCount]
            FROM RPA3.[ReceiptReceivableNote] AS note
            INNER JOIN RPA3.[Receipt] AS receipt
                ON receipt.[ReceiptID] = note.[ReceiptRef]
            LEFT JOIN RPA3.[ReceivableNote] AS master_note
                ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
            LEFT JOIN FIN3.[DL] AS counterpart
                ON counterpart.[DLID] = note.[CounterPartRef]
            WHERE receipt.[ApproveState] = 3
              AND receipt.[ItemType] = 1
              AND master_note.[NoteType] = 1
              AND master_note.[NormalORGuarantee] = 1
              AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
              AND note.[CounterPartRef] IS NOT NULL
            GROUP BY note.[CounterPartRef], counterpart.[Code], counterpart.[Title]
            """
        )
        with self.engine.connect() as connection:
            return connection.execute(
                query,
                {
                    "history_days": self.history_days,
                    "forecast_days": self.forecast_days,
                    "allowed_term_days": self.allowed_term_days,
                },
            ).mappings().all()

    def _build_customer_prediction(self, row: dict[str, Any]) -> dict[str, Any]:
        cheque_count = int(row.get("ChequeCount") or 0)
        collected = int(row.get("CollectedCount") or 0)
        returned = int(row.get("ReturnedCount") or 0)
        open_count = int(row.get("OpenCount") or 0)
        overdue_open_count = int(row.get("OverdueOpenCount") or 0)
        resolved = collected + returned

        # Bayesian smoothing with a 10% prior return rate (alpha=1, beta=9).
        return_probability = (returned + 1.0) / (resolved + 10.0)
        collection_probability = 1.0 - return_probability
        overdue_open_ratio = overdue_open_count / max(open_count, 1)
        over_policy_ratio = int(row.get("OverPolicyCount") or 0) / max(cheque_count, 1)

        # Transparent late-risk estimate. No claim of trained statistical probability.
        late_risk = _clamp(
            0.50 * overdue_open_ratio
            + 0.25 * over_policy_ratio
            + 0.25 * return_probability,
            0.02,
            0.95,
        )
        expected_collection_rate = _clamp(
            collection_probability * (1.0 - 0.35 * late_risk),
            0.05,
            0.98,
        )

        upcoming = _money(row.get("UpcomingOpenAmount"))
        overdue = _money(row.get("OverdueOpenAmount"))
        # Overdue open exposure receives a more conservative collection factor.
        expected_collection_amount = (
            upcoming * expected_collection_rate
            + overdue * expected_collection_rate * 0.60
        )
        open_exposure = _money(row.get("OpenAmount"))
        priority_base = (
            40 * (open_exposure > 0)
            + 30 * overdue_open_ratio
            + 20 * late_risk
            + 10 * return_probability
        )

        resolved_collection_rate = collected / max(resolved, 1)
        resolved_return_rate = returned / max(resolved, 1)
        history_confidence = _clamp(resolved / 20.0, 0.20, 1.0)
        reliability_score = 100 * _clamp(
            0.55 * resolved_collection_rate
            + 0.20 * (1.0 - resolved_return_rate)
            + 0.15 * (1.0 - overdue_open_ratio)
            + 0.10 * (1.0 - over_policy_ratio)
        )
        # With very little resolved history, pull the score toward neutral 50.
        reliability_score = 50 + (reliability_score - 50) * history_confidence
        behavior_level = (
            "excellent" if reliability_score >= 85 else
            "good" if reliability_score >= 70 else
            "review" if reliability_score >= 50 else
            "weak" if reliability_score >= 30 else
            "high_risk"
        )
        recommended_reliance = _clamp(
            expected_collection_rate * (0.65 + 0.35 * history_confidence),
            0.10,
            0.95,
        )
        credit_policy = (
            "accept_normal" if reliability_score >= 80 and overdue_open_ratio < 0.10 else
            "accept_with_monitoring" if reliability_score >= 65 and overdue_open_ratio < 0.25 else
            "accept_with_guarantee" if reliability_score >= 45 else
            "manual_approval_required"
        )

        evidence = [
            f"{collected} فقره وصول‌شده و {returned} فقره واخواست‌شده در سوابق حل‌شده.",
            f"{overdue_open_count} فقره از {open_count} چک باز فعلی سررسیدگذشته است.",
            f"{int(row.get('OverPolicyCount') or 0)} فقره خارج از سقف {self.allowed_term_days} روز ثبت شده است.",
        ]
        late_reasons: list[str] = []
        if overdue_open_ratio >= 0.25:
            late_reasons.append("نسبت چک‌های باز سررسیدگذشته بالاست.")
        if over_policy_ratio >= 0.20:
            late_reasons.append("تعداد قابل توجهی از چک‌ها خارج از سیاست سررسید هستند.")
        if return_probability >= 0.20:
            late_reasons.append("سابقه واخواست، ریسک دیرکرد/عدم وصول را افزایش می‌دهد.")
        if not late_reasons:
            late_reasons.append("عامل پرریسک غالب در قواعد نسخه MVP مشاهده نشد.")

        # One canonical engine owns customer behaviour and credit calculations.
        # The legacy local variables above are retained temporarily for backward
        # compatibility, but every published score below comes from this engine.
        behavior_result = CustomerChequeBehaviorEngine(
            allowed_term_days=self.allowed_term_days,
            forecast_days=self.forecast_days,
        ).evaluate(row)

        return {
            "counterpart_ref": int(row["CounterPartRef"]),
            "counterpart_code": str(row.get("CounterPartCode") or row["CounterPartRef"]),
            "counterpart_name": str(row.get("CounterPartName") or "نامشخص"),
            "historical_cheque_count": cheque_count,
            "source_row_count": cheque_count,
            "distinct_cheque_count": int(row.get("DistinctChequeCount") or 0),
            "repeated_source_row_count": int(row.get("RepeatedSourceRowCount") or 0),
            "historical_total_cheque_amount": round(_money(row.get("TotalAmount")), 2),
            "collected_cheque_count": collected,
            "collected_cheque_amount": round(_money(row.get("CollectedAmount")), 2),
            "returned_cheque_count": returned,
            "returned_cheque_amount": round(_money(row.get("ReturnedAmount")), 2),
            "open_cheque_count": open_count,
            "overdue_open_cheque_count": overdue_open_count,
            "other_state_cheque_count": int(row.get("OtherStateCount") or 0),
            "other_state_cheque_amount": round(_money(row.get("OtherStateAmount")), 2),
            "historical_average_cheque_amount": round(_money(row.get("AverageChequeAmount")), 2),
            "over_policy_count": int(row.get("OverPolicyCount") or 0),
            "open_received_cheque_amount": round(open_exposure, 2),
            "open_exposure": round(open_exposure, 2),
            "overdue_open_received_cheque_amount": round(overdue, 2),
            "overdue_open_amount": round(overdue, 2),
            "current_overdue_open_ratio_percent": _pct(overdue_open_ratio),
            **behavior_result,
        }
