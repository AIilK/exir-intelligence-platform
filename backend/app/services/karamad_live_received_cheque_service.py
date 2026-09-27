from __future__ import annotations

"""V158: Live read-only source for Karamad received cheques.

Reads directly from dbo.tblChequeD (and its lookup tables) instead of the
manual Excel snapshot. Output shape matches
KaramadManualImportService.cheque_rows("received_cheques") field-for-field,
so the frontend and every downstream service that already consumes that
shape (treasury_service._karamad_cheques, finance_prediction_service,
unified_cashflow_service, ...) work unchanged.

Every join below was confirmed against three real rows (شناسه 36540, 38709,
41775) pulled from the same Excel export the person uses today:

- SLRef / DLRef / DL2Ref / DL3Ref reference tblSL.ID / tblDL.ID — their
  internal primary key — NOT tblSL.Code / tblDL.Code (a separate display
  code). Joining on Code silently returns NULL names.
- FundRef -> tblAccFund.Code correctly resolves «محل چک» (e.g. "صندوق مازندران").
- BranchRef -> tblBranch.Code correctly resolves the branch name.
- BankIDRef -> tblBankList.Code correctly resolves the real bank name
  (e.g. "ملی"). d.[Bank] itself is NOT a bank name despite the column
  name — in the sample data it held a plain numeric branch/routing code,
  matching the Excel column «نام بانک و شعبه» (also numeric there).
- InquiryCode is «شناسه صیاد» — confirmed by an exact match against the
  Excel column.
- FiscalYear references tblFiscalYear.ID, not .Code (both happen to look
  like a year for recent rows, but ID is the correct join key).
- ReturnReasonRef most likely references tblReturnChequeDReason.ID, by the
  same ID/CompanyRef/Code table shape as tblSL/tblDL/tblFiscalYear — not
  empirically confirmed yet since the sample rows all had a blank return
  reason.

Status table (dbo.tblChequeDStatus), confirmed by direct inspection:
    1  غیرقطعی
    2  نزد صندوق
    3  واگذار شده
    4  وصول شده          (final)
    5  خرج شده           (final)
    6  برگشت نزذ صندوق   (typo in Karamad's own data: نزذ instead of نزد)
    7  برگشتی نزد مشتری
    8  برگشتی وصول شده   (final)
    9  عودت نزد مشتری     (final)
    10 برگشتی نزد صندوق
    11 انتقال بین شعب
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.database.karamad_sqlserver import get_karamad_sqlserver_engine


def _number(value: Any) -> int | float:
    if value is None:
        return 0
    n = value if isinstance(value, Decimal) else Decimal(str(value))
    return int(n) if n == n.to_integral_value() else float(n)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _jalali(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import jdatetime
        d = value.date() if isinstance(value, datetime) else value
        return jdatetime.date.fromgregorian(date=d).isoformat().replace("-", "/")
    except Exception:
        return None


class KaramadLiveReceivedChequeService:
    """Live read-only source for Karamad received cheques (dbo.tblChequeD)."""

    def __init__(self, engine=None):
        self.engine = engine or get_karamad_sqlserver_engine()

    def report(self, branch: str | None = None, limit: int = 200000, offset: int = 0, open_only: bool = True) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200000))
        offset = max(0, int(offset))
        # V158: codes agreed with the person as still non-final (open) —
        # 1 غیرقطعی, 2 نزد صندوق, 3 واگذار شده, 6 برگشت نزذ صندوق (typo in
        # Karamad's own status name), 7 برگشتی نزد مشتری, 10 برگشتی نزد صندوق.
        # Closed/final: 4 وصول شده, 5 خرج شده, 8 برگشتی وصول شده, 9 عودت نزد
        # مشتری, 11 انتقال بین شعب (person confirmed 11 stays closed).
        where = "d.[StatusRef] IN (1, 2, 3, 6, 7, 10)" if open_only else "1=1"
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if branch:
            where += " AND CAST(d.[BranchRef] AS varchar(50)) = :branch"
            params["branch"] = branch

        rows_sql = text(f"""
            SELECT
                d.[inx] AS movement_id,
                d.[BranchRef] AS branch_ref,
                d.[Code] AS document_code,
                d.[BookDate] AS registration_date,
                d.[DueDate] AS due_date,
                d.[Price] AS amount_rial,
                d.[BankIDRef] AS bank_id_ref,
                d.[AccountNo] AS account_number,
                d.[Behalf] AS behalf,
                d.[Description] AS description,
                d.[SLRef] AS sl_ref,
                d.[DLRef] AS dl_ref,
                d.[DL2Ref] AS dl2_ref,
                d.[DL3Ref] AS dl3_ref,
                d.[FundRef] AS fund_ref,
                d.[StatusRef] AS status_ref,
                d.[Serial] AS serial_number,
                d.[InquiryCode] AS sayad_number,
                d.[ReturnReasonRef] AS return_reason_ref,
                d.[OwnerName] AS owner_name,
                d.[OwnerIDCode] AS owner_national_id,
                d.[IsECheque] AS is_e_cheque,
                d.[AssignmentDate] AS assignment_date,
                d.[Confirmed] AS confirmed,
                lop_sl.[Name] AS last_op_sl_name,
                lop_dl.[Name] AS last_op_level4_name,
                lop_dl2.[Name] AS last_op_level5_name,
                lop_dl3.[Name] AS last_op_level6_name,
                stt.[status_name],
                brr.[branch_name],
                rrr.[return_reason_name],
                fundd.[fund_name],
                bankk.[bank_name],
                fyy.[fiscal_year_name]
            FROM dbo.[tblChequeD] d
            -- SLRef/DLRef reference tblSL.ID / tblDL.ID (internal PK), not .Code — safe as a plain JOIN.
            LEFT JOIN dbo.[tblSL] sl ON sl.[ID] = d.[SLRef]
            LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = d.[DLRef]
            LEFT JOIN dbo.[tblDL] dl2 ON dl2.[ID] = d.[DL2Ref]
            LEFT JOIN dbo.[tblDL] dl3 ON dl3.[ID] = d.[DL3Ref]
            -- Every lookup below keys off .Code, and Karamad's own data has proven
            -- duplicate Codes in at least tblAccFund (confirmed: one FundRef matched
            -- two rows and silently duplicated a cheque). OUTER APPLY TOP(1) makes
            -- every one of these immune to that, guaranteeing exactly one output row
            -- per cheque regardless of dirty lookup data.
            OUTER APPLY (SELECT TOP (1) st.[Name] AS status_name FROM dbo.[tblChequeDStatus] st WHERE st.[Code] = d.[StatusRef]) stt
            OUTER APPLY (SELECT TOP (1) br.[Name] AS branch_name FROM dbo.[tblBranch] br WHERE br.[Code] = d.[BranchRef]) brr
            OUTER APPLY (SELECT TOP (1) rr.[Name] AS return_reason_name FROM dbo.[tblReturnChequeDReason] rr WHERE rr.[ID] = d.[ReturnReasonRef]) rrr
            OUTER APPLY (SELECT TOP (1) fund.[Name] AS fund_name FROM dbo.[tblAccFund] fund WHERE fund.[Code] = d.[FundRef]) fundd
            OUTER APPLY (SELECT TOP (1) bank.[Name] AS bank_name FROM dbo.[tblBankList] bank WHERE bank.[Code] = d.[BankIDRef]) bankk
            OUTER APPLY (SELECT TOP (1) fy.[Name] AS fiscal_year_name FROM dbo.[tblFiscalYear] fy WHERE fy.[ID] = d.[FiscalYear]) fyy
            -- «آخرین عملیات»: آخرین ردیف تاریخچه چک (tblChequeDLines)، که با خود چک فرق دارد.
            OUTER APPLY (
                SELECT TOP (1) l.[SLRef], l.[DLRef], l.[DL2Ref], l.[DL3Ref]
                FROM dbo.[tblChequeDLines] l
                WHERE l.[ChequeRef] = d.[inx]
                ORDER BY l.[lvl] DESC, l.[inx] DESC
            ) lop
            LEFT JOIN dbo.[tblSL] lop_sl ON lop_sl.[ID] = lop.[SLRef]
            LEFT JOIN dbo.[tblDL] lop_dl ON lop_dl.[ID] = lop.[DLRef]
            LEFT JOIN dbo.[tblDL] lop_dl2 ON lop_dl2.[ID] = lop.[DL2Ref]
            LEFT JOIN dbo.[tblDL] lop_dl3 ON lop_dl3.[ID] = lop.[DL3Ref]
            WHERE {where}
            ORDER BY d.[BookDate] DESC, d.[inx] DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(rows_sql, params).mappings().all()

        result: list[dict[str, Any]] = []
        for row in rows:
            status_name = row.get("status_name") or ""
            reg_date = row.get("registration_date")
            due_date = row.get("due_date")
            reg_iso = _iso(reg_date)
            due_iso = _iso(due_date)
            days = (due_date - date.today()).days if due_date else None
            branch_ref = row.get("branch_ref")
            result.append({
                "cheque_id": f"karamad:received:{row['movement_id']}",
                "document_id": row["movement_id"],
                "document_number": row.get("document_code"),
                "document_date": reg_iso,
                "document_date_jalali": _jalali(reg_date),
                "registration_date": reg_iso,
                "registration_date_jalali": _jalali(reg_date),
                "transfer_date": reg_iso,
                "transfer_date_jalali": _jalali(reg_date),
                "transfer_number": row.get("document_code"),
                "cheque_type": "received",
                "state_code": None,
                "state": status_name or "karamad_imported",
                "state_label": status_name or "ثبت‌شده در کارآمد",
                "amount": _number(row.get("amount_rial")),
                "due_date": due_iso,
                "due_date_jalali": _jalali(due_date),
                "days_until_due": days,
                "days_to_due": days,
                "serial_number": row.get("serial_number") or row.get("document_code"),
                "series": row.get("serial_number"),
                "sayad_number": row.get("sayad_number"),
                "account_number": row.get("account_number"),
                "bank_ref": row.get("bank_id_ref"),
                "bank_name": row.get("bank_name"),
                "bank_branch_name": row.get("bank_name"),
                "bank_branch_code": None,
                "counterpart_ref": row.get("dl_ref"),
                "counterpart_code": None,
                "counterpart_name": row.get("level4_name") or row.get("level5_name") or row.get("level6_name") or row.get("owner_name"),
                "description": row.get("behalf") or row.get("description"),
                "cheque_status": status_name,
                "cheque_location": row.get("fund_name") or status_name,
                "last_operation_account": row.get("last_op_sl_name") or row.get("sl_name"),
                "last_operation_level4": row.get("last_op_level4_name") or row.get("level4_name"),
                "last_operation_level5": row.get("last_op_level5_name") or row.get("level5_name"),
                "last_operation_level6": row.get("last_op_level6_name") or row.get("level6_name"),
                "assignment_date_jalali": _jalali(row.get("assignment_date")),
                "collection_date_jalali": None,
                "return_reason": row.get("return_reason_name"),
                "future_data_complete": None,
                "returns_available": None,
                "karamad_raw_status": status_name,
                "source_system": "karamad",
                "source_label": "کارآمد · Live SQL",
                "branch": row.get("branch_name") or (str(branch_ref) if branch_ref is not None else None),
                "branch_name": row.get("branch_name"),
                "owner_name": row.get("owner_name"),
                "owner_national_id": row.get("owner_national_id"),
                "is_e_cheque": bool(row.get("is_e_cheque")),
                "confirmed": row.get("confirmed"),
                "fiscal_year": row.get("fiscal_year_name"),
                "subsidiary_name": row.get("sl_name"),
                "level4_name": row.get("level4_name"),
                "level5_name": row.get("level5_name"),
                "level6_name": row.get("level6_name"),
            })

        result.sort(key=lambda item: (item.get("due_date") or "", str(item.get("cheque_id") or "")))
        return {
            "status": "success",
            "live": True,
            "source_system": "karamad",
            "rules": {
                "read_only": True,
                "source": "dbo.tblChequeD",
                "status_lookup": "dbo.tblChequeDStatus",
            },
            "cheques": result,
            "returned_count": len(result),
        }
