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
def run_weekly_ai_file_analysis():
    from app.services.ai_file_analysis_service import run_batch
    return run_batch(trigger="scheduled")
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
    if not any((settings.customer_intelligence_scheduler_enabled, settings.karamad_excel_scan_enabled,
                settings.hybrid_risk_weekly_enabled, settings.whatsapp_enabled, settings.forecast_refresh_enabled)): return None
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler=BackgroundScheduler(timezone="Asia/Tehran")
    if settings.forecast_refresh_enabled:
        from app.services.production_forecast import run_scheduled_plan, run_scheduled_market
        _scheduler.add_job(run_scheduled_plan, "cron", hour=6, minute=15, id="production_forecast",
                           max_instances=1, coalesce=True, misfire_grace_time=6*3600)
        _scheduler.add_job(run_scheduled_market, "cron", day_of_week="sat", hour=9, minute=15,
                           id="production_forecast_market", max_instances=1, coalesce=True, misfire_grace_time=6*3600)
    if settings.customer_intelligence_scheduler_enabled:
        _scheduler.add_job(run_daily_customer_intelligence,"cron",hour=settings.customer_intelligence_daily_hour,minute=settings.customer_intelligence_daily_minute,id="daily_customer_intelligence",replace_existing=True,max_instances=1,coalesce=True)
    if settings.hybrid_risk_weekly_enabled:
        _scheduler.add_job(run_weekly_hybrid_risk,"cron",day_of_week=settings.hybrid_risk_weekly_day,hour=settings.hybrid_risk_weekly_hour,minute=settings.hybrid_risk_weekly_minute,id="weekly_hybrid_risk",replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=6*3600)
    if settings.ai_file_analysis_enabled and settings.openai_api_key:
        _scheduler.add_job(run_weekly_ai_file_analysis,"cron",day_of_week=settings.hybrid_risk_weekly_day,hour=settings.ai_file_analysis_weekly_hour,minute=settings.ai_file_analysis_weekly_minute,id="weekly_ai_file_analysis",replace_existing=True,max_instances=1,coalesce=True,misfire_grace_time=6*3600)
    if settings.karamad_excel_scan_enabled:
        _scheduler.add_job(run_karamad_excel_scan,"interval",minutes=max(1,settings.karamad_excel_scan_minutes),id="karamad_excel_folder_scan",replace_existing=True,max_instances=1,coalesce=True)
    if settings.whatsapp_enabled:
        # ارسال واتساپ: هر دقیقه قاعده‌های سررسیده اجرا و صف تأییدشده ارسال می‌شود (app/services/whatsapp/runner.py)
        from app.services.whatsapp.runner import tick as whatsapp_tick
        _scheduler.add_job(whatsapp_tick,"interval",minutes=1,id="whatsapp_tick",replace_existing=True,max_instances=1,coalesce=True)
    _scheduler.start(); return _scheduler
def stop_customer_scheduler():
    global _scheduler
    if _scheduler is not None: _scheduler.shutdown(wait=False); _scheduler=None
def scheduler_status():
    job=_scheduler.get_job("daily_customer_intelligence") if _scheduler else None
    karamad_job=_scheduler.get_job("karamad_excel_folder_scan") if _scheduler else None
    return {"enabled":settings.customer_intelligence_scheduler_enabled,"running":_scheduler is not None,"daily_time":f"{settings.customer_intelligence_daily_hour:02d}:{settings.customer_intelligence_daily_minute:02d}","next_run_time":job.next_run_time.isoformat() if job and job.next_run_time else None,"karamad_excel":{"enabled":settings.karamad_excel_scan_enabled,"scan_minutes":settings.karamad_excel_scan_minutes,"next_run_time":karamad_job.next_run_time.isoformat() if karamad_job and karamad_job.next_run_time else None}}
