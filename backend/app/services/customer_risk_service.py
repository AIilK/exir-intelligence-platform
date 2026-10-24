
from typing import List, Dict


def calculate_risk_score(customer: Dict):

    score = 0
    reasons = []

    if customer.get("returned_amount", 0) > 0:
        score += 40
        reasons.append("سابقه چک برگشتی یا برگشت مبلغ مشاهده شده")

    if customer.get("overdue_amount", 0) > 0:
        score += 25
        reasons.append("دارای مطالبات یا چک سررسید گذشته")

    if customer.get("average_term_days", 0) > 90:
        score += 20
        reasons.append("میانگین سررسید بالاتر از سیاست ۹۰ روزه شرکت")

    if customer.get("open_amount", 0) > 1000000000:
        score += 15
        reasons.append("مبلغ چک‌های دریافتی باز بالاست")

    if score >= 80:
        level = "HIGH"
    elif score >= 50:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "risk_score": score,
        "level": level,
        "reasons": reasons
    }


def get_customer_risk_report():

    customers = [
        {
            "customer": "نمونه مشتری",
            "open_amount": 3500000000,
            "returned_amount": 500000000,
            "overdue_amount": 800000000,
            "average_term_days": 120
        }
    ]

    result = []

    for customer in customers:
        risk = calculate_risk_score(customer)

        result.append({
            **customer,
            **risk,
            "recommendation":
                "بررسی سقف اعتبار و پیگیری وصول مطالبات پیشنهاد می‌شود"
        })

    return result


class CustomerRiskService:

    def __init__(self):
        pass

    def get_customer_risks(self):
        return get_customer_risk_report()
