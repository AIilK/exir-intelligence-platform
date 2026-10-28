from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    gregorian_month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    adjusted_year = year - 1600
    adjusted_month = month - 1
    adjusted_day = day - 1
    gregorian_day_number = (
        365 * adjusted_year
        + (adjusted_year + 3) // 4
        - (adjusted_year + 99) // 100
        + (adjusted_year + 399) // 400
    )
    for index in range(adjusted_month):
        gregorian_day_number += gregorian_month_days[index]
    if adjusted_month > 1 and (
        adjusted_year % 4 == 0
        and (adjusted_year % 100 != 0 or adjusted_year % 400 == 0)
    ):
        gregorian_day_number += 1
    gregorian_day_number += adjusted_day

    jalali_day_number = gregorian_day_number - 79
    jalali_cycle = jalali_day_number // 12053
    jalali_day_number %= 12053
    jalali_year = 979 + 33 * jalali_cycle + 4 * (jalali_day_number // 1461)
    jalali_day_number %= 1461
    if jalali_day_number >= 366:
        jalali_year += (jalali_day_number - 1) // 365
        jalali_day_number = (jalali_day_number - 1) % 365
    if jalali_day_number < 186:
        jalali_month = 1 + jalali_day_number // 31
        jalali_day = 1 + jalali_day_number % 31
    else:
        jalali_month = 7 + (jalali_day_number - 186) // 30
        jalali_day = 1 + (jalali_day_number - 186) % 30
    return jalali_year, jalali_month, jalali_day


def _jalali_to_gregorian(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert a Jalali calendar date to Gregorian without optional packages."""
    jy = year + 1595
    days = (
        -355668
        + 365 * jy
        + (jy // 33) * 8
        + ((jy % 33 + 3) // 4)
        + day
        + ((month - 1) * 31 if month < 7 else (month - 7) * 30 + 186)
    )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd


def parse_jalali_date(value: Any) -> date | None:
    """Parse YYYY/MM/DD Jalali text into a Gregorian ``date``."""
    if value in (None, ""):
        return None
    normalized = str(value).translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS).strip()
    match = re.fullmatch(r"(1[34]\d{2})[/.-](\d{1,2})[/.-](\d{1,2})", normalized)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    try:
        return date(*_jalali_to_gregorian(year, month, day))
    except ValueError:
        return None


def _as_gregorian_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    normalized = str(value).translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS).strip()
    if re.fullmatch(r"1[34]\d{2}[/.-]\d{1,2}[/.-]\d{1,2}", normalized):
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
    except ValueError:
        match = re.search(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", normalized)
        if not match:
            return None
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            return None


def format_jalali_date(value: Any) -> str | None:
    """Return YYYY/MM/DD for Gregorian date-like values; preserve Jalali input."""
    if value in (None, ""):
        return None
    normalized = str(value).translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS).strip()
    match = re.fullmatch(r"(1[34]\d{2})[/.-](\d{1,2})[/.-](\d{1,2})", normalized)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return f"{year:04d}/{month:02d}/{day:02d}"
    gregorian = _as_gregorian_date(value)
    if gregorian is None:
        return None
    year, month, day = _gregorian_to_jalali(gregorian.year, gregorian.month, gregorian.day)
    return f"{year:04d}/{month:02d}/{day:02d}"


def format_jalali_datetime(value: Any) -> str | None:
    """Return a Jalali date plus time when an ISO datetime includes one."""
    jalali_date = format_jalali_date(value)
    if jalali_date is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return jalali_date
    return f"{jalali_date} {parsed:%H:%M}"
