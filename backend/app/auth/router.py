"""API ورود، کاربر فعلی، تنظیمات ظاهری و مدیریت کاربران (فقط مدیر سیستم)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.auth import guard, store
from app.auth.modules import allowed_views, catalog, user_modules
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9_.\-]+$")
PASSWORD = Field(min_length=6, max_length=128)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=128)


class SetupBody(BaseModel):
    username: str = USERNAME
    full_name: str = Field(min_length=2, max_length=120)
    password: str = PASSWORD


class UserCreate(BaseModel):
    username: str = USERNAME
    full_name: str = Field(min_length=2, max_length=120)
    password: str = PASSWORD
    modules: list[str] = Field(default_factory=list)
    is_admin: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    modules: list[str] | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


class Preferences(BaseModel):
    theme: str | None = Field(default=None, max_length=30)
    wallpaper: str | None = Field(default=None, max_length=30)
    # حیوان خانگی اپ: کلید حیوان («none» یعنی خاموش) و اسمی که کاربر رویش گذاشته
    pet: str | None = Field(default=None, max_length=30)
    pet_name: str | None = Field(default=None, max_length=30)


def _profile(user: dict[str, Any]) -> dict[str, Any]:
    return {"user": user, "modules": user_modules(user), "views": allowed_views(user), "catalog": catalog()}


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(guard.COOKIE_NAME, token, max_age=store.SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/")


@router.get("/status", summary="آیا اولین مدیر سیستم هنوز ساخته نشده؟")
async def status():
    count = await run_in_threadpool(store.user_count)
    return {"auth_enabled": settings.auth_enabled, "needs_setup": count == 0}


@router.post("/setup", summary="ساخت اولین مدیر سیستم (فقط وقتی هیچ کاربری وجود ندارد)")
async def setup(body: SetupBody, response: Response):
    if await run_in_threadpool(store.user_count):
        raise HTTPException(409, detail="مدیر سیستم قبلاً ساخته شده است؛ وارد شوید.")
    await run_in_threadpool(store.create_user, body.username, body.full_name, body.password, [], True)
    result = await run_in_threadpool(store.login, body.username, body.password)
    token, user = result  # type: ignore[misc]
    _set_cookie(response, token)
    return _profile(user)


@router.post("/login", summary="ورود با نام کاربری و رمز عبور")
async def login(body: LoginBody, response: Response):
    result = await run_in_threadpool(store.login, body.username, body.password)
    if not result:
        raise HTTPException(401, detail="نام کاربری یا رمز عبور اشتباه است.")
    token, user = result
    _set_cookie(response, token)
    return _profile(user)


@router.post("/logout", summary="خروج")
async def logout(request: Request, response: Response):
    token = guard.request_token(request)
    guard.forget_token(token)
    await run_in_threadpool(store.logout, token)
    response.delete_cookie(guard.COOKIE_NAME, path="/")
    return {"status": "success"}


@router.get("/me", summary="کاربر فعلی، ماژول‌ها و صفحه‌های مجاز")
def me(user: dict[str, Any] = Depends(guard.current_user)):
    return _profile(user)


@router.patch("/me/preferences", summary="تم و والپیپر کاربر")
def preferences(body: Preferences, request: Request, user: dict[str, Any] = Depends(guard.current_user)):
    if not user.get("id"):
        raise HTTPException(400, detail="کاربر سیستمی تنظیمات ندارد.")
    prefs = store.set_preferences(user["id"], body.model_dump(exclude_none=True))
    guard.forget_token(guard.request_token(request))
    return {"preferences": prefs}


@router.get("/modules", summary="فهرست ماژول‌های قابل واگذاری")
def modules():
    return {"modules": catalog()}


# ------------------------------------------------------------------ admin
@router.get("/users", summary="فهرست کاربران", dependencies=[Depends(guard.require_admin)])
def users():
    return {"users": store.list_users(), "modules": catalog()}


@router.post("/users", summary="تعریف کاربر جدید", dependencies=[Depends(guard.require_admin)])
def create_user(body: UserCreate):
    try:
        return store.create_user(body.username, body.full_name, body.password, body.modules, body.is_admin)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.patch("/users/{user_id}", summary="ویرایش کاربر، رمز یا ماژول‌ها", dependencies=[Depends(guard.require_admin)])
def update_user(user_id: int, body: UserUpdate):
    try:
        out = store.update_user(user_id, **body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(404, detail="کاربر پیدا نشد.") from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    guard.forget_all()
    return out


@router.delete("/users/{user_id}", summary="حذف کاربر", dependencies=[Depends(guard.require_admin)])
def delete_user(user_id: int, admin: dict[str, Any] = Depends(guard.require_admin)):
    if admin.get("id") == user_id:
        raise HTTPException(400, detail="نمی‌توانید حساب خودتان را حذف کنید.")
    try:
        store.delete_user(user_id)
    except KeyError as exc:
        raise HTTPException(404, detail="کاربر پیدا نشد.") from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    guard.forget_all()
    return {"status": "success"}
