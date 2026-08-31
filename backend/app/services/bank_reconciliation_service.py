from __future__ import annotations

from collections.abc import Iterable
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
import re
from typing import Any
import unicodedata

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database.sqlserver import get_sqlserver_engine


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_DATA_ROWS = 10_000


class ReconciliationInputError(ValueError):
    """خطای قابل نمایش مربوط به فایل یا تنظیمات ورودی."""


_PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)
_PERSIAN_TEXT = str.maketrans(
    {
        "آ": "ا",
        "أ": "ا",
        "إ": "ا",
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "\u200c": " ",
    }
)


_COLUMN_ALIASES = {
    "date": {
        "تاریخ",
        "تاریخ تراکنش",
        "تاریخ موثر",
        "تاریخ عملیات",
        "date",
        "transaction date",
    },
    "deposit": {
        "واریز",
        "مبلغ واریز",
        "بستانکار",
        "مبلغ بستانکار",
        "credit",
        "deposit",
    },
    "withdrawal": {
        "برداشت",
        "مبلغ برداشت",
        "بدهکار",
        "مبلغ بدهکار",
        "debit",
        "withdrawal",
    },
    "description": {
        "شرح",
        "شرح تراکنش",
        "توضیحات",
        "description",
        "details",
        "narration",
    },
    "document_description": {
        "شرح سند",
        "توضیحات سند",
        "document description",
    },
    "reference": {
        "RRN",
        "شماره پیگیری",
        "کد پیگیری",
        "شماره مرجع",
        "کد رهگیری",
        "reference",
        "reference number",
        "tracking",
        "tracking number",
    },
    "balance": {
        "مانده",
        "موجودی",
        "balance",
    },
    "payer": {
        "نام واریز کننده",
        "نام واریزکننده",
        "صاحب حساب مبدا",
        "نام صاحب حساب مبدا",
        "payer",
        "sender name",
    },
    "origin_account": {
        "حساب مبدا",
        "شماره حساب مبدا",
        "شماره شبا مبدا",
        "شبا مبدا",
        "origin account",
        "source account",
        "source iban",
    },
    "operation": {
        "عملیات",
        "شرح عملیات",
        "نوع عملیات",
        "operation",
    },
    "time": {"زمان", "ساعت", "time"},
    "bank_document_number": {
        "شماره سند",
        "شماره سند بانک",
        "bank document number",
    },
    "deposit_id": {"شناسه واریز", "deposit id"},
    "note": {"یادداشت", "توضیحات کاربر", "note"},
    "branch": {"شعبه", "نام شعبه", "branch"},
    "cheque_number": {
        "شماره برگه شماره چک",
        "شماره چک",
        "cheque number",
    },
}


_BANK_NAME_HINTS = (
    ("تجارت", ("تجارت", "tejarat")),
    ("سپه", ("سپه", "sepah")),
    ("شهر", ("بانک شهر", "بانکشهر", "shahr", "city bank")),
    ("پاسارگاد", ("پاسارگاد", "pasargad")),
    ("ملت", ("بانک ملت", "bank mellat")),
    ("ملی", ("بانک ملی", "bank melli")),
)


def _detect_statement_bank_name(
    filename: str,
    sheet_name: str | None,
    rows: list[list[Any]],
) -> str | None:
    # نام فایل و Sheet قابل‌اعتمادترین نشانه بانک صادرکننده‌اند. شرح گردش‌ها
    # ممکن است نام بانک طرف چک یا حواله را داشته باشد؛ مثلاً فایل بانک شهر در
    # ردیف‌های ابتدایی چکی عهده بانک تجارت دارد و نباید «تجارت» تشخیص داده شود.
    identity_haystack = _normalize_text(
        " ".join((filename, sheet_name or ""))
    )
    for bank_name, hints in _BANK_NAME_HINTS:
        if any(
            _normalize_text(hint) in identity_haystack
            for hint in hints
        ):
            return bank_name

    # اگر نام فایل عمومی بود، فقط بخش سربرگ را می‌خوانیم. هفت ردیف اول در
    # قالب‌های پشتیبانی‌شده هنوز قبل از جزئیات تراکنش قرار دارند.
    header_values: list[str] = []
    for row in rows[:7]:
        header_values.extend(_as_text(value) for value in row if value)
    header_haystack = _normalize_text(" ".join(header_values))
    for bank_name, hints in _BANK_NAME_HINTS:
        if any(
            _normalize_text(hint) in header_haystack
            for hint in hints
        ):
            return bank_name
    return None


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


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = normalized.translate(_PERSIAN_DIGITS).translate(_PERSIAN_TEXT)
    normalized = re.sub(r"[^\w\u0600-\u06ff]+", " ", normalized.lower())
    return " ".join(normalized.split())


def _parse_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return abs(value)
    if isinstance(value, (int, float)):
        return abs(Decimal(str(value)))

    raw = str(value).strip().translate(_PERSIAN_DIGITS)
    if not raw or raw in {"-", "--"}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()")
    raw = re.sub(r"[,_،\s]", "", raw)
    raw = re.sub(r"(?i)(irr|rial|ریال|تومان)", "", raw)
    raw = re.sub(r"[^0-9.\-]", "", raw)
    if raw in {"", "-", "."}:
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ReconciliationInputError(
            f"مبلغ نامعتبر در فایل بانک: {value}"
        ) from exc
    return abs(-amount if negative else amount)


def _as_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    if isinstance(value, (int, float)):
        try:
            from openpyxl.utils.datetime import from_excel

            return from_excel(value).date()
        except Exception as exc:
            raise ReconciliationInputError(
                f"تاریخ عددی نامعتبر در فایل بانک: {value}"
            ) from exc

    raw = str(value or "").strip().translate(_PERSIAN_DIGITS)
    raw = raw.split()[0] if raw else ""
    parts = [part for part in re.split(r"[/\-.]", raw) if part]
    if len(parts) != 3:
        raise ReconciliationInputError(
            f"تاریخ نامعتبر در فایل بانک: {value}"
        )

    first, second, third = (int(part) for part in parts)
    if first < 1700:
        try:
            import jdatetime

            return jdatetime.date(first, second, third).togregorian()
        except Exception as exc:
            raise ReconciliationInputError(
                f"تاریخ شمسی نامعتبر در فایل بانک: {value}"
            ) from exc

    try:
        return date(first, second, third)
    except ValueError as exc:
        raise ReconciliationInputError(
            f"تاریخ میلادی نامعتبر در فایل بانک: {value}"
        ) from exc


def _read_csv(content: bytes) -> list[list[Any]]:
    decoded: str | None = None
    for encoding in ("utf-8-sig", "cp1256", "windows-1256"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ReconciliationInputError("Encoding فایل CSV قابل تشخیص نیست.")

    sample = decoded[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(StringIO(decoded), dialect)]


def _read_xlsx(
    content: bytes,
    sheet_name: str | None,
) -> tuple[list[list[Any]], str]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl is not installed") from exc

    workbook = load_workbook(
        BytesIO(content),
        read_only=True,
        data_only=True,
    )
    try:
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                raise ReconciliationInputError(
                    f"Sheet با نام {sheet_name} پیدا نشد."
                )
            worksheet = workbook[sheet_name]
        else:
            worksheet = workbook[workbook.sheetnames[0]]

        rows = [
            list(row)
            for row in worksheet.iter_rows(values_only=True)
        ]
        return rows, worksheet.title
    finally:
        workbook.close()


def _read_xls(
    content: bytes,
    sheet_name: str | None,
) -> tuple[list[list[Any]], str]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError(
            "برای خواندن فایل XLS بسته xlrd نصب نشده است."
        ) from exc

    try:
        workbook = xlrd.open_workbook(file_contents=content)
    except Exception as exc:
        raise ReconciliationInputError("فایل XLS قابل خواندن نیست.") from exc

    if sheet_name:
        if sheet_name not in workbook.sheet_names():
            raise ReconciliationInputError(
                f"Sheet با نام {sheet_name} پیدا نشد."
            )
        worksheet = workbook.sheet_by_name(sheet_name)
    else:
        worksheet = workbook.sheet_by_index(0)

    rows = [worksheet.row_values(index) for index in range(worksheet.nrows)]
    return rows, worksheet.name


def _resolve_column(
    headers: list[Any],
    semantic_name: str,
    explicit_name: str | None,
    required: bool,
) -> int | None:
    normalized_headers = [_normalize_text(header) for header in headers]
    if explicit_name:
        target = _normalize_text(explicit_name)
        if target not in normalized_headers:
            raise ReconciliationInputError(
                f"ستون «{explicit_name}» در فایل پیدا نشد."
            )
        return normalized_headers.index(target)

    aliases = {
        _normalize_text(alias)
        for alias in _COLUMN_ALIASES[semantic_name]
    }
    # ابتدا تطبیق دقیق را انجام می‌دهیم؛ در غیر این صورت عنوان عمومی «شرح»
    # ممکن است زودتر از ستون دقیق‌تر «شرح تراکنش» انتخاب شود.
    for index, header in enumerate(normalized_headers):
        if header in aliases:
            return index
    for index, header in enumerate(normalized_headers):
        if any(header.startswith(f"{alias} ") for alias in aliases):
            return index

    if required:
        raise ReconciliationInputError(
            f"ستون {semantic_name} خودکار پیدا نشد؛ نام ستون را دستی وارد کنید."
        )
    return None


def _detect_header_row(rows: list[list[Any]]) -> int:
    required_semantics = ("date", "deposit", "withdrawal")
    for row_index, row in enumerate(rows[:100], start=1):
        normalized_headers = [_normalize_text(value) for value in row]
        if all(
            any(
                header == alias or header.startswith(f"{alias} ")
                for header in normalized_headers
                for alias in {
                    _normalize_text(value)
                    for value in _COLUMN_ALIASES[semantic]
                }
            )
            for semantic in required_semantics
        ):
            return row_index
    raise ReconciliationInputError(
        "ردیف عنوان خودکار پیدا نشد؛ شماره header_row را دستی وارد کنید."
    )


def _extract_statement_metadata(
    rows: list[list[Any]],
    header_row: int,
) -> dict[str, str | None]:
    account_number: str | None = None
    iban: str | None = None
    report_period: str | None = None

    account_labels = {
        "شماره حساب",
        "شماره حساب سپرده",
        "شماره سپرده",
        "صورت حساب سپرده",
    }

    metadata_rows = rows[: max(0, header_row - 1)]
    normalized_account_labels = {
        _normalize_text(label) for label in account_labels
    }

    for row_index, row in enumerate(metadata_rows):
        values = [_as_text(value) for value in row if value not in (None, "")]
        joined = " | ".join(values)
        compact = re.sub(r"\s+", "", joined).upper()

        iban_match = re.search(r"IR\d{24}", compact)
        if iban_match and iban is None:
            iban = iban_match.group(0)

        if report_period is None and "از " in joined and " تا " in joined:
            report_period = joined

        if account_number is None:
            for column_index, raw_value in enumerate(row):
                normalized_value = _normalize_text(raw_value)
                if not any(
                    normalized_value == label
                    or normalized_value.startswith(f"{label} ")
                    for label in normalized_account_labels
                ):
                    continue

                # شماره ممکن است داخل همان سلول، در سلول‌های بعدی همان ردیف
                # (بانک شهر)، یا زیر عنوان در همان ستون (بانک تجارت) باشد.
                candidates: list[Any] = [raw_value]
                candidates.extend(row[column_index + 1 : column_index + 3])
                for next_row in metadata_rows[row_index + 1 : row_index + 4]:
                    if column_index < len(next_row):
                        candidates.append(next_row[column_index])

                for candidate in candidates:
                    digits = re.sub(
                        r"\D",
                        "",
                        _as_text(candidate).translate(_PERSIAN_DIGITS),
                    )
                    if 4 <= len(digits) <= 30:
                        account_number = digits
                        break
                if account_number is not None:
                    break

    # در برخی خروجی‌ها شماره حساب در ستون جزئیات همه تراکنش‌ها تکرار می‌شود.
    if account_number is None and 0 < header_row <= len(rows):
        headers = rows[header_row - 1]
        for column_index, header in enumerate(headers):
            if _normalize_text(header) not in normalized_account_labels:
                continue
            for data_row in rows[header_row : header_row + 25]:
                if column_index >= len(data_row):
                    continue
                digits = re.sub(
                    r"\D",
                    "",
                    _as_text(data_row[column_index]).translate(_PERSIAN_DIGITS),
                )
                if 4 <= len(digits) <= 30:
                    account_number = digits
                    break
            if account_number is not None:
                break

    # بانک تجارت شبا را در سربرگ نمی‌نویسد، اما در شرح حواله‌های ورودی، شبای
    # مقصدِ همین حساب وجود دارد. فقط شبایی پذیرفته می‌شود که انتهای آن با شماره
    # حساب تشخیص‌داده‌شده یکسان باشد تا شبای طرف مقابل انتخاب نشود.
    if iban is None and account_number:
        account_tail = account_number.lstrip("0")
        if len(account_tail) >= 8:
            for row in rows[:500]:
                joined_row = " ".join(
                    _as_text(value) for value in row if value not in (None, "")
                )
                compact_row = re.sub(r"\s+", "", joined_row).upper()
                for candidate in re.findall(r"IR\d{24}", compact_row):
                    if candidate[2:].endswith(account_tail):
                        iban = candidate
                        break
                if iban is not None:
                    break

    return {
        "statement_account_number": account_number,
        "statement_iban": iban,
        "statement_period": report_period,
    }


def parse_bank_statement(
    *,
    content: bytes,
    filename: str,
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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(content) > MAX_FILE_SIZE:
        raise ReconciliationInputError("حداکثر اندازه فایل ۱۰ مگابایت است.")
    if header_row < 0:
        raise ReconciliationInputError("header_row نمی‌تواند منفی باشد.")

    suffix = Path(filename).suffix.lower()
    selected_sheet: str | None = None
    if suffix == ".csv":
        rows = _read_csv(content)
    elif suffix == ".xlsx":
        rows, selected_sheet = _read_xlsx(content, sheet_name)
    elif suffix == ".xls":
        rows, selected_sheet = _read_xls(content, sheet_name)
    else:
        raise ReconciliationInputError(
            "فقط فایل‌های CSV، XLSX و XLS پشتیبانی می‌شوند."
        )

    if header_row == 0:
        header_row = _detect_header_row(rows)

    if len(rows) < header_row:
        raise ReconciliationInputError("ردیف عنوان مشخص‌شده در فایل وجود ندارد.")
    headers = rows[header_row - 1]
    if not any(_normalize_text(header) for header in headers):
        raise ReconciliationInputError("ردیف عنوان فایل خالی است.")

    indexes = {
        "date": _resolve_column(headers, "date", date_column, True),
        "deposit": _resolve_column(
            headers,
            "deposit",
            deposit_column,
            True,
        ),
        "withdrawal": _resolve_column(
            headers,
            "withdrawal",
            withdrawal_column,
            True,
        ),
        "description": _resolve_column(
            headers,
            "description",
            description_column,
            False,
        ),
        "document_description": _resolve_column(
            headers,
            "document_description",
            None,
            False,
        ),
        "reference": _resolve_column(
            headers,
            "reference",
            reference_column,
            False,
        ),
        "balance": _resolve_column(
            headers,
            "balance",
            balance_column,
            False,
        ),
        "payer": _resolve_column(
            headers,
            "payer",
            payer_column,
            False,
        ),
        "origin_account": _resolve_column(
            headers,
            "origin_account",
            origin_account_column,
            False,
        ),
        "operation": _resolve_column(headers, "operation", None, False),
        "time": _resolve_column(headers, "time", None, False),
        "bank_document_number": _resolve_column(
            headers,
            "bank_document_number",
            None,
            False,
        ),
        "deposit_id": _resolve_column(headers, "deposit_id", None, False),
        "note": _resolve_column(headers, "note", None, False),
        "branch": _resolve_column(headers, "branch", None, False),
        "cheque_number": _resolve_column(
            headers,
            "cheque_number",
            None,
            False,
        ),
    }

    parsed_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for row_number, row in enumerate(rows[header_row:], start=header_row + 1):
        if len(parsed_rows) >= MAX_DATA_ROWS:
            raise ReconciliationInputError("حداکثر ۱۰٬۰۰۰ ردیف قابل پردازش است.")
        if not any(value not in (None, "") for value in row):
            continue

        def value_at(index: int | None) -> Any:
            return row[index] if index is not None and index < len(row) else None

        try:
            raw_date = value_at(indexes["date"])
            if raw_date in (None, ""):
                # ردیف‌های جمع، پاورقی و فاصله‌های انتهای گزارش بانکی تراکنش نیستند.
                continue
            deposit = _parse_amount(value_at(indexes["deposit"]))
            withdrawal = _parse_amount(value_at(indexes["withdrawal"]))
            if deposit and withdrawal:
                raise ReconciliationInputError(
                    "هم‌زمان مبلغ واریز و برداشت دارد."
                )
            if not deposit and not withdrawal:
                continue
            direction = "deposit" if deposit else "withdrawal"
            amount = deposit or withdrawal
            description = " | ".join(
                part
                for part in (
                    _as_text(value_at(indexes["description"])),
                    _as_text(value_at(indexes["document_description"])),
                    _as_text(value_at(indexes["operation"])),
                )
                if part
            )
            parsed_rows.append(
                {
                    "row_number": row_number,
                    "date": _parse_date(raw_date),
                    "amount": amount,
                    "direction": direction,
                    "description": description,
                    "reference": _as_text(value_at(indexes["reference"])),
                    "balance": _parse_amount(value_at(indexes["balance"])),
                    "payer": _as_text(value_at(indexes["payer"])),
                    "origin_account": _as_text(
                        value_at(indexes["origin_account"])
                    ),
                    "operation": _as_text(value_at(indexes["operation"])),
                    "time": _as_text(value_at(indexes["time"])),
                    "bank_document_number": _as_text(
                        value_at(indexes["bank_document_number"])
                    ),
                    "deposit_id": _as_text(value_at(indexes["deposit_id"])),
                    "note": _as_text(value_at(indexes["note"])),
                    "branch": _as_text(value_at(indexes["branch"])),
                    "cheque_number": _as_text(
                        value_at(indexes["cheque_number"])
                    ),
                }
            )
        except ReconciliationInputError as exc:
            errors.append(f"ردیف {row_number}: {exc}")

    if errors:
        preview = " | ".join(errors[:10])
        raise ReconciliationInputError(
            f"فایل دارای {len(errors)} ردیف نامعتبر است: {preview}"
        )
    if not parsed_rows:
        raise ReconciliationInputError("هیچ واریز یا برداشتی در فایل پیدا نشد.")

    detected_columns = {
        name: (
            str(headers[index])
            if index is not None
            else None
        )
        for name, index in indexes.items()
    }
    metadata = _extract_statement_metadata(rows, header_row)
    metadata["statement_bank_name"] = _detect_statement_bank_name(
        filename,
        selected_sheet,
        rows,
    )
    return parsed_rows, {
        "filename": Path(filename).name,
        "sheet_name": selected_sheet,
        "header_row": header_row,
        "detected_columns": detected_columns,
        **metadata,
    }


def _transaction_date_candidates(transaction: dict[str, Any]) -> Iterable[date]:
    for key in ("booking_date", "settlement_date"):
        value = transaction.get(key)
        if isinstance(value, datetime):
            yield value.date()
        elif isinstance(value, date):
            yield value


def _description_similarity(left: str, right: str) -> float:
    left_tokens = set(_normalize_text(left).split())
    right_tokens = set(_normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _closest_day_difference(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> int | None:
    available_dates = list(_transaction_date_candidates(transaction))
    if not available_dates:
        return None
    return min(
        abs((candidate_date - bank_row["date"]).days)
        for candidate_date in available_dates
    )


def _cheque_serial_matches(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    """Match the cheque serial itself, excluding generic bank references."""

    if transaction.get("transaction_type") not in {
        "received_cheque_status",
        "issued_cheque_status",
    }:
        return False
    bank_text = _normalize_text(
        " ".join(
            str(bank_row.get(key, ""))
            for key in (
                "description",
                "reference",
                "bank_document_number",
                "deposit_id",
                "cheque_number",
            )
        )
    ).replace(" ", "")
    item_tokens = {
        token
        for token in re.findall(r"\d{5,}", str(transaction.get("item_number") or ""))
        if len(token) <= 20
    }
    return any(token in bank_text for token in item_tokens)


def _reference_matches(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    references = {
        _normalize_text(bank_row.get(key, ""))
        for key in (
            "reference",
            "bank_document_number",
            "deposit_id",
            "cheque_number",
        )
    }
    references = {
        reference
        for reference in references
        if len(reference.replace(" ", "")) >= 4
    }
    searchable_values = {
        _normalize_text(value)
        for value in (
            transaction.get("description"),
            transaction.get("reference_ref"),
        )
        if value not in (None, "")
    }
    if any(
        reference in searchable
        for reference in references
        for searchable in searchable_values
    ):
        return True

    # در برخی صورت‌حساب‌ها (از جمله بانک شهر) سریال چک ستون مستقل ندارد
    # و در میانه شرح بانک چسبیده به تاریخ قرار می‌گیرد. سریال ثبت‌شده در
    # راهکاران را از ItemNumber می‌گیریم و به‌صورت زیررشته در متن بانک می‌جوییم.
    return _cheque_serial_matches(bank_row, transaction)


def _bank_identity_text(bank_row: dict[str, Any]) -> str:
    return " ".join(
        value
        for value in (
            str(bank_row.get("payer", "")),
            str(bank_row.get("origin_account", "")),
            str(bank_row.get("operation", "")),
            str(bank_row.get("description", "")),
            str(bank_row.get("note", "")),
        )
        if value
    )


def _is_bank_cheque_event(bank_row: dict[str, Any]) -> bool:
    """Return true only for bank rows that explicitly describe a cheque event."""

    normalized = _normalize_text(
        " ".join(
            str(bank_row.get(key, ""))
            for key in ("description", "operation", "note")
        )
    )
    cheque_phrases = (
        "تعین وضعیت چک",
        "تعیین وضعیت چک",
        "وصول چک",
        "نقد کردن چک",
        "برداشت وجه چک",
        "پرداخت انتقالی چک",
        "پرداخت چک",
    )
    return any(phrase in normalized for phrase in cheque_phrases)


def _is_bank_issued_cheque_event(bank_row: dict[str, Any]) -> bool:
    if bank_row.get("direction") != "withdrawal":
        return False
    normalized = _normalize_text(
        " ".join(
            str(bank_row.get(key, ""))
            for key in ("description", "operation", "note")
        )
    )
    issued_phrases = (
        "برداشت وجه چک",
        "پرداخت انتقالی چک",
        "پرداخت چک",
        "وصول چک شماره",
    )
    return any(phrase in normalized for phrase in issued_phrases)


def _transaction_type_is_compatible(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    # وصول چک نباید صرفاً به دلیل برابری مبلغ و تاریخ به واریز پایا، ساتنا
    # یا انتقال عادی متصل شود.
    if transaction.get("transaction_type") == "received_cheque_status":
        return _is_bank_cheque_event(bank_row)
    if transaction.get("transaction_type") == "issued_cheque_status":
        return _is_bank_issued_cheque_event(bank_row)
    return True


def _candidate_score(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
    tolerance_days: int,
) -> tuple[int, list[str]] | None:
    if not _transaction_type_is_compatible(bank_row, transaction):
        return None
    expected_effect = 1 if bank_row["direction"] == "deposit" else 2
    if transaction["effect"] != expected_effect:
        return None
    if abs(transaction["amount"] - bank_row["amount"]) > Decimal("0.01"):
        return None

    day_difference = _closest_day_difference(bank_row, transaction)
    if day_difference is None:
        return None
    cheque_serial_match = _cheque_serial_matches(bank_row, transaction)
    # تاریخ ثبت تغییر وضعیت چک صادرشده در راهکاران همیشه تاریخ برداشت بانک
    # نیست. در نمونه واقعی بانک تجارت، ثبت وضعیت تا ۳۷ روز بعد انجام شده است.
    # وقتی حساب، جهت، مبلغ و سریال چک همگی دقیق‌اند، فاصله زمانی تا ۴۵ روز
    # پذیرفته می‌شود؛ برای سایر تراکنش‌ها همان تلورانس انتخابی کاربر می‌ماند.
    allowed_days = max(tolerance_days, 45) if cheque_serial_match else tolerance_days
    if day_difference > allowed_days:
        return None

    score = 60
    reasons = ["مبلغ و جهت تراکنش برابر است"]
    if day_difference == 0:
        score += 30
        reasons.append("تاریخ دقیقاً برابر است")
    elif day_difference == 1:
        score += 20
        reasons.append("اختلاف تاریخ یک روز است")
    else:
        score += 10
        reasons.append(f"اختلاف تاریخ {day_difference} روز است")

    if cheque_serial_match:
        score += 25
        reasons.append("سریال چک دقیقاً در اطلاعات راهکاران پیدا شد")
    elif _reference_matches(bank_row, transaction):
        score += 10
        reasons.append(
            "سریال یا شناسه چک در اطلاعات راهکاران پیدا شد"
            if transaction.get("transaction_type") == "received_cheque_status"
            else "شماره پیگیری در اطلاعات سند پیدا شد"
        )

    similarity = _description_similarity(
        _bank_identity_text(bank_row),
        transaction["description"],
    )
    if similarity >= 0.60:
        score += 10
        reasons.append("شرح بانک و سند شباهت زیاد دارد")
    elif similarity >= 0.30:
        score += 5
        reasons.append("شرح بانک و سند تا حدی مشابه است")

    return min(score, 100), reasons


def _review_candidate_score(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
    tolerance_days: int,
) -> tuple[int, list[str]] | None:
    """پیشنهاد مورد مشکوک برای بررسی انسانی، بدون تأیید خودکار سند."""

    expected_effect = 1 if bank_row["direction"] == "deposit" else 2
    if transaction["effect"] != expected_effect:
        return None

    day_difference = _closest_day_difference(bank_row, transaction)
    if day_difference is None or day_difference > tolerance_days:
        return None

    # بعضی واریزهای وصول چک در متن بانک به شکل «انتقال وجه» دیده می‌شوند.
    # این موارد نباید خودکار سندخورده شوند، ولی برابری مبلغ و نزدیکی تاریخ
    # برای نمایش آن‌ها در صف بررسی انسانی کافی است.
    if (
        transaction.get("transaction_type") == "received_cheque_status"
        and not _is_bank_cheque_event(bank_row)
    ):
        amount_difference = abs(transaction["amount"] - bank_row["amount"])
        if amount_difference > Decimal("0.01"):
            return None
        score = 72 if day_difference == 0 else 68 if day_difference == 1 else 64
        return score, [
            "مبلغ و جهت با رویداد وصول چک راهکاران برابر است",
            (
                "تاریخ دقیقاً برابر است"
                if day_difference == 0
                else f"اختلاف تاریخ {day_difference} روز است"
            ),
            "شرح بانک انتقال وجه است؛ تأیید خزانه برای تشخیص وصول چک لازم است",
        ]

    if not _transaction_type_is_compatible(bank_row, transaction):
        return None

    reference_match = _reference_matches(bank_row, transaction)
    similarity = _description_similarity(
        _bank_identity_text(bank_row),
        transaction["description"],
    )
    if not reference_match and similarity < 0.30:
        return None

    amount_difference = abs(transaction["amount"] - bank_row["amount"])
    if amount_difference <= Decimal("0.01"):
        return None

    score = 45
    reasons = [
        "مبلغ بانک و سند برابر نیست؛ احتمال پرداخت ناقص، تجمیعی یا اصلاح مبلغ وجود دارد"
    ]
    if day_difference == 0:
        score += 15
        reasons.append("تاریخ برابر است")
    elif day_difference == 1:
        score += 10
        reasons.append("اختلاف تاریخ یک روز است")
    else:
        score += 5
        reasons.append(f"اختلاف تاریخ {day_difference} روز است")

    if reference_match:
        score += 20
        reasons.append(
            "سریال یا شناسه چک در اطلاعات راهکاران پیدا شد"
            if transaction.get("transaction_type") == "received_cheque_status"
            else "شماره پیگیری در اطلاعات سند پیدا شد"
        )
    if similarity >= 0.60:
        score += 10
        reasons.append("شرح بانک و سند شباهت زیاد دارد")
    elif similarity >= 0.30:
        score += 5
        reasons.append("شرح بانک و سند تا حدی مشابه است")

    return min(score, 89), reasons


def _serialize_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_id": transaction["transaction_id"],
        "booking_date": (
            transaction["booking_date"].isoformat()
            if transaction["booking_date"]
            else None
        ),
        "settlement_date": (
            transaction["settlement_date"].isoformat()
            if transaction["settlement_date"]
            else None
        ),
        "amount": float(transaction["amount"]),
        "entry_amount": float(transaction.get("entry_amount", transaction["amount"])),
        "gl_amount": float(transaction.get("gl_amount", 0)),
        "amount_source": transaction.get("amount_source", "entry_amount"),
        "effect": transaction["effect"],
        "description": transaction["description"],
        "reference_component": transaction["reference_component"],
        "reference_entity": transaction["reference_entity"],
        "reference_ref": transaction["reference_ref"],
        "transaction_type": transaction.get("transaction_type"),
        "item_id": transaction.get("item_id"),
        "document_id": transaction.get("document_id"),
        "document_number": transaction.get("document_number"),
        "item_number": transaction.get("item_number"),
        "counterpart_account_ref": transaction.get("counterpart_account_ref"),
        "counterpart_account_name": transaction.get("counterpart_account_name"),
        "member_transaction_ids": transaction.get("member_transaction_ids", []),
    }


def _is_fee_text(value: Any) -> bool:
    normalized = _normalize_text(str(value or ""))
    # در خروجی بانک شهر بعضی هزینه‌های بانکی واژه «کارمزد» ندارند، اما
    # راهکاران همه آن‌ها را در یک سند روزانه کارمزد ثبت می‌کند.
    fee_descriptions = (
        "کارمزد",
        "بابت ثبت چک",
        "ثبت چک ش ص",
        "درخواست ابطال برگ چک",
        "نگهداری امانی چک",
        "انتقال وجه بین بانکی ساتنا حضوری",
        "دستور پرداخت سمت متعهد",
        "هزینه حسابرسی",
    )
    return any(description in normalized for description in fee_descriptions)


def _is_reversal_text(value: Any) -> bool:
    normalized = _normalize_text(str(value or ""))
    return any(
        marker in normalized
        for marker in ("برگشت عملیات", "بازگشت عملیات", "سند اصلاحی")
    )


def _reversal_base_text(value: Any) -> str:
    normalized = _normalize_text(str(value or ""))
    # برخی خروجی‌های بانک سپه در ابتدای شرح «برگشت عملیات» و در انتهای همان
    # شرح «بازگشت عملیات» می‌نویسند. هر دو عبارت باید حذف شوند تا متن پایه با
    # برداشت اصلی مقایسه شود.
    for marker in (
        "برگشت عملیات",
        "بازگشت عملیات",
        "سند اصلاحی",
        "طرف بستانکار",
        "طرف بدهکار",
    ):
        normalized = normalized.replace(marker, " ")
    return " ".join(normalized.split()).strip(" |-")


def _match_bank_reversal_pairs(
    bank_rows: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Pair a bank reversal deposit with its original same-day withdrawal."""

    results: dict[int, dict[str, Any]] = {}
    used_withdrawals: set[int] = set()
    for reversal_index, reversal in enumerate(bank_rows):
        if reversal.get("direction") != "deposit" or not _is_reversal_text(
            reversal.get("description")
        ):
            continue
        reversal_base = _reversal_base_text(reversal.get("description"))
        candidates: list[tuple[int, float, int, dict[str, Any]]] = []
        for withdrawal_index, withdrawal in enumerate(bank_rows):
            if withdrawal_index in used_withdrawals:
                continue
            if withdrawal.get("direction") != "withdrawal":
                continue
            if withdrawal.get("date") != reversal.get("date"):
                continue
            if abs(withdrawal["amount"] - reversal["amount"]) > Decimal("0.01"):
                continue
            withdrawal_text = _normalize_text(withdrawal.get("description"))
            similarity = _description_similarity(reversal_base, withdrawal_text)
            identifier_match = any(
                reversal.get(key)
                and reversal.get(key) == withdrawal.get(key)
                for key in ("reference", "bank_document_number")
            )
            reversal_tokens = set(
                re.findall(r"\d{6,}", _normalize_text(reversal.get("description")))
            )
            withdrawal_tokens = set(
                re.findall(r"\d{6,}", withdrawal_text)
            )
            token_match = bool(reversal_tokens & withdrawal_tokens)
            if (
                identifier_match
                or token_match
                or (
                    reversal_base
                    and (
                    reversal_base in withdrawal_text
                    or withdrawal_text in reversal_base
                    or similarity >= 0.60
                    )
                )
            ):
                strength = 3 if identifier_match else 2 if token_match else 1
                candidates.append(
                    (strength, similarity, withdrawal_index, withdrawal)
                )
        if not candidates:
            continue
        candidates.sort(
            key=lambda candidate: (candidate[0], candidate[1]),
            reverse=True,
        )
        if (
            len(candidates) > 1
            and candidates[0][0] == 1
            and candidates[1][0] == 1
            and candidates[1][1] >= candidates[0][1] - 0.05
        ):
            continue

        _, _, withdrawal_index, withdrawal = candidates[0]
        used_withdrawals.add(withdrawal_index)
        group_id = f"bank_reversal:{reversal['row_number']}:{withdrawal['row_number']}"
        for index, bank_row, counterpart in (
            (reversal_index, reversal, withdrawal),
            (withdrawal_index, withdrawal, reversal),
        ):
            results[index] = {
                "row_number": bank_row["row_number"],
                "bank_date": bank_row["date"].isoformat(),
                "amount": float(bank_row["amount"]),
                "direction": bank_row["direction"],
                "description": bank_row["description"],
                "reference": bank_row.get("reference", ""),
                "payer": bank_row.get("payer", ""),
                "origin_account": bank_row.get("origin_account", ""),
                "operation": bank_row.get("operation", ""),
                "time": bank_row.get("time", ""),
                "bank_document_number": bank_row.get("bank_document_number", ""),
                "deposit_id": bank_row.get("deposit_id", ""),
                "note": bank_row.get("note", ""),
                "branch": bank_row.get("branch", ""),
                "cheque_number": bank_row.get("cheque_number", ""),
                "balance": (
                    float(bank_row["balance"])
                    if bank_row.get("balance") is not None
                    else None
                ),
                "match_status": "reversed",
                "business_status": "reversed",
                "business_status_fa": "برگشت/خنثی‌شده",
                "confidence": 100,
                "reasons": [
                    "برداشت و برگشت بانکی با مبلغ و تاریخ یکسان جفت شدند",
                    f"ردیف متناظر فایل بانک: {counterpart['row_number']}",
                ],
                "match_method": "bank_reversal_pair",
                "match_group_id": group_id,
                "match_group_row_count": 2,
                "match_group_bank_total": 0.0,
                "match_group_document_total": None,
                "amount_difference": 0.0,
                "date_difference_days": 0,
                "matched_transaction": None,
                "alternative_candidates": [],
            }
    # اگر چند برداشت و چند برگشت کاملاً هم‌مبلغ و هم‌شرح باشند، انتخاب ردیف
    # متناظر در سطح فردی اهمیتی ندارد. در این حالت کل گروه را خنثی می‌کنیم.
    remaining_reversals: dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]] = {}
    for index, bank_row in enumerate(bank_rows):
        if index in results:
            continue
        if bank_row.get("direction") != "deposit" or not _is_reversal_text(
            bank_row.get("description")
        ):
            continue
        key = (
            bank_row.get("date"),
            bank_row.get("amount"),
            _reversal_base_text(bank_row.get("description")),
        )
        remaining_reversals.setdefault(key, []).append((index, bank_row))

    for (bank_date, amount, base_text), reversals in remaining_reversals.items():
        withdrawals = [
            (index, bank_row)
            for index, bank_row in enumerate(bank_rows)
            if index not in results
            and index not in used_withdrawals
            and bank_row.get("direction") == "withdrawal"
            and bank_row.get("date") == bank_date
            and abs(bank_row["amount"] - amount) <= Decimal("0.01")
            and (
                base_text in _normalize_text(bank_row.get("description"))
                or _description_similarity(
                    base_text,
                    _normalize_text(bank_row.get("description")),
                )
                >= 0.60
            )
        ]
        if not reversals or len(reversals) != len(withdrawals):
            continue

        reversals.sort(key=lambda item: item[1]["row_number"])
        withdrawals.sort(key=lambda item: item[1]["row_number"])
        group_id = f"bank_reversal_batch:{bank_date.isoformat()}:{amount}"
        for (reversal_index, reversal), (withdrawal_index, withdrawal) in zip(
            reversals,
            withdrawals,
        ):
            used_withdrawals.add(withdrawal_index)
            for index, bank_row, counterpart in (
                (reversal_index, reversal, withdrawal),
                (withdrawal_index, withdrawal, reversal),
            ):
                results[index] = {
                    "row_number": bank_row["row_number"],
                    "bank_date": bank_row["date"].isoformat(),
                    "amount": float(bank_row["amount"]),
                    "direction": bank_row["direction"],
                    "description": bank_row["description"],
                    "reference": bank_row.get("reference", ""),
                    "payer": bank_row.get("payer", ""),
                    "origin_account": bank_row.get("origin_account", ""),
                    "operation": bank_row.get("operation", ""),
                    "time": bank_row.get("time", ""),
                    "bank_document_number": bank_row.get("bank_document_number", ""),
                    "deposit_id": bank_row.get("deposit_id", ""),
                    "note": bank_row.get("note", ""),
                    "branch": bank_row.get("branch", ""),
                    "cheque_number": bank_row.get("cheque_number", ""),
                    "balance": (
                        float(bank_row["balance"])
                        if bank_row.get("balance") is not None
                        else None
                    ),
                    "match_status": "reversed",
                    "business_status": "reversed",
                    "business_status_fa": "برگشت/خنثی‌شده",
                    "confidence": 100,
                    "reasons": [
                        "تعداد، مبلغ، تاریخ و شرح گروه برداشت و برگشت برابر است",
                        f"ردیف متناظر فایل بانک: {counterpart['row_number']}",
                    ],
                    "match_method": "bank_reversal_batch",
                    "match_group_id": group_id,
                    "match_group_row_count": len(reversals) * 2,
                    "match_group_bank_total": 0.0,
                    "match_group_document_total": None,
                    "amount_difference": 0.0,
                    "date_difference_days": 0,
                    "matched_transaction": None,
                    "alternative_candidates": [],
                }

    return results


def _aggregate_fee_documents(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate fee payment items that belong to one Rahkaran document."""

    document_groups: dict[Any, list[dict[str, Any]]] = {}
    for transaction in transactions:
        if transaction.get("transaction_type") != "payment":
            continue
        document_key = transaction.get("document_id")
        if document_key is None:
            document_key = transaction["transaction_id"]
        document_groups.setdefault(document_key, []).append(transaction)

    aggregates: list[dict[str, Any]] = []
    for document_key, members in document_groups.items():
        if not members or not all(
            _is_fee_text(member.get("description")) for member in members
        ):
            continue
        first = members[0]
        descriptions = list(
            dict.fromkeys(
                str(member.get("description") or "")
                for member in members
                if member.get("description")
            )
        )
        aggregates.append(
            {
                **first,
                "transaction_id": f"fee_document:{document_key}",
                "item_id": None,
                "item_number": ", ".join(
                    str(member.get("item_number") or "")
                    for member in members
                    if member.get("item_number") not in (None, "")
                ),
                "amount": sum(
                    (member["amount"] for member in members),
                    Decimal("0"),
                ),
                "entry_amount": sum(
                    (
                        member.get("entry_amount", member["amount"])
                        for member in members
                    ),
                    Decimal("0"),
                ),
                "gl_amount": sum(
                    (member.get("gl_amount", Decimal("0")) for member in members),
                    Decimal("0"),
                ),
                "description": " | ".join(descriptions),
                "member_transaction_ids": [
                    member["transaction_id"] for member in members
                ],
            }
        )
    return aggregates


def _match_daily_fee_groups(
    bank_rows: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    excluded_indexes: set[int] | None = None,
) -> tuple[dict[int, dict[str, Any]], set[Any]]:
    """Match multiple same-day bank fees to one exact Rahkaran fee document."""

    bank_groups: dict[date, list[tuple[int, dict[str, Any]]]] = {}
    excluded = excluded_indexes or set()
    for index, bank_row in enumerate(bank_rows):
        if index in excluded:
            continue
        if (
            bank_row.get("direction") == "withdrawal"
            and _is_fee_text(bank_row.get("description"))
        ):
            bank_groups.setdefault(bank_row["date"], []).append((index, bank_row))

    fee_documents = _aggregate_fee_documents(transactions)
    results: dict[int, dict[str, Any]] = {}
    used_transactions: set[Any] = set()

    for bank_date, original_group in bank_groups.items():
        group = list(original_group)
        date_documents = [
            document
            for document in fee_documents
            if _closest_day_difference({"date": bank_date}, document) == 0
            and not set(document.get("member_transaction_ids", []))
            & used_transactions
        ]
        sequence = 0

        def store_group_result(
            matched_group: list[tuple[int, dict[str, Any]]],
            selected: dict[str, Any],
            alternatives: list[dict[str, Any]],
        ) -> None:
            nonlocal sequence
            sequence += 1
            is_ambiguous = bool(alternatives)
            status = "possible_match" if is_ambiguous else "matched"
            business_status = "needs_review" if is_ambiguous else "posted"
            confidence = 85 if is_ambiguous else 98
            group_total = sum(
                (bank_row["amount"] for _, bank_row in matched_group),
                Decimal("0"),
            )
            group_id = f"daily_fee:{bank_date.isoformat()}:{sequence}"
            reasons = [
                (
                    "کارمزد بانکی به سند مستقل همان روز متصل شد"
                    if len(matched_group) == 1
                    else "برداشت‌های دارای شرح کارمزد در همان روز به‌صورت گروهی جمع شدند"
                ),
                "جمع کارمزدهای بانک با مبلغ سند کارمزد راهکاران برابر است",
            ]
            if is_ambiguous:
                reasons.append("بیش از یک سند کارمزد با جمع یکسان پیدا شد")
            else:
                used_transactions.update(
                    selected.get("member_transaction_ids", [])
                )

            for index, bank_row in matched_group:
                results[index] = {
                    "row_number": bank_row["row_number"],
                    "bank_date": bank_row["date"].isoformat(),
                    "amount": float(bank_row["amount"]),
                    "direction": bank_row["direction"],
                    "description": bank_row["description"],
                    "reference": bank_row.get("reference", ""),
                    "payer": bank_row.get("payer", ""),
                    "origin_account": bank_row.get("origin_account", ""),
                    "operation": bank_row.get("operation", ""),
                    "time": bank_row.get("time", ""),
                    "bank_document_number": bank_row.get("bank_document_number", ""),
                    "deposit_id": bank_row.get("deposit_id", ""),
                    "note": bank_row.get("note", ""),
                    "branch": bank_row.get("branch", ""),
                    "cheque_number": bank_row.get("cheque_number", ""),
                    "balance": (
                        float(bank_row["balance"])
                        if bank_row.get("balance") is not None
                        else None
                    ),
                    "match_status": status,
                    "business_status": business_status,
                    "business_status_fa": (
                        "نیازمند بررسی" if is_ambiguous else "سندخورده"
                    ),
                    "confidence": confidence,
                    "reasons": reasons,
                    "match_method": "daily_fee_group",
                    "match_group_id": group_id,
                    "match_group_row_count": len(matched_group),
                    "match_group_bank_total": float(group_total),
                    "match_group_document_total": float(selected["amount"]),
                    "amount_difference": 0.0,
                    "date_difference_days": 0,
                    "matched_transaction": _serialize_transaction(selected),
                    "alternative_candidates": [
                        {
                            "confidence": 85,
                            **_serialize_transaction(candidate),
                        }
                        for candidate in alternatives[:3]
                    ],
                }

        while group and date_documents:
            group_total = sum(
                (bank_row["amount"] for _, bank_row in group),
                Decimal("0"),
            )
            full_group_candidates = [
                document
                for document in date_documents
                if abs(document["amount"] - group_total) <= Decimal("0.01")
            ]
            if full_group_candidates:
                selected = full_group_candidates[0]
                store_group_result(
                    group,
                    selected,
                    full_group_candidates[1:],
                )
                if len(full_group_candidates) == 1:
                    date_documents.remove(selected)
                break

            # گاهی یک کارمزد سند مستقل دارد و بقیه کارمزدهای همان روز در یک
            # سند تجمیعی ثبت شده‌اند. ابتدا جفت مبلغ یکتای مستقل را جدا می‌کنیم
            # و سپس جمع باقی‌مانده را دوباره می‌سنجیم.
            unique_pair: tuple[
                tuple[int, dict[str, Any]],
                dict[str, Any],
            ] | None = None
            for bank_item in group:
                same_amount_rows = [
                    item
                    for item in group
                    if abs(item[1]["amount"] - bank_item[1]["amount"])
                    <= Decimal("0.01")
                ]
                same_amount_documents = [
                    document
                    for document in date_documents
                    if abs(document["amount"] - bank_item[1]["amount"])
                    <= Decimal("0.01")
                ]
                if len(same_amount_rows) == 1 and len(same_amount_documents) == 1:
                    unique_pair = (bank_item, same_amount_documents[0])
                    break

            if unique_pair is None:
                break
            bank_item, selected = unique_pair
            store_group_result([bank_item], selected, [])
            group.remove(bank_item)
            date_documents.remove(selected)

    return results, used_transactions


def _build_batch_match_result(
    bank_row: dict[str, Any],
    candidate: dict[str, Any],
    *,
    method: str,
    group_id: str,
    group_row_count: int,
    group_bank_total: Decimal,
    group_document_total: Decimal,
    confidence: int,
    reasons: list[str],
) -> dict[str, Any]:
    transaction = candidate["transaction"]
    day_difference = _closest_day_difference(bank_row, transaction)
    return {
        "row_number": bank_row["row_number"],
        "bank_date": bank_row["date"].isoformat(),
        "amount": float(bank_row["amount"]),
        "direction": bank_row["direction"],
        "description": bank_row["description"],
        "reference": bank_row.get("reference", ""),
        "payer": bank_row.get("payer", ""),
        "origin_account": bank_row.get("origin_account", ""),
        "operation": bank_row.get("operation", ""),
        "time": bank_row.get("time", ""),
        "bank_document_number": bank_row.get("bank_document_number", ""),
        "deposit_id": bank_row.get("deposit_id", ""),
        "note": bank_row.get("note", ""),
        "branch": bank_row.get("branch", ""),
        "cheque_number": bank_row.get("cheque_number", ""),
        "balance": (
            float(bank_row["balance"])
            if bank_row.get("balance") is not None
            else None
        ),
        "match_status": "matched",
        "business_status": "posted",
        "business_status_fa": "سندخورده",
        "confidence": confidence,
        "reasons": reasons,
        "match_method": method,
        "match_group_id": group_id,
        "match_group_row_count": group_row_count,
        "match_group_bank_total": float(group_bank_total),
        "match_group_document_total": float(group_document_total),
        "amount_difference": 0.0,
        "date_difference_days": day_difference,
        "matched_transaction": _serialize_transaction(transaction),
        "alternative_candidates": [],
    }


def _perfect_candidate_assignment(
    bank_indexes: list[int],
    candidates_by_row: dict[int, list[dict[str, Any]]],
    used_transactions: set[Any],
    *,
    exact_date_only: bool,
    minimum_score: int,
) -> dict[int, dict[str, Any]] | None:
    """Return a one-to-one assignment when every bank row can consume one ERP row."""

    eligible: dict[int, list[dict[str, Any]]] = {}
    for index in bank_indexes:
        choices = [
            candidate
            for candidate in candidates_by_row.get(index, [])
            if candidate["transaction"]["transaction_id"] not in used_transactions
            and candidate["score"] >= minimum_score
            and (
                not exact_date_only
                or _closest_day_difference(
                    {"date": candidate.get("bank_date")},
                    candidate["transaction"],
                )
                == 0
            )
        ]
        if not choices:
            return None
        eligible[index] = choices

    transaction_to_bank: dict[Any, int] = {}
    selected_by_bank: dict[int, dict[str, Any]] = {}

    def assign(bank_index: int, visited: set[Any]) -> bool:
        for candidate in eligible[bank_index]:
            transaction_id = candidate["transaction"]["transaction_id"]
            if transaction_id in visited:
                continue
            visited.add(transaction_id)
            previous_bank = transaction_to_bank.get(transaction_id)
            if previous_bank is None or assign(previous_bank, visited):
                transaction_to_bank[transaction_id] = bank_index
                selected_by_bank[bank_index] = candidate
                return True
        return False

    ordered_indexes = sorted(
        bank_indexes,
        key=lambda index: (
            len(eligible[index]),
            -max(candidate["score"] for candidate in eligible[index]),
        ),
    )
    for index in ordered_indexes:
        if not assign(index, set()):
            return None
    return selected_by_bank


def _match_exact_date_amount_groups(
    bank_rows: list[dict[str, Any]],
    candidates_by_row: dict[int, list[dict[str, Any]]],
    results_by_index: dict[int, dict[str, Any]],
    used_transactions: set[Any],
) -> None:
    """Resolve same-day equal-amount ambiguity as a balanced batch."""

    groups: dict[tuple[Any, ...], list[int]] = {}
    for index, bank_row in enumerate(bank_rows):
        if index in results_by_index:
            continue
        key = (bank_row["date"], bank_row["direction"], bank_row["amount"])
        groups.setdefault(key, []).append(index)

    for (bank_date, direction, amount), indexes in groups.items():
        if len(indexes) < 2:
            continue
        exact_candidates = {
            candidate["transaction"]["transaction_id"]
            for index in indexes
            for candidate in candidates_by_row.get(index, [])
            if candidate["transaction"]["transaction_id"] not in used_transactions
            and _closest_day_difference(bank_rows[index], candidate["transaction"])
            == 0
        }
        if len(exact_candidates) != len(indexes):
            continue

        enriched_candidates = {
            index: [
                {**candidate, "bank_date": bank_rows[index]["date"]}
                for candidate in candidates_by_row.get(index, [])
            ]
            for index in indexes
        }
        assignment = _perfect_candidate_assignment(
            indexes,
            enriched_candidates,
            used_transactions,
            exact_date_only=True,
            minimum_score=90,
        )
        if assignment is None:
            continue

        group_total = amount * len(indexes)
        group_id = (
            f"same_day_amount:{bank_date.isoformat()}:{direction}:{amount}"
        )
        reasons = [
            "چند تراکنش هم‌مبلغ در همان روز به‌صورت گروهی بررسی شدند",
            "تعداد و مجموعه مبالغ بانک و راهکاران کاملاً برابر است",
            "هر ردیف راهکاران فقط یک‌بار مصرف شد",
        ]
        for index, candidate in assignment.items():
            transaction_id = candidate["transaction"]["transaction_id"]
            used_transactions.add(transaction_id)
            results_by_index[index] = _build_batch_match_result(
                bank_rows[index],
                candidate,
                method="same_day_amount_batch",
                group_id=group_id,
                group_row_count=len(indexes),
                group_bank_total=group_total,
                group_document_total=group_total,
                confidence=96,
                reasons=reasons,
            )


def _match_tolerance_amount_components(
    bank_rows: list[dict[str, Any]],
    candidates_by_row: dict[int, list[dict[str, Any]]],
    results_by_index: dict[int, dict[str, Any]],
    used_transactions: set[Any],
) -> None:
    """Resolve a fully balanced one-to-one component inside the date tolerance."""

    remaining_indexes = [
        index
        for index in range(len(bank_rows))
        if index not in results_by_index
        and any(
            candidate["transaction"]["transaction_id"] not in used_transactions
            and candidate["score"] >= 80
            for candidate in candidates_by_row.get(index, [])
        )
    ]
    row_edges: dict[int, set[Any]] = {
        index: {
            candidate["transaction"]["transaction_id"]
            for candidate in candidates_by_row.get(index, [])
            if candidate["transaction"]["transaction_id"] not in used_transactions
            and candidate["score"] >= 80
        }
        for index in remaining_indexes
    }
    transaction_edges: dict[Any, set[int]] = {}
    for index, transaction_ids in row_edges.items():
        for transaction_id in transaction_ids:
            transaction_edges.setdefault(transaction_id, set()).add(index)

    visited_rows: set[int] = set()
    for start_index in remaining_indexes:
        if start_index in visited_rows:
            continue
        component_rows: set[int] = set()
        component_transactions: set[Any] = set()
        row_stack = [start_index]
        while row_stack:
            index = row_stack.pop()
            if index in component_rows:
                continue
            component_rows.add(index)
            visited_rows.add(index)
            for transaction_id in row_edges.get(index, set()):
                if transaction_id in component_transactions:
                    continue
                component_transactions.add(transaction_id)
                row_stack.extend(transaction_edges.get(transaction_id, set()))

        if len(component_rows) < 2 or len(component_rows) != len(
            component_transactions
        ):
            continue
        indexes = sorted(component_rows)
        assignment = _perfect_candidate_assignment(
            indexes,
            candidates_by_row,
            used_transactions,
            exact_date_only=False,
            minimum_score=80,
        )
        if assignment is None:
            continue

        bank_total = sum(
            (bank_rows[index]["amount"] for index in indexes),
            Decimal("0"),
        )
        document_total = sum(
            (
                candidate["transaction"]["amount"]
                for candidate in assignment.values()
            ),
            Decimal("0"),
        )
        if abs(bank_total - document_total) > Decimal("0.01"):
            continue

        group_id = f"tolerance_batch:{indexes[0]}:{indexes[-1]}"
        reasons = [
            "گروه تراکنش‌ها در بازه مجاز تاریخ به‌صورت یکجا بررسی شد",
            "تعداد و مجموع مبالغ بانک و راهکاران برابر است",
            "تخصیص یکتای کامل برای تمام ردیف‌های گروه پیدا شد",
        ]
        for index, candidate in assignment.items():
            used_transactions.add(candidate["transaction"]["transaction_id"])
            results_by_index[index] = _build_batch_match_result(
                bank_rows[index],
                candidate,
                method="tolerance_amount_batch",
                group_id=group_id,
                group_row_count=len(indexes),
                group_bank_total=bank_total,
                group_document_total=document_total,
                confidence=92,
                reasons=reasons,
            )


def _bank_row_fingerprint(bank_row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        bank_row["date"],
        bank_row["amount"],
        bank_row["direction"],
        _normalize_text(bank_row["reference"]),
        _normalize_text(bank_row["description"]),
    )


def _match_bank_rows(
    bank_rows: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    tolerance_days: int,
) -> tuple[list[dict[str, Any]], set[Any]]:
    internal_transfer_types = {"bank_transfer_in", "bank_transfer_out"}
    internal_transfers = [
        transaction
        for transaction in transactions
        if transaction.get("transaction_type") in internal_transfer_types
    ]
    # انتقال بین حساب‌های خود شرکت یک وضعیت مستقل است: نه سندخورده است و نه
    # بدون سند. این رکوردها فقط برای تشخیص انتقال داخلی نگه داشته می‌شوند و
    # نباید وارد موتور تطبیق اسناد عادی شوند.
    matchable_transactions = [
        transaction
        for transaction in transactions
        if transaction.get("transaction_type") not in internal_transfer_types
    ]
    candidates_by_row: dict[int, list[dict[str, Any]]] = {}
    review_candidates_by_row: dict[int, list[dict[str, Any]]] = {}
    fingerprint_counts: dict[tuple[Any, ...], int] = {}
    for bank_row in bank_rows:
        fingerprint = _bank_row_fingerprint(bank_row)
        fingerprint_counts[fingerprint] = fingerprint_counts.get(fingerprint, 0) + 1

    for index, bank_row in enumerate(bank_rows):
        candidates = []
        review_candidates = []
        for transaction in matchable_transactions:
            scored = _candidate_score(bank_row, transaction, tolerance_days)
            if scored is not None:
                score, reasons = scored
                candidates.append(
                    {
                        "transaction": transaction,
                        "score": score,
                        "reasons": reasons,
                    }
                )
                continue

            review_scored = _review_candidate_score(
                bank_row,
                transaction,
                tolerance_days,
            )
            if review_scored is not None:
                score, reasons = review_scored
                review_candidates.append(
                    {
                        "transaction": transaction,
                        "score": score,
                        "reasons": reasons,
                    }
                )
        candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
        review_candidates.sort(
            key=lambda candidate: candidate["score"],
            reverse=True,
        )
        candidates_by_row[index] = candidates
        review_candidates_by_row[index] = review_candidates

    results_by_index = _match_bank_reversal_pairs(bank_rows)
    fee_results, used_transactions = _match_daily_fee_groups(
        bank_rows,
        matchable_transactions,
        excluded_indexes=set(results_by_index),
    )
    results_by_index.update(fee_results)
    _match_exact_date_amount_groups(
        bank_rows,
        candidates_by_row,
        results_by_index,
        used_transactions,
    )
    _match_tolerance_amount_components(
        bank_rows,
        candidates_by_row,
        results_by_index,
        used_transactions,
    )
    processing_order = sorted(
        range(len(bank_rows)),
        key=lambda index: (
            candidates_by_row[index][0]["score"]
            if candidates_by_row[index]
            else -1,
            -len(candidates_by_row[index]),
        ),
        reverse=True,
    )

    for index in processing_order:
        if index in results_by_index:
            continue
        bank_row = bank_rows[index]
        all_candidates = candidates_by_row[index]
        candidates = [
            candidate
            for candidate in all_candidates
            if candidate["transaction"]["transaction_id"]
            not in used_transactions
        ]

        status = "unmatched"
        confidence = 0
        selected: dict[str, Any] | None = None
        reasons = ["سند متناظر پیدا نشد"]
        alternatives: list[dict[str, Any]] = []
        is_duplicate_bank_row = (
            fingerprint_counts[_bank_row_fingerprint(bank_row)] > 1
        )

        if is_duplicate_bank_row and all_candidates:
            top = all_candidates[0]
            status = "possible_match"
            confidence = min(top["score"], 89)
            selected = top["transaction"]
            reasons = list(top["reasons"])
            reasons.append(
                "ردیف تکراری مشابه در فایل بانک وجود دارد؛ تأیید انسانی لازم است"
            )
        elif candidates:
            top = candidates[0]
            confidence = top["score"]
            ambiguous = (
                len(candidates) > 1
                and candidates[1]["score"] >= top["score"] - 5
            )
            if confidence >= 90 and not ambiguous:
                status = "matched"
                selected = top["transaction"]
                reasons = top["reasons"]
                used_transactions.add(selected["transaction_id"])
            else:
                status = "possible_match"
                selected = top["transaction"]
                reasons = list(top["reasons"])
                if ambiguous:
                    reasons.append("بیش از یک سند با امتیاز مشابه پیدا شد")

            alternatives = [
                {
                    "confidence": candidate["score"],
                    **_serialize_transaction(candidate["transaction"]),
                }
                for candidate in candidates[1:4]
            ]
        elif review_candidates_by_row[index]:
            top = review_candidates_by_row[index][0]
            status = "possible_match"
            confidence = top["score"]
            selected = top["transaction"]
            reasons = top["reasons"]
            alternatives = [
                {
                    "confidence": candidate["score"],
                    **_serialize_transaction(candidate["transaction"]),
                }
                for candidate in review_candidates_by_row[index][1:4]
            ]
        elif all_candidates:
            status = "unmatched"
            confidence = 0
            selected = None
            reasons = [
                "تمام اسناد هم‌مبلغ قبلاً با ردیف‌های دیگر به‌صورت یکتا تطبیق داده شده‌اند",
                "برای این گردش، ردیف مستقل مصرف‌نشده‌ای در راهکاران باقی نمانده است",
            ]

        business_status = {
            "matched": "posted",
            "possible_match": "needs_review",
            "unmatched": "unposted",
        }[status]
        matched_amount = selected["amount"] if selected is not None else None

        results_by_index[index] = {
            "row_number": bank_row["row_number"],
            "bank_date": bank_row["date"].isoformat(),
            "amount": float(bank_row["amount"]),
            "direction": bank_row["direction"],
            "description": bank_row["description"],
            "reference": bank_row["reference"],
            "payer": bank_row.get("payer", ""),
            "origin_account": bank_row.get("origin_account", ""),
            "operation": bank_row.get("operation", ""),
            "time": bank_row.get("time", ""),
            "bank_document_number": bank_row.get(
                "bank_document_number",
                "",
            ),
            "deposit_id": bank_row.get("deposit_id", ""),
            "note": bank_row.get("note", ""),
            "branch": bank_row.get("branch", ""),
            "cheque_number": bank_row.get("cheque_number", ""),
            "balance": (
                float(bank_row["balance"])
                if bank_row["balance"] is not None
                else None
            ),
            "match_status": status,
            "business_status": business_status,
            "business_status_fa": {
                "posted": "سندخورده",
                "needs_review": "نیازمند بررسی",
                "unposted": "بدون سند",
            }[business_status],
            "confidence": confidence,
            "reasons": reasons,
            "match_method": "one_to_one" if selected is not None else None,
            "match_group_id": None,
            "match_group_row_count": None,
            "match_group_bank_total": None,
            "match_group_document_total": None,
            "amount_difference": (
                float(matched_amount - bank_row["amount"])
                if matched_amount is not None
                else None
            ),
            "date_difference_days": (
                _closest_day_difference(bank_row, selected)
                if selected is not None
                else None
            ),
            "matched_transaction": (
                _serialize_transaction(selected)
                if selected is not None
                else None
            ),
            "alternative_candidates": alternatives,
        }

    ordered_results = [
        results_by_index[index] for index in range(len(bank_rows))
    ]

    for result in ordered_results:
        if result.get("business_status") == "reversed":
            continue
        expected_effect = 1 if result["direction"] == "deposit" else 2
        bank_date = date.fromisoformat(result["bank_date"])
        bank_amount = Decimal(str(result["amount"]))
        evidence = [
            transaction
            for transaction in internal_transfers
            if transaction.get("effect") == expected_effect
            and abs(transaction["amount"] - bank_amount) <= Decimal("0.01")
            and any(
                abs((candidate_date - bank_date).days) <= tolerance_days
                for candidate_date in _transaction_date_candidates(transaction)
            )
        ]
        if not evidence:
            continue
        evidence.sort(
            key=lambda transaction: (
                _closest_day_difference({"date": bank_date}, transaction)
                or 0
            )
        )
        selected_transfer = evidence[0]
        used_transactions.add(selected_transfer["transaction_id"])
        result.update(
            {
                "match_status": "internal_transfer",
                "business_status": "internal_transfer",
                "business_status_fa": "انتقال داخلی شرکت",
                "confidence": 100,
                "reasons": [
                    "گردش متناظر انتقال بین حساب‌های خود شرکت در راهکاران پیدا شد",
                    "طبق سیاست خزانه، انتقال داخلی نه سندخورده و نه بدون سند محسوب می‌شود",
                ],
                "match_method": "internal_transfer_policy",
                "amount_difference": 0.0,
                "date_difference_days": _closest_day_difference(
                    {"date": bank_date},
                    selected_transfer,
                ),
                "matched_transaction": _serialize_transaction(
                    selected_transfer
                ),
                "alternative_candidates": [],
            }
        )

    return ordered_results, used_transactions


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
        WHERE rnt.BankAccountRef = :bank_account_id
          AND rn.NormalORGuarantee = 1
          AND ISNULL(rn.Description, N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(rn.Description, N'') NOT LIKE N'%تضمین%'
          AND ISNULL(rn.Description, N'') NOT LIKE N'%حسن انجام%'
          AND rnt.State = 3
          AND rnt.DocumentItemType = 12
          AND rnt.DocumentState = 3
          AND rnt.Date >= :start_date
          AND rnt.Date < :end_date

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
                    else "receipt_payment_deposit_amount"
                ),
                "effect": (
                    1
                    if transaction_type
                    in {
                        "receipt",
                        "received_cheque_status",
                        "bank_transfer_in",
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
                "RPA3.ReceivableNoteTransaction(State=3, DocumentItemType=12)"
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
            "definite_match_rate": (
                definite_match_count / total_bank_rows if total_bank_rows else 0
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
        },
        "rows": results,
        "unmatched_erp_transactions": unmatched_erp,
        "unmatched_raahkaran_items": unmatched_erp,
    }
