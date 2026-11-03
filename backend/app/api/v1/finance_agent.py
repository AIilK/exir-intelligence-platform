
from fastapi import APIRouter
from app.agents.finance_analyst.agent import FinanceAnalystAgent

router = APIRouter(
    prefix='/finance-agent',
    tags=['Finance Analyst Agent']
)

@router.get('/daily-report')
def daily_report():
    return FinanceAnalystAgent().analyze()
