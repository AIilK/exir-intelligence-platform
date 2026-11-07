"""خواندن صورتحساب بانک (اکسل، CSV، HTML، PDF) و تشخیص ستون‌ها و بانک (از bank_reconciliation_service.py جدا شده)."""

from __future__ import annotations
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any
import unicodedata
from app.utils.jalali import parse_jalali_date


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
        "مبلغ گردش بستانکار",
        "credit",
        "deposit",
    },
    "withdrawal": {
        "برداشت",
        "مبلغ برداشت",
        "بدهکار",
        "مبلغ بدهکار",
        "مبلغ گردش بدهکار",
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
        "شماره سریال",
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
        "واریز کننده/ ذیتفع",
        "واریز کننده/ ذینفع",
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
        parsed_jalali = parse_jalali_date(raw)
        if parsed_jalali is None:
            raise ReconciliationInputError(
                f"تاریخ شمسی نامعتبر در فایل بانک: {value}"
            )
        return parsed_jalali

    try:
        return date(first, second, third)
    except ValueError as exc:
        raise ReconciliationInputError(
            f"تاریخ میلادی نامعتبر در فایل بانک: {value}"
        ) from exc


class _StatementHTMLTableParser(HTMLParser):
    """Small dependency-free table reader for bank HTML exports."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(" ".join("".join(self._cell_parts).split()))
            self._cell_parts = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _decode_html(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "windows-1256"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ReconciliationInputError("Encoding فایل HTML قابل تشخیص نیست.")


def _clean_mellat_table_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """Collapse repeated Jasper page headers/footers to one transaction table."""

    header: list[Any] | None = None
    transactions: list[list[Any]] = []
    metadata: list[list[Any]] = []
    account_number: str | None = None
    report_from: str | None = None
    report_to: str | None = None

    for raw_row in rows:
        row = [_as_text(value) for value in raw_row]
        normalized = [_normalize_text(value) for value in row]
        joined = " | ".join(value for value in row if value)

        if "بانک ملت" in joined and len(metadata) < 1:
            metadata.append(["بانک ملت"])

        if account_number is None and any("شماره حساب" in value for value in normalized):
            # Mellat places the number immediately beside/inside the account label block.
            for value in row:
                match = re.search(r"(?<!\d)(\d{6,20})(?!\d)", value.translate(_PERSIAN_DIGITS))
                if match and len(match.group(1)) >= 8:
                    account_number = match.group(1)
                    break

        jalali_dates = re.findall(r"1[34]\d{2}[/-]\d{1,2}[/-]\d{1,2}", joined.translate(_PERSIAN_DIGITS))
        if len(jalali_dates) >= 2 and ("بازه گزارش" in joined or "تا تاریخ" in joined):
            report_from = jalali_dates[-1]
            report_to = jalali_dates[0]

        if (
            _header_matches_semantic(normalized, "date")
            and _header_matches_semantic(normalized, "deposit")
            and _header_matches_semantic(normalized, "withdrawal")
        ):
            if header is None:
                header = row
            continue

        if header is None:
            continue

        # Transaction rows in Mellat have a Jalali date in the same column as header "تاریخ".
        try:
            date_index = next(i for i, value in enumerate([_normalize_text(v) for v in header]) if value == _normalize_text("تاریخ"))
        except StopIteration:
            continue
        if date_index >= len(row):
            continue
        raw_date = row[date_index].translate(_PERSIAN_DIGITS)
        if not re.fullmatch(r"1[34]\d{2}[/-]\d{1,2}[/-]\d{1,2}", raw_date):
            continue
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))
        transactions.append(row[: len(header)])

    if header is None or not transactions:
        raise ReconciliationInputError(
            "جدول گردش بانک ملت در فایل پیدا نشد. PDF/HTML باید متن قابل انتخاب و ستون‌های تاریخ، بستانکار و بدهکار داشته باشد."
        )

    if account_number:
        metadata.append(["شماره حساب", account_number])
    if report_from or report_to:
        metadata.append(["بازه گزارش از تاریخ", report_from or "", "تا تاریخ", report_to or ""])
    return [*metadata, header, *transactions]


def _read_html_statement(content: bytes) -> list[list[Any]]:
    parser = _StatementHTMLTableParser()
    try:
        parser.feed(_decode_html(content))
    except Exception as exc:
        raise ReconciliationInputError("فایل HTML بانک قابل خواندن نیست.") from exc
    return _clean_mellat_table_rows(parser.rows)


def _read_pdf_statement(content: bytes) -> list[list[Any]]:
    """Extract digital bank tables from PDF; optimized for Bank Mellat Jasper reports."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "برای خواندن PDF صورتحساب، بسته pdfplumber نصب نشده است. requirements را نصب/به‌روزرسانی کنید."
        ) from exc

    extracted_rows: list[list[Any]] = []
    extracted_text: list[str] = []
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                text_value = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                if text_value:
                    extracted_text.append(text_value)
                tables = page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 5,
                        "snap_tolerance": 4,
                        "join_tolerance": 4,
                    }
                )
                if not tables:
                    tables = page.extract_tables()
                for table in tables or []:
                    for row in table or []:
                        if row:
                            extracted_rows.append([_as_text(value).replace("\n", " ") for value in row])
    except Exception as exc:
        raise ReconciliationInputError("PDF صورتحساب قابل خواندن نیست یا ساختار آن خراب است.") from exc

    if extracted_rows:
        try:
            return _clean_mellat_table_rows(extracted_rows)
        except ReconciliationInputError:
            pass

    # Some PDFs have no visible ruling lines. Rebuild Mellat rows from layout text.
    lines = [" ".join(line.split()) for text_value in extracted_text for line in text_value.splitlines() if line.strip()]
    synthetic: list[list[Any]] = []
    if any("بانک ملت" in line for line in lines):
        synthetic.append(["بانک ملت"])
    for line in lines:
        if "شماره حساب" in line:
            synthetic.append([line])
        if "بازه گزارش" in line or ("از تاریخ" in line and "تا تاریخ" in line):
            synthetic.append([line])

    # Layout extraction commonly returns each transaction as one row. Parse from right-to-left:
    # row, date, time, branch, accounting code, deposit id, serial, payer, description, debit, credit, balance.
    header = [
        "مانده", "مبلغ گردش بستانکار", "مبلغ گردش بدهکار", "شرح",
        "واریز کننده/ ذیتفع", "شماره سریال", "شناسه واریز", "کد حسابگری",
        "شعبه", "زمان", "تاریخ", "رديف",
    ]
    parsed_tx: list[list[Any]] = []
    for line in lines:
        match = re.search(
            r"(?P<date>1[34]\d{2}/\d{1,2}/\d{1,2})\s+(?P<time>\d{1,2}:\d{2}:\d{2})",
            line.translate(_PERSIAN_DIGITS),
        )
        if not match:
            continue
        # Without table coordinates monetary columns cannot be recovered safely.
        # Keep this branch only as a diagnostic; do not guess amounts.
        continue

    if parsed_tx:
        return [*synthetic, header, *parsed_tx]
    raise ReconciliationInputError(
        "متن PDF خوانده شد اما جدول تراکنش‌های بانک ملت استخراج نشد. لطفاً PDF اصلی دانلودشده از بانک (نه اسکن/عکس) را بارگذاری کنید؛ HTML بانک ملت نیز پشتیبانی می‌شود."
    )


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


def _header_matches_semantic(headers: list[str], semantic: str) -> bool:
    aliases = {_normalize_text(value) for value in _COLUMN_ALIASES[semantic]}
    for header in headers:
        if not header:
            continue
        if any(
            header == alias
            or header.startswith(f"{alias} ")
            or header.endswith(f" {alias}")
            for alias in aliases
        ):
            return True
    return False


def _detect_header_row(rows: list[list[Any]]) -> int:
    # Bank exports often contain logos, account summaries and merged cells before
    # the transaction table. Scan a generous prefix and score rows by recognized
    # transaction semantics instead of requiring a brittle exact layout.
    required_semantics = ("date", "deposit", "withdrawal")
    optional_semantics = ("description", "reference", "balance", "operation")
    best_row: int | None = None
    best_score = -1

    for row_index, row in enumerate(rows[:200], start=1):
        normalized_headers = [_normalize_text(value) for value in row]
        required_hits = sum(
            _header_matches_semantic(normalized_headers, semantic)
            for semantic in required_semantics
        )
        optional_hits = sum(
            _header_matches_semantic(normalized_headers, semantic)
            for semantic in optional_semantics
        )
        non_empty = sum(bool(value) for value in normalized_headers)
        score = required_hits * 10 + optional_hits * 2 + min(non_empty, 10)

        if required_hits == len(required_semantics):
            return row_index
        if required_hits >= 2 and score > best_score:
            best_row, best_score = row_index, score

    # A near-match is safer than forcing operators to discover an Excel row
    # manually. Column resolution below will still validate required columns.
    if best_row is not None:
        return best_row

    raise ReconciliationInputError(
        "ردیف عنوان تراکنش‌های بانکی خودکار پیدا نشد. فایل باید ستون‌های تاریخ، واریز و برداشت داشته باشد."
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
    elif suffix in {".html", ".htm"}:
        rows = _read_html_statement(content)
    elif suffix == ".pdf":
        rows = _read_pdf_statement(content)
    else:
        raise ReconciliationInputError(
            "فایل‌های CSV، XLSX، XLS، PDF و HTML پشتیبانی می‌شوند."
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
