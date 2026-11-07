"""تحلیل هوشمند پرونده هر هیبرید و هر نماینده راهکاران بر اساس تاریخچه‌اش (هوش مصنوعی).

ورودی مدل فقط «پروفایل تاریخچه» است که file_history_service با کد می‌سازد: فروش، توزیع و وصول، چک‌های هر ماه و
سرنوشتشان، وضعیت مالی فعلی و روند امتیاز ریسک. مدل حق ساختن عدد ندارد؛ خروجی با json_schema سخت‌گیر برگردانده و
ذخیره می‌شود و پروفایلی که مدل دیده هم کنارش نگه داشته می‌شود تا هر جمله قابل وارسی باشد.

اجرا: هفتگی (شنبه بعد از گزارش ریسک، app/automation/daily_finance_job.py)، فقط برای پرونده‌هایی که تاریخچه‌شان از
تحلیل قبلی عوض شده؛ و دستی از دکمه «تحلیل دوباره» در هر پرونده.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_file_analysis.sqlite3"
KINDS = ("hybrid", "rep")
REBUILD_AFTER_DAYS = 7

ASSESSMENTS = ["خوب", "قابل قبول", "نیازمند توجه", "پرخطر"]
TRENDS = ["رو به بهبود", "ثابت", "رو به افت", "نامشخص"]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string", "description": "یک جمله: مهم‌ترین نتیجه درباره این پرونده"},
        "assessment": {"type": "string", "enum": ASSESSMENTS},
        "assessment_reason": {"type": "string", "description": "چرا این ارزیابی؛ با عدد از پروفایل"},
        "summary": {"type": "string", "description": "حداکثر ۴ جمله: تصویر کلی از روی تاریخچه"},
        "sales_trend": {"type": "string", "enum": TRENDS},
        "sales_story": {"type": "string", "description": "روند فروش ماه‌به‌ماه و نسبت به پارسال"},
        "payment_trend": {"type": "string", "enum": TRENDS},
        "payment_story": {"type": "string", "description": "رفتار پرداخت: وصول، چک‌ها، برگشتی‌ها، مدت چک‌ها در طول زمان"},
        "changes": {"type": "array", "items": {"type": "string"}, "description": "تغییرهای مهم اخیر نسبت به گذشته خودش"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "outlook": {"type": "string", "description": "اگر همین روند ادامه یابد، ۱ تا ۳ ماه آینده چه انتظاری داریم"},
        "actions": {"type": "array", "items": {"type": "string"}, "description": "۲ تا ۴ اقدام عملی برای مدیر فروش/مالی"},
    },
    "required": ["headline", "assessment", "assessment_reason", "summary", "sales_trend", "sales_story",
                 "payment_trend", "payment_story", "changes", "strengths", "risks", "outlook", "actions"],
}

INSTRUCTIONS = """تو تحلیلگر ارشد فروش و اعتبار شرکت پخش «اکسیر کادوس» هستی. یک «پروفایل تاریخچه» به تو داده می‌شود که
همه اعدادش با کد از سیستم‌های راهکاران و کارآمد ساخته شده است. کارت: نگاه به گذشته همین هیبرید/نماینده،
پیدا کردن روندها و تغییرها، و جمع‌بندی برای مدیر.

قواعد سخت:
- فقط از اعداد و واقعیت‌های همین پروفایل استفاده کن؛ هیچ عدد، درصد، نام یا رویدادی نساز. اگر داده کافی نیست، بگو.
- مبالغ پروفایل «میلیون تومان» (mt) است؛ در متن به شکل خوانا بنویس (مثلاً «۱۸٫۵ میلیارد تومان» یا «۴۲۰ میلیون تومان»).
- «روند» یعنی مقایسه با گذشته خودش: ماه‌های اخیر در برابر ماه‌های قبل، و امسال در برابر همان ماه پارسال.
- چک‌های ماه‌های اخیر اغلب هنوز سررسید نشده‌اند (still_open)؛ آن‌ها را برگشتی یا بد حساب نکن.
  نرخ برگشت را فقط روی ماه‌هایی قضاوت کن که بیشتر چک‌هایشان تعیین تکلیف شده‌اند.
- ماه جاری ناقص است (تا امروز)؛ آن را با ماه کامل مقایسه نکن مگر با ذکر این نکته.
- اگر امتیاز ریسک یا سطح ریسک قاعده‌محور در پروفایل هست، آن را جایگزین نکن؛ ارزیابی تو برداشت از روندهاست و می‌تواند
  با آن فرق داشته باشد، ولی دلیلش را بگو.
- فارسی روان و کوتاه، برای مدیرعامل و مدیر فروش؛ بدون نام فیلد انگلیسی یا اصطلاح فنی.
"""


# ---------------------------------------------------------------- ذخیره
def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS analyses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, key TEXT NOT NULL, name TEXT,
        created_at TEXT NOT NULL, trigger_type TEXT NOT NULL, model TEXT, profile_hash TEXT NOT NULL,
        profile TEXT NOT NULL, result TEXT, error TEXT, seconds REAL)""")
    db.execute("CREATE INDEX IF NOT EXISTS ix_analyses_entity ON analyses(kind, key, created_at)")
    return db


def _hash(profile: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _latest_row(kind: str, key: str, ok_only: bool = True):
    with _connect() as db:
        sql = "SELECT * FROM analyses WHERE kind=? AND key=?" + (" AND result IS NOT NULL" if ok_only else "") + " ORDER BY created_at DESC LIMIT 1"
        return db.execute(sql, (kind, str(key))).fetchone()


# ---------------------------------------------------------------- مدل
def enabled() -> bool:
    return bool(settings.openai_api_key) and settings.ai_file_analysis_enabled


def _ask_model(profile: dict[str, Any]) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    who = "هیبرید (شعبه فروش کارآمد)" if profile.get("kind") == "hybrid" else "نماینده استانی راهکاران (B2B)"
    r = client.responses.create(
        model=settings.ai_file_analysis_model or settings.openai_model,
        reasoning={"effort": "medium"},
        instructions=INSTRUCTIONS,
        input=[{"role": "user", "content": f"پروفایل تاریخچه این {who}:\n" + json.dumps(profile, ensure_ascii=False)}],
        text={"format": {"type": "json_schema", "name": "file_analysis", "schema": SCHEMA, "strict": True}},
    )
    out = json.loads(r.output_text)
    if out.get("assessment") not in ASSESSMENTS:
        raise ValueError("assessment خارج از گزینه‌ها")
    return out


def analyze(profile: dict[str, Any], trigger: str = "manual", *, force: bool = False) -> dict[str, Any]:
    """یک پرونده را تحلیل و ذخیره می‌کند؛ اگر تاریخچه از تحلیل قبلی عوض نشده و force نیست، همان قبلی می‌ماند."""
    kind, key = profile["kind"], str(profile["key"])
    digest = _hash(profile)
    prev = _latest_row(kind, key)
    if prev is not None and prev["profile_hash"] == digest and not force:
        return {"status": "unchanged", "created_at": prev["created_at"]}
    started = time.monotonic()
    model = settings.ai_file_analysis_model or settings.openai_model
    result, error = None, None
    try:
        result = _ask_model(profile)
    except Exception as exc:  # noqa: BLE001 — خطای مدل ذخیره می‌شود و تحلیل قبلی سر جایش می‌ماند
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
        logger.warning("ai file analysis failed for %s/%s: %s", kind, key, error)
    with _connect() as db:
        db.execute("INSERT INTO analyses(kind, key, name, created_at, trigger_type, model, profile_hash, profile, result, error, seconds)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (kind, key, profile.get("name"), datetime.now(timezone.utc).isoformat(), trigger, model, digest,
                    json.dumps(profile, ensure_ascii=False), json.dumps(result, ensure_ascii=False) if result else None,
                    error, round(time.monotonic() - started, 1)))
    return {"status": "error" if error else "analyzed", "error": error}


# ---------------------------------------------------------------- اجرای گروهی و دستی
_state: dict[str, Any] = {"batch": None, "single": set()}
_batch_lock = threading.Lock()


def _profiles(kind: str) -> dict[str, dict[str, Any]]:
    from app.services import file_history_service as fh

    return {str(k): v for k, v in (fh.hybrid_profiles() if kind == "hybrid" else fh.rep_profiles()).items()}


def run_batch(trigger: str = "scheduled", kinds: tuple[str, ...] = KINDS) -> dict[str, Any]:
    """همه هیبریدها و نمایندگان فعال؛ فقط پرونده‌هایی که تاریخچه‌شان عوض شده دوباره به مدل فرستاده می‌شوند."""
    if not enabled():
        return {"status": "disabled"}
    if not _batch_lock.acquire(blocking=False):
        return {"status": "busy"}
    counts = {"analyzed": 0, "unchanged": 0, "error": 0}
    try:
        _state["batch"] = {"started_at": datetime.now(timezone.utc).isoformat(), "done": 0, "total": None}
        for kind in kinds:
            profiles = _profiles(kind)
            _state["batch"]["total"] = (_state["batch"]["total"] or 0) + len(profiles)
            for profile in profiles.values():
                outcome = analyze(profile, trigger)
                counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
                _state["batch"]["done"] += 1
        logger.info("ai file analysis batch done: %s", counts)
        return {"status": "done", **counts}
    finally:
        _state["batch"] = None
        _batch_lock.release()


def refresh_one_in_background(kind: str, key: str) -> bool:
    """«تحلیل دوباره» یک پرونده: پروفایل همان نوع ساخته و فقط همین یکی (حتی بدون تغییر) دوباره تحلیل می‌شود."""
    tag = (kind, str(key))
    if tag in _state["single"]:
        return False
    _state["single"].add(tag)

    def run() -> None:
        try:
            profile = _profiles(kind).get(str(key))
            if profile is None:
                raise KeyError(f"{kind}/{key} در فهرست پرونده‌ها نیست")
            analyze(profile, "manual", force=True)
        except Exception:  # noqa: BLE001
            logger.exception("ai file analysis refresh failed for %s/%s", kind, key)
        finally:
            _state["single"].discard(tag)
    threading.Thread(target=run, name=f"ai-file-{kind}-{key}", daemon=True).start()
    return True


def ensure_recent() -> None:
    """بعد از راه‌اندازی: اگر آخرین اجرای گروهی قدیمی‌تر از یک هفته است (مثلاً سرور شنبه خاموش بوده)، در پس‌زمینه اجرا شود."""
    if not enabled():
        return
    with _connect() as db:
        row = db.execute("SELECT MAX(created_at) AS at FROM analyses WHERE trigger_type IN ('scheduled', 'startup')").fetchone()
    if row and row["at"] and datetime.now(timezone.utc) - datetime.fromisoformat(row["at"]) < timedelta(days=REBUILD_AFTER_DAYS):
        return
    threading.Thread(target=lambda: run_batch("startup"), name="ai-file-analysis-catch-up", daemon=True).start()


# ---------------------------------------------------------------- خواندن
def latest(kind: str, key: str) -> dict[str, Any]:
    row = _latest_row(kind, key)
    last_any = _latest_row(kind, key, ok_only=False)
    busy = (kind, str(key)) in _state["single"]
    base = {"enabled": enabled(), "refreshing": busy, "batch": _state["batch"]}
    if row is None:
        return {**base, "status": "empty",
                "message": ("تحلیل هوشمند با کلید OpenAI فعال می‌شود." if not enabled()
                            else "هنوز تحلیلی برای این پرونده ساخته نشده است."),
                "last_error": last_any["error"] if last_any is not None else None}
    return {
        **base, "status": "ready", "created_at": row["created_at"], "trigger": row["trigger_type"], "model": row["model"],
        "analysis": json.loads(row["result"]), "profile": json.loads(row["profile"]),
        "last_error": last_any["error"] if last_any is not None and last_any["id"] != row["id"] else None,
    }
