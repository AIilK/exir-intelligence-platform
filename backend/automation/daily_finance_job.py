from __future__ import annotations
from app.core.config import settings
from app.services.customer_automation_service import CustomerAutomationService
_scheduler = None
def run_daily_customer_intelligence():
    customer_result = CustomerAutomationService().run(trigger="scheduled")
    from app.services.finance_operations_service import FinanceAgentOrchestrator
    manager_result = FinanceAgentOrchestrator().run_all(trigger="scheduled")
    return {"customer_automation": customer_result, "finance_agent_team": manager_result}
def start_customer_scheduler():
    global _scheduler
    if not settings.customer_intelligence_scheduler_enabled or _scheduler is not None: return _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler=BackgroundScheduler(timezone="Asia/Tehran")
    _scheduler.add_job(run_daily_customer_intelligence,"cron",hour=settings.customer_intelligence_daily_hour,minute=settings.customer_intelligence_daily_minute,id="daily_customer_intelligence",replace_existing=True,max_instances=1,coalesce=True)
    _scheduler.start(); return _scheduler
def stop_customer_scheduler():
    global _scheduler
    if _scheduler is not None: _scheduler.shutdown(wait=False); _scheduler=None
def scheduler_status():
    job=_scheduler.get_job("daily_customer_intelligence") if _scheduler else None
    return {"enabled":settings.customer_intelligence_scheduler_enabled,"running":_scheduler is not None,"daily_time":f"{settings.customer_intelligence_daily_hour:02d}:{settings.customer_intelligence_daily_minute:02d}","next_run_time":job.next_run_time.isoformat() if job and job.next_run_time else None}
