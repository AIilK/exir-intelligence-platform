"""ابزارهای داده چت‌بات: هر ابزار یک خلاصه کوچک و زنده از داده‌های خود اپ برمی‌گرداند.

ابزارها همان APIهای داخلی اپ را صدا می‌زنند (همان اعدادی که صفحه‌ها نشان می‌دهند) و خروجی را
کوچک می‌کنند تا مدل فقط اعداد واقعی ببیند. همه مبالغ به «تومان» تبدیل می‌شوند (کلیدهای *_toman).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

API = "http://127.0.0.1:8000/api/v1"
CACHE_SECONDS = 120
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _get(path: str, timeout: int = 120) -> Any:
    with _lock:
        hit = _cache.get(path)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    from app.auth.guard import INTERNAL_HEADER, INTERNAL_TOKEN

    req = urllib.request.Request(f"{API}{path}", headers={INTERNAL_HEADER: INTERNAL_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (local API only)
        data = json.loads(r.read().decode("utf-8"))
    with _lock:
        _cache[path] = (time.time(), data)
    return data


def _toman(value: Any) -> int:
    try:
        return int(round(float(value or 0) / 10))
    except (TypeError, ValueError):
        return 0


_SKIP_KEYS = {"note", "days", "timeline", "calendar", "cheques", "customers", "items", "documents"}


def _slim(obj: Any, depth: int = 0) -> Any:
    """ریال → تومان، حذف کلیدهای فنی و کوتاه کردن فهرست‌ها."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.endswith("_id") or k in _SKIP_KEYS:
                continue
            if k.endswith("_rial"):
                out[k[:-5] + "_toman"] = _toman(v)
            elif depth < 4:
                out[k] = _slim(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_slim(x, depth + 1) for x in obj[:8]]
    return obj


# ------------------------------------------------------------------ ابزارها
def cheques_overview() -> dict[str, Any]:
    rec = _get("/liquidity/received-cheques?horizon_days=30").get("data", {})
    iss = _get("/liquidity/issued-cheques?horizon_days=30").get("data", {})
    top_customers = sorted(rec.get("customers", []), key=lambda c: -float(c.get("definite_rial") or 0))[:5]
    return {
        "received": {
            "next_30_days": _slim(rec.get("kpis", {}).get("horizon")),
            "next_7_days": _slim(rec.get("kpis", {}).get("next_7_days")),
            "today": _slim(rec.get("kpis", {}).get("today")),
            "returned_this_year": _slim({k: v for k, v in (rec.get("returned_open") or {}).items() if k != "by_system"}),
            "returned_by_system": [_slim(x) for x in (rec.get("returned_open") or {}).get("by_system", [])],
            "undetermined_overdue": {"amount_toman": _toman(float((rec.get("overdue") or {}).get("definite_rial") or 0) + float((rec.get("overdue") or {}).get("other_state_rial") or 0)),
                                     "count": int((rec.get("overdue") or {}).get("count") or 0) + int((rec.get("overdue") or {}).get("other_state_count") or 0)},
            "top_customers_next_30_days": [{"name": c.get("customer_name"), "system": c.get("system"), "amount_toman": _toman(c.get("definite_rial")),
                                            "count": c.get("count"), "reliance_percent": c.get("reliance_percent")} for c in top_customers],
        },
        "issued": {
            "kpis": _slim(iss.get("kpis")),
            "needs_status_review": _slim({k: v for k, v in (iss.get("needs_status_review") or {}).items() if k != "cheques"}),
            "top_payees": [_slim(p) for p in (iss.get("top_payees") or [])[:5]],
        },
    }


def cheque_status_list(kind: str) -> dict[str, Any]:
    kind = "returned" if kind == "returned" else "undetermined"
    d = _get(f"/liquidity/received-cheques/status/{kind}")
    rows = sorted(d.get("cheques", []), key=lambda x: -float(x.get("amount_rial") or 0))
    # تجمیع به تفکیک مشتری: «کدوم مشتری بیشترین چک برگشتی رو داره؟» (هم تعداد، هم مبلغ)
    per: dict[tuple, dict[str, Any]] = {}
    for x in rows:
        key = (x.get("system_label"), x.get("customer_name"))
        g = per.setdefault(key, {"customer": x.get("customer_name"), "system": x.get("system_label"), "code": x.get("customer_code"),
                                 "branch": x.get("branch_name"), "count": 0, "amount_rial": 0.0, "max_days_overdue": 0})
        g["count"] += 1
        g["amount_rial"] += float(x.get("amount_rial") or 0)
        g["max_days_overdue"] = max(g["max_days_overdue"], int(x.get("days_overdue") or 0))
    customers = list(per.values())
    by_count = sorted(customers, key=lambda g: (-g["count"], -g["amount_rial"]))[:8]
    by_amount = sorted(customers, key=lambda g: -g["amount_rial"])[:8]
    return {
        "kind": kind, "count": len(rows), "amount_toman": _toman(sum(float(x.get("amount_rial") or 0) for x in rows)),
        "customer_count": len(customers),
        "rule": d.get("rule"),
        "by_system": [_slim(x) for x in d.get("by_system", [])],
        "top_customers_by_count": [_slim(g) for g in by_count],
        "top_customers_by_amount": [_slim(g) for g in by_amount],
        "by_status": [_slim(x) for x in d.get("by_status", [])],
        "largest": [{"customer": x.get("customer_name"), "system": x.get("system_label"), "cheque_number": x.get("serial_number"),
                     "amount_toman": _toman(x.get("amount_rial")), "due": x.get("due_date_jalali"), "status": x.get("status_label"),
                     "days_overdue": x.get("days_overdue"), "registered_by": x.get("registered_by")} for x in rows[:10]],
    }


def find_cheque(number: str) -> dict[str, Any]:
    digits = "".join(ch for ch in str(number) if ch.isdigit()).lstrip("0")
    if len(digits) < 4:
        return {"error": "شماره چک یا صیاد حداقل ۴ رقم لازم است"}
    found = []
    for path, kind in (("/treasury/cheques/received/open?period=all", "دریافتی"), ("/treasury/cheques/issued/open", "پرداختی")):
        for x in _get(path, timeout=240).get("cheques", []):
            keys = ["".join(ch for ch in str(x.get(k) or "") if ch.isdigit()).lstrip("0") for k in ("serial_number", "cheque_number", "sayad_number")]
            if digits in keys:
                found.append({"type": kind, "system": x.get("source_label"), "cheque_number": x.get("serial_number"), "sayad": x.get("sayad_number"),
                              "counterpart": x.get("counterpart_name"), "amount_toman": _toman(x.get("amount_rial") or x.get("amount")),
                              "due": x.get("due_date_jalali"), "status": x.get("cheque_status") if isinstance(x.get("cheque_status"), str) else x.get("state_label"),
                              "bank": x.get("bank_name"), "registered_at": x.get("registered_at_jalali"), "registered_by": x.get("registered_by")})
    return {"query": number, "found": found[:5], "note": "فقط چک‌های باز جستجو می‌شوند" if not found else None}


def find_customer(name: str, system: str = "all") -> dict[str, Any]:
    """جستجوی سریع مشتری با نام، برند یا کد (نمایه حافظه‌ای search.py). اگر ambiguous بود باید از کاربر پرسید.

    فقط برای نتیجه یکتا (یا حداکثر ۳ نتیجه اول) ارقام چک و مانده هم ضمیمه می‌شود.
    """
    from app.chatbot import search

    if len(str(name or "").strip()) < 2:
        return {"error": "نام یا کد مشتری کوتاه است"}
    rows = []
    if system in ("all", "rahkaran"):
        rows += search.rahkaran_customers()
    if system in ("all", "karamad"):
        rows += search.karamad_customers()
    found = search.search(rows, name, limit=8)
    detail_for = found["candidates"][:1] if not found["ambiguous"] else []
    for c in detail_for:
        c["details"] = _customer_details(c)
    return found


def _customer_details(c: dict[str, Any]) -> dict[str, Any]:
    try:
        if c["system"] == "rahkaran":
            # فقط اگر پرتفوی در حافظه آماده است (ساخت سردش ~۳۰ ثانیه است و چت نباید منتظر بماند؛ پرونده خودش ارقام را دارد)
            import time
            from app.services.customer_intelligence_service import _PORTFOLIO_CACHE
            hit = _PORTFOLIO_CACHE.get(1000)
            if not hit or time.time() - hit[0] > 600:
                return {"note": "ارقام مانده هنوز آماده نیست؛ در پرونده مشتری دیده می‌شود"}
            rows = hit[1].get("customers", [])
            x = next((r for r in rows if str(r.get("counterpart_ref")) == str(c.get("ref"))), None)
            if not x:
                return {}
            pos = x.get("collection_position") or {}
            return {"open_account_receivable_toman": _toman(pos.get("open_account_receivable_rial")),
                    "customer_credit_toman": _toman(pos.get("customer_credit_rial")),
                    "open_cheques_toman": _toman(x.get("open_received_cheque_amount")), "open_cheque_count": x.get("open_cheque_count"),
                    "overdue_open_toman": _toman(x.get("overdue_open_amount")), "returned_count": x.get("returned_cheque_count"),
                    "returned_toman": _toman(x.get("returned_cheque_amount")), "risk_level": x.get("risk_level"),
                    "invoices_this_year": x.get("invoice_current_year_count"), "last_invoice": x.get("last_invoice_date_jalali")}
        rows = _get("/finance/customer-collection-portfolio?source=karamad&limit=1000", timeout=240).get("customers", [])
        x = next((r for r in rows if str(r.get("counterpart_ref")) == str(c.get("ref"))), None)
        if not x:
            return {}
        return {"karamad_file_name": x.get("customer_name"),
                "received_cheques_toman": _toman(x.get("received_cheque_amount_rial")),
                "future_cheques_toman": _toman(x.get("received_cheque_future_amount_rial")),
                "overdue_cheques_toman": _toman(x.get("received_cheque_overdue_amount_rial")),
                "returned_cheques_toman": _toman(x.get("received_cheque_returned_amount_rial")),
                "returned_count": x.get("received_cheque_returned_count")}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}"}


def find_supplier(name: str) -> dict[str, Any]:
    """تأمین‌کننده / طرف حساب پرداخت تجاری با نام یا کد تفصیلی؛ بدهی و پیش‌پرداخت هر نتیجه."""
    from app.chatbot import search
    return search.search(search.suppliers(), name, limit=8)


def find_product(name: str) -> dict[str, Any]:
    """کالا با نام یا کد قلم (برای اسناد خرید / مرور تدارکات)؛ تعداد رسید ۱۲ ماه اخیر هر کالا."""
    from app.chatbot import search
    return search.search(search.parts(), name, limit=8)


def payables_overview() -> dict[str, Any]:
    m = _get("/finance/payables").get("modules", {})
    def top(mod: dict, key: str) -> list:
        rows = sorted([p for p in mod.get("counterparties", []) if float(p.get(key) or 0) > 0], key=lambda p: -float(p.get(key) or 0))[:5]
        return [{"name": p.get("title"), "code": p.get("dl_code"), "amount_toman": _toman(p.get(key))} for p in rows]
    return {name: {"debt_toman": _toman(mod.get("credit_balance_rial")), "creditor_count": mod.get("creditor_count"),
                   "advance_toman": _toman(mod.get("debit_balance_rial")), "advance_count": mod.get("debtor_count"),
                   "largest_debts": top(mod, "credit_balance_rial"), "largest_advances": top(mod, "debit_balance_rial")}
            for name, mod in (("trade_511002", m.get("trade", {})), ("nontrade_512001", m.get("nontrade", {})))}


def liquidity_forecast() -> dict[str, Any]:
    d = _get("/liquidity/summary?horizon_days=30", timeout=240).get("data", {})
    return {"horizon": d.get("horizon"), "base_scenario": d.get("base_scenario"), "note": "بدون موجودی فعلی بانک",
            "scenarios": [{"key": s.get("key"), "label": s.get("label"), "inflow_toman": _toman(s.get("inflow_rial")),
                           "outflow_toman": _toman(s.get("outflow_rial")), "coverage_percent": s.get("coverage_percent"),
                           "financing_need_toman": _toman(s.get("financing_need_rial")), "first_shortage": (s.get("first_shortage") or {}).get("date_jalali"),
                           "worst_balance_date": (s.get("worst_balance") or {}).get("date_jalali"), "parts": _slim(s.get("totals"))}
                          for s in d.get("scenarios", [])]}


def distribution_month(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    q = f"?year={int(year)}&month={int(month)}" if year and month else ""
    if not q:
        import jdatetime
        t = jdatetime.date.today()
        q = f"?year={t.year}&month={t.month}"
    d = _get(f"/finance/distribution/monthly{q}", timeout=240)
    branches = sorted(d.get("branches", []), key=lambda b: -float(b.get("sales_rial") or 0))
    return {"month": d.get("month_label") or q, "company_sales": _slim({k: v for k, v in (d.get("company_sales") or {}).items() if k != "by_branch"}),
            "sales_by_branch_top": [_slim(b) for b in (d.get("company_sales") or {}).get("by_branch", [])[:6]],
            "hybrids_totals": _slim(d.get("totals")),
            "hybrids": [{"name": b.get("branch_name"), "sales_toman": _toman(b.get("sales_rial")), "distributed_toman": _toman(b.get("distributed_rial")),
                         "undistributed_toman": _toman(b.get("undistributed_rial")), "collected_toman": _toman(b.get("collected_rial")),
                         "remaining_toman": _toman(b.get("remaining_rial"))} for b in branches[:10]]}


def purchase_documents(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    import jdatetime
    y = int(year or jdatetime.date.today().year)
    prefix = f"{y}/{int(month):02d}" if month else f"{y}/"
    docs = [x for x in _get(f"/finance/purchase-documents?from_year={y}").get("documents", []) if x.get("date_jalali", "").startswith(prefix)]
    items = [x for x in _get(f"/finance/purchase-items?from_year={y}").get("items", []) if x.get("date_jalali", "").startswith(prefix)]
    priced = [x for x in docs if x.get("priced")]
    pending = [x for x in items if x.get("converted") is False]
    return {"period": prefix.rstrip("/"),
            "unposted_purchase_documents": {"count": len(docs), "priced_ready_for_accounting": len(priced),
                                            "priced_amount_toman": _toman(sum(float(x.get("price_rial") or 0) for x in priced)),
                                            "unpriced": len(docs) - len(priced), "returns": sum(1 for x in docs if x.get("is_return"))},
            "procurement_review": {"rows": len(items), "permanent_rows": sum(1 for x in items if x.get("kind") == "دائم"),
                                   "temporary_rows": sum(1 for x in items if x.get("kind") == "موقت"),
                                   "temporary_not_converted_rows": len(pending),
                                   "temporary_not_converted_vouchers": sorted({x.get("number") for x in pending})[:15]}}


def inventory_pricing() -> dict[str, Any]:
    d = _get("/finance/inventory-pricing")
    stores = sorted(d.get("stores", []), key=lambda s: -int(s.get("unpriced_count") or 0))
    return {"total": d.get("total"), "factory_total": d.get("factory_total"), "from": d.get("from_date_jalali"),
            "stores_most_unpriced": [{"store": s.get("store_name"), "site": s.get("plant_name"), "unpriced": s.get("unpriced_count"),
                                      "documents": s.get("document_count"), "oldest_unpriced": s.get("oldest_unpriced_date_jalali")} for s in stores[:8]]}


# ------------------------------------------------------ تعریف ابزار برای مدل
def _schema(props: dict[str, Any] | None = None) -> dict[str, Any]:
    props = props or {}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_YEAR = {"type": ["integer", "null"], "description": "سال شمسی، مثلاً 1405؛ null یعنی سال جاری"}
_MONTH = {"type": ["integer", "null"], "description": "ماه شمسی ۱ تا ۱۲ (مهر = 7)؛ null یعنی کل سال/ماه جاری"}

TOOLS: dict[str, tuple[Callable[..., Any], str, dict[str, Any]]] = {
    "cheques_overview": (cheques_overview, "خلاصه چک‌های دریافتی (امروز، ۷ و ۳۰ روز آینده، برگشتی امسال، تعیین تکلیف نشده، بزرگ‌ترین مشتریان) و پرداختی (سررسیدها، وضعیت به‌روز نشده، بزرگ‌ترین ذی‌نفعان).", _schema()),
    "cheque_status_list": (cheque_status_list, "چک‌های برگشتی امسال یا تعیین تکلیف نشده: جمع، تفکیک سیستم و وضعیت، رتبه مشتریان (بیشترین تعداد و بیشترین مبلغ) و بزرگ‌ترین چک‌ها.",
                           _schema({"kind": {"type": "string", "enum": ["returned", "undetermined"]}})),
    "find_cheque": (find_cheque, "پیدا کردن یک چک باز با شماره چک یا شماره صیاد: طرف حساب، مبلغ، سررسید، وضعیت و اینکه کی و چه کسی ثبتش کرده.",
                    _schema({"number": {"type": "string"}})),
    "find_customer": (find_customer, "جستجوی سریع مشتری با نام، برند یا کد (راهکاران/کارآمد). ambiguous=true یعنی چند نفر پیدا شد و باید از کاربر پرسید؛ برای نتیجه یکتا details (مانده، چک باز، برگشتی، ریسک) هم دارد.",
                      _schema({"name": {"type": "string"}, "system": {"type": "string", "enum": ["all", "rahkaran", "karamad"]}})),
    "find_supplier": (find_supplier, "جستجوی تأمین‌کننده/طرف حساب پرداخت تجاری با نام یا کد تفصیلی؛ بدهی و پیش‌پرداخت. ambiguous=true یعنی باید پرسید.",
                      _schema({"name": {"type": "string"}})),
    "find_product": (find_product, "جستجوی کالا با نام یا کد قلم (برای اسناد خرید و مرور تدارکات). ambiguous=true یعنی چند کالا پیدا شد و باید پرسید.",
                     _schema({"name": {"type": "string"}})),
    "payables_overview": (payables_overview, "بدهی تجاری/غیرتجاری شرکت، پیش‌پرداخت‌های باز و بزرگ‌ترین طرف حساب‌ها.", _schema()),
    "liquidity_forecast": (liquidity_forecast, "پیش‌بینی نقدینگی ۳۰ روز آینده در سه سناریو: ورودی، خروجی، پوشش، نیاز به تأمین، اولین روز کسری.", _schema()),
    "distribution_month": (distribution_month, "فروش کل و توزیع/وصول فاکتورهای هیبریدها در یک ماه.", _schema({"year": _YEAR, "month": _MONTH})),
    "purchase_documents": (purchase_documents, "اسناد خرید ثبت‌حسابداری‌نشده و مرور تدارکات (رسید موقت/دائم) در یک سال یا ماه.", _schema({"year": _YEAR, "month": _MONTH})),
    "inventory_pricing": (inventory_pricing, "اسناد انبار قیمت‌گذاری‌نشده به تفکیک انبار.", _schema()),
}


# ابزارهای فروش (بک‌اند فروش، داشبورد یکپارچه) — sales_tools.py
from app.chatbot import sales_tools as _sales  # noqa: E402

TOOLS.update({name: (fn, desc, _schema(props)) for name, (fn, desc, props) in _sales.TOOLS.items()})


def openai_tools(allowed: set[str] | None = None) -> list[dict[str, Any]]:
    """allowed = ابزارهای مجاز ماژول‌های کاربر (None یعنی همه)."""
    return [{"type": "function", "name": name, "description": desc, "parameters": params, "strict": True}
            for name, (_, desc, params) in TOOLS.items() if allowed is None or name in allowed]


def run_tool(name: str, args: dict[str, Any], allowed: set[str] | None = None) -> Any:
    fn = TOOLS.get(name, (None,))[0]
    if fn is None:
        return {"error": f"ابزار ناشناخته: {name}"}
    if allowed is not None and name not in allowed:
        return {"error": "این کاربر به داده این بخش دسترسی ندارد."}
    try:
        return fn(**{k: v for k, v in (args or {}).items() if v is not None})
    except Exception as exc:  # noqa: BLE001 — خطای داده را به مدل بگو تا صادقانه جواب دهد
        return {"error": f"دریافت داده ناموفق بود: {type(exc).__name__}: {str(exc)[:160]}"}
