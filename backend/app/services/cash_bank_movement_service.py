from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
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
    ) -> dict[str, Any]:
        start, end = _range(period, date_from, date_to)
        limit, offset = max(1, min(int(limit), 5000)), max(0, int(offset))
        union = self._base_union(approval_status)
        params = {"date_from": start, "date_to_exclusive": end + timedelta(days=1), "limit": limit, "offset": offset}
        where = "[DocumentDate] >= :date_from AND [DocumentDate] < :date_to_exclusive"
        summary_sql = text(f"""
            WITH movements AS ({union})
            SELECT
                COUNT_BIG(*) AS [TotalCount],
                SUM(CASE WHEN [Direction]=N'inflow' THEN [AmountRial] ELSE 0 END) AS [InflowRial],
                SUM(CASE WHEN [Direction]=N'outflow' THEN [AmountRial] ELSE 0 END) AS [OutflowRial],
                SUM(CASE WHEN [MovementType]=N'cash_receipt' THEN [AmountRial] ELSE 0 END) AS [CashReceiptRial],
                SUM(CASE WHEN [MovementType]=N'bank_receipt' THEN [AmountRial] ELSE 0 END) AS [BankReceiptRial],
                SUM(CASE WHEN [MovementType]=N'cash_payment' THEN [AmountRial] ELSE 0 END) AS [CashPaymentRial],
                SUM(CASE WHEN [MovementType]=N'bank_payment' THEN [AmountRial] ELSE 0 END) AS [BankPaymentRial]
            FROM movements WHERE {where}
        """)
        rows_sql = text(f"""
            WITH movements AS ({union})
            SELECT m.*, cp.[Code] AS [CounterPartCode], cp.[Title] AS [CounterPartName],
                   ba.[Number] AS [BankAccountNumber], ba.[InternationalNumber] AS [BankAccountIBAN]
            FROM movements m
            LEFT JOIN FIN3.[DL] cp ON cp.[DLID] = m.[CounterPartRef]
            LEFT JOIN RPA3.[BankAccount] ba ON ba.[BankAccountID] = m.[BankAccountRef]
            WHERE {where}
            ORDER BY m.[DocumentDate] DESC, m.[DocumentID] DESC, m.[MovementID] DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)
        daily_sql = text(f"""
            WITH movements AS ({union})
            SELECT CAST([DocumentDate] AS date) AS [MovementDate],
                   SUM(CASE WHEN [Direction]=N'inflow' THEN [AmountRial] ELSE 0 END) AS [InflowRial],
                   SUM(CASE WHEN [Direction]=N'outflow' THEN [AmountRial] ELSE 0 END) AS [OutflowRial]
            FROM movements WHERE {where}
            GROUP BY CAST([DocumentDate] AS date) ORDER BY [MovementDate]
        """)
        with self.engine.connect() as connection:
            summary = dict(connection.execute(summary_sql, params).mappings().one())
            rows = connection.execute(rows_sql, params).mappings().all()
            daily = connection.execute(daily_sql, params).mappings().all()
        inflow = _number(summary.get("InflowRial"))
        outflow = _number(summary.get("OutflowRial"))
        return {
            "status": "success", "report_type": "cash_bank_movements",
            "filters": {"period": period, "approval_status": approval_status, "date_from": start.isoformat(), "date_to": end.isoformat()},
            "pagination": {"limit": limit, "offset": offset, "returned_count": len(rows), "total_count": int(summary.get("TotalCount") or 0), "has_more": offset + len(rows) < int(summary.get("TotalCount") or 0)},
            "summary": {"inflow_rial": inflow, "outflow_rial": outflow, "net_rial": inflow - outflow,
                        "cash_receipt_rial": _number(summary.get("CashReceiptRial")), "bank_receipt_rial": _number(summary.get("BankReceiptRial")),
                        "cash_payment_rial": _number(summary.get("CashPaymentRial")), "bank_payment_rial": _number(summary.get("BankPaymentRial"))},
            "movements": [{
                "movement_type": r["MovementType"], "direction": r["Direction"], "channel": r["Channel"],
                "movement_id": r["MovementID"], "document_id": r["DocumentID"], "document_number": r["DocumentNumber"],
                "document_date": _iso(r["DocumentDate"]), "document_date_jalali": _jalali(r["DocumentDate"]), "approve_state": r["ApproveState"],
                "amount_rial": _number(r["AmountRial"]), "counterpart_ref": r["CounterPartRef"], "counterpart_code": r["CounterPartCode"],
                "counterpart_name": r["CounterPartName"], "cash_flow_factor_ref": r["CashFlowFactorRef"], "bank_account_ref": r["BankAccountRef"],
                "bank_account_number": r["BankAccountNumber"], "bank_account_iban": r["BankAccountIBAN"], "cash_ref": r["CashRef"], "description": r["Description"],
            } for r in rows],
            "daily": [{"date": _iso(r["MovementDate"]), "date_jalali": _jalali(r["MovementDate"]), "inflow_rial": _number(r["InflowRial"]), "outflow_rial": _number(r["OutflowRial"]), "net_rial": _number(r["InflowRial"]) - _number(r["OutflowRial"])} for r in daily],
            "accounting_rules": ["Only Receipt/Payment child cash and deposit rows are counted.", "Cheque rows are excluded.", "Internal transfers are excluded from company net cash flow."],
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
                "transfers": [{"transfer_type": r["TransferType"], "transfer_id": r["TransferID"], "number": r["Number"], "date": _iso(r["Date"]), "date_jalali": _jalali(r["Date"]), "state": r["State"], "description": r["Description"], "source_bank_account_ref": r["SourceBankAccountRef"], "destination_bank_account_ref": r["DestinationBankAccountRef"], "source_cash_ref": r["SourceCashRef"], "destination_cash_ref": r["DestinationCashRef"], "destination_petty_cash_ref": r["DestinationPettyCashRef"], "payment_amount_rial": _number(r["PaymentAmountRial"]), "receipt_amount_rial": _number(r["ReceiptAmountRial"]), "company_net_effect_rial": 0} for r in rows]}
