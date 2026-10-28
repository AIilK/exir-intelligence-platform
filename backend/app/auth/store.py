"""کاربران، نشست‌های ورود، تنظیمات ظاهری و حافظه چت هر کاربر — در دیتابیس اصلی اپ (DATABASE_URL).

رمز عبور با PBKDF2-SHA256 (کتابخانه استاندارد پایتون) و نمک تصادفی ذخیره می‌شود؛ خود رمز هیچ‌جا نگه داشته نمی‌شود.
توکن نشست فقط به‌صورت هش SHA-256 در دیتابیس است.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func, select, delete
from sqlalchemy.orm import Session

from app.auth.modules import clean_modules
from app.database.base import Base
from app.database.session import SessionLocal, engine

SESSION_DAYS = 14
PBKDF2_ROUNDS = 260_000
MEMORY_LIMIT = 40          # بیشترین تعداد یادداشت حافظه بلندمدت هر کاربر
CHAT_HISTORY_LIMIT = 2000  # پیام‌های نگه‌داشته‌شده هر کاربر (گفتگوهای قدیمی‌تر پاک می‌شوند)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    """SQLite منطقه زمانی را نگه نمی‌دارد؛ زمان‌ها UTC ذخیره شده‌اند و با +00:00 برگردانده می‌شوند."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


class User(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True)
    username = Column(String(60), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    modules_json = Column(Text, nullable=False, default="[]")
    preferences_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    last_login_at = Column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "app_user_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class UserMemory(Base):
    """حافظه بلندمدت چت‌بات برای هر شخص (با نام کاربری و نام کامل)."""
    __tablename__ = "app_user_memory"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    username = Column(String(60), nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class UserChatMessage(Base):
    """تاریخچه گفتگوی هر شخص با چت‌بات."""
    __tablename__ = "app_user_chat_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    username = Column(String(60), nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    role = Column(String(12), nullable=False)
    text = Column(Text, nullable=False)
    view = Column(String(40))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class UserAlarmState(Base):
    """وضعیت هر الارم برای هر شخص: seen (دیده شد)، done (انجام شد)، dismissed (نادیده)؛ با نام کاربر."""
    __tablename__ = "app_user_alarm_state"
    user_id = Column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True)
    alarm_key = Column(String(300), primary_key=True)
    username = Column(String(60), nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False)
    note = Column(Text)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class UserReminder(Base):
    """یادآوری‌های شخصی که حیوان خانگی اپ (گربه/سگ) سر وقت به همان شخص می‌گوید."""
    __tablename__ = "app_user_reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True)
    username = Column(String(60), nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    text = Column(String(300), nullable=False)
    due_at = Column(DateTime(timezone=True))
    done = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


def init_tables() -> None:
    Base.metadata.create_all(bind=engine, tables=[User.__table__, UserSession.__table__, UserMemory.__table__, UserChatMessage.__table__,
                                                  UserAlarmState.__table__, UserReminder.__table__])


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(check, digest)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------ users
def public_user(u: User) -> dict[str, Any]:
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "is_admin": bool(u.is_admin),
        "is_active": bool(u.is_active), "modules": json.loads(u.modules_json or "[]"),
        "preferences": json.loads(u.preferences_json or "{}"),
        "created_at": _iso(u.created_at),
        "last_login_at": _iso(u.last_login_at),
    }


def user_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count(User.id))) or 0


def list_users() -> list[dict[str, Any]]:
    with SessionLocal() as db:
        return [public_user(u) for u in db.scalars(select(User).order_by(User.id))]


def _norm_username(username: str) -> str:
    return (username or "").strip().lower()


def create_user(username: str, full_name: str, password: str, modules: list[str], is_admin: bool = False) -> dict[str, Any]:
    username = _norm_username(username)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            raise ValueError("این نام کاربری قبلاً ثبت شده است.")
        u = User(username=username, full_name=full_name.strip(), password_hash=hash_password(password),
                 is_admin=is_admin, modules_json=json.dumps(clean_modules(modules)), preferences_json="{}")
        db.add(u)
        db.commit()
        db.refresh(u)
        return public_user(u)


def update_user(user_id: int, *, full_name: str | None = None, password: str | None = None, modules: list[str] | None = None,
                is_admin: bool | None = None, is_active: bool | None = None) -> dict[str, Any]:
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise KeyError(user_id)
        if full_name is not None:
            u.full_name = full_name.strip()
        if password:
            u.password_hash = hash_password(password)
            db.execute(delete(UserSession).where(UserSession.user_id == u.id))
        if modules is not None:
            u.modules_json = json.dumps(clean_modules(modules))
        if is_admin is not None:
            u.is_admin = is_admin
        if is_active is not None:
            u.is_active = is_active
            if not is_active:
                db.execute(delete(UserSession).where(UserSession.user_id == u.id))
        _ensure_an_admin_remains(db)
        db.commit()
        db.refresh(u)
        return public_user(u)


def delete_user(user_id: int) -> None:
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise KeyError(user_id)
        db.delete(u)
        db.flush()
        _ensure_an_admin_remains(db)
        for model in (UserSession, UserMemory, UserChatMessage, UserAlarmState, UserReminder):
            db.execute(delete(model).where(model.user_id == user_id))
        db.commit()


def _ensure_an_admin_remains(db: Session) -> None:
    db.flush()
    if not db.scalar(select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))):
        db.rollback()
        raise ValueError("حداقل یک مدیر سیستم فعال باید باقی بماند.")


def set_preferences(user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise KeyError(user_id)
        merged = {**json.loads(u.preferences_json or "{}"), **prefs}
        u.preferences_json = json.dumps(merged, ensure_ascii=False)
        db.commit()
        return merged


# ------------------------------------------------------------------ sessions
def login(username: str, password: str) -> tuple[str, dict[str, Any]] | None:
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.username == _norm_username(username)))
        if not u or not u.is_active or not verify_password(password, u.password_hash):
            return None
        token = secrets.token_urlsafe(32)
        db.add(UserSession(token_hash=_token_hash(token), user_id=u.id, expires_at=_now() + timedelta(days=SESSION_DAYS)))
        u.last_login_at = _now()
        db.execute(delete(UserSession).where(UserSession.expires_at < _now()))
        db.commit()
        db.refresh(u)
        return token, public_user(u)


def user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with SessionLocal() as db:
        s = db.get(UserSession, _token_hash(token))
        if not s:
            return None
        expires = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
        if expires < _now():
            return None
        u = db.get(User, s.user_id)
        return public_user(u) if u and u.is_active else None


def logout(token: str | None) -> None:
    if not token:
        return
    with SessionLocal() as db:
        db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
        db.commit()


# ------------------------------------------------------------------ chatbot memory
def memories(user_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        rows = db.scalars(select(UserMemory).where(UserMemory.user_id == user_id).order_by(UserMemory.id.desc()).limit(MEMORY_LIMIT))
        return [{"id": m.id, "content": m.content, "created_at": _iso(m.created_at)} for m in rows][::-1]


def add_memory(user: dict[str, Any], content: str) -> dict[str, Any]:
    content = " ".join((content or "").split())[:500]
    if not content:
        raise ValueError("متن حافظه خالی است.")
    with SessionLocal() as db:
        if db.scalar(select(UserMemory).where(UserMemory.user_id == user["id"], UserMemory.content == content)):
            return {"saved": False, "reason": "قبلاً ذخیره شده بود"}
        db.add(UserMemory(user_id=user["id"], username=user["username"], full_name=user["full_name"], content=content))
        db.flush()
        old = db.scalars(select(UserMemory.id).where(UserMemory.user_id == user["id"]).order_by(UserMemory.id.desc()).offset(MEMORY_LIMIT)).all()
        if old:
            db.execute(delete(UserMemory).where(UserMemory.id.in_(old)))
        db.commit()
    return {"saved": True}


def delete_memory(user_id: int, memory_id: int | None = None) -> None:
    with SessionLocal() as db:
        q = delete(UserMemory).where(UserMemory.user_id == user_id)
        if memory_id is not None:
            q = q.where(UserMemory.id == memory_id)
        db.execute(q)
        db.commit()


def save_chat(user: dict[str, Any], role: str, text: str, view: str | None) -> None:
    with SessionLocal() as db:
        db.add(UserChatMessage(user_id=user["id"], username=user["username"], full_name=user["full_name"],
                               role=role, text=text[:8000], view=view))
        db.flush()
        old = db.scalars(select(UserChatMessage.id).where(UserChatMessage.user_id == user["id"])
                         .order_by(UserChatMessage.id.desc()).offset(CHAT_HISTORY_LIMIT)).all()
        if old:
            db.execute(delete(UserChatMessage).where(UserChatMessage.id.in_(old)))
        db.commit()


# «گفتگوی جدید» پیام‌ها را پاک نمی‌کند؛ یک سطر جداکننده (role = new) می‌گذارد و گفتگوهای قبلی در تاریخچه می‌مانند.
NEW_CHAT = "new"


def start_new_chat(user: dict[str, Any], view: str | None = None) -> None:
    save_chat(user, NEW_CHAT, "", view)


def chat_history(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """پیام‌های گفتگوی جاری (بعد از آخرین «گفتگوی جدید»)."""
    with SessionLocal() as db:
        last_new = db.scalar(select(func.max(UserChatMessage.id)).where(UserChatMessage.user_id == user_id, UserChatMessage.role == NEW_CHAT)) or 0
        rows = db.scalars(select(UserChatMessage).where(UserChatMessage.user_id == user_id, UserChatMessage.id > last_new)
                          .order_by(UserChatMessage.id.desc()).limit(limit))
        return [{"role": m.role, "text": m.text, "view": m.view, "created_at": _iso(m.created_at)} for m in rows][::-1]


def chat_conversations(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """همه گفتگوهای این کاربر (جدیدترین اول): عنوان = اولین پرسش، تاریخ و پیام‌ها."""
    with SessionLocal() as db:
        rows = db.scalars(select(UserChatMessage).where(UserChatMessage.user_id == user_id).order_by(UserChatMessage.id))
        convs: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        for m in rows:
            if m.role == NEW_CHAT or cur is None:
                cur = {"id": m.id, "started_at": _iso(m.created_at), "messages": []}
                convs.append(cur)
                if m.role == NEW_CHAT:
                    continue
            cur["messages"].append({"role": m.role, "text": m.text, "created_at": _iso(m.created_at)})
    out = [c for c in convs if c["messages"]]
    for c in out:
        c["title"] = next((x["text"][:80] for x in c["messages"] if x["role"] == "user"), "گفتگو")
        c["count"] = len(c["messages"])
    return out[::-1][:limit]


def clear_chat(user_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(UserChatMessage).where(UserChatMessage.user_id == user_id))
        db.commit()


# ------------------------------------------------------------------ alarm state per user
ALARM_STATES = {"seen", "done", "dismissed", "open"}


def alarm_states(user_id: int) -> dict[str, dict[str, Any]]:
    with SessionLocal() as db:
        rows = db.scalars(select(UserAlarmState).where(UserAlarmState.user_id == user_id))
        return {r.alarm_key: {"status": r.status, "note": r.note, "updated_at": _iso(r.updated_at)} for r in rows}


def set_alarm_state(user: dict[str, Any], alarm_key: str, status: str, note: str | None = None) -> None:
    if status not in ALARM_STATES:
        raise ValueError("وضعیت الارم نامعتبر است.")
    with SessionLocal() as db:
        row = db.get(UserAlarmState, (user["id"], alarm_key))
        if status == "open":
            if row:
                db.delete(row)
        elif row:
            row.status, row.note, row.updated_at = status, note if note is not None else row.note, _now()
        else:
            db.add(UserAlarmState(user_id=user["id"], alarm_key=alarm_key, username=user["username"], full_name=user["full_name"],
                                  status=status, note=note, updated_at=_now()))
        db.commit()


# ------------------------------------------------------------------ reminders per user
def _reminder(r: UserReminder) -> dict[str, Any]:
    return {"id": r.id, "text": r.text, "due_at": _iso(r.due_at), "done": bool(r.done), "created_at": _iso(r.created_at)}


def reminders(user_id: int, include_done: bool = False) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        q = select(UserReminder).where(UserReminder.user_id == user_id)
        if not include_done:
            q = q.where(UserReminder.done.is_(False))
        rows = db.scalars(q.order_by(UserReminder.done, UserReminder.due_at.is_(None), UserReminder.due_at, UserReminder.id).limit(200))
        return [_reminder(r) for r in rows]


def add_reminder(user: dict[str, Any], text: str, due_at: datetime | None) -> dict[str, Any]:
    text = " ".join((text or "").split())[:300]
    if not text:
        raise ValueError("متن یادآوری خالی است.")
    with SessionLocal() as db:
        r = UserReminder(user_id=user["id"], username=user["username"], full_name=user["full_name"], text=text,
                         due_at=due_at.astimezone(timezone.utc) if due_at and due_at.tzinfo else due_at, done=False)
        db.add(r)
        db.commit()
        db.refresh(r)
        return _reminder(r)


def update_reminder(user_id: int, reminder_id: int, *, done: bool | None = None, due_at: datetime | None = None,
                    clear_due: bool = False) -> dict[str, Any]:
    with SessionLocal() as db:
        r = db.get(UserReminder, reminder_id)
        if not r or r.user_id != user_id:
            raise KeyError(reminder_id)
        if done is not None:
            r.done = done
        if due_at is not None:
            r.due_at = due_at.astimezone(timezone.utc) if due_at.tzinfo else due_at
        if clear_due:
            r.due_at = None
        db.commit()
        db.refresh(r)
        return _reminder(r)


def delete_reminder(user_id: int, reminder_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(UserReminder).where(UserReminder.user_id == user_id, UserReminder.id == reminder_id))
        db.commit()
