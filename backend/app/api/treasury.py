import logging
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.schemas.treasury import (
    FinancialQueryRequest,
    PaymentCommitmentDecisionRequest,
    TreasuryChatRequest,
    TreasuryChatResponse,
    TreasuryChatStatusResponse,
)
from app.services.bank_reconciliation_service import (
    MAX_FILE_SIZE,
    ReconciliationInputError,
    reconcile_bank_statement,
)
from app.services.reconciliation_export_service import (
    build_reconciliation_workbook,
)
from app.services.reconciliation_store import (
    ReconciliationNotFoundError,
    get_reconciliation_report,
    get_reconciliation_rows,
    get_reconciliation_summary,
    save_reconciliation_report,
)
from app.services.treasury_service import (
    get_account_balance,
    get_account_transactions,
    get_cheque_due_report,
    get_latest_issued_cheques,
    get_cheque_state_quality,
    get_received_cheque_current_state_quality,
    get_received_cheque_sql_scope,
    get_received_cheque_status_signatures,
    compare_received_open_sql_with_rahkaran_excel,
    analyze_received_cheque_official_discrepancies,
    analyze_received_cheque_official_scope_rule,
    trace_received_cheque_mapping,
    get_latest_payments,
    get_company_payment_orders,
    get_customer_b2b_remittances,
    get_customer_b2b_remittances_karamad,
    get_latest_received_cheques,
    get_open_issued_cheques,
    get_open_received_cheques,
    get_latest_receipts,
    get_received_cheques_by_status,
    get_customer_cheque_settlement,
    search_received_cheque_debtors,
    search_accounts,
)
from app.services.treasury_insight_service import (
    get_cashflow_scenarios,
    get_cheque_risk_dashboard,
    get_customer_financial_profile,
    get_daily_treasury_briefing,
    get_financial_anomaly_report,
    get_payment_plan,
    get_treasury_executive_dashboard,
)
from app.services.financial_query_service import (
    FinancialQueryError,
    ask_financial_data,
)
from app.services.treasury_chat_service import (
    TreasuryAgentConfigurationError,
    TreasuryAgentExecutionError,
    TreasuryAgentRateLimitError,
    TreasuryAgentTimeoutError,
    get_treasury_agent_status,
    run_treasury_chat,
)
from app.services.cash_bank_movement_service import CashBankMovementService
from app.services.payment_commitment_service import PaymentCommitmentService
from app.api.reconciliation_access import require_reconciliation_api_key


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/treasury",
    tags=["treasury"],
)


@router.get("/cash-bank/karamad-live/health", summary="بررسی اتصال Live SQL کارآمد برای نقد و حواله")
def karamad_live_health():
    try:
        from app.services.karamad_live_cash_draft_service import KaramadLiveCashDraftService
        service = KaramadLiveCashDraftService()
        branches = service.branches()
        return {
            "status": "success",
            "live": True,
            "source_system": "karamad",
            "database": "KDB",
            "tables": ["dbo.tblCashD", "dbo.tblCashP", "dbo.tblDraftD", "dbo.tblDraftP"],
            "available_branches": branches,
        }
    except Exception as exc:
        logger.exception("Karamad live SQL health check failed")
        raise HTTPException(status_code=500, detail=f"اتصال Live SQL کارآمد برقرار نشد: {exc}") from exc


@router.get("/cash-bank/movements", summary="ریز دریافت و پرداخت نقدی و بانکی")
def cash_bank_movements(
    period: Literal["today", "week", "month", "3m", "6m", "12m", "custom"] = Query(default="month"),
    approval_status: Literal["approved", "pending", "all"] = Query(default="approved"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    branch: str | None = Query(default=None, max_length=200),
    source: Literal["all", "rahkaran", "karamad"] = Query(default="all"),
):
    try:
        return CashBankMovementService().report(
            period=period, approval_status=approval_status,
            date_from=date_from, date_to=date_to, limit=limit, offset=offset, branch=branch, source=source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Cash/bank movement endpoint failed")
        raise HTTPException(status_code=500, detail=f"دریافت گردش نقد و حواله با خطا مواجه شد: {exc}") from exc


@router.get("/cash-bank/transfers", summary="ریز انتقال‌های داخلی بین حساب و صندوق")
def internal_cash_bank_transfers(
    period: Literal["today", "week", "month", "3m", "6m", "12m", "custom"] = Query(default="month"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    try:
        return CashBankMovementService().internal_transfers(
            period=period, date_from=date_from, date_to=date_to, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Internal transfer endpoint failed")
        raise HTTPException(status_code=500, detail=f"دریافت انتقال‌های داخلی با خطا مواجه شد: {exc}") from exc


@router.get("/cash-bank/petty-cash", summary="تنخواه‌های شرکت؛ خارج از Cash Flow")
def petty_cash_transfers(
    period: Literal["today", "week", "month", "3m", "6m", "12m", "custom"] = Query(default="month"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    try:
        return CashBankMovementService().petty_cash_transfers(period, date_from, date_to, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Petty cash endpoint failed")
        raise HTTPException(status_code=500, detail=f"دریافت تنخواه با خطا مواجه شد: {exc}") from exc


@router.get("/cash-bank/commitments", summary="تعهدات آینده و دستورهای پرداخت تعیین‌تکلیف‌نشده")
def payment_order_commitments(
    horizon_days: int = Query(default=365, ge=1, le=730),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    try:
        return PaymentCommitmentService().report(
            horizon_days=horizon_days, limit=limit, offset=offset,
        )
    except Exception as exc:
        logger.exception("Payment commitment endpoint failed")
        raise HTTPException(status_code=500, detail=f"دریافت تعهدات پرداخت با خطا مواجه شد: {exc}") from exc


@router.put(
    "/cash-bank/commitments/{installment_id}/decision",
    summary="ثبت تصمیم خزانه برای یک قسط معوق دستور پرداخت",
)
def update_payment_commitment_decision(
    installment_id: int,
    request: PaymentCommitmentDecisionRequest,
):
    try:
        return PaymentCommitmentService().set_review_decision(
            installment_id=installment_id,
            payment_order_id=request.payment_order_id,
            decision=request.decision,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Payment commitment decision update failed")
        raise HTTPException(
            status_code=500,
            detail=f"ثبت تعیین‌تکلیف تعهد پرداخت با خطا مواجه شد: {exc}",
        ) from exc


@router.post(
    "/intelligence/ask",
    summary="پرسش آزاد و امن از داده‌های مالی",
)
def treasury_financial_intelligence(request: FinancialQueryRequest):
    try:
        return ask_financial_data(request.question)
    except FinancialQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Safe financial query failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="تحلیل آزاد اطلاعات مالی با خطا مواجه شد.",
        ) from exc


@router.get(
    "/forecast/cashflow",
    summary="سناریوهای توضیح‌پذیر جریان نقد",
)
def treasury_cashflow_forecast(
    days: int = Query(default=30, ge=1, le=180),
    opening_cash: str | None = Query(default=None),
    history_days: int = Query(default=90, ge=30, le=730),
):
    try:
        return get_cashflow_scenarios(
            days=days,
            opening_cash=opening_cash,
            history_days=history_days,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Cashflow scenario forecast failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت سناریوی جریان نقد با خطا مواجه شد.",
        ) from exc


async def _process_reconciliation_upload(
    file: UploadFile,
    **options,
):
    """Run reconciliation and keep API error handling identical for all UIs."""

    content = await file.read(MAX_FILE_SIZE + 1)
    try:
        report = reconcile_bank_statement(
            content=content,
            filename=file.filename or "bank_statement.xlsx",
            **options,
        )
        return save_reconciliation_report(report)
    except ReconciliationInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Bank reconciliation endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="مغایرت‌گیری صورتحساب بانک با خطا مواجه شد.",
        ) from exc
    finally:
        await file.close()


@router.get("/accounts/search")
def search_treasury_accounts(
    name: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
):
    return {
        "status": "success",
        "accounts": search_accounts(name, limit=limit),
    }


@router.get("/accounts/{account_id}/balance")
def treasury_account_balance(account_id: int):
    return get_account_balance(account_id=account_id)


@router.get("/accounts/{account_id}/transactions")
def treasury_account_transactions(
    account_id: int,
    limit: int = Query(default=10, ge=1, le=1000),
):
    return get_account_transactions(
        account_id=account_id,
        limit=limit,
    )


@router.get("/receipts/latest")
def latest_treasury_receipts(
    limit: int = Query(default=10, ge=1, le=1000),
):
    try:
        return get_latest_receipts(limit=limit)
    except Exception as exc:
        logger.exception("Latest treasury receipts endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="دریافت آخرین اسناد دریافت خزانه با خطا مواجه شد.",
        ) from exc


@router.get("/payment-orders/company", summary="حواله‌های پرداختی شرکت در راهکاران")
def company_payment_orders(limit: int = Query(default=1000, ge=1, le=5000)):
    try:
        return get_company_payment_orders(limit=limit)
    except Exception as exc:
        logger.exception("Company payment orders endpoint failed")
        raise HTTPException(status_code=500, detail="دریافت حواله‌های پرداختی شرکت از راهکاران با خطا مواجه شد.") from exc


@router.get("/customer-b2b-remittances", summary="حواله‌ها و واریزهای B2B مشتریان")
def customer_b2b_remittances(
    limit: int = Query(default=20000, ge=1, le=20000),
    counterpart_ref: int | None = Query(default=None, ge=1),
    source: str = Query(default="rahkaran", pattern="^(rahkaran|karamad|all)$"),
):
    try:
        if source == "rahkaran":
            return get_customer_b2b_remittances(limit=limit, counterpart_ref=counterpart_ref)
        if source == "karamad":
            return get_customer_b2b_remittances_karamad(limit=limit, counterpart_ref=counterpart_ref)
        rahkaran = get_customer_b2b_remittances(limit=limit, counterpart_ref=counterpart_ref)
        karamad = get_customer_b2b_remittances_karamad(limit=limit, counterpart_ref=counterpart_ref)
        merged_rows = rahkaran.get("rows", []) + karamad.get("rows", [])
        merged_rows.sort(key=lambda x: (x.get("deposit_date_jalali") or "", str(x.get("receipt_deposit_id") or "")), reverse=True)
        return {
            "status": "success", "source": "Rahkaran + Karamad", "rows": merged_rows,
            "summary": {
                key: (rahkaran["summary"].get(key, 0) or 0) + (karamad["summary"].get(key, 0) or 0)
                for key in rahkaran["summary"]
            },
        }
    except Exception as exc:
        logger.exception("Customer B2B remittances endpoint failed")
        raise HTTPException(status_code=500, detail="دریافت حواله‌های B2B مشتریان با خطا مواجه شد.") from exc


@router.get("/payments/latest")
def latest_treasury_payments(
    limit: int = Query(default=10, ge=1, le=100),
):
    try:
        return get_latest_payments(limit=limit)
    except Exception as exc:
        logger.exception("Latest treasury payments endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="دریافت آخرین اسناد پرداخت خزانه با خطا مواجه شد.",
        ) from exc


@router.get("/cheques/received/latest")
def latest_received_treasury_cheques(
    limit: int = Query(default=10, ge=1, le=100),
):
    try:
        return get_latest_received_cheques(limit=limit)
    except Exception as exc:
        logger.exception("Latest received treasury cheques endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"دریافت آخرین چک‌های دریافتی با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/received/open")
def open_received_treasury_cheques(
    period: Literal["all", "overdue", "1m", "3m", "6m", "12m"] = Query(default="all"),
):
    """همه چک‌های دریافتی باز غیرتضمینی، بدون محدودیت ۱۰۰ رکورد."""
    try:
        return get_open_received_cheques(period=period)
    except Exception as exc:
        logger.exception("Open received treasury cheques endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"دریافت چک‌های باز غیرتضمینی با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/issued/latest")
def latest_issued_treasury_cheques(
    limit: int = Query(default=10, ge=1, le=1000),
    upcoming_only: bool = Query(default=False),
    sort_by_due: bool = Query(default=False),
):
    try:
        return get_latest_issued_cheques(
            limit=limit,
            upcoming_only=upcoming_only,
            sort_by_due=sort_by_due,
        )
    except Exception as exc:
        logger.exception("Latest issued treasury cheques endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"دریافت آخرین چک‌های پرداختی با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/issued/open", summary="چک‌های پرداختی باز و فعال")
def open_issued_treasury_cheques():
    """فقط State=11؛ پرداخت‌شده، تضمینی و سهامدار حذف می‌شوند."""
    try:
        return get_open_issued_cheques()
    except Exception as exc:
        logger.exception("Open issued treasury cheques endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"دریافت چک‌های پرداختی باز با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/received/sql-scope", summary="کنترل دامنه زمانی SQL چک‌های دریافتی راهکاران")
def treasury_received_cheque_sql_scope():
    try:
        return get_received_cheque_sql_scope()
    except Exception as exc:
        logger.exception("Received cheque SQL scope endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"کنترل دامنه SQL چک‌های دریافتی با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/received/current-state-quality", summary="کنترل وضعیت فعلی چک‌های دریافتی راهکاران")
def treasury_received_cheque_current_state_quality():
    try:
        return get_received_cheque_current_state_quality()
    except Exception as exc:
        logger.exception("Received cheque current-state quality endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"کنترل وضعیت فعلی چک‌های دریافتی با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/received/status-signatures", summary="ممیزی SQL برای بازسازی وضعیت فعلی راهکاران")
def treasury_received_cheque_status_signatures():
    try:
        return get_received_cheque_status_signatures()
    except Exception as exc:
        logger.exception("Received cheque status-signatures endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ممیزی وضعیت فعلی چک‌های دریافتی با خطا مواجه شد: {exc}",
        ) from exc




@router.post("/cheques/received/compare-official-excel", summary="مقایسه کاندیدهای SQL با گزارش رسمی راهکاران")
async def compare_received_cheques_with_official_excel(file: UploadFile = File(..., description="Excel رسمی ListData راهکاران")):
    try:
        content = await file.read()
        if not content: raise HTTPException(status_code=400, detail="فایل خالی است")
        return compare_received_open_sql_with_rahkaran_excel(content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Received cheque official Excel comparison failed")
        raise HTTPException(status_code=500, detail=f"مقایسه SQL و Excel راهکاران با خطا مواجه شد: {exc}") from exc


@router.post("/cheques/received/analyze-official-difference", summary="ردیابی کامل اختلاف SQL با وضعیت فعلی گزارش رسمی راهکاران")
async def analyze_received_cheque_official_difference(file: UploadFile = File(..., description="Excel رسمی ListData راهکاران")):
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="فایل خالی است")
        return analyze_received_cheque_official_discrepancies(content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Received cheque discrepancy-history analysis failed")
        raise HTTPException(status_code=500, detail=f"ردیابی اختلاف SQL و Excel راهکاران با خطا مواجه شد: {exc}") from exc


@router.get("/cheques/status-quality", summary="نرخ قطعی وصول و کنترل وضعیت چک‌های صادرشده")
def treasury_cheque_state_quality():
    try:
        return get_cheque_state_quality()
    except Exception as exc:
        logger.exception("Cheque state quality endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"کنترل وضعیت قطعی چک‌ها با خطا مواجه شد: {exc}",
        ) from exc


@router.get("/cheques/due")
def treasury_cheque_due_report(
    cheque_type: str = Query(pattern="^(received|issued)$"),
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description=(
            "بازه آینده؛ اگر overdue=true باشد، بازه گذشته برای معوق‌ها"
        ),
    ),
    overdue: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return get_cheque_due_report(
            cheque_type=cheque_type,
            days=days,
            overdue=overdue,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("Treasury cheque due report endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="گزارش سررسید چک‌ها با خطا مواجه شد.",
        ) from exc


@router.get("/cheques/received/status")
def treasury_received_cheque_status_report(
    cheque_status: str = Query(pattern="^(collected|protested)$"),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return get_received_cheques_by_status(
            cheque_status=cheque_status,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("Received cheque status report endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="گزارش وضعیت چک‌های دریافتی با خطا مواجه شد.",
        ) from exc


@router.get("/cheques/received/debtors/search")
def treasury_received_cheque_debtors_search(
    name: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
):
    try:
        return search_received_cheque_debtors(name=name, limit=limit)
    except Exception as exc:
        logger.exception("Received cheque debtor search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="جست‌وجوی بدهکاران چک‌های دریافتی با خطا مواجه شد.",
        ) from exc


@router.get("/cheques/received/settlement")
def treasury_customer_cheque_settlement(
    counterpart_ref: int = Query(ge=1),
    opening_debt: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
):
    try:
        return get_customer_cheque_settlement(
            counterpart_ref=counterpart_ref,
            opening_debt=opening_debt,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Customer cheque settlement report failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="گزارش تسویه چک‌های مشتری با خطا مواجه شد.",
        ) from exc


@router.get(
    "/overview/daily",
    summary="گزارش هوشمند روزانه خزانه",
)
def treasury_daily_briefing(
    due_days: int = Query(default=7, ge=1, le=60),
):
    try:
        return get_daily_treasury_briefing(due_days=due_days)
    except Exception as exc:
        logger.exception("Daily treasury briefing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت گزارش روزانه خزانه با خطا مواجه شد.",
        ) from exc


@router.get(
    "/risk/cheques",
    summary="داشبورد ریسک و سررسید چک‌ها",
)
def treasury_cheque_risk_dashboard(
    days: int = Query(default=60, ge=1, le=365),
):
    try:
        return get_cheque_risk_dashboard(days=days)
    except Exception as exc:
        logger.exception("Cheque risk dashboard failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت داشبورد ریسک چک‌ها با خطا مواجه شد.",
        ) from exc


@router.get(
    "/controls/anomalies",
    summary="کنترل موارد مالی غیرعادی",
)
def treasury_financial_anomaly_report(
    days: int = Query(default=30, ge=1, le=365),
    large_amount_threshold: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=10, le=5000),
):
    try:
        return get_financial_anomaly_report(
            days=days,
            large_amount_threshold=large_amount_threshold,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Financial anomaly report failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="کنترل موارد مالی غیرعادی با خطا مواجه شد.",
        ) from exc


@router.get(
    "/planning/payments",
    summary="برنامه پیشنهادی پرداخت چک‌ها",
)
def treasury_payment_plan(
    days: int = Query(default=30, ge=1, le=365),
    available_cash: str | None = Query(
        default=None,
        description="اختیاری؛ موجودی قابل تخصیص برای محاسبه کسری منابع",
    ),
):
    try:
        return get_payment_plan(days=days, available_cash=available_cash)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Payment planning report failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت برنامه پیشنهادی پرداخت با خطا مواجه شد.",
        ) from exc


@router.get(
    "/customers/{counterpart_ref}/profile",
    summary="پرونده مالی و وصول مشتری",
)
def treasury_customer_financial_profile(
    counterpart_ref: int,
    days: int = Query(default=90, ge=1, le=730),
    transaction_limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return get_customer_financial_profile(
            counterpart_ref=counterpart_ref,
            days=days,
            transaction_limit=transaction_limit,
        )
    except Exception as exc:
        logger.exception("Customer financial profile failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت پرونده مالی مشتری با خطا مواجه شد.",
        ) from exc


@router.get(
    "/dashboard/executive",
    summary="داشبورد مدیریتی جامع خزانه",
)
def treasury_executive_dashboard(
    days: int = Query(default=30, ge=1, le=365),
    available_cash: str | None = Query(default=None),
):
    try:
        return get_treasury_executive_dashboard(
            days=days,
            available_cash=available_cash,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Executive treasury dashboard failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت داشبورد مدیریتی خزانه با خطا مواجه شد.",
        ) from exc


@router.post(
    "/reconciliation/auto-upload",
    summary="مغایرت‌گیری خودکار صورتحساب بانک",
    description=(
        "Endpoint عملیاتی کارکنان خزانه؛ فقط فایل صورتحساب ارسال می‌شود. "
        "بانک، حساب، شبا، Sheet، ردیف عنوان و ستون‌ها خودکار تشخیص داده می‌شوند."
    ),
    dependencies=[Depends(require_reconciliation_api_key)],
)
async def auto_upload_bank_statement_for_reconciliation(
    file: UploadFile = File(
        ...,
        description="فایل صورتحساب بانک با فرمت XLS، XLSX، CSV، PDF یا HTML",
    ),
):
    return await _process_reconciliation_upload(
        file,
        bank_account_id=None,
        tolerance_days=2,
        sheet_name=None,
        header_row=0,
        date_column=None,
        deposit_column=None,
        withdrawal_column=None,
        description_column=None,
        reference_column=None,
        balance_column=None,
        payer_column=None,
        origin_account_column=None,
    )


@router.post(
    "/reconciliation/upload",
    summary="مغایرت‌گیری پیشرفته صورتحساب بانک",
    description="تنظیمات دستی؛ فقط برای پشتیبانی فنی و قالب‌های ناشناخته.",
    deprecated=True,
    dependencies=[Depends(require_reconciliation_api_key)],
)
async def upload_bank_statement_for_reconciliation(
    file: UploadFile = File(...),
    bank_account_id: int | None = Form(
        default=None,
        description=(
            "اختیاری؛ اگر خالی باشد از شماره حساب/شبای فایل تشخیص داده می‌شود. "
            "برای بانک سپه فراز مقدار تأییدشده 82 است."
        ),
    ),
    tolerance_days: int = Form(default=2, ge=0, le=7),
    sheet_name: str | None = Form(default=None),
    header_row: int = Form(
        default=0,
        ge=0,
        le=100,
        description="۰ یعنی تشخیص خودکار ردیف عنوان",
    ),
    date_column: str | None = Form(default=None),
    deposit_column: str | None = Form(default=None),
    withdrawal_column: str | None = Form(default=None),
    description_column: str | None = Form(default=None),
    reference_column: str | None = Form(default=None),
    balance_column: str | None = Form(default=None),
    payer_column: str | None = Form(default=None),
    origin_account_column: str | None = Form(default=None),
):
    return await _process_reconciliation_upload(
        file,
        bank_account_id=bank_account_id or None,
        tolerance_days=tolerance_days,
        sheet_name=sheet_name,
        header_row=header_row,
        date_column=date_column,
        deposit_column=deposit_column,
        withdrawal_column=withdrawal_column,
        description_column=description_column,
        reference_column=reference_column,
        balance_column=balance_column,
        payer_column=payer_column,
        origin_account_column=origin_account_column,
    )


@router.get(
    "/reconciliation/{reconciliation_id}",
    dependencies=[Depends(require_reconciliation_api_key)],
)
def treasury_reconciliation_report(reconciliation_id: str):
    try:
        return get_reconciliation_report(reconciliation_id)
    except ReconciliationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/reconciliation/{reconciliation_id}/summary",
    dependencies=[Depends(require_reconciliation_api_key)],
)
def treasury_reconciliation_summary(reconciliation_id: str):
    try:
        return get_reconciliation_summary(reconciliation_id)
    except ReconciliationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/reconciliation/{reconciliation_id}/rows",
    dependencies=[Depends(require_reconciliation_api_key)],
)
def treasury_reconciliation_rows(
    reconciliation_id: str,
    business_status: Literal[
        "posted",
        "reversed",
        "internal_transfer",
        "needs_review",
        "unposted",
    ] = Query(
        default="needs_review",
        pattern="^(posted|reversed|internal_transfer|needs_review|unposted)$",
    ),
    limit: int = Query(default=20, ge=1, le=100),
):
    try:
        return get_reconciliation_rows(
            reconciliation_id,
            business_status,
            limit=limit,
        )
    except ReconciliationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/reconciliation/{reconciliation_id}/export.xlsx",
    dependencies=[Depends(require_reconciliation_api_key)],
)
def treasury_reconciliation_excel(reconciliation_id: str):
    try:
        report = get_reconciliation_report(reconciliation_id)
        workbook = build_reconciliation_workbook(report)
    except ReconciliationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Reconciliation Excel export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ساخت فایل اکسل مغایرت‌گیری با خطا مواجه شد.",
        ) from exc

    account_last_four = str(
        (report.get("bank_account") or {}).get("account_last_four") or "account"
    )
    filename = (
        f"treasury-reconciliation-{account_last_four}-"
        f"{reconciliation_id}.xlsx"
    )
    encoded_filename = quote(filename)
    return StreamingResponse(
        workbook,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}; "
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.post(
    "/chat",
    response_model=TreasuryChatResponse,
)
async def treasury_chat(request: TreasuryChatRequest):
    try:
        result = await run_treasury_chat(
            request.message,
            session_id=request.session_id,
        )
    except TreasuryAgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except TreasuryAgentRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except TreasuryAgentTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except TreasuryAgentExecutionError as exc:
        logger.exception("Treasury chat endpoint failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unhandled treasury chat endpoint error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "خطای داخلی کنترل‌نشده رخ داد "
                f"({type(exc).__name__})؛ جزئیات در ترمینال uvicorn ثبت شد."
            ),
        ) from exc

    return TreasuryChatResponse(
        status="success",
        answer=result.answer,
        session_id=result.session_id,
    )


@router.get(
    "/chat/status",
    response_model=TreasuryChatStatusResponse,
)
def treasury_chat_status():
    return get_treasury_agent_status()


@router.post("/cheques/received/analyze-official-scope-rule", summary="کشف Rule دامنه گزارش رسمی چک‌های دریافتی راهکاران")
async def analyze_received_cheque_scope_rule(file: UploadFile = File(..., description="Excel رسمی ListData راهکاران - فقط کنترل")):
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="فایل خالی است")
        return analyze_received_cheque_official_scope_rule(content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Received cheque official scope-rule analysis failed")
        raise HTTPException(status_code=500, detail=f"کشف Rule دامنه گزارش رسمی راهکاران با خطا مواجه شد: {exc}") from exc


@router.get("/cheques/received/trace", summary="ردیابی کامل یک چک دریافتی از SQL تا API")
def trace_received_cheque(
    cheque_id: int | None = Query(default=None),
    serial_number: str | None = Query(default=None),
    sayad_number: str | None = Query(default=None),
    document_number: str | None = Query(default=None),
):
    try:
        return trace_received_cheque_mapping(
            cheque_id=cheque_id, serial_number=serial_number,
            sayad_number=sayad_number, document_number=document_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Received cheque mapping trace failed")
        raise HTTPException(status_code=500, detail=f"ردیابی چک با خطا مواجه شد: {exc}") from exc
