from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.sqlserver import get_sqlserver_engine
from app.services.payment_commitment_review_store import (
    PaymentCommitmentReviewStore,
)


CommitmentScope = Literal["future", "overdue", "all"]


def _number(value: Any) -> int | float:
    if value is None:
        return 0
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def _jalali(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import jdatetime

        day = value.date() if isinstance(value, datetime) else value
        return jdatetime.date.fromgregorian(date=day).isoformat().replace("-", "/")
    except (ImportError, TypeError, ValueError):
        return None


class PaymentCommitmentService:
    """Approved/draft payable-cheque orders that have not become real payments.

    PaymentDocumentItemType=26 is the verified Rahkaran relation between
    PaymentOrderPayableNote and PaymentPayableNote.  The anti-join prevents an
    executed order from being counted again beside the real PayableNote.
    """

    def __init__(
        self,
        engine: Engine | None = None,
        review_store: PaymentCommitmentReviewStore | None = None,
    ):
        self.engine = engine or get_sqlserver_engine()
        self.review_store = review_store or PaymentCommitmentReviewStore()

    @staticmethod
    def _base_where() -> str:
        return """
            popn.[NoteType] = 1
            AND popn.[NormalORGuarantee] = 1
            AND ISNULL(popn.[Description], N'') NOT LIKE N'%ضمانت%'
            AND ISNULL(popn.[Description], N'') NOT LIKE N'%تضمین%'
            AND ISNULL(popn.[Description], N'') NOT LIKE N'%حسن انجام%'
            AND NOT EXISTS (
                SELECT 1
                FROM RPA3.[PaymentOrderItemToPaymentItem] link
                INNER JOIN RPA3.[Payment] payment
                    ON payment.[PaymentID] = link.[PaymentRef]
                WHERE link.[PaymentOrderItemRef] = popn.[PaymentOrderPayableNoteID]
                  AND link.[PaymentDocumentItemType] = 26
                  AND payment.[ApproveState] = 3
            )
        """

    def report(
        self,
        *,
        horizon_days: int = 365,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, Any]:
        horizon_days = max(1, min(int(horizon_days), 730))
        limit, offset = max(1, min(int(limit), 5000)), max(0, int(offset))
        where = self._base_where()
        params = {"horizon_days": horizon_days, "limit": limit, "offset": offset}

        summary_sql = text(f"""
            SELECT
                COUNT(DISTINCT CASE WHEN po.[State] = 2 AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date))
                    THEN po.[PaymentOrderID] END) AS [FutureApprovedOrderCount],
                SUM(CASE WHEN po.[State] = 2 AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date)) THEN 1 ELSE 0 END)
                    AS [FutureApprovedInstallmentCount],
                SUM(CASE WHEN po.[State] = 2 AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date))
                    THEN popn.[Amount] ELSE 0 END) AS [FutureApprovedAmountRial],
                COUNT(DISTINCT CASE WHEN po.[State] = 1 AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date))
                    THEN po.[PaymentOrderID] END) AS [FutureDraftOrderCount],
                SUM(CASE WHEN po.[State] = 1 AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date)) THEN 1 ELSE 0 END)
                    AS [FutureDraftInstallmentCount],
                SUM(CASE WHEN po.[State] = 1 AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date))
                    THEN popn.[Amount] ELSE 0 END) AS [FutureDraftAmountRial],
                COUNT(DISTINCT CASE WHEN po.[State] = 2 AND popn.[DueDate] < CAST(GETDATE() AS date)
                    AND YEAR(popn.[DueDate]) = YEAR(GETDATE()) THEN po.[PaymentOrderID] END)
                    AS [CurrentYearOverdueOrderCount],
                SUM(CASE WHEN po.[State] = 2 AND popn.[DueDate] < CAST(GETDATE() AS date)
                    AND YEAR(popn.[DueDate]) = YEAR(GETDATE()) THEN 1 ELSE 0 END)
                    AS [CurrentYearOverdueInstallmentCount],
                SUM(CASE WHEN po.[State] = 2 AND popn.[DueDate] < CAST(GETDATE() AS date)
                    AND YEAR(popn.[DueDate]) = YEAR(GETDATE()) THEN popn.[Amount] ELSE 0 END)
                    AS [CurrentYearOverdueAmountRial],
                COUNT(DISTINCT CASE WHEN po.[State] = 2 AND popn.[DueDate] < DATEFROMPARTS(YEAR(GETDATE()),1,1)
                    THEN po.[PaymentOrderID] END) AS [HistoricalBacklogOrderCount],
                SUM(CASE WHEN po.[State] = 2 AND popn.[DueDate] < DATEFROMPARTS(YEAR(GETDATE()),1,1)
                    THEN 1 ELSE 0 END) AS [HistoricalBacklogInstallmentCount],
                SUM(CASE WHEN po.[State] = 2 AND popn.[DueDate] < DATEFROMPARTS(YEAR(GETDATE()),1,1)
                    THEN popn.[Amount] ELSE 0 END) AS [HistoricalBacklogAmountRial]
            FROM RPA3.[PaymentOrderPayableNote] popn
            INNER JOIN RPA3.[PaymentOrder] po ON po.[PaymentOrderID] = popn.[PaymentOrderRef]
            WHERE {where}
        """)
        rows_sql = text(f"""
            SELECT po.[PaymentOrderID], po.[Number] AS [PaymentOrderNumber], po.[Date] AS [OrderDate],
                   po.[ApproveDate], po.[State] AS [OrderState], popn.[PaymentOrderPayableNoteID] AS [InstallmentID],
                   popn.[DueDate], popn.[Amount] AS [AmountRial],
                   COALESCE(popn.[CounterPartRef], po.[CounterPartRef]) AS [CounterPartRef],
                   cp.[Code] AS [CounterPartCode], cp.[Title] AS [CounterPartName],
                   COALESCE(NULLIF(popn.[Description], N''), po.[Description]) AS [Description],
                   CASE
                     WHEN po.[State] = 2 AND popn.[DueDate] >= CAST(GETDATE() AS date) THEN N'approved_future'
                     WHEN po.[State] = 1 AND popn.[DueDate] >= CAST(GETDATE() AS date) THEN N'draft_future'
                     WHEN po.[State] = 2 AND YEAR(popn.[DueDate]) = YEAR(GETDATE()) THEN N'current_year_overdue'
                     WHEN po.[State] = 2 THEN N'historical_backlog'
                   END AS [CommitmentClass]
            FROM RPA3.[PaymentOrderPayableNote] popn
            INNER JOIN RPA3.[PaymentOrder] po ON po.[PaymentOrderID] = popn.[PaymentOrderRef]
            LEFT JOIN FIN3.[DL] cp ON cp.[DLID] = COALESCE(popn.[CounterPartRef], po.[CounterPartRef])
            WHERE {where}
              AND (
                (po.[State] IN (1,2) AND popn.[DueDate] >= CAST(GETDATE() AS date)
                    AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date)))
                OR (po.[State] = 2 AND popn.[DueDate] < CAST(GETDATE() AS date))
              )
            ORDER BY CASE WHEN popn.[DueDate] < CAST(GETDATE() AS date) THEN 0 ELSE 1 END,
                     popn.[DueDate], popn.[Amount] DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)
        daily_sql = text(f"""
            SELECT CAST(popn.[DueDate] AS date) AS [DueDate], SUM(popn.[Amount]) AS [AmountRial],
                   COUNT_BIG(*) AS [InstallmentCount], COUNT(DISTINCT po.[PaymentOrderID]) AS [OrderCount]
            FROM RPA3.[PaymentOrderPayableNote] popn
            INNER JOIN RPA3.[PaymentOrder] po ON po.[PaymentOrderID] = popn.[PaymentOrderRef]
            WHERE {where}
              AND po.[State] = 2
              AND popn.[DueDate] >= CAST(GETDATE() AS date)
              AND popn.[DueDate] < DATEADD(day, :horizon_days + 1, CAST(GETDATE() AS date))
            GROUP BY CAST(popn.[DueDate] AS date)
            ORDER BY [DueDate]
        """)
        overdue_review_sql = text(f"""
            SELECT popn.[PaymentOrderPayableNoteID] AS [InstallmentID],
                   po.[PaymentOrderID], popn.[Amount] AS [AmountRial]
            FROM RPA3.[PaymentOrderPayableNote] popn
            INNER JOIN RPA3.[PaymentOrder] po
                ON po.[PaymentOrderID] = popn.[PaymentOrderRef]
            WHERE {where}
              AND po.[State] = 2
              AND popn.[DueDate] < CAST(GETDATE() AS date)
              AND YEAR(popn.[DueDate]) = YEAR(GETDATE())
        """)
        with self.engine.connect() as connection:
            summary = dict(connection.execute(summary_sql, params).mappings().one())
            rows = connection.execute(rows_sql, params).mappings().all()
            daily = connection.execute(daily_sql, params).mappings().all()
            overdue_review_rows = connection.execute(
                overdue_review_sql, params
            ).mappings().all()

        reviews = self.review_store.all()
        review_counts = {
            "pending_review": 0,
            "paid": 0,
            "cancelled": 0,
            "still_due": 0,
        }
        review_amounts = {key: Decimal("0") for key in review_counts}
        still_due_order_ids: set[int] = set()
        for row in overdue_review_rows:
            stored = reviews.get(int(row["InstallmentID"]))
            decision = stored["decision"] if stored else "pending_review"
            if decision not in review_counts:
                decision = "pending_review"
            review_counts[decision] += 1
            review_amounts[decision] += Decimal(str(row["AmountRial"] or 0))
            if decision == "still_due":
                still_due_order_ids.add(int(row["PaymentOrderID"]))

        daily_map: dict[date, dict[str, Any]] = {}
        for row in daily:
            due_day = row["DueDate"]
            daily_map[due_day] = {
                "DueDate": due_day,
                "AmountRial": Decimal(str(row["AmountRial"] or 0)),
                "InstallmentCount": int(row["InstallmentCount"] or 0),
                "OrderCount": int(row["OrderCount"] or 0),
                "ReviewedOverdueAmountRial": Decimal("0"),
            }
        still_due_amount = review_amounts["still_due"]
        if still_due_amount:
            today_row = daily_map.setdefault(
                date.today(),
                {
                    "DueDate": date.today(),
                    "AmountRial": Decimal("0"),
                    "InstallmentCount": 0,
                    "OrderCount": 0,
                    "ReviewedOverdueAmountRial": Decimal("0"),
                },
            )
            today_row["AmountRial"] += still_due_amount
            today_row["InstallmentCount"] += review_counts["still_due"]
            today_row["OrderCount"] += len(still_due_order_ids)
            today_row["ReviewedOverdueAmountRial"] += still_due_amount
        effective_daily = [daily_map[key] for key in sorted(daily_map)]

        def group(prefix: str) -> dict[str, Any]:
            return {
                "payment_order_count": int(summary.get(f"{prefix}OrderCount") or 0),
                "installment_count": int(summary.get(f"{prefix}InstallmentCount") or 0),
                "amount_rial": _number(summary.get(f"{prefix}AmountRial")),
            }

        return {
            "status": "success",
            "report_type": "payment_order_commitments",
            "as_of_date": date.today().isoformat(),
            "horizon_days": horizon_days,
            "summary": {
                "approved_future": group("FutureApproved"),
                "draft_future": group("FutureDraft"),
                "current_year_overdue": group("CurrentYearOverdue"),
                "historical_backlog": group("HistoricalBacklog"),
            },
            "pagination": {"limit": limit, "offset": offset, "returned_count": len(rows)},
            "commitments": [{
                "commitment_class": row["CommitmentClass"],
                "payment_order_id": row["PaymentOrderID"],
                "payment_order_number": row["PaymentOrderNumber"],
                "order_date": _iso(row["OrderDate"]),
                "approve_date": _iso(row["ApproveDate"]),
                "order_state": row["OrderState"],
                "installment_id": row["InstallmentID"],
                "due_date": _iso(row["DueDate"]),
                "due_date_jalali": _jalali(row["DueDate"]),
                "amount_rial": _number(row["AmountRial"]),
                "counterpart_ref": row["CounterPartRef"],
                "counterpart_code": row["CounterPartCode"],
                "counterpart_name": row["CounterPartName"],
                "description": row["Description"],
                "review_decision": (
                    (reviews.get(int(row["InstallmentID"])) or {}).get(
                        "decision", "pending_review"
                    )
                    if row["CommitmentClass"] == "current_year_overdue"
                    else None
                ),
                "review_note": (
                    (reviews.get(int(row["InstallmentID"])) or {}).get("note")
                    if row["CommitmentClass"] == "current_year_overdue"
                    else None
                ),
                "reviewed_at": (
                    (reviews.get(int(row["InstallmentID"])) or {}).get("updated_at")
                    if row["CommitmentClass"] == "current_year_overdue"
                    else None
                ),
                "cashflow_included": (
                    (reviews.get(int(row["InstallmentID"])) or {}).get("decision")
                    == "still_due"
                    if row["CommitmentClass"] == "current_year_overdue"
                    else row["CommitmentClass"] == "approved_future"
                ),
            } for row in rows],
            "manual_review_summary": {
                "counts": review_counts,
                "amounts_rial": {
                    key: _number(value) for key, value in review_amounts.items()
                },
                "cashflow_included_count": review_counts["still_due"],
                "cashflow_included_payment_order_count": len(still_due_order_ids),
                "cashflow_included_amount_rial": _number(still_due_amount),
                "rule": "Only manually confirmed still_due overdue installments are added as due today.",
            },
            "approved_future_daily": [{
                "due_date": _iso(row["DueDate"]),
                "due_date_jalali": _jalali(row["DueDate"]),
                "amount_rial": _number(row["AmountRial"]),
                "installment_count": int(row["InstallmentCount"] or 0),
                "payment_order_count": int(row["OrderCount"] or 0),
                "reviewed_overdue_amount_rial": _number(
                    row.get("ReviewedOverdueAmountRial") or 0
                ),
            } for row in effective_daily],
            "cashflow_rules": {
                "base_forecast": "Only approved_future is included.",
                "conservative_scenario": "draft_future is shown separately and is not in the base forecast.",
                "overdue": "Current-year overdue items stay excluded until treasury marks them still_due.",
                "historical_backlog": "Excluded from forecast.",
                "double_count_protection": "Executed Type 26 links to approved Payment are excluded.",
                "guarantee_cheques_excluded": True,
            },
        }

    def set_review_decision(
        self,
        *,
        installment_id: int,
        payment_order_id: int,
        decision: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        where = self._base_where()
        validation_sql = text(f"""
            SELECT TOP (1) popn.[PaymentOrderPayableNoteID] AS [InstallmentID],
                   po.[PaymentOrderID]
            FROM RPA3.[PaymentOrderPayableNote] popn
            INNER JOIN RPA3.[PaymentOrder] po
                ON po.[PaymentOrderID] = popn.[PaymentOrderRef]
            WHERE {where}
              AND popn.[PaymentOrderPayableNoteID] = :installment_id
              AND po.[PaymentOrderID] = :payment_order_id
              AND po.[State] = 2
              AND popn.[DueDate] < CAST(GETDATE() AS date)
              AND YEAR(popn.[DueDate]) = YEAR(GETDATE())
        """)
        with self.engine.connect() as connection:
            row = connection.execute(
                validation_sql,
                {
                    "installment_id": int(installment_id),
                    "payment_order_id": int(payment_order_id),
                },
            ).mappings().first()
        if row is None:
            raise LookupError(
                "قسط معوق سال جاری با این شناسه و دستور پرداخت پیدا نشد."
            )
        return self.review_store.set(
            installment_id=installment_id,
            payment_order_id=payment_order_id,
            decision=decision,
            note=note,
        )

    def approved_future_daily(self, horizon_days: int) -> dict[date, float]:
        report = self.report(horizon_days=horizon_days, limit=1)
        return {
            date.fromisoformat(row["due_date"][:10]): float(row["amount_rial"] or 0)
            for row in report.get("approved_future_daily") or []
        }
