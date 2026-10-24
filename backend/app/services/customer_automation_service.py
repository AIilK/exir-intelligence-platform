from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.customer_intelligence_service import CustomerIntelligenceService
from app.services.representative_intelligence_service import RepresentativeIntelligenceService
from app.agents.customer_behavior_agent import CustomerBehaviorAgent


class CustomerAutomationStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or settings.customer_intelligence_history_db)
        self._init()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init(self):
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS automation_runs(
              run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
              status TEXT NOT NULL, trigger_type TEXT NOT NULL, error TEXT, payload_json TEXT);
            CREATE TABLE IF NOT EXISTS alert_state(
              alert_id TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
              level TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
              assignee TEXT, resolved_at TEXT, payload_json TEXT NOT NULL);
            """)

    def save_run(self, run_id: str, trigger: str, status: str, payload: dict | None = None, error: str | None = None):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO automation_runs VALUES(?,?,?,?,?,?,?)", (run_id, now, now, status, trigger, error, json.dumps(payload, ensure_ascii=False, default=str) if payload else None))

    def upsert_alerts(self, alerts: list[dict[str, Any]]):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            active_ids = [str(a["id"]) for a in alerts]
            if active_ids:
                placeholders = ",".join("?" for _ in active_ids)
                db.execute(
                    f"""UPDATE alert_state
                    SET status='resolved', resolved_at=?
                    WHERE status='open'
                      AND alert_id NOT IN ({placeholders})""",
                    [now, *active_ids],
                )
            else:
                db.execute(
                    """UPDATE alert_state
                    SET status='resolved', resolved_at=?
                    WHERE status='open'""",
                    (now,),
                )
            for a in alerts:
                existing = db.execute("SELECT first_seen_at,status,assignee FROM alert_state WHERE alert_id=?", (a["id"],)).fetchone()
                first, _, assignee = existing if existing else (now, "open", None)
                db.execute("""INSERT OR REPLACE INTO alert_state
                (alert_id,first_seen_at,last_seen_at,level,title,status,assignee,resolved_at,payload_json)
                VALUES(?,?,?,?,?,?,?,?,?)""", (a["id"], first, now, a["level"], a["title"], "open", assignee, None, json.dumps(a, ensure_ascii=False, default=str)))

    def list_alerts(self, status: str = "open", limit: int = 100):
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM alert_state WHERE status=? ORDER BY CASE level WHEN 'critical' THEN 1 ELSE 2 END,last_seen_at DESC LIMIT ?", (status, limit)).fetchall()
            return [{**dict(r), "payload": json.loads(r["payload_json"])} for r in rows]

    def update_alert(self, alert_id: str, status: str, assignee: str | None = None):
        resolved = datetime.now(timezone.utc).isoformat() if status == "resolved" else None
        with self._connect() as db:
            cur = db.execute("UPDATE alert_state SET status=?,assignee=COALESCE(?,assignee),resolved_at=? WHERE alert_id=?", (status, assignee, resolved, alert_id))
            return cur.rowcount > 0

    def recent_runs(self, limit: int = 20):
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT run_id,started_at,finished_at,status,trigger_type,error FROM automation_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]

    def latest_payload(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM automation_runs WHERE status='success' AND payload_json IS NOT NULL ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return json.loads(row[0]) if row and row[0] else None


class CustomerAutomationService:
    def __init__(self):
        self.store = CustomerAutomationStore()

    def run(self, trigger: str = "manual") -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        try:
            dashboard = CustomerIntelligenceService().dashboard(limit=1000)
            representatives = RepresentativeIntelligenceService().aggregate(dashboard["customers"])
            agent_result = CustomerBehaviorAgent().analyze(dashboard, trigger=trigger)
            payload = {
                **dashboard,
                "human_analysis": agent_result["analysis"],
                "agent": agent_result,
                "representative_intelligence": representatives,
                "run_id": run_id,
                "trigger": trigger,
            }
            self.store.upsert_alerts(dashboard["alerts"])
            self.store.save_run(run_id, trigger, "success", payload)
            return payload
        except Exception as exc:
            self.store.save_run(run_id, trigger, "failed", error=str(exc))
            raise
