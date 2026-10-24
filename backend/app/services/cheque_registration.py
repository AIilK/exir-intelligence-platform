"""«ثبت در سیستم»: چه کسی و چه زمانی هر چک را در راهکاران یا کارآمد ثبت کرده است (فقط خواندنی).

منبع:
- راهکاران دریافتی: اولین رسید دریافت (RPA3.Receipt) که چک در آن آمده؛ Creator و CreationDate (تاریخ و ساعت).
- راهکاران پرداختی: اولین سند پرداخت (RPA3.Payment) که چک در آن آمده؛ Creator و CreationDate.
- کارآمد دریافتی/پرداختی: dbo.tblChequeD / dbo.tblChequeP؛ UserRef و BookDate (کارآمد ساعت ثبت ندارد و
  لاگ کاربران آن هم ثبت چک را نگه نمی‌دارد، پس فقط تاریخ ثبت نشان داده می‌شود).

annotate(payload) هر ردیف چکی را که در یک پاسخ JSON پیدا کند با سه فیلد کامل می‌کند:
registered_at، registered_at_jalali و registered_by. تطبیق به ترتیب: شناسه صریح کارآمد (karamad:received:N)،
شماره صیاد، و شماره سریال + مبلغ.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from app.utils.jalali import format_jalali_date

logger = logging.getLogger(__name__)
CACHE_SECONDS = 300
_lock = threading.Lock()
_index: dict[str, Any] = {"at": 0.0, "data": None}
_building = threading.Lock()

_KARAMAD_ID = re.compile(r"^karamad:(?:(received|issued):)?(\d+)$")


def _digits(value: Any) -> str:
    s = re.sub(r"\D", "", str(value or ""))
    return s.lstrip("0")


def _amount(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _entry(at: Any, user: Any, has_time: bool) -> dict[str, Any]:
    if isinstance(at, datetime):
        d = at.date()
    elif isinstance(at, date):
        d, has_time = at, False
    else:
        return {}
    label = format_jalali_date(d) or ""
    if has_time and isinstance(at, datetime) and (at.hour or at.minute):
        label = f"{label} {at:%H:%M}"
    return {
        "registered_at": at.isoformat() if isinstance(at, datetime) else d.isoformat(),
        "registered_at_jalali": label,
        "registered_by": " ".join(str(user or "").split()) or None,
    }


def _build() -> dict[str, dict]:
    by_id: dict[tuple, dict] = {}
    by_sayad: dict[str, dict] = {}
    by_serial: dict[tuple, dict] = {}

    def add(system: str, kind: str, ident: Any, serials: tuple, sayad: Any, amount: Any, info: dict):
        if not info:
            return
        if ident is not None:
            by_id[(system, kind, int(ident))] = info
        s = _digits(sayad)
        if len(s) >= 10:
            by_sayad.setdefault(s, info)
        amt = _amount(amount)
        for serial in serials:
            key = _digits(serial)
            if key and amt:
                by_serial.setdefault((system, key, amt), info)

    try:
        from app.database.sqlserver import get_sqlserver_engine
        with get_sqlserver_engine().connect() as c:
            rows = c.execute(text("""
                SELECT x.ReceivableNoteRef AS ID, x.SerialNumber, x.SayadNumber, x.Amount, x.CreationDate, u.Name AS UserName
                FROM (
                    SELECT rn.ReceivableNoteRef, rn.SerialNumber, rn.SayadNumber, rn.Amount, r.CreationDate, r.Creator,
                           ROW_NUMBER() OVER (PARTITION BY rn.ReceivableNoteRef ORDER BY r.CreationDate, r.ReceiptID) AS rk
                    FROM RPA3.ReceiptReceivableNote rn
                    JOIN RPA3.Receipt r ON r.ReceiptID = rn.ReceiptRef
                    WHERE rn.ReceivableNoteRef IS NOT NULL
                ) x
                LEFT JOIN SYS3.[User] u ON u.UserID = x.Creator
                WHERE x.rk = 1
            """)).mappings().all()
            for r in rows:
                add("rahkaran", "received", r["ID"], (r["SerialNumber"],), r["SayadNumber"], r["Amount"],
                    _entry(r["CreationDate"], r["UserName"], True))
            rows = c.execute(text("""
                SELECT x.PayableNoteRef AS ID, x.SerialNumber, x.Amount, x.CreationDate, u.Name AS UserName
                FROM (
                    SELECT pn.PayableNoteRef, pn.SerialNumber, pn.Amount, p.CreationDate, p.Creator,
                           ROW_NUMBER() OVER (PARTITION BY pn.PayableNoteRef ORDER BY p.CreationDate, p.PaymentID) AS rk
                    FROM RPA3.PaymentPayableNote pn
                    JOIN RPA3.Payment p ON p.PaymentID = pn.PaymentRef
                    WHERE pn.PayableNoteRef IS NOT NULL
                ) x
                LEFT JOIN SYS3.[User] u ON u.UserID = x.Creator
                WHERE x.rk = 1
            """)).mappings().all()
            for r in rows:
                add("rahkaran", "issued", r["ID"], (r["SerialNumber"],), None, r["Amount"],
                    _entry(r["CreationDate"], r["UserName"], True))
    except Exception as exc:  # راهکاران در دسترس نیست → فقط کارآمد
        logger.warning("cheque registration (rahkaran) unavailable: %s", exc)

    try:
        from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
        with get_karamad_sqlserver_engine().connect() as c:
            rows = c.execute(text("""
                SELECT d.inx, d.Code, d.Serial, d.InquiryCode, d.Price, d.BookDate, u.Name AS UserName
                FROM dbo.tblChequeD d LEFT JOIN dbo.tblUser u ON u.ID = d.UserRef
            """)).mappings().all()
            for r in rows:
                add("karamad", "received", r["inx"], (r["Serial"], r["Code"]), r["InquiryCode"], r["Price"],
                    _entry(r["BookDate"], r["UserName"], False))
            rows = c.execute(text("""
                SELECT p.inx, p.Code, p.InquiryCode, p.Price, p.BookDate, u.Name AS UserName
                FROM dbo.tblChequeP p LEFT JOIN dbo.tblUser u ON u.ID = p.UserRef
            """)).mappings().all()
            for r in rows:
                add("karamad", "issued", r["inx"], (r["Code"], r["inx"]), r["InquiryCode"], r["Price"],
                    _entry(r["BookDate"], r["UserName"], False))
    except Exception as exc:
        logger.warning("cheque registration (karamad) unavailable: %s", exc)

    return {"by_id": by_id, "by_sayad": by_sayad, "by_serial": by_serial}


def index() -> dict[str, dict]:
    with _lock:
        data, at = _index["data"], _index["at"]
    if data is not None and time.time() - at < CACHE_SECONDS:
        return data
    if data is not None:
        # کهنه است: نسخه فعلی را برگردان و در پس‌زمینه تازه کن تا هیچ درخواستی ~۱۰ ثانیه منتظر نماند.
        if _building.acquire(blocking=False):
            threading.Thread(target=_refresh, daemon=True).start()
        return data
    with _building:
        with _lock:
            if _index["data"] is not None:
                return _index["data"]
        built = _build()
        with _lock:
            _index.update(data=built, at=time.time())
        return built


def _refresh() -> None:
    try:
        built = _build()
        with _lock:
            _index.update(data=built, at=time.time())
    finally:
        _building.release()


def _system_of(row: dict) -> str | None:
    s = str(row.get("source_system") or row.get("system") or "").lower()
    if "rahkaran" in s:
        return "rahkaran"
    if "karamad" in s:
        return "karamad"
    cid = str(row.get("cheque_id") or "")
    return "karamad" if cid.startswith("karamad") else "rahkaran" if cid.startswith("rahkaran") else None


def lookup(row: dict, idx: dict[str, dict]) -> dict[str, Any] | None:
    system = _system_of(row)
    m = _KARAMAD_ID.match(str(row.get("cheque_id") or ""))
    if m:
        kind = m.group(1) or ("issued" if "issued" in str(row.get("cheque_type") or row.get("source_kind") or "") else "received")
        hit = idx["by_id"].get(("karamad", kind, int(m.group(2))))
        if hit:
            return hit
    sayad = _digits(row.get("sayad_number"))
    if len(sayad) >= 10 and sayad in idx["by_sayad"]:
        return idx["by_sayad"][sayad]
    amt = _amount(row.get("amount_rial") if row.get("amount_rial") is not None else row.get("amount"))
    for field in ("serial_number", "cheque_number", "series"):
        serial = _digits(row.get(field))
        if not serial or not amt:
            continue
        for sysname in ((system,) if system else ("rahkaran", "karamad")):
            hit = idx["by_serial"].get((sysname, serial, amt))
            if hit:
                return hit
        # «3055/223596»: شماره سریال کارآمد گاهی با پیشوند حساب می‌آید
        tail = _digits(str(row.get(field)).split("/")[-1])
        if tail and tail != serial:
            for sysname in ((system,) if system else ("rahkaran", "karamad")):
                hit = idx["by_serial"].get((sysname, tail, amt))
                if hit:
                    return hit
    return None


def _is_cheque(row: dict) -> bool:
    return (("due_date" in row or "due_date_jalali" in row)
            and any(k in row for k in ("serial_number", "cheque_number", "sayad_number"))
            and ("amount" in row or "amount_rial" in row)
            and "registered_by" not in row)


def annotate(payload: Any) -> int:
    """همه ردیف‌های چک داخل payload را در جا کامل می‌کند؛ تعداد ردیف‌های کامل‌شده را برمی‌گرداند."""
    idx = None
    count = 0
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if _is_cheque(node):
                idx = idx or index()
                hit = lookup(node, idx)
                node.update(hit or {"registered_at": None, "registered_at_jalali": None, "registered_by": None})
                count += 1 if hit else 0
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            stack.extend(v for v in node if isinstance(v, (dict, list)))
    return count
