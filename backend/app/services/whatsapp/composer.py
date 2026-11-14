"""ساختن پیام‌های واتساپ از داده زنده کارآمد.

- بدهی مشتری: همان مانده دفتر کل که در داشبورد است (ledger_positions: قطعی + موقت، سال مالی جاری)
- چک‌های پیش‌رو: چک‌های دریافتی باز (غیرقطعی، نزد صندوق، واگذار شده) با سررسید از امروز تا N روز آینده،
  بدون چک‌های تضمینی
- ویزیتور: مشتریان هر ویزیتور = ویزیتور آخرین فاکتور مشتری (همان قاعده سایر گزارش‌های کارآمد)
شماره گیرنده: موبایل کارآمد (tblCustomer.Mobile / tblVisitor.Mobile) مگر شماره جایگزین در دفترچه گیرنده‌ها ثبت شده باشد.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from io import BytesIO
from typing import Any, Protocol

from app.services.whatsapp import store
from app.services.whatsapp.waha_client import normalize_mobile
from app.utils.jalali import format_jalali_date

OPEN_UPCOMING_STATUSES = (1, 2, 3)  # غیرقطعی، نزد صندوق، واگذار شده (به بانک)
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_num(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", "٬").translate(_FA_DIGITS)


def toman(rial: float | int) -> str:
    return fa_num((rial or 0) / 10)


def fa_text(value: Any) -> str:
    return str(value or "").translate(_FA_DIGITS)


_PHONE_IN_NAME = re.compile(r"[\s/\-–—،,]*(?:\+?98|0)?9\d{9}|[\s/\-–—،,]*(?:\+?98|0)9\d{2}[\s-]?\d{3}[\s-]?\d{4}")


def clean_name(raw: Any) -> str:
    """نام برای پیام: ی/ک فارسی، بدون شماره موبایلی که در کارآمد داخل نام نوشته شده."""
    name = str(raw or "").replace("ي", "ی").replace("ك", "ک")
    name = _PHONE_IN_NAME.sub("", name.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    return re.sub(r"\s+", " ", name).strip(" /-–—،,") or str(raw or "")


def mobile_in_name(raw: Any) -> str | None:
    m = re.search(r"(?:\+?98|0)?9\d{9}", re.sub(r"[\s-]", "", str(raw or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))))
    return normalize_mobile(m.group(0)) if m else None


class _Blank(dict):
    def __missing__(self, key: str) -> str:
        return ""


def render(template: str, values: dict[str, Any]) -> str:
    try:
        return template.format_map(_Blank(values)).strip()
    except (ValueError, IndexError):
        # آکولاد نامتوازن در متن قالب؛ متن خام را بدون جایگذاری نمی‌فرستیم
        raise ValueError("متن قالب نامعتبر است: آکولادهای { } را بررسی کنید.")


class Source(Protocol):
    def customers(self) -> list[dict[str, Any]]: ...
    def positions(self) -> dict[int, dict[str, Any]]: ...
    def upcoming_cheques(self, days_ahead: int) -> list[dict[str, Any]]: ...
    def visitors(self) -> list[dict[str, Any]]: ...
    def customer_visitor(self) -> dict[int, int]: ...
    def branches(self) -> list[dict[str, Any]]: ...


class KaramadSource:
    """خواندن فقط-خواندنی از SQL Server کارآمد."""

    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
            self._engine = get_karamad_sqlserver_engine()
        return self._engine

    def _rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.connect().execution_options(isolation_level="READ UNCOMMITTED") as c:
            return [dict(r) for r in c.execute(text(sql), params or {}).mappings().all()]

    def customers(self) -> list[dict[str, Any]]:
        return self._rows("""
            SELECT cu.[ID] AS id, cu.[DLRef] AS dl_ref, cu.[Name] AS name, cu.[Code] AS code, cu.[Mobile] AS mobile,
                   cu.[BranchRef] AS branch_ref, b.[Name] AS branch
            FROM dbo.[tblCustomer] cu
            OUTER APPLY (SELECT TOP (1) x.[Name] FROM dbo.[tblBranch] x WHERE x.[Code] = cu.[BranchRef]) b
            WHERE cu.[DLRef] IS NOT NULL
        """)

    def positions(self) -> dict[int, dict[str, Any]]:
        from app.services.karamad_sales_network_service import ledger_positions
        return ledger_positions()

    def upcoming_cheques(self, days_ahead: int) -> list[dict[str, Any]]:
        from app.services.karamad_live_received_cheque_service import not_guarantee_cheque
        statuses = ", ".join(str(s) for s in OPEN_UPCOMING_STATUSES)
        return self._rows(f"""
            SELECT d.[inx] AS id, d.[Code] AS number, d.[DueDate] AS due_date, d.[Price] AS amount_rial,
                   d.[DLRef] AS dl_ref, d.[DL2Ref] AS dl2_ref, d.[DL3Ref] AS dl3_ref, d.[StatusRef] AS status_ref,
                   st.[Name] AS status, bk.[Name] AS bank
            FROM dbo.[tblChequeD] d
            OUTER APPLY (SELECT TOP (1) s.[Name] FROM dbo.[tblChequeDStatus] s WHERE s.[Code] = d.[StatusRef]) st
            OUTER APPLY (SELECT TOP (1) b.[Name] FROM dbo.[tblBankList] b WHERE b.[Code] = d.[BankIDRef]) bk
            WHERE d.[StatusRef] IN ({statuses}) AND {not_guarantee_cheque('d')}
              AND d.[DueDate] >= CAST(GETDATE() AS date)
              AND d.[DueDate] < DATEADD(day, :days, CAST(GETDATE() AS date))
            ORDER BY d.[DueDate], d.[inx]
        """, {"days": int(days_ahead) + 1})

    def visitors(self) -> list[dict[str, Any]]:
        return self._rows("""
            SELECT v.[ID] AS id, v.[Name] AS name, v.[Code] AS code, v.[Mobile] AS mobile, v.[BranchRef] AS branch_ref,
                   b.[Name] AS branch
            FROM dbo.[tblVisitor] v
            OUTER APPLY (SELECT TOP (1) x.[Name] FROM dbo.[tblBranch] x WHERE x.[Code] = v.[BranchRef]) b
            WHERE v.[Status] = 1
        """)

    def customer_visitor(self) -> dict[int, int]:
        rows = self._rows("""
            SELECT cu.[DLRef] AS dl_ref, last.[VisitorRef] AS visitor_id FROM dbo.[tblCustomer] cu
            CROSS APPLY (SELECT TOP (1) f.[VisitorRef] FROM dbo.[tblFactorF] f WHERE f.[CustomerRef] = cu.[ID]
                         ORDER BY f.[DateE] DESC) last
            WHERE cu.[DLRef] IS NOT NULL AND last.[VisitorRef] IS NOT NULL
        """)
        return {int(r["dl_ref"]): int(r["visitor_id"]) for r in rows}

    def branches(self) -> list[dict[str, Any]]:
        return self._rows("SELECT [Code] AS id, [Name] AS name FROM dbo.[tblBranch] ORDER BY [Code]")


# ---------------------------------------------------------------------------
def _branch_ok(branch_ref: Any, branch_ids: list[Any]) -> bool:
    return not branch_ids or str(branch_ref) in {str(b) for b in branch_ids}


def _cheques_by_customer(cheques: list[dict[str, Any]], customer_dls: set[int]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ch in cheques:
        dl = next((int(d) for d in (ch.get("dl_ref"), ch.get("dl2_ref"), ch.get("dl3_ref")) if d and int(d) in customer_dls), None)
        if dl is not None:
            out[dl].append(ch)
    return out


def _cheque_line(ch: dict[str, Any]) -> str:
    bank = f" ({ch['bank']})" if ch.get("bank") else ""
    return f"• چک {fa_text(ch.get('number'))} — سررسید {fa_text(format_jalali_date(ch.get('due_date')))} — {toman(ch.get('amount_rial') or 0)} تومان{bank}"


class Composer:
    def __init__(self, source: Source | None = None, today: date | None = None):
        self.source = source or KaramadSource()
        self.today = today or date.today()
        self.today_jalali = format_jalali_date(self.today) or self.today.isoformat()

    def _resolve(self, kind: str, ref: Any, raw_mobile: Any, overrides: dict, raw_name: Any = None) -> tuple[str | None, bool]:
        ov = overrides.get((kind, str(ref)))
        if ov and ov.get("opted_out"):
            return None, True
        phone = normalize_mobile(ov.get("phone")) if ov and ov.get("phone") else None
        return phone or normalize_mobile(raw_mobile) or mobile_in_name(raw_name), False

    def compose(self, rule: dict[str, Any], *, dedupe_suffix: str = "") -> dict[str, Any]:
        kind = rule["kind"]
        fn = {"customer_debt": self._customer_debt, "customer_cheques": self._customer_cheques,
              "visitor_report": self._visitor_report}[kind]
        stats: dict[str, Any] = {"candidates": 0, "ready": 0, "no_phone": 0, "opted_out": 0, "no_phone_names": []}
        items = fn(rule, rule.get("params") or {}, stats)
        for it in items:
            it["rule_id"] = rule.get("id")
            it["kind"] = kind
            it["dedupe_key"] = f"{rule.get('id')}:{it['recipient_kind']}:{it['recipient_ref']}:{self.today.isoformat()}{dedupe_suffix}"
        stats["ready"] = len(items)
        stats["no_phone_names"] = stats["no_phone_names"][:50]
        return {"items": items, "stats": stats}

    def _skip(self, stats: dict[str, Any], name: str, opted_out: bool) -> None:
        if opted_out:
            stats["opted_out"] += 1
        else:
            stats["no_phone"] += 1
            stats["no_phone_names"].append(name)

    # ---- بدهی مشتری ----
    def _customer_debt(self, rule, params, stats) -> list[dict[str, Any]]:
        min_rial = float(params.get("min_debt_toman") or 0) * 10
        branch_ids = params.get("branch_ids") or []
        positions = self.source.positions()
        overrides = store.recipient_overrides("customer")
        items = []
        for cu in self.source.customers():
            if not _branch_ok(cu.get("branch_ref"), branch_ids):
                continue
            debt = float((positions.get(int(cu["dl_ref"])) or {}).get("balance_rial") or 0)
            if debt <= 0 or debt < min_rial:
                continue
            stats["candidates"] += 1
            phone, opted = self._resolve("customer", cu["dl_ref"], cu.get("mobile"), overrides, cu.get("name"))
            if not phone:
                self._skip(stats, cu.get("name") or "", opted)
                continue
            items.append({
                "recipient_kind": "customer", "recipient_ref": cu["dl_ref"], "recipient_name": clean_name(cu.get("name")),
                "branch": cu.get("branch"), "phone": phone, "amount_rial": debt,
                "message": render(rule["template"], {"name": clean_name(cu.get("name")), "code": cu.get("code"), "debt": toman(debt),
                                                     "date": fa_text(self.today_jalali), "branch": cu.get("branch")}),
            })
        return items

    # ---- چک‌های پیش‌رو مشتری ----
    def _customer_cheques(self, rule, params, stats) -> list[dict[str, Any]]:
        days = max(0, int(params.get("days_ahead") or 3))
        branch_ids = params.get("branch_ids") or []
        customers = {int(c["dl_ref"]): c for c in self.source.customers()}
        by_customer = _cheques_by_customer(self.source.upcoming_cheques(days), set(customers))
        overrides = store.recipient_overrides("customer")
        items = []
        for dl, cheques in by_customer.items():
            cu = customers[dl]
            if not _branch_ok(cu.get("branch_ref"), branch_ids):
                continue
            stats["candidates"] += 1
            phone, opted = self._resolve("customer", dl, cu.get("mobile"), overrides, cu.get("name"))
            if not phone:
                self._skip(stats, cu.get("name") or "", opted)
                continue
            total = sum(float(c.get("amount_rial") or 0) for c in cheques)
            items.append({
                "recipient_kind": "customer", "recipient_ref": dl, "recipient_name": clean_name(cu.get("name")),
                "branch": cu.get("branch"), "phone": phone, "amount_rial": total,
                "message": render(rule["template"], {
                    "name": clean_name(cu.get("name")), "code": cu.get("code"), "days": fa_num(days), "count": fa_num(len(cheques)),
                    "cheques": "\n".join(_cheque_line(c) for c in cheques), "total": toman(total),
                    "date": fa_text(self.today_jalali), "branch": cu.get("branch")}),
            })
        return items

    # ---- گزارش ویزیتور (متن + اکسل) ----
    def _visitor_report(self, rule, params, stats) -> list[dict[str, Any]]:
        days = max(0, int(params.get("days_ahead") or 7))
        min_rial = float(params.get("min_debt_toman") or 0) * 10
        branch_ids = params.get("branch_ids") or []
        attach = params.get("attach_excel", True)
        customers = {int(c["dl_ref"]): c for c in self.source.customers()}
        positions = self.source.positions()
        cheques = _cheques_by_customer(self.source.upcoming_cheques(days), set(customers))
        cust_visitor = self.source.customer_visitor()
        by_visitor: dict[int, list[int]] = defaultdict(list)
        for dl, vid in cust_visitor.items():
            if dl in customers:
                by_visitor[vid].append(dl)
        overrides = store.recipient_overrides("visitor")
        items = []
        for v in self.source.visitors():
            if not _branch_ok(v.get("branch_ref"), branch_ids):
                continue
            dls = by_visitor.get(int(v["id"]), [])
            debtors = []
            for dl in dls:
                debt = float((positions.get(dl) or {}).get("balance_rial") or 0)
                if debt > 0 and debt >= min_rial:
                    debtors.append((customers[dl], debt))
            vcheques = [(customers[dl], ch) for dl in dls for ch in cheques.get(dl, [])]
            if not debtors and not vcheques:
                continue
            stats["candidates"] += 1
            phone, opted = self._resolve("visitor", v["id"], v.get("mobile"), overrides, v.get("name"))
            if not phone:
                self._skip(stats, v.get("name") or "", opted)
                continue
            debtors.sort(key=lambda x: -x[1])
            vcheques.sort(key=lambda x: (x[1].get("due_date") or date.max))
            debt_total = sum(d for _, d in debtors)
            cheque_total = sum(float(ch.get("amount_rial") or 0) for _, ch in vcheques)
            item = {
                "recipient_kind": "visitor", "recipient_ref": v["id"], "recipient_name": clean_name(v.get("name")),
                "branch": v.get("branch"), "phone": phone, "amount_rial": debt_total,
                "message": render(rule["template"], {
                    "name": clean_name(v.get("name")), "date": fa_text(self.today_jalali), "days": fa_num(days),
                    "debtor_count": fa_num(len(debtors)), "debt": toman(debt_total),
                    "cheque_count": fa_num(len(vcheques)), "cheque_total": toman(cheque_total), "branch": v.get("branch")}),
            }
            if attach:
                fname = f"گزارش-مشتریان-{clean_name(v.get('name')) or v['id']}-{self.today_jalali.replace('/', '-')}.xlsx"
                path = store.files_dir() / f"visitor_{v['id']}_{self.today.isoformat()}_{rule.get('id')}.xlsx"
                path.write_bytes(visitor_excel(v, debtors, vcheques, self.today_jalali))
                item.update(file_path=str(path), file_name=fname.replace(" ", "-"))
            items.append(item)
        return items


def visitor_excel(visitor: dict[str, Any], debtors: list[tuple[dict, float]], cheques: list[tuple[dict, dict]], today_jalali: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="0F766E")

    def sheet(ws, title: str, headers: list[str], rows: list[list[Any]], money_cols: set[int], widths: list[int]):
        ws.title = title
        ws.sheet_view.rightToLeft = True
        ws.append([f"{clean_name(visitor.get('name'))} — {title} — تاریخ {today_jalali}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append(headers)
        for cell in ws[2]:
            cell.font, cell.fill, cell.alignment = head_font, head_fill, Alignment(horizontal="center")
        for r in rows:
            ws.append(r)
        for row in ws.iter_rows(min_row=3):
            for idx in money_cols:
                row[idx].number_format = "#,##0"
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        ws.freeze_panes = "A3"

    sheet(wb.active, "بدهی مشتریان", ["مشتری", "کد", "موبایل", "شعبه", "مانده بدهی (تومان)"],
          [[clean_name(c.get("name")), c.get("code"), c.get("mobile"), c.get("branch"), round(d / 10)] for c, d in debtors]
          + [["جمع", None, None, None, round(sum(d for _, d in debtors) / 10)]],
          {4}, [34, 12, 15, 18, 20])
    sheet(wb.create_sheet(), "چک‌های پیش‌رو", ["مشتری", "شماره چک", "سررسید", "مبلغ (تومان)", "بانک", "وضعیت"],
          [[clean_name(c.get("name")), ch.get("number"), format_jalali_date(ch.get("due_date")), round(float(ch.get("amount_rial") or 0) / 10),
            ch.get("bank"), ch.get("status")] for c, ch in cheques]
          + [["جمع", None, None, round(sum(float(ch.get("amount_rial") or 0) for _, ch in cheques) / 10), None, None]],
          {3}, [34, 16, 12, 18, 18, 16])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
