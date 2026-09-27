from __future__ import annotations

"""V160: Karamad customer receivable balance — «مانده بدهی مشتری» — computed
the same way as the Rahkaran side (finance_prediction_service.customer_account_position):
SUM(Debtor) - SUM(Creditor) from the general ledger, for the CURRENT fiscal
year only, restricted to the receivable SL codes.

Confirmed with the person against real transaction volume in fiscal year
1405: SL codes 1313 (حسابهای دریافتنی(بدهکاران تجاری) — 70,297 lines /
10,035 customers), 1319 (حسابهای دریافتنی - قطعی — tiny but real), and 1320
(حساب های دریافتنی بابت چک برگشتی — tiny but real). Codes 1416/1417/1318/1316
had zero activity this fiscal year and were excluded.

Ledger tables: dbo.tblVoucherLines (Debtor/Creditor/SLRef/DLRef/DL2Ref/DL3Ref)
joined to dbo.tblVoucher (for FiscalYear) and dbo.tblSL (SLRef -> .ID, same
ID-not-Code convention already confirmed for tblSL/tblDL elsewhere).
A customer's DL id can appear at any of the three DL levels on a voucher
line, so all three (DLRef/DL2Ref/DL3Ref) are matched, mirroring Rahkaran's
DLLevel4/5/6 OR-match.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.database.karamad_sqlserver import get_karamad_sqlserver_engine

_RECEIVABLE_SL_CODES = ("1313", "1319", "1320")


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value) if not isinstance(value, Decimal) else float(value)


def _jalali(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import jdatetime
        d = value.date() if hasattr(value, "date") and not isinstance(value, date) else value
        return jdatetime.date.fromgregorian(date=d).isoformat().replace("-", "/")
    except Exception:
        return None


class KaramadCustomerAccountService:
    def __init__(self, engine=None):
        self.engine = engine or get_karamad_sqlserver_engine()

    def bulk_account_positions(self) -> dict[int, dict[str, Any]]:
        """محاسبه مانده همه مشتری‌ها با یک کوئری (GROUP BY)، به‌جای یک کوئری
        جداگانه به ازای هر مشتری — چون یک کوئری جدا برای هر مشتری روی جدول
        ۱۷.۵ میلیون ردیفی دفتر کل باعث کندی محسوس کل صفحه می‌شد.
        خروجی: دیکشنری از dl_ref به نتیجه (همون شکل account_position)."""
        in_clause = ", ".join(f"N'{code}'" for code in _RECEIVABLE_SL_CODES)
        query = text(f"""
            WITH active_fy AS (
                SELECT TOP (1) [ID] AS FiscalYearRef
                FROM dbo.[tblFiscalYear]
                WHERE CAST(GETDATE() AS date) BETWEEN [DateStart] AND [DateEnd]
                ORDER BY [DateStart] DESC
            ),
            receivable_sl AS (
                SELECT [ID] FROM dbo.[tblSL] WHERE [Code] IN ({in_clause})
            ),
            customer_lines AS (
                SELECT vl.[DLRef] AS EffectiveDLRef, vl.[Debtor], vl.[Creditor]
                FROM dbo.[tblVoucherLines] vl
                JOIN receivable_sl sl ON sl.[ID] = vl.[SLRef]
                JOIN dbo.[tblVoucher] v ON v.[ID] = vl.[VoucherRef]
                CROSS JOIN active_fy fy
                WHERE v.[FiscalYear] = fy.[FiscalYearRef]
                  AND (vl.[isDeleted] = 0 OR vl.[isDeleted] IS NULL)
                  AND vl.[DLRef] IS NOT NULL
                UNION ALL
                SELECT vl.[DL2Ref], vl.[Debtor], vl.[Creditor]
                FROM dbo.[tblVoucherLines] vl
                JOIN receivable_sl sl ON sl.[ID] = vl.[SLRef]
                JOIN dbo.[tblVoucher] v ON v.[ID] = vl.[VoucherRef]
                CROSS JOIN active_fy fy
                WHERE v.[FiscalYear] = fy.[FiscalYearRef]
                  AND (vl.[isDeleted] = 0 OR vl.[isDeleted] IS NULL)
                  AND vl.[DL2Ref] IS NOT NULL
                UNION ALL
                SELECT vl.[DL3Ref], vl.[Debtor], vl.[Creditor]
                FROM dbo.[tblVoucherLines] vl
                JOIN receivable_sl sl ON sl.[ID] = vl.[SLRef]
                JOIN dbo.[tblVoucher] v ON v.[ID] = vl.[VoucherRef]
                CROSS JOIN active_fy fy
                WHERE v.[FiscalYear] = fy.[FiscalYearRef]
                  AND (vl.[isDeleted] = 0 OR vl.[isDeleted] IS NULL)
                  AND vl.[DL3Ref] IS NOT NULL
            )
            SELECT EffectiveDLRef AS DLRef, SUM(Debtor) AS DebtorAmount, SUM(Creditor) AS CreditorAmount
            FROM customer_lines
            GROUP BY EffectiveDLRef
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        result: dict[int, dict[str, Any]] = {}
        for r in rows:
            debit = _money(r.get("DebtorAmount"))
            credit = _money(r.get("CreditorAmount"))
            balance = round(debit - credit, 2)
            result[int(r["DLRef"])] = {
                "found": True,
                "debit_balance_rial": round(debit, 2),
                "credit_balance_rial": round(credit, 2),
                "balance_rial": balance,
                "open_account_receivable_rial": max(balance, 0.0),
                "customer_credit_rial": max(-balance, 0.0),
                "balance_status": "debtor" if balance > 0 else "creditor" if balance < 0 else "settled",
            }
        return result

    def account_position(self, dl_ref: int) -> dict[str, Any]:
        # _RECEIVABLE_SL_CODES is a fixed internal constant (not user input),
        # so building the IN list directly is safe.
        in_clause = ", ".join(f"N'{code}'" for code in _RECEIVABLE_SL_CODES)
        query = text(f"""
            WITH active_fy AS (
                SELECT TOP (1) [ID] AS FiscalYearRef, [DateStart], [DateEnd]
                FROM dbo.[tblFiscalYear]
                WHERE CAST(GETDATE() AS date) BETWEEN [DateStart] AND [DateEnd]
                ORDER BY [DateStart] DESC
            ),
            receivable_sl AS (
                SELECT [ID], [Code], [Name] FROM dbo.[tblSL] WHERE [Code] IN ({in_clause})
            )
            SELECT
                dl.[ID] AS DLID, dl.[Name] AS DLName,
                fy.[FiscalYearRef], fy.[DateStart], fy.[DateEnd],
                sl.[ID] AS SLID, sl.[Code] AS SLCode, sl.[Name] AS SLName,
                COALESCE(SUM(vl.[Debtor]), 0) AS DebtorAmount,
                COALESCE(SUM(vl.[Creditor]), 0) AS CreditorAmount,
                COALESCE(SUM(vl.[Debtor] - vl.[Creditor]), 0) AS NetAmount,
                COUNT(vl.[VoucherRef]) AS TransactionCount
            FROM dbo.[tblDL] dl
            CROSS JOIN active_fy fy
            CROSS JOIN receivable_sl sl
            LEFT JOIN dbo.[tblVoucherLines] vl
                ON vl.[SLRef] = sl.[ID]
               AND (vl.[DLRef] = dl.[ID] OR vl.[DL2Ref] = dl.[ID] OR vl.[DL3Ref] = dl.[ID])
               AND (vl.[isDeleted] = 0 OR vl.[isDeleted] IS NULL)
            LEFT JOIN dbo.[tblVoucher] v
                ON v.[ID] = vl.[VoucherRef]
               AND v.[FiscalYear] = fy.[FiscalYearRef]
            WHERE dl.[ID] = :dl_ref
              AND (vl.[VoucherRef] IS NULL OR v.[ID] IS NOT NULL)
            GROUP BY dl.[ID], dl.[Name], fy.[FiscalYearRef], fy.[DateStart], fy.[DateEnd],
                     sl.[ID], sl.[Code], sl.[Name]
            ORDER BY sl.[Code]
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(query, {"dl_ref": int(dl_ref)}).mappings().all()

        if not rows:
            return {"found": False, "dl_ref": int(dl_ref)}

        debit = round(sum(_money(r.get("DebtorAmount")) for r in rows), 2)
        credit = round(sum(_money(r.get("CreditorAmount")) for r in rows), 2)
        balance = round(debit - credit, 2)
        first = rows[0]
        breakdown = [
            {
                "account_id": int(r["SLID"]),
                "account_name": r.get("SLName"),
                "sl_id": int(r["SLID"]),
                "sl_code": str(r.get("SLCode") or ""),
                "sl_title": r.get("SLName"),
                "debit_balance_rial": round(_money(r.get("DebtorAmount")), 2),
                "credit_balance_rial": round(_money(r.get("CreditorAmount")), 2),
                "balance_rial": round(_money(r.get("DebtorAmount")) - _money(r.get("CreditorAmount")), 2),
                "transaction_count": int(r.get("TransactionCount") or 0),
            }
            for r in rows
        ]
        fy_start = first.get("DateStart")
        fy_end = first.get("DateEnd")
        return {
            "found": True,
            "dl_ref": int(dl_ref),
            "dl_id": int(first["DLID"]),
            "dl_name": first.get("DLName"),
            "fiscal_year_ref": int(first["FiscalYearRef"]) if first.get("FiscalYearRef") is not None else None,
            "fiscal_year_start": fy_start.isoformat() if isinstance(fy_start, date) else fy_start,
            "fiscal_year_end": fy_end.isoformat() if isinstance(fy_end, date) else fy_end,
            "account_count": len(rows),
            "account_breakdown": breakdown,
            "debit_balance_rial": debit,
            "credit_balance_rial": credit,
            "balance_rial": balance,
            "open_account_receivable_rial": max(balance, 0.0),
            "customer_credit_rial": max(-balance, 0.0),
            "balance_status": "debtor" if balance > 0 else "creditor" if balance < 0 else "settled",
            "accounting_note": "مانده مشتری از گردش دفتر کل کارآمد (tblVoucherLines) سال مالی جاری روی تفصیلی مشتری و معین‌های ۱۳۱۳/۱۳۱۹/۱۳۲۰ محاسبه می‌شود.",
        }

    def ledger_entries(self, dl_ref: int, limit: int = 500) -> list[dict[str, Any]]:
        """ریز تراکنش‌های بدهکار/بستانکار مشتری — همون شکل گردش حسابی که خود
        اپ کارآمد صادر می‌کند (شعبه، تاریخ، معین، تفضیلی، بدهکار، بستانکار)،
        به‌علاوه ماه شمسی و مانده تجمعی بعد از هر تراکنش."""
        in_clause = ", ".join(f"N'{code}'" for code in _RECEIVABLE_SL_CODES)
        query = text(f"""
            WITH active_fy AS (
                SELECT TOP (1) [ID] AS FiscalYearRef
                FROM dbo.[tblFiscalYear]
                WHERE CAST(GETDATE() AS date) BETWEEN [DateStart] AND [DateEnd]
                ORDER BY [DateStart] DESC
            )
            SELECT TOP (:limit)
                v.[DateE] AS VoucherDate, v.[BranchRef] AS BranchRef, br.[Name] AS BranchName,
                sl.[Name] AS SLName, dl.[Name] AS DLName,
                vl.[Debtor], vl.[Creditor], vl.[Description], vl.[VoucherRef]
            FROM dbo.[tblVoucherLines] vl
            JOIN dbo.[tblSL] sl ON sl.[ID] = vl.[SLRef]
            JOIN dbo.[tblVoucher] v ON v.[ID] = vl.[VoucherRef]
            CROSS JOIN active_fy fy
            LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = vl.[DLRef]
            LEFT JOIN dbo.[tblBranch] br ON br.[Code] = v.[BranchRef]
            WHERE (vl.[DLRef] = :dl_ref OR vl.[DL2Ref] = :dl_ref OR vl.[DL3Ref] = :dl_ref)
              AND sl.[Code] IN ({in_clause})
              AND v.[FiscalYear] = fy.[FiscalYearRef]
              AND (vl.[isDeleted] = 0 OR vl.[isDeleted] IS NULL)
            ORDER BY v.[DateE] ASC
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"dl_ref": int(dl_ref), "limit": int(limit)}).mappings().all()

        entries: list[dict[str, Any]] = []
        running = 0.0
        for r in rows:
            debit = _money(r.get("Debtor"))
            credit = _money(r.get("Creditor"))
            running = round(running + debit - credit, 2)
            v_date = r["VoucherDate"]
            jalali = _jalali(v_date)
            entries.append({
                "date": v_date.isoformat() if hasattr(v_date, "isoformat") else v_date,
                "date_jalali": jalali,
                "jalali_month": jalali[:7].replace("/", "-") if jalali else None,  # e.g. "1405-06"
                "branch_ref": r.get("BranchRef"),
                "branch_name": r.get("BranchName"),
                "sl_name": r.get("SLName"),
                "dl_name": r.get("DLName"),
                "debit_rial": debit,
                "credit_rial": credit,
                "running_balance_rial": running,
                "description": r.get("Description"),
                "voucher_ref": r.get("VoucherRef"),
            })
        entries.reverse()  # جدیدترین بالا، برای نمایش؛ مانده تجمعی همچنان درست محاسبه شده
        return entries

    def monthly_summary(self, dl_ref: int) -> list[dict[str, Any]]:
        """جمع‌بندی گردش حساب مشتری به تفکیک ماه شمسی: بدهکار، بستانکار و
        مانده در پایان هر ماه."""
        entries = self.ledger_entries(dl_ref, limit=2000)
        by_month: dict[str, dict[str, Any]] = {}
        for e in sorted(entries, key=lambda x: x.get("date") or ""):
            month = e.get("jalali_month") or "نامشخص"
            m = by_month.setdefault(month, {"jalali_month": month, "debit_rial": 0.0, "credit_rial": 0.0, "transaction_count": 0, "closing_balance_rial": 0.0})
            m["debit_rial"] = round(m["debit_rial"] + e["debit_rial"], 2)
            m["credit_rial"] = round(m["credit_rial"] + e["credit_rial"], 2)
            m["transaction_count"] += 1
            m["closing_balance_rial"] = e["running_balance_rial"]
        return sorted(by_month.values(), key=lambda x: x["jalali_month"], reverse=True)
