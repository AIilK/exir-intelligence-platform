"""مشترک خزانه: اتصال SQL راهکاران و تبدیل عدد/تاریخ (از treasury_service.py جدا شده)."""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from sqlalchemy.engine import Engine
from app.database.sqlserver import get_sqlserver_engine


def _as_number(value: Any) -> int | float:
    if value is None:
        return 0.0
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _as_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _as_jalali_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import jdatetime
    except ImportError:
        return None

    if isinstance(value, datetime):
        gregorian_date = value.date()
    elif isinstance(value, date):
        gregorian_date = value
    else:
        try:
            gregorian_date = datetime.fromisoformat(str(value)).date()
        except ValueError:
            return None

    return jdatetime.date.fromgregorian(date=gregorian_date).isoformat().replace("-", "/")


def _engine(engine: Engine | None) -> Engine:
    return engine or get_sqlserver_engine()
