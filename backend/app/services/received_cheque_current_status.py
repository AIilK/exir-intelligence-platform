from __future__ import annotations

import re

"""SQL helpers for Rahkaran received-cheque *current* business status.

Rahkaran keeps the cheque master row and a transaction/history table.  The UI
report called ``وضعیت فعلی`` is operation-driven; using ``ReceivableNote.State``
alone can therefore leave already-moved/settled cheques in the open portfolio
or miss a cheque that has been moved back to an active location.

The current status below follows the latest approved ReceivableNoteTransaction
for each cheque. The master note state remains the candidate gate for whether
a cheque can be open; the latest transaction is only a business-status override.
"""

KNOWN_TERMINAL_RECEIVED_STATES = (3, 4, 10)


def current_received_status_apply(
    note_alias: str = "note",
    status_alias: str = "current_status",
) -> str:
    """OUTER APPLY returning the latest approved cheque transaction."""

    return f"""
        OUTER APPLY (
            SELECT TOP (1)
                rnt.[State] AS [CurrentChequeState],
                rnt.[Description] AS [CurrentStatusDescription],
                rnt.[Date] AS [CurrentStatusDate],
                rnt.[DocumentDate] AS [CurrentStatusDocumentDate],
                rnt.[ReceivableNoteTransactionID] AS [CurrentStatusTransactionID],
                rnt.[BankAccountRef] AS [CurrentBankAccountRef],
                rnt.[DocumentItemType] AS [CurrentDocumentItemType],
                rnt.[DocumentRef] AS [CurrentDocumentRef],
                rnt.[DocumentNumber] AS [CurrentDocumentNumber]
            FROM RPA3.[ReceivableNoteTransaction] AS rnt
            WHERE rnt.[ReceivableNoteRef] = {note_alias}.[ReceivableNoteID]
              AND (rnt.[DocumentState] = 3 OR rnt.[DocumentState] IS NULL)
            ORDER BY
                rnt.[Date] DESC,
                rnt.[DocumentDate] DESC,
                rnt.[ReceivableNoteTransactionID] DESC
        ) AS {status_alias}
    """


def current_received_state_expr(
    note_alias: str = "note",
    status_alias: str = "current_status",
) -> str:
    return f"{note_alias}.[State]"


def current_received_status_description_expr(
    status_alias: str = "current_status",
) -> str:
    return f"ISNULL({status_alias}.[CurrentStatusDescription], N'')"


def received_cheque_open_expression(
    note_alias: str = "note",
    status_alias: str = "current_status",
) -> str:
    """Return only the three management-approved open holding locations.

    Final business rule (V117): a received cheque belongs to the open portfolio
    only when its *current holding* is one of these three buckets:
      1) نزد مأمور وصول
      2) نزد بانک
      3) نزد صندوق

    We deliberately exclude intermediate phrases such as
    ``در انتظار واگذاری به مأمور وصول`` because the cheque is not yet physically
    نزد مأمور وصول.  Master state remains a safe fallback only when the latest
    transaction does not provide a contradictory/terminal description.
    """

    description = current_received_status_description_expr(status_alias)
    terminal = f"""(
        {description} LIKE N'%مسترد%'
        OR {description} LIKE N'%استرداد%'
        OR {description} LIKE N'%واخواست%'
        OR {description} LIKE N'%نقد شده%'
        OR {description} LIKE N'%نقد‌شده%'
        OR {description} LIKE N'%وصول شده%'
        OR {description} LIKE N'%وصول‌شده%'
        OR ({description} LIKE N'%واگذار%' AND {description} LIKE N'%غیر%')
    )"""
    collector = f"""(
        {description} NOT LIKE N'%در انتظار%'
        AND {description} NOT LIKE N'%منتظر%'
        AND (
            {description} LIKE N'%نزد مأمور وصول%'
            OR {description} LIKE N'%نزد مامور وصول%'
            OR {description} LIKE N'%تحویل مأمور وصول%'
            OR {description} LIKE N'%تحویل مامور وصول%'
            OR {description} LIKE N'%واگذار%مأمور وصول%'
            OR {description} LIKE N'%واگذار%مامور وصول%'
        )
    )"""
    # Rahkaran often stores a neutral operation description such as «برگ دریافت چک»
    # on future notes.  That text is NOT a holding location.  Therefore, after
    # terminal outcomes have been excluded, master State remains the authoritative
    # holding fallback even when the latest description is non-empty:
    #   State=1 -> نزد صندوق, State=2 -> نزد بانک.
    # Explicit collector text overrides the display bucket but is still open.
    bank = f"""(
        {description} LIKE N'%نزد بانک%'
        OR {description} LIKE N'%در جریان وصول%'
        OR {status_alias}.[CurrentBankAccountRef] IS NOT NULL
        OR {note_alias}.[State] = 2
    )"""
    cashbox = f"""(
        {description} LIKE N'%نزد صندوق%'
        OR {description} LIKE N'%نزد شرکت%'
        OR (
            {note_alias}.[State] = 1
            AND {status_alias}.[CurrentBankAccountRef] IS NULL
            AND NOT {collector}
        )
    )"""
    return f"""(
        {note_alias}.[State] IN (1, 2)
        AND NOT {terminal}
        AND ({collector} OR {bank} OR {cashbox})
    )"""


def received_cheque_open_predicate(
    note_alias: str = "note",
    status_alias: str = "current_status",
) -> str:
    return "AND " + received_cheque_open_expression(note_alias, status_alias)


def current_received_holding_label(state: int | None, description: str | None = None) -> str:
    """Human-readable label restricted to the three approved open buckets."""

    text = (description or "").replace("ي", "ی").replace("ك", "ک")
    terminal_words = ("مسترد", "استرداد", "واخواست", "نقد شده", "نقد‌شده", "وصول شده", "وصول‌شده")
    if any(word in text for word in terminal_words) or ("واگذار" in text and "غیر" in text):
        return "وضعیت تعیین‌تکلیف‌شده"
    if ("مأمور وصول" in text or "مامور وصول" in text) and ("در انتظار" in text or "منتظر" in text):
        return "وضعیت خارج از سبد باز"
    if ("مأمور وصول" in text or "مامور وصول" in text):
        return "نزد مأمور وصول"
    if "نزد بانک" in text or "در جریان وصول" in text:
        return "نزد بانک"
    if "نزد صندوق" in text or "نزد شرکت" in text:
        return "نزد صندوق"
    if state == 2:
        return "نزد بانک"
    if state == 1:
        return "نزد صندوق"
    return "وضعیت خارج از سبد باز"


def received_cheque_is_approved_open_holding(row: dict) -> bool:
    """Python-side guard used for KarAmand snapshots and merged portfolios.

    V128: for a KarAmand full snapshot, the explicit latest Excel status is authoritative.
    Older description/return fields must not override a newer ``واگذار شده``/``نزد صندوق`` status.
    """
    if str(row.get("source_system") or "").casefold() == "karamad":
        status_text = str(row.get("cheque_status") or row.get("state_label") or "").replace("ي", "ی").replace("ك", "ک").replace("نزذ", "نزد").strip()
        # V129: in the KarAmand received-cheque snapshot, blank/legacy-unknown status is
        # an approved cashbox holding. This also keeps old snapshots correct until re-uploaded.
        # V157: «غیرقطعی» (tblChequeDStatus code 1) is Karamad's own not-yet-final status,
        # so it is treated the same as blank/unknown.
        if not status_text or status_text in {"وضعیت نامشخص", "نامشخص", "karamad_imported", "ثبت‌شده در کارآمد", "غیرقطعی"}:
            return True
        if status_text:
            # V157: a returned cheque still sitting at the cashbox or with the customer
            # (tblChequeDStatus codes 6, 7, 10 — «برگشت/برگشتی نزد صندوق»، «برگشتی نزد مشتری»)
            # is business-non-final and must stay in the open portfolio. Only cheques that
            # were actually collected, spent, or physically refunded to the customer close out.
            if re.search(r"برگشتی?\s*نزد\s*(?:صندوق|مشتری)", status_text):
                return True
            if any(word in status_text for word in ("مسترد", "استرداد", "واخواست", "نقد شده", "نقد‌شده", "وصول شده", "وصول‌شده", "خرج شده", "خرج‌شده", "عودت")):
                return False
            if "واگذار" in status_text and "غیر" in status_text:
                return False
            if (("مأمور وصول" in status_text or "مامور وصول" in status_text) and "در انتظار" not in status_text and "منتظر" not in status_text):
                return True
            if "نزد بانک" in status_text or "در جریان وصول" in status_text or status_text == "واگذار شده":
                return True
            if "نزد صندوق" in status_text or "نزد شرکت" in status_text:
                return True
            return False
    text = " ".join(str(row.get(k) or "") for k in (
        "state_label", "cheque_status", "cheque_location", "last_operation_account",
        "last_operation_level4", "current_status_description", "description"
    )).replace("ي", "ی").replace("ك", "ک")
    if any(word in text for word in ("مسترد", "استرداد", "واخواست", "برگشتی", "نقد شده", "نقد‌شده", "وصول شده", "وصول‌شده")):
        return False
    if "واگذار" in text and "غیر" in text:
        return False
    if ("مأمور وصول" in text or "مامور وصول" in text) and "در انتظار" not in text and "منتظر" not in text:
        return True
    if "نزد بانک" in text or "در جریان وصول" in text or "واگذار شده" in text:
        return True
    if "نزد صندوق" in text or "نزد شرکت" in text:
        return True
    state = row.get("state_code")
    return (state in (1, 2)) and not text.strip()
