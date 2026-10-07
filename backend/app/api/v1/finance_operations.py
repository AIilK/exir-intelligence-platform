from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.finance_operations_service import FinanceAgentOrchestrator, FinanceOperationsStore

router=APIRouter(prefix="/finance",tags=["finance-agents-and-operations"])

class CaseCreate(BaseModel):
    counterpart_ref:int|None=None
    counterpart_name:str
    priority:str="high"
    assignee:str|None=None
    due_at:str|None=None

class CaseUpdate(BaseModel):
    status:str|None=None
    priority:str|None=None
    assignee:str|None=None
    due_at:str|None=None

class FollowupCreate(BaseModel):
    channel:str="call"
    result:str|None=None
    note:str|None=None
    created_by:str|None=None

class PromiseCreate(BaseModel):
    amount:float=Field(ge=0)
    promise_date:str
    status:str="pending"
    note:str|None=None

class ScenarioRequest(BaseModel):
    collection_rate_percent:float=Field(default=75,ge=0,le=100)
    payment_delay_days:int=Field(default=0,ge=0,le=30)
    opening_cash:float|None=Field(default=None,ge=0)

class PoliciesUpdate(BaseModel):
    values:dict[str,Any]

class OutcomeCreate(BaseModel):
    prediction_type:str
    entity_ref:str|None=None
    predicted_value:float|None=None
    actual_value:float
    predicted_at:str|None=None
    outcome_at:str|None=None
    status:str="evaluated"
    metadata:dict[str,Any]|None=None

class AgentAlertUpdate(BaseModel):
    status:str

@router.post("/agents/run-all",summary="اجرای همه Agentهای صفحات و Finance Manager Agent")
def run_all_agents():
    return run_all_page_agents()

# ------------------------------------------------------------------ V171 page agents
@router.get("/page-agents",summary="آخرین گزارش Agent هر صفحه")
def page_agents_latest():
    from app.services.page_agent_orchestrator import PageAgentOrchestrator
    return PageAgentOrchestrator().latest()

@router.post("/page-agents/run-all",summary="اجرای همه Agentهای صفحات")
def run_all_page_agents():
    from app.services.page_agent_orchestrator import PageAgentOrchestrator
    try:return PageAgentOrchestrator().run_all("manual")
    except RuntimeError as exc:raise HTTPException(409,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(500,detail=f"اجرای تیم Agentهای مالی با خطا مواجه شد: {exc}") from exc

@router.get("/page-agents/{agent_key}",summary="گزارش، حافظه و هشدارهای Agent یک صفحه")
def page_agent_detail(agent_key:str):
    from app.services.page_agent_orchestrator import PageAgentOrchestrator
    try:return PageAgentOrchestrator().detail(agent_key)
    except KeyError as exc:raise HTTPException(404,detail="Agent پیدا نشد.") from exc

@router.post("/page-agents/{agent_key}/run",summary="اجرای دستی Agent یک صفحه")
def run_page_agent(agent_key:str):
    from app.services.page_agent_orchestrator import PageAgentOrchestrator
    try:return PageAgentOrchestrator().run(agent_key,"manual")
    except KeyError as exc:raise HTTPException(404,detail="Agent پیدا نشد.") from exc
    except RuntimeError as exc:raise HTTPException(409,detail=str(exc)) from exc

@router.get("/agent-alerts",summary="هشدارهای Agentها با حافظه تکرار")
def agent_alerts(page:str|None=Query(default=None),level:str|None=Query(default=None),
                 status:str|None=Query(default="active"),agent_key:str|None=Query(default=None),
                 limit:int=Query(default=300,ge=1,le=1000)):
    from app.services.agent_memory_store import AgentMemoryStore
    from app.agents.page_agents import AGENT_VIEWS
    rows=AgentMemoryStore().list_alerts(agent_key=agent_key,page=page,status=status,level=level,limit=limit)
    # هشدارهای مدیر مالی جمع‌بندی همان هشدارهای صفحات است؛ در مرکز هشدار تکرار نمی‌شوند.
    if agent_key is None: rows=[row for row in rows if row["agent_key"]!="management"]
    for row in rows: row["view"]=AGENT_VIEWS.get(row["agent_key"])
    return {"status":"success","alerts":rows}

@router.patch("/agent-alerts/{alert_key:path}",summary="تأیید، نادیده گرفتن یا بستن هشدار Agent")
def update_agent_alert(alert_key:str,body:AgentAlertUpdate):
    from app.services.agent_memory_store import AgentMemoryStore
    try:ok=AgentMemoryStore().update_alert(alert_key,body.status)
    except ValueError as exc:raise HTTPException(400,detail=str(exc)) from exc
    if not ok:raise HTTPException(404,detail="هشدار پیدا نشد.")
    return {"status":"success"}

@router.get("/agents/latest",summary="آخرین خلاصه مدیریتی و خروجی Agentها")
def latest_agents():
    row=FinanceOperationsStore().latest_report()
    return {"status":"empty","message":"هنوز تیم Agentها اجرا نشده است."} if row is None else {"status":"success",**row["payload"]}

@router.get("/agents/data-hub", summary="Snapshot مشترک داده برای همه Agentهای مالی")
def agents_data_hub():
    from app.services.finance_agent_data_hub import FinanceAgentDataHub
    return {"status": "success", **FinanceAgentDataHub().build()}

@router.get("/agents/status",summary="وضعیت همه Agentهای مالی")
def agents_status():
    from app.core.config import settings
    from app.services.page_agent_orchestrator import PageAgentOrchestrator
    return {"status":"ready","llm_configured":bool(settings.openai_api_key),"model":settings.openai_model,"agents":[{"name":x["name"],"agent_key":x["agent_key"],"page":x["page"],"status":"ready","fallback_available":True} for x in PageAgentOrchestrator().catalog()]}

@router.get("/management-summary/latest",summary="آخرین خلاصه مدیریتی Finance Manager Agent")
def management_summary():
    row=FinanceOperationsStore().latest_report()
    return {"status":"empty","message":"هنوز گزارش مدیریتی ساخته نشده است."} if row is None else {"status":"success","report_id":row["report_id"],"created_at":row["created_at"],"management_summary":row["payload"].get("management_summary"),"agents":row["payload"].get("agents")}

@router.get("/collection-cases",summary="مرکز عملیات وصول")
def collection_cases(status:str|None=Query(default=None)):
    return {"status":"success","cases":FinanceOperationsStore().list_cases(status)}

@router.post("/collection-cases",summary="ساخت پرونده پیگیری وصول")
def create_collection_case(body:CaseCreate):
    return {"status":"success","case":FinanceOperationsStore().create_case(body.model_dump())}

@router.patch("/collection-cases/{case_id}",summary="تغییر مسئول، مهلت یا وضعیت وصول")
def update_collection_case(case_id:str,body:CaseUpdate):
    if not FinanceOperationsStore().update_case(case_id,body.model_dump(exclude_none=True)):raise HTTPException(404,detail="پرونده پیدا نشد.")
    return {"status":"success"}

@router.post("/collection-cases/{case_id}/followups",summary="ثبت تماس و نتیجه پیگیری")
def add_followup(case_id:str,body:FollowupCreate):return {"status":"success","followup":FinanceOperationsStore().add_followup(case_id,body.model_dump())}

@router.post("/collection-cases/{case_id}/promises",summary="ثبت قول پرداخت مشتری")
def add_promise(case_id:str,body:PromiseCreate):return {"status":"success","promise":FinanceOperationsStore().add_promise(case_id,body.model_dump())}

@router.get("/policies",summary="قوانین ریسک و اتوماسیون")
def policies():return {"status":"success","values":FinanceOperationsStore().policies()}

@router.put("/policies",summary="ویرایش قوانین بدون تغییر کد")
def update_policies(body:PoliciesUpdate):return {"status":"success","values":FinanceOperationsStore().update_policies(body.values)}

@router.post("/cashflow/scenario",summary="شبیه‌ساز سناریوی نقدینگی")
def cashflow_scenario(body:ScenarioRequest):
    try:return FinanceAgentOrchestrator().scenario(body.collection_rate_percent/100,body.payment_delay_days,body.opening_cash)
    except Exception as exc:raise HTTPException(500,detail=f"محاسبه سناریو با خطا مواجه شد: {exc}") from exc

@router.get("/agent-reports/history",summary="تاریخچه گزارش‌های روزانه Agentها")
def report_history(limit:int=Query(default=30,ge=1,le=365)):return {"status":"success","reports":FinanceOperationsStore().reports(limit)}

@router.get("/prediction-performance",summary="ارزیابی دقت پیش‌بینی‌ها")
def prediction_performance():return {"status":"success",**FinanceOperationsStore().performance()}

@router.post("/prediction-performance/outcomes",summary="ثبت نتیجه واقعی برای سنجش دقت")
def add_prediction_outcome(body:OutcomeCreate):return {"status":"success","outcome":FinanceOperationsStore().add_outcome(body.model_dump())}

@router.get("/notifications",summary="صندوق اعلان‌های داشبورد، ایمیل و پیامک")
def notifications(limit:int=Query(default=100,ge=1,le=500)):return {"status":"success","notifications":FinanceOperationsStore().notifications(limit)}
