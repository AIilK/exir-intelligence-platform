from __future__ import annotations
from app.core.config import settings
from app.services.customer_automation_service import CustomerAutomationService
_scheduler = None
def run_karamad_excel_scan():
    from app.services.karamad_manual_import_service import KaramadManualImportService
    return KaramadManualImportService().scan()
def run_weekly_hybrid_risk():
    from app.services.hybrid_risk_service import build
    return build(trigger="scheduled")
def run_daily_customer_intelligence():
    karamad_import = {"status": "disabled"}
    if settings.karamad_excel_scan_enabled:
        karamad_import = run_karamad_excel_scan()
    customer_result = CustomerAutomationService().run(trigger="scheduled")
    from app.services.page_agent_orchestrator import PageAgentOrchestrator
    manager_result = PageAgentOrchestrator().run_all(trigger="scheduled")
    return {"karamad_excel_import": karamad_import, "customer_automation": customer_result, "finance_agent_team": manager_result}
def start_customer_scheduler():
    global _scheduler
    if _scheduler is not None: return _scheduler
    if not settings.customer_intelligence_scheduler_enabled and not settings.karamad_excel_scan_enabled and not settings.hybrid_risk_weekly_enabled: return None
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler=BackgroundScheduler(timezone="Asia/Tehran")
    if settings.customer_intelligence_scheduler_enabled:
        _scheduler.add_job(run_daily_customer_intelligence,"cron",hour=settings.customer_intelligence_daily_hour,minute=settings.customer_intelligence_daily_minute,id="daily_customer_intelligence",replace_existing=True,max_instances=1,coalesce=True)
    if settings.hybrid_risk_weekly_enabled:
        _scheduler.add_job(run_weekly_hybrid_risk,"cron",day_of_week=settings.hybrid_risk_weekly_day,hour=settings.hybrid_risk_weekly_hour,minute=settings.hybrid_risk_weekly_minute,id="weekly_hybrid_risk",replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=6*3600)
    if settings.karamad_excel_scan_enabled:
        _scheduler.add_job(run_karamad_excel_scan,"interval",minutes=max(1,settings.karamad_excel_scan_minutes),id="karamad_excel_folder_scan",replace_existing=True,max_instances=1,coalesce=True)
    _scheduler.start(); return _scheduler
def stop_customer_scheduler():
    global _scheduler
    if _scheduler is not None: _scheduler.shutdown(wait=False); _scheduler=None
def scheduler_status():
    job=_scheduler.get_job("daily_customer_intelligence") if _scheduler else None
    karamad_job=_scheduler.get_job("karamad_excel_folder_scan") if _scheduler else None
    return {"enabled":settings.customer_intelligence_scheduler_enabled,"running":_scheduler is not None,"daily_time":f"{settings.customer_intelligence_daily_hour:02d}:{settings.customer_intelligence_daily_minute:02d}","next_run_time":job.next_run_time.isoformat() if job and job.next_run_time else None,"karamad_excel":{"enabled":settings.karamad_excel_scan_enabled,"scan_minutes":settings.karamad_excel_scan_minutes,"next_run_time":karamad_job.next_run_time.isoformat() if karamad_job and karamad_job.next_run_time else None}}
