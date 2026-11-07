from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any
import unicodedata

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.sqlserver import get_sqlserver_engine
from app.utils.jalali import format_jalali_date, parse_jalali_date
from app.services.bank_statement_parser import (  # noqa: F401 — moved to bank_statement_parser.py, re-exported for existing imports
    MAX_DATA_ROWS,
    MAX_FILE_SIZE,
    ReconciliationInputError,
    _BANK_NAME_HINTS,
    _COLUMN_ALIASES,
    _PERSIAN_DIGITS,
    _PERSIAN_TEXT,
    _StatementHTMLTableParser,
    _as_text,
    _clean_mellat_table_rows,
    _decode_html,
    _detect_header_row,
    _detect_statement_bank_name,
    _extract_statement_metadata,
    _header_matches_semantic,
    _normalize_text,
    _parse_amount,
    _parse_date,
    _read_csv,
    _read_html_statement,
    _read_pdf_statement,
    _read_xls,
    _read_xlsx,
    _resolve_column,
    parse_bank_statement,
)
from app.services.bank_reconciliation_matching import (  # noqa: F401 — moved to bank_reconciliation_matching.py, re-exported for existing imports
    _BANK_CHEQUE_SERIAL_PATTERN,
    _aggregate_fee_documents,
    _bank_cheque_serials,
    _bank_identity_text,
    _bank_row_fingerprint,
    _build_batch_match_result,
    _candidate_score,
    _cheque_serial_contradicts,
    _cheque_serial_matches,
    _cheque_serial_token_matches,
    _closest_day_difference,
    _combine_fee_documents,
    _description_similarity,
    _document_lists_bank_serial,
    _is_bank_cheque_event,
    _is_bank_issued_cheque_event,
    _is_fee_text,
    _is_generic_bank_cheque_text,
    _is_issued_cheque_term_change,
    _is_received_cheque_collection_transaction,
    _is_reversal_text,
    _match_bank_reversal_pairs,
    _match_bank_rows,
    _match_daily_fee_groups,
    _match_exact_date_amount_groups,
    _match_tolerance_amount_components,
    _perfect_candidate_assignment,
    _reference_matches,
    _reversal_base_text,
    _review_candidate_score,
    _serialize_transaction,
    _transaction_cheque_serials,
    _transaction_date_candidates,
    _transaction_type_is_compatible,
)


def _derive_statement_account_core(
    account_number: str,
    bank_name: str,
) -> str:
    normalized = re.sub(r"\D", "", account_number)
    if (
        bank_name == "تجارت"
        and len(normalized) == 13
        and normalized.startswith("010")
    ):
        return normalized[3:-1]
    return ""


_FEE_KINDS = (
    ("ساتنا", "کارمزد ساتنا"),
    ("پایا", "کارمزد پایا"),
    ("دستور پرداخت سمت متعهد", "کارمزد پل (دستور پرداخت)"),
    ("واگذاری", "کارمزد واگذاری چک"),
)


def _fee_kind(description: Any) -> str:
    normalized = _normalize_text(description)
    for marker, label in _FEE_KINDS:
        if marker in normalized:
            return label
    return "سایر کارمزد بانکی"


def _attach_fee_details(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Tag each bank fee with its kind and the transfer it was charged for.

    بانک کارمزد پایا/پل/ساتنا را بلافاصله کنار گردش اصلی و با همان تاریخ و
    ساعت ثبت می‌کند؛ کارمزد واگذاری چک هنگام تحویل چک به بانک کسر می‌شود و
    گردش اصلی در صورت‌حساب ندارد.
    """

    for result in results:
        result.setdefault("is_fee", False)
        result.setdefault("fee_amount", 0.0)
        result.setdefault("fee_row_numbers", [])

    by_kind: dict[str, dict[str, Any]] = {}
    for index, result in enumerate(results):
        if result.get("direction") != "withdrawal" or not _is_fee_text(
            result.get("description")
        ):
            continue
        kind = _fee_kind(result.get("description"))
        result["is_fee"] = True
        result["fee_kind"] = kind
        if result.get("business_status") == "reversed":
            result["fee_note"] = "کارمزد توسط بانک برگشت خورده است"
            continue

        summary = by_kind.setdefault(
            kind,
            {"kind": kind, "count": 0, "amount": 0.0, "posted_count": 0},
        )
        summary["count"] += 1
        summary["amount"] += float(result["amount"])
        if result.get("business_status") == "posted":
            summary["posted_count"] += 1

        parent = None
        if result.get("time"):
            for offset in (1, -1, 2, -2, 3, -3):
                neighbour_index = index - offset
                if not 0 <= neighbour_index < len(results):
                    continue
                neighbour = results[neighbour_index]
                if (
                    neighbour.get("bank_date") == result.get("bank_date")
                    and neighbour.get("time") == result.get("time")
                    and not _is_fee_text(neighbour.get("description"))
                    and not _is_reversal_text(neighbour.get("description"))
                ):
                    parent = neighbour
                    break
        if parent is None:
            result["fee_parent_row_number"] = None
            if kind == "کارمزد واگذاری چک":
                result["fee_note"] = "کارمزد تحویل هر برگ چک به بانک (گردش اصلی در صورت‌حساب ندارد)"
            continue
        result["fee_parent_row_number"] = parent["row_number"]
        result["fee_parent_amount"] = parent["amount"]
        result["fee_parent_description"] = parent.get("description", "")
        result["fee_rate_percent"] = (
            round(float(result["amount"]) / float(parent["amount"]) * 100, 4)
            if parent.get("amount")
            else None
        )
        parent["fee_amount"] = float(parent.get("fee_amount") or 0) + float(
            result["amount"]
        )
        parent["fee_row_numbers"].append(result["row_number"])
        parent["related_fee_kind"] = kind

    return {
        "by_kind": sorted(by_kind.values(), key=lambda item: -item["amount"]),
        "total_count": sum(item["count"] for item in by_kind.values()),
        "total_amount": sum(item["amount"] for item in by_kind.values()),
    }


def _load_book_ledger(
    connection: Any,
    bank_account: Any,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """GL lines of the bank account's level-4 DL for the statement fiscal year."""

    account_digits = re.sub(r"\D", "", _as_text(bank_account["Number"]))
    dl_rows = connection.execute(
        text(
            """
            SELECT DLID, Code, Title
            FROM FIN3.DL
            WHERE ReferenceID = :bank_account_id
            """
        ),
        {"bank_account_id": bank_account["BankAccountID"]},
    ).mappings().all()
    dl_row = next(
        (
            row
            for row in dl_rows
            if account_digits
            and account_digits in re.sub(r"\D", "", _as_text(row["Title"]))
        ),
        None,
    )
    if dl_row is None:
        return {
            "available": False,
            "message": "تفصیلی حساب بانک در راهکاران با شماره حساب پیدا نشد.",
        }
    lines = connection.execute(
        text(
            """
            SELECT
                v.Date AS VoucherDate,
                v.Number AS VoucherNumber,
                vi.RowNumber,
                ISNULL(vi.Debit, 0) AS Debit,
                ISNULL(vi.Credit, 0) AS Credit,
                vi.Description
            FROM FIN3.VoucherItem vi
            INNER JOIN FIN3.Voucher v
                ON v.VoucherID = vi.VoucherRef
            WHERE vi.DLLevel4 = :dl_code
              AND v.FiscalYearRef IN (
                  SELECT DISTINCT FiscalYearRef
                  FROM FIN3.Voucher
                  WHERE Date >= :start_date AND Date < :end_date
              )
              AND v.Date < :end_date
            ORDER BY v.Date, v.Number, vi.RowNumber
            """
        ),
        {
            "dl_code": dl_row["Code"],
            "start_date": start_date,
            "end_date": end_date,
        },
    ).mappings().all()
    running = Decimal("0")
    ledger_lines = []
    for line in lines:
        net = Decimal(str(line["Debit"] or 0)) - Decimal(str(line["Credit"] or 0))
        running += net
        voucher_date = line["VoucherDate"]
        if isinstance(voucher_date, datetime):
            voucher_date = voucher_date.date()
        ledger_lines.append(
            {
                "date": voucher_date,
                "voucher_number": _as_text(line["VoucherNumber"]),
                "net": net,
                "balance": running,
            }
        )
    return {
        "available": True,
        "dl_code": _as_text(dl_row["Code"]),
        "dl_title": _as_text(dl_row["Title"]),
        "lines": ledger_lines,
    }


def _side_label(difference: float) -> str:
    """Which side carries the balance difference (difference = bank − book)."""
    if abs(difference) <= 0.01:
        return ""
    return "مانده بانک بیشتر از راهکاران" if difference > 0 else "مانده راهکاران بیشتر از بانک"


def _explain_balance_differences(
    daily: list[dict[str, Any]],
    results: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    used_lines: set[int],
) -> None:
    """For each mismatched day: which side is higher, and which document makes the gap.

    The day difference is cumulative, so the documents behind a day are the ones whose effect
    equals the change in difference since the previous day: a bank row with no Rahkaran voucher
    (deposit +amount, withdrawal −amount) or a Rahkaran ledger line with no bank row (−net).
    The gap is cumulative, so each day lists every document found since the last balanced day.
    """

    previous_difference = 0.0
    open_documents: list[str] = []
    for item in daily:
        difference = item["difference"]
        item["difference_side"] = _side_label(difference)
        item["difference_documents"] = ""
        item["difference_basis"] = ""
        if item["matched"]:
            previous_difference, open_documents = difference, []
            continue
        delta = round(difference - previous_difference, 2)
        previous_difference = difference
        item["difference_change"] = delta
        if abs(delta) <= 0.01:
            item["difference_documents"] = " | ".join(open_documents)
            item["difference_basis"] = "اختلاف از روزهای قبل مانده است"
            continue

        day = date.fromisoformat(item["date"])
        candidates: list[tuple[float, str]] = []
        for result in results:
            if result.get("bank_date") != item["date"] or result.get("business_status") != "unposted":
                continue
            amount = float(result.get("amount") or 0)
            signed = amount if result.get("direction") == "deposit" else -amount
            label = "واریز" if signed > 0 else "برداشت"
            reference = result.get("bank_document_number") or result.get("reference") or ""
            candidates.append((
                signed,
                f"بانک: ردیف {result.get('row_number')} {label} {abs(amount):,.0f}"
                + (f" (سند بانک {reference})" if reference else "")
                + " — سند راهکاران ندارد",
            ))
        for position, line in enumerate(lines):
            if line["date"] != day or position in used_lines:
                continue
            net = float(line["net"])
            candidates.append((
                -net,
                f"راهکاران: سند {line['voucher_number']} "
                f"{'بدهکار' if net > 0 else 'بستانکار'} {abs(net):,.0f} — در بانک نیامده",
            ))

        exact = [text for value, text in candidates if abs(value - delta) <= 0.01]
        if exact:
            documents, basis = exact[:1], "مبلغ سند دقیقاً برابر اختلاف"
        elif candidates and abs(sum(value for value, _ in candidates) - delta) <= 0.01:
            documents, basis = [text for _, text in candidates], "جمع این اسناد برابر اختلاف"
        elif candidates:
            documents, basis = [text for _, text in candidates], "اسناد احتمالی همان روز (جمعشان با اختلاف برابر نیست)"
        else:
            documents, basis = [], "سند مشخصی در همان روز پیدا نشد؛ اختلاف از تاریخ یا مبلغ سند در روز دیگر است"
        open_documents.extend(f"{item['date_jalali']} {text}" for text in documents)
        item["difference_documents"] = " | ".join(open_documents)
        item["difference_basis"] = basis

    by_date = {item["date"]: item for item in daily}
    for result in results:
        item = by_date.get(result.get("bank_date"))
        if item and not item["matched"]:
            result["day_balance_side"] = item["difference_side"]
            result["day_balance_documents"] = item["difference_documents"]


def _attach_balances(
    results: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Bank vs Rahkaran book balance, per day and through each matched document."""

    if not ledger.get("available"):
        return {
            "available": False,
            "message": ledger.get("message", ""),
        }
    lines: list[dict[str, Any]] = ledger["lines"]
    line_dates = [line["date"] for line in lines]

    def book_balance_at_end_of(day: date) -> Decimal:
        position = bisect_right(line_dates, day) - 1
        return lines[position]["balance"] if position >= 0 else Decimal("0")

    ascending = (
        not results
        or results[0]["bank_date"] <= results[-1]["bank_date"]
    )
    bank_end_of_day: dict[str, float] = {}
    for result in results if ascending else reversed(results):
        if result.get("balance") is not None:
            bank_end_of_day[result["bank_date"]] = result["balance"]

    daily = []
    for bank_day, bank_balance in sorted(bank_end_of_day.items()):
        book_balance = book_balance_at_end_of(date.fromisoformat(bank_day))
        difference = Decimal(str(bank_balance)) - book_balance
        daily.append(
            {
                "date": bank_day,
                "date_jalali": format_jalali_date(date.fromisoformat(bank_day)),
                "bank_balance": float(bank_balance),
                "book_balance": float(book_balance),
                "difference": float(difference),
                "matched": abs(difference) <= Decimal("0.01"),
            }
        )
    daily_by_date = {item["date"]: item for item in daily}

    used_lines: set[int] = set()
    line_by_transaction: dict[str, int | None] = {}

    def find_line(amount: Decimal, sign: int, days: set[date]) -> int | None:
        for position, line in enumerate(lines):
            if position in used_lines or line["date"] not in days:
                continue
            if abs(line["net"] - sign * amount) <= Decimal("0.01"):
                used_lines.add(position)
                return position
        return None

    for result in results:
        day_item = daily_by_date.get(result["bank_date"])
        if day_item:
            result["bank_day_end_balance"] = day_item["bank_balance"]
            result["book_day_end_balance"] = day_item["book_balance"]
            result["day_balance_difference"] = day_item["difference"]
            result["day_balance_matched"] = day_item["matched"]
            # A day whose closing balance equals the Rahkaran book cannot hold a bank row without a
            # voucher: the voucher exists (combined, or with a different description/reference).
            if result.get("business_status") == "unposted" and day_item["matched"]:
                result["business_status"] = "posted"
                result["business_status_fa"] = "سندخورده"
                result["match_status"] = "matched"
                result["match_method"] = "daily_balance_match"
                result["reasons"] = list(result.get("reasons") or []) + [
                    "سند یک‌به‌یک پیدا نشد، ولی مانده پایان روز بانک با مانده دفتر راهکاران برابر است؛ "
                    "پس این گردش در دفتر ثبت شده (احتمالاً تجمیعی یا با شرح متفاوت)"
                ]

        transaction = result.get("matched_transaction")
        if not transaction or result.get("business_status") not in {
            "posted",
            "needs_review",
            "internal_transfer",
        }:
            continue
        transaction_id = transaction["transaction_id"]
        if transaction_id not in line_by_transaction:
            days = {
                date.fromisoformat(value[:10])
                for value in (
                    transaction.get("booking_date"),
                    transaction.get("settlement_date"),
                )
                if value
            }
            members = transaction.get("member_documents") or [
                {"amount": transaction["amount"]}
            ]
            sign = 1 if transaction.get("effect") == 1 else -1
            positions = [
                find_line(Decimal(str(member["amount"])), sign, days)
                for member in members
            ]
            line_by_transaction[transaction_id] = (
                max(positions)
                if positions and all(position is not None for position in positions)
                else None
            )
        position = line_by_transaction[transaction_id]
        if position is not None:
            line = lines[position]
            result["book_balance_after_document"] = float(line["balance"])
            result["book_voucher_number"] = line["voucher_number"]
            result["book_balance_basis"] = "سطر سند حسابداری"
        elif transaction.get("booking_date"):
            booking_day = date.fromisoformat(transaction["booking_date"][:10])
            result["book_balance_after_document"] = float(
                book_balance_at_end_of(booking_day)
            )
            result["book_voucher_number"] = None
            result["book_balance_basis"] = "پایان روز سند"

    _explain_balance_differences(daily, results, lines, used_lines)

    unmatched_days = [item for item in daily if not item["matched"]]
    return {
        "available": True,
        "dl_code": ledger["dl_code"],
        "dl_title": ledger["dl_title"],
        "day_count": len(daily),
        "matched_day_count": len(daily) - len(unmatched_days),
        "unmatched_day_count": len(unmatched_days),
        "first_unmatched_date": (
            unmatched_days[0]["date"] if unmatched_days else None
        ),
        "first_unmatched_date_jalali": (
            unmatched_days[0]["date_jalali"] if unmatched_days else None
        ),
        "last_matched_date_jalali": next(
            (
                item["date_jalali"]
                for item in reversed(daily)
                if item["matched"]
                and (
                    not unmatched_days
                    or item["date"] < unmatched_days[0]["date"]
                )
            ),
            None,
        ),
        "daily": daily,
    }


def reconcile_bank_statement(
    *,
    content: bytes,
    filename: str,
    bank_account_id: int | None = None,
    tolerance_days: int = 2,
    sheet_name: str | None = None,
    header_row: int = 0,
    date_column: str | None = None,
    deposit_column: str | None = None,
    withdrawal_column: str | None = None,
    description_column: str | None = None,
    reference_column: str | None = None,
    balance_column: str | None = None,
    payer_column: str | None = None,
    origin_account_column: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    safe_tolerance = max(0, min(int(tolerance_days), 7))
    bank_rows, file_info = parse_bank_statement(
        content=content,
        filename=filename,
        sheet_name=sheet_name,
        header_row=header_row,
        date_column=date_column,
        deposit_column=deposit_column,
        withdrawal_column=withdrawal_column,
        description_column=description_column,
        reference_column=reference_column,
        balance_column=balance_column,
        payer_column=payer_column,
        origin_account_column=origin_account_column,
    )

    start_date = min(row["date"] for row in bank_rows) - timedelta(
        days=safe_tolerance
    )
    end_date = max(row["date"] for row in bank_rows) + timedelta(
        days=safe_tolerance + 1
    )

    selected_engine = engine or get_sqlserver_engine()
    bank_account_query = text(
        """
        SELECT
            ba.BankAccountID,
            ba.Number,
            ba.InternationalNumber,
            ba.Description,
            ba.LedgerRef,
            ba.CurrencyRef,
            ba.State,
            bb.BankBranchID,
            bb.Code AS BankBranchCode,
            bb.Name AS BankBranchName,
            b.BankID,
            b.Name AS BankName,
            (
                SELECT COUNT_BIG(*)
                FROM RPA3.ReceiptDeposit rd
                WHERE rd.BankAccountRef = ba.BankAccountID
            ) + (
                SELECT COUNT_BIG(*)
                FROM RPA3.PaymentDeposit pd
                WHERE pd.BankAccountRef = ba.BankAccountID
            ) + (
                SELECT COUNT_BIG(*)
                FROM RPA3.ReceivableNoteTransaction rnt
                WHERE rnt.BankAccountRef = ba.BankAccountID
                  AND rnt.State = 3
                  AND rnt.DocumentItemType = 12
                  AND rnt.DocumentState = 3
            ) + (
                SELECT COUNT_BIG(*)
                FROM RPA3.TransferDeposit td
                INNER JOIN RPA3.Transfer tr
                    ON tr.TransferID = td.TransferRef
                WHERE tr.State = 3
                  AND (
                      td.SourceBankAccountRef = ba.BankAccountID
                      OR td.DestinationBankAccountRef = ba.BankAccountID
                  )
            ) AS UsageCount
        FROM RPA3.BankAccount ba
        LEFT JOIN RPA3.BankBranch bb
            ON bb.BankBranchID = ba.BankBranchRef
        LEFT JOIN RPA3.Bank b
            ON b.BankID = bb.BankRef
        WHERE
            (
                :bank_account_id IS NOT NULL
                AND ba.BankAccountID = :bank_account_id
            )
            OR
            (
                :bank_account_id IS NULL
                AND (
                    REPLACE(REPLACE(ba.Number, N'-', N''), N' ', N'')
                        = :statement_account_number
                    OR REPLACE(REPLACE(ba.Number, N'-', N''), N' ', N'')
                        = :statement_account_core
                    OR TRY_CONVERT(
                        DECIMAL(38, 0),
                        REPLACE(REPLACE(ba.Number, N'-', N''), N' ', N'')
                    ) = TRY_CONVERT(
                        DECIMAL(38, 0),
                        :statement_account_number
                    )
                    OR REPLACE(
                        REPLACE(ba.InternationalNumber, N'-', N''),
                        N' ',
                        N''
                    ) = :statement_iban
                )
                AND (
                    :statement_bank_name = N''
                    OR b.Name LIKE N'%' + :statement_bank_name + N'%'
                )
            )
        ORDER BY UsageCount DESC, ba.BankAccountID DESC
        """
    )
    transaction_query = text(
        """
        SELECT
            N'receipt' AS TransactionType,
            rd.ReceiptDepositID AS ItemID,
            r.ReceiptID AS DocumentID,
            r.Number AS DocumentNumber,
            r.Date AS DocumentDate,
            rd.Date AS ItemDate,
            rd.Amount,
            rd.CurrencyAmount,
            rd.BaseCurrencyAmount,
            rd.Number AS ItemNumber,
            rd.Description AS ItemDescription,
            r.Description AS DocumentDescription,
            rd.AccountRef,
            a.Name AS CounterpartAccountName
        FROM RPA3.ReceiptDeposit rd
        INNER JOIN RPA3.Receipt r
            ON r.ReceiptID = rd.ReceiptRef
        LEFT JOIN FIN3.Account a
            ON a.AccountID = rd.AccountRef
        WHERE rd.BankAccountRef = :bank_account_id
          AND r.ApproveState = 3
          AND rd.Date >= :start_date
          AND rd.Date < :end_date

        UNION ALL

        SELECT
            N'payment' AS TransactionType,
            pd.PaymentDepositID AS ItemID,
            p.PaymentID AS DocumentID,
            p.Number AS DocumentNumber,
            p.Date AS DocumentDate,
            pd.Date AS ItemDate,
            pd.Amount,
            pd.CurrencyAmount,
            pd.BaseCurrencyAmount,
            pd.Number AS ItemNumber,
            pd.Description AS ItemDescription,
            p.Description AS DocumentDescription,
            pd.AccountRef,
            a.Name AS CounterpartAccountName
        FROM RPA3.PaymentDeposit pd
        INNER JOIN RPA3.Payment p
            ON p.PaymentID = pd.PaymentRef
        LEFT JOIN FIN3.Account a
            ON a.AccountID = pd.AccountRef
        WHERE pd.BankAccountRef = :bank_account_id
          AND p.ApproveState = 3
          AND pd.Date >= :start_date
          AND pd.Date < :end_date

        UNION ALL

        SELECT
            N'received_cheque_status' AS TransactionType,
            rnt.ReceivableNoteTransactionID AS ItemID,
            rnt.DocumentRef AS DocumentID,
            rnt.DocumentNumber AS DocumentNumber,
            rnt.DocumentDate AS DocumentDate,
            rnt.Date AS ItemDate,
            COALESCE(rn.BaseCurrencyAmount, rn.Amount) AS Amount,
            rn.Amount AS CurrencyAmount,
            rn.BaseCurrencyAmount AS BaseCurrencyAmount,
            CONCAT_WS(
                N' ',
                rn.SerialNumber,
                rn.Series,
                rn.SayadNumber
            ) AS ItemNumber,
            COALESCE(rn.Description, N'') AS ItemDescription,
            COALESCE(rnt.Description, N'') AS DocumentDescription,
            rn.AccountRef,
            a.Name AS CounterpartAccountName
        FROM RPA3.ReceivableNoteTransaction rnt
        INNER JOIN RPA3.ReceivableNote rn
            ON rn.ReceivableNoteID = rnt.ReceivableNoteRef
        LEFT JOIN FIN3.Account a
            ON a.AccountID = rn.AccountRef
        WHERE (rnt.BankAccountRef = :bank_account_id OR rnt.BankAccountRef IS NULL)
          AND rn.NormalORGuarantee = 1
          AND ISNULL(rn.Description, N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(rn.Description, N'') NOT LIKE N'%تضمین%'
          AND ISNULL(rn.Description, N'') NOT LIKE N'%حسن انجام%'
          -- V96: State و DocumentItemType در نصب‌های مختلف راهکاران برای
          -- تعیین وضعیت/وصول یکسان نیستند. همه رویدادهای تاییدشده را در بازه
          -- امن می‌گیریم و تشخیص وصول را به Matcher (متن/سریال/مبلغ/تاریخ)
          -- واگذار می‌کنیم.
          AND rnt.DocumentState = 3
          AND (
                rnt.State = 3
                OR rnt.DocumentItemType = 12
                OR ISNULL(rnt.Description, N'') LIKE N'%وصول%'
                OR ISNULL(rnt.Description, N'') LIKE N'%نقد%'
                OR ISNULL(rnt.Description, N'') LIKE N'%تعیین وضعیت%'
                OR ISNULL(rnt.Description, N'') LIKE N'%تعین وضعیت%'
              )
          AND (
                (rnt.Date >= :received_cheque_start_date AND rnt.Date < :received_cheque_end_date)
                OR
                (rnt.DocumentDate >= :received_cheque_start_date AND rnt.DocumentDate < :received_cheque_end_date)
              )

        UNION ALL

        SELECT
            N'issued_cheque_status' AS TransactionType,
            pnt.PayableNoteTransactionID AS ItemID,
            pnt.DocumentRef AS DocumentID,
            pnt.DocumentNumber AS DocumentNumber,
            pnt.DocumentDate AS DocumentDate,
            pnt.Date AS ItemDate,
            COALESCE(
                pnt.BaseCurrencyAmount,
                pn.BaseCurrencyAmount,
                pn.Amount
            ) AS Amount,
            pn.Amount AS CurrencyAmount,
            COALESCE(pnt.BaseCurrencyAmount, pn.BaseCurrencyAmount) AS BaseCurrencyAmount,
            CONCAT_WS(N' ', pn.SerialNumber, pn.Series) AS ItemNumber,
            COALESCE(pn.Description, N'') AS ItemDescription,
            COALESCE(pnt.Description, N'') AS DocumentDescription,
            pn.AccountRef,
            a.Name AS CounterpartAccountName
        FROM RPA3.PayableNoteTransaction pnt
        INNER JOIN RPA3.PayableNote pn
            ON pn.PayableNoteID = pnt.PayableNoteRef
        LEFT JOIN FIN3.Account a
            ON a.AccountID = pn.AccountRef
        WHERE pn.BankAccountRef = :bank_account_id
          AND pn.NoteType = 1
          AND pn.NormalORGuarantee = 1
          AND ISNULL(pn.Description, N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(pn.Description, N'') NOT LIKE N'%تضمین%'
          AND ISNULL(pn.Description, N'') NOT LIKE N'%حسن انجام%'
          AND pnt.State = 11
          AND pnt.DocumentItemType IN (24, 26)
          AND pnt.DocumentState = 3
          AND (
              pnt.DocumentItemType = 24
              OR NOT EXISTS (
                  SELECT 1
                  FROM RPA3.PayableNoteTransaction preferred_pnt
                  WHERE preferred_pnt.PayableNoteRef = pnt.PayableNoteRef
                    AND preferred_pnt.State = 11
                    AND preferred_pnt.DocumentItemType = 24
                    AND preferred_pnt.DocumentState = 3
              )
          )
          AND pnt.Date >= :issued_cheque_start_date
          AND pnt.Date < :issued_cheque_end_date

        UNION ALL

        SELECT
            N'bank_transfer_in' AS TransactionType,
            td.TransferDepositID AS ItemID,
            tr.TransferID AS DocumentID,
            tr.Number AS DocumentNumber,
            tr.Date AS DocumentDate,
            COALESCE(td.ReceiptDepositDate, td.Date) AS ItemDate,
            COALESCE(
                td.ReceiptOperationalCurrencyAmount,
                td.ReceiptAmount
            ) AS Amount,
            td.ReceiptAmount AS CurrencyAmount,
            td.ReceiptOperationalCurrencyAmount AS BaseCurrencyAmount,
            td.ReceiptDepositNumber AS ItemNumber,
            COALESCE(td.Description, N'') AS ItemDescription,
            COALESCE(tr.Description, N'') AS DocumentDescription,
            CAST(NULL AS bigint) AS AccountRef,
            CAST(NULL AS nvarchar(1024)) AS CounterpartAccountName
        FROM RPA3.TransferDeposit td
        INNER JOIN RPA3.Transfer tr
            ON tr.TransferID = td.TransferRef
        WHERE td.DestinationBankAccountRef = :bank_account_id
          AND tr.State = 3
          AND COALESCE(td.ReceiptDepositDate, td.Date) >= :start_date
          AND COALESCE(td.ReceiptDepositDate, td.Date) < :end_date

        UNION ALL

        SELECT
            N'bank_transfer_out' AS TransactionType,
            td.TransferDepositID AS ItemID,
            tr.TransferID AS DocumentID,
            tr.Number AS DocumentNumber,
            tr.Date AS DocumentDate,
            COALESCE(tr.PaymentDate, td.Date) AS ItemDate,
            COALESCE(
                td.PaymentOperationalCurrencyAmount,
                td.PaymentAmount
            ) AS Amount,
            td.PaymentAmount AS CurrencyAmount,
            td.PaymentOperationalCurrencyAmount AS BaseCurrencyAmount,
            td.Number AS ItemNumber,
            COALESCE(td.Description, N'') AS ItemDescription,
            COALESCE(tr.Description, N'') AS DocumentDescription,
            CAST(NULL AS bigint) AS AccountRef,
            CAST(NULL AS nvarchar(1024)) AS CounterpartAccountName
        FROM RPA3.TransferDeposit td
        INNER JOIN RPA3.Transfer tr
            ON tr.TransferID = td.TransferRef
        WHERE td.SourceBankAccountRef = :bank_account_id
          AND tr.State = 3
          AND COALESCE(tr.PaymentDate, td.Date) >= :start_date
          AND COALESCE(tr.PaymentDate, td.Date) < :end_date

        UNION ALL

        -- واریز وجه نقد صندوق به بانک (انتقال از صندوق به بانک) در
        -- TransferCashMoney ثبت می‌شود، نه ReceiptDeposit یا TransferDeposit.
        SELECT
            N'cash_transfer_in' AS TransactionType,
            tcm.TransferCashMoneyID AS ItemID,
            tr.TransferID AS DocumentID,
            tr.Number AS DocumentNumber,
            tr.Date AS DocumentDate,
            COALESCE(tcm.ReceiptDepositDate, tr.ReceiptDate, tr.Date) AS ItemDate,
            COALESCE(
                tcm.ReceiptOperationalCurrencyAmount,
                tcm.ReceiptAmount
            ) AS Amount,
            tcm.ReceiptAmount AS CurrencyAmount,
            tcm.ReceiptOperationalCurrencyAmount AS BaseCurrencyAmount,
            tcm.ReceiptDepositNumber AS ItemNumber,
            COALESCE(tcm.Description, N'') AS ItemDescription,
            COALESCE(tr.Description, N'') AS DocumentDescription,
            CAST(NULL AS bigint) AS AccountRef,
            CAST(NULL AS nvarchar(1024)) AS CounterpartAccountName
        FROM RPA3.TransferCashMoney tcm
        INNER JOIN RPA3.Transfer tr
            ON tr.TransferID = tcm.TransferRef
        WHERE tcm.DestinationBankAccountRef = :bank_account_id
          AND tr.State = 3
          AND COALESCE(tcm.ReceiptDepositDate, tr.ReceiptDate, tr.Date) >= :start_date
          AND COALESCE(tcm.ReceiptDepositDate, tr.ReceiptDate, tr.Date) < :end_date

        ORDER BY ItemDate, TransactionType, ItemID
        """
    )

    statement_account_number = re.sub(
        r"\D",
        "",
        _as_text(file_info.get("statement_account_number")),
    )
    statement_iban = re.sub(
        r"[^A-Za-z0-9]",
        "",
        _as_text(file_info.get("statement_iban")),
    ).upper()
    statement_bank_name = _as_text(file_info.get("statement_bank_name"))
    # بانک تجارت شماره را در خروجی اینترنت‌بانک به قالب زیر می‌دهد:
    # 010 + شماره ۹ رقمی ذخیره‌شده در راهکاران + رقم کنترل.
    # نمونه: 0103560567877 در فایل برابر است با 356056787 در RPA3.BankAccount.
    statement_account_core = _derive_statement_account_core(
        statement_account_number,
        statement_bank_name,
    )
    file_info["statement_account_core"] = statement_account_core or None
    if bank_account_id is None and not (statement_account_number or statement_iban):
        raise ReconciliationInputError(
            "شناسه حساب بانکی داده نشده و شماره حساب/شبا از فایل قابل تشخیص نیست."
        )

    parameters = {
        "bank_account_id": (
            int(bank_account_id) if bank_account_id is not None else None
        ),
        "statement_account_number": statement_account_number,
        "statement_account_core": statement_account_core,
        "statement_iban": statement_iban,
        "statement_bank_name": statement_bank_name,
        "start_date": start_date,
        "end_date": end_date,
        # برای چک صادرشده شماره سریال شناسه اصلی است و ثبت وضعیت ممکن است
        # چند هفته پس از گردش بانک انجام شود. بازه Query کمی بزرگ‌تر گرفته
        # می‌شود، ولی تأیید نهایی همچنان به برابری مبلغ/جهت/سریال وابسته است.
        "issued_cheque_start_date": start_date - timedelta(days=60),
        "issued_cheque_end_date": end_date + timedelta(days=60),
        # بانک شهر ممکن است سند تعیین وضعیت/وصول را چند روز بعد از گردش بانک
        # ثبت کند. Query دریافت چک بازتر است؛ Matcher فقط با شواهد چکی معتبر
        # و مبلغ/جهت/تاریخ آن را تایید می‌کند.
        "received_cheque_start_date": start_date - timedelta(days=45),
        "received_cheque_end_date": end_date + timedelta(days=45),
    }
    with selected_engine.connect() as connection:
        bank_account_rows = connection.execute(
            bank_account_query,
            parameters,
        ).mappings().all()
        if not bank_account_rows:
            raise ReconciliationInputError("حساب بانکی راهکاران پیدا نشد.")
        if (
            bank_account_id is None
            and len(bank_account_rows) > 1
            and bank_account_rows[0]["UsageCount"]
            == bank_account_rows[1]["UsageCount"]
        ):
            raise ReconciliationInputError(
                "چند حساب بانکی با شماره یکسان و سابقه مشابه پیدا شد؛ "
                "bank_account_id را دستی وارد کنید."
            )
        bank_account = bank_account_rows[0]
        parameters["bank_account_id"] = bank_account["BankAccountID"]
        transaction_rows = connection.execute(
            transaction_query,
            parameters,
        ).mappings().all()
        # کنترل مانده: خطای خواندن دفتر نباید مغایرت‌گیری تراکنش‌ها را متوقف کند.
        try:
            book_ledger = _load_book_ledger(
                connection,
                bank_account,
                start_date,
                end_date,
            )
        except Exception as error:  # noqa: BLE001
            book_ledger = {
                "available": False,
                "message": f"خواندن مانده دفتر راهکاران ممکن نشد: {error}",
            }

    transactions: list[dict[str, Any]] = []
    for row in transaction_rows:
        transaction_type = row["TransactionType"]
        item_description = row["ItemDescription"] or ""
        document_description = row["DocumentDescription"] or ""
        counterpart_name = row["CounterpartAccountName"] or ""
        description = " | ".join(
            value
            for value in (
                item_description,
                document_description,
                counterpart_name,
            )
            if value
        )
        item_number = _as_text(row["ItemNumber"])
        document_number = _as_text(row["DocumentNumber"])
        transactions.append(
            {
                "transaction_id": f"{transaction_type}:{row['ItemID']}",
                "transaction_type": transaction_type,
                "item_id": row["ItemID"],
                "document_id": row["DocumentID"],
                "document_number": document_number,
                "item_number": item_number,
                "booking_date": row["ItemDate"],
                "settlement_date": row["DocumentDate"],
                "description": description,
                "amount": abs(Decimal(str(row["Amount"] or 0))),
                "entry_amount": abs(
                    Decimal(str(row["CurrencyAmount"] or 0))
                ),
                "gl_amount": abs(
                    Decimal(str(row["BaseCurrencyAmount"] or 0))
                ),
                "amount_source": (
                    "receivable_note_base_currency_amount"
                    if transaction_type == "received_cheque_status"
                    else "payable_note_base_currency_amount"
                    if transaction_type == "issued_cheque_status"
                    else "transfer_deposit_amount"
                    if transaction_type
                    in {"bank_transfer_in", "bank_transfer_out"}
                    else "transfer_cash_money_amount"
                    if transaction_type == "cash_transfer_in"
                    else "receipt_payment_deposit_amount"
                ),
                "effect": (
                    1
                    if transaction_type
                    in {
                        "receipt",
                        "received_cheque_status",
                        "bank_transfer_in",
                        "cash_transfer_in",
                    }
                    else 2
                ),
                "reference_component": "RPA3",
                "reference_entity": (
                    {
                        "receipt": "ReceiptDeposit",
                        "payment": "PaymentDeposit",
                        "received_cheque_status": "ReceivableNoteTransaction",
                        "issued_cheque_status": "PayableNoteTransaction",
                        "bank_transfer_in": "TransferDeposit",
                        "bank_transfer_out": "TransferDeposit",
                        "cash_transfer_in": "TransferCashMoney",
                    }[transaction_type]
                ),
                "reference_ref": " ".join(
                    value for value in (document_number, item_number) if value
                ),
                "counterpart_account_ref": row["AccountRef"],
                "counterpart_account_name": counterpart_name,
            }
        )

    results, used_transaction_ids = _match_bank_rows(
        bank_rows,
        transactions,
        safe_tolerance,
    )
    for result in results:
        result["bank_date_jalali"] = format_jalali_date(
            result.get("bank_date")
        )
    fee_summary = _attach_fee_details(results)
    book_balance = _attach_balances(results, book_ledger)
    file_info["statement_period_jalali"] = (
        f"{format_jalali_date(min(row['date'] for row in bank_rows))} تا "
        f"{format_jalali_date(max(row['date'] for row in bank_rows))}"
    )
    unmatched_erp = [
        _serialize_transaction(transaction)
        for transaction in transactions
        if transaction["transaction_id"] not in used_transaction_ids
    ]

    counts = {
        status: sum(
            1 for result in results if result["match_status"] == status
        )
        for status in (
            "matched",
            "possible_match",
            "unmatched",
            "reversed",
            "internal_transfer",
        )
    }
    amounts = {
        status: sum(
            result["amount"]
            for result in results
            if result["match_status"] == status
        )
        for status in (
            "matched",
            "possible_match",
            "unmatched",
            "reversed",
            "internal_transfer",
        )
    }
    business_counts = {
        status: sum(
            1 for result in results if result["business_status"] == status
        )
        for status in (
            "posted",
            "reversed",
            "internal_transfer",
            "needs_review",
            "unposted",
        )
    }
    business_amounts = {
        status: sum(
            result["amount"]
            for result in results
            if result["business_status"] == status
        )
        for status in (
            "posted",
            "reversed",
            "internal_transfer",
            "needs_review",
            "unposted",
        )
    }
    total_bank_rows = len(results)
    definite_match_count = business_counts["posted"]
    confirmed_coverage_count = (
        business_counts["posted"] + business_counts["reversed"]
    )
    tolerant_coverage_count = (
        confirmed_coverage_count + business_counts["needs_review"]
    )
    internal_transfer_policy_count = business_counts["internal_transfer"]
    definite_resolution_count = (
        confirmed_coverage_count + internal_transfer_policy_count
    )
    direction_summary = {
        direction: {
            "count": sum(
                1 for result in results if result["direction"] == direction
            ),
            "amount": sum(
                result["amount"]
                for result in results
                if result["direction"] == direction
            ),
        }
        for direction in ("deposit", "withdrawal")
    }
    business_direction_summary = {
        status: {
            direction: {
                "count": sum(
                    1
                    for result in results
                    if result["business_status"] == status
                    and result["direction"] == direction
                ),
                "amount": sum(
                    result["amount"]
                    for result in results
                    if result["business_status"] == status
                    and result["direction"] == direction
                ),
            }
            for direction in ("deposit", "withdrawal")
        }
        for status in (
            "posted",
            "reversed",
            "internal_transfer",
            "needs_review",
            "unposted",
        )
    }
    statement_account_number = file_info.get("statement_account_number")
    erp_account_number = _as_text(bank_account["Number"])
    resolved_international_number = (
        _as_text(bank_account["InternationalNumber"])
        or _as_text(file_info.get("statement_iban"))
    )
    normalized_statement_account = re.sub(
        r"\D",
        "",
        _as_text(statement_account_number),
    )
    normalized_statement_core = re.sub(
        r"\D",
        "",
        _as_text(file_info.get("statement_account_core")),
    )
    normalized_erp_account = re.sub(r"\D", "", erp_account_number)
    display_account_number = (
        normalized_statement_account or normalized_erp_account
    )
    account_last_four = display_account_number[-4:]
    bank_name = _as_text(bank_account["BankName"])
    account_display_label = " ".join(
        value
        for value in (
            f"حساب {account_last_four}" if account_last_four else "حساب بانکی",
            bank_name,
        )
        if value
    )
    if normalized_statement_account and normalized_erp_account:
        account_number_check = (
            "matched"
            if (
                normalized_statement_account == normalized_erp_account
                or normalized_statement_core == normalized_erp_account
                or normalized_statement_account.lstrip("0")
                == normalized_erp_account.lstrip("0")
            )
            else "different"
        )
    else:
        account_number_check = "not_available"

    return {
        "status": "success",
        "file": file_info,
        "account": {
            "account_id": bank_account["BankAccountID"],
            "bank_account_id": bank_account["BankAccountID"],
            "name": bank_account["Description"],
            "number": bank_account["Number"],
            "international_number": resolved_international_number,
            "ledger_ref": bank_account["LedgerRef"],
            "currency_ref": bank_account["CurrencyRef"],
            "status": bank_account["State"],
            "bank_id": bank_account["BankID"],
            "bank_name": bank_name,
            "account_last_four": account_last_four,
            "display_label": account_display_label,
            "bank_branch_id": bank_account["BankBranchID"],
            "bank_branch_name": bank_account["BankBranchName"] or "",
            "bank_branch_code": bank_account["BankBranchCode"] or "",
            "usage_count": bank_account["UsageCount"],
            "resolution_method": (
                "explicit_id" if bank_account_id is not None else "statement_number"
            ),
            "statement_account_number_check": account_number_check,
        },
        "bank_account": {
            "bank_account_id": bank_account["BankAccountID"],
            "description": bank_account["Description"],
            "number": bank_account["Number"],
            "international_number": resolved_international_number,
            "ledger_ref": bank_account["LedgerRef"],
            "currency_ref": bank_account["CurrencyRef"],
            "state": bank_account["State"],
            "bank_id": bank_account["BankID"],
            "bank_name": bank_name,
            "account_last_four": account_last_four,
            "display_label": account_display_label,
            "bank_branch_id": bank_account["BankBranchID"],
            "bank_branch_name": bank_account["BankBranchName"] or "",
            "bank_branch_code": bank_account["BankBranchCode"] or "",
            "usage_count": bank_account["UsageCount"],
            "resolution_method": (
                "explicit_id" if bank_account_id is not None else "statement_number"
            ),
            "statement_account_number_check": account_number_check,
        },
        "matching_rules": {
            "date_tolerance_days": safe_tolerance,
            "deposit_source": (
                "RPA3.ReceiptDeposit + "
                "RPA3.ReceivableNoteTransaction(approved status events; matcher-filtered)"
            ),
            "withdrawal_source": "RPA3.PaymentDeposit",
            "approve_state": 3,
            "amount_field": "Amount",
            "one_to_one_matching": True,
            "different_amount_is_never_auto_posted": True,
            "duplicate_bank_rows_require_review": True,
            "daily_fee_group_matching": True,
            "daily_fee_group_requires_exact_total": True,
            "daily_fee_group_requires_same_date": True,
            "same_day_amount_batch_matching": True,
            "tolerance_window_batch_matching": True,
            "erp_rows_are_consumed_once": True,
            "cheque_serial_matching": True,
            "cheque_like_transfer_requires_review": True,
            "bank_reversal_pair_matching": True,
            "bank_reversal_batch_matching": True,
        },
        "summary": {
            "bank_row_count": total_bank_rows,
            "erp_transaction_count": len(transactions),
            "rahkaran_item_count": len(transactions),
            "bank_total_amount": sum(result["amount"] for result in results),
            "business_counts": business_counts,
            "business_amounts": business_amounts,
            "documentable_bank_row_count": max(
                0,
                total_bank_rows
                - int(business_counts.get("reversed", 0) or 0)
                - int(business_counts.get("internal_transfer", 0) or 0),
            ),
            "definite_match_rate": (
                definite_match_count
                / max(
                    1,
                    total_bank_rows
                    - int(business_counts.get("reversed", 0) or 0)
                    - int(business_counts.get("internal_transfer", 0) or 0),
                )
                if total_bank_rows
                else 0
            ),
            "confirmed_coverage_rate": (
                confirmed_coverage_count / total_bank_rows
                if total_bank_rows
                else 0
            ),
            "tolerant_coverage_rate": (
                tolerant_coverage_count / total_bank_rows
                if total_bank_rows
                else 0
            ),
            "tolerant_coverage_count": tolerant_coverage_count,
            "internal_transfer_policy_count": internal_transfer_policy_count,
            "definite_resolution_count": definite_resolution_count,
            "definite_resolution_rate": (
                definite_resolution_count / total_bank_rows
                if total_bank_rows
                else 0
            ),
            "direction_summary": direction_summary,
            "business_direction_summary": business_direction_summary,
            "erp_only_count": len(unmatched_erp),
            "erp_only_amount": sum(
                transaction["amount"] for transaction in unmatched_erp
            ),
            "rahkaran_only_count": len(unmatched_erp),
            "rahkaran_only_amount": sum(
                transaction["amount"] for transaction in unmatched_erp
            ),
            "counts": counts,
            "amounts": amounts,
            "unmatched_erp_count": len(unmatched_erp),
            "fee_summary": fee_summary,
        },
        "book_balance": book_balance,
        "rows": results,
        "unmatched_erp_transactions": unmatched_erp,
        "unmatched_raahkaran_items": unmatched_erp,
    }
