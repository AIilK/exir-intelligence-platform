from __future__ import annotations

"""V159: Live customer-level roll-up of Karamad activity («حواله مشتریان» /
the customer-profile drill-down), replacing
KaramadManualImportService.customer_summary()/customer_detail() for the
transfers and received-cheques portion.

Sources:
- received/paid transfers -> KaramadLiveCashDraftService, filtered to
  channel == "draft" (i.e. dbo.tblDraftD/tblDraftP — bank drafts/«حواله»,
  not dbo.tblCashD/tblCashP which is company petty cash).
- received cheques -> KaramadLiveReceivedChequeService (dbo.tblChequeD).
- issued cheques -> still the manual Excel snapshot, because tblChequeP has
  not been reverse-engineered yet. Merged in so the combined per-customer
  view stays complete rather than silently dropping a whole category.

Output shape matches KaramadManualImportService.customer_summary() and
.customer_detail() field-for-field, so the frontend and
finance_agent_data_hub consumers work unchanged.
"""

from typing import Any

from app.services.karamad_live_cash_draft_service import KaramadLiveCashDraftService
from app.services.karamad_live_received_cheque_service import KaramadLiveReceivedChequeService


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


class KaramadLiveCustomerActivityService:
    def __init__(self):
        self._cash_draft = KaramadLiveCashDraftService()
        self._received_cheque = KaramadLiveReceivedChequeService()

    def _transfer_rows(self, branch: str | None = None) -> list[dict[str, Any]]:
        from datetime import date
        data = self._cash_draft.report(start=date(2000, 1, 1), end=date.today(), branch=branch)
        # فقط طرف‌حساب‌هایی که واقعاً «مشتری»اند (tblDLClass کد ۹)؛ بانک/پرسنل/
        # تامین‌کننده و... با اینکه ممکنه توی همون حواله‌ها هم ظاهر بشن، اینجا
        # جزو «مطالبات مشتری» به‌حساب نمی‌آیند.
        rows = [r for r in data.get("movements", []) if r.get("channel") == "draft" and r.get("dl_class_ref") == 9]
        for r in rows:
            r["source_kind"] = "received_transfers" if r.get("direction") == "inflow" else "paid_transfers"
            r["transfer_id"] = r.get("document_id")
            r["transfer_number"] = r.get("document_number")
            r["registration_date_jalali"] = r.get("document_date_jalali")
            r["transfer_date_jalali"] = r.get("document_date_jalali")
        return rows

    def _received_cheque_rows(self, branch: str | None = None) -> list[dict[str, Any]]:
        rows = self._received_cheque.report(branch=branch).get("cheques", [])
        for r in rows:
            r["source_kind"] = "received_cheques"
        return rows

    def _issued_cheque_rows(self) -> list[dict[str, Any]]:
        # tblChequeP has not been reverse-engineered yet; keep the manual
        # snapshot for this one category so the combined view stays complete.
        from app.services.karamad_manual_import_service import KaramadManualImportService
        try:
            rows = KaramadManualImportService().cheque_rows("issued_cheques")
        except Exception:
            rows = []
        for r in rows:
            r["source_kind"] = "issued_cheques"
        return rows

    def _all_rows(self, branch: str | None = None) -> list[dict[str, Any]]:
        return self._transfer_rows(branch) + self._received_cheque_rows(branch) + self._issued_cheque_rows()

    def customer_summary(self, branch: str | None = None) -> dict[str, Any]:
        rows = self._all_rows(branch=branch)
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = _text(row.get("level4_name") or row.get("level5_name") or row.get("level6_name") or row.get("counterpart_name"))
            if not name:
                continue
            key = name.casefold()
            item = grouped.setdefault(key, {
                "customer_name": name, "branches": set(), "dl_refs": set(), "movement_count": 0,
                "inflow_rial": 0.0, "outflow_rial": 0.0,
                "received_cheque_count": 0, "received_cheque_amount_rial": 0.0,
                "received_cheque_overdue_count": 0, "received_cheque_overdue_amount_rial": 0.0,
                "received_cheque_today_count": 0, "received_cheque_today_amount_rial": 0.0,
                "received_cheque_future_count": 0, "received_cheque_future_amount_rial": 0.0,
                "received_cheque_returned_count": 0, "received_cheque_returned_amount_rial": 0.0,
                "issued_cheque_count": 0, "issued_cheque_amount_rial": 0.0,
                "received_transfer_count": 0, "received_transfer_amount_rial": 0.0,
                "paid_transfer_count": 0, "paid_transfer_amount_rial": 0.0,
            })
            dl_ref = row.get("dl_ref") or row.get("counterpart_ref")
            if dl_ref is not None:
                item["dl_refs"].add(int(dl_ref))
            b = _text(row.get("branch"))
            if b:
                item["branches"].add(b)
            amount = float(row.get("amount_rial") or row.get("amount") or 0)
            item["movement_count"] += 1
            kind = row.get("source_kind")
            if row.get("direction") == "inflow" or kind == "received_cheques":
                item["inflow_rial"] += amount
            else:
                item["outflow_rial"] += amount
            if kind == "received_cheques":
                item["received_cheque_count"] += 1
                item["received_cheque_amount_rial"] += amount
                status = _text(row.get("cheque_status")).replace("ي", "ی").replace("ك", "ک")
                is_returned = any(t in status for t in ("برگشت", "واخواست", "مسترد"))
                if is_returned:
                    item["received_cheque_returned_count"] += 1
                    item["received_cheque_returned_amount_rial"] += amount
                due = row.get("days_until_due")
                if isinstance(due, int) and not is_returned:
                    if due < 0:
                        item["received_cheque_overdue_count"] += 1
                        item["received_cheque_overdue_amount_rial"] += amount
                    elif due == 0:
                        item["received_cheque_today_count"] += 1
                        item["received_cheque_today_amount_rial"] += amount
                    else:
                        item["received_cheque_future_count"] += 1
                        item["received_cheque_future_amount_rial"] += amount
            elif kind == "issued_cheques":
                item["issued_cheque_count"] += 1
                item["issued_cheque_amount_rial"] += amount
            elif kind == "received_transfers":
                item["received_transfer_count"] += 1
                item["received_transfer_amount_rial"] += amount
            elif kind == "paid_transfers":
                item["paid_transfer_count"] += 1
                item["paid_transfer_amount_rial"] += amount

        customers = []
        for item in grouped.values():
            item["branches"] = sorted(item["branches"])
            item["dl_refs"] = sorted(item["dl_refs"])
            item["net_rial"] = round(item["inflow_rial"] - item["outflow_rial"], 2)
            customers.append(item)
        customers.sort(key=lambda x: (x["received_cheque_amount_rial"] + x["received_transfer_amount_rial"]), reverse=True)
        for item in customers:
            item["selected_branch"] = branch

        return {
            "status": "success",
            "live": True,
            "source": "Karamad Live SQL (+ اکسل دستی فقط برای چک پرداختی)",
            "selected_branch": branch,
            "available_branches": sorted({_text(r.get("branch")) for r in rows if _text(r.get("branch"))}),
            "customer_count": len(customers),
            "customers": customers,
            "summary": {
                "movement_count": sum(x["movement_count"] for x in customers),
                "inflow_rial": round(sum(x["inflow_rial"] for x in customers), 2),
                "outflow_rial": round(sum(x["outflow_rial"] for x in customers), 2),
                "received_cheque_count": sum(x["received_cheque_count"] for x in customers),
                "received_cheque_amount_rial": round(sum(x["received_cheque_amount_rial"] for x in customers), 2),
                "received_cheque_overdue_count": sum(x["received_cheque_overdue_count"] for x in customers),
                "received_cheque_overdue_amount_rial": round(sum(x["received_cheque_overdue_amount_rial"] for x in customers), 2),
                "received_cheque_today_count": sum(x["received_cheque_today_count"] for x in customers),
                "received_cheque_today_amount_rial": round(sum(x["received_cheque_today_amount_rial"] for x in customers), 2),
                "received_cheque_future_count": sum(x["received_cheque_future_count"] for x in customers),
                "received_cheque_future_amount_rial": round(sum(x["received_cheque_future_amount_rial"] for x in customers), 2),
                "received_cheque_returned_count": sum(x["received_cheque_returned_count"] for x in customers),
                "received_cheque_returned_amount_rial": round(sum(x["received_cheque_returned_amount_rial"] for x in customers), 2),
            },
        }

    def _account_position_for_dl_refs(self, dl_refs: list[int]) -> dict[str, Any]:
        """Sum GL balance across every DL ref that shares this customer's name
        (Karamad often has several tblDL rows for the same real-world customer,
        created at different times)."""
        from app.services.karamad_customer_account_service import KaramadCustomerAccountService

        service = KaramadCustomerAccountService()
        found_any = False
        debit = 0.0
        credit = 0.0
        breakdown: list[dict[str, Any]] = []
        fiscal_year_ref = None
        fy_start = fy_end = None
        for ref in dl_refs:
            try:
                pos = service.account_position(ref)
            except Exception:
                continue
            if not pos.get("found"):
                continue
            found_any = True
            debit += float(pos.get("debit_balance_rial") or 0)
            credit += float(pos.get("credit_balance_rial") or 0)
            breakdown.extend(pos.get("account_breakdown") or [])
            fiscal_year_ref = fiscal_year_ref or pos.get("fiscal_year_ref")
            fy_start = fy_start or pos.get("fiscal_year_start")
            fy_end = fy_end or pos.get("fiscal_year_end")
        if not found_any:
            return {"found": False}
        balance = round(debit - credit, 2)
        return {
            "found": True,
            "dl_refs": dl_refs,
            "fiscal_year_ref": fiscal_year_ref,
            "fiscal_year_start": fy_start,
            "fiscal_year_end": fy_end,
            "account_breakdown": breakdown,
            "debit_balance_rial": round(debit, 2),
            "credit_balance_rial": round(credit, 2),
            "balance_rial": balance,
            "open_account_receivable_rial": max(balance, 0.0),
            "customer_credit_rial": max(-balance, 0.0),
            "balance_status": "debtor" if balance > 0 else "creditor" if balance < 0 else "settled",
            "accounting_note": "مانده مشتری از گردش دفتر کل کارآمد (tblVoucherLines) سال مالی جاری روی تفصیلی مشتری و معین‌های ۱۳۱۳/۱۳۱۹/۱۳۲۰ محاسبه می‌شود؛ اگر مشتری چند کد تفصیلی داشته باشد، مانده همه‌شان جمع زده می‌شود.",
        }

    def collection_portfolio(self, branch: str | None = None, limit: int = 300) -> dict[str, Any]:
        """Karamad equivalent of customer_intelligence_service.collection_portfolio():
        customer list + GL balance + open cheque exposure in one dataset.

        V161: balances now come from ONE bulk GROUP BY query (bulk_account_positions)
        instead of a separate query per customer — the previous N+1 pattern could
        fire hundreds of sequential queries against the 17.5M-row ledger and made
        this page noticeably slow."""
        from app.services.karamad_customer_account_service import KaramadCustomerAccountService

        summary = self.customer_summary(branch=branch)
        customers = (summary.get("customers") or [])[: max(1, int(limit))]
        balances_by_dl = KaramadCustomerAccountService().bulk_account_positions()

        rows: list[dict[str, Any]] = []
        for item in customers:
            dl_refs = item.get("dl_refs") or []
            debit = sum(balances_by_dl.get(ref, {}).get("debit_balance_rial", 0) or 0 for ref in dl_refs)
            credit = sum(balances_by_dl.get(ref, {}).get("credit_balance_rial", 0) or 0 for ref in dl_refs)
            balance = round(debit - credit, 2)
            found_any = any(ref in balances_by_dl for ref in dl_refs)
            account = {
                "found": found_any,
                "dl_refs": dl_refs,
                "debit_balance_rial": round(debit, 2),
                "credit_balance_rial": round(credit, 2),
                "balance_rial": balance,
                "open_account_receivable_rial": max(balance, 0.0) if found_any else 0.0,
                "customer_credit_rial": max(-balance, 0.0) if found_any else 0.0,
                "balance_status": ("debtor" if balance > 0 else "creditor" if balance < 0 else "settled") if found_any else "unknown",
            }
            open_account = float(account["open_account_receivable_rial"])
            customer_credit = float(account["customer_credit_rial"])
            open_cheques = float(item.get("received_cheque_amount_rial", 0) or 0)
            exposure = round(open_account + open_cheques, 2)
            rows.append({
                **item,
                "counterpart_ref": (dl_refs or [None])[0],
                "account_position": account,
                "collection_position": {
                    "open_account_receivable_rial": round(open_account, 2),
                    "customer_credit_rial": round(customer_credit, 2),
                    "open_cheque_amount_rial": round(open_cheques, 2),
                    "total_collection_exposure_rial": exposure,
                    "cheque_coverage_percent": round(open_cheques / exposure * 100, 1) if exposure else 0.0,
                    "uncovered_percent": round(open_account / exposure * 100, 1) if exposure else 0.0,
                },
            })
        rows.sort(key=lambda x: float(x["collection_position"]["total_collection_exposure_rial"]), reverse=True)
        return {
            "status": "success",
            "live": True,
            "summary": {
                "customer_count": len(rows),
                "open_account_receivable_rial": round(sum(float(x["collection_position"]["open_account_receivable_rial"]) for x in rows), 2),
                "open_cheque_amount_rial": round(sum(float(x["collection_position"]["open_cheque_amount_rial"]) for x in rows), 2),
                "total_collection_exposure_rial": round(sum(float(x["collection_position"]["total_collection_exposure_rial"]) for x in rows), 2),
                "customer_credit_rial": round(sum(float(x["collection_position"]["customer_credit_rial"]) for x in rows), 2),
            },
            "available_branches": summary.get("available_branches") or [],
            "customers": rows,
        }

    def customer_detail(self, customer_name: str, branch: str | None = None) -> dict[str, Any]:
        wanted = _text(customer_name).casefold()
        rows = self._all_rows(branch=branch)
        matched: list[dict[str, Any]] = []
        for row in rows:
            names = [_text(row.get("level4_name")), _text(row.get("level5_name")), _text(row.get("level6_name")), _text(row.get("counterpart_name"))]
            if wanted and wanted in {n.casefold() for n in names if n}:
                payload = dict(row)
                payload["customer_name"] = next((n for n in names if n), customer_name)
                payload["effective_date_jalali"] = row.get("due_date_jalali") or row.get("transfer_date_jalali") or row.get("registration_date_jalali")
                payload["source_system"] = "karamad"
                payload["source_label"] = row.get("source_label") or "کارآمد"
                matched.append(payload)
        matched.sort(key=lambda row: (row.get("effective_date_jalali") or "", str(row.get("transfer_id") or "")), reverse=True)

        def by_kind(kind: str) -> list[dict[str, Any]]:
            return [row for row in matched if row.get("source_kind") == kind]

        def total(rows_: list[dict[str, Any]]) -> float:
            return round(sum(float(row.get("amount_rial") or row.get("amount") or 0) for row in rows_), 2)

        received_cheques = by_kind("received_cheques")
        issued_cheques = by_kind("issued_cheques")
        received_transfers = by_kind("received_transfers")
        paid_transfers = by_kind("paid_transfers")

        def is_returned(row: dict[str, Any]) -> bool:
            status = _text(row.get("cheque_status")).replace("ي", "ی").replace("ك", "ک")
            return any(t in status for t in ("برگشت", "واخواست", "مسترد"))

        returned_received = [row for row in received_cheques if is_returned(row)]
        open_received = [row for row in received_cheques if not is_returned(row)]
        overdue_received = [row for row in open_received if isinstance(row.get("days_until_due"), int) and row["days_until_due"] < 0]
        today_received = [row for row in open_received if row.get("days_until_due") == 0]
        future_received = [row for row in open_received if isinstance(row.get("days_until_due"), int) and row["days_until_due"] > 0]

        dl_refs = sorted({int(row.get("dl_ref") or row.get("counterpart_ref")) for row in matched if row.get("dl_ref") or row.get("counterpart_ref")})
        account = self._account_position_for_dl_refs(dl_refs)
        ledger_entries: list[dict[str, Any]] = []
        monthly_summary: list[dict[str, Any]] = []
        if dl_refs:
            from app.services.karamad_customer_account_service import KaramadCustomerAccountService
            ledger_service = KaramadCustomerAccountService()
            for ref in dl_refs:
                try:
                    ledger_entries.extend(ledger_service.ledger_entries(ref))
                except Exception:
                    continue
            ledger_entries.sort(key=lambda e: e.get("date") or "", reverse=True)
            # مانده تجمعی هر ردیف روی همون یک تفصیلی محاسبه شده بود؛ برای مشتری‌هایی
            # که چند تفصیلی دارن، مانده تجمعی واقعی رو روی کل ردیف‌های ادغام‌شده
            # (به ترتیب زمانی) دوباره حساب می‌کنیم تا خلاصه ماهانه درست باشه.
            running = 0.0
            by_month: dict[str, dict[str, Any]] = {}
            for e in sorted(ledger_entries, key=lambda x: x.get("date") or ""):
                running = round(running + e.get("debit_rial", 0) - e.get("credit_rial", 0), 2)
                e["running_balance_rial"] = running
                month = e.get("jalali_month") or "نامشخص"
                m = by_month.setdefault(month, {"jalali_month": month, "debit_rial": 0.0, "credit_rial": 0.0, "transaction_count": 0, "closing_balance_rial": 0.0})
                m["debit_rial"] = round(m["debit_rial"] + e.get("debit_rial", 0), 2)
                m["credit_rial"] = round(m["credit_rial"] + e.get("credit_rial", 0), 2)
                m["transaction_count"] += 1
                m["closing_balance_rial"] = running
            monthly_summary = sorted(by_month.values(), key=lambda x: x["jalali_month"], reverse=True)
        open_account = max(float(account.get("balance_rial", 0) or 0), 0.0) if account.get("found") else 0.0
        open_cheque_amount = total(open_received)
        total_exposure = round(open_account + open_cheque_amount, 2)
        all_transfers_by_date = sorted(
            received_transfers + paid_transfers,
            key=lambda row: (row.get("transfer_date_jalali") or row.get("registration_date_jalali") or "", str(row.get("transfer_id") or "")),
            reverse=True,
        )

        return {
            "status": "success",
            "live": True,
            "source": "Karamad Live SQL (+ اکسل دستی فقط برای چک پرداختی)",
            "customer_name": customer_name,
            "selected_branch": branch,
            "branches": sorted({_text(row.get("branch")) for row in matched if _text(row.get("branch"))}),
            "account_position": account,
            "collection_position": {
                "open_account_receivable_rial": round(open_account, 2),
                "customer_credit_rial": round(max(-float(account.get("balance_rial", 0) or 0), 0.0) if account.get("found") else 0.0, 2),
                "open_cheque_amount_rial": round(open_cheque_amount, 2),
                "total_collection_exposure_rial": total_exposure,
                "cheque_coverage_percent": round(open_cheque_amount / total_exposure * 100, 1) if total_exposure else 0.0,
                "uncovered_percent": round(open_account / total_exposure * 100, 1) if total_exposure else 0.0,
                "accounting_note": account.get("accounting_note"),
            },
            # درخواست شده: دو تا آخرین حواله (دریافتی یا پرداختی) این مشتری.
            "latest_transfers": all_transfers_by_date[:2],
            "ledger_entries": ledger_entries,
            "monthly_summary": monthly_summary,
            "summary": {
                "movement_count": len(matched),
                "inflow_rial": total([row for row in matched if row.get("direction") == "inflow" or row.get("source_kind") == "received_cheques"]),
                "outflow_rial": total([row for row in matched if row.get("direction") == "outflow" and row.get("source_kind") != "received_cheques"]),
                "received_cheque_count": len(received_cheques),
                "received_cheque_amount_rial": total(received_cheques),
                "received_cheque_overdue_count": len(overdue_received),
                "received_cheque_overdue_amount_rial": total(overdue_received),
                "received_cheque_today_count": len(today_received),
                "received_cheque_today_amount_rial": total(today_received),
                "received_cheque_future_count": len(future_received),
                "received_cheque_future_amount_rial": total(future_received),
                "received_cheque_returned_count": len(returned_received),
                "received_cheque_returned_amount_rial": total(returned_received),
                "issued_cheque_count": len(issued_cheques),
                "issued_cheque_amount_rial": total(issued_cheques),
                "received_transfer_count": len(received_transfers),
                "received_transfer_amount_rial": total(received_transfers),
                "paid_transfer_count": len(paid_transfers),
                "paid_transfer_amount_rial": total(paid_transfers),
            },
            "received_cheques": received_cheques,
            "returned_received_cheques": returned_received,
            "future_received_cheques": future_received,
            "issued_cheques": issued_cheques,
            "received_transfers": received_transfers,
            "paid_transfers": paid_transfers,
            "movements": matched,
        }
