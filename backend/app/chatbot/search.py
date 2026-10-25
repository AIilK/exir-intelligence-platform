"""جستجوی سریع چت‌بات: نمایه نام/کد مشتریان (راهکاران و کارآمد)، تأمین‌کنندگان و کالاها.

نمایه‌ها یک بار از SQL خوانده و ۱۰ دقیقه در حافظه نگه داشته می‌شوند (جستجو زیر یک ثانیه).
تطبیق نام «حواس‌جمع» است: ی/ک عربی، نیم‌فاصله، پرانتز و خط تیره، ارقام فارسی و ترتیب کلمات مهم نیست؛
اگر چند نتیجه نزدیک بود ambiguous = True برمی‌گردد تا چت‌بات از کاربر بپرسد کدام را می‌خواهد.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)
CACHE_SECONDS = 600
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_lock = threading.Lock()

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_PUNCT = re.compile(r"[‌‏‎()\[\]{}\-_/\\.,،؛:;«»\"'+*#|]+")


_NOISE = {"کد", "کدش", "در", "از", "به", "با", "و", "را", "رو", "پرونده", "مشتری", "مشتریان", "کالا", "کالای", "قلم", "طرف", "حساب",
          "تامین", "کننده", "تامینکننده", "راهکاران", "کارامد", "کارآمد", "باز", "کن", "نشان", "نشون", "بده", "اسناد", "خرید",
          "سند", "شرکت", "اقای", "آقای", "خانم", "شعبه"}


def norm(value: Any) -> str:
    s = str(value or "").translate(_FA_DIGITS).replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("ة", "ه")
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = _PUNCT.sub(" ", s)
    return " ".join(s.split()).lower()


def _index(key: str, build: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    rows = build()
    for r in rows:
        r["_n"] = norm(r.get("name"))
        r["_c"] = norm(r.get("code"))
    with _lock:
        _cache[key] = (time.time(), rows)
    return rows


def _score(q: str, tokens: list[str], row: dict[str, Any]) -> int:
    name, code = row["_n"], row["_c"]
    if not q:
        return 0
    # هر عدد ۳+ رقمی داخل جستجو که دقیقاً کد/شناسه همین ردیف باشد کافی است («شمس(بیس) کد 820023»)
    ref = str(row.get("ref") or "")
    if any(t.isdigit() and len(t) >= 3 and (t == code or t == ref) for t in tokens) or (q.isdigit() and q in (code, ref)):
        return 100
    words_q = [t for t in tokens if not t.isdigit()]
    q_text = " ".join(words_q)
    if q_text and q_text == name:
        return 95
    words = name.split()
    if words_q and all(any(w.startswith(t) for w in words) for t in words_q):
        whole = sum(t in words for t in words_q)          # کلمه کامل بهتر از شروع کلمه («شمس» ≠ «شمسائی»)
        return 78 + min(10, whole * 10 // len(words_q)) - min(12, max(0, len(words) - len(words_q)) * 2)
    if len(q) >= 3 and q.replace(" ", "") in name.replace(" ", ""):
        return 65
    if tokens and len(tokens) > 1 and sum(any(w.startswith(t) for w in words) for t in tokens) >= len(tokens) - 1:
        return 55
    return 0


def search(rows: list[dict[str, Any]], query: str, limit: int = 8) -> dict[str, Any]:
    q = norm(query)
    # کلمه‌های غیرنام («پرونده مشتری … کد … در راهکاران») در امتیاز حساب نمی‌شوند
    tokens = [t for t in q.split() if (len(t) > 1 or t.isdigit()) and t not in _NOISE]
    q = " ".join(tokens)
    scored = sorted(((_score(q, tokens, r), r) for r in rows), key=lambda x: (-x[0], -float(x[1].get("rank") or 0)))
    hits = [(s, r) for s, r in scored if s >= 55][:limit]
    top = hits[0][0] if hits else 0
    close = [r for s, r in hits if s >= top - 10]
    strong = [r for s, r in hits if s >= 80]
    exact = [r for s, r in hits if s >= 95]
    # باید از کاربر پرسید اگر: چند نتیجه نزدیک، یا جستجوی یک‌کلمه‌ای (مثل نام خانوادگی) که چند نتیجه قوی دارد.
    # کد دقیق هرگز مبهم نیست؛ نام کامل چندکلمه‌ای که فقط یک تطبیق کامل دارد هم مبهم نیست.
    ambiguous = top < 100 and (
        (len(close) > 1 and not (len(exact) == 1 and len(tokens) > 1))
        or (len(tokens) == 1 and len(strong) > 1)
    )
    clean = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}  # noqa: E731
    return {
        "query": query,
        "match_count": len(hits),
        "ambiguous": ambiguous,
        "candidates": [clean(r) for _, r in hits],
    }


# ------------------------------------------------------------------ نمایه‌ها
def rahkaran_customers() -> list[dict[str, Any]]:
    def build():
        from app.database.sqlserver import get_sqlserver_engine
        from app.services.customer_intelligence_service import active_rahkaran_buyers
        buyers = active_rahkaran_buyers()
        with get_sqlserver_engine().connect() as c:
            rows = c.execute(text("""
                SELECT DISTINCT dl.DLID, dl.Code, dl.Title
                FROM FIN3.DL dl JOIN SLS3.Customer cu ON cu.PartyRef = dl.ReferenceID
            """)).mappings().all()
        out = []
        for r in rows:
            b = buyers.get(int(r["DLID"])) or {}
            out.append({"system": "rahkaran", "system_label": "راهکاران", "ref": str(r["DLID"]), "code": str(r["Code"] or "").strip(),
                        "name": " ".join(str(r["Title"] or "").split()),
                        "invoices_this_year": b.get("invoice_current_year_count") or 0,
                        "active": bool(b.get("invoice_current_year_count") or b.get("invoice_previous_year_count")),
                        "rank": (b.get("invoice_current_year_rial") or 0) + (b.get("invoice_previous_year_rial") or 0) / 2})
        return out
    return _index("rk_customers", build)


def karamad_customers() -> list[dict[str, Any]]:
    def build():
        from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
        with get_karamad_sqlserver_engine().connect() as c:
            rows = c.execute(text("""
                SELECT cu.[ID], cu.[Code], cu.[Name], cu.[DLRef], b.[Name] AS BranchName, s.n AS Invoices
                FROM dbo.[tblCustomer] cu
                LEFT JOIN dbo.[tblBranch] b ON b.[ID] = cu.[BranchRef]
                OUTER APPLY (SELECT COUNT(*) AS n FROM dbo.[tblFactorF] f
                             WHERE f.[CustomerRef] = cu.[ID] AND f.[DateE] >= DATEADD(year, -1, CAST(GETDATE() AS date))) s
            """)).mappings().all()
        return [{"system": "karamad", "system_label": "کارآمد", "ref": str(r["DLRef"] or ""), "code": str(r["Code"] or "").strip(),
                 "name": " ".join(str(r["Name"] or "").split()), "branch": " ".join(str(r["BranchName"] or "").split()),
                 "invoices_last_12_months": int(r["Invoices"] or 0), "active": bool(r["Invoices"]), "rank": int(r["Invoices"] or 0) * 1e7}
                for r in rows]
    return _index("km_customers", build)


def suppliers() -> list[dict[str, Any]]:
    def build():
        from app.services.payables_service import PayablesService
        mods = PayablesService().overview().get("modules", {})
        out = []
        for key, mod in mods.items():
            for p in mod.get("counterparties", []):
                out.append({"module": key, "module_label": "تجاری" if key == "trade" else "غیرتجاری", "code": str(p.get("dl_code") or ""),
                            "name": str(p.get("title") or ""), "debt_toman": round(float(p.get("credit_balance_rial") or 0) / 10),
                            "advance_toman": round(float(p.get("debit_balance_rial") or 0) / 10),
                            "rank": float(p.get("credit_balance_rial") or 0) + float(p.get("debit_balance_rial") or 0)})
        return out
    return _index("suppliers", build)


def parts() -> list[dict[str, Any]]:
    def build():
        from app.database.sqlserver import get_sqlserver_engine
        with get_sqlserver_engine().connect() as c:
            rows = c.execute(text("""
                SELECT p.PartID, p.Code, p.Name, x.n AS Receipts
                FROM LGS3.Part p
                OUTER APPLY (SELECT COUNT(*) AS n FROM LGS3.InventoryVoucherItem i
                             JOIN LGS3.InventoryVoucher v ON v.InventoryVoucherID = i.InventoryVoucherRef
                             WHERE i.PartRef = p.PartID AND v.InventoryVoucherSpecificationRef IN (2, 3, 10001)
                               AND v.Date >= DATEADD(year, -1, CAST(GETDATE() AS date))) x
            """)).mappings().all()
        return [{"code": str(r["Code"] or "").strip(), "name": " ".join(str(r["Name"] or "").split()),
                 "receipts_last_12_months": int(r["Receipts"] or 0), "rank": int(r["Receipts"] or 0)} for r in rows]
    return _index("parts", build)


def warm_up() -> None:
    """در شروع سرور نمایه‌ها و پرتفوی‌های پرهزینه را آماده کن تا اولین سؤال کند نباشد."""
    def run():
        for fn in (rahkaran_customers, karamad_customers, suppliers, parts):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                logger.warning("chatbot index %s failed: %s", fn.__name__, exc)
        try:
            from app.services.customer_intelligence_service import CustomerIntelligenceService
            CustomerIntelligenceService().collection_portfolio(limit=1000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chatbot portfolio warm-up failed: %s", exc)
    threading.Thread(target=run, daemon=True).start()
