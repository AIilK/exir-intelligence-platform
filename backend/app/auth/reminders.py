"""یادآوری‌های شخصی هر کاربر (حیوان خانگی اپ سر وقت یادآوری می‌کند): GET/POST/PATCH/DELETE /api/v1/reminders."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import guard, store

router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    due_at: datetime | None = None


class ReminderUpdate(BaseModel):
    done: bool | None = None
    due_at: datetime | None = None
    clear_due: bool = False


def _user(user: dict[str, Any]) -> dict[str, Any]:
    if not user.get("id"):
        raise HTTPException(400, detail="کاربر سیستمی یادآوری ندارد.")
    return user


@router.get("", summary="یادآوری‌های کاربر فعلی")
def list_reminders(include_done: bool = Query(default=False), user: dict[str, Any] = Depends(guard.current_user)):
    return {"reminders": store.reminders(_user(user)["id"], include_done)}


@router.post("", summary="افزودن یادآوری")
def create(body: ReminderCreate, user: dict[str, Any] = Depends(guard.current_user)):
    try:
        return store.add_reminder(_user(user), body.text, body.due_at)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.patch("/{reminder_id}", summary="انجام شد / بعداً یادآوری کن")
def update(reminder_id: int, body: ReminderUpdate, user: dict[str, Any] = Depends(guard.current_user)):
    try:
        return store.update_reminder(_user(user)["id"], reminder_id, done=body.done, due_at=body.due_at, clear_due=body.clear_due)
    except KeyError as exc:
        raise HTTPException(404, detail="یادآوری پیدا نشد.") from exc


@router.delete("/{reminder_id}", summary="حذف یادآوری")
def remove(reminder_id: int, user: dict[str, Any] = Depends(guard.current_user)):
    store.delete_reminder(_user(user)["id"], reminder_id)
    return {"status": "success"}
