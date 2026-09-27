from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.services.treasury_service import (
    _as_datetime,
    _as_jalali_date,
    _as_number,
    _currency_name,
    _engine,
    get_cheque_due_report,
    get_customer_cheque_settlement,
    get_received_cheques_by_status,
)
from app.services.received_cheque_current_status import (
    current_received_status_apply,
    received_cheque_open_predicate,
)


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _optional_non_negative_decimal(value: Any, field_name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = _decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid number") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return parsed


def _document_payload(row: Any) -> dict[str, Any]:
    return {
        "document_type": row["DocumentType"],
        "document_id": row["DocumentID"],
        "number": row["DocumentNumber"],
        "date": _as_datetime(row["DocumentDate"]),
        "date_jalali": _as_jalali_date(row["DocumentDate"]),
        "counterpart_ref": row["CounterPartRef"],
        "amount": _as_number(row["Amount"]),
        "item_type": row["ItemType"],
        "description": row["Description"],
    }


def _report_total_count(report: dict[str, Any]) -> int:
    return int(report.get("total_count", report["returned_count"]) or 0)


def _report_total_amount(report: dict[str, Any]) -> int | float:
    return report.get("total_amount", report["returned_total_amount"])


def _build_daily_briefing_payload(
    *,
    target_date: date,
    aggregate_rows: list[Any],
    largest_rows: list[Any],
    issued_upcoming: dict[str, Any],
    issued_overdue: dict[str, Any],
    received_upcoming: dict[str, Any],
    received_overdue: dict[str, Any],
) -> dict[str, Any]:
    aggregates = {
        row["DocumentType"]: {
            "count": int(row["DocumentCount"] or 0),
            "amount": _decimal(row["TotalAmount"]),
        }
        for row in aggregate_rows
    }
    receipt = aggregates.get("receipt", {"count": 0, "amount": Decimal("0")})
    payment = aggregates.get("payment", {"count": 0, "amount": Decimal("0")})
    net = receipt["amount"] - payment["amount"]
    alerts: list[dict[str, Any]] = []
    if _report_total_count(issued_overdue):
        alerts.append(
            {
                "severity": "critical",
                "code": "issued_cheques_overdue",
                "message": "چک صادرشده سررسیدگذشته وجود دارد.",
                "count": _report_total_count(issued_overdue),
                "amount": _report_total_amount(issued_overdue),
            }
        )
    if _report_total_count(received_overdue):
        alerts.append(
            {
                "severity": "high",
                "code": "received_cheques_overdue",
                "message": "چک دریافتی فعال سررسیدگذشته وجود دارد.",
                "count": _report_total_count(received_overdue),
                "amount": _report_total_amount(received_overdue),
            }
        )
    if _decimal(_report_total_amount(issued_upcoming)) > _decimal(
        _report_total_amount(received_upcoming)
    ):
        alerts.append(
            {
                "severity": "medium",
                "code": "near_term_nominal_outflow_gap",
                "message": "تعهد اسمی چک‌های صادرشده از چک‌های دریافتی نزدیک‌سررسید بیشتر است.",
                "amount": _as_number(
                    _decimal(_report_total_amount(issued_upcoming))
                    - _decimal(_report_total_amount(received_upcoming))
                ),
            }
        )

    return {
        "status": "success",
        "report_type": "daily_treasury_briefing",
        "date": target_date.isoformat(),
        "date_jalali": _as_jalali_date(target_date),
        "currency_name": settings.treasury_operational_currency_name,
        "today": {
            "receipt_count": receipt["count"],
            "receipt_total": _as_number(receipt["amount"]),
            "payment_count": payment["count"],
            "payment_total": _as_number(payment["amount"]),
            "document_net_movement": _as_number(net),
            "net_direction": "net_receipt" if net > 0 else "net_payment" if net < 0 else "balanced",
            "note": "خالص اسناد تأییدشده است و مانده بانکی محسوب نمی‌شود.",
        },
        "cheques": {
            "issued_upcoming": {
                "count": _report_total_count(issued_upcoming),
                "amount": _report_total_amount(issued_upcoming),
            },
            "issued_overdue": {
                "count": _report_total_count(issued_overdue),
                "amount": _report_total_amount(issued_overdue),
            },
            "received_upcoming": {
                "count": _report_total_count(received_upcoming),
                "amount": _report_total_amount(received_upcoming),
            },
            "received_overdue": {
                "count": _report_total_count(received_overdue),
                "amount": _report_total_amount(received_overdue),
            },
        },
        "largest_documents": [_document_payload(row) for row in largest_rows],
        "alerts": alerts,
        "alert_count": len(alerts),
    }


def get_daily_treasury_briefing(
    due_days: int = 7,
    engine: Engine | None = None,
) -> dict[str, Any]:
    safe_days = max(1, min(int(due_days), 60))
    selected_engine = _engine(engine)
    aggregate_query = text(
        """
        SELECT 'receipt' AS [DocumentType], COUNT_BIG(*) AS [DocumentCount],
               COALESCE(SUM([TotalOperationalCurrencyAmount]), 0) AS [TotalAmount]
        FROM RPA3.[Receipt]
        WHERE [ApproveState] = 3 AND CAST([Date] AS date) = CAST(GETDATE() AS date)
        UNION ALL
        SELECT 'payment', COUNT_BIG(*),
               COALESCE(SUM([TotalOperationalCurrencyAmount]), 0)
        FROM RPA3.[Payment]
        WHERE [ApproveState] = 3 AND CAST([Date] AS date) = CAST(GETDATE() AS date)
        """
    )
    largest_query = text(
        """
        SELECT TOP (10) * FROM (
            SELECT 'receipt' AS [DocumentType], [ReceiptID] AS [DocumentID],
                   [Number] AS [DocumentNumber], [Date] AS [DocumentDate],
                   [CounterPartRef], [TotalOperationalCurrencyAmount] AS [Amount],
                   [ItemType], [Description]
            FROM RPA3.[Receipt]
            WHERE [ApproveState] = 3 AND CAST([Date] AS date) = CAST(GETDATE() AS date)
            UNION ALL
            SELECT 'payment', [PaymentID], [Number], [Date], [CounterPartRef],
                   [TotalOperationalCurrencyAmount], [ItemType], [Description]
            FROM RPA3.[Payment]
            WHERE [ApproveState] = 3 AND CAST([Date] AS date) = CAST(GETDATE() AS date)
        ) AS documents
        ORDER BY [Amount] DESC, [DocumentID] DESC
        """
    )
    date_query = text("SELECT CAST(GETDATE() AS date) AS [ServerDate]")
    with selected_engine.connect() as connection:
        target_date = connection.execute(date_query).mappings().one()["ServerDate"]
        aggregate_rows = connection.execute(aggregate_query).mappings().all()
        largest_rows = connection.execute(largest_query).mappings().all()
    return _build_daily_briefing_payload(
        target_date=target_date,
        aggregate_rows=aggregate_rows,
        largest_rows=largest_rows,
        issued_upcoming=get_cheque_due_report("issued", safe_days, False, 500, selected_engine),
        issued_overdue=get_cheque_due_report("issued", safe_days, True, 500, selected_engine),
        received_upcoming=get_cheque_due_report("received", safe_days, False, 500, selected_engine),
        received_overdue=get_cheque_due_report("received", safe_days, True, 500, selected_engine),
    )


def _counterpart_concentration(cheques: list[dict[str, Any]], top: int = 5) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any], dict[str, Any]] = {}
    for cheque in cheques:
        key = (cheque.get("counterpart_ref"), cheque.get("counterpart_name"))
        item = grouped.setdefault(
            key,
            {
                "counterpart_ref": key[0],
                "counterpart_name": key[1],
                "count": 0,
                "amount": Decimal("0"),
            },
        )
        item["count"] += 1
        item["amount"] += _decimal(cheque.get("amount"))
    ranked = sorted(grouped.values(), key=lambda item: item["amount"], reverse=True)
    return [
        {**item, "amount": _as_number(item["amount"])}
        for item in ranked[:top]
    ]


def _query_upcoming_concentration(
    cheque_type: str,
    days: int,
    engine: Engine,
) -> list[dict[str, Any]]:
    configurations = {
        "issued": ("PayableNote", (11,)),
        "received": ("ReceivableNote", ()),
    }
    table_name, states = configurations[cheque_type]
    if cheque_type == "received":
        current_status_apply = current_received_status_apply("note", "current_status")
        active_state_predicate = received_cheque_open_predicate("note", "current_status")
    else:
        current_status_apply = ""
        state_sql = ", ".join(str(state) for state in states)
        active_state_predicate = f"AND note.[State] IN ({state_sql})"
    query = text(
        f"""
        SELECT TOP (5)
            note.[CounterPartRef],
            counterpart.[Title] AS [CounterPartName],
            COUNT_BIG(*) AS [ChequeCount],
            COALESCE(SUM(note.[Amount]), 0) AS [ChequeAmount]
        FROM RPA3.[{table_name}] AS note
        LEFT JOIN FIN3.[DL] AS counterpart
            ON counterpart.[DLID] = note.[CounterPartRef]
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          {active_state_predicate}
          AND note.[DueDate] IS NOT NULL
          AND CAST(note.[DueDate] AS date) >= CAST(GETDATE() AS date)
          AND CAST(note.[DueDate] AS date) <=
              DATEADD(day, :days, CAST(GETDATE() AS date))
        GROUP BY note.[CounterPartRef], counterpart.[Title]
        ORDER BY SUM(note.[Amount]) DESC, COUNT_BIG(*) DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"days": days}).mappings().all()
    return [
        {
            "counterpart_ref": row["CounterPartRef"],
            "counterpart_name": row["CounterPartName"],
            "count": int(row["ChequeCount"] or 0),
            "amount": _as_number(row["ChequeAmount"]),
        }
        for row in rows
    ]


def _build_cheque_risk_payload(
    *,
    days: int,
    issued_upcoming: dict[str, Any],
    issued_overdue: dict[str, Any],
    received_upcoming: dict[str, Any],
    received_overdue: dict[str, Any],
    protested: dict[str, Any],
    issued_concentration: list[dict[str, Any]] | None = None,
    received_concentration: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    issued_amount = _decimal(_report_total_amount(issued_upcoming))
    received_amount = _decimal(_report_total_amount(received_upcoming))
    nominal_gap = received_amount - issued_amount
    coverage = None
    if issued_amount > 0:
        coverage = _as_number(received_amount * Decimal("100") / issued_amount)
    alerts: list[dict[str, Any]] = []
    if _report_total_count(issued_overdue):
        alerts.append({"severity": "critical", "code": "overdue_issued", "count": _report_total_count(issued_overdue), "amount": _report_total_amount(issued_overdue)})
    if protested["returned_count"]:
        alerts.append({"severity": "high", "code": "protested_received", "count": protested["returned_count"], "amount": protested["returned_total_amount"]})
    if nominal_gap < 0:
        alerts.append({"severity": "medium", "code": "nominal_coverage_gap", "amount": _as_number(-nominal_gap)})
    return {
        "status": "success",
        "report_type": "cheque_risk_dashboard",
        "as_of_date": date.today().isoformat(),
        "as_of_date_jalali": _as_jalali_date(date.today()),
        "days": days,
        "currency_name": settings.treasury_operational_currency_name,
        "summary": {
            "issued_upcoming_count": _report_total_count(issued_upcoming),
            "issued_upcoming_total": _report_total_amount(issued_upcoming),
            "received_upcoming_count": _report_total_count(received_upcoming),
            "received_upcoming_total": _report_total_amount(received_upcoming),
            "issued_overdue_count": _report_total_count(issued_overdue),
            "issued_overdue_total": _report_total_amount(issued_overdue),
            "received_overdue_count": _report_total_count(received_overdue),
            "received_overdue_total": _report_total_amount(received_overdue),
            "protested_received_count": protested["returned_count"],
            "protested_received_total": protested["returned_total_amount"],
            "overdue_scope": f"previous_{days}_days",
            "protested_scope": "current_state_all_history",
            "nominal_near_term_gap": _as_number(nominal_gap),
            "nominal_coverage_percent": coverage,
            "coverage_note": "مقایسه اسمی چک‌هاست و تضمین وصول یا مانده بانکی نیست.",
        },
        "concentration_scope": "all_upcoming_rows",
        "issued_counterparty_concentration": (
            issued_concentration
            if issued_concentration is not None
            else _counterpart_concentration(issued_upcoming["cheques"])
        ),
        "received_counterparty_concentration": (
            received_concentration
            if received_concentration is not None
            else _counterpart_concentration(received_upcoming["cheques"])
        ),
        "detail_is_truncated": {
            "issued_upcoming": bool(issued_upcoming.get("is_truncated")),
            "received_upcoming": bool(received_upcoming.get("is_truncated")),
        },
        "alerts": alerts,
        "alert_count": len(alerts),
        "issued_upcoming": issued_upcoming["cheques"],
        "received_upcoming": received_upcoming["cheques"],
    }


def get_cheque_risk_dashboard(days: int = 60, engine: Engine | None = None) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 365))
    selected_engine = _engine(engine)
    return _build_cheque_risk_payload(
        days=safe_days,
        issued_upcoming=get_cheque_due_report("issued", safe_days, False, 500, selected_engine),
        issued_overdue=get_cheque_due_report("issued", safe_days, True, 500, selected_engine),
        received_upcoming=get_cheque_due_report("received", safe_days, False, 500, selected_engine),
        received_overdue=get_cheque_due_report("received", safe_days, True, 500, selected_engine),
        protested=get_received_cheques_by_status("protested", 500, selected_engine),
        issued_concentration=_query_upcoming_concentration(
            "issued", safe_days, selected_engine
        ),
        received_concentration=_query_upcoming_concentration(
            "received", safe_days, selected_engine
        ),
    )


def _anomaly_document(row: Any) -> dict[str, Any]:
    return {
        "document_type": row["DocumentType"],
        "document_id": row["DocumentID"],
        "number": row["DocumentNumber"],
        "date": _as_datetime(row["DocumentDate"]),
        "date_jalali": _as_jalali_date(row["DocumentDate"]),
        "counterpart_ref": row["CounterPartRef"],
        "amount": _as_number(row["Amount"]),
        "item_type": row["ItemType"],
        "description": row["Description"],
    }


def _detect_financial_anomalies(
    rows: list[Any],
    *,
    explicit_large_threshold: Decimal | None,
) -> dict[str, Any]:
    positive_amounts = [_decimal(row["Amount"]) for row in rows if _decimal(row["Amount"]) > 0]
    calculated_median = Decimal(str(median(positive_amounts))) if positive_amounts else Decimal("0")
    large_threshold = explicit_large_threshold or calculated_median * Decimal("5")
    findings: list[dict[str, Any]] = []

    duplicate_groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for row in rows:
        amount = _decimal(row["Amount"])
        key = (
            row["DocumentType"],
            str(row["DocumentDate"])[:10],
            row["CounterPartRef"],
            amount,
        )
        if amount > 0:
            duplicate_groups[key].append(row)
    for group in duplicate_groups.values():
        if len(group) > 1:
            findings.append(
                {
                    "finding_type": "possible_duplicate",
                    "severity": "high",
                    "reason": "جهت، تاریخ، طرف حساب و مبلغ یکسان است؛ تکراری‌بودن باید انسانی تأیید شود.",
                    "documents": [_anomaly_document(row) for row in group],
                }
            )

    if large_threshold > 0:
        for row in rows:
            if _decimal(row["Amount"]) >= large_threshold:
                findings.append(
                    {
                        "finding_type": "unusually_large_amount",
                        "severity": "medium",
                        "reason": "مبلغ از آستانه شفاف گزارش بزرگ‌تر یا مساوی است.",
                        "threshold": _as_number(large_threshold),
                        "documents": [_anomaly_document(row)],
                    }
                )

    for row in rows:
        if _decimal(row["Amount"]) > 0 and not str(row["Description"] or "").strip():
            findings.append(
                {
                    "finding_type": "missing_description",
                    "severity": "low",
                    "reason": "سند مالی مبلغ‌دار فاقد توضیح است.",
                    "documents": [_anomaly_document(row)],
                }
            )

    counts: dict[str, int] = defaultdict(int)
    for finding in findings:
        counts[finding["finding_type"]] += 1
    return {
        "median_amount": _as_number(calculated_median),
        "large_amount_threshold": _as_number(large_threshold),
        "rules": {
            "possible_duplicate": "جهت + تاریخ + طرف حساب + مبلغ یکسان",
            "unusually_large_amount": "آستانه دستی یا پنج برابر میانه مبالغ مثبت",
            "missing_description": "مبلغ مثبت و توضیح خالی",
        },
        "finding_counts": dict(counts),
        "findings": findings,
        "finding_count": len(findings),
    }


def get_financial_anomaly_report(
    days: int = 30,
    large_amount_threshold: Any = None,
    limit: int = 1000,
    engine: Engine | None = None,
) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 365))
    safe_limit = max(10, min(int(limit), 5000))
    threshold = _optional_non_negative_decimal(large_amount_threshold, "large_amount_threshold")
    query = text(
        f"""
        SELECT TOP ({safe_limit}) * FROM (
            SELECT 'receipt' AS [DocumentType], [ReceiptID] AS [DocumentID],
                   [Number] AS [DocumentNumber], [Date] AS [DocumentDate],
                   [CounterPartRef], [TotalOperationalCurrencyAmount] AS [Amount],
                   [ItemType], [Description]
            FROM RPA3.[Receipt]
            WHERE [ApproveState] = 3 AND [Date] >= DATEADD(day, -:days, GETDATE())
            UNION ALL
            SELECT 'payment', [PaymentID], [Number], [Date], [CounterPartRef],
                   [TotalOperationalCurrencyAmount], [ItemType], [Description]
            FROM RPA3.[Payment]
            WHERE [ApproveState] = 3 AND [Date] >= DATEADD(day, -:days, GETDATE())
        ) AS documents
        ORDER BY [DocumentDate] DESC, [DocumentID] DESC
        """
    )
    with _engine(engine).connect() as connection:
        rows = connection.execute(query, {"days": safe_days}).mappings().all()
    analysis = _detect_financial_anomalies(rows, explicit_large_threshold=threshold)
    return {
        "status": "success",
        "report_type": "financial_anomaly_candidates",
        "days": safe_days,
        "currency_name": settings.treasury_operational_currency_name,
        "review_required": True,
        "disclaimer": "این گزارش تخلف را اثبات نمی‌کند و فقط موارد نیازمند کنترل را نشان می‌دهد.",
        "scanned_document_count": len(rows),
        **analysis,
    }


def _build_payment_plan_payload(
    *,
    days: int,
    overdue_cheques: list[dict[str, Any]],
    upcoming_cheques: list[dict[str, Any]],
    available_cash: Decimal | None,
    total_count: int | None = None,
    total_amount: Decimal | None = None,
    total_overdue_count: int | None = None,
    is_truncated: bool = False,
) -> dict[str, Any]:
    all_cheques = [*overdue_cheques, *upcoming_cheques]
    all_cheques.sort(key=lambda item: (item.get("days_until_due") or 0, item.get("due_date") or ""))
    cumulative = Decimal("0")
    items: list[dict[str, Any]] = []
    daily_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for cheque in all_cheques:
        amount = _decimal(cheque.get("amount"))
        cumulative += amount
        due_days = cheque.get("days_until_due")
        priority = "critical" if due_days is not None and due_days < 0 else "high" if due_days is not None and due_days <= 3 else "medium" if due_days is not None and due_days <= 7 else "planned"
        funding_status = None
        if available_cash is not None:
            funding_status = "funded" if cumulative <= available_cash else "unfunded"
        items.append(
            {
                **cheque,
                "priority": priority,
                "cumulative_required": _as_number(cumulative),
                "funding_status": funding_status,
            }
        )
        daily_totals[str(cheque.get("due_date") or "unknown")[:10]] += amount
    total_required = total_amount if total_amount is not None else cumulative
    funding_gap = None
    if available_cash is not None:
        funding_gap = max(total_required - available_cash, Decimal("0"))
    return {
        "status": "success",
        "report_type": "payment_plan_advisory",
        "days": days,
        "currency_name": settings.treasury_operational_currency_name,
        "advisory_only": True,
        "bank_transaction_execution": False,
        "summary": {
            "cheque_count": total_count if total_count is not None else len(items),
            "overdue_count": (
                total_overdue_count
                if total_overdue_count is not None
                else len(overdue_cheques)
            ),
            "total_required": _as_number(total_required),
            "available_cash": _as_number(available_cash) if available_cash is not None else None,
            "funding_gap": _as_number(funding_gap) if funding_gap is not None else None,
        },
        "daily_requirements": [
            {"due_date": due_date, "amount": _as_number(amount)}
            for due_date, amount in sorted(daily_totals.items())
        ],
        "returned_item_count": len(items),
        "is_truncated": is_truncated,
        "items": items,
    }


def get_payment_plan(
    days: int = 30,
    available_cash: Any = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 365))
    parsed_cash = _optional_non_negative_decimal(available_cash, "available_cash")
    selected_engine = _engine(engine)
    overdue = get_cheque_due_report("issued", safe_days, True, 500, selected_engine)
    upcoming = get_cheque_due_report("issued", safe_days, False, 500, selected_engine)
    return _build_payment_plan_payload(
        days=safe_days,
        overdue_cheques=overdue["cheques"],
        upcoming_cheques=upcoming["cheques"],
        available_cash=parsed_cash,
        total_count=(
            _report_total_count(overdue)
            + _report_total_count(upcoming)
        ),
        total_amount=(
            _decimal(_report_total_amount(overdue))
            + _decimal(_report_total_amount(upcoming))
        ),
        total_overdue_count=_report_total_count(overdue),
        is_truncated=bool(
            overdue.get("is_truncated")
            or upcoming.get("is_truncated")
        ),
    )


def get_customer_financial_profile(
    counterpart_ref: int,
    days: int = 90,
    transaction_limit: int = 100,
    engine: Engine | None = None,
) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 730))
    safe_limit = max(1, min(int(transaction_limit), 500))
    selected_engine = _engine(engine)
    party_query = text(
        """
        SELECT TOP (1) [DLID] AS [CounterPartRef], [Code], [Title]
        FROM FIN3.[DL] WHERE [DLID] = :counterpart_ref
        """
    )
    accounts_query = text(
        """
        SELECT account.[AccountID], account.[Name], account.[Number],
               account.[DebitBalance], account.[CreditBalance], account.[Balance],
               account.[CurrencyRef], account.[Status]
        FROM FIN3.[Account] AS account
        INNER JOIN FIN3.[DL] AS dl ON dl.[ReferenceID] = account.[PartyRef]
        WHERE dl.[DLID] = :counterpart_ref
          AND account.[CurrencyRef] = :currency_ref
        ORDER BY account.[AccountID]
        """
    )
    transactions_query = text(
        f"""
        SELECT TOP ({safe_limit}) transaction_row.[TransactionID],
               transaction_row.[BookingDate], transaction_row.[Description],
               transaction_row.[EntryAmount], transaction_row.[GLAmount],
               transaction_row.[Effect], account.[AccountID], account.[Name] AS [AccountName]
        FROM FIN3.[Transaction] AS transaction_row
        INNER JOIN FIN3.[Account] AS account ON account.[AccountID] = transaction_row.[AccountRef]
        INNER JOIN FIN3.[DL] AS dl ON dl.[ReferenceID] = account.[PartyRef]
        WHERE dl.[DLID] = :counterpart_ref
          AND account.[CurrencyRef] = :currency_ref
          AND transaction_row.[Status] = 1
          AND transaction_row.[BookingDate] >= DATEADD(day, -:days, GETDATE())
        ORDER BY transaction_row.[BookingDate] DESC, transaction_row.[TransactionID] DESC
        """
    )
    parameters = {
        "counterpart_ref": int(counterpart_ref),
        "currency_ref": settings.treasury_operational_currency_ref,
        "days": safe_days,
    }
    with selected_engine.connect() as connection:
        party = connection.execute(party_query, parameters).mappings().first()
        if party is None:
            return {"status": "not_found", "message": "طرف حساب پیدا نشد.", "counterpart_ref": int(counterpart_ref)}
        accounts = connection.execute(accounts_query, parameters).mappings().all()
        transactions = connection.execute(transactions_query, parameters).mappings().all()
    settlement = get_customer_cheque_settlement(
        counterpart_ref=int(counterpart_ref),
        opening_debt=None,
        limit=1000,
        engine=selected_engine,
    )
    debit_total = sum((_decimal(row["EntryAmount"]) for row in transactions if row["Effect"] == 1), Decimal("0"))
    credit_total = sum((_decimal(row["EntryAmount"]) for row in transactions if row["Effect"] == 2), Decimal("0"))
    current_balance = sum((_decimal(row["Balance"]) for row in accounts), Decimal("0"))
    return {
        "status": "success",
        "report_type": "customer_financial_profile",
        "customer": {
            "counterpart_ref": party["CounterPartRef"],
            "code": party["Code"],
            "name": party["Title"],
        },
        "days": safe_days,
        "currency_name": settings.treasury_operational_currency_name,
        "account_summary": {
            "account_count": len(accounts),
            "stored_balance_total": _as_number(current_balance),
            "period_debit_total": _as_number(debit_total),
            "period_credit_total": _as_number(credit_total),
            "period_net": _as_number(debit_total - credit_total),
        },
        "accounts": [
            {
                "account_id": row["AccountID"],
                "name": row["Name"],
                "number": row["Number"],
                "debit": _as_number(row["DebitBalance"]),
                "credit": _as_number(row["CreditBalance"]),
                "balance": _as_number(row["Balance"]),
                "currency_ref": row["CurrencyRef"],
                "currency_name": _currency_name(row["CurrencyRef"]),
                "status": row["Status"],
            }
            for row in accounts
        ],
        "recent_transactions": [
            {
                "transaction_id": row["TransactionID"],
                "booking_date": _as_datetime(row["BookingDate"]),
                "booking_date_jalali": _as_jalali_date(row["BookingDate"]),
                "description": row["Description"],
                "amount": _as_number(row["EntryAmount"]),
                "gl_amount": _as_number(row["GLAmount"]),
                "side": "debit" if row["Effect"] == 1 else "credit" if row["Effect"] == 2 else "unknown",
                "account_id": row["AccountID"],
                "account_name": row["AccountName"],
            }
            for row in transactions
        ],
        "cheque_settlement": settlement,
        "limitations": {
            "open_invoice_data_available": False,
            "message": "اتصال فاکتورهای باز فروش هنوز به این گزارش اضافه نشده است.",
        },
    }


def get_treasury_executive_dashboard(
    days: int = 30,
    available_cash: Any = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    safe_days = max(1, min(int(days), 365))
    selected_engine = _engine(engine)
    return {
        "status": "success",
        "report_type": "treasury_executive_dashboard",
        "daily_briefing": get_daily_treasury_briefing(min(safe_days, 30), selected_engine),
        "cheque_risk": get_cheque_risk_dashboard(safe_days, selected_engine),
        "payment_plan": get_payment_plan(safe_days, available_cash, selected_engine),
        "anomaly_controls": get_financial_anomaly_report(safe_days, None, 1000, selected_engine),
        "notes": [
            "خروجی‌ها فقط خواندنی و تصمیم‌یار هستند.",
            "هیچ پرداخت یا ثبت سندی به‌صورت خودکار انجام نمی‌شود.",
            "موارد غیرعادی برای بررسی انسانی‌اند و اثبات تخلف نیستند.",
        ],
    }


def get_cashflow_scenarios(
    days: int = 30,
    opening_cash: Any = None,
    history_days: int = 90,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """پیش‌بینی توضیح‌پذیر بر پایه تاریخچه اسناد و سررسید چک‌ها.

    این خروجی مدل آماری آموزش‌دیده نیست؛ سه سناریوی شفاف برای تصمیم‌گیری است.
    """

    safe_days = max(1, min(int(days), 180))
    safe_history_days = max(30, min(int(history_days), 730))
    parsed_opening_cash = _optional_non_negative_decimal(opening_cash, "opening_cash")
    selected_engine = _engine(engine)
    history_query = text(
        """
        SELECT document_type,
               COALESCE(SUM(amount), 0) AS total_amount
        FROM (
            SELECT 'receipt' AS document_type,
                   [TotalOperationalCurrencyAmount] AS amount
            FROM RPA3.[Receipt]
            WHERE [ApproveState] = 3
              AND [Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
              AND [Date] < CAST(GETDATE() AS date)
            UNION ALL
            SELECT 'payment', [TotalOperationalCurrencyAmount]
            FROM RPA3.[Payment]
            WHERE [ApproveState] = 3
              AND [Date] >= DATEADD(day, -:history_days, CAST(GETDATE() AS date))
              AND [Date] < CAST(GETDATE() AS date)
        ) AS history
        GROUP BY document_type
        """
    )
    with selected_engine.connect() as connection:
        history_rows = connection.execute(
            history_query, {"history_days": safe_history_days}
        ).mappings().all()
    history = {
        row["document_type"]: _decimal(row["total_amount"])
        for row in history_rows
    }
    daily_receipt = history.get("receipt", Decimal("0")) / Decimal(safe_history_days)
    daily_payment = history.get("payment", Decimal("0")) / Decimal(safe_history_days)
    issued = get_cheque_due_report("issued", safe_days, False, 500, selected_engine)
    received = get_cheque_due_report("received", safe_days, False, 500, selected_engine)
    issued_total = _decimal(_report_total_amount(issued))
    received_total = _decimal(_report_total_amount(received))
    projected_operating_receipts = daily_receipt * Decimal(safe_days)
    projected_operating_payments = daily_payment * Decimal(safe_days)
    scenario_rules = {
        "optimistic": Decimal("0.95"),
        "probable": Decimal("0.75"),
        "stress": Decimal("0.50"),
    }
    scenarios: list[dict[str, Any]] = []
    for name, received_cheque_rate in scenario_rules.items():
        projected_inflow = projected_operating_receipts + received_total * received_cheque_rate
        projected_outflow = projected_operating_payments + issued_total
        net_change = projected_inflow - projected_outflow
        closing_cash = (
            parsed_opening_cash + net_change
            if parsed_opening_cash is not None
            else None
        )
        scenarios.append(
            {
                "scenario": name,
                "received_cheque_collection_rate": _as_number(
                    received_cheque_rate * Decimal("100")
                ),
                "projected_inflow": _as_number(projected_inflow),
                "projected_outflow": _as_number(projected_outflow),
                "projected_net_change": _as_number(net_change),
                "projected_closing_cash": (
                    _as_number(closing_cash) if closing_cash is not None else None
                ),
                "liquidity_warning": bool(closing_cash is not None and closing_cash < 0),
            }
        )
    return {
        "status": "success",
        "report_type": "explainable_cashflow_scenarios",
        "as_of_date": date.today().isoformat(),
        "as_of_date_jalali": _as_jalali_date(date.today()),
        "forecast_days": safe_days,
        "history_days": safe_history_days,
        "currency_name": settings.treasury_operational_currency_name,
        "opening_cash": (
            _as_number(parsed_opening_cash) if parsed_opening_cash is not None else None
        ),
        "inputs": {
            "historical_daily_approved_receipts": _as_number(daily_receipt),
            "historical_daily_approved_payments": _as_number(daily_payment),
            "issued_cheques_due_total": _as_number(issued_total),
            "received_cheques_due_total": _as_number(received_total),
        },
        "scenarios": scenarios,
        "method": "historical_daily_average_plus_weighted_due_cheques",
        "limitations": [
            "این خروجی سناریوی تصمیم‌یار است و مدل آماری آموزش‌دیده محسوب نمی‌شود.",
            "اسناد تاریخی ممکن است دقیقاً معادل جریان واقعی بانک نباشند.",
            "برای پیش‌بینی دقیق‌تر باید مانده روزانه بانک و سابقه وصول هر مشتری اضافه شود.",
        ],
    }
