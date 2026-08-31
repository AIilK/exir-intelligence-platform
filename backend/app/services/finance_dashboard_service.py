from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.database.sqlserver import get_sqlserver_engine
from app.services.customer_risk_service import CustomerRiskService
from app.services.finance_prediction_service import FinancePredictionService
from app.services.explainable_alert_service import ExplainableAlertService
from app.services.treasury_insight_service import (
    get_cashflow_scenarios,
    get_cheque_risk_dashboard,
    get_daily_treasury_briefing,
    get_financial_anomaly_report,
    get_payment_plan,
)
from app.services.treasury_service import _as_number


class FinanceDashboardService:
    """SQL-backed finance intelligence dashboard.

    All financial numbers come from the company SQL Server. The service only
    applies deterministic calculations/rules on top of those numbers; it does
    not ask an LLM to calculate or invent financial values.
    """

    def __init__(
        self,
        *,
        allowed_term_days: int = 90,
        history_days: int = 365,
        forecast_days: int = 30,
        opening_cash: Any = None,
        engine: Engine | None = None,
    ):
        self.allowed_term_days = max(1, min(int(allowed_term_days), 365))
        self.history_days = max(30, min(int(history_days), 730))
        self.forecast_days = max(1, min(int(forecast_days), 180))
        self.opening_cash = opening_cash
        self.engine = engine or get_sqlserver_engine()
        self.risk_service = CustomerRiskService()

    def build_dashboard(self) -> dict[str, Any]:
        server_date = self._server_date()
        daily = get_daily_treasury_briefing(
            due_days=min(self.forecast_days, 30),
            engine=self.engine,
        )
        cheque_risk = get_cheque_risk_dashboard(
            days=max(self.forecast_days, 60),
            engine=self.engine,
        )
        cashflow = get_cashflow_scenarios(
            days=self.forecast_days,
            opening_cash=self.opening_cash,
            history_days=min(self.history_days, 730),
            engine=self.engine,
        )
        anomalies = get_financial_anomaly_report(
            days=min(self.history_days, 365),
            large_amount_threshold=None,
            limit=1000,
            engine=self.engine,
        )
        payment_plan = get_payment_plan(
            days=self.forecast_days,
            available_cash=self.opening_cash,
            engine=self.engine,
        )
        customer_risks = self._customer_risks()

        prediction_service = FinancePredictionService(
            history_days=self.history_days,
            forecast_days=self.forecast_days,
            allowed_term_days=self.allowed_term_days,
            opening_cash=self.opening_cash,
            engine=self.engine,
        )
        customer_predictions = prediction_service.customer_predictions(limit=250)
        cheque_return_predictions = prediction_service.cheque_return_predictions(limit=100)
        cash_shortage = prediction_service.cash_shortage_forecast()
        collection_priorities = prediction_service.collection_priorities(limit=25)

        legacy_alerts = self._build_alerts(
            daily=daily,
            cheque_risk=cheque_risk,
            cashflow=cashflow,
            anomalies=anomalies,
            customer_risks=customer_risks,
        )
        alerts = ExplainableAlertService.build(
            daily=daily,
            cheque_risk=cheque_risk,
            anomalies=anomalies,
            customer_predictions=customer_predictions,
            cash_shortage=cash_shortage,
            collection_priorities=collection_priorities,
        )
        recommendations = self._build_recommendations(
            cashflow=cashflow,
            cheque_risk=cheque_risk,
            payment_plan=payment_plan,
            anomalies=anomalies,
            customer_risks=customer_risks,
        )

        return {
            "status": "success",
            "source": "company_sql_server",
            "database": settings.SQLSERVER_DATABASE,
            "as_of_date": server_date.isoformat(),
            "currency_name": settings.treasury_operational_currency_name,
            "policy": {
                "allowed_cheque_term_days": self.allowed_term_days,
                "customer_history_days": self.history_days,
                "forecast_days": self.forecast_days,
            },
            "executive_summary": self._executive_summary(
                daily=daily,
                cheque_risk=cheque_risk,
                cashflow=cashflow,
                alerts=alerts,
                customer_risks=customer_risks,
            ),
            "kpis": {
                "today_approved_receipts": daily.get("today", {}).get("receipt_total", 0),
                "today_approved_payments": daily.get("today", {}).get("payment_total", 0),
                "today_document_net": daily.get("today", {}).get("document_net_movement", 0),
                "upcoming_issued_cheques": cheque_risk.get("summary", {}).get("issued_upcoming_total", 0),
                "upcoming_received_cheques": cheque_risk.get("summary", {}).get("received_upcoming_total", 0),
                "overdue_issued_cheques": cheque_risk.get("summary", {}).get("issued_overdue_total", 0),
                "overdue_received_cheques": cheque_risk.get("summary", {}).get("received_overdue_total", 0),
                "protested_received_cheques": cheque_risk.get("summary", {}).get("protested_received_total", 0),
                "high_risk_customers": sum(1 for item in customer_risks if item["risk_level"] == "high"),
                "medium_risk_customers": sum(1 for item in customer_risks if item["risk_level"] == "medium"),
                "alert_count": len(alerts),
            },
            "cashflow_forecast": cashflow,
            "predictions": {
                "customer_collection": customer_predictions,
                "cheque_return": cheque_return_predictions,
                "cash_shortage": cash_shortage,
                "collection_priorities": collection_priorities,
            },
            "cheque_risk": cheque_risk,
            "customer_risk": {
                "history_days": self.history_days,
                "allowed_term_days": self.allowed_term_days,
                "count": len(customer_risks),
                "customers": customer_risks,
            },
            "payment_plan": payment_plan,
            "anomaly_controls": anomalies,
            "alerts": alerts,
            "alerts_legacy": legacy_alerts,
            "recommendations": recommendations,
            "data_classification": {
                "actual": "مستقیماً از SQL Server/ERP",
                "calculated": "محاسبه قطعی روی داده واقعی",
                "forecast": "برآورد توضیح‌پذیر بر پایه داده واقعی و قواعد/نرخ‌های تاریخی",
                "recommendation": "پیشنهاد تصمیم‌یار؛ نیازمند تایید مدیر مالی",
            },
            "limitations": [
                "Cash-flow output is an explainable scenario model, not a trained statistical probability model.",
                "If opening_cash is not configured/passed, projected closing cash remains unknown rather than being guessed.",
                "Customer risk is rule-based and auditable; it is not an ML probability until labeled historical outcomes are available.",
                "Dashboard is read-only and does not post documents, transfer money, or approve cheques.",
                "Collection prediction in this version is cheque-based; open sales invoices are not yet integrated.",
                "Late-payment and cheque-return percentages are explainable empirical estimates, not trained ML probabilities.",
            ],
        }

    def health(self) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT DB_NAME() AS [DatabaseName], "
                    "CAST(GETDATE() AS datetime2) AS [ServerTime]"
                )
            ).mappings().one()
        return {
            "status": "ready",
            "source": "company_sql_server",
            "database": row["DatabaseName"],
            "server_time": str(row["ServerTime"]),
            "read_only_intent": True,
        }

    def _server_date(self) -> date:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT CAST(GETDATE() AS date) AS [ServerDate]")
            ).mappings().one()["ServerDate"]

    def _customer_risks(self) -> list[dict[str, Any]]:
        """Aggregate received-cheque behavior by ERP CounterPartRef."""
        query = text(
            """
            SELECT
                note.[CounterPartRef],
                counterpart.[Code] AS [CounterPartCode],
                counterpart.[Title] AS [CounterPartName],
                COUNT_BIG(*) AS [ChequeCount],
                COALESCE(SUM(note.[Amount]), 0) AS [TotalAmount],
                COALESCE(SUM(CASE WHEN master_note.[State] = 4 THEN 1 ELSE 0 END), 0)
                    AS [ReturnedCount],
                COALESCE(SUM(CASE WHEN master_note.[State] = 4 THEN note.[Amount] ELSE 0 END), 0)
                    AS [ReturnedAmount],
                AVG(CASE
                    WHEN note.[DueDate] IS NOT NULL AND receipt.[Date] IS NOT NULL
                    THEN CAST(DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date)) AS float)
                    ELSE NULL
                END) AS [AverageTermDays],
                MAX(CASE
                    WHEN note.[DueDate] IS NOT NULL AND receipt.[Date] IS NOT NULL
                    THEN DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date))
                    ELSE NULL
                END) AS [MaxTermDays],
                COALESCE(SUM(CASE
                    WHEN note.[DueDate] IS NOT NULL
                     AND receipt.[Date] IS NOT NULL
                     AND DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date)) > :allowed_term_days
                    THEN 1 ELSE 0 END), 0) AS [OverPolicyCount],
                COALESCE(SUM(CASE WHEN master_note.[State] IN (1, 2) THEN note.[Amount] ELSE 0 END), 0)
                    AS [OpenChequeAmount]
            FROM RPA3.[ReceiptReceivableNote] AS note
            INNER JOIN RPA3.[Receipt] AS receipt
                ON receipt.[ReceiptID] = note.[ReceiptRef]
            LEFT JOIN RPA3.[ReceivableNote] AS master_note
                ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
            LEFT JOIN FIN3.[DL] AS counterpart
                ON counterpart.[DLID] = note.[CounterPartRef]
            WHERE receipt.[ApproveState] = 3
              AND receipt.[ItemType] = 1
              AND receipt.[Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
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
            rows = connection.execute(
                query,
                {
                    "history_days": self.history_days,
                    "allowed_term_days": self.allowed_term_days,
                },
            ).mappings().all()

        result: list[dict[str, Any]] = []
        for row in rows:
            risk = self.risk_service.analyze(
                counterpart_code=str(row["CounterPartCode"] or row["CounterPartRef"]),
                counterpart_name=str(row["CounterPartName"] or "نامشخص"),
                cheque_count=int(row["ChequeCount"] or 0),
                total_amount=float(row["TotalAmount"] or 0),
                returned_count=int(row["ReturnedCount"] or 0),
                returned_amount=float(row["ReturnedAmount"] or 0),
                average_term_days=(
                    float(row["AverageTermDays"])
                    if row["AverageTermDays"] is not None
                    else None
                ),
                max_term_days=(
                    float(row["MaxTermDays"])
                    if row["MaxTermDays"] is not None
                    else None
                ),
                allowed_term_days=self.allowed_term_days,
            )
            risk["counterpart_ref"] = int(row["CounterPartRef"])
            risk["metrics"]["over_policy_count"] = int(row["OverPolicyCount"] or 0)
            risk["metrics"]["open_cheque_amount"] = _as_number(row["OpenChequeAmount"])
            result.append(risk)

        rank = {"high": 3, "medium": 2, "low": 1}
        result.sort(
            key=lambda item: (
                rank.get(item["risk_level"], 0),
                item["risk_score"],
                item["metrics"]["total_amount"],
            ),
            reverse=True,
        )
        return result

    @staticmethod
    def _probable_scenario(cashflow: dict[str, Any]) -> dict[str, Any]:
        for scenario in cashflow.get("scenarios", []):
            if scenario.get("scenario") == "probable":
                return scenario
        return {}

    def _build_alerts(
        self,
        *,
        daily: dict[str, Any],
        cheque_risk: dict[str, Any],
        cashflow: dict[str, Any],
        anomalies: dict[str, Any],
        customer_risks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []

        for item in daily.get("alerts", []):
            alerts.append({
                "level": item.get("severity", "warning"),
                "type": item.get("code", "treasury"),
                "title": item.get("message", "هشدار خزانه"),
                "message": item.get("message", ""),
                "metric": item.get("amount"),
            })

        for item in cheque_risk.get("alerts", []):
            alerts.append({
                "level": item.get("severity", item.get("level", "warning")),
                "type": item.get("code", item.get("type", "cheque_risk")),
                "title": item.get("message", "ریسک چک"),
                "message": item.get("message", ""),
                "metric": item.get("amount"),
            })

        probable = self._probable_scenario(cashflow)
        if probable.get("liquidity_warning"):
            alerts.append({
                "level": "critical",
                "type": "forecast_liquidity_gap",
                "title": "هشدار کسری نقدینگی در سناریوی محتمل",
                "message": f"سناریوی محتمل {self.forecast_days} روزه مانده پایانی منفی نشان می‌دهد.",
                "metric": probable.get("projected_closing_cash"),
            })

        finding_count = int(anomalies.get("finding_count", 0) or 0)
        if finding_count:
            alerts.append({
                "level": "warning",
                "type": "anomaly_candidates",
                "title": "موارد مالی نیازمند کنترل",
                "message": f"{finding_count} مورد کاندید بررسی در کنترل‌های مالی شناسایی شد.",
                "metric": finding_count,
            })

        for customer in customer_risks:
            if customer["risk_level"] not in {"high", "medium"}:
                continue
            alerts.append({
                "level": "critical" if customer["risk_level"] == "high" else "warning",
                "type": "customer_cheque_risk",
                "title": f"ریسک مشتری: {customer['counterpart_name']}",
                "message": "؛ ".join(customer.get("reasons", [])[:3]) or "نیازمند بررسی",
                "metric": customer["risk_score"],
                "counterpart_ref": customer["counterpart_ref"],
            })

        severity = {"critical": 4, "high": 3, "warning": 2, "medium": 2, "info": 1}
        alerts.sort(key=lambda item: severity.get(str(item.get("level")).lower(), 0), reverse=True)
        return alerts[:50]

    def _build_recommendations(
        self,
        *,
        cashflow: dict[str, Any],
        cheque_risk: dict[str, Any],
        payment_plan: dict[str, Any],
        anomalies: dict[str, Any],
        customer_risks: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        recommendations: list[dict[str, str]] = []
        probable = self._probable_scenario(cashflow)

        if probable.get("projected_net_change", 0) < 0:
            recommendations.append({
                "priority": "high",
                "action": "بازبینی برنامه پرداخت و تمرکز بر وصول‌های نزدیک‌سررسید",
                "reason": "سناریوی محتمل جریان نقد، خالص تغییر منفی نشان می‌دهد.",
            })

        summary = cheque_risk.get("summary", {})
        if (summary.get("protested_received_count", 0) or 0) > 0:
            recommendations.append({
                "priority": "high",
                "action": "پیگیری چک‌های واخواست‌شده پیش از افزایش اعتبار مشتری",
                "reason": "در وضعیت فعلی چک دریافتی واخواست‌شده وجود دارد.",
            })

        plan_summary = payment_plan.get("summary", {})
        if plan_summary.get("funding_gap") not in (None, 0, 0.0):
            recommendations.append({
                "priority": "high",
                "action": "تأمین یا جابه‌جایی منابع برای تعهدات سررسیدشونده",
                "reason": "برنامه پرداخت با منابع اعلام‌شده دارای کسری است.",
            })

        high_risk = [item for item in customer_risks if item["risk_level"] == "high"]
        if high_risk:
            names = "، ".join(item["counterpart_name"] for item in high_risk[:3])
            recommendations.append({
                "priority": "high",
                "action": "بازبینی سقف و شرایط پذیرش چک مشتریان پرریسک",
                "reason": f"بالاترین ریسک فعلی مربوط به: {names}",
            })

        if int(anomalies.get("finding_count", 0) or 0) > 0:
            recommendations.append({
                "priority": "medium",
                "action": "بازبینی موارد غیرعادی قبل از بستن کنترل روزانه",
                "reason": "کنترل‌های خودکار موارد نیازمند بررسی انسانی پیدا کرده‌اند.",
            })

        if not recommendations:
            recommendations.append({
                "priority": "normal",
                "action": "ادامه پایش روزانه",
                "reason": "بر اساس قواعد نسخه فعلی، اقدام فوری جدیدی شناسایی نشد.",
            })
        return recommendations

    def _executive_summary(
        self,
        *,
        daily: dict[str, Any],
        cheque_risk: dict[str, Any],
        cashflow: dict[str, Any],
        alerts: list[dict[str, Any]],
        customer_risks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        probable = self._probable_scenario(cashflow)
        high = [item for item in customer_risks if item["risk_level"] == "high"]
        critical_alerts = sum(1 for item in alerts if item.get("level") in {"critical", "high"})
        return {
            "headline": (
                "نیازمند توجه فوری"
                if critical_alerts
                else "وضعیت تحت کنترل قواعد فعلی"
            ),
            "today_net_document_movement": daily.get("today", {}).get("document_net_movement", 0),
            "probable_forecast_net_change": probable.get("projected_net_change"),
            "probable_projected_closing_cash": probable.get("projected_closing_cash"),
            "high_risk_customer_count": len(high),
            "critical_alert_count": critical_alerts,
            "top_alerts": alerts[:5],
            "note": "خلاصه از داده SQL و قواعد قطعی تولید شده و عدد مالی توسط LLM ساخته نشده است.",
        }
