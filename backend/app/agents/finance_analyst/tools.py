
from app.services.finance_intelligence_service import get_customer_risk_data


def get_customer_risk():

    return get_customer_risk_data()


def get_cashflow_forecast():
    return {
        "status": "waiting"
    }


def get_finance_alerts():
    return {
        "status": "waiting"
    }


def get_collection_priority():
    return {
        "status": "waiting"
    }
