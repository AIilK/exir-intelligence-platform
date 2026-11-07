"""به‌روزرسانی الارم‌ها و گزارش مدیر: قواعد الارم همه ماژول‌ها، سپس Agent مدیر (روزانه، دکمه به‌روزرسانی، بعد از ورود فایل کارآمد)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from app.agents.page_agents import PAGE_AGENT_CLASSES, ManagerAgent, SalesManagerAgent
from app.agents.page_agents.context import AgentRunContext
from app.services.agent_memory_store import AgentMemoryStore

MAX_WORKERS = 4
_run_all_lock = threading.Lock()


class PageAgentOrchestrator:
    def __init__(self, store: AgentMemoryStore | None = None):
        self.store = store or AgentMemoryStore()

    def run_all(self, trigger: str = "manual") -> dict[str, Any]:
        if not _run_all_lock.acquire(blocking=False):
            raise RuntimeError("اجرای همه Agentها همین حالا در جریان است؛ چند دقیقه بعد دوباره امتحان کنید.")
        try:
            return self._run_all(trigger)
        finally:
            _run_all_lock.release()

    def _run_all(self, trigger: str) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        context = AgentRunContext()

        def run_one(cls: type) -> tuple[str, dict[str, Any]]:
            return cls.key, cls(self.store, context).run(trigger)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            team = dict(pool.map(run_one, PAGE_AGENT_CLASSES))
        manager = ManagerAgent(self.store, context, team_results=team).run(trigger)
        # Sales team (sales_agents.py) after the finance team; it must never break the finance run.
        try:
            sales = SalesManagerAgent(self.store, context).run(trigger)
        except Exception as exc:  # noqa: BLE001
            sales = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        # داده‌ای که صفحات فعلی از آخرین گزارش می‌خوانند (فهرست مشتریان، نقدینگی، چک‌ها، نمایندگان).
        data: dict[str, Any] = {}
        for key, getter in (("customer", context.customer), ("cashflow", context.cash),
                            ("cheques", context.cheque_predictions), ("representatives", context.representatives),
                            ("collections", context.collections), ("cheque_portfolio", context.cheque_portfolio)):
            try:
                data[key] = getter()
            except Exception as exc:  # noqa: BLE001
                data[key] = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

        payload = {
            "status": "success",
            "data_version": "page-agents-v171",
            "generated_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
            "agents": team,
            "management_summary": manager,
            "sales_summary": sales,
            "data": data,
            "summary": {
                "agents_total": len(team) + 1,
                "agents_failed": [k for k, v in team.items() if v.get("status") != "success"],
                "critical_alerts": sum(1 for r in team.values() for a in (r.get("alerts") or []) if a["level"] == "critical"),
            },
        }
        # سازگاری با /agents/latest و «تاریخچه و مقایسه»: همان قالب گزارش قدیمی ذخیره می‌شود.
        from app.services.finance_operations_service import FinanceOperationsStore
        store = FinanceOperationsStore()
        payload["notifications"] = store.enqueue_management_notifications(
            manager, list(store.policies().get("notification_channels") or ["dashboard"]))
        payload["report_id"] = store.save_report(payload, trigger)
        return payload
