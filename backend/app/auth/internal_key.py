"""کلید مشترک سرویس‌های داخلی (بک‌اند مالی ↔ بک‌اند فروش).

بک‌اند فروش (sales/backend) فقط کاربر واردشده را می‌پذیرد؛ فراخوانی‌های سرور-به-سرور بک‌اند مالی
(Agentهای فروش، گزارش توزیع) با این کلید در هدر X-Exir-Internal-Key عبور می‌کنند.
مقدار از EXIR_INTERNAL_KEY یا فایل «.exir_internal_key» ریشه مخزن خوانده می‌شود و اگر نبود ساخته می‌شود.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

HEADER = "X-Exir-Internal-Key"
KEY_FILE = Path(__file__).resolve().parents[3] / ".exir_internal_key"


@lru_cache(maxsize=1)
def internal_key() -> str:
    env = os.environ.get("EXIR_INTERNAL_KEY", "").strip()
    if env:
        return env
    try:
        with open(KEY_FILE, "x", encoding="utf-8") as f:
            key = secrets.token_urlsafe(32)
            f.write(key)
            return key
    except FileExistsError:
        return KEY_FILE.read_text(encoding="utf-8").strip()


def internal_headers() -> dict[str, str]:
    return {HEADER: internal_key()}
