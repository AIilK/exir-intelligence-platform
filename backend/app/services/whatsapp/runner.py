"""اجرای قاعده‌ها و ارسال صف واتساپ.

- tick(): هر دقیقه از زمان‌بند صدا زده می‌شود؛ قاعده‌ای که روز و ساعتش رسیده و امروز اجرا نشده را اجرا می‌کند
  (اگر سرور سر ساعت خاموش بوده، تا CATCH_UP_HOURS ساعت بعد هم جبران می‌شود).
- پیام‌های قاعده با «ارسال خودکار» مستقیم در صف ارسال می‌روند؛ بقیه منتظر تأیید در صفحه واتساپ می‌مانند.
- worker: پیام‌های تأییدشده را یکی‌یکی با فاصله تصادفی می‌فرستد، فقط در ساعت مجاز ارسال و تا سقف روزانه.
- حالت آزمایشی (WHATSAPP_TEST_PHONE): همه پیام‌ها به همان شماره آزمایشی می‌رود، نه به مشتری.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.services.whatsapp import store
from app.services.whatsapp.composer import Composer
from app.services.whatsapp.waha_client import WahaClient, WahaError, normalize_mobile

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Tehran")
CATCH_UP_HOURS = 3
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # datetime.weekday() order

_worker_lock = threading.Lock()
_run_lock = threading.Lock()
_worker: threading.Thread | None = None
state: dict[str, Any] = {"running": False, "last_error": None, "last_sent_at": None, "stopped_reason": None}


def now() -> datetime:
    return datetime.now(TZ)


def in_send_window(at: datetime | None = None) -> bool:
    h = (at or now()).hour
    return settings.whatsapp_send_from_hour <= h < settings.whatsapp_send_to_hour


# ---------------------------------------------------------------- rules
def run_rule(rule_id: int, *, trigger: str = "manual", force: bool = False, composer: Composer | None = None) -> dict[str, Any]:
    """قاعده را اجرا و پیام‌ها را در صف می‌گذارد. force: حتی اگر امروز برای همین گیرنده‌ها پیام ساخته شده."""
    rule = store.get_rule(rule_id)
    with _run_lock:
        t0 = time.monotonic()
        composed = (composer or Composer()).compose(rule, dedupe_suffix=f"#{int(time.time())}" if force else "")
        auto = rule["auto_send"] and trigger == "scheduled"
        res = store.enqueue(composed["items"], "approved" if auto else "pending")
        result = {**composed["stats"], **res, "trigger": trigger, "queued_as": "approved" if auto else "pending",
                  "seconds": round(time.monotonic() - t0, 1)}
        store.mark_rule_run(rule_id, now().date().isoformat(), result)
    if auto and res["added"]:
        ensure_worker()
    return result


def preview_rule(rule_id: int, limit: int = 30, composer: Composer | None = None) -> dict[str, Any]:
    rule = store.get_rule(rule_id)
    composed = (composer or Composer()).compose(rule)
    for it in composed["items"]:
        if it.get("file_path"):
            Path(it["file_path"]).unlink(missing_ok=True)  # پیش‌نمایش فایل نگه نمی‌دارد
    return {"stats": composed["stats"],
            "items": [{k: v for k, v in it.items() if k not in ("file_path", "dedupe_key")} for it in composed["items"][:limit]]}


def due_rules(at: datetime) -> list[dict[str, Any]]:
    today = at.date().isoformat()
    day = DAY_KEYS[at.weekday()]
    out = []
    for r in store.list_rules():
        if not r["enabled"] or day not in r["days"] or r.get("last_run_date") == today:
            continue
        scheduled = at.replace(hour=r["hour"], minute=r["minute"], second=0, microsecond=0)
        if scheduled <= at < scheduled + timedelta(hours=CATCH_UP_HOURS):
            out.append(r)
    return out


def tick() -> None:
    """هر دقیقه: اجرای قاعده‌های سررسیده و راه انداختن ارسال صف."""
    if not settings.whatsapp_enabled:
        return
    for r in due_rules(now()):
        try:
            run_rule(r["id"], trigger="scheduled")
        except Exception as exc:  # یک قاعده خراب جلوی بقیه را نگیرد
            logger.exception("whatsapp rule %s failed", r["id"])
            store.mark_rule_run(r["id"], now().date().isoformat(), {"error": str(exc), "trigger": "scheduled"})
    if store.outbox_counts().get("approved"):
        ensure_worker()


# ---------------------------------------------------------------- sending
def _target(item: dict[str, Any]) -> tuple[str | None, str]:
    """(شماره مقصد، متن). در حالت آزمایشی پیام به شماره آزمایشی می‌رود با یک سرخط توضیحی."""
    test = normalize_mobile(settings.whatsapp_test_phone) if settings.whatsapp_test_phone else None
    if test:
        return test, f"[آزمایشی ← {item.get('recipient_name') or ''} {item.get('phone') or ''}]\n{item['message']}"
    return item.get("phone"), item["message"]


def send_item(item: dict[str, Any], client: WahaClient) -> tuple[str, str | None]:
    phone, text = _target(item)
    if not phone:
        return "failed", "شماره معتبر ندارد."
    chat = client.check_exists(phone)
    if not chat:
        return "no_whatsapp", f"شماره {phone} واتساپ ندارد."
    if item.get("file_path") and Path(item["file_path"]).exists():
        try:
            client.send_file(chat, Path(item["file_path"]).read_bytes(), item.get("file_name") or "report.xlsx", caption=text)
            return "sent", None
        except WahaError as exc:
            # بعضی نسخه‌های WAHA Core ارسال فایل ندارند؛ متن را می‌فرستیم و خطای فایل را نگه می‌داریم
            client.send_text(chat, text)
            return "sent", f"متن ارسال شد ولی فایل نه: {exc}"
    client.send_text(chat, text)
    return "sent", None


def _work() -> None:
    client = WahaClient()
    state.update(running=True, stopped_reason=None)
    try:
        while True:
            if not settings.whatsapp_enabled:
                state["stopped_reason"] = "ارسال واتساپ در تنظیمات خاموش است (WHATSAPP_ENABLED)."
                return
            if not in_send_window():
                state["stopped_reason"] = "خارج از ساعت مجاز ارسال؛ ادامه در ساعت مجاز بعدی."
                return
            if store.sent_today() >= settings.whatsapp_daily_limit:
                state["stopped_reason"] = "سقف ارسال روزانه پر شد؛ بقیه فردا ارسال می‌شود."
                return
            try:
                info = client.session_info() or {}
            except WahaError as exc:
                state.update(last_error=str(exc), stopped_reason="WAHA در دسترس نیست.")
                return
            if info.get("status") != "WORKING":
                state["stopped_reason"] = f"نشست واتساپ وصل نیست (وضعیت: {info.get('status') or 'ساخته نشده'})."
                return
            item = store.next_approved()
            if not item:
                state["stopped_reason"] = None
                return
            try:
                status, err = send_item(item, client)
            except WahaError as exc:
                status, err = "failed", str(exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("whatsapp send failed")
                status, err = "failed", str(exc)
            store.finish(item["id"], status, err)
            if status == "sent":
                state["last_sent_at"] = now().isoformat(timespec="seconds")
            if err:
                state["last_error"] = err
            time.sleep(random.uniform(settings.whatsapp_min_delay_seconds, settings.whatsapp_max_delay_seconds))
    finally:
        state["running"] = False


def ensure_worker() -> bool:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return False
        _worker = threading.Thread(target=_work, name="whatsapp-sender", daemon=True)
        _worker.start()
        return True


def send_test(phone: str, text: str) -> dict[str, Any]:
    if not settings.whatsapp_enabled:
        raise RuntimeError("ارسال واتساپ خاموش است؛ در فایل .env مقدار WHATSAPP_ENABLED=true را بگذارید.")
    target = normalize_mobile(phone)
    if not target:
        raise ValueError("شماره موبایل نامعتبر است.")
    client = WahaClient()
    chat = client.check_exists(target)
    if not chat:
        raise ValueError(f"شماره {target} واتساپ ندارد.")
    client.send_text(chat, text)
    return {"status": "sent", "to": target}


def startup() -> None:
    store.reset_stuck_sending()
