"""جستجوی سراسری بالای داشبورد: مشتری و نماینده (راهکاران و کارآمد)، شعبه، تأمین‌کننده و شماره چک.

نتیجه هر ردیف {kind, title, sub, to} است؛ to مسیر داشبورد یکپارچه است (پرونده همان نفر، نه صفحه کلی).
نمایه‌ها همان نمایه‌های حافظه‌ای چت‌بات‌اند (app/chatbot/search.py)؛ هر کاربر فقط نتیجه ماژول‌های خودش را می‌بیند.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query

from app.auth import guard
from app.auth.modules import user_modules

router = APIRouter(prefix="/search", tags=["search"])

CUSTOMER_MODULES = {"management", "sales", "customers", "collections", "cheques", "salesB2B", "salesHybrid", "salesCustomers", "salesTeam"}
CHEQUE_MODULES = {"management", "cheques", "collections"}
SUPPLIER_MODULES = {"management", "payables", "purchaseDocs"}
REP_CODE = re.compile(r"[789]\d{5}")
_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def rahkaran_file(code: str) -> str:
    """نماینده B2B (کد ۷xxxxx تا ۹xxxxx) ← پرونده نماینده؛ بقیه مشتریان راهکاران ← پرونده مشتری مالی."""
    return f"/files/rahkaran/{quote(code)}" if REP_CODE.fullmatch(code) else f"/finance/customers?c={quote(code)}"


def hybrid_file(branch: str) -> str:
    return f"/files/hybrids/{quote(branch)}"


@router.get("", summary="جستجوی سراسری: مشتری، نماینده، شعبه، تأمین‌کننده، شماره چک")
def global_search(q: str = Query(min_length=2, max_length=80), user: dict[str, Any] = Depends(guard.current_user)):
    from app.chatbot import search

    mods = set(user_modules(user))
    admin = bool(user.get("is_admin"))
    allow = lambda need: admin or bool(mods & need)  # noqa: E731
    out: list[dict[str, Any]] = []
    first: list[dict[str, Any]] = []   # شعبه و چک: همیشه بالای فهرست
    errors: list[str] = []
    text_q = q.translate(_FA).strip()

    if allow(CUSTOMER_MODULES):
        try:
            for r in search.search(search.rahkaran_customers(), text_q, limit=6)["candidates"]:
                rep = bool(REP_CODE.fullmatch(r["code"]))
                out.append({"kind": "نماینده B2B" if rep else "مشتری راهکاران", "title": r["name"],
                            "sub": f"کد {r['code']}" + ("" if r.get("active") else " · بدون خرید در دو سال اخیر"), "to": rahkaran_file(r["code"])})
        except Exception as exc:  # noqa: BLE001 — یک منبع قطع نباید بقیه نتیجه‌ها را بگیرد
            errors.append(f"راهکاران: {type(exc).__name__}")
        try:
            km = search.karamad_customers()
            nq = search.norm(text_q)
            branches = sorted({r["branch"] for r in km if r.get("branch") and nq and nq in search.norm(r["branch"])})
            for b in branches[:4]:
                first.append({"kind": "شعبه / هیبرید", "title": b, "sub": "پرونده هیبرید", "to": hybrid_file(b)})
            for r in search.search(km, text_q, limit=6)["candidates"]:
                out.append({"kind": "مشتری کارآمد", "title": r["name"],
                            "sub": f"کد {r['code']}" + (f" · {r['branch']}" if r.get("branch") else ""),
                            "to": hybrid_file(r["branch"]) if r.get("branch") else "/customers"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"کارآمد: {type(exc).__name__}")

    if allow(SUPPLIER_MODULES):
        try:
            for r in search.search(search.suppliers(), text_q, limit=4)["candidates"]:
                out.append({"kind": "تأمین‌کننده", "title": r["name"], "sub": f"کد {r['code']} · {r['module_label']}", "to": "/finance/payables"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"تأمین‌کنندگان: {type(exc).__name__}")

    digits = re.sub(r"\D", "", text_q)
    if allow(CHEQUE_MODULES) and len(digits) >= 5 and len(digits) >= len(text_q.replace(" ", "")) - 1:
        try:
            from app.chatbot.tools import find_cheque

            for c in find_cheque(digits).get("found") or []:
                received = c.get("type") == "دریافتی"
                first.append({"kind": f"چک {c.get('type')}", "title": f"چک {c.get('cheque_number')} · {c.get('counterpart') or '—'}",
                            "sub": " · ".join(str(x) for x in (f"{c.get('amount_toman'):,} تومان" if isinstance(c.get("amount_toman"), (int, float)) else c.get("amount_toman"),
                                                              f"سررسید {c.get('due')}" if c.get("due") else None, c.get("status"), c.get("system")) if x),
                            "to": "/finance/receivedCheques" if received else "/finance/issuedCheques"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"چک‌ها: {type(exc).__name__}")

    return {"query": q, "results": (first + out)[:24], "errors": errors}
