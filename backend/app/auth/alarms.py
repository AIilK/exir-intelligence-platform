"""الارم‌های هر ماژول: همان هشدارهای قاعده‌محور Agentها، فقط برای ماژول‌هایی که کاربر به آن‌ها دسترسی دارد."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import guard, store
from app.auth.modules import MODULES, alarm_agents, alarm_module

router = APIRouter(prefix="/alarms", tags=["alarms"])
LEVELS = ("critical", "high", "medium", "info")


class AlarmUpdate(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=500)


def _agent_module(user: dict[str, Any]) -> dict[str, str]:
    """agent_key ← ماژولی از کاربر که الارم زیر آن نشان داده می‌شود."""
    return {agent: mod for agent in alarm_agents(user) if (mod := alarm_module(user, agent))}


# صفحه هر ماژول فروش در داشبورد یکپارچه (ماژول‌های فروش view مالی ندارند)
UNIFIED_ROUTES = {"salesOverview": "/sales", "salesHybrid": "/hybrid", "salesTeam": "/team", "salesProducts": "/products",
                  "salesCustomers": "/files/hybrids", "salesAnalysis": "/analysis", "salesInventory": "/inventory",
                  "salesB2B": "/rahkaran", "salesExport": "/rahkaran/export"}


def _target(mod: str) -> str | None:
    """view مالی (مثلاً payables) یا مسیر داشبورد یکپارچه (با / شروع می‌شود)."""
    return (MODULES[mod]["views"] or [None])[0] or UNIFIED_ROUTES.get(mod)


@router.get("", summary="الارم‌های فعال ماژول‌های کاربر، با وضعیت شخصی هر الارم (my_status)")
def alarms(module: str | None = Query(default=None), limit: int = Query(default=300, ge=1, le=1000),
           user: dict[str, Any] = Depends(guard.current_user)):
    from app.services.agent_memory_store import AgentMemoryStore

    owned = _agent_module(user)
    if module:
        owned = {a: m for a, m in owned.items() if m == module or a in MODULES.get(module, {}).get("alarm_agents", [])}
    mine = store.alarm_states(user["id"]) if user.get("id") else {}
    out = []
    for row in AgentMemoryStore().list_alerts(status="active", limit=1000):
        mod = owned.get(row["agent_key"])
        # مدیر مالی/فروش هشدارهای تیم را با پیشوند team: تکرار می‌کنند؛ هر الارم فقط یک بار و از منبع خودش نشان داده شود.
        if not mod or str(row.get("alert_type") or "").startswith("team:"):
            continue
        state = mine.get(row["alert_key"])
        # اگر الارم بعد از «انجام شد» یک بار رفع و دوباره ظاهر شده باشد، دوباره برای همه باز است.
        if state and state["updated_at"] and str(row["first_seen"]) > state["updated_at"]:
            state = None
        p = row.get("payload") or {}
        out.append({
            "key": row["alert_key"], "agent_key": row["agent_key"], "module": mod, "module_title": MODULES[mod]["title"],
            "view": _target(mod), "level": row["level"] if row["level"] in LEVELS else "info",
            "title": row["title"], "why": (p.get("why") or [])[:3], "action": p.get("action"),
            "evidence": (p.get("evidence") or [])[:3], "first_seen": row["first_seen"], "last_seen": row["last_seen"],
            "repeats": row["consecutive_runs"], "status": row["status"],
            "my_status": state["status"] if state else "open", "my_note": state["note"] if state else None,
            "my_updated_at": state["updated_at"] if state else None,
        })
        if len(out) >= limit:
            break
    active = [a for a in out if a["my_status"] in ("open", "seen")]
    counts = {lv: sum(1 for a in active if a["level"] == lv) for lv in LEVELS}
    return {"alarms": out, "counts": counts, "total": len(active)}


@router.patch("/{alarm_key:path}", summary="وضعیت شخصی الارم: seen (دیده شد)، done (انجام شد)، dismissed (نادیده)، open (برگرداندن)")
def update(alarm_key: str, body: AlarmUpdate, user: dict[str, Any] = Depends(guard.current_user)):
    from app.services.agent_memory_store import AgentMemoryStore

    row = next((r for r in AgentMemoryStore().list_alerts(limit=5000) if r["alert_key"] == alarm_key), None)
    if not row or row["agent_key"] not in alarm_agents(user):
        raise HTTPException(404, detail="الارم پیدا نشد.")
    if not user.get("id"):
        raise HTTPException(400, detail="کاربر سیستمی وضعیت الارم ندارد.")
    try:
        store.set_alarm_state(user, alarm_key, body.status, body.note)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"status": "success"}
