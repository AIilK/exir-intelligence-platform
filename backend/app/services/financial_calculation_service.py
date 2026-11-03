from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal


MAX_VALUES = 500


def _decimal(value: str) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Invalid financial number: {value}") from exc
    if not number.is_finite():
        raise ValueError("Financial numbers must be finite")
    return number


def _rounded(value: Decimal, precision: int) -> str:
    safe_precision = max(0, min(int(precision), 6))
    quantum = Decimal(1).scaleb(-safe_precision)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded:.{safe_precision}f}"


def calculate_percentage(
    part: str,
    total: str,
    precision: int = 2,
) -> dict[str, str | int]:
    """درصد دقیق part از total را با Decimal محاسبه می‌کند."""

    part_value = _decimal(part)
    total_value = _decimal(total)
    if total_value == 0:
        raise ValueError("Percentage total cannot be zero")

    result = (part_value / total_value) * Decimal(100)
    return {
        "status": "success",
        "operation": "percentage",
        "part": str(part_value),
        "total": str(total_value),
        "result": _rounded(result, precision),
        "unit": "percent",
        "precision": max(0, min(int(precision), 6)),
    }


def calculate_aggregate(
    operation: Literal["sum", "average", "difference"],
    values: list[str],
    precision: int = 2,
) -> dict[str, object]:
    """جمع، میانگین یا تفاضل مبالغ را با Decimal محاسبه می‌کند."""

    if not values:
        raise ValueError("At least one financial value is required")
    if len(values) > MAX_VALUES:
        raise ValueError(f"At most {MAX_VALUES} values are allowed")

    numbers = [_decimal(value) for value in values]
    if operation == "sum":
        result = sum(numbers, Decimal(0))
    elif operation == "average":
        result = sum(numbers, Decimal(0)) / Decimal(len(numbers))
    elif operation == "difference":
        result = numbers[0] - sum(numbers[1:], Decimal(0))
    else:
        raise ValueError("Unsupported financial operation")

    return {
        "status": "success",
        "operation": operation,
        "values": [str(number) for number in numbers],
        "result": _rounded(result, precision),
        "precision": max(0, min(int(precision), 6)),
    }
