from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FinanceOperationsStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or settings.customer_intelligence_history_db)
        self._init()

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS finance_policies(key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collection_cases(case_id TEXT PRIMARY KEY,counterpart_ref INTEGER,counterpart_name TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL,assignee TEXT,due_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collection_followups(followup_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,channel TEXT,result TEXT,note TEXT,created_by TEXT,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS payment_promises(promise_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,amount REAL,promise_date TEXT,status TEXT NOT NULL,note TEXT,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS finance_agent_reports(report_id TEXT PRIMARY KEY,trigger_type TEXT NOT NULL,created_at TEXT NOT NULL,payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS prediction_outcomes(outcome_id TEXT PRIMARY KEY,prediction_type TEXT NOT NULL,entity_ref TEXT,predicted_value REAL,actual_value REAL,predicted_at TEXT,outcome_at TEXT,status TEXT,metadata_json TEXT);
            CREATE TABLE IF NOT EXISTS notification_outbox(notification_id TEXT PRIMARY KEY,channel TEXT NOT NULL,title TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,sent_at TEXT,error TEXT);
            """)
            defaults = {"allowed_term_days":90,"high_return_probability_percent":35,"critical_overdue_ratio_percent":50,"cash_pressure_days_threshold":5,"daily_run_hour":7,"daily_run_minute":0,"notification_channels":["dashboard"]}
            for key, value in defaults.items():
                db.execute("INSERT OR IGNORE INTO finance_policies VALUES(?,?,?)",(key,json.dumps(value,ensure_ascii=False),_now()))

    def policies(self):
        with self.connect() as db:
            return {r["key"]: json.loads(r["value_json"]) for r in db.execute("SELECT * FROM finance_policies")}

    def update_policies(self, values: dict[str, Any]):
        with self.connect() as db:
            for key, value in values.items():
                db.execute("INSERT OR REPLACE INTO finance_policies VALUES(?,?,?)",(key,json.dumps(value,ensure_ascii=False),_now()))
        return self.policies()

    def list_cases(self, status: str | None = None):
        sql="SELECT * FROM collection_cases"; params=[]
        if status: sql+=" WHERE status=?"; params.append(status)
        sql+=" ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,updated_at DESC"
        with self.connect() as db:
            rows=[dict(r) for r in db.execute(sql,params)]
            for row in rows:
                row["followups"]=[dict(x) for x in db.execute("SELECT * FROM collection_followups WHERE case_id=? ORDER BY created_at DESC",(row["case_id"],))]
                row["promises"]=[dict(x) for x in db.execute("SELECT * FROM payment_promises WHERE case_id=? ORDER BY created_at DESC",(row["case_id"],))]
            return rows

    def create_case(self, data: dict[str, Any]):
        case_id=str(uuid.uuid4()); now=_now()
        with self.connect() as db:
            db.execute("INSERT INTO collection_cases VALUES(?,?,?,?,?,?,?,?,?)",(case_id,data.get("counterpart_ref"),data["counterpart_name"],data.get("status","open"),data.get("priority","high"),data.get("assignee"),data.get("due_at"),now,now))
        return next(x for x in self.list_cases() if x["case_id"]==case_id)

    def update_case(self, case_id: str, data: dict[str, Any]):
        allowed=("status","priority","assignee","due_at"); updates=[]; params=[]
        for key in allowed:
            if key in data: updates.append(f"{key}=?"); params.append(data[key])
        if not updates: return False
        updates.append("updated_at=?"); params.extend([_now(),case_id])
        with self.connect() as db:
            return db.execute(f"UPDATE collection_cases SET {','.join(updates)} WHERE case_id=?",params).rowcount>0

    def add_followup(self, case_id: str, data: dict[str, Any]):
        row={"followup_id":str(uuid.uuid4()),"case_id":case_id,"channel":data.get("channel","call"),"result":data.get("result"),"note":data.get("note"),"created_by":data.get("created_by"),"created_at":_now()}
        with self.connect() as db: db.execute("INSERT INTO collection_followups VALUES(?,?,?,?,?,?,?)",tuple(row.values()))
        return row

    def add_promise(self, case_id: str, data: dict[str, Any]):
        row={"promise_id":str(uuid.uuid4()),"case_id":case_id,"amount":data.get("amount"),"promise_date":data.get("promise_date"),"status":data.get("status","pending"),"note":data.get("note"),"created_at":_now()}
        with self.connect() as db: db.execute("INSERT INTO payment_promises VALUES(?,?,?,?,?,?,?)",tuple(row.values()))
        return row

    def save_report(self, payload: dict[str, Any], trigger: str):
        report_id=str(uuid.uuid4())
        with self.connect() as db: db.execute("INSERT INTO finance_agent_reports VALUES(?,?,?,?)",(report_id,trigger,_now(),json.dumps(payload,ensure_ascii=False,default=str)))
        return report_id

    def latest_report(self):
        with self.connect() as db: row=db.execute("SELECT * FROM finance_agent_reports ORDER BY created_at DESC LIMIT 1").fetchone()
        return {**dict(row),"payload":json.loads(row["payload_json"])} if row else None

    def reports(self, limit=30):
        with self.connect() as db: rows=db.execute("SELECT report_id,trigger_type,created_at,payload_json FROM finance_agent_reports ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
        return [{"report_id":r["report_id"],"trigger_type":r["trigger_type"],"created_at":r["created_at"],"management_summary":json.loads(r["payload_json"]).get("management_summary")} for r in rows]

    def performance(self):
        with self.connect() as db: rows=[dict(r) for r in db.execute("SELECT * FROM prediction_outcomes ORDER BY outcome_at DESC")]
        evaluated=[r for r in rows if r.get("actual_value") is not None]
        mae=(sum(abs((r.get("predicted_value") or 0)-(r.get("actual_value") or 0)) for r in evaluated)/len(evaluated)) if evaluated else None
        return {"evaluated_predictions":len(evaluated),"mean_absolute_error":mae,"items":rows,"message":"پس از ثبت نتیجه واقعی، دقت پیش‌بینی اینجا محاسبه می‌شود." if not evaluated else None}

    def add_outcome(self, data: dict[str, Any]):
        row={"outcome_id":str(uuid.uuid4()),"prediction_type":data["prediction_type"],"entity_ref":data.get("entity_ref"),"predicted_value":data.get("predicted_value"),"actual_value":data.get("actual_value"),"predicted_at":data.get("predicted_at"),"outcome_at":data.get("outcome_at") or _now(),"status":data.get("status","evaluated"),"metadata_json":json.dumps(data.get("metadata") or {},ensure_ascii=False)}
        with self.connect() as db: db.execute("INSERT INTO prediction_outcomes VALUES(?,?,?,?,?,?,?,?,?)",tuple(row.values()))
        return row

    def enqueue_management_notifications(self, manager: dict[str, Any], channels: list[str]):
        analysis=manager.get("analysis") or {}; title=analysis.get("headline") or "گزارش روزانه مالی"; message=analysis.get("summary") or analysis.get("next_best_action") or "گزارش آماده است."
        created=[]
        with self.connect() as db:
            for channel in channels:
                row={"notification_id":str(uuid.uuid4()),"channel":channel,"title":title,"message":message,"status":"ready" if channel=="dashboard" else "waiting_provider","created_at":_now(),"sent_at":_now() if channel=="dashboard" else None,"error":None}
                db.execute("INSERT INTO notification_outbox VALUES(?,?,?,?,?,?,?,?)",tuple(row.values()));created.append(row)
        return created

    def notifications(self, limit=100):
        with self.connect() as db:return [dict(r) for r in db.execute("SELECT * FROM notification_outbox ORDER BY created_at DESC LIMIT ?",(limit,))]


class FinanceAgentOrchestrator:
    def __init__(self): self.store=FinanceOperationsStore()

    def run_all(self, trigger: str="manual"):
        from app.services.customer_intelligence_service import CustomerIntelligenceService
        from app.services.finance_prediction_service import FinancePredictionService
        from app.services.representative_intelligence_service import RepresentativeIntelligenceService
        from app.agents.customer_behavior_agent import CustomerBehaviorAgent
        from app.agents.finance_specialist_agents import ChequeRiskAgent,CashFlowAgent,CollectionAgent,RepresentativeAgent,FinanceManagerAgent
        policies=self.store.policies(); allowed=int(policies.get("allowed_term_days",90))
        customer=CustomerIntelligenceService(allowed_term_days=allowed).dashboard(limit=1000)
        prediction=FinancePredictionService(allowed_term_days=allowed)
        cheques=prediction.cheque_return_predictions(limit=300)
        cash=prediction.cash_shortage_forecast()
        collections=prediction.collection_priorities(limit=100)
        representatives=RepresentativeIntelligenceService().aggregate(customer.get("customers") or [])
        agents={
            "customer_behavior":CustomerBehaviorAgent().analyze(customer,trigger=trigger),
            "cheque_risk":ChequeRiskAgent().run(cheques),
            "cashflow":CashFlowAgent().run(cash),
            "collection":CollectionAgent().run(collections),
            "representative":RepresentativeAgent().run(representatives),
        }
        manager=FinanceManagerAgent().run(agents)
        notifications=self.store.enqueue_management_notifications(manager,list(policies.get("notification_channels") or ["dashboard"]))
        payload={"status":"success","data_version":"received-cheque-open-v2","generated_at":_now(),"trigger":trigger,"agents":agents,"management_summary":manager,"data":{"customer":customer,"cheques":cheques,"cashflow":cash,"collections":collections,"representatives":representatives},"policies":policies,"notifications":notifications}
        payload["report_id"]=self.store.save_report(payload,trigger)
        return payload

    def scenario(self, collection_rate: float=.75, payment_delay_days: int=0, opening_cash: float|None=None):
        from app.services.finance_prediction_service import FinancePredictionService
        base=FinancePredictionService(opening_cash=opening_cash).cash_shortage_forecast(); source=base.get("timeline") or []
        issued=[float(x.get("issued_cheques_due") or 0) for x in source]; running=0.0; timeline=[]; first=None; worst=None
        for i,row in enumerate(source):
            gross_received=float(row.get("weighted_received_cheques") or 0)/.75 if .75 else 0
            shifted=issued[i-payment_delay_days] if i>=payment_delay_days else 0
            inflow=float(row.get("historical_average_operating_inflow") or 0)+gross_received*collection_rate
            outflow=float(row.get("historical_average_operating_outflow") or 0)+shifted
            net=inflow-outflow; running+=net; cash=None if opening_cash is None else opening_cash+running
            if cash is not None and cash<0 and first is None: first=row.get("date_jalali") or row.get("date")
            if cash is not None: worst=cash if worst is None else min(worst,cash)
            timeline.append({"date":row.get("date"),"date_jalali":row.get("date_jalali"),"projected_inflow":round(inflow,2),"projected_outflow":round(outflow,2),"daily_net_change":round(net,2),"cumulative_net_change":round(running,2),"projected_cash":None if cash is None else round(cash,2),"cash_shortage":cash is not None and cash<0})
        return {"status":"success","inputs":{"collection_rate_percent":collection_rate*100,"payment_delay_days":payment_delay_days,"opening_cash":opening_cash},"first_shortage_date":first,"worst_projected_cash":worst,"timeline":timeline,"management_advice":"اگر روز منفی باقی مانده است، وصول مشتریان اولویت‌دار را جلو انداخته و پرداخت‌های غیرضروری را با تأیید مدیر مالی جابه‌جا کنید."}
