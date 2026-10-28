"""احتمال برگشت هر چک باز یک مشتری — مشترک بین راهکاران و کارآمد.

همان منطق مدل پرتفوی (finance_prediction_service.cheque_return_predictions):
نرخ برگشت تجربی خود مشتری به‌عنوان پایه + تعدیل‌های مخصوص همان چک،
با همان آستانه‌ها (بالا ≥ ۳۵٪، متوسط ≥ ۱۸٪). چون این محاسبه فقط روی
چک‌های همان مشتری انجام می‌شود، برای صفحه پرونده مشتری سریع است.

برای مشتری کم‌سابقه، نرخ تجربی با یک پیش‌فرض ۱۰٪ و وزن ۵ چک هموار می‌شود
تا مثلاً یک برگشتی از دو چک، احتمال ۵۰٪ نسازد.
"""

from __future__ import annotations

from typing import Any

PRIOR_RETURN_RATE = 0.10
PRIOR_WEIGHT = 5.0
ALLOWED_TERM_DAYS = 90
HIGH_THRESHOLD = 0.35
MEDIUM_THRESHOLD = 0.18


STALE_AFTER_DAYS = 30
# Rahkaran RPA3.ReceivableNote.State (SYS3.Lookup NoteState). Only a cheque still held by the
# company, its bank or its collector can bounce, so only those states get a probability.
RAHKARAN_OPEN_STATES = {1, 2, 16, 29}          # نزد صندوق، نزد بانک، نزد مأمور وصول
RAHKARAN_COLLECTED_STATES = {3, 30, 32, 33}    # وصول شده، نقد شده توسط مأمور وصول، نقد شده حقوقی، تسویه شده
RAHKARAN_RETURNED_STATES = {4, 10, 17, 26}     # واخواست شده، مسترد شده، حقوقی شده، مسترد شده نزد صندوق
# Any other Rahkaran state (e.g. 6 واگذار شده به غیر، 34 سوخت شده) left the company's hands: closed.


def _rahkaran_state(row: dict[str, Any]) -> int | None:
    state = row.get("master_state")
    return int(state) if isinstance(state, int) and state else None


def _status(row: dict[str, Any]) -> str:
    text = str(row.get("cheque_status") or row.get("state_label") or "")
    return text.replace("ي", "ی").replace("ك", "ک").replace("‌", " ")


def is_returned(row: dict[str, Any]) -> bool:
    state = _rahkaran_state(row)
    if state is not None:
        return state in RAHKARAN_RETURNED_STATES
    return any(t in _status(row) for t in ("برگشت", "واخواست", "مسترد"))


def is_closed(row: dict[str, Any]) -> bool:
    """A Rahkaran cheque that is neither open, collected nor returned (spent, voided, ...)."""
    state = _rahkaran_state(row)
    return state is not None and state not in (
        RAHKARAN_OPEN_STATES | RAHKARAN_COLLECTED_STATES | RAHKARAN_RETURNED_STATES)


def is_collected(row: dict[str, Any]) -> bool:
    """Only explicit final collection; «در جریان وصول» is still open.

    Karamad never marks a cheque collected: it stays «واگذار شده» (in bank, V129).
    A cheque that is in the bank more than 30 days after its due date without
    being returned has cleared, so it counts as collected history.
    """
    if is_returned(row):
        return False
    state = _rahkaran_state(row)
    if state is not None:
        return state in RAHKARAN_COLLECTED_STATES
    status = _status(row)
    if any(t in status for t in ("وصول شده", "نقد شده")):
        return True
    days = _days(row)
    return "واگذار شده" in status and days is not None and days < -STALE_AFTER_DAYS


def _amount(row: dict[str, Any]) -> float:
    return float(row.get("amount_rial") or row.get("amount") or 0)


def _days(row: dict[str, Any]) -> int | None:
    for key in ("days_until_due", "days_to_due"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def attach_return_risk(cheques: list[dict[str, Any]], history: dict[str, Any] | None = None) -> dict[str, Any]:
    """Adds ``return_risk`` to every row in-place and returns a customer summary.

    Returned cheques get ``state="returned"``, collected ones ``state="collected"``, Rahkaran
    cheques that otherwise left the company ``state="closed"``; only still-open cheques get a
    probability.

    ``history`` ({"collected_count", "returned_count", "average_amount_rial"}) overrides
    the base rate when ``cheques`` is not the full history (Karamad's live feed only
    contains open cheques).
    """
    returned = [r for r in cheques if is_returned(r)]
    collected = [r for r in cheques if is_collected(r)]
    closed = [r for r in cheques if is_closed(r)]
    unresolved = [r for r in cheques if not is_returned(r) and not is_collected(r) and not is_closed(r)]
    # Long past due with no final state: history we cannot classify, not a live cheque.
    stale = [r for r in unresolved if (_days(r) is not None and _days(r) < -STALE_AFTER_DAYS)]
    open_rows = [r for r in unresolved if r not in stale]

    if history is not None:
        returned_count = int(history.get("returned_count") or 0)
        resolved = returned_count + int(history.get("collected_count") or 0)
        average_amount = float(history.get("average_amount_rial") or 0)
    else:
        returned_count = len(returned)
        resolved = len(returned) + len(collected)
        history_amounts = [_amount(r) for r in returned + collected if _amount(r) > 0]
        average_amount = sum(history_amounts) / len(history_amounts) if history_amounts else 0.0
    base = (returned_count + PRIOR_RETURN_RATE * PRIOR_WEIGHT) / (resolved + PRIOR_WEIGHT)
    open_amount = sum(_amount(r) for r in open_rows)
    overdue_amount = sum(_amount(r) for r in open_rows if (_days(r) or 0) < 0)
    overdue_ratio = overdue_amount / open_amount if open_amount else 0.0

    base_reason = (
        f"از {resolved} چک تعیین‌تکلیف‌شده این مشتری، {returned_count} چک برگشت خورده است."
        if resolved
        else "مشتری سابقه چک تعیین‌تکلیف‌شده ندارد؛ نرخ پیش‌فرض ۱۰٪ استفاده شد."
    )

    for row in returned:
        row["return_risk"] = {"state": "returned", "label": "برگشت خورده"}
    for row in collected:
        row["return_risk"] = {"state": "collected", "label": "وصول شده"}
    for row in closed:
        row["return_risk"] = {"state": "closed", "label": str(row.get("state_label") or "تعیین‌تکلیف‌شده")}
    for row in stale:
        row["return_risk"] = {"state": "unresolved", "label": "وضعیت نهایی نامشخص"}

    high_count = 0
    for row in open_rows:
        probability = base
        reasons = [base_reason]
        term_days = row.get("term_days")
        if isinstance(term_days, (int, float)) and term_days > ALLOWED_TERM_DAYS:
            probability += min(0.15, (term_days - ALLOWED_TERM_DAYS) / 365.0)
            reasons.append(f"سررسید {int(term_days)} روزه از سقف {ALLOWED_TERM_DAYS} روز بیشتر است.")
        ratio = _amount(row) / average_amount if average_amount else 0.0
        if ratio >= 2.0:
            probability += 0.08
            reasons.append("مبلغ چک حداقل دو برابر میانگین چک‌های قبلی این مشتری است.")
        elif ratio >= 1.5:
            probability += 0.04
            reasons.append("مبلغ چک به‌طور محسوسی از میانگین چک‌های قبلی مشتری بالاتر است.")
        if overdue_ratio >= 0.25:
            probability += 0.08
            reasons.append("بخش قابل توجهی از چک‌های باز این مشتری سررسیدگذشته است.")
        days = _days(row)
        if days is not None and days < 0:
            probability += 0.10
            reasons.append(f"{abs(days)} روز از سررسید گذشته و هنوز وصول نشده است.")

        probability = max(0.01, min(probability, 0.95))
        level = "high" if probability >= HIGH_THRESHOLD else "medium" if probability >= MEDIUM_THRESHOLD else "low"
        high_count += level == "high"
        row["return_risk"] = {
            "state": "open",
            "probability_percent": round(probability * 100, 1),
            "level": level,
            "label": {"high": "احتمال برگشت بالا", "medium": "احتمال برگشت متوسط", "low": "احتمال برگشت کم"}[level],
            "reasons": reasons,
        }

    return {
        "base_return_rate_percent": round(base * 100, 1),
        "resolved_cheque_count": resolved,
        "returned_cheque_count": returned_count,
        "open_cheque_count": len(open_rows),
        "unresolved_cheque_count": len(stale),
        "high_risk_open_count": high_count,
        "method": "customer_empirical_return_rate_with_prior_plus_cheque_adjustments",
    }
