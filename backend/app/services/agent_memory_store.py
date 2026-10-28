"""حافظه Page Agentها: اجراهای قبلی، روند اعداد و تکرار هشدارها (V171).

روی همان SQLite عملیات مالی (settings.customer_intelligence_history_db) ذخیره می‌شود.
- agent_runs: هر اجرای هر Agent با اعداد، تحلیل، هشدار و پیش‌بینی.
- agent_alerts: هشدار یکتا با کلید agent_key:type:entity_ref؛ اگر در اجراهای پشت‌سرهم تکرار شود
  شمارنده «اجرای متوالی» زیاد می‌شود و اگر دیگر دیده نشود خودکار «رفع‌شده» علامت می‌خورد.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

SERIES_LENGTH = 30
OPEN_STATUSES = ("open", "acknowledged")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class AgentMemoryStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or settings.customer_intelligence_history_db)
        self._init()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs(
                    run_id TEXT PRIMARY KEY, agent_key TEXT NOT NULL, created_at TEXT NOT NULL,
                    trigger_type TEXT NOT NULL, status TEXT NOT NULL, mode TEXT,
                    metrics_json TEXT NOT NULL, result_json TEXT NOT NULL, error TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_agent_runs_key_time ON agent_runs(agent_key, created_at DESC);
                CREATE TABLE IF NOT EXISTS agent_alerts(
                    alert_key TEXT PRIMARY KEY, agent_key TEXT NOT NULL, page TEXT, alert_type TEXT NOT NULL,
                    level TEXT NOT NULL, title TEXT NOT NULL, entity_ref TEXT,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_run_id TEXT,
                    consecutive_runs INTEGER NOT NULL, total_runs INTEGER NOT NULL,
                    status TEXT NOT NULL, status_updated_at TEXT, payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_agent_alerts_status ON agent_alerts(status, level);
                """
            )

    # ------------------------------------------------------------------ runs
    def save_run(
        self,
        *,
        agent_key: str,
        trigger: str,
        status: str,
        mode: str | None,
        metrics: dict[str, Any],
        result: dict[str, Any],
        error: str | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        run = {
            "run_id": str(uuid.uuid4()),
            "agent_key": agent_key,
            "created_at": (created_at or _now()).isoformat(),
            "trigger_type": trigger,
            "status": status,
            "mode": mode,
        }
        with self.connect() as db:
            db.execute(
                "INSERT INTO agent_runs VALUES(?,?,?,?,?,?,?,?,?)",
                (run["run_id"], agent_key, run["created_at"], trigger, status, mode,
                 _dumps(metrics), _dumps(result), error),
            )
        return run

    def runs(self, agent_key: str, limit: int = SERIES_LENGTH, include_result: bool = False) -> list[dict[str, Any]]:
        columns = "run_id, agent_key, created_at, trigger_type, status, mode, metrics_json, error"
        if include_result:
            columns += ", result_json"
        with self.connect() as db:
            rows = db.execute(
                f"SELECT {columns} FROM agent_runs WHERE agent_key=? AND status='success' "
                "ORDER BY created_at DESC LIMIT ?",
                (agent_key, limit),
            ).fetchall()
        out = []
        for row in rows:
            item = {k: row[k] for k in row.keys() if not k.endswith("_json")}
            item["metrics"] = json.loads(row["metrics_json"])
            if include_result:
                item["result"] = json.loads(row["result_json"])
            out.append(item)
        return out

    def latest_result(self, agent_key: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT result_json FROM agent_runs WHERE agent_key=? ORDER BY created_at DESC LIMIT 1",
                (agent_key,),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def latest_results(self) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT r.agent_key, r.result_json FROM agent_runs r
                JOIN (SELECT agent_key, MAX(created_at) AS m FROM agent_runs GROUP BY agent_key) x
                  ON x.agent_key = r.agent_key AND x.m = r.created_at
                """
            ).fetchall()
        return {row["agent_key"]: json.loads(row["result_json"]) for row in rows}

    # ---------------------------------------------------------------- memory
    def memory_context(
        self,
        agent_key: str,
        tracked: dict[str, str],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Previous numbers for this agent: last run, ~7 days ago, and the recent series."""

        now = now or _now()
        history = self.runs(agent_key, limit=200)
        previous = history[0] if history else None
        week_cutoff = (now - timedelta(days=6, hours=12)).isoformat()
        week_ago = next((run for run in history if run["created_at"] <= week_cutoff), None)
        series = {
            metric: [
                {"at": run["created_at"], "value": _number(run["metrics"].get(metric))}
                for run in reversed(history[:SERIES_LENGTH])
            ]
            for metric in tracked
        }
        return {
            "run_count": len(history),
            "previous": {"run_id": previous["run_id"], "at": previous["created_at"], "metrics": previous["metrics"]}
            if previous else None,
            "week_ago": {"run_id": week_ago["run_id"], "at": week_ago["created_at"], "metrics": week_ago["metrics"]}
            if week_ago else None,
            "series": series,
        }

    @staticmethod
    def deltas(
        metrics: dict[str, Any],
        memory: dict[str, Any],
        tracked: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Change of each tracked metric vs the previous run and vs ~7 days ago."""

        out = []
        for metric, label in tracked.items():
            current = _number(metrics.get(metric))
            item: dict[str, Any] = {"metric": metric, "label": label, "current": current}
            for ref in ("previous", "week_ago"):
                base = _number(((memory.get(ref) or {}).get("metrics") or {}).get(metric))
                if current is None or base is None:
                    item[f"vs_{ref}"] = None
                    continue
                change = current - base
                item[f"vs_{ref}"] = {
                    "base": base,
                    "change": change,
                    "percent": round(change / abs(base) * 100, 1) if base else None,
                    "at": (memory.get(ref) or {}).get("at"),
                }
            out.append(item)
        return out

    # ---------------------------------------------------------------- alerts
    def upsert_alerts(
        self,
        *,
        agent_key: str,
        page: str,
        alerts: list[dict[str, Any]],
        run_id: str,
        previous_run_id: str | None,
        seen_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Store this run's alerts; count consecutive runs; auto-resolve alerts no longer seen."""

        seen = (seen_at or _now()).isoformat()
        enriched: list[dict[str, Any]] = []
        current_keys: set[str] = set()
        with self.connect() as db:
            for alert in alerts:
                key = f"{agent_key}:{alert['type']}:{alert.get('entity_ref') or '-'}"
                current_keys.add(key)
                existing = db.execute("SELECT * FROM agent_alerts WHERE alert_key=?", (key,)).fetchone()
                if existing:
                    # هشداری که کاربر نادیده گرفته (dismissed) تا وقتی پشت‌سرهم تکرار شود ساکت می‌ماند.
                    continuing = (
                        existing["last_run_id"] == previous_run_id
                        and existing["status"] != "resolved"
                    )
                    consecutive = existing["consecutive_runs"] + 1 if continuing else 1
                    first_seen = existing["first_seen"] if continuing else seen
                    status = existing["status"] if continuing else "open"
                    db.execute(
                        """UPDATE agent_alerts SET level=?, title=?, page=?, last_seen=?, last_run_id=?,
                           consecutive_runs=?, total_runs=total_runs+1, first_seen=?, status=?, payload_json=?
                           WHERE alert_key=?""",
                        (alert["level"], alert["title"], page, seen, run_id, consecutive,
                         first_seen, status, _dumps(alert), key),
                    )
                    total = existing["total_runs"] + 1
                else:
                    consecutive, first_seen, status, total = 1, seen, "open", 1
                    db.execute(
                        "INSERT INTO agent_alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, agent_key, page, alert["type"], alert["level"], alert["title"],
                         alert.get("entity_ref"), seen, seen, run_id, 1, 1, "open", None, _dumps(alert)),
                    )
                enriched.append({
                    **alert,
                    "alert_key": key,
                    "first_seen": first_seen,
                    "consecutive_runs": consecutive,
                    "total_runs": total,
                    "status": status,
                })
            stale = db.execute(
                "SELECT alert_key FROM agent_alerts WHERE agent_key=? AND status IN ('open','acknowledged')",
                (agent_key,),
            ).fetchall()
            for row in stale:
                if row["alert_key"] not in current_keys:
                    db.execute(
                        "UPDATE agent_alerts SET status='resolved', status_updated_at=? WHERE alert_key=?",
                        (seen, row["alert_key"]),
                    )
        return enriched

    def list_alerts(
        self,
        *,
        agent_key: str | None = None,
        page: str | None = None,
        status: str | None = None,
        level: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM agent_alerts WHERE 1=1"
        params: list[Any] = []
        for column, value in (("agent_key", agent_key), ("page", page), ("level", level)):
            if value:
                sql += f" AND {column}=?"
                params.append(value)
        if status == "active":
            sql += " AND status IN ('open','acknowledged')"
        elif status:
            sql += " AND status=?"
            params.append(status)
        sql += (" ORDER BY CASE level WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,"
                " consecutive_runs DESC, last_seen DESC LIMIT ?")
        params.append(limit)
        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [{**{k: row[k] for k in row.keys() if k != "payload_json"},
                 "payload": json.loads(row["payload_json"])} for row in rows]

    def update_alert(self, alert_key: str, status: str) -> bool:
        if status not in {"open", "acknowledged", "dismissed", "resolved"}:
            raise ValueError("وضعیت هشدار نامعتبر است.")
        with self.connect() as db:
            return db.execute(
                "UPDATE agent_alerts SET status=?, status_updated_at=? WHERE alert_key=?",
                (status, _now().isoformat(), alert_key),
            ).rowcount > 0
