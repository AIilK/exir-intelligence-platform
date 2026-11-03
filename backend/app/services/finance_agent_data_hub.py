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

    @staticmethod
    def _live_cheque_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Same summary shape as _cheque_summary, from live rows carrying days_until_due."""

        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            days = row.get("days_until_due", row.get("days_to_due"))
            bucket = "unknown" if days is None else "overdue" if days < 0 else "today" if days == 0 else "future"
            buckets[bucket].append({**row, "amount_rial": row.get("amount_rial", row.get("amount"))})
        everything = [r for items in buckets.values() for r in items]
        amount = FinanceAgentDataHub._amount
        return {
            "count": len(everything), "amount_rial": amount(everything),
            **{f"{name}_count": len(buckets[name]) for name in ("overdue", "today", "future")},
            **{f"{name}_amount_rial": amount(buckets[name]) for name in ("overdue", "today", "future")},
            "unknown_due_count": len(buckets["unknown"]), "unknown_due_amount_rial": amount(buckets["unknown"]),
        }

    def _live_karamad(self) -> dict[str, Any]:
        """V171: cheques and drafts straight from Karamad SQL instead of the manual Excel import."""

        from app.services.karamad_live_cash_draft_service import KaramadLiveCashDraftService
        from app.services.treasury_service import _karamad_cheques

        from app.services.received_cheque_current_status import received_cheque_is_approved_open_holding

        received = self._live_cheque_summary(
            [row for row in _karamad_cheques("received_cheques") if received_cheque_is_approved_open_holding(row)])
        issued = self._live_cheque_summary(_karamad_cheques("issued_cheques"))
        start = date(date.today().year - (1 if date.today().month < 3 or (date.today().month == 3 and date.today().day < 21) else 0), 3, 21)
        drafts = KaramadLiveCashDraftService().report(start=start, end=date.today(), limit=200000).get("movements") or []

        def total(items: list[dict[str, Any]]) -> dict[str, Any]:
            return {"count": len(items), "amount_rial": round(sum(float(x.get("amount_rial") or 0) for x in items), 2)}

        receipts = [m for m in drafts if m["movement_type"] == "bank_receipt"]
        payments = [m for m in drafts if m["movement_type"] == "bank_payment"]
        bank_to_bank = [m for m in payments if m.get("classification") == "company_bank_transfer"]
        petty = [m for m in drafts if m.get("classification") == "petty_cash"]
        return {
            "received_cheques": received,
            "issued_cheques": issued,
            "received_transfers": total(receipts),
            "paid_transfers": {
                **total(payments),
                "bank_to_bank_count": len(bank_to_bank),
                "bank_to_bank_amount_rial": total(bank_to_bank)["amount_rial"],
                "other_count": len(payments) - len(bank_to_bank),
                "other_amount_rial": round(total(payments)["amount_rial"] - total(bank_to_bank)["amount_rial"], 2),
            },
            "petty_cash": total(petty),
            "period_start": start.isoformat(),
        }

    def build(self) -> dict[str, Any]:
        state = self.karamad._state()
        rows = list(state.get("records", {}).values())
        summary = self.karamad.summary(state=state)
        received_cheques = self._cheque_summary(rows, "received_cheques")
        issued_cheques = self._cheque_summary(rows, "issued_cheques")
        try:
            live = self._live_karamad()
        except Exception as exc:  # noqa: BLE001 — fall back to the last manual import
            live = None
            live_error = f"{type(exc).__name__}: {str(exc)[:200]}"
        if live:
            received_cheques, issued_cheques = live["received_cheques"], live["issued_cheques"]

        customer = self.karamad.customer_summary()
        customers = customer.get("customers") or []
        top_customers = sorted(
            customers,
            key=lambda x: float(x.get("received_cheque_amount_rial") or 0)
            + float(x.get("received_transfer_amount_rial") or 0),
            reverse=True,
        )[:20]

        imported_transfers = {
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
        }
        transfers = {key: live[key] for key in imported_transfers} if live else imported_transfers

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_version": "karamad-live-sql-v171" if live else "karamad-unified-snapshot-v106",
            "karamad": {
                "source": "live" if live else "import",
                "live_error": None if live else live_error,
                "live_period_start": live.get("period_start") if live else None,
                "record_count": len(rows),
                "freshness": self._freshness(state),
                "received_cheques": received_cheques,
                "issued_cheques": {
                    **issued_cheques,
                    "future_data_complete": bool(live),
                    "returns_available": False,
                    "note": (
                        "چک‌های پرداختی زنده کارآمد با وضعیت نهایی «عادی» (هنوز پاس‌نشده)."
                        if live else
                        "فایل فعلی فقط چک‌های پرداختی ثبت‌شده کارآمد است؛ نبود رکورد آینده به معنی نبود تعهد آینده نیست و برگشتی برای این منبع فعلاً گزارش نشده است."
                    ),
                },
                **transfers,
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
                "karamad_issued_future_complete": bool(live),
                "karamad_issued_returns_available": False,
                "karamad_snapshots_replace_previous": not live,
            },
        }
