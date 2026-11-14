"""ذخیره‌سازی ارسال واتساپ در یک SQLite جدا (settings.whatsapp_db).

جدول‌ها:
- rules: قاعده‌های ارسال (نوع، روزها و ساعت، تأیید دستی یا ارسال خودکار، پارامترها، متن قالب)
- outbox: صف پیام‌ها؛ dedupe_key جلوی ارسال تکراری در یک روز را می‌گیرد
- recipients: شماره جایگزین یا لغو ارسال برای یک مشتری/ویزیتور
وضعیت پیام: pending (منتظر تأیید) → approved (در صف ارسال) → sent | failed | no_whatsapp؛ یا skipped
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings

_lock = threading.RLock()
_ready = False

KINDS = {
    "customer_debt": "بدهی مشتری",
    "customer_cheques": "چک‌های پیش‌رو مشتری",
    "visitor_report": "گزارش اکسل ویزیتور",
}
DAYS = ["sat", "sun", "mon", "tue", "wed", "thu", "fri"]
STATUSES = ["pending", "approved", "sending", "sent", "failed", "no_whatsapp", "skipped"]

DEFAULT_TEMPLATES = {
    "customer_debt": (
        "{name} عزیز، سلام\n"
        "مانده حساب شما نزد اکسیر کادوس تا تاریخ {date}: {debt} تومان است.\n"
        "در صورت پرداخت، لطفاً این پیام را نادیده بگیرید. سپاس از همکاری شما."
    ),
    "customer_cheques": (
        "{name} عزیز، سلام\n"
        "یادآوری سررسید چک‌های شما در {days} روز آینده:\n"
        "{cheques}\n"
        "جمع: {total} تومان. لطفاً از کافی بودن موجودی حساب اطمینان حاصل فرمایید."
    ),
    "visitor_report": (
        "{name} عزیز، سلام\n"
        "گزارش مشتریان شما تا تاریخ {date}:\n"
        "• {debtor_count} مشتری بدهکار، جمع بدهی {debt} تومان\n"
        "• {cheque_count} چک با سررسید {days} روز آینده، جمع {cheque_total} تومان\n"
        "فایل اکسل جزئیات پیوست است."
    ),
}

DEFAULT_RULES = [
    {"title": "یادآوری بدهی مشتریان (هفتگی)", "kind": "customer_debt", "days": "sat", "hour": 10, "minute": 0,
     "params": {"min_debt_toman": 5_000_000, "branch_ids": []}},
    {"title": "یادآوری چک‌های پیش‌رو (روزانه)", "kind": "customer_cheques", "days": "sat,sun,mon,tue,wed", "hour": 9, "minute": 0,
     "params": {"days_ahead": 3, "branch_ids": []}},
    {"title": "اکسل مشتریان هر ویزیتور (هفتگی)", "kind": "visitor_report", "days": "sat", "hour": 8, "minute": 30,
     "params": {"min_debt_toman": 0, "days_ahead": 7, "branch_ids": [], "attach_excel": True}},
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    days TEXT NOT NULL DEFAULT 'sat',
    hour INTEGER NOT NULL DEFAULT 9,
    minute INTEGER NOT NULL DEFAULT 0,
    auto_send INTEGER NOT NULL DEFAULT 0,
    params TEXT NOT NULL DEFAULT '{}',
    template TEXT NOT NULL DEFAULT '',
    last_run_date TEXT,
    last_run_at TEXT,
    last_result TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER,
    kind TEXT NOT NULL,
    recipient_kind TEXT NOT NULL,
    recipient_ref TEXT NOT NULL,
    recipient_name TEXT,
    branch TEXT,
    phone TEXT,
    message TEXT NOT NULL,
    file_path TEXT,
    file_name TEXT,
    amount_rial REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    dedupe_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    approved_by TEXT,
    sent_at TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_outbox_status ON outbox(status, id);
CREATE TABLE IF NOT EXISTS recipients (
    kind TEXT NOT NULL,
    ref TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    opted_out INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at TEXT,
    PRIMARY KEY (kind, ref)
);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def files_dir() -> Path:
    p = Path(settings.whatsapp_db).resolve().parent / "whatsapp_files"
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    global _ready
    with _lock:
        path = Path(settings.whatsapp_db)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            if not _ready:
                conn.executescript(SCHEMA)
                if not conn.execute("SELECT 1 FROM rules LIMIT 1").fetchone():
                    for r in DEFAULT_RULES:
                        conn.execute(
                            "INSERT INTO rules (title, kind, enabled, days, hour, minute, auto_send, params, template) "
                            "VALUES (?, ?, 0, ?, ?, ?, 0, ?, ?)",
                            (r["title"], r["kind"], r["days"], r["hour"], r["minute"],
                             json.dumps(r["params"], ensure_ascii=False), DEFAULT_TEMPLATES[r["kind"]]),
                        )
                _ready = True
            yield conn
            conn.commit()
        finally:
            conn.close()


def _rule(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["enabled"] = bool(d["enabled"])
    d["auto_send"] = bool(d["auto_send"])
    d["params"] = json.loads(d["params"] or "{}")
    d["days"] = [x for x in (d["days"] or "").split(",") if x]
    d["kind_title"] = KINDS.get(d["kind"], d["kind"])
    d["template"] = d["template"] or DEFAULT_TEMPLATES.get(d["kind"], "")
    d["last_result"] = json.loads(d["last_result"]) if d.get("last_result") else None
    return d


# ---------------- rules ----------------
def list_rules() -> list[dict[str, Any]]:
    with _conn() as c:
        return [_rule(r) for r in c.execute("SELECT * FROM rules ORDER BY id")]


def get_rule(rule_id: int) -> dict[str, Any]:
    with _conn() as c:
        row = c.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    if not row:
        raise KeyError(rule_id)
    return _rule(row)


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "title" in data:
        out["title"] = str(data["title"]).strip()[:120] or "قاعده بی‌نام"
    if "kind" in data:
        if data["kind"] not in KINDS:
            raise ValueError("نوع قاعده نامعتبر است.")
        out["kind"] = data["kind"]
    if "enabled" in data:
        out["enabled"] = 1 if data["enabled"] else 0
    if "auto_send" in data:
        out["auto_send"] = 1 if data["auto_send"] else 0
    if "days" in data:
        days = data["days"] if isinstance(data["days"], list) else str(data["days"]).split(",")
        days = [d for d in DAYS if d in {x.strip() for x in days}]
        if not days:
            raise ValueError("حداقل یک روز هفته را انتخاب کنید.")
        out["days"] = ",".join(days)
    if "hour" in data:
        out["hour"] = int(data["hour"])
        if not 0 <= out["hour"] <= 23:
            raise ValueError("ساعت باید بین ۰ تا ۲۳ باشد.")
    if "minute" in data:
        out["minute"] = int(data["minute"])
        if not 0 <= out["minute"] <= 59:
            raise ValueError("دقیقه باید بین ۰ تا ۵۹ باشد.")
    if "params" in data:
        out["params"] = json.dumps(data["params"] or {}, ensure_ascii=False)
    if "template" in data:
        out["template"] = str(data["template"] or "")[:3000]
    return out


def create_rule(data: dict[str, Any]) -> dict[str, Any]:
    vals = _validate({"enabled": False, "auto_send": False, "days": "sat", "hour": 9, "minute": 0, "params": {}, **data})
    if "kind" not in vals:
        raise ValueError("نوع قاعده لازم است.")
    vals.setdefault("title", KINDS[vals["kind"]])
    if not vals.get("template"):
        vals["template"] = DEFAULT_TEMPLATES[vals["kind"]]
    cols = ", ".join(vals)
    with _conn() as c:
        cur = c.execute(f"INSERT INTO rules ({cols}) VALUES ({', '.join('?' * len(vals))})", tuple(vals.values()))
        rule_id = cur.lastrowid
    return get_rule(int(rule_id))


def update_rule(rule_id: int, data: dict[str, Any]) -> dict[str, Any]:
    vals = _validate(data)
    vals.pop("kind", None)  # نوع قاعده بعد از ساخت عوض نمی‌شود
    if vals:
        sets = ", ".join(f"{k} = ?" for k in vals)
        with _conn() as c:
            if not c.execute(f"UPDATE rules SET {sets} WHERE id = ?", (*vals.values(), rule_id)).rowcount:
                raise KeyError(rule_id)
    return get_rule(rule_id)


def delete_rule(rule_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM rules WHERE id = ?", (rule_id,))


def mark_rule_run(rule_id: int, run_date: str, result: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute("UPDATE rules SET last_run_date = ?, last_run_at = ?, last_result = ? WHERE id = ?",
                  (run_date, now_iso(), json.dumps(result, ensure_ascii=False), rule_id))


# ---------------- outbox ----------------
def enqueue(items: list[dict[str, Any]], status: str) -> dict[str, int]:
    """پیام‌ها را به صف اضافه می‌کند؛ پیامی که dedupe_key آن قبلاً بوده نادیده گرفته می‌شود."""
    added = dup = 0
    with _conn() as c:
        for it in items:
            try:
                c.execute(
                    "INSERT INTO outbox (rule_id, kind, recipient_kind, recipient_ref, recipient_name, branch, phone, message, "
                    "file_path, file_name, amount_rial, status, dedupe_key, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (it.get("rule_id"), it["kind"], it["recipient_kind"], str(it["recipient_ref"]), it.get("recipient_name"),
                     it.get("branch"), it.get("phone"), it["message"], it.get("file_path"), it.get("file_name"),
                     it.get("amount_rial"), status, it["dedupe_key"], now_iso()),
                )
                added += 1
            except sqlite3.IntegrityError:
                dup += 1
    return {"added": added, "duplicates": dup}


def list_outbox(status: str | None = None, rule_id: int | None = None, limit: int = 300) -> list[dict[str, Any]]:
    where, args = [], []
    if status:
        where.append("status = ?")
        args.append(status)
    if rule_id:
        where.append("rule_id = ?")
        args.append(rule_id)
    sql = "SELECT * FROM outbox" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY id DESC LIMIT ?"
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, (*args, max(1, min(limit, 5000))))]


def outbox_counts() -> dict[str, int]:
    with _conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT status, COUNT(*) FROM outbox GROUP BY status")}


def get_item(item_id: int) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM outbox WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def set_status(ids: list[int], new_status: str, from_statuses: tuple[str, ...], by: str | None = None) -> int:
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    froms = ",".join("?" * len(from_statuses))
    with _conn() as c:
        return c.execute(
            f"UPDATE outbox SET status = ?, approved_by = COALESCE(?, approved_by), error = NULL "
            f"WHERE id IN ({marks}) AND status IN ({froms})",
            (new_status, by, *ids, *from_statuses),
        ).rowcount


def approve_all_pending(by: str, rule_id: int | None = None) -> int:
    with _conn() as c:
        sql = "UPDATE outbox SET status = 'approved', approved_by = ? WHERE status = 'pending'"
        args: tuple[Any, ...] = (by,)
        if rule_id:
            sql += " AND rule_id = ?"
            args += (rule_id,)
        return c.execute(sql, args).rowcount


def next_approved() -> dict[str, Any] | None:
    """اولین پیام تأییدشده را برمی‌دارد و وضعیتش را «در حال ارسال» می‌کند."""
    with _conn() as c:
        row = c.execute("SELECT * FROM outbox WHERE status = 'approved' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        c.execute("UPDATE outbox SET status = 'sending', attempts = attempts + 1 WHERE id = ?", (row["id"],))
    return dict(row)


def finish(item_id: int, status: str, error: str | None = None) -> None:
    with _conn() as c:
        c.execute("UPDATE outbox SET status = ?, error = ?, sent_at = ? WHERE id = ?",
                  (status, (error or None) and error[:1000], now_iso() if status == "sent" else None, item_id))


def reset_stuck_sending() -> None:
    """بعد از ری‌استارت سرور، پیام‌هایی که وسط ارسال مانده بودند دوباره در صف قرار می‌گیرند."""
    with _conn() as c:
        c.execute("UPDATE outbox SET status = 'approved' WHERE status = 'sending'")


def sent_today() -> int:
    today = datetime.now().date().isoformat()
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM outbox WHERE status = 'sent' AND sent_at >= ?", (today,)).fetchone()[0]


# ---------------- recipients ----------------
def recipient_overrides(kind: str | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM recipients" + (" WHERE kind = ?" if kind else ""), (kind,) if kind else ())
        return {(r["kind"], r["ref"]): dict(r) for r in rows}


def list_recipients() -> list[dict[str, Any]]:
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM recipients ORDER BY updated_at DESC")]


def upsert_recipient(kind: str, ref: str, name: str | None, phone: str | None, opted_out: bool, note: str | None) -> dict[str, Any]:
    if kind not in ("customer", "visitor"):
        raise ValueError("نوع گیرنده باید customer یا visitor باشد.")
    with _conn() as c:
        c.execute(
            "INSERT INTO recipients (kind, ref, name, phone, opted_out, note, updated_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(kind, ref) DO UPDATE SET name = COALESCE(excluded.name, name), phone = excluded.phone, "
            "opted_out = excluded.opted_out, note = excluded.note, updated_at = excluded.updated_at",
            (kind, str(ref), name, phone, 1 if opted_out else 0, note, now_iso()),
        )
    return recipient_overrides()[(kind, str(ref))]


def delete_recipient(kind: str, ref: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM recipients WHERE kind = ? AND ref = ?", (kind, str(ref)))
