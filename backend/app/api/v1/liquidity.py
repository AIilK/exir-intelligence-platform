from typing import Literal

from fastapi import APIRouter, Query

from app.services.liquidity.account_map import CATEGORY_LABELS
from app.services.liquidity.bank_balances import BankBalanceService, attach_balances
from app.services.liquidity.cash_movements import CHANNEL_LABELS, CashMovementService
from app.services.liquidity.issued_cheques import IssuedChequeService
from app.services.liquidity.payroll import PayrollService
from app.services.liquidity.received_cheques import ReceivedChequeService
from app.services.liquidity.summary import LiquiditySummaryService

router = APIRouter(
    prefix="/liquidity",
    tags=["liquidity"],
)

ChannelParam = Literal["b2b", "hybrid", "all"]
Channel = Query(default="all", description="کانال فروش: b2b = راهکاران، hybrid = کارآمد، all = کل گروه (تسویه داخلی حذف)")
BaseDays = Query(default=90, ge=7, le=365, description="دوره مبنای میانگین (روز کامل تا دیروز)")
Refresh = Query(default=False, description="نادیده گرفتن کش ۵ دقیقه‌ای")


@router.get("/inflows", summary="میانگین ورودی: وصول از مشتری نهایی (حواله و نقد)")
def liquidity_inflows(
    base_days: int = BaseDays,
    channel: ChannelParam = Channel,
    method: Literal["bank", "cash"] | None = None,
    refresh: bool = Refresh,
):
    return CashMovementService().inflows(base_days=base_days, channel=channel, method=method, refresh=refresh)


@router.get("/outflows", summary="میانگین خروجی به تفکیک دسته مدیریتی")
def liquidity_outflows(
    base_days: int = BaseDays,
    channel: ChannelParam = Channel,
    category: str | None = Query(default=None, description="یکی از دسته‌های خروجی account_map"),
    refresh: bool = Refresh,
):
    return CashMovementService().outflows(base_days=base_days, channel=channel, category=category, refresh=refresh)


@router.get("/financing", summary="تأمین مالی: وام و سهامداران (ورودی، خروجی، خالص)")
def liquidity_financing(base_days: int = BaseDays, channel: ChannelParam = Channel, refresh: bool = Refresh):
    return CashMovementService().financing(base_days=base_days, channel=channel, refresh=refresh)


@router.get("/data-quality", summary="حساب‌های نگاشت‌نشده، واریزی نامشخص و تسویه داخلی")
def liquidity_data_quality(base_days: int = BaseDays, channel: ChannelParam = Channel, refresh: bool = Refresh):
    return CashMovementService().data_quality(base_days=base_days, channel=channel, refresh=refresh)


@router.get("/received-cheques", summary="چک‌های دریافتی باز: قطعی، اتکا، ریسک وصول، معوق، برگشتی و مشتری‌ها")
def liquidity_received_cheques(
    horizon_days: int = Query(default=30, ge=1, le=365, description="افق از امروز"),
    channel: ChannelParam = Channel,
    branch: str | None = Query(default=None, description="شعبه کارآمد (بخشی از نام)"),
    visitor: str | None = Query(default=None, description="ویزیتور کارآمد (بخشی از نام)"),
    holding: Literal["cashbox", "bank", "collector", "pending"] | None = Query(default=None, description="محل نگهداری"),
    reliance_band: Literal["high", "medium", "low"] | None = Query(default=None, description="بالای ۸۰٪ / ۵۰ تا ۸۰٪ / زیر ۵۰٪"),
    search: str | None = Query(default=None, description="نام یا کد مشتری یا سریال چک"),
    refresh: bool = Refresh,
):
    return ReceivedChequeService().report(horizon_days=horizon_days, channel=channel, branch=branch, visitor=visitor,
                                          holding=holding, reliance_band=reliance_band, search=search, refresh=refresh)


@router.get("/received-cheques/customers/{system}/{customer_ref}", summary="ریز چک‌های باز یک مشتری با دلایل کسر اتکا")
def liquidity_received_customer(system: Literal["rahkaran", "karamad"], customer_ref: str, refresh: bool = Refresh):
    return ReceivedChequeService().customer_detail(system=system, customer_ref=customer_ref, refresh=refresh)


@router.get("/issued-cheques", summary="چک‌های پرداختی باز: تعهد بازه، معوق، تقویم، حساب بانکی و ذی‌نفع")
def liquidity_issued_cheques(
    horizon_days: int = Query(default=30, ge=1, le=365, description="افق از امروز"),
    channel: ChannelParam = Channel,
    bank_account: str | None = Query(default=None, description="bank_account_key از جدول حساب‌ها"),
    payee: str | None = Query(default=None, description="نام یا کد ذی‌نفع"),
    min_amount: float | None = Query(default=None, ge=0, description="حداقل مبلغ (ریال)"),
    max_amount: float | None = Query(default=None, ge=0, description="حداکثر مبلغ (ریال)"),
    refresh: bool = Refresh,
):
    result = IssuedChequeService().report(horizon_days=horizon_days, channel=channel, bank_account=bank_account,
                                          payee=payee, min_amount=min_amount, max_amount=max_amount, refresh=refresh)
    try:
        accounts, _, _ = BankBalanceService().accounts(channel, refresh)
        attach_balances(result["data"]["by_bank_account"], accounts)
    except Exception as exc:  # the cheque table stays usable without balances
        result["warnings"].append({"code": "balances_unavailable",
                                   "message": f"مانده حساب‌ها دریافت نشد؛ ستون پوشش خالی است. ({exc.__class__.__name__})"})
    return result


@router.get("/payroll", summary="حقوق پرسنل از راهکاران: خالص، بیمه، مالیات، جمع کل و زمان پرداخت")
def liquidity_payroll(
    months: int = Query(default=12, ge=1, le=24, description="تعداد ماه‌های روند"),
    horizon_days: int = Query(default=90, ge=7, le=180, description="افق پیش‌بینی پرداخت"),
    refresh: bool = Refresh,
):
    return PayrollService().report(months=months, horizon_days=horizon_days, refresh=refresh)


@router.get("/summary", summary="پیش‌بینی روزانه نقدینگی: موجودی، ورودی و خروجی، اولین کسری، Runway و سناریوها")
def liquidity_summary(
    horizon_days: int = Query(default=30, ge=7, le=180, description="افق پیش‌بینی از امروز"),
    channel: ChannelParam = Channel,
    base_days: int = BaseDays,
    include_cash: bool = Query(default=False, description="موجودی صندوق هم در موجودی اول دوره بیاید"),
    opening_balance: float | None = Query(default=None, description="موجودی واقعی امروز (ریال)؛ جایگزین موجودی دفتری"),
    refresh: bool = Refresh,
):
    return LiquiditySummaryService().report(horizon_days=horizon_days, channel=channel, base_days=base_days,
                                            include_cash=include_cash, opening_balance_rial=opening_balance,
                                            refresh=refresh)


@router.get("/bank-balances", summary="موجودی دفتری بانک و صندوق به تفکیک حساب")
def liquidity_bank_balances(channel: ChannelParam = Channel, refresh: bool = Refresh):
    return BankBalanceService().report(channel=channel, refresh=refresh)


@router.get("/categories", summary="برچسب فارسی دسته‌ها و کانال‌ها")
def liquidity_categories():
    return {"status": "success", "categories": CATEGORY_LABELS, "channels": CHANNEL_LABELS}
