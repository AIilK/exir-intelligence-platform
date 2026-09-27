from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from app.services.karamad_manual_import_service import KaramadManualImportService
from app.utils.jalali import parse_jalali_date


class FinanceAgentDataHub:
    """Single auditable data snapshot shared by finance agents.

    The hub does not invent or forecast missing KarAmand data. It exposes what is
    currently loaded and marks known completeness limitations explicitly.
    """

    def __init__(self, karamad: KaramadManualImportService | None = None):
        self.karamad = karamad or KaramadManualImportService()

    @staticmethod
    def _amount(rows: list[dict[str, Any]]) -> float:
        return round(sum(float(row.get("amount_rial") or 0) for row in rows), 2)

    @staticmethod
    def _source_kinds(row: dict[str, Any]) -> list[str]:
        return list(row.get("source_kinds") or [row.get("source_kind")])

    @staticmethod
    def _due_bucket(row: dict[str, Any]) -> tuple[str, int | None]:
        due = parse_jalali_date(row.get("due_date_jalali") or row.get("transfer_date_jalali"))
        if due is None:
            return "unknown", None
        days = (due - date.today()).days
        if days < 0:
            return "overdue", days
        if days == 0:
            return "today", 0
        return "future", days

    def _kind_rows(self, rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        return [row for row in rows if kind in self._source_kinds(row)]

    def _cheque_summary(self, rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
        selected = self._kind_rows(rows, kind)
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in selected:
            bucket, days = self._due_bucket(row)
            payload = dict(row)
            payload["days_to_due"] = days
            buckets[bucket].append(payload)
        return {
            "count": len(selected),
            "amount_rial": self._amount(selected),
            "overdue_count": len(buckets["overdue"]),
            "overdue_amount_rial": self._amount(buckets["overdue"]),
            "today_count": len(buckets["today"]),
            "today_amount_rial": self._amount(buckets["today"]),
            "future_count": len(buckets["future"]),
            "future_amount_rial": self._amount(buckets["future"]),
            "unknown_due_count": len(buckets["unknown"]),
            "unknown_due_amount_rial": self._amount(buckets["unknown"]),
        }

    def _freshness(self, state: dict[str, Any]) -> dict[str, Any]:
        latest_by_kind: dict[str, dict[str, Any]] = {}
        for item in state.get("imports") or []:
            kind = item.get("source_kind")
            if kind:
                latest_by_kind[kind] = item
        result: dict[str, Any] = {}
        for kind in ("received_cheques", "issued_cheques", "received_transfers", "paid_transfers"):
            item = latest_by_kind.get(kind) or {}
            result[kind] = {
                "filename": item.get("filename"),
                "imported_at": item.get("imported_at"),
                "rows_in_file": item.get("rows_in_file"),
                "snapshot_replace": bool(item.get("snapshot_replace")),
            }
        return result

    def build(self) -> dict[str, Any]:
        state = self.karamad._state()
        rows = list(state.get("records", {}).values())
        summary = self.karamad.summary(state=state)
        received_cheques = self._cheque_summary(rows, "received_cheques")
        issued_cheques = self._cheque_summary(rows, "issued_cheques")

        customer = self.karamad.customer_summary()
        customers = customer.get("customers") or []
        top_customers = sorted(
            customers,
            key=lambda x: float(x.get("received_cheque_amount_rial") or 0)
            + float(x.get("received_transfer_amount_rial") or 0),
            reverse=True,
        )[:20]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_version": "karamad-unified-snapshot-v106",
            "karamad": {
                "record_count": len(rows),
                "freshness": self._freshness(state),
                "received_cheques": received_cheques,
                "issued_cheques": {
                    **issued_cheques,
                    "future_data_complete": False,
                    "returns_available": False,
                    "note": "فایل فعلی فقط چک‌های پرداختی ثبت‌شده کارآمد است؛ نبود رکورد آینده به معنی نبود تعهد آینده نیست و برگشتی برای این منبع فعلاً گزارش نشده است.",
                },
                "received_transfers": {
                    "count": int(summary.get("received_transfer_total_count") or 0),
                    "amount_rial": float(summary.get("received_transfer_total_rial") or 0),
                },
                "paid_transfers": {
                    "count": int(summary.get("paid_transfer_total_count") or 0),
                    "amount_rial": float(summary.get("paid_transfer_total_rial") or 0),
                    "bank_to_bank_count": int(summary.get("paid_transfer_bank_to_bank_count") or 0),
                    "bank_to_bank_amount_rial": float(summary.get("paid_transfer_bank_to_bank_rial") or 0),
                    "other_count": int(summary.get("paid_transfer_other_count") or 0),
                    "other_amount_rial": float(summary.get("paid_transfer_other_rial") or 0),
                },
                "petty_cash": {
                    "count": int(summary.get("petty_cash_count") or 0),
                    "amount_rial": float(summary.get("petty_cash_rial") or 0),
                },
                "customer_count": int(customer.get("customer_count") or 0),
                "top_customers": top_customers,
            },
            "routing": {
                "cash_bank_movement": ["rahkaran approved cash/deposit", "karamad received_transfers", "karamad paid_transfers"],
                "cashflow_forecast": ["rahkaran open future cheques", "karamad received_cheques with due date", "karamad issued_cheques only as registered/incomplete future source", "salary reserve"],
                "cheque_risk": ["rahkaran received cheques", "karamad received_cheques"],
                "cheque_payment": ["rahkaran issued cheques", "karamad issued_cheques registered snapshot"],
                "customer_behavior": ["rahkaran customer history", "karamad unified customer cheque/transfer history"],
                "collection": ["rahkaran receivables", "karamad received cheque overdue/today/future"],
                "management_summary": ["all agent outputs from the same V106 hub snapshot"],
            },
            "rules": {
                "bank_to_bank_net_effect": 0,
                "petty_cash_cashflow_included": False,
                "karamad_issued_future_complete": False,
                "karamad_issued_returns_available": False,
                "karamad_snapshots_replace_previous": True,
            },
        }
