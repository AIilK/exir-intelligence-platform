
from fastapi import APIRouter
from app.services.customer_risk_service import get_customer_risk_report

router = APIRouter(
    prefix="/finance-agent",
    tags=["Customer Risk"]
)


@router.get("/customer-risk")
def customer_risk():

    return {
        "success": True,
        "data": get_customer_risk_report()
    }
