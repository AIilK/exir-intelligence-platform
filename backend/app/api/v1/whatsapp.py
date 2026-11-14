"""ارسال واتساپ: /api/v1/whatsapp (فقط کاربرانی که ماژول «whatsapp» دارند؛ app/auth/modules.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import guard
from app.core.config import settings
from app.services.whatsapp import runner, store
from app.services.whatsapp.composer import KaramadSource
from app.services.whatsapp.waha_client import WahaClient, WahaError, normalize_mobile

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


class RuleBody(BaseModel):
    title: str | None = None
    kind: str | None = None
    enabled: bool | None = None
    auto_send: bool | None = None
    days: list[str] | None = None
    hour: int | None = None
    minute: int | None = None
    params: dict[str, Any] | None = None
    template: str | None = None


class IdsBody(BaseModel):
    ids: list[int] = Field(default_factory=list)
    all_pending: bool = False
    rule_id: int | None = None


class TestBody(BaseModel):
    phone: str
    text: str = Field(min_length=1, max_length=2000)


class RecipientBody(BaseModel):
    kind: str
    ref: str
    name: str | None = None
    phone: str | None = None
    opted_out: bool = False
    note: str | None = None


def _by(user: dict[str, Any]) -> str:
    return user.get("username") or "system"


def _waha(call):
    try:
        return call()
    except WahaError as exc:
        raise HTTPException(502, detail=str(exc)) from exc


@router.get("/status", summary="وضعیت اتصال WAHA، صف و تنظیمات")
def status():
    waha: dict[str, Any] = {"url": settings.waha_url, "session": settings.waha_session}
    try:
        info = WahaClient(timeout=8).session_info()
        waha.update(reachable=True, status=(info or {}).get("status") or "NOT_CREATED", me=(info or {}).get("me"))
    except WahaError as exc:
        waha.update(reachable=False, status="UNREACHABLE", error=str(exc))
    return {
        "enabled": settings.whatsapp_enabled,
        "test_phone": normalize_mobile(settings.whatsapp_test_phone) if settings.whatsapp_test_phone else None,
        "daily_limit": settings.whatsapp_daily_limit, "sent_today": store.sent_today(),
        "send_window": [settings.whatsapp_send_from_hour, settings.whatsapp_send_to_hour],
        "delay_seconds": [settings.whatsapp_min_delay_seconds, settings.whatsapp_max_delay_seconds],
        "waha": waha, "worker": runner.state, "counts": store.outbox_counts(),
    }


@router.post("/session/start", summary="ساخت/شروع نشست واتساپ در WAHA")
def session_start():
    return {"result": _waha(lambda: WahaClient().start_session())}


@router.get("/session/qr", summary="کد QR برای اسکن با واتساپ گوشی")
def session_qr():
    return _waha(lambda: WahaClient().qr())


@router.post("/session/logout", summary="خروج شماره از WAHA")
def session_logout():
    return {"result": _waha(lambda: WahaClient().logout())}


@router.get("/branches", summary="شعب کارآمد برای فیلتر قاعده‌ها")
def branches():
    try:
        return {"branches": KaramadSource().branches()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, detail=f"خواندن شعب از کارآمد ناموفق بود: {exc}") from exc


# ---------------- rules ----------------
@router.get("/rules")
def rules():
    return {"rules": store.list_rules(), "kinds": store.KINDS, "days": store.DAYS, "templates": store.DEFAULT_TEMPLATES}


@router.post("/rules")
def create_rule(body: RuleBody):
    try:
        return store.create_rule(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleBody):
    try:
        return store.update_rule(rule_id, body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(404, detail="قاعده پیدا نشد.") from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int):
    store.delete_rule(rule_id)
    return {"status": "success"}


@router.post("/rules/{rule_id}/preview", summary="پیش‌نمایش پیام‌ها بدون ذخیره و ارسال")
def preview(rule_id: int, limit: int = Query(30, ge=1, le=200)):
    try:
        return runner.preview_rule(rule_id, limit)
    except KeyError as exc:
        raise HTTPException(404, detail="قاعده پیدا نشد.") from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.post("/rules/{rule_id}/run", summary="ساختن پیام‌ها الان (برای تأیید در صف)")
def run_now(rule_id: int, force: bool = False):
    try:
        return runner.run_rule(rule_id, trigger="manual", force=force)
    except KeyError as exc:
        raise HTTPException(404, detail="قاعده پیدا نشد.") from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


# ---------------- outbox ----------------
@router.get("/outbox")
def outbox(status: str | None = None, rule_id: int | None = None, limit: int = Query(300, ge=1, le=5000)):
    return {"items": store.list_outbox(status, rule_id, limit), "counts": store.outbox_counts()}


@router.post("/outbox/approve", summary="تأیید پیام‌ها برای ارسال")
def approve(body: IdsBody, user: dict[str, Any] = Depends(guard.current_user)):
    n = store.approve_all_pending(_by(user), body.rule_id) if body.all_pending \
        else store.set_status(body.ids, "approved", ("pending", "failed"), _by(user))
    started = runner.ensure_worker() if n and settings.whatsapp_enabled else False
    return {"approved": n, "worker_started": started, "enabled": settings.whatsapp_enabled}


@router.post("/outbox/skip", summary="لغو پیام‌ها (ارسال نمی‌شوند)")
def skip(body: IdsBody, user: dict[str, Any] = Depends(guard.current_user)):
    return {"skipped": store.set_status(body.ids, "skipped", ("pending", "approved", "failed"), _by(user))}


@router.post("/outbox/send-now", summary="شروع ارسال صف تأییدشده")
def send_now():
    if not settings.whatsapp_enabled:
        raise HTTPException(400, detail="ارسال واتساپ خاموش است (WHATSAPP_ENABLED در .env).")
    return {"worker_started": runner.ensure_worker(), "worker": runner.state}


@router.get("/outbox/{item_id}/file", summary="دانلود فایل اکسل پیوست")
def outbox_file(item_id: int):
    item = store.get_item(item_id)
    if not item or not item.get("file_path") or not Path(item["file_path"]).exists():
        raise HTTPException(404, detail="فایل پیدا نشد.")
    return FileResponse(item["file_path"], filename=item.get("file_name") or "report.xlsx")


@router.post("/test", summary="ارسال یک پیام آزمایشی")
def test(body: TestBody):
    try:
        return runner.send_test(body.phone, body.text)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except WahaError as exc:
        raise HTTPException(502, detail=str(exc)) from exc


# ---------------- recipients ----------------
@router.get("/recipients")
def recipients():
    return {"recipients": store.list_recipients()}


@router.post("/recipients", summary="شماره جایگزین یا لغو ارسال برای یک مشتری/ویزیتور")
def upsert_recipient(body: RecipientBody):
    phone = None
    if body.phone:
        phone = normalize_mobile(body.phone)
        if not phone:
            raise HTTPException(400, detail="شماره موبایل نامعتبر است.")
    try:
        return store.upsert_recipient(body.kind, body.ref, body.name, phone, body.opted_out, body.note)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.delete("/recipients/{kind}/{ref}")
def delete_recipient(kind: str, ref: str):
    store.delete_recipient(kind, ref)
    return {"status": "success"}
