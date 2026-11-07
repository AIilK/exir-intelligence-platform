"""دستور پرداخت‌های شرکت در راهکاران و کارآمد (از treasury_service.py جدا شده)."""

from __future__ import annotations
import re
from typing import Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.services.treasury_common import (
    _as_datetime,
    _as_jalali_date,
    _as_number,
    _engine,
)


def _payment_order_category(description: str | None) -> str:
    text_value = (description or "").strip()
    rules = [
        ("تنخواه", ("تنخواه",)),
        ("حقوق و پرسنل", ("حقوق", "مساعده", "تسویه حساب", "تسويه حساب")),
        ("حمل و باربری", ("بارنامه", "حمل بار", "حمل و نقل", "راهداری")),
        ("واردات و بازرگانی", ("ترخیص", "ترخيص", "کوتاژ", "ثبت سفارش", "پرفرم", "گواهینامه بازرسی")),
        ("خرید و تأمین‌کننده", ("پ ف", "پیش فاکتور", "پيش فاکتور", "فاکتور", "بابت ظرف", "بابت قوطی", "بابت لیبل", "مواد اولیه")),
        ("خدمات و هزینه‌ها", ("تعمیر", "سرویس", "آنالیز", "آزمایشگاه", "اجاره", "ایونت", "مارکتینگ", "طراحی", "کارشناسی")),
    ]
    for label, tokens in rules:
        if any(token in text_value for token in tokens):
            return label
    return "سایر"


def get_company_payment_orders(limit: int = 1000, engine: Engine | None = None) -> dict[str, Any]:
    """حواله‌های پرداختی شرکت از PaymentOrder راهکاران، با تفکیک روش پرداخت و دسته مدیریتی."""
    safe_limit = max(1, min(int(limit), 5000))
    query = text(f"""
        SELECT TOP ({safe_limit})
            po.[PaymentOrderID], po.[Number] AS [PaymentOrderNumber],
            po.[Date] AS [OrderDate], po.[CreationDate], po.[ApproveDate],
            po.[CounterPartRef], cp.[Code] AS [CounterPartCode], cp.[Title] AS [CounterPartName],
            po.[State], po.[PaymentType], po.[SourceType], po.[SourceRef],
            po.[BranchRef], po.[FiscalYearRef], po.[Description], po.[CurrencyRef],
            po.[TotalOperationalCurrencyAmount],
            ISNULL(dep.[Amount], 0) AS [DepositAmount],
            ISNULL(cash.[Amount], 0) AS [CashAmount],
            ISNULL(note.[Amount], 0) AS [ChequeAmount]
        FROM RPA3.[PaymentOrder] po
        LEFT JOIN FIN3.[DL] cp ON cp.[DLID] = po.[CounterPartRef]
        OUTER APPLY (
            SELECT SUM(x.[Amount]) AS [Amount] FROM RPA3.[PaymentOrderDeposit] x
            WHERE x.[PaymentOrderRef] = po.[PaymentOrderID]
        ) dep
        OUTER APPLY (
            SELECT SUM(x.[Amount]) AS [Amount] FROM RPA3.[PaymentOrderCashMoney] x
            WHERE x.[PaymentOrderRef] = po.[PaymentOrderID]
        ) cash
        OUTER APPLY (
            SELECT SUM(x.[Amount]) AS [Amount] FROM RPA3.[PaymentOrderPayableNote] x
            WHERE x.[PaymentOrderRef] = po.[PaymentOrderID]
        ) note
        ORDER BY po.[Date] DESC, po.[PaymentOrderID] DESC
    """)
    with _engine(engine).connect() as connection:
        db_rows = connection.execute(query).mappings().all()

    rows: list[dict[str, Any]] = []
    for row in db_rows:
        deposit = _as_number(row["DepositAmount"])
        cash = _as_number(row["CashAmount"])
        cheque = _as_number(row["ChequeAmount"])
        calculated = deposit + cash + cheque
        if cheque and not (deposit or cash):
            method = "چکی"
        elif (deposit or cash) and not cheque:
            method = "نقد/بانکی"
        elif calculated:
            method = "ترکیبی"
        else:
            method = "نامشخص"
        rows.append({
            "payment_order_id": row["PaymentOrderID"],
            "payment_order_number": row["PaymentOrderNumber"],
            "order_date": _as_datetime(row["OrderDate"]),
            "order_date_jalali": _as_jalali_date(row["OrderDate"]),
            "creation_date": _as_datetime(row["CreationDate"]),
            "approve_date": _as_datetime(row["ApproveDate"]),
            "counterpart_ref": row["CounterPartRef"],
            "counterpart_code": row["CounterPartCode"],
            "counterpart_name": row["CounterPartName"],
            "state": row["State"],
            "state_label": f"وضعیت {row['State']}",
            "payment_type": row["PaymentType"],
            "source_type": row["SourceType"],
            "source_ref": row["SourceRef"],
            "branch_ref": row["BranchRef"],
            "fiscal_year_ref": row["FiscalYearRef"],
            "description": row["Description"],
            "currency_ref": row["CurrencyRef"],
            "operational_currency_amount": _as_number(row["TotalOperationalCurrencyAmount"]),
            "deposit_amount": deposit,
            "cash_amount": cash,
            "cheque_amount": cheque,
            "calculated_amount": calculated,
            "payment_method": method,
            "category": _payment_order_category(row["Description"]),
            "is_approved": row["ApproveDate"] is not None,
            "source": "rahkaran",
            "source_label": "راهکاران",
        })

    categories: dict[str, dict[str, Any]] = {}
    for item in rows:
        bucket = categories.setdefault(item["category"], {"count": 0, "amount": 0})
        bucket["count"] += 1
        bucket["amount"] += item["calculated_amount"]
    return {
        "status": "ok", "source": "rahkaran", "rows": rows,
        "summary": {
            "count": len(rows),
            "calculated_amount": sum(x["calculated_amount"] for x in rows),
            "approved_count": sum(1 for x in rows if x["is_approved"]),
            "waiting_count": sum(1 for x in rows if not x["is_approved"]),
            "bank_cash_count": sum(1 for x in rows if x["payment_method"] == "نقد/بانکی"),
            "cheque_count": sum(1 for x in rows if x["payment_method"] == "چکی"),
            "categories": categories,
        },
        "note": "دسته‌بندی مدیریتی بر پایه شرح حواله است؛ State خام راهکاران نیز برای کنترل نمایش داده می‌شود.",
    }


_KARAMAD_FEE_TOKENS = ("کارمزد", "شاپرک", "هزینه بانکی", "هزنیه بانکی", "واگذاری چک", "هزینه کارمزد")


_KARAMAD_BANK_NAMES = ("سپه", "بانک", "ملت", "ملی", "تجارت", "صادرات", "پارسیان", "پاسارگاد", "رفاه", "سامان", "اقتصاد نوین", "شهر")


def _karamad_payment_category(counterpart: Any, behalf: Any, description: Any) -> str:
    """دسته پرداخت کارآمد؛ در کارآمد معنای پرداخت بیشتر در «تفصیلی طرف حساب» است تا شرح."""

    from app.services.karamad_live_cash_draft_service import _classify

    def clean(value: Any) -> str:
        value = str(value or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
        return re.sub(r"\s+", " ", value).strip()

    name = clean(counterpart)
    text_value = clean(f"{behalf or ''} {description or ''}")
    is_company_account = (
        (name.startswith(_KARAMAD_BANK_NAMES) and re.search(r"\d{6,}", name) is not None)
        or name.startswith(("هیبرید", "انتقال"))
        or "برداشت از سپرده" in name
    )
    if is_company_account or _classify(behalf, description)[0] == "company_bank_transfer":
        return "انتقال بین حساب‌های شرکت"
    if name == "جاری شرکا":
        return "جاری شرکا"
    if name in {"ک"} or any(token in f"{name} {text_value}" for token in _KARAMAD_FEE_TOKENS):
        return "کارمزد و هزینه بانکی"
    if any(token in f"{name} {text_value}" for token in ("سنوات", "پرسنل", "پاداش", "عیدی")):
        return "حقوق و پرسنل"
    if name.startswith("شرکت"):
        return "شرکت‌ها و تأمین‌کنندگان"
    category = _payment_order_category(f"{name} {text_value}")
    if category == "سایر" and name.startswith(("هزینه", "هزنیه")):
        return "خدمات و هزینه‌ها"
    return category


def get_company_payment_orders_karamad(limit: int = 5000, since: Any = None) -> dict[str, Any]:
    """پرداخت‌های شرکت از کارآمد، هم‌شکل خروجی راهکاران.

    هر سند پرداخت کارآمد یک ردیف است:
    - حواله پرداخت بانکی: dbo.tblDraftP (Price، بانک از tblAccBank)
    - پرداخت نقدی صندوق: dbo.tblCashP (PriceN، صندوق از tblAccFund)
    - چک پرداختی: dbo.tblChequeP (Price، وضعیت از tblChequePStatus)
    tblPaymentRequest در کارآمد کم استفاده می‌شود (حدود ۹٪ حواله‌ها)، پس مبنا خود اسناد پرداخت است.
    کارآمد تاریخ تأیید ندارد؛ «صدور سند حسابداری» (VoucherRef) معادل تأیید نمایش داده می‌شود.
    """
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    from app.services.karamad_live_cash_draft_service import _classify

    safe_limit = max(1, min(int(limit), 20000))
    query = text(f"""
        WITH payments AS (
            SELECT N'draft' AS Kind, CAST(d.[inx] AS bigint) AS ItemID, CAST(d.[Code] AS nvarchar(50)) AS Number,
                   d.[BookDate], CAST(NULL AS date) AS DueDate, d.[Price] AS Amount, d.[Charge] AS Charge,
                   d.[Behalf], d.[Description], d.[DLRef], d.[BranchRef], d.[BankRef], CAST(NULL AS int) AS FundRef,
                   d.[VoucherRef], CAST(NULL AS int) AS StatusRef, d.[UserRef], d.[PaymentRequestRef]
            FROM dbo.[tblDraftP] d
            UNION ALL
            SELECT N'cash', CAST(c.[inx] AS bigint), CAST(c.[Code] AS nvarchar(50)), c.[BookDate], NULL, c.[PriceN], NULL,
                   c.[Behalf], c.[Description], c.[DLRef], c.[BranchRef], NULL, c.[FundRef],
                   c.[VoucherRef], NULL, c.[UserRef], c.[PaymentRequestRef]
            FROM dbo.[tblCashP] c
            UNION ALL
            SELECT N'cheque', CAST(q.[inx] AS bigint), CAST(q.[Code] AS nvarchar(50)), q.[BookDate], q.[DueDate], q.[Price], NULL,
                   q.[Behalf], q.[Description], q.[DLRef], q.[BranchRef], q.[BankRef], NULL,
                   NULL, q.[StatusRef], q.[UserRef], q.[PaymentRequestRef]
            FROM dbo.[tblChequeP] q
        )
        SELECT TOP ({safe_limit}) p.*, dl.[Name] AS CounterpartName, dl.[Code] AS CounterpartCode,
               br.[Name] AS BranchName, bk.[Name] AS BankName, fd.[Name] AS FundName,
               st.[Name] AS ChequeStatus, u.[Name] AS UserName
        FROM payments p
        LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = p.[DLRef]
        LEFT JOIN dbo.[tblUser] u ON u.[ID] = p.[UserRef]
        OUTER APPLY (SELECT TOP (1) b.[Name] FROM dbo.[tblBranch] b WHERE b.[Code] = p.[BranchRef]) br
        OUTER APPLY (SELECT TOP (1) a.[Name] FROM dbo.[tblAccBank] a WHERE a.[Code] = p.[BankRef]) bk
        OUTER APPLY (SELECT TOP (1) f.[Name] FROM dbo.[tblAccFund] f WHERE f.[Code] = p.[FundRef]) fd
        OUTER APPLY (SELECT TOP (1) s.[Name] FROM dbo.[tblChequePStatus] s WHERE s.[Code] = p.[StatusRef]) st
        WHERE (:since IS NULL OR p.[BookDate] >= :since)
        ORDER BY p.[BookDate] DESC, p.[ItemID] DESC
    """)
    with get_karamad_sqlserver_engine().connect() as connection:
        db_rows = connection.execute(query, {"since": since}).mappings().all()

    method_by_kind = {"draft": "نقد/بانکی", "cash": "نقد/بانکی", "cheque": "چکی"}
    kind_label = {"draft": "حواله بانکی", "cash": "پرداخت نقدی", "cheque": "چک پرداختی"}
    rows: list[dict[str, Any]] = []
    for row in db_rows:
        kind = row["Kind"]
        amount = _as_number(row["Amount"])
        description = " | ".join(
            str(value).strip() for value in (row["Behalf"], row["Description"]) if value and str(value).strip()
        )
        category = _karamad_payment_category(row["CounterpartName"] or row["Behalf"], row["Behalf"], row["Description"])
        if kind == "cheque":
            state = f"cheque:{row['StatusRef']}"
            state_label = f"چک {row['ChequeStatus'] or 'نامشخص'}"
            approved = row["StatusRef"] not in (None, 1)
        else:
            approved = row["VoucherRef"] is not None
            state = "voucher" if approved else "no_voucher"
            state_label = "سند حسابداری صادر شده" if approved else "بدون سند حسابداری"
        order_date = row["BookDate"]
        rows.append({
            "payment_order_id": f"karamad:{kind}:{row['ItemID']}",
            "payment_order_number": row["Number"],
            "order_date": _as_datetime(order_date),
            "order_date_jalali": _as_jalali_date(order_date),
            "creation_date": None,
            "approve_date": _as_datetime(order_date) if approved else None,
            "counterpart_ref": row["DLRef"],
            "counterpart_code": row["CounterpartCode"],
            "counterpart_name": row["CounterpartName"] or row["Behalf"],
            "state": state,
            "state_label": state_label,
            "payment_type": kind,
            "payment_kind_label": kind_label[kind],
            "source_type": None,
            "source_ref": row["PaymentRequestRef"],
            "branch_ref": row["BranchRef"],
            "branch_name": row["BranchName"],
            "fiscal_year_ref": None,
            "description": description,
            "currency_ref": None,
            "operational_currency_amount": amount,
            "deposit_amount": amount if kind == "draft" else 0,
            "cash_amount": amount if kind == "cash" else 0,
            "cheque_amount": amount if kind == "cheque" else 0,
            "calculated_amount": amount,
            "bank_fee_amount": _as_number(row["Charge"]) if row["Charge"] is not None else 0,
            "payment_method": method_by_kind[kind],
            "category": category,
            "is_approved": approved,
            "bank_name": row["BankName"] or row["FundName"],
            "due_date_jalali": _as_jalali_date(row["DueDate"]) if row["DueDate"] else None,
            "registered_by": row["UserName"],
            "source": "karamad",
            "source_label": "کارآمد",
        })
    return _company_payment_response(rows, source="karamad")


def _company_payment_response(rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = {}
    for item in rows:
        bucket = categories.setdefault(item["category"], {"count": 0, "amount": 0})
        bucket["count"] += 1
        bucket["amount"] += item["calculated_amount"]
    return {
        "status": "ok", "source": source, "rows": rows,
        "summary": {
            "count": len(rows),
            "calculated_amount": sum(x["calculated_amount"] for x in rows),
            "approved_count": sum(1 for x in rows if x["is_approved"]),
            "waiting_count": sum(1 for x in rows if not x["is_approved"]),
            "bank_cash_count": sum(1 for x in rows if x["payment_method"] == "نقد/بانکی"),
            "cheque_count": sum(1 for x in rows if x["payment_method"] == "چکی"),
            "categories": categories,
        },
    }
