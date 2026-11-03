from typing import Literal

from app.services.treasury_service import (
    get_account_balance,
    get_account_transactions,
    get_cheque_due_report,
    get_latest_issued_cheques,
    get_latest_payments,
    get_latest_received_cheques,
    get_latest_receipts,
    get_received_cheques_by_status,
    get_customer_cheque_settlement,
    get_receivable_report,
    search_accounts,
    search_received_cheque_debtors,
)
from app.services.financial_calculation_service import (
    calculate_aggregate,
    calculate_percentage,
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
from app.services.financial_query_service import ask_financial_data
from app.services.finance_prediction_service import FinancePredictionService
from app.services.reconciliation_store import (
    ReconciliationNotFoundError,
    get_reconciliation_rows,
    get_reconciliation_summary,
)


def financial_percentage_tool(
    part: str,
    total: str,
    precision: int = 2,
):
    """درصد دقیق یک مبلغ از مبلغ کل؛ اعداد را بدون تغییر از داده ابزار قبلی بگیر."""

    return calculate_percentage(part, total, precision=precision)


def financial_aggregate_tool(
    operation: Literal["sum", "average", "difference"],
    values: list[str],
    precision: int = 2,
):
    """محاسبه قطعی sum، average یا difference روی فهرست مبالغ مالی."""

    return calculate_aggregate(operation, values, precision=precision)


def search_accounts_tool(account_name: str, limit: int = 10):
    """جست‌وجوی حساب خزانه با بخشی از نام و برگرداندن account_id و ارز."""

    return {
        "status": "success",
        "accounts": search_accounts(account_name, limit=limit),
    }


def account_balance_tool(
    account_name: str | None = None,
    account_id: int | None = None,
):
    """
    دریافت مانده یک حساب از ERP

    مثال:
    آبرام
    آرسن
    شرکت الامرای
    """

    result = get_account_balance(
        account_name=account_name,
        account_id=account_id,
    )

    return result



def account_transactions_tool(
    account_name: str | None = None,
    limit: int = 10,
    account_id: int | None = None,
):
    """
    دریافت آخرین گردش حساب یک حساب
    """

    result = get_account_transactions(
        account_name=account_name,
        limit=limit,
        account_id=account_id,
    )

    return result



def receivable_report_tool():
    """
    گزارش کلی دریافتنی ها
    """

    result = get_receivable_report()

    return result


def latest_receipts_tool(limit: int = 10):
    """دریافت آخرین اسناد دریافت تأییدشده خزانه."""

    return get_latest_receipts(limit=limit)


def latest_payments_tool(limit: int = 10):
    """دریافت آخرین اسناد پرداخت تأییدشده خزانه."""

    return get_latest_payments(limit=limit)


def latest_received_cheques_tool(limit: int = 10):
    """دریافت آخرین چک‌های دریافتی ثبت‌شده در اسناد تأییدشده."""

    return get_latest_received_cheques(limit=limit)


def latest_issued_cheques_tool(limit: int = 10):
    """دریافت آخرین چک‌های پرداختی ثبت‌شده در اسناد تأییدشده."""

    return get_latest_issued_cheques(limit=limit)


def cheque_due_report_tool(
    cheque_type: str,
    days: int = 30,
    overdue: bool = False,
    limit: int = 100,
):
    """گزارش چک‌های فعال سررسیدشونده یا سررسیدگذشته."""

    return get_cheque_due_report(
        cheque_type=cheque_type,
        days=days,
        overdue=overdue,
        limit=limit,
    )


def received_cheque_status_report_tool(
    cheque_status: str,
    limit: int = 100,
):
    """گزارش چک‌های دریافتی وصول‌شده یا واخواست‌شده."""

    return get_received_cheques_by_status(
        cheque_status=cheque_status,
        limit=limit,
    )


def search_received_cheque_debtors_tool(
    name: str,
    limit: int = 10,
):
    """جست‌وجوی بدهکار/تحویل‌دهنده چک مستقل از نام صاحب چک."""

    return search_received_cheque_debtors(name=name, limit=limit)


def customer_cheque_settlement_tool(
    counterpart_ref: int,
    opening_debt: str | None = None,
    limit: int = 500,
):
    """تسویه چندچکی مشتری، شامل چک‌های شخص ثالث و مانده قطعی/موقت."""

    return get_customer_cheque_settlement(
        counterpart_ref=counterpart_ref,
        opening_debt=opening_debt,
        limit=limit,
    )


def reconciliation_summary_tool(reconciliation_id: str):
    """خلاصه قطعی یک گزارش مغایرت‌گیری ذخیره‌شده با شناسه آن."""

    try:
        return get_reconciliation_summary(reconciliation_id)
    except ReconciliationNotFoundError as exc:
        return {"status": "not_found", "message": str(exc)}


def reconciliation_rows_tool(
    reconciliation_id: str,
    business_status: Literal[
        "posted",
        "reversed",
        "internal_transfer",
        "needs_review",
        "unposted",
    ],
    limit: int = 20,
):
    """ردیف‌های یک وضعیت مغایرت‌گیری، از جمله انتقال داخلی شرکت."""

    try:
        return get_reconciliation_rows(
            reconciliation_id,
            business_status,
            limit=limit,
        )
    except ReconciliationNotFoundError as exc:
        return {"status": "not_found", "message": str(exc)}


def daily_treasury_briefing_tool(due_days: int = 7):
    """گزارش روزانه دریافت، پرداخت، سررسیدها و هشدارهای خزانه."""

    return get_daily_treasury_briefing(due_days=due_days)


def cheque_risk_dashboard_tool(days: int = 60):
    """ریسک چک‌های صادرشده، دریافتی، معوق و واخواست‌شده."""

    return get_cheque_risk_dashboard(days=days)


def financial_anomaly_report_tool(
    days: int = 30,
    large_amount_threshold: str | None = None,
):
    """موارد نیازمند کنترل؛ نتیجه نشانه است و اثبات تخلف نیست."""

    return get_financial_anomaly_report(
        days=days,
        large_amount_threshold=large_amount_threshold,
    )


def payment_plan_tool(
    days: int = 30,
    available_cash: str | None = None,
):
    """برنامه پیشنهادی چک‌های پرداختی و کسری منابع؛ بدون اجرای پرداخت."""

    return get_payment_plan(days=days, available_cash=available_cash)


def customer_financial_profile_tool(
    counterpart_ref: int,
    days: int = 90,
    transaction_limit: int = 100,
):
    """پرونده حساب، گردش و چک‌های یک مشتری با شناسه طرف حساب."""

    return get_customer_financial_profile(
        counterpart_ref=counterpart_ref,
        days=days,
        transaction_limit=transaction_limit,
    )


def executive_treasury_dashboard_tool(
    days: int = 30,
    available_cash: str | None = None,
):
    """داشبورد مدیریتی جامع خزانه برای ارائه به مدیران."""

    return get_treasury_executive_dashboard(
        days=days,
        available_cash=available_cash,
    )


def safe_financial_query_tool(question: str):
    """پاسخ به سؤال مالی آزاد با SQL فقط‌خواندنی و جداول سفیدشده."""

    return ask_financial_data(question)


def cashflow_scenario_tool(
    days: int = 30,
    opening_cash: str | None = None,
    history_days: int = 90,
):
    """سناریوی خوش‌بینانه، محتمل و تنش جریان نقد؛ پیش‌بینی قطعی نیست."""

    return get_cashflow_scenarios(
        days=days,
        opening_cash=opening_cash,
        history_days=history_days,
    )


def customer_collection_prediction_tool(
    counterpart_ref: int | None = None,
    history_days: int = 365,
    forecast_days: int = 30,
    allowed_term_days: int = 90,
):
    """پیش‌بینی توضیح‌پذیر وصول، دیرکرد و ریسک برگشت چک مشتری از SQL شرکت."""
    service = FinancePredictionService(
        history_days=history_days,
        forecast_days=forecast_days,
        allowed_term_days=allowed_term_days,
    )
    if counterpart_ref is not None:
        return service.customer_prediction(counterpart_ref)
    return service.customer_predictions(limit=100)


def cheque_return_prediction_tool(
    forecast_days: int = 30,
    history_days: int = 365,
    allowed_term_days: int = 90,
    limit: int = 50,
):
    """ریسک توضیح‌پذیر برگشت چک‌های دریافتی آینده؛ پیش‌بینی قطعی نیست."""
    return FinancePredictionService(
        history_days=history_days,
        forecast_days=forecast_days,
        allowed_term_days=allowed_term_days,
    ).cheque_return_predictions(limit=limit)


def cash_shortage_prediction_tool(
    forecast_days: int = 30,
    history_days: int = 365,
    opening_cash: float | None = None,
):
    """پیش‌بینی روزانه فشار نقد و در صورت وجود مانده افتتاحیه، کسری مطلق نقدینگی."""
    return FinancePredictionService(
        history_days=history_days,
        forecast_days=forecast_days,
        opening_cash=opening_cash,
    ).cash_shortage_forecast()


def collection_priority_tool(
    forecast_days: int = 30,
    history_days: int = 365,
    allowed_term_days: int = 90,
    limit: int = 20,
):
    """اولویت پیشنهادی پیگیری وصول مشتریان براساس مانده، معوق و ریسک."""
    return FinancePredictionService(
        history_days=history_days,
        forecast_days=forecast_days,
        allowed_term_days=allowed_term_days,
    ).collection_priorities(limit=limit)
