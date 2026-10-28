"""ماژول‌های اپ و اینکه هر ماژول به چه صفحه، هشدار (Alarm)، API و ابزار چت‌باتی دسترسی می‌دهد.

هر کاربر فهرستی از کلید ماژول‌ها دارد؛ مدیر سیستم (is_admin) همه را می‌بیند.
کلید صفحه‌ها همان View فرانت (dashboard-client.tsx) است.
ماژول‌های sales* صفحه‌های فروش داشبورد یکپارچه‌اند (view مالی ندارند)؛ نگاشت مسیرهایشان در unified/src/Shell.jsx (canOpen)
و نگاشت APIهای فروش در sales/backend/exir_auth.py است. ماژول chatbot اجازه استفاده از دستیار هوشمند است.
group: دسته‌بندی در فرم «مدیریت کاربران».
"""

from __future__ import annotations

from typing import Any

MODULES: dict[str, dict[str, Any]] = {
    "management": {
        "title": "خلاصه مدیریتی مالی",
        "views": ["overview", "management", "history"],
        # خلاصه مالی همه بلوک‌هایش را نشان می‌دهد؛ پس الارم همان بخش‌ها را هم می‌گیرد.
        "alarm_agents": ["management", "received_cheques", "issued_cheques", "payables", "liquidity", "cashflow", "distribution"],
        "chat_tools": ["cheques_overview", "cheque_status_list", "liquidity_forecast", "payables_overview", "distribution_month"],
    },
    "sales": {
        "title": "خلاصه مدیریتی فروش",
        "group": "sales",
        "views": ["overview", "sales"],
        "alarm_agents": ["sales_manager", "sales_pace", "sales_requests", "sales_finance_bridge", "distribution"],
        "chat_tools": ["distribution_month", "sales_hybrids", "sales_team", "sales_b2b"],
    },
    "salesOverview": {
        "title": "نمای کلی فروش",
        "group": "sales", "views": [], "alarm_agents": [],
        "chat_tools": ["sales_hybrids"],
    },
    "salesHybrid": {
        "title": "عملکرد هیبرید و پرونده هیبریدها",
        "group": "sales", "views": [], "alarm_agents": ["sales_pace", "sales_requests"],
        "chat_tools": ["sales_hybrids"],
    },
    "salesTeam": {
        "title": "تیم فروش (ویزیتورها)",
        "group": "sales", "views": [], "alarm_agents": [],
        "chat_tools": ["sales_team"],
    },
    "salesProducts": {
        "title": "محصولات و گروه‌ها",
        "group": "sales", "views": [], "alarm_agents": [], "chat_tools": [],
    },
    "salesCustomers": {
        "title": "مشتریان فروش",
        "group": "sales", "views": [], "alarm_agents": ["sales_finance_bridge"], "chat_tools": [],
    },
    "salesAnalysis": {
        "title": "تحلیل فروش",
        "group": "sales", "views": [], "alarm_agents": [], "chat_tools": ["sales_hybrids"],
    },
    "salesInventory": {
        "title": "موجودی و سفارش",
        "group": "sales", "views": [], "alarm_agents": [], "chat_tools": [],
    },
    "salesB2B": {
        "title": "فروش راهکاران (B2B)",
        "group": "sales", "views": [], "alarm_agents": [], "chat_tools": ["sales_b2b"],
    },
    "salesExport": {
        "title": "فروش صادراتی",
        "group": "sales", "views": [], "alarm_agents": [], "chat_tools": [],
    },
    "customers": {
        "title": "پرونده مشتری",
        "views": ["customers"],
        "alarm_agents": ["customer_behavior"],
        "chat_tools": ["find_customer", "find_cheque"],
    },
    "cheques": {
        "title": "چک و سررسید",
        "views": ["cheques", "receivedCheques", "issuedCheques"],
        "alarm_agents": ["received_cheques", "issued_cheques"],
        "chat_tools": ["cheques_overview", "cheque_status_list", "find_cheque", "find_customer"],
    },
    "cashBank": {
        "title": "نقد و حواله",
        "views": ["cashBank", "monthlyExcel"],
        "alarm_agents": ["cash_bank_movement", "daily_cash_excel"],
        "chat_tools": [],
    },
    "companyPayments": {
        "title": "حواله‌های پرداختی شرکت",
        "views": ["companyPayments", "b2bRemittances"],
        "alarm_agents": ["company_payments", "b2b_remittances"],
        "chat_tools": [],
    },
    "payables": {
        "title": "پرداخت تجاری",
        "views": ["payables"],
        "alarm_agents": ["payables"],
        "chat_tools": ["payables_overview", "find_supplier"],
    },
    "liquidity": {
        "title": "نقدینگی",
        "views": ["liquidity", "cashflow", "simulator"],
        "alarm_agents": ["liquidity", "cashflow", "scenario"],
        "chat_tools": ["liquidity_forecast"],
    },
    "inventoryPricing": {
        "title": "قیمت‌گذاری انبار",
        "views": ["inventoryPricing"],
        "alarm_agents": [],
        "chat_tools": ["inventory_pricing"],
    },
    "purchaseDocs": {
        "title": "اسناد خرید",
        "views": ["purchaseDocs"],
        "alarm_agents": [],
        "chat_tools": ["purchase_documents", "find_product", "find_supplier"],
    },
    "collections": {
        "title": "مرکز عملیات وصول",
        "views": ["collections", "representatives"],
        "alarm_agents": ["collection", "representative"],
        "chat_tools": ["cheque_status_list", "find_customer", "find_cheque"],
    },
    "distribution": {
        "title": "توزیع بار",
        "views": ["distribution"],
        "alarm_agents": ["distribution"],
        "chat_tools": ["distribution_month"],
    },
    "performance": {
        "title": "دقت پیش‌بینی",
        "views": ["performance"],
        "alarm_agents": [],
        "chat_tools": [],
    },
    "settings": {
        "title": "قوانین و اتوماسیون",
        "views": ["settings"],
        "alarm_agents": [],
        "chat_tools": [],
    },
    "reconciliation": {
        "title": "مغایرت‌گیری بانک",
        "group": "finance",
        "views": [],
        "alarm_agents": ["reconciliation"],
        "chat_tools": [],
    },
    "chatbot": {
        # اجازه استفاده از دستیار هوشمند؛ داده‌ای که جواب می‌دهد همچنان به ماژول‌های دیگر همین کاربر محدود است.
        "title": "دستیار هوشمند (چت‌بات)",
        "group": "system", "views": [], "alarm_agents": [], "chat_tools": [],
    },
}
GROUP_TITLES = {"finance": "مالی و خزانه", "sales": "فروش", "system": "سیستم"}

# صفحه‌هایی که همه کاربران واردشده می‌بینند (مرکز هشدارهای ماژول‌های خودشان).
COMMON_VIEWS = ["alerts"]

# API هایی که فقط برای بعضی ماژول‌ها باز است (پیشوند مسیر ← ماژول‌های مجاز). بقیه APIها فقط ورود می‌خواهند.
# «admin» یعنی فقط مدیر سیستم (SQL آزاد، اتصال دیتابیس، اجرای دستی همه Agentها).
API_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("/api/v1/query", ("admin",)),
    ("/api/v1/chatbot", ("chatbot",)),
    ("/api/v1/connections", ("admin",)),
    ("/api/v1/finance/agents/run-all", ("admin",)),
    ("/api/v1/finance/page-agents/run-all", ("admin",)),
    ("/api/v1/finance/payables", ("payables", "management")),
    ("/api/v1/finance/purchase-", ("purchaseDocs",)),
    ("/api/v1/finance/inventory-pricing", ("inventoryPricing",)),
    ("/api/v1/finance/distribution", ("distribution", "management", "sales")),
    ("/api/v1/finance/sales-network", ("customers", "sales")),
    ("/api/v1/finance/collection-cases", ("collections",)),
    ("/api/v1/finance/representative-", ("collections",)),
    ("/api/v1/finance/karamad-payment-transfers", ("cashBank", "companyPayments")),
    ("/api/v1/treasury/cash-bank", ("cashBank", "management")),
    ("/api/v1/treasury/payment-orders", ("companyPayments",)),
    ("/api/v1/treasury/customer-b2b-remittances", ("companyPayments",)),
    ("/api/v1/liquidity/summary", ("liquidity", "management")),
    ("/api/v1/liquidity/financing", ("liquidity", "management")),
    ("/api/v1/liquidity/payroll", ("liquidity", "management")),
    ("/api/v1/liquidity/bank-balances", ("liquidity", "management")),
]


# ماژول‌های خلاصه (چند بخش را با هم نشان می‌دهند): الارم هر Agent ترجیحاً به ماژول اصلی خودش نسبت داده می‌شود.
SUMMARY_MODULES = ("management", "sales")


def alarm_module(user: dict[str, Any], agent_key: str) -> str | None:
    """ماژولی از ماژول‌های کاربر که این الارم زیر آن نشان داده می‌شود (اول ماژول اصلی، بعد خلاصه‌ها)."""
    mine = user_modules(user)
    ordered = [k for k in mine if k not in SUMMARY_MODULES] + [k for k in mine if k in SUMMARY_MODULES]
    return next((k for k in ordered if agent_key in MODULES[k]["alarm_agents"]), None)


def all_module_keys() -> list[str]:
    return list(MODULES)


def clean_modules(keys: list[str] | None) -> list[str]:
    return [k for k in dict.fromkeys(keys or []) if k in MODULES]


def user_modules(user: dict[str, Any]) -> list[str]:
    return all_module_keys() if user.get("is_admin") else clean_modules(user.get("modules"))


def allowed_views(user: dict[str, Any]) -> list[str]:
    views = [v for key in user_modules(user) for v in MODULES[key]["views"]]
    return list(dict.fromkeys(views + COMMON_VIEWS + (["users"] if user.get("is_admin") else [])))


def alarm_agents(user: dict[str, Any]) -> set[str]:
    return {a for key in user_modules(user) for a in MODULES[key]["alarm_agents"]}


def chat_tools(user: dict[str, Any]) -> set[str] | None:
    """None یعنی همه ابزارها (مدیر سیستم)."""
    if user.get("is_admin"):
        return None
    return {t for key in user_modules(user) for t in MODULES[key]["chat_tools"]}


def api_allowed(user: dict[str, Any], path: str) -> bool:
    for prefix, modules in API_RULES:
        if path.startswith(prefix):
            if user.get("is_admin"):
                return True
            return bool(set(modules) & set(user_modules(user)))
    return True


def catalog() -> list[dict[str, Any]]:
    return [{"key": k, "title": m["title"], "views": m["views"], "has_alarms": bool(m["alarm_agents"]),
             "group": m.get("group", "finance"), "group_title": GROUP_TITLES[m.get("group", "finance")]} for k, m in MODULES.items()]


def module_titles(user: dict[str, Any]) -> list[str]:
    return [MODULES[k]["title"] for k in user_modules(user)]
