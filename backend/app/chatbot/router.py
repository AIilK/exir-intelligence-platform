"""API چت‌بات: پرسش، پیشنهادها، تاریخچه و حافظه هر کاربر — همه محدود به ماژول‌های همان کاربر."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.auth import guard, store
from app.auth.modules import allowed_views, chat_tools, module_titles
from app.chatbot import bot, knowledge

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=4000)


class AskBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    view: str | None = Field(default=None, max_length=40)


class MemoryBody(BaseModel):
    content: str = Field(min_length=1, max_length=500)


def _views(user: dict[str, Any]) -> set[str] | None:
    return None if user.get("is_admin") else set(allowed_views(user))


def _scope(user: dict[str, Any]) -> bot.Scope:
    memories = [m["content"] for m in store.memories(user["id"])] if user.get("id") else []
    return bot.Scope(user=user, views=_views(user), tools=chat_tools(user), memories=memories,
                     module_titles=[] if user.get("is_admin") else module_titles(user))


def _ask(body: AskBody, user: dict[str, Any]) -> dict[str, Any]:
    out = bot.ask(body.message, [t.model_dump() for t in body.history], body.view, _scope(user))
    if user.get("id"):
        store.save_chat(user, "user", body.message, body.view)
        store.save_chat(user, "assistant", out.get("answer", ""), body.view)
    return out


@router.post("/ask", summary="پرسش از چت‌بات (فقط درباره داده‌ها و صفحه‌های مجاز همین کاربر)")
async def ask(body: AskBody, user: dict[str, Any] = Depends(guard.current_user)):
    # مدل و ابزارها مسدودکننده‌اند (شبکه/SQL)؛ در threadpool اجرا شوند تا سرور قفل نشود.
    return await run_in_threadpool(_ask, body, user)


@router.get("/suggestions", summary="پیشنهادهای آماده چت برای صفحه فعلی")
def suggestions(view: str | None = Query(default=None, max_length=40), user: dict[str, Any] = Depends(guard.current_user)):
    views = _views(user)
    return {"suggestions": knowledge.suggestions(view, views),
            "pages": {k: p["title"] for k, p in knowledge.visible_pages(views).items()}}


@router.get("/history", summary="تاریخچه گفتگوی کاربر فعلی")
def history(user: dict[str, Any] = Depends(guard.current_user)):
    return {"messages": store.chat_history(user["id"]) if user.get("id") else []}


@router.post("/new", summary="شروع گفتگوی جدید (گفتگوهای قبلی در تاریخچه می‌مانند)")
def new_chat(user: dict[str, Any] = Depends(guard.current_user)):
    if user.get("id"):
        store.start_new_chat(user)
    return {"status": "success"}


@router.get("/conversations", summary="تاریخچه همه گفتگوهای کاربر فعلی")
def conversations(user: dict[str, Any] = Depends(guard.current_user)):
    return {"conversations": store.chat_conversations(user["id"]) if user.get("id") else []}


@router.delete("/history", summary="پاک کردن کامل تاریخچه گفتگوهای خود (حافظه بلندمدت می‌ماند)")
def clear_history(user: dict[str, Any] = Depends(guard.current_user)):
    if user.get("id"):
        store.clear_chat(user["id"])
    return {"status": "success"}


@router.get("/memory", summary="حافظه ماندگار چت‌بات درباره کاربر فعلی")
def memory(user: dict[str, Any] = Depends(guard.current_user)):
    return {"memories": store.memories(user["id"]) if user.get("id") else [], "full_name": user.get("full_name")}


@router.post("/memory", summary="افزودن دستی یک نکته به حافظه")
def add_memory(body: MemoryBody, user: dict[str, Any] = Depends(guard.current_user)):
    if not user.get("id"):
        return {"saved": False}
    return store.add_memory(user, body.content)


@router.delete("/memory/{memory_id}", summary="حذف یک نکته از حافظه")
def delete_memory(memory_id: int, user: dict[str, Any] = Depends(guard.current_user)):
    if user.get("id"):
        store.delete_memory(user["id"], memory_id)
    return {"status": "success"}
