from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from threading import RLock
from typing import Any

from openpyxl import load_workbook

from app.core.config import settings
from app.utils.jalali import format_jalali_date, parse_jalali_date


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
SOURCE_FOLDERS = {
    "01_Received_Cheques": {"source_kind": "received_cheques", "direction": "inflow", "label": "چک دریافتی"},
    "02_Issued_Cheques": {"source_kind": "issued_cheques", "direction": "outflow", "label": "چک پرداختی"},
    "03_Received_Transfers": {"source_kind": "received_transfers", "direction": "inflow", "label": "حواله دریافت"},
    "04_Paid_Transfers": {"source_kind": "paid_transfers", "direction": "outflow", "label": "حواله پرداخت"},
}
FILENAME_KIND = {
    "چک دریافتی": "received_cheques",
    "چک پرداختی": "issued_cheques",
    "حواله دریافت": "received_transfers",
    "حواله پرداخت": "paid_transfers",
}
KIND_META = {spec["source_kind"]: spec for spec in SOURCE_FOLDERS.values()}
REQUIRED_HEADERS = {"شناسه حواله", "شماره حواله", "تاریخ ثبت", "مبلغ", "بانک", "بابت"}

RECEIVED_CHEQUE_PORTFOLIO_REQUIRED_HEADERS = {"شناسه", "شماره چک", "شعبه", "وضعیت", "تاریخ ثبت", "تاریخ سررسید", "مبلغ"}
# Alternate full-snapshot export used by the current KarAmand ListData screen.
# It exposes serial/Sayad and "وضعیت فعلی" instead of the legacy شناسه/شماره چک/وضعیت columns.
RECEIVED_CHEQUE_LISTDATA_REQUIRED_HEADERS = {"شماره سریال", "شماره صیاد", "تاریخ سررسید", "مبلغ", "شعبه", "وضعیت فعلی"}
RECEIVED_CHEQUE_LISTDATA_HEADER_MAP = {
    "شماره سریال": "cheque_series", "شماره صیاد": "sayad_number", "ماهیت": "nature",
    "تاریخ سررسید": "due_date_jalali", "تاریخ توافق شده": "agreed_date_jalali", "طرف مقابل": "counterparty_name",
    "مبلغ": "amount_rial", "مبلغ به ارز عملیاتی": "operational_currency_amount", "صندوق": "cashbox",
    "شماره حساب": "account_number", "شعبه": "branch", "نام بانک": "bank", "حساب واگذاری": "assignment_account",
    "واگذار به غیر": "assigned_to_other", "وضعیت در تاریخ گزارش": "status_at_report_date", "وضعیت فعلی": "cheque_status",
    "شماره رسید دریافت": "receipt_number", "تاریخ رسید دریافت": "receipt_date_jalali", "شماره عملیات": "operation_number",
    "تاریخ عملیات": "operation_date_jalali", "شرح دریافت": "description", "شرح به زبان دوم": "description_second_language",
    "تحویل دهنده": "deliverer",
}
RECEIVED_CHEQUE_PORTFOLIO_HEADER_MAP = {
    "ردیف": "row_number", "شناسه": "transfer_id", "شماره چک": "cheque_number",
    "شعبه": "branch", "چک الکترونیکی": "electronic_cheque", "محل چک": "cheque_location",
    "شماره حساب": "account_number", "وضعیت": "cheque_status", "تاریخ ثبت": "registration_date_jalali",
    "تاریخ سررسید": "due_date_jalali", "تاریخ واگذاری": "assignment_date_jalali", "تاریخ وصول": "collection_date_jalali",
    "مبلغ": "amount_rial", "نام بانک و شعبه": "bank_and_branch", "بابت": "purpose", "توضیحات": "description",
    "نام بانک": "bank", "کد شعبه": "bank_branch_code", "کد معین": "subsidiary_code", "کد سطح 4": "level4_code",
    "کد سطح4": "level4_code", "کد سطح 5": "level5_code", "کد سطح5": "level5_code", "کد سطح 6": "level6_code", "کد سطح6": "level6_code",
    "معین": "subsidiary_name", "تفضیلی": "level4_name", "سطح 5": "level5_name", "سطح 6": "level6_name",
    "سال مالی": "fiscal_year", "معین آخرین عملیات": "last_operation_account", "سطح 4 آخرین عملیات": "last_operation_level4",
    "سطح 5 آخرین عملیات": "last_operation_level5", "سطح 6 آخرین عملیات": "last_operation_level6",
    "دلیل برگشتی": "return_reason", "سریال چک": "cheque_series", "شناسه صیاد": "sayad_number",
    "کد ملی/شناسه صاحب حساب": "owner_national_id", "نام صاحب حساب": "owner_name", "نام  کاربر": "user_name",
}

ISSUED_CHEQUE_PORTFOLIO_REQUIRED_HEADERS = {"شناسه", "شماره چک", "شعبه", "اسناد پرداختنی", "وضعیت", "تاریخ ثبت", "تاریخ سررسید", "مبلغ"}
ISSUED_CHEQUE_PORTFOLIO_HEADER_MAP = {
    "ردیف": "row_number", "شناسه": "transfer_id", "شماره چک": "cheque_number",
    "شعبه": "branch", "اسناد پرداختنی": "bank_and_branch", "وضعیت": "karamad_raw_status",
    "تاریخ ثبت": "registration_date_jalali", "تاریخ سررسید": "due_date_jalali", "مبلغ": "amount_rial",
    "بابت": "purpose", "توضیحات": "description", "کد معین": "subsidiary_code",
    "کد سطح 4": "level4_code", "کد سطح4": "level4_code", "کد سطح 5": "level5_code", "کد سطح5": "level5_code",
    "کد سطح 6": "level6_code", "کد سطح6": "level6_code", "معین": "subsidiary_name",
    "تفضیلی": "level4_name", "سطح 5": "level5_name", "سطح 6": "level6_name",
    "تضمینی": "guarantee_flag", "سال مالی": "fiscal_year", "تاریخ وصول": "collection_date_jalali",
    "بررسی": "review_flag", "شماره درخواست پرداخت": "payment_request_number", "شماره صیادی": "sayad_number",
}

HEADER_MAP = {
    "ردیف": "row_number", "شناسه حواله": "transfer_id", "شماره حواله": "transfer_number",
    "شعبه": "branch", "شماره سند": "document_number", "تاریخ ثبت": "registration_date_jalali",
    "تاریخ حواله": "transfer_date_jalali", "مبلغ": "amount_rial", "کارمزد": "fee_rial",
    "بانک": "bank", "کد معین": "subsidiary_code", "کد سطح4": "level4_code",
    "کد سطح5": "level5_code", "کد سطح6": "level6_code", "نام معین": "subsidiary_name",
    "نام سطح4": "level4_name", "نام سطح5": "level5_name", "نام سطح6": "level6_name",
    "بابت": "purpose", "توضیحات": "description", "شماره فاکتور": "invoice_number",
    "تاریخ سند": "document_date_jalali", "شماره درخواست پرداخت": "payment_request_number",
    "پوز بانکی": "bank_pos", "1": "legacy_flag", "شناسه سند وجوه در راه": "in_transit_document_id",
    "نام کاربر": "user_name", "وجوه در راه": "in_transit",
}
TRANSFER_MARKERS = (
    "بابت انتقال", "جهت انتقال", "انتقال از", "انتقال به", "انتقال بین بانکی",
    "انتقال بین‌بانکی", "انتقال بانک به بانک", "انتقال بانک‌به‌بانک", "بانک به بانک",
    "بانک‌به‌بانک", "حواله شرکتی", "طرف حساب شرکتی", "جابجایی بین حساب",
    "جابه جایی بین حساب", "جابه‌جایی بین حساب",
)
PETTY_CASH_MARKERS = ("تنخواه", "علی الحساب تنخواه", "علی‌الحساب تنخواه")
_LOCK = RLock()


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (Path(__file__).resolve().parents[3] / path).resolve()


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200c", " ").split()).strip()


def _id(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value or "").strip()


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    normalized = str(value).translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS).replace(",", "").replace("٬", "").strip()
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"مبلغ نامعتبر است: {value}") from exc


def _jalali(value: Any, field: str, row_number: int, *, required: bool = False) -> str | None:
    raw = str(value or "").translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS).strip()
    if not raw:
        if required:
            raise ValueError(f"{field} در ردیف {row_number} خالی است.")
        return None
    match = re.search(r"(1[34]\d{2})\s*[/_.-]\s*(\d{1,2})\s*[/_.-]\s*(\d{1,2})", raw)
    if not match:
        raise ValueError(f"{field} در ردیف {row_number} شمسی معتبر نیست: {value}")
    year, month, day = map(int, match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError(f"{field} در ردیف {row_number} معتبر نیست: {value}")
    return f"{year:04d}/{month:02d}/{day:02d}"


def _classify(record: dict[str, Any]) -> tuple[str, str]:
    purpose = _text(record.get("purpose")).casefold()
    source = f"{purpose} {record.get('description') or ''} {record.get('subsidiary_name') or ''}".casefold()
    if any(marker.casefold() in source for marker in PETTY_CASH_MARKERS):
        return "petty_cash", "شرح یا حساب شامل نشانهٔ تنخواه است"
    if re.match(r"^انتقال(?:ی)?(?:\s|$)", purpose) or any(marker.casefold() in source for marker in TRANSFER_MARKERS):
        return "company_bank_transfer", "شرح شامل نشانهٔ انتقال بانک‌به‌بانک است"
    return "operational", "گردش قطعی عملیاتی کارآمد"


class KaramadManualImportService:
    """Folder-driven, read-only companion source for four recurring KarAmand exports."""

    def __init__(self, inbox: Path | None = None, archive: Path | None = None, state_path: Path | None = None):
        self.inbox = inbox or _project_path(settings.karamad_excel_inbox)
        self.archive = archive or _project_path(settings.karamad_excel_archive)
        self.state_path = state_path or _project_path(settings.karamad_excel_state_file)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.archive.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        for folder in SOURCE_FOLDERS:
            (self.inbox / folder).mkdir(parents=True, exist_ok=True)
            (self.archive / folder).mkdir(parents=True, exist_ok=True)

    def _empty_state(self) -> dict[str, Any]:
        return {"records": {}, "imports": [], "processed_hashes": {}, "conflicts": [], "last_scan_at": None, "last_error": None}

    def _state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._empty_state()
        try:
            return {**self._empty_state(), **json.loads(self.state_path.read_text(encoding="utf-8"))}
        except (OSError, ValueError, json.JSONDecodeError):
            return self._empty_state()

    def _save(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.state_path)

    @staticmethod
    def detect_kind(filename: str, parent_name: str | None = None) -> str:
        if parent_name in SOURCE_FOLDERS:
            return SOURCE_FOLDERS[parent_name]["source_kind"]
        stem = _text(Path(filename).stem)
        for marker, source_kind in FILENAME_KIND.items():
            if marker in stem:
                return source_kind
        raise ValueError("نوع فایل مشخص نیست؛ فایل را با یکی از نام‌های چک دریافتی، چک پرداختی، حواله دریافت یا حواله پرداخت ذخیره کنید.")

    def parse(self, path: Path, source_kind: str) -> tuple[list[dict[str, Any]], list[str]]:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.worksheets[0]
            header_row = None
            headers: list[str] = []
            detected_schema = "executed_movement"
            for row_number, values in enumerate(sheet.iter_rows(min_row=1, max_row=min(10, sheet.max_row or 10), values_only=True), start=1):
                normalized = [_text(value) for value in values]
                names = set(normalized)
                if source_kind == "received_cheques" and RECEIVED_CHEQUE_PORTFOLIO_REQUIRED_HEADERS.issubset(names):
                    header_row, headers, detected_schema = row_number, normalized, "received_cheque_portfolio"
                    break
                if source_kind == "received_cheques" and RECEIVED_CHEQUE_LISTDATA_REQUIRED_HEADERS.issubset(names):
                    header_row, headers, detected_schema = row_number, normalized, "received_cheque_listdata"
                    break
                if source_kind == "issued_cheques" and ISSUED_CHEQUE_PORTFOLIO_REQUIRED_HEADERS.issubset(names):
                    header_row, headers, detected_schema = row_number, normalized, "issued_cheque_portfolio"
                    break
                if REQUIRED_HEADERS.issubset(names):
                    header_row, headers = row_number, normalized
                    break
            if header_row is None:
                if source_kind == "received_cheques":
                    raise ValueError("ساختار فایل چک دریافتی کارآمد معتبر نیست؛ ستون‌های شناسه، شماره چک، شعبه، وضعیت، تاریخ ثبت، تاریخ سررسید و مبلغ لازم‌اند.")
                if source_kind == "issued_cheques":
                    raise ValueError("ساختار فایل چک پرداختی کارآمد معتبر نیست؛ ستون‌های شناسه، شماره چک، شعبه، اسناد پرداختنی، وضعیت، تاریخ ثبت، تاریخ سررسید و مبلغ لازم‌اند.")
                raise ValueError("ساختار فایل کارآمد معتبر نیست؛ ستون‌های شناسه حواله، شماره حواله، تاریخ ثبت، مبلغ، بانک و بابت لازم‌اند.")
            header_map = (
                RECEIVED_CHEQUE_PORTFOLIO_HEADER_MAP if detected_schema == "received_cheque_portfolio"
                else RECEIVED_CHEQUE_LISTDATA_HEADER_MAP if detected_schema == "received_cheque_listdata"
                else ISSUED_CHEQUE_PORTFOLIO_HEADER_MAP if detected_schema == "issued_cheque_portfolio"
                else HEADER_MAP
            )
            unknown = [name for name in headers if name and name not in header_map]
            warnings = [f"ستون‌های ناشناخته نادیده گرفته شدند: {', '.join(unknown)}"] if unknown else []
            if detected_schema == "executed_movement" and source_kind in {"received_cheques", "issued_cheques"} and not any(name in headers for name in ("شماره چک", "تاریخ سررسید", "شناسه صیاد")):
                warnings.append("فایل چک کارآمد با تاریخ حواله/ثبت خوانده شد؛ تاریخ حواله و در نبود آن تاریخ ثبت، مبنای فیلتر و محاسبه است.")
            invalid_optional_dates = 0
            def optional_date(value: Any, field: str, row_number: int) -> str | None:
                nonlocal invalid_optional_dates
                try:
                    return _jalali(value, field, row_number)
                except ValueError:
                    invalid_optional_dates += 1
                    return None
            keys = [header_map.get(name) for name in headers]
            records: list[dict[str, Any]] = []
            seen: set[str] = set()
            meta = KIND_META[source_kind]
            for excel_row, values in enumerate(sheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
                if not any(value not in (None, "") for value in values):
                    continue
                raw = {key: values[index] if index < len(values) else None for index, key in enumerate(keys) if key}
                if detected_schema == "received_cheque_listdata":
                    # Sayad is the strongest stable business key; fall back to serial.
                    transfer_id = _id(raw.get("sayad_number")) or _id(raw.get("cheque_series"))
                else:
                    transfer_id = _id(raw.get("transfer_id"))
                if not transfer_id:
                    if detected_schema in {"received_cheque_portfolio", "received_cheque_listdata", "issued_cheque_portfolio"}:
                        continue
                    raise ValueError(f"شناسه در ردیف {excel_row} خالی است.")
                if transfer_id in seen:
                    raise ValueError(f"شناسه {transfer_id} داخل همین فایل تکراری است.")
                seen.add(transfer_id)
                if detected_schema == "received_cheque_listdata":
                    # ListData has no legacy "تاریخ ثبت". Receipt date is the closest source field;
                    # operation date is the second choice. Due date is only a final non-invented fallback
                    # so existing downstream month grouping remains structurally valid.
                    registered = (
                        optional_date(raw.get("receipt_date_jalali"), "تاریخ رسید دریافت", excel_row)
                        or optional_date(raw.get("operation_date_jalali"), "تاریخ عملیات", excel_row)
                        or _jalali(raw.get("due_date_jalali"), "تاریخ سررسید", excel_row, required=True)
                    )
                else:
                    registered = _jalali(raw.get("registration_date_jalali"), "تاریخ ثبت", excel_row, required=True)
                record = {key: _id(value) for key, value in raw.items() if key not in {"amount_rial", "fee_rial", "in_transit"}}
                if detected_schema in {"received_cheque_portfolio", "received_cheque_listdata"}:
                    due = optional_date(raw.get("due_date_jalali"), "تاریخ سررسید", excel_row)
                    assignment = optional_date(raw.get("assignment_date_jalali"), "تاریخ واگذاری", excel_row) if detected_schema == "received_cheque_portfolio" else None
                    collection = optional_date(raw.get("collection_date_jalali"), "تاریخ وصول", excel_row) if detected_schema == "received_cheque_portfolio" else None
                    record.update({
                        "transfer_id": transfer_id, "direction": "inflow", "source_kind": source_kind,
                        "source_label": meta["label"], "registration_date_jalali": registered, "registration_month": registered[:7],
                        "due_date_jalali": due, "assignment_date_jalali": assignment, "collection_date_jalali": collection,
                        "transfer_date_jalali": due, "document_date_jalali": registered,
                        "amount_rial": _number(raw.get("amount_rial")), "fee_rial": 0.0, "in_transit": False,
                        "source_row": excel_row, "detected_schema": detected_schema,
                        "transfer_number": _id(raw.get("cheque_number")) or _id(raw.get("cheque_series")),
                    })
                    # V129 business rule (KarAmand received cheques only):
                    # a blank/null current status means the cheque is still physically in the cashbox.
                    # Persist the normalized business status so every downstream KPI/agent sees the same bucket.
                    if not _text(record.get("cheque_status")):
                        record["cheque_status"] = "نزد صندوق"
                    record["classification"] = "operational"
                    record["classification_reason"] = "سبد کامل چک‌های دریافتی کارآمد"
                elif detected_schema == "issued_cheque_portfolio":
                    # Guaranteed cheques are collateral instruments, not operational issued-cheque commitments.
                    # KarAmand may expose them either via the explicit `تضمینی` flag or through the
                    # subsidiary account name, so exclude both forms from this operational snapshot.
                    guarantee_raw = raw.get("guarantee_flag")
                    guarantee_text = _text(guarantee_raw).casefold()
                    subsidiary_text = _text(raw.get("subsidiary_name")).casefold()
                    is_guaranteed = (
                        guarantee_raw is True
                        or guarantee_text in {"true", "1", "بله", "بلی", "yes", "y"}
                        or "تضمینی" in subsidiary_text
                        or "تضمينی" in subsidiary_text
                    )
                    if is_guaranteed:
                        continue
                    due = optional_date(raw.get("due_date_jalali"), "تاریخ سررسید", excel_row)
                    collection = optional_date(raw.get("collection_date_jalali"), "تاریخ وصول", excel_row)
                    record.update({
                        "transfer_id": transfer_id, "direction": "outflow", "source_kind": source_kind,
                        "source_label": meta["label"], "registration_date_jalali": registered, "registration_month": registered[:7],
                        "due_date_jalali": due, "collection_date_jalali": collection,
                        "transfer_date_jalali": due, "document_date_jalali": registered,
                        "amount_rial": _number(raw.get("amount_rial")), "fee_rial": 0.0, "in_transit": False,
                        "source_row": excel_row, "detected_schema": detected_schema,
                        "transfer_number": _id(raw.get("cheque_number")),
                        "cheque_status": "ثبت‌شده در کارآمد",
                        "return_reason": None,
                        "future_data_complete": False,
                        "returns_available": False,
                    })
                    record["classification"] = "operational"
                    record["classification_reason"] = "سبد چک‌های پرداختی ثبت‌شده کارآمد؛ داده آینده فعلاً کامل نیست و برگشتی گزارش نشده است"
                else:
                    record.update({
                        "transfer_id": transfer_id, "direction": meta["direction"], "source_kind": source_kind,
                        "source_label": meta["label"], "registration_date_jalali": registered, "registration_month": registered[:7],
                        "transfer_date_jalali": optional_date(raw.get("transfer_date_jalali"), "تاریخ حواله", excel_row),
                        "document_date_jalali": optional_date(raw.get("document_date_jalali"), "تاریخ سند", excel_row),
                        "amount_rial": _number(raw.get("amount_rial")), "fee_rial": _number(raw.get("fee_rial")),
                        "in_transit": bool(raw.get("in_transit")), "source_row": excel_row, "detected_schema": detected_schema,
                    })
                    record["classification"], record["classification_reason"] = _classify(record)
                if record["amount_rial"] < 0 or record["fee_rial"] < 0:
                    raise ValueError(f"مبلغ یا کارمزد منفی در ردیف {excel_row} مجاز نیست.")
                records.append(record)
            if not records:
                raise ValueError("فایل کارآمد هیچ ردیفی ندارد.")
            if invalid_optional_dates:
                warnings.append(f"{invalid_optional_dates} تاریخ اختیاری نامعتبر/غیرتاریخی نادیده گرفته شد؛ تاریخ ثبت معتبر مبنای محاسبه ماند.")
            return records, warnings
        finally:
            workbook.close()

    @staticmethod
    def _business(record: dict[str, Any]) -> dict[str, Any]:
        ignored = {"source_filename", "source_row", "source_kind", "source_label", "source_kinds", "imported_at"}
        return {key: value for key, value in record.items() if key not in ignored}

    def import_workbook(self, path: Path, filename: str, source_kind: str | None = None) -> dict[str, Any]:
        source_kind = source_kind or self.detect_kind(filename, path.parent.name)
        records, warnings = self.parse(path, source_kind)
        fingerprint = sha256(path.read_bytes()).hexdigest()
        imported_at = datetime.now(timezone.utc).isoformat()
        with _LOCK:
            state = self._state()
            if fingerprint in state["processed_hashes"]:
                return {"status": "success", "duplicate_file": True, "import": state["processed_hashes"][fingerprint], "warnings": warnings, "summary": self.summary(state=state)}
            inserted = updated = unchanged = overlapped = 0
            conflicts: list[dict[str, Any]] = []
            snapshot_kind = (
                "received_cheques" if records and records[0].get("detected_schema") in {"received_cheque_portfolio", "received_cheque_listdata"}
                else "issued_cheques" if records and records[0].get("detected_schema") == "issued_cheque_portfolio"
                # The recurring KarAmand transfer exports are full snapshots too.
                # Replacing the previous snapshot prevents stale rows from old exports
                # remaining in management totals when a newer file is imported.
                else source_kind if source_kind in {"received_transfers", "paid_transfers"}
                else None
            )
            is_snapshot = snapshot_kind is not None
            replaced_previous_count = 0
            previous_snapshot_count = 0
            previous_snapshot_amount_rial = 0.0
            if snapshot_kind:
                for previous in state["records"].values():
                    kinds = set(previous.get("source_kinds") or [previous.get("source_kind")])
                    if snapshot_kind in kinds:
                        previous_snapshot_count += 1
                        previous_snapshot_amount_rial += float(previous.get("amount_rial") or 0)
                for record_key, previous in list(state["records"].items()):
                    kinds = set(previous.get("source_kinds") or [previous.get("source_kind")])
                    if snapshot_kind not in kinds:
                        continue
                    if previous.get("source_kind") == snapshot_kind or len(kinds) == 1:
                        del state["records"][record_key]
                        replaced_previous_count += 1
                    else:
                        previous["source_kinds"] = sorted(kinds - {snapshot_kind})
            for record in records:
                key = (f"{snapshot_kind}:{record['transfer_id']}" if snapshot_kind else f"{record['direction']}:{record['transfer_id']}")
                previous = state["records"].get(key)
                source_kinds = sorted(set((previous or {}).get("source_kinds") or []) | {source_kind})
                enriched = {**record, "source_kinds": source_kinds, "source_filename": filename, "imported_at": imported_at}
                if previous is None:
                    inserted += 1
                else:
                    overlapped += 1
                    if self._business(previous) == self._business(enriched):
                        unchanged += 1
                    else:
                        updated += 1
                        conflict = {"record_key": key, "previous_file": previous.get("source_filename"), "new_file": filename, "detected_at": imported_at}
                        conflicts.append(conflict)
                        state["conflicts"].append(conflict)
                state["records"][key] = enriched
            archive_folder = next(folder for folder, meta in SOURCE_FOLDERS.items() if meta["source_kind"] == source_kind)
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name)
            archive_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}__{safe}"
            archive_target = self.archive / archive_folder / archive_name
            shutil.copy2(path, archive_target)
            item = {"filename": filename, "source_kind": source_kind, "source_label": KIND_META[source_kind]["label"], "stored_file": str(archive_target.relative_to(self.archive)), "content_sha256": fingerprint, "imported_at": imported_at, "rows_in_file": len(records), "inserted_count": inserted, "overlap_count": overlapped, "updated_count": updated, "unchanged_count": unchanged, "conflict_count": len(conflicts), "warnings": warnings, "snapshot_replace": is_snapshot, "snapshot_kind": snapshot_kind, "replaced_previous_count": replaced_previous_count}
            state["processed_hashes"][fingerprint] = item
            state["imports"].append(item)
            state["imports"] = state["imports"][-200:]
            state["conflicts"] = state["conflicts"][-500:]
            state["last_error"] = None
            self._save(state)
        current_snapshot_rows = [r for r in self._state()["records"].values() if snapshot_kind and snapshot_kind in set(r.get("source_kinds") or [r.get("source_kind")])] if snapshot_kind else []
        current_open_rows = []
        if snapshot_kind == "received_cheques":
            from app.services.received_cheque_current_status import received_cheque_is_approved_open_holding
            current_open_rows = [r for r in self.cheque_rows("received_cheques") if received_cheque_is_approved_open_holding(r)]
        snapshot_verification = {
            "snapshot_kind": snapshot_kind,
            "before_count": previous_snapshot_count,
            "after_count": len(current_snapshot_rows),
            "before_amount_rial": round(previous_snapshot_amount_rial, 2),
            "after_amount_rial": round(sum(float(r.get("amount_rial") or 0) for r in current_snapshot_rows), 2),
            "open_count": len(current_open_rows) if snapshot_kind == "received_cheques" else None,
            "open_amount_rial": round(sum(float(r.get("amount") or 0) for r in current_open_rows), 2) if snapshot_kind == "received_cheques" else None,
            "changed": (previous_snapshot_count != len(current_snapshot_rows)) or abs(previous_snapshot_amount_rial - sum(float(r.get("amount_rial") or 0) for r in current_snapshot_rows)) > 0.5,
        }
        return {"status": "success", "duplicate_file": False, "import": item, "snapshot_verification": snapshot_verification, "warnings": warnings, "summary": self.summary(), "message": (
            f"سبد چک دریافتی کارآمد با {len(records)} چک جایگزین شد؛ {replaced_previous_count} رکورد قبلی کنار گذاشته شد." if snapshot_kind == "received_cheques"
            else f"سبد چک پرداختی ثبت‌شده کارآمد با {len(records)} چک جایگزین شد؛ {replaced_previous_count} رکورد قبلی کنار گذاشته شد. داده آینده فعلاً کامل نیست و برگشتی گزارش نشده است." if snapshot_kind == "issued_cheques"
            else f"حواله‌های دریافتی کارآمد با {len(records)} ردیف جایگزین شد؛ {replaced_previous_count} ردیف قبلی کنار گذاشته شد." if snapshot_kind == "received_transfers"
            else f"حواله‌های پرداختی کارآمد با {len(records)} ردیف جایگزین شد؛ {replaced_previous_count} ردیف قبلی کنار گذاشته شد." if snapshot_kind == "paid_transfers"
            else f"{len(records)} ردیف خوانده شد؛ {inserted} ردیف جدید و {overlapped} ردیف هم‌پوشان بدون دوباره‌شماری."
        )}

    def scan(self) -> dict[str, Any]:
        imported, skipped, errors = [], [], []
        candidates = list(self.inbox.glob("*.xlsx"))
        for folder in SOURCE_FOLDERS:
            candidates.extend((self.inbox / folder).glob("*.xlsx"))
        for source in sorted(set(candidates), key=lambda item: item.stat().st_mtime):
            try:
                age = datetime.now().timestamp() - source.stat().st_mtime
                if age < settings.karamad_excel_min_file_age_seconds:
                    skipped.append({"filename": source.name, "reason": "file_is_still_new"})
                    continue
                result = self.import_workbook(source, source.name)
                if result.get("duplicate_file"):
                    skipped.append({"filename": source.name, "reason": "duplicate_content"})
                else:
                    imported.append(result["import"])
                source.unlink()
            except Exception as exc:
                errors.append({"filename": source.name, "error": str(exc)})
        state = self._state()
        state["last_scan_at"] = datetime.now(timezone.utc).isoformat()
        state["last_error"] = errors[-1] if errors else None
        self._save(state)
        return {"status": "success" if not errors else "partial_success", "inbox": str(self.inbox), "archive": str(self.archive), "imported_count": len(imported), "skipped_count": len(skipped), "error_count": len(errors), "imported": imported, "skipped": skipped, "errors": errors, "summary": self.summary(state=state)}

    def _records(self, *, month: str | None = None, direction: str | None = None, classification: str | None = None, branch: str | None = None, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = list((state or self._state())["records"].values())
        if month:
            if not re.fullmatch(r"1[34]\d{2}/(?:0[1-9]|1[0-2])", month):
                raise ValueError("ماه باید به‌شکل 1405/06 باشد.")
            rows = [row for row in rows if row.get("registration_month") == month]
        if direction:
            rows = [row for row in rows if row.get("direction") == direction]
        if classification:
            rows = [row for row in rows if row.get("classification") == classification]
        if branch:
            wanted = _text(branch).casefold()
            rows = [row for row in rows if _text(row.get("branch")).casefold() == wanted]
        return rows

    def summary(self, month: str | None = None, branch: str | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = state or self._state()
        rows = self._records(month=month, branch=branch, state=state)
        operational = [row for row in rows if row.get("classification") == "operational"]
        transfers = [row for row in rows if row.get("classification") == "company_bank_transfer"]
        petty = [row for row in rows if row.get("classification") == "petty_cash"]
        by_source: dict[str, dict[str, Any]] = {}
        for kind, meta in KIND_META.items():
            source_rows = [row for row in rows if kind in (row.get("source_kinds") or [row.get("source_kind")])]
            by_source[kind] = {"label": meta["label"], "source_row_count": len(source_rows), "unique_operational_count": sum(row.get("classification") == "operational" for row in source_rows), "source_amount_rial": sum(float(row.get("amount_rial") or 0) for row in source_rows)}
        paid_transfer_rows = [row for row in rows if "paid_transfers" in (row.get("source_kinds") or [row.get("source_kind")])]
        paid_transfer_bank_to_bank = [row for row in paid_transfer_rows if row.get("classification") == "company_bank_transfer"]
        paid_transfer_other = [row for row in paid_transfer_rows if row.get("classification") != "company_bank_transfer"]
        received_transfer_rows = [row for row in rows if "received_transfers" in (row.get("source_kinds") or [row.get("source_kind")])]
        dates = [row["registration_date_jalali"] for row in rows if row.get("registration_date_jalali")]
        months: dict[str, dict[str, Any]] = {}
        for row in state["records"].values():
            key = row.get("registration_month") or "نامشخص"
            item = months.setdefault(key, {"month": key, "count": 0, "amount_rial": 0.0})
            item["count"] += 1
            item["amount_rial"] += float(row.get("amount_rial") or 0)
        return {
            "selected_month": month, "selected_branch": branch, "unique_record_count": len(rows),
            "operational_inflow_rial": sum(float(row.get("amount_rial") or 0) for row in operational if row.get("direction") == "inflow"),
            "operational_outflow_rial": sum(float(row.get("amount_rial") or 0) for row in operational if row.get("direction") == "outflow"),
            "bank_transfer_rial": sum(float(row.get("amount_rial") or 0) for row in transfers),
            "bank_transfer_count": len(transfers),
            "received_transfer_total_rial": sum(float(row.get("amount_rial") or 0) for row in received_transfer_rows),
            "received_transfer_total_count": len(received_transfer_rows),
            "paid_transfer_total_rial": sum(float(row.get("amount_rial") or 0) for row in paid_transfer_rows),
            "paid_transfer_total_count": len(paid_transfer_rows),
            "paid_transfer_bank_to_bank_rial": sum(float(row.get("amount_rial") or 0) for row in paid_transfer_bank_to_bank),
            "paid_transfer_bank_to_bank_count": len(paid_transfer_bank_to_bank),
            "paid_transfer_other_rial": sum(float(row.get("amount_rial") or 0) for row in paid_transfer_other),
            "paid_transfer_other_count": len(paid_transfer_other),
            "petty_cash_rial": sum(float(row.get("amount_rial") or 0) for row in petty),
            "petty_cash_count": len(petty), "min_date_jalali": min(dates) if dates else None, "max_date_jalali": max(dates) if dates else None,
            "source_breakdown": by_source, "overlap_rule": "شناسه حواله در هر جهت فقط یک‌بار شمرده می‌شود؛ هم‌پوشانی چهار فایل حذف عددی می‌شود.",
            "available_months": sorted(months.values(), key=lambda item: item["month"], reverse=True),
            "available_branches": sorted({_text(row.get("branch")) for row in state["records"].values() if _text(row.get("branch"))}),
            "forecast_rule": "این ساختار، گردش قطعی تاریخی است و وارد چک یا تعهد آینده نمی‌شود. سیاست ۷۵٪ فقط برای چک باز دارای تاریخ سررسید اعمال می‌شود.",
            "cross_system_rule": "شباهت با راهکاران فقط برای کنترل گزارش می‌شود و بدون کلید قطعی، رکوردی خودکار حذف نمی‌شود.",
            "last_import": state["imports"][-1] if state["imports"] else None, "conflict_count": len(state.get("conflicts") or []),
        }

    def actual_movements(self, start: date, end: date, branch: str | None = None) -> dict[str, Any]:
        start_jalali, end_jalali = format_jalali_date(start), format_jalali_date(end)
        rows = self._records(branch=branch)
        if start_jalali and end_jalali:
            rows = [row for row in rows if start_jalali <= (row.get("registration_date_jalali") or "") <= end_jalali]
        operational = [row for row in rows if row.get("classification") == "operational"]
        return {"date_from_jalali": start_jalali, "date_to_jalali": end_jalali, "movements": sorted(operational, key=lambda row: (row.get("registration_date_jalali") or "", row.get("transfer_id") or ""), reverse=True), "company_bank_transfers": [row for row in rows if row.get("classification") == "company_bank_transfer"], "petty_cash_movements": [row for row in rows if row.get("classification") == "petty_cash"]}

    @staticmethod
    def _gregorian_iso(jalali_value: str | None) -> str | None:
        parsed = parse_jalali_date(jalali_value)
        return parsed.isoformat() if parsed else None

    def cheque_rows(self, source_kind: str) -> list[dict[str, Any]]:
        """Return KarAmand cheque exports in the canonical treasury shape.

        KarAmand currently exports transfer-style identifiers. Per the business
        rule, transfer date is the effective cheque date and registration date
        is the fallback. The original values are retained for audit/display.
        """
        if source_kind not in {"received_cheques", "issued_cheques"}:
            raise ValueError("source_kind must be received_cheques or issued_cheques")
        cheque_type = "received" if source_kind == "received_cheques" else "issued"
        today = date.today()
        result: list[dict[str, Any]] = []
        for row in self._records():
            kinds = row.get("source_kinds") or [row.get("source_kind")]
            if source_kind not in kinds:
                continue
            # V129 compatibility: normalize blank/legacy unknown statuses from older
            # KarAmand received snapshots to the approved cashbox bucket at read time.
            if cheque_type == "received_cheques":
                raw_status = _text(row.get("cheque_status"))
                if not raw_status or raw_status in {"وضعیت نامشخص", "نامشخص", "karamad_imported", "ثبت‌شده در کارآمد"}:
                    row = dict(row)
                    row["cheque_status"] = "نزد صندوق"
            effective_jalali = row.get("transfer_date_jalali") or row.get("registration_date_jalali")
            effective_iso = self._gregorian_iso(effective_jalali)
            due_day = date.fromisoformat(effective_iso) if effective_iso else None
            days = (due_day - today).days if due_day else None
            result.append({
                "cheque_id": f"karamad:{cheque_type}:{row.get('transfer_id')}",
                "document_id": row.get("transfer_id"),
                "document_number": row.get("transfer_number"),
                "document_date": self._gregorian_iso(row.get("registration_date_jalali")),
                "document_date_jalali": row.get("registration_date_jalali"),
                "registration_date": self._gregorian_iso(row.get("registration_date_jalali")),
                "registration_date_jalali": row.get("registration_date_jalali"),
                "transfer_date": self._gregorian_iso(row.get("transfer_date_jalali")),
                "transfer_date_jalali": row.get("transfer_date_jalali"),
                "transfer_number": row.get("transfer_number"),
                "cheque_type": cheque_type,
                "state_code": None,
                "state": row.get("cheque_status") or "karamad_imported",
                "state_label": row.get("cheque_status") or "ثبت‌شده در کارآمد",
                "amount": _number(row.get("amount_rial")),
                "due_date": effective_iso,
                "due_date_jalali": row.get("due_date_jalali") or effective_jalali,
                "days_until_due": days,
                "days_to_due": days,
                "serial_number": row.get("cheque_number") or row.get("transfer_number"),
                "series": row.get("cheque_series"),
                "sayad_number": row.get("sayad_number"),
                "account_number": row.get("account_number"),
                "bank_ref": None,
                "bank_name": row.get("bank"),
                "bank_branch_name": row.get("bank_and_branch") or row.get("branch"),
                "bank_branch_code": row.get("bank_branch_code"),
                "counterpart_ref": None,
                "counterpart_code": None,
                "counterpart_name": row.get("level4_name") or row.get("level5_name") or row.get("level6_name") or row.get("owner_name"),
                "description": row.get("purpose") or row.get("description"),
                "cheque_status": row.get("cheque_status"),
                "cheque_location": row.get("cheque_location"),
                "last_operation_account": row.get("last_operation_account"),
                "last_operation_level4": row.get("last_operation_level4"),
                "assignment_date_jalali": row.get("assignment_date_jalali"),
                "collection_date_jalali": row.get("collection_date_jalali"),
                "return_reason": row.get("return_reason"),
                "future_data_complete": row.get("future_data_complete"),
                "returns_available": row.get("returns_available"),
                "karamad_raw_status": row.get("karamad_raw_status"),
                "source_system": "karamad",
                "source_label": "کارآمد",
                "branch": row.get("branch"),
                "branch_name": row.get("branch"),
            })
        result.sort(key=lambda item: (item.get("due_date") or "", str(item.get("cheque_id") or "")))
        return result

    def report(self, month: str | None = None, direction: str | None = None, classification: str | None = None, search: str | None = None, limit: int = 500, offset: int = 0, branch: str | None = None) -> dict[str, Any]:
        rows = self._records(month=month, direction=direction, classification=classification, branch=branch)
        normalized_search = _text(search).casefold()
        if normalized_search:
            searchable = ("transfer_id", "transfer_number", "document_number", "bank", "branch", "purpose", "description", "level4_name", "level5_name", "level6_name")
            rows = [row for row in rows if normalized_search in " ".join(str(row.get(key) or "") for key in searchable).casefold()]
        rows.sort(key=lambda row: (row.get("registration_date_jalali") or "", row.get("transfer_id") or ""), reverse=True)
        limit, offset = max(1, min(int(limit), 5000)), max(0, int(offset))
        return {"status": "success", "source": "KarAmand Excel", "filters": {"month": month, "direction": direction, "classification": classification, "search": search, "branch": branch}, "summary": self.summary(month=month, branch=branch), "pagination": {"limit": limit, "offset": offset, "returned_count": len(rows[offset:offset + limit]), "total_count": len(rows), "has_more": offset + limit < len(rows)}, "movements": rows[offset:offset + limit]}

    def customer_summary(self, branch: str | None = None) -> dict[str, Any]:
        """Aggregate imported KarAmand activity by customer/counterpart name and branch."""
        rows = self._records(branch=branch)
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = _text(row.get("level4_name") or row.get("level5_name") or row.get("level6_name"))
            if not name:
                continue
            key = name.casefold()
            item = grouped.setdefault(key, {
                "customer_name": name, "branches": set(), "movement_count": 0,
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
            b = _text(row.get("branch"))
            if b: item["branches"].add(b)
            amount = float(row.get("amount_rial") or 0)
            item["movement_count"] += 1
            if row.get("direction") == "inflow": item["inflow_rial"] += amount
            else: item["outflow_rial"] += amount
            for kind, count_key, amount_key in (
                ("received_cheques", "received_cheque_count", "received_cheque_amount_rial"),
                ("issued_cheques", "issued_cheque_count", "issued_cheque_amount_rial"),
                ("received_transfers", "received_transfer_count", "received_transfer_amount_rial"),
                ("paid_transfers", "paid_transfer_count", "paid_transfer_amount_rial"),
            ):
                if kind in (row.get("source_kinds") or [row.get("source_kind")]):
                    item[count_key] += 1
                    item[amount_key] += amount
            if "received_cheques" in (row.get("source_kinds") or [row.get("source_kind")]):
                status = _text(row.get("cheque_status")).replace("ي", "ی").replace("ك", "ک")
                is_returned = any(token in status for token in ("برگشت", "واخواست", "مسترد"))
                if is_returned:
                    item["received_cheque_returned_count"] += 1
                    item["received_cheque_returned_amount_rial"] += amount
                due = parse_jalali_date(row.get("due_date_jalali") or row.get("transfer_date_jalali"))
                if due is not None and not is_returned:
                    delta = (due - date.today()).days
                    if delta < 0:
                        item["received_cheque_overdue_count"] += 1
                        item["received_cheque_overdue_amount_rial"] += amount
                    elif delta == 0:
                        item["received_cheque_today_count"] += 1
                        item["received_cheque_today_amount_rial"] += amount
                    else:
                        item["received_cheque_future_count"] += 1
                        item["received_cheque_future_amount_rial"] += amount
        customers=[]
        for item in grouped.values():
            item["branches"] = sorted(item["branches"])
            item["net_rial"] = round(item["inflow_rial"] - item["outflow_rial"], 2)
            customers.append(item)
        customers.sort(key=lambda x: (x["received_cheque_amount_rial"] + x["received_transfer_amount_rial"]), reverse=True)
        for item in customers:
            item["selected_branch"] = branch
        return {
            "status": "success", "source": "KarAmand Excel", "selected_branch": branch,
            "available_branches": sorted({_text(r.get("branch")) for r in self._state()["records"].values() if _text(r.get("branch"))}),
            "customer_count": len(customers), "customers": customers,
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

    def customer_detail(self, customer_name: str, branch: str | None = None) -> dict[str, Any]:
        """Return raw KarAmand rows for one customer, split like the Rahkaran customer detail view."""
        wanted = _text(customer_name).casefold()
        rows = self._records(branch=branch)
        matched: list[dict[str, Any]] = []
        for row in rows:
            names = [_text(row.get("level4_name")), _text(row.get("level5_name")), _text(row.get("level6_name"))]
            if wanted and wanted in {name.casefold() for name in names if name}:
                payload = dict(row)
                payload["customer_name"] = next((name for name in names if name), customer_name)
                payload["effective_date_jalali"] = row.get("due_date_jalali") or row.get("transfer_date_jalali") or row.get("registration_date_jalali")
                due = parse_jalali_date(row.get("due_date_jalali") or row.get("transfer_date_jalali"))
                payload["due_date_jalali"] = row.get("due_date_jalali") or row.get("transfer_date_jalali")
                payload["due_date"] = due.isoformat() if due else None
                payload["days_until_due"] = (due - date.today()).days if due else None
                payload["days_to_due"] = payload["days_until_due"]
                payload["source_system"] = "karamad"
                payload["source_label"] = "کارآمد"
                matched.append(payload)
        matched.sort(key=lambda row: (row.get("effective_date_jalali") or "", row.get("transfer_id") or ""), reverse=True)

        def by_kind(kind: str) -> list[dict[str, Any]]:
            return [row for row in matched if kind in (row.get("source_kinds") or [row.get("source_kind")])]

        def total(rows_: list[dict[str, Any]]) -> float:
            return round(sum(float(row.get("amount_rial") or 0) for row in rows_), 2)

        received_cheques = by_kind("received_cheques")
        issued_cheques = by_kind("issued_cheques")
        received_transfers = by_kind("received_transfers")
        paid_transfers = by_kind("paid_transfers")
        def is_returned(row: dict[str, Any]) -> bool:
            status = _text(row.get("cheque_status")).replace("ي", "ی").replace("ك", "ک")
            return any(token in status for token in ("برگشت", "واخواست", "مسترد"))
        returned_received = [row for row in received_cheques if is_returned(row)]
        open_received = [row for row in received_cheques if not is_returned(row)]
        overdue_received = [row for row in open_received if isinstance(row.get("days_until_due"), int) and row["days_until_due"] < 0]
        today_received = [row for row in open_received if row.get("days_until_due") == 0]
        future_received = [row for row in open_received if isinstance(row.get("days_until_due"), int) and row["days_until_due"] > 0]
        return {
            "status": "success",
            "source": "KarAmand Excel",
            "customer_name": customer_name,
            "selected_branch": branch,
            "branches": sorted({_text(row.get("branch")) for row in matched if _text(row.get("branch"))}),
            "summary": {
                "movement_count": len(matched),
                "inflow_rial": total([row for row in matched if row.get("direction") == "inflow"]),
                "outflow_rial": total([row for row in matched if row.get("direction") == "outflow"]),
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

    def status(self) -> dict[str, Any]:
        state = self._state()
        waiting = [str(path.relative_to(self.inbox)) for path in self.inbox.rglob("*.xlsx")]
        return {"status": "ready" if settings.karamad_excel_scan_enabled else "disabled", "enabled": settings.karamad_excel_scan_enabled, "inbox": str(self.inbox), "archive": str(self.archive), "scan_minutes": settings.karamad_excel_scan_minutes, "folders": [{"folder": folder, **meta} for folder, meta in SOURCE_FOLDERS.items()], "waiting_count": len(waiting), "waiting_files": waiting[:20], "last_scan_at": state.get("last_scan_at"), "last_error": state.get("last_error"), "summary": self.summary(state=state)}
