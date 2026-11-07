"""کش «داده قبلی فوراً، نسخه تازه در پس‌زمینه» (stale-while-revalidate) برای گزارش‌های سنگین SQL.

- تا وقتی داده تازه است (کمتر از ttl ثانیه)، همان برمی‌گردد.
- بعد از انقضا، داده قبلی فوراً برمی‌گردد و نسخه تازه در یک رشته پس‌زمینه ساخته می‌شود؛
  پس هیچ کاربری منتظر کوئری چندده‌ثانیه‌ای نمی‌ماند.
- فقط وقتی هنوز هیچ داده‌ای نیست (اولین بار بعد از راه‌اندازی) درخواست منتظر ساخت می‌ماند؛
  اگر چند درخواست هم‌زمان برسند، کوئری فقط یک بار اجرا می‌شود و بقیه منتظر همان می‌مانند.
- refresh=True همیشه همین الان دوباره می‌سازد (دکمه «به‌روزرسانی»).

استفاده: cache و lock همان دیکشنری و قفل فعلی هر سرویس‌اند و مقدار هر کلید (زمان، داده) است.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Hashable

logger = logging.getLogger(__name__)

_registry_lock = threading.Lock()
_refreshing: set[tuple[int, Hashable]] = set()
_key_locks: dict[tuple[int, Hashable], threading.Lock] = {}


def _key_lock(cache_id: int, key: Hashable) -> threading.Lock:
    with _registry_lock:
        return _key_locks.setdefault((cache_id, key), threading.Lock())


def swr_get(
    cache: dict,
    lock: Any,
    key: Hashable,
    ttl: float,
    loader: Callable[[], Any],
    *,
    refresh: bool = False,
    keep: Callable[[Any], bool] = lambda value: True,
    clock: Callable[[], float] = time.time,
) -> Any:
    """مقدار کش‌شده‌ی key؛ بعد از انقضا داده قبلی را برمی‌گرداند و در پس‌زمینه دوباره می‌سازد.

    keep(value) تعیین می‌کند نتیجه ذخیره شود یا نه (مثلاً فقط status == "success")."""
    if ttl <= 0:  # کش خاموش (مثلاً در تست‌ها)
        return loader()
    full_key = (id(cache), key)
    if not refresh:
        with lock:
            hit = cache.get(key)
        if hit is not None:
            if clock() - hit[0] < ttl:
                return hit[1]
            _refresh_in_background(cache, lock, key, loader, keep, clock)
            return hit[1]
    # هنوز داده‌ای نیست (یا refresh): یک بار بساز؛ درخواست‌های هم‌زمان منتظر همین یکی می‌مانند
    with _key_lock(*full_key):
        if not refresh:
            with lock:
                hit = cache.get(key)
            if hit is not None:
                return hit[1]
        value = loader()
        if keep(value):
            with lock:
                cache[key] = (clock(), value)
        return value


def _refresh_in_background(cache, lock, key, loader, keep, clock) -> None:
    full_key = (id(cache), key)
    with _registry_lock:
        if full_key in _refreshing:
            return
        _refreshing.add(full_key)

    def run() -> None:
        try:
            with _key_lock(*full_key):
                value = loader()
            if keep(value):
                with lock:
                    cache[key] = (clock(), value)
        except Exception:  # noqa: BLE001 — داده قبلی می‌ماند؛ دفعه بعد دوباره امتحان می‌شود
            logger.exception("background refresh failed for %s", key)
        finally:
            with _registry_lock:
                _refreshing.discard(full_key)

    threading.Thread(target=run, name=f"swr-refresh-{key}", daemon=True).start()
