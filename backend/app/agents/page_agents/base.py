"""پایه Page Agent: هر صفحه داشبورد یک Agent گزارشی با هشدار، پیش‌بینی و حافظه (V171).

جریان اجرا:
  collect() → اعداد زنده از سرویس‌های موجود
  memory    → اعداد اجرای قبل و ~۷ روز قبل از AgentMemoryStore
  rules()   → تحلیل قطعی بدون LLM (تیتر، خلاصه، هشدار، پیش‌بینی، اقدام)
  narrate() → اگر کلید OpenAI باشد فقط متن تیتر/خلاصه/نشانه‌ها بازنویسی می‌شود؛
              اعداد، هشدارها، پیش‌بینی‌ها و اقدام‌ها همیشه از قواعد ماشینی می‌آیند.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from app.agents.finance_decision_agents import _toman
from app.core.config import settings
from app.services.agent_memory_store import AgentMemoryStore

LEVEL_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}


def toman(value_rial: Any) -> str:
    try:
        return _toman(float(value_rial or 0))
    except (TypeError, ValueError):
        return "—"


def fa_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    text = f"{number:,.0f}" if abs(number - round(number)) < 1e-9 else f"{number:,.1f}"
    return text.translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


def alert(
    alert_type: str,
    level: str,
    title: str,
    why: list[str],
    action: str,
    *,
    entity_ref: Any = None,
    evidence: list[dict[str, Any]] | None = None,
    metric: Any = None,
) -> dict[str, Any]:
    return {
        "type": alert_type,
        "level": level,
        "title": title,
        "why": [str(x) for x in why if x and str(x).strip()],
        "action": action,
        "entity_ref": None if entity_ref is None else str(entity_ref),
        "evidence": evidence or [],
        "metric": metric,
    }


def prediction(
    metric: str,
    label: str,
    horizon: str,
    value: Any,
    confidence: str,
    basis: str,
    *,
    unit: str = "rial",
    display: str | None = None,
) -> dict[str, Any]:
    if display is None:
        display = toman(value) if unit == "rial" else fa_number(value) + (" روز" if unit == "days" else "")
    return {
        "metric": metric, "label": label, "horizon": horizon, "value": value, "unit": unit,
        "display": display, "confidence": confidence, "basis": basis,
    }


def action(text: str, why: str, owner: str, priority: str, deadline: str, effect: str = "") -> dict[str, str]:
    return {"action": text, "why": why, "owner": owner, "priority": priority,
            "deadline": deadline, "expected_effect": effect}


def change_phrase(delta: dict[str, Any] | None, unit: str = "rial") -> str:
    """«۱۲٪ بیشتر از اجرای قبل» از یک ردیف deltas."""

    info = (delta or {}).get("vs_previous")
    if not info or not info.get("change"):
        return ""
    change = info["change"]
    direction = "بیشتر" if change > 0 else "کمتر"
    amount = toman(abs(change)) if unit == "rial" else fa_number(abs(change))
    percent = f" ({fa_number(abs(info['percent']))}٪)" if info.get("percent") is not None else ""
    return f"{amount}{percent} {direction} از اجرای قبل"


class PageAgent:
    key = "page_agent"
    page = ""
    name = "Page Agent"
    role_fa = ""
    prompt_fa = ""
    #: metric key → Persian label; tracked across runs for trend and deltas.
    tracked_metrics: dict[str, str] = {}
    #: metric drawn as the memory sparkline on the page card.
    primary_metric = ""
    primary_unit = "rial"
    #: Wrapped legacy agents already call the LLM themselves.
    narrate_with_llm = True

    def __init__(self, store: AgentMemoryStore | None = None, context: Any = None):
        from app.agents.page_agents.context import AgentRunContext

        self.store = store or AgentMemoryStore()
        self.ctx = context or AgentRunContext()

    # ------------------------------------------------------------ overridables
    def collect(self) -> dict[str, Any]:
        raise NotImplementedError

    def rules(self, data: dict[str, Any], memory: dict[str, Any], deltas: dict[str, dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    # ---------------------------------------------------------------- running
    def run(self, trigger: str = "manual") -> dict[str, Any]:
        started = time.monotonic()
        generated_at = datetime.now(timezone.utc)
        base = {
            "agent_key": self.key, "page": self.page, "name": self.name, "role": self.role_fa,
            "generated_at": generated_at.isoformat(), "trigger": trigger,
            "primary_metric": self.primary_metric, "primary_unit": self.primary_unit,
        }
        try:
            data = self.collect()
        except Exception as exc:  # noqa: BLE001 — one failing source must not stop the team
            result = {**base, "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                      "duration_seconds": round(time.monotonic() - started, 1)}
            self.store.save_run(agent_key=self.key, trigger=trigger, status="error", mode=None,
                                metrics={}, result=result, error=result["error"])
            return result

        metrics = data.get("metrics") or {}
        memory = self.store.memory_context(self.key, self.tracked_metrics, now=generated_at)
        delta_rows = AgentMemoryStore.deltas(metrics, memory, self.tracked_metrics)
        deltas = {row["metric"]: row for row in delta_rows}
        analysis = self.rules(data, memory, deltas)
        alerts = sorted(analysis.pop("alerts", []), key=lambda x: LEVEL_ORDER.get(x["level"], 9))
        predictions = analysis.pop("predictions", [])
        analysis.setdefault("management_status", self._status(alerts))
        mode, fallback_reason = "rules", None
        if self.narrate_with_llm:
            mode, fallback_reason = self._narrate(analysis, metrics, alerts, predictions, delta_rows, memory)
        else:
            mode = data.get("mode") or "rules"

        result = {
            **base,
            "status": "success",
            "mode": mode,
            "fallback_reason": fallback_reason,
            "metrics": metrics,
            "analysis": analysis,
            "predictions": predictions,
            "memory": {
                "run_count": memory["run_count"],
                "previous_at": (memory.get("previous") or {}).get("at"),
                "week_ago_at": (memory.get("week_ago") or {}).get("at"),
                "deltas": delta_rows,
            },
            "duration_seconds": round(time.monotonic() - started, 1),
            # سازگاری با AgentPanel و کلیدهای قدیمی /agents/latest
            "metadata": {"agent_name": self.name, "role": self.role_fa, "mode": mode,
                         "generated_at": generated_at.isoformat()},
        }
        run = self.store.save_run(agent_key=self.key, trigger=trigger, status="success", mode=mode,
                                  metrics=metrics, result={**result, "alerts": alerts}, created_at=generated_at)
        result["run_id"] = run["run_id"]
        result["alerts"] = self.store.upsert_alerts(
            agent_key=self.key, page=self.page, alerts=alerts, run_id=run["run_id"],
            previous_run_id=(memory.get("previous") or {}).get("run_id"), seen_at=generated_at,
        )
        # نتیجه نهایی (با شمارنده تکرار هشدارها) جایگزین نسخه اولیه ذخیره‌شده می‌شود.
        with self.store.connect() as db:
            db.execute("UPDATE agent_runs SET result_json=? WHERE run_id=?",
                       (json.dumps(result, ensure_ascii=False, default=str), run["run_id"]))
        return result

    @staticmethod
    def _status(alerts: list[dict[str, Any]]) -> str:
        levels = {item["level"] for item in alerts}
        if "critical" in levels:
            return "critical"
        if levels & {"high", "medium"}:
            return "attention"
        return "healthy"

    def _narrate(
        self,
        analysis: dict[str, Any],
        metrics: dict[str, Any],
        alerts: list[dict[str, Any]],
        predictions: list[dict[str, Any]],
        deltas: list[dict[str, Any]],
        memory: dict[str, Any],
    ) -> tuple[str, str | None]:
        if not settings.openai_api_key:
            return "rules", "کلید OpenAI تنظیم نشده است"
        try:
            from openai import OpenAI

            prompt = f"""
تو {self.name} شرکت اکسیر کادوس هستی؛ گزارش‌دهنده صفحه «{self.page}». نقش: {self.role_fa}.
{self.prompt_fa}
فقط از اعداد و واقعیت‌های JSON زیر استفاده کن؛ عدد، نام، درصد یا رویداد جدید نساز.
حافظه تو اعداد اجرای قبلی و ~۷ روز قبل است (deltas)؛ اگر تغییری معنادار است آن را در خلاصه بگو.
مخاطب مدیرعامل و مدیر مالی است: فارسی روان، مبالغ به تومان خوانا، بدون نام جدول/فیلد انگلیسی.
فقط JSON معتبر با کلیدهای headline (یک جمله)، summary (حداکثر ۳ جمله)، good_signals (آرایه)،
risks (آرایه) و next_best_action (یک جمله) برگردان.
{json.dumps({"draft": analysis, "metrics": metrics, "alerts": alerts, "predictions": predictions,
             "deltas": deltas, "previous_run_at": (memory.get("previous") or {}).get("at")},
            ensure_ascii=False, default=str)}
"""
            raw = OpenAI(api_key=settings.openai_api_key).responses.create(
                model=settings.openai_model, input=prompt,
            ).output_text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            text = json.loads(raw)
            for key in ("headline", "summary", "next_best_action"):
                if isinstance(text.get(key), str) and text[key].strip():
                    analysis[key] = text[key].strip()
            for key in ("good_signals", "risks"):
                if isinstance(text.get(key), list):
                    analysis[key] = [str(x) for x in text[key] if str(x).strip()][:6]
            return "llm", None
        except Exception as exc:  # noqa: BLE001
            return "rules", f"{type(exc).__name__}: {str(exc)[:160]}"
