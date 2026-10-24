"""API چت‌بات: POST /api/v1/chatbot/ask و GET /api/v1/chatbot/suggestions."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.chatbot import bot, knowledge

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=4000)


class AskBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    view: str | None = Field(default=None, max_length=40)


@router.post("/ask", summary="پرسش از چت‌بات (فقط درباره داده‌ها و صفحه‌های اپ)")
async def ask(body: AskBody):
    # مدل و ابزارها مسدودکننده‌اند (شبکه/SQL)؛ در threadpool اجرا شوند تا سرور قفل نشود.
    return await run_in_threadpool(bot.ask, body.message, [t.model_dump() for t in body.history], body.view)


@router.get("/suggestions", summary="پیشنهادهای آماده چت برای صفحه فعلی")
def suggestions(view: str | None = Query(default=None, max_length=40)):
    return {"suggestions": knowledge.suggestions(view),
            "pages": {k: p["title"] for k, p in knowledge.PAGES.items()}}
