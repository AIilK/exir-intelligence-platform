"""Page Agentهای هر صفحه داشبورد با هشدار، پیش‌بینی و حافظه (V171)."""

from app.agents.page_agents.agents import PAGE_AGENT_CLASSES, ManagerAgent

#: agent_key → frontend view key (same strings as `View` in dashboard-client.tsx).
AGENT_VIEWS = {
    "management": "management",
    "customer_behavior": "customers",
    "received_cheques": "receivedCheques",
    "issued_cheques": "issuedCheques",
    "cash_bank_movement": "cashBank",
    "company_payments": "companyPayments",
    "b2b_remittances": "b2bRemittances",
    "cashflow": "cashflow",
    "daily_cash_excel": "monthlyExcel",
    "collection": "collections",
    "distribution": "distribution",
    "representative": "representatives",
    "scenario": "simulator",
    "reconciliation": "management",
}

AGENTS_BY_KEY = {cls.key: cls for cls in [*PAGE_AGENT_CLASSES, ManagerAgent]}

__all__ = ["AGENT_VIEWS", "AGENTS_BY_KEY", "PAGE_AGENT_CLASSES", "ManagerAgent"]
