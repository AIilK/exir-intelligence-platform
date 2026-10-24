from datetime import datetime, timedelta, timezone

from app.agents.page_agents.base import PageAgent, alert, prediction
from app.services.agent_memory_store import AgentMemoryStore

NOW = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)
TRACKED = {"amount": "مبلغ"}


def _store(tmp_path):
    return AgentMemoryStore(str(tmp_path / "memory.db"))


def _save(store, value, at):
    return store.save_run(agent_key="a", trigger="test", status="success", mode="rules",
                          metrics={"amount": value}, result={}, created_at=at)


def test_deltas_against_previous_and_week_ago(tmp_path):
    store = _store(tmp_path)
    _save(store, 100, NOW - timedelta(days=8))
    _save(store, 150, NOW - timedelta(days=1))
    memory = store.memory_context("a", TRACKED, now=NOW)
    delta = AgentMemoryStore.deltas({"amount": 180}, memory, TRACKED)[0]
    assert delta["vs_previous"]["change"] == 30
    assert delta["vs_previous"]["percent"] == 20.0
    assert delta["vs_week_ago"]["base"] == 100
    assert [p["value"] for p in memory["series"]["amount"]] == [100, 150]


def test_first_run_has_no_deltas(tmp_path):
    memory = _store(tmp_path).memory_context("a", TRACKED, now=NOW)
    assert memory["previous"] is None
    assert AgentMemoryStore.deltas({"amount": 5}, memory, TRACKED)[0]["vs_previous"] is None


def _upsert(store, alerts, run, previous):
    return store.upsert_alerts(agent_key="a", page="p", alerts=alerts, run_id=run, previous_run_id=previous)


def test_alert_streak_resets_and_auto_resolves(tmp_path):
    store = _store(tmp_path)
    item = alert("overdue", "high", "t", ["why"], "act")
    assert _upsert(store, [item], "r1", None)[0]["consecutive_runs"] == 1
    assert _upsert(store, [item], "r2", "r1")[0]["consecutive_runs"] == 2
    _upsert(store, [], "r3", "r2")  # not seen any more → resolved
    assert store.list_alerts(status="resolved")[0]["alert_key"] == "a:overdue:-"
    again = _upsert(store, [item], "r4", "r3")[0]
    assert again["consecutive_runs"] == 1 and again["status"] == "open"


def test_dismissed_alert_stays_dismissed_while_it_repeats(tmp_path):
    store = _store(tmp_path)
    item = alert("x", "medium", "t", [], "act", entity_ref=7)
    _upsert(store, [item], "r1", None)
    store.update_alert("a:x:7", "dismissed")
    repeated = _upsert(store, [item], "r2", "r1")[0]
    assert repeated["status"] == "dismissed" and repeated["consecutive_runs"] == 2


class _DummyAgent(PageAgent):
    key = "dummy"
    page = "صفحه آزمایشی"
    tracked_metrics = TRACKED
    narrate_with_llm = False

    def __init__(self, store, value):
        super().__init__(store)
        self.value = value

    def collect(self):
        return {"metrics": {"amount": self.value}}

    def rules(self, data, memory, deltas):
        return {"headline": "h", "summary": "s",
                "alerts": [alert("big", "critical", "big", ["w"], "a")] if self.value > 10 else [],
                "predictions": [prediction("amount", "مبلغ", "۷ روز", self.value, "low", "test")]}


def test_page_agent_run_persists_memory_and_status(tmp_path):
    store = _store(tmp_path)
    first = _DummyAgent(store, 20).run("test")
    assert first["status"] == "success"
    assert first["analysis"]["management_status"] == "critical"
    second = _DummyAgent(store, 5).run("test")
    assert second["memory"]["deltas"][0]["vs_previous"]["change"] == -15
    assert second["analysis"]["management_status"] == "healthy"
    assert store.list_alerts(agent_key="dummy", status="resolved")


def test_page_agent_collect_failure_is_isolated(tmp_path):
    class Broken(_DummyAgent):
        def collect(self):
            raise RuntimeError("SQL down")

    result = Broken(_store(tmp_path), 0).run("test")
    assert result["status"] == "error" and "SQL down" in result["error"]
