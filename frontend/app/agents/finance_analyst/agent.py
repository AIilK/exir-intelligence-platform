
from .tools import (
    get_customer_risk,
    get_cashflow_forecast,
    get_finance_alerts,
    get_collection_priority
)


class FinanceAnalystAgent:

    def analyze(self):

        return {
            "success": True,
            "agent": "Finance Analyst Agent",
            "context": {
                "customer_risk": get_customer_risk(),
                "cashflow_forecast": get_cashflow_forecast(),
                "alerts": get_finance_alerts(),
                "collection_priority": get_collection_priority()
            }
        }
