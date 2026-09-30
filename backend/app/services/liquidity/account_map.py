"""Single source of truth: which account a cash/bank movement belongs to on the liquidity dashboard.

Rahkaran rows are keyed by ``RPA3.CashFlowFactor.Number`` (each factor maps to one SL
account and is filled on ~98% of Receipt/Payment rows).  Karamad rows are keyed by
``tblSL.Code`` of the row's ``SLRef``.  Every decision agreed with finance lives here
so it is reviewable in git and covered by ``test_liquidity_account_map.py``.

Two sales channels, one per system:
  B2B (Rahkaran)   -> the company sells to B2B customers *and* supplies stock to the
                      hybrid branches, which are Rahkaran customers named «هیبرید …».
  Hybrid (Karamad) -> branches sell to salons/galleries on a percentage basis; the end
                      customer pays into the hybrid's bank account.
The hybrid pays the company for its stock through the group firms (پادینا، مولهنس، …,
Karamad SL 3112) and the same money arrives in Rahkaran as «دریافت از هیبرید … بابت تامین
موجودی» (70 of 108 payments in 90 days matched by amount within 0-3 days).  Both sides are
section ``internal``: shown per channel, eliminated from the group total.  Payments the
hybrid makes straight to an FX seller for the company («خرید ارز») are real imports.

Sections:
  inflow    -> operating inflow (only ``customer_collection`` feeds the average/forecast)
  outflow   -> operating outflow by management category
  financing -> loans received and shareholder/partner current accounts (in, out, net)
  internal  -> hybrid ↔ company stock settlement; never in a group total
  excluded  -> counted elsewhere or zero net effect (inter-bank, cheques, payroll)
  review    -> unknown deposits and unmapped accounts; shown on the data-quality card
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

System = Literal["rahkaran", "karamad"]
Direction = Literal["inflow", "outflow"]


@dataclass(frozen=True)
class Classification:
    section: str
    category: str
    # -1 reduces the category instead of adding to it (e.g. a returned currency block).
    sign: int = 1


CATEGORY_LABELS: dict[str, str] = {
    "customer_collection": "وصول از مشتری",
    "other_operating_inflow": "سایر ورودی‌ها",
    "imports": "واردات / مسدودی خرید ارز",
    "suppliers": "خرید و تأمین‌کننده",
    "commission": "پورسانت",
    "tax": "مالیات و عوارض",
    "admin": "اداری، عمومی و خدمات",
    "freight": "حمل",
    "petty_cash": "تنخواه",
    "loan_installments": "اقساط وام",
    "personnel_other": "پرسنلی سایر (مساعده، وام کارکنان)",
    "customer_refund": "استرداد به مشتری",
    "loan": "تسهیلات بانکی",
    "shareholders": "سهامداران و جاری شرکا",
    "hybrid_settlement": "تسویه هیبرید با شرکت (گردش داخلی)",
    "inter_bank": "انتقال بین‌بانکی",
    "cheque_section": "چک (در بخش چک‌ها)",
    "payroll_section": "حقوق (در بخش حقوق)",
    "karamad_payroll_ignored": "حقوق کارآمد (طبق تصمیم مدیریت حساب نمی‌شود)",
    "unknown_deposit": "واریزی نامشخص",
    "unmapped": "حساب نگاشت‌نشده",
}

_IN = "inflow"
_OUT = "outflow"
_ANY = "*"


def _c(section: str, category: str, sign: int = 1) -> Classification:
    return Classification(section, category, sign)


def _both(classification: Classification) -> dict[str, Classification]:
    return {_ANY: classification}


INTER_BANK = _c("excluded", "inter_bank")
HYBRID_SETTLEMENT = _c("internal", "hybrid_settlement")
# Movement notes set in SQL from the row's «بابت»/شرح (the only signal these rows carry):
# Karamad 3112 rows that bought FX for the company, and cash-ins of a cheque, which the
# cheque sections already count (management rule: each amount is counted once).
NOTE_FX_PURCHASE = "fx_purchase"
NOTE_CHEQUE_COLLECTION = "cheque_collection"

# Rahkaran FIN3.DL codes that override the account: the counterparty says more
# than the factor.  «شرکتی» rows are the group's own accounts (اکسیر ↔ کادوس ↔ فراز)
# with same-day same-amount twins, i.e. inter-bank transfers.
RAHKARAN_COUNTERPART_OVERRIDES: dict[str, dict[str, Classification]] = {
    "950028": _both(INTER_BANK),
    "950031": _both(_c("financing", "shareholders")),
}

RAHKARAN_FACTORS: dict[str, dict[str, Classification]] = {
    # Customer collections (the only input of the inflow average).
    "123003": {_IN: _c("inflow", "customer_collection"), _OUT: _c("outflow", "customer_refund")},
    "123011": {_IN: _c("inflow", "customer_collection"), _OUT: _c("outflow", "customer_refund")},
    "1": {_IN: _c("inflow", "customer_collection")},  # حسابهای دریافتنی بابت برگشتی
    "123008": {_IN: _c("inflow", "customer_collection")},
    # Other inflows: shown, never averaged into the forecast.
    "124001": {_IN: _c("inflow", "other_operating_inflow")},
    "124028": {_IN: _c("inflow", "other_operating_inflow")},
    "612004": {_IN: _c("inflow", "other_operating_inflow")},
    "717012": {_IN: _c("inflow", "other_operating_inflow")},
    # Currency blocking for imports: blocked = outflow, returned block reduces it.
    "116001": {_OUT: _c("outflow", "imports"), _IN: _c("outflow", "imports", -1)},
    # Suppliers.  A supplier refund arrives as an inflow and is shown as other inflow.
    "511002": {_OUT: _c("outflow", "suppliers"), _IN: _c("inflow", "other_operating_inflow")},
    "512001": {_OUT: _c("outflow", "suppliers"), _IN: _c("inflow", "other_operating_inflow")},
    "511008": {_OUT: _c("outflow", "suppliers")},
    "121003": {_OUT: _c("outflow", "suppliers")},
    "121006": {_OUT: _c("outflow", "suppliers")},  # سایر پیش‌پرداخت‌ها — pending finance confirmation
    "124046": {_OUT: _c("outflow", "suppliers"), _IN: _c("inflow", "other_operating_inflow")},
    "126005": {_OUT: _c("outflow", "petty_cash")},  # counted once, when petty cash is funded
    "711050": {_OUT: _c("outflow", "commission")},
    "513003": {_OUT: _c("outflow", "tax")},
    "512006": {_OUT: _c("outflow", "tax")},
    "512044": {_OUT: _c("outflow", "tax")},
    "715010": {_OUT: _c("outflow", "tax")},
    "121005": {_OUT: _c("outflow", "tax")},
    "712010": {_OUT: _c("outflow", "freight")},
    "121013": {_OUT: _c("outflow", "admin")},
    "512024": {_OUT: _c("outflow", "admin")},
    "124006": {_OUT: _c("outflow", "admin")},
    "124007": {_OUT: _c("outflow", "admin")},
    "124003": {_OUT: _c("outflow", "personnel_other")},
    "124002": {_OUT: _c("outflow", "personnel_other")},
    "124018": {_OUT: _c("outflow", "personnel_other")},
    "712045": {_OUT: _c("outflow", "personnel_other")},
    "711022": {_OUT: _c("outflow", "personnel_other")},
    # Loans: received = financing; repayments = operating outflow (management decision).
    "412001": {_IN: _c("financing", "loan"), _OUT: _c("outflow", "loan_installments")},
    "515001": {_IN: _c("financing", "loan"), _OUT: _c("outflow", "loan_installments")},
    "515006": {_IN: _c("financing", "loan"), _OUT: _c("outflow", "loan_installments")},
    # جاری شرکا - پروژه و بانک: shareholder money unless the counterparty says «شرکتی».
    "512029": _both(_c("financing", "shareholders")),
    # Payroll is computed from HCM3 in the payroll section; never count payments twice.
    "512002": _both(_c("excluded", "payroll_section")),
    "512003": _both(_c("excluded", "payroll_section")),
    "512031": _both(_c("excluded", "payroll_section")),
    "512018": _both(_c("excluded", "payroll_section")),
    "512033": _both(_c("excluded", "payroll_section")),
    "512013": _both(_c("excluded", "payroll_section")),
    # Cheque accounts belong to the cheque sections.
    "123001": _both(_c("excluded", "cheque_section")),
    "123002": _both(_c("excluded", "cheque_section")),
    "123009": _both(_c("excluded", "cheque_section")),
    "123012": _both(_c("excluded", "cheque_section")),
    # Own bank and cash accounts.
    "126001": _both(INTER_BANK),
    "126002": _both(INTER_BANK),
    "126003": _both(INTER_BANK),
    "126004": _both(INTER_BANK),
    "126010": _both(INTER_BANK),
    "512025": _both(_c("review", "unknown_deposit")),
}

KARAMAD_ACCOUNTS: dict[str, dict[str, Classification]] = {
    "1313": {_IN: _c("inflow", "customer_collection"), _OUT: _c("outflow", "customer_refund")},
    "1423": {_IN: _c("inflow", "customer_collection")},  # هیبرید من
    "1317": {_IN: _c("inflow", "other_operating_inflow")},
    "6504": {_IN: _c("inflow", "other_operating_inflow")},
    "2115": {_IN: _c("inflow", "other_operating_inflow")},
    # «حساب‌های پرداختنی (شرکت‌ها)»: the group firms the hybrid buys its stock from.
    # FX purchases made for the company are split off in ``classify`` via the note.
    "3112": _both(HYBRID_SETTLEMENT),
    "3232": {_OUT: _c("outflow", "suppliers"), _IN: _c("inflow", "other_operating_inflow")},
    "3233": {_OUT: _c("outflow", "commission")},
    "4411": {_OUT: _c("outflow", "commission")},
    "8704": {_OUT: _c("outflow", "commission")},
    "8119": {_OUT: _c("outflow", "commission")},
    "8138": {_OUT: _c("outflow", "commission")},
    "1422": {_OUT: _c("outflow", "tax")},
    "3231": {_OUT: _c("outflow", "tax")},
    "8707": {_OUT: _c("outflow", "freight")},
    "3237": {_OUT: _c("outflow", "freight")},
    "1115": {_OUT: _c("outflow", "petty_cash")},
    "1116": {_OUT: _c("outflow", "petty_cash")},
    "8511": {_OUT: _c("outflow", "loan_installments")},
    "1413": {_OUT: _c("outflow", "personnel_other")},
    "3235": {_OUT: _c("outflow", "admin")},
    "3701": _both(_c("financing", "shareholders")),
    "3702": _both(_c("financing", "shareholders")),
    "3709": _both(_c("financing", "shareholders")),
    # Management decision: payroll comes only from Rahkaran; Karamad payroll is ignored.
    "3220": _both(_c("excluded", "karamad_payroll_ignored")),
    "3216": _both(_c("excluded", "karamad_payroll_ignored")),
    "3214": _both(_c("excluded", "karamad_payroll_ignored")),
    "3226": _both(_c("excluded", "karamad_payroll_ignored")),
    "3222": _both(_c("excluded", "karamad_payroll_ignored")),
    "8124": _both(_c("excluded", "karamad_payroll_ignored")),
    "1111": _both(INTER_BANK),
    "1113": _both(INTER_BANK),
    "9512": _both(_c("review", "unknown_deposit")),
}

UNMAPPED = _c("review", "unmapped")


def _normalize_code(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def _pick(rules: dict[str, Classification], direction: str) -> Classification | None:
    return rules.get(direction) or rules.get(_ANY)


def is_hybrid_counterpart(name: object) -> bool:
    """Rahkaran customers that are hybrid branches; same name rule as customer_intelligence_service."""
    text = str(name or "").replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("‌", " ").lower()
    return "هیبرید" in text or "hybrid" in text


def classify(
    system: System,
    direction: Direction,
    account_code: object,
    counterpart_code: object = None,
    counterpart_name: object = None,
    note: str | None = None,
) -> Classification:
    """Classify one movement. Unknown accounts land in ``review/unmapped``, never in a total."""
    code = _normalize_code(account_code)
    if note == NOTE_CHEQUE_COLLECTION and direction == _IN:
        return _c("excluded", "cheque_section")
    if system == "rahkaran":
        counterpart = _normalize_code(counterpart_code)
        override = RAHKARAN_COUNTERPART_OVERRIDES.get(counterpart or "")
        if override and (hit := _pick(override, direction)):
            return hit
        rules = RAHKARAN_FACTORS.get(code or "")
        hit = _pick(rules, direction) if rules else None
        # Money from/to a hybrid branch is the stock settlement, unless the account
        # already routes it elsewhere (cheques, own bank accounts).
        if is_hybrid_counterpart(counterpart_name) and (hit is None or hit.section != "excluded"):
            return HYBRID_SETTLEMENT
        if hit:
            return hit
        # Expense accounts (71xxxx) paid in cash/bank are general and administrative.
        if direction == _OUT and code and code.startswith("71"):
            return _c("outflow", "admin")
        return UNMAPPED
    if code == "3112" and direction == _OUT and note == NOTE_FX_PURCHASE:
        return _c("outflow", "imports")
    rules = KARAMAD_ACCOUNTS.get(code or "")
    if rules and (hit := _pick(rules, direction)):
        return hit
    # Karamad expense accounts (8xxx) are general and administrative.
    if direction == _OUT and code and code.startswith("8"):
        return _c("outflow", "admin")
    return UNMAPPED
