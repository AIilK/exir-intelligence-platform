
from app.services.customer_risk_service import get_customer_risk_report


def get_customer_risk_data():

    return {
        "status": "connected",
        "module": "customer_risk",
        "customers": get_customer_risk_report()
    }


def get_cashflow_forecast_data():
    return {
        "status": "waiting",
        "module": "cashflow_forecast",
        "forecast": []
    }


def get_finance_alerts_data():
    return {
        "status": "waiting",
        "module": "alerts",
        "alerts": []
    }


def get_collection_priority_data():
    return {
        "status": "waiting",
        "module": "collection_priority",
        "customers": []
    }
