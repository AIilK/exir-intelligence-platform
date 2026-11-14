"""تطبیق ردیف‌های بانک با دفتر: امتیازدهی، چک، کارمزد، برگشتی و ترکیب مبالغ (از bank_reconciliation_service.py جدا شده)."""

from __future__ import annotations
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any
import unicodedata
from app.utils.jalali import format_jalali_date
from app.services.bank_statement_parser import _PERSIAN_DIGITS, _normalize_text


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
    } | _transaction_cheque_serials(transaction)
    return any(token in bank_text for token in item_tokens)


# بانک سپه سریال چک را به شکل «چ ش/سری/سریال» در شرح می‌آورد.
_BANK_CHEQUE_SERIAL_PATTERN = re.compile(r"چ\s*ش\s*/\s*\d+\s*/\s*(\d{4,})")


def _bank_cheque_serials(bank_row: dict[str, Any]) -> set[str]:
    """Explicit cheque serials stated by the bank (leading zeros removed)."""

    raw = unicodedata.normalize(
        "NFKC",
        str(bank_row.get("description") or ""),
    ).translate(_PERSIAN_DIGITS)
    serials = {
        serial.lstrip("0")
        for serial in _BANK_CHEQUE_SERIAL_PATTERN.findall(raw)
    }
    cheque_number = re.sub(
        r"\D",
        "",
        str(bank_row.get("cheque_number") or "").translate(_PERSIAN_DIGITS),
    )
    if len(cheque_number) >= 5:
        serials.add(cheque_number.lstrip("0"))
    return {serial for serial in serials if serial}


def _transaction_cheque_serials(transaction: dict[str, Any]) -> set[str]:
    """Serial candidates of a Rahkaran cheque event.

    ItemNumber شامل سریال، سری و شناسه صیادی است و ترتیب آن در همه منابع یکسان
    نیست؛ توکن‌های ۵ تا ۱۲ رقمی (بدون شناسه ۱۶ رقمی صیادی) نامزد سریال‌اند.
    """

    if transaction.get("transaction_type") not in {
        "received_cheque_status",
        "issued_cheque_status",
    }:
        return set()
    item_number = str(transaction.get("item_number") or "").translate(_PERSIAN_DIGITS)
    tokens = set(re.findall(r"\d+", item_number))
    # بعضی سریال‌ها در راهکاران با ممیز ثبت شده‌اند («605039/31») و بانک همان را
    # یکجا می‌نویسد («60503931»)؛ دو بخش کنار هم هم نامزد سریال است.
    tokens |= {left + right for left, right in re.findall(r"(\d+)\s*/\s*(\d+)", item_number)}
    return {
        token.lstrip("0")
        for token in tokens
        if 5 <= len(token.lstrip("0")) <= 12
    }


def _cheque_serial_contradicts(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    """Bank names one cheque serial and the Rahkaran cheque has another."""

    transaction_serials = _transaction_cheque_serials(transaction)
    if not transaction_serials:
        return False
    bank_serials = _bank_cheque_serials(bank_row)
    return bool(bank_serials) and not (transaction_serials & bank_serials)


def _cheque_serial_token_matches(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    """Rahkaran cheque serial appears as a whole number token in bank text."""

    transaction_serials = _transaction_cheque_serials(transaction)
    if not transaction_serials:
        return False
    bank_text = unicodedata.normalize(
        "NFKC",
        " ".join(
            str(bank_row.get(key) or "")
            for key in ("description", "reference", "cheque_number")
        ),
    ).translate(_PERSIAN_DIGITS)
    return bool(
        transaction_serials
        & {token.lstrip("0") for token in re.findall(r"\d+", bank_text)}
    )


def _document_lists_bank_serial(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    """Receipt/payment text lists the bank's cheque serial.

    نمونه: سند دریافت «نقد کردن چکهای 956902-...-857248» که سریال‌ها را در
    شرح آورده و ItemNumber آن سریال چک نیست.
    """

    if transaction.get("transaction_type") not in {"receipt", "payment"}:
        return False
    bank_serials = _bank_cheque_serials(bank_row)
    if not bank_serials:
        return False
    text_value = unicodedata.normalize(
        "NFKC",
        str(transaction.get("description") or ""),
    ).translate(_PERSIAN_DIGITS)
    document_tokens = {
        token.lstrip("0") for token in re.findall(r"\d{4,}", text_value)
    }
    return bool(bank_serials & document_tokens)


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
        # Bank Mellat statement wording for cleared/collected incoming cheques.
        "واریز چک کلر",
        "واریز چک کلر بانک",
        "واریزواگذاری جام",
        "واریز واگذاری جام",
        "واریز چک",
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
        # Bank Mellat uses these exact phrases for cheque withdrawals.
        "وصول چک چکاوک",
        "برداشت انتقالی طی چک",
        "برداشت انتقالی چک",
        "وصول چک",
    )
    return any(phrase in normalized for phrase in issued_phrases)


def _is_generic_bank_cheque_text(bank_row: dict[str, Any]) -> bool:
    """Detect cheque-related bank narratives even when the exact serial is absent.

    Bank Shahr and some other statement formats often mention a cheque/status
    operation without exposing the full cheque serial in a dedicated field.
    This helper is deliberately broad only on the bank-text side; final matching
    still requires withdrawal direction, exact amount, a Rahkaran issued-cheque
    status/term-change transaction, and a close date.
    """

    normalized = _normalize_text(
        " ".join(
            str(bank_row.get(key, ""))
            for key in ("description", "operation", "note", "reference")
        )
    )
    markers = (
        "چک",
        "چكاوك",
        "چکاوک",
        "صياد",
        "صیاد",
        "برگ چک",
        "تغيير وضعيت",
        "تغییر وضعیت",
    )
    return any(marker in normalized for marker in markers)


def _is_issued_cheque_term_change(transaction: dict[str, Any]) -> bool:
    """Detect Rahkaran status documents that mean long-term -> current/short-term.

    Some banks (notably Tejarat and a few other statement formats) do not put an
    explicit "cheque paid" phrase in the bank narration.  Rahkaran, however,
    records the accounting event as a cheque term/status change.  These phrases
    are therefore useful corroborating evidence, but never sufficient by
    themselves: the matcher still requires amount/direction/date and, for the
    relaxed bank-description path, an exact cheque serial match.
    """

    normalized = _normalize_text(
        " ".join(
            str(transaction.get(key, ""))
            for key in ("description", "reference_ref")
        )
    )
    phrases = (
        "تغییر مدت",
        "تغيير مدت",
        "تغییرمدت",
        "تغييرمدت",
        "کوتاه مدت",
        "کوتاه مدت چک",
        "کوتاه مدت شدن",
        "کوتاه مدت شده",
        "کوتاه مدت گردید",
        "بلند مدت به روز",
        "بلندمدت به روز",
        "بلند مدت به کوتاه مدت",
        "بلندمدت به کوتاه مدت",
        "تبدیل بلند مدت",
        "تبديل بلند مدت",
        "تبدیل بلندمدت",
        "تبديل بلندمدت",
        "تعیین وضعیت چک",
        "تعین وضعیت چک",
    )
    return any(phrase in normalized for phrase in phrases)


def _is_received_cheque_collection_transaction(transaction: dict[str, Any]) -> bool:
    """Identify approved Rahkaran received-cheque status rows that represent collection.

    Different Rahkaran installations/status workflows do not always use the same
    ReceivableNoteTransaction.State or DocumentItemType.  The accounting text is
    more stable, so after broad SQL retrieval we keep only rows whose description
    is collection/status related (or whose cheque serial matches exactly).
    """

    normalized = _normalize_text(
        " ".join(
            str(transaction.get(key, ""))
            for key in ("description", "reference_ref")
        )
    )
    # «مشکوک الوصول / سنواتی و مشکوک وصول» نام گروه طرف‌حساب در اسناد «برگ
    # دریافت چک» است، نه رویداد وصول.
    for label in ("مشکوک الوصول", "مشکوکالوصول", "مشکوک وصول"):
        normalized = normalized.replace(label, " ")
    markers = (
        "وصولی",
        "وصول",
        "وصول چک",
        "نقد کردن چک",
        "نقد چک",
        "تعیین وضعیت چک",
        "تعین وضعیت چک",
        "تغيير وضعيت چک",
        "تغییر وضعیت چک",
    )
    return any(marker in normalized for marker in markers)


def _transaction_type_is_compatible(
    bank_row: dict[str, Any],
    transaction: dict[str, Any],
) -> bool:
    # وصول چک نباید صرفاً به دلیل برابری مبلغ و تاریخ به واریز پایا، ساتنا
    # یا انتقال عادی متصل شود.
    if transaction.get("transaction_type") == "received_cheque_status":
        # خود ردیف بانک باید صراحتاً رویداد چک باشد. فیلتر SQL فقط رویدادهای
        # تاییدشده و محتملِ وصول را وارد Candidate می‌کند؛ سریال/شرح/مبلغ/تاریخ
        # در امتیازدهی برای انتخاب یکتا استفاده می‌شوند.
        # چک هم‌بانک (مثلاً سپه به سپه) در صورت‌حساب به شکل «انتقال وجه ... از
        # 0149 679540» می‌آید؛ اگر سریال چک راهکاران به‌صورت عدد مستقل در
        # متن بانک باشد، رویداد چکی محسوب می‌شود.
        return _is_bank_cheque_event(bank_row) or _cheque_serial_token_matches(
            bank_row, transaction
        )
    if transaction.get("transaction_type") == "issued_cheque_status":
        if _is_bank_issued_cheque_event(bank_row):
            return True
        # بانک تجارت و بعضی بانک‌ها متن صریح «وصول چک» ندارند. اگر سریال
        # خود چک در صورت‌حساب دقیقاً با PayableNote راهکاران برابر باشد،
        # اجازه می‌دهیم Candidate وارد امتیازدهی شود. مبلغ/جهت/تاریخ در
        # _candidate_score همچنان الزامی است و از Match اشتباه جلوگیری می‌کند.
        if bank_row.get("direction") == "withdrawal" and _cheque_serial_matches(
            bank_row, transaction
        ):
            return True
        # بانک شهر و برخی خروجی‌ها سریال کامل چک را در فایل بانک نمی‌دهند.
        # اگر متن بانک مشخصاً مربوط به چک باشد و سند راهکاران نیز «تغییر مدت /
        # تعیین وضعیت» باشد، Candidate را وارد امتیازدهی می‌کنیم. در مرحله بعد
        # مبلغ دقیق، برداشت بودن و فاصله تاریخ همچنان اجباری‌اند.
        if (
            bank_row.get("direction") == "withdrawal"
            and _is_generic_bank_cheque_text(bank_row)
            and _is_issued_cheque_term_change(transaction)
        ):
            return True
        return False
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
    # بانک سریال چک را صریحاً گفته و چک راهکاران سریال دیگری دارد؛ این دو
    # یک چک نیستند، حتی اگر مبلغ و تاریخ برابر باشد.
    if _cheque_serial_contradicts(bank_row, transaction):
        return None

    day_difference = _closest_day_difference(bank_row, transaction)
    if day_difference is None:
        return None
    cheque_serial_match = _cheque_serial_matches(
        bank_row, transaction
    ) or _document_lists_bank_serial(bank_row, transaction)
    # تاریخ ثبت تغییر وضعیت چک صادرشده در راهکاران همیشه تاریخ برداشت بانک
    # نیست. در نمونه واقعی بانک تجارت، ثبت وضعیت تا ۳۷ روز بعد انجام شده است.
    # وقتی حساب، جهت، مبلغ و سریال چک همگی دقیق‌اند، فاصله زمانی تا ۴۵ روز
    # پذیرفته می‌شود؛ برای سایر تراکنش‌ها همان تلورانس انتخابی کاربر می‌ماند.
    term_change_without_serial = (
        transaction.get("transaction_type") == "issued_cheque_status"
        and _is_issued_cheque_term_change(transaction)
        and _is_generic_bank_cheque_text(bank_row)
        and not cheque_serial_match
    )
    received_collection_without_serial = (
        transaction.get("transaction_type") == "received_cheque_status"
        and _is_bank_cheque_event(bank_row)
        and _is_received_cheque_collection_transaction(transaction)
        and not cheque_serial_match
    )
    # برای بانک شهر ممکن است سریال در صورت‌حساب نباشد؛ وقتی هم متن بانک چکی
    # است و هم سند راهکاران تغییر مدت/تعیین وضعیت است، تا 7 روز اختلاف تاریخ
    # می‌پذیریم. این مسیر همچنان فقط با مبلغ دقیق و جهت برداشت فعال می‌شود.
    allowed_days = (
        max(tolerance_days, 45)
        if cheque_serial_match
        else max(tolerance_days, 7)
        if term_change_without_serial or received_collection_without_serial
        else tolerance_days
    )
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
        if (
            transaction.get("transaction_type") == "issued_cheque_status"
            and _is_issued_cheque_term_change(transaction)
        ):
            score += 5
            reasons.append("سند راهکاران تغییر مدت / کوتاه‌مدت شدن چک را ثبت کرده است")
    elif term_change_without_serial:
        score += 15
        reasons.append("شرح بانک مربوط به چک و سند راهکاران تغییر مدت / تعیین وضعیت است")
    elif received_collection_without_serial:
        score += 15
        reasons.append("شرح بانک و سند راهکاران هر دو رویداد وصول / تعیین وضعیت چک را نشان می‌دهند")
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
    if _cheque_serial_contradicts(bank_row, transaction):
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
        "booking_date_jalali": format_jalali_date(
            transaction.get("booking_date")
        ),
        "settlement_date": (
            transaction["settlement_date"].isoformat()
            if transaction["settlement_date"]
            else None
        ),
        "settlement_date_jalali": format_jalali_date(
            transaction.get("settlement_date")
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
        "member_documents": transaction.get("member_documents", []),
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
        # Bank Mellat cheque assignment/service-fee wording.
        "واگذاری چک",
        # Bank Sepah: «دريافت وجه واگذاري و واگذاري» بدون واژه کارمزد.
        "دریافت وجه واگذاری",
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
            tied = [
                candidate
                for candidate in candidates
                if candidate[0] == 1
                and candidate[1] >= candidates[0][1] - 0.05
            ]
            # برداشت‌های هم‌مبلغ، هم‌روز و هم‌شرح از هم قابل تفکیک نیستند؛
            # انتخاب هر کدام نتیجه یکسانی دارد. نزدیک‌ترین برداشت قبل از برگشت
            # انتخاب می‌شود (نمونه: دو کارمزد ۵٬۰۰۰ پل و یک برگشت).
            if (
                len(
                    {
                        _normalize_text(candidate[3].get("description"))
                        for candidate in tied
                    }
                )
                != 1
            ):
                continue
            preceding = [
                candidate
                for candidate in tied
                if candidate[3]["row_number"] < reversal["row_number"]
            ]
            candidates = [
                max(preceding, key=lambda candidate: candidate[3]["row_number"])
                if preceding
                else min(tied, key=lambda candidate: candidate[3]["row_number"])
            ]

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


def _combine_fee_documents(
    bank_date: date,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge several same-day Rahkaran fee documents into one match target."""

    ordered = sorted(documents, key=lambda document: str(document.get("document_number") or ""))
    first = ordered[0]
    return {
        **first,
        "transaction_id": f"fee_documents:{bank_date.isoformat()}",
        "document_id": None,
        "document_number": " + ".join(
            str(document.get("document_number") or "") for document in ordered
        ),
        "item_number": " + ".join(
            str(document.get("item_number") or "")
            for document in ordered
            if document.get("item_number") not in (None, "")
        ),
        "amount": sum((document["amount"] for document in ordered), Decimal("0")),
        "entry_amount": sum(
            (document.get("entry_amount", document["amount"]) for document in ordered),
            Decimal("0"),
        ),
        "gl_amount": sum(
            (document.get("gl_amount", Decimal("0")) for document in ordered),
            Decimal("0"),
        ),
        "description": " | ".join(
            f"سند {document.get('document_number')}: {document['amount']:,.0f}"
            for document in ordered
        ),
        "member_transaction_ids": [
            member_id
            for document in ordered
            for member_id in document.get("member_transaction_ids", [])
        ],
        "member_documents": [
            {
                "document_number": document.get("document_number"),
                "amount": float(document["amount"]),
            }
            for document in ordered
        ],
    }


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

            # خزانه گاهی کارمزدهای یک روز را در چند سند جدا ثبت می‌کند (مثلاً
            # کارمزد واگذاری چک در یک سند و کارمزد پایا/پل در سند دیگر). اگر
            # جمع همه اسناد کارمزد همان روز با جمع کارمزدهای بانک برابر باشد،
            # کل گروه سندخورده است.
            if len(date_documents) > 1:
                combined_total = sum(
                    (document["amount"] for document in date_documents),
                    Decimal("0"),
                )
                if abs(combined_total - group_total) <= Decimal("0.01"):
                    store_group_result(
                        group,
                        _combine_fee_documents(bank_date, date_documents),
                        [],
                    )
                    date_documents = []
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
