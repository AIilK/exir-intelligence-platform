
"""
V161 patch: Received Karamad cheques - Uncertain filter.

Business rule:
    uncertain = Status is NULL, empty, or whitespace.
This patch does NOT alter the source rows or any other cheque status.
"""
from typing import Any

def is_uncertain_received_cheque(row: dict[str, Any]) -> bool:
    # Support the common status field names used by the existing API.
    value = row.get("status", row.get("Status", row.get("StatusRef")))
    # IMPORTANT: for the new "uncertain" bucket we only treat textual/NULL
    # empty status as uncertain. Numeric StatusRef values remain explicit.
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def filter_received_cheques(rows: list[dict[str, Any]], status: str | None = None):
    """
    status:
      None / 'all' -> unchanged dataset
      'uncertain'  -> only rows with empty/NULL status
    """
    if not status or status == "all":
        return rows
    if status == "uncertain":
        return [row for row in rows if is_uncertain_received_cheque(row)]
    return rows
