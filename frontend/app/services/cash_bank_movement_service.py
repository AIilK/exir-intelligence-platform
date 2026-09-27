from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.sqlserver import get_sqlserver_engine


Period = Literal["today", "week", "month", "3m", "6m", "12m", "custom"]
Approval = Literal["approved", "pending", "all"]


def _number(value: Any) -> int | float:
    if value is None:
        return 0
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _jalali(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import jdatetime
        day = value.date() if isinstance(value, datetime) else value
        return jdatetime.date.fromgregorian(date=day).isoformat().replace("-", "/")
    except (ImportError, TypeError, ValueError):
        return None


def _range(period: Period, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = date.today()
    if period == "custom":
        if not date_from or not date_to:
            raise ValueError("برای بازه دلخواه، date_from و date_to الزامی است.")
        if date_from > date_to:
            raise ValueError("date_from نباید بعد از date_to باشد.")
        start, end = date_from, date_to
    elif period == "today":
        start = end = today
    elif period == "week":
        start, end = today - timedelta(days=6), today
    elif period == "month":
        start, end = today - timedelta(days=29), today
    else:
        months = {"3m": 3, "6m": 6, "12m": 12}[period]
        start, end = today - timedelta(days=months * 30 - 1), today
    if (end - start).days > 731:
        raise ValueError("حداکثر بازه مجاز ۷۳۱ روز است.")
    return start, end


def _approval_clause(status: Approval, alias: str) -> str:
    if status == "approved":
        return f"{alias}.[ApproveState] = 3"
    if status == "pending":
        return f"{alias}.[ApproveState] IN (1, 2)"
    return "1 = 1"


class CashBankMovementService:
    """Canonical cash/bank movement source; cheque and internal-transfer safe."""

    PETTY_CASH_MARKERS = ("تنخواه", "علی الحساب تنخواه", "علی‌الحساب تنخواه")
    COMPANY_TRANSFER_MARKERS = (
        "حواله شرکتی", "انتقال بین بانکی", "انتقال بین‌بانکی", "انتقال بانک به بانک",
        "انتقال بانک‌به‌بانک", "بانک به بانک", "بانک‌به‌بانک", "بابت انتقال",
        "جهت انتقال", "طرف حساب شرکتی", "شرکتی",
    )

    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_sqlserver_engine()

    @staticmethod
    def _base_union(approval: Approval) -> str:
        receipt_state = _approval_clause(approval, "h")
        payment_state = _approval_clause(approval, "h")
        return f"""
            SELECT N'cash_receipt' AS [MovementType], N'inflow' AS [Direction],
                   N'cash' AS [Channel], d.[ReceiptCashMoneyID] AS [MovementID],
                   h.[ReceiptID] AS [DocumentID], h.[Number] AS [DocumentNumber],
                   h.[Date] AS [DocumentDate], h.[ApproveState],
                   COALESCE(d.[CurrencyAmount], d.[Amount], 0) AS [AmountRial],
                   COALESCE(d.[CounterPartRef], h.[CounterPartRef]) AS [CounterPartRef],
                   d.[CashFlowFactorRef], NULL AS [BankAccountRef], h.[CashRef],
                   COALESCE(NULLIF(d.[Description], N''), h.[Description]) AS [Description]
            FROM RPA3.[ReceiptCashMoney] d
            INNER JOIN RPA3.[Receipt] h ON h.[ReceiptID] = d.[ReceiptRef]
            WHERE {receipt_state}

            UNION ALL
            SELECT N'bank_receipt', N'inflow', N'bank', d.[ReceiptDepositID],
                   h.[ReceiptID], h.[Number], h.[Date], h.[ApproveState],
                   COALESCE(d.[CurrencyAmount], d.[Amount], 0),
                   COALESCE(d.[CounterPartRef], h.[CounterPartRef]),
                   d.[CashFlowFactorRef], d.[BankAccountRef], NULL,
                   COALESCE(NULLIF(d.[Description], N''), h.[Description])
            FROM RPA3.[ReceiptDeposit] d
            INNER JOIN RPA3.[Receipt] h ON h.[ReceiptID] = d.[ReceiptRef]
            WHERE {receipt_state}

            UNION ALL
            SELECT N'cash_payment', N'outflow', N'cash', d.[PaymentCashMoneyID],
                   h.[PaymentID], h.[Number], h.[Date], h.[ApproveState],
                   COALESCE(d.[CurrencyAmount], d.[Amount], 0),
                   COALESCE(d.[CounterPartRef], h.[CounterPartRef]),
                   d.[CashFlowFactorRef], NULL, h.[CashRef],
                   COALESCE(NULLIF(d.[Description], N''), h.[Description])
            FROM RPA3.[PaymentCashMoney] d
            INNER JOIN RPA3.[Payment] h ON h.[PaymentID] = d.[PaymentRef]
            WHERE {payment_state}

            UNION ALL
            SELECT N'bank_payment', N'outflow', N'bank', d.[PaymentDepositID],
                   h.[PaymentID], h.[Number], h.[Date], h.[ApproveState],
                   COALESCE(d.[CurrencyAmount], d.[Amount], 0),
                   COALESCE(d.[CounterPartRef], h.[CounterPartRef]),
                   d.[CashFlowFactorRef], d.[BankAccountRef], NULL,
                   COALESCE(NULLIF(d.[Description], N''), h.[Description])
            FROM RPA3.[PaymentDeposit] d
            INNER JOIN RPA3.[Payment] h ON h.[PaymentID] = d.[PaymentRef]
            WHERE {payment_state}
        """

    def report(
        self,
        period: Period = "month",
        approval_status: Approval = "approved",
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 500,
        offset: int = 0,
        branch: str | None = None,
        source: Literal["all", "rahkaran", "karamad"] = "all",
    ) -> dict[str, Any]:
        if source not in ("all", "rahkaran", "karamad"):
            raise ValueError("منبع گزارش معتبر نیست")
        if source == "rahkaran":
            branch = None
        start, end = _range(period, date_from, date_to)
        limit, offset = max(1, min(int(limit), 5000)), max(0, int(offset))
        union = self._base_union(approval_status)
        params = {"date_from": start, "date_to_exclusive": end + timedelta(days=1), "limit": limit, "offset": offset}
        where = "[DocumentDate] >= :date_from AND [DocumentDate] < :date_to_exclusive"
        rows_sql = text(f"""
            WITH movements AS ({union})
            SELECT m.*, cp.[Code] AS [CounterPartCode], cp.[Title] AS [CounterPartName],
                   ba.[Number] AS [BankAccountNumber], ba.[InternationalNumber] AS [BankAccountIBAN]
            FROM movements m
            LEFT JOIN FIN3.[DL] cp ON cp.[DLID] = m.[CounterPartRef]
            LEFT JOIN RPA3.[BankAccount] ba ON ba.[BankAccountID] = m.[BankAccountRef]
            WHERE {where}
            ORDER BY m.[DocumentDate] DESC, m.[DocumentID] DESC, m.[MovementID] DESC
        """)
        rows = []
        if source != "karamad" and not branch:
            with self.engine.connect() as connection:
                rows = connection.execute(rows_sql, params).mappings().all()
        payloads = [self._movement_payload(row) for row in rows]
        operational_rows = [row for row in payloads if row["classification"] == "operational"]
        company_transfer_rows = [row for row in payloads if row["classification"] == "company_bank_transfer"]
        petty_cash_rows = [row for row in payloads if row["classification"] == "petty_cash"]

        # KarAmand is a separate manually refreshed source. Its four exports
        # overlap heavily, so the import service deduplicates them by
        # direction + transfer id before any total is added here.
        from app.services.karamad_manual_import_service import KaramadManualImportService
        karamad_service = KaramadManualImportService()
        karamad = karamad_service.actual_movements(start, end, branch=branch) if source != "rahkaran" else {"movements": [], "company_bank_transfers": [], "petty_cash_movements": []}
        karamad_operational = [self._karamad_payload(row) for row in karamad["movements"]]
        karamad_transfers = [self._karamad_payload(row) for row in karamad["company_bank_transfers"]]
        karamad_petty = [self._karamad_payload(row) for row in karamad["petty_cash_movements"]]

        def total(kind: str) -> int | float:
            return _number(sum(float(row["amount_rial"] or 0) for row in operational_rows if row["movement_type"] == kind))

        rahkaran_inflow = _number(sum(float(row["amount_rial"] or 0) for row in operational_rows if row["direction"] == "inflow"))
        rahkaran_outflow = _number(sum(float(row["amount_rial"] or 0) for row in operational_rows if row["direction"] == "outflow"))
        karamad_inflow = _number(sum(float(row["amount_rial"] or 0) for row in karamad_operational if row["direction"] == "inflow"))
        karamad_outflow = _number(sum(float(row["amount_rial"] or 0) for row in karamad_operational if row["direction"] == "outflow"))
        inflow = _number(float(rahkaran_inflow) + float(karamad_inflow))
        outflow = _number(float(rahkaran_outflow) + float(karamad_outflow))
        merged_operational = sorted(
            operational_rows + karamad_operational,
            key=lambda row: (row.get("document_date_jalali") or "", str(row.get("movement_id") or "")),
            reverse=True,
        )
        available_branches = KaramadManualImportService().summary().get("available_branches", [])
        if branch:
            # A selected branch is a KarAmand scope. Rahkaran has no comparable branch dimension,
            # so branch statistics and rows intentionally show only that KarAmand branch.
            operational_rows = []
            company_transfer_rows = []
            petty_cash_rows = []
            merged_operational = sorted(karamad_operational, key=lambda row: (row.get("document_date_jalali") or "", str(row.get("movement_id") or "")), reverse=True)
            inflow = karamad_inflow
            outflow = karamad_outflow
        # Classify the entire filtered population before pagination. Totals and
        # the daily chart must use the same population as the detail report.
        all_scoped = merged_operational + company_transfer_rows + karamad_transfers + petty_cash_rows + karamad_petty
        bank_paid = [r for r in all_scoped if r["movement_type"] == "bank_payment"]
        bank_paid_total = _number(sum(float(r["amount_rial"] or 0) for r in bank_paid))
        bank_paid_internal = _number(sum(float(r["amount_rial"] or 0) for r in bank_paid if r["classification"] == "company_bank_transfer"))
        daily_totals = {}
        for row in merged_operational:
            key = row.get("document_date_jalali") or row.get("document_date") or ""
            item = daily_totals.setdefault(key, {"date": row.get("document_date"), "date_jalali": row.get("document_date_jalali"), "inflow_rial": 0, "outflow_rial": 0})
            item[row["direction"] + "_rial"] += float(row["amount_rial"] or 0)
        operational_count = len(merged_operational)
        page = merged_operational[offset:offset + limit]
        return {
            "status": "success", "report_type": "cash_bank_movements",
            "filters": {"period": period, "approval_status": approval_status, "date_from": start.isoformat(), "date_to": end.isoformat(), "branch": branch, "source": source},
            "pagination": {"limit": limit, "offset": offset, "returned_count": len(page), "total_count": operational_count, "has_more": offset + len(page) < operational_count},
            "summary": {"inflow_rial": inflow, "outflow_rial": outflow, "net_rial": inflow - outflow,
                        "cash_receipt_rial": total("cash_receipt"), "bank_receipt_rial": _number(float(total("bank_receipt")) + float(karamad_inflow)),
                        "cash_payment_rial": total("cash_payment"), "bank_payment_rial": _number(float(total("bank_payment")) + float(karamad_outflow)),
                        "bank_payment_total_rial": bank_paid_total,
                        "bank_payment_internal_transfer_rial": bank_paid_internal,
                        "bank_payment_excluding_transfer_rial": bank_paid_total - bank_paid_internal,
                        "bank_payment_total_count": len(bank_paid),
                        "bank_payment_excluding_transfer_count": sum(r["classification"] != "company_bank_transfer" for r in bank_paid),
                        "rahkaran_inflow_rial": rahkaran_inflow, "rahkaran_outflow_rial": rahkaran_outflow,
                        "karamad_inflow_rial": karamad_inflow, "karamad_outflow_rial": karamad_outflow,
                        "karamad_operational_count": len(karamad_operational),
                        "selected_branch": branch, "available_branches": available_branches,
                        "company_bank_transfer_rial": _number(sum(float(row["amount_rial"] or 0) for row in company_transfer_rows + karamad_transfers)),
                        "petty_cash_rial": _number(sum(float(row["amount_rial"] or 0) for row in petty_cash_rows + karamad_petty)),
                        "source_note": "همهٔ جمع‌ها روی سبد یکپارچه محاسبه شده‌اند؛ ستون منبع فقط منشأ هر ردیف را نشان می‌دهد. انتقال داخلی و تنخواه حذف شده‌اند."},
            "movements": page,
            "company_bank_transfers": company_transfer_rows + karamad_transfers,
            "petty_cash_movements": petty_cash_rows + karamad_petty,
            "daily": [{**r, "net_rial": r["inflow_rial"] - r["outflow_rial"]} for _, r in sorted(daily_totals.items())],
            "accounting_rules": ["Only operational Receipt/Payment child cash and deposit rows are counted.", "KarAmand rows are historical executed movements and are deduplicated by direction + transfer id before being added to actual totals.", "Cheque forecast rows are excluded; the 75% collection policy applies only to open future cheques with a due date.", "Rows whose description contains بابت انتقال or another company-transfer marker are moved to bank-to-bank transfers; rows marked تنخواه are moved to petty cash and both have zero net company effect.", "SQL Server remains read-only; KarAmand state is stored locally."],
        }

    def _movement_payload(self, row: Any) -> dict[str, Any]:
        description = row["Description"] or ""
        counterpart_name = row["CounterPartName"] or ""
        source_text = f"{description} {counterpart_name}".casefold()
        has_transfer_purpose = bool(re.search(r"بابت\s*[:\-–—]?\s*انتقال", source_text))
        if any(marker.casefold() in source_text for marker in self.PETTY_CASH_MARKERS):
            classification, reason = "petty_cash", "متن شرح یا طرف حساب شامل «تنخواه» است"
        elif has_transfer_purpose or any(marker.casefold() in source_text for marker in self.COMPANY_TRANSFER_MARKERS):
            classification, reason = "company_bank_transfer", "متن شرح یا طرف حساب شامل نشانهٔ انتقال بانک‌به‌بانک است"
        else:
            classification, reason = "operational", "پرداخت یا دریافت عملیاتی"
        return {
            "movement_type": row["MovementType"], "direction": row["Direction"], "channel": row["Channel"],
            "movement_id": row["MovementID"], "document_id": row["DocumentID"], "document_number": row["DocumentNumber"],
            "document_date": _iso(row["DocumentDate"]), "document_date_jalali": _jalali(row["DocumentDate"]), "approve_state": row["ApproveState"],
            "amount_rial": _number(row["AmountRial"]), "counterpart_ref": row["CounterPartRef"], "counterpart_code": row["CounterPartCode"],
            "counterpart_name": counterpart_name, "cash_flow_factor_ref": row["CashFlowFactorRef"], "bank_account_ref": row["BankAccountRef"],
            "bank_account_number": row["BankAccountNumber"], "bank_account_iban": row["BankAccountIBAN"], "cash_ref": row["CashRef"], "description": description,
            "classification": classification, "classification_reason": reason, "source_system": "rahkaran",
        }

    @staticmethod
    def _karamad_payload(row: dict[str, Any]) -> dict[str, Any]:
        direction = row.get("direction") or "outflow"
        return {
            "movement_type": "bank_receipt" if direction == "inflow" else "bank_payment",
            "direction": direction, "channel": "bank", "movement_id": f"karamad:{direction}:{row.get('transfer_id')}",
            "document_id": None, "document_number": row.get("document_number") or row.get("transfer_number"),
            "document_date": None, "document_date_jalali": row.get("transfer_date_jalali") or row.get("registration_date_jalali"),
            "approve_state": 3, "amount_rial": _number(row.get("amount_rial")), "counterpart_ref": None,
            "counterpart_code": None, "counterpart_name": row.get("level4_name") or row.get("level5_name") or row.get("level6_name"),
            "cash_flow_factor_ref": None, "bank_account_ref": None, "bank_account_number": row.get("bank"),
            "bank_account_iban": None, "cash_ref": None, "description": row.get("purpose") or row.get("description"),
            "classification": row.get("classification"), "classification_reason": row.get("classification_reason"),
            "source_system": "karamad", "source_label": "کارآمد", "source_kind": row.get("source_kind"), "source_kinds": row.get("source_kinds"),
            "branch": row.get("branch"), "branch_name": row.get("branch"), "bank_name": row.get("bank"),
            "registration_date_jalali": row.get("registration_date_jalali"), "transfer_date_jalali": row.get("transfer_date_jalali"),
            "transfer_id": row.get("transfer_id"), "number": row.get("transfer_number"),
            "date_jalali": row.get("transfer_date_jalali") or row.get("registration_date_jalali"),
            "payment_amount_rial": _number(row.get("amount_rial")) if direction == "outflow" else 0,
            "receipt_amount_rial": _number(row.get("amount_rial")) if direction == "inflow" else 0,
            "company_net_effect_rial": 0 if row.get("classification") != "operational" else None,
        }

    def internal_transfers(self, period: Period = "month", date_from: date | None = None, date_to: date | None = None, limit: int = 500, offset: int = 0) -> dict[str, Any]:
        start, end = _range(period, date_from, date_to)
        limit, offset = max(1, min(int(limit), 5000)), max(0, int(offset))
        params = {"date_from": start, "date_to_exclusive": end + timedelta(days=1), "limit": limit, "offset": offset}
        union = """
            SELECT N'bank_transfer' AS [TransferType], t.[TransferID], t.[Number], t.[Date], t.[State], t.[Description],
                   d.[RowNumber] AS [RowNumber], d.[SourceBankAccountRef], d.[DestinationBankAccountRef],
                   NULL AS [SourceCashRef], d.[DestinationCashRef], d.[DestinationPettyCashRef],
                   COALESCE(d.[PaymentOperationalCurrencyAmount], d.[PaymentAmount], 0) AS [PaymentAmountRial],
                   COALESCE(d.[ReceiptOperationalCurrencyAmount], d.[ReceiptAmount], 0) AS [ReceiptAmountRial]
            FROM RPA3.[TransferDeposit] d INNER JOIN RPA3.[Transfer] t ON t.[TransferID]=d.[TransferRef]
            WHERE t.[State] IN (3,5)
            UNION ALL
            SELECT N'cash_transfer', t.[TransferID], t.[Number], t.[Date], t.[State], t.[Description],
                   d.[Number], NULL, d.[DestinationBankAccountRef], d.[SourceCashRef], d.[DestinationCashRef], d.[DestinationPettyCashRef],
                   COALESCE(d.[PaymentOperationalCurrencyAmount], d.[PaymentAmount], 0),
                   COALESCE(d.[ReceiptOperationalCurrencyAmount], d.[ReceiptAmount], 0)
            FROM RPA3.[TransferCashMoney] d INNER JOIN RPA3.[Transfer] t ON t.[TransferID]=d.[TransferRef]
            WHERE t.[State] IN (3,5)
        """
        where = "[Date] >= :date_from AND [Date] < :date_to_exclusive"
        count_sql = text(f"WITH transfers AS ({union}) SELECT COUNT_BIG(*) AS [TotalCount], COALESCE(SUM([PaymentAmountRial]),0) AS [TotalRial] FROM transfers WHERE {where}")
        rows_sql = text(f"WITH transfers AS ({union}) SELECT * FROM transfers WHERE {where} ORDER BY [Date] DESC,[TransferID] DESC OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY")
        with self.engine.connect() as connection:
            summary = connection.execute(count_sql, params).mappings().one()
            rows = connection.execute(rows_sql, params).mappings().all()
        return {"status": "success", "report_type": "internal_transfers", "filters": {"period": period, "date_from": start.isoformat(), "date_to": end.isoformat()},
                "pagination": {"limit": limit, "offset": offset, "returned_count": len(rows), "total_count": int(summary["TotalCount"] or 0), "has_more": offset + len(rows) < int(summary["TotalCount"] or 0)},
                "summary": {"transfer_amount_rial": _number(summary["TotalRial"]), "company_net_effect_rial": 0},
                "transfers": [{"transfer_type": r["TransferType"], "transfer_id": r["TransferID"], "number": r["Number"], "date": _iso(r["Date"]), "date_jalali": _jalali(r["Date"]), "state": r["State"], "description": r["Description"], "source_bank_account_ref": r["SourceBankAccountRef"], "destination_bank_account_ref": r["DestinationBankAccountRef"], "source_cash_ref": r["SourceCashRef"], "destination_cash_ref": r["DestinationCashRef"], "destination_petty_cash_ref": r["DestinationPettyCashRef"], "payment_amount_rial": _number(r["PaymentAmountRial"]), "receipt_amount_rial": _number(r["ReceiptAmountRial"]), "company_net_effect_rial": 0, "source_system": "rahkaran", "source_label": "راهکاران"} for r in rows]}

    def petty_cash_transfers(self, period: Period = "month", date_from: date | None = None, date_to: date | None = None, limit: int = 500, offset: int = 0) -> dict[str, Any]:
        """Transfers funded to petty cash. They are internal and never Cash Flow."""
        report = self.internal_transfers(period, date_from, date_to, limit=5000, offset=0)
        all_rows = [x for x in report.get("transfers", []) if x.get("destination_petty_cash_ref")]
        page = all_rows[offset:offset + limit]
        total = sum(float(x.get("payment_amount_rial") or 0) for x in all_rows)
        return {
            "status": "success", "report_type": "petty_cash_transfers",
            "filters": report.get("filters"),
            "pagination": {"limit": limit, "offset": offset, "returned_count": len(page), "total_count": len(all_rows), "has_more": offset + len(page) < len(all_rows)},
            "summary": {"funded_amount_rial": total, "cashflow_included": False, "company_net_effect_rial": 0},
            "transfers": page,
            "rule": "تنخواه انتقال داخلی است؛ نه دریافت و نه پرداخت عملیاتی و در Cash Flow وارد نمی‌شود.",
        }
