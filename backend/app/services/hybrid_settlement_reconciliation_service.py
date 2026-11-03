"""تطبیق تسویه هیبریدها: پرداخت هیبرید در کارآمد ↔ دریافت شرکت در راهکاران (V173).

هیبرید بدهی کالای خود را به شرکت‌های گروه (پادینا، مولهنس، …) می‌پردازد:
- در کارآمد: پرداخت به معین 3112 «حساب‌های پرداختنی (شرکت‌ها)» با تفصیلی شرکت گروه
  (همان قانون صفحه نقدینگی؛ خرید ارز برای شرکت مستثناست).
- در راهکاران: دریافت از مشتری «هیبرید <منطقه> - <برند>».
اگر پرداخت کارآمد معادلی در راهکاران نداشته باشد، هیبرید پرداخت کرده ولی سند دریافت در راهکاران
نخورده و بدهی‌اش در راهکاران بیش از واقع است.

کلید تطبیق = منطقه + برند. تطبیق در سه مرحله: (۱) هم‌کلید و هم‌مبلغ با نزدیک‌ترین تاریخ (±۱۵ روز)،
(۲) همان منطقه با برند دیگر (±۷ روز؛ احتمال ثبت روی برند اشتباه)، (۳) جمع ۲ تا ۳ ردیف در ±۳ روز
(پرداخت یک‌جا در یک سیستم و چندتکه در دیگری). خروجی فقط برای بررسی است؛ سندی ثبت نمی‌شود.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from itertools import combinations
from typing import Any

from sqlalchemy import text

from app.utils.jalali import format_jalali_date

BRANDS = ("پادینا", "مولهنس", "بیس", "آرکیا", "وینا", "جوو", "لورینت", "تاکوری", "کالیون", "رزتی", "اورادنت", "آپ اسکای")
AMOUNT_TOLERANCE_RIAL = 10_000
EXACT_WINDOW_DAYS = 15
CROSS_BRAND_WINDOW_DAYS = 7
GROUP_WINDOW_DAYS = 3
# Karamad branch names that differ from the Rahkaran hybrid customer naming.
REGION_ALIASES = {frozenset({"تهران"}): frozenset({"غرب", "تهران"})}


def _clean(value: Any) -> str:
    value = str(value or "").replace("ي", "ی").replace("ك", "ک").replace("\xa0", " ").replace("‌", " ")
    return re.sub(r"\s+", " ", value).strip()


def brand_of(value: Any) -> str | None:
    text_value = _clean(value).replace("ارکیا", "آرکیا")
    return next((b for b in BRANDS if b in text_value), None)


def region_of(value: Any, karamad: bool = False) -> frozenset[str]:
    text_value = _clean(value)
    for brand in BRANDS:
        text_value = text_value.replace(brand, " ")
    text_value = re.sub(r"هیبریدی|هیبرید|[()\-.،]", " ", text_value)
    tokens = frozenset(t for t in text_value.split() if t)
    return REGION_ALIASES.get(tokens, tokens) if karamad else tokens


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


class HybridSettlementReconciliationService:
    def __init__(self, rahkaran_engine=None, karamad_engine=None):
        self._rahkaran = rahkaran_engine
        self._karamad = karamad_engine

    @property
    def rahkaran(self):
        if self._rahkaran is None:
            from app.database.sqlserver import get_sqlserver_engine
            self._rahkaran = get_sqlserver_engine()
        return self._rahkaran

    @property
    def karamad(self):
        if self._karamad is None:
            from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
            self._karamad = get_karamad_sqlserver_engine()
        return self._karamad

    # ------------------------------------------------------------------ data
    def _karamad_payments(self, since: date) -> list[dict[str, Any]]:
        with self.karamad.connect() as c:
            rows = c.execute(text("""
                SELECT k.kind, k.inx, k.Code, k.BookDate, k.Amount, k.Behalf, k.Description, b.Name AS Branch,
                       dl.Name AS Firm, k.VoucherRef, u.Name AS UserName, bk.Name AS BankName
                FROM (
                    SELECT N'حواله بانکی' AS kind, inx, CAST(Code AS nvarchar(50)) AS Code, BookDate, Price AS Amount,
                           Behalf, Description, BranchRef, SLRef, DLRef, VoucherRef, UserRef, BankRef FROM dbo.[tblDraftP]
                    UNION ALL
                    SELECT N'پرداخت نقدی', inx, CAST(Code AS nvarchar(50)), BookDate, PriceN, Behalf, Description,
                           BranchRef, SLRef, DLRef, VoucherRef, UserRef, NULL FROM dbo.[tblCashP]
                ) k
                JOIN dbo.[tblSL] sl ON sl.[ID] = k.SLRef
                LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = k.DLRef
                LEFT JOIN dbo.[tblUser] u ON u.[ID] = k.UserRef
                OUTER APPLY (SELECT TOP (1) x.[Name] FROM dbo.[tblBranch] x WHERE x.[Code] = k.BranchRef) b
                OUTER APPLY (SELECT TOP (1) a.[Name] FROM dbo.[tblAccBank] a WHERE a.[Code] = k.BankRef) bk
                WHERE sl.[Code] = N'3112' AND k.BookDate >= :since AND ISNULL(k.Amount, 0) <> 0
                  AND ISNULL(k.Behalf, N'') NOT LIKE N'%خرید ارز%'
            """), {"since": since}).mappings().all()
        out = []
        for r in rows:
            out.append({
                "side": "karamad", "kind": r["kind"], "number": r["Code"], "day": _day(r["BookDate"]),
                "amount": round(float(r["Amount"] or 0)), "branch": _clean(r["Branch"]), "firm": _clean(r["Firm"]),
                "behalf": _clean(r["Behalf"]), "description": _clean(r["Description"]), "bank": _clean(r["BankName"]),
                "registered_by": r["UserName"], "has_voucher": r["VoucherRef"] is not None,
                "region": region_of(r["Branch"], karamad=True), "brand": brand_of(r["Firm"]),
            })
        return out

    def _rahkaran_receipts(self, since: date) -> list[dict[str, Any]]:
        with self.rahkaran.connect() as c:
            rows = c.execute(text("""
                SELECT x.kind, x.Number, x.Date, x.Amount, x.ApproveState, x.CP, dl.[Title] AS Party, x.Description
                FROM (
                    SELECT N'حواله بانکی' AS kind, h.[Number], h.[Date], COALESCE(d.[CurrencyAmount], d.[Amount], 0) AS Amount,
                           h.[ApproveState], COALESCE(d.[CounterPartRef], h.[CounterPartRef]) AS CP,
                           COALESCE(NULLIF(d.[Description], N''), h.[Description]) AS Description
                    FROM RPA3.[ReceiptDeposit] d JOIN RPA3.[Receipt] h ON h.[ReceiptID] = d.[ReceiptRef]
                    UNION ALL
                    SELECT N'دریافت نقدی', h.[Number], h.[Date], COALESCE(d.[CurrencyAmount], d.[Amount], 0), h.[ApproveState],
                           COALESCE(d.[CounterPartRef], h.[CounterPartRef]),
                           COALESCE(NULLIF(d.[Description], N''), h.[Description])
                    FROM RPA3.[ReceiptCashMoney] d JOIN RPA3.[Receipt] h ON h.[ReceiptID] = d.[ReceiptRef]
                ) x
                LEFT JOIN FIN3.[DL] dl ON dl.[DLID] = x.CP
                WHERE x.Date >= :since AND dl.[Title] LIKE N'%هیبرید%'
            """), {"since": since}).mappings().all()
            hybrids = c.execute(text(
                "SELECT dl.[DLID], dl.[Title] FROM FIN3.[DL] dl "
                "JOIN SLS3.[Customer] cu ON cu.[PartyRef] = dl.[ReferenceID] WHERE dl.[Title] LIKE N'%هیبرید%'"
            )).mappings().all()
        receipts = [{
            "side": "rahkaran", "kind": r["kind"], "number": str(r["Number"] or ""), "day": _day(r["Date"]),
            "amount": round(float(r["Amount"] or 0)), "party": _clean(r["Party"]), "dl_ref": r["CP"],
            "approved": r["ApproveState"] == 3, "description": _clean(r["Description"]),
            "region": region_of(r["Party"]), "brand": brand_of(r["Party"]),
        } for r in rows]
        customers = {int(h["DLID"]): _clean(h["Title"]) for h in hybrids}
        return receipts, customers

    # -------------------------------------------------------------- matching
    @staticmethod
    def _match(karamad: list[dict[str, Any]], rahkaran: list[dict[str, Any]]) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        k_used: set[int] = set()
        r_used: set[int] = set()

        def gap(a: dict[str, Any], b: dict[str, Any]) -> int:
            return abs((a["day"] - b["day"]).days) if a["day"] and b["day"] else 999

        def same_amount(a: int, b: int) -> bool:
            return abs(a - b) <= AMOUNT_TOLERANCE_RIAL

        # (1) same hybrid + brand, then (2) same hybrid any brand
        for window, same_brand, label in ((EXACT_WINDOW_DAYS, True, "هم‌مبلغ و هم‌برند"),
                                          (CROSS_BRAND_WINDOW_DAYS, False, "هم‌مبلغ، برند متفاوت در راهکاران")):
            for ki in sorted(range(len(karamad)), key=lambda i: karamad[i]["day"] or date.min):
                if ki in k_used:
                    continue
                k = karamad[ki]
                cands = [(gap(k, r), ri) for ri, r in enumerate(rahkaran)
                         if ri not in r_used and r["region"] == k["region"]
                         and (r["brand"] == k["brand"] if same_brand else True)
                         and same_amount(r["amount"], k["amount"]) and gap(k, r) <= window]
                if cands:
                    days, ri = min(cands)
                    k_used.add(ki)
                    r_used.add(ri)
                    matches.append({"karamad": [k], "rahkaran": [rahkaran[ri]], "method": label, "gap_days": days})

        # (3) one row on one side = 2..3 rows on the other side (same hybrid + brand, ±3 days)
        def group_pass(singles, many, s_used, m_used, single_is_karamad):
            for si, s in enumerate(singles):
                if si in s_used:
                    continue
                pool = [mi for mi, m in enumerate(many) if mi not in m_used and m["region"] == s["region"]
                        and m["brand"] == s["brand"] and gap(s, m) <= GROUP_WINDOW_DAYS and m["amount"] < s["amount"]]
                found = None
                for size in (2, 3):
                    for combo in combinations(pool[:12], size):
                        if same_amount(sum(many[i]["amount"] for i in combo), s["amount"]):
                            found = combo
                            break
                    if found:
                        break
                if found:
                    s_used.add(si)
                    m_used.update(found)
                    group = [many[i] for i in found]
                    matches.append({
                        "karamad": [s] if single_is_karamad else group,
                        "rahkaran": group if single_is_karamad else [s],
                        "method": "جمع چند ردیف", "gap_days": max(gap(s, g) for g in group),
                    })

        group_pass(karamad, rahkaran, k_used, r_used, True)
        group_pass(rahkaran, karamad, r_used, k_used, False)
        for i, k in enumerate(karamad):
            k["matched"] = i in k_used
        for i, r in enumerate(rahkaran):
            r["matched"] = i in r_used
        return matches

    # ----------------------------------------------------------------- build
    def build(self, days: int = 180) -> dict[str, Any]:
        from app.services.finance_prediction_service import FinancePredictionService

        since = date.today() - timedelta(days=days)
        karamad = self._karamad_payments(since)
        rahkaran, customers = self._rahkaran_receipts(since - timedelta(days=EXACT_WINDOW_DAYS))
        matches = self._match(karamad, rahkaran)

        # Rahkaran hybrid customer for each (region, brand) key.
        customer_by_key: dict[tuple[frozenset[str], str | None], tuple[int, str]] = {}
        for dl, title in customers.items():
            customer_by_key.setdefault((region_of(title), brand_of(title)), (dl, title))

        prediction = FinancePredictionService(engine=self.rahkaran)
        balances: dict[int, float | None] = {}

        def balance(dl: int) -> float | None:
            if dl not in balances:
                try:
                    pos = prediction.customer_account_position(dl)
                    balances[dl] = float(pos.get("open_account_receivable_rial") or 0) if pos.get("found") else None
                except Exception:  # noqa: BLE001
                    balances[dl] = None
            return balances[dl]

        groups: dict[tuple, dict[str, Any]] = {}
        for k in karamad:
            key = (k["region"], k["brand"])
            customer = customer_by_key.get(key)
            g = groups.setdefault(key, {
                "region": " ".join(sorted(k["region"])) or "—", "brand": k["brand"] or "—",
                "karamad_branch": k["branch"], "rahkaran_customer": customer[1] if customer else None,
                "dl_ref": customer[0] if customer else None, "paid_count": 0, "paid_rial": 0,
                "unmatched_count": 0, "unmatched_rial": 0, "payments": [],
            })
            g["paid_count"] += 1
            g["paid_rial"] += k["amount"]
            if not k["matched"]:
                g["unmatched_count"] += 1
                g["unmatched_rial"] += k["amount"]
                g["payments"].append(k)
        for r in rahkaran:
            if not r["matched"]:
                key = (r["region"], r["brand"])
                g = groups.get(key)
                if g is not None:
                    g.setdefault("rahkaran_only_rial", 0)
                    g["rahkaran_only_rial"] += r["amount"]
        rows = []
        for g in groups.values():
            debt = balance(g["dl_ref"]) if g["dl_ref"] else None
            g["rahkaran_debt_rial"] = debt
            g["adjusted_debt_rial"] = None if debt is None else debt - g["unmatched_rial"]
            # منفی یعنی پرداخت‌های بی‌معادل بیش از بدهی است؛ احتمالاً دریافت در راهکاران روی مشتری/تاریخ دیگری ثبت شده.
            g["needs_review"] = g["adjusted_debt_rial"] is not None and g["adjusted_debt_rial"] < 0
            g.setdefault("rahkaran_only_rial", 0)
            rows.append(g)
        rows.sort(key=lambda g: -g["unmatched_rial"])

        unmatched_k = [k for k in karamad if not k["matched"]]
        unmatched_r = [r for r in rahkaran if not r["matched"] and r["day"] and r["day"] >= since]
        return {
            "status": "success",
            "since_jalali": format_jalali_date(since),
            "summary": {
                "karamad_count": len(karamad), "karamad_rial": sum(k["amount"] for k in karamad),
                "matched_karamad_count": sum(1 for k in karamad if k["matched"]),
                "unmatched_karamad_count": len(unmatched_k), "unmatched_karamad_rial": sum(k["amount"] for k in unmatched_k),
                "rahkaran_count": len([r for r in rahkaran if r["day"] and r["day"] >= since]),
                "unmatched_rahkaran_count": len(unmatched_r), "unmatched_rahkaran_rial": sum(r["amount"] for r in unmatched_r),
                "no_rahkaran_customer_rial": sum(g["unmatched_rial"] for g in rows if not g["dl_ref"]),
            },
            "hybrids": rows,
            "unmatched_karamad": sorted(unmatched_k, key=lambda k: (k["day"] or date.min), reverse=True),
            "unmatched_rahkaran": sorted(unmatched_r, key=lambda r: (r["day"] or date.min), reverse=True),
            "matches": matches,
        }

    # ----------------------------------------------------------------- excel
    def workbook(self, days: int = 180) -> BytesIO:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        report = self.build(days)
        toman = lambda rial: None if rial is None else round(float(rial) / 10)  # noqa: E731
        jal = lambda d: format_jalali_date(d) if d else ""  # noqa: E731
        wb = Workbook()
        head_fill, head_font = PatternFill("solid", fgColor="1F4E78"), Font(color="FFFFFF", bold=True)

        def sheet(title, headers, rows, widths, money=()):
            ws = wb.create_sheet(title)
            ws.sheet_view.rightToLeft = True
            ws.append(headers)
            for cell in ws[1]:
                cell.fill, cell.font = head_fill, head_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for row in rows:
                ws.append(row)
            for col in money:
                for cell in ws[get_column_letter(col)][1:]:
                    cell.number_format = "#,##0"
            for i, w in enumerate(widths, start=1):
                ws.column_dimensions[get_column_letter(i)].width = w
            for r in ws.iter_rows(min_row=2):
                for cell in r:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            ws.freeze_panes = "A2"
            if rows:
                ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"

        s = report["summary"]
        ws = wb.active
        ws.title = "خلاصه و راهنما"
        ws.sheet_view.rightToLeft = True
        for line in [
            ["تطبیق تسویه هیبریدها: پرداخت در کارآمد ↔ دریافت در راهکاران", ""],
            [f"تاریخ گزارش {format_jalali_date(date.today())} — از {report['since_jalali']}", ""], ["", ""],
            ["پرداخت هیبریدها در کارآمد (تعداد)", s["karamad_count"]],
            ["پرداخت هیبریدها در کارآمد (تومان)", toman(s["karamad_rial"])],
            ["تطبیق‌شده با دریافت راهکاران", s["matched_karamad_count"]],
            ["پرداخت‌شده در کارآمد ولی بدون دریافت در راهکاران (تعداد)", s["unmatched_karamad_count"]],
            ["پرداخت‌شده در کارآمد ولی بدون دریافت در راهکاران (تومان)", toman(s["unmatched_karamad_rial"])],
            ["…از آن، بدون مشتری هیبرید متناظر در راهکاران (زنجیره‌ای/اینترنتی/برند ناموجود) (تومان)", toman(s["no_rahkaran_customer_rial"])],
            ["دریافت راهکاران از هیبرید بدون پرداخت متناظر در کارآمد (تعداد)", s["unmatched_rahkaran_count"]],
            ["دریافت راهکاران از هیبرید بدون پرداخت متناظر در کارآمد (تومان)", toman(s["unmatched_rahkaran_rial"])],
            ["", ""], ["راهنما", ""],
            ["تطبیق", "پرداخت کارآمد (معین 3112، به شرکت گروه) با دریافت راهکاران از مشتری «هیبرید منطقه - برند»: هم‌مبلغ با نزدیک‌ترین تاریخ (±۱۵ روز)، سپس همان هیبرید با برند دیگر (±۷ روز)، سپس جمع ۲ تا ۳ ردیف (±۳ روز)."],
            ["بدهی اصلاح‌شده", "بدهی فعلی هیبرید در راهکاران منهای پرداخت‌های کارآمدِ بدون معادل؛ یعنی اگر سند دریافت این پرداخت‌ها در راهکاران ثبت شود، بدهی به این عدد می‌رسد."],
            ["محدودیت", "پرداخت با چک و پرداخت مستقیم مشتری نهایی به شرکت در این تطبیق نیستند. دریافت‌های راهکارانِ بی‌معادل ممکن است پرداخت هیبرید از حساب دیگری یا پیش از بازه گزارش باشند."],
        ]:
            ws.append(line)
        ws["A1"].font = Font(bold=True, size=14)
        for cell in ws["B"][3:11]:
            cell.number_format = "#,##0"
        ws.column_dimensions["A"].width = 70
        ws.column_dimensions["B"].width = 100
        for r in ws.iter_rows(min_row=13):
            for cell in r:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

        sheet("به تفکیک هیبرید و برند",
              ["هیبرید (کارآمد)", "برند", "مشتری در راهکاران", "پرداخت در کارآمد (تومان)", "تعداد پرداخت",
               "بدون دریافت در راهکاران (تومان)", "تعداد بدون معادل", "بدهی فعلی در راهکاران (تومان)",
               "بدهی اصلاح‌شده (تومان)", "دریافت راهکاران بی‌معادل (تومان)", "وضعیت"],
              [[g["karamad_branch"], g["brand"], g["rahkaran_customer"] or "— مشتری هیبرید متناظر پیدا نشد",
                toman(g["paid_rial"]), g["paid_count"], toman(g["unmatched_rial"]), g["unmatched_count"],
                toman(g["rahkaran_debt_rial"]), toman(g["adjusted_debt_rial"]), toman(g["rahkaran_only_rial"]),
                "نیازمند بررسی: بدهی اصلاح‌شده منفی است (احتمالاً دریافت جای دیگری ثبت شده)" if g.get("needs_review")
                else ("بدون مشتری هیبرید در راهکاران" if not g["dl_ref"] else "")]
               for g in report["hybrids"]],
              [24, 12, 36, 20, 12, 22, 14, 22, 20, 22, 44], money=(4, 6, 8, 9, 10))
        sheet("پرداخت بدون دریافت در راهکاران",
              ["تاریخ", "هیبرید", "پرداخت به", "نوع", "شماره", "مبلغ (تومان)", "بانک", "بابت", "شرح", "ثبت‌کننده", "سند حسابداری کارآمد"],
              [[jal(k["day"]), k["branch"], k["firm"], k["kind"], k["number"], toman(k["amount"]), k["bank"],
                k["behalf"], k["description"], k["registered_by"], "دارد" if k["has_voucher"] else "ندارد"]
               for k in report["unmatched_karamad"]],
              [12, 22, 18, 14, 10, 18, 24, 40, 30, 22, 14], money=(6,))
        sheet("دریافت راهکاران بی‌معادل",
              ["تاریخ", "مشتری هیبرید", "نوع", "شماره دریافت", "مبلغ (تومان)", "قطعی", "شرح"],
              [[jal(r["day"]), r["party"], r["kind"], r["number"], toman(r["amount"]), "بله" if r["approved"] else "خیر",
                r["description"]] for r in report["unmatched_rahkaran"]],
              [12, 36, 14, 14, 18, 8, 60], money=(5,))
        sheet("تطبیق‌شده",
              ["روش", "فاصله (روز)", "تاریخ کارآمد", "هیبرید", "پرداخت به", "مبلغ کارآمد (تومان)",
               "تاریخ راهکاران", "مشتری راهکاران", "مبلغ راهکاران (تومان)", "قطعی در راهکاران"],
              [[m["method"], m["gap_days"], "، ".join(jal(k["day"]) for k in m["karamad"]), m["karamad"][0]["branch"],
                m["karamad"][0]["firm"], toman(sum(k["amount"] for k in m["karamad"])),
                "، ".join(jal(r["day"]) for r in m["rahkaran"]), m["rahkaran"][0]["party"],
                toman(sum(r["amount"] for r in m["rahkaran"])),
                "بله" if all(r["approved"] for r in m["rahkaran"]) else "خیر"] for m in report["matches"]],
              [24, 10, 22, 22, 18, 18, 22, 36, 18, 12], money=(6, 9))
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        return out
