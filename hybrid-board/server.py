"""تابلوی فرودگاهی تحقق تارگت هیبریدها — سرور جدا روی پورت خودش (پیش‌فرض 2000).

داده از API پورسانت داشبورد فروش (/api/commission روی SALES_API، پیش‌فرض http://127.0.0.1:8000) با کلید داخلی
«.exir_internal_key» ریشه مخزن خوانده می‌شود و فقط خلاصه لازم برای تابلو (بدون حقوق و پورسانت) بیرون داده می‌شود.

تنظیم با متغیر محیطی:
  BOARD_PORT  (پیش‌فرض 2000)
  BOARD_HOST  (پیش‌فرض 0.0.0.0 = از شبکه داخلی؛ صفحه ورود ندارد. فقط همین سیستم: 127.0.0.1)
  SALES_API   (پیش‌فرض http://127.0.0.1:8000)
  EXIR_INTERNAL_KEY یا EXIR_KEY_FILE (پیش‌فرض: .exir_internal_key در ریشه مخزن)
فقط کتابخانه استاندارد پایتون؛ اجرا: python -X utf8 hybrid-board/server.py
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parent  # ریشه مخزن (کنار فولدر sales)
SALES_API = os.environ.get("SALES_API", "http://127.0.0.1:8000").rstrip("/")
HOST = os.environ.get("BOARD_HOST", "0.0.0.0")  # از شبکه داخلی باز است (صفحه ورود ندارد)؛ فقط همین سیستم: 127.0.0.1
PORT = int(os.environ.get("BOARD_PORT", "2000"))
CACHE_SECONDS = 120
TOMAN_M = 1e7  # ریال ← میلیون تومان

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _key() -> str:
    env = os.environ.get("EXIR_INTERNAL_KEY", "").strip()
    if env:
        return env
    path = Path(os.environ.get("EXIR_KEY_FILE") or REPO / ".exir_internal_key")
    return path.read_text(encoding="utf-8").strip()


def _norm(s) -> str:
    s = str(s or "").replace("ي", "ی").replace("ك", "ک").replace("\xa0", " ").replace("‌", " ")
    return re.sub(r"^هیبریدی(?= )", "هیبرید", re.sub(r"\s+", " ", s).strip())


def _status(ach_month: float | None, pace: float | None) -> str:
    if ach_month is None:
        return "none"
    if ach_month >= 1:
        return "landed"
    if pace is not None and pace >= 1:
        return "ontrack"
    if pace is not None and pace >= 0.9:
        return "behind"
    return "late"


def build(month: str | None) -> dict:
    url = f"{SALES_API}/api/commission" + (f"?month={month}" if month else "")
    req = Request(url, headers={"X-Exir-Internal-Key": _key()})
    with urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8"))

    visitors: dict[str, list[dict]] = {}
    for v in d.get("visitors", []):
        visitors.setdefault(_norm(v.get("branch")), []).append(v)
    sups: dict[str, list[str]] = {}
    for s in d.get("supervisors", []):
        if s.get("name"):
            sups.setdefault(_norm(s.get("branch")), []).append(re.sub(r"\s*-\s*.*$", "", s["name"]).strip())

    out = []
    for b in d.get("branches", []):
        name = _norm(b["branch"])
        t = b.get("target_rial")
        gross = float(b.get("gross") or 0)
        ach_m = gross / t if t else None
        pace = b.get("ach")
        vs = visitors.get(name, [])
        top = sorted((v for v in vs if (v.get("gross") or 0) > 0), key=lambda v: -v["gross"])[:3]
        groups = []
        for g in b.get("groups") or []:
            if not g.get("target"):
                continue
            q = max(0.0, float(g.get("qty") or 0))
            groups.append({"key": g["key"], "target": g["target"], "qty": q, "ach": q / g["target"]})
        out.append({
            "name": name, "short": name.replace("هیبرید ", "", 1),
            "visitors": len([v for v in vs if v.get("type") != "channel"]),
            "supervisors": sups.get(name, []),
            "target": t / TOMAN_M if t else None, "gross": gross / TOMAN_M,
            "target_day": (b.get("target_day") or 0) / TOMAN_M if b.get("target_day") else None,
            "ach": ach_m, "pace": pace, "status": _status(ach_m, pace),
            "customers": b.get("customers") or 0,
            "groups": groups,
            "top": [{"name": v["name"], "gross": v["gross"] / TOMAN_M,
                     "ach": (v["gross"] / v["target_rial"]) if v.get("target_rial") else None} for v in top],
        })
    out.sort(key=lambda x: (x["ach"] is None, -(x["ach"] or 0)))
    for i, x in enumerate(out):
        x["rank"] = i + 1
    return {"month": d.get("month"), "today": d.get("today"), "current": d.get("current"),
            "wd_elapsed": d.get("wd_elapsed"), "wd_total": d.get("wd_total"),
            "fetched_at": time.strftime("%H:%M"), "branches": out}


def board_data(month: str | None) -> dict:
    k = month or ""
    with _lock:
        hit = _cache.get(k)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        data = build(month)
        _cache[k] = (time.time(), data)
        return data


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, (HERE / "board.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/board":
            month = (parse_qs(u.query).get("month") or [None])[0]
            if month and not re.fullmatch(r"\d{4}/\d{2}", month):
                return self._send(400, b'{"error":"bad month"}', "application/json")
            try:
                body = json.dumps(board_data(month), ensure_ascii=False).encode("utf-8")
                return self._send(200, body, "application/json; charset=utf-8")
            except (HTTPError, URLError, OSError, ValueError) as e:
                msg = {"error": f"داده از داشبورد فروش ({SALES_API}) خوانده نشد: {e}"}
                return self._send(502, json.dumps(msg, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        self._send(404, b"not found", "text/plain")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    import socket
    ips = sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1"})
    shown = [f"http://{ip}:{PORT}" for ip in ips] if HOST == "0.0.0.0" else [f"http://{HOST}:{PORT}"]
    print("Hybrid board: " + "  ".join(shown) + f"  (data: {SALES_API})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
