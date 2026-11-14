"""قراردادهای همکاران (مدیران هیبریدها و …): تاریخ پایان هر قرارداد و الارم یک هفته مانده به پایان.

هر قرارداد یک ردیف SQLite است (نام، هیبرید/محل، سمت، تاریخ پایان شمسی، یادداشت).
قراردادها فقط از صفحه «قراردادهای همکاران» اضافه و ویرایش می‌شوند (در کد هیچ نامی نگه داشته نمی‌شود).
وضعیت: ended (تمام‌شده و تمدیدنشده) | week (۷ روز یا کمتر) | month (تا ۳۰ روز) | ok.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import jdatetime

from app.core.config import settings

WARN_DAYS = 7      # الارم «یک هفته مانده»
SOON_DAYS = 30     # فقط برای نمایش «کمتر از یک ماه»
_lock = threading.Lock()

# فهرست اولیه قراردادها در کد نگه داشته نمی‌شود (اطلاعات شخصی همکاران)؛ قراردادها فقط در دیتابیس محلی
# backend/data/staff_contracts.db هستند و از صفحه «قراردادهای همکاران» اضافه و ویرایش می‌شوند.
SEED: list[tuple[str, str, str]] = []

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class ContractError(ValueError):
    pass


def parse_jalali(text: Any) -> jdatetime.date:
    """«۱۴۰۵/۰۹/۰۱» یا «1405-9-1» ← تاریخ شمسی؛ تاریخ نامعتبر خطا می‌دهد."""
    raw = str(text or "").translate(_FA_DIGITS).strip()
    m = re.fullmatch(r"(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})", raw)
    if not m:
        raise ContractError("تاریخ باید به شکل ۱۴۰۵/۰۹/۰۱ باشد.")
    try:
        return jdatetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError as exc:
        raise ContractError(f"تاریخ {raw} وجود ندارد.") from exc


def status_of(days_left: int) -> str:
    if days_left < 0:
        return "ended"
    if days_left <= WARN_DAYS:
        return "week"
    if days_left <= SOON_DAYS:
        return "month"
    return "ok"


class ContractsStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or settings.staff_contracts_db).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init(self) -> None:
        with _lock, self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, hybrid TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            if not db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
                now = _now()
                db.executemany("INSERT INTO contracts(name, hybrid, role, end_date, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                               [(n, h, "مدیر هیبرید", parse_jalali(d).strftime("%Y/%m/%d"), "", now, now) for n, h, d in SEED])
                db.execute("INSERT INTO meta(key, value) VALUES ('seeded', ?)", (now,))

    # ---------------------------------------------------------------- read
    def list(self, today: date | None = None) -> list[dict[str, Any]]:
        today = today or date.today()
        with self.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM contracts")]
        for r in rows:
            end = parse_jalali(r["end_date"])
            r["end_date_gregorian"] = end.togregorian().isoformat()
            r["days_left"] = (end.togregorian() - today).days
            r["status"] = status_of(r["days_left"])
        return sorted(rows, key=lambda r: (r["days_left"], r["name"]))

    def summary(self, today: date | None = None) -> dict[str, Any]:
        rows = self.list(today)
        counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("ended", "week", "month", "ok")}
        return {"today_jalali": jdatetime.date.fromgregorian(date=today or date.today()).strftime("%Y/%m/%d"),
                "warn_days": WARN_DAYS, "counts": counts, "total": len(rows), "contracts": rows}

    # ---------------------------------------------------------------- write
    def add(self, data: dict[str, Any]) -> dict[str, Any]:
        clean = _clean(data, require=True)
        now = _now()
        with _lock, self.connect() as db:
            cur = db.execute("INSERT INTO contracts(name, hybrid, role, end_date, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                             (clean["name"], clean["hybrid"], clean["role"], clean["end_date"], clean["note"], now, now))
            new_id = cur.lastrowid
        return next(r for r in self.list() if r["id"] == new_id)

    def update(self, contract_id: int, data: dict[str, Any]) -> dict[str, Any]:
        clean = _clean(data, require=False)
        if not clean:
            raise ContractError("چیزی برای تغییر فرستاده نشد.")
        with _lock, self.connect() as db:
            sets = ", ".join(f"{k}=?" for k in clean)
            cur = db.execute(f"UPDATE contracts SET {sets}, updated_at=? WHERE id=?", (*clean.values(), _now(), contract_id))
            if not cur.rowcount:
                raise KeyError(contract_id)
        return next(r for r in self.list() if r["id"] == contract_id)

    def delete(self, contract_id: int) -> None:
        with _lock, self.connect() as db:
            if not db.execute("DELETE FROM contracts WHERE id=?", (contract_id,)).rowcount:
                raise KeyError(contract_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(data: dict[str, Any], require: bool) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("name", "hybrid", "role", "note"):
        if data.get(key) is not None:
            out[key] = str(data[key]).strip()[:200]
    if data.get("end_date") is not None:
        out["end_date"] = parse_jalali(data["end_date"]).strftime("%Y/%m/%d")
    if require:
        if not out.get("name"):
            raise ContractError("نام همکار لازم است.")
        if not out.get("end_date"):
            raise ContractError("تاریخ پایان قرارداد لازم است.")
        out.setdefault("hybrid", "")
        out.setdefault("role", "")
        out.setdefault("note", "")
    if "name" in out and not out["name"]:
        raise ContractError("نام همکار خالی است.")
    return out


def refresh_alarms_async() -> None:
    """بعد از هر تغییر، الارم قراردادها همان لحظه دوباره ساخته شود (بدون صبر برای اجرای روزانه)."""
    def run() -> None:
        try:
            from app.agents.page_agents.agents import ContractsAgent
            ContractsAgent().run("contract_update")
        except Exception:  # noqa: BLE001 — الارم در اجرای روزانه دوباره ساخته می‌شود
            pass
    threading.Thread(target=run, name="contracts-alarm", daemon=True).start()
