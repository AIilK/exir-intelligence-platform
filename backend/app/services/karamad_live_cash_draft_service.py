from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import text

from app.database.karamad_sqlserver import get_karamad_sqlserver_engine


Direction = Literal["inflow", "outflow"]

TRANSFER_MARKERS = (
    "بابت انتقال", "جهت انتقال", "انتقال از", "انتقال به", "انتقال بین بانکی",
    "انتقال بین‌بانکی", "انتقال بانک به بانک", "انتقال بانک‌به‌بانک", "بانک به بانک",
    "بانک‌به‌بانک", "صندوق به بانک", "بانک به صندوق", "تسویه صندوق نقدی انتقال به بانک",
    "انتقال وجه نقد به حساب", "حواله شرکتی", "جابجایی بین حساب", "جابه جایی بین حساب",
    "جابه‌جایی بین حساب",
)
PETTY_MARKERS = ("تنخواه", "علی الحساب تنخواه", "علی‌الحساب تنخواه")


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


def _classify(behalf: Any, description: Any) -> tuple[str, str]:
    source = f"{behalf or ''} {description or ''}".replace("\u200c", " ").casefold()
    if any(marker.casefold() in source for marker in PETTY_MARKERS):
        return "petty_cash", "شرح شامل نشانه تنخواه است"
    if any(marker.casefold() in source for marker in TRANSFER_MARKERS):
        return "company_bank_transfer", "شرح نشان‌دهنده انتقال داخلی/بین حساب است"
    return "operational", "گردش عملیاتی نقد/حواله"


class KaramadLiveCashDraftService:
    """Live read-only source for Karamad cash and draft/remittance tables."""

    def __init__(self, engine=None):
        self.engine = engine or get_karamad_sqlserver_engine()

    @staticmethod
    def _queries() -> str:
        # Karamad live cash/remittance movement source.
        # IMPORTANT:
        # - Code is not numeric consistently across the four tables
        #   (tblDraftD.Code is nvarchar), so normalize it to nvarchar.
        # - Some fields do not exist in every table; use explicitly typed NULLs
        #   so SQL Server cannot infer an incompatible UNION type.
        # V156: cash tables carry FundRef (cashbox), draft tables carry BankRef
        # (bank account). Both columns are now always present in the UNION,
        # typed explicitly, so downstream name-resolution JOINs can rely on
        # fund_ref / bank_ref regardless of which of the four tables a row
        # came from. Previously bank_ref was silently dropped for both draft
        # tables (NULL was written where BankRef belongs) — this is fixed.
        return """
            SELECT
                N'cash_receipt' AS movement_type,
                N'inflow' AS direction,
                N'cash' AS channel,
                d.[inx] AS movement_id,
                CAST(d.[Code] AS nvarchar(100)) AS document_number,
                d.[BookDate] AS document_date,
                d.[PriceN] AS amount_rial,
                d.[BranchRef] AS branch_ref,
                d.[Behalf] AS behalf,
                d.[Description] AS description,
                d.[SLRef] AS sl_ref,
                d.[DLRef] AS dl_ref,
                d.[DL2Ref] AS dl2_ref,
                d.[DL3Ref] AS dl3_ref,
                d.[FundRef] AS fund_ref,
                CAST(NULL AS int) AS bank_ref,
                d.[FactorRef] AS factor_ref,
                d.[VoucherRef] AS voucher_ref,
                d.[PayoffMultiRef] AS payoff_multi_ref,
                d.[ReturnChequeRef] AS return_cheque_ref,
                d.[CustomerDebtRef] AS customer_debt_ref,
                d.[Confirmed] AS confirmed
            FROM dbo.[tblCashD] d

            UNION ALL

            SELECT
                N'cash_payment',
                N'outflow',
                N'cash',
                d.[inx],
                CAST(d.[Code] AS nvarchar(100)),
                d.[BookDate],
                d.[PriceN],
                d.[BranchRef],
                d.[Behalf],
                d.[Description],
                d.[SLRef],
                d.[DLRef],
                d.[DL2Ref],
                d.[DL3Ref],
                d.[FundRef],
                CAST(NULL AS int),
                d.[FactorRef],
                d.[VoucherRef],
                CAST(NULL AS int),
                CAST(NULL AS int),
                CAST(NULL AS int),
                CAST(NULL AS bit)
            FROM dbo.[tblCashP] d

            UNION ALL

            SELECT
                N'bank_receipt',
                N'inflow',
                N'draft',
                d.[inx],
                CAST(d.[Code] AS nvarchar(100)),
                d.[BookDate],
                d.[Price],
                d.[BranchRef],
                d.[Behalf],
                d.[Description],
                d.[SLRef],
                d.[DLRef],
                d.[DL2Ref],
                d.[DL3Ref],
                CAST(NULL AS int),
                d.[BankRef],
                d.[FactorRef],
                d.[VoucherRef],
                d.[PayoffMultiRef],
                d.[ReturnChequeRef],
                d.[CustomerDebtRef],
                d.[Confirmed]
            FROM dbo.[tblDraftD] d

            UNION ALL

            SELECT
                N'bank_payment',
                N'outflow',
                N'draft',
                d.[inx],
                CAST(d.[Code] AS nvarchar(100)),
                d.[BookDate],
                d.[Price],
                d.[BranchRef],
                d.[Behalf],
                d.[Description],
                d.[SLRef],
                d.[DLRef],
                d.[DL2Ref],
                d.[DL3Ref],
                CAST(NULL AS int),
                d.[BankRef],
                d.[FactorRef],
                d.[VoucherRef],
                CAST(NULL AS int),
                CAST(NULL AS int),
                CAST(NULL AS int),
                CAST(NULL AS bit)
            FROM dbo.[tblDraftP] d
        """

    def branches(self) -> list[str]:
        sql = text("""
            SELECT DISTINCT CAST([BranchRef] AS varchar(50)) AS branch
            FROM (
                SELECT [BranchRef] FROM dbo.[tblCashD]
                UNION ALL SELECT [BranchRef] FROM dbo.[tblCashP]
                UNION ALL SELECT [BranchRef] FROM dbo.[tblDraftD]
                UNION ALL SELECT [BranchRef] FROM dbo.[tblDraftP]
            ) x
            WHERE [BranchRef] IS NOT NULL
            ORDER BY branch
        """)
        with self.engine.connect() as conn:
            return [str(r[0]) for r in conn.execute(sql).all()]

    def report(
        self,
        start: date,
        end: date,
        limit: int = 500,
        offset: int = 0,
        branch: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200000))
        offset = max(0, int(offset))
        where = "document_date >= :date_from AND document_date < :date_to_exclusive"
        params: dict[str, Any] = {
            "date_from": start,
            "date_to_exclusive": end + timedelta(days=1),
            "limit": limit,
            "offset": offset,
        }
        if branch:
            where += " AND CAST(branch_ref AS varchar(50)) = :branch"
            params["branch"] = branch

        union = self._queries()
        # V156: resolve human-readable names for every code/ref column.
        # tblSL = "معین" (SLRef); tblDL = تفصیلی سطح ۴/۵/۶ (DLRef/DL2Ref/DL3Ref,
        # same lookup table for all three levels); tblBranch = شعبه;
        # tblAccFund = صندوق (cash tables only); tblAccBank = بانک (draft
        # tables only). All LEFT JOINs so a missing code never drops the row.
        rows_sql = text(f"""
            WITH movements AS ({union})
            SELECT
                m.*,
                sl.[Name]   AS sl_name,
                dl.[Name]   AS level4_name,
                dl.[ClassRef] AS dl_class_ref,
                dl2.[Name]  AS level5_name,
                dl3.[Name]  AS level6_name,
                brr.[branch_name],
                fundd.[fund_name],
                bankk.[bank_name]
            FROM movements m
            -- V158: SLRef/DLRef point at tblSL.ID / tblDL.ID (their internal primary
            -- key), NOT tblSL.Code / tblDL.Code (a separate display code). Confirmed
            -- empirically: joining on Code returned NULL names for known-good rows.
            LEFT JOIN dbo.[tblSL] sl ON sl.[ID] = m.sl_ref
            LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = m.dl_ref
            LEFT JOIN dbo.[tblDL] dl2 ON dl2.[ID] = m.dl2_ref
            LEFT JOIN dbo.[tblDL] dl3 ON dl3.[ID] = m.dl3_ref
            -- V159: tblBranch/tblAccFund/tblAccBank are keyed by .Code, and Karamad's
            -- own data has proven duplicate Codes in tblAccFund (confirmed on the
            -- received-cheque table: one FundRef matched two fund rows and silently
            -- duplicated a row). OUTER APPLY TOP(1) makes every one of these immune
            -- to that, guaranteeing exactly one output row per movement.
            OUTER APPLY (SELECT TOP (1) br.[Name] AS branch_name FROM dbo.[tblBranch] br WHERE br.[Code] = m.branch_ref) brr
            OUTER APPLY (SELECT TOP (1) fund.[Name] AS fund_name FROM dbo.[tblAccFund] fund WHERE fund.[Code] = m.fund_ref) fundd
            OUTER APPLY (SELECT TOP (1) bank.[Name] AS bank_name FROM dbo.[tblAccBank] bank WHERE bank.[Code] = m.bank_ref) bankk
            WHERE {where}
            ORDER BY document_date DESC, movement_id DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)
        count_sql = text(f"""
            WITH movements AS ({union})
            SELECT COUNT_BIG(*) AS total_count,
                   COALESCE(SUM(CASE WHEN direction='inflow' THEN amount_rial ELSE 0 END),0) AS inflow_rial,
                   COALESCE(SUM(CASE WHEN direction='outflow' THEN amount_rial ELSE 0 END),0) AS outflow_rial
            FROM movements
            WHERE {where}
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(rows_sql, params).mappings().all()
            summary = conn.execute(count_sql, params).mappings().one()

        payloads: list[dict[str, Any]] = []
        for row in rows:
            classification, reason = _classify(row.get("behalf"), row.get("description"))
            payloads.append({
                "movement_type": row["movement_type"],
                "direction": row["direction"],
                "channel": row["channel"],
                "movement_id": row["movement_id"],
                "document_id": row["movement_id"],
                "document_number": row["document_number"],
                "document_date": _iso(row["document_date"]),
                "document_date_jalali": _jalali(row["document_date"]),
                "amount_rial": _number(row["amount_rial"]),
                "branch": row.get("branch_name") or (str(row["branch_ref"]) if row.get("branch_ref") is not None else None),
                "branch_ref": row.get("branch_ref"),
                "branch_name": row.get("branch_name"),
                "behalf": row.get("behalf"),
                "purpose": row.get("behalf"),
                "description": row.get("description"),
                "sl_ref": row.get("sl_ref"),
                "sl_name": row.get("sl_name"),
                "dl_ref": row.get("dl_ref"),
                "dl2_ref": row.get("dl2_ref"),
                "dl3_ref": row.get("dl3_ref"),
                "level4_name": row.get("level4_name"),
                "dl_class_ref": row.get("dl_class_ref"),
                "level5_name": row.get("level5_name"),
                "level6_name": row.get("level6_name"),
                "counterpart_name": row.get("level4_name") or row.get("level5_name") or row.get("level6_name"),
                "fund_ref": row.get("fund_ref"),
                "fund_name": row.get("fund_name"),
                "bank_ref": row.get("bank_ref"),
                # A single "bank" column serves both channels: the bank account
                # name for حواله rows, the cashbox name for نقد rows.
                "bank_name": row.get("bank_name") or row.get("fund_name"),
                "bank": row.get("bank_name") or row.get("fund_name"),
                "factor_ref": row.get("factor_ref"),
                "voucher_ref": row.get("voucher_ref"),
                "payoff_multi_ref": row.get("payoff_multi_ref"),
                "return_cheque_ref": row.get("return_cheque_ref"),
                "customer_debt_ref": row.get("customer_debt_ref"),
                "confirmed": row.get("confirmed"),
                "classification": classification,
                "classification_reason": reason,
                "source_system": "karamad",
                "source_label": "کارآمد · Live SQL",
            })

        total_count = int(summary["total_count"] or 0)
        operational = [r for r in payloads if r["classification"] == "operational"]
        transfers = [r for r in payloads if r["classification"] == "company_bank_transfer"]
        petty = [r for r in payloads if r["classification"] == "petty_cash"]

        return {
            "status": "success",
            "live": True,
            "source_system": "karamad",
            "filters": {"date_from": start.isoformat(), "date_to": end.isoformat(), "branch": branch},
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned_count": len(payloads),
                "total_count": total_count,
                "has_more": offset + len(payloads) < total_count,
            },
            "summary": {
                "total_count": total_count,
                "inflow_rial": _number(summary["inflow_rial"]),
                "outflow_rial": _number(summary["outflow_rial"]),
                "bank_receipt_rial": _number(sum(float(r["amount_rial"] or 0) for r in operational if r["movement_type"] == "bank_receipt")),
                "bank_payment_total_rial": _number(sum(float(r["amount_rial"] or 0) for r in payloads if r["movement_type"] == "bank_payment")),
                "bank_payment_excluding_transfer_rial": _number(sum(float(r["amount_rial"] or 0) for r in operational if r["movement_type"] == "bank_payment")),
                "cash_receipt_rial": _number(sum(float(r["amount_rial"] or 0) for r in operational if r["movement_type"] == "cash_receipt")),
                "cash_payment_rial": _number(sum(float(r["amount_rial"] or 0) for r in operational if r["movement_type"] == "cash_payment")),
                "company_bank_transfer_rial": _number(sum(float(r["amount_rial"] or 0) for r in transfers)),
                "petty_cash_rial": _number(sum(float(r["amount_rial"] or 0) for r in petty)),
                "available_branches": self.branches(),
            },
            "movements": payloads,
            "company_bank_transfers": transfers,
            "petty_cash_movements": petty,
            "rules": {
                "read_only": True,
                "source": "dbo.tblCashD / dbo.tblCashP / dbo.tblDraftD / dbo.tblDraftP",
                "transfer_excluded_from_operational_cashflow": True,
                "petty_cash_excluded_from_operational_cashflow": True,
            },
        }
