"""داده مشترک یک دور اجرای Page Agentها (V171).

هر منبع (چک‌ها، نقدینگی، مشتری، ...) فقط یک بار در هر دور خوانده می‌شود و بین Agentهایی که
موازی اجرا می‌شوند به اشتراک گذاشته می‌شود. اجرای دستی یک Agent فقط منابع همان Agent را می‌خواند.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, timedelta
from typing import Any, Callable


def _days(row: dict[str, Any]) -> int | None:
    value = row.get("days_until_due")
    if value is None:
        value = row.get("days_to_due")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source(row: dict[str, Any]) -> str:
    raw = str(row.get("source_system") or row.get("data_source") or "rahkaran").lower()
    return "karamad" if "karamad" in raw or "کارآمد" in raw else "rahkaran"


def cheque_buckets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Open cheques split by due window (same rule as the management page: future = today or later)."""

    def pack(items: list[dict[str, Any]]) -> dict[str, Any]:
        by_source: dict[str, dict[str, float]] = {}
        for item in items:
            bucket = by_source.setdefault(_source(item), {"count": 0, "amount_rial": 0.0})
            bucket["count"] += 1
            bucket["amount_rial"] += float(item.get("amount") or 0)
        return {"count": len(items), "amount_rial": round(sum(float(x.get("amount") or 0) for x in items), 2),
                "sources": by_source}

    known = [(row, _days(row)) for row in rows]
    return {
        "all": pack(rows),
        "overdue": pack([r for r, d in known if d is not None and d < 0]),
        "today": pack([r for r, d in known if d == 0]),
        "next_7": pack([r for r, d in known if d is not None and 0 <= d <= 7]),
        "next_30": pack([r for r, d in known if d is not None and 0 <= d <= 30]),
        "future": pack([r for r, d in known if d is not None and d >= 0]),
        "unknown": pack([r for r, d in known if d is None]),
    }


class AgentRunContext:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _get(self, key: str, loader: Callable[[], Any]) -> Any:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if key not in self._values:
                self._values[key] = loader()
            return self._values[key]

    # ------------------------------------------------------------ policies
    def policies(self) -> dict[str, Any]:
        from app.services.finance_operations_service import FinanceOperationsStore
        return self._get("policies", lambda: FinanceOperationsStore().policies())

    def allowed_term_days(self) -> int:
        return int(self.policies().get("allowed_term_days", 90))

    # ------------------------------------------------------------- cheques
    def received_open(self) -> dict[str, Any]:
        from app.services.treasury_service import get_open_received_cheques
        return self._get("received_open", lambda: get_open_received_cheques(period="all"))

    def issued_open(self) -> dict[str, Any]:
        from app.services.treasury_service import get_open_issued_cheques
        return self._get("issued_open", get_open_issued_cheques)

    def cheque_portfolio(self) -> dict[str, Any]:
        """Same structure the management page reads from management_summary.analysis.cheque_portfolio."""

        def build() -> dict[str, Any]:
            received = cheque_buckets(self.received_open().get("cheques") or [])
            issued = cheque_buckets(self.issued_open().get("cheques") or [])
            portfolio: dict[str, Any] = {"data_sources": ["راهکاران", "کارآمد"]}
            for prefix, buckets in (("received", received), ("issued", issued)):
                for name, bucket in (("future_open", buckets["future"]), ("overdue", buckets["overdue"]),
                                     ("unknown_due", buckets["unknown"])):
                    portfolio[f"{prefix}_{name}_count"] = bucket["count"]
                    portfolio[f"{prefix}_{name}_amount_rial"] = bucket["amount_rial"]
                    portfolio[f"{prefix}_{name}_sources"] = bucket["sources"]
            portfolio["rule"] = "مانده باز آینده فقط شامل سررسید امروز و آینده است؛ سررسیدگذشته جدا گزارش می‌شود."
            return portfolio
        return self._get("cheque_portfolio", build)

    def cheque_quality(self) -> dict[str, Any]:
        from app.services.treasury_service import get_cheque_state_quality
        return self._get("cheque_quality", get_cheque_state_quality)

    # ------------------------------------------------------------ cashflow
    def excel_service(self):
        from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService
        return self._get("excel_service", MonthlyCashflowExcelService)

    def excel_latest(self) -> dict[str, Any] | None:
        return self._get("excel_latest", lambda: self.excel_service().latest_snapshot())

    def excel_monthly(self) -> dict[str, Any] | None:
        def build():
            months = self.excel_service().months()
            if not months:
                return None
            latest = months[0]
            return self.excel_service().analyze(latest["jalali_year"], latest["jalali_month"])
        return self._get("excel_monthly", build)

    def opening_cash(self) -> float | None:
        latest = self.excel_latest()
        return float(latest.get("liquidity_rial") or 0) if latest else None

    def cash(self) -> dict[str, Any]:
        from app.services.unified_cashflow_service import UnifiedDailyCashflowService
        return self._get("cash", lambda: UnifiedDailyCashflowService(allowed_term_days=self.allowed_term_days()).build())

    def prediction_service(self):
        from app.services.finance_prediction_service import FinancePredictionService
        return self._get("prediction_service", lambda: FinancePredictionService(
            allowed_term_days=self.allowed_term_days(), opening_cash=self.opening_cash()))

    def cheque_predictions(self) -> dict[str, Any]:
        """Return-risk prediction of every open received cheque (dashboard cheque list reads it)."""
        return self._get("cheque_predictions", lambda: self.prediction_service().cheque_return_predictions(
            limit=None, batch_size=1000, include_all_open=True))

    def collections(self) -> dict[str, Any]:
        def build():
            report = self.prediction_service().collection_priorities(limit=100)
            report["karamad_context"] = {"received_cheques": self.data_hub()["karamad"]["received_cheques"],
                                         "top_customers": self.data_hub()["karamad"].get("top_customers")}
            return report
        return self._get("collections", build)

    # ------------------------------------------------------------ customers
    def data_hub(self) -> dict[str, Any]:
        from app.services.finance_agent_data_hub import FinanceAgentDataHub
        return self._get("data_hub", lambda: FinanceAgentDataHub().build())

    def customer(self) -> dict[str, Any]:
        def build():
            from app.services.customer_intelligence_service import CustomerIntelligenceService
            report = CustomerIntelligenceService(allowed_term_days=self.allowed_term_days()).dashboard(limit=1000)
            karamad = self.data_hub()["karamad"]
            report["karamad_context"] = {key: karamad.get(key) for key in (
                "customer_count", "top_customers", "received_cheques", "received_transfers", "paid_transfers")}
            return report
        return self._get("customer", build)

    def representatives(self) -> dict[str, Any]:
        from app.services.representative_intelligence_service import RepresentativeIntelligenceService
        return self._get("representatives", lambda: RepresentativeIntelligenceService().aggregate(
            self.customer().get("customers") or []))

    # ----------------------------------------------------------- movements
    def cash_bank(self) -> dict[str, Any]:
        from app.services.cash_bank_movement_service import CashBankMovementService
        return self._get("cash_bank", lambda: CashBankMovementService().report(
            period="month", approval_status="approved", limit=5000))

    def internal_transfers(self) -> dict[str, Any]:
        from app.services.cash_bank_movement_service import CashBankMovementService
        return self._get("internal_transfers", lambda: CashBankMovementService().internal_transfers(
            period="month", limit=100))

    def payment_commitments(self) -> dict[str, Any]:
        from app.services.payment_commitment_service import PaymentCommitmentService
        return self._get("payment_commitments", lambda: PaymentCommitmentService().report(horizon_days=365, limit=500))

    def company_payments(self) -> list[dict[str, Any]]:
        def build():
            from app.services.treasury_service import get_company_payment_orders, get_company_payment_orders_karamad
            rahkaran = get_company_payment_orders(limit=5000)["rows"]
            since = (date.today() - timedelta(days=95)).isoformat()
            karamad = get_company_payment_orders_karamad(limit=20000, since=since)["rows"]
            return rahkaran + karamad
        return self._get("company_payments", build)

    def b2b(self) -> list[dict[str, Any]]:
        def build():
            from app.services.treasury_service import (
                get_customer_b2b_remittances, get_customer_b2b_remittances_karamad)
            rows = list(get_customer_b2b_remittances(limit=20000).get("rows") or [])
            try:
                rows += get_customer_b2b_remittances_karamad(limit=20000).get("rows") or []
            except Exception:  # noqa: BLE001 — Rahkaran alone is still a valid report
                pass
            return rows
        return self._get("b2b", build)

    # --------------------------------------------------------- distribution
    def distribution_overview(self) -> dict[str, Any]:
        from app.services.karamad_distribution_service import KaramadDistributionService
        return self._get("distribution_overview", lambda: KaramadDistributionService().overview())

    def distribution_timeline(self) -> dict[str, Any]:
        from app.services.karamad_distribution_service import KaramadDistributionService
        return self._get("distribution_timeline", lambda: KaramadDistributionService().timeline(14))

    # ------------------------------------------------------- reconciliation
    def reconciliation_reports(self, limit: int = 40) -> list[dict[str, Any]]:
        def build():
            import json
            from app.core.config import settings
            with sqlite3.connect(settings.treasury_reconciliation_db) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute(
                    "SELECT reconciliation_id, created_at, account_id, filename, report_json "
                    "FROM treasury_reconciliation_reports ORDER BY created_at DESC LIMIT ?", (limit,),
                ).fetchall()
            out = []
            for row in rows:
                report = json.loads(row["report_json"])
                out.append({
                    "reconciliation_id": row["reconciliation_id"], "created_at": row["created_at"],
                    "filename": row["filename"], "account": report.get("account") or {},
                    "file": report.get("file") or {}, "summary": report.get("summary") or {},
                    "book_balance": {k: v for k, v in (report.get("book_balance") or {}).items() if k != "daily"},
                })
            return out
        return self._get("reconciliation_reports", build)

    # --------------------------------------------------- legacy agent cache
    def legacy(self, key: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Legacy decision-agent outputs (they call the LLM themselves), shared by manager/scenario."""
        return self._get(f"legacy:{key}", loader)
